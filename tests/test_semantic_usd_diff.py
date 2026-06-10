"""L0 tests for semantic_usd_diff [P2-01]. Load-bearing assertion: 'same
scene, different source text' reads EQUIVALENT (order/formatting/float-eps),
while a real content change reads DIVERGENT with an actionable pointer."""
import pytest

pxr = pytest.importorskip("pxr")  # usd-core; present in CI/system python

from service.isaac_assist_service.qa.semantic_usd_diff import (  # noqa: E402
    diff_stages,
    stage_signature,
)

pytestmark = pytest.mark.l0

# Same scene, three authoring styles: A = reference; B = different prim ORDER,
# different float formatting (+1e-9 eps), different attr order; C = real change.
SCENE_A = """#usda 1.0
def Xform "World" {
    def Cube "Cube_1" {
        double size = 0.05
        float3 xformOp:translate = (0.4, -0.3, 1.05)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }
    def Cube "Bin" {
        double size = 0.3
        float3 xformOp:translate = (0.5, -0.4, 0.95)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }
}
"""

SCENE_B = """#usda 1.0
def Xform "World" {
    def Cube "Bin" {
        float3 xformOp:translate = (0.5, -0.4, 0.95)
        uniform token[] xformOpOrder = ["xformOp:translate"]
        double size = 0.30000000001
    }
    def Cube "Cube_1" {
        uniform token[] xformOpOrder = ["xformOp:translate"]
        double size = 0.05
        float3 xformOp:translate = (0.4, -0.3, 1.05)
    }
}
"""

SCENE_C = SCENE_A.replace("(0.4, -0.3, 1.05)", "(0.9, -0.3, 1.05)")  # moved cube


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_same_scene_different_text_is_equivalent(tmp_path):
    a = _write(tmp_path, "a.usda", SCENE_A)
    b = _write(tmp_path, "b.usda", SCENE_B)
    d = diff_stages(a, b)
    assert d["equivalent"], f"false divergence: {d}"


def test_real_change_is_divergent_with_pointer(tmp_path):
    a = _write(tmp_path, "a.usda", SCENE_A)
    c = _write(tmp_path, "c.usda", SCENE_C)
    d = diff_stages(a, c)
    assert not d["equivalent"]
    hits = [x for x in d["attr_diffs"] if x["prim"] == "/World/Cube_1"]
    assert hits and hits[0]["attr"] == "xformOp:translate"


def test_missing_prim_detected(tmp_path):
    a = _write(tmp_path, "a.usda", SCENE_A)
    b = _write(tmp_path, "b.usda", SCENE_A.replace(
        '    def Cube "Bin" {\n        double size = 0.3\n'
        '        float3 xformOp:translate = (0.5, -0.4, 0.95)\n'
        '        uniform token[] xformOpOrder = ["xformOp:translate"]\n    }\n', ""))
    d = diff_stages(a, b)
    assert not d["equivalent"]
    assert "/World/Bin" in d["missing_in_b"]


def test_float_tolerance_is_a_knob(tmp_path):
    a = _write(tmp_path, "a.usda", SCENE_A)
    b = _write(tmp_path, "b.usda", SCENE_A.replace("0.05", "0.0501"))
    assert not diff_stages(a, b)["equivalent"]          # default tol: divergent
    assert diff_stages(a, b, float_tol=0.001)["equivalent"]  # loose tol: equivalent


def test_signature_shape(tmp_path):
    a = _write(tmp_path, "a.usda", SCENE_A)
    sig = stage_signature(a)
    assert "/World/Cube_1" in sig
    assert sig["/World/Cube_1"]["type"] == "Cube"
    assert "size" in sig["/World/Cube_1"]["attrs"]


def test_identical_infinities_are_equal():
    from service.isaac_assist_service.qa.semantic_usd_diff import _values_equal
    inf = float("inf")
    assert _values_equal(inf, inf, 1e-6)
    assert _values_equal(-inf, -inf, 1e-6)
    assert not _values_equal(inf, -inf, 1e-6)
    assert not _values_equal(inf, 1.0, 1e-6)
    assert _values_equal([inf, 0.5], [inf, 0.5], 1e-6)


def test_render_prims_excluded_from_signature(tmp_path):
    from service.isaac_assist_service.qa.semantic_usd_diff import stage_signature
    p = tmp_path / "s.usda"
    p.write_text('''#usda 1.0
def Xform "World"
{
    def Cube "Box"
    {
        double size = 2
    }
}
def Scope "Render"
{
    custom bool omni_rtx_thing = true
}
''')
    sig = stage_signature(str(p))
    assert "/World/Box" in sig
    assert not any(k.startswith("/Render") for k in sig)
