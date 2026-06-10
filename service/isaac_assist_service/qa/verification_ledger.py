"""verification_ledger — structured, queryable gate-verdict records [P0-19].

Replaces reliance on free-text ``verified_status`` prose with a machine-
readable per-template record plus an append-only run ledger, so the corpus
DoD ("N templates function-gate green") is QUERYABLE and verdict DECAY is
visible (a code change re-gates; stale claims age out via last_run_sha).

Design decisions (hard-won this run):
- The structured field is ADDITIVE: ``"verification": {"function_gate":
  {status, n, m, wilson_lower, last_run_sha, last_run_at}}`` lives alongside
  the human ``verified_status`` prose — we never destroy the historical record.
- Template writes are SURGICAL single-line text edits (insert-before-final-
  brace or regex-replace of our own line). NEVER a json round-trip: the
  corpus mixes indent styles and raw-vs-escaped unicode, and a round-trip
  reformats unrelated lines (proven twice on P0-08).
- ``n``/``m`` = passes/total runs; ``wilson_lower`` is the 95% Wilson score
  lower bound — the honest "at least this reliable" number the N-of-M
  discipline wants (project memory: single-run verdicts lie).

No Kit imports. Pure Python; unit-testable.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_FIELD_RE = re.compile(r'^[ \t]*"verification":[ \t]*\{.*\},?[ \t]*$', re.M)
_Z95 = 1.959963984540054


def wilson_lower(n_pass: int, m_total: int, z: float = _Z95) -> float:
    """95% Wilson score lower bound for n_pass successes in m_total trials.

    Returns 0.0 for m_total == 0. This is the project's honest reliability
    floor: 3/3 -> 0.438, 1/1 -> 0.207 (a single pass proves little — exactly
    the stochastic-gate lesson).
    """
    if m_total <= 0:
        return 0.0
    p = n_pass / m_total
    denom = 1.0 + z * z / m_total
    centre = p + z * z / (2 * m_total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * m_total)) / m_total)
    out = (centre - margin) / denom
    return 0.0 if out < 1e-12 else out


def read_verification(template_path: str | Path) -> Optional[Dict[str, Any]]:
    """Return the template's ``verification`` record, or None if absent."""
    data = json.loads(Path(template_path).read_text(encoding="utf-8"))
    return data.get("verification")


def _render_line(record: Dict[str, Any], trailing_comma: bool) -> str:
    return ('  "verification": ' + json.dumps(record, ensure_ascii=True)
            + ("," if trailing_comma else ""))


def write_verification(template_path: str | Path, record: Dict[str, Any]) -> None:
    """Surgically write/replace the single-line ``verification`` field.

    If the field exists (written by us — always single-line) it is replaced
    in place; otherwise it is inserted immediately before the final closing
    brace. The rest of the file is byte-untouched.
    """
    p = Path(template_path)
    raw = p.read_text(encoding="utf-8")
    json.loads(raw)  # refuse to touch a broken file

    m_field = _FIELD_RE.search(raw)
    if m_field:
        had_comma = m_field.group(0).rstrip().endswith(",")
        new = (raw[: m_field.start()]
               + _render_line(record, trailing_comma=had_comma)
               + raw[m_field.end():])
    else:
        m = re.search(r"\n\}\s*$", raw)
        if not m:
            raise ValueError(f"{p}: no final closing brace found")
        head = raw[: m.start()].rstrip()
        sep = "" if head.endswith(",") else ","
        new = head + sep + "\n" + _render_line(record, trailing_comma=False) + "\n}\n"

    json.loads(new)  # never write invalid JSON
    p.write_text(new, encoding="utf-8")


