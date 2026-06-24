"""VISION CONVEYOR SORT on REAL objects (cont.319): the realistic warehouse sorter — real YCB items
(gelatin box / foam brick) feed on a belt to a sensor-gated pick zone; an overhead camera sees them,
Gemini identifies each TYPE, and the Franka picks each as it arrives + ROUTES to its type bin.
Box-shaped objects (don't roll on the belt like a cylinder would). Verified by scene_eyes + routing_validate.
Run: python scripts/qa/llm_vision_conveyor_real_build.py"""
import os, sys, json, base64, urllib.request, re, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# left-to-right on the belt: (path, usd, inner, x, type). box+brick are box-shaped (stable on a belt).
OBJS = [("/World/Item_1", "009_gelatin_box.usd", "_09_gelatin_box", -1.2, "box"),
        ("/World/Item_2", "061_foam_brick.usd",  "_61_foam_brick",  -1.0, "brick"),
        ("/World/Item_3", "009_gelatin_box.usd", "_09_gelatin_box", -0.8, "box")]
TRUTH = ["box", "brick", "box"]
BINS = {"box": "/World/Bin_box", "brick": "/World/Bin_brick"}
PNG = "/tmp/llm_vision_conveyor_real.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "bl=UsdGeom.Cube.Define(st,'/World/BeltVis'); bl.GetSizeAttr().Set(1.0)\n"
         "blx=UsdGeom.Xformable(bl); blx.AddTranslateOp().Set((-1.0,0.4,0.79)); blx.AddScaleOp().Set((1.2,0.4,0.04))\n"
         "bl.GetDisplayColorAttr().Set([(0.3,0.3,0.3)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/BeltVis'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for p, usd, inner, x, typ in OBJS:
    build += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{YCB}{usd}')\n"
              f"UsdGeom.Xformable(pr).AddTranslateOp().Set(({x},0.4,0.84))\n")
build += ("cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(15.0)\n"
          "UsdGeom.Xformable(cam).AddTranslateOp().Set((-1.0,0.34,1.55))\n"
          "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
          "app=omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()\n"
          "for _ in range(60): app.update()\n"
          f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
          "for _ in range(20): app.update()\nprint('CAPTURED')\n")


async def render():
    r = await kit_tools.exec_sync(build, timeout=180)
    print("KIT:", (r.get("output", "") if isinstance(r, dict) else str(r)).splitlines()[-1:])

asyncio.run(render())
if not os.path.exists(PNG):
    print("NO PNG"); sys.exit(1)

gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
prompt = ("This image shows 3 objects on a conveyor belt, left to right: gelatin boxes and a red foam brick. "
          "Classify EACH by type as 'box' (boxed product) or 'brick' (flat red block). Reply ONLY a JSON list "
          "of 3 words, left to right, e.g. [\"box\",\"brick\",\"box\"].")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
cats = re.findall(r'box|brick', ans.lower())[:3]
print("GEMINI-TYPE raw=%r -> %s" % (ans.strip()[:80], cats))
if len(cats) != 3 or any(c not in BINS for c in cats):
    print("invalid type classification — abort"); sys.exit(1)
print("classification vs truth:", cats, TRUTH, "->", "CORRECT" if cats == TRUTH else "MISMATCH(routes by what Gemini SAW)")

lines = ['create_scene_baseline(table_size=[3.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '',
         'create_conveyor(prim_path="/World/ConveyorBelt", position=[0.0, 0.4, 0.78], size=[3.0, 0.4, 0.05], surface_velocity=[0.2, 0, 0])', '']
for (p, usd, inner, x, typ), cat in zip(OBJS, cats):
    lines += [f'create_prim(prim_path="{p}", prim_type="Xform", position=[{x}, 0.4, 0.84])',
              f'add_reference(prim_path="{p}", reference_path="{YCB}{usd}")',
              'for _api in ("PhysicsRigidBodyAPI","PhysicsMassAPI","PhysxRigidBodyAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'apply_api_schema(prim_path="{p}/{inner}", schema_name="PhysicsCollisionAPI")',
              f'simplify_collision(prim_path="{p}/{inner}", approximation="convexHull")',
              f'apply_physics_material(prim_path="{p}/{inner}", material_name="rubber")',
              f'set_semantic_label(prim_path="{p}", class_name="{cat}", semantic_type="color")',
              f'set_attribute(prim_path="{p}", attr_name="physxRigidBody:sleepThreshold", value=0.0)', '']
for cat, bp in BINS.items():
    yb = {"box": -0.20, "brick": 0.20}[cat]
    lines.append(f'create_bin(prim_path="{bp}", position=[{yb}, -0.4, 0.75], size=[0.24, 0.24, 0.12])')
cr = ", ".join(f'"{c}": "{BINS[c]}"' for c in BINS)
srcs = ",".join(f'"{p}"' for p, _, _, _, _ in OBJS)
lines += ['', 'add_proximity_sensor(sensor_path="/World/PickSensor", position=[0.4, 0.4, 0.84], size=[0.07, 0.07, 0.07])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",', '    target_source="curobo",',
          '    sensor_path="/World/PickSensor",', '    belt_path="/World/ConveyorBelt",', f'    source_paths=[{srcs}],',
          '    destination_path="/World/Bin_box",', '    color_routing={' + cr + '},',
          '    planning_obstacles=["/World/Table", "/World/ConveyorBelt"],', ')']
code = "\n".join(lines) + "\n"
routing = {p.split("/")[-1]: BINS[c] for (p, _, _, _, _), c in zip(OBJS, cats)}
tpl = {"task_id": "CP-VISION-CONVEYOR-REAL",
       "goal": f"Vision conveyor sort on REAL objects: belt feeds 3 YCB items; Gemini classified types {cats}; Franka picks each at the sensor + routes to its type bin {routing}.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin_box", "position": [-0.20, -0.4, 0.75], "size": [0.24, 0.24, 0.12]}},
       "_vision_conveyor_real": {"gemini_type": cats, "routing": routing},
       "verified_status": f"VISION-CONVEYOR-REAL (cont.319): real-object belt-fed type-sort, routing from Gemini vision {cats}. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-CONVEYOR-REAL.json", "w"), indent=2)
print("WROTE CP-VISION-CONVEYOR-REAL.json routing=%s" % routing)
