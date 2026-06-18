#!/usr/bin/env python3
"""Regression: workspace/composable_blocks.json (the block catalog the composer/LLM draws from) stays consistent.

Guards three things that would silently mislead composition if they drifted:
  1. every canonical_blocks representative exists in `all` AND has a template file;
  2. every catalogued block has a template file (a 'trusted' block with no template is a broken reference);
  3. the summary roll-up MATCHES the per-block verdicts -- crucially the genuine_execution_verified vs
     position_honest_only split (a consumer reading 'trusted: 64' must not over-trust the 43 position-honest-ONLY
     blocks whose EXECUTION was never verified; that's the CP-08-grid-collapse / CP-54-jaw false-success class).
Run: python3 scripts/qa/test_composable_blocks.py
"""
import json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
F = f"{REPO}/workspace/composable_blocks.json"


def tpl_exists(cid):
    return os.path.exists(f"{REPO}/workspace/templates/{cid}.json")


def ids_in(rep):
    out = []
    for r in (rep if isinstance(rep, list) else [rep]):
        if isinstance(r, str):
            out.append(r)
        elif isinstance(r, dict):
            out += [v for v in r.values() if isinstance(v, str) and v.startswith("CP")]
    return out


def main():
    d = json.load(open(F))
    allb, cb, summ = d["all"], d["canonical_blocks"], d["summary"]
    errs = []

    # 1: canonical reps exist + have templates
    for key, rep in cb.items():
        for cid in ids_in(rep):
            if cid not in allb:
                errs.append(f"canonical {key} -> {cid} not in `all`")
            if not tpl_exists(cid):
                errs.append(f"canonical {key} -> {cid} has no template")

    # 2: every catalogued block has a template
    for cid in allb:
        if not tpl_exists(cid):
            errs.append(f"block {cid} has no template file")

    # 3: summary matches per-block verdicts
    v = lambda b: b.get("verdict", "")
    genuine = sum(1 for b in allb.values() if v(b).startswith("GENUINE"))
    pos = sum(1 for b in allb.values() if "position-honest" in v(b))
    false = sum(1 for b in allb.values() if v(b).startswith("FALSE"))
    partial = sum(1 for b in allb.values() if v(b).startswith("PARTIAL"))
    checks = {
        "total": (summ.get("total"), len(allb)),
        "genuine_execution_verified": (summ.get("genuine_execution_verified"), genuine),
        "position_honest_only": (summ.get("position_honest_only"), pos),
        "trusted": (summ.get("trusted"), genuine + pos),
        "false": (summ.get("false"), false),
        "partial": (summ.get("partial"), partial),
    }
    for k, (claimed, actual) in checks.items():
        if claimed != actual:
            errs.append(f"summary.{k}={claimed} but actual={actual}")

    print(f"  blocks={len(allb)} genuine={genuine} position_honest={pos} false={false} partial={partial}")
    if errs:
        print("REGRESSION:")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    print("composable_blocks.json consistent (canonical reps + templates present, summary matches verdicts).")


if __name__ == "__main__":
    main()
