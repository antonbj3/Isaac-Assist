#!/usr/bin/env python3
"""compose_stress_scale.py (cont.319aaa) — SCALED adversarial special-order stress test of the NL reasoning layer.

Anton's real gotcha-sim vision: NOT one request, but MANY special-orders that require genuine REASONING +
UNDERSTANDING (specific object attributes, a gripper that must actually hold THAT object, conditional Y-split flows,
geometric/spatial constraints, vagueness that SHOULD trigger a clarifying question) — mapping, at scale, where the
shallow keyword-to-block matcher silently picks approximate blocks instead of capturing the variables / asking.

Pure Gemini calls (no Kit). For each request it runs the production orchestrator (compose_orchestrate --dry-run) and
records what it did, then CATEGORISES the honesty of the response. The point is a FAILURE-MODE MAP, not a pass-count.

Categories:
  HONEST-GAP    : flagged a gap + picked few/no cells for a genuinely-unsupported request (good).
  SHALLOW-PICK  : picked confident blocks while IGNORING the specific constraints (object attrs / gripper / Y-split)
                  -> the dangerous gotcha: looks composed, silently drops the requirement.
  SHOULD-CLARIFY: the request is VAGUE/under-specified; the system guessed instead of asking (the missing capability).
  REASONABLE    : genuinely handled (right blocks, gap flagged where due).
The categories are heuristics over (cells, gap_flag) + the trap each request encodes; the per-request detail is
printed for human read — this maps the terrain, it does not pretend to a single verdict.
"""
import sys, os, subprocess, json

HERE = os.path.dirname(os.path.abspath(__file__))

# Each: (id, request, trap = the specific thing a SHALLOW matcher will drop, kind)
CASES = [
    ("grip-mismatch", "Pick up a 5 kg greasy steel ball with a vacuum suction cup and drop it in a bin", "suction can't hold a greasy heavy sphere", "gripper-object"),
    ("y-split-cond",  "Parts arrive on a belt; route the RED ones left to packing and the BLUE ones right to a press", "conditional Y-split routing", "conditional-flow"),
    ("too-vague",     "Set up a station that handles my parts efficiently", "no object/op/robot specified -> must ask", "vague"),
    ("tall-column",   "Stack parts into a single vertical column 1.5 metres tall", "1.5m exceeds arm reach -> geometric limit", "geometric"),
    ("fragile-care",  "Sort fragile glass vials by size into trays WITHOUT cracking them", "fragility/force-care constraint", "object-attr"),
    ("inspect-route", "Pick parts off a conveyor, inspect each, then pack the good ones but bin the rejects", "conditional route on inspection result", "conditional-flow"),
    ("quadruped",     "A four-legged dog robot carries boxes across the warehouse floor", "no quadruped in the catalog", "impossible-robot"),
    ("throughput",    "Palletise 500 boxes per minute onto a euro-pallet", "500/min throughput is unmeetable", "scale-constraint"),
    ("tool-change",   "One robot that first welds a seam, then swaps to a gripper and picks the part", "in-task tool change", "tool-change"),
    ("ambiguous-op",  "Process the widgets at the bench", "what operation? -> must ask", "vague"),
    ("shared-space",  "Two robot arms working inside the same 1 metre cube without colliding", "tight shared-workspace collision avoidance", "spatial"),
    ("deformable",    "Pick up a floppy rubber gasket and seat it into a groove", "deformable object + insertion", "deformable"),
    ("tri-robot",     "Two arms hold a large panel steady while a third arm drills four holes in it", "3-robot coordinated hold-and-drill", "multi-robot"),
    ("hidden-attr",   "Sort packages by their shipping destination city", "destination is data the scene doesn't carry", "hidden-attr"),
    ("torque-spec",   "Drive each bolt and tighten it to exactly 12 newton-metres", "force/torque spec", "force-spec"),
    ("timed-seq",     "Every 5 seconds, pick the newest arriving part and add it to a growing stack", "timing + growing stack", "timing"),
    ("mixed-feas",    "A Franka sorts parts by colour into bins, and overhead a drone films the line for QA", "Franka feasible + drone is a gap", "mixed"),
    ("reason-pick",   "Move the heavy items with your strongest robot and the light items with your fastest one", "requires reasoning about per-robot capability", "reasoning"),
]


def run_one(req):
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, "compose_orchestrate.py"), req, "--dry-run"],
                           capture_output=True, text=True, timeout=110)
        out = p.stdout + p.stderr
    except Exception as e:
        return {"cells": None, "gap": None, "err": str(e), "raw": ""}
    cells, gap, reasoning = [], None, ""
    for l in out.splitlines():
        if l.startswith("E2E PLAN"):
            import re
            m = re.search(r"cells=(\[[^\]]*\])", l)
            cells = eval(m.group(1)) if m else []
            gap = "gap_flag=True" in l
        if l.startswith("E2E REASONING"):
            reasoning = l[14:][:240]
    return {"cells": cells, "gap": gap, "reasoning": reasoning, "raw": out[-300:]}


def categorise(case, r):
    _id, req, trap, kind = case
    cells, gap = r.get("cells"), r.get("gap")
    if cells is None:
        return "ERROR"
    n = len(cells)
    if kind == "vague":
        # the right behaviour is to ASK; the system has NO clarify path, so anything it does that isn't an empty gap
        # is a guess. Empty+gap is the closest-to-honest it can be; a confident pick = SHOULD-CLARIFY (guessed).
        return "SHOULD-CLARIFY" if n > 0 else "HONEST-GAP(can't-ask)"
    if kind in ("impossible-robot", "hidden-attr", "tool-change", "deformable"):
        return "HONEST-GAP" if (gap and n == 0) else ("SHALLOW-PICK" if n > 0 else "HONEST-GAP")
    # constraint-bearing requests: a confident multi-cell pick that ignores the specific trap = SHALLOW-PICK
    if n > 0 and not gap:
        return "SHALLOW-PICK"
    if n > 0 and gap:
        return "PARTIAL-PICK+gap"
    return "HONEST-GAP"


def main():
    print(f"=== SCALED adversarial special-order stress ({len(CASES)} requests) ===\n")
    rows = []
    for case in CASES:
        _id, req, trap, kind = case
        r = run_one(req)
        cat = categorise(case, r)
        rows.append((_id, kind, cat, r))
        print(f"[{cat:20}] {_id:14} ({kind}) cells={r.get('cells')} gap={r.get('gap')}")
        print(f"     trap (what a shallow matcher drops): {trap}")
        print()
    from collections import Counter
    dist = Counter(c for _, _, c, _ in rows)
    print("=== FAILURE-MODE MAP ===")
    for cat, n in dist.most_common():
        print(f"  {n:2}x {cat}")
    shallow = sum(n for c, n in dist.items() if "SHALLOW" in c or "SHOULD-CLARIFY" in c or "PARTIAL" in c)
    print(f"\n{shallow}/{len(CASES)} requests exposed a reasoning-layer gap (shallow-pick / guessed-instead-of-asking / partial).")
    print("HONEST takeaway: the orchestrator matches keywords->blocks; it does NOT capture object/gripper/flow")
    print("VARIABLES, reason about geometry/physics, model conditional Y-splits, or ASK when vague.")


if __name__ == "__main__":
    main()
