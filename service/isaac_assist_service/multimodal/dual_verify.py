"""dual_verify — confidence-tiered measurement + the skip-or-gate decision policy.

Implements P1-12..14 (spec: docs/research/DUAL_VERIFICATION_SPEC.md, local):
- the 4 METRIC PAIRS (reach / delivery / support / geometry), each with a cheap
  static estimate (a static_eyes report) and an expensive physics measurement
  (the function gate / live probes);
- the DECISION POLICY: static FAIL -> reject without building; reach UNCERTAIN
  -> tier-2 IK probe; PASS -> gate (or, ONLY once calibration exists, SKIP);
- FIDELITY TIERS (SYNTHETIC < INFERRED < ESTIMATED < MEASURED, weakest wins) so
  a verdict always declares whether it is cheap-estimated or physics-proven.

HONESTY INVARIANT: without a measured calibration (P1-15), the SKIP path never
activates — a static PASS still runs the physics gate. Skipping on an
uncalibrated proxy is precisely the false-positive trap this project keeps
re-learning ("gates lie"). `geometry` is the designated TRUST pair (static
FAIL rejects pre-build) per the spec's near-zero-divergence analysis, but even
its PASS does not skip the gate until calibration confirms the band.

No Kit imports — pure Python, unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

from .static_eyes import StaticEyesReport

# ---------------------------------------------------------------------------
# Fidelity tiers — provenance of a verdict; the WEAKEST input wins.
# ---------------------------------------------------------------------------


class FidelityTier(IntEnum):
    SYNTHETIC = 0   # asserted/config-only, nothing computed
    INFERRED = 1    # derived from indirect signals
    ESTIMATED = 2   # computed from authored geometry (the static_eyes layer)
    MEASURED = 3    # physics-proven (function gate / live probe)


def floor_tier(tiers: List[FidelityTier]) -> FidelityTier:
    """The weakest input dominates — a verdict never over-claims."""
    return min(tiers) if tiers else FidelityTier.SYNTHETIC


# ---------------------------------------------------------------------------
# The 4 metric pairs — static_eyes check ids mapped to their pair.
# ---------------------------------------------------------------------------

PAIRS = ("reach", "delivery", "support", "geometry")

_CHECK_TO_PAIR: Dict[str, str] = {
    "reach:shell": "reach",
    "occlusion": "reach",            # advisory; never fails a pair by itself
    "drop_in_container": "delivery",
    "fit": "delivery",               # workpiece-fits-destination is a delivery precondition
    "support": "support",
    "interpenetration": "geometry",
    "footprint": "geometry",
}

# Static-estimate trustworthiness per pair (spec §1 summary):
# geometry is the TRUST pair (near-zero divergence); reach is necessary-not-
# sufficient (non-convex floor); delivery sees only where the drop was AIMED;
# support's stack verdict is a COM heuristic.
_PAIR_CONFIDENCE: Dict[str, float] = {
    "geometry": 0.95,
    "delivery": 0.70,
    "reach": 0.60,
    "support": 0.55,
}


@dataclass
class PairVerdict:
    pair: str
    status: str                      # pass | fail | uncertain | unknown
    confidence: float
    fidelity: FidelityTier
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pair": self.pair, "status": self.status,
            "confidence": self.confidence, "fidelity": self.fidelity.name,
            "notes": self.notes,
        }


def static_pair_verdicts(report: StaticEyesReport) -> Dict[str, PairVerdict]:
    """Aggregate a static_eyes report into per-pair verdicts (all ESTIMATED).

    Aggregation per pair: any non-advisory ``fail`` -> fail; else any
    ``uncertain`` -> uncertain; else ``pass`` if the pair had checks, else
    ``unknown`` (no information — never silently passes).
    """
    buckets: Dict[str, List] = {p: [] for p in PAIRS}
    for c in report.checks:
        pair = _CHECK_TO_PAIR.get(c.id)
        if pair is None and c.id.startswith("relation:"):
            pair = "geometry"  # declared spatial relations are geometric intent
        if pair:
            buckets[pair].append(c)

    out: Dict[str, PairVerdict] = {}
    for pair, checks in buckets.items():
        notes = [f"{c.id}:{c.status}" + (f" {c.target}" if c.target else "")
                 for c in checks if c.status != "pass"]
        hard = [c for c in checks if c.status == "fail" and c.id != "occlusion"]
        uncertain = [c for c in checks if c.status == "uncertain"]
        if hard:
            status = "fail"
        elif uncertain:
            status = "uncertain"
        elif checks:
            status = "pass"
        else:
            status = "unknown"
        out[pair] = PairVerdict(
            pair=pair, status=status,
            confidence=_PAIR_CONFIDENCE[pair] if checks else 0.0,
            fidelity=FidelityTier.ESTIMATED if checks else FidelityTier.SYNTHETIC,
            notes=notes,
        )
    return out


# ---------------------------------------------------------------------------
# The decision policy — skip-or-gate.
# ---------------------------------------------------------------------------

# Actions, in escalation order.
REJECT_FIX = "reject_fix_and_recall"     # static fail: do NOT build; apply fixes, re-run static_eyes
PROBE_REACH = "tier2_reach_probe"        # reach uncertain: one live IK probe (Kit+cuRobo, no settle)
RUN_GATE = "run_function_gate"           # build + physics gate (the expensive truth)
SKIP_GATE = "skip_gate_calibrated"       # calibrated-only: trust the static PASS


@dataclass
class Decision:
    action: str
    reasons: List[str]
    pair_verdicts: Dict[str, PairVerdict]
    fidelity_floor: FidelityTier

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action, "reasons": self.reasons,
            "pairs": {p: v.to_dict() for p, v in self.pair_verdicts.items()},
            "fidelity_floor": self.fidelity_floor.name,
        }


def decide(report: StaticEyesReport,
           calibration: Optional[Dict[str, Any]] = None) -> Decision:
    """Map a static_eyes report to the next verification action.

    Policy (spec §2):
      any pair FAIL          -> REJECT_FIX (never build a geometrically broken layout)
      reach UNCERTAIN        -> PROBE_REACH (cheapest sufficient probe first)
      all PASS, calibration  -> SKIP_GATE only for pairs whose measured band
                                clears the false-PASS threshold; else RUN_GATE
      all PASS, no calib     -> RUN_GATE (the honesty invariant)
    """
    pairs = static_pair_verdicts(report)
    fails = [p for p, v in pairs.items() if v.status == "fail"]
    uncertains = [p for p, v in pairs.items() if v.status == "uncertain"]

    if fails:
        return Decision(
            action=REJECT_FIX,
            reasons=[f"{p} static-FAIL: {'; '.join(pairs[p].notes) or 'see report'}" for p in fails],
            pair_verdicts=pairs,
            fidelity_floor=FidelityTier.ESTIMATED,
        )
    if "reach" in uncertains:
        return Decision(
            action=PROBE_REACH,
            reasons=["reach in the uncertain band (non-convex floor / near radius limit) — "
                     "one live IK probe is cheaper than a doomed full gate run"],
            pair_verdicts=pairs,
            fidelity_floor=FidelityTier.ESTIMATED,
        )
    if calibration:
        # Calibrated skip: every pair must be PASS and its measured false-PASS
        # rate must clear the threshold recorded by P1-15 calibration.
        skippable = all(
            pairs[p].status == "pass"
            and calibration.get(p, {}).get("skip_cleared", False)
            for p in PAIRS
        )
        if skippable:
            return Decision(
                action=SKIP_GATE,
                reasons=["all pairs static-PASS within calibrated bands "
                         f"(calibration: {calibration.get('_meta', 'unversioned')})"],
                pair_verdicts=pairs,
                fidelity_floor=FidelityTier.ESTIMATED,
            )
    return Decision(
        action=RUN_GATE,
        reasons=["static PASS — physics gate still required "
                 + ("(pair(s) not skip-cleared by calibration)" if calibration
                    else "(no calibration measured yet — SKIP never activates uncalibrated)")],
        pair_verdicts=pairs,
        fidelity_floor=FidelityTier.ESTIMATED,
    )


def tag_measured(pairs: Dict[str, PairVerdict], gate_success: bool,
                 note: str = "function gate") -> Dict[str, PairVerdict]:
    """After a physics run, upgrade the verdicts to MEASURED provenance."""
    for v in pairs.values():
        v.fidelity = FidelityTier.MEASURED
        v.notes.append(f"physics: {note} -> {'pass' if gate_success else 'fail'}")
    return pairs
