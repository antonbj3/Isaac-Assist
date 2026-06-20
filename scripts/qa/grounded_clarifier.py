#!/usr/bin/env python3
"""grounded_clarifier.py (cont.319eee) — the "ASK FOR CLARIFICATION / capture the variables" vision piece.

Anton's vision: a special-order may be VAGUE; the system must then ASK clarifying questions + capture the missing
variables (not silently guess + assert success). The production agent has an LLM negotiator that asks questions, but
those are prompt-GUESSED. This is the GROUNDED complement: it asks EXACTLY the variables a feasibility DECISION needs
and no more — driven by which grounded check (grip-selection / jaw / suction / magnetic / reach / payload / flow)
cannot run without them. A precise tool the negotiator can call to know what's actually missing, deterministically.

Pairs with grounded_feasibility.diagnose_special_order: clarify FIRST (capture variables) -> then diagnose (ground).
No LLM, no Kit, no ChromaDB.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))


def _missing(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "unknown", "unclear", "n/a", "?"))


def clarify_special_order(raw: dict) -> dict:
    """raw = the parser's spec dict (object as a plain dict, fields may be absent/None/'unknown').
    Returns {complete, questions:[{field, question, needed_for}], assumptions:[...]}. Questions are need-driven:
    only the variables a grounded check actually requires are asked, deduped by field, ordered by how blocking they are."""
    qs, seen = [], set()
    assumptions = []

    def ask(field, question, needed_for):
        if field in seen:
            return
        seen.add(field)
        qs.append({"field": field, "question": question, "needed_for": needed_for})

    obj = raw.get("object") or {}
    gripper = raw.get("gripper")
    robot = raw.get("robot")

    # ── object identity: without the material we can neither choose nor validate a grip ──
    if _missing(obj.get("material")):
        ask("object.material", "What is the object made of? (steel/aluminium/plastic/glass/cardboard/…) — "
            "determines which grip can actually hold it (e.g. magnetic needs a ferrous metal).", "grip-selection")

    # ── destination: reach can't be grounded without a target ──
    if not raw.get("targets"):
        ask("targets", "Where should the object end up — a position (x,y,z) or a named destination (bin/conveyor/station)?",
            "reach")

    # ── robot: defaultable, but say so honestly rather than silently ──
    if _missing(robot):
        ask("robot", "Which robot/arm should do this — or shall I select one by reach + payload? "
            "(I'll otherwise assume a UR10 for its larger reach/payload.)", "reach+payload")
        assumptions.append("robot=ur10 (largest reach/payload) unless told otherwise")

    # ── gripper: if unstated, capture the attributes needed to CHOOSE one; if stated, only that grip's needs ──
    if _missing(gripper):
        if _missing(obj.get("mass_kg")):
            ask("object.mass_kg", "How heavy is the object (kg)? — sets the payload limit and whether suction can lift it.", "gripper-choice")
        if _missing(obj.get("width_m")):
            ask("object.width_m", "What is the across-grip width (m)? — a parallel-jaw only spans ~1–12 cm.", "gripper-choice")
        if _missing(obj.get("surface")):
            ask("object.surface", "What's the surface like — dry / wet / oily / porous? — suction can't seal on wet/oily/porous.", "gripper-choice")
    else:
        g = gripper.lower().replace("-", "_")
        if any(k in g for k in ("jaw", "finger", "gripper")):
            if _missing(obj.get("width_m")):
                ask("object.width_m", "What is the across-grip width (m)? — needed to check it fits the parallel-jaw range.", "jaw")
        if any(k in g for k in ("suction", "vacuum")):
            if _missing(obj.get("surface")):
                ask("object.surface", "What's the surface finish? — suction can't seal on a wet/oily/porous surface.", "suction")
            if _missing(obj.get("mass_kg")):
                ask("object.mass_kg", "How heavy is it (kg)? — suction has a ~3 kg payload ceiling.", "suction")
        if "magnet" in g:
            if _missing(obj.get("material")):
                ask("object.material", "What is it made of? — a magnetic grip only holds ferrous metals (steel/iron).", "magnetic")

    # ── flow vagueness: a conditional route with no stated property/destination ──
    for step in raw.get("flow") or []:
        if step.get("conditional") and _missing(step.get("condition")):
            ask("flow.condition", "You described conditional routing — sort by which property (colour/weight/barcode/material) "
                "and route to bins or to distinct downstream stations?", "flow")

    return {"complete": len(qs) == 0, "questions": qs, "assumptions": assumptions}


# ── test battery: vague orders + the variables each SHOULD trigger ─────────────
CASES = [
    ("CL-bare", {"object": {}, "flow": [{"conditional": False}]},
     {"object.material", "object.mass_kg", "object.width_m", "object.surface", "targets", "robot"},
     "almost-empty order, no gripper -> ALL choose-a-grip attrs + destination + robot (capture every variable)"),
    ("CL-gripperless", {"robot": "franka", "object": {"material": "plastic"}, "targets": [(0.4, 0, 0.85)]},
     {"object.mass_kg", "object.width_m", "object.surface"}, "no gripper -> need attrs to CHOOSE one"),
    ("CL-jaw-nowidth", {"robot": "franka", "gripper": "parallel_jaw", "object": {"material": "plastic"}, "targets": [(0.4, 0, 0.85)]},
     {"object.width_m"}, "jaw stated -> only width missing (not surface)"),
    ("CL-suction-noattrs", {"robot": "ur10", "gripper": "vacuum_suction", "object": {"material": "steel"}, "targets": [(0.5, 0, 0.9)]},
     {"object.surface", "object.mass_kg"}, "suction stated -> surface + mass (sealing + payload)"),
    ("CL-magnet-nomat", {"robot": "ur10", "gripper": "magnetic", "object": {}, "targets": [(0.5, 0, 0.9)]},
     {"object.material"}, "magnet stated -> only material (ferrous?)"),
    ("CL-vague-flow", {"robot": "franka", "gripper": "parallel_jaw", "object": {"material": "plastic", "width_m": 0.06},
                       "targets": [(0.4, 0, 0.85)], "flow": [{"conditional": True, "condition": ""}]},
     {"flow.condition"}, "conditional routing with no property -> ask"),
    ("CL-complete", {"robot": "ur10", "gripper": "magnetic", "object": {"material": "steel", "mass_kg": 2.0, "width_m": 0.1, "surface": "smooth-dry"},
                     "targets": [(0.6, 0, 0.9)]},
     set(), "fully specified -> NO questions (must not over-ask)"),
]


def run():
    bad = []
    for cid, raw, expect_fields, note in CASES:
        rep = clarify_special_order(raw)
        got = {q["field"] for q in rep["questions"]}
        ok = got == expect_fields
        if not ok:
            bad.append((cid, expect_fields, got, note))
        mark = "✓" if ok else "✗"
        print(f"[{mark}] {cid:18} complete={str(rep['complete']):5} asks={sorted(got)}")
        for q in rep["questions"]:
            print(f"        ({q['needed_for']}) {q['question'][:88]}")
        if rep["assumptions"]:
            print(f"        assume: {rep['assumptions']}")
    print(f"\n=== {len(CASES)-len(bad)}/{len(CASES)} correct ===")
    if bad:
        for cid, exp, got, note in bad:
            print(f"  ✗ {cid} ({note}): expected {sorted(exp)} got {sorted(got)}")
    return not bad


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
