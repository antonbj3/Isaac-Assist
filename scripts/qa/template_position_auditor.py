"""
template_position_auditor.py — scan all canonical templates and flag those
where cube/source positions are outside robot reach. Outputs a structured
report ranking templates by severity.

Usage:
    python scripts/qa/template_position_auditor.py
    python scripts/qa/template_position_auditor.py --templates CP-13,CP-18
    python scripts/qa/template_position_auditor.py --reach-margin 0.05

Pure static analysis — no Kit RPC, no sweeps, only stdlib.

Severity:
  CRITICAL — every workpiece is out-of-reach
  MAJOR    — > 50% of workpieces out-of-reach
  MARGINAL — at least one workpiece 0-15 cm beyond reach
  OK       — all workpieces inside reach * (1 + margin)
  UNKNOWN  — could not determine robot or workpiece positions
  SKIPPED  — template has no robot or no cube-like workpieces
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "workspace" / "templates"
OUTPUT_DIR = REPO_ROOT / "workspace" / "qa_runs"

# Reach per robot family in metres. Conservative numbers — match what the
# function-gate uses for reach validation. Franka 0.85 m, UR10/UR10e 1.20 m,
# Cobotta 0.95 m. (Numbers come from the spec block in the task description.)
ROBOT_REACH: Dict[str, float] = {
    "franka": 0.85,
    "franka_panda": 0.85,
    "panda": 0.85,
    "ur3": 0.50,
    "ur3e": 0.50,
    "ur5": 0.85,
    "ur5e": 0.85,
    "ur10": 1.20,
    "ur10e": 1.20,
    "ur16": 0.90,
    "ur16e": 0.90,
    "kinova_gen3": 0.90,
    "kinova": 0.90,
    "cobotta": 0.95,
    "denso_cobotta": 0.95,
    "iiwa": 0.80,
    "kuka_iiwa": 0.80,
    "kuka": 0.80,
    "jaco": 0.90,
    "abb_yumi": 0.50,
    "yumi": 0.50,
}

# Default reach for unknown robot families — pessimistic, treats unknown as
# Franka-class so we don't silently accept far-out-of-reach cubes.
DEFAULT_REACH_M = 0.85

# Margin above reach where we still tolerate a cube (5% by default).
DEFAULT_REACH_MARGIN = 0.05

# How far past reach (m) before a cube goes from MARGINAL to MAJOR/CRITICAL.
MARGINAL_BAND_M = 0.15

# Regex for `create_prim(...)` calls — captures the kwargs body so we can
# parse prim_path / prim_type / position. Multi-line aware via re.DOTALL.
CREATE_PRIM_RE = re.compile(
    r"create_prim\s*\((?P<body>[^()]*?(?:\([^()]*\)[^()]*?)*?)\)",
    re.DOTALL,
)

# Capture an assignment like `key = value` inside the create_prim body where
# value is either a string literal, a list, or another simple atom.
KWARG_RE = re.compile(
    r"(\w+)\s*=\s*("
    r"\"[^\"]*\"|'[^']*'"  # string literal
    r"|\[[^\[\]]*\]"  # flat list
    r"|[-+]?\d+(?:\.\d+)?"  # number
    r"|True|False|None"
    r")"
)

# Loop heuristic: `for i, x in enumerate([VAL_LIST]):` where VAL_LIST is a
# list of numeric x-coordinates and the inner body uses
# `position=[x, Y, Z, ...]` literally.
LOOP_HEADER_RE = re.compile(
    r"for\s+\w+\s*,\s*(?P<var>\w+)\s+in\s+enumerate\s*\(\s*(?P<list>\[[^\[\]]*\])\s*\)\s*:"
)
LOOP_POSITION_RE = re.compile(
    r"position\s*=\s*\[\s*(?P<x>[^,\]]+)\s*,\s*(?P<y>[^,\]]+)\s*,\s*(?P<z>[^,\]]+)\s*\]"
)
LOOP_PRIM_PATH_RE = re.compile(
    r"prim_path\s*=\s*(?:path|f?\"(?P<f>[^\"]+)\"|f?'(?P<g>[^']+)')"
)


def parse_list_literal(text: str) -> Optional[List[float]]:
    """Parse a flat list literal like `[1.0, 2, -0.4]` → [1.0, 2.0, -0.4]."""
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return None
    inner = text[1:-1].strip()
    if not inner:
        return []
    parts = [p.strip() for p in inner.split(",")]
    out: List[float] = []
    for p in parts:
        if not p:
            continue
        try:
            out.append(float(p))
        except ValueError:
            return None
    return out


def parse_string_literal(text: str) -> Optional[str]:
    """Parse a single-quote or double-quote string literal."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("\"", "'"):
        return text[1:-1]
    return None


