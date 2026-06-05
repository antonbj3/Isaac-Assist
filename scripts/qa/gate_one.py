#!/usr/bin/env python3
"""Authoritative function-gate check for one template: builds the canonical, settles,
and runs simulate_traversal_check with the template's OWN verify_args/simulate_args
(correct cube_path + target_path + duration_s — the grader's fixed 90s under-measures
slow relays like CP-65 @180s). Prints the gate JSON (success=True => gate PASS).

Usage: gate_one.py <TEMPLATE> [TEMPLATE2 ...]
"""
import asyncio, json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPLS = sys.argv[1:] or ["CP-52"]


async def gate(tpl_name):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical, settle_after_canonical)
    from service.isaac_assist_service.chat.tools.tool_executor import execute_tool_call
    tpl = json.load(open(f"{REPO}/workspace/templates/{tpl_name}.json"))
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        print(f"{tpl_name}: BUILD_FAIL {str(b.get('errors'))[:200]}"); return
    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception:
        pass
    va = tpl.get("verify_args", {}) or {}
    sa = tpl.get("simulate_args", {}) or {}
    args = {"cube_path": va.get("cube_path") or sa.get("cube_path"),
            "target_path": sa.get("target_path"),
            "duration_s": int(sa.get("duration_s", 90))}
    for k in ("cube_paths", "color_routing", "target_path"):
        if k in sa and sa[k] is not None:
            args[k] = sa[k]
    res = await asyncio.wait_for(execute_tool_call("simulate_traversal_check", args),
                                 timeout=args["duration_s"] + 200)
    out = (res.get("output") or "").strip()
    jl = [l for l in out.splitlines() if l.strip().startswith("{")]
    verdict = "?"
    if jl:
        try: verdict = json.loads(jl[-1])
        except Exception: verdict = jl[-1][:200]
    succ = verdict.get("success") if isinstance(verdict, dict) else "?"
    print(f"{tpl_name}: GATE success={succ} dur={args['duration_s']} cube={args['cube_path']} -> {json.dumps(verdict)[:260] if isinstance(verdict,dict) else verdict}")


async def main():
    for t in TPLS:
        try:
            await gate(t)
        except Exception as e:
            print(f"{t}: ERROR {type(e).__name__}: {str(e)[:160]}")

asyncio.run(main())
