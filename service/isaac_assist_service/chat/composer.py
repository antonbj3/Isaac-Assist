"""composer.py — foundation for multi-canonical COMPOSITION (chaining robust
templates into one scene). See docs/notes/COMPOSITION_AND_BRANCH_AUDIT.md (PART A)
and memory project_isaac_assist_composition_direction.

The composer places 2+ canonical templates in ONE Kit stage. Each template authors
absolute prim paths (/World/Franka, /World/Cube_1, ...) and absolute positions, so
two templates collide. This module supplies the two transforms the single-template
path (canonical_instantiator.execute_template_canonical) lacks:

  1. PRIM-PATH NAMESPACING — re-root every authored /World/<X> prim path under a
     per-instance subtree /World/<instance_root>/<X> so template A's /World/Cube_1
     can't clobber template B's. The /World/ prefix is the discriminator: it
     auto-excludes FILESYSTEM paths (output_path/file_path/hdri_path/...), which
     must NOT be re-rooted.
  2. COORDINATE OFFSET — add a per-instance origin_offset to authored position-type
     args so instances are spatially separated.

This operates on the CAPTURED tool-call list [(tool_name, kwargs), ...] that the
canonical capture phase produces, so it is UNIVERSAL (works for both role-based and
legacy code templates — by capture time all placeholders are concrete values).

Pure + side-effect-free + offline-testable. Phase_id isolation (already in
pick_place handlers) + deferred single world.reset() are handled by the eventual
compose_canonicals() wrapper, not here.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple

# kwargs whose value is a POSITION (3-vector, or 2-vector for nav goals) to which
# the per-instance origin_offset is added. Derived from the tool schemas. A value-
# only heuristic can't tell a position from any other 3-float list (orientation is
# 4, but colours/scales are 3), so positions are recognised by KWARG NAME.
POSITION_KWARGS = frozenset({
    "position", "target_position", "target", "pick_target", "drop_target",
    "home_target", "drop_pose", "place_position", "goal_position", "nav_goal",
    "start_position", "waypoint", "via_point",
})

# Filesystem-path kwargs that look path-like but must NEVER be re-rooted. (Belt-and-
# suspenders — the /World/ prefix check already excludes them since they don't start
# with /World/. Listed for clarity / future asserts.)
FILESYSTEM_PATH_KWARGS = frozenset({
    "output_path", "real_data_path", "checkpoint_path", "file_path", "hdri_path",
    "env_source_path", "watched_path_pattern", "reference_path",
})

_WORLD = "/World/"

# Tools whose per-robot+phase_id controller state must be ISOLATED per composed
# instance — without a distinct phase_id, two instances of the same template share
# the controller's subscription/state keys and the 2nd instance stalls (audit PART A:
# "the composer must pass a distinct phase_id per instance"). The composer sets
# phase_id = instance_root for these.
PHASE_ID_TOOLS = frozenset({
    "setup_pick_place_controller", "setup_cortex_behavior", "setup_nav_robot",
})


def reroot_prim_path(path: str, instance_root: str) -> str:
    """/World/Cube_1 -> /World/<instance_root>/Cube_1. Non-/World/ strings pass
    through unchanged (filesystem paths, ros topics, relative names, etc.)."""
    if not isinstance(path, str) or not path.startswith(_WORLD):
        return path
    if not instance_root:
        return path
    rest = path[len(_WORLD):]
    if not rest:  # exactly "/World/" -> keep
        return path
    # already namespaced under this root? idempotent.
    if rest.startswith(instance_root + "/"):
        return path
    return f"{_WORLD}{instance_root}/{rest}"


def _transform_value(key: str, value: Any, instance_root: str, offset) -> Any:
    """Re-root any /World/ prim paths anywhere in the value (str / list / dict),
    and offset the value if `key` is a position kwarg."""
    # position offset (by kwarg name)
    if key in POSITION_KWARGS and isinstance(value, (list, tuple)) and value \
            and all(isinstance(n, (int, float)) for n in value) and len(value) in (2, 3):
        return [value[i] + (offset[i] if i < len(offset) else 0.0) for i in range(len(value))]
    # prim-path re-rooting (recursive over str / list / dict)
    if isinstance(value, str):
        return reroot_prim_path(value, instance_root)
    if isinstance(value, list):
        return [_transform_value(key, v, instance_root, offset) for v in value]
    if isinstance(value, tuple):
        return tuple(_transform_value(key, v, instance_root, offset) for v in value)
    if isinstance(value, dict):
        return {k: _transform_value(k, v, instance_root, offset) for k, v in value.items()}
    return value


def namespace_and_offset_calls(
    captured: List[Tuple[str, Dict[str, Any]]],
    instance_root: str,
    origin_offset=(0.0, 0.0, 0.0),
) -> List[Tuple[str, Dict[str, Any]]]:
    """Transform a captured tool-call list for one composed instance:
    re-root every /World/ prim path under instance_root + add origin_offset to
    position args. Returns a new list (does not mutate input)."""
    off = tuple(origin_offset) + (0.0,) * (3 - len(origin_offset)) if len(origin_offset) < 3 else tuple(origin_offset)
    out: List[Tuple[str, Dict[str, Any]]] = []
    for tool, kwargs in captured:
        nk = {k: _transform_value(k, v, instance_root, off) for k, v in kwargs.items()}
        # isolate per-instance controller state (distinct phase_id) so two instances
        # of the same template don't share subscription/state keys (2nd one stalls).
        if tool in PHASE_ID_TOOLS or "phase_id" in nk:
            nk["phase_id"] = instance_root
        # NOTE (2026-06-15): a per-instance planner-scope injection (arm_scope=instance_root
        # -> separate cuRobo MotionPlanner per cell) was tried + REVERTED — MEASURED to give
        # ZERO benefit (the 2nd-arm fling persisted identically with separate planners). The
        # real (partial) fix was the move-token clock-freeze in pick_place.py (cont.59). Per-arm
        # planners remain a CANDIDATE for the dedicated multi-arm session IF they enable
        # relaxing the plan/move serialization lock (true concurrency) — not before that's tested.
        out.append((tool, nk))
    return out


SOURCE_KWARGS = ("source_paths", "cube_paths")


def apply_source_override(captured, source_paths, dest_override=None):
    """CHAIN wiring: make a composed stage SOURCE another stage's outputs (end-state
    -> start-state handoff). Replaces the pick-place controller's source_paths (and
    cube_paths) with `source_paths` (e.g. the prior instance's delivered cube paths,
    already namespaced to that instance), so stage-B picks the cubes stage-A delivered
    rather than its own. Optionally override destination_path too. Returns a new list.

    This is the cross-instance reference the parallel namespacing deliberately does NOT
    do (parallel keeps each instance self-contained); a CHAIN opts in per stage.
    """
    out = []
    for tool, kwargs in captured:
        nk = dict(kwargs)
        if tool == "setup_pick_place_controller":
            for sk in SOURCE_KWARGS:
                if sk in nk:
                    nk[sk] = list(source_paths)
            if dest_override is not None and "destination_path" in nk:
                nk["destination_path"] = dest_override
        out.append((tool, nk))
    return out


# ── LAYER 1: layout solver (2026-06-15) ────────────────────────────────────
# The primary composition fix. compose_canonicals takes a caller-supplied origin_offset;
# the offline harnesses hardcoded offset = 2.5*idx — BELOW the authored conveyor footprints
# (CP-01 belt x-span 3.0, CP-09 4.0, CP-07 20.0) -> instances' belts OVERLAP -> an
# occasionally-unpicked cube rides the merged belt off the end (MEASURED cont.62-63, the 1/3
# failure). This solver derives each template's axis footprint from its authored scene prims
# and lays cells out so footprints + a throw/landing pad never overlap. Pure + offline (no Kit).
import re as _re

_GEOM_FNS = ("create_prim", "create_bin", "create_conveyor", "create_rotary_table", "robot_wizard")
_DEFAULT_HALF = 0.3          # half-extent for a prim with no parseable scale/size
_FALLBACK_FOOT = (-1.5, 1.5)  # conservative footprint for legacy/unparseable templates (flagged)


def template_footprint(template, axis="x"):
    """Axis (x|y) world extent (lo, hi, known) of a template's authored scene prims, parsed
    from its `code`. Conveyor scale dominates. known=False (+ a conservative default) when no
    geometry is parseable (legacy roles={} / absolute-path templates) so the caller can flag the
    spacing as a guess rather than trust it."""
    ai = {"x": 0, "y": 1, "z": 2}.get(axis, 0)
    code = (template or {}).get("code") or ""
    lo = hi = None
    for fn in _GEOM_FNS:
        for m in _re.finditer(_re.escape(fn) + r"\(([^)]*(?:\([^)]*\)[^)]*)*)\)", code):
            args = m.group(1)
            pm = _re.search(r"position\s*=\s*\[([^\]]+)\]", args)
            sm = _re.search(r"(?:scale|size)\s*=\s*\[([^\]]+)\]", args)
            if not pm:
                continue
            try:
                pv = [float(x) for x in pm.group(1).split(",")]
            except ValueError:
                continue
            if ai >= len(pv):
                continue
            half = _DEFAULT_HALF
            if sm:
                try:
                    sv = [float(x) for x in sm.group(1).split(",")]
                    if ai < len(sv):
                        half = sv[ai] / 2.0
                except ValueError:
                    pass
            l, h = pv[ai] - half, pv[ai] + half
            lo = l if lo is None else min(lo, l)
            hi = h if hi is None else max(hi, h)
    if lo is None:
        return (_FALLBACK_FOOT[0], _FALLBACK_FOOT[1], False)
    return (lo, hi, True)


def compute_layout_offsets(templates, axis="x", throw_pad=2.5, clearance=0.6):
    """Per-instance origin_offset so authored footprints + a throw/landing pad never overlap.
    Replaces the hardcoded 2.5*idx. `throw_pad` is the gap between adjacent footprints that
    absorbs a thrown/rolled-off object (MEASURED: a ride-off cube landed ~2.3m past the belt end,
    OUTSIDE the footprint bbox — so footprint alone is insufficient). Returns a list of
    {offset:(dx,dy,dz), footprint:[lo,hi], known:bool} dicts, one per template, in order.
    Lays cells out along `axis`; each cell's footprint-min is placed at the running cursor, then
    the cursor advances past it by throw_pad+clearance."""
    ai = {"x": 0, "y": 1, "z": 2}.get(axis, 0)
    out = []
    cursor = None   # world position where the NEXT cell's footprint-min must start
    for t in templates:
        lo, hi, known = template_footprint(t, axis)
        if cursor is None:
            off = 0.0                            # first cell: unshifted (natural authored pos)
        else:
            off = cursor - lo                    # shift this template's lo to the cursor
        vec = [0.0, 0.0, 0.0]
        vec[ai] = round(off, 3)
        out.append({"offset": tuple(vec), "footprint": [round(lo, 2), round(hi, 2)], "known": known})
        cursor = off + hi + throw_pad + clearance
    return out


# ── LAYER 2: precondition check (2026-06-15) ───────────────────────────────
# Convert the SILENT-fusion failure classes into LOUD, explicit findings BEFORE a composed
# scene is built (serves "false positives = progress poison"). Pure + offline. Returns a list of
# {severity, kind, template, detail}: 'refuse' = a real fusion/contention risk the builder must
# refuse or serialize; 'warn' = inspect. The REFUSAL POLICY (refuse vs serialize-fallback) is a
# product decision (Anton) — this layer only DETECTS + reports.
def precondition_check(templates, layout="parallel"):
    issues = []
    curobo_idxs = []
    for i, t in enumerate(templates or []):
        code = (t or {}).get("code") or ""
        tid = (t or {}).get("task_id")
        mc = ((t or {}).get("motion_controllers") or {}).get("verified") or []
        # (a) NAMESPACING-ESCAPE: run_usd_script bakes absolute /World/ paths inside a body string
        # that namespace_and_offset_calls (which only re-roots captured kwargs) cannot reach ->
        # template A's /World/Cube_1 clobbers template B's. (CP-07/08/22 class.)
        if "run_usd_script" in code and _WORLD in code:
            issues.append({"severity": "refuse", "kind": "namespacing_escape", "template": tid,
                           "detail": "run_usd_script bakes absolute %s paths -> not re-rooted -> prim collision across instances" % _WORLD})
        # (b) EXCLUSIVE cuRobo planner: the plan/move locks are process-global (per-instance scope
        # was MEASURED ineffective + reverted). >1 concurrent in a parallel layout -> contention.
        if ("curobo" in mc) or ("_gen_pick_place_curobo" in code) or ("setup_pick_place_controller" in code):
            curobo_idxs.append(tid or i)
        # (c) POSITION-LIKE kwarg outside POSITION_KWARGS -> namespaced but NOT offset -> placed at
        # absolute world coords (silently fused). Best-effort: a *position*-suffixed kwarg not covered.
        for m in _re.finditer(r"(\w+)\s*=\s*\[\s*-?\d", code):
            k = m.group(1)
            if k.endswith("position") and k not in POSITION_KWARGS:
                issues.append({"severity": "warn", "kind": "uncovered_position_kwarg", "template": tid,
                               "detail": "kwarg '%s' looks positional but is not in POSITION_KWARGS -> may not be offset (verify)" % k})
                break
    if layout == "parallel" and len(curobo_idxs) > 1:
        issues.append({"severity": "refuse", "kind": "concurrent_curobo", "template": None,
                       "detail": "%d instances share the process-global cuRobo plan/move lock in a 'parallel' layout (%s) -> serialize or expect contention ride-off (per-instance planner scope was measured ineffective)" % (len(curobo_idxs), curobo_idxs)})
    return issues


def _selftest():
    cap = [
        ("robot_wizard", {"robot_name": "carter", "dest_path": "/World/Carter", "position": [0.0, 0.0, 0.3]}),
        ("setup_pick_place_controller", {
            "robot_path": "/World/Franka",
            "source_paths": ["/World/Cube_1", "/World/Cube_2"],
            "destination_path": "/World/StackBin",
            "pick_target": [-1.4, 0.4, 0.835],
            "planning_obstacles": ["/World/Table", "/World/ConveyorBelt"],
            "ee_link": "/World/Franka/panda_hand",
            "destination_map": {"red": "/World/RedBin", "blue": "/World/BlueBin"},
        }),
        ("export_nav2_map", {"output_path": "workspace/maps/x.pgm", "resolution": 0.05}),  # filesystem path: must NOT re-root
        ("set_attribute", {"prim_path": "/World/inst0/Foo", "value": 1.0}),  # already-namespaced: idempotent
    ]
    out = dict((t, k) for t, k in namespace_and_offset_calls(cap, "inst0", (10.0, 0.0, 0.0)))
    rw = out["robot_wizard"]
    assert rw["dest_path"] == "/World/inst0/Carter", rw
    assert rw["position"] == [10.0, 0.0, 0.3], rw
    spc = out["setup_pick_place_controller"]
    assert spc["robot_path"] == "/World/inst0/Franka", spc
    assert spc["source_paths"] == ["/World/inst0/Cube_1", "/World/inst0/Cube_2"], spc
    assert spc["destination_path"] == "/World/inst0/StackBin", spc
    assert spc["pick_target"] == [9.0 - 0.4, 0.4, 0.835] or spc["pick_target"] == [-1.4 + 10.0, 0.4, 0.835], spc
    assert spc["planning_obstacles"] == ["/World/inst0/Table", "/World/inst0/ConveyorBelt"], spc
    assert spc["ee_link"] == "/World/inst0/Franka/panda_hand", spc
    assert spc["destination_map"] == {"red": "/World/inst0/RedBin", "blue": "/World/inst0/BlueBin"}, spc
    nav = out["export_nav2_map"]
    assert nav["output_path"] == "workspace/maps/x.pgm", nav  # filesystem path untouched
    assert out["set_attribute"]["prim_path"] == "/World/inst0/Foo", "idempotent re-root"
    # chain wiring: stage-B sources stage-A's delivered cubes
    chained = dict((t, k) for t, k in apply_source_override(
        namespace_and_offset_calls(cap, "inst1", (0.0, -0.9, 0.0)),
        source_paths=["/World/inst0/Cube_1", "/World/inst0/Cube_2"],
        dest_override="/World/inst1/FinalBin"))
    spc2 = chained["setup_pick_place_controller"]
    assert spc2["source_paths"] == ["/World/inst0/Cube_1", "/World/inst0/Cube_2"], spc2  # cross-instance source
    assert spc2["destination_path"] == "/World/inst1/FinalBin", spc2
    assert spc2["robot_path"] == "/World/inst1/Franka", spc2  # robot still namespaced to inst1
    print("composer selftest OK (namespacing + offset + phase_id + chain source-override)")


if __name__ == "__main__":
    _selftest()
