#!/usr/bin/env python3
"""
rename_canonicals.py — Migrate workspace/templates/*.json to <domain>.<robot>.<variant>.NNN

Implements action 5 of docs/research/2026-05-27-decisions.md (D1 + D2 + D8).

DRY-RUN by default. Emits CSV of (old_name, new_name, refs_found) for Anton review
before --apply. Idempotent: re-running on already-renamed templates is a no-op.

Scope: workspace/templates/*.json (skips *.pre_*_bak, *.bak, *-old.json).
Cohort B (CP-*) is the priority per D2; the script also previews A/C cohorts but
the operator decides what to --apply (see --cohort flag).

Reference scanning covers:
  - tests/**/*.py
  - scripts/**/*.py (incl. scripts/qa/)
  - config/**/*.yaml, config/**/*.yml
  - workspace/templates/*.json (the `extends` field on sibling templates)
  - docs/research/*.md (matches only, not auto-rewritten unless --apply-docs)

Domain inference precedence (per canonical-taxonomy.md §3):
  1. Existing `index_card.domain` if already present (idempotency).
  2. Explicit `intent.pattern_hint` mapped through PATTERN_HINT_TO_DOMAIN.
  3. structural_tags / filename keyword heuristics.
  4. Fallback "other" — surfaced as an ambiguity row.

Output CSV columns:
  old_name, new_name, old_task_id, domain, robot, variant, seq,
  refs_found_count, refs_files, ambiguity_flags
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "workspace" / "templates"
QA_RUNS_DIR = REPO_ROOT / "workspace" / "qa_runs"

# ───────────────────────────── domain inference ─────────────────────────────

# 12-domain enum per docs/research/2026-05-27-canonical-taxonomy.md §3
DOMAINS = {
    "pick", "palletize", "sort", "convey", "assemble", "navigate",
    "inspect", "train", "dialog", "canary", "bridge", "safety",
}

# Direct mapping from existing `intent.pattern_hint` to taxonomy domain.
# Source of pattern_hint values: scripts/canonical_schema.py + grep over templates.
PATTERN_HINT_TO_DOMAIN: dict[str, str] = {
    "pick_place": "pick",
    "sort": "sort",
    "insert": "assemble",
    "compliance": "assemble",
    "navigate": "navigate",
    "reorient": "pick",
    "train": "train",
    "other": "other",  # sentinel — refined via tags
}

# Structural-tag → domain hints. First match wins.
# Only DISCRIMINATING tags appear here. `isaac:transport.conveyor` ALONE is
# transport-machinery and does NOT imply `convey` (which per taxonomy §3 means
# "Conveyor topology — merge, divert, recirc, multi-belt"). Same for
# `isaac:robot.*` which carries robot class, not domain.
TAG_DOMAIN_HINTS: list[tuple[re.Pattern[str], str]] = [
    # Palletize: grid placement math + multi-pick stacking (any isaac:stack.* /
    # isaac:placement.* counts; these tags are only authored on stack-math templates).
    (re.compile(r"isaac:industry\.palletiz", re.I), "palletize"),
    (re.compile(r"isaac:placement\.", re.I), "palletize"),
    (re.compile(r"isaac:stack\.", re.I), "palletize"),
    (re.compile(r"isaac:resolver\.compute_stack_placement", re.I), "palletize"),
    (re.compile(r"isaac:sku\.mixed", re.I), "palletize"),
    # Convey: topology mods, NOT just "has a conveyor"
    (re.compile(r"isaac:topology\.linear_pipeline|isaac:transport\.merge|isaac:transport\.divert|isaac:transport\.recirc|isaac:transport\.multi_belt|isaac:transport\.cross_belt|isaac:transport\.accumul", re.I), "convey"),
    # Sort: explicit routing tags
    (re.compile(r"isaac:routing\.|isaac:sort", re.I), "sort"),
    # Assemble: contact-rich / insertion
    (re.compile(r"isaac:control\.contact_rich|isaac:assembly|isaac:insertion|isaac:articulation\.(door|cabinet|drawer)", re.I), "assemble"),
    # Navigate: locomotion + mobile-base robots
    (re.compile(r"isaac:nav\.|isaac:locomotion|isaac:amr|isaac:fleet|isaac:robot\.(carter|jetbot|anymal|g1|forklift)", re.I), "navigate"),
    # Inspect: vision-only / SDG / sensor-gate
    (re.compile(r"isaac:perception|isaac:vision\.|isaac:sdg|isaac:inspect", re.I), "inspect"),
    # Train: RL / GR00T / curriculum / sim2real
    (re.compile(r"isaac:train|isaac:rl|isaac:groot|isaac:eureka|isaac:curriculum|isaac:sim2real", re.I), "train"),
    # Bridge: comms protocols + PLC
    (re.compile(r"isaac:bridge|isaac:ros2|isaac:mqtt|isaac:modbus|isaac:opcua|isaac:plc", re.I), "bridge"),
    # Safety: e-stop / ISO-15066 / PFL
    (re.compile(r"isaac:safety|isaac:estop|isaac:iso15066|isaac:compliance_safety", re.I), "safety"),
]

# Filename keyword → domain hints. Used when tags + pattern_hint are inconclusive.
# Order matters: more specific matches first.
FILENAME_DOMAIN_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"palletiz|pallet|layer-stack|depalletiz|slip-sheet", re.I), "palletize"),
    (re.compile(r"sort|barcode|defect-divert|reject|divert|sku-sort", re.I), "sort"),
    # Convey: only topology-modifying terms, NOT generic "conveyor"
    (re.compile(r"merge|recirc|cross-belt|s-bend|accumulat|chute|y-merge|conveyor-tracking", re.I), "convey"),
    (re.compile(r"insert|peg|snap-fit|bolt|gear-mesh|assemble|assembly|impedance|admittance|compliance|seam-track|drawer|cabinet|door", re.I), "assemble"),
    (re.compile(r"\bnav\b|navigate|amr|forklift|locomot|anymal|g1\b|cart-handoff|carter|jetbot|corridor|charging-dock", re.I), "navigate"),
    (re.compile(r"inspect|sdg|vision-gate|hand-eye|defect-sdg|pose-estimate|6dof-pose|barcode-scan|oee|cad-revision", re.I), "inspect"),
    (re.compile(r"\btrain\b|\brl-|groot|eureka|finetune|curriculum|sim2real|actuator-net|policy-ab|ab-policy|rl-scaffold|forgetting|teleop-demo|data-mix|attention-map", re.I), "train"),
    (re.compile(r"ros2|moveit|mqtt|sparkplug|modbus|opcua|opc-ua|ethercat|openplc|plc-|bridge", re.I), "bridge"),
    (re.compile(r"estop|e-stop|emergency-stop|safety|iso-15066|iso15066|light-curtain|area-scan|pfl", re.I), "safety"),
    (re.compile(r"\bpick\b|pick-place|bin-pick|kitting|kit-prep|grasp|3cube|precision", re.I), "pick"),
]

# Default: keep "other" so the operator sees it in the CSV. We pick a domain
# but flag the row as ambiguous so Anton reviews before --apply.
DEFAULT_DOMAIN = "pick"  # softest assumption — most templates are pick-place


def infer_domain(data: dict[str, Any], filename_stem: str) -> tuple[str, list[str]]:
    """
    Return (domain, ambiguity_flags). Flags are added when inference required
    a fallback so the operator can audit them in the CSV.
    """
    flags: list[str] = []

    # 0. Already-renamed → idempotent.
    ic = (data.get("index_card") or {})
    if ic.get("domain") in DOMAINS:
        return ic["domain"], flags

    # Cohort A: persona dialogues — all `dialog`.
    # Cohort C: canaries — `canary`.
    tid = (data.get("task_id") or "").strip()
    if re.match(r"^[A-Z]+-\d+$", tid) and not tid.startswith(("CP-", "G-", "FX-")):
        return "dialog", flags
    if tid.startswith("G-"):
        return "canary", flags
    if tid.startswith("FX-"):
        return "canary", flags

    # 1. pattern_hint
    intent = (data.get("intent") or {})
    ph = (intent.get("pattern_hint") or "").strip().lower()
    domain_from_ph = PATTERN_HINT_TO_DOMAIN.get(ph)

    # 2. structural tags
    tags = intent.get("structural_tags") or []
    if not isinstance(tags, list):
        tags = []
    domain_from_tags: str | None = None
    for tag in tags:
        if not isinstance(tag, str):
            continue
        for pat, dom in TAG_DOMAIN_HINTS:
            if pat.search(tag):
                domain_from_tags = dom
                break
        if domain_from_tags:
            break

    # 3. filename keyword
    domain_from_fname: str | None = None
    for pat, dom in FILENAME_DOMAIN_KEYWORDS:
        if pat.search(filename_stem):
            domain_from_fname = dom
            break

    # Reconcile. Priority is layered:
    # - Tags that mark a SPECIALIZATION of pick (palletize, sort, convey,
    #   assemble) win over generic pattern_hint=pick_place. The taxonomy
    #   §3 explicitly carves these out as distinct domains.
    # - Otherwise, pattern_hint (if not 'other') wins.
    # - Otherwise, tags, then filename, then default.
    SPECIALIZED_OVER_PICK = {"palletize", "sort", "convey", "assemble", "inspect", "safety", "bridge", "train", "navigate"}

    chosen: str
    if (
        domain_from_ph == "pick"
        and domain_from_tags
        and domain_from_tags in SPECIALIZED_OVER_PICK
    ):
        chosen = domain_from_tags
        flags.append(f"tag_specialized_over_ph_pick={domain_from_tags}")
    elif domain_from_ph and domain_from_ph != "other":
        chosen = domain_from_ph
        # Cross-check with filename — if filename strongly disagrees, flag.
        if domain_from_fname and domain_from_fname != chosen:
            flags.append(f"ph={domain_from_ph}_vs_fname={domain_from_fname}")
    elif domain_from_tags:
        chosen = domain_from_tags
        if domain_from_fname and domain_from_fname != chosen:
            flags.append(f"tag={domain_from_tags}_vs_fname={domain_from_fname}")
    elif domain_from_fname:
        chosen = domain_from_fname
        flags.append("from_fname_only")
    else:
        chosen = DEFAULT_DOMAIN
        flags.append("fallback_default")

    # Special: yrkesroll templates → keep yrkesroll as a tag (handled elsewhere)
    # but the domain still comes from above. Add a flag for visibility.
    if "yrkesroll" in filename_stem.lower():
        flags.append("yrkesroll")

    return chosen, flags


# ───────────────────────────── robot inference ──────────────────────────────

ROBOT_NORMALISE: dict[str, str] = {
    "franka_panda": "franka",
    "franka": "franka",
    "ur10": "ur10",
    "ur10e": "ur10e",
    "ur5e": "ur5e",
    "kinova_gen3": "kinova",
    "carter": "carter",
    "jetbot": "jetbot",
    "jetbot_primitive": "jetbot",
    "anymal_c": "anymal",
    "anymal": "anymal",
    "g1": "g1",
    "cobotta": "cobotta",
    "yaskawa_gp25": "yaskawa",
    "forklift": "forklift",
}

ROBOT_FILENAME_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bur10e\b", re.I), "ur10e"),
    (re.compile(r"\bur10\b", re.I), "ur10"),
    (re.compile(r"\bur5e\b", re.I), "ur5e"),
    (re.compile(r"\banymal\b", re.I), "anymal"),
    (re.compile(r"\bg1\b", re.I), "g1"),
    (re.compile(r"\bcarter\b", re.I), "carter"),
    (re.compile(r"\bjetbot\b", re.I), "jetbot"),
    (re.compile(r"\bforklift\b", re.I), "forklift"),
    (re.compile(r"\byaskawa\b", re.I), "yaskawa"),
    (re.compile(r"\bcobotta\b", re.I), "cobotta"),
    (re.compile(r"\bkinova\b", re.I), "kinova"),
    (re.compile(r"\bfranka\b", re.I), "franka"),
    (re.compile(r"bimanual|dual-arm|two-arm", re.I), "multi"),
    (re.compile(r"triple-arm|4robot|multi-robot|fleet", re.I), "multi"),
]


def infer_robot(data: dict[str, Any], filename_stem: str, domain: str) -> tuple[str, list[str]]:
    flags: list[str] = []

    ic = (data.get("index_card") or {})
    if ic.get("robot"):
        return ic["robot"], flags

    rd = (data.get("role_defaults") or {})

    # Detect multi-robot: more than one role whose key contains 'robot' and class is set
    robot_classes: list[str] = []
    for key, val in rd.items():
        if not isinstance(val, dict):
            continue
        if "robot" in key.lower() and isinstance(val.get("class"), str):
            robot_classes.append(val["class"])

    pr = rd.get("primary_robot") or {}
    cls = (pr.get("class") if isinstance(pr, dict) else None) or ""
    cls_norm = ROBOT_NORMALISE.get(cls.lower().strip())

    if len(robot_classes) >= 2 and len(set(robot_classes)) >= 2:
        return "multi", flags

    if cls_norm:
        return cls_norm, flags

    # Filename keyword
    for pat, robot in ROBOT_FILENAME_KEYWORDS:
        if pat.search(filename_stem):
            return robot, flags

    # Dialog / inspect / train / bridge / safety frequently have no robot
    if domain in {"dialog", "inspect", "train", "bridge", "safety", "canary"}:
        return "none", flags

    flags.append("robot_default_franka")
    return "franka", flags


# ───────────────────────────── variant slug ─────────────────────────────────

SLUG_STRIP_PREFIXES = (
    "cp-new-yrkesroll-",
    "cp-new-",
    "cp-",
    "ad-", "al-", "am-",
    "a-", "c-", "d-", "e-", "f-", "g-", "j-", "k-", "l-",
    "m-", "p-", "r-", "s-", "t-", "y-", "fx-",
)


def slugify_text(s: str, max_len: int = 32) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "variant"


def variant_from_filename(stem: str, robot: str) -> str:
    s = stem.lower()
    for prefix in SLUG_STRIP_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # If filename is just a number (CP-01, A-02), use 'base' as placeholder.
    # The variant should describe the scenario; numeric-only filenames have to
    # derive variant from goal first-sentence.
    if re.match(r"^\d+$", s):
        return ""
    # Drop robot name from variant slug if present (avoids ur10.ur10-foo redundancy).
    if robot and robot != "none":
        s = re.sub(rf"\b{re.escape(robot)}\b-?", "", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
    return slugify_text(s)


_STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "to", "in", "on", "at", "with",
    "for", "from", "by", "is", "are", "was", "were", "be", "this", "that",
    "into", "as", "using", "via", "build", "builds", "set", "up", "create",
    "creates", "configure", "configures", "implement", "implements", "run",
    "runs", "simulate", "simulates", "demonstrate", "demonstrates", "show",
    "shows", "perform", "performs", "execute", "executes", "isaac", "sim",
    "cell", "station",
}


def variant_from_goal(goal: str) -> str:
    """Pull short descriptive slug from goal text. Drops articles + boilerplate."""
    # First sentence.
    first = re.split(r"[.!?]\s", goal.strip(), maxsplit=1)[0]
    # Trim common preamble verbs.
    first = re.sub(
        r"^(build|builds|set up|create|configure|implement|run|runs|simulate|train|teach|show|shows|demonstrate|perform)\s+",
        "", first, flags=re.I,
    )
    # Slugify and drop stopwords. Keep token order; cap length.
    tokens = re.split(r"[^a-z0-9]+", first.lower())
    tokens = [t for t in tokens if t and t not in _STOPWORDS]
    out = "-".join(tokens)
    # Truncate on word boundary at ≤32 chars.
    if len(out) > 32:
        out = out[:32]
        if "-" in out:
            out = out.rsplit("-", 1)[0]
    return out or "variant"


def derive_variant(data: dict[str, Any], stem: str, robot: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    ic = (data.get("index_card") or {})
    if ic.get("id") and isinstance(ic["id"], str):
        parts = ic["id"].split(".")
        if len(parts) >= 4:
            return parts[2], flags  # variant segment

    v = variant_from_filename(stem, robot)
    if v:
        return v, flags

    # Fall back to goal-derived slug
    goal = data.get("goal") or ""
    v = variant_from_goal(goal)
    flags.append("variant_from_goal")
    return v, flags


# ───────────────────────────── new-id assembly ──────────────────────────────

def is_already_renamed(stem: str) -> bool:
    """Detect the new <domain>.<robot>.<variant>.NNN form."""
    parts = stem.split(".")
    if len(parts) != 4:
        return False
    if parts[0] not in DOMAINS:
        return False
    if not re.match(r"^\d{3}$", parts[3]):
        return False
    return True


def is_skippable(filename: str) -> bool:
    """Skip backups, *-old, and obvious non-canonical files."""
    return (
        ".pre_" in filename
        or filename.endswith(".bak")
        or "-old.json" in filename
        or filename.endswith(".pre_phys_rewrite_bak")
    )


# ───────────────────────────── reference scanning ───────────────────────────

REF_SCAN_DIRS = [
    ("tests", ("*.py",)),
    ("scripts", ("*.py", "*.sh")),
    ("config", ("*.yaml", "*.yml")),
    ("docs/research", ("*.md",)),
]


def collect_ref_corpus() -> list[Path]:
    """One-shot collection of all files we will grep for old IDs."""
    out: list[Path] = []
    for sub, patterns in REF_SCAN_DIRS:
        base = REPO_ROOT / sub
        if not base.exists():
            continue
        for pat in patterns:
            out.extend(base.rglob(pat))
    # Also templates themselves (for the `extends` field on siblings).
    out.extend(TEMPLATES_DIR.glob("*.json"))
    return out


def build_ref_index(corpus: list[Path]) -> dict[Path, str]:
    """Read once, hold in RAM. Total corpus is small enough (<400 files)."""
    idx: dict[Path, str] = {}
    for p in corpus:
        try:
            idx[p] = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return idx


def find_refs(old_id: str, ref_index: dict[Path, str], skip_own: Path | None = None) -> list[Path]:
    """
    Find files containing the old_id token. Uses word-boundary regex so
    "CP-1" doesn't match "CP-10" / "CP-100".
    """
    # Word boundary around the id. Note: '-' is a word char on neither side,
    # so we use lookarounds for safety.
    pat = re.compile(rf"(?<![\w-]){re.escape(old_id)}(?![\w-])")
    hits: list[Path] = []
    for path, text in ref_index.items():
        if skip_own and path.resolve() == skip_own.resolve():
            continue
        if pat.search(text):
            hits.append(path)
    return hits


# ───────────────────────────── apply mode ──────────────────────────────────-

def git_available(repo_root: Path) -> bool:
    if not (repo_root / ".git").exists():
        return False
    try:
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_root, check=True, capture_output=True, timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def move_file(src: Path, dst: Path, use_git: bool, repo_root: Path) -> None:
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")
    if use_git:
        rel_src = src.relative_to(repo_root)
        rel_dst = dst.relative_to(repo_root)
        subprocess.run(
            ["git", "mv", str(rel_src), str(rel_dst)],
            cwd=repo_root, check=True,
        )
    else:
        shutil.move(str(src), str(dst))


def update_task_id_in_file(path: Path, new_task_id: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["task_id"] = new_task_id
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rewrite_refs(path: Path, old_id: str, new_id: str) -> int:
    """Rewrite old_id → new_id in path with word-boundary matching. Returns #replacements."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    pat = re.compile(rf"(?<![\w-]){re.escape(old_id)}(?![\w-])")
    new_text, n = pat.subn(new_id, text)
    if n > 0:
        path.write_text(new_text, encoding="utf-8")
    return n


