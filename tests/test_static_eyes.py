"""L0 tests for static_eyes — pure-Python geometric layout verifier (no Kit).

Covers: clean PASS, out-of-reach FAIL + convergent fix, interpenetration,
drop-outside-container, below-base UNCERTAIN (tier-2 routing), and the
form-gate reach_diagnostics shape.
"""
import copy

import pytest

from service.isaac_assist_service.multimodal import static_eyes as se

pytestmark = pytest.mark.l0


def _good():
    return {
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


def _status(rep, check_id):
    return [c for c in rep.checks if c.id == check_id]


def test_good_layout_passes():
    rep = se.run(_good())
    assert rep.verdict == "PASS"
    assert rep.next_gate == "function_gate"
    # no false-positive fails on a clean layout
    assert not any(c.status == "fail" for c in rep.checks)


def test_out_of_reach_fails_with_convergent_fix():
    layout = _good()
    layout["objects"][0]["position"] = [0.4, -1.6, 1.05]  # 1.65m from base > 1.30 reach
    rep = se.run(layout)
    assert rep.verdict == "FAIL"
    reach = _status(rep, "reach:shell")
    fail = [c for c in reach if c.status == "fail" and c.target == "/World/Cube_1"]
    assert fail, "expected reach:shell fail on the far pick"
    fix = fail[0].fix
    assert fix and fix["action"] == "move_object"
    sp = fix["suggest_position"]
    # the suggested position must itself be within reach (the loop converges)
    layout2 = copy.deepcopy(layout)
    layout2["objects"][0]["position"] = sp
    rep2 = se.run(layout2)
    assert not [c for c in _status(rep2, "reach:shell")
                if c.status == "fail" and c.target == "/World/Cube_1"], \
        "applying suggest_position should clear the reach fail"


def test_interpenetration_detected():
    layout = {
        "robots": [{"path": "/World/UR10", "family": "ur10", "base": [0.0, 0.0, 1.0]}],
        "objects": [
            {"path": "/World/Cube_1", "position": [0.4, -0.3, 1.05], "asset_name": "cube_medium"},
            {"path": "/World/Cube_2", "position": [0.41, -0.3, 1.05], "asset_name": "cube_medium"},
        ],
        "picks": ["/World/Cube_1", "/World/Cube_2"], "places": [],
    }
    rep = se.run(layout)
    assert any(c.id == "interpenetration" and c.status == "fail" for c in rep.checks)


def test_drop_outside_container_fails():
    layout = _good()
    layout["places"] = [{"target_path": "/World/Bin", "drop_target": [2.0, -0.4, 1.15]}]
    rep = se.run(layout)
    dic = _status(rep, "drop_in_container")
    assert any(c.status == "fail" for c in dic)
    fail = [c for c in dic if c.status == "fail"][0]
    assert fail.fix and fail.fix["action"] == "move_drop_target"


def test_below_base_is_uncertain_not_pass():
    layout = _good()
    layout["objects"][0]["position"] = [0.4, -0.3, 0.6]  # below base z=1.0
    rep = se.run(layout)
    assert rep.verdict == "UNCERTAIN"
    assert rep.next_gate == "tier2_reach_probe"
    assert any(c.id == "reach:shell" and c.status == "uncertain" for c in rep.checks)


def test_reach_diagnostics_shape():
    good = se.run(_good())
    assert se.reach_diagnostics(good) == {"all_reachable": True, "unreachable": []}
    layout = _good()
    layout["objects"][0]["position"] = [0.4, -1.6, 1.05]
    bad = se.run(layout)
    diag = se.reach_diagnostics(bad)
    assert diag["all_reachable"] is False
    assert "/World/Cube_1" in diag["unreachable"]
