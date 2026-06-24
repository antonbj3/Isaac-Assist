"""LLM-pick end-to-end (#50): Gemini SELECTS which cube to pick, then we generate
a pick-place template with source_paths = the LLM's choice, for scene_eyes to verify
the selected cube (and ONLY it) is delivered. Run with a TASK arg, e.g.
  python scripts/qa/llm_pick_build.py "Pick the blue cube."
Writes workspace/templates/CP-LLM-PICK.json. Then: scene_eyes.py CP-LLM-PICK 120"""
import asyncio, os, sys, json
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

CUBES = {  # path -> (color, [x,y,z])
    "/World/Cube_red":   ("RED",   [0.32, 0.16, 0.79]),
    "/World/Cube_green": ("GREEN", [0.42, 0.16, 0.79]),
    "/World/Cube_blue":  ("BLUE",  [0.52, 0.16, 0.79]),
}
SYS = ("You are a robot pick-selector. Given a scene and a task, choose the ONE object to pick. "
       "Reply with ONLY its prim path (e.g. /World/Cube_red) and nothing else.")
TASK = sys.argv[1] if len(sys.argv) > 1 else "Pick the red cube."


async def select():
    scene = "Scene objects (Isaac Sim prims a Franka can pick):\n" + "\n".join(
        f"- {p} : a {c[0]} cube, position {c[1]}" for p, c in CUBES.items())
    p = GeminiProvider(api_key=os.environ.get("GEMINI_API_KEY", "vertex-adc"), model="gemini-2.5-flash")
    r = await p.complete([{"role": "user", "content": scene + "\n\nTask: " + TASK}], {"system_override": SYS})
    ans = (r.text or "").strip()
    pick = next((p for p in CUBES if p in ans), None)
    return pick, ans


pick, raw = asyncio.run(select())
print(f"TASK={TASK!r}  GEMINI_RAW={raw!r}  -> PICK={pick}")
if pick is None:
    print("LLM-PICK: no valid selection — abort"); sys.exit(1)

# Generate the template: 3 cubes, source_paths = ONLY the LLM's pick, bin destination.
lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for p, (col, pos) in CUBES.items():
    lines.append(f'create_prim(prim_path="{p}", prim_type="Cube", position={pos}, size=0.05)')
    lines.append(f'for _api in ("PhysicsRigidBodyAPI","PhysicsCollisionAPI","PhysicsMassAPI"):')
    lines.append(f'    apply_api_schema(prim_path="{p}", schema_name=_api)')
    lines.append(f'set_semantic_label(prim_path="{p}", semantic_type="color", class_name="{col.lower()}")')
lines += ['', 'create_bin(prim_path="/World/Bin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.15])', '',
          'setup_pick_place_controller(',
          '    robot_path="/World/Franka",', '    robot_family="franka",', '    target_source="curobo",',
          f'    source_paths=["{pick}"],',  # ONLY the LLM-selected cube
          '    destination_path="/World/Bin",', '    planning_obstacles=["/World/Table"],', ')']
tpl = {"task_id": "CP-LLM-PICK",
       "goal": f"LLM-pick: Gemini selected {pick} for task {TASK!r}; the Franka picks ONLY that cube, leaving the others.",
       "code": "\n".join(lines) + "\n",
       "code_template": "\n".join(lines) + "\n",
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_llm_pick": {"task": TASK, "selected": pick},
       "verified_status": f"LLM-PICK (cont.319): source_paths set from Gemini's selection ({pick}). UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-LLM-PICK.json", "w"), indent=2)
print(f"WROTE CP-LLM-PICK.json with source_paths=[{pick}]")
