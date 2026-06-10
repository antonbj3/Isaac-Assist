#!/usr/bin/env python
"""reach_validate.py — UR10 CUP-DOWN REACHABILITY validator (Anton-requested constraint).

WHY: the LLM that authors canonical layouts can place pick/place targets the UR10 physically
CANNOT reach with a top-down suction approach — too far (+y), too low/high, inside an enclosure
(collision), or on a moving feed. This tool turns the live cuRobo reach probe into a layout
CONSTRAINT: build the scene, probe each declared pick target with the CUP pointing down at the real
grasp height (REPOINT=-90 + _reach_probe_z_off=0.193 — because ee+Z-down != cup-down due to ee_joint
rpy=π,-π/2, and the cup-down cup sits ~0.193 below ee), and return a per-target REACHABLE/UNREACHABLE
verdict the generation pipeline can gate on.

IMPORTANT CAVEAT (verified 2026-06-07): REACHABLE here means "the grasp POSE has an IK solution from
the home seed" — it does NOT guarantee the function gate PASSES. The controller plans a multi-segment
descend, which can still res_None for MARGINAL/path-limited poses even when a single-IK probe succeeds.
Measured: CP-81 probed REACHABLE (full) yet the gate FAILED; CP-83 likewise marginal. So treat REACHABLE
as "necessary, not sufficient" — borderline picks must be GATE-verified (gate_one.py). The probe is also
STOCHASTIC (cuRobo Halton seeds) -> single runs flip; use N-of-M for a reliable verdict. The 8/13
faithful gate PASS set (CP-69/70/75/79/80/84/85/86) all probe REACHABLE; the 5 fails are far/marginal.

WHY LIVE (not an analytic envelope): straight-down reachability is non-convex AND conflates
kinematics with scene collision (measured: at base-relative radius the reach floor is non-monotonic
in y; [-0.50,0.40] reaches z<=0.80 but [-0.50,0.25]+Pedestal only reaches 1.10). A radial formula
mispredicts; only a probe against the real scene is correct.

USAGE:
    # Kit must be running (launch_isaac_sim_with_assist.sh --headless) on 127.0.0.1:8001.
    conda run --no-capture-output -n isaac_lab_env python scripts/qa/reach_validate.py CP-70 [CP-83 ...]
    # JSON report on stdout (one object per template) + a human summary on stderr.

NUANCE (encoded as a WARNING, not yet auto-resolved): for DYNAMIC feeds (carousel/conveyor) the item
sits at its t=0 spawn, NOT the fixed pick STATION — probing the spawn is the wrong question. The tool
flags templates whose code/roles mention a carousel/conveyor so the caller knows the verdict needs a
station-position check instead.
"""
import asyncio, json, os, sys

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

REACH_LOG = "/tmp/reachprobe.log"
IK_SEEDS = os.environ.get("IKSEEDS", "48")
PLAY_UPDATES = int(os.environ.get("PLAY_UPDATES", "60"))   # app.update() calls to drive >=1 physics tick (probe fires on tick 1)

# minimal play burst: start the timeline + pump the app so the controller's physics _on_step runs.
# The tick-1 reach probe fires on the first step and BLOCKS that step for ~10-15s (N plan_pose calls),
# so the exec timeout is generous.
_PLAY = (
    "import omni.timeline, omni.kit.app\n"
    "_app = omni.kit.app.get_app(); _tl = omni.timeline.get_timeline_interface()\n"
    "for _ in range(3): _app.update()\n"
    "try: _tl.play()\n"
    "except Exception: pass\n"
    "for _ in range(%d): _app.update()\n"
    "print('PLAY_DONE')\n"
) % PLAY_UPDATES


def _dynamic_feed(tpl):
    blob = (json.dumps(tpl.get("roles") or {}) + (tpl.get("code") or "") +
            (tpl.get("code_template") or "") + json.dumps(tpl.get("diagnose_args") or {})).lower()
    for kw in ("carousel", "conveyor", "turntable", "rotary", "belt", "indexer"):
        if kw in blob:
            return kw
    return None


