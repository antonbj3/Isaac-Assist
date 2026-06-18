#!/usr/bin/env python3
"""STATIC validator for workspace/chain_stages.json -- guards the composition registry's internal consistency.

Per-run gates (chain_xkit_gate, scene_eyes) verify a chain ONCE in Kit; nothing checked that the REGISTRY itself
stays consistent as entries are added (a stale stage ref, a role that can't play its chain position, a handoff
height outside the receiver robot's reach). This formalizes handoff_rule and asserts, with ZERO Kit:
  1. every stage named in a proven_chain exists in `stages`;
  2. POSITION capability: chain[0] can SOURCE, chain[-1] can RECEIVE, every MIDDLE stage can do BOTH;
  3. SURFACE: a source delivers onto flat/raised/grid (never a deep bin a receiver arm can't reach into);
  4. REACH: the source's delivery height lands in the receiver robot's pick band (Franka flat ~0.70-0.88,
     UR10 raised ~0.90-1.00) -- the handoff_rule's robot envelope, made checkable.
Run: python3 scripts/qa/chain_registry_validate.py   (exit 0 = consistent; non-zero = a registry bug).
"""
import json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REG = f"{REPO}/workspace/chain_stages.json"

# receiver pick reach bands per robot (z of the cube to pick), from the proven pairs + handoff_rule
PICK_BAND = {"Franka": (0.70, 0.88), "UR10": (0.90, 1.00)}
DEEP_CONTAINERS = ("bin", "container", "tote", "box")  # a receiver arm can't pick from inside these


def can_source(st):
    return st.get("can_source", st.get("role") in ("source", "both"))


def can_receive(st):
    return st.get("can_receive", st.get("role") in ("receiver", "both"))


def delivers_z(st):
    return st.get("delivers_z", st.get("handoff_z"))


def delivers_surface(st):
    return st.get("delivers_surface", st.get("handoff_surface", ""))


def main():
    reg = json.load(open(REG))
    stages, chains = reg["stages"], reg["proven_chains"]
    errs = []
    for ch in chains:
        names = ch["stages"]
        tag = "->".join(names)
        # 1: existence
        missing = [n for n in names if n not in stages]
        if missing:
            errs.append(f"[{tag}] references unknown stage(s): {missing}")
            continue
        # 2: position capability
        if not can_source(stages[names[0]]):
            errs.append(f"[{tag}] first stage {names[0]} cannot SOURCE (role={stages[names[0]].get('role')})")
        if not can_receive(stages[names[-1]]):
            errs.append(f"[{tag}] last stage {names[-1]} cannot RECEIVE (role={stages[names[-1]].get('role')})")
        for mid in names[1:-1]:
            if not (can_receive(stages[mid]) and can_source(stages[mid])):
                errs.append(f"[{tag}] middle stage {mid} must do BOTH (can_recv={can_receive(stages[mid])} "
                            f"can_src={can_source(stages[mid])}) -- add can_source/delivers_z")
        # 3+4: per adjacent (src, recv) handoff
        for a, b in zip(names, names[1:]):
            sa, sb = stages[a], stages[b]
            surf = delivers_surface(sa).lower()
            if any(c in surf for c in DEEP_CONTAINERS):
                errs.append(f"[{tag}] {a} delivers into a deep '{surf}' -- {b} cannot pick from it")
            dz = delivers_z(sa)
            band = PICK_BAND.get(sb["robot"])
            if dz is None or band is None:
                errs.append(f"[{tag}] {a}->{b}: missing delivery height or unknown receiver robot {sb['robot']}")
            elif not (band[0] <= dz <= band[1]):
                errs.append(f"[{tag}] {a} delivers at z={dz} outside {sb['robot']} pick band {band} (recv {b})")
    n = len(chains)
    if errs:
        print(f"REGISTRY INCONSISTENT ({len(errs)} issue(s)):")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    print(f"{n}/{n} proven_chains internally consistent (stages exist, positions valid, handoff reach OK).")


if __name__ == "__main__":
    main()
