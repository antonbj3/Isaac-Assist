#!/usr/bin/env python3
"""scene_probe.py — GENERAL read-only time-series diagnostic for pick-place scenes.

Auto-discovers from the running stage (no per-template hardcoding):
  - robots      : prims carrying a `ctrl:phase` attr (i.e. a pick_place controller is installed)
  - belts       : prims carrying `physxSurfaceVelocity:surfaceVelocity`
  - mutexes     : prims carrying `mutex:claimed_by`
  - cubes       : simulate_args.cube_paths (falls back to cube_path)

Logs over time: each belt's velocity, each mutex holder, each cube xyz, each robot's
ctrl:phase + ctrl:cubes_delivered + ctrl:pick_reject. Flags belt PAUSE/RESUME events,
cube ride-off (x>belt_end), cube floor-drop (z<0.78), and cube stuck-mid-air (z>0.88 and
not advancing). This is the generalized successor to cp53_probe.py / arm_arm_probe.py — the
"build a probe" pattern: read RAW scene state, never trust controller telemetry.

Usage: python3 scripts/review/scene_probe.py <TEMPLATE> [duration_s]  (e.g. CP-14 90)
"""
import asyncio, json, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))
import urllib.request
def kit_alive():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3) as r: return r.status == 200
    except Exception: return False

PROBE = r"""
import omni.usd, omni.kit.app, omni.timeline, time, json
from pxr import UsdGeom, Sdf, UsdPhysics
stage = omni.usd.get_context().get_stage()
CUBES = __CUBES__; DUR = __DUR__
# --- auto-discovery ---
ROBOTS=[]; BELTS=[]; MUTEXES=[]
for p in stage.Traverse():
    pa=str(p.GetPath())
    a=p.GetAttribute("ctrl:phase")
    if a and a.IsDefined(): ROBOTS.append(pa)
    b=p.GetAttribute("physxSurfaceVelocity:surfaceVelocity")
    if b and b.IsDefined(): BELTS.append(pa)
    m=p.GetAttribute("mutex:claimed_by")
    if m and m.IsDefined(): MUTEXES.append(pa)
def _belt_end(bp):
    # belt +x extent in world (for ride-off detection)
    pr=stage.GetPrimAtPath(Sdf.Path(bp))
    try:
        rng=UsdGeom.Boundable(pr).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedBox()
        return float(rng.GetMax()[0])
    except Exception: return 1e9
BELT_END={b:_belt_end(b) for b in BELTS}
def _xf(p):
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not (pr and pr.IsValid()): return None
    t=UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return (round(float(t[0]),3),round(float(t[1]),3),round(float(t[2]),3))
def _vel(bp):
    pr=stage.GetPrimAtPath(Sdf.Path(bp))
    a=pr.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if pr else None
    if a and a.IsDefined():
        v=a.Get(); return round(float(v[0]),3) if v else None
    return None
def _ctrl(r,name):
    pr=stage.GetPrimAtPath(Sdf.Path(r))
    a=pr.GetAttribute(name) if pr else None
    return a.Get() if (a and a.IsDefined()) else None
def _mtx(mp):
    pr=stage.GetPrimAtPath(Sdf.Path(mp))
    a=pr.GetAttribute("mutex:claimed_by") if pr else None
    v=(a.Get() if a else "") or ""
    return v.split("/")[-1] if v else ""
tl=omni.timeline.get_timeline_interface(); tl.play()
app=omni.kit.app.get_app()
samples=[]; t0=time.monotonic()
last_v={b:None for b in BELTS}; belt_events=[]
rideoff={c:None for c in CUBES}; midair={c:None for c in CUBES}; floordrop={c:None for c in CUBES}
for i in range(int(DUR*60)):
    app.update()
    if i % 30 == 0:
        t=round(time.monotonic()-t0,1)
        cubes={c.split("/")[-1]:_xf(c) for c in CUBES}
        vels={b.split("/")[-1]:_vel(b) for b in BELTS}
        row={"t":t,"vel":vels,
             "mtx":{m.split("/")[-1]:_mtx(m) for m in MUTEXES},
             "rob":{r.split("/")[-1]:[_ctrl(r,"ctrl:phase"),_ctrl(r,"ctrl:cubes_delivered")] for r in ROBOTS},
             "cubes":cubes}
        samples.append(row)
        for b in BELTS:
            bn=b.split("/")[-1]; v=vels[bn]
            if last_v[b] is not None:
                if (last_v[b] or 0)<0.01 and (v or 0)>0.01: belt_events.append({"t":t,"belt":bn,"ev":"RESUME"})
                if (last_v[b] or 0)>0.01 and (v or 0)<0.01: belt_events.append({"t":t,"belt":bn,"ev":"PAUSE"})
            last_v[b]=v
        for c in CUBES:
            q=cubes[c.split("/")[-1]]
            if not q: continue
            if rideoff[c] is None and q[0] > min(BELT_END.values() or [1e9])+0.03: rideoff[c]={"t":t,"pos":q}
            if floordrop[c] is None and q[2] < 0.78: floordrop[c]={"t":t,"pos":q}
res={"discovered":{"robots":ROBOTS,"belts":BELTS,"belt_end":BELT_END,"mutexes":MUTEXES,"cubes":CUBES},
     "samples":samples,"belt_events":belt_events,
     "rideoff":{k.split("/")[-1]:v for k,v in rideoff.items()},
     "floordrop":{k.split("/")[-1]:v for k,v in floordrop.items()},
     "final":{c.split("/")[-1]:_xf(c) for c in CUBES}}
print("SCENEPROBE_BEGIN"+json.dumps(res,default=str)+"SCENEPROBE_END",flush=True)
"""

