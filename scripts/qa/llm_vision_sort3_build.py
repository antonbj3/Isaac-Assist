"""VISION 3-SHAPE SORT (cont.319): the sort the can-tip BLOCKED, now unblocked by per-asset YCB
rotation. Gemini SEES 3 distinct shapes (cylinder can / box / flat brick) + classifies each
(cylinder vs box) -> routes to its category bin. Validates the can-fix (rotation_euler=[90,0,0])
in a multi-pick sort. scene_eyes + routing_validate verify each object in its ASSIGNED bin.
Run: python scripts/qa/llm_vision_sort3_build.py"""
import os, sys, json, base64, urllib.request, re, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# left-to-right: (path, usd, inner, [x,y,z], rotation_euler). PER-ASSET orientation (can=[90,0,0]).
OBJS = [("/World/Item_can",   "005_tomato_soup_can.usd", "_05_tomato_soup_can", [0.32, 0.16, 0.82], [90, 0, 0]),
        ("/World/Item_box",   "009_gelatin_box.usd",     "_09_gelatin_box",     [0.42, 0.16, 0.82], [0, 0, 0]),
        ("/World/Item_brick", "061_foam_brick.usd",      "_61_foam_brick",      [0.52, 0.16, 0.82], [0, 0, 0])]
BINS = {"cylinder": "/World/Bin_cyl", "box": "/World/Bin_box"}
TRUTH = ["cylinder", "box", "box"]  # can, gelatin box, foam brick
PNG = "/tmp/llm_vision_sort3.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
         "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.42,0.16,0.40)); tx.AddScaleOp().Set((1.2,1.2,0.8))\n"
         "tb.GetDisplayColorAttr().Set([(0.55,0.55,0.55)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for p, usd, inner, pos, rot in OBJS:
    build += (f"pr=st.DefinePrim('{p}','Xform'); pr.GetReferences().AddReference('{YCB}{usd}')\n"
              f"_xf=UsdGeom.Xformable(pr); _xf.AddTranslateOp().Set(({pos[0]},{pos[1]},{pos[2]})); _xf.AddRotateXYZOp().Set(({rot[0]}.0,{rot[1]}.0,{rot[2]}.0))\n")
build += ("cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(14.0)\n"
          "UsdGeom.Xformable(cam).AddTranslateOp().Set((0.42,-0.10,1.55))\n"
          "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
          "app=omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()\n"
          "for _ in range(260): app.update()\n"
          f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
          "for _ in range(20): app.update()\nprint('CAPTURED')\n")


async def render():
    r = await kit_tools.exec_sync(build, timeout=200)
    print("KIT:", (r.get("output", "") if isinstance(r, dict) else str(r)).splitlines()[-1:])

asyncio.run(render())
if not os.path.exists(PNG):
    print("NO PNG"); sys.exit(1)

gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
prompt = ("This image shows 3 objects on a table, left to right. Classify EACH by shape as either "
          "'cylinder' (round/can-like) or 'box' (rectangular block). Reply ONLY as a JSON list of 3 words, "
          "left to right, e.g. [\"cylinder\",\"box\",\"box\"].")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
cats = re.findall(r'cylinder|box', ans.lower())[:3]
print("GEMINI-CLASSIFY raw=%r -> %s" % (ans.strip()[:80], cats))
if len(cats) != 3 or any(c not in BINS for c in cats):
    print("invalid classification — abort"); sys.exit(1)
print("classification vs truth:", cats, TRUTH, "->", "CORRECT" if cats == TRUTH else "MISMATCH(routes by what Gemini SAW)")

lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for (p, usd, inner, pos, rot), cat in zip(OBJS, cats):
    lines += [f'create_prim(prim_path="{p}", prim_type="Xform", position={pos}, rotation_euler={rot})',
              f'add_reference(prim_path="{p}", reference_path="{YCB}{usd}")',
              'for _api in ("PhysicsRigidBodyAPI", "PhysicsMassAPI", "PhysxRigidBodyAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'apply_api_schema(prim_path="{p}/{inner}", schema_name="PhysicsCollisionAPI")',
              f'simplify_collision(prim_path="{p}/{inner}", approximation="convexHull")',
              f'apply_physics_material(prim_path="{p}/{inner}", material_name="rubber")',
              f'set_semantic_label(prim_path="{p}", semantic_type="color", class_name="{cat}")', '']
cr = ", ".join(f'"{c}": "{BINS[c]}"' for c in BINS)
srcs = ",".join(f'"{p}"' for p, _, _, _, _ in OBJS)
lines += ['create_bin(prim_path="/World/Bin_cyl", position=[0.0, -0.45, 0.75], size=[0.22, 0.22, 0.15])',
          'create_bin(prim_path="/World/Bin_box", position=[0.32, -0.45, 0.75], size=[0.22, 0.22, 0.15])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",', f'    source_paths=[{srcs}],',
          '    destination_path="/World/Bin_cyl",', '    color_routing={' + cr + '},',
          '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
routing = {p.split("/")[-1]: BINS[c] for (p, _, _, _, _), c in zip(OBJS, cats)}
tpl = {"task_id": "CP-VISION-SORT3",
       "goal": f"Vision 3-shape sort: Gemini SAW + classified shapes {cats}; Franka routes each to its category bin {routing}.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin_cyl", "position": [0.0, -0.45, 0.75], "size": [0.22, 0.22, 0.15]}},
       "_vision_sort3": {"gemini_classify": cats, "routing": routing},
       "verified_status": f"VISION-SORT3 (cont.319): color_routing from Gemini shape-classify {cats}. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-SORT3.json", "w"), indent=2)
print("WROTE CP-VISION-SORT3.json routing=%s" % routing)
