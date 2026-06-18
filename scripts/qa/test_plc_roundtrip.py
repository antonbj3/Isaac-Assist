#!/usr/bin/env python3
"""Regression: the consume-IR round-trip (controller -> IR -> controller) must stay FAITHFUL + HONEST.

Guards the three false-successes caught in cont.297-299 (all were tautological/blind self-assessments):
  1. POSITION orchestration round-trips losslessly for the chain templates.
  2. LITERAL place ORIENTATION (gripper_rotation) is captured + round-trips (was silently dropped; roundtrip
     claimed lossless while blind to it).
  3. RUNTIME-COMPUTED orientation is HONESTLY flagged NOT-captured => lossless=False (must NOT falsely pass).
  4. The template's actual approach_height is captured (was hardcoded 0.10).

This locks in that roundtrip_check can SEE the fields it checks -- a comparator that can't see a dropped field
is a lie. Run: python3 scripts/qa/test_plc_roundtrip.py   (exit 0 = all hold; non-zero = regression).
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plc_export_poc as plc  # noqa: E402

# (template, expectations) -- only assert on templates that exist
CASES = [
    # position-only chains: fully lossless
    ("CP-CHAIN-FLAT", {"lossless": True, "orientation_note": "no_orientation"}),
    ("CP-08", {"lossless": True, "orientation_note": "no_orientation"}),
    ("CP-CHAIN-PALLETIZE-RECV", {"lossless": True, "orientation_note": "no_orientation"}),
    # literal orientation: captured + lossless WITH yaw
    ("CP-20", {"lossless": True, "orientation": True, "orientation_note": "literal_captured"}),
    ("CP-NEW-label-applicator-pose",
     {"lossless": True, "orientation": True, "orientation_note": "literal_captured", "approach_height": True}),
    # runtime-computed orientation: HONESTLY lossy (must not falsely pass)
    ("CP-NEW-6dof-pose-estimate-pick",
     {"lossless": False, "orientation": False, "orientation_note": "runtime_computed_NOT_captured"}),
    # approach_height varies -> must be captured
    ("CP-NEW-yrkesroll-ergonomics-lift-assist", {"approach_height": True, "lossless": True}),
]


def main():
    fails, n = [], 0
    for tid, exp in CASES:
        if not os.path.exists(f"{plc.TPL_DIR}/{tid}.json"):
            print(f"  SKIP {tid} (not present)")
            continue
        rc = plc.roundtrip_check(tid)
        n += 1
        bad = {k: (exp[k], rc.get(k)) for k in exp if rc.get(k) != exp[k]}
        # also assert the IR genuinely carries the actual approach_height value when the template sets one
        ir = plc.extract_ir(tid)
        if exp.get("approach_height") and ir.get("approach_height") is None:
            bad["approach_height_value"] = ("a real value", None)
        print(f"  {'OK  ' if not bad else 'FAIL'} {tid}  lossless={rc['lossless']} orient={rc['orientation']}"
              f"({rc['orientation_note']}) approach={rc['approach_height']}" + (f"  <- {bad}" if bad else ""))
        if bad:
            fails.append((tid, bad))
    print(f"\n{n - len(fails)}/{n} consume-IR round-trips faithful + honest.")
    if fails:
        print("REGRESSION:", fails)
        sys.exit(1)
    print("ALL FAITHFUL.")


if __name__ == "__main__":
    main()
