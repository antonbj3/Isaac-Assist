"""Pinpoint WHY a static depalletize cell's controller doesn't step under compose
(plan_calls=0). Builds compose 2x CP-DEPAL-01R via the SAME path scene_eyes uses,
steps physics, then dumps each instance's robot ctrl: attributes (tick/phase/
pick_reject/mode_log) so we see if _on_step fires + where it stalls. cont.319."""
import asyncio, sys, json
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.canonical_instantiator import compose_canonicals
from service.isaac_assist_service.chat.composer import compute_layout_offsets


async def main():
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    tpl = json.load(open(f"{REPO}/workspace/templates/CP-DEPAL-01R.json"))
    tpls = [tpl, tpl]
    offs = [o["offset"] for o in compute_layout_offsets(tpls)]
    compose_arg = [(tpls[i], f"inst{i}", offs[i]) for i in range(2)]
    cb = await asyncio.wait_for(compose_canonicals(compose_arg), timeout=900)
    print("COMPOSE_BUILT instances=%s offsets=%s" % (cb.get("n_instances"), offs))
    step = (
        "import omni.timeline, omni.kit.app, omni.usd\n"
        "from pxr import Usd\n"
        "omni.timeline.get_timeline_interface().play()\n"
        "_app = omni.kit.app.get_app()\n"
        "for _ in range(500): _app.update()\n"
        "st = omni.usd.get_context().get_stage()\n"
        "for root in ('/World/inst0/Franka','/World/inst1/Franka'):\n"
        "    p = st.GetPrimAtPath(root)\n"
        "    if not p or not p.IsValid():\n"
        "        print('PROBE', root, 'PRIM-INVALID'); continue\n"
        "    d = {}\n"
        "    for a in p.GetAttributes():\n"
        "        n = a.GetName()\n"
        "        if n.startswith('ctrl:') or n.startswith('curobo'):\n"
        "            try: d[n] = a.Get()\n"
        "            except Exception: d[n] = '<err>'\n"
        "    print('PROBE', root, d)\n"
        "# also: does the controller's SOURCE cubes exist + where?\n"
        "for cp in ('/World/inst1/Cube_1','/World/inst1/Cube_4'):\n"
        "    pr = st.GetPrimAtPath(cp)\n"
        "    print('PROBE cube', cp, 'valid=' + str(bool(pr and pr.IsValid())))\n"
    )
    r = await kit_tools.exec_sync(step, timeout=180)
    print(r.get("output", "") if isinstance(r, dict) else str(r))


asyncio.run(main())