def record_gate_run(
    template_path: str | Path,
    passed: bool,
    run_sha: str,
    ledger_path: str | Path = "workspace/qa_runs/verification_ledger.jsonl",
    when: Optional[str] = None,
    extras: Optional[Dict[str, Any]] = None,
    axis: str = "function_gate",
) -> Dict[str, Any]:
    """Record one verification run under the given AXIS: update the
    template's structured record (n/m/wilson_lower/status) and append to the
    run ledger. Returns the new full record.

    ``axis`` separates the two measurement axes (P0-06 batch lesson —
    munging them made every template with one TS warning read "mixed"):
      - ``function_gate``: did it deliver? (gate_one verdict)
      - ``faithfulness``: did the run LOOK right? (scene_timeseries states)
    Other axes in the record are preserved on write, as is any
    ``legacy_claim`` carried inside the updated axis.

    ``extras`` (optional) enriches the per-RUN ledger row — not the template
    record — with training-grade context: e.g. ``verdict_vector`` (the per-cube
    classification), ``snapshot_hash``, ``gate_score``, ``kit_session_age_s``.
    The session-age tag makes Kit-degradation-poisoned rows distrustable; the
    typed verdict vector is what future verdict->fix dispatch trains on
    (typed verdicts beat raw logs for LLM repair)."""
    when = when or datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = read_verification(template_path) or {}
    ax = record.get(axis) or {}
    n = int(ax.get("n", 0)) + (1 if passed else 0)
    m = int(ax.get("m", 0)) + 1
    new_ax: Dict[str, Any] = {
        "status": "pass" if n == m else ("fail" if n == 0 else "mixed"),
        "n": n,
        "m": m,
        "wilson_lower": round(wilson_lower(n, m), 4),
        "last_run_sha": run_sha,
        "last_run_at": when,
    }
    if "legacy_claim" in ax:  # backfill provenance survives measurement
        new_ax["legacy_claim"] = ax["legacy_claim"]
    record[axis] = new_ax
    write_verification(template_path, record)

    lp = Path(ledger_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    row: Dict[str, Any] = {
        "ts": when, "template": str(template_path), "passed": passed,
        "sha": run_sha, "n": n, "m": m, "axis": axis,
        "wilson_lower": new_ax["wilson_lower"],
    }
    if extras:
        for k, v in extras.items():
            row.setdefault(k, v)  # extras never overwrite core fields
    with lp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return record


def corpus_summary(templates_dir: str | Path = "workspace/templates") -> Dict[str, Any]:
    """The queryable DoD: counts by structured status across the corpus,
    per measurement axis (delivery vs faithfulness, never munged)."""
    counts: Dict[str, int] = {"pass": 0, "mixed": 0, "fail": 0, "unmeasured": 0}
    faith: Dict[str, int] = {"pass": 0, "mixed": 0, "fail": 0, "unmeasured": 0}
    stale: list = []
    for f in sorted(Path(templates_dir).glob("CP*.json")):
        if ".bak" in f.name or ".pre_" in f.name:
            continue
        try:
            rec = read_verification(f)
        except Exception:
            continue
        rec = rec or {}
        for axis, bucket in (("function_gate", counts), ("faithfulness", faith)):
            ax = rec.get(axis)
            status = (ax or {}).get("status", "unmeasured")
            bucket[status] = bucket.get(status, 0) + 1
    return {"counts": counts, "faithfulness_counts": faith, "stale": stale}


def rebuild_from_ledger(
    ledger_path: str | Path = "workspace/qa_runs/verification_ledger.jsonl",
    templates_dir: str | Path = "workspace/templates",
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Recompute every mentioned template's verification record FROM the run
    ledger (the ledger is the source of truth; template records are a cache).

    Axis per row: explicit ``axis`` field when present; else inferred from
    ``source`` (``nofm_scene_timeseries`` → faithfulness, everything else →
    function_gate — matches every writer that existed before the axis split).
    Used once to un-munge the 2026-06-10 batch records and available for any
    future re-derivation. Returns {template: record}.
    """
    lp = Path(ledger_path)
    if not lp.exists():
        return {}
    tallies: Dict[str, Dict[str, list]] = {}
    skipped_lines = 0
    for line in lp.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            # a torn line (crash mid-append) must never brick the whole
            # rebuild (QA-audit fynd 5) — skip and surface the count
            skipped_lines += 1
            continue
        axis = row.get("axis") or (
            "faithfulness" if row.get("source") == "nofm_scene_timeseries"
            else "function_gate")
        # Writers log both absolute and repo-relative paths for the same
        # template — normalize to the resolved path or their runs land in
        # separate tallies and the last write wins.
        tp_key = Path(row["template"])
        if not tp_key.is_absolute():
            # anchor on the REPO (this file lives in service/<pkg>/qa/), not
            # the CWD — relative rows silently dropped when run from the
            # wrong directory (QA-audit fynd 7). repo_root injectable for tests.
            repo = repo_root or Path(__file__).resolve().parents[3]
            tp_key = Path(repo) / row["template"]
        t = tallies.setdefault(str(tp_key.resolve()), {})
        t.setdefault(axis, []).append(row)
    out: Dict[str, Any] = {}
    for template, axes in tallies.items():
        tp = Path(template)
        if not tp.exists():
            continue
        record = read_verification(tp) or {}
        for axis, rows in axes.items():
            n = sum(1 for r in rows if r.get("passed"))
            m = len(rows)
            last = rows[-1]
            prev = record.get(axis) or {}
            new_ax: Dict[str, Any] = {
                "status": "pass" if n == m else ("fail" if n == 0 else "mixed"),
                "n": n,
                "m": m,
                "wilson_lower": round(wilson_lower(n, m), 4),
                "last_run_sha": last.get("sha"),
                "last_run_at": last.get("ts"),
            }
            if "legacy_claim" in prev:
                new_ax["legacy_claim"] = prev["legacy_claim"]
            record[axis] = new_ax
        write_verification(tp, record)
        out[str(tp)] = record
    if skipped_lines:
        out["_skipped_ledger_lines"] = skipped_lines
    return out
