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


# --- P1-18..20: typed Relations -------------------------------------------

def test_relation_model_and_legacy_dicts_coexist():
    from service.isaac_assist_service.multimodal import LayoutSpec, Relation
    spec = LayoutSpec.model_validate({
        "version": "1.1",
        "intent": {"pattern_hint": "pick_place"},
        "constraints": [
            {"type": "on_top_of", "from_id": "a", "to_id": "b"},
            {"legacy": True},
        ],
        "source": {"modality": "drag_drop", "session_id": "s", "confidence": 1.0},
    })
    assert isinstance(spec.constraints[0], Relation)
    assert isinstance(spec.constraints[1], dict)


def test_validator_flags_unknown_relation_ids_and_sequence_cycles():
    from service.isaac_assist_service.multimodal import LayoutSpec
    from service.isaac_assist_service.multimodal.validate import validate_layout_spec
    base = {
        "version": "1.1",
        "intent": {"pattern_hint": "pick_place"},
        "objects": [
            {"id": "a", "class": "cube_medium", "name": "A",
             "position": {"x": 0, "y": 0}, "size": {"w": 0.05, "h": 0.05}},
            {"id": "b", "class": "bin", "name": "B",
             "position": {"x": 1, "y": 0}, "size": {"w": 0.4, "h": 0.3}},
        ],
        "source": {"modality": "drag_drop", "session_id": "s", "confidence": 1.0},
    }
    # unknown id
    spec = LayoutSpec.model_validate({**base, "constraints": [
        {"type": "on_top_of", "from_id": "a", "to_id": "GHOST"}]})
    res = validate_layout_spec(spec, raise_on_error=False)
    assert any(i.code == "relation.unknown_object_id" for i in res.issues)
    # sequence cycle a->b->a
    spec2 = LayoutSpec.model_validate({**base, "constraints": [
        {"type": "sequence", "from_id": "a", "to_id": "b"},
        {"type": "sequence", "from_id": "b", "to_id": "a"}]})
    res2 = validate_layout_spec(spec2, raise_on_error=False)
    assert any(i.code == "relation.sequence_cycle" for i in res2.issues)


def test_static_eyes_verifies_declared_relations():
    layout = _layout()
    # violated on_top_of: cube floats far from the bin top
    layout["relations"] = [{"type": "on_top_of", "from": "/World/Cube_1", "to": "/World/Bin"}]
    rep = se.run(layout)
    rel = [c for c in rep.checks if c.id == "relation:on_top_of"]
    assert rel and rel[0].status == "fail"
    assert rel[0].fix and rel[0].fix["suggest_position"]
    # applying the suggestion satisfies the relation
    layout2 = _layout()
    layout2["objects"][0]["position"] = rel[0].fix["suggest_position"]
    layout2["relations"] = layout["relations"]
    rep2 = se.run(layout2)
    rel2 = [c for c in rep2.checks if c.id == "relation:on_top_of"]
    assert rel2 and rel2[0].status == "pass"
    # soft severity -> warn, not fail
    layout3 = _layout()
    layout3["relations"] = [{"type": "on_top_of", "from": "/World/Cube_1",
                             "to": "/World/Bin", "severity": "soft"}]
    rep3 = se.run(layout3)
    rel3 = [c for c in rep3.checks if c.id == "relation:on_top_of"]
    assert rel3 and rel3[0].status == "warn"


def test_relation_fail_reaches_decide_via_geometry_pair():
    layout = _layout()
    layout["relations"] = [{"type": "on_top_of", "from": "/World/Cube_1", "to": "/World/Bin"}]
    d = decide(se.run(layout))
    assert d.action == REJECT_FIX
    assert d.pair_verdicts["geometry"].status == "fail"
