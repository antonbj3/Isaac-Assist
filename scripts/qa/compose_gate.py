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
    import os as _osc
    dbg = bool(_osc.environ.get("COMPOSE_DEBUG"))
    traj = bool(_osc.environ.get("COMPOSE_TRAJ"))
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
DBG = {dbg}
N = 6000 * max(1, len(INSTS))   # concurrent cells run slower; scale budget
# Trajectory capture (COMPOSE_TRAJ): sample every TRAJ_EVERY steps so a FLING shows
# as a sudden per-cube jump -> distinguishes flung (bad trajectory) from topple/slip.
TRAJ = {traj}
TRAJ_EVERY = 600
_trail = {{}}  # cube_path -> list of (step, x, y, z)
if TRAJ:
    _allc = [c for d in INSTS for c in d["cubes"]]
    for _s in range(N):
        app.update()
        if _s % TRAJ_EVERY == 0 or _s == N - 1:
            for c in _allc:
                cp = cpos(c)
                if cp: _trail.setdefault(c, []).append((_s, cp[0], cp[1], cp[2]))
    for c, tr in _trail.items():
        # report max single-step jump (fling signature) + the trail
        jmax = 0.0; jstep = -1
        for i in range(1, len(tr)):
            j = ((tr[i][1]-tr[i-1][1])**2 + (tr[i][2]-tr[i-1][2])**2) ** 0.5
            if j > jmax: jmax = j; jstep = tr[i][0]
        flag = " FLING" if jmax > 0.5 else ""
        print("COMPOSE_TRAJ cube=%s max_jump=%.2f@step%d%s trail=%s" % (
            c.split("/")[-1], jmax, jstep, flag,
            ";".join("%d:[%.2f,%.2f,%.2f]" % (s, x, y, z) for s, x, y, z in tr)))
else:
    for _ in range(N): app.update()
for d in INSTS:
    tb = bbox(d["target"]) if d["target"] else None
    n = 0
    for c in d["cubes"]:
        cp = cpos(c)
        hit = bool(tb and cp and tb[0][0]-0.05<=cp[0]<=tb[1][0]+0.05 and tb[0][1]-0.05<=cp[1]<=tb[1][1]+0.05 and cp[2]>tb[0][2]-0.05)
        if hit:
            n += 1
        if DBG and not hit:
            # how far did the MISSED cube land from the target bbox? (tolerance-miss vs genuine)
            if tb and cp:
                dx = max(tb[0][0]-cp[0], 0, cp[0]-tb[1][0])
                dy = max(tb[0][1]-cp[1], 0, cp[1]-tb[1][1])
                dz_below = (tb[0][2]-0.05) - cp[2]
                print("COMPOSE_MISS inst=%s cube=%s pos=[%.3f,%.3f,%.3f] xy_out=[%.3f,%.3f] below_z=%.3f" % (
                    d["root"], c.split("/")[-1], cp[0], cp[1], cp[2], dx, dy, dz_below))
            else:
                print("COMPOSE_MISS inst=%s cube=%s NO_POS/NO_TARGET" % (d["root"], c.split("/")[-1]))
    print("COMPOSE_GATE inst=%s tpl=%s delivered=%d/%d target=%s tbbox=%s" % (
        d["root"], d["name"], n, len(d["cubes"]), d["target"],
        ("[%.2f,%.2f,%.2f]-[%.2f,%.2f,%.2f]" % (tb[0][0],tb[0][1],tb[0][2],tb[1][0],tb[1][1],tb[1][2])) if tb else "None"))
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
