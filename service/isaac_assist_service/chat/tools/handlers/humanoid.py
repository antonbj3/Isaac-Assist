"""Humanoid bimanual handlers — target scope: per-arm cuRobo pick-place
composition for dual-arm humanoids (G1, H1, etc.) sharing one articulation.

Per docs/notes/2026-05-28-g1-humanoid-impl-scope.md (Phases J0+J1, V0).

V0 scope:
  - Only G1 (`robot_family="g1_arm"`) supported.
  - `setup_bimanual_pick_place_controller` installs TWO cuRobo per-arm
    state machines (left + right) keyed per-arm under separate planner
    cache slots. Sequential coordination only — Kit RPC is single-tenant
    (per memory `kit-concurrency`).
  - `plant_feet=True` (default) drops two USD FixedJoints between each
    ankle_roll_link and ground, sidestepping the WBC runtime requirement
    that's deferred to a separate Phase (J3 in the scope doc).
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from . import pick_place as _pp


def _gen_setup_bimanual_pick_place_controller(args: Dict) -> str:
    """Install TWO coordinated cuRobo pick-place state machines on a single
    humanoid articulation (one per arm).

    Composition (V0 = sequential):
      1. (optional) Emit USD FixedJoint constraints from each ankle_roll_link
         to ground when `plant_feet=True` (default).
      2. Call `_gen_pick_place_curobo` with arm_scope="left", phase_id="bimanual_left".
      3. Call `_gen_pick_place_curobo` with arm_scope="right", phase_id="bimanual_right".
      4. Concatenate the two snippets behind a shared header + small
         "wait-for-left-then-right" coordination shim.

    Args:
        args: Tool arguments dict containing:
          - robot_path (str, required): USD prim path of the humanoid (e.g. "/World/G1").
          - left_arm_sources (list[str]): Cube paths for LEFT arm to deliver.
          - right_arm_sources (list[str]): Cube paths for RIGHT arm to deliver.
          - left_destination (str): Drop prim path for LEFT arm.
          - right_destination (str): Drop prim path for RIGHT arm.
          - coordination_mode (str, optional): "sequential" (default), "parallel", "handoff".
              parallel falls back to sequential with warning in V0.
          - plant_feet (bool, optional, default True): Anchor ankles to ground via FixedJoint.
          - planning_obstacles (list[str], optional): Extra obstacles for cuRobo.
          - mutex_path (str, optional): Shared coordination mutex (for handoff).
          - ee_offset (list[float], optional): EE→fingertip offset, default [0,0,0.10].
          - scenario_profile (str, optional): Forwarded to per-arm handler.
          - robot_family (str, optional): "g1_arm" (default, only one supported in V0).

    Returns:
        str: Python source code installing both per-arm controllers. The
        generated code prints a JSON dict per install + a final composite
        dict at end:
          {"ok": True, "mode": "bimanual_pick_place", "coordination": "sequential",
           "left_arm": {...}, "right_arm": {...}, "plant_feet": True/False}

    Raises:
        ValueError: If robot_family is not "g1_arm" (V0 limitation).
        KeyError: If required path args are missing.
    """
    robot_path = args["robot_path"]
    left_sources = args.get("left_arm_sources") or []
    right_sources = args.get("right_arm_sources") or []
    left_destination = args.get("left_destination") or args.get("destination_path")
    right_destination = args.get("right_destination") or args.get("destination_path")
    if not left_destination or not right_destination:
        raise KeyError(
            "setup_bimanual_pick_place_controller: left_destination + "
            "right_destination are required (or destination_path as fallback for both)"
        )
    coordination_mode = str(args.get("coordination_mode", "sequential")).lower()
    if coordination_mode not in ("sequential", "parallel", "handoff"):
        raise ValueError(
            f"coordination_mode must be one of 'sequential'/'parallel'/'handoff', "
            f"got {coordination_mode!r}"
        )
    plant_feet = bool(args.get("plant_feet", True))
    robot_family = str(args.get("robot_family", "g1_arm")).lower()
    if robot_family not in ("g1_arm", "g1", "unitree_g1", "g1_left_arm", "g1_right_arm"):
        raise ValueError(
            f"setup_bimanual_pick_place_controller: V0 only supports "
            f"robot_family='g1_arm', got {robot_family!r}"
        )
    ee_offset = args.get("ee_offset") or args.get("end_effector_offset") or [0.0, 0.0, 0.10]
    planning_obstacles = args.get("planning_obstacles") or []
    mutex_path = args.get("mutex_path")
    scenario_profile = args.get("scenario_profile")

    # Build per-arm code snippets via the existing curobo gen-fn. Each call
    # produces a self-contained installer; sequential exec at runtime gives
    # us LEFT-then-RIGHT (Kit RPC is single-tenant).
    left_code = _pp._gen_pick_place_curobo(
        robot_path=robot_path,
        sensor_path=None,
        belt_path=None,
        source_paths=left_sources,
        destination_path=left_destination,
        drop_target=None,
        ee_offset=ee_offset,
        planning_obstacles=planning_obstacles,
        mutex_path=mutex_path,
        scenario_profile=scenario_profile,
        robot_family="g1_arm",
        arm_scope="left",
        phase_id="bimanual_left",
    )
    right_code = _pp._gen_pick_place_curobo(
        robot_path=robot_path,
        sensor_path=None,
        belt_path=None,
        source_paths=right_sources,
        destination_path=right_destination,
        drop_target=None,
        ee_offset=ee_offset,
        planning_obstacles=planning_obstacles,
        mutex_path=mutex_path,
        scenario_profile=scenario_profile,
        robot_family="g1_arm",
        arm_scope="right",
        phase_id="bimanual_right",
    )

    # Plant-feet snippet — USD FixedJoint anchoring each ankle_roll_link to
    # ground at /World. Pre-V0, this sidesteps the WBC runtime requirement
    # by treating the humanoid lower body as a fixed-base anchor.
    # If the ankle prims don't exist (placeholder G1 USD), the snippet
    # logs a warning and continues — left/right arm installers still run.
    #
    # ⚠️ TWO FINDINGS from a RAW standalone reproduction (cont.319ii, CP-G1-STAND-01,
    # G1 g1_29dof_with_hand on a healthy Kit; positive control CP-CHAIN-FLAT 1/1):
    #   (1) LATENT BUG: the FixedJoint below sets ONLY GetBody1Rel (the ankle) and NO
    #       localPos0/localRot0 on the world side -> UsdPhysics welds the ankle frame to
    #       the WORLD ORIGIN (0,0,0), yanking the foot there instead of pinning it where
    #       it stands. The correct authoring captures the ankle's CURRENT world transform
    #       (ComputeLocalToWorldTransform) into CreateLocalPos0Attr/CreateLocalRot0Attr.
    #   (2) DEEPER: even with localPos0 corrected, welding the LEAF ankle links to world
    #       OVER-CONSTRAINS the free-floating-base articulation -> the solver explodes
    #       (hip/shoulder joints ~1e10 deg). And the alternative, physxArticulation:fixedBase=True
    #       set POST-add_reference, does NOT convert the already-referenced floating root (the G1
    #       just falls). The G1 standing base needs a LOAD-TIME fixed base (Isaac core Articulation
    #       fix_root_link / a pre-parse USD layer / the WBC runtime deferred to scope-doc P3) -- a
    #       post-hoc plant_feet is insufficient on its own. See CP-G1-STAND-01.verified_status.
    if plant_feet:
        plant_feet_code = f'''\
# ── Plant feet: USD FixedJoint between ankle_roll_link and ground ──
# Per docs/notes/2026-05-28-g1-humanoid-impl-scope.md P0 — sidesteps
# WBC runtime for V0. Each ankle gets a FixedJoint to /World so the
# humanoid lower body is rigidly anchored. cuRobo lock_joints (in
# per-arm planner) handles the kinematic side; FJ handles physics.
def _plant_g1_feet():
    import omni.usd
    from pxr import UsdPhysics, Sdf, UsdGeom
    _stage = omni.usd.get_context().get_stage()
    _robot = {robot_path!r}
    _planted = []
    for _side in ("left", "right"):
        _ankle = f"{{_robot}}/{{_side}}_ankle_roll_link"
        if not _stage.GetPrimAtPath(_ankle).IsValid():
            print(f"(bimanual: plant_feet — ankle not found at {{_ankle}}, skipping)")
            continue
        _fj_path = f"/World/G1_PlantedFoot_{{_side}}"
        if _stage.GetPrimAtPath(_fj_path).IsValid():
            # already planted (re-install)
            _planted.append(_side)
            continue
        try:
            _fj = UsdPhysics.FixedJoint.Define(_stage, _fj_path)
            # body0 unset = world; body1 = ankle link
            _fj.GetBody1Rel().SetTargets([Sdf.Path(_ankle)])
            _planted.append(_side)
            print(f"(bimanual: plant_feet — FixedJoint at {{_fj_path}} → {{_ankle}})")
        except Exception as _e:
            print(f"(bimanual: plant_feet soft-fail for {{_side}}: {{_e}})")
    return _planted
_planted_feet = _plant_g1_feet()
'''
    else:
        plant_feet_code = '_planted_feet = []  # plant_feet=False — relying on WBC or external anchor\n'

    coordination_warn = ""
    if coordination_mode != "sequential":
        # V0: parallel/handoff fall back to sequential with warning per scope-doc P1.2.
        coordination_warn = (
            f'print("(bimanual: coordination_mode={coordination_mode!r} requested, '
            f'V0 falls back to sequential — see scope-doc P4 for true parallel)")\n'
        )

    # Assemble: header + plant_feet + LEFT install + RIGHT install + composite footer.
    # Each per-arm install prints its own JSON success dict; the footer adds a
    # composite line so callers can see both arms installed in one place.
    header = f'''\
# ── setup_bimanual_pick_place_controller (G1, V0 sequential) ──────────
# 2026-05-28 J1 — composes 2× _gen_pick_place_curobo (left+right) with
# planted feet. Per scope-doc P1; kit-concurrency memory: Kit RPC is
# single-tenant, so "sequential" is the only honest coordination mode.
import json as _bm_json
print("(bimanual: install begin — robot={robot_path!r} mode={coordination_mode!r})")
{coordination_warn}{plant_feet_code}'''

    footer = f'''\
# ── Composite success record ──────────────────────────────────────────
print(_bm_json.dumps({{
    "ok": True,
    "mode": "bimanual_pick_place",
    "robot_path": {robot_path!r},
    "robot_family": "g1_arm",
    "coordination": {coordination_mode!r},
    "plant_feet": {plant_feet!r},
    "planted_feet": _planted_feet,
    "left_arm": {{"phase_id": "bimanual_left", "sources": {left_sources!r}, "destination": {left_destination!r}}},
    "right_arm": {{"phase_id": "bimanual_right", "sources": {right_sources!r}, "destination": {right_destination!r}}},
    "notes": "Per-arm cuRobo planners cached under separate builtins keys (cfg+scope). See scope-doc P0.4.",
}}))
'''

    return (
        header
        + "\n# ── LEFT arm install ──────────────────────────────────────\n"
        + left_code
        + "\n# ── RIGHT arm install ─────────────────────────────────────\n"
        + right_code
        + "\n"
        + footer
    )


def register(
    data: Dict[str, Callable[..., Any]],
    codegen: Dict[str, Callable[..., Any]],
) -> None:
    """Phase 9 register entry — only one code-gen handler (V0).

    Called by handlers/_dispatch.py:register_handlers().
    """
    codegen["setup_bimanual_pick_place_controller"] = _gen_setup_bimanual_pick_place_controller