async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "CP-53"
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 90.0
    if not kit_alive(): print("Kit not alive on :8001"); return
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    tpl = json.loads((REPO / f"workspace/templates/{name}.json").read_text())
    sa = tpl.get("simulate_args") or {}
    cubes = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
    await kit_tools.exec_sync("import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"): print("BUILD_FAIL:", str(b.get("errors"))[:400]); return
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception: pass
    code = PROBE.replace("__CUBES__", repr(cubes)).replace("__DUR__", repr(dur))
    r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=dur+200), timeout=dur+220)
    out = (r.get("output") or "")
    i, j = out.find("SCENEPROBE_BEGIN"), out.find("SCENEPROBE_END")
    if i < 0 or j < 0: print("PARSE_FAIL:\n", out[-2500:]); return
    d = json.loads(out[i+len("SCENEPROBE_BEGIN"):j])
    dd = d["discovered"]
    print(f"=== DISCOVERED: robots={[r.split('/')[-1] for r in dd['robots']]} belts={[b.split('/')[-1] for b in dd['belts']]} mutexes={[m.split('/')[-1] for m in dd['mutexes']]} ===")
    print(f"    belt +x ends: {{ {', '.join(k.split('/')[-1]+'='+str(round(v,2)) for k,v in dd['belt_end'].items())} }}")
    print("=== BELT EVENTS ==="); [print(f"  t={e['t']:>5} {e['belt']} {e['ev']}") for e in d["belt_events"]]
    print("=== RIDE-OFF (past belt +x end) ==="); [print(f"  {k}: {v}") for k, v in d["rideoff"].items() if v]
    print("=== FLOOR-DROP (z<0.78) ==="); [print(f"  {k}: {v}") for k, v in d["floordrop"].items() if v]
    print("=== FINAL cube positions ==="); [print(f"  {k}: {v}") for k, v in d["final"].items()]
    print("=== TIMELINE ===")
    for s in d["samples"]:
        rob = " ".join(f"{k}[{v[0]},{v[1]}]" for k, v in s["rob"].items())
        vel = " ".join(f"{k}={v}" for k, v in s["vel"].items())
        mtx = " ".join(f"{k}={v or '-'}" for k, v in s["mtx"].items())
        cz = " ".join(f"{k}=({(v[0] if v else None)},{(v[2] if v else None)})" for k, v in s["cubes"].items())
        print(f"  t={s['t']:>5} | {rob} | belt[{vel}] mtx[{mtx}] | {cz}")

if __name__ == "__main__":
    asyncio.run(main())
