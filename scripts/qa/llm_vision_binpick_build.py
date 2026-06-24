"""VISION BIN-PICK (cont.319, Anton CV direction): the canonical bin-picking task — a camera
looks INTO a shallow container of mixed real objects, Gemini identifies the target by appearance,
the Franka extracts ONLY it into an output bin (the input bin walls are a planning obstacle).
scene_eyes verifies the visually-identified object is extracted, the others left in the source bin.
Run: python scripts/qa/llm_vision_binpick_build.py box"""
import os, sys, json, base64, urllib.request, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# distinct objects spread in the source bin (target=box is a clean grasper; others just identified+left)
OBJS = {"brick": ("/World/Item_brick", "061_foam_brick.usd",      "_61_foam_brick",      [0.30, 0.20, 0.80]),
        "box":   ("/World/Item_box",   "009_gelatin_box.usd",     "_09_gelatin_box",     [0.45, 0.12, 0.80]),
        "can":   ("/World/Item_can",   "005_tomato_soup_can.usd", "_05_tomato_soup_can", [0.55, 0.22, 0.80])}
TARGET = sys.argv[1] if len(sys.argv) > 1 else "box"
PNG = "/tmp/llm_vision_binpick.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
         "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.42,0.16,0.375)); tx.AddScaleOp().Set((1.3,1.3,0.75))\n"
         "tb.GetDisplayColorAttr().Set([(0.5,0.5,0.5)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
         # shallow source-bin floor (objects rest on it; walls added in the TEMPLATE as obstacle)
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for t, (p, usd, inner, pos) in OBJS.items():
    build += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{YCB}{usd}')\n"
              f"UsdGeom.Xformable(pr).AddTranslateOp().Set(({pos[0]},{pos[1]},{pos[2]}))\n")
build += ("cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(14.0)\n"
          "UsdGeom.Xformable(cam).AddTranslateOp().Set((0.42,0.16,1.6))\n"   # straight above the bin
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
desc = {"brick": "the flat red brick", "box": "the boxed product (gelatin box)", "can": "the cylindrical can"}[TARGET]
prompt = ("This is a top-down view into a bin containing several objects. The robot must extract %s. "
          "Looking ONLY at the image, which object type is it? Reply ONE word from {brick, box, can}." % desc)
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
got = next((t for t in OBJS if t in ans.lower()), None)
print("GEMINI-BINPICK-RAW=%r -> type=%s (target=%s) %s" % (ans.strip()[:60], got, TARGET, "CORRECT" if got == TARGET else "WRONG"))
if got is None:
    print("no valid type — abort"); sys.exit(1)
pick = OBJS[got][0]

# template: objects in a walled source bin (obstacle), extract the visually-identified one to output bin
lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '',
         'create_bin(prim_path="/World/SourceBin", position=[0.42, 0.16, 0.75], size=[0.42, 0.34, 0.05])', '']
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
tpl = {"task_id": "CP-VISION-BINPICK",
       "goal": f"Vision bin-pick: Gemini SAW into the bin + visually identified the {TARGET} ({pick}); Franka extracts ONLY it to the output bin.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/OutBin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_vision_binpick": {"target": TARGET, "gemini_visual_type": got, "selected": pick},
       "verified_status": f"VISION-BINPICK (cont.319): source_paths from Gemini VISUAL id into a bin ({pick}). UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-BINPICK.json", "w"), indent=2)
print("WROTE CP-VISION-BINPICK.json source_paths=[%s]" % pick)
