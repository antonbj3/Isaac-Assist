"""l0 render tests for the task-mode seams (pull/turn/sweep) in the curobo
codegen. The seams live inside a generated-code f-string — a scope or brace
mistake there parses fine in the handler module yet NameErrors at runtime in
Kit (TASK_MODE scoping, live-diagnosed 2026-06-12: 5625 errors/run). These
tests render the generated module per task mode and parse it."""
import ast

import pytest

pytestmark = pytest.mark.l0

from service.isaac_assist_service.chat.tools.handlers.pick_place import (
    _gen_pick_place_curobo,
)


def _render(task=None, task_joint_path=None, task_args=None):
    return _gen_pick_place_curobo(
        robot_path="/World/Franka",
        sensor_path="/World/PickSensor",
        belt_path="",
        source_paths=["/World/Thing/Handle"],
        destination_path="/World/Thing/Handle",
        drop_target=[0.4, 0.0, 0.9],
        ee_offset=[0.0, 0.0, 0.0],
        task=task,
        task_joint_path=task_joint_path,
        task_args=task_args,
    )


@pytest.mark.parametrize("task,joint,targs", [
    (None, None, None),
    ("pull", "/World/DrawerJoint", {"task_travel_m": -0.3}),
    ("turn", "/World/FaucetJoint", {"task_target_deg": 90.0}),
    ("sweep", None, {"task_debris_paths": ["/World/Debris/Item_1"],
                     "task_backswing_m": 0.2}),
])
def test_generated_module_parses(task, joint, targs):
    code = _render(task=task, task_joint_path=joint, task_args=targs)
    ast.parse(code)


def test_task_constants_are_module_scope():
    # TASK_* must be defined at generated-module top level (column 0) —
    # consumed by _cube_to_pick, _build_segments AND _on_step
    code = _render(task="pull", task_joint_path="/World/J")
    for name in ("TASK_MODE = ", "TASK_JOINT_PATH = ", "TASK_ARGS = "):
        lines = [l for l in code.splitlines() if l.startswith(name)]
        assert len(lines) == 1, f"{name!r} not at module scope exactly once"
    assert "TASK_MODE = 'pull'" in code


def test_task_none_keeps_branches_dead():
    code = _render()
    assert "TASK_MODE = None" in code
