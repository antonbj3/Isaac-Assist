"""LLM-pick (#50, cont.319): does Gemini correctly SELECT which object a robot
should pick, given a scene description + a natural-language task? This is the
novel core of LLM-driven manipulation (the pick-execution is standard). Uses
the Vertex Gemini path (GEMINI_PROVIDER_VERTEX). Run: python scripts/qa/llm_pick_eval.py"""
import asyncio, os, sys
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

SCENE = (
    "Scene objects (Isaac Sim prims a Franka robot can pick):\n"
    "- /World/Cube_red   : a RED cube,   position [0.40, 0.15, 0.80]\n"
    "- /World/Cube_green : a GREEN cube, position [0.40, 0.00, 0.80]\n"
    "- /World/Cube_blue  : a BLUE cube,  position [0.40, -0.15, 0.80]"
)
SYS = ("You are a robot pick-selector. Given a scene and a task, choose the ONE object to pick. "
       "Reply with ONLY its prim path (e.g. /World/Cube_red) and nothing else.")
TASKS = [
    ("Pick the red cube.", "/World/Cube_red"),
    ("Pick the cube in the middle (between the others).", "/World/Cube_green"),
    ("Grab the blue one.", "/World/Cube_blue"),
    ("I need the cube with the largest Y coordinate.", "/World/Cube_red"),
    ("Pick the object that is the colour of the sky.", "/World/Cube_blue"),
]


async def main():
    p = GeminiProvider(api_key=os.environ.get("GEMINI_API_KEY", "vertex-adc"), model="gemini-2.5-flash")
    correct = 0
    for instr, expect in TASKS:
        prompt = SCENE + "\n\nTask: " + instr
        try:
            r = await p.complete([{"role": "user", "content": prompt}], {"system_override": SYS})
            ans = (r.text or "").strip()
        except Exception as e:
            ans = "EXC:" + str(e)[:120]
        ok = expect in ans
        correct += ok
        print(f"  task={instr!r}\n    -> gemini={ans!r}  expect={expect}  {'OK' if ok else 'WRONG'}")
    print(f"LLM-SELECT: {correct}/{len(TASKS)} correct")


asyncio.run(main())