def extract_kwargs(body: str) -> Dict[str, Any]:
    """Best-effort kwargs extraction from a function-call body."""
    out: Dict[str, Any] = {}
    for m in KWARG_RE.finditer(body):
        key, val = m.group(1), m.group(2).strip()
        s = parse_string_literal(val)
        if s is not None:
            out[key] = s
            continue
        lst = parse_list_literal(val)
        if lst is not None:
            out[key] = lst
            continue
        # numeric / boolean / None
        if val == "True":
            out[key] = True
        elif val == "False":
            out[key] = False
        elif val == "None":
            out[key] = None
        else:
            try:
                out[key] = float(val) if "." in val else int(val)
            except ValueError:
                out[key] = val
    return out


def looks_like_cube_path(path: str) -> bool:
    """Heuristic — does this prim_path look like a workpiece cube?"""
    if not path:
        return False
    leaf = path.rsplit("/", 1)[-1].lower()
    if leaf.startswith("ground") or leaf == "ground":
        return False
    if "table" in leaf or "pallet" in leaf or "bin" in leaf:
        return False
    if leaf.startswith("conveyor") or leaf == "conveyorbelt":
        return False
    if leaf.startswith("sensor") or "sensor" in leaf:
        return False
    # explicit cube names — common conventions seen in templates
    if leaf.startswith("cube") or leaf.startswith("cube_"):
        return True
    if "cube" in leaf:
        return True
    # Path-style /World/Workpiece_N
    if leaf.startswith("workpiece") or leaf.startswith("item_") or leaf.startswith("part"):
        return True
    return False


def is_static_workpiece(path: str) -> bool:
    """Filter out structural prims (ground/table/bin) by path-suffix."""
    if not path:
        return True
    leaf = path.rsplit("/", 1)[-1].lower()
    structural_terms = (
        "ground",
        "table",
        "wall",
        "pallet",
        "bin",
        "rack",
        "shelf",
        "fixture",
        "dome",
        "light",
        "stand",
        "tray",
        "pedestal",
        "platform",
        "frame",
        "cell",
        "sensor",
        "camera",
        "robot",
        "gripper",
    )
    return any(term in leaf for term in structural_terms)


def find_create_prim_positions(code: str) -> List[Dict[str, Any]]:
    """Walk every create_prim(...) call in the code, return its kwargs."""
    out: List[Dict[str, Any]] = []
    for m in CREATE_PRIM_RE.finditer(code):
        body = m.group("body")
        kwargs = extract_kwargs(body)
        if "prim_path" in kwargs and "position" in kwargs:
            out.append(kwargs)
    return out


