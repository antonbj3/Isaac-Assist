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
) -> Dict[str, Any]:
    """Record one function-gate run: update the template's structured record
    (n/m/wilson_lower/status) and append to the run ledger. Returns the new
    record.

    ``extras`` (optional) enriches the per-RUN ledger row — not the template
    record — with training-grade context: e.g. ``verdict_vector`` (the per-cube
    classification), ``snapshot_hash``, ``gate_score``, ``kit_session_age_s``.
    The session-age tag makes Kit-degradation-poisoned rows distrustable; the
    typed verdict vector is what future verdict->fix dispatch trains on
    (typed verdicts beat raw logs for LLM repair)."""
    when = when or datetime.now(timezone.utc).isoformat(timespec="seconds")
    existing = read_verification(template_path) or {}
    fg = existing.get("function_gate") or {}
    n = int(fg.get("n", 0)) + (1 if passed else 0)
    m = int(fg.get("m", 0)) + 1
    record = {
        "function_gate": {
            "status": "pass" if n == m else ("fail" if n == 0 else "mixed"),
            "n": n,
            "m": m,
            "wilson_lower": round(wilson_lower(n, m), 4),
            "last_run_sha": run_sha,
            "last_run_at": when,
        }
    }
    write_verification(template_path, record)

    lp = Path(ledger_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    row: Dict[str, Any] = {
        "ts": when, "template": str(template_path), "passed": passed,
        "sha": run_sha, "n": n, "m": m,
        "wilson_lower": record["function_gate"]["wilson_lower"],
    }
    if extras:
        for k, v in extras.items():
            row.setdefault(k, v)  # extras never overwrite core fields
    with lp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return record


def corpus_summary(templates_dir: str | Path = "workspace/templates") -> Dict[str, Any]:
    """The queryable DoD: counts by structured status across the corpus."""
    counts: Dict[str, int] = {"pass": 0, "mixed": 0, "fail": 0, "unmeasured": 0}
    stale: list = []
    for f in sorted(Path(templates_dir).glob("CP*.json")):
        if ".bak" in f.name or ".pre_" in f.name:
            continue
        try:
            rec = read_verification(f)
        except Exception:
            continue
        if not rec or "function_gate" not in rec:
            counts["unmeasured"] += 1
            continue
        fg = rec["function_gate"]
        counts[fg.get("status", "unmeasured")] = counts.get(fg.get("status", "unmeasured"), 0) + 1
    return {"counts": counts, "stale": stale}
