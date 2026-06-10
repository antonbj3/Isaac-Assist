#!/usr/bin/env python3
"""tier2_reach_probe — N-of-M aggregated reach probe [P1-09].

The dual-verify PROBE_REACH action: when static_eyes returns reach=UNCERTAIN
(the non-convex straight-down floor), run the live cuRobo single-IK probe
(reach_validate.py, Kit + cuRobo, NO physics settle) N times and aggregate —
the probe is STOCHASTIC (Halton seeds flip single runs; reach_validate.py:12-18),
so a single run is not a verdict.

Aggregation per target (honest, not majority-vote-optimistic):
  REACHABLE   — reachable in ALL m runs
  MARGINAL    — mixed results (the flip zone — treat as needs-gate)
  UNREACHABLE — reachable in 0 runs
Plus n/m + Wilson lower bound via verification_ledger.wilson_lower.

REACHABLE stays necessary-NOT-sufficient (CP-81 probed REACHABLE yet the
gate failed) — this probe REJECTS cheaply and ranks; it never green-lights
past the function gate.

Usage:
    python3 scripts/qa/tier2_reach_probe.py CP-70 [CP-83 ...] [--runs 3]
Kit must be up on 127.0.0.1:8001. Runs are SERIAL (Kit single-tenant).
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _wilson(n: int, m: int, z: float = 1.959963984540054) -> float:
    if m <= 0:
        return 0.0
    p = n / m
    denom = 1 + z * z / m
    centre = p + z * z / (2 * m)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * m)) / m)
    out = (centre - margin) / denom
    return 0.0 if out < 1e-12 else out


def run_probe(names: list[str], runs: int = 3) -> dict:
    """Run reach_validate `runs` times (serial) and aggregate per target."""
    per_target: dict = defaultdict(lambda: {"reachable": 0, "runs": 0, "verdicts": []})
    raw_reports = []
    for i in range(runs):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/qa/reach_validate.py"), *names],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise RuntimeError(f"reach_validate run {i+1} failed: {proc.stderr[-400:]}")
        # reach_validate prints a JSON list of per-template reports (last JSON blob on stdout)
        out = proc.stdout
        start = out.find("[")
        reports = json.loads(out[start:]) if start >= 0 else []
        raw_reports.append(reports)
        for rep in reports:
            tname = rep.get("template", names[0] if len(names) == 1 else "?")
            for t in rep.get("targets", []):
                key = (tname, t.get("path", "?"))
                per_target[key]["runs"] += 1
                per_target[key]["verdicts"].append(t.get("verdict"))
                if t.get("verdict") == "REACHABLE":
                    per_target[key]["reachable"] += 1

    results = []
    for (tname, path), agg in sorted(per_target.items()):
        n, m = agg["reachable"], agg["runs"]
        verdict = ("REACHABLE" if n == m and m > 0
                   else "UNREACHABLE" if n == 0
                   else "MARGINAL")
        results.append({
            "template": tname, "target": path,
            "verdict": verdict, "n": n, "m": m,
            "wilson_lower": round(_wilson(n, m), 4),
            "runs": agg["verdicts"],
        })
    return {
        "targets": results,
        "caveat": "REACHABLE is necessary-not-sufficient; MARGINAL/borderline must be gate-verified",
        "n_runs": runs,
    }


def main() -> int:
    args = sys.argv[1:]
    runs = 3
    if "--runs" in args:
        idx = args.index("--runs")
        runs = int(args[idx + 1])
        del args[idx:idx + 2]
    names = [a for a in args if not a.startswith("--")]
    if not names:
        print(__doc__)
        return 2
    out = run_probe(names, runs=runs)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