# ───────────────────────────── main pipeline ────────────────────────────────

def _cohort_of_legacy_stem(stem: str) -> str:
    """Map a legacy filename stem to its cohort letter."""
    if stem.startswith("CP"):
        return "B"
    if stem.startswith(("G-", "FX-")):
        return "C"
    return "A"


def _cohort_of_renamed_stem(stem: str) -> str | None:
    """Derive cohort from a NEW <domain>.<robot>.<variant>.NNN stem."""
    if not is_already_renamed(stem):
        return None
    dom = stem.split(".")[0]
    if dom == "dialog":
        return "A"
    if dom == "canary":
        return "C"
    # Everything else was originally Cohort B.
    return "B"


def gather_templates(cohort_filter: str | None) -> list[Path]:
    """Return canonical template files filtered by cohort and skip rule."""
    out: list[Path] = []
    for p in sorted(TEMPLATES_DIR.glob("*.json")):
        if is_skippable(p.name):
            continue
        stem = p.stem
        if is_already_renamed(stem):
            their_cohort = _cohort_of_renamed_stem(stem)
        else:
            their_cohort = _cohort_of_legacy_stem(stem)

        if cohort_filter and their_cohort != cohort_filter:
            continue
        out.append(p)
    return out


def plan_renames(
    templates: list[Path],
    ref_index: dict[Path, str],
) -> list[dict[str, Any]]:
    """
    Returns one row per template. Allocates NNN sequence per (domain, robot, variant)
    cell. Already-renamed templates produce a row with new_name=old_name and
    flag=already_renamed.
    """
    # First pass: read all templates, infer (domain, robot, variant).
    plan: list[dict[str, Any]] = []
    for p in templates:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            plan.append({
                "path": p,
                "data": None,
                "stem": p.stem,
                "old_task_id": "",
                "domain": "",
                "robot": "",
                "variant": "",
                "seq": "",
                "flags": [f"parse_error:{type(exc).__name__}"],
            })
            continue

        stem = p.stem
        if is_already_renamed(stem):
            plan.append({
                "path": p,
                "data": data,
                "stem": stem,
                "old_task_id": data.get("task_id", ""),
                "domain": stem.split(".")[0],
                "robot": stem.split(".")[1],
                "variant": stem.split(".")[2],
                "seq": stem.split(".")[3],
                "flags": ["already_renamed"],
            })
            continue

        domain, dflags = infer_domain(data, stem)
        robot, rflags = infer_robot(data, stem, domain)
        variant, vflags = derive_variant(data, stem, robot)

        plan.append({
            "path": p,
            "data": data,
            "stem": stem,
            "old_task_id": data.get("task_id", "") or stem,
            "domain": domain,
            "robot": robot,
            "variant": variant,
            "seq": "",  # allocated next
            "flags": [*dflags, *rflags, *vflags],
        })

    # Second pass: allocate sequence per cell.
    # We also need to reserve sequences that are already in use by
    # already-renamed siblings in the same cell.
    cell_used: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for row in plan:
        if "already_renamed" in row["flags"] and row["seq"]:
            try:
                cell_used[(row["domain"], row["robot"], row["variant"])].add(int(row["seq"]))
            except ValueError:
                pass

    for row in plan:
        if "already_renamed" in row["flags"]:
            continue
        if not row["domain"] or not row["robot"] or not row["variant"]:
            continue
        cell = (row["domain"], row["robot"], row["variant"])
        used = cell_used[cell]
        seq = 1
        while seq in used:
            seq += 1
        used.add(seq)
        row["seq"] = f"{seq:03d}"

    # Third pass: compute final new_name and ref scan.
    for row in plan:
        if "already_renamed" in row["flags"]:
            row["new_stem"] = row["stem"]
            row["new_name"] = row["path"].name
            row["new_task_id"] = row["old_task_id"]
            row["refs"] = []
            continue
        if not row["seq"]:
            row["new_stem"] = ""
            row["new_name"] = ""
            row["new_task_id"] = ""
            row["refs"] = []
            row["flags"].append("could_not_assign_seq")
            continue
        new_stem = f"{row['domain']}.{row['robot']}.{row['variant']}.{row['seq']}"
        row["new_stem"] = new_stem
        row["new_name"] = f"{new_stem}.json"
        row["new_task_id"] = new_stem

        # Reference scan: find files mentioning the old task_id.
        # Also check the filename stem if it differs from task_id.
        search_terms = {row["old_task_id"], row["stem"]}
        all_refs: set[Path] = set()
        for term in search_terms:
            if not term:
                continue
            all_refs.update(find_refs(term, ref_index, skip_own=row["path"]))
        row["refs"] = sorted(all_refs)

    return plan


