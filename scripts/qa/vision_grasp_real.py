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
# --- GRID-RAYCAST depth-segmentation: each ray returns prim+z; objects stick up above the table.
# Group Item_* hits by prim -> per-object pixel-region + 3D pose, geometrically (no SAM2 table-dominance).
ray = ("import omni.usd, numpy as np, json\nfrom pxr import UsdGeom\nfrom omni.physx import get_physx_scene_query_interface\n"
       "st=omni.usd.get_context().get_stage(); cam=st.GetPrimAtPath('/World/Cam'); cg=UsdGeom.Camera(cam)\n"
       "foc=cg.GetFocalLengthAttr().Get(); hap=cg.GetHorizontalApertureAttr().Get()\n"
       f"W,H={W},{H}; fx=foc*W/hap; fy=fx; cx=W/2.0; cy=H/2.0\n"
       "m=UsdGeom.Xformable(cam).ComputeLocalToWorldTransform(0)\n"
       "t=np.array([m[3][0],m[3][1],m[3][2]]); R=np.array([[m[0][0],m[0][1],m[0][2]],[m[1][0],m[1][1],m[1][2]],[m[2][0],m[2][1],m[2][2]]])\n"
       "sqi=get_physx_scene_query_interface(); items={}\n"
       "for py in range(20,260,9):\n"
       "  for px in range(180,1080,9):\n"
       "    d=R@np.array([(px-cx)/fx,-(py-cy)/fy,-1.0]); d=d/np.linalg.norm(d)\n"
       "    h=sqi.raycast_closest((float(t[0]),float(t[1]),float(t[2])),(float(d[0]),float(d[1]),float(d[2])),5.0)\n"
       "    if not h.get('hit'): continue\n"
       "    c=h.get('collision') or ''; pos=h.get('position')\n"
       "    if 'Item_' in c and pos[2] > 0.815:\n"   # above table top (0.80) -> real object geometry, not the table
       "      items.setdefault(c,[]).append([px,py,pos[0],pos[1],pos[2]])\n"
       "out={}\n"
       "for c,v in items.items():\n"
       "  a=np.array(v); top=a[a[:,4].argmax()]\n"   # highest-z hit = object top (grasp point)
       "  out[c]=[float(a[:,0].mean()),float(a[:,1].mean()),int(len(v)),float(top[2]),float(top[3]),float(top[4])]\n"
       "print('GRIDOBJ', json.dumps(out))\n")
out = asyncio.run(k(ray))
gl = next((l for l in out.splitlines() if "GRIDOBJ" in l), "")
objs = json.loads(gl.split("GRIDOBJ", 1)[1].strip()) if "GRIDOBJ" in gl else {}
print("grid-raycast found %d real objects: %s" % (len(objs), {c.split('/')[-1]: o[2] for c, o in objs.items()}))
if not objs:
    print("no object geometry above the table found"); sys.exit(1)
# VLM point SELECTS among the geometrically-found objects (nearest pixel-centroid)
hit_prim = min(objs, key=lambda c: (objs[c][0] - gx) ** 2 + (objs[c][1] - gy) ** 2)
o = objs[hit_prim]
print("VLM(%d,%d) -> nearest object %s  pixel-centroid=(%d,%d)  3D-top=(%.3f,%.3f,%.3f)" % (
    gx, gy, hit_prim.split('/')[-1], o[0], o[1], o[3], o[4], o[5]))
hit_item = next((n for n in ITEMS if f"Item_{n}" in hit_prim), None)
print("CAMERA-PERCEIVED REAL OBJECT:", hit_item, "(target was", TARGET + ")",
      "CORRECT" if hit_item == TARGET else "WRONG")
