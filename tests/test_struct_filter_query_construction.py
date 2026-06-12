"""
test_struct_filter_query_construction.py
-----------------------------------------
Round 15 regression tests for the struct-filter query-construction bugs
fixed in template_retriever.py.

Bug 1 (Failure Mode A): Stage 2 re-embed used the structural fingerprint
    instead of the original user prompt for embedding similarity within
    the struct-filtered candidate set.

Bug 2 (Failure Mode B): The fallback path (Stage 1 returns 0 candidates)
    also used the fingerprint string as the query to retrieve_templates_with_scores,
    instead of the original user prompt.

Fix: retrieve_with_intent_filter now accepts `original_query` and uses it
    (when provided) for ALL embedding calls — both Stage 2 and the fallback.
    The fingerprint is only used for metadata filtering (Stage 1).

These tests use a mock embedding-call hook to capture what string was
actually embedded, and assert the user prompt was used.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.l0

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from service.isaac_assist_service.chat.tools.template_retriever import (
    retrieve_with_intent_filter,
    canonical_structural_fingerprint,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SAMPLE_PROMPT = "Pick and place a cube from the conveyor belt into a bin using a Franka robot"

_SAMPLE_INTENT = {
    "pattern_hint": "pick_place",
    "structural_features": {
        "destination_kind": "single_bin",
        "n_robot_stations": 1,
    },
    "counts": {"robots": 1, "conveyors": 1, "bins": 1},
    "structural_tags": [],
}

_FINGERPRINT = canonical_structural_fingerprint(_SAMPLE_INTENT)


# ---------------------------------------------------------------------------
# Helper: build a fake ChromaDB collection + template cache for isolation
# ---------------------------------------------------------------------------

def _make_fake_collection(task_ids: List[str]):
    """Return a MagicMock ChromaDB collection that echos the task_ids back."""
    col = MagicMock()
    col.count.return_value = len(task_ids)

    # col.query(query_texts=[...], n_results=N, where=...) → fake result
    def _query_side_effect(query_texts, n_results=3, where=None, **_kw):
        # Capture the query text via side_effect attribute (tests read it)
        _query_side_effect.last_query = query_texts[0] if query_texts else ""
        # Return first N ids from task_ids list
        ids_to_return = task_ids[:n_results]
        metas = [{"task_id": tid} for tid in ids_to_return]
        dists = [0.3] * len(ids_to_return)
        return {"metadatas": [metas], "distances": [dists]}

    _query_side_effect.last_query = None
    col.query.side_effect = _query_side_effect
    return col


def _make_fake_cache(task_ids: List[str], with_intent: bool = True) -> dict:
    """Return a fake _template_cache dict."""
    cache = {}
    for tid in task_ids:
        t = {
            "task_id": tid,
            "goal": f"Goal for {tid}",
            "thoughts": f"Thoughts for {tid}",
            "tools_used": ["create_prim"],
            "code": "",
            "failure_modes": [],
        }
        if with_intent:
            # Give matching intent so Stage 1 passes
            t["intent"] = {
                "pattern_hint": "pick_place",
                "structural_features": {"destination_kind": "single_bin"},
                "counts": {"robots": 1, "conveyors": 1, "bins": 1},
                "structural_tags": [],
            }
        cache[tid] = t
    return cache


# ---------------------------------------------------------------------------
# Test 1: Stage 2 uses original_query, not fingerprint
# ---------------------------------------------------------------------------

class TestStage2UsesOriginalQuery:
    """When Stage 1 finds candidates and original_query is provided, Stage 2
    must embed the user prompt — NOT the structural fingerprint."""

    def test_stage2_embeds_prompt_not_fingerprint(self):
        """Stage 2 query_texts should be [original_query], not [fingerprint]."""
        task_ids = ["CP-01", "CP-02", "CP-03"]
        fake_col = _make_fake_collection(task_ids)
        fake_cache = _make_fake_cache(task_ids, with_intent=True)

        with (
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._get_collection",
                return_value=fake_col,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
                fake_cache,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._load_template",
                side_effect=lambda tid: fake_cache.get(tid),
            ),
        ):
            results = retrieve_with_intent_filter(
                _SAMPLE_INTENT,
                top_k=3,
                original_query=_SAMPLE_PROMPT,
            )

        # col.query should have been called with the user prompt, not the fingerprint
        assert fake_col.query.called, "col.query was never called"
        actual_query = fake_col.query.side_effect.last_query
        assert actual_query == _SAMPLE_PROMPT, (
            f"Stage 2 embedded {actual_query!r} instead of user prompt {_SAMPLE_PROMPT!r}. "
            "Bug 1 (Failure Mode A) regression."
        )
        assert actual_query != _FINGERPRINT, (
            "Stage 2 used the fingerprint string for embedding — this is the R14 bug."
        )

    def test_stage2_fallback_to_fingerprint_when_no_original_query(self):
        """When original_query is None (legacy caller), fingerprint is used (backward compat)."""
        task_ids = ["CP-01", "CP-02"]
        fake_col = _make_fake_collection(task_ids)
        fake_cache = _make_fake_cache(task_ids, with_intent=True)

        with (
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._get_collection",
                return_value=fake_col,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
                fake_cache,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._load_template",
                side_effect=lambda tid: fake_cache.get(tid),
            ),
        ):
            retrieve_with_intent_filter(
                _SAMPLE_INTENT,
                top_k=3,
                original_query=None,  # legacy call — no prompt available
            )

        actual_query = fake_col.query.side_effect.last_query
        assert actual_query == _FINGERPRINT, (
            f"Without original_query, Stage 2 should embed the fingerprint (legacy). "
            f"Got: {actual_query!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: Fallback path uses original_query, not fingerprint
# ---------------------------------------------------------------------------

class TestFallbackUsesOriginalQuery:
    """When Stage 1 returns 0 candidates, the fallback embedding search must
    use the original user prompt — not the fingerprint."""

    def test_fallback_embeds_prompt_not_fingerprint(self):
        """When no candidates pass Stage 1, retrieve_templates_with_scores
        must be called with the user prompt, not the fingerprint."""
        # Use an intent with a pattern_hint that no template has → 0 candidates
        intent_no_match = {
            "pattern_hint": "nonexistent_pattern_xyz",
            "structural_features": {},
            "counts": {},
            "structural_tags": [],
        }
        # Cache has templates but none match the above pattern_hint
        fake_cache = _make_fake_cache(["CP-01", "CP-02"], with_intent=True)
        # (Their pattern_hint is pick_place, not nonexistent_pattern_xyz)

        captured_queries: List[str] = []

        def _fake_retrieve_with_scores(query: str, top_k: int = 3, **kw):
            captured_queries.append(query)
            return []

        with (
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
                fake_cache,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever.retrieve_templates_with_scores",
                side_effect=_fake_retrieve_with_scores,
            ),
            # _get_collection needed for filter_templates_by_intent cache init
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._get_collection",
                return_value=MagicMock(count=lambda: 2),
            ),
        ):
            retrieve_with_intent_filter(
                intent_no_match,
                top_k=3,
                original_query=_SAMPLE_PROMPT,
                fallback_to_embedding_only=True,
            )

        assert len(captured_queries) == 1, (
            f"Expected exactly 1 call to retrieve_templates_with_scores, got {len(captured_queries)}"
        )
        assert captured_queries[0] == _SAMPLE_PROMPT, (
            f"Fallback embedded {captured_queries[0]!r} instead of user prompt {_SAMPLE_PROMPT!r}. "
            "Bug 2 (Failure Mode B) regression."
        )

    def test_fallback_uses_fingerprint_when_no_original_query(self):
        """Legacy caller (no original_query) → fallback uses fingerprint (backward compat)."""
        intent_no_match = {
            "pattern_hint": "nonexistent_pattern_xyz",
            "structural_features": {},
            "counts": {},
            "structural_tags": [],
        }
        fake_cache = _make_fake_cache(["CP-01"], with_intent=True)
        captured_queries: List[str] = []

        def _fake_retrieve_with_scores(query: str, top_k: int = 3, **kw):
            captured_queries.append(query)
            return []

        expected_fingerprint = canonical_structural_fingerprint(intent_no_match)

        with (
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
                fake_cache,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever.retrieve_templates_with_scores",
                side_effect=_fake_retrieve_with_scores,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._get_collection",
                return_value=MagicMock(count=lambda: 1),
            ),
        ):
            retrieve_with_intent_filter(
                intent_no_match,
                top_k=3,
                original_query=None,  # legacy
                fallback_to_embedding_only=True,
            )

        assert len(captured_queries) == 1
        assert captured_queries[0] == expected_fingerprint, (
            f"Without original_query, fallback should use fingerprint. "
            f"Got: {captured_queries[0]!r}"
        )

    def test_fallback_not_called_when_disabled(self):
        """When fallback_to_embedding_only=False and Stage 1 returns 0 candidates,
        the function returns [] without calling retrieve_templates_with_scores."""
        intent_no_match = {
            "pattern_hint": "nonexistent_pattern_xyz",
            "structural_features": {},
            "counts": {},
            "structural_tags": [],
        }
        fake_cache = _make_fake_cache(["CP-01"], with_intent=True)

        with (
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
                fake_cache,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever.retrieve_templates_with_scores"
            ) as mock_rts,
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._get_collection",
                return_value=MagicMock(count=lambda: 1),
            ),
        ):
            result = retrieve_with_intent_filter(
                intent_no_match,
                top_k=3,
                original_query=_SAMPLE_PROMPT,
                fallback_to_embedding_only=False,
            )

        assert result == [], "Should return [] when fallback disabled"
        mock_rts.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Signature contract — original_query param exists and is Optional[str]
# ---------------------------------------------------------------------------

class TestSignatureContract:
    """Ensure retrieve_with_intent_filter accepts original_query as Optional[str]."""

    def test_original_query_param_accepted(self):
        """Calling with original_query=None should not raise TypeError."""
        fake_cache = _make_fake_cache([], with_intent=False)
        with (
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
                fake_cache,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever.retrieve_templates_with_scores",
                return_value=[],
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._get_collection",
                return_value=MagicMock(count=lambda: 0),
            ),
        ):
            # Both call forms must work without TypeError
            retrieve_with_intent_filter(_SAMPLE_INTENT, original_query=None)
            retrieve_with_intent_filter(_SAMPLE_INTENT, original_query=_SAMPLE_PROMPT)
            retrieve_with_intent_filter(_SAMPLE_INTENT)  # omitted = None

    def test_canonical_fingerprint_not_used_as_query_when_original_provided(self):
        """Defensive: even if fingerprint starts with 'pattern_hint=', the
        embedding call should never receive a string starting with 'pattern_hint='
        when original_query is a natural-language prompt."""
        task_ids = ["CP-01"]
        fake_col = _make_fake_collection(task_ids)
        fake_cache = _make_fake_cache(task_ids, with_intent=True)

        with (
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._get_collection",
                return_value=fake_col,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._template_cache",
                fake_cache,
            ),
            patch(
                "service.isaac_assist_service.chat.tools.template_retriever._load_template",
                side_effect=lambda tid: fake_cache.get(tid),
            ),
        ):
            retrieve_with_intent_filter(
                _SAMPLE_INTENT,
                top_k=1,
                original_query=_SAMPLE_PROMPT,
            )

        actual_query = fake_col.query.side_effect.last_query
        assert not actual_query.startswith("pattern_hint="), (
            f"Embedding query started with 'pattern_hint=' — this is the fingerprint, "
            f"not the user prompt. R14 bug regression detected. Query was: {actual_query!r}"
        )

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
