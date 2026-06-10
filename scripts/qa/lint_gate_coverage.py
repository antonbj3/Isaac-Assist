#!/usr/bin/env python3
"""P0-18 gate-coverage lint — report workpieces excluded from the gate.

The honest-delivery gate (``simulate_traversal_check``) only grades the cubes
listed in a template's ``simulate_args.cube_paths`` (or the single
``cube_path``). A template can therefore game the gate by AUTHORING a hard
cube in its scene code but OMITTING it from ``cube_paths`` — the sim never
tracks it, so its non-delivery is invisible and the template reports green.

This lint loads a canonical template JSON and reports every workpiece-like
prim it can find in the scene definition that is MISSING from
``simulate_args.cube_paths``. It is REPORT-ONLY — it never edits a template.

Workpiece-like prims are gathered from two sources:

  1. SCENE CODE — ``create_prim(prim_path="...Cube...")`` /
     ``DynamicCuboid(prim_path=...)`` / ``FixedCuboid(...)`` /
     ``add_cube(...)`` whose path matches a cube-ish pattern
     (``/Cube_<n>``, ``...Cube...``, ``Workpiece``, ``Part_<n>``, ``Brick``).
  2. ``role_defaults.workpieces[*].path`` — the canonical role contract.

Ground / Table / Bin / Conveyor / Stand / Pillar / Wall and other
structural prims are NOT workpieces and are excluded by a stop-list even
when their prim_type is "Cube".

Exit code: 0 if every template fully covers its workpieces (or no
workpieces found), 1 if any template has an uncovered workpiece. Use
``--json`` for machine-readable output.

Usage:
    python3 scripts/qa/lint_gate_coverage.py workspace/templates/CP-12.json
    python3 scripts/qa/lint_gate_coverage.py workspace/templates/*.json
    python3 scripts/qa/lint_gate_coverage.py --json workspace/templates/
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Set


# Prim-path leaf tokens that are scene STRUCTURE, never a tracked workpiece,
# even if authored as a "Cube" prim_type (Ground/Table planes etc).
_STRUCTURAL = (
    "ground", "floor", "table", "bin", "binstand", "conveyor", "belt",
    "stand", "pillar", "wall", "cell", "light", "dome", "camera", "robot",
    "franka", "ur10", "ur5", "kinova", "tower", "tray", "shelf", "rack",
    "base", "platform", "fixture", "tote", "pallet", "housing", "dispenser",
    "gantry", "frame", "mount", "stage", "room", "sensor", "target", "bench",
)

# Leaf tokens that POSITIVELY mark a tracked workpiece.
_WORKPIECE_TOKENS = ("cube", "workpiece", "part_", "brick", "block", "widget", "peg")

# Code-call patterns that author a prim at a literal prim_path=... .
_PRIM_PATH_RE = re.compile(
    r'(?:create_prim|DynamicCuboid|FixedCuboid|add_cube|GeometryPrim|RigidPrim)'
    r'\s*\(\s*[^)]*?prim_path\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)


def _leaf(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1].lower()


def _is_workpiece_path(path: str) -> bool:
    """True if the prim path looks like a tracked workpiece, not structure."""
    leaf = _leaf(path)
    if any(tok in leaf for tok in _STRUCTURAL):
        return False
    return any(tok in leaf for tok in _WORKPIECE_TOKENS)


def _gather_code_workpieces(code: str) -> Set[str]:
    out: Set[str] = set()
    if not code:
        return out
    for m in _PRIM_PATH_RE.finditer(code):
        path = m.group(1)
        if _is_workpiece_path(path):
            out.add(path)
    return out


def _gather_role_workpieces(template: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    rd = template.get("role_defaults") or {}
    wps = rd.get("workpieces")
    if isinstance(wps, list):
        for w in wps:
            if isinstance(w, dict):
                p = w.get("path")
                if isinstance(p, str) and p:
                    out.add(p)
            elif isinstance(w, str):
                out.add(w)
    return out


def _gate_cube_paths(template: Dict[str, Any]) -> Set[str]:
    sa = template.get("simulate_args") or {}
    out: Set[str] = set()
    cps = sa.get("cube_paths")
    if isinstance(cps, list):
        out.update(str(p) for p in cps if p)
    elif isinstance(cps, str) and cps:
        out.add(cps)
    cp = sa.get("cube_path")
    if isinstance(cp, str) and cp:
        out.add(cp)
    return out


def lint_template(template: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    """Pure-ish per-template result (template dict in, report dict out)."""
    has_gate = bool(template.get("simulate_args"))
    code_wp = _gather_code_workpieces(template.get("code") or "")
    role_wp = _gather_role_workpieces(template)
    authored = code_wp | role_wp
    covered = _gate_cube_paths(template)
    missing = sorted(authored - covered)
    return {
        "file": path,
        "task_id": template.get("task_id"),
        "has_gate": has_gate,
        "authored_workpieces": sorted(authored),
        "code_workpieces": sorted(code_wp),
        "role_workpieces": sorted(role_wp),
        "gate_cube_paths": sorted(covered),
        "missing_from_gate": missing,
        # Only flag templates that actually run the gate; a template with no
        # simulate_args is not (yet) gated and is out of scope for this lint.
        "ok": (not has_gate) or (len(missing) == 0),
    }


def _iter_template_files(paths: List[str]) -> List[str]:
    files: List[str] = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith(".json"):
                    files.append(os.path.join(p, name))
        else:
            files.append(p)
    return files


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Report workpieces excluded from the honest-delivery gate.")
    ap.add_argument("paths", nargs="+", help="Template JSON file(s) or directory of templates.")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    ap.add_argument("--quiet", action="store_true", help="Only print templates with uncovered workpieces.")
    args = ap.parse_args(argv)

    results: List[Dict[str, Any]] = []
    for f in _iter_template_files(args.paths):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                tpl = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            results.append({"file": f, "error": str(exc), "ok": True})
            continue
        results.append(lint_template(tpl, f))

    n_bad = sum(1 for r in results if not r.get("ok"))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            if r.get("error"):
                print(f"SKIP  {r['file']}: {r['error']}")
                continue
            if args.quiet and r["ok"]:
                continue
            if not r["ok"]:
                print(f"UNCOVERED  {r['file']}  ({r.get('task_id')})")
                print(f"           authored: {r['authored_workpieces']}")
                print(f"           gate:     {r['gate_cube_paths']}")
                print(f"           MISSING:  {r['missing_from_gate']}")
            elif not args.quiet:
                tag = "no-gate" if not r["has_gate"] else "ok"
                print(f"{tag:9} {r['file']}  workpieces={len(r['authored_workpieces'])} covered")
        print(f"\n{n_bad} template(s) with workpieces excluded from the gate "
              f"out of {len(results)} scanned.")

    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
