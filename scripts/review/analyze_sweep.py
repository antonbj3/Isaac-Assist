"""Analyze a scene_observer JSONL sweep and produce review-ready markdown
for Anton's visual review pass.

Per template: status, virtual_eyes patterns + narrative, ctrl_state root-cause
hints, predicted-vs-actual after manual review.

Usage:
    python scripts/review/analyze_sweep.py <jsonl_path> [--out OUT]
"""
import argparse, json, sys
from collections import Counter
from pathlib import Path

ROOT_CAUSE_RULES = [
    # (hypothesis, predicate) — first match wins
    ("planning_unreachable", lambda r: (r.get('ctrl_state') or {}).get('ctrl:plan_calls', 0) and
        ((r.get('ctrl_state') or {}).get('ctrl:plan_fails', 0) / max(1, (r.get('ctrl_state') or {}).get('ctrl:plan_calls', 0))) > 0.30),
    ("curobo_off_target_pose", lambda r: (r.get('ctrl_state') or {}).get('ctrl:curobo_pos_err_last', 0) and
        float((r.get('ctrl_state') or {}).get('ctrl:curobo_pos_err_last', 0)) > 0.03),
    ("phase_stuck_wait_sensor", lambda r: (r.get('ctrl_state') or {}).get('ctrl:phase') == 'wait_sensor'
        and (r.get('ctrl_state') or {}).get('ctrl:cubes_delivered', 0) == 0),
    ("fj_attach_path_error", lambda r: 'FJ_FAIL' in str((r.get('ctrl_state') or {}).get('ctrl:last_error', ''))
        or 'name' in str((r.get('ctrl_state') or {}).get('ctrl:last_error', '')).lower() and 'defined' in str((r.get('ctrl_state') or {}).get('ctrl:last_error', '')).lower()),
    ("controller_pipeline_silent_fail", lambda r: (r.get('ctrl_state') or {}).get('ctrl:plan_calls', 0) > 3
        and (r.get('ctrl_state') or {}).get('ctrl:plan_fails', 0) == 0
        and (r.get('ctrl_state') or {}).get('ctrl:cubes_delivered', 0) == 0),
]


def diagnose(rec):
    """Return list of root-cause hypothesis labels matching this record."""
    # Normalize ctrl_state into top-level for easier rule access
    cs = rec.get('engine_data', {}).get('ctrl_state') or {}
    # Strip path prefix on multi-robot keys (e.g. "/World/Franka::ctrl:phase" -> "ctrl:phase")
    norm = {}
    for k, v in cs.items():
        if '::ctrl:' in k:
            norm[k.split('::', 1)[1]] = v
        elif k.startswith('ctrl:'):
            norm[k] = v
    proxy = {'ctrl_state': norm}
    hits = []
    for label, pred in ROOT_CAUSE_RULES:
        try:
            if pred(proxy): hits.append(label)
        except Exception: pass
    return hits


def fmt_pct(n, d):
    return f"{int(n)}/{int(d)} ({100*n/d:.0f}%)" if d else f"{int(n)}/0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if not args.jsonl.exists():
        sys.exit(f"not found: {args.jsonl}")
    out = args.out or args.jsonl.with_suffix('.review.md')

    recs = []
    for line in args.jsonl.read_text().splitlines():
        if not line.strip(): continue
        try: recs.append(json.loads(line))
        except: pass

    if not recs:
        sys.exit("empty input")

    n = len(recs)
    n_pass = sum(1 for r in recs if r.get('honest_pass'))
    n_exc = sum(1 for r in recs if r.get('exception'))

    # Aggregate patterns
    pattern_counts = Counter()
    rootcause_counts = Counter()
    for r in recs:
        ve = r.get('virtual_eyes') or {}
        for n_p, p in (ve.get('patterns') or {}).items():
            if p.get('detected'):
                pattern_counts[n_p] += 1
        for rc in diagnose(r):
            rootcause_counts[rc] += 1

    lines = [
        f"# Sweep review — {args.jsonl.name}",
        "",
        f"**Templates:** {n} | **HONEST_PASS:** {fmt_pct(n_pass, n)} | **Exceptions:** {fmt_pct(n_exc, n)}",
        "",
        "## Root-cause hypothesis (aggregated)",
        "",
    ]
    for label, count in rootcause_counts.most_common():
        lines.append(f"- **{label}**: {fmt_pct(count, n)}")
    if not rootcause_counts:
        lines.append("- (no root-cause rule matched — all PASS or signals missing)")

    lines.extend([
        "",
        "## Pattern frequency (Virtual Eyes detectors)",
        "",
    ])
    for label, count in pattern_counts.most_common(15):
        lines.append(f"- `{label}`: {count}")
    if not pattern_counts:
        lines.append("- (no patterns triggered)")

    lines.extend(["", "## Per-template", ""])

    for r in sorted(recs, key=lambda x: x.get('template', '?')):
        name = r.get('template', '?')
        verdict = "✅ HONEST_PASS" if r.get('honest_pass') else "❌ FAIL"
        exc = r.get('exception')
        ve = r.get('virtual_eyes') or {}
        patterns = [n for n, p in (ve.get('patterns') or {}).items() if p.get('detected')]
        narrative = ve.get('narrative', '—')
        cs = (r.get('engine_data') or {}).get('ctrl_state') or {}
        # Pull key signals (handle multi-robot prefix)
        def _get(k):
            for kk, v in cs.items():
                if kk == k or kk.endswith('::' + k): return v
            return None
        plan_c = _get('ctrl:plan_calls')
        plan_f = _get('ctrl:plan_fails')
        delivered = _get('ctrl:cubes_delivered')
        pos_err = _get('ctrl:curobo_pos_err_last')
        last_err = _get('ctrl:last_error')
        phase = _get('ctrl:phase')
        rcs = diagnose(r)
        elapsed = r.get('elapsed_s', '?')

        lines.append(f"### {name} — {verdict} ({elapsed}s)")
        if exc:
            lines.append(f"- **exception**: `{exc}`")
        lines.append(f"- **patterns**: {', '.join(patterns) if patterns else '∅'}")
        lines.append(f"- **narrative**: _{narrative}_")
        if rcs:
            lines.append(f"- **root-cause hypothesis**: {', '.join(f'`{x}`' for x in rcs)}")
        if plan_c is not None or plan_f is not None or delivered is not None:
            lines.append(f"- **ctrl**: plan_calls={plan_c} plan_fails={plan_f} delivered={delivered} phase={phase}")
        if pos_err is not None:
            try:
                lines.append(f"- **curobo_pos_err_last**: {float(pos_err):.4f}m")
            except Exception: pass
        if last_err and last_err != "":
            lines.append(f"- **last_error**: `{str(last_err)[:120]}`")
        lines.append("")

    out.write_text("\n".join(lines))
    print(f"Wrote {out}")
    print(f"  {n} templates | {n_pass} pass | {n_exc} exception")
    print(f"  Top root-causes: {dict(rootcause_counts.most_common(3))}")


if __name__ == "__main__":
    main()
