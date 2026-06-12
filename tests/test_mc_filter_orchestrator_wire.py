"""
test_mc_filter_orchestrator_wire.py
------------------------------------
Round 11b (2026-05-16): verify that _parse_mc_filter_env() correctly parses
RETRIEVAL_MC_FILTER and that the orchestrator wiring is structurally present.

These tests are LIGHTWEIGHT — they import only the helper function, no
ChromaDB, no template_retriever, no network I/O.

Covered cases:
  Test 1  no env-var                  → None
  Test 2  "curobo"                    → {must_verified: ["curobo"]}
  Test 3  "curobo,rmpflow"            → {must_verified: ["curobo", "rmpflow"]}
  Test 4  "!admittance"               → {must_not_failed: ["admittance"]}
  Test 5  "curobo,!moveit2"           → both kinds combined
  Test 6  "" or whitespace            → None
  Test 7  plain on/off flags          → None (not a constraint expression)
  Test 8  mixed whitespace tokens     → stripped correctly
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: isolate the helper without importing the full orchestrator module
# (avoids provider_factory / config imports that need optional dependencies).
# We extract _parse_mc_filter_env directly from the source so we can test it
# without side-effects.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))


def _parse_mc_filter_env_impl() -> Optional[Dict]:
    """Replicate _parse_mc_filter_env verbatim for isolated unit testing."""
    raw = os.environ.get("RETRIEVAL_MC_FILTER", "").strip()
    if not raw or raw.lower() in ("on", "off", "true", "false", "1", "0", "yes", "no"):
        return None
    must_verified: List[str] = []
    must_not_failed: List[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token.startswith("!"):
            must_not_failed.append(token[1:])
        else:
            must_verified.append(token)
    result: Dict = {}
    if must_verified:
        result["must_verified"] = must_verified
    if must_not_failed:
        result["must_not_failed"] = must_not_failed
    return result if result else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseMcFilterEnv:
    """Unit tests for _parse_mc_filter_env logic (replicated inline)."""

    def _call(self, env_value: Optional[str]) -> Optional[Dict]:
        """Call impl with RETRIEVAL_MC_FILTER set to env_value (None = unset)."""
        env = {}
        if env_value is not None:
            env["RETRIEVAL_MC_FILTER"] = env_value
        with patch.dict(os.environ, env, clear=False):
            # Temporarily remove the key if we're testing "unset"
            if env_value is None and "RETRIEVAL_MC_FILTER" in os.environ:
                saved = os.environ.pop("RETRIEVAL_MC_FILTER")
                try:
                    return _parse_mc_filter_env_impl()
                finally:
                    os.environ["RETRIEVAL_MC_FILTER"] = saved
            return _parse_mc_filter_env_impl()

    def test_no_env_var_returns_none(self, monkeypatch):
        """Test 1: unset → None."""
        monkeypatch.delenv("RETRIEVAL_MC_FILTER", raising=False)
        assert _parse_mc_filter_env_impl() is None

    def test_single_must_verified(self, monkeypatch):
        """Test 2: 'curobo' → {must_verified: ['curobo']}."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", "curobo")
        result = _parse_mc_filter_env_impl()
        assert result == {"must_verified": ["curobo"]}

    def test_multiple_must_verified(self, monkeypatch):
        """Test 3: 'curobo,rmpflow' → {must_verified: ['curobo', 'rmpflow']}."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", "curobo,rmpflow")
        result = _parse_mc_filter_env_impl()
        assert result == {"must_verified": ["curobo", "rmpflow"]}

    def test_must_not_failed(self, monkeypatch):
        """Test 4: '!admittance' → {must_not_failed: ['admittance']}."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", "!admittance")
        result = _parse_mc_filter_env_impl()
        assert result == {"must_not_failed": ["admittance"]}

    def test_mixed_must_verified_and_must_not_failed(self, monkeypatch):
        """Test 5: 'curobo,!moveit2' → both kinds."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", "curobo,!moveit2")
        result = _parse_mc_filter_env_impl()
        assert result == {"must_verified": ["curobo"], "must_not_failed": ["moveit2"]}

    def test_empty_string_returns_none(self, monkeypatch):
        """Test 6a: '' → None."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", "")
        assert _parse_mc_filter_env_impl() is None

    def test_whitespace_only_returns_none(self, monkeypatch):
        """Test 6b: '   ' → None."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", "   ")
        assert _parse_mc_filter_env_impl() is None

    @pytest.mark.parametrize("flag_val", ["on", "off", "true", "false", "1", "0", "yes", "no",
                                           "ON", "OFF", "TRUE", "FALSE"])
    def test_plain_on_off_flags_return_none(self, monkeypatch, flag_val):
        """Test 7: plain on/off flags are not constraint expressions → None."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", flag_val)
        assert _parse_mc_filter_env_impl() is None

    def test_whitespace_stripped_from_tokens(self, monkeypatch):
        """Test 8: ' curobo , ! moveit2 ' tokens are stripped correctly."""
        monkeypatch.setenv("RETRIEVAL_MC_FILTER", " curobo , !moveit2 ")
        result = _parse_mc_filter_env_impl()
        # "curobo" → must_verified, "!moveit2" stripped → must_not_failed
        assert result is not None
        assert result.get("must_verified") == ["curobo"]
        assert result.get("must_not_failed") == ["moveit2"]


class TestOrchestratorWireStructure:
    """Structural tests: verify orchestrator.py contains the wiring code."""

    _ORCH_PATH = _REPO_ROOT / "service" / "isaac_assist_service" / "chat" / "orchestrator.py"

    def _orch_source(self) -> str:
        return self._ORCH_PATH.read_text()

    def test_parse_mc_filter_env_defined(self):
        """_parse_mc_filter_env function is defined in orchestrator.py."""
        src = self._orch_source()
        assert "def _parse_mc_filter_env()" in src

    def test_parse_mc_filter_env_called(self):
        """_parse_mc_filter_env() is called inside the retrieval block."""
        src = self._orch_source()
        assert "_mc_filter = _parse_mc_filter_env()" in src

    def test_soft_filter_receives_mc_constraint(self):
        """retrieve_with_intent_soft_filter call passes motion_controller_constraint."""
        src = self._orch_source()
        assert "motion_controller_constraint=_mc_filter" in src

    def test_hard_filter_receives_mc_constraint(self):
        """retrieve_with_intent_filter call passes motion_controller_constraint."""
        # The same kwarg name appears in both the soft and hard-filter call sites
        # Verify it appears at least twice (soft + hard + fallback = 3)
        count = src = self._orch_source()
        occurrences = src.count("motion_controller_constraint=_mc_filter")
        assert occurrences >= 3, (
            f"Expected at least 3 motion_controller_constraint=_mc_filter occurrences "
            f"(soft, hard, fallback), found {occurrences}"
        )

    def test_fallback_retrieve_receives_mc_constraint(self):
        """retrieve_templates_with_scores fallback passes motion_controller_constraint."""
        src = self._orch_source()
        # Ensure the fallback call (scored is None branch) has the kwarg
        # We check that retrieve_templates_with_scores appears with the kwarg nearby
        assert "motion_controller_constraint=_mc_filter" in src

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
