"""LLM-VISION pick on REAL YCB objects (cont.319, Anton CV direction): Gemini SEES the
rendered scene and identifies the target object VISUALLY (by appearance, returns its type),
we map type->prim and reuse the GOLD YCB grasp (CP-LLM-PICK-REAL structure). scene_eyes verifies
only the visually-selected object is delivered. Combines visual real-object ID (proven 3/3) +
real-object grasp (gold). The raycast-pose path is blocked for YCB (referenced mesh colliders are
not scene-query-hittable) — not needed: the controller bbox-localizes the selected prim.
Run: python scripts/qa/llm_vision_ycb_build.py box"""
import os, sys, json, base64, urllib.request, re, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# type -> (path, usd, inner mesh, [x,y,z], rotation_euler). YCB orientation is PER-ASSET: the gelatin
# BOX is graspable in its native pose ([0,0,0]); the tomato CAN + curved BANANA need [90,0,0] to settle
# graspable (the Y-up-native cylinder/banana — matches CP-YCB-02/BANANA). A blanket rotation TOPPLES the box.
OBJS = {"banana": ("/World/Item_banana", "011_banana.usd",          "_11_banana",          [0.32, 0.16, 0.82], [90, 0, 0]),
        "can":    ("/World/Item_can",    "005_tomato_soup_can.usd", "_05_tomato_soup_can", [0.42, 0.16, 0.82], [90, 0, 0]),
        "box":    ("/World/Item_box",    "009_gelatin_box.usd",     "_09_gelatin_box",     [0.52, 0.16, 0.82], [0, 0, 0])}
TARGET = sys.argv[1] if len(sys.argv) > 1 else "box"
PNG = "/tmp/llm_vision_ycb.png"

build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "tb=UsdGeom.Cube.Define(st,'/World/Table'); tb.GetSizeAttr().Set(1.0)\n"
         "tx=UsdGeom.Xformable(tb); tx.AddTranslateOp().Set((0.42,0.16,0.40)); tx.AddScaleOp().Set((1.2,1.2,0.8))\n"
         "tb.GetDisplayColorAttr().Set([(0.55,0.55,0.55)]); UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('/World/Table'))\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(700); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for t, (p, usd, inner, pos, rot) in OBJS.items():
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

# Gemini SEES the image and identifies the target object's TYPE visually (no position hint, no GT)
gp = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
desc = {"banana": "the one you would peel and eat", "can": "the metal cylindrical container",
        "box": "the rectangular boxed product"}[TARGET]
prompt = ("This image shows 3 objects on a table. The robot must pick %s. "
          "Looking ONLY at the image, which object type is it? Reply with ONE word from {banana, can, box}." % desc)
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(PNG, 'rb').read()).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
got = next((t for t in OBJS if t in ans.lower()), None)
print("GEMINI-VISION-RAW=%r -> type=%s (target=%s) %s" % (ans.strip()[:60], got, TARGET, "CORRECT" if got == TARGET else "WRONG"))
if got is None:
    print("no valid type — abort"); sys.exit(1)
pick = OBJS[got][0]

# reuse the GOLD YCB grasp template (CP-LLM-PICK-REAL structure), source_paths = the VISUALLY-selected object
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
lines += ['create_bin(prim_path="/World/Bin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.15])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",', f'    source_paths=["{pick}"],',
          '    destination_path="/World/Bin",', '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-VISION-YCB",
       "goal": f"Vision-pick on REAL objects: Gemini SAW the scene + visually identified the {TARGET} ({pick}); Franka picks ONLY it.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_vision_ycb": {"target": TARGET, "gemini_visual_type": got, "selected": pick},
       "verified_status": f"VISION-YCB (cont.319): source_paths from Gemini VISUAL id ({pick}). UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-YCB.json", "w"), indent=2)
print("WROTE CP-VISION-YCB.json source_paths=[%s]" % pick)
