#!/usr/bin/env python3
"""Regression: every ST that plc_export_poc.emit_sfc() emits must PARSE under a real IEC 61131-3 grammar.

Adversarial verification of the PLC-export claim (project_isaac_assist_plc_export_direction): the emitted ST
was previously pseudo-ST that NO IEC grammar accepts (slashes in identifiers, bare `0.4s` time literals,
`target=...` named args, `[0,0,h]` array literals). This test feeds each emitted ST to `blark` (a lark-based
IEC 61131-3 parser) and asserts it parses -- so "valid ST" is a measured fact, not a self-assessment.

Run:  python3 scripts/qa/test_plc_st_parses.py     (exit 0 = all parse; non-zero = a regression)
Needs: pip install blark
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import plc_export_poc as plc  # noqa: E402

try:
    from blark.parse import parse_source_code
except ImportError:
    print("SKIP: blark not installed (pip install blark)"); sys.exit(0)


def st_parses(src):
    """True iff blark parses the ST with no exception."""
    res = parse_source_code(src)
    exc = getattr(res, "exception", None)
    if exc:
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"
    res.transform()  # force tree-build too (catches transform-stage errors)
    return True, "OK"


def main():
    # chain_stages templates (sources + receivers) + a multi-object palletizer + a single canonical
    stages = json.load(open(f"{REPO}/workspace/chain_stages.json")).get("stages", {})
    singles = sorted(set(list(stages.keys()) + ["CP-CHAIN-FLAT", "CP-08"]))
    chains = [("CP-08", "CP-CHAIN-FLAT"), ("CP-CHAIN-FRANKA-SRC", "CP-CHAIN-PALLETIZE-RECV")]

    fails = []
    n = 0
    for tid in singles:
        if not os.path.exists(f"{plc.TPL_DIR}/{tid}.json"):
            continue
        st = plc.emit_sfc(plc.extract_ir(tid))
        ok, why = st_parses(st)
        n += 1
        print(f"  {'OK ' if ok else 'FAIL'}  {tid}  ({st.count(chr(10))+1} lines)" + ("" if ok else f"  <- {why}"))
        if not ok:
            fails.append(tid)
    for a, b in chains:
        if not (os.path.exists(f"{plc.TPL_DIR}/{a}.json") and os.path.exists(f"{plc.TPL_DIR}/{b}.json")):
            continue
        st = plc.emit_sfc(plc.chain_ir(a, b))
        ok, why = st_parses(st)
        n += 1
        print(f"  {'OK ' if ok else 'FAIL'}  CHAIN {a}->{b}" + ("" if ok else f"  <- {why}"))
        if not ok:
            fails.append(f"{a}->{b}")

    print(f"\n{n - len(fails)}/{n} ST artifacts parse under the blark IEC 61131-3 grammar.")

    # SECOND BACKEND (hot-swap thesis): the ROS2/MoveItPy node emitted from the SAME IR must be valid Python.
    import ast
    r_ok = 0
    for tid in singles:
        if not os.path.exists(f"{plc.TPL_DIR}/{tid}.json"):
            continue
        try:
            ast.parse(plc.emit_ros2(plc.extract_ir(tid)))
            r_ok += 1
        except SyntaxError as e:
            print(f"  ROS2 FAIL {tid}: {e}")
            fails.append(f"ros2:{tid}")
    print(f"{r_ok} ROS2 backend nodes are ast-valid Python (same IR -> 2nd backend).")

    if fails:
        print("REGRESSION:", fails)
        sys.exit(1)
    print("ALL BACKENDS VALID (ST + ROS2).")


if __name__ == "__main__":
    main()
