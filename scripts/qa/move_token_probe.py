#!/usr/bin/env python3
"""Multi-robot exec-gate instrumentation. Loads <TPL>, plays, and over ~10s samples
the shared MOVE_LOCK / PLAN_LOCK builtins state + each robot's ctrl:phase / plan_calls.
Pins WHY a robot in `executing` cannot acquire the move-token (round-robin starvation,
stale holder, etc.). Read the timeline — do not guess.
"""
import asyncio, json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPL = sys.argv[1] if len(sys.argv) > 1 else "CP-52"

_KIT = r'''
import omni.usd, omni.kit.app, omni.timeline, builtins
from pxr import UsdGeom
stage = omni.usd.get_context().get_stage()
def lock(name):
    L = getattr(builtins, name, None)
    if not isinstance(L, dict): return None
    return {k:(v if not isinstance(v,float) else round(v,2)) for k,v in L.items()}
# robot prims with ctrl: attrs
robots = []
for pr in stage.Traverse():
    a = pr.GetAttribute("ctrl:phase")
    if a and a.IsValid():
        robots.append(str(pr.GetPath()))
def rstate(rp):
    pr = stage.GetPrimAtPath(rp)
    def g(attr, d=None):
        a = pr.GetAttribute(attr)
        return a.Get() if (a and a.IsValid()) else d
    return {"phase": g("ctrl:phase"), "pc": g("ctrl:plan_calls"),
            "pf": g("ctrl:plan_fails"), "picked": (g("ctrl:picked_path") or "")[-7:]}
app = omni.kit.app.get_app(); tl = omni.timeline.get_timeline_interface()
for _ in range(3): app.update()
tl.play()
for _ in range(12): app.update()
print("ROBOTS", robots)
subs = [k for k in vars(builtins) if k.startswith("_curobo_pp_sub_")]
print("SUBS", subs)
for i in range(600):
    app.update()
    if i % 30 == 0:
        ml = lock("_curobo_exec_motion_lock_v1")
        pl = lock("_curobo_plan_serial_lock_v1")
        rs = {r.split("/")[-1]: rstate(r) for r in robots}
        print("t=%.1f MOVE=%s PLAN=%s %s" % (i/60.0, ml, pl, rs))
print("MTPROBE_DONE")
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
    r = await asyncio.wait_for(kit_tools.exec_sync(_KIT, timeout=160), timeout=180)
    print(r.get("output") or "(no output)")

asyncio.run(main())
