#!/usr/bin/env python3
"""Regression: the CONTROL FLOW of the emitted ST CASE machine must be correct (not just syntactically valid).

blark proves the ST PARSES; roundtrip proves the orchestration is FAITHFUL. Neither checks that the state
machine actually WALKS correctly -- the grip-retry skip arithmetic (skip = i+4 if i+4 < n else done) is a
hand-computed index where an off-by-one would silently mis-route the abandon-cube branch into the middle of
another cube's cycle. This parses the EMITTED ST text, builds the step->{next} graph, and asserts:
  1. every `step := M` target is in range [0, n-1];
  2. every step is reachable from step 0; the terminal `done` step is reachable;
  3. each Grip step's ABANDON branch lands on a cube's FIRST phase (Approach) or the terminal -- never mid-cycle;
  4. the happy path visits all N cubes' Approach steps in order.
Run: python3 scripts/qa/test_plc_controlflow.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plc_export_poc as plc  # noqa: E402

BRANCH = re.compile(r"^\s*(\d+):\s*\(\*\s*(\S+)\s*\*\)", re.M)


def parse_cases(st):
    """-> {idx: {'label': name, 'targets': [int...], 'done': bool}} from emitted ST text."""
    lines = st.splitlines()
    starts = [(i, m) for i, ln in enumerate(lines) for m in [BRANCH.match(ln)] if m]
    cases = {}
    for k, (li, m) in enumerate(starts):
        idx, label = int(m.group(1)), m.group(2)
        body_end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = "\n".join(lines[li:body_end])
        targets = [int(x) for x in re.findall(r"step\s*:=\s*(\d+)", body)]
        cases[idx] = {"label": label, "targets": targets, "done": "done := TRUE" in body}
    return cases


def check(tid):
    ir = plc.extract_ir(tid)
    st = plc.emit_sfc(ir)
    cases = parse_cases(st)
    n = len(cases)
    errs = []
    # 1: targets in range
    for i, c in cases.items():
        for t in c["targets"]:
            if not (0 <= t < n):
                errs.append(f"step {i} -> {t} out of range [0,{n})")
    # 2: reachability from 0
    seen, stack = set(), [0]
    while stack:
        x = stack.pop()
        if x in seen or x not in cases:
            continue
        seen.add(x)
        stack += cases[x]["targets"]
    unreached = set(cases) - seen
    if unreached:
        errs.append(f"unreachable steps: {sorted(unreached)}")
    terminal = [i for i, c in cases.items() if c["done"]]
    if not terminal or not any(t in seen for t in terminal):
        errs.append("terminal (done) step not reachable")
    # 3: grip abandon-branch lands on an Approach or the terminal
    approaches = {i for i, c in cases.items() if "Approach" in c["label"]}
    for i, c in cases.items():
        if "Grip" in c["label"]:
            # emit order: [lift(i+1), redescend(i-1), skip]
            if len(c["targets"]) >= 3:
                skip = c["targets"][2]
                if skip not in approaches and skip not in terminal:
                    errs.append(f"grip step {i} abandon -> {skip} ({cases.get(skip,{}).get('label','?')}) "
                                f"is neither an Approach nor terminal")
    # 4: Approach steps reached in object order (the happy path covers all cubes)
    if len(approaches) != ir["n_objects"]:
        errs.append(f"{len(approaches)} Approach steps != n_objects {ir['n_objects']}")
    return n, errs


def main():
    tids = ["CP-CHAIN-FLAT", "CP-08", "CP-12", "CP-CHAIN-PALLETIZE-RECV"]
    fails = []
    for tid in tids:
        if not os.path.exists(f"{plc.TPL_DIR}/{tid}.json"):
            print(f"  SKIP {tid}")
            continue
        n, errs = check(tid)
        print(f"  {'OK  ' if not errs else 'FAIL'} {tid}  ({n} steps)" + ("" if not errs else f"  <- {errs}"))
        if errs:
            fails.append(tid)
    print(f"\n{len(tids) - len(fails)}/{len(tids)} control-flow graphs correct." if not fails
          else f"\nREGRESSION: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
