#!/usr/bin/env python3
"""compose_and_verify.py — the CONTINUOUS verified-composition training pipeline (Anton 2026-06-15).

The complexity ladder: L1 verified templates -> L2 verified COMPOSITIONS -> L3 compositions-of-
compositions. Training data must capture VERIFIED compositions (that actually DELIVER via the gate),
not just proposed plans — else we train on errors. This is the L2 generator: it BUILDS a composition
via build_composed_scene, MEASURES delivery per instance, and — only if it delivers — APPENDS a
verified training record (task -> plan -> composed tool-calls -> delivery) to
workspace/training_data/verified_compositions.jsonl. Run it as compositions grow + complexity climbs
(more cells, deeper chains) and the dataset ladders up automatically.

Usage: compose_and_verify.py CP-01 CP-01 [--task "..."]   (parallel layout; cells = the args)
Needs ONE local Kit on :8001 (restart-before-run by the caller wrapper).
"""
import asyncio, json, os, sys, time

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
OUT_DIR = os.path.join(REPO, "workspace", "training_data")


def _args():
    cells = [a for a in sys.argv[1:] if not a.startswith("--")]
    task = "compose " + " + ".join(cells)
    if "--task" in sys.argv:
        task = sys.argv[sys.argv.index("--task") + 1]
    return cells, task


async def main():
    names, task = _args()
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import build_composed_scene
    from service.isaac_assist_service.chat.composer import reroot_prim_path

    cells = [{"id": f"inst{i}", "template": n} for i, n in enumerate(names)]
    r = await build_composed_scene(cells, layout="parallel")
    print("BUILT:", r.get("built"), "| findings:", [(f["kind"], f["severity"]) for f in r.get("findings", [])])
    if not r.get("built"):
        print("NOT_BUILT:", r.get("refused_reason"))
        return

    # per-instance namespaced cube/target paths for the delivery measurement
    insts = []
    for i, n in enumerate(names):
        t = json.load(open(f"{REPO}/workspace/templates/{n}.json"))
        sa = t.get("simulate_args") or t.get("verify_args") or {}
        cubes = (sa.get("cube_paths") or sa.get("source_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else []))
        target = sa.get("target_path")
        insts.append({"root": f"inst{i}", "name": n,
                      "cubes": [reroot_prim_path(c, f"inst{i}") for c in cubes if c],
                      "target": reroot_prim_path(target, f"inst{i}") if target else None})

    spec = json.dumps(insts)
    chk = f'''
import omni.usd, omni.timeline, omni.kit.app, json as _j
from pxr import UsdGeom
stage = omni.usd.get_context().get_stage()
INSTS = _j.loads({spec!r})
def bbox(p):
    pr = stage.GetPrimAtPath(p)
    if not pr or not pr.IsValid(): return None
    rg = UsdGeom.Imageable(pr).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    if rg.IsEmpty(): return None
    mn, mx = rg.GetMin(), rg.GetMax()
    return [float(mn[0]),float(mn[1]),float(mn[2])],[float(mx[0]),float(mx[1]),float(mx[2])]
def cpos(p):
    bb = bbox(p); return [(bb[0][i]+bb[1][i])/2.0 for i in range(3)] if bb else None
tl = omni.timeline.get_timeline_interface(); tl.play(); app = omni.kit.app.get_app()
for _ in range(6000 * max(1, len(INSTS))): app.update()
for d in INSTS:
    tb = bbox(d["target"]) if d["target"] else None; n = 0
    for c in d["cubes"]:
        cp = cpos(c)
        if tb and cp and tb[0][0]-0.05<=cp[0]<=tb[1][0]+0.05 and tb[0][1]-0.05<=cp[1]<=tb[1][1]+0.05 and cp[2]>tb[0][2]-0.05:
            n += 1
    print("DELIV inst=%s tpl=%s delivered=%d/%d" % (d["root"], d["name"], n, len(d["cubes"])))
'''
    rr = await kit_tools.exec_sync(chk, timeout=int(6000 * max(1, len(insts)) / 8) + 90)
    out = (rr.get("output") or rr.get("error") or "").strip()
    print(out)
    deliv = {}
    for l in out.splitlines():
        if l.startswith("DELIV"):
            root = l.split("inst=")[1].split()[0]
            d, tot = map(int, l.split("delivered=")[1].split()[0].split("/"))
            deliv[root] = {"delivered": d, "total": tot}
    all_full = bool(deliv) and all(v["delivered"] == v["total"] and v["total"] > 0 for v in deliv.values())
    rec = {
        "ts": time.time(), "level": "L2_composition",
        "verification_tier": "gold_kit_delivery_verified",  # only appended when it DELIVERED full in Kit
        "task": task,
        "plan": {"cells": cells, "layout": "parallel"},
        "offsets": r.get("offsets"),
        "composed_tool_calls": [{"id": ins.get("template") if isinstance(ins, dict) else None}
                                for ins in r.get("instances", [])],
        "delivery": deliv,
        "verified": all_full,
        "complexity": {"n_cells": len(cells), "layout": "parallel",
                       "n_objects": sum(v["total"] for v in deliv.values())},
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "verified_compositions.jsonl")
    if all_full:
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print("VERIFIED_COMPOSITION_APPENDED:", json.dumps(deliv), "-> ", path)
    else:
        print("NOT_VERIFIED (not appended to training data):", json.dumps(deliv))
    print("COMPOSE_VERIFY_DONE verified=%s" % all_full)


if __name__ == "__main__":
    asyncio.run(main())
