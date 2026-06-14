#!/usr/bin/env python3
"""compose_gate.py — function-gate for COMPOSED multi-canonical scenes.

The single-template gate (gate_one / simulate_traversal_check) measures one scene's
delivery. This is its composition equivalent: build N templates into one stage via
compose_canonicals (each namespaced + offset), step physics once, and measure EACH
instance's delivery against its OWN (namespaced + offset) target bbox.

Verifies the composition multiplier: do all composed cells deliver concurrently?
Per-instance pass = its cubes reach its namespaced target bin.

Usage:
  compose_gate.py CP-01 CP-04            # 2 instances, auto-offset +2.5x each
  compose_gate.py CP-01@0,0,0 CP-04@2.5,0,0   # explicit offsets

Read-only on the scene logic; builds + steps. One local Kit (restart-before-run).
"""
import asyncio, json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)


def _parse(arg, idx):
    """'CP-01' or 'CP-01@2.5,0,0' -> (name, (dx,dy,dz)). Default offset = +2.5*idx in x."""
    if "@" in arg:
        name, off = arg.split("@", 1)
        dx, dy, dz = (float(x) for x in off.split(","))
        return name, (dx, dy, dz)
    return arg, (2.5 * idx, 0.0, 0.0)


async def run(specs):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import compose_canonicals
    from service.isaac_assist_service.chat.composer import reroot_prim_path

    insts = []   # (instance_root, template, namespaced_verify)
    compose_arg = []
    for i, (name, off) in enumerate(specs):
        tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
        root = f"inst{i}"
        sa = tpl.get("simulate_args") or tpl.get("verify_args") or {}
        cubes = (sa.get("cube_paths") or sa.get("source_paths")
                 or ([sa.get("cube_path")] if sa.get("cube_path") else []))
        target = sa.get("target_path")
        nv = {
            "name": name, "root": root, "off": off,
            "cubes": [reroot_prim_path(c, root) for c in cubes if c],
            "target": reroot_prim_path(target, root) if target else None,
        }
        insts.append(nv)
        compose_arg.append((tpl, root, off))

    await compose_canonicals(compose_arg)

    spec_json = json.dumps([{k: v for k, v in d.items() if k in ("name", "root", "cubes", "target")} for d in insts])
    chk = f'''
import omni.usd, omni.timeline, omni.kit.app, json as _j
from pxr import UsdGeom
stage = omni.usd.get_context().get_stage()
INSTS = _j.loads({spec_json!r})
def bbox(p):
    pr = stage.GetPrimAtPath(p)
    if not pr or not pr.IsValid(): return None
    r = UsdGeom.Imageable(pr).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    if r.IsEmpty(): return None
    mn, mx = r.GetMin(), r.GetMax()
    return [float(mn[0]),float(mn[1]),float(mn[2])], [float(mx[0]),float(mx[1]),float(mx[2])]
def cpos(p):
    bb = bbox(p)
    return [(bb[0][i]+bb[1][i])/2.0 for i in range(3)] if bb else None
tl = omni.timeline.get_timeline_interface(); tl.play(); app = omni.kit.app.get_app()
N = 6000 * max(1, len(INSTS))   # concurrent cells run slower; scale budget
for _ in range(N): app.update()
for d in INSTS:
    tb = bbox(d["target"]) if d["target"] else None
    n = 0
    for c in d["cubes"]:
        cp = cpos(c)
        if tb and cp and tb[0][0]-0.05<=cp[0]<=tb[1][0]+0.05 and tb[0][1]-0.05<=cp[1]<=tb[1][1]+0.05 and cp[2]>tb[0][2]-0.05:
            n += 1
    print("COMPOSE_GATE inst=%s tpl=%s delivered=%d/%d target=%s" % (d["root"], d["name"], n, len(d["cubes"]), d["target"]))
'''
    rr = await kit_tools.exec_sync(chk, timeout=int(6000 * max(1, len(insts)) / 8) + 90)
    out = (rr.get("output") or rr.get("error") or "").strip()
    print(out)
    lines = [l for l in out.splitlines() if l.startswith("COMPOSE_GATE")]
    npass = sum(1 for l in lines if (lambda d, t: d > 0 and d == t)(*map(int, l.split("delivered=")[1].split()[0].split("/"))))
    print(f"COMPOSE_GATE SUMMARY: {npass}/{len(lines)} instances fully delivered")


async def main():
    args = sys.argv[1:] or ["CP-01", "CP-04"]
    specs = [_parse(a, i) for i, a in enumerate(args)]
    await run(specs)

if __name__ == "__main__":
    asyncio.run(main())
