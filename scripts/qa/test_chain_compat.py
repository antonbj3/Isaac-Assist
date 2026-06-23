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
        names = c.get("stages")
        if not names:                                      # branching_chain (L2.5) entries are prose-described and
            continue                                       # validated by chain_branch_gate.py, not the linear pair-compat check
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

    # 3: NEGATIVE CONTROL -- reach-RANGE still discriminates (not a rubber stamp): a GROSS-unreachable handoff z
    # (floor-level 0.1, far below any receiver reach) MUST be INCOMPAT. (cont.319-L3: the OLD "flat 0.775 -> UR10
    # raised" neg-control was UNphysical -- the cross-Kit relay re-instantiates at the source z with z-offset=0, so
    # 0.775 IS within UR10 reach and that pair actually chains; CP-CONV-02-SRC@0.825->UR10 is a PROVEN COMPAT pair.
    # Replaced with a real out-of-reach case via measured_z.)
    neg = ch.chain_compat("CP-36", "CP-CHAIN-UR10-RECV-NATIVE", measured_z=0.1)  # 0.1 below UR10 reach floor (0.40)
    if neg["compatible"]:
        print("  floor-0.1->UR10: COMPAT (WRONG -- reach-range is a rubber stamp)")
        fails.append("floor-level z=0.1 -> UR10 receiver should be INCOMPAT (out of reach) but predicted COMPAT")
    else:
        print(f"  floor-0.1->UR10: INCOMPAT ok ({neg['reason'][:60]})")

    # 4: CAPACITY overflow neg-control (cont.318n) -- CP-08 (4 parts) -> STACK-RECV (capacity 3) MUST be INCOMPAT
    # (verified: the chain executes 3/4, extra part falls). Distinct from height/deep-bin = capacity branch works.
    cap = ch.chain_compat("CP-08", "CP-CHAIN-STACK-RECV")
    if cap["compatible"]:
        print("  CP-08->STACK-RECV: COMPAT (WRONG -- 4 parts overflow a 3-slot stacker)")
        fails.append("CP-08 (4) -> STACK-RECV (cap 3) should be INCOMPAT by capacity but predicted COMPAT")
    else:
        print(f"  CP-08->STACK-RECV: INCOMPAT ok ({cap['reason'][:60]})")

    # 5: FIXED-HEIGHT receiver neg-control (cont.319-CHAIN2) -- a RAISED source (z=0.975) into a fixed-height
    # palletize/stack receiver (pick surface z~0.825) MUST be INCOMPAT: the relayed cube lands with no support
    # at the pick surface and falls. MEASURED: CP-CHAIN-FRANKA-RAISED-SRC -> CP-CHAIN-PALLETIZE-RECV chained 0/1.
    # (The matched-height FRANKA-SRC -> PALLETIZE-RECV is a proven COMPAT pair, checked above — so this branch
    # discriminates by Δz, not a blanket reject of palletize receivers.)
    fix = ch.chain_compat("CP-CHAIN-FRANKA-RAISED-SRC", "CP-CHAIN-PALLETIZE-RECV")
    if fix["compatible"]:
        print("  RAISED->PALLETIZE: COMPAT (WRONG -- raised cube has no support on the flat pick surface, falls)")
        fails.append("RAISED-SRC@0.975 -> PALLETIZE-RECV@0.825 should be INCOMPAT (fixed-height Δ0.15) but predicted COMPAT")
    else:
        print(f"  RAISED->PALLETIZE: INCOMPAT ok ({fix['reason'][:60]})")

    # 6: FIXED-HEIGHT applies to ALL Franka receivers, not just palletize/stack (cont.319-CHAIN10). A RAISED
    # source into a Franka FLAT receiver MUST be INCOMPAT (measured: RAISED-SRC -> franka-flat-receive 0/1, the
    # relayed cube falls from 0.975 and the receiver misses it). Distinct from #5 (palletize) — locks that the
    # height-sensitivity is robot-based (Franka fixed, UR10 adaptive), not routine-name-based.
    fr = ch.chain_compat("CP-CHAIN-FRANKA-RAISED-SRC", "CP-NEW-franka-flat-receive")
    if fr["compatible"]:
        print("  RAISED->franka-flat: COMPAT (WRONG -- Franka flat receiver is height-sensitive, cube falls)")
        fails.append("RAISED-SRC@0.975 -> franka-flat-receive@0.825 should be INCOMPAT (Δ0.15) but predicted COMPAT")
    else:
        print(f"  RAISED->franka-flat: INCOMPAT ok ({fr['reason'][:55]})")

    print(f"\n{n_pairs} proven pairs checked.")
    if fails:
        print("REGRESSION:")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"PREDICTOR FAITHFUL: {n_pairs} proven pairs COMPAT, bad case + neg-control INCOMPAT.")


if __name__ == "__main__":
    main()
