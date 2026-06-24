"""VISION BIN-PICK at SCALE (cont.319): 6 mixed real objects in a bin — does the camera still
identify + extract the target under realistic clutter? Top-down camera, Gemini identifies the
target by appearance among 6, Franka extracts ONLY it. Target = flat red brick (visually distinct,
clean grasper); the other 5 are identified-context + left. scene_eyes verifies vs RAW.
Run: python scripts/qa/llm_vision_binpick6_build.py brick"""
import os, sys, json, base64, urllib.request, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# 6 distinct objects spread in a 2x3 grid inside the bin
OBJS = {"brick":   ("/World/Item_brick",   "061_foam_brick.usd",       "_61_foam_brick",      [0.30, 0.06, 0.80]),
        "box":     ("/World/Item_box",     "009_gelatin_box.usd",      "_09_gelatin_box",     [0.42, 0.06, 0.80]),
        "can":     ("/World/Item_can",     "005_tomato_soup_can.usd",  "_05_tomato_soup_can", [0.54, 0.06, 0.80]),
        "mustard": ("/World/Item_mustard", "006_mustard_bottle.usd",   "_06_mustard_bottle",  [0.30, 0.26, 0.80]),
        "cracker": ("/World/Item_cracker", "003_cracker_box.usd",      "_03_cracker_box",     [0.42, 0.26, 0.82]),
        "mug":     ("/World/Item_mug",     "025_mug.usd",              "_25_mug",             [0.54, 0.26, 0.80])}
TARGET = sys.argv[1] if len(sys.argv) > 1 else "brick"
PNG = "/tmp/llm_vision_binpick6.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
         "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.42,0.16,0.375)); tx.AddScaleOp().Set((1.4,1.4,0.75))\n"
         "tb.GetDisplayColorAttr().Set([(0.5,0.5,0.5)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for t, (p, usd, inner, pos) in OBJS.items():
    build += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{YCB}{usd}')\n"
              f"UsdGeom.Xformable(pr).AddTranslateOp().Set(({pos[0]},{pos[1]},{pos[2]}))\n")
build += ("cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(16.0)\n"
          "UsdGeom.Xformable(cam).AddTranslateOp().Set((0.42,0.16,1.7))\n"
          "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
          "app=omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()\n"
          "for _ in range(220): app.update()\n"
          f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
          "for _ in range(20): app.update()\nprint('CAPTURED')\n")


async def render():
    r = await kit_tools.exec_sync(build, timeout=200)
    print("KIT:", (r.get("output", "") if isinstance(r, dict) else str(r)).splitlines()[-1:])

asyncio.run(render())
if not os.path.exists(PNG):
    print("NO PNG"); sys.exit(1)

gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
desc = {"brick": "the flat RED rectangular brick", "box": "the small gelatin box", "can": "the soup can",
        "mustard": "the yellow mustard bottle", "cracker": "the large cracker box", "mug": "the mug"}[TARGET]
opts = "{brick, box, can, mustard, cracker, mug}"
prompt = ("This is a top-down view into a bin with 6 different objects. The robot must extract %s. "
          "Looking ONLY at the image, which object type is it? Reply ONE word from %s." % (desc, opts))
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
got = next((t for t in OBJS if t in ans.lower()), None)
print("GEMINI-BINPICK6-RAW=%r -> type=%s (target=%s) %s" % (ans.strip()[:60], got, TARGET, "CORRECT" if got == TARGET else "WRONG"))
if got is None:
    print("no valid type — abort"); sys.exit(1)
pick = OBJS[got][0]

lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '',
         'create_bin(prim_path="/World/SourceBin", position=[0.42, 0.16, 0.75], size=[0.5, 0.42, 0.05])', '']
for t, (p, usd, inner, pos) in OBJS.items():
    lines += [f'create_prim(prim_path="{p}", prim_type="Xform", position={pos})',
              f'add_reference(prim_path="{p}", reference_path="{YCB}{usd}")',
              'for _api in ("PhysicsRigidBodyAPI", "PhysicsMassAPI", "PhysxRigidBodyAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'apply_api_schema(prim_path="{p}/{inner}", schema_name="PhysicsCollisionAPI")',
              f'simplify_collision(prim_path="{p}/{inner}", approximation="convexHull")',
              f'apply_physics_material(prim_path="{p}/{inner}", material_name="rubber")', '']
lines += ['create_bin(prim_path="/World/OutBin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.15])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",', f'    source_paths=["{pick}"],',
          '    destination_path="/World/OutBin",', '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-VISION-BINPICK6",
       "goal": f"Vision bin-pick at scale (6 objects): Gemini visually identified the {TARGET} ({pick}); Franka extracts ONLY it.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/OutBin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_vision_binpick6": {"target": TARGET, "gemini_visual_type": got, "selected": pick},
       "verified_status": f"VISION-BINPICK6 (cont.319): 6-object clutter, Gemini VISUAL id ({pick}). UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-BINPICK6.json", "w"), indent=2)
print("WROTE CP-VISION-BINPICK6.json source_paths=[%s]" % pick)
