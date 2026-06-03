"""
Analyze function_gate_2026-05-18.jsonl and emit the baseline report.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS = REPO_ROOT / "workspace/qa_runs/function_gate_2026-05-18.jsonl"
SMOKE = REPO_ROOT / "workspace/qa_runs/function_gate_2026-05-18_smoke.jsonl"
SCOPE = REPO_ROOT / "workspace/qa_runs/function_gate_2026-05-18_scope.json"
REPORT = REPO_ROOT / "docs/research/2026-05-18-function-gate-baseline.md"


def main() -> None:
    rows = []
    if RESULTS.exists():
        for line in RESULTS.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if SMOKE.exists():
        for line in SMOKE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                # CP-01 smoke counted as new evidence
                rows.append(row)
            except Exception:
                pass

    # Deduplicate by name (latest wins)
    by_name = {}
    for r in rows:
        by_name[r["name"]] = r
    rows = list(by_name.values())
    rows.sort(key=lambda r: r["name"])

    scope = json.loads(SCOPE.read_text())
    eligible = scope["eligible"]
    scope_by_name = {e["name"]: e for e in eligible}

    n_total = len(rows)
    n_build_ok = sum(1 for r in rows if r.get("build_ok"))
    n_build_fail = sum(1 for r in rows if not r.get("build_ok") and r.get("function_gate_verdict") == "BUILD_FAILED")
    n_fg_pass = sum(1 for r in rows if r.get("function_gate_verdict") == "PASS")
    n_fg_fail = sum(1 for r in rows if r.get("function_gate_verdict") == "FAIL")
    n_exc = sum(1 for r in rows if r.get("function_gate_verdict") in {"EXC", "OUTER_EXC", "LOAD_FAILED", "NO_JSON"})

    # New vs grandfathered
    new_pass = []
    new_fail = []
    new_build_fail = []
    new_exc = []
    grandfather_pass = []
    grandfather_fail = []  # regressions
    grandfather_build_fail = []

    for r in rows:
        sp = scope_by_name.get(r["name"])
        if not sp:
            continue
        had = bool(sp.get("had_function_gate_pass"))
        verdict = r.get("function_gate_verdict")
        if had:
            if verdict == "PASS":
                grandfather_pass.append(r)
            elif verdict == "FAIL":
                grandfather_fail.append(r)
            elif verdict == "BUILD_FAILED":
                grandfather_build_fail.append(r)
        else:
            if verdict == "PASS":
                new_pass.append(r)
            elif verdict == "FAIL":
                new_fail.append(r)
            elif verdict == "BUILD_FAILED":
                new_build_fail.append(r)
            elif verdict in {"EXC", "OUTER_EXC", "NO_JSON", "LOAD_FAILED"}:
                new_exc.append(r)

    # Failure-mode taxonomy for build-pass + function-fail
    fail_modes = defaultdict(list)
    for r in new_fail + grandfather_fail:
        if not r.get("function_gate_ran"):
            continue
        in_xy = r.get("in_target_xy")
        above = r.get("above_floor")
        at_rest = r.get("at_rest")
        speed = r.get("cube_speed")
        ci = r.get("cube_initial")
        cf = r.get("cube_final")
        if ci and cf:
            moved = ((ci[0]-cf[0])**2 + (ci[1]-cf[1])**2 + (ci[2]-cf[2])**2) ** 0.5
        else:
            moved = None

        if moved is not None and moved < 0.02:
            cat = "cube_didnt_move"
        elif in_xy is False and above is True:
            cat = "wrong_xy_landed_elsewhere"
        elif above is False:
            cat = "fell_below_floor"
        elif at_rest is False:
            cat = "not_at_rest_at_timeout"
        else:
            cat = "other"
        fail_modes[cat].append({
            "name": r["name"], "in_xy": in_xy, "above_floor": above,
            "at_rest": at_rest, "speed": speed, "moved": round(moved or -1, 3),
            "cube_initial": ci, "cube_final": cf,
        })

    # ---------- Console summary ----------
    print(f"\n=== Function-Gate Sweep 2026-05-18 ===")
    print(f"Templates processed: {n_total}")
    print(f"  build_ok: {n_build_ok}  build_fail: {n_build_fail}  exc: {n_exc}")
    print(f"  function-gate PASS: {n_fg_pass}")
    print(f"  function-gate FAIL: {n_fg_fail}")
    print()
    print(f"New verified pre→post: {len(new_pass)} pass / {len(new_fail)} fail / {len(new_build_fail)} build-fail / {len(new_exc)} exc")
    print(f"Grandfather sample:    {len(grandfather_pass)} pass / {len(grandfather_fail)} fail (regressions) / {len(grandfather_build_fail)} build-fail")
    print()
    print(f"Failure-mode breakdown:")
    for cat, lst in sorted(fail_modes.items(), key=lambda x: -len(x[1])):
        print(f"  {cat}: {len(lst)}")

    # ---------- Build the markdown report ----------
    REPORT.parent.mkdir(exist_ok=True, parents=True)
    lines = []
    lines.append("# Function-Gate Baseline — 2026-05-18")
    lines.append("")
    lines.append("Sweep run after pre-sweep success-criteria fixes (commits 41f910f8, f2ffcbcb, be169a5c, 807316f6, 9b9dba63).")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    summ = scope.get("summary", {})
    lines.append(f"- Eligible templates (delivery-pattern + valid simulate_args + not sentinel + not env_blocked): **{summ.get('eligible_count')}**")
    lines.append(f"- By pattern_hint: {summ.get('by_pattern')}")
    lines.append(f"  - {summ.get('inferred_count')} of these had pattern inferred from goal text (empty intent.pattern_hint, but pick_place/sort/etc clearly described)")
    lines.append(f"- Skipped: {summ.get('skipped_count')}")
    skip_reasons = summ.get("skip_reasons", {})
    for k, v in skip_reasons.items():
        lines.append(f"  - {k}: {v}")
    lines.append("")
    lines.append("**Skipped categories**:")
    lines.append("- 14 `is_self_consistent:false` sentinels — invalid by audit")
    lines.append("- 11 `verified_status` contains `env_blocked:` — permanent-env-blocked")
    lines.append("- 86 pattern_hint not in {pick_place, sort, reorient, navigate} (mostly `other`, `train`, `insert`)")
    lines.append("- 1 missing simulate_args")
    lines.append("")
    lines.append("## Sweep configuration")
    lines.append("")
    lines.append("- `--skip-already-passing`: only run the **50 not-yet-verified** templates from the eligible 121")
    lines.append("- `--grandfather-sample 10`: random sample of 10 already-passing templates to verify no regression")
    lines.append("- `--cap-duration 120`: cap simulate_traversal_check duration_s at 120s (templates with 180s/240s/300s capped)")
    lines.append("- Sequential execution (Kit RPC is single-tenant)")
    lines.append("- Result log: `workspace/qa_runs/function_gate_2026-05-18.jsonl`")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| Templates processed | {n_total} |")
    lines.append(f"| build_ok | {n_build_ok} |")
    lines.append(f"| build_fail | {n_build_fail} |")
    lines.append(f"| function-gate PASS | {n_fg_pass} |")
    lines.append(f"| function-gate FAIL | {n_fg_fail} |")
    lines.append(f"| Exceptions | {n_exc} |")
    lines.append("")
    lines.append("### New verifications (50 not-yet-passing templates)")
    lines.append("")
    lines.append(f"- **Newly PASS**: {len(new_pass)}")
    lines.append(f"- FAIL (build-pass, function-fail): {len(new_fail)}")
    lines.append(f"- BUILD_FAILED: {len(new_build_fail)}")
    lines.append(f"- Exception: {len(new_exc)}")
    lines.append("")
    if new_pass:
        lines.append("**Newly verified stable_ok:**")
        for r in sorted(new_pass, key=lambda x: x["name"]):
            lines.append(f"- `{r['name']}` (pattern={r.get('pattern')}, dur={r.get('duration_s_used')}s, cube_final={r.get('cube_final')})")
        lines.append("")
    if new_fail:
        lines.append("**Build-pass + function-fail (physics-tuning candidates):**")
        for r in sorted(new_fail, key=lambda x: x["name"]):
            lines.append(f"- `{r['name']}` in_xy={r.get('in_target_xy')} above={r.get('above_floor')} at_rest={r.get('at_rest')} speed={r.get('cube_speed')} moved? init={r.get('cube_initial')} final={r.get('cube_final')}")
        lines.append("")
    if new_build_fail:
        lines.append("**BUILD_FAILED:**")
        for r in sorted(new_build_fail, key=lambda x: x["name"]):
            errs = r.get("build_errors", [])
            err_short = (errs[0] if errs else {"error": "n/a"})
            if isinstance(err_short, dict):
                err_text = err_short.get("error") or err_short.get("output") or str(err_short)[:140]
            else:
                err_text = str(err_short)[:140]
            lines.append(f"- `{r['name']}` ({r.get('build_n_ok')}/{r.get('build_n_calls')} calls): {err_text}")
        lines.append("")
    if new_exc:
        lines.append("**Exceptions:**")
        for r in sorted(new_exc, key=lambda x: x["name"]):
            lines.append(f"- `{r['name']}` {r.get('exception')}")
        lines.append("")
    lines.append("### Grandfather sample (10 random previously-passing templates)")
    lines.append("")
    lines.append(f"- Still PASS: {len(grandfather_pass)}/{len(grandfather_pass)+len(grandfather_fail)+len(grandfather_build_fail)}")
    if grandfather_fail:
        lines.append(f"- **REGRESSED** (had function-gate ✓, now fails):")
        for r in sorted(grandfather_fail, key=lambda x: x["name"]):
            lines.append(f"  - `{r['name']}` in_xy={r.get('in_target_xy')} above={r.get('above_floor')} at_rest={r.get('at_rest')}")
    if grandfather_build_fail:
        lines.append(f"- Build-failed (regression on build side):")
        for r in grandfather_build_fail:
            lines.append(f"  - `{r['name']}`")
    lines.append("")
    lines.append("### Failure-mode taxonomy (build-pass + function-fail)")
    lines.append("")
    for cat, lst in sorted(fail_modes.items(), key=lambda x: -len(x[1])):
        lines.append(f"- **{cat}** ({len(lst)} templates):")
        for r in sorted(lst, key=lambda x: x["name"])[:20]:
            lines.append(f"  - `{r['name']}` speed={r['speed']} moved={r['moved']}m in_xy={r['in_xy']} above_floor={r['above_floor']}")
    lines.append("")
    lines.append("## Total stable_ok post-sweep")
    lines.append("")
    pre_existing_grandfathered = len([e for e in eligible if e.get("had_function_gate_pass")])
    new_pass_count = len(new_pass)
    lines.append(f"- Pre-sweep grandfathered function-gate ✓: **{pre_existing_grandfathered}** (across full eligible scope of {len(eligible)})")
    lines.append(f"- Newly verified by this sweep: **{new_pass_count}**")
    lines.append(f"- Total verified function-gate ✓ in delivery-pattern scope: **{pre_existing_grandfathered + new_pass_count}/{len(eligible)}** "
                 f"({100*(pre_existing_grandfathered + new_pass_count)/len(eligible):.1f}%)")
    lines.append("")
    lines.append(f"Historical reference: 49 stable_ok grandfathered cited in feedback `project_isaac_assist_phase_b_state.md` and `project_isaac_assist_session_end_2026_05_09.md`. Today's grandfather sample of {len(grandfather_pass + grandfather_fail + grandfather_build_fail)} from those 49 shows {len(grandfather_pass)} still passing.")
    lines.append("")
    lines.append("## Recommendation for Wave 2 (sentinel-template redesign)")
    lines.append("")
    # Priority assessment
    n_fail_total = len(new_fail) + len(new_build_fail) + len(new_exc)
    redesign_priority_count = 14  # sentinel count from scope
    lines.append(f"- 14 `is_self_consistent:false` sentinel templates need redesign — they were excluded from this sweep because the audit flagged them as invalid.")
    lines.append(f"- Of the 50 not-yet-passing eligible: **{n_fail_total} still don't deliver** (build_fail + function_fail + exc).")
    failure_categories = sorted(fail_modes.items(), key=lambda x: -len(x[1]))
    if failure_categories:
        top_cat, top_list = failure_categories[0]
        lines.append(f"- Top failure mode: `{top_cat}` ({len(top_list)} templates) — physics-tuning lever candidate")
    lines.append("")
    lines.append("**Wave 2 priority order:**")
    lines.append("1. **14 sentinel templates** — redesign or convert to negative-test cases (highest priority; explicitly flagged invalid by pre-sweep audit)")
    lines.append("2. **`cube_didnt_move` cluster** — controller not picking; possibly missing pickup-handler wire, gripper mismatch, or reach issue")
    lines.append("3. **`wrong_xy_landed_elsewhere` cluster** — controller executes but drops at wrong destination; bin path resolution or target_path mismatch")
    lines.append("4. **`fell_below_floor` cluster** — physics-tuning (sleep threshold, collision mesh, mass)")
    lines.append("5. **Remaining build_failures** — handler API changes or template bugs")
    lines.append("")
    REPORT.write_text("\n".join(lines))
    print(f"\nReport written to {REPORT}")


if __name__ == "__main__":
    main()
