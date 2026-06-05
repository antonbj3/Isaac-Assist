#!/usr/bin/env python3
"""Belt-freeze mechanism probe for multi-robot conveyor templates.

Loads <TPL>, plays, and over ~6s samples:
  - LIVE_SUBS         (>1 => multi-robot belt-pause gate is armed)
  - belt surfaceVelocity over time  (0,0,0 => force-paused = mechanism A;
                                      nominal but cubes static => drive dead = mechanism B)
  - source-cube positions           (confirms whether anything moves)
Distinguishes A (controller standing-pause self-lock) from B (conveyor drive broken).
"""
import asyncio, json, sys, os
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPL = sys.argv[1] if len(sys.argv) > 1 else "CP-52"

_KIT = r'''
import omni.usd, omni.kit.app, omni.timeline, builtins
from pxr import UsdGeom
stage = omni.usd.get_context().get_stage()
belt = stage.GetPrimAtPath("/World/ConveyorBelt")
sv = belt.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if (belt and belt.IsValid()) else None
def wp(p):
    pr = stage.GetPrimAtPath(p)
    if not pr or not pr.IsValid(): return None
    t = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return [round(float(t[0]),3), round(float(t[1]),3), round(float(t[2]),3)]
app = omni.kit.app.get_app(); tl = omni.timeline.get_timeline_interface()
for _ in range(3): app.update()
tl.play()
for _ in range(12): app.update()
nsubs = len([k for k in vars(builtins) if k.startswith("_curobo_pp_sub_")])
print("LIVE_SUBS", nsubs)
cubes = [str(pr.GetPath()) for pr in stage.Traverse() if pr.GetName().startswith("Cube")]
print("CUBES", cubes)
for i in range(420):
    app.update()
    if i % 30 == 0:
        v = list(sv.Get()) if (sv and sv.Get() is not None) else None
        cps = {c.split("/")[-1]: wp(c) for c in cubes}
        print("t=%.1f beltSV=%s %s" % (i/60.0, v, cps))
print("PROBE_DONE")
'''

async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical, settle_after_canonical)
    tpl = json.load(open(f"{REPO}/workspace/templates/{TPL}.json"))
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        print("BUILD_FAIL", str(b.get("errors"))[:400]); return
    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception:
        pass
    r = await asyncio.wait_for(kit_tools.exec_sync(_KIT, timeout=120), timeout=140)
    print(r.get("output") or "(no output)")

asyncio.run(main())