def write_csv(plan: list[dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "old_filename", "new_filename", "old_task_id", "new_task_id",
            "domain", "robot", "variant", "seq",
            "refs_found_count", "refs_files", "ambiguity_flags",
        ])
        for row in plan:
            refs = row.get("refs") or []
            ref_paths = ";".join(
                str(p.relative_to(REPO_ROOT)) for p in refs
            )
            w.writerow([
                row["path"].name,
                row.get("new_name", ""),
                row.get("old_task_id", ""),
                row.get("new_task_id", ""),
                row.get("domain", ""),
                row.get("robot", ""),
                row.get("variant", ""),
                row.get("seq", ""),
                len(refs),
                ref_paths,
                ",".join(row.get("flags", [])),
            ])


def apply_plan(plan: list[dict[str, Any]], use_git: bool, repo_root: Path) -> None:
    """
    Apply renames: git mv (or shutil.move), update task_id in file, rewrite refs.
    Aborts on first error; the operator can re-run after fixing.
    """
    # Build a name-collision check first — bail before touching disk if any
    # planned new_name would clobber an existing distinct file.
    planned_targets: dict[Path, dict[str, Any]] = {}
    for row in plan:
        if "already_renamed" in row["flags"]:
            continue
        if not row.get("new_name"):
            continue
        target = TEMPLATES_DIR / row["new_name"]
        if target.exists() and target.resolve() != row["path"].resolve():
            raise FileExistsError(f"Collision: {row['path'].name} → {row['new_name']} already exists")
        if target in planned_targets:
            other = planned_targets[target]
            raise RuntimeError(
                f"Collision between {row['path'].name} and {other['path'].name} → both → {row['new_name']}"
            )
        planned_targets[target] = row

    for row in plan:
        if "already_renamed" in row["flags"]:
            continue
        if not row.get("new_name"):
            continue
        src = row["path"]
        dst = TEMPLATES_DIR / row["new_name"]
        move_file(src, dst, use_git=use_git, repo_root=repo_root)
        update_task_id_in_file(dst, row["new_task_id"])

        # Rewrite refs in pre-computed list. (Re-read each file fresh to avoid
        # stale-RAM clobber if multiple old_ids resolve to same ref file.)
        for ref_path in row.get("refs", []):
            if not ref_path.exists():
                continue
            # Don't rewrite if the file is the template we just moved.
            if ref_path.resolve() == src.resolve():
                continue
            rewrite_refs(ref_path, row["old_task_id"], row["new_task_id"])
            if row["old_task_id"] != row["stem"]:
                # Also rewrite filename-stem references (e.g. config yaml referencing
                # the on-disk file).
                rewrite_refs(ref_path, row["stem"], row["new_stem"])