def find_loop_positions(code: str) -> List[Dict[str, Any]]:
    """Expand for-loops of the shape `for i, x in enumerate([...]):` so that
    cubes spawned inside a loop are captured. Yields synthetic entries with a
    prim_path label (the f-string body) and position [x, Y, Z]."""
    out: List[Dict[str, Any]] = []
    lines = code.split("\n")
    i = 0
    while i < len(lines):
        m = LOOP_HEADER_RE.search(lines[i])
        if not m:
            i += 1
            continue
        var = m.group("var")
        xs = parse_list_literal(m.group("list"))
        # Capture loop body — indentation-based
        body_indent: Optional[int] = None
        j = i + 1
        body_lines: List[str] = []
        while j < len(lines):
            line = lines[j]
            stripped = line.lstrip()
            if not stripped:
                body_lines.append(line)
                j += 1
                continue
            indent = len(line) - len(stripped)
            if body_indent is None:
                body_indent = indent
            if indent < body_indent:
                break
            body_lines.append(line)
            j += 1
        body_text = "\n".join(body_lines)
        # Find position=[var, Y, Z] inside loop body
        pos_match = LOOP_POSITION_RE.search(body_text)
        path_match = LOOP_PRIM_PATH_RE.search(body_text)
        if pos_match and xs is not None:
            x_expr = pos_match.group("x").strip()
            y_expr = pos_match.group("y").strip()
            z_expr = pos_match.group("z").strip()
            try:
                y_val = float(y_expr)
                z_val = float(z_expr)
            except ValueError:
                # Y or Z is non-literal; skip
                i = j
                continue
            # Only handle the case where x is the loop variable
            if x_expr == var:
                # Build a synthetic path label for each iteration
                label = "loop_cube"
                if path_match:
                    label = path_match.group("f") or path_match.group("g") or "loop_cube"
                for idx, x_val in enumerate(xs):
                    # Substitute {i+1} / {i} into label if present
                    label_resolved = label.replace("{i+1}", str(idx + 1)).replace(
                        "{i}", str(idx)
                    )
                    out.append(
                        {
                            "prim_path": label_resolved,
                            "position": [x_val, y_val, z_val],
                            "_source": "loop_enumerate",
                        }
                    )
        i = j
    return out


def normalize_robot_class(cls: Optional[str]) -> Optional[str]:
    if not cls:
        return None
    c = cls.strip().lower()
    # strip common suffixes
    if c in ROBOT_REACH:
        return c
    # try fuzzy match
    for key in ROBOT_REACH:
        if key in c or c in key:
            return key
    return None


def get_robot_reach(robot_class: Optional[str]) -> Tuple[float, str]:
    norm = normalize_robot_class(robot_class)
    if norm and norm in ROBOT_REACH:
        return ROBOT_REACH[norm], norm
    return DEFAULT_REACH_M, "unknown_default"


