"""Load a canonical template into the running Kit, build + settle + play.
Leaves Kit in playing state so user can watch in viewport.

Usage: load_for_review.py <CP-NAME>
Pre-req: Kit running on port 8001 WITH visible viewport (not --no-window).
"""
import asyncio, json, sys, urllib.request
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))

HEALTH = "http://127.0.0.1:8001/health"
def kit_alive():
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as r: return r.status == 200
    except: return False

async def main():
    if len(sys.argv) < 2:
        print("usage: load_for_review.py <CP-NAME>"); sys.exit(1)
    name = sys.argv[1]
    if not kit_alive():
        print("ERR: Kit not alive on :8001. Start with launch_isaac_sim_with_assist.sh (no --headless flag)."); sys.exit(2)

    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical

    tpl_path = REPO/f"workspace/templates/{name}.json"
    if not tpl_path.exists():
        print(f"NOT_FOUND: {tpl_path}"); sys.exit(3)
    tpl = json.loads(tpl_path.read_text())

    # Reset stage
    code = "import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n"
    await kit_tools.exec_sync(code, timeout=20)

    # Build
    print(f"Building {name}...")
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        print(f"BUILD_FAIL: {b.get('errors')}"); sys.exit(4)
    print(f"Build OK ({b.get('n_ok','?')}/{b.get('n_calls','?')} tools)")

    # Settle
    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except: pass

    # Frame viewport on scene + ensure light + play timeline
    frame_code = """
import omni.usd, omni.kit.app, omni.timeline
from pxr import UsdGeom, UsdLux, Sdf, Gf
stage = omni.usd.get_context().get_stage()

# Ensure dome light
lp = "/World/_review_dome_light"
if not stage.GetPrimAtPath(Sdf.Path(lp)).IsValid():
    d = UsdLux.DomeLight.Define(stage, lp)
    d.CreateIntensityAttr(1500.0)

# Frame viewport on /World
try:
    import omni.kit.viewport.utility as vp_util
    vp = vp_util.get_active_viewport()
    if vp:
        # Set camera near scene
        bb_cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
        world = stage.GetPrimAtPath(Sdf.Path("/World"))
        bb = bb_cache.ComputeWorldBound(world).ComputeAlignedRange()
        ctr = bb.GetMidpoint(); mn = bb.GetMin(); mx = bb.GetMax()
        sz = max(float(mx[0]-mn[0]), float(mx[1]-mn[1]), float(mx[2]-mn[2]), 1.0)
        cam_path = "/World/_review_cam"
        existing = stage.GetPrimAtPath(Sdf.Path(cam_path))
        if not existing or not existing.IsValid():
            cam = UsdGeom.Camera.Define(stage, cam_path)
        else:
            cam = UsdGeom.Camera(existing)
        xf = UsdGeom.Xformable(cam); xf.ClearXformOpOrder()
        eye = Gf.Vec3d(float(ctr[0])+sz*0.8, float(ctr[1])-sz*1.2, float(ctr[2])+sz*1.3)
        target = Gf.Vec3d(float(ctr[0]), float(ctr[1]), float(ctr[2]))
        view = Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0,0,1))
        xf.AddTransformOp().Set(view.GetInverse())
        cam.CreateFocalLengthAttr(35.0)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 100.0))
        vp.camera_path = cam_path
except Exception as e:
    print(f"viewport setup failed: {type(e).__name__}: {e}")

# Start timeline playing
tl = omni.timeline.get_timeline_interface()
tl.set_current_time(0.0)
tl.set_end_time(300.0)
tl.play()
print("READY_FOR_REVIEW")
"""
    r = await kit_tools.exec_sync(frame_code, timeout=20)
    print((r.get("output") or "").strip()[-300:])

asyncio.run(main())
