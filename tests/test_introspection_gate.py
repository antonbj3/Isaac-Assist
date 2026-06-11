"""l0 for the introspection gate evaluator — pure, no Kit."""
import pytest

pytestmark = pytest.mark.l0
from service.isaac_assist_service.qa.introspection_gate import (
    checks_from_expected_args, evaluate_checks)

BUILD = {
    "executed": [
        {"tool": "setup_grasp_pose_sampler",
         "args": {"sampling_mode": "antipodal"},
         "output": '{"n_samples": 24}'},
        {"tool": "check_singularity", "args": {},
         "output": '{"condition_number": 142.0}'},
        {"tool": "check_singularity", "args": {},
         "output": "condition_number=88.5"},
        {"tool": "check_singularity", "args": {},
         "output": '{"condition_number": 250.1}'},
        {"tool": "plan_trajectory", "args": {"planner": "lula_rrt"},
         "output": "{}"},
    ],
    "artifacts": {"grasp_poses": [{"q": i} for i in range(24)]},
}


def test_call_count_pass_and_fail():
    ok = evaluate_checks([{"kind": "call_count", "tool": "check_singularity",
                           "expect": 3}], BUILD)
    assert ok["success"] and ok["status"] == "PASS"
    bad = evaluate_checks([{"kind": "call_count", "tool": "check_singularity",
                            "expect": 5}], BUILD)
    assert not bad["success"] and bad["checks"][0]["got"] == 3


def test_call_arg_and_which():
    ok = evaluate_checks([{"kind": "call_arg", "tool": "plan_trajectory",
                           "arg": "planner", "expect": "lula_rrt"}], BUILD)
    assert ok["success"]
    miss = evaluate_checks([{"kind": "call_arg", "tool": "plan_trajectory",
                             "arg": "planner", "expect": "rmpflow"}], BUILD)
    assert miss["status"] == "FAIL"


def test_output_min_json_and_printed_text():
    ok = evaluate_checks([{"kind": "output_min", "tool": "check_singularity",
                           "field": "condition_number", "min": 100,
                           "which": 0}], BUILD)
    assert ok["success"]
    # second call's output is printed text, below floor -> FAIL with got
    bad = evaluate_checks([{"kind": "output_min", "tool": "check_singularity",
                            "field": "condition_number", "min": 100,
                            "which": 1}], BUILD)
    assert bad["status"] == "FAIL" and bad["checks"][0]["got"] == 88.5


def test_artifact_len():
    b = dict(BUILD); b["artifacts"] = {"grasp_poses": list(range(24))}
    ok = evaluate_checks([{"kind": "artifact_len", "artifact": "grasp_poses",
                           "min": 24}], b)
    assert ok["success"]
    bad = evaluate_checks([{"kind": "artifact_len", "artifact": "grasp_poses",
                            "min": 25}], b)
    assert bad["status"] == "FAIL"


def test_blocked_never_false():
    r = evaluate_checks([
        {"kind": "ros2_topic", "key": "expected_nav_topic", "expect": "/cmd_vel"},
        {"kind": "call_count", "tool": "plan_trajectory", "expect": 1},
    ], BUILD)
    assert r["status"] == "BLOCKED" and not r["success"]
    assert r["n_blocked"] == 1 and r["n_fail"] == 0
    # a real FAIL outranks BLOCKED
    r2 = evaluate_checks([
        {"kind": "ros2_topic", "key": "expected_nav_topic", "expect": "/cmd_vel"},
        {"kind": "call_count", "tool": "plan_trajectory", "expect": 9},
    ], BUILD)
    assert r2["status"] == "FAIL"


def test_unknown_kind_fails_loudly():
    r = evaluate_checks([{"kind": "telepathy", "expect": 1}], BUILD)
    assert r["status"] == "FAIL" and "unknown check kind" in r["checks"][0]["error"]


def test_expected_args_mapping_ik_singularity():
    va = {"robot_path": "/World/UR10",
          "expected_check_singularity_calls": "3",
          "wp1_expected_condition_number_min": "100",
          "expected_plan_trajectory_planner": "lula_rrt",
          "expected_get_joint_positions_calls": "3"}
    checks = checks_from_expected_args(va)
    kinds = sorted(c["kind"] for c in checks)
    assert kinds == ["call_arg", "call_count", "call_count", "output_min"]
    r = evaluate_checks(checks, BUILD)
    # get_joint_positions never called in BUILD -> exactly one FAIL surfaces
    fails = [c for c in r["checks"] if c["status"] == "FAIL"]
    assert len(fails) == 1 and fails[0]["tool"] == "get_joint_positions"


def test_expected_args_mapping_sampler_and_topics():
    va = {"expected_n_samples": "24", "expected_sampling_mode": "antipodal",
          "expected_nav_topic": "/cmd_vel"}
    checks = checks_from_expected_args(va)
    kinds = {c["kind"] for c in checks}
    assert {"output_min", "call_arg", "ros2_topic"} <= kinds
    r = evaluate_checks(checks, BUILD)
    assert r["status"] == "BLOCKED"  # topic check blocks, others pass


def test_unique_prefix_tool_match():
    b = {"executed": [{"tool": "interpolate_trajectory",
                       "args": {"method": "rmpflow"}, "output": "{}"}]}
    r = evaluate_checks([{"kind": "call_arg", "tool": "interpolate",
                          "arg": "method", "expect": "rmpflow"}], b)
    assert r["success"]


def test_unmapped_keys_surface():
    checks = checks_from_expected_args({"expected_weirdness": object()})
    assert any(c["kind"] in ("unmapped", "call_arg") for c in checks)


def test_attr_equals_with_and_without_tol():
    b = {"executed": [], "attrs": {"/World/Robot.stiffness_kp": 0.0,
                                   "/World/Robot.mode": "estopped"}}
    ok = evaluate_checks([
        {"kind": "attr_equals", "prim": "/World/Robot", "attr": "stiffness_kp",
         "expect": 0.0, "tol": 1e-6},
        {"kind": "attr_equals", "prim": "/World/Robot", "attr": "mode",
         "expect": "estopped"},
    ], b)
    assert ok["success"]
    bad = evaluate_checks([{"kind": "attr_equals", "prim": "/World/Robot",
                            "attr": "stiffness_kp", "expect": 400.0,
                            "tol": 1.0}], b)
    assert bad["status"] == "FAIL" and bad["checks"][0]["got"] == 0.0
    missing = evaluate_checks([{"kind": "attr_equals", "prim": "/World/X",
                                "attr": "nope", "expect": 1}], b)
    assert missing["status"] == "FAIL" and missing["checks"][0]["got"] is None
