"""VISION CONVEYOR SORT (cont.319): the composition multiplier, unblocked by the CP-37 conveyor-pick
stale-re-audit. A belt FEEDS 3 colour cubes to a sensor-gated pick zone; an overhead camera sees them,
Gemini classifies each colour, and the Franka picks each as it arrives + ROUTES to its colour bin.
Composes verified conveyor-pick (CP-37 N-of-2) x vision-classify x colour-sort routing.
scene_eyes + routing_validate verify each cube in its ASSIGNED colour bin. Run: python scripts/qa/llm_vision_conveyor_build.py"""
import os, sys, json, base64, urllib.request, re, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

# left-to-right on the belt (x increasing): (path, displayColor, x)
CUBES = [("/World/Cube_1", (1.0, 0.0, 0.0), -1.2),
         ("/World/Cube_2", (0.0, 1.0, 0.0), -1.0),
         ("/World/Cube_3", (0.0, 0.0, 1.0), -0.8)]
TRUTH = ["red", "green", "blue"]
BINS = {"red": "/World/Bin_red", "green": "/World/Bin_green", "blue": "/World/Bin_blue"}
PNG = "/tmp/llm_vision_conveyor.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         # belt surface as a static visual (objects sit on it for the render; physics belt is in the template)
         "bl=UsdGeom.Cube.Define(st,'/World/BeltVis'); bl.GetSizeAttr().Set(1.0)\n"
         "blx=UsdGeom.Xformable(bl); blx.AddTranslateOp().Set((-1.0,0.4,0.79)); blx.AddScaleOp().Set((1.2,0.4,0.04))\n"
         "bl.GetDisplayColorAttr().Set([(0.3,0.3,0.3)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/BeltVis'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for p, col, x in CUBES:
    build += (f"c=UsdGeom.Cube.Define(st,'{p}'); c.GetSizeAttr().Set(0.05)\n"
              f"UsdGeom.Xformable(c).AddTranslateOp().Set(({x},0.4,0.835)); c.GetDisplayColorAttr().Set([{col}])\n"
              f"UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('{p}'))\n")
build += ("cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(15.0)\n"
          "UsdGeom.Xformable(cam).AddTranslateOp().Set((-1.0,0.34,1.55))\n"
          "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
          "app=omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()\n"
          "for _ in range(40): app.update()\n"
          f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
          "for _ in range(20): app.update()\nprint('CAPTURED')\n")


async def render():
    r = await kit_tools.exec_sync(build, timeout=180)
    print("KIT:", (r.get("output", "") if isinstance(r, dict) else str(r)).splitlines()[-1:])

asyncio.run(render())
if not os.path.exists(PNG):
    print("NO PNG"); sys.exit(1)

gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
prompt = ("This image shows 3 cubes on a conveyor belt, left to right. Name each cube's COLOUR. "
          "Reply ONLY a JSON list of 3 colour words, left to right, e.g. [\"red\",\"green\",\"blue\"].")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
cats = re.findall(r'red|green|blue', ans.lower())[:3]
print("GEMINI-COLOUR raw=%r -> %s" % (ans.strip()[:80], cats))
if len(cats) != 3 or any(c not in BINS for c in cats):
    print("invalid colour classification — abort"); sys.exit(1)
print("classification vs truth:", cats, TRUTH, "->", "CORRECT" if cats == TRUTH else "MISMATCH(routes by what Gemini SAW)")

# Template: conveyor (physics belt) feeds the cubes; sensor-gated pick; route each by Gemini's colour.
mats = {"red": [1.0, 0.0, 0.0], "green": [0.0, 1.0, 0.0], "blue": [0.0, 0.0, 1.0]}
lines = ['create_scene_baseline(table_size=[3.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '',
         'create_conveyor(prim_path="/World/ConveyorBelt", position=[0.0, 0.4, 0.78], size=[3.0, 0.4, 0.05], surface_velocity=[0.2, 0, 0])', '']
for (p, col, x), cat in zip(CUBES, cats):
    lines += [f'create_prim(prim_path="{p}", prim_type="Cube", position=[{x}, 0.4, 0.835], size=0.05)',
              f'for _api in ("PhysicsRigidBodyAPI","PhysicsCollisionAPI","PhysicsMassAPI","PhysxRigidBodyAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'create_material(material_path="/World/Mat_{cat}_{p[-1]}", shader_type="OmniPBR", diffuse_color={mats[cat]})',
              f'assign_material(prim_path="{p}", material_path="/World/Mat_{cat}_{p[-1]}")',
              f'set_semantic_label(prim_path="{p}", class_name="{cat}", semantic_type="color")',
              f'apply_physics_material(prim_path="{p}", material_name="rubber")',
              f'set_attribute(prim_path="{p}", attr_name="physxRigidBody:sleepThreshold", value=0.0)', '']
for cat, bp in BINS.items():
    yb = {"red": -0.30, "green": 0.0, "blue": 0.30}[cat]
    lines.append(f'create_bin(prim_path="{bp}", position=[{yb}, -0.4, 0.75], size=[0.22, 0.22, 0.12])')
cr = ", ".join(f'"{c}": "{BINS[c]}"' for c in BINS)
srcs = ",".join(f'"{p}"' for p, _, _ in CUBES)
lines += ['', 'add_proximity_sensor(sensor_path="/World/PickSensor", position=[0.4, 0.4, 0.835], size=[0.06, 0.06, 0.06])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",', '    target_source="curobo",',
          '    sensor_path="/World/PickSensor",', '    belt_path="/World/ConveyorBelt",', f'    source_paths=[{srcs}],',
          '    destination_path="/World/Bin_red",', '    color_routing={' + cr + '},',
          '    planning_obstacles=["/World/Table", "/World/ConveyorBelt"],', ')']
code = "\n".join(lines) + "\n"
routing = {p.split("/")[-1]: BINS[c] for (p, _, _), c in zip(CUBES, cats)}
tpl = {"task_id": "CP-VISION-CONVEYOR",
       "goal": f"Vision conveyor sort: belt feeds 3 cubes; Gemini classified colours {cats}; Franka picks each at the sensor + routes to its colour bin {routing}.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin_red", "position": [-0.30, -0.4, 0.75], "size": [0.22, 0.22, 0.12]}},
       "_vision_conveyor": {"gemini_colour": cats, "routing": routing},
       "verified_status": f"VISION-CONVEYOR (cont.319): belt-fed colour-sort, routing from Gemini vision {cats}. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-CONVEYOR.json", "w"), indent=2)
print("WROTE CP-VISION-CONVEYOR.json routing=%s" % routing)