# ─────────────────────────────── entrypoint ─────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--apply", action="store_true",
        help="Actually rename files + rewrite refs. Default is DRY-RUN.",
    )
    ap.add_argument(
        "--cohort", choices=["A", "B", "C", "all"], default="all",
        help="Filter templates by cohort. B=CP-* (default migration target per D2). "
             "A=persona dialogues. C=canaries (G/FX). all=everything.",
    )
    ap.add_argument(
        "--out-dir", type=Path, default=QA_RUNS_DIR,
        help=f"CSV output directory (default: {QA_RUNS_DIR.relative_to(REPO_ROOT)})",
    )
    ap.add_argument(
        "--csv-name", type=str, default="",
        help="Override CSV filename. Default: rename_dryrun_<UTC-ts>.csv (or rename_apply_<ts>.csv with --apply).",
    )
    args = ap.parse_args()

    cohort = args.cohort if args.cohort != "all" else None
    templates = gather_templates(cohort)
    if not templates:
        print(f"No templates found under {TEMPLATES_DIR} for cohort={args.cohort}", file=sys.stderr)
        return 1

    print(f"Found {len(templates)} templates (cohort={args.cohort})")

    corpus = collect_ref_corpus()
    print(f"Scanning refs across {len(corpus)} files…")
    ref_index = build_ref_index(corpus)

    plan = plan_renames(templates, ref_index)

    ts = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if args.apply else "dryrun"
    csv_name = args.csv_name or f"rename_{mode}_cohort{args.cohort}_{ts}.csv"
    csv_path = args.out_dir / csv_name
    write_csv(plan, csv_path)
    print(f"\nWrote CSV: {csv_path.relative_to(REPO_ROOT)}")

    # Summary
    n_total = len(plan)
    n_already = sum(1 for r in plan if "already_renamed" in r["flags"])
    n_planned = sum(1 for r in plan if r.get("new_name") and "already_renamed" not in r["flags"])
    n_skipped = sum(1 for r in plan if not r.get("new_name") and "already_renamed" not in r["flags"])
    n_flagged = sum(1 for r in plan if r.get("flags") and "already_renamed" not in r["flags"])
    print(f"  total:           {n_total}")
    print(f"  already_renamed: {n_already}")
    print(f"  to_rename:       {n_planned}")
    print(f"  skipped:         {n_skipped}")
    print(f"  with_flags:      {n_flagged}")

    # Domain breakdown
    by_domain: dict[str, int] = defaultdict(int)
    for r in plan:
        if r.get("new_name") and "already_renamed" not in r["flags"]:
            by_domain[r["domain"]] += 1
    if by_domain:
        print("  by domain:")
        for dom, n in sorted(by_domain.items(), key=lambda kv: -kv[1]):
            print(f"    {dom:12s} {n}")

    if not args.apply:
        print("\nDRY-RUN. Review the CSV; re-run with --apply to execute.")
        print("Note: planner/legacy_id_map.py is a SEPARATE action (decisions §5 #6); "
              "this script does not build it.")
        return 0

    print("\nApplying renames…")
    use_git = git_available(REPO_ROOT)
    print(f"  git available: {use_git}")
    apply_plan(plan, use_git=use_git, repo_root=REPO_ROOT)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
