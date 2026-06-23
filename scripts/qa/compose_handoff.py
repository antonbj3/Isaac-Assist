#!/usr/bin/env python3
"""compose_handoff.py — #29 handoff-compatibility checker for SEQUENTIAL robot-diversity chains (Kit-free).

Predicts whether a (source, receiver) pair can CHAIN. Grounded in the proven pairs (workspace/chain_stages
.json) + the cont.262 failure (CP-73 delivers into a deep Bin -> CP-13 Franka can't pick from inside it).

A pair chains iff:
  (1) the source delivers its object onto a PICKABLE SURFACE (flat/raised) — NOT into a deep bin/container
      (a receiver arm can't grasp top-down from inside a deep container), AND
  (2) the source's delivery HEIGHT matches the receiver ROBOT's pick envelope:
      UR10 picks RAISED (~0.975 pedestal), Franka picks FLAT (~0.775 table). (memory cont.229 handoff-height.)

This pre-filters incompatible chains BEFORE an expensive cross-Kit run, so the orchestrator/LLM only routes
chainable pairs into chain_xkit_gate. Use: compose_handoff.py SRC RECV  | or import chain_compat(src,recv).
"""
import json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
_STAGES = json.load(open(f"{REPO}/workspace/chain_stages.json"))["stages"]
_PICK_Z = {"UR10": 0.975, "Franka": 0.775}                 # a robot's DESIGN/native top-down pick z (source-height guess)
# cont.319-L3 reach-RANGE: the cross-Kit relay (chain_xkit_gate run_stage_k) re-instantiates the handoff object at
# the SOURCE delivery world-z with z-offset=0.0 — so the RECEIVER picks at the source's delivery height, which only
# needs to fall inside the receiver's top-down REACH RANGE (NOT equal a single native pick z). The old single-z+-0.08
# match FALSE-NEGATIVED proven pairs (CP-CONV-02-SRC@0.825 -> UR10 native@0.975: 0.825 IS in UR10 reach -> works).
# Bounds contain every proven handoff height (Franka receives {0.775,0.825}; UR10 receives {0.825,0.975}) + ballpark
# arm kinematics; they catch only GROSS unreachability (floor/ceiling), not unphysical cm-level discrimination.
_REACH = {"UR10": (0.40, 1.35), "Franka": (0.30, 1.05)}    # (lo, hi) top-down pickable z range per receiver robot
_DEEP_CONTAINER = ("bin", "container", "crate", "hopper", "box")  # NOT pickable from inside by a receiver arm


def _robot_of(tpl):
    blob = (json.dumps(tpl.get("roles") or {}) + " " + (tpl.get("goal") or "")).lower()
    return "UR10" if "ur10" in blob else "Franka"