async def _validate_one(kit_tools, etc, sac, name):
    tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
    sa = tpl.get("simulate_args") or {}
    declared = list(sa.get("cube_paths") or ([sa["cube_path"]] if sa.get("cube_path") else []))
    dest = sa.get("target_path")
    feed = _dynamic_feed(tpl)

    # truncate the shared probe log FIRST (before build/settle), so the probe output — which may fire during
    # settle_after_canonical's physics steps OR during the play burst — is retained. Kit is single-tenant.
    try:
        open(REACH_LOG, "w").close()
    except Exception:
        pass

    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    # 2026-06-07: test CUP-DOWN reachability (the FAITHFUL grasp orientation), NOT ee-down. The cup grips along the
    # gripper out-axis, and ee+Z-down != cup-down (ee_joint rpy=π,-π/2), so the descend repoint -90 is what points the
    # CUP down. And the cup-down cup sits ~0.193 BELOW ee, so probe ee at cube_top+0.193 (ZOFF) = the real grasp pose.
    # This makes the validator correctly predict faithful-graspability (the 8/13 PASS set); ee-down over-counts.
    # _reach_probe_extra_paths makes the probe ALSO cover the destination (place reach), not just picks.
    _extra = json.dumps([dest] if dest else [])
    await kit_tools.exec_sync(
        "import builtins\n"
        "builtins._sg_use_asset_gripper=True\n"
        "builtins._sg_nvidia_cup=True\n"
        "builtins._ur10_cupframe_down=False\n"
        "builtins._sg_descend_repoint_deg=-90.0\n"
        "builtins._reach_probe_z_off=0.193\n"
        "builtins._reach_probe=True\n"
        "builtins._reach_probe_done=False\n"
        "builtins._reach_probe_extra_paths=%s\n"
        "builtins._ur10_ik_seeds=%s\n" % (_extra, IK_SEEDS), timeout=10)

    b = await asyncio.wait_for(etc(tpl), timeout=600)
    if not b.get("instantiated"):
        return {"template": name, "status": "BUILD_FAIL", "errors": str(b.get("errors"))[:300]}
    try:
        await asyncio.wait_for(sac(tpl), timeout=30)
    except Exception:
        pass

    # play burst -> drives physics so the controller's _on_step (and the tick-1 probe) runs, in case settle didn't.
    try:
        await asyncio.wait_for(kit_tools.exec_sync(_PLAY, timeout=180), timeout=190)
    except Exception as e:
        # the probe can outlast a short play; we still read whatever it wrote
        print("PLAY_TIMEOUT %s %r" % (name, e), file=sys.stderr)

    targets = []
    try:
        for ln in open(REACH_LOG):
            ln = ln.strip()
            if not ln.startswith("REACH_TGT"):
                continue
            # REACH_TGT path=P xy=[x,y] top=Z top@Z=n/3 -> VERDICT
            d = {"raw": ln}
            for tok in ln.split():
                if tok.startswith("path="): d["path"] = tok[5:]
                elif tok.startswith("xy="): d["xy"] = tok[3:]
                elif tok.startswith("top=") and "@" not in tok: d["top"] = float(tok[4:])
                elif "/3" in tok and "@" in tok: d["n_ok"] = int(tok.split("=")[-1].split("/")[0])
            d["verdict"] = ln.split("->")[-1].strip() if "->" in ln else "?"
            targets.append(d)
    except Exception as e:
        print("PARSE_ERR %s %r" % (name, e), file=sys.stderr)

    # split the destination target out of the picks
    dest_tgt = next((t for t in targets if dest and t.get("path") == dest), None)
    pick_tgts = [t for t in targets if t is not dest_tgt]
    probed = {t.get("path") for t in pick_tgts}
    n_reach = sum(1 for t in pick_tgts if t["verdict"] == "REACHABLE")
    missing = [p for p in declared if p not in probed and (p + "/Cube") not in probed]
    dest_reachable = (dest_tgt["verdict"] == "REACHABLE") if dest_tgt else None
    # VERDICT is PICK-based (the robust signal): reach-OK iff EVERY probed pick is reachable + none missing.
    # `feed` and `destination_reachable` are WARNINGS, not gates -- a dynamic feed delivers the item TO a fixed
    # pick station (the t=0 spawn probe can be conservative), and a drop happens ABOVE a container (so probing the
    # destination's top column straight-down is a noisy proxy). They inform the caller without failing real passers.
    warnings = []
    if not pick_tgts:
        layout = "NO_PICK_TARGETS_PROBED"
    elif n_reach == len(pick_tgts) and not missing:
        layout = "REACHABLE"
    else:
        layout = "UNREACHABLE"
    if feed:
        warnings.append("dynamic_feed:%s — picks probed at t=0 spawn; verify the fixed pick STATION position" % feed)
    if dest_reachable is False:
        warnings.append("destination top-column not reachable straight-down (noisy: drops happen ABOVE a container)")
    if missing:
        warnings.append("declared picks not probed: %s" % missing)
    return {
        "template": name,
        "status": "OK",
        "layout_verdict": layout,
        "warnings": warnings,
        "dynamic_feed": feed,
        "n_picks_probed": len(pick_tgts),
        "n_reachable": n_reach,
        "declared_picks": declared,
        "destination": dest,
        "destination_reachable": dest_reachable,
        "destination_target": dest_tgt,
        "missing_unprobed_picks": missing,
        "targets": pick_tgts,
    }


async def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not names:
        print("usage: reach_validate.py <TEMPLATE> [TEMPLATE ...]", file=sys.stderr)
        return
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical as etc, settle_after_canonical as sac)
    reports = []
    for nm in names:
        try:
            rep = await _validate_one(kit_tools, etc, sac, nm)
        except Exception as e:
            rep = {"template": nm, "status": "ERROR", "error": repr(e)[:300]}
        reports.append(rep)
        # human summary -> stderr (stdout stays clean JSON)
        v = rep.get("layout_verdict", rep.get("status"))
        print("[reach_validate] %-44s %-22s (%s/%s picks reachable)%s" % (
            nm, v, rep.get("n_reachable", "?"), rep.get("n_picks_probed", "?"),
            ("  WARN: " + " | ".join(rep["warnings"])) if rep.get("warnings") else ""), file=sys.stderr)
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
