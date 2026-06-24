"""CV-perception on REAL YCB geometry (cont.319, Anton honest-sim-to-real CV direction):
prove the camera pipeline (Gemini-vision SELECT -> SAM2-auto LOCALIZE -> raycast) identifies +
localizes a REAL object mesh (banana/can/brick), not a colour cube. Flow:
 1. Kit: add_reference 3 YCB props (collision built in) + offset-overhead camera, capture RGB.
 2. Gemini-vision: point at the TARGET object by name.
 3. SAM2-auto masks -> nearest to VLM point -> mask centroid pixel.
 4. camera-ray + physx raycast -> HIT PRIM (real mesh collision) + 3D pose.
Run: python scripts/qa/vision_grasp_real.py banana"""
import os, sys, json, base64, urllib.request, re, asyncio
import numpy as np
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
from service.isaac_assist_service.chat.tools import kit_tools

TARGET = sys.argv[1] if len(sys.argv) > 1 else "banana"
YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned"
ITEMS = {"banana": (f"{YCB}/011_banana.usd", [0.28, 0.16]),
         "can":    (f"{YCB}/005_tomato_soup_can.usd", [0.43, 0.16]),
         "brick":  (f"{YCB}/061_foam_brick.usd", [0.58, 0.16])}
Z = 0.84  # just above table top (0.80) -> minimal drop -> less roll
PNG = "/tmp/vision_grasp_real.png"
W, H = 1280, 720
CAM = (0.43, -0.10, 1.55)

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux, Sdf\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         # static table (CollisionAPI only -> doesn't fall) so the rigid YCB props REST at a known z
         "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
         "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.43,0.16,0.40)); tx.AddScaleOp().Set((1.2,1.2,0.8))\n"
         "tb.GetDisplayColorAttr().Set([(0.55,0.55,0.55)])\n"
         "UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700)\n"
         "UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for name, (usd, pos) in ITEMS.items():
    p = f"/World/Item_{name}"
    build += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{usd}')\n"
              f"UsdGeom.Xformable(pr).AddTranslateOp().Set(({pos[0]},{pos[1]},{Z}))\n")
build += (f"cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(14.0)\n"
          f"UsdGeom.Xformable(cam).AddTranslateOp().Set({CAM})\n"
          "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
          "app=omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()\n"
          "for _ in range(260): app.update()\n"   # settle FULLY -> rigid YCB props static (roll stops) before capture
          f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
          "for _ in range(20): app.update()\n"
          "print('SCENE_BUILT')\n")


async def k(code):
    r = await kit_tools.exec_sync(code, timeout=200)
    return (r.get("output", "") if isinstance(r, dict) else str(r))

print("P1:", asyncio.run(k(build)).splitlines()[-1:])
if not os.path.exists(PNG):
    print("NO PNG"); sys.exit(1)

# Gemini-vision points at the target object by NAME (semantic, no colour, no GT)
from PIL import Image
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
img = np.array(Image.open(PNG).convert("RGB"))
pred = SAM2ImagePredictor(build_sam2("configs/sam2.1/sam2.1_hiera_s.yaml",
       "/home/anton/projects/Omniverse_Nemotron_Ext/vision_models/sam2.1_hiera_small.pt", device="cuda"))
pred.set_image(img)
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider
gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
desc = {"banana": "yellow banana", "can": "tomato soup can (red/white cylinder)", "brick": "red foam brick"}[TARGET]
prompt = (f"This {W}x{H} image shows kitchen/warehouse objects on a table. Point at the {desc}. "
          f"Reply with ONLY the pixel of its centre as JSON: {{\"x\": <int 0-{W}>, \"y\": <int 0-{H}>}}.")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
mm = re.search(r'"x"\s*:\s*(\d+).*?"y"\s*:\s*(\d+)', ans, re.S)
if not mm:
    print("VLM no point:", ans[:120]); sys.exit(1)
