"""LLM-driven SORT (#50/LLM-manipulation): Gemini reasons about a natural-language
SORTING RULE and assigns EACH object to a bin (not just one pick). We set color_routing
from Gemini's plan and scene_eyes verifies each object lands in the LLM-assigned bin.
Run: python scripts/qa/llm_sort_build.py "Warm colours to bin_A, cool colours to bin_B." """
import asyncio, os, sys, json, re
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

CUBES = {  # color -> [x,y,z] (in the +y reach band)
    "red":   [0.32, 0.16, 0.79],
    "green": [0.42, 0.16, 0.79],
    "blue":  [0.52, 0.16, 0.79],
}
BINS = {"bin_A": [0.0, -0.45, 0.75], "bin_B": [0.32, -0.45, 0.75]}
RULE = sys.argv[1] if len(sys.argv) > 1 else "Warm colours go to bin_A, cool colours go to bin_B."
SYS = ("You are a robot SORT planner. Objects: a RED cube, a GREEN cube, a BLUE cube. "
       "Bins: bin_A, bin_B. Apply the sorting rule and assign EACH colour to a bin. "
       "Reply with ONLY a JSON object mapping colour->bin, e.g. {\"red\":\"bin_A\",\"green\":\"bin_B\",\"blue\":\"bin_B\"}. No other text.")


async def plan():
    g = GeminiProvider(api_key=os.environ.get("GEMINI_API_KEY", "vertex-adc"), model="gemini-2.5-flash")
    r = await g.complete([{"role": "user", "content": "Sorting rule: " + RULE}], {"system_override": SYS})
    ans = (r.text or "").strip()
    m = re.search(r"\{.*\}", ans, re.DOTALL)
    return (json.loads(m.group(0)) if m else None), ans


routing, raw = asyncio.run(plan())
print(f"RULE={RULE!r}\nGEMINI_RAW={raw!r}\n-> ROUTING={routing}")
if not routing or set(routing) != set(CUBES) or any(v not in BINS for v in routing.values()):
    print("LLM-SORT: invalid routing — abort"); sys.exit(1)

lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for col, pos in CUBES.items():
    p = f"/World/Cube_{col}"
    lines += [f'create_prim(prim_path="{p}", prim_type="Cube", position={pos}, size=0.05)',
              f'for _api in ("PhysicsRigidBodyAPI","PhysicsCollisionAPI","PhysicsMassAPI"):',
              f'    apply_api_schema(prim_path="{p}", schema_name=_api)',
              f'set_semantic_label(prim_path="{p}", semantic_type="color", class_name="{col}")']
for b, pos in BINS.items():
    lines.append(f'create_bin(prim_path="/World/{b}", position={pos}, size=[0.22, 0.22, 0.15])')
# color_routing from Gemini's plan: colour -> its assigned bin path
cr = ", ".join(f'"{col}": "/World/{routing[col]}"' for col in CUBES)
lines += ['', 'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",',
          '    target_source="curobo",',
          '    source_paths=[' + ", ".join(f'"/World/Cube_{c}"' for c in CUBES) + '],',
          '    destination_path="/World/bin_A",',
          '    color_routing={' + cr + '},',
          '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-LLM-SORT",
       "goal": f"LLM-driven sort: Gemini planned {routing} for rule {RULE!r}; the Franka routes each cube to its LLM-assigned bin.",
       "code": code, "code_template": code,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/bin_A", "position": [0.0, -0.45, 0.75], "size": [0.22, 0.22, 0.15]}},
       "_llm_sort": {"rule": RULE, "routing": routing},
       "verified_status": f"LLM-SORT (cont.319): color_routing from Gemini's plan {routing}. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-LLM-SORT.json", "w"), indent=2)
print(f"WROTE CP-LLM-SORT.json routing={routing}")
