"""L0 tests for scene_body codegen tools [P2-02]."""
import ast

import pytest

from service.isaac_assist_service.chat.tools.expand import expand_tool_call
from service.isaac_assist_service.chat.tools.handlers.scene_body import (
    _gen_create_scene_baseline,
)

pytestmark = pytest.mark.l0


def test_baseline_emits_parseable_canonical_opening():
    code = _gen_create_scene_baseline({})
    ast.parse(code)
    for marker in ("DomeLight", "Ground", "Table", "PhysicsScene",
                   "CollisionAPI", "BroadphaseTypeAttr"):
        assert marker in code, f"saknar {marker}"
    assert "Set(False)" in code            # CPU dynamics default
    assert "'MBP'" in code                 # broadphase default


def test_baseline_parameterized_and_tableless():
    code = _gen_create_scene_baseline({
        "intensity": 1500, "ground_scale": 10,
        "include_table": False, "physics": {"enable_gpu_dynamics": True}})
    ast.parse(code)
    assert "1500" in code and "Set(True)" in code
    assert "Table" not in code             # tableless variant

def test_table_geometry_matches_handrolled_convention():
    # top at 0.75 => slab centre z=0.375, scale z=0.375 (the CP-70/CP-01 convention)
    code = _gen_create_scene_baseline({"table_height": 0.75, "table_size": [1.5, 0.5]})
    assert "Gf.Vec3d(0.0, 0.0, 0.375)" in code
    assert "Gf.Vec3f(0.75, 0.25, 0.375)" in code


def test_registered_and_expandable():
    code = expand_tool_call("create_scene_baseline", {"intensity": 777})
    ast.parse(code)
    assert "777" in code