gx, gy = int(mm.group(1)), int(mm.group(2))
print("VLM pointed at %s (%s) pixel=(%d,%d)" % (TARGET, desc, gx, gy))
amg = SAM2AutomaticMaskGenerator(pred.model, points_per_side=32, pred_iou_thresh=0.82, stability_score_thresh=0.88)
cands = []
for m in amg.generate(img):
    a = m["area"]
    if 0.0004 * img.shape[0] * img.shape[1] < a < 0.05 * img.shape[0] * img.shape[1]:
        ys, xs = np.where(m["segmentation"]); cands.append((int(xs.mean()), int(ys.mean())))
if not cands:
    print("SAM2-auto found no object-sized masks"); sys.exit(1)
px, py = min(cands, key=lambda c: (c[0] - gx) ** 2 + (c[1] - gy) ** 2)
print("SAM2-auto %d object masks; nearest to VLM -> seed=(%d,%d)" % (len(cands), px, py))
masks, scores, _ = pred.predict(point_coords=np.array([[px, py]]), point_labels=np.array([1]), multimask_output=False)
mys, mxs = np.where(masks[0].astype(bool))
# sample up to 60 pixels ACROSS the mask -> raycast each -> majority-vote the non-table prim (thin-mesh robust)
idx = np.linspace(0, len(mxs) - 1, min(60, len(mxs))).astype(int)
samples = [[int(mxs[i]), int(mys[i])] for i in idx]
print("mask %d px, raycasting %d samples across it" % (len(mxs), len(samples)))

ray = ("import omni.usd, numpy as np, json\nfrom pxr import UsdGeom\nfrom omni.physx import get_physx_scene_query_interface\n"
       "st=omni.usd.get_context().get_stage(); cam=st.GetPrimAtPath('/World/Cam'); cg=UsdGeom.Camera(cam)\n"
       "foc=cg.GetFocalLengthAttr().Get(); hap=cg.GetHorizontalApertureAttr().Get()\n"
       f"W,H={W},{H}; fx=foc*W/hap; fy=fx; cx=W/2.0; cy=H/2.0\n"
       "m=UsdGeom.Xformable(cam).ComputeLocalToWorldTransform(0)\n"
       "t=np.array([m[3][0],m[3][1],m[3][2]]); R=np.array([[m[0][0],m[0][1],m[0][2]],[m[1][0],m[1][1],m[1][2]],[m[2][0],m[2][1],m[2][2]]])\n"
       f"samples={samples!r}\n"
       "sqi=get_physx_scene_query_interface(); from collections import Counter\n"
       "hits=[]\n"
       "for px,py in samples:\n"
       "    d=R@np.array([(px-cx)/fx,-(py-cy)/fy,-1.0]); d=d/np.linalg.norm(d)\n"
       "    h=sqi.raycast_closest((float(t[0]),float(t[1]),float(t[2])),(float(d[0]),float(d[1]),float(d[2])),5.0)\n"
       "    if h.get('hit'): hits.append((h.get('collision'), h.get('position')))\n"
       "obj=[(c,p) for c,p in hits if 'Item_' in (c or '')]\n"
       "if obj:\n"
       "    top=Counter(c for c,_ in obj).most_common(1)[0][0]\n"
       "    pos=next(p for c,p in obj if c==top)\n"
       "    print('RAYHIT_VOTE', top, pos, '(%d/%d obj-hits)'%(len(obj),len(hits)))\n"
       "else:\n"
       "    print('RAYHIT_VOTE none', Counter(c for c,_ in hits).most_common(3))\n")
out = asyncio.run(k(ray))
hitline = next((l for l in out.splitlines() if "RAYHIT_VOTE" in l), "")
print("P3:", hitline)
hit_item = next((n for n in ITEMS if f"Item_{n}" in hitline), None)
print("CAMERA-PERCEIVED REAL OBJECT:", hit_item, "(target was", TARGET + ")",
      "CORRECT" if hit_item == TARGET else "WRONG")
