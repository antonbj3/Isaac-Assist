"""L0 tests for the code<->code_template drift audit [P2-07 follow-up]."""
import pytest

from scripts.qa.audit_code_template_drift import capture, classify

pytestmark = pytest.mark.l0


def test_capture_handles_loops_and_fstrings():
    calls, errs = capture(
        'for i in range(3):\n'
        '    create_prim(prim_path=f"/W/Cube_{i}", prim_type="Cube")\n'
        '    set_semantic_label(prim_path=f"/W/Cube_{i}", class_name="box")\n')
    assert calls.count("create_prim") == 3
    assert calls.count("set_semantic_label") == 3
    assert errs == []


def test_classify_baseline_only_vs_content_drift():
    base = {"roles": {"r": {}}, "role_defaults": {"r": {}}}
    t1 = dict(base, code="create_scene_baseline()\ncreate_bin(prim_path='/W/B')",
              code_template="create_prim(prim_path='/W/T', prim_type='Cube')\ncreate_bin(prim_path='/W/B')")
    assert classify(t1)["class"] == "BASELINE_ONLY"
    t2 = dict(base, code="create_bin(prim_path='/W/B')\nset_semantic_label(prim_path='/W/B', class_name='x')",
              code_template="create_bin(prim_path='/W/B')")
    r2 = classify(t2)
    assert r2["class"] == "CONTENT_DRIFT"
    assert r2["missing_in_ct"] == {"set_semantic_label": 1}
    t3 = dict(base, code="create_bin(prim_path='/W/B')",
              code_template="create_bin(prim_path='/W/B')")
    assert classify(t3)["class"] == "IN_SYNC"
    assert classify({"code": "x=1"}) is None        # no role path -> no drift


def test_kit_prep_stays_repaired():
    """2026-06-10 natt: kit-prep's ct was regenerated from code via reverse
    placeholder substitution (roundtrip-exact). It must STAY in sync — this
    template is the type specimen of the CONTENT_DRIFT class."""
    import json
    t = json.load(open("workspace/templates/CP-NEW-kit-prep-vision-gate.json"))
    assert classify(t)["class"] == "IN_SYNC"
    # the roundtrip property that PROVES the repair
    from service.isaac_assist_service.chat.canonical_instantiator import (
        substitute_role_placeholders)
    assert substitute_role_placeholders(
        t["code_template"], t["role_defaults"]) == t["code"]
