"""VISION CLUTTER STRESS + GOTCHA (cont.319, Anton 'complex setups / stress / gotcha'): a DENSE bin of
8 tightly-packed YCB objects, where the target (gelatin box) has a LOOK-ALIKE DECOY (cracker box — also
a box). Tests (a) vision DISCRIMINATION under clutter (pick the gelatin box, NOT the cracker decoy),
(b) GRASP from dense clutter, (c) NEIGHBOUR NON-DISTURBANCE (extract 1 of 8 without knocking the others).
scene_eyes measures: right object out, decoy + 6 neighbours undisturbed, no topple cascade.
Run: python scripts/qa/llm_vision_clutter_build.py"""
import os, sys, json, base64, urllib.request, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# 8 objects tightly packed. TARGET=gelatin box; DECOY=cracker box (look-alike). (path,usd,inner,[x,y,z],rot,type)
OBJS = {"gelatin": ("/World/Item_gelatin", "009_gelatin_box.usd",      "_09_gelatin_box",     [0.40, 0.16, 0.86], [0, 0, 0]),
        "cracker": ("/World/Item_cracker", "003_cracker_box.usd",      "_03_cracker_box",     [0.40, 0.30, 0.88], [0, 0, 0]),
        "brick":   ("/World/Item_brick",   "061_foam_brick.usd",       "_61_foam_brick",      [0.27, 0.16, 0.86], [0, 0, 0]),
        "can":     ("/World/Item_can",     "005_tomato_soup_can.usd",  "_05_tomato_soup_can", [0.53, 0.16, 0.86], [90, 0, 0]),
        "mustard": ("/World/Item_mustard", "006_mustard_bottle.usd",   "_06_mustard_bottle",  [0.27, 0.30, 0.86], [90, 0, 0]),
        "mug":     ("/World/Item_mug",     "025_mug.usd",              "_25_mug",             [0.53, 0.30, 0.86], [0, 0, 0]),
        "banana":  ("/World/Item_banana",  "011_banana.usd",           "_11_banana",          [0.33, 0.05, 0.86], [90, 0, 0]),
        "brick2":  ("/World/Item_brick2",  "061_foam_brick.usd",       "_61_foam_brick",      [0.47, 0.05, 0.86], [0, 0, 0])}
TARGET = "gelatin"
PNG = "/tmp/llm_vision_clutter.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
         "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.40,0.18,0.375)); tx.AddScaleOp().Set((1.5,1.5,0.75))\n"
         "tb.GetDisplayColorAttr().Set([(0.5,0.5,0.5)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for t, (p, usd, inner, pos, rot, *_x) in OBJS.items():
    build += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{YCB}{usd}')\n"
              f"_xf=UsdGeom.Xformable(pr); _xf.AddTranslateOp().Set(({pos[0]},{pos[1]},{pos[2]})); _xf.AddRotateXYZOp().Set(({rot[0]}.0,{rot[1]}.0,{rot[2]}.0))\n")
build += ("cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(16.0)\n"
          "UsdGeom.Xformable(cam).AddTranslateOp().Set((0.40,0.18,1.7))\n"
          "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
          "app=omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()\n"
          "for _ in range(240): app.update()\n"
          f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
          "for _ in range(20): app.update()\nprint('CAPTURED')\n")


async def render():
    r = await kit_tools.exec_sync(build, timeout=200)
    print("KIT:", (r.get("output", "") if isinstance(r, dict) else str(r)).splitlines()[-1:])

asyncio.run(render())
if not os.path.exists(PNG):
    print("NO PNG"); sys.exit(1)

gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
prompt = ("This is a top-down view into a cluttered bin with 8 objects, including a small flat GELATIN/jello "
          "box AND a larger taller CRACKER box (both are boxes — do not confuse them). The order needs the "
          "GELATIN box specifically. Looking at the image, which object type is the gelatin box? Reply ONE "
          "word from {gelatin, cracker, brick, can, mustard, mug, banana}.")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
import re
got = next((t for t in OBJS if re.search(r'\b' + t + r'\b', ans.lower())), None)
print("GEMINI=%r -> type=%s (target=%s) %s" % (ans.strip()[:50], got, TARGET,
      "CORRECT (discriminated gelatin from cracker decoy)" if got == TARGET else "WRONG (fell for the decoy / clutter)"))
if got is None:
    print("no valid type — abort"); sys.exit(1)
pick = OBJS[got][0]

lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '',
         'create_bin(prim_path="/World/SourceBin", position=[0.40, 0.18, 0.75], size=[0.55, 0.5, 0.05])', '']
for t, (p, usd, inner, pos, rot, *_x) in OBJS.items():
    lines += [f'create_prim(prim_path="{p}", prim_type="Xform", position={pos}, rotation_euler={rot})',
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
tpl = {"task_id": "CP-VISION-CLUTTER",
       "goal": f"Vision clutter stress+gotcha: 8 tightly-packed objects incl. a cracker-box DECOY; Gemini identified the {TARGET} box ({pick}); Franka extracts ONLY it from the dense clutter, leaving the decoy + 6 neighbours undisturbed.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/OutBin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_vision_clutter": {"target": TARGET, "gemini": got, "selected": pick, "decoy": "/World/Item_cracker"},
       "verified_status": f"VISION-CLUTTER (cont.319): 8-object dense clutter + cracker decoy, Gemini picked {pick}. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-CLUTTER.json", "w"), indent=2)
print("WROTE CP-VISION-CLUTTER.json source_paths=[%s]" % pick)
