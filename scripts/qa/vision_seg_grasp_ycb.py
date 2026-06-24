"""RIGOROUS vision grasp on REAL YCB objects (cont.319): the case the raycast-path could NOT do
(referenced YCB colliders aren't raycast-hittable) — now solved by Camera-sensor instance-segmentation.
Gemini points at the target -> seg[pixel] -> EXACT Item prim path (no layout) -> Franka grasps it.
2x2 mixed YCB scene. scene_eyes verifies the right physical object delivered. Run: python scripts/qa/vision_seg_grasp_ycb.py box"""
import os, sys, json, base64, urllib.request, re, asyncio
import numpy as np
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# 2x2 mixed YCB. (usd, inner, [x,y], rot)
# 2x2: front row y=0.16 (proven graspable band), back row y=0.26 -> still 2 rows (horizontal-ambiguous)
OBJS = {"box":    ("009_gelatin_box.usd",     "_09_gelatin_box",     [0.40, 0.16], [0, 0, 0]),
        "brick":  ("061_foam_brick.usd",      "_61_foam_brick",      [0.50, 0.16], [0, 0, 0]),
        "can":    ("005_tomato_soup_can.usd", "_05_tomato_soup_can", [0.40, 0.26], [90, 0, 0]),
        "banana": ("011_banana.usd",          "_11_banana",          [0.50, 0.26], [90, 0, 0])}
TARGET = sys.argv[1] if len(sys.argv) > 1 else "box"
PNG = "/tmp/vsgy_rgb.png"; SEG = "/tmp/vsgy_seg.npy"; IDS = "/tmp/vsgy_ids.json"
W, H = 640, 480

kit = ("import omni.usd, omni.kit.app, omni.timeline, numpy as np, json\n"
       "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
       "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
       "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
       "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
       "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.45,0.16,0.40)); tx.AddScaleOp().Set((1.2,1.2,0.8)); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
       "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(800); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1200)\n")
for n, (usd, inner, (x, y), rot) in OBJS.items():
    p = f"/World/Item_{n}"
    kit += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{YCB}{usd}')\n"
            f"_xf=UsdGeom.Xformable(pr); _xf.AddTranslateOp().Set(({x},{y},0.84)); _xf.AddRotateXYZOp().Set(({rot[0]}.0,{rot[1]}.0,{rot[2]}.0))\n"
            f"try:\n    from semantics.schema.editor import PrimSemanticData\n    PrimSemanticData(st.GetPrimAtPath('{p}')).add_entry('class','{n}')\nexcept Exception: pass\n")
kit += ("uc=UsdGeom.Camera.Define(st,'/World/SensorCam'); uc.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
        "UsdGeom.Xformable(uc).AddTranslateOp().Set((0.45,0.16,1.55))\n"
        "app=omni.kit.app.get_app()\nfrom isaacsim.sensors.camera import Camera\n"
        f"cam=Camera(prim_path='/World/SensorCam', frequency=20, resolution=({W},{H}))\n"
        "cam.initialize(); cam.add_instance_segmentation_to_frame()\n"
        "omni.timeline.get_timeline_interface().play()\nfor _ in range(220): app.update()\n"
        "fr=cam.get_current_frame(); rgba=cam.get_rgba()\nfrom PIL import Image\n"
        f"Image.fromarray(rgba[:,:,:3].astype('uint8')).save('{PNG}')\n"
        "seg=fr['instance_segmentation']; data=np.asarray(seg['data'])\n"
        f"np.save('{SEG}', data); json.dump(seg.get('info',{{}}).get('idToLabels',{{}}), open('{IDS}','w'))\n"
        "print('SENSOR_DONE uniq='+str(len(np.unique(data))))\n")


async def run(c):
    r = await kit_tools.exec_sync(c, timeout=240)
    return (r.get("output", "") if isinstance(r, dict) else str(r))

print("P1:", [l for l in asyncio.run(run(kit)).splitlines() if "SENSOR_DONE" in l or "Error" in l][:2])
if not (os.path.exists(PNG) and os.path.exists(SEG)):
    print("capture failed"); sys.exit(1)

gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
desc = {"box": "the gelatin box", "brick": "the red foam brick", "can": "the soup can", "banana": "the banana"}[TARGET]
prompt = (f"This {W}x{H} top-down image shows 4 objects. Point at {desc}. Reply ONLY its centre pixel as JSON {{\"x\":<int>,\"y\":<int>}}.")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
mm = re.search(r'"x"\s*:\s*(\d+).*?"y"\s*:\s*(\d+)', ans, re.S)
if not mm:
    print("VLM no point:", ans[:100]); sys.exit(1)
gx, gy = min(int(mm.group(1)), W - 1), min(int(mm.group(2)), H - 1)
seg = np.load(SEG); ids = json.load(open(IDS))
bgids = [int(k) for k, v in ids.items() if v in ("BACKGROUND", "UNLABELLED")]
pid = int(seg[gy, gx])
if pid in bgids:
    mask = ~np.isin(seg, bgids); ys, xs = np.where(mask)
    i = int(np.argmin((xs - gx) ** 2 + (ys - gy) ** 2)); pid = int(seg[ys[i], xs[i]])
prim = ids.get(str(pid), "?"); leaf = prim.split("/")[-1]
print("Gemini point=(%d,%d) -> SEG prim=%s (target=Item_%s) %s" % (gx, gy, prim, TARGET, "CORRECT" if leaf == f"Item_{TARGET}" else "WRONG"))
if not prim.startswith("/World/Item_"):
    print("seg did not resolve an item — abort"); sys.exit(1)

lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for n, (usd, inner, (x, y), rot) in OBJS.items():
    p = f"/World/Item_{n}"
    lines += [f'create_prim(prim_path="{p}", prim_type="Xform", position=[{x}, {y}, 0.84], rotation_euler={rot})',
              f'add_reference(prim_path="{p}", reference_path="{YCB}{usd}")',
              'for _api in ("PhysicsRigidBodyAPI","PhysicsMassAPI","PhysxRigidBodyAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'apply_api_schema(prim_path="{p}/{inner}", schema_name="PhysicsCollisionAPI")',
              f'simplify_collision(prim_path="{p}/{inner}", approximation="convexHull")',
              f'apply_physics_material(prim_path="{p}/{inner}", material_name="rubber")']
lines += ['', 'create_bin(prim_path="/World/Bin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.15])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",', f'    source_paths=["{prim}"],',
          '    destination_path="/World/Bin",', '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-VISION-SEG-YCB", "code": code, "code_template": code,
       "goal": f"Rigorous vision grasp on REAL objects: Gemini pointed at {desc}; segmentation resolved {prim} (no layout, no raycast); Franka grasps it.",
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_vision_seg_ycb": {"target": TARGET, "gemini_point": [gx, gy], "seg_prim": prim},
       "verified_status": f"VISION-SEG-YCB (cont.319): source_paths from SEGMENTATION ({prim}) on real objects. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-SEG-YCB.json", "w"), indent=2)
print("WROTE CP-VISION-SEG-YCB.json source_paths=[%s] (seg-resolved real object)" % prim)
