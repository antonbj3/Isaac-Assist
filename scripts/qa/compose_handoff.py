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
_PICK_Z = {"UR10": 0.975, "Franka": 0.775}                 # the z a robot can grasp from, top-down
_DEEP_CONTAINER = ("bin", "container", "crate", "hopper", "box")  # NOT pickable from inside by a receiver arm


def _robot_of(tpl):
    blob = (json.dumps(tpl.get("roles") or {}) + " " + (tpl.get("goal") or "")).lower()
    return "UR10" if "ur10" in blob else "Franka"


def chain_compat(src_name, recv_name):
    """-> {compatible: bool, reason: str}. Source delivers; receiver picks the handoff."""
    src = json.load(open(f"{REPO}/workspace/templates/{src_name}.json"))
    recv = json.load(open(f"{REPO}/workspace/templates/{recv_name}.json"))
    s_stage = _STAGES.get(src_name)
    if s_stage:                                            # known chain-ready source
        # a MID-stage source delivers at its OUTPUT height (delivers_z, e.g. a re-palletized grid), which can
        # differ from its INPUT handoff_z; fall back to handoff_z for a pure source.
        deliver_z = s_stage.get("delivers_z", s_stage.get("handoff_z")); kind = "surface"; leaf = "(catalog)"
    else:                                                  # infer from the template's delivery target
        tgt = (src.get("simulate_args") or {}).get("target_path") or ""
        leaf = tgt.rsplit("/", 1)[-1].lower()
        kind = "deep_container" if any(k in leaf for k in _DEEP_CONTAINER) else "surface"
        deliver_z = None
    if kind == "deep_container":
        return {"compatible": False,
                "reason": f"source {src_name} delivers into a DEEP CONTAINER ('{leaf}') — a receiver arm cannot pick from inside it"}
    recv_robot = (_STAGES.get(recv_name) or {}).get("robot") or _robot_of(recv)
    pick_z = _PICK_Z.get(recv_robot, 0.775)
    if deliver_z is not None and abs(deliver_z - pick_z) > 0.08:
        return {"compatible": False,
                "reason": f"handoff HEIGHT mismatch: source delivers at z={deliver_z}, but {recv_robot} receiver picks at z~{pick_z} (UR10 raised / Franka flat)"}
    return {"compatible": True,
            "reason": f"source delivers onto a pickable surface (z~{deliver_z}) matching {recv_robot} pick z~{pick_z}"}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: compose_handoff.py SRC RECV", file=sys.stderr); sys.exit(2)
    r = chain_compat(sys.argv[1], sys.argv[2])
    print(("COMPAT" if r["compatible"] else "INCOMPAT") + ": " + r["reason"])
    sys.exit(0 if r["compatible"] else 1)