def chain_compat(src_name, recv_name, measured_z=None):
    """-> {compatible, height_verified, needs_measure, reason}. Source delivers; receiver picks the handoff.

    measured_z (cont.319-L3): pass the REAL delivery-surface z from measure_fixture(target_path) in Kit to CLOSE
    the loop — a non-catalog source's height becomes VERIFIED instead of a source-robot guess. Flow: pre-filter
    flags needs_measure -> caller runs measure_fixture(needs_measure) in Kit -> re-calls with measured_z=that.
    """
    src = json.load(open(f"{REPO}/workspace/templates/{src_name}.json"))
    recv = json.load(open(f"{REPO}/workspace/templates/{recv_name}.json"))
    s_stage = _STAGES.get(src_name)
    if s_stage:                                            # known chain-ready source
        # a MID-stage source delivers at its OUTPUT height (delivers_z, e.g. a re-palletized grid), which can
        # differ from its INPUT handoff_z; fall back to handoff_z for a pure source.
        # cont.319cc audit #12: do NOT hardcode kind='surface' for a catalog source -- a chain-ready source can
        # deliver into a deep container; read delivers_surface from the registry (default True for back-compat).
        deliver_z = s_stage.get("delivers_z", s_stage.get("handoff_z")); leaf = "(catalog)"
        kind = "surface" if s_stage.get("delivers_surface", True) else "deep_container"
        height_inferred = False; measure_target = None      # catalog z is VERIFIED (declared from a measured chain run)
    else:                                                  # infer from the template's delivery target
        # cont.319-L3: a NON-catalog source's delivery HEIGHT is not statically known Kit-free — it depends on the
        # target prim's world-z (needs USD). Previously deliver_z=None => the height-check (below) was SILENTLY
        # bypassed => a height-incompatible arbitrary pair (e.g. UR10 source @0.975 -> Franka flat receiver) FALSE-
        # PASSED the pre-filter. Honor "never silently assume": infer a BEST-EFFORT height from the SOURCE robot's
        # working envelope so gross mismatches are still caught, but FLAG it unverified + surface the target_path
        # that measure_fixture must resolve in Kit for a trusted verdict (measured-vs-modelled provenance).
        tgt = (src.get("simulate_args") or {}).get("target_path") or ""
        leaf = tgt.rsplit("/", 1)[-1].lower()
        kind = "deep_container" if any(k in leaf for k in _DEEP_CONTAINER) else "surface"
        if measured_z is not None:                          # Kit-measured surface z -> VERIFIED, no longer a guess
            deliver_z = float(measured_z); height_inferred = False; measure_target = None
        else:
            deliver_z = _PICK_Z.get(_robot_of(src), 0.775)  # best-effort: source delivers at its own working height
            height_inferred = True; measure_target = tgt or None
    if kind == "deep_container":
        return {"compatible": False,
                "reason": f"source {src_name} delivers into a DEEP CONTAINER ('{leaf}') — a receiver arm cannot pick from inside it"}
    recv_robot = (_STAGES.get(recv_name) or {}).get("robot") or _robot_of(recv)
    lo, hi = _REACH.get(recv_robot, _REACH["Franka"])
    if deliver_z is not None and not (lo <= deliver_z <= hi):
        _inf = " (INFERRED from source robot — verify in Kit)" if height_inferred else ""
        return {"compatible": False, "height_verified": not height_inferred, "needs_measure": measure_target,
                "reason": f"handoff height z={deliver_z}{_inf} is OUTSIDE {recv_robot} receiver reach [{lo},{hi}] — the cross-Kit relay re-instantiates the object at the SOURCE delivery z (z-offset=0), so the receiver must REACH that height"}
    # cont.319-CHAIN2: reach-range is necessary but NOT sufficient. ADAPTIVE arm receivers (a generic cuRobo
    # pick — flat-receive, UR10-NATIVE) plan to the cube's LIVE pose, so any in-reach delivery works. But a
    # FIXED-height receiver (a palletize/stack ROUTINE that picks at a SET surface z) needs the relayed cube
    # to LAND ON that surface: if the source delivers far above it, the cube has no support and FALLS, and the
    # routine misses it. MEASURED: RAISED-SRC@0.975 -> PALLETIZE-RECV@0.825 (Δ0.15) chained 0/1 (cube fell to
    # 0.775); FRANKA-SRC@0.775 -> same (Δ0.05) chained 1/1. So require |deliver_z - receiver handoff_z| <= 0.10
    # for fixed-height receivers only.
    _rs = _STAGES.get(recv_name) or {}
    _recv_hz = _rs.get("handoff_z")
    # cont.319-CHAIN10: which receivers are HEIGHT-SENSITIVE (need source-z ~= their pick-surface)? MEASURED Δz
    # tolerance: FRANKA receivers fail at Δ0.15 (chain2 palletize, chain10 flat-receive — the relayed cube falls
    # from the raised delivery and the routine misses it) but work at Δ0.05; the UR10 receiver tolerated Δ0.20
    # (chain8 — big arm, picks the cube where it lands). So the line is ROBOT-based: Franka receivers are fixed-
    # height, UR10 is adaptive. (was palletize/stack-only -> too narrow, false-passed RAISED->flat-receive.)
    _fixed_pick = (not _rs.get("adaptive")) and recv_robot != "UR10"
    if _fixed_pick and deliver_z is not None and _recv_hz is not None and abs(deliver_z - _recv_hz) > 0.10:
        return {"compatible": False, "height_verified": not height_inferred, "needs_measure": measure_target,
                "reason": f"FIXED-height receiver {recv_name} picks at a SET surface z~{_recv_hz}; source delivers z={deliver_z} (Δ={round(abs(deliver_z-_recv_hz),3)}>0.10) — the relayed cube lands with no support at the pick surface and FALLS (verified RAISED-SRC->PALLETIZE = 0/1). Adaptive arm receivers tolerate this; fixed routines do not"}
    # CAPACITY overflow (cont.318n): a FIXED-capacity receiver (e.g. a 3-slot stacker) cannot absorb a source
    # that delivers MORE parts than it has slots — the extra parts have no target and fall. VERIFIED: CP-08(4)
    # -> CP-CHAIN-STACK-RECV(cap 3) executes at 3/4 (3 not even stacked + 1 fell). Fail-closed pre-filter so the
    # orchestrator HALTs an overflow pairing instead of running a doomed chain.
    recv_cap = (_STAGES.get(recv_name) or {}).get("capacity")
    src_n = (_STAGES.get(src_name) or {}).get("n_cube")
    # cont.319cc audit #12: src_n may be a STRING ('4' or a '1..N' range). Parse a concrete int so a string count
    # is NOT silently bypassed (the isinstance(int) check skipped it); a variable range stays None = unparseable
    # (a best-effort pre-filter cannot statically check a runtime-variable count).
    if isinstance(src_n, str):
        import re as _re12
        _m12 = _re12.fullmatch(r"\s*(\d+)\s*", src_n)
        src_n = int(_m12.group(1)) if _m12 else None
    if isinstance(recv_cap, int) and isinstance(src_n, int) and src_n > recv_cap:
        return {"compatible": False,
                "reason": f"CAPACITY overflow: source {src_name} delivers {src_n} parts but receiver {recv_name} holds only {recv_cap} (extra parts have no slot and fall — verified CP-08->STACK-RECV = 3/4)"}
    if height_inferred:                                    # surface passed the GROSS check, but z is a robot-guess
        return {"compatible": True, "height_verified": False, "needs_measure": measure_target,
                "reason": f"source delivers onto a pickable surface; height z~{deliver_z} is INFERRED from the source "
                          f"robot (within {recv_robot} reach [{lo},{hi}]) — measure_fixture('{measure_target}') in Kit to VERIFY before trusting the chain"}
    return {"compatible": True, "height_verified": True, "needs_measure": None,
            "reason": f"source delivers onto a pickable surface (z~{deliver_z}) within {recv_robot} reach [{lo},{hi}]"}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: compose_handoff.py SRC RECV", file=sys.stderr); sys.exit(2)
    r = chain_compat(sys.argv[1], sys.argv[2])
    print(("COMPAT" if r["compatible"] else "INCOMPAT") + ": " + r["reason"])
    sys.exit(0 if r["compatible"] else 1)
