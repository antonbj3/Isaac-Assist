"""L0 tests for dual_verify (P1-12..14) — metric pairs, skip-or-gate policy,
fidelity tiers. The load-bearing assertions are the HONESTY INVARIANTS:
uncalibrated PASS never skips; unknown pairs block SKIP; geometry fail rejects.
"""
import pytest

from service.isaac_assist_service.multimodal import static_eyes as se
from service.isaac_assist_service.multimodal.dual_verify import (
    Decision,
    FidelityTier,
    PROBE_REACH,
    REJECT_FIX,
    RUN_GATE,
    SKIP_GATE,
    decide,
    floor_tier,
    static_pair_verdicts,
    tag_measured,
)

pytestmark = pytest.mark.l0


def _layout(**over):
    d = {
        "robots": [{"path": "/World/UR10", "family": "ur10", "base": [0.0, 0.0, 1.0]}],
        "objects": [
            {"path": "/World/Cube_1", "position": [0.4, -0.3, 1.05], "asset_name": "cube_medium"},
            {"path": "/World/Bin", "position": [0.5, -0.4, 0.95], "asset_name": "bin"},
            {"path": "/World/Table", "position": [0.4, -0.3, 0.5], "asset_name": "table_medium",
             "bbox": [[-0.2, -0.7, 0.0], [1.0, 0.1, 1.0]]},
        ],
        "picks": ["/World/Cube_1"],
        "places": [{"target_path": "/World/Bin", "drop_target": [0.5, -0.4, 1.15]}],
    }
    d.update(over)
    return d


_FULL_CAL = {p: {"skip_cleared": True} for p in ("reach", "delivery", "support", "geometry")}


def test_pass_without_calibration_runs_gate_never_skips():
    """THE honesty invariant: uncalibrated static PASS still pays for physics."""
    d = decide(se.run(_layout()))
    assert d.action == RUN_GATE
    assert any("no calibration" in r for r in d.reasons)
    assert d.fidelity_floor == FidelityTier.ESTIMATED  # cheap-estimated, not proven


def test_reach_fail_rejects_before_build():
    layout = _layout()
    layout["objects"][0]["position"] = [0.4, -1.6, 1.05]
    d = decide(se.run(layout))
    assert d.action == REJECT_FIX
    assert d.pair_verdicts["reach"].status == "fail"


def test_reach_uncertain_routes_to_probe():
    layout = _layout()
    layout["objects"][0]["position"] = [0.4, -0.3, 0.6]  # below base z
    d = decide(se.run(layout))
    assert d.action == PROBE_REACH


def test_geometry_trust_pair_clump_rejects():
    layout = _layout(
        objects=[
            {"path": "/World/Cube_1", "position": [0.4, -0.3, 1.05], "asset_name": "cube_medium"},
            {"path": "/World/Cube_2", "position": [0.41, -0.3, 1.05], "asset_name": "cube_medium"},
        ],
        picks=["/World/Cube_1", "/World/Cube_2"],
        places=[],
    )
    d = decide(se.run(layout))
    assert d.action == REJECT_FIX
    assert d.pair_verdicts["geometry"].status == "fail"


def test_calibrated_full_pass_skips():
    d = decide(se.run(_layout()), calibration=_FULL_CAL)
    assert d.action == SKIP_GATE


def test_calibration_missing_one_pair_still_gates():
    cal = {p: {"skip_cleared": True} for p in ("reach", "delivery", "support")}
    cal["geometry"] = {"skip_cleared": False}  # one pair not cleared
    d = decide(se.run(_layout()), calibration=cal)
    assert d.action == RUN_GATE


def test_unknown_pair_blocks_calibrated_skip():
    """No places -> delivery has no checks -> unknown -> SKIP must not fire."""
    layout = _layout(places=[])
    d = decide(se.run(layout), calibration=_FULL_CAL)
    assert d.pair_verdicts["delivery"].status == "unknown"
    assert d.action == RUN_GATE


def test_fidelity_floor_weakest_wins():
    assert floor_tier([FidelityTier.MEASURED, FidelityTier.ESTIMATED]) == FidelityTier.ESTIMATED
    assert floor_tier([FidelityTier.MEASURED]) == FidelityTier.MEASURED
    assert floor_tier([]) == FidelityTier.SYNTHETIC


def test_tag_measured_upgrades_provenance():
    pairs = static_pair_verdicts(se.run(_layout()))
    assert all(v.fidelity == FidelityTier.ESTIMATED for v in pairs.values() if v.status != "unknown")
    tag_measured(pairs, gate_success=True)
    assert all(v.fidelity == FidelityTier.MEASURED for v in pairs.values())
    assert any("physics" in n for n in pairs["reach"].notes)
