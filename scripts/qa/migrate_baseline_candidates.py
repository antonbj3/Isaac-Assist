#!/usr/bin/env python3
"""Generate create_scene_baseline candidates for the baseline cluster and
batch-verify them with migrate_verify [P2-07 wave driver].

Strict-match only: templates whose opening is EXACTLY the canonical
DomeLight(+Ground)+Cell+Table+physics block (89 in corpus today). Variants
stay untouched — they migrate in later waves with their own patterns.

Usage:
    python3 scripts/qa/migrate_baseline_candidates.py CP-03 CP-08 ...
    python3 scripts/qa/migrate_baseline_candidates.py --scan   # list matches
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

PAT = re.compile(
    r'(?:#[^\n]*\n)*'
    r'create_prim\(prim_path="/World/DomeLight", prim_type="DomeLight"\)\n'
    r'set_attribute\(prim_path="/World/DomeLight", attr_name="inputs:intensity", value=(?P<inten>[\d.]+)\)\n'
    r'(?:\n?#[^\n]*\n)*'
    r'(?P<ground>create_prim\(prim_path="/World/Ground", prim_type="Cube", position=\[0, 0, -0\.5\], scale=\[(?P<gs>[\d.]+), [\d.]+, 1\]\)\n'
    r'apply_api_schema\(prim_path="/World/Ground", schema_name="PhysicsCollisionAPI"\)\n)?'
    r'(?:\n?#[^\n]*\n)*'
    r'create_prim\(prim_path="/World/Cell", prim_type="Xform"\)\n'
    r'(?:\n?#[^\n]*\n)*'
    r'create_prim\(prim_path="/World/Table", prim_type="Cube", position=\[0, 0, 0\.375\], scale=\[(?P<tx>[\d.]+), (?P<ty>[\d.]+), 0\.375\]\)\n'
    r'apply_api_schema\(prim_path="/World/Table", schema_name="PhysicsCollisionAPI"\)\n'
    r'(?:\n?#[^\n]*\n)*'
    r'\n?set_physics_scene_config\(config=\{"enable_gpu_dynamics": False, "broadphase_type": "MBP"\}\)')


def candidate_code(code: str):
    m = PAT.search(code)
    if not m:
        return None
    parts = ["# Toolified opening [P2-07]: light"
             + ("+ground" if m.group("ground") else "")
             + "+cell+table+physics in ONE call"]
    args = []
    if float(m.group("inten")) != 1000.0:
        args.append(f"intensity={m.group('inten')}")
    if m.group("ground"):
        if float(m.group("gs")) != 20.0:
            args.append(f"ground_scale={m.group('gs')}")
    else:
        args.append("include_ground=False")
    tx, ty = float(m.group("tx")), float(m.group("ty"))
    if [tx * 2, ty * 2] != [1.5, 0.5]:
        args.append(f"table_size=[{tx * 2}, {ty * 2}]")
    parts.append(f"create_scene_baseline({', '.join(args)})")
    return code[:m.start()] + "\n".join(parts) + code[m.end():]


def main() -> int:
    args = sys.argv[1:]
    names = [a for a in args if not a.startswith("--")]
    if "--scan" in args:
        for f in sorted((REPO / "workspace/templates").glob("CP*.json")):
            if ".bak" in f.name or ".pre_" in f.name:
                continue
            try:
                code = json.loads(f.read_text(encoding="utf-8")).get("code") or ""
            except Exception:
                continue
            if PAT.search(code):
                print(f.stem)
        return 0
    if not names:
        print(__doc__)
        return 2
    results = {}
    for n in names:
        tpl = json.load(open(REPO / f"workspace/templates/{n}.json"))
        new_code = candidate_code(tpl["code"])
        if new_code is None:
            results[n] = "NO_MATCH"
            print(f"{n}: NO_MATCH (variant — later wave)", flush=True)
            continue
        tpl["code"] = new_code
        cand = f"/tmp/cand_{n}.json"
        json.dump(tpl, open(cand, "w"), ensure_ascii=False)
        p = subprocess.run([sys.executable, str(REPO / "scripts/qa/migrate_verify.py"),
                            n, cand], capture_output=True, text=True, timeout=1200)
        out = p.stdout + p.stderr
        if "MIGRATION_VERDICT=ZERO_DELTA" in out:
            verdict = "ZERO_DELTA"
        elif "MIGRATION_VERDICT=DELTA" in out:
            verdict = "DELTA"
        else:
            verdict = "ERROR"  # build/export crash is NOT a diff verdict
        if verdict != "ZERO_DELTA":
            tail = [l for l in out.splitlines() if l][-12:]
            print(f"{n}: {verdict}\n  " + "\n  ".join(tail), flush=True)
        else:
            print(f"{n}: {verdict}", flush=True)
        results[n] = verdict
    print("SUMMARY " + json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
