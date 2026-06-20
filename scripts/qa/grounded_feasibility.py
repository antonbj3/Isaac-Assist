#!/usr/bin/env python3
"""grounded_feasibility.py (cont.319ddd) — GROUNDED gripper<->object feasibility reasoning.

The big-vision gap (Anton): a special-order like "use a robot whose gripper can ACTUALLY hold a slippery wet steel
cylinder" must be reasoned about with a GROUNDED check, not guessed by the LLM or merely deferred to the user.
The production agent has grasp tools (grasp_object, define_grasp_pose, get_gripper_state) but NO gripper<->object
COMPATIBILITY check (verified: no such tool in tools/). This builds that grounded reasoning: given a gripper type
and an object's physical attributes, decide feasibility from first-principles rules + suggest a working gripper.

Wire-in target: a tool `check_gripper_object_feasibility` the ChatOrchestrator can call BEFORE picking a cell — so
the agent GROUNDS the gripper choice instead of asserting it. Pure + deterministic (no LLM, no Kit, no ChromaDB).
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Obj:
    material: str = "unknown"      # steel|iron|aluminum|plastic|glass|rubber|cardboard|foam|cloth|wood|ceramic
    shape: str = "box"             # box|cylinder|sphere|irregular|flat-sheet|bag
    surface: str = "smooth-dry"    # smooth-dry|smooth-wet|oily|rough|porous|textured
    mass_kg: float = 0.5
    width_m: float = 0.06          # the across-grip dimension
    fragile: bool = False


FERROUS = {"steel", "iron", "carbon-steel", "stainless-steel"}
POROUS = {"porous", "cloth"}
POROUS_MAT = {"cardboard", "foam", "cloth", "wood"}
SEAL_BREAKING = {"smooth-wet", "oily", "rough", "porous", "textured"}

# rough per-gripper limits (representative of common industrial end-effectors)
SUCTION_MAX_KG = 3.0
JAW_MIN_M, JAW_MAX_M = 0.01, 0.12


def check_gripper_object_feasibility(gripper_type: str, obj: Obj) -> dict:
    """Returns {feasible, reason, confidence, suggested_gripper}. Grounded first-principles rules."""
    g = (gripper_type or "").lower().replace("-", "_")
    o = obj
    porous = o.surface in POROUS or o.material in POROUS_MAT

    def ok(reason, conf=0.9):
        return {"feasible": True, "reason": reason, "confidence": conf, "suggested_gripper": gripper_type}

    def no(reason, suggest, conf=0.9):
        return {"feasible": False, "reason": reason, "confidence": conf, "suggested_gripper": suggest}

    def _suggest_for(o):
        # pick a gripper that WOULD work for this object
        if o.material in FERROUS and not o.fragile:
            return "magnetic"
        if JAW_MIN_M <= o.width_m <= JAW_MAX_M:
            return "parallel_jaw" + ("(force-limited)" if o.fragile else "")
        if o.surface in ("smooth-dry",) and not porous and o.mass_kg <= SUCTION_MAX_KG:
            return "vacuum_suction"
        return "soft_compliant"

    if g in ("vacuum_suction", "suction", "suction_cup", "surface_gripper"):
        if porous:
            return no(f"suction cannot seal on a {o.material}/{o.surface} (porous) surface", _suggest_for(o))
        if o.surface in SEAL_BREAKING:
            return no(f"suction seal breaks on a {o.surface} surface (e.g. a wet/oily {o.shape})", _suggest_for(o))
        if o.mass_kg > SUCTION_MAX_KG:
            return no(f"{o.mass_kg}kg exceeds the ~{SUCTION_MAX_KG}kg suction payload", _suggest_for(o))
        return ok(f"smooth-dry non-porous {o.shape}, {o.mass_kg}kg within suction payload")

    if g in ("parallel_jaw", "jaw", "gripper", "two_finger", "franka_hand"):
        if not (JAW_MIN_M <= o.width_m <= JAW_MAX_M):
            return no(f"width {o.width_m}m outside jaw range [{JAW_MIN_M},{JAW_MAX_M}]m", _suggest_for(o))
        if o.fragile:
            return ok(f"graspable width but FRAGILE -> requires force/impedance control", conf=0.6)
        if o.surface in ("oily",):
            return ok(f"graspable but {o.surface} -> may slip; recommend textured fingertips", conf=0.6)
        return ok(f"width {o.width_m}m within jaw range, sufficient friction")

    if g in ("magnetic", "electromagnet", "magnet"):
        if o.material not in FERROUS:
            return no(f"magnetic grip needs a FERROUS object; {o.material} is non-ferrous", _suggest_for(o))
        if o.fragile:
            return ok("ferrous but fragile -> control hold force", conf=0.6)
        return ok(f"{o.material} is ferrous -> magnetic grip holds")

    if g in ("soft_compliant", "soft", "compliant", "fin_ray"):
        if o.mass_kg > 2.0:
            return no(f"{o.mass_kg}kg likely exceeds a soft gripper's secure payload", _suggest_for(o))
        return ok("soft/compliant suits irregular or delicate objects", conf=0.8)

    return {"feasible": None, "reason": f"unknown gripper type '{gripper_type}'", "confidence": 0.0,
            "suggested_gripper": _suggest_for(o)}


# ── REACH feasibility (the "stack 1.5m tall" / far-target trap) ──────────────
# Max reach RADIUS from the robot base (representative datasheet values, metres).
ROBOT_REACH = {"franka": 0.855, "panda": 0.855, "ur3": 0.5, "ur5": 0.85, "ur10": 1.30,
               "ur10e": 1.30, "kuka_iiwa": 0.8, "g1": 0.7}
DEFAULT_BASE_Z = 0.75   # robots in these cells sit on a ~0.75m pedestal/table


def check_reach_feasibility(robot: str, target_xyz, base_xyz=(0.0, 0.0, DEFAULT_BASE_Z)) -> dict:
    """Grounded reach pre-check (before the heavier solve_ik): is the target within the robot's reach sphere?
    Catches 'stack a 1.5m column' / 'far target' specs the LLM would otherwise assert as buildable."""
    r = (robot or "").lower().replace("-", "_")
    reach = ROBOT_REACH.get(r)
    if reach is None:
        return {"feasible": None, "reason": f"unknown robot reach for '{robot}'", "confidence": 0.0}
    dx = target_xyz[0] - base_xyz[0]
    dy = target_xyz[1] - base_xyz[1]
    dz = target_xyz[2] - base_xyz[2]
    dist = (dx * dx + dy * dy + dz * dz) ** 0.5
    if dist > reach:
        return {"feasible": False, "confidence": 0.9,
                "reason": f"target {tuple(round(c,2) for c in target_xyz)} is {dist:.2f}m from base, "
                          f"exceeds {robot}'s {reach}m reach (need a taller/longer robot, a lift axis, or a closer target)"}
    if dist > 0.9 * reach:
        return {"feasible": True, "confidence": 0.6,
                "reason": f"{dist:.2f}m is near {robot}'s {reach}m limit -> marginal IK / singularity risk"}
    return {"feasible": True, "confidence": 0.9, "reason": f"{dist:.2f}m within {robot}'s {reach}m reach"}


def _selftest():
    cases = [
        # (gripper, obj, expected_feasible, label)
        ("vacuum_suction", Obj("stainless-steel", "cylinder", "smooth-wet", 2.0, 0.08), False, "slippery wet steel cylinder + suction (THE trap)"),
        ("vacuum_suction", Obj("plastic", "box", "smooth-dry", 0.3, 0.06), True, "dry plastic box + suction"),
        ("vacuum_suction", Obj("cardboard", "box", "porous", 0.5, 0.10), False, "cardboard (porous) + suction"),
        ("vacuum_suction", Obj("steel", "box", "smooth-dry", 5.0, 0.08), False, "5kg + suction (over payload)"),
        ("magnetic", Obj("steel", "box", "smooth-dry", 4.0, 0.08), True, "heavy steel + magnetic"),
        ("magnetic", Obj("aluminum", "box", "smooth-dry", 1.0, 0.06), False, "aluminum (non-ferrous) + magnetic"),
        ("magnetic", Obj("glass", "cylinder", "smooth-dry", 0.5, 0.05), False, "glass + magnetic"),
        ("parallel_jaw", Obj("plastic", "box", "smooth-dry", 0.3, 0.05), True, "graspable plastic box + jaw"),
        ("parallel_jaw", Obj("steel", "box", "smooth-dry", 1.0, 0.30), False, "too-wide (0.30m) + jaw"),
        ("parallel_jaw", Obj("glass", "cylinder", "smooth-dry", 0.2, 0.04, fragile=True), True, "fragile glass + jaw (force-limited)"),
        ("soft_compliant", Obj("rubber", "irregular", "textured", 0.4, 0.07), True, "irregular rubber + soft gripper"),
    ]
    npass = 0
    print("=== GROUNDED gripper<->object feasibility — trap battery ===")
    for g, o, exp, label in cases:
        r = check_gripper_object_feasibility(g, o)
        hit = (r["feasible"] == exp)
        npass += hit
        sug = "" if r["feasible"] else f" -> suggest {r['suggested_gripper']}"
        print(f"  [{'OK' if hit else 'XX'}] {g:14} {label:46} feasible={r['feasible']!s:5}{sug}")
        if not hit:
            print(f"        reason: {r['reason']}")
    print(f"\n{npass}/{len(cases)} grip verdicts correct.")
    # REACH battery — (robot, target_xyz, expected_feasible, label)
    reach_cases = [
        ("franka", (0.5, -0.3, 2.25), False, "stack 1.5m-tall column (target z=2.25) + Franka (THE reach trap)"),
        ("franka", (0.5, -0.3, 0.93), True, "normal bin drop z=0.93 + Franka"),
        ("ur10", (0.5, -0.3, 2.25), False, "1.5m column + UR10 (1.3m reach, still too far)"),
        ("ur10", (1.05, 0.0, 0.78), True, "far-but-reachable target 1.05m + UR10 (within 1.3m)"),
        ("franka", (1.6, 0.0, 0.78), False, "1.6m-away target + Franka (0.855m reach)"),
    ]
    rpass = 0
    print("=== GROUNDED reach feasibility — trap battery ===")
    for rob, tgt, exp, label in reach_cases:
        r = check_reach_feasibility(rob, tgt)
        hit = (r["feasible"] == exp)
        rpass += hit
        print(f"  [{'OK' if hit else 'XX'}] {rob:7} {label:52} feasible={r['feasible']!s:5}")
        if not hit:
            print(f"        reason: {r['reason']}")
    print(f"\n{rpass}/{len(reach_cases)} reach verdicts correct.")
    print("THE TRAPS now grounded: suction-on-slippery-cylinder (seal breaks) + 1.5m-column (exceeds arm reach).")
    print("These are the grounded checks the agent should CALL before asserting a special-order is buildable.")
    total, tot = npass + rpass, len(cases) + len(reach_cases)
    print(f"OVERALL: {total}/{tot}")
    return 0 if total == tot else 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
