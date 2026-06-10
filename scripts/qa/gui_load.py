#!/usr/bin/env python3
"""Load a template into the (GUI) Kit and PLAY it, for human visual inspection.
Builds the canonical, settles, presses play. Leaves the scene running.
Usage: gui_load.py <TEMPLATE>
"""
import asyncio, json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPL = sys.argv[1] if len(sys.argv) > 1 else "CP-84"


async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical, settle_after_canonical)
    tpl = json.load(open(f"{REPO}/workspace/templates/{TPL}.json"))
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        print(f"{TPL}: BUILD_FAIL {str(b.get('errors'))[:300]}"); return
    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception:
        pass
    # frame the cell + press play so the human sees the motion immediately
    await kit_tools.exec_sync(
        "import omni.timeline\n"
        "tl = omni.timeline.get_timeline_interface()\n"
        "tl.set_looping(False)\n"
        "tl.play()\n", timeout=15)
    print(f"{TPL}: LOADED + PLAYING (inspect in the Isaac Sim window)")

asyncio.run(main())
