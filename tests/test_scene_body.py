"""L0 tests for scene_body codegen tools [P2-02, P2-03]."""
import ast

import pytest

from service.isaac_assist_service.chat.tools.expand import expand_tool_call
from service.isaac_assist_service.chat.tools.handlers.scene_body import (
    _gen_create_rigid_body_array,
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


# --- P2-03 create_rigid_body_array -----------------------------------------

def test_rba_corpus_default_full_physics_stack():
    # 3 cubes + rubber = the CP-70-family workpiece pattern in one call
    code = _gen_create_rigid_body_array({
        "positions": [[-0.5, 0.4, 0.835], [0.1, 0.2, 0.835], [0.3, 0.2, 0.835]],
        "material": "rubber"})
    ast.parse(code)
    for marker in ("RigidBodyAPI.Apply", "CollisionAPI.Apply", "MassAPI.Apply",
                   "PhysxRigidBodyAPI.Apply", "CreateSleepThresholdAttr().Set(0.0)",
                   "physics:materialBinding"):
        assert marker in code, f"saknar {marker}"
    assert "/World/Cube_1" in code and "/World/Cube_3" in code
    assert "GetSizeAttr().Set(0.05)" in code   # corpus workpiece size


def test_rba_asset_ref_is_the_bridge():
    # SAME tool, asset_ref present -> add_reference, no primitive define,
    # colliders backfilled on Gprims only when the asset authors none.
    code = _gen_create_rigid_body_array({
        "positions": [[0, 0, 1]], "asset_ref": "/data/assets/widget.usd",
        "asset_scale": [1, 1, 2], "mass": 0.5})
    ast.parse(code)
    assert "AddReference('/data/assets/widget.usd')" in code
    assert "UsdGeom.Cube.Define" not in code
    assert "Usd.PrimRange" in code and "UsdGeom.Gprim" in code
    assert "GetMassAttr().Set(0.5)" in code
    # the physics stack is identical to the primitive branch
    for marker in ("RigidBodyAPI.Apply", "PhysxRigidBodyAPI.Apply"):
        assert marker in code


def test_rba_sphere_and_explicit_paths():
    code = _gen_create_rigid_body_array({
        "positions": [[0, 0, 1], [1, 0, 1]], "prim_type": "Sphere",
        "size": 0.08, "paths": ["/World/Ball_A", "/World/Ball_B"]})
    ast.parse(code)
    assert "GetRadiusAttr().Set(0.04)" in code   # size = diameter
    assert "/World/Ball_A" in code and "/World/Ball_B" in code
    assert "Cube_" not in code


@pytest.mark.parametrize("bad", [
    {},                                                   # positions required
    {"positions": []},
    {"positions": [[1, 2]]},                              # not [x,y,z]
    {"positions": [[0, 0, 0]], "material": "unobtainium"},
    {"positions": [[0, 0, 0]], "prim_type": "Torus"},
    {"positions": [[0, 0, 0], [1, 1, 1]], "paths": ["/W/a"]},  # len mismatch
    {"positions": [[0, 0, 0]], "asset_ref": "x.usd", "asset_scale": [1]},
])
def test_rba_error_paths_emit_parseable_raise(bad):
    code = _gen_create_rigid_body_array(bad)
    ast.parse(code)                                       # quotes survive repr
    assert code.startswith("raise ValueError")


def test_rba_registered_and_expandable():
    code = expand_tool_call("create_rigid_body_array",
                            {"positions": [[0.2, 0.3, 0.835]]})
    ast.parse(code)
    assert "/World/Cube_1" in code
