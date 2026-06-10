"""P0-18 — unit tests for the honest-delivery-gate pure logic.

Covers the testable core of ``simulate_traversal_check`` that was factored
out of the Kit-bound codegen into
``service.isaac_assist_service.qa.honest_gate``:

  * routing-map normalization (targets / routing / fallback)
  * per-cube classification + misroute detection
  * completeness aggregation (any / all / min_delivered)
  * the end-to-end ``grade`` BACKWARDS-COMPAT contract (legacy verdict
    reproduced byte-for-byte when no routing + completeness='any')
  * the ``scripts/qa/lint_gate_coverage`` workpiece-exclusion lint

These mirror the logic inlined into the codegen string so the live gate
and the unit tests grade identically.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.l0

from service.isaac_assist_service.qa.honest_gate import (
    aggregate_completeness,
    all_targets,
    classify_cube,
    grade,
    normalize_routing,
)


# ---------------------------------------------------------------------------
# normalize_routing
# ---------------------------------------------------------------------------

def test_normalize_routing_empty_falls_back_to_global():
    cubes = ["/W/C1", "/W/C2"]
    out = normalize_routing(cubes, "/W/Bin")
    assert out == {"/W/C1": "/W/Bin", "/W/C2": "/W/Bin"}


def test_normalize_routing_targets_map():
    cubes = ["/W/C1", "/W/C2", "/W/C3"]
    out = normalize_routing(cubes, "/W/Bin", targets={"/W/C1": "/W/BinA", "/W/C2": "/W/BinB"})
    # C3 not named -> falls back to global.
    assert out == {"/W/C1": "/W/BinA", "/W/C2": "/W/BinB", "/W/C3": "/W/Bin"}


def test_normalize_routing_list_form():
    cubes = ["/W/C1", "/W/C2"]
    routing = [{"cube": "/W/C1", "target": "/W/BinA"}, {"cube": "/W/C2", "target": "/W/BinB"}]
    out = normalize_routing(cubes, "/W/Bin", routing=routing)
    assert out == {"/W/C1": "/W/BinA", "/W/C2": "/W/BinB"}


def test_normalize_routing_targets_wins_over_routing_on_conflict():
    cubes = ["/W/C1"]
    out = normalize_routing(
        cubes, "/W/Bin",
        targets={"/W/C1": "/W/BinA"},
        routing=[{"cube": "/W/C1", "target": "/W/BinZ"}],
    )
    assert out["/W/C1"] == "/W/BinA"


def test_all_targets_distinct_and_ordered():
    pct = {"/W/C1": "/W/BinA", "/W/C2": "/W/BinB", "/W/C3": "/W/BinA"}
    assert all_targets(pct) == ["/W/BinA", "/W/BinB"]


# ---------------------------------------------------------------------------
# classify_cube
# ---------------------------------------------------------------------------

def _delivered_bundle(**over):
    b = {"in_xy": True, "above_floor": True, "at_rest": True,
         "upright_ok": True, "support": "/W/BinA/floor", "final": [0, 0, 1]}
    b.update(over)
    return b


def test_classify_cube_delivered():
    r = classify_cube("/W/C1", _delivered_bundle(), "/W/BinA", ["/W/BinA", "/W/BinB"])
    assert r["delivered"] is True
    assert r["misrouted"] is False
    assert r["actual_location"] == "/W/BinA"
    assert r["target"] == "/W/BinA"


def test_classify_cube_not_in_xy_not_delivered():
    r = classify_cube("/W/C1", _delivered_bundle(in_xy=False), "/W/BinA", ["/W/BinA"])
    assert r["delivered"] is False
    assert r["misrouted"] is False


def test_classify_cube_not_at_rest_not_delivered():
    r = classify_cube("/W/C1", _delivered_bundle(at_rest=False), "/W/BinA", ["/W/BinA"])
    assert r["delivered"] is False


def test_classify_cube_upright_gate():
    r = classify_cube("/W/C1", _delivered_bundle(upright_ok=False), "/W/BinA", ["/W/BinA"])
    assert r["delivered"] is False


def test_classify_cube_misrouted_into_other_target():
    # In BinA's bbox physically but raycast says it's resting in BinB.
    b = _delivered_bundle(support="/W/BinB/floor")
    r = classify_cube("/W/C1", b, "/W/BinA", ["/W/BinA", "/W/BinB"])
    assert r["misrouted"] is True
    assert r["actual_location"] == "/W/BinB"
    assert r["delivered"] is False  # misroute overrides in_xy success


def test_classify_cube_support_is_target_prim_itself():
    b = _delivered_bundle(support="/W/BinA")  # exact, not descendant
    r = classify_cube("/W/C1", b, "/W/BinA", ["/W/BinA", "/W/BinB"])
    assert r["misrouted"] is False
    assert r["delivered"] is True


def test_classify_cube_no_support_hit_not_misrouted():
    b = _delivered_bundle(support=None)
    r = classify_cube("/W/C1", b, "/W/BinA", ["/W/BinA", "/W/BinB"])
    assert r["misrouted"] is False
    assert r["actual_location"] is None
    assert r["delivered"] is True  # bbox+rest+upright still pass


def test_classify_cube_not_at_rest_skips_misroute_check():
    # A moving cube cannot be "misrouted" (it hasn't come to rest anywhere).
    b = _delivered_bundle(at_rest=False, support="/W/BinB/floor")
    r = classify_cube("/W/C1", b, "/W/BinA", ["/W/BinA", "/W/BinB"])
    assert r["misrouted"] is False


# ---------------------------------------------------------------------------
# aggregate_completeness
# ---------------------------------------------------------------------------

def _cubes(delivered_flags, misrouted_flags=None):
    misrouted_flags = misrouted_flags or [False] * len(delivered_flags)
    return [
        {"cube": f"/W/C{i}", "delivered": d, "misrouted": m}
        for i, (d, m) in enumerate(zip(delivered_flags, misrouted_flags))
    ]


def test_aggregate_any_one_of_three():
    agg = aggregate_completeness(_cubes([True, False, False]), "any")
    assert agg["success"] is True
    assert agg["delivered_count"] == 1
    assert agg["total"] == 3
    assert agg["min_required"] == 1
    assert agg["completeness_mode"] == "any"


def test_aggregate_any_none_delivered_fails():
    agg = aggregate_completeness(_cubes([False, False]), "any")
    assert agg["success"] is False


def test_aggregate_all_requires_every_cube():
    assert aggregate_completeness(_cubes([True, True, True]), "all")["success"] is True
    agg = aggregate_completeness(_cubes([True, True, False]), "all")
    assert agg["success"] is False
    assert agg["min_required"] == 3
    assert agg["completeness_mode"] == "all"


def test_aggregate_min_delivered():
    agg = aggregate_completeness(_cubes([True, True, False, False]), {"min_delivered": 2})
    assert agg["success"] is True
    assert agg["min_required"] == 2
    assert agg["completeness_mode"] == "min_delivered=2"
    agg2 = aggregate_completeness(_cubes([True, False, False, False]), {"min_delivered": 2})
    assert agg2["success"] is False


def test_aggregate_min_delivered_clamped_to_total():
    agg = aggregate_completeness(_cubes([True, True]), {"min_delivered": 9})
    assert agg["min_required"] == 2  # clamped


def test_aggregate_int_completeness():
    agg = aggregate_completeness(_cubes([True, True, False]), 2)
    assert agg["min_required"] == 2
    assert agg["success"] is True


def test_aggregate_unknown_string_falls_back_to_any():
    agg = aggregate_completeness(_cubes([True, False]), "garbage")
    assert agg["min_required"] == 1  # never tighten on unknown input
    assert agg["success"] is True


def test_aggregate_misrouted_count_reported():
    agg = aggregate_completeness(_cubes([False, True], [True, False]), "any")
    assert agg["misrouted_count"] == 1


def test_aggregate_empty_never_succeeds():
    agg = aggregate_completeness([], "any")
    assert agg["success"] is False
    assert agg["total"] == 0


# ---------------------------------------------------------------------------
# grade — end-to-end + BACKWARDS-COMPAT contract
# ---------------------------------------------------------------------------

def test_grade_legacy_any_one_of_many_is_byte_identical():
    # Legacy multi-cube: success = bool(delivered) and upright_ok.
    cubes = ["/W/C1", "/W/C2", "/W/C3"]
    measured = {
        "/W/C1": _delivered_bundle(support=None),          # delivered
        "/W/C2": _delivered_bundle(in_xy=False, support=None),  # not
        "/W/C3": _delivered_bundle(at_rest=False, support=None),  # not
    }
    out = grade(cubes, measured, "/W/Bin")  # no routing, completeness default
    assert out["success"] is True
    assert out["delivered_count"] == 1
    assert out["completeness_mode"] == "any"
    assert out["routing_active"] is False
    # No cube can be misrouted in single-target mode (other_targets is empty).
    assert all(c["misrouted"] is False for c in out["per_cube"])


def test_grade_legacy_all_fail_is_fail():
    cubes = ["/W/C1", "/W/C2"]
    measured = {
        "/W/C1": _delivered_bundle(in_xy=False, support=None),
        "/W/C2": _delivered_bundle(above_floor=False, support=None),
    }
    out = grade(cubes, measured, "/W/Bin")
    assert out["success"] is False
    assert out["delivered_count"] == 0


def test_grade_completeness_all_tightens_without_routing():
    cubes = ["/W/C1", "/W/C2"]
    measured = {
        "/W/C1": _delivered_bundle(support=None),
        "/W/C2": _delivered_bundle(in_xy=False, support=None),
    }
    # legacy 'any' would pass (1 delivered); 'all' must fail.
    assert grade(cubes, measured, "/W/Bin", completeness="any")["success"] is True
    assert grade(cubes, measured, "/W/Bin", completeness="all")["success"] is False


def test_grade_routing_per_bin_correct():
    cubes = ["/W/C1", "/W/C2"]
    # Each cube rests in its OWN bin.
    measured = {
        "/W/C1": _delivered_bundle(support="/W/BinA/floor"),
        "/W/C2": _delivered_bundle(support="/W/BinB/floor"),
    }
    out = grade(cubes, measured, "/W/Bin",
                targets={"/W/C1": "/W/BinA", "/W/C2": "/W/BinB"},
                completeness="all")
    assert out["routing_active"] is True
    assert out["success"] is True
    assert out["delivered_count"] == 2
    assert out["misrouted_count"] == 0


def test_grade_routing_detects_misroute():
    cubes = ["/W/C1", "/W/C2"]
    # C2 ended up in BinA (its target was BinB) -> misrouted -> not delivered.
    measured = {
        "/W/C1": _delivered_bundle(support="/W/BinA/floor"),
        "/W/C2": _delivered_bundle(support="/W/BinA/floor"),
    }
    out = grade(cubes, measured, "/W/Bin",
                targets={"/W/C1": "/W/BinA", "/W/C2": "/W/BinB"},
                completeness="all")
    assert out["success"] is False
    assert out["misrouted_count"] == 1
    c2 = next(c for c in out["per_cube"] if c["cube"] == "/W/C2")
    assert c2["misrouted"] is True
    assert c2["actual_location"] == "/W/BinA"
    assert c2["delivered"] is False


def test_grade_route_all_to_one_bin_degenerate_caught():
    # The motivating bug: a 2-way sort where the controller dumps BOTH cubes
    # into BinA. Under per-bin routing + 'all', this MUST fail (C2 misrouted).
    cubes = ["/W/C1", "/W/C2"]
    measured = {
        "/W/C1": _delivered_bundle(support="/W/BinA/floor"),
        "/W/C2": _delivered_bundle(support="/W/BinA/floor"),
    }
    out = grade(cubes, measured, "/W/Bin",
                routing=[{"cube": "/W/C1", "target": "/W/BinA"},
                         {"cube": "/W/C2", "target": "/W/BinB"}],
                completeness="all")
    assert out["success"] is False


def test_grade_per_cube_payload_shape():
    cubes = ["/W/C1"]
    measured = {"/W/C1": _delivered_bundle(support="/W/BinA/floor")}
    out = grade(cubes, measured, "/W/Bin", targets={"/W/C1": "/W/BinA"})
    pc = out["per_cube"][0]
    for key in ("cube", "delivered", "target", "actual_location", "misrouted"):
        assert key in pc
    for key in ("delivered_count", "total", "completeness_mode", "success"):
        assert key in out


def test_grade_skips_cube_with_no_measurement():
    cubes = ["/W/C1", "/W/C2"]
    measured = {"/W/C1": _delivered_bundle(support=None)}  # C2 missing
    out = grade(cubes, measured, "/W/Bin")
    assert out["total"] == 1
    assert out["delivered_count"] == 1


# ---------------------------------------------------------------------------
# lint_gate_coverage
# ---------------------------------------------------------------------------

def _load_lint():
    import importlib.util
    import os
    here = os.path.dirname(__file__)
    path = os.path.join(here, "..", "scripts", "qa", "lint_gate_coverage.py")
    spec = importlib.util.spec_from_file_location("lint_gate_coverage", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lint_detects_excluded_workpiece():
    lint = _load_lint()
    tpl = {
        "task_id": "TST-1",
        "code": (
            'create_prim(prim_path="/World/Ground", prim_type="Cube")\n'
            'create_prim(prim_path="/World/Cube_1", prim_type="Cube", size=0.05)\n'
            'create_prim(prim_path="/World/Cube_2", prim_type="Cube", size=0.05)\n'
        ),
        "simulate_args": {"cube_paths": ["/World/Cube_1"], "target_path": "/World/Bin"},
    }
    r = lint.lint_template(tpl, "tst.json")
    assert r["ok"] is False
    assert r["missing_from_gate"] == ["/World/Cube_2"]
    assert "/World/Ground" not in r["authored_workpieces"]  # structural excluded


def test_lint_full_coverage_passes():
    lint = _load_lint()
    tpl = {
        "task_id": "TST-2",
        "code": (
            'create_prim(prim_path="/World/Cube_1", prim_type="Cube")\n'
            'create_prim(prim_path="/World/Cube_2", prim_type="Cube")\n'
        ),
        "simulate_args": {"cube_paths": ["/World/Cube_1", "/World/Cube_2"], "target_path": "/World/Bin"},
    }
    r = lint.lint_template(tpl, "tst.json")
    assert r["ok"] is True
    assert r["missing_from_gate"] == []


def test_lint_role_defaults_workpieces_counted():
    lint = _load_lint()
    tpl = {
        "task_id": "TST-3",
        "role_defaults": {"workpieces": [{"path": "/World/Item_1"}, {"path": "/World/Item_2"}]},
        "simulate_args": {"cube_path": "/World/Item_1", "target_path": "/World/Bin"},
    }
    r = lint.lint_template(tpl, "tst.json")
    assert r["ok"] is False
    assert r["missing_from_gate"] == ["/World/Item_2"]


def test_lint_single_cube_path_str_coverage():
    lint = _load_lint()
    tpl = {
        "task_id": "TST-4",
        "code": 'create_prim(prim_path="/World/Cube_1", prim_type="Cube")\n',
        "simulate_args": {"cube_path": "/World/Cube_1", "target_path": "/World/Bin"},
    }
    r = lint.lint_template(tpl, "tst.json")
    assert r["ok"] is True


def test_lint_no_gate_is_out_of_scope():
    lint = _load_lint()
    tpl = {"task_id": "TST-5", "code": 'create_prim(prim_path="/World/Cube_1", prim_type="Cube")\n'}
    r = lint.lint_template(tpl, "tst.json")
    assert r["has_gate"] is False
    assert r["ok"] is True  # not gated -> not flagged


# --- Conductor QC addition: cover the HANDLER path (the worktree's own tests
# --- never executed it — a broken relative import slipped through them).

async def test_handler_emits_codegen_with_correct_flags(monkeypatch):
    from service.isaac_assist_service.chat.tools import kit_tools
    captured = {}

    async def _stub_queue(code, desc, **kw):
        captured["code"] = code
        return {"queued": True, "code": code, "description": desc, "type": "code_patch"}

    monkeypatch.setattr(kit_tools, "queue_exec_patch", _stub_queue)
    from service.isaac_assist_service.chat.tools.handlers import diagnostics as d

    # routing + completeness=all -> honest flags in the emitted script
    await d._handle_simulate_traversal_check({
        "cube_paths": ["/World/Cube_1", "/World/Cube_2"],
        "targets": {"/World/Cube_1": "/World/BinA", "/World/Cube_2": "/World/BinB"},
        "completeness": "all", "target_path": "/World/BinA", "duration_s": 5,
    })
    import ast
    code = captured["code"]
    ast.parse(code)
    assert "routing_active = True" in code
    assert "completeness = 'all'" in code
    assert "_cube_support(cp, assigned)" in code  # misroute uses the verified raycast

    # legacy call -> flags exactly legacy (byte-compat guarantee)
    await d._handle_simulate_traversal_check({
        "cube_path": "/World/C", "target_path": "/World/B", "duration_s": 5,
    })
    code2 = captured["code"]
    ast.parse(code2)
    assert "routing_active = False" in code2
    assert "completeness = 'any'" in code2


# --- transitive support (stacked deliveries) — live CP-NEW-inspect-reject ---

def test_transitive_support_resolves_tower_to_bin():
    from service.isaac_assist_service.qa.honest_gate import resolve_transitive_support
    chain = {"/W/Cube_1": "/W/Cube_2", "/W/Cube_2": "/W/Cube_3",
             "/W/Cube_3": "/W/PassBin/Floor"}
    r = resolve_transitive_support(chain)
    assert r == {"/W/Cube_1": "/W/PassBin/Floor",
                 "/W/Cube_2": "/W/PassBin/Floor",
                 "/W/Cube_3": "/W/PassBin/Floor"}


def test_transitive_support_cycle_resolves_to_none():
    from service.isaac_assist_service.qa.honest_gate import resolve_transitive_support
    r = resolve_transitive_support({"/W/A": "/W/B", "/W/B": "/W/A",
                                    "/W/C": "/W/Table"})
    assert r["/W/A"] is None and r["/W/B"] is None and r["/W/C"] == "/W/Table"


def test_stack_misroute_is_LABELED_never_verdict_bearing():
    """QA-audit 2026-06-10 natt: transitive resolution EXECUTED two
    verdict-flips (adjacent-bin xy-overlap; chain through an assigned
    cube-target) -> resolution is diagnosis-LABELING only. The verdict-
    bearing misrouted uses the RAW support exactly as P0-18 shipped; the
    tower case still FAILS via completeness, and the label points at the
    carrying bin for the fix loop."""
    from service.isaac_assist_service.qa.honest_gate import grade
    measured = {
        "/W/Cube_3": {"in_xy": False, "above_floor": True, "at_rest": True,
                      "support": "/W/Cube_4", "final": [0.5, -0.3, 0.95]},
        "/W/Cube_4": {"in_xy": True, "above_floor": True, "at_rest": True,
                      "support": "/W/PassBin/Floor", "final": [0.5, -0.3, 0.85]},
    }
    out = grade(["/W/Cube_3", "/W/Cube_4"], measured,
                global_target="/W/PassBin",
                targets={"/W/Cube_3": "/W/RejectBin"},
                completeness="all")
    c3 = next(c for c in out["per_cube"] if c["cube"] == "/W/Cube_3")
    assert c3["misrouted"] is False                  # raw support = a cube
    assert c3["misrouted_label"] is True             # resolved chain -> PassBin
    assert c3["actual_location_label"] == "/W/PassBin"
    assert c3["support"] == "/W/PassBin/Floor"       # resolved (reporting)
    assert c3["support_raw"] == "/W/Cube_4"
    assert c3["delivered"] is False                  # not in RejectBin xy
    assert out["success"] is False                   # completeness=all


def test_resolution_can_never_flip_delivered():
    """CE1 from the audit: xy inside ASSIGNED bin but stacked on a tower
    based in ANOTHER bin — delivered must match the raw-support behavior
    (True), with the conflict surfaced as a label."""
    from service.isaac_assist_service.qa.honest_gate import grade
    measured = {
        "/W/C2": {"in_xy": True, "above_floor": True, "at_rest": True,
                  "support": "/W/C1", "final": [0.1, 0, 0.9]},
        "/W/C1": {"in_xy": True, "above_floor": True, "at_rest": True,
                  "support": "/W/BinA/Floor", "final": [0.05, 0, 0.85]},
    }
    out = grade(["/W/C2", "/W/C1"], measured, global_target="/W/BinA",
                targets={"/W/C2": "/W/BinB"}, completeness="any")
    c2 = next(c for c in out["per_cube"] if c["cube"] == "/W/C2")
    assert c2["misrouted"] is False and c2["delivered"] is True  # as shipped
    assert c2["misrouted_label"] is True             # the conflict, surfaced


def test_resolve_color_routing_maps_classes_to_bins():
    """P0-18b: the gate finally reads the controller's routing vocabulary."""
    from service.isaac_assist_service.qa.honest_gate import resolve_color_routing
    targets = resolve_color_routing(
        {"GREEN": "/W/PassBin", "red": "/W/RejectBin"},
        {"/W/C1": "green", "/W/C2": "Red", "/W/C3": None, "/W/C4": "blue"})
    assert targets == {"/W/C1": "/W/PassBin", "/W/C2": "/W/RejectBin"}
    assert resolve_color_routing({}, {"/W/C1": "green"}) == {}
    assert resolve_color_routing({"green": "/W/B"}, {}) == {}
