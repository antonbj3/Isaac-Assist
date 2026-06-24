"""RIGOROUS vision GRASP end-to-end (cont.319, Anton steer): Camera-sensor segmentation resolves the
EXACT prim from Gemini's point (no layout/horizontal-counting), then the Franka grasps THAT physical prim.
Proof scene: 2x2 grid of colour cubes (2 rows -> horizontal-counting ambiguous). source_paths is set from
SEGMENTATION, not from known layout. scene_eyes verifies the right physical cube is delivered.
Run: python scripts/qa/vision_seg_grasp.py blue"""
import os, sys, json, base64, urllib.request, re, asyncio
import numpy as np
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

# 2x2 grid (2 rows), reachable +y band. color -> rgb
CUBES = {"red": (1.0, 0.0, 0.0), "green": (0.0, 1.0, 0.0), "blue": (0.0, 0.0, 1.0), "yellow": (1.0, 1.0, 0.0)}
POS = {"red": [0.40, 0.10], "green": [0.50, 0.10], "blue": [0.40, 0.22], "yellow": [0.50, 0.22]}
TARGET = sys.argv[1] if len(sys.argv) > 1 else "blue"
PNG = "/tmp/vsg_rgb.png"; SEG = "/tmp/vsg_seg.npy"; IDS = "/tmp/vsg_ids.json"
W, H = 640, 480

# --- perception phase: Camera sensor (RGB + instance segmentation) ---
kit = ("import omni.usd, omni.kit.app, omni.timeline, numpy as np, json\n"
       "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
       "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
       "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
       "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(800); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1200)\n")
for col, rgb in CUBES.items():
    x, y = POS[col]; p = f"/World/Cube_{col}"
    kit += (f"c=UsdGeom.Cube.Define(st,'{p}'); c.GetSizeAttr().Set(0.05)\n"
            f"UsdGeom.Xformable(c).AddTranslateOp().Set(({x},{y},0.83)); c.GetDisplayColorAttr().Set([{rgb}])\n"
            f"UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('{p}'))\n"
            f"try:\n    from semantics.schema.editor import PrimSemanticData\n    PrimSemanticData(st.GetPrimAtPath('{p}')).add_entry('class','{col}')\nexcept Exception: pass\n")
kit += ("uc=UsdGeom.Camera.Define(st,'/World/SensorCam'); uc.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
        "UsdGeom.Xformable(uc).AddTranslateOp().Set((0.45,0.16,1.6))\n"
        "app=omni.kit.app.get_app()\nfrom isaacsim.sensors.camera import Camera\n"
        f"cam=Camera(prim_path='/World/SensorCam', frequency=20, resolution=({W},{H}))\n"
        "cam.initialize(); cam.add_distance_to_image_plane_to_frame(); cam.add_instance_segmentation_to_frame()\n"
        "omni.timeline.get_timeline_interface().play()\nfor _ in range(50): app.update()\n"
        "fr=cam.get_current_frame(); rgba=cam.get_rgba()\nfrom PIL import Image\n"
        f"Image.fromarray(rgba[:,:,:3].astype('uint8')).save('{PNG}')\n"
        "seg=fr['instance_segmentation']; data=np.asarray(seg['data'])\n"
        f"np.save('{SEG}', data); json.dump(seg.get('info',{{}}).get('idToLabels',{{}}), open('{IDS}','w'))\n"
        "print('SENSOR_DONE uniq='+str(len(np.unique(data))))\n")


async def run(c):
    r = await kit_tools.exec_sync(c, timeout=200)
    return (r.get("output", "") if isinstance(r, dict) else str(r))

print("P1:", [l for l in asyncio.run(run(kit)).splitlines() if "SENSOR_DONE" in l or "Error" in l][:2])
if not (os.path.exists(PNG) and os.path.exists(SEG)):
    print("capture failed"); sys.exit(1)

# Gemini points at the target (no layout given)
gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
prompt = (f"This {W}x{H} image shows 4 coloured cubes. Point at the {TARGET.upper()} cube. "
          f"Reply ONLY its centre pixel as JSON {{\"x\": <int>, \"y\": <int>}}.")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
mm = re.search(r'"x"\s*:\s*(\d+).*?"y"\s*:\s*(\d+)', ans, re.S)
if not mm:
    print("VLM no point:", ans[:100]); sys.exit(1)
gx, gy = min(int(mm.group(1)), W - 1), min(int(mm.group(2)), H - 1)

# SEGMENTATION resolves the exact prim (no layout). nearest-non-bg fallback for coarse points.
seg = np.load(SEG); ids = json.load(open(IDS))
bgids = [int(k) for k, v in ids.items() if v in ("BACKGROUND", "UNLABELLED")]
pid = int(seg[gy, gx])
if pid in bgids:
    mask = ~np.isin(seg, bgids); ys, xs = np.where(mask)
    i = int(np.argmin((xs - gx) ** 2 + (ys - gy) ** 2)); pid = int(seg[ys[i], xs[i]])
prim = ids.get(str(pid), "?")
leaf = prim.split("/")[-1]
print("Gemini point=(%d,%d) -> SEG prim=%s (target=Cube_%s) %s" % (
    gx, gy, prim, TARGET, "CORRECT" if leaf == f"Cube_{TARGET}" else "WRONG"))
if not prim.startswith("/World/Cube_"):
    print("seg did not resolve a cube — abort"); sys.exit(1)

# --- grasp phase: template with source_paths = the SEG-RESOLVED prim (NOT layout) ---
lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for col in CUBES:
    x, y = POS[col]; p = f"/World/Cube_{col}"
    lines += [f'create_prim(prim_path="{p}", prim_type="Cube", position=[{x}, {y}, 0.83], size=0.05)',
              'for _api in ("PhysicsRigidBodyAPI","PhysicsCollisionAPI","PhysicsMassAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)']
lines += ['', 'create_bin(prim_path="/World/Bin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.15])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",', f'    source_paths=["{prim}"],',
          '    destination_path="/World/Bin",', '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-VISION-SEG", "code": code, "code_template": code,
       "goal": f"Rigorous vision grasp: Gemini pointed at the {TARGET} cube; segmentation resolved {prim} (NO layout); Franka grasps that physical prim.",
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_vision_seg": {"target": TARGET, "gemini_point": [gx, gy], "seg_prim": prim},
       "verified_status": f"VISION-SEG (cont.319): source_paths from SEGMENTATION ({prim}), no layout. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-SEG.json", "w"), indent=2)
print("WROTE CP-VISION-SEG.json source_paths=[%s]  (seg-resolved, not layout)" % prim)
