#!/usr/bin/env python3
"""tier1_triage.py — bucket the tier-1 (role-based + cuRobo, not-yet-verified)
templates by READINESS, so gate runs target the tractable ones and skip hidden
CAT-A research problems.

Buckets (priority order):
  ALREADY   verified_status already says VERIFIED/DELIVERED/N/N (done — just field
            hygiene; motion_controllers.verified likely stale). DON'T re-run.
  READY     form-gate ✓ / schema ✓ AND function-gate pending -> just needs a Kit
            gate run. HIGHEST yield for "drive to verified".
  SMOKE     smoke-test ✓ 1/1 but no function-gate -> builds+runs once; promising.
  CATA      vision/grip research-hard (bin-pick, 3finger, 6dof, conveyor-tracking,
            peg, tactile, snap-fit, wire-harness, welder, impedance). PARK.
  LINT      form-gate still pending lint/schema -> needs a form pass before gate.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composability_scan import classify, TPL_DIR  # noqa: E402
import json  # noqa: E402

CATA_KW = ("bin-picking", "3finger", "6dof", "conveyor-tracking", "moving-conveyor",
           "peg", "tactile", "snap-fit", "wire-harness", "welder", "impedance",
           "bottle-cap", "turn-faucet", "oxe-sweep", "sponge", "robohive")


def bucket(tid: str, vs: str) -> str:
    low = vs.lower()
    t = tid.lower()
    if any(k in low for k in ("verified", "delivered", "n/n")) or \
       any(f"{n}/{n}" in vs for n in range(2, 13)):
        return "ALREADY"
    if any(k in t for k in CATA_KW):
        return "CATA"
    formgate_ok = ("form-gate ✓" in low) or ("form-gate-schema ✓" in low) or \
                  ("form-gate-schema: ✓" in low)
    func_pending = ("function-gate ⏳" in low) or ("function-gate pending" in low) or \
                   ("function-gate ✓" not in low and "function-gate" in low)
    if formgate_ok and func_pending:
        return "READY"
    if "smoke-test ✓" in low:
        return "SMOKE"
    if "pending lint" in low or "pending-lint" in low or "schema pending" in low or \
       "form-gate-schema ⏳" in low or "form-gate pending" in low:
        return "LINT"
    return "OTHER"


def main():
    rows = []
    for p in sorted(TPL_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        r = classify(d)
        if r["tier"] != 1:
            continue
        r["bucket"] = bucket(r["task_id"], r["vs"])
        r["file"] = p.name
        rows.append(r)

    order = ["READY", "SMOKE", "ALREADY", "LINT", "CATA", "OTHER"]
    from collections import Counter
    print(f"=== {len(rows)} tier-1 templates ===")
    print("BUCKETS:", dict(Counter(r["bucket"] for r in rows)))
    for b in order:
        items = [r for r in rows if r["bucket"] == b]
        if not items:
            continue
        print(f"\n--- {b} ({len(items)}) ---")
        for r in sorted(items, key=lambda r: r["task_id"]):
            print(f"  {r['primitive']:12} {r['task_id']:40} {r['vs']}")


if __name__ == "__main__":
    main()
