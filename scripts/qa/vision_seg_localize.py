"""RIGOROUS vision localization (cont.319, Anton: horizontal-counting crutch fails on complex scenes).
Camera SENSOR (depth + instance-segmentation, now proven to work in RPC Kit) -> Gemini IDs the target
from RGB + points (coarse) -> segmentation[pixel] resolves the EXACT prim path (no layout, no left-to-right,
clutter-robust). Proof scene: a 3x2 GRID of 6 colour cubes (TWO rows -> horizontal-counting is ambiguous).
Verify the seg-resolved prim == the target colour's prim (verification uses ground-truth; the PIPELINE does NOT).
Run: python scripts/qa/vision_seg_localize.py green"""
import os, sys, json, base64, urllib.request, re, asyncio
import numpy as np
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

# 3x2 grid (2 rows) -> left-to-right ordering is ambiguous. color -> prim + grid pos
CUBES = {"red": (1.0,0.0,0.0), "green": (0.0,1.0,0.0), "blue": (0.0,0.0,1.0),
         "yellow": (1.0,1.0,0.0), "cyan": (0.0,1.0,1.0), "magenta": (1.0,0.0,1.0)}
GRID = [(-0.10,0.10),(0.0,0.10),(0.10,0.10),(-0.10,0.26),(0.0,0.26),(0.10,0.26)]  # 3 cols x 2 rows
ORDER = list(CUBES)
TARGET = sys.argv[1] if len(sys.argv) > 1 else "green"
PNG = "/tmp/vseg_rgb.png"; SEG = "/tmp/vseg_seg.npy"; IDS = "/tmp/vseg_ids.json"
W, H = 640, 480

kit = ("import omni.usd, omni.kit.app, omni.timeline, numpy as np, json\n"
       "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
       "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
       "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(800); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1200)\n")
for (col, rgb), (x, y) in zip(CUBES.items(), GRID):
    p = f"/World/Cube_{col}"
    kit += (f"c=UsdGeom.Cube.Define(st,'{p}'); c.GetSizeAttr().Set(0.05)\n"
            f"UsdGeom.Xformable(c).AddTranslateOp().Set(({x},{y},0.05)); c.GetDisplayColorAttr().Set([{rgb}])\n"
            f"try:\n    from semantics.schema.editor import PrimSemanticData\n    PrimSemanticData(st.GetPrimAtPath('{p}')).add_entry('class','{col}')\nexcept Exception as _e: pass\n")
kit += ("uc=UsdGeom.Camera.Define(st,'/World/SensorCam'); uc.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
        "UsdGeom.Xformable(uc).AddTranslateOp().Set((0.0,0.18,0.8))\n"   # translate-only -> looks straight down -Z
        "app=omni.kit.app.get_app()\n"
        "from isaacsim.sensors.camera import Camera\n"
        f"cam=Camera(prim_path='/World/SensorCam', frequency=20, resolution=({W},{H}))\n"
        "cam.initialize(); cam.add_distance_to_image_plane_to_frame(); cam.add_instance_segmentation_to_frame()\n"
        "omni.timeline.get_timeline_interface().play()\n"
        "for _ in range(50): app.update()\n"
        "fr=cam.get_current_frame(); rgba=cam.get_rgba()\n"
        "from PIL import Image\n"
        f"Image.fromarray(rgba[:,:,:3].astype('uint8')).save('{PNG}')\n"
        "seg=fr['instance_segmentation']; data=np.asarray(seg['data'])\n"
        f"np.save('{SEG}', data)\n"
        f"json.dump(seg.get('info',{{}}).get('idToLabels',{{}}), open('{IDS}','w'))\n"
        "print('SENSOR_DONE seg_shape='+str(data.shape)+' uniq='+str(len(np.unique(data))))\n")


async def run():
    r = await kit_tools.exec_sync(kit, timeout=200)
    return (r.get("output", "") if isinstance(r, dict) else str(r))

out = asyncio.run(run())
print("KIT:", [l for l in out.splitlines() if "SENSOR_DONE" in l or "Error" in l][:2])
if not os.path.exists(PNG) or not os.path.exists(SEG):
    print("capture failed"); sys.exit(1)

# Gemini IDs + points at the target from the RGB (no layout given)
gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
prompt = (f"This {W}x{H} image shows 6 coloured cubes in a grid. Point at the {TARGET.upper()} cube. "
          f"Reply ONLY its centre pixel as JSON {{\"x\": <int>, \"y\": <int>}}.")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
m = re.search(r'"x"\s*:\s*(\d+).*?"y"\s*:\s*(\d+)', ans, re.S)
if not m:
    print("VLM no point:", ans[:100]); sys.exit(1)
gx, gy = int(m.group(1)), int(m.group(2))

# RIGOROUS: segmentation[pixel] -> exact prim path. Absorb Gemini's coarse point: if it lands on
# background/edge, take the nearest non-background prim pixel.
seg = np.load(SEG); ids = json.load(open(IDS))
gx = min(max(gx, 0), W - 1); gy = min(max(gy, 0), H - 1)
def labels_at(v): return ids.get(str(int(v)), "?")
pid = int(seg[gy, gx]); lbl = labels_at(pid)
if lbl in ("BACKGROUND", "UNLABELLED", "?"):
    ys, xs = np.where(~np.isin(seg, [k for k, v in ids.items() if v in ("BACKGROUND", "UNLABELLED")] and []))  # placeholder
    # nearest non-bg pixel
    bgids = [int(k) for k, v in ids.items() if v in ("BACKGROUND", "UNLABELLED")]
    mask = ~np.isin(seg, bgids); ys, xs = np.where(mask)
    if len(xs):
        i = np.argmin((xs - gx) ** 2 + (ys - gy) ** 2); pid = int(seg[ys[i], xs[i]]); lbl = labels_at(pid)
resolved = lbl.split("/")[-1] if lbl.startswith("/") else lbl
truth_prim = f"Cube_{TARGET}"
print("Gemini point=(%d,%d) -> segmentation prim=%s | target=%s -> %s" % (
    gx, gy, resolved, truth_prim, "CORRECT (seg-localized, NO layout/horizontal-counting)" if resolved == truth_prim else "WRONG (resolved %s)" % resolved))
