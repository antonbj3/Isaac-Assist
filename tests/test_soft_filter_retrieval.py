"""
test_soft_filter_retrieval.py
------------------------------
Unit tests for retrieve_with_intent_soft_filter (R15d).

Tests are isolated from ChromaDB by monkeypatching
retrieve_templates_with_scores and _template_cache so no real index is
needed.  Each test focuses on one aspect of the soft-filter algorithm.

Run with:
    python -m pytest tests/test_soft_filter_retrieval.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import pytest

# All tests in this file are pure-unit (no external dependencies)
pytestmark = pytest.mark.l0

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from service.isaac_assist_service.chat.tools.template_retriever import (
    retrieve_with_intent_soft_filter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(task_id: str, pattern_hint: str = "pick_place") -> Dict:
    """Minimal template fixture with an intent field."""
    return {
        "task_id": task_id,
        "goal": f"Goal for {task_id}",
        "intent": {"pattern_hint": pattern_hint, "counts": {}, "structural_features": {}},
    }


def _make_template_no_intent(task_id: str) -> Dict:
    """Minimal template fixture WITHOUT an intent field (legacy template)."""
    return {
        "task_id": task_id,
        "goal": f"Legacy goal for {task_id}",
    }


def _make_scored(task_id: str, similarity: float, template: Dict) -> Dict:
    """Minimal scored-entry dict as returned by retrieve_templates_with_scores."""
    return {
        "task_id": task_id,
        "similarity": similarity,
        "distance": 1.0 - similarity,
        "template": template,
    }


def _make_spec(pattern_hint: str = "pick_place") -> Dict:
    """Minimal spec intent dict that is NOT null-signal (has a non-default pattern_hint)."""
    return {
        "pattern_hint": pattern_hint,
        "counts": {"robots": 1},
        "structural_features": {},
        "structural_tags": [],
    }


def _make_null_spec() -> Dict:
    """Spec intent that _spec_is_null_signal returns True for."""
    return {
        "pattern_hint": "pick_place",
        "counts": {"robots": 0, "conveyors": 0, "bins": 0, "cubes": 0, "sensors": 0, "humans": 0},
        "structural_features": {
            "multi_robot": False,
            "has_conveyor": False,
            "destination_kind": "single_bin",
        },
        "structural_tags": [],
    }


# ---------------------------------------------------------------------------
# Test 1: matching pattern_hint → similarity is boosted
# ---------------------------------------------------------------------------

def test_matching_pattern_hint_gets_boosted():
    """A candidate whose intent.pattern_hint matches the spec gets similarity * boost."""
    tmpl_a = _make_template("CP-01", pattern_hint="pick_place")
    tmpl_b = _make_template("CP-02", pattern_hint="sort")

    raw_results = [
        _make_scored("CP-01", 0.70, tmpl_a),
        _make_scored("CP-02", 0.80, tmpl_b),
    ]
    spec = _make_spec(pattern_hint="pick_place")

    fake_cache = {"CP-01": tmpl_a, "CP-02": tmpl_b}

    with (
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever"
            ".retrieve_templates_with_scores",
            return_value=raw_results,
        ),
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
            fake_cache,
        ),
    ):
        results = retrieve_with_intent_soft_filter(
            spec, top_k=2, original_query="pick and place", boost=1.15, oversample=1
        )

    # CP-01 should have boost_applied=True; CP-02 should not
    cp01 = next(r for r in results if r["task_id"] == "CP-01")
    cp02 = next(r for r in results if r["task_id"] == "CP-02")

    assert cp01["boost_applied"] is True
    assert abs(cp01["similarity_boosted"] - 0.70 * 1.15) < 1e-9, (
        f"Expected {0.70 * 1.15}, got {cp01['similarity_boosted']}"
    )
    assert cp02["boost_applied"] is False
    assert abs(cp02["similarity_boosted"] - 0.80) < 1e-9, (
        f"Expected 0.80 unchanged, got {cp02['similarity_boosted']}"
    )


# ---------------------------------------------------------------------------
# Test 2: candidate WITHOUT intent field → no penalty (similarity unchanged)
# ---------------------------------------------------------------------------

def test_no_intent_field_no_penalty():
    """Legacy templates (no intent field) must not be penalized — similarity unchanged."""
    tmpl_legacy = _make_template_no_intent("M-08")

    raw_results = [_make_scored("M-08", 0.75, tmpl_legacy)]
    spec = _make_spec(pattern_hint="train")

    fake_cache = {"M-08": tmpl_legacy}

    with (
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever"
            ".retrieve_templates_with_scores",
            return_value=raw_results,
        ),
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
            fake_cache,
        ),
    ):
        results = retrieve_with_intent_soft_filter(
            spec, top_k=1, original_query="train allegro", boost=1.15, oversample=1
        )

    assert len(results) == 1
    r = results[0]
    assert r["boost_applied"] is False
    assert abs(r["similarity_boosted"] - 0.75) < 1e-9, (
        f"Legacy template should be unchanged; got {r['similarity_boosted']}"
    )
    assert r["similarity"] == 0.75


# ---------------------------------------------------------------------------
# Test 3: non-matching pattern_hint → no boost (similarity unchanged)
# ---------------------------------------------------------------------------

def test_nonmatching_pattern_hint_no_boost():
    """Candidates with a different pattern_hint get no boost and no penalty."""
    tmpl = _make_template("CP-55", pattern_hint="navigate")

    raw_results = [_make_scored("CP-55", 0.65, tmpl)]
    spec = _make_spec(pattern_hint="sort")

    fake_cache = {"CP-55": tmpl}

    with (
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever"
            ".retrieve_templates_with_scores",
            return_value=raw_results,
        ),
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
            fake_cache,
        ),
    ):
        results = retrieve_with_intent_soft_filter(
            spec, top_k=1, original_query="sort by color", boost=1.15, oversample=1
        )

    r = results[0]
    assert r["boost_applied"] is False
    assert abs(r["similarity_boosted"] - 0.65) < 1e-9


# ---------------------------------------------------------------------------
# Test 4: null-signal spec → no boost applied to anyone
# ---------------------------------------------------------------------------

def test_null_signal_spec_no_boost():
    """When spec is null-signal, no template should receive a boost."""
    tmpl_a = _make_template("CP-01", pattern_hint="pick_place")
    tmpl_b = _make_template("CP-02", pattern_hint="pick_place")

    raw_results = [
        _make_scored("CP-01", 0.80, tmpl_a),
        _make_scored("CP-02", 0.70, tmpl_b),
    ]
    spec = _make_null_spec()

    fake_cache = {"CP-01": tmpl_a, "CP-02": tmpl_b}

    with (
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever"
            ".retrieve_templates_with_scores",
            return_value=raw_results,
        ),
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
            fake_cache,
        ),
    ):
        results = retrieve_with_intent_soft_filter(
            spec, top_k=2, original_query="robot task", boost=1.15, oversample=1
        )

    for r in results:
        assert r["boost_applied"] is False, (
            f"{r['task_id']} should not be boosted for null-signal spec"
        )
        assert r["similarity_boosted"] == r["similarity"]


# ---------------------------------------------------------------------------
# Test 5: oversample parameter — fetches top_k * oversample candidates
# ---------------------------------------------------------------------------

def test_oversample_fetches_extended_set():
    """oversample=3 with top_k=3 means retrieve_templates_with_scores is called with n=9."""
    spec = _make_spec(pattern_hint="pick_place")

    call_args_holder = {}

    def fake_retrieve(query: str, top_k: int = 3, **kwargs) -> List[Dict]:
        call_args_holder["top_k"] = top_k
        # Return exactly top_k items to satisfy the slice
        return [
            _make_scored(f"CP-{i:02d}", 0.9 - i * 0.01, _make_template(f"CP-{i:02d}"))
            for i in range(top_k)
        ]

    with (
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever"
            ".retrieve_templates_with_scores",
            side_effect=fake_retrieve,
        ),
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
            {},
        ),
    ):
        retrieve_with_intent_soft_filter(
            spec, top_k=3, original_query="test", boost=1.15, oversample=3
        )

    assert call_args_holder.get("top_k") == 9, (
        f"Expected 9 (3*3), got {call_args_holder.get('top_k')}"
    )


# ---------------------------------------------------------------------------
# Test 6: re-sort order is correct after boost
# ---------------------------------------------------------------------------

def test_resort_order_after_boost():
    """After boosting, the result list should be ordered by similarity_boosted desc."""
    # CP-A: raw similarity 0.70, matching pattern → boosted to 0.70*1.20=0.840
    # CP-B: raw similarity 0.80, non-matching pattern → stays 0.80
    # CP-C: raw similarity 0.60, matching pattern → boosted to 0.60*1.20=0.720
    tmpl_a = _make_template("CP-A", pattern_hint="sort")
    tmpl_b = _make_template("CP-B", pattern_hint="navigate")
    tmpl_c = _make_template("CP-C", pattern_hint="sort")

    raw_results = [
        _make_scored("CP-B", 0.80, tmpl_b),  # highest raw, but no boost
        _make_scored("CP-A", 0.70, tmpl_a),  # gets boost: 0.840 → should be rank 1
        _make_scored("CP-C", 0.60, tmpl_c),  # gets boost: 0.720 → should be rank 2 or 3
    ]
    spec = _make_spec(pattern_hint="sort")

    fake_cache = {"CP-A": tmpl_a, "CP-B": tmpl_b, "CP-C": tmpl_c}

    with (
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever"
            ".retrieve_templates_with_scores",
            return_value=raw_results,
        ),
        patch(
            "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
            fake_cache,
        ),
    ):
        results = retrieve_with_intent_soft_filter(
            spec, top_k=3, original_query="sort items", boost=1.20, oversample=1
        )

    assert len(results) == 3
    # Expected order: CP-A (0.840) > CP-B (0.80) > CP-C (0.720)
    assert results[0]["task_id"] == "CP-A", f"Expected CP-A first, got {results[0]['task_id']}"
    assert results[1]["task_id"] == "CP-B", f"Expected CP-B second, got {results[1]['task_id']}"
    assert results[2]["task_id"] == "CP-C", f"Expected CP-C third, got {results[2]['task_id']}"

    # Verify the boosted similarities are descending
    sims = [r["similarity_boosted"] for r in results]
    assert sims == sorted(sims, reverse=True), f"Not descending: {sims}"
    assert abs(sims[0] - 0.70 * 1.20) < 1e-9
    assert abs(sims[1] - 0.80) < 1e-9
    assert abs(sims[2] - 0.60 * 1.20) < 1e-9

# ── MACHINE-SAFETY GUARD (2026-06-12) ──────────────────────────────────────
# This module touches ChromaDB/HNSW natively. Running it while the
# long-lived daemons on this machine hold the same store froze the whole
# machine TWICE (05:45 + 05:59, ~1-4 min after each pytest invocation that
# name-matched a test in here via -k). Skip locally when the sentinel file
# exists; run these in the cloud container or with all daemons stopped.
import pathlib as _pl_guard
import pytest as _pt_guard
if _pl_guard.Path("/home/anton/.no_local_chroma_tests").exists():
    pytestmark = _pt_guard.mark.skip(
        reason="ChromaDB tests disabled on this machine: shared HNSW store "
               "with live daemons — parallel native access froze the machine "
               "2x on 2026-06-12 (sentinel: ~/.no_local_chroma_tests)")

import math
import sys
from pathlib import Path

import pytest

# All tests in this module are L0 (pure functions, no external deps)
pytestmark = pytest.mark.l0

# scripts/ is not a package — load _stats.py directly
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "qa"))
import _stats  # type: ignore  # noqa: E402


def test_wilson_zero_trials_returns_full_unit_interval():
    """n=0: no information → uninformative prior [0, 1]."""
    lo, hi = _stats.wilson(0, 0)
    assert lo == 0.0
    assert hi == 1.0


def test_wilson_all_pass_lower_bound_strictly_below_one():
    """10/10 must give lower bound < 1.0 (we cannot prove certainty
    from 10 trials), upper bound = 1.0."""
    lo, hi = _stats.wilson(10, 10)
    assert hi == 1.0
    assert 0.65 < lo < 0.85, f"expected lo near 0.72, got {lo}"


def test_wilson_all_fail_upper_bound_strictly_above_zero():
    """0/10 must give upper bound > 0.0, lower bound = 0.0."""
    lo, hi = _stats.wilson(0, 10)
    assert lo == 0.0
    assert 0.18 < hi < 0.40, f"expected hi near 0.28, got {hi}"


def test_wilson_fifty_fifty_centered_with_wide_ci_at_small_n():
    """5/10 should be centered around 0.5, with wide CI."""
    lo, hi = _stats.wilson(5, 10)
    assert 0.20 < lo < 0.30
    assert 0.70 < hi < 0.80


def test_wilson_fifty_fifty_narrows_with_more_data():
    """50/100 should be centered at 0.5 with narrower CI than 5/10."""
    lo_small, hi_small = _stats.wilson(5, 10)
    lo_large, hi_large = _stats.wilson(50, 100)
    width_small = hi_small - lo_small
    width_large = hi_large - lo_large
    assert width_large < width_small, "more trials should narrow CI"
    assert 0.40 < lo_large < 0.45
    assert 0.55 < hi_large < 0.60


def test_wilson_z_99_wider_than_z_95():
    """Higher confidence level → wider interval (same data)."""
    lo95, hi95 = _stats.wilson(50, 100, z=_stats.Z_95)
    lo99, hi99 = _stats.wilson(50, 100, z=_stats.Z_99)
    assert (hi99 - lo99) > (hi95 - lo95)


def test_wilson_invalid_passes_raises():
    """passes > n is invalid input."""
    with pytest.raises(ValueError):
        _stats.wilson(5, 3)
    with pytest.raises(ValueError):
        _stats.wilson(-1, 10)


def test_wilson_lower_extracts_first_element():
    lo = _stats.wilson_lower(7, 10)
    full_lo, _ = _stats.wilson(7, 10)
    assert lo == full_lo


def test_wilson_upper_extracts_second_element():
    hi = _stats.wilson_upper(7, 10)
    _, full_hi = _stats.wilson(7, 10)
    assert hi == full_hi


def test_format_proportion_includes_counts_percent_and_ci():
    s = _stats.format_proportion(13, 20)
    assert "13/20" in s
    assert "65%" in s
    # CI should be present in [LL%, UU%] form
    assert "[" in s and "]" in s


def test_format_proportion_zero_n_is_safe():
    s = _stats.format_proportion(0, 0)
    assert "0/0" in s


def test_overlapping_returns_true_for_overlapping_intervals():
    """13/20 → ~[0.43, 0.82], 16/20 → ~[0.58, 0.92]. Heavy overlap."""
    assert _stats.overlapping(13, 20, 16, 20) is True


def test_overlapping_returns_false_for_clearly_separated():
    """0/100 → ~[0, 0.04], 100/100 → ~[0.96, 1]. Disjoint."""
    assert _stats.overlapping(0, 100, 100, 100) is False


def test_overlapping_symmetric():
    """overlapping(a, b) should equal overlapping(b, a)."""
    assert (
        _stats.overlapping(5, 10, 15, 20)
        == _stats.overlapping(15, 20, 5, 10)
    )


def test_wilson_clamps_to_unit_interval():
    """Bounds must always be in [0, 1] regardless of inputs."""
    for passes, n in [(0, 1), (1, 1), (1, 2), (99, 100), (1000, 1000)]:
        lo, hi = _stats.wilson(passes, n)
        assert 0.0 <= lo <= 1.0
        assert 0.0 <= hi <= 1.0
        assert lo <= hi


def test_wilson_known_reference_value():
    """Cross-check against a known Wilson value:
    13/20 at z=1.96 → roughly [0.4326, 0.8190]
    (verified via scipy.stats.binomtest or external Wilson calculator)."""
    lo, hi = _stats.wilson(13, 20)
    assert math.isclose(lo, 0.4326, abs_tol=0.01)
    assert math.isclose(hi, 0.8190, abs_tol=0.01)


# ── find_wilson_passing tests (mark_verified.py) ──
# These exercise the verification helper directly. We import the function
# rather than running the CLI to keep tests pure (no chromadb).

def _build_runs(*per_task_results):
    """per_task_results: list of (task_id, [pass_or_fail, ...]) tuples.
    Returns N runs in mark_verified's load_judged dict shape."""
    n_runs = len(per_task_results[0][1]) if per_task_results else 0
    runs = []
    for run_idx in range(n_runs):
        run = {}
        for tid, results in per_task_results:
            ok = results[run_idx]
            run[tid] = {
                "real": ok, "scene": ok, "fab": 0 if ok else 1, "turns": 5,
            }
        runs.append(run)
    return runs


