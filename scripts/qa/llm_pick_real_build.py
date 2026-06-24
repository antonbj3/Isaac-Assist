"""LLM-pick on REAL objects (#50): Gemini selects a YCB object by name from a
scene, then we generate a pick-place with source_paths=[selection] for scene_eyes
to verify the LLM's object (and only it) is picked. Combines LLM-select + real-object
manipulation. Run: python scripts/qa/llm_pick_real_build.py "Pick the banana." """
import asyncio, os, sys, json
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/"
# path -> (human name, usd file, inner mesh, [x,y,z])
OBJS = {
    "/World/Item_banana": ("a yellow BANANA",      "011_banana.usd",          "_11_banana",          [0.32, 0.16, 0.82]),
    "/World/Item_can":    ("a tomato SOUP CAN",     "005_tomato_soup_can.usd", "_05_tomato_soup_can", [0.42, 0.16, 0.82]),
    "/World/Item_box":    ("a GELATIN BOX",         "009_gelatin_box.usd",     "_09_gelatin_box",     [0.52, 0.16, 0.82]),
}
SYS = ("You are a robot pick-selector. Given a scene and a task, choose the ONE object to pick. "
       "Reply with ONLY its prim path (e.g. /World/Item_banana) and nothing else.")
TASK = sys.argv[1] if len(sys.argv) > 1 else "Pick the banana."


async def select():
    scene = "Scene objects (real YCB items a Franka can pick):\n" + "\n".join(
        f"- {p} : {o[0]}, position {o[3]}" for p, o in OBJS.items())
    g = GeminiProvider(api_key=os.environ.get("GEMINI_API_KEY", "vertex-adc"), model="gemini-2.5-flash")
    r = await g.complete([{"role": "user", "content": scene + "\n\nTask: " + TASK}], {"system_override": SYS})
    ans = (r.text or "").strip()
    return next((p for p in OBJS if p in ans), None), ans


pick, raw = asyncio.run(select())
print(f"TASK={TASK!r}  GEMINI_RAW={raw!r}  -> PICK={pick}")
if pick is None:
    print("LLM-PICK-REAL: no valid selection — abort"); sys.exit(1)

lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for p, (name, usd, inner, pos) in OBJS.items():
    lines += [f'create_prim(prim_path="{p}", prim_type="Xform", position={pos})',
              f'add_reference(prim_path="{p}", reference_path="{YCB}{usd}")',
              f'for _api in ("PhysicsRigidBodyAPI", "PhysicsMassAPI", "PhysxRigidBodyAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'apply_api_schema(prim_path="{p}/{inner}", schema_name="PhysicsCollisionAPI")',
              f'simplify_collision(prim_path="{p}/{inner}", approximation="convexHull")',
              f'apply_physics_material(prim_path="{p}/{inner}", material_name="rubber")', '']
lines += ['create_bin(prim_path="/World/Bin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.15])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",', f'    source_paths=["{pick}"],',
          '    destination_path="/World/Bin",', '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-LLM-PICK-REAL",
       "goal": f"LLM-pick on REAL objects: Gemini selected {pick} for {TASK!r}; Franka picks ONLY that YCB object.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_llm_pick": {"task": TASK, "selected": pick},
       "verified_status": f"LLM-PICK-REAL (cont.319): source_paths from Gemini ({pick}). UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-LLM-PICK-REAL.json", "w"), indent=2)
print(f"WROTE CP-LLM-PICK-REAL.json source_paths=[{pick}]")
