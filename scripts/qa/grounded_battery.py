#!/usr/bin/env python3
"""grounded_battery.py (cont.319eee) — the grounded special-order reasoner AT SCALE (Anton: "jag ville göra det på skala").

diagnose_special_order is PURE first-principles Python (no LLM, no GPU) -> it can be exercised on a large LABELLED
battery of adversarial special-orders, fully deterministic + instant. Each case carries the EXPECTED verdict, so this
measures real precision/recall instead of just "it ran":

  * FALSE-PASS  = an INFEASIBLE order judged feasible          (the dangerous class -> reported LOUDLY)
  * FALSE-BLOCK = a FEASIBLE order judged infeasible/unclear   (over-refusal -> also reported)

This is the false-success-vakt applied to my OWN reasoning rules, on scale. The labels were hand-checked against the
rules in grounded_feasibility.py (suction seal-breaks, jaw width range, magnetic=ferrous, reach sphere @ base_z=0.75,
payload table, flow sorter map). The point is NOT to confirm the rules — it's to surface where they over/under-fire.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from grounded_feasibility import Obj, diagnose_special_order

# Each case: (id, spec, expect_feasible, note). expect_feasible is the EXPECTED overall verdict (bool).
# kind tags let me group the failure-mode map.
C = []
def case(cid, kind, spec, expect_feasible, note):
    C.append((cid, kind, spec, expect_feasible, note))

# ── gripper-object (suction / jaw / magnetic / soft) ──────────────────────────
case("GO-suction-dry-box",  "gripper", {"robot":"franka","gripper":"vacuum_suction","object":Obj("plastic","box","smooth-dry",0.5,0.08)}, True,  "suction OK on dry smooth box")
case("GO-suction-wet-cyl",  "gripper", {"robot":"ur10","gripper":"vacuum_suction","object":Obj("steel","cylinder","smooth-wet",2.0,0.07)}, False, "suction seal breaks on wet -> the slippery-cylinder trap")
case("GO-suction-oily",     "gripper", {"robot":"franka","gripper":"vacuum_suction","object":Obj("steel","box","oily",1.0,0.08)}, False, "suction breaks on oily")
case("GO-suction-porous",   "gripper", {"robot":"franka","gripper":"vacuum_suction","object":Obj("cardboard","box","rough",0.4,0.09)}, False, "suction can't seal porous cardboard")
case("GO-suction-heavy",    "gripper", {"robot":"ur10","gripper":"vacuum_suction","object":Obj("plastic","box","smooth-dry",4.0,0.10)}, False, "4kg > 3kg suction payload")
case("GO-magnet-steel",     "gripper", {"robot":"ur10","gripper":"magnetic","object":Obj("steel","box","smooth-dry",2.0,0.10)}, True,  "magnetic OK on ferrous steel")
case("GO-magnet-alu",       "gripper", {"robot":"ur10","gripper":"magnetic","object":Obj("aluminum","box","smooth-dry",1.0,0.10)}, False, "magnetic needs ferrous; aluminum non-ferrous")
case("GO-magnet-plastic",   "gripper", {"robot":"franka","gripper":"magnetic","object":Obj("plastic","box","smooth-dry",0.5,0.08)}, False, "magnetic on plastic")
case("GO-jaw-graspable",    "gripper", {"robot":"franka","gripper":"parallel_jaw","object":Obj("plastic","box","smooth-dry",0.5,0.06)}, True,  "jaw OK at 6cm")
case("GO-jaw-toowide",      "gripper", {"robot":"franka","gripper":"parallel_jaw","object":Obj("wood","box","rough",1.0,0.20)}, False, "0.20m outside jaw range")
case("GO-jaw-toonarrow",    "gripper", {"robot":"franka","gripper":"parallel_jaw","object":Obj("steel","cylinder","smooth-dry",0.2,0.005)}, False, "0.005m below jaw min")
case("GO-jaw-fragile",      "gripper", {"robot":"franka","gripper":"parallel_jaw","object":Obj("glass","box","smooth-dry",0.3,0.05,fragile=True)}, True, "graspable+fragile -> feasible w/ force control (low conf)")
case("GO-soft-heavy",       "gripper", {"robot":"ur10","gripper":"soft_compliant","object":Obj("rubber","irregular","textured",3.0,0.10)}, False, "3kg > soft gripper payload")
case("GO-soft-light",       "gripper", {"robot":"franka","gripper":"soft_compliant","object":Obj("rubber","irregular","textured",0.4,0.08)}, True,  "soft OK on light irregular")

# ── reach (base_z=0.75) ───────────────────────────────────────────────────────
case("RE-franka-close",     "reach", {"robot":"franka","targets":[(0.3,0.0,0.85)]}, True,  "0.32m within franka 0.855m")
case("RE-franka-column",    "reach", {"robot":"franka","targets":[(0.0,0.0,2.25)]}, False, "1.5m column top out of franka reach")
case("RE-ur10-marginal",    "reach", {"robot":"ur10","targets":[(1.2,0.0,0.75)]}, True,  "1.2m near ur10 1.3m limit -> marginal but feasible")
case("RE-ur10-far",         "reach", {"robot":"ur10","targets":[(1.5,0.0,0.75)]}, False, "1.5m beyond ur10 1.30m")
case("RE-ur5-far",          "reach", {"robot":"ur5","targets":[(0.0,0.0,2.0)]}, False, "1.25m up beyond ur5 0.85m")

# ── payload ───────────────────────────────────────────────────────────────────
case("PA-franka-over",      "payload", {"robot":"franka","gripper":"magnetic","object":Obj("steel","box","smooth-dry",5.0,0.10)}, False, "5kg > franka 3kg payload")
case("PA-ur10-ok",          "payload", {"robot":"ur10","gripper":"magnetic","object":Obj("steel","box","smooth-dry",5.0,0.10)}, True,  "5kg within ur10 10kg")

# ── flow expressibility ───────────────────────────────────────────────────────
case("FL-colour-bins",      "flow", {"robot":"franka","flow":[{"conditional":True,"condition":"route red items to the left bin, blue to the right"}]}, True,  "colour->bins expressible")
case("FL-barcode-bins",     "flow", {"robot":"franka","flow":[{"conditional":True,"condition":"sort by barcode into bins"}]}, True,  "barcode->bins")
case("FL-dest-city",        "flow", {"robot":"franka","flow":[{"conditional":True,"condition":"route each box to its shipping destination city"}]}, False, "destination not sensable in-sim")
case("FL-smell",            "flow", {"robot":"franka","flow":[{"conditional":True,"condition":"divert items that smell of solvent"}]}, False, "no sorter for smell")
case("FL-weight-station",   "flow", {"robot":"ur10","flow":[{"conditional":True,"condition":"over 1.5kg goes to a palletizer station, lighter to inspection"}]}, False, "weight sortable BUT branch-to-stations is a gap (unclear -> not feasible)")
case("FL-weight-bins",      "flow", {"robot":"franka","flow":[{"conditional":True,"condition":"heavier parts to the far bin"}]}, True,  "weight->bins expressible")

# ── throughput ────────────────────────────────────────────────────────────────
case("TP-over",             "throughput", {"robot":"franka","throughput_per_min":120}, False, "120/min beyond single arm")
case("TP-ok",               "throughput", {"robot":"franka","throughput_per_min":30}, True,  "30/min realistic")

# ── COMBINED (Anton-style multi-constraint special-orders) ────────────────────
case("CB-slippery-order",   "combined", {"robot":"ur10","gripper":"vacuum_suction","object":Obj("steel","cylinder","smooth-wet",2.0,0.07),
                                          "targets":[(0.6,0.0,0.9)],"flow":[{"conditional":True,"condition":"split by weight: over 1.5kg to a palletizer, lighter to a camera"}]}, False,
                                          "Anton's exact trap: suction-wet BLOCK + weight-to-station UNCLEAR")
case("CB-clean-feasible",   "combined", {"robot":"franka","gripper":"parallel_jaw","object":Obj("plastic","box","smooth-dry",0.4,0.06),
                                          "targets":[(0.4,0.0,0.85)],"flow":[{"conditional":True,"condition":"sort by colour into bins"}],"throughput_per_min":20}, True,
                                          "fully feasible multi-constraint order -> must NOT false-block")
case("CB-heavy-magnet-ok",  "combined", {"robot":"ur10","gripper":"magnetic","object":Obj("steel","box","smooth-dry",8.0,0.12),
                                          "targets":[(1.0,0.0,0.75)],"throughput_per_min":15}, True, "8kg steel, magnetic, ur10 reach+payload OK")


def run():
    fp, fb, ok_pass, ok_block = [], [], [], []
    for cid, kind, spec, exp, note in C:
        rep = diagnose_special_order(spec)
        got = rep["feasible"]
        status = "OK " if got == exp else ("FALSE-PASS" if (got and not exp) else "FALSE-BLOCK")
        if got == exp:
            (ok_pass if got else ok_block).append(cid)
        elif got and not exp:
            fp.append((cid, kind, note, rep))
        else:
            fb.append((cid, kind, note, rep))
        why = ""
        if rep["blockers"]:
            why = " | BLOCK: " + "; ".join(f"{b['check']}:{b['reason'][:60]}" for b in rep["blockers"][:2])
        elif rep["unclear"]:
            why = " | UNCLEAR: " + "; ".join(f"{u['check']}:{u['reason'][:55]}" for u in rep["unclear"][:2])
        mark = "✓" if got == exp else "✗"
        print(f"[{mark}] {cid:22} {kind:10} exp={'feas' if exp else 'INFEAS':6} got={'feas' if got else 'INFEAS':6} {status}{why}")

    n = len(C)
    print(f"\n=== {len(ok_pass)+len(ok_block)}/{n} correct  |  {len(fp)} FALSE-PASS  |  {len(fb)} FALSE-BLOCK ===")
    if fp:
        print("\n⚠️  FALSE-PASS (infeasible order judged feasible — the dangerous class):")
        for cid, kind, note, rep in fp:
            print(f"    {cid} ({kind}): {note}")
    if fb:
        print("\n⚠️  FALSE-BLOCK (feasible order judged infeasible — over-refusal):")
        for cid, kind, note, rep in fb:
            print(f"    {cid} ({kind}): {note}")
            for b in rep["blockers"] + rep["unclear"]:
                print(f"        {b['check']}: {b['reason'][:90]}")
    # honest precision/recall on the dangerous axis (catching infeasible)
    infeas = [c for c in C if not c[3]]
    caught = [c for c in infeas if not diagnose_special_order(c[2])["feasible"]]
    feas = [c for c in C if c[3]]
    passed = [c for c in feas if diagnose_special_order(c[2])["feasible"]]
    print(f"\nrecall on INFEASIBLE (traps caught):   {len(caught)}/{len(infeas)}")
    print(f"specificity on FEASIBLE (no over-block): {len(passed)}/{len(feas)}")
    return len(fp) == 0 and len(fb) == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