def test_find_wilson_passing_strict_threshold_rejects_2_of_3():
    """2/3 successes — Wilson lower at 95% is ~0.21. So threshold ≥ 0.5
    must reject; threshold ≤ 0.2 must accept."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "qa"))
    import mark_verified as mv  # type: ignore  # noqa: E402
    runs = _build_runs(("T-A", [True, True, False]))
    # Strict 0.5: not enough evidence from n=3
    out = mv.find_wilson_passing(runs, threshold=0.5)
    assert out == [], f"expected empty at threshold 0.5, got {out}"
    # Lenient 0.2: 2/3 should pass
    out = mv.find_wilson_passing(runs, threshold=0.2)
    assert len(out) == 1
    tid, passes, n, lo = out[0]
    assert tid == "T-A" and passes == 2 and n == 3
    assert 0.20 < lo < 0.25, f"expected lo near 0.21, got {lo}"


def test_find_wilson_passing_three_perfect_passes_at_low_threshold():
    """3/3 — Wilson lower at 95% is ~0.44. Threshold ≤ 0.4 should accept,
    ≥ 0.5 should reject."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "qa"))
    import mark_verified as mv  # type: ignore  # noqa: E402
    runs = _build_runs(("T-PERFECT", [True, True, True]))
    out = mv.find_wilson_passing(runs, threshold=0.4)
    assert len(out) == 1, "3/3 should pass at threshold 0.4"
    out = mv.find_wilson_passing(runs, threshold=0.5)
    assert out == [], "3/3 too small for threshold 0.5"


