#!/usr/bin/env python3
"""Regression: the handoff-compatibility PREDICTOR (compose_handoff.chain_compat) must agree with ground truth.

chain_compat is the Kit-free gate that decides which (src,recv) pairs the orchestrator/LLM routes into an
expensive cross-Kit chain run. If it drifts, the LLM either wastes runs on impossible chains or skips possible
ones. This locks it against the proven ground truth + the documented failure it claims to pre-filter:
  - every adjacent pair in workspace/chain_stages.json proven_chains MUST predict COMPAT (no false-negatives);
  - the cont.262 CP-73 -> CP-13 case (CP-73 delivers into a deep Bin) MUST predict INCOMPAT (the claim in its
    own docstring);
  - NEGATIVE CONTROL: a flat delivery into a RAISED-picking UR10 receiver MUST predict INCOMPAT (height branch
    actually discriminates -- not an always-COMPAT rubber stamp).
Run: python3 scripts/qa/test_chain_compat.py
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import compose_handoff as ch  # noqa: E402


def main():
    reg = json.load(open(f"{REPO}/workspace/chain_stages.json"))
    fails = []

    # 1: all proven adjacent pairs -> COMPAT
    n_pairs = 0
    for c in reg["proven_chains"]:
        names = c["stages"]
        for a, b in zip(names, names[1:]):
            n_pairs += 1
            try:
                r = ch.chain_compat(a, b)
            except Exception as e:
                r = {"compatible": False, "reason": f"EXC {e}"}
            if not r["compatible"]:
                fails.append(f"proven pair {a}->{b} WRONGLY incompatible: {r['reason'][:90]}")

    # 2: documented bad case -> INCOMPAT
    bad = ch.chain_compat("CP-73", "CP-13")
    if bad["compatible"]:
        print("  CP-73->CP-13: COMPAT (WRONG)")
        fails.append("CP-73->CP-13 should be INCOMPAT (deep bin) but predicted COMPAT")
    else:
        print(f"  CP-73->CP-13: INCOMPAT ok ({bad['reason'][:60]})")

    # 3: NEGATIVE CONTROL -- flat delivery (0.775) into a RAISED-picking UR10 must be INCOMPAT by height
    neg = ch.chain_compat("CP-CHAIN-UR10-SRC", "CP-CHAIN-UR10-RECV-NATIVE")  # delivers flat 0.775 -> UR10 picks 0.975
    if neg["compatible"]:
        print("  flat->UR10-raised: COMPAT (WRONG -- height branch is a rubber stamp)")
        fails.append("flat 0.775 -> UR10 raised pick should be INCOMPAT by height but predicted COMPAT")
    else:
        print(f"  flat->UR10-raised: INCOMPAT ok ({neg['reason'][:60]})")

    print(f"\n{n_pairs} proven pairs checked.")
    if fails:
        print("REGRESSION:")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"PREDICTOR FAITHFUL: {n_pairs} proven pairs COMPAT, bad case + neg-control INCOMPAT.")


if __name__ == "__main__":
    main()
