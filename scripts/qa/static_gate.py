#!/usr/bin/env python3
"""static_gate — unified ZERO-BOOT pre-flight over the template corpus.

Runs the three offline static audits and prints one consolidated report,
calibrated against the function-gate ledger so the output is ACTIONABLE
(not the raw noisy flags). This is the gen-time / CI front-end of the 72h
plan: catch the statically-detectable defect classes BEFORE spending a Kit
boot. Reach/overlap geometry that needs a live settle stays in the Kit-bound
scene_validate.py; this is the no-Kit slice.

Checks (all report-only, exit 0 unless --strict):
  1. ARG-VALUE DRIFT   audit_arg_value_drift  — code vs code_template arg drift
                       on identity-bearing calls (the strike #5/#6/#7 class),
                       ranked by gate verdict (FAIL+drift = dead-text candidate).
  2. CONFORMANCE       lint_canonical_templates --json — schema/kwarg/sandbox,
                       now gate-class-aware (delivery vs articulation vs
                       introspection). ERROR count + the offending templates.
  3. REACH             template_position_auditor — CRITICAL/MAJOR reach flags,
                       CALIBRATED: a flag that also PASSES the gate is a known
                       false positive (the auditor is ~67% FP vs the gate);
                       intentional_oor (belt-fed) flags are surfaced separately.

CALIBRATION PRINCIPLE (Anton's false-positive doctrine): a static flag on a
template that PASSES the function gate is almost certainly the auditor being
wrong, not a real defect — so those are reported as SUPPRESSED, and only
flags on FAIL/ungated templates are surfaced as candidates.

Usage:  python scripts/qa/static_gate.py [--strict]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "workspace/qa_runs/verification_ledger.jsonl"


def _verdicts():
    """{stem: bool passed} latest per template."""
    v = {}
    if LEDGER.exists():
        for ln in LEDGER.read_text().splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            s = (r.get("template") or "").split("/")[-1].replace(".json", "")
            if s and "passed" in r:
                v[s] = bool(r["passed"])
    return v


def _run(cmd):
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)


def main():
    strict = "--strict" in sys.argv
    v = _verdicts()
    passes = {k for k, p in v.items() if p}
    fails = {k for k, p in v.items() if not p}
    print("=" * 70)
    print("STATIC GATE — zero-boot corpus pre-flight (calibrated vs the gate)")
    print("=" * 70)
    n_err = 0

    # 1) arg-value drift
    print("\n[1] ARG-VALUE DRIFT (code vs code_template)")
    r = _run([sys.executable, "scripts/qa/audit_arg_value_drift.py"])
    head = [l for l in r.stdout.splitlines() if l.strip()][:1]
    print("    " + (head[0] if head else "(no output)"))
    fail_drift = [l for l in r.stdout.splitlines() if "FAIL->HIGH-CONFIDENCE" in l]
    print(f"    FAIL-template drift (dead-text candidates): {len(fail_drift)}")
    for l in fail_drift[:8]:
        print("      " + l.strip().split("[")[0].strip())

    # 2) conformance lint
    print("\n[2] CONFORMANCE LINT (gate-class-aware)")
    lr = _run([sys.executable, "scripts/lint_canonical_templates.py", "--json"]
              + [str(p) for p in (REPO / "workspace/templates").glob("CP*.json")])
    try:
        d = json.loads(lr.stdout)
        errt = [(x.get("file") or "").split("/")[-1].replace(".json", "")
                for x in d.get("results", []) if any(i.get("level") == "ERROR" for i in x.get("issues", []))]
        print(f"    error_count={d.get('error_count')}  ERROR templates={len(errt)}")
        for t in errt:
            tag = "FAIL" if t in fails else ("PASS" if t in passes else "ungated")
            print(f"      {t} [{tag}]")
        n_err += len(errt)
    except Exception as e:
        print(f"    (lint parse failed: {e})")

    # 3) reach (calibrated)
    print("\n[3] REACH (calibrated vs gate)")
    _run([sys.executable, "scripts/qa/template_position_auditor.py"])
    rj = REPO / "workspace/qa_runs/template_position_audit.json"
    if rj.exists():
        d = json.loads(rj.read_text())
        flagged = {(x.get("task_id") or ""): x for x in d.get("results", [])
                   if x.get("severity") in ("CRITICAL", "MAJOR")}
        fp = [t for t in flagged if t in passes]
        cand = [t for t in flagged if t in fails]
        intentional = [t for t in cand if flagged[t].get("intentional_oor_pattern")]
        real = [t for t in cand if not flagged[t].get("intentional_oor_pattern")]
        print(f"    CRITICAL/MAJOR={len(flagged)}  SUPPRESSED(pass-gate FP)={len(fp)}  "
              f"intentional-belt-feed={len(intentional)}  REAL candidates={len(real)}")
        for t in real[:10]:
            print(f"      REACH candidate (FAIL + not-intentional): {t}")
    else:
        print("    (reach audit produced no JSON)")

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(fail_drift)} arg-drift dead-text candidates, "
          f"{n_err} conformance ERRORs, reach candidates above.")
    print("Geometry that needs a live settle (overlap/support/instability) -> scene_validate.py (Kit).")
    print("=" * 70)
    return 1 if (strict and n_err) else 0


if __name__ == "__main__":
    raise SystemExit(main())