def test_find_wilson_passing_intersects_runs():
    """Tasks present in only some runs are excluded (same as triple-perfect)."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "qa"))
    import mark_verified as mv  # type: ignore  # noqa: E402
    runs = [
        {"T-COMMON": {"real": True, "scene": True, "fab": 0},
         "T-ONLY-1": {"real": True, "scene": True, "fab": 0}},
        {"T-COMMON": {"real": True, "scene": True, "fab": 0}},
    ]
    out = mv.find_wilson_passing(runs, threshold=0.1)
    ids = [t[0] for t in out]
    assert "T-COMMON" in ids
    assert "T-ONLY-1" not in ids, "task missing from one run must be excluded"


def test_find_wilson_passing_empty_runs_returns_empty():
    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "qa"))
    import mark_verified as mv  # type: ignore  # noqa: E402
    assert mv.find_wilson_passing([], threshold=0.5) == []


# ── MACHINE-SAFETY GUARD (2026-06-12) — placed LAST so it cannot be
# overridden by earlier pytestmark assignments. This module touches
# ChromaDB/HNSW natively; running it while this machine's long-lived
# daemons hold the same store froze the whole machine TWICE (05:45 +
# 05:59, minutes after each pytest invocation that matched a test in
# here via -k). Run these in the cloud container or with daemons stopped.
import pathlib as _pl_guard
import pytest as _pt_guard
if _pl_guard.Path("/home/anton/.no_local_chroma_tests").exists():
    _skip_chroma = _pt_guard.mark.skip(
        reason="ChromaDB tests disabled on this machine: shared HNSW store "
               "with live daemons froze the machine 2x on 2026-06-12 "
               "(sentinel: ~/.no_local_chroma_tests)")
    try:
        pytestmark = (list(pytestmark) if isinstance(pytestmark, (list, tuple))
                      else [pytestmark]) + [_skip_chroma]
    except NameError:
        pytestmark = _skip_chroma
