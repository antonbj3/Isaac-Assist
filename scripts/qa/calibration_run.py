#!/usr/bin/env python3
"""calibration_run — dual-verification calibration sweep [P1-15].

For each sample template: (1) extract a static LAYOUT (pure, no Kit) and get
static_eyes pair verdicts; (2) run the physics function gate (gate_one.py,
live Kit, serial); (3) record both to a JSONL + print the per-pair confusion
summary. This MEASURES the static-vs-physics divergence bands — the
precondition for ever activating dual_verify's SKIP path (the ~3.5-4x
throughput claim stays a hypothesis until this data exists).

Extraction is best-effort: cube positions from settle_state.cubes (the settle
truth) falling back to create_prim parses; robot from robot_wizard(...) or
add_reference; destination from create_bin(...); drop from drop_target=[...].
Missing pieces are recorded as extraction_gaps — a pair with no data is
"unknown", never silently passed.

Usage:
    python3 scripts/qa/calibration_run.py CP-70 CP-01 ... [--out FILE]
    python3 scripts/qa/calibration_run.py --static-only CP-70   # no Kit
Kit must be up for the gate leg. Runs are SERIAL (Kit single-tenant).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from service.isaac_assist_service.multimodal import static_eyes  # noqa: E402
from service.isaac_assist_service.multimodal.dual_verify import static_pair_verdicts  # noqa: E402

_ROBOT_RE = re.compile(
    r'robot_wizard\(\s*robot_name="(?P<fam>[a-z0-9_]+)",\s*dest_path="(?P<path>[^"]+)",\s*position=\[(?P<pos>[^\]]+)\]',
    re.S)
_ADDREF_RE = re.compile(
    r'add_reference\(prim_path="(?P<path>/World/[A-Za-z0-9_]+)",\s*reference_path="[^"]*?/(?P<fam>ur10|ur10e|ur5e|franka)[a-z_]*\.usd"')
_BIN_RE = re.compile(
    r'create_bin\(\s*prim_path="(?P<path>[^"]+)",\s*position=\[(?P<pos>[^\]]+)\],\s*size=\[(?P<size>[^\]]+)\]')
_DROP_RE = re.compile(r'drop_target=\[(?P<pos>[^\]]+)\]')
_PRIM_POS_RE = re.compile(
    r'create_prim\(prim_path="(?P<path>/World/[A-Za-z0-9_]+)",\s*prim_type="Cube",\s*position=\[(?P<pos>[^\]]+)\],\s*size=(?P<size>[0-9.]+)')


def _vec(s: str):
    return [float(x.strip()) for x in s.split(",")]


def template_to_layout(tpl: dict) -> tuple[dict, list]:
    """Best-effort static layout from a template. Returns (layout, gaps)."""
    gaps: list = []
    code = (tpl.get("code") or "") + (tpl.get("code_template") or "")
    sa = tpl.get("simulate_args") or {}

    robots = []
    m = _ROBOT_RE.search(code)
    if m:
        robots.append({"path": m.group("path"), "family": m.group("fam"),
                       "base": _vec(m.group("pos"))})
    else:
        m2 = _ADDREF_RE.search(code)
        if m2:
            # add_reference robots: position often set separately; assume table z=0.75
            robots.append({"path": m2.group("path"), "family": m2.group("fam"),
                           "base": [0.0, 0.0, 0.75]})
            gaps.append("robot_base_assumed")
        else:
            gaps.append("no_robot_found")

    # dynamic feed? cubes SPAWN far on the belt and RIDE to the pick zone —
    # static reach on the spawn position is a documented false-FAIL (spec §6.4)
    feed = any(kw in code.lower() for kw in
               ("create_conveyor", "carousel", "rotary", "belt", "indexer"))

    objects = []
    settle = (tpl.get("settle_state") or {}).get("cubes") or {}
    for path, pos in settle.items():
        objects.append({"path": path, "position": list(pos),
                        "asset_name": "cube_medium", "dynamic_feed": feed})
    if not settle:
        for pm in _PRIM_POS_RE.finditer(code):
            objects.append({"path": pm.group("path"), "position": _vec(pm.group("pos")),
                            "asset_name": "cube_medium", "dynamic_feed": feed})
        if not objects:
            gaps.append("no_workpieces_found")

    for bm in _BIN_RE.finditer(code):
        pos, size = _vec(bm.group("pos")), _vec(bm.group("size"))
        objects.append({"path": bm.group("path"), "position": pos,
                        "bbox": [[pos[0] - size[0] / 2, pos[1] - size[1] / 2, pos[2]],
                                 [pos[0] + size[0] / 2, pos[1] + size[1] / 2, pos[2] + size[2]]]})

    picks = list(sa.get("cube_paths") or ([sa["cube_path"]] if sa.get("cube_path") else []))
    if not picks:
        picks = [o["path"] for o in objects if "Cube" in o["path"]]
        if picks:
            gaps.append("picks_inferred")

    places = []
    dest = sa.get("target_path")
    dm = _DROP_RE.search(code)
    if dest:
        place = {"target_path": dest}
        if dm:
            place["drop_target"] = _vec(dm.group("pos"))
        else:
            # no explicit drop_target (destination_path-only controller call):
            # the controller drops over the destination -> derive bin-center-top,
            # mirroring the controller's implicit behavior.
            dest_obj = next((o for o in objects if o["path"] == dest and "bbox" in o), None)
            if dest_obj:
                lo, hi = dest_obj["bbox"]
                place["drop_target"] = [round((lo[0] + hi[0]) / 2, 3),
                                        round((lo[1] + hi[1]) / 2, 3),
                                        round(hi[2] + 0.10, 3)]
                gaps.append("drop_target_derived")
            else:
                gaps.append("no_drop_target")
        places.append(place)
    else:
        gaps.append("no_destination")

    return {"robots": robots, "objects": objects, "picks": picks, "places": places}, gaps


def _gate_run(name: str, timeout: int = 900) -> dict:
    proc = subprocess.run([sys.executable, str(REPO / "scripts/qa/gate_one.py"), name],
                          capture_output=True, text=True, timeout=timeout)
    out = proc.stdout + proc.stderr
    m = re.search(r"GATE success=(\w+)", out)
    return {"gate_success": (m.group(1) == "True") if m else None,
            "gate_raw": out[-300:] if m is None else ""}


def main() -> int:
    args = sys.argv[1:]
    static_only = "--static-only" in args
    out_path = REPO / "data/calibration/calib_run.jsonl"
    if "--out" in args:
        i = args.index("--out"); out_path = Path(args[i + 1]); del args[i:i + 2]
    names = [a for a in args if not a.startswith("--")]
    if not names:
        print(__doc__); return 2

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                         capture_output=True, text=True).stdout.strip()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    confusion: dict = {}

    for name in names:
        tpl = json.load(open(REPO / f"workspace/templates/{name}.json"))
        layout, gaps = template_to_layout(tpl)
        report = static_eyes.run(layout)
        pairs = {p: v.status for p, v in static_pair_verdicts(report).items()}
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "template": name, "sha": sha, "static": pairs,
               "static_verdict": report.verdict, "extraction_gaps": gaps}
        if not static_only:
            row.update(_gate_run(name))
            for pair, status in pairs.items():
                key = f"{pair}:{status}|gate:{row['gate_success']}"
                confusion[key] = confusion.get(key, 0) + 1
        with open(out_path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(f"{name}: static={report.verdict} pairs={pairs} gaps={gaps}"
              + ("" if static_only else f" gate={row['gate_success']}"), flush=True)

    if confusion:
        print("\nCONFUSION:", json.dumps(confusion, indent=2))
    print(f"\nrows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
