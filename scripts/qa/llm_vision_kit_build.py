"""VISION KITTING / order fulfilment (cont.319): the camera sees a bin of mixed objects, Gemini
reads an ORDER (a list of needed item types), identifies which objects match, and the Franka picks
ONLY the ordered subset into a kit tray — leaving the rest. This is multi-target SELECTIVE pick
(distinct from single bin-pick and from sort-all). Exercises the gate's claimed-scoping with MULTIPLE
claimed picks. scene_eyes verifies the ordered items delivered + the others left.
Run: python scripts/qa/llm_vision_kit_build.py "a soup can and a gelatin box" """
import os, sys, json, base64, urllib.request, re, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# (path, usd, inner, [x,y,z], rotation_euler). Picked objects (can,box) at reachable x; left at far x.
OBJS = {"can":    ("/World/Item_can",    "005_tomato_soup_can.usd", "_05_tomato_soup_can", [0.32, 0.16, 0.82], [90, 0, 0]),
        "box":    ("/World/Item_box",    "009_gelatin_box.usd",     "_09_gelatin_box",     [0.42, 0.16, 0.82], [0, 0, 0]),
        "brick":  ("/World/Item_brick",  "061_foam_brick.usd",      "_61_foam_brick",      [0.30, 0.30, 0.82], [0, 0, 0]),
        "banana": ("/World/Item_banana", "011_banana.usd",          "_11_banana",          [0.44, 0.30, 0.82], [90, 0, 0])}
ORDER = sys.argv[1] if len(sys.argv) > 1 else "a soup can and a gelatin box"
PNG = "/tmp/llm_vision_kit.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
         "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.40,0.23,0.40)); tx.AddScaleOp().Set((1.4,1.4,0.8))\n"
         "tb.GetDisplayColorAttr().Set([(0.55,0.55,0.55)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for t, (p, usd, inner, pos, rot) in OBJS.items():
    build += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{YCB}{usd}')\n"
              f"_xf=UsdGeom.Xformable(pr); _xf.AddTranslateOp().Set(({pos[0]},{pos[1]},{pos[2]})); _xf.AddRotateXYZOp().Set(({rot[0]}.0,{rot[1]}.0,{rot[2]}.0))\n")
build += ("cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(15.0)\n"
          "UsdGeom.Xformable(cam).AddTranslateOp().Set((0.40,0.23,1.7))\n"
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
prompt = ("This is a top-down view of a bin with several objects: a soup can (cylinder), a gelatin box, "
          "a red foam brick, and a banana. A picking ORDER needs: %s. Looking at the image, which object "
          "TYPES does the order need? Reply ONLY a JSON list from {can, box, brick, banana}, e.g. "
          "[\"can\",\"box\"]." % ORDER)
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
picked = [t for t in OBJS if re.search(r'\b' + t + r'\b', ans.lower())]
print("ORDER=%r  GEMINI=%r  -> picked types=%s" % (ORDER, ans.strip()[:60], picked))
if not picked:
    print("no items identified — abort"); sys.exit(1)
src_paths = [OBJS[t][0] for t in picked]

lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for t, (p, usd, inner, pos, rot) in OBJS.items():
    lines += [f'create_prim(prim_path="{p}", prim_type="Xform", position={pos}, rotation_euler={rot})',
              f'add_reference(prim_path="{p}", reference_path="{YCB}{usd}")',
              'for _api in ("PhysicsRigidBodyAPI", "PhysicsMassAPI", "PhysxRigidBodyAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'apply_api_schema(prim_path="{p}/{inner}", schema_name="PhysicsCollisionAPI")',
              f'simplify_collision(prim_path="{p}/{inner}", approximation="convexHull")',
              f'apply_physics_material(prim_path="{p}/{inner}", material_name="rubber")', '']
srcs = ",".join(f'"{s}"' for s in src_paths)
lines += ['create_bin(prim_path="/World/KitBin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.12])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",', f'    source_paths=[{srcs}],',
          '    destination_path="/World/KitBin",', '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-VISION-KIT",
       "goal": f"Vision KITTING/order fulfilment: order {ORDER!r}; Gemini identified {picked}; Franka picks ONLY the ordered subset {src_paths} into the kit tray, leaving the rest.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/KitBin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.12]}},
       "_vision_kit": {"order": ORDER, "picked_types": picked, "source_paths": src_paths},
       "verified_status": f"VISION-KIT (cont.319): multi-target selective pick from Gemini order-read {picked}. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-KIT.json", "w"), indent=2)
print("WROTE CP-VISION-KIT.json source_paths=%s" % src_paths)
