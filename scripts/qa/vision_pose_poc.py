"""Vision-perception PoC step 1a (cont.319, Anton CV/camera direction): prove the
Isaac camera -> RGB+DEPTH -> unproject chain is ACCURATE vs sim ground-truth (before SAM2).
Uses isaacsim.sensors.camera.Camera (handles annotators + app.update, no orchestrator).
Projects the cube centre to a pixel, reads depth there, unprojects to world, compares to GT."""
import asyncio, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
from service.isaac_assist_service.chat.tools import kit_tools

KIT = r'''
import omni.usd, omni.kit.app, numpy as np
from pxr import UsdGeom, Gf, UsdLux
omni.usd.get_context().new_stage()
stage = omni.usd.get_context().get_stage()
UsdGeom.Xform.Define(stage, "/World")
UsdLux.DistantLight.Define(stage, "/World/Light").CreateIntensityAttr(2000)
gp = UsdGeom.Cube.Define(stage, "/World/Ground"); gp.GetSizeAttr().Set(1.0)
gx = UsdGeom.Xformable(gp); gx.AddTranslateOp().Set((0.4,0.15,-0.5)); gx.AddScaleOp().Set((4,4,0.5))
CUBE_POS = (0.40, 0.15, 0.05)
c = UsdGeom.Cube.Define(stage, "/World/Cube"); c.GetSizeAttr().Set(0.05)
UsdGeom.Xformable(c).AddTranslateOp().Set(CUBE_POS); c.GetDisplayColorAttr().Set([(0.9,0.1,0.1)])

# overhead USD camera, look straight down (-Z). USD camera at identity looks down -Z.
CAM_POS = (0.40, 0.15, 0.80)
camp = UsdGeom.Camera.Define(stage, "/World/PoCcam")
import math as _m
FOV = 60.0; HAP = 20.955
camp.GetHorizontalApertureAttr().Set(HAP); camp.GetVerticalApertureAttr().Set(HAP)
camp.GetFocalLengthAttr().Set(0.5 * HAP / _m.tan(_m.radians(FOV/2)))
camp.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))
UsdGeom.Xformable(camp).AddTranslateOp().Set(CAM_POS)  # identity rot -> looks down -Z
# repoint the ACTIVE viewport (which DOES render) to our camera + attach annotators to ITS render product
import omni.kit.viewport.utility as vpu, omni.replicator.core as rep
vp = vpu.get_active_viewport(); vp.camera_path = "/World/PoCcam"
_app = omni.kit.app.get_app()
for _ in range(10): _app.update()
rp_path = vp.get_render_product_path()
W, H = vp.get_texture_resolution()
rgb_a = rep.AnnotatorRegistry.get_annotator("rgb"); rgb_a.attach(rp_path)
dep_a = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane"); dep_a.attach(rp_path)
for _ in range(60): _app.update()
depth = np.asarray(dep_a.get_data()); rgb = np.asarray(rgb_a.get_data())
print("RENDER W=%d H=%d rgb=%s depth=%s" % (W, H, getattr(rgb,'shape',None), getattr(depth,'shape',None)))
if depth is None or depth.size == 0:
    print("NO DEPTH DATA"); raise SystemExit
print("depth range [%.3f, %.3f]" % (float(np.nanmin(depth)), float(np.nanmax(depth))))
foc = camp.GetFocalLengthAttr().Get()
fx = foc * W / HAP; fy = foc * H / HAP; cx = W/2.0; cy = H/2.0
m = UsdGeom.Xformable(camp).ComputeLocalToWorldTransform(0)
cam_t = np.array([m[3][0], m[3][1], m[3][2]])
R = np.array([[m[0][0],m[0][1],m[0][2]],[m[1][0],m[1][1],m[1][2]],[m[2][0],m[2][1],m[2][2]]])
gt = np.array(CUBE_POS)
pc = R.T @ (gt - cam_t)               # world -> camera
u = cx + fx * (pc[0] / -pc[2]); v = cy - fy * (pc[1] / -pc[2])
ui, vi = int(round(u)), int(round(v))
print("INTRINSICS fx=%.1f fy=%.1f cx=%.1f cy=%.1f | cube pixel=(%d,%d) cam_z=%.3f" % (fx,fy,cx,cy,ui,vi,pc[2]))
if 0 <= vi < H and 0 <= ui < W:
    d = float(depth[vi, ui])
    Xc=(ui-cx)*d/fx; Yc=-(vi-cy)*d/fy; Zc=-d
    world = cam_t + R @ np.array([Xc,Yc,Zc])
    err = float(np.linalg.norm(world - gt))
    print("UNPROJECT d=%.3f -> world=[%.3f,%.3f,%.3f] gt=[%.3f,%.3f,%.3f] ERR=%.1fmm" % (
        d, world[0],world[1],world[2], gt[0],gt[1],gt[2], err*1000))
else:
    print("PIXEL OUT OF FRAME (%d,%d)" % (ui,vi))
'''


async def main():
    r = await kit_tools.exec_sync(KIT, timeout=200)
    print(r.get("output", "") if isinstance(r, dict) else str(r))


asyncio.run(main())
