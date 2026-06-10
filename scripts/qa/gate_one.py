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
    import os as _os
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    # faithful-cup verification hooks (mirror scene_eyes): set BEFORE build so the controller picks them up.
    _flags = []
    if _os.environ.get("ASSETGRIPPER") == "1": _flags.append("builtins._sg_use_asset_gripper=True")
    if _os.environ.get("NVCUP") == "1": _flags.append("builtins._sg_nvidia_cup=True")
    if _os.environ.get("CUPFRAME") == "0": _flags.append("builtins._ur10_cupframe_down=False")
    if _os.environ.get("CUPFRAME") == "1": _flags.append("builtins._ur10_cupframe_down=True")
    if _os.environ.get("GRIPZOFF"): _flags.append("builtins._sg_nvidia_grip_z_off=%s" % _os.environ["GRIPZOFF"])
    if _os.environ.get("REPOINT"): _flags.append("builtins._sg_descend_repoint_deg=%s" % _os.environ["REPOINT"])
    if _os.environ.get("FLUSH") == "1": _flags.append("builtins._sg_flush_mount=True")
    if _os.environ.get("FLUSH") == "0": _flags.append("builtins._sg_flush_mount=False")
    if _os.environ.get("HIGHPICK") == "1": _flags.append("builtins._ur10_highpick_approach=True")
    if _os.environ.get("CSPACE") == "1": _flags.append("builtins._ur10_plan_cspace=True")
    if _os.environ.get("DROPPIN") == "1": _flags.append("builtins._ur10_drop_branch_pin=True")
    if _os.environ.get("GRIPLOG") == "1": _flags.append("builtins._sg_grip_log=True")
    if _os.environ.get("PLANBUDGET"): _flags.append("builtins._ur10_plan_budget_s=%s" % _os.environ["PLANBUDGET"])
    if _os.environ.get("IKSEEDS"): _flags.append("builtins._ur10_ik_seeds=%s" % _os.environ["IKSEEDS"])
    if _os.environ.get("TRAJSEEDS"): _flags.append("builtins._ur10_trajopt_seeds=%s" % _os.environ["TRAJSEEDS"])
    if _os.environ.get("JOINTSPACE") == "1": _flags.append("builtins._ur10_jointspace_transit=True")
    if _os.environ.get("JSIGN"): _flags.append("builtins._ur10_jointspace_sign=%s" % _os.environ["JSIGN"])
    if _os.environ.get("POSONLY") == "1": _flags.append("builtins._ur10_transit_posonly=True")
    if _os.environ.get("FARREACH"): _flags.append("builtins._ur10_jointspace_far_reach=%s" % _os.environ["FARREACH"])
    if _os.environ.get("PLEARLY") == "1": _flags.append("builtins._sg_place_early_release=True")
    if _os.environ.get("PLRELXY"): _flags.append("builtins._sg_place_release_xy=%s" % _os.environ["PLRELXY"])
    if _os.environ.get("PLNUDGEMAX"): _flags.append("builtins._sg_place_nudge_max=%s" % _os.environ["PLNUDGEMAX"])
    if _os.environ.get("VMAXFAST"): _flags.append("builtins._sg_loaded_vmax_fast=%s" % _os.environ["VMAXFAST"])
    if _os.environ.get("DROPSEED") == "1": _flags.append("builtins._ur10_drop_seed_chained=True")
    if _os.environ.get("RELIVE") == "1": _flags.append("builtins._ur10_s5_relive=True")
    if _os.environ.get("RELIVEBP") == "1": _flags.append("builtins._ur10_s5_relive_branch_pin=True")
    if _os.environ.get("FREEIK") == "1": _flags.append("builtins._ur10_freeik_probe=True")
    if _os.environ.get("DLSEED") == "1": _flags.append("builtins._ur10_descend_downlock_seed=True")
    if _os.environ.get("DROPTIP"): _flags.append("builtins._sg_drop_tip_release=%s" % _os.environ["DROPTIP"])
    if _os.environ.get("PLBP") == "1": _flags.append("builtins._ur10_place_nudge_branch_pin=True")
    if _os.environ.get("RAWSEED") == "1": _flags.append("builtins._ur10_relive_seed_raw=True")
    if _os.environ.get("FAITHFUL") == "1": _flags.append("builtins._ur10_faithful_default=True")
    if _os.environ.get("FAITHFUL") == "0": _flags.append("builtins._ur10_faithful_default=False")  # explicit side-cup baseline (overrides the flipped source default)
    if _os.environ.get("MCUBEOBS") == "0": _flags.append("builtins._ur10_multicube_obs=False")  # isolate: are the multi-cube collision obstacles blocking the straight-cup approach?
    if _os.environ.get("MCUBEOBS") == "1": _flags.append("builtins._ur10_multicube_obs=True")
    if _os.environ.get("MCUBECARRY") == "1": _flags.append("builtins._ur10_multicube_obs_carry_only=True")  # A1: scope obstacles to carry phase (approach plans obstacle-light)
    if _os.environ.get("MCUBECARRY") == "0": _flags.append("builtins._ur10_multicube_obs_carry_only=False")  # rank-5 test: pedestals as obstacles ALL phases (incl approach) -> does the approach plan around or res_None?
    if _os.environ.get("PICKPIN") == "1": _flags.append("builtins._ur10_pick_descend_pin=True")  # branch-pin the pick CL-nudge descend
    if _os.environ.get("PLACEPIN") == "1": _flags.append("builtins._ur10_place_descend_pin=True")  # branch-pin the place descend (2nd cube)
    if _os.environ.get("PLACEFAILOPEN") == "1": _flags.append("builtins._ur10_place_failopen=True")  # fail-open build-time place -> RELIVE re-plans live
    if _os.environ.get("CSPACEUNWRAP") == "1": _flags.append("builtins._ur10_cspace_unwrap=True")  # wrist-unwrap the cspace branch-pin seed
    if _os.environ.get("PANROTATE") == "1": _flags.append("builtins._ur10_pick_approach_panrotate=True")  # H7-approach: base-rotate to face the pick
    if _os.environ.get("EXCLDELIV") == "1": _flags.append("builtins._ur10_obs_exclude_delivered=True")  # delivered cube not an obstacle for next place
    if _os.environ.get("BUILDBUDGET"): _flags.append("builtins._ur10_build_budget_s=%s" % _os.environ["BUILDBUDGET"])  # rank-2: abort _build_segments plan fan-out after N wall-clock s (anti-hang)
    if _os.environ.get("POSONLYALL") == "1": _flags.append("builtins._ur10_pos_only=True")  # rank-5: WHOLE-PLAN position-only (renamed from POSONLY which L42 uses for _ur10_transit_posonly, to remove the double-assign)
    if _os.environ.get("STRUCTOBS2") == "1": _flags.append("builtins._ur10_struct_obs_v2=True")  # rank-4: add non-target bins as carry-phase obstacles (CP-82 place collision)
    if _os.environ.get("HANGLOC") == "1": _flags.append("builtins._ur10_hangloc=True")  # CP-71 hang localizer: rolling sentinel /tmp/cp71_hangloc.txt -> last label = the blocking cuRobo call
    if _os.environ.get("PICKLOCK") == "1": _flags.append("builtins._ur10_pick_center_lock=True")  # rank-3: xy-gate the grip close (<6mm) + pin the centering nudge; 6s fallback
    if _os.environ.get("EXCLOWN") == "1": _flags.append("builtins._ur10_excl_own_support=True")  # CP-83 probe: exclude the target cube's OWN pedestal from obstacles (neighbour stays)
    if _os.environ.get("NOGRAPH") == "1": _flags.append("builtins._ur10_no_graph=True")  # rank-2b: disable cuRobo graph planner (PRM) -> plan fails fast instead of hanging (CP-71)
    if _os.environ.get("NUDGEPIN") == "0": _flags.append("builtins._ur10_place_nudge_branch_pin=False")  # rank-1 A/B: turn the release-spin fix OFF (master switch's `if not hasattr` then skips it) -> baseline free-IK fling
    if _os.environ.get("NORECIPE") == "1":  # CP-83 regression hunt: strip the 06-09 multi-cube auto-on recipe -> 06-06-like (multicube_obs ALL-PHASES, no pan/pin/etc) which delivered CP-83 3/3
        for _rf in ("_ur10_multicube_obs_carry_only", "_ur10_pick_approach_panrotate", "_ur10_pick_descend_pin",
                    "_ur10_place_descend_pin", "_ur10_descend_downlock_seed", "_ur10_cspace_unwrap",
                    "_ur10_obs_exclude_delivered", "_ur10_place_failopen"):
            _flags.append("builtins.%s=False" % _rf)
    if _flags:
        await kit_tools.exec_sync("import builtins\n" + "\n".join(_flags) + "\n", timeout=10)
        print("FLAGS " + " ".join(_flags))
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=int(_os.environ.get("BUILDTO", 600)))
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
    # Forward the FULL honest-gate surface (P0-18): targets/routing/
    # completeness were silently dropped by the old 3-key whitelist, so a
    # template's completeness="all" never reached the handler and the gate
    # quietly graded legacy any-delivered (caught live on CP-71 2026-06-10).
    for k in ("cube_paths", "color_routing", "target_path",
              "targets", "routing", "completeness"):
        if k in sa and sa[k] is not None:
            args[k] = sa[k]
    res = await asyncio.wait_for(execute_tool_call("simulate_traversal_check", args),
                                 timeout=args["duration_s"] + int(_os.environ.get("SIMTO", 200)))
    out = (res.get("output") or "").strip()
    jl = [l for l in out.splitlines() if l.strip().startswith("{")]
    verdict = "?"
    if jl:
        try: verdict = json.loads(jl[-1])
        except Exception: verdict = jl[-1][:200]
    succ = verdict.get("success") if isinstance(verdict, dict) else "?"
    print(f"{tpl_name}: GATE success={succ} dur={args['duration_s']} cube={args['cube_path']} -> {json.dumps(verdict)[:260] if isinstance(verdict,dict) else verdict}")
    if isinstance(verdict, dict):
        # full verdict on its own line — the 260-char teaser above hid the
        # honest-gate fields (per_cube/completeness) exactly when they mattered
        print("GATE_FULL=" + json.dumps(verdict))


async def main():
    for t in TPLS:
        try:
            await gate(t)
        except Exception as e:
            print(f"{t}: ERROR {type(e).__name__}: {str(e)[:160]}")

asyncio.run(main())
