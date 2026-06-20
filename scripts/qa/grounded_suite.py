#!/usr/bin/env python3
"""grounded_suite.py (cont.319eee) — one-command regression gate for the grounded special-order harness.

Runs every grounded-reasoning check (all pure Python, no LLM/Kit/ChromaDB) so the harness has a single durable gate
instead of scattered scripts:
    grounded_feasibility._selftest   — the gripper/reach/payload/flow rules
    grounded_battery                 — 32 labelled adversarial orders (precision/recall, false-pass/false-block)
    grounded_clarifier               — vague-order variable-capture (ask exactly what's needed)
    grounded_harness                 — the ASK/BUILD/EXPLAIN decision skeleton (smoke: runs the demo, asserts shape)
Exit non-zero if any sub-check fails.
"""
import sys, os, subprocess
HERE = os.path.dirname(__file__)


def _run(mod):
    r = subprocess.run([sys.executable, os.path.join(HERE, mod)], capture_output=True, text=True)
    ok = r.returncode == 0
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    print(f"[{'PASS' if ok else 'FAIL'}] {mod:28} {tail[:80]}")
    if not ok:
        print(r.stdout[-600:]); print(r.stderr[-400:])
    return ok


def _harness_smoke():
    sys.path.insert(0, HERE)
    from grounded_harness import ground_order
    a = ground_order({"object": {}})["action"]
    b = ground_order({"robot": "franka", "gripper": "parallel_jaw",
                      "object": {"material": "plastic", "surface": "smooth-dry", "mass_kg": 0.4, "width_m": 0.06},
                      "targets": [(0.4, 0, 0.85)]})["action"]
    c = ground_order({"robot": "ur10", "gripper": "vacuum_suction",
                      "object": {"material": "steel", "shape": "cylinder", "surface": "smooth-wet", "mass_kg": 2.0, "width_m": 0.07},
                      "targets": [(0.6, 0, 0.9)]})["action"]
    ok = (a, b, c) == ("ASK", "BUILD", "EXPLAIN")
    print(f"[{'PASS' if ok else 'FAIL'}] grounded_harness (smoke)      ASK/BUILD/EXPLAIN = {a}/{b}/{c}")
    return ok


if __name__ == "__main__":
    print("=== grounded special-order harness — regression suite ===")
    results = [
        _run("grounded_feasibility.py"),
        _run("grounded_battery.py"),
        _run("grounded_clarifier.py"),
        _harness_smoke(),
    ]
    n = sum(results)
    print(f"\n=== {n}/{len(results)} grounded checks PASS ===")
    sys.exit(0 if n == len(results) else 1)
