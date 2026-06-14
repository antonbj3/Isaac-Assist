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
        out.append((tool, nk))
    return out


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
    print("composer selftest OK")


if __name__ == "__main__":
    _selftest()