def xy_distance(a: List[float], b: List[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def extract_robot_info(template: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull robot path/class/position from role_defaults.primary_robot,
    falling back to scanning role_defaults for any robot-like role."""
    rd = template.get("role_defaults") or {}
    # Try primary_robot first
    candidate_keys = ["primary_robot", "robot", "primary_arm"]
    for key in candidate_keys:
        info = rd.get(key)
        if isinstance(info, dict) and "position" in info:
            return {
                "role": key,
                "path": info.get("path"),
                "class": info.get("class"),
                "position": list(info.get("position") or []),
            }
    # Try any role whose value looks like a robot
    for role_name, info in rd.items():
        if not isinstance(info, dict):
            continue
        if "class" in info and "position" in info and isinstance(info["position"], list):
            cls = (info.get("class") or "").lower()
            if any(k in cls for k in ROBOT_REACH):
                return {
                    "role": role_name,
                    "path": info.get("path"),
                    "class": info.get("class"),
                    "position": list(info.get("position") or []),
                }
    return None


_WORKPIECE_ROLE_HINTS = (
    "workpiece",
    "workpieces",
    "cube",
    "cubes",
    "source",
    "sources",
    "part",
    "parts",
    "item",
    "items",
    "box",
    "boxes",
    "carton",
    "cartons",
    "package",
    "packages",
    "good_workpiece",
    "good_workpieces",
    "bad_workpiece",
    "defective_workpiece",
    "defective_workpieces",
    "reject_workpiece",
    "reject_workpieces",
    "payload",
    "payloads",
)


def _role_name_looks_workpiece(role_name: str) -> bool:
    rn = role_name.lower()
    return any(hint in rn for hint in _WORKPIECE_ROLE_HINTS)


def extract_workpieces_from_role_defaults(
    template: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Pick up workpieces as declared in role_defaults — these are the
    authoritative positions when present. Handles the standard
    `workpieces: [...]` form plus per-cube variants seen across templates
    (good_workpieces, defective_workpiece, sources, etc.)."""
    rd = template.get("role_defaults") or {}
    out: List[Dict[str, Any]] = []

    for role_name, value in rd.items():
        if not _role_name_looks_workpiece(role_name):
            continue
        # List of workpiece dicts
        if isinstance(value, list):
            for w in value:
                if not isinstance(w, dict):
                    continue
                pos = w.get("position")
                if isinstance(pos, list) and len(pos) >= 2:
                    out.append(
                        {
                            "path": w.get("path") or f"unnamed_{role_name}",
                            "position": list(pos),
                            "_source": f"role_defaults.{role_name}",
                        }
                    )
            continue
        # Single workpiece dict
        if isinstance(value, dict):
            pos = value.get("position")
            if isinstance(pos, list) and len(pos) >= 2:
                out.append(
                    {
                        "path": value.get("path") or f"unnamed_{role_name}",
                        "position": list(pos),
                        "_source": f"role_defaults.{role_name}",
                    }
                )
    return out


def extract_workpieces_from_code(code: str) -> List[Dict[str, Any]]:
    """Static parse — find every cube-like create_prim, plus loop-spawned
    cubes."""
    out: List[Dict[str, Any]] = []
    for entry in find_create_prim_positions(code):
        path = entry.get("prim_path", "")
        prim_type = entry.get("prim_type", "")
        position = entry.get("position")
        if not isinstance(position, list) or len(position) < 2:
            continue
        if prim_type and prim_type != "Cube":
            # Only Cube prim_type for static check — DomeLight/Xform skipped
            continue
        if is_static_workpiece(path):
            continue
        if not looks_like_cube_path(path):
            continue
        out.append(
            {
                "path": path,
                "position": list(position),
                "_source": "create_prim_static",
            }
        )
    for entry in find_loop_positions(code):
        path = entry.get("prim_path", "")
        position = entry.get("position")
        if not isinstance(position, list) or len(position) < 2:
            continue
        if is_static_workpiece(path):
            continue
        if not looks_like_cube_path(path):
            continue
        out.append(
            {
                "path": path,
                "position": list(position),
                "_source": entry.get("_source", "loop"),
            }
        )
    return out


def merge_workpieces(
    role_wps: List[Dict[str, Any]], code_wps: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Prefer role_defaults positions; fall back to code-extracted positions
    for paths not declared in role_defaults."""
    seen_paths = set()
    merged: List[Dict[str, Any]] = []
    for w in role_wps:
        merged.append(w)
        seen_paths.add(w["path"])
    for w in code_wps:
        if w["path"] in seen_paths:
            continue
        merged.append(w)
        seen_paths.add(w["path"])
    return merged


def classify_template(
    template: Dict[str, Any], reach_margin: float
) -> Dict[str, Any]:
    task_id = template.get("task_id", "unknown")
    robot = extract_robot_info(template)
    if not robot:
        return {
            "task_id": task_id,
            "severity": "SKIPPED",
            "reason": "no_robot_in_role_defaults",
            "robot": None,
            "workpieces": [],
        }
    if not robot["position"] or len(robot["position"]) < 2:
        return {
            "task_id": task_id,
            "severity": "UNKNOWN",
            "reason": "robot_position_missing",
            "robot": robot,
            "workpieces": [],
        }
    role_wps = extract_workpieces_from_role_defaults(template)
    # Prefer role_defaults — these are authoritative positions, declared in
    # the same template as the robot pos. Falling back to code parsing pulls
    # in synthetic loop_cube entries that double-count with no real benefit.
    if role_wps:
        workpieces = role_wps
    else:
        code_wps = extract_workpieces_from_code(template.get("code") or "")
        workpieces = merge_workpieces([], code_wps)

    # Detect conveyor / heap / mobile-handoff / carousel patterns so the
    # reviewer can tell apart "real bug" (fixed pick station out of reach)
    # from "intentional" (cubes start outside reach and arrive into reach
    # via a transport mechanism).
    rd = template.get("role_defaults") or {}
    conveyor_role_present = any(
        "conveyor" in k.lower() or "belt" in k.lower() for k in rd.keys()
    )
    heap_role_present = any(
        "heap" in k.lower() or "pile" in k.lower() or "spawn" in k.lower()
        for k in rd.keys()
    )
    mobile_handoff_role_present = any(
        any(
            term in k.lower()
            for term in ("forklift", "amr", "agv", "cart", "trolley", "mobile")
        )
        for k in rd.keys()
    )
    carousel_role_present = any(
        any(
            term in k.lower()
            for term in ("carousel", "rotary", "turntable", "indexer")
        )
        for k in rd.keys()
    )
    structural_tags = (template.get("intent") or {}).get("structural_tags") or []
    has_conveyor_tag = any("transport.conveyor" in t for t in structural_tags)
    has_amr_tag = any("amr" in t.lower() or "mobile" in t.lower() for t in structural_tags)
    intentional_oor = (
        conveyor_role_present
        or has_conveyor_tag
        or heap_role_present
        or mobile_handoff_role_present
        or carousel_role_present
        or has_amr_tag
    )
    if not workpieces:
        return {
            "task_id": task_id,
            "severity": "SKIPPED",
            "reason": "no_cube_workpieces_found",
            "robot": robot,
            "workpieces": [],
        }
    reach, robot_norm = get_robot_reach(robot.get("class"))
    threshold = reach * (1.0 + reach_margin)
    flagged_workpieces: List[Dict[str, Any]] = []
    out_of_reach_count = 0
    marginal_count = 0
    for w in workpieces:
        pos = w["position"]
        dist = xy_distance(robot["position"], pos)
        overrun = dist - reach  # negative means inside reach
        flag = "OK"
        if dist > threshold:
            if 0 < overrun <= MARGINAL_BAND_M:
                flag = "MARGINAL"
                marginal_count += 1
                out_of_reach_count += 1
            else:
                flag = "OUT_OF_REACH"
                out_of_reach_count += 1
        elif overrun > 0:
            # within margin but slightly above raw reach — note but don't fail
            flag = "WITHIN_MARGIN"
        flagged_workpieces.append(
            {
                "path": w["path"],
                "position": pos,
                "source": w.get("_source", "unknown"),
                "xy_distance_m": round(dist, 4),
                "overrun_m": round(overrun, 4),
                "flag": flag,
            }
        )
    total = len(workpieces)
    severity = "OK"
    if out_of_reach_count == total and total > 0:
        severity = "CRITICAL"
    elif out_of_reach_count > total / 2 and out_of_reach_count > 0:
        severity = "MAJOR"
    elif out_of_reach_count >= 1:
        severity = "MARGINAL" if out_of_reach_count == marginal_count else "MAJOR"
    return {
        "task_id": task_id,
        "severity": severity,
        "robot": {
            "role": robot["role"],
            "path": robot["path"],
            "class": robot.get("class"),
            "class_normalized": robot_norm,
            "position": robot["position"],
            "reach_m": reach,
            "threshold_m": round(threshold, 4),
        },
        "workpieces": flagged_workpieces,
        "summary": {
            "total": total,
            "out_of_reach": out_of_reach_count,
            "marginal": marginal_count,
        },
        "intentional_oor_pattern": intentional_oor,
        "patterns": {
            "has_conveyor_role": conveyor_role_present,
            "has_conveyor_tag": has_conveyor_tag,
            "has_heap_role": heap_role_present,
            "has_mobile_handoff_role": mobile_handoff_role_present,
            "has_carousel_role": carousel_role_present,
            "has_amr_tag": has_amr_tag,
        },
    }


def load_template(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {
            "_parse_error": f"{type(exc).__name__}: {exc}",
            "task_id": path.stem,
        }


def select_template_paths(filter_ids: Optional[List[str]]) -> List[Path]:
    """Return CP-* templates, optionally filtered by an ID list. Excludes
    *.pre_*_bak.json backups."""
    all_paths = sorted(TEMPLATES_DIR.glob("CP-*.json"))
    # Filter out backup variants and pre-rewrite variants
    cleaned = [
        p for p in all_paths if ".pre_" not in p.name and ".bak" not in p.name
    ]
    if not filter_ids:
        return cleaned
    wanted = {f.strip() for f in filter_ids if f.strip()}
    return [p for p in cleaned if p.stem in wanted]


def build_markdown_report(
    results: List[Dict[str, Any]],
    parse_errors: List[Dict[str, Any]],
    reach_margin: float,
) -> str:
    by_severity: Dict[str, List[Dict[str, Any]]] = {
        "CRITICAL": [],
        "MAJOR": [],
        "MARGINAL": [],
        "OK": [],
        "UNKNOWN": [],
        "SKIPPED": [],
    }
    for r in results:
        sev = r.get("severity", "UNKNOWN")
        by_severity.setdefault(sev, []).append(r)

    total = len(results)
    lines: List[str] = []
    lines.append("# Template position audit")
    lines.append("")
    lines.append(
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    )
    lines.append("")
    lines.append(f"Total templates scanned: {total}")
    lines.append(f"Parse errors: {len(parse_errors)}")
    lines.append(f"Reach margin: {reach_margin * 100:.0f}%")
    lines.append("")
    lines.append("## Reading this report")
    lines.append("")
    lines.append(
        "This auditor checks the **starting position** of every cube-like"
        " workpiece against the robot's reach. Many conveyor templates"
        " intentionally spawn cubes outside reach so the belt carries them"
        " *into* the pick zone — these surface as CRITICAL/MAJOR but are"
        " not bugs."
    )
    lines.append("")
    lines.append(
        "**True bugs** are CRITICAL/MAJOR templates with `intentional_oor_pattern=false`"
        " — fixed-station picks where the cube is unreachable at start-of-frame."
        " These appear in the **Likely real bugs** section below."
    )
    lines.append("")
    lines.append("## Severity counts")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("| --- | ---: |")
    for sev in ("CRITICAL", "MAJOR", "MARGINAL", "OK", "UNKNOWN", "SKIPPED"):
        lines.append(f"| {sev} | {len(by_severity.get(sev, []))} |")
    lines.append("")

    # Likely real bugs — non-conveyor, non-heap templates that still flag
    real_bugs: List[Dict[str, Any]] = []
    intentional: List[Dict[str, Any]] = []
    for r in by_severity.get("CRITICAL", []) + by_severity.get("MAJOR", []):
        if r.get("intentional_oor_pattern"):
            intentional.append(r)
        else:
            real_bugs.append(r)
    lines.append("## Likely real bugs (no conveyor / heap pattern)")
    lines.append("")
    if not real_bugs:
        lines.append("None — every flagged template uses a conveyor or heap spawn pattern.")
    else:
        lines.append(
            f"{len(real_bugs)} template(s) have cubes out-of-reach at start"
            " AND no conveyor/heap role declared. These are the candidates"
            " most likely to be real positioning bugs."
        )
        lines.append("")
        lines.append("| Task | Severity | Robot | Reach (m) | OOR / Total | Worst overrun (m) |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: |")
        for r in sorted(real_bugs, key=lambda x: (-_severity_rank(x["severity"]), x["task_id"])):
            robot = r.get("robot") or {}
            summary = r.get("summary") or {}
            worst = max(
                (w["overrun_m"] for w in r.get("workpieces", []) if w["flag"] != "OK"),
                default=0.0,
            )
            lines.append(
                f"| {r['task_id']} | {r['severity']} | {robot.get('class_normalized') or 'unknown'} "
                f"| {robot.get('reach_m', 0)} | {summary.get('out_of_reach', 0)}/{summary.get('total', 0)} "
                f"| {worst:.3f} |"
            )
    lines.append("")

    lines.append("## Intentional out-of-reach (conveyor / heap patterns)")
    lines.append("")
    lines.append(
        f"{len(intentional)} template(s) — likely fine; cubes ride the belt"
        " or spawn from a heap zone into reach. Confirm by checking that"
        " the pick sensor / heap pickup zone is itself inside reach."
    )
    lines.append("")

    # Rebuild candidates
    needs_rebuild = by_severity.get("CRITICAL", []) + by_severity.get("MAJOR", [])
    lines.append("## All CRITICAL + MAJOR flags")
    lines.append("")
    if not needs_rebuild:
        lines.append("None.")
    else:
        lines.append("| Task | Severity | Robot | Reach (m) | OOR / Total | Worst overrun (m) |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: |")
        for r in sorted(needs_rebuild, key=lambda x: (-_severity_rank(x["severity"]), x["task_id"])):
            robot = r.get("robot") or {}
            summary = r.get("summary") or {}
            worst = max(
                (w["overrun_m"] for w in r.get("workpieces", []) if w["flag"] != "OK"),
                default=0.0,
            )
            lines.append(
                f"| {r['task_id']} | {r['severity']} | {robot.get('class_normalized') or 'unknown'} "
                f"| {robot.get('reach_m', 0)} | {summary.get('out_of_reach', 0)}/{summary.get('total', 0)} "
                f"| {worst:.3f} |"
            )
    lines.append("")

    lines.append("## MARGINAL templates")
    lines.append("")
    marginal = by_severity.get("MARGINAL", [])
    if not marginal:
        lines.append("None.")
    else:
        lines.append("| Task | Robot | Reach (m) | OOR / Total | Worst overrun (m) |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for r in sorted(marginal, key=lambda x: x["task_id"]):
            robot = r.get("robot") or {}
            summary = r.get("summary") or {}
            worst = max(
                (w["overrun_m"] for w in r.get("workpieces", []) if w["flag"] != "OK"),
                default=0.0,
            )
            lines.append(
                f"| {r['task_id']} | {robot.get('class_normalized') or 'unknown'} "
                f"| {robot.get('reach_m', 0)} | {summary.get('out_of_reach', 0)}/{summary.get('total', 0)} "
                f"| {worst:.3f} |"
            )
    lines.append("")

    lines.append("## Per-template detail (non-OK)")
    lines.append("")
    detail_targets = [
        r
        for r in results
        if r.get("severity") in ("CRITICAL", "MAJOR", "MARGINAL", "UNKNOWN")
    ]
    if not detail_targets:
        lines.append("All scanned templates are OK or SKIPPED.")
    else:
        for r in sorted(detail_targets, key=lambda x: (-_severity_rank(x["severity"]), x["task_id"])):
            robot = r.get("robot") or {}
            lines.append(f"### {r['task_id']} — {r['severity']}")
            lines.append("")
            if r["severity"] == "UNKNOWN":
                lines.append(f"- reason: `{r.get('reason')}`")
                lines.append("")
                continue
            lines.append(
                f"- robot: `{robot.get('class')}` (norm: `{robot.get('class_normalized')}`)"
                f" at `{robot.get('position')}` reach `{robot.get('reach_m')}` m"
            )
            lines.append("")
            lines.append("| Workpiece | Position | xy_dist (m) | overrun (m) | flag |")
            lines.append("| --- | --- | ---: | ---: | --- |")
            for w in r.get("workpieces", []):
                lines.append(
                    f"| `{w['path']}` | `{w['position']}` | {w['xy_distance_m']} "
                    f"| {w['overrun_m']:+.3f} | {w['flag']} |"
                )
            lines.append("")
    lines.append("## Parse errors")
    lines.append("")
    if not parse_errors:
        lines.append("None.")
    else:
        for e in parse_errors:
            lines.append(f"- `{e['file']}`: {e['error']}")
    lines.append("")
    return "\n".join(lines)


_SEVERITY_ORDER = {
    "CRITICAL": 4,
    "MAJOR": 3,
    "MARGINAL": 2,
    "UNKNOWN": 1,
    "OK": 0,
    "SKIPPED": -1,
}


def _severity_rank(sev: str) -> int:
    return _SEVERITY_ORDER.get(sev, 0)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--templates",
        type=str,
        default=None,
        help="Comma-separated list of template IDs (e.g. CP-13,CP-18).",
    )
    parser.add_argument(
        "--reach-margin",
        type=float,
        default=DEFAULT_REACH_MARGIN,
        help="Fractional margin above advertised reach where a cube is still OK.",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="template_position_audit",
        help="Filename stem (without extension) for the report.",
    )
    parser.add_argument(
        "--templates-dir",
        type=str,
        default=str(TEMPLATES_DIR),
        help="Override the templates directory.",
    )
    args = parser.parse_args(argv)

    templates_dir = Path(args.templates_dir)
    if not templates_dir.is_dir():
        print(f"[ERR] templates dir not found: {templates_dir}", file=sys.stderr)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    filter_ids = args.templates.split(",") if args.templates else None
    paths = select_template_paths(filter_ids)
    print(f"Scanning {len(paths)} templates from {templates_dir}")

    results: List[Dict[str, Any]] = []
    parse_errors: List[Dict[str, Any]] = []
    for p in paths:
        tpl = load_template(p)
        if tpl is None:
            parse_errors.append({"file": str(p), "error": "load_returned_none"})
            continue
        if "_parse_error" in tpl:
            parse_errors.append({"file": str(p), "error": tpl["_parse_error"]})
            continue
        try:
            r = classify_template(tpl, args.reach_margin)
            r["_file"] = str(p)
            results.append(r)
        except Exception as exc:  # pragma: no cover — failure-tolerant
            tb = traceback.format_exc(limit=2)
            parse_errors.append(
                {
                    "file": str(p),
                    "error": f"{type(exc).__name__}: {exc}\n{tb}",
                }
            )

    severity_count: Dict[str, int] = {}
    for r in results:
        sev = r.get("severity", "UNKNOWN")
        severity_count[sev] = severity_count.get(sev, 0) + 1

    json_path = OUTPUT_DIR / f"{args.output_prefix}.json"
    md_path = OUTPUT_DIR / f"{args.output_prefix}.md"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "templates_scanned": len(paths),
        "reach_margin": args.reach_margin,
        "severity_counts": severity_count,
        "robot_reach_m": ROBOT_REACH,
        "default_reach_m": DEFAULT_REACH_M,
        "marginal_band_m": MARGINAL_BAND_M,
        "results": results,
        "parse_errors": parse_errors,
    }
    json_path.write_text(json.dumps(payload, indent=2))
    md_path.write_text(build_markdown_report(results, parse_errors, args.reach_margin))

    print("Severity counts:")
    for sev in ("CRITICAL", "MAJOR", "MARGINAL", "OK", "UNKNOWN", "SKIPPED"):
        print(f"  {sev:<9} {severity_count.get(sev, 0)}")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
