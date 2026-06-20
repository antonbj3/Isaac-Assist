#!/usr/bin/env python3
"""grounded_harness.py (cont.319eee) — the agentic-harness DECISION skeleton that composes the grounded tools.

Anton's deepest intent: not prompt/system-message engineering, but "a HARNESS sitting underneath that STEERS and
FETCHES, has TOOLS and forms of scene_eyes." This is the deterministic skeleton of that control logic for a
special-order: it STEERS to one of three actions by calling the grounded tools, instead of guessing + asserting:

    ASK     — the order is vague; capture the missing variables first   (clarify_special_order)
    BUILD   — fully specified AND grounded-feasible; hand to the composer/Kit
    EXPLAIN — fully specified but grounded-INFEASIBLE; say why + suggest the fix   (diagnose_special_order)

This is the reference for wiring these as ChatOrchestrator tools: the production agent's tool-loop makes the same
ASK/BUILD/EXPLAIN decision via the LLM, but now backed by GROUNDED checks (physics) rather than assertion. The whole
skeleton is pure + deterministic (no LLM, no Kit, no ChromaDB) so it's testable; the LLM sits ABOVE it, the grounding
sits BELOW it.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from grounded_clarifier import clarify_special_order
from grounded_feasibility import Obj, diagnose_special_order


def ground_order(raw: dict) -> dict:
    """Steer a parsed special-order to ASK / BUILD / EXPLAIN, grounded at every step."""
    clar = clarify_special_order(raw)
    if not clar["complete"]:
        return {"action": "ASK", "questions": clar["questions"], "assumptions": clar["assumptions"]}

    o = raw.get("object") or {}
    obj = Obj(material=o.get("material", "unknown"), shape=o.get("shape", "box"),
              surface=o.get("surface", "smooth-dry"), mass_kg=float(o.get("mass_kg", 0.5) or 0.5),
              width_m=float(o.get("width_m", 0.06) or 0.06), fragile=bool(o.get("fragile", False)))
    spec = {"robot": raw.get("robot") or "ur10", "gripper": raw.get("gripper"), "object": obj,
            "targets": raw.get("targets", []), "flow": raw.get("flow", []),
            "throughput_per_min": raw.get("throughput_per_min")}
    rep = diagnose_special_order(spec)
    if rep["feasible"]:
        return {"action": "BUILD", "verdict": "feasible", "report": rep}
    return {"action": "EXPLAIN", "verdict": "infeasible",
            "blockers": rep["blockers"], "unclear": rep["unclear"], "report": rep}


def _fmt(res, raw):
    a = res["action"]
    if a == "ASK":
        out = [f"  -> ASK ({len(res['questions'])} clarifying question(s)):"]
        for q in res["questions"]:
            out.append(f"       · [{q['needed_for']}] {q['question']}")
        for asm in res["assumptions"]:
            out.append(f"       (assume {asm})")
        return "\n".join(out)
    if a == "BUILD":
        return "  -> BUILD (grounded-feasible) — hand to composer/Kit"
    out = ["  -> EXPLAIN (grounded-INFEASIBLE):"]
    for b in res["blockers"]:
        sug = f"  [suggest: {b.get('suggested_gripper')}]" if b.get("suggested_gripper") and b.get("suggested_gripper") != raw.get("gripper") else ""
        out.append(f"       ✗ {b['check']}: {b['reason']}{sug}")
    for u in res["unclear"]:
        out.append(f"       ? {u['check']}: {u['reason']}")
    return "\n".join(out)


DEMO = [
    ("VAGUE: 'place an object somewhere and sort the output'",
     {"object": {}, "flow": [{"conditional": True, "condition": ""}]}),
    ("COMPLETE+FEASIBLE: Franka jaw, dry plastic box 6cm to a reachable bin, colour-sort",
     {"robot": "franka", "gripper": "parallel_jaw",
      "object": {"material": "plastic", "shape": "box", "surface": "smooth-dry", "mass_kg": 0.4, "width_m": 0.06},
      "targets": [(0.4, 0.0, 0.85)], "flow": [{"conditional": True, "condition": "sort by colour into bins"}]}),
    ("COMPLETE+INFEASIBLE: Anton's slippery wet steel cylinder + suction + weight-to-station Y-split",
     {"robot": "ur10", "gripper": "vacuum_suction",
      "object": {"material": "steel", "shape": "cylinder", "surface": "smooth-wet", "mass_kg": 2.0, "width_m": 0.07},
      "targets": [(0.6, 0.0, 0.9)],
      "flow": [{"conditional": True, "condition": "over 1.5kg goes to a palletizer station, lighter to inspection"}]}),
]


if __name__ == "__main__":
    print("=== grounded agentic-harness decision skeleton (ASK / BUILD / EXPLAIN) ===\n")
    for label, raw in DEMO:
        print(label)
        print(_fmt(ground_order(raw), raw))
        print()
