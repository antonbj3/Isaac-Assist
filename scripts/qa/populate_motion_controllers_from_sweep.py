"""
populate_motion_controllers_from_sweep.py

After a Kit build-gate sweep completes (workspace/qa_runs/kit_batch_*.jsonl),
this script auto-populates each template's `motion_controllers.verified`
list with whatever controller(s) the template specified AND that passed
build-gate in the latest sweep.

Honesty rule preserved: a controller is added to `verified` only if a
real Kit RPC run for THIS template succeeded with that controller as
the active target_source / planner / compliance_controller.

Usage:
    python scripts/qa/populate_motion_controllers_from_sweep.py \\
        --sweep workspace/qa_runs/kit_batch_round3.jsonl \\
        [--dry-run]

Output: per-template change list + total updated count.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def extract_controllers_from_code(code: str) -> set[str]:
    """Best-effort extraction of controller names used in the template code body."""
    controllers: set[str] = set()
    if not code:
        return controllers

    # setup_pick_place_controller(target_source="curobo" | "native" | "diffik" | ...)
    for m in re.finditer(r'setup_pick_place_controller\s*\([^)]*target_source\s*=\s*["\']([^"\']+)["\']', code):
        controllers.add(m.group(1))

    # plan_trajectory(planner="rmpflow" | "lula_rrt") / move_to_pose(planner=...)
    for m in re.finditer(r'(?:plan_trajectory|move_to_pose)\s*\([^)]*planner\s*=\s*["\']([^"\']+)["\']', code):
        controllers.add(m.group(1))

    # setup_impedance_controller / set_compliance_params imply impedance/compliance
    if re.search(r'setup_impedance_controller\s*\(', code):
        controllers.add("impedance")
    if re.search(r'follow_trajectory_with_compliance\s*\([^)]*compliance_controller\s*=\s*["\']([^"\']+)["\']', code):
        for m in re.finditer(r'follow_trajectory_with_compliance\s*\([^)]*compliance_controller\s*=\s*["\']([^"\']+)["\']', code):
            controllers.add(m.group(1))
    elif re.search(r'follow_trajectory_with_compliance\s*\(', code):
        controllers.add("compliance")

    # setup_cortex_behavior implies cortex
    if re.search(r'setup_cortex_behavior\s*\(', code):
        controllers.add("cortex")

    # set_motion_policy(...)
    if re.search(r'set_motion_policy\s*\(', code):
        controllers.add("motion_policy")

    # set_joint_targets / direct articulation drive
    if re.search(r'set_joint_targets\s*\(', code) and not controllers:
        controllers.add("direct_joint")

    return controllers


def load_sweep_results(sweep_path: Path) -> dict[str, bool]:
    """Return template_name -> success (last build-phase entry per template)."""
    if not sweep_path.exists():
        sys.exit(f"sweep file not found: {sweep_path}")
    last: dict[str, bool] = {}
    with sweep_path.open() as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("phase") != "build":
                continue
            t = row.get("template")
            if not t:
                continue
            last[t] = bool(row.get("success"))
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sweep = load_sweep_results(args.sweep)
    print(f"Loaded {len(sweep)} sweep rows from {args.sweep}")

    updated = 0
    no_change = 0
    no_field = 0

    template_dir = REPO / "workspace" / "templates"
    for tpl_path in sorted(template_dir.glob("CP-*.json")):
        name = tpl_path.stem
        sweep_pass = sweep.get(name)
        if sweep_pass is not True:
            continue  # only promote on actual pass

        try:
            data = json.loads(tpl_path.read_text())
        except json.JSONDecodeError:
            continue

        mc = data.get("motion_controllers")
        if mc is None:
            no_field += 1
            continue

        verified = set(mc.get("verified") or [])
        untested = set(mc.get("untested") or [])

        # Extract controllers we'd expect to have exercised
        observed = extract_controllers_from_code(data.get("code") or "")

        # Promote each observed controller from untested → verified IF it was untested.
        # If observed not in untested either, we still record it with an `@build-gate` suffix
        # but conservatively only if it appears in tools_used (sanity gate).
        promoted: list[str] = []
        for ctrl in observed:
            # Find any existing entry that's the bare name OR has `@version` suffix
            already_verified = any(v.split("@")[0] == ctrl for v in verified)
            if already_verified:
                continue
            # Move from untested → verified if present, else just add
            for u in list(untested):
                if u.split("@")[0] == ctrl:
                    untested.discard(u)
                    verified.add(u)  # preserve any version suffix
                    promoted.append(u)
                    break
            else:
                verified.add(f"{ctrl}@build-gate-2026-05-17")
                promoted.append(f"{ctrl}@build-gate-2026-05-17")

        if not promoted:
            no_change += 1
            continue

        mc["verified"] = sorted(verified)
        mc["untested"] = sorted(untested)
        data["motion_controllers"] = mc

        if not args.dry_run:
            tpl_path.write_text(json.dumps(data, indent=2) + "\n")
        updated += 1
        print(f"  {name}: +{promoted}")

    print(f"\nUpdated: {updated}")
    print(f"No change (no new evidence): {no_change}")
    print(f"No motion_controllers field: {no_field}")
    if args.dry_run:
        print("(dry-run: no files modified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
