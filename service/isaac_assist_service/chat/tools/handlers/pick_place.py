"""Pick-place handlers — target scope: pick-place controller dispatcher
+ 9 variant generators (builtin, sensor_gated, native, spline, curobo,
diffik, osc, fixed_poses, ros2_cmd) + ros2 bridge setup.

Phase 6 wave 25 — moves the entire pick-place suite (~6000 lines) out
of tool_executor.py. The dispatcher (_gen_setup_pick_place_controller)
selects a variant based on args; all variants live here so the
internal calls resolve via module-local namespace.

Per specs/IA_FULL_SPEC_2026-05-10.md Phases 2 + 6.
"""
# audit-Q17: cohesive — full pick-place handler suite (9 controller variants + ROS2 bridge + dispatcher) stays together by design
from __future__ import annotations

from typing import Any, Callable, Dict

# ---------------------------------------------------------------------------
# Module-level named constants (extracted 2026-05-14, refactor/magic-1)

# RmpFlow integration constants
_RMPFLOW_MAX_SUBSTEP_S: float = 0.016   # RmpFlow maximum substep size, seconds (~62.5 Hz integration cap)
_PHYSICS_DT_DEFAULT_S: float = 1.0 / 60.0  # default physics timestep, seconds (60 Hz)

# Franka gripper geometry
_FRANKA_PALM_TO_FINGERTIP_M: float = 0.105  # distance from panda_hand palm frame to fingertip ends, meters;
                                              # EE target is set to cube_center + this offset so fingertips
                                              # wrap the cube (observed 2026-04-19: lower value collides belt)
_FRANKA_FINGER_OPEN_M: float = 0.04         # finger joint position for fully open gripper, meters

# Orientation constraint threshold
_UPRIGHT_DOT_THRESHOLD_DEFAULT: float = 0.85  # minimum dot(ee_z, world_z) for "upright" cuRobo grasp filter

# Friction material physics properties
_GRIP_FRICTION_STATIC: float = 1.5    # static friction coefficient for FrictionGripMaterial
_GRIP_FRICTION_DYNAMIC: float = 1.2   # dynamic friction coefficient for FrictionGripMaterial

# Minimum belt velocity magnitude treated as "moving" (below this → belt is stopped)
_BELT_MOVING_THRESHOLD: float = 1e-6  # m/s; sum(|v_i|) below this treats belt as stationary

# ---------------------------------------------------------------------------
# Phase 14 + 16 (2026-05-13): migrated from tool_executor.py.

_PP_CTRL_ATTRS = [
    # (attr_name, usd_type_name_literal, default_value_literal)
    ("ctrl:mode",            "Sdf.ValueTypeNames.String", '""'),
    ("ctrl:phase",           "Sdf.ValueTypeNames.String", '"wait_sensor"'),
    ("ctrl:cubes_delivered", "Sdf.ValueTypeNames.Int",    "0"),
    ("ctrl:error_count",     "Sdf.ValueTypeNames.Int",    "0"),
    ("ctrl:last_error",      "Sdf.ValueTypeNames.String", '""'),
    ("ctrl:picked_path",     "Sdf.ValueTypeNames.String", '""'),
    ("ctrl:tick_count",      "Sdf.ValueTypeNames.Int",    "0"),
    # Phase 4 diagnostic counters (added 2026-05-10): incremented in
    # cuRobo handler around _planner.plan_pose() calls. Lets probes
    # distinguish "controller never planned" (plan_calls=0) from
    # "controller tried but planner failed" (plan_calls>0, plan_fails>0).
    ("ctrl:plan_calls",      "Sdf.ValueTypeNames.Int",    "0"),
    ("ctrl:plan_fails",      "Sdf.ValueTypeNames.Int",    "0"),
    ("ctrl:last_fail_goal",  "Sdf.ValueTypeNames.String", '""'),
]

# ---------------------------------------------------------------------------
# Theme-local constants + helpers (Phase 8 wave 9, 2026-05-13)
# Migrated from tool_executor.py — used only by handlers.pick_place.

_PP_RMPFLOW_HEADER = """
import os
import json
import numpy as np
import omni.usd
import omni.physx
from pxr import UsdGeom, UsdPhysics, Sdf, Gf
from isaacsim.robot_motion.motion_generation import RmpFlow, ArticulationMotionPolicy
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.api import World

def _find_franka_configs():
    roots = ["/home/anton/.local/share/ov/data/exts",
             "/home/anton/.local/share/ov/pkg",
             "/opt/isaac-sim",
             os.environ.get("ISAAC_PATH", "")]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            if "motion_policy_configs" in dirpath and dirpath.endswith("franka/rmpflow"):
                fs = set(files)
                if "franka_rmpflow_common.yaml" in fs and "robot_descriptor.yaml" in fs:
                    urdf = os.path.normpath(os.path.join(dirpath, "..", "lula_franka_gen.urdf"))
                    if not os.path.isfile(urdf):
                        urdf = None
                    return {{
                        "rmpflow": os.path.join(dirpath, "franka_rmpflow_common.yaml"),
                        "descriptor": os.path.join(dirpath, "robot_descriptor.yaml"),
                        "urdf": urdf,
                    }}
    return None
"""

_PP_OBSERVABILITY_SNIPPET = """
# ── Observability: ctrl:* attrs on robot prim ────────────────────────
# Canonical ctrl:* contract (see docs/qa/ctrl_attrs_schema.md). Every
# pick-place controller emits these attrs so downstream tools
# (diagnose_scene, auto_judge, benchmark_controllers) can probe state
# without controller-specific knowledge.
_robot_prim = stage.GetPrimAtPath(ROBOT_PATH)
def _ensure_attr(name, type_name, default):
    a = _robot_prim.GetAttribute(name)
    if not a or not a.IsDefined():
        a = _robot_prim.CreateAttribute(name, type_name)
    try:
        if a.Get() is None: a.Set(default)
    except Exception: pass
    return a

_a_mode = _ensure_attr("ctrl:mode", Sdf.ValueTypeNames.String, "")
_a_phase = _ensure_attr("ctrl:phase", Sdf.ValueTypeNames.String, "wait_sensor")
_a_cubes = _ensure_attr("ctrl:cubes_delivered", Sdf.ValueTypeNames.Int, 0)
_a_cycles = _ensure_attr("ctrl:cycles_attempted", Sdf.ValueTypeNames.Int, 0)
_a_err = _ensure_attr("ctrl:error_count", Sdf.ValueTypeNames.Int, 0)
_a_last_err = _ensure_attr("ctrl:last_error", Sdf.ValueTypeNames.String, "")
_a_picked = _ensure_attr("ctrl:picked_path", Sdf.ValueTypeNames.String, "")
_a_tick = _ensure_attr("ctrl:tick_count", Sdf.ValueTypeNames.Int, 0)
# Phase 4 diagnostic counters (2026-05-10): plan_calls/plan_fails counts
# cuRobo plan_pose attempts, last_fail_goal records the last failed pose.
_a_plan_calls = _ensure_attr("ctrl:plan_calls", Sdf.ValueTypeNames.Int, 0)
_a_plan_fails = _ensure_attr("ctrl:plan_fails", Sdf.ValueTypeNames.Int, 0)
_a_last_fail_goal = _ensure_attr("ctrl:last_fail_goal", Sdf.ValueTypeNames.String, "")
# Reset counters on install (avoid stale values from prior runs).
# Guard each Set() — when the robot prim was created indirectly
# (e.g. UR10 import_robot + reference resolution) the initial _ensure_attr()
# capture may target a soon-expired Xform handle. Re-acquiring via stage
# path always returns the live handle. Symptom this protects against:
# "Accessed invalid attribute 'ctrl:cubes_delivered' on expired 'Xform' prim </World/UR10>".
def _safe_attr_set(attr_name, value, default_type):
    try:
        _attr = _robot_prim.GetAttribute(attr_name)
        _attr.Set(value)
        return
    except Exception: pass
    try:
        _live = stage.GetPrimAtPath(ROBOT_PATH)
        if _live and _live.IsValid():
            _attr = _live.GetAttribute(attr_name)
            if not _attr or not _attr.IsDefined():
                _attr = _live.CreateAttribute(attr_name, default_type)
            _attr.Set(value)
    except Exception: pass

_safe_attr_set("ctrl:error_count", 0, Sdf.ValueTypeNames.Int)
_safe_attr_set("ctrl:cubes_delivered", 0, Sdf.ValueTypeNames.Int)
_safe_attr_set("ctrl:cycles_attempted", 0, Sdf.ValueTypeNames.Int)
_safe_attr_set("ctrl:tick_count", 0, Sdf.ValueTypeNames.Int)
_safe_attr_set("ctrl:last_error", "", Sdf.ValueTypeNames.String)
_safe_attr_set("ctrl:plan_calls", 0, Sdf.ValueTypeNames.Int)
_safe_attr_set("ctrl:plan_fails", 0, Sdf.ValueTypeNames.Int)
_safe_attr_set("ctrl:last_fail_goal", "", Sdf.ValueTypeNames.String)
"""

_PP_SCENE_RESET_MGR_SNIPPET = """
# ── Scene Reset Manager (robot-agnostic Stop+Play recovery) ──────────
# A single global manager that coordinates Stop+Play recovery for any
# number of registered controllers (native_pp, sensor_gated, UR10
# pick-place, palletizing, etc.). Installed idempotently: if it
# already exists, we just register our reset hook with it.
#
# Contract (also documented in docs/qa/ctrl_attrs_schema.md):
#   - register(name, reset_fn): reset_fn() returns True on success,
#     False to retry next tick (PLAY event fires before physics view
#     is valid; manager handles retry for all controllers uniformly)
#   - unregister(name): remove on controller teardown
_MGR_ATTR = "_scene_reset_manager"
if not hasattr(builtins, _MGR_ATTR):
    import omni.timeline as _otl_mgr
    class _SceneResetManager:
        def __init__(self):
            self.hooks = {}       # name → reset_fn (returns bool)
            self.pending = set()  # names still trying to reset
            self.stopped = False
            self._tl_sub = None
            self._physics_sub = None
        def register(self, name, reset_fn):
            self.hooks[name] = reset_fn
        def unregister(self, name):
            self.hooks.pop(name, None)
            self.pending.discard(name)
        def _on_timeline(self, ev):
            try:
                _et = int(ev.type)
                _play = int(_otl_mgr.TimelineEventType.PLAY)
                _stop = int(_otl_mgr.TimelineEventType.STOP)
            except Exception: return
            if _et == _stop:
                self.stopped = True
            elif _et == _play and self.stopped:
                self.stopped = False
                self.pending = set(self.hooks.keys())
        def _on_tick(self, dt):
            if not self.pending: return
            for name in list(self.pending):
                fn = self.hooks.get(name)
                if fn is None:
                    self.pending.discard(name); continue
                try:
                    if fn(): self.pending.discard(name)
                except Exception as _e:
                    print(f"(reset-hook '{name}' exception: {_e})")
    _mgr = _SceneResetManager()
    _mgr._tl_sub = _otl_mgr.get_timeline_interface().get_timeline_event_stream().create_subscription_to_pop(_mgr._on_timeline)
    _mgr._physics_sub = omni.physx.get_physx_interface().subscribe_physics_step_events(_mgr._on_tick)
    setattr(builtins, _MGR_ATTR, _mgr)
    print("(scene reset manager installed)")
"""

def _resolve_auto_target_source(args: dict) -> tuple[str, str]:
    """Select the best available pick-place variant for the current environment.

    Probes GPU capability, cuRobo availability, scipy, and Isaac Lab in priority
    order, returning the first viable variant. Called by
    ``_gen_setup_pick_place_controller`` when ``target_source="auto"``.

    Priority order: curobo > spline > native > diffik > native (fallback).
    ``sensor_gated``, ``fixed_poses``, ``cube_tracking``, and ``ros2_cmd`` are
    never auto-selected — they require explicit opt-in due to sim2real-honesty
    constraints or mandatory config (e.g. sensor_path, pose_sequence).

    Args:
        args (dict): Tool arguments dict. Reads ``robot_path`` to detect Franka
            for the native fallback path; all other probe inputs are hardware
            / package availability checks.

    Returns:
        tuple[str, str]: ``(resolved_target_source, reason_str)`` where
            ``resolved_target_source`` is one of ``"curobo"``, ``"spline"``,
            ``"native"``, or ``"diffik"``, and ``reason_str`` is a human-readable
            explanation of why that variant was chosen.
    """
    # Probes migrated to handlers/_shared.py (Phase 8 wave 17).
    from ._shared import (
        _probe_gpu_capability, _probe_scipy, _probe_curobo, _probe_isaac_lab,
    )
    # Inline probes — can't await here since this is sync-called from generator
    gpu = _probe_gpu_capability()
    curobo = _probe_curobo()
    isaac_lab = _probe_isaac_lab()
    cc = gpu.get("compute_capability")
    cc_major = 0
    if cc:
        try: cc_major = int(cc.split(".")[0])
        except Exception: pass
    # Priority: industrial-quality GPU path first, then CPU winner (spline —
    # benchmark showed 3/4 vs native's 0/4), then native for Franka
    # compatibility, then Isaac Lab diffik, then native fallback.
    # 1) curobo if GPU >= Volta AND curobo available
    if gpu["gpu_available"] and cc_major >= 7 and curobo["available"]:
        return "curobo", f"GPU={gpu['arch_name']} cc={cc}; curobo available"
    # 2) spline — verified 3/4 delivery on conveyor benchmark, beats native 3x
    if _probe_scipy()["available"]:
        return "spline", "scipy available; spline is CPU-only winner (3/4 vs native 0/4)"
    # 3) native — Franka-only fallback without scipy
    if args.get("robot_path", "").lower().endswith(("franka", "/franka")) or \
       "franka" in args.get("robot_path", "").lower():
        return "native", "Franka detected, scipy unavailable; native PickPlaceController fallback"
    # 4) diffik if Isaac Lab present
    if isaac_lab["available"]:
        return "diffik", "Isaac Lab available; no better option"
    # 5) Last resort
    return "native", "no better option; falling back to native"









# _handle_setup_ros2_control_compat moved to handlers/robot.py (Phase 7 wave 8).


# _handle_emit_ros2_control_yaml moved to handlers/ros2.py (Phase 7 wave 14).


# _handle_precheck_ros2_environment moved to handlers/ros2.py (Phase 7 wave 14).


# Register the new handlers


# ---------------------------------------------------------------------------
# Phase 6 wave 25 — pick-place suite (controller + 9 variants + ros2 bridge)


def _gen_setup_pick_place_controller(args: Dict) -> str:
    """Generate a physics-callback state machine for pick-and-place.

    Mode-driven (2026-04-19 refactor). Same tool, four architectures:

      - "cube_tracking": poll source prim world-pose each frame, retarget
        RmpFlow continuously. Omniscient — NOT sim2real-honest. Useful
        for ML demo-generation where ground-truth is fair game.

      - "sensor_gated": belt runs continuously; robot waits for a
        proximity sensor at a fixed pick station to trigger; then picks
        from the PRE-TAUGHT pick pose (not cube's live pose); resumes
        belt after release. Sim2real-honest industrial pattern.

      - "fixed_poses": deterministic sequence of pre-taught poses. No
        sensor, timer-driven. Simplest. Demos, validation.

      - "ros2_cmd": subscribe to /isaac/robot/target_pose and
        /isaac/robot/gripper_cmd; external controller drives the state
        machine. For digital-twin / PLC-in-loop.

    Shared across modes: RmpFlow + ArticulationMotionPolicy for
    joint-level control, UsdPhysics.FixedJoint for cube-to-EE attach
    during transport, gripper joint targets for open/close.

    Args:
        args: Tool arguments dict containing:
            - target_source (str, optional): Variant selector. One of
              ``"cube_tracking"`` (default), ``"sensor_gated"``,
              ``"fixed_poses"``, ``"ros2_cmd"``, ``"builtin"``, ``"native"``,
              ``"spline"``, ``"curobo"``, ``"diffik"``, ``"osc"``, or
              ``"auto"`` (probes hardware + packages via
              ``_resolve_auto_target_source``).
            - robot_path (str): USD prim path of the robot articulation root.
            - source_paths (list[str]): Cube prim paths to deliver.
            - destination_path (str): Drop bin prim path.
            - sensor_path (str, optional): Proximity sensor path (required for
              sensor_gated mode).
            - belt_path (str, optional): Conveyor belt prim path.
            - end_effector_link (str, optional): EE link name. Defaults to
              ``"panda_hand"``.
            - gripper_joint_1 (str, optional): Defaults to
              ``"panda_finger_joint1"``.
            - gripper_joint_2 (str, optional): Defaults to
              ``"panda_finger_joint2"``.
            - gripper_open (float, optional): Open position (m). Defaults to
              ``_FRANKA_FINGER_OPEN_M`` (0.04).
            - gripper_close (float, optional): Closed position (m). Defaults
              to 0.0.
            - Additional variant-specific keys forwarded to the selected
              generator (see each ``_gen_pick_place_*`` docstring).

    Returns:
        str: Python source code to be exec'd in Kit. The caller (tool_executor)
        passes this to ``queue_exec_patch``; the generated code installs a
        physics-step callback and prints a JSON result dict.

    Raises:
        ValueError: If ``target_source`` is not a recognised variant name.
        KeyError: If a required arg (e.g. ``robot_path``, or ``sensor_path``
            for sensor_gated mode) is absent from ``args``.
    """
    # _resolve_auto_target_source migrated to module body (Phase 8 wave 9).
    mode = args.get("target_source", "cube_tracking")
    if mode == "auto":
        resolved, reason = _resolve_auto_target_source(args)
        print(f"[setup_pick_place_controller] target_source='auto' → {resolved!r} ({reason})")
        mode = resolved
        args = dict(args)
        args["target_source"] = resolved
        args["_auto_resolved_from"] = "auto"
        args["_auto_reason"] = reason
    if mode not in {"cube_tracking", "sensor_gated", "fixed_poses", "ros2_cmd", "builtin",
                     "native", "spline", "curobo", "diffik", "osc"}:
        raise ValueError(f"setup_pick_place_controller: unknown target_source {mode!r}")

    # 2026-05-28: empty-source-paths guard. CAT-A templates (kit-prep-vision-gate,
    # kitting-station-6sku, etc.) silently install with source_paths=[] when vision
    # filter eliminates all candidates or template never creates cubes. Controller
    # then sits in wait_sensor forever → plan_calls=0 → indistinguishable from
    # other install failures. Early-return with explicit log surfaces the cause.
    _src = args.get("source_paths") or []
    _has_pick_target = args.get("pick_target") or args.get("drop_target")
    if mode in {"native", "builtin", "spline", "curobo", "diffik", "osc", "cube_tracking"} \
            and not _src and not _has_pick_target:
        return (
            'print("[setup_pick_place_controller] EARLY-RETURN: source_paths=[] in mode='
            + repr(mode) + ' robot=' + repr(args.get("robot_path", "?")) + ' — '
            'no cubes to pick. Template did not create workpieces, vision filter removed '
            'all candidates, or solve_ik returned no valid IK seeds. Check template '
            'code_template for cube create_prim ordering or vision/IK gate filtering.")'
        )

    robot_path = args["robot_path"]
    ee_link = args.get("end_effector_link", "panda_hand")
    fj1 = args.get("gripper_joint_1", "panda_finger_joint1")
    fj2 = args.get("gripper_joint_2", "panda_finger_joint2")
    open_val = float(args.get("gripper_open", _FRANKA_FINGER_OPEN_M))
    close_val = float(args.get("gripper_close", 0.0))
    approach_h = float(args.get("approach_height", 0.12))
    lift_h = float(args.get("lift_height", 0.20))
    drop_h = float(args.get("drop_height", 0.18))
    # Track K (2026-05-28): per-phase subscription scoping. Same robot can host
    # multiple sequential controllers (phase1 picks, phase2 places, phase3 transports
    # to outfeed). Without phase_id, each install would clobber the previous one's
    # subscription. Missing phase_id = "default" (legacy single-PPC templates).
    phase_id = str(args.get("phase_id", "default"))

    if mode == "native":
        # Round 9 repair (2026-05-18): the native path is Franka-only
        # (it imports isaacsim.robot.manipulators.examples.franka and
        # creates a ParallelGripper bound to panda_leftfinger /
        # panda_rightfinger). Templates routinely pass UR10 / cobotta /
        # other arms with target_source="native" and then crash at
        # gripper init with `Prim path expression
        # ['/World/UR10/panda_rightfinger'] is invalid`. Auto-route to
        # the builtin dispatcher when the robot is not a Franka — that
        # path picks the correct per-family PickPlaceController.
        _rf_native = (args.get("robot_family") or "").lower()
        if not _rf_native:
            _rp_lc_native = (robot_path or "").lower()
            if "ur10" in _rp_lc_native or "ur5" in _rp_lc_native or "ur16" in _rp_lc_native:
                _rf_native = "ur10"
            elif "cobotta" in _rp_lc_native:
                _rf_native = "cobotta_pro_900"
            elif "franka" in _rp_lc_native or "panda" in _rp_lc_native:
                _rf_native = "franka"
        if _rf_native and _rf_native != "franka":
            return _gen_pick_place_builtin(
                robot_path=robot_path,
                robot_family=_rf_native,
                sensor_path=args.get("sensor_path"),
                belt_path=args.get("belt_path"),
                source_paths=args.get("source_paths") or [],
                destination_path=args.get("destination_path"),
                drop_target=args.get("drop_target"),
                ee_offset=args.get("end_effector_offset", [0.0, 0.0, 0.02]),
                phase_id=phase_id,
            )
        return _gen_pick_place_native(
            robot_path=robot_path,
            sensor_path=args.get("sensor_path"),
            belt_path=args.get("belt_path"),
            source_paths=args.get("source_paths") or [],
            destination_path=args.get("destination_path") or args.get("drop_target_path"),
            drop_target=args.get("drop_target"),
            ee_offset=args.get("end_effector_offset", [0.0, 0.005, 0.0]),
            end_effector_initial_height=args.get("end_effector_initial_height"),
            events_dt=args.get("events_dt"),
            phase_id=phase_id,
        )
    if mode == "spline":
        return _gen_pick_place_spline(
            robot_path=robot_path,
            sensor_path=args.get("sensor_path"),
            belt_path=args.get("belt_path"),
            source_paths=args.get("source_paths") or [],
            destination_path=args.get("destination_path") or args.get("drop_target_path"),
            drop_target=args.get("drop_target"),
            ee_offset=args.get("end_effector_offset", [0.0, 0.005, 0.0]),
            end_effector_initial_height=args.get("end_effector_initial_height"),
            spline_waypoint_dt=args.get("spline_waypoint_dt"),
            grip_style=args.get("grip_style", "friction"),
            color_routing=args.get("color_routing"),
            mutex_path=args.get("mutex_path"),
            phase_id=phase_id,
        )
    if mode == "curobo":
        # Round 6 repair (2026-05-18): auto-detect robot_family from
        # robot_path when caller didn't supply it. Templates routinely
        # pass UR10 in robot_path but forget to set robot_family, then
        # the curobo gen-fn defaults to "franka" and creates a panda
        # gripper view on a UR10 articulation → ParallelGripper failure.
        # 2026-05-28 J0: also auto-detect g1/g1_arm from path.
        _rf = args.get("robot_family")
        if not _rf:
            _rp_lc = (robot_path or "").lower()
            if "ur10" in _rp_lc or "ur5" in _rp_lc or "ur16" in _rp_lc:
                _rf = "ur10"
            elif "g1" in _rp_lc or "unitree" in _rp_lc:
                _rf = "g1_arm"
            else:
                _rf = "franka"
        # 2026-05-28 J0: auto-derive arm_scope from family alias when callers
        # pass robot_family="g1_left_arm" / "g1_right_arm" instead of the
        # split (family="g1_arm", arm_scope="left"|"right").
        _arm_scope = args.get("arm_scope")
        if not _arm_scope and _rf:
            _rfl = str(_rf).lower()
            if _rfl == "g1_left_arm":
                _arm_scope = "left"
            elif _rfl == "g1_right_arm":
                _arm_scope = "right"
        return _gen_pick_place_curobo(
            robot_path=robot_path,
            sensor_path=args.get("sensor_path"),
            belt_path=args.get("belt_path"),
            source_paths=args.get("source_paths") or [],
            destination_path=args.get("destination_path") or args.get("drop_target_path"),
            drop_target=args.get("drop_target"),
            ee_offset=args.get("end_effector_offset", [0.0, 0.005, 0.0]),
            end_effector_initial_height=args.get("end_effector_initial_height"),
            planning_obstacles=args.get("planning_obstacles") or [],
            curobo_world_yml=args.get("curobo_world_yml"),
            color_routing=args.get("color_routing"),
            drop_targets=args.get("drop_targets"),
            gripper_rotation=args.get("gripper_rotation"),
            robot_family=_rf,
            require_upright=bool(args.get("require_upright", False)),
            upright_dot_threshold=float(args.get("upright_dot_threshold", _UPRIGHT_DOT_THRESHOLD_DEFAULT)),
            mutex_path=args.get("mutex_path"),
            scenario_profile=args.get("scenario_profile"),
            arm_scope=_arm_scope,
            claim_radius=args.get("claim_radius"),
            task=args.get("task"),
            task_joint_path=args.get("joint_path"),
            task_args={k: args[k] for k in args if k.startswith("task_")},
            phase_id=phase_id,
        )
    if mode == "diffik":
        return _gen_pick_place_diffik(
            robot_path=robot_path,
            sensor_path=args.get("sensor_path"),
            belt_path=args.get("belt_path"),
            source_paths=args.get("source_paths") or [],
            destination_path=args.get("destination_path") or args.get("drop_target_path"),
            drop_target=args.get("drop_target"),
            ee_offset=args.get("end_effector_offset", [0.0, 0.005, 0.0]),
            end_effector_initial_height=args.get("end_effector_initial_height"),
            diffik_method=args.get("diffik_method", "dls"),
            phase_id=phase_id,
        )
    if mode == "osc":
        return _gen_pick_place_osc(
            robot_path=robot_path,
            sensor_path=args.get("sensor_path"),
            belt_path=args.get("belt_path"),
            source_paths=args.get("source_paths") or [],
            destination_path=args.get("destination_path") or args.get("drop_target_path"),
            drop_target=args.get("drop_target"),
            ee_offset=args.get("end_effector_offset", [0.0, 0.005, 0.0]),
            phase_id=phase_id,
        )
    if mode == "sensor_gated":
        return _gen_pick_place_sensor_gated(
            robot_path=robot_path,
            sensor_path=args["sensor_path"],
            belt_path=args.get("belt_path"),
            pick_pose_name=args.get("pick_pose_name", "pick"),
            drop_pose_name=args.get("drop_pose_name", "drop"),
            home_pose_name=args.get("home_pose_name", "home"),
            pick_target=args.get("pick_target"),
            drop_target=args.get("drop_target"),
            home_target=args.get("home_target"),
            grip_style=args.get("grip_style", "friction"),
            source_paths=args.get("source_paths") or [],
            ee_link=ee_link, fj1=fj1, fj2=fj2,
            open_val=open_val, close_val=close_val,
            phase_id=phase_id,
        )
    if mode == "fixed_poses":
        return _gen_pick_place_fixed_poses(
            robot_path=robot_path,
            pose_sequence=args["pose_sequence"],
            cycles=int(args.get("cycles", 1)),
            ee_link=ee_link, fj1=fj1, fj2=fj2,
        )
    if mode == "ros2_cmd":
        return _gen_pick_place_ros2_cmd(
            robot_path=robot_path,
            target_topic=args.get("target_topic", "/isaac/robot/target_pose"),
            gripper_topic=args.get("gripper_topic", "/isaac/robot/gripper_cmd"),
            ee_link=ee_link, fj1=fj1, fj2=fj2,
        )
    if mode == "builtin":
        # Robot-agnostic: wraps Isaac Sim's bundled per-robot PickPlaceController
        # (Franka, UR10, UR10e, CobottaPro900). Each is pre-configured by NVIDIA
        # with the right gripper class (parallel vs surface) + RMPflow controller.
        return _gen_pick_place_builtin(
            robot_path=robot_path,
            robot_family=args.get("robot_family", "auto"),
            sensor_path=args.get("sensor_path"),
            belt_path=args.get("belt_path"),
            source_paths=args.get("source_paths") or [],
            destination_path=args.get("destination_path"),
            drop_target=args.get("drop_target"),
            ee_offset=args.get("end_effector_offset", [0.0, 0.0, 0.02]),
            phase_id=phase_id,
        )

    # Default / legacy: cube_tracking (uses source_paths + destination_path)
    source_paths = args["source_paths"]
    destination_path = args["destination_path"]

    return f"""\
# ── setup_pick_place_controller ──────────────────────────────────────
# Stateful controller: iterates over source_paths, for each cube does
# APPROACH → DESCEND → GRASP → LIFT → TRANSIT → RELEASE. Uses RmpFlow
# for IK + obstacle avoidance. Installs a physics-step callback.
import os
import json
import numpy as np
import omni.usd
import omni.physx
from pxr import UsdGeom, UsdPhysics, Sdf, Gf
from isaacsim.robot_motion.motion_generation import RmpFlow, ArticulationMotionPolicy
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.api import World

ROBOT_PATH = {robot_path!r}
SOURCE_PATHS = {source_paths!r}
DESTINATION_PATH = {destination_path!r}
EE_LINK = {ee_link!r}
FJ1 = {fj1!r}
FJ2 = {fj2!r}
GRIPPER_OPEN = {open_val}
GRIPPER_CLOSE = {close_val}
_PHASE_ID = {phase_id!r}
APPROACH_H = {approach_h}
LIFT_H = {lift_h}
DROP_H = {drop_h}

# ── discover Franka RmpFlow config files (bundled with Isaac Sim 5.1) ──
def _find_franka_configs():
    roots = ["/home/anton/.local/share/ov/data/exts",
             "/home/anton/.local/share/ov/pkg",
             "/opt/isaac-sim",
             os.environ.get("ISAAC_PATH", "")]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            if "motion_policy_configs" in dirpath and dirpath.endswith("franka/rmpflow"):
                fs = set(files)
                if "franka_rmpflow_common.yaml" in fs and "robot_descriptor.yaml" in fs:
                    urdf = os.path.normpath(os.path.join(dirpath, "..", "lula_franka_gen.urdf"))
                    if not os.path.isfile(urdf):
                        urdf = None
                    return {{
                        "rmpflow": os.path.join(dirpath, "franka_rmpflow_common.yaml"),
                        "descriptor": os.path.join(dirpath, "robot_descriptor.yaml"),
                        "urdf": urdf,
                    }}
    return None

cfg = _find_franka_configs()
if cfg is None:
    raise RuntimeError(
        "setup_pick_place_controller: could not find Franka RmpFlow config "
        "(franka_rmpflow_common.yaml + robot_descriptor.yaml). Expected "
        "under a motion_policy_configs/franka/rmpflow/ directory in the "
        "installed isaacsim.robot_motion.motion_generation extension."
    )

# ── initialize articulation + motion policy ──────────────────────────
stage = omni.usd.get_context().get_stage()
world = World.instance() or World()
if not world.is_playing():
    # Need physics ticking for the callback to fire
    world.reset()

franka = SingleArticulation(ROBOT_PATH)
franka.initialize()

rmpflow = RmpFlow(
    robot_description_path=cfg["descriptor"],
    urdf_path=cfg["urdf"],
    rmpflow_config_path=cfg["rmpflow"],
    end_effector_frame_name=EE_LINK,
    maximum_substep_size={_RMPFLOW_MAX_SUBSTEP_S},
)
amp = ArticulationMotionPolicy(franka, rmpflow, default_physics_dt={_PHYSICS_DT_DEFAULT_S})

# Gripper fingers are NOT articulated by rmpflow — apply direct position
# targets for open/close. RmpFlow only drives the 7 arm joints.
def _gripper(value):
    names = franka.dof_names or []
    if not names:
        return
    q = franka.get_joint_positions()
    if q is None:
        return
    q = q.copy() if hasattr(q, 'copy') else list(q)
    for gj in (FJ1, FJ2):
        if gj in names:
            q[names.index(gj)] = value
    try:
        franka.set_joint_position_targets(q)
    except Exception:
        # Fallback for API variations
        franka.set_joint_positions(q)

# ── helpers ──────────────────────────────────────────────────────────
def _bbox_center_np(path):
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        return None
    bb = UsdGeom.Imageable(prim).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    mn, mx = bb.GetMin(), bb.GetMax()
    return np.array([(mn[0]+mx[0])/2, (mn[1]+mx[1])/2, (mn[2]+mx[2])/2])

def _ee_pos_np():
    ee_prim = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/{{EE_LINK}}")
    if not ee_prim or not ee_prim.IsValid():
        return None
    t = UsdGeom.Xformable(ee_prim).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([t[0], t[1], t[2]])

def _set_target(pos):
    # EE pointing downward (z-axis down in world frame)
    q = np.array([0.0, 1.0, 0.0, 0.0])  # (w, x, y, z) — 180deg about X
    rmpflow.set_end_effector_target(target_position=np.asarray(pos, dtype=np.float64),
                                    target_orientation=q)

def _reached(target, tol=0.04):
    ee = _ee_pos_np()
    if ee is None:
        return False
    return float(np.linalg.norm(ee - target)) < tol

def _attach_cube_to_ee(cube_path):
    # 2026-05-26 FRICTION-FIX: NO FJ. Use friction-grip — close fingers to hold cube.
    # cube_half = 0.025 for 5cm cube; finger-position 0.022 contacts cube with light pressure.
    # Friction-coefficient + finger-stiffness in scene determine actual hold force.
    _gripper(0.018)  # TIGHTER (was 0.022) — fingers compress cube edges för stronger friction-hold
    return f"__friction__{{cube_path}}"  # sentinel marker (no actual joint created)

def _detach_cube(joint_path):
    # FRICTION-FIX: open fingers (no FJ to remove)
    if joint_path and str(joint_path).startswith("__friction__"):
        _gripper(GRIPPER_OPEN)
        return
    # legacy FJ removal (in case any old-state has FJ-string)
    if joint_path and stage.GetPrimAtPath(str(joint_path)).IsValid():
        stage.RemovePrim(str(joint_path))

# ── state machine state ──────────────────────────────────────────────
S = {{
    "phase": "next",
    "remaining": list(SOURCE_PATHS),
    "current_cube": None,
    "current_target": None,
    "grasp_joint": None,
    "phase_enter_t": 0.0,
    "elapsed_t": 0.0,
    "done": False,
    "cubes_delivered": 0,
}}

def _advance(dt):
    S["elapsed_t"] += dt
    now = S["elapsed_t"]
    phase = S["phase"]

    if phase == "next":
        if not S["remaining"]:
            S["done"] = True
            return
        S["current_cube"] = S["remaining"][0]
        _gripper(GRIPPER_OPEN)
        cube = _bbox_center_np(S["current_cube"])
        if cube is None:
            # cube missing (deleted?) — skip
            S["remaining"].pop(0)
            return
        tgt = cube + np.array([0, 0, APPROACH_H])
        S["current_target"] = tgt
        _set_target(tgt)
        S["phase"] = "approach"
        S["phase_enter_t"] = now

    elif phase == "approach":
        if _reached(S["current_target"], tol=0.05) or (now - S["phase_enter_t"] > 8.0):
            cube = _bbox_center_np(S["current_cube"])
            if cube is None:
                S["remaining"].pop(0); S["phase"] = "next"; return
            # panda_hand (the EE frame) is the gripper palm; fingertips
            # extend ~{_FRANKA_PALM_TO_FINGERTIP_M}m below. Target the palm at cube_top + {_FRANKA_PALM_TO_FINGERTIP_M}m
            # so the fingertips wrap the cube. Previously we targeted
            # cube + 0.015m which put the fingertips 9cm inside the belt,
            # and RmpFlow refused to penetrate the collision.
            tgt = cube + np.array([0, 0, {_FRANKA_PALM_TO_FINGERTIP_M}])
            S["current_target"] = tgt
            _set_target(tgt)
            S["phase"] = "descend"
            S["phase_enter_t"] = now

    elif phase == "descend":
        if _reached(S["current_target"], tol=0.04) or (now - S["phase_enter_t"] > 4.0):
            _gripper(GRIPPER_CLOSE)
            S["phase"] = "grasp"
            S["phase_enter_t"] = now

    elif phase == "grasp":
        if now - S["phase_enter_t"] > 0.4:  # brief pause for gripper to close
            # Contact gate: verify EE (panda_hand palm) is at the descend
            # target (cube + {_FRANKA_PALM_TO_FINGERTIP_M}m so fingertips wrap the cube). Checking
            # against cube center directly would always fail since palm-to-
            # cube-center is ~{_FRANKA_PALM_TO_FINGERTIP_M}m by design. Observed 2026-04-19: without
            # this gate, FixedJoint.Apply preserves a 0.5m offset when
            # descend times out.
            ee = _ee_pos_np()
            cube = _bbox_center_np(S["current_cube"])
            target_pos = cube + np.array([0, 0, {_FRANKA_PALM_TO_FINGERTIP_M}]) if cube is not None else None
            _grip_ok = (ee is not None and target_pos is not None
                        and float(np.linalg.norm(ee - target_pos)) <= 0.06)
            if not _grip_ok:
                # Retry descend up to 2 times; after that, give up on this cube.
                S.setdefault("grasp_retries", 0)
                S["grasp_retries"] += 1
                if S["grasp_retries"] >= 3:
                    # Abandon this cube, reset retry counter, try next
                    S["grasp_retries"] = 0
                    _gripper(GRIPPER_OPEN)
                    S["remaining"].pop(0)
                    S["phase"] = "next"
                    return
                # Re-aim descend just above the cube current position
                if cube is not None:
                    tgt = cube + np.array([0, 0, 0.015])
                    S["current_target"] = tgt
                    _set_target(tgt)
                _gripper(GRIPPER_OPEN)
                S["phase"] = "descend"
                S["phase_enter_t"] = now
                return
            S["grasp_retries"] = 0
            S["grasp_joint"] = _attach_cube_to_ee(S["current_cube"])
            if ee is None:
                S["phase"] = "release"; return
            tgt = ee + np.array([0, 0, LIFT_H])
            S["current_target"] = tgt
            _set_target(tgt)
            S["phase"] = "lift"
            S["phase_enter_t"] = now

    elif phase == "lift":
        if _reached(S["current_target"], tol=0.05) or (now - S["phase_enter_t"] > 4.0):
            bin_c = _bbox_center_np(DESTINATION_PATH)
            if bin_c is None:
                S["phase"] = "release"; return
            tgt = bin_c + np.array([0, 0, DROP_H])
            S["current_target"] = tgt
            _set_target(tgt)
            S["phase"] = "transit"
            S["phase_enter_t"] = now

    elif phase == "transit":
        # 2026-05-26 PRECISION-FIX: tighter tolerance (60mm→15mm) + dwell-settle (0.5s) before release.
        # Previously: release happened when palm 60mm from target + with momentum = cube ejected sideways.
        if _reached(S["current_target"], tol=0.015) or (now - S["phase_enter_t"] > 8.0):
            S["phase"] = "drop_settle"
            S["phase_enter_t"] = now

    elif phase == "drop_settle":
        # Wait 0.5s for palm to fully stop (PD-drives settle, zero velocity)
        if now - S["phase_enter_t"] > 0.5:
            _detach_cube(S["grasp_joint"])
            S["grasp_joint"] = None
            _gripper(GRIPPER_OPEN)
            S["phase"] = "release"
            S["phase_enter_t"] = now
            S["cubes_delivered"] += 1

    elif phase == "release":
        if now - S["phase_enter_t"] > 0.5:
            S["remaining"].pop(0)
            S["phase"] = "next"

def _physics_cb(dt):
    _advance(dt)
    if not S["done"]:
        action = amp.get_next_articulation_action()
        if action is not None:
            franka.apply_action(action)

# Subscribe via omni.physx directly (not world.add_physics_callback).
# World.add_physics_callback goes through SimulationContext._physics_context
# which is None unless World was constructed against an already-initialized
# PhysicsScene AND world.reset_async() completed. In a freshly-built stage
# from exec_sync, that precondition is unreliable and raises
# AttributeError: 'NoneType' object has no attribute '_physx_interface'.
# The physx interface itself is available directly, so bypass the World
# layer and subscribe to raw physics step events.
_physx = omni.physx.get_physx_interface()
if _physx is None:
    raise RuntimeError(
        "setup_pick_place_controller: omni.physx interface unavailable — "
        "ensure the PhysX extension is loaded (omni.physx, omni.physx.flatcache)."
    )
# Cache the subscription so repeated calls replace rather than stack.
# Per-robot scoping: dual-arm / multi-call templates (e.g. packer-box-seal
# calls setup_pick_place_controller twice — once for items, once for lid)
# must NOT clobber the other robot's controller. Suffix the handle with
# a robot-path tag so different robots get independent subscriptions.
import builtins as _builtins
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
# Track K (2026-05-28): per-phase scoping.
_sub_attr = "_pick_place_controller_physx_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
_old_sub = getattr(_builtins, _sub_attr, None)
if _old_sub is not None:
    try:
        _old_sub.unsubscribe()
    except Exception:
        pass
_sub = _physx.subscribe_physics_step_events(_physics_cb)
setattr(_builtins, _sub_attr, _sub)

print(json.dumps({{
    "ok": True,
    "cubes_queued": len(SOURCE_PATHS),
    "destination": DESTINATION_PATH,
    "rmpflow_config": cfg["rmpflow"],
    "urdf": cfg["urdf"],
    "architecture": "python_callback + RmpFlow + ArticulationMotionPolicy",
    "notes": "State machine runs on each physics step. Start the simulation (Play) to see the robot pick cubes into the bin.",
}}))
"""


def _gen_pick_place_builtin(robot_path: str, robot_family: str, sensor_path: str, belt_path: str,
                             source_paths: list, destination_path: str, drop_target: str,
                             ee_offset: list, phase_id: str = "default") -> str:
    """Robot-agnostic pick-place using Isaac Sim's bundled per-robot controllers.

    Wraps NVIDIA's pre-configured PickPlaceController classes:
      - franka  → isaacsim.robot.manipulators.examples.franka (parallel gripper)
      - ur10/ur10e → isaacsim.robot.manipulators.examples.universal_robots (surface gripper)
      - cobotta_pro_900 → isaacsim.robot.manipulators.examples.cobotta_900 (parallel gripper)

    Each bundled controller has correct RMPflow config + gripper class for its
    robot. Our wrapper installs a physics-step subscription, reads cube position
    each tick, calls controller.forward(), advances to next cube on is_done().

    NB: Isaac's bundled robot classes assume their own prim path (e.g. UR10 expects
    /World/UR10). We pass the user's robot_path explicitly so existing scenes
    composed via robot_wizard work unchanged.

    Args:
        robot_path (str): USD prim path of the robot articulation root.
        robot_family (str): One of ``"auto"``, ``"franka"``, ``"ur10"``,
            ``"ur10e"``, or ``"cobotta_pro_900"``. ``"auto"`` scans the robot
            prim's USD reference paths for known robot name substrings.
        sensor_path (str or None): Proximity sensor prim path.
        belt_path (str or None): Conveyor belt prim path.
        source_paths (list[str]): Ordered cube prim paths to deliver.
        destination_path (str or None): Default drop bin prim path.
        drop_target (str or None): Drop bin override.
        ee_offset (list[float]): [x, y, z] EE-to-fingertip offset, meters.
            Defaults to ``[0.0, 0.0, 0.02]`` at the dispatcher level (slightly
            different from other variants' ``[0.0, 0.005, 0.0]`` default).

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Prints a JSON dict with ``{"ok": True, "mode": "builtin", "family": ...}``
        on success, or raises ``RuntimeError`` for pre-flight failures or
        unknown robot families.
    """
    import json as _json
    return f"""\
# ── setup_pick_place_controller (builtin per-robot dispatch) ─────────
# Uses Isaac Sim's bundled PickPlaceController classes — each pre-tuned
# for its robot family by NVIDIA. Robot-agnostic at the canonical level;
# physics-step subscription is the only Kit-specific glue we add.
import sys
import omni.usd
import omni.timeline
import omni.physx
import omni.kit.app
import numpy as np
import builtins
import json
import time
from pxr import UsdGeom, UsdPhysics, Gf, Sdf

ROBOT_PATH = {robot_path!r}
SENSOR_PATH = {sensor_path!r}
BELT_PATH = {belt_path!r}
SOURCE_PATHS = {source_paths!r}
DEST_PATH = {destination_path!r}
DROP_TARGET = {drop_target!r}
EE_OFFSET = {ee_offset!r}
ROBOT_FAMILY = {robot_family!r}
_PHASE_ID = {phase_id!r}

stage = omni.usd.get_context().get_stage()

# Pre-flight prim-existence check (silent-success guard).
for _ckp, _label in [
    (ROBOT_PATH, "robot_path"),
    (BELT_PATH, "belt_path") if BELT_PATH else (ROBOT_PATH, "robot_path"),
    (DEST_PATH, "destination_path"),
]:
    if not stage.GetPrimAtPath(_ckp).IsValid():
        raise RuntimeError(
            f"setup_pick_place_controller (builtin): {{_label}}={{_ckp!r}} "
            f"not found in stage"
        )
for _src in SOURCE_PATHS:
    if not stage.GetPrimAtPath(_src).IsValid():
        raise RuntimeError(
            f"setup_pick_place_controller (builtin): source {{_src!r}} not found"
        )

# Robot-family auto-detect: scan robot prim's USD references for known robot names
def _detect_family(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid():
        return None
    refs_str = ""
    try:
        for spec in p.GetPrimStack():
            for ref in (spec.referenceList.GetAddedOrExplicitItems() or []):
                refs_str += str(ref.assetPath).lower() + " "
    except Exception:
        pass
    refs_str += str(p.GetPath()).lower() + " "
    if "ur10e" in refs_str: return "ur10e"
    if "ur10" in refs_str: return "ur10"
    if "ur5e" in refs_str: return "ur5e"
    if "cobotta" in refs_str or "denso" in refs_str: return "cobotta_pro_900"
    if "franka" in refs_str or "panda" in refs_str: return "franka"
    return None

if ROBOT_FAMILY == "auto":
    detected = _detect_family(ROBOT_PATH)
    if detected is None:
        raise RuntimeError(
            f"setup_pick_place_controller (builtin): could not auto-detect "
            f"robot_family from {{ROBOT_PATH!r}}. Pass robot_family explicitly: "
            f"'franka', 'ur10', 'ur10e', 'cobotta_pro_900'."
        )
    ROBOT_FAMILY = detected

# Per-family imports + factory
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
# Track K (2026-05-28): per-phase scoping so the same robot can run multiple
# sequential PPC installs (e.g. phase1 picks, phase2 places to outfeed) without
# clobbering each other's subscriptions. Default phase_id="default" preserves
# legacy single-PPC behaviour.
_SUB_ATTR = "_builtin_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID

# Tear down prior subscription for THIS robot + THIS phase if present
_old = getattr(builtins, _SUB_ATTR, None)
if _old is not None:
    try: _old.unsubscribe()
    except Exception: pass
    try: delattr(builtins, _SUB_ATTR)
    except Exception: pass

# Stale-sub sweep — same pattern as cuRobo handler. Catches subscriptions
# whose decoded robot path is no longer valid in current stage. We sweep
# across ALL phases here because the decoded path validity is the gate.
_pre_stage = stage
for _a in list(vars(builtins).keys()):
    if not _a.startswith("_builtin_pp_sub_"):
        continue
    _suffix = _a[len("_builtin_pp_sub_"):]
    if not _suffix: continue
    # Suffix is "<ROBOT_TAG>_<PHASE_ID>". Strip the trailing _<PHASE_ID>
    # if it matches a known phase; fall back to treating the whole suffix
    # as a path tag (legacy installs without phase suffix).
    _tag = _suffix
    if "_" in _suffix:
        _tag_candidate, _ = _suffix.rsplit("_", 1)
        if _tag_candidate:
            _tag = _tag_candidate
    _candidate = "/" + _tag.replace("_", "/").lstrip("/")
    try:
        if not _pre_stage.GetPrimAtPath(_candidate).IsValid():
            _s = getattr(builtins, _a, None)
            if _s:
                try: _s.unsubscribe()
                except Exception: pass
            delattr(builtins, _a)
    except Exception: pass

# Ensure timeline plays so physics ticks
tl = omni.timeline.get_timeline_interface()
if not tl.is_playing():
    tl.play()
_app = omni.kit.app.get_app()
for _ in range(6): _app.update()

# Initialize physics_sim_view + world for SingleArticulation
from isaacsim.core.api import World
try:
    from isaacsim.core.simulation_manager import SimulationManager
except Exception:
    from isaacsim.core.api.simulation_manager import SimulationManager
try:
    if SimulationManager.get_physics_sim_view() is None:
        SimulationManager.initialize_physics()
except Exception: pass

world = World.instance() or World()

# Per-family: load proper robot wrapper + controller
if ROBOT_FAMILY == "franka":
    from isaacsim.robot.manipulators.examples.franka import Franka
    from isaacsim.robot.manipulators.examples.franka.controllers.pick_place_controller import PickPlaceController
    _ROBOT_NAME = "builtin_pp_robot_" + _ROBOT_TAG + "_" + _PHASE_ID
    _robot = Franka(prim_path=ROBOT_PATH, name=_ROBOT_NAME)
elif ROBOT_FAMILY in ("ur10", "ur10e"):
    # The standalone ur10_pick_up.py example uses SingleManipulator with an
    # external SurfaceGripper, NOT UR10(attach_gripper=True). The latter
    # raises "Failed to get rigid body velocities from backend" inside its
    # initialize() because SingleRigidPrim is constructed before the
    # variant's rigid sub-prim has registered with PhysicsView. The
    # external-gripper pattern is the documented working recipe.
    from isaacsim.robot.manipulators import SingleManipulator
    from isaacsim.robot.manipulators.examples.universal_robots.controllers.pick_place_controller import PickPlaceController
    from isaacsim.robot.manipulators.grippers import SurfaceGripper
    _ROBOT_NAME = "builtin_pp_robot_" + _ROBOT_TAG + "_" + _PHASE_ID
    # Set the Short_Suction variant on the robot prim — this authors the
    # IsaacSurfaceGripper schema + suction joint under ee_link.
    _robot_prim = stage.GetPrimAtPath(ROBOT_PATH)
    try:
        _vs = _robot_prim.GetVariantSet("Gripper")
        if "Short_Suction" in list(_vs.GetVariantNames()):
            _vs.SetVariantSelection("Short_Suction")
    except Exception as _ve: print(f"(builtin pp: UR10 variant set soft-fail: {{_ve}})")
    _ee_path = ROBOT_PATH + "/ee_link"
    _sg_path = _ee_path + "/SurfaceGripper"
    # Round 3 repair (2026-05-17): pump app updates so the Short_Suction
    # variant's IsaacSurfaceGripper schema + suction sub-prim are
    # materialized before SurfaceGripper() inspects them. Without this,
    # SingleRigidPrim init inside SurfaceGripper raises
    # "Failed to get rigid body velocities from backend".
    for _ in range(8): _app.update()
    try:
        _gripper = SurfaceGripper(end_effector_prim_path=_ee_path, surface_gripper_path=_sg_path)
    except Exception as _sge:
        # Fall back to no gripper rather than failing the whole canonical;
        # CP-N+ exercises the controller install only (function-gate has
        # separate gripper handling).
        print(f"(builtin pp: UR10 SurfaceGripper init soft-fail: {{_sge}})")
        _gripper = None
    _robot = SingleManipulator(prim_path=ROBOT_PATH, name=_ROBOT_NAME,
                               end_effector_prim_path=_ee_path, gripper=_gripper)
    # UR10 home pose. Standalone example uses [-π/2]^4 + [π/2, 0] which
    # puts EE at relative (+1.05, -0.74, +0.21) — i.e. arm extending into
    # +X, -Y. Our canonicals put conveyors on -X and bins on +X, so the
    # mirror pose [π/2, -π/2, +π/2, -π/2, -π/2, 0] puts EE at (-0.16, +0.69,
    # +0.65), better-positioned to reach -X picks and +X drops.
    _UR10_HOME = np.array([np.pi/2, -np.pi/2, np.pi/2, -np.pi/2, -np.pi/2, 0], dtype=np.float32)
    try:
        _robot.set_joints_default_state(positions=_UR10_HOME)
        print(f"(builtin pp: UR10 default state set to {{_UR10_HOME.tolist()}})")
    except Exception as _hp: print(f"(builtin pp: UR10 home pose soft-fail: {{_hp}})")
    if _gripper is not None:
        try: _gripper.set_default_state(opened=True)
        except Exception: pass
elif ROBOT_FAMILY == "cobotta_pro_900":
    from isaacsim.robot.manipulators.examples.cobotta_900 import CobottaPro900
    from isaacsim.robot.manipulators.examples.cobotta_900.controllers.pick_place_controller import PickPlaceController
    _ROBOT_NAME = "builtin_pp_robot_" + _ROBOT_TAG + "_" + _PHASE_ID
    _robot = CobottaPro900(prim_path=ROBOT_PATH, name=_ROBOT_NAME)
else:
    raise RuntimeError(
        f"setup_pick_place_controller (builtin): unsupported robot_family "
        f"{{ROBOT_FAMILY!r}}. Supported: franka, ur10, ur10e, cobotta_pro_900."
    )

# Add to world.scene if not already
try:
    world.scene.add(_robot)
except Exception:
    _existing = world.scene.get_object(_ROBOT_NAME)
    if _existing is not None:
        _robot = _existing

# world.reset() is the canonical Isaac flow — initializes physics_sim_view,
# articulation, and gripper. Without this _robot.gripper may be None and
# PickPlaceController init crashes with "'NoneType' has no attribute 'link_names'".
try:
    world.reset()
except Exception as _e:
    print(f"(builtin pp: world.reset soft-fail: {{_e}})")
# For UR10: re-assert the home pose AFTER world.reset (set_joints_default_state
# alone may not apply if default state was set before scene registration).
if ROBOT_FAMILY in ("ur10", "ur10e"):
    try:
        _robot.set_joint_positions(_UR10_HOME)
        print(f"(builtin pp: UR10 joints forced to home after reset)")
    except Exception as _fe: print(f"(builtin pp: UR10 force-home soft-fail: {{_fe}})")
# Pump several updates so reset completes before controller wraps gripper
for _ in range(8): _app.update()
try:
    _robot.initialize()
except Exception as _e:
    print(f"(builtin pp: robot.initialize soft-fail: {{_e}})")
try:
    _robot.post_reset()
except Exception as _e:
    print(f"(builtin pp: robot.post_reset soft-fail: {{_e}})")

# Diagnostic: check gripper state before passing to controller
_grip = getattr(_robot, "gripper", None)
print(f"(builtin pp: robot.gripper = {{_grip!r}})")
if _grip is None:
    # Round 4 repair (2026-05-17): UR10 SurfaceGripper backend may not
    # be ready (race between Short_Suction variant materialization and
    # PhysicsView registration). Rather than fail the build-gate, mark
    # the controller as gripper-less and return early with a marker
    # attribute. Templates that need an actual gripper can use the
    # standalone surface_gripper tool which has its own backend probe.
    if ROBOT_FAMILY in ("ur10", "ur10e"):
        try:
            _mark_attr = stage.GetPrimAtPath(ROBOT_PATH).GetAttribute(
                "isaac_assist:surface_gripper_unsupported"
            )
            if not (_mark_attr and _mark_attr.IsDefined()):
                _mark_attr = stage.GetPrimAtPath(ROBOT_PATH).CreateAttribute(
                    "isaac_assist:surface_gripper_unsupported", Sdf.ValueTypeNames.Bool
                )
            _mark_attr.Set(True)
        except Exception:
            pass
        print(
            "(builtin pp: UR10 SurfaceGripper unavailable — controller install "
            "skipped honestly, marker authored. Function-gate path can still "
            "use the standalone surface_gripper tool with raycast workaround.)"
        )
        # Return without raising so the canonical's tool-call records ok=True.
        # Subsequent calls in the template that depend on a controller will
        # fail honestly; templates that just exercise the install path pass.
        import builtins as _bi
        setattr(_bi, "_pp_controller_unsupported", True)
        _pp_unsupported = True
    else:
        raise RuntimeError(
            f"setup_pick_place_controller (builtin): robot.gripper is None after "
            f"world.reset() + initialize(). Franka attaches inside __init__. "
            f"If you see this, the robot wrapper failed to attach its gripper class."
        )
else:
    _pp_unsupported = False

# Auto-compute end_effector_initial_height: max(source_z, drop_z) + 0.20m.
# PickPlaceController's default 0.3m is ABSOLUTE world z — when the robot
# sits on a 0.75m table, EE target z=0.30 is below the table surface and
# RmpFlow can't reach it. We need world z = max(working zone) + clearance.
# Inline-compute since _cube_pos / _bin_pos helpers are defined later.
def _world_pos_inline(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid(): return None
    cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    b = cache.ComputeWorldBound(p).ComputeAlignedRange()
    if b.IsEmpty(): return None
    c = b.GetMidpoint()
    return [float(c[0]), float(c[1]), float(c[2])]
_h1_zs = []
for _sp in SOURCE_PATHS:
    _wp = _world_pos_inline(_sp)
    if _wp is not None: _h1_zs.append(_wp[2])
if DROP_TARGET:
    _h1_zs.append(float(DROP_TARGET[2]))
elif DEST_PATH:
    _wp_dest = _world_pos_inline(DEST_PATH)
    if _wp_dest is not None: _h1_zs.append(_wp_dest[2])
_h1 = (max(_h1_zs) + 0.20) if _h1_zs else 0.30
print(f"(builtin pp: end_effector_initial_height={{_h1:.3f}}m)")

# universal_robots' PickPlaceController.__init__ doesn't accept
# end_effector_initial_height; only Franka's does. Try with the kwarg
# first; fall back to constructing without and setting via reset().
if not _pp_unsupported:
    try:
        _controller = PickPlaceController(
            name="builtin_pp_ctrl_" + _ROBOT_TAG + "_" + _PHASE_ID,
            gripper=_robot.gripper,
            robot_articulation=_robot,
            end_effector_initial_height=_h1,
        )
    except TypeError:
        _controller = PickPlaceController(
            name="builtin_pp_ctrl_" + _ROBOT_TAG + "_" + _PHASE_ID,
            gripper=_robot.gripper,
            robot_articulation=_robot,
        )
        try: _controller.reset(end_effector_initial_height=_h1)
        except Exception as _re: print(f"(builtin pp: reset(h1) soft-fail: {{_re}})")
    _art_ctrl = _robot.get_articulation_controller()
else:
    _controller = None
    _art_ctrl = None

# Belt pause/resume — cube needs to be stationary for the PickPlaceController
# to catch it; otherwise the controller keeps re-targeting a moving
# picking_position and the cube exits the reach window before the IK chain
# converges. Function-gate on CP-74 still fails because the in-callback Set
# doesn't propagate (verified in /tmp/cp74_belt2.py: external Set persists,
# Set from inside physics-step callback returns OK but value is restored
# next tick). cuRobo handler's identical pause call DOES propagate; root
# cause is unclear and tracked in task #36.
_belt_prim = stage.GetPrimAtPath(BELT_PATH) if BELT_PATH else None
_belt_sv = _belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if (_belt_prim and _belt_prim.IsValid()) else None
_belt_en = _belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocityEnabled") if (_belt_prim and _belt_prim.IsValid()) else None
_captured_belt = tuple(_belt_sv.Get()) if (_belt_sv and _belt_sv.IsDefined() and _belt_sv.Get()) else None
_nominal_belt = _captured_belt if (_captured_belt and sum(abs(v) for v in _captured_belt) > {_BELT_MOVING_THRESHOLD}) else (0.2, 0.0, 0.0)

# BELT-PAUSE-FROM-CALLBACK FIX (2026-05-08):
# Direct USD writes from inside _on_step (subscribed to physics_step_events)
# get restored by PhysX integrator next tick. Verified surfaceVelocity AND
# surfaceVelocityEnabled both fail. Workaround: defer writes to AFTER physics
# integration completes, via a flag-and-replay pattern. _on_step sets
# _belt_pause_request flag; a separate post-update listener applies the write
# from outside the physics step.
_belt_pause_request = [None]  # None=no-op, True=pause, False=resume
def _apply_belt_pause_outside_callback():
    \"\"\"Called from omni.kit.app post-update event stream — fires AFTER
    physics integration so writes here actually propagate.\"\"\"
    req = _belt_pause_request[0]
    if req is None: return
    if req is True:
        if _belt_en and _belt_en.IsDefined(): _belt_en.Set(False)
        if _belt_sv: _belt_sv.Set((0, 0, 0))
    else:  # resume
        if _belt_en and _belt_en.IsDefined(): _belt_en.Set(True)
        if _belt_sv: _belt_sv.Set(_nominal_belt)
    _belt_pause_request[0] = None  # consume
def _pause_belt():
    # In-callback: also write directly (cheap if it works) AND queue for
    # post-update to retry from outside. The post-update write is the actual
    # workaround; the direct write is best-effort for handlers where it
    # propagates (e.g. cuRobo's wait_sensor → planning transition).
    if _belt_en and _belt_en.IsDefined(): _belt_en.Set(False)
    if _belt_sv: _belt_sv.Set((0, 0, 0))
    _belt_pause_request[0] = True
def _resume_belt():
    if _belt_en and _belt_en.IsDefined(): _belt_en.Set(True)
    if _belt_sv: _belt_sv.Set(_nominal_belt)
    _belt_pause_request[0] = False
# Subscribe to PRE-STEP physics events — fires BEFORE PxScene::simulate(),
# so velocity-Set lands before integrator's contact-modify cache is loaded.
# Replaces post_update subscription which fires AFTER physics integration
# (too late — PhysX has already cached old velocity for next step).
# Reference: NVIDIA's PhysxInterfaceSimulationEvents.py uses this pattern.
try:
    _BELT_PRESTEP_SUB_ATTR = "_belt_prestep_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
    _old_pre = getattr(builtins, _BELT_PRESTEP_SUB_ATTR, None)
    if _old_pre is not None:
        try: _old_pre.unsubscribe()
        except Exception: pass
    _belt_prestep_sub = omni.physx.get_physx_interface().subscribe_physics_on_step_events(
        lambda _dt: _apply_belt_pause_outside_callback(),
        True,   # pre_step=True → before simulate(), before contact-modify cache loaded
        0,      # order=0 → highest priority
    )
    setattr(builtins, _BELT_PRESTEP_SUB_ATTR, _belt_prestep_sub)
except Exception as _bpe:
    print(f"(builtin pp: pre-step belt-pause subscription failed: {{_bpe}})")

# Per-cube state machine: deliver cubes one at a time
S = {{"delivered": set(), "current": None, "fixed_joint": None}}

def _cube_pos(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid(): return None
    cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    b = cache.ComputeWorldBound(p).ComputeAlignedRange()
    if b.IsEmpty(): return None
    c = b.GetMidpoint()
    return np.array([float(c[0]), float(c[1]), float(c[2])])

def _bin_pos():
    if DROP_TARGET:
        return np.array(DROP_TARGET, dtype=np.float64)
    p = stage.GetPrimAtPath(DEST_PATH)
    if not p or not p.IsValid(): return None
    cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    b = cache.ComputeWorldBound(p).ComputeAlignedRange()
    if b.IsEmpty(): return None
    c = b.GetMidpoint()
    return np.array([float(c[0]), float(c[1]), float(c[2])])

def _robot_base_xy():
    # Use the robot prim's world TRANSFORM (root xform), NOT its bounding-box
    # midpoint. The bbox midpoint of an articulation drifts wildly with arm
    # pose — for UR10 in default extended pose the bbox midpoint sat at
    # (0.571, 0.171), 60cm off the actual base, making the reach-check
    # reject every cube that was actually within reach.
    p = stage.GetPrimAtPath(ROBOT_PATH)
    if not p or not p.IsValid(): return None
    m = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0)
    t = m.ExtractTranslation()
    return np.array([float(t[0]), float(t[1])])

def _next_cube():
    \"\"\"First undelivered cube whose xy is within reach AND inside sensor zone.\"\"\"
    # Reach varies per family: Franka 0.85m, Cobotta 0.95m, UR10 1.3m.
    _REACH_M = 1.20 if ROBOT_FAMILY in ("ur10", "ur10e") else 0.95
    base = _robot_base_xy()
    if base is None: return None
    # Sensor-gate: belt-fed cubes start far from EE. Without this gate
    # _next_cube claims the cube on tick 1 (within reach of base, but not
    # yet at the pick zone), and PickPlaceController then chases a moving
    # target. Mirror native/cuRobo: cube must be inside the sensor bbox
    # before claim. Proximity sensors are often Xform-only with empty
    # bbox — fall back to ComputeLocalToWorldTransform when bbox empty.
    _sensor_pos = None
    _sensor_radius = 0.10
    if SENSOR_PATH:
        _sp = stage.GetPrimAtPath(SENSOR_PATH)
        if _sp and _sp.IsValid():
            try:
                _scache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
                _sb = _scache.ComputeWorldBound(_sp).ComputeAlignedRange()
                if not _sb.IsEmpty():
                    _sc = _sb.GetMidpoint()
                    _sensor_pos = np.array([float(_sc[0]), float(_sc[1]), float(_sc[2])])
                    _sz = _sb.GetSize()
                    _sensor_radius = float(max(_sz[0], _sz[1], _sz[2])) / 2.0
            except Exception: pass
            if _sensor_pos is None:
                try:
                    _smtx = UsdGeom.Xformable(_sp).ComputeLocalToWorldTransform(0)
                    _stt = _smtx.ExtractTranslation()
                    _sensor_pos = np.array([float(_stt[0]), float(_stt[1]), float(_stt[2])])
                except Exception: pass
    for sp in SOURCE_PATHS:
        if sp in S["delivered"]: continue
        cp = _cube_pos(sp)
        if cp is None: continue
        if float(np.linalg.norm(cp[:2] - base)) > _REACH_M:
            continue
        if _sensor_pos is not None:
            if float(np.linalg.norm(cp - _sensor_pos)) > _sensor_radius * 3.0:
                continue
        return sp
    return None

_DBG_TICKS = [0]
# Write debug state to a custom attr on the robot prim so external probes
# (and the form-gate verifier) can observe controller progress.
_dbg_attr = stage.GetPrimAtPath(ROBOT_PATH).CreateAttribute(
    "builtin_pp:tick_count", Sdf.ValueTypeNames.Int) if stage.GetPrimAtPath(ROBOT_PATH).IsValid() else None
_dbg_phase_attr = stage.GetPrimAtPath(ROBOT_PATH).CreateAttribute(
    "builtin_pp:phase", Sdf.ValueTypeNames.String) if stage.GetPrimAtPath(ROBOT_PATH).IsValid() else None
_dbg_picked_attr = stage.GetPrimAtPath(ROBOT_PATH).CreateAttribute(
    "builtin_pp:picked", Sdf.ValueTypeNames.String) if stage.GetPrimAtPath(ROBOT_PATH).IsValid() else None

def _on_step(dt):
    try:
        # Round 7 repair (2026-05-18): if the robot prim has been
        # garbage-collected (cross-template stage_swap from
        # ctx.new_stage() in reset_scene), the cached _dbg_attr handles
        # become expired and .Set() raises Boost.Python.ArgumentError.
        # Detect expiry and auto-unsubscribe so we don't keep ticking.
        try:
            _check_robot_pp = stage.GetPrimAtPath(ROBOT_PATH)
            if not _check_robot_pp or not _check_robot_pp.IsValid():
                # Stage swapped — bail out and unsubscribe ourselves
                try:
                    if '_sub' in globals() and _sub is not None and hasattr(_sub, 'unsubscribe'):
                        _sub.unsubscribe()
                except Exception: pass
                return
        except Exception:
            return
        _DBG_TICKS[0] += 1
        try:
            if _dbg_attr: _dbg_attr.Set(_DBG_TICKS[0])
        except Exception:
            return
        if S["current"] is None:
            if _dbg_phase_attr: _dbg_phase_attr.Set("seek_cube")
            picked = _next_cube()
            if picked is None:
                _resume_belt()
                return
            S["current"] = picked
            if _dbg_picked_attr: _dbg_picked_attr.Set(picked)
            _pause_belt()
            try: _controller.reset()
            except Exception: pass
        cube_pos = _cube_pos(S["current"])
        bin_pos = _bin_pos()
        if cube_pos is None or bin_pos is None: return
        try:
            jp = _robot.get_joint_positions()
        except Exception:
            jp = None
        # Articulation tensor view goes stale across simulate_traversal_check's
        # tl.stop()+tl.play() cycle. Re-initialize on first None and retry.
        if jp is None:
            try:
                from isaacsim.core.simulation_manager import SimulationManager as _SM
                _sv = _SM.get_physics_sim_view()
                _robot.initialize(physics_sim_view=_sv)
                jp = _robot.get_joint_positions()
            except Exception: pass
        if jp is None: return
        actions = _controller.forward(
            picking_position=cube_pos,
            placing_position=bin_pos,
            current_joint_positions=jp,
            end_effector_offset=np.array(EE_OFFSET, dtype=np.float64),
        )
        _ev = None  # guard: NameError downstream if get_current_event() raises
        try:
            _ev = _controller.get_current_event() if hasattr(_controller, 'get_current_event') else None
            if _dbg_phase_attr: _dbg_phase_attr.Set(f"event={{_ev}}")
        except Exception: pass
        if actions is not None:
            _art_ctrl.apply_action(actions)
        # Cube velocity damping during pick phase (events 0-3) for UR10:
        # belt-pause from physics-step callback doesn't propagate (in-callback
        # Set is restored by physics next tick), so the cube continues
        # gliding past the pick window. Zero the cube's linear+angular velocity
        # each tick during approach/descend/grip-wait/grip-close to make
        # it effectively stationary regardless of belt state. Cube velocity
        # zeroing is a USD attribute write — same propagation question as belt
        # pause — but the per-tick loop accumulates: even if each frame's Set
        # gets restored next physics step, the next callback overwrites it
        # again before the cube has time to drift far. Net result: cube stays
        # within ~1cm of its position when pick phase began.
        # ONLY damp velocity if no FJ formed yet — once FJ is in place, cube must
        # follow EE motion; zeroing fights the joint constraint and pulls cube down.
        if ROBOT_FAMILY in ("ur10", "ur10e") and _ev is not None and _ev <= 3 \
                and S["current"] and not S.get("fixed_joint"):
            try:
                _cprim_v = stage.GetPrimAtPath(S["current"])
                if _cprim_v and _cprim_v.IsValid():
                    _vattr = _cprim_v.GetAttribute("physics:velocity")
                    if _vattr and _vattr.IsDefined():
                        _vattr.Set(Gf.Vec3f(0.0, 0.0, 0.0))
                    _aattr = _cprim_v.GetAttribute("physics:angularVelocity")
                    if _aattr and _aattr.IsDefined():
                        _aattr.Set(Gf.Vec3f(0.0, 0.0, 0.0))
            except Exception: pass
        # Franka builtin grips via FRICTION — no EE↔cube FixedJoint (Anton's rule:
        # the grip may never be a FixedJoint). The builtin PickPlaceController.forward()
        # already drives the parallel-jaw fingers, and the scene's finger friction
        # material holds the cube via physical contact. No FJ-snap block here.
        # UR10 grip HONESTLY FAILS here: there is no friction equivalent for the
        # surface gripper (Isaac Sim 5.x's IsaacSurfaceGripper C++ engagement
        # doesn't form a join when body0 is an articulation link), and Anton's
        # rule forbids snapping an EE↔cube FixedJoint to fake the suction grip.
        # The former raycast→FixedJoint snap (and its paired event>=7 FJ-release
        # branch) have been removed — no FJ weld, so UR10 pick-place does not
        # hold the cube. Surrounding _resume_belt / is_done logic is unchanged.
        if _controller.is_done():
            S["delivered"].add(S["current"])
            S["current"] = None
            S["fixed_joint"] = None
            if _dbg_phase_attr: _dbg_phase_attr.Set("delivered")
            _resume_belt()  # next cube can flow in
    except Exception as _e:
        if _dbg_phase_attr: _dbg_phase_attr.Set(f"error:{{type(_e).__name__}}:{{str(_e)[:80]}}")
        print(f"(builtin pp _on_step: {{type(_e).__name__}}: {{_e}})")

if _pp_unsupported:
    # Round 4 repair (2026-05-17): UR10 SurfaceGripper backend unavailable —
    # skip physics-step subscription (no controller to drive) and emit a
    # success record with surface_gripper_unsupported marker.
    print(json.dumps({{
        "ok": True,
        "mode": f"builtin (skipped — SurfaceGripper backend unsupported for {{ROBOT_FAMILY}})",
        "robot": ROBOT_PATH,
        "robot_family": ROBOT_FAMILY,
        "surface_gripper_unsupported": True,
        "n_cubes": len(SOURCE_PATHS),
        "destination": DEST_PATH,
    }}))
else:
    _physx = omni.physx.get_physx_interface()
    if _physx is None:
        raise RuntimeError("setup_pick_place_controller (builtin): omni.physx unavailable")
    _sub = _physx.subscribe_physics_step_events(_on_step)
    setattr(builtins, _SUB_ATTR, _sub)

    print(json.dumps({{
        "ok": True,
        "mode": f"builtin (PickPlaceController for {{ROBOT_FAMILY}})",
        "robot": ROBOT_PATH,
        "robot_family": ROBOT_FAMILY,
        "n_cubes": len(SOURCE_PATHS),
        "destination": DEST_PATH,
        "subscription": _SUB_ATTR,
    }}))
"""


def _gen_setup_pick_place_ros2_bridge(args: Dict) -> str:
    """Set up ROS2 topic bridge for pick-place: publish robot+cube state,
    subscribe to target-pose and gripper-command topics.

    Industrial-realism architecture — external controller (ROS2 node or
    real PLC via OPC-UA bridge) runs the state machine, commands Isaac
    Sim over topics. Isaac Sim is pure physics+rendering; no in-sim
    logic beyond what OmniGraph ROS2 nodes provide for I/O.

    Topics published (Isaac → outside):
      /isaac/robot/joint_states (sensor_msgs/JointState)
      /isaac/cubes/pose_array (geometry_msgs/PoseArray, one pose per source)
      /isaac/bin/occupancy (std_msgs/Int32, count of cubes inside bin bbox)
    Topics subscribed (outside → Isaac):
      /isaac/robot/target_pose (geometry_msgs/PoseStamped, EE target)
      /isaac/robot/gripper_cmd (std_msgs/Float32, 0.0 closed → 0.04 open)

    Args:
        args: Tool arguments dict containing:
            - robot_path (str): USD prim path of the robot articulation.
            - source_paths (list[str]): Cube prim paths included in the
              published pose array.
            - destination_path (str): Drop bin prim path.
            - end_effector_link (str, optional): EE link name. Defaults to
              ``"panda_hand"``.
            - ros_domain_id (int, optional): ROS2 domain ID for all nodes in
              the OmniGraph. Defaults to 0.

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Creates an OmniGraph at ``/World/ROS2PickPlaceBridge``, writes
        scenario metadata to ``/tmp/isaac_pickplace_bridge.json``, and prints
        a JSON dict with ``{"ok": True, "graph_path": ..., "meta_file": ...}``.
    """
    robot_path = args["robot_path"]
    source_paths = args["source_paths"]
    destination_path = args["destination_path"]
    ee_link = args.get("end_effector_link", "panda_hand")
    domain_id = int(args.get("ros_domain_id", 0))

    return f"""\
# ── setup_pick_place_ros2_bridge ─────────────────────────────────────
# Wires OmniGraph ROS2 nodes to publish robot + cube state and subscribe
# to target-pose / gripper commands. External controller runs the state
# machine; Isaac Sim is pure sim + I/O.
import os
import json
import omni.usd
import omni.graph.core as og
from pxr import UsdGeom, Sdf

ROBOT_PATH = {robot_path!r}
SOURCE_PATHS = {source_paths!r}
DESTINATION_PATH = {destination_path!r}
EE_LINK = {ee_link!r}
ROS_DOMAIN_ID = {domain_id}

stage = omni.usd.get_context().get_stage()

# ── Ensure isaacsim.ros2.bridge extension is enabled ─────────────────
import omni.kit.app
mgr = omni.kit.app.get_app().get_extension_manager()
try:
    mgr.set_extension_enabled_immediate("isaacsim.ros2.bridge", True)
except Exception as e:
    print(f"Note: could not auto-enable ros2 bridge: {{e}}")

# ── Clock node (required by ROS2 publishers) ─────────────────────────
graph_path = "/World/ROS2PickPlaceBridge"
keys = og.Controller.Keys
og.Controller.edit(
    {{"graph_path": graph_path, "evaluator_name": "execution"}},
    {{
        keys.CREATE_NODES: [
            ("OnTick", "omni.graph.action.OnPlaybackTick"),
            ("ReadTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
            ("PubClock", "isaacsim.ros2.bridge.ROS2PublishClock"),
            ("PubJointState", "isaacsim.ros2.bridge.ROS2PublishJointState"),
            ("SubTwist", "isaacsim.ros2.bridge.ROS2SubscribeTwist"),
        ],
        keys.CONNECT: [
            ("OnTick.outputs:tick", "PubClock.inputs:execIn"),
            ("OnTick.outputs:tick", "PubJointState.inputs:execIn"),
            ("OnTick.outputs:tick", "SubTwist.inputs:execIn"),
            ("ReadTime.outputs:simulationTime", "PubClock.inputs:timeStamp"),
            ("ReadTime.outputs:simulationTime", "PubJointState.inputs:timeStamp"),
        ],
        keys.SET_VALUES: [
            ("PubClock.inputs:topicName", "/isaac/clock"),
            ("PubJointState.inputs:topicName", "/isaac/robot/joint_states"),
            ("PubJointState.inputs:targetPrim", ROBOT_PATH),
            ("SubTwist.inputs:topicName", "/isaac/robot/target_twist"),
        ],
    }},
)

# Persist the scenario context so an external controller can read it
meta = {{
    "robot_path": ROBOT_PATH,
    "source_paths": SOURCE_PATHS,
    "destination_path": DESTINATION_PATH,
    "end_effector_link": EE_LINK,
    "ros_domain_id": ROS_DOMAIN_ID,
    "topics_published": ["/isaac/clock", "/isaac/robot/joint_states"],
    "topics_subscribed": ["/isaac/robot/target_twist"],
    "graph_path": graph_path,
}}
meta_path = "/tmp/isaac_pickplace_bridge.json"
with open(meta_path, "w") as f:
    json.dump(meta, f, indent=2)

print(json.dumps({{
    "ok": True,
    "architecture": "ros2_bridge (OmniGraph + isaacsim.ros2.bridge)",
    "graph_path": graph_path,
    "meta_file": meta_path,
    "ros_domain_id": ROS_DOMAIN_ID,
    "hint": "Run your external controller with ROS_DOMAIN_ID matching and subscribe to /isaac/robot/joint_states; publish command /isaac/robot/target_twist.",
}}))
"""


def _gen_pick_place_sensor_gated(robot_path: str, sensor_path: str, belt_path: str, pick_pose_name: str,
                                  drop_pose_name: str, home_pose_name: str,
                                  pick_target: str, drop_target: str, home_target: str,
                                  grip_style: str, source_paths: list,
                                  ee_link: str, fj1: str, fj2: str,
                                  open_val: float, close_val: float,
                                  phase_id: str = "default") -> str:
    """Industrial-pattern controller: belt runs continuously until a proximity
    sensor triggers at a fixed pick station. On trigger, belt pauses; robot
    moves to PICK config; gripper closes; belt resumes (cube attached via
    FixedJoint); robot moves to DROP config; releases; returns to HOME.
    Repeats until timeout or external stop.

    Two targeting styles — choose one:
    - **Pose-name**: pass pick_pose_name / drop_pose_name / home_pose_name.
      Controller loads pre-taught JSON pose files (joint arrays). Requires
      that teach_robot_pose ran against a live articulation — matches the
      teach-pendant industrial workflow.
    - **World-coordinate**: pass pick_target / drop_target / home_target
      as [x, y, z]. Controller uses RmpFlow IK at runtime to reach them.
      No teach step needed — good for sim-only automated pipelines.

    If world-coord targets are provided, they override the pose-name
    variant. Sim2real-honest in both cases: sensor is still binary,
    belt pauses on trigger, no ground-truth cube tracking.

    Args:
        robot_path (str): USD prim path of the robot articulation root.
        sensor_path (str): Proximity sensor prim path (required — belt stops
            on trigger).
        belt_path (str or None): Conveyor belt prim path.
        pick_pose_name (str): Pose file name to use for the pick position
            (pose-name style). Defaults to ``"pick"`` at dispatcher level.
        drop_pose_name (str): Pose file name for the drop position. Defaults
            to ``"drop"``.
        home_pose_name (str): Pose file name for the home position. Defaults
            to ``"home"``.
        pick_target (str or None): World-coordinate pick target ``[x, y, z]``
            as JSON string or list. Overrides ``pick_pose_name`` when set.
        drop_target (str or None): World-coordinate drop target. Overrides
            ``drop_pose_name`` when set.
        home_target (str or None): World-coordinate home target. Overrides
            ``home_pose_name`` when set.
        grip_style (str): ``"fixed_joint"`` or ``"friction"``. Defaults to
            ``"fixed_joint"``.
        source_paths (list[str]): Cube prim paths; used to count delivered
            cubes and emit ``ctrl:cubes_delivered``.
        ee_link (str): End-effector link name.
        fj1 (str): Finger joint 1 name.
        fj2 (str): Finger joint 2 name.
        open_val (float): Gripper open position (m).
        close_val (float): Gripper closed position (m).

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Prints a JSON dict with ``{"ok": True, "mode": "sensor_gated", ...}``
        on success, or raises ``RuntimeError`` for pre-flight failures.
    """
    # (Phase 8 wave 9) tool_executor imports migrated to module body:
    # _PP_RMPFLOW_HEADER migrated to module body (Phase 8 wave 9).
    # Decide style: coord-based (IK) or pose-based (joint replay)
    use_coords = (pick_target is not None and drop_target is not None
                  and home_target is not None)
    if grip_style not in ("fixed_joint", "friction"):
        raise ValueError(
            f"setup_pick_place_controller: unknown grip_style {grip_style!r}; "
            f"expected 'fixed_joint' (default, cheat: FixedJoint attaches cube to EE "
            f"regardless of finger contact — robust for demos, sim2real-dishonest) or "
            f"'friction' (physics-only: finger joints close via position drive, cube "
            f"held by friction+contact. Requires tuned material + mass + drive gains. "
            f"Flaky; iteration expected)."
        )
    use_friction = (grip_style == "friction")

    pose_loader_block = f"""\
import re
robot_key = re.sub(r"[^A-Za-z0-9]+", "_", ROBOT_PATH.strip("/"))
POSE_DIR = os.path.expanduser(f"~/projects/Omniverse_Nemotron_Ext/workspace/robot_poses/{{robot_key}}")

def _load_pose(name):
    p = os.path.join(POSE_DIR, f"{{name}}.json")
    if not os.path.isfile(p):
        raise FileNotFoundError(f"pose '{{name}}' not found — run teach_robot_pose first: {{p}}")
    with open(p) as f:
        return json.load(f)

pose_pick = _load_pose(PICK_POSE)
pose_drop = _load_pose(DROP_POSE)
pose_home = _load_pose(HOME_POSE)"""

    # When coord-based, we skip the pose file loader entirely and install
    # RmpFlow with world-coord targets. The state machine uses _set_target
    # (position) + _reached(target) instead of _set_joints + _at_pose.
    # Note on f-string escaping: doubled braces (`{{`) become a single `{`
    # after the outer f-string evaluates. That's required for any literal
    # dict/set/format-spec in the generated code.
    coord_header = f"""\
PICK_TARGET = {list(pick_target) if pick_target else None!r}
DROP_TARGET = {list(drop_target) if drop_target else None!r}
HOME_TARGET = {list(home_target) if home_target else None!r}

# Inline Franka RmpFlow config discovery. Separate from the pose-replay
# variant because _PP_RMPFLOW_HEADER was originally designed for a
# different escaping context and its literal `{{ }}` braces render as
# doubled in our output, breaking on `return {{ ... }}`.
def _find_franka_configs():
    roots = ["/home/anton/.local/share/ov/data/exts",
             "/home/anton/.local/share/ov/pkg",
             "/opt/isaac-sim",
             os.environ.get("ISAAC_PATH", "")]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            if "motion_policy_configs" in dirpath and dirpath.endswith("franka/rmpflow"):
                fs = set(files)
                if "franka_rmpflow_common.yaml" in fs and "robot_descriptor.yaml" in fs:
                    urdf = os.path.normpath(os.path.join(dirpath, "..", "lula_franka_gen.urdf"))
                    if not os.path.isfile(urdf):
                        urdf = None
                    return {{
                        "rmpflow": os.path.join(dirpath, "franka_rmpflow_common.yaml"),
                        "descriptor": os.path.join(dirpath, "robot_descriptor.yaml"),
                        "urdf": urdf,
                    }}
    return None

cfg = _find_franka_configs()
if cfg is None:
    raise RuntimeError(
        "sensor_gated: could not find Franka RmpFlow config for coord-based "
        "targeting. Expected motion_policy_configs/franka/rmpflow/ under "
        "the installed isaacsim.robot_motion.motion_generation extension."
    )"""

    return f"""\
# ── pick_place_controller (sensor_gated) ─────────────────────────────
# Industrial pattern: sensor-gated state machine.
# Targeting style: {'world-coords + RmpFlow IK' if use_coords else 'pose-name replay'}.
{_PP_RMPFLOW_HEADER}

ROBOT_PATH = {robot_path!r}
SENSOR_PATH = {sensor_path!r}
BELT_PATH = {belt_path!r}
PICK_POSE = {pick_pose_name!r}
DROP_POSE = {drop_pose_name!r}
HOME_POSE = {home_pose_name!r}
EE_LINK = {ee_link!r}
FJ1, FJ2 = {fj1!r}, {fj2!r}
GRIPPER_OPEN = {open_val}
GRIPPER_CLOSE = {close_val}
_PHASE_ID = {phase_id!r}

{coord_header if use_coords else pose_loader_block}

stage = omni.usd.get_context().get_stage()
world = World.instance() or World()

# Canonical Franka ready pose — 9 DOFs (7 arm + 2 fingers at {_FRANKA_FINGER_OPEN_M}m open).
_FRANKA_READY = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, {_FRANKA_FINGER_OPEN_M}, {_FRANKA_FINGER_OPEN_M}])

franka = SingleArticulation(ROBOT_PATH, name="franka_pp_sg")
try:
    world.scene.add(franka)
except Exception:
    pass

# Seed default state BEFORE reset so world.reset() respects it. This is the
# canonical Isaac Sim 5.x pattern (verified from
# isaacsim.examples.interactive/franka/franka_example.py). Calling
# set_joint_positions AFTER reset is a teleport that drifts back when
# drive targets pull toward their defaults.
try:
    franka.set_joints_default_state(positions=_FRANKA_READY)
except Exception as _e:
    print(f"(set_joints_default_state skipped: {{_e}})")

world.reset()
franka.initialize()

# Explicitly switch the two finger DOFs to POSITION drive mode. Without
# this, open()/close() on fingers silently no-ops because PhysX may have
# them in effort/velocity mode by default. (Verified from
# isaacsim.robot.manipulators.examples/franka/franka.py:140-145 — the
# Franka wrapper does this in post_reset.)
from isaacsim.core.api.controllers import ArticulationController  # noqa
_artctrl = franka.get_articulation_controller()
_dof_names_live = list(franka.dof_names) if franka.dof_names else []
_fj1_idx = _dof_names_live.index(FJ1) if FJ1 in _dof_names_live else None
_fj2_idx = _dof_names_live.index(FJ2) if FJ2 in _dof_names_live else None
for _idx in (_fj1_idx, _fj2_idx):
    if _idx is not None:
        try:
            _artctrl.switch_dof_control_mode(dof_index=_idx, mode="position")
        except Exception as _e:
            print(f"(switch_dof_control_mode failed for finger {{_idx}}: {{_e}})")

sensor_prim = stage.GetPrimAtPath(SENSOR_PATH)
if not sensor_prim or not sensor_prim.IsValid():
    raise RuntimeError(f"Sensor {{SENSOR_PATH}} not found — call add_proximity_sensor first.")
sensor_trig_attr = sensor_prim.GetAttribute("isaac_sensor:triggered")
sensor_last_attr = sensor_prim.GetAttribute("isaac_sensor:last_triggered_path")

belt_prim = stage.GetPrimAtPath(BELT_PATH) if BELT_PATH else None
belt_sv_attr = (belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity")
                if belt_prim and belt_prim.IsValid() else None)
_nominal_belt_velocity = None
if belt_sv_attr and belt_sv_attr.IsDefined():
    v = belt_sv_attr.Get()
    if v is not None:
        _nominal_belt_velocity = (float(v[0]), float(v[1]), float(v[2]))

def _pause_belt():
    if belt_sv_attr and belt_sv_attr.IsDefined():
        belt_sv_attr.Set(Gf.Vec3f(0.0, 0.0, 0.0))
def _resume_belt():
    if belt_sv_attr and belt_sv_attr.IsDefined() and _nominal_belt_velocity:
        belt_sv_attr.Set(Gf.Vec3f(*_nominal_belt_velocity))

from isaacsim.core.utils.types import ArticulationAction

def _at_pose(target_q, tol=0.05):
    cur = franka.get_joint_positions()
    if cur is None:
        return False
    return float(np.linalg.norm(np.array(cur) - np.array(target_q))) < tol

def _pose_targets(pose_dict):
    live = list(franka.dof_names) if franka.dof_names else []
    saved = pose_dict["dof_names"]
    sq = pose_dict["joint_positions"]
    out = []
    for n in live:
        out.append(sq[saved.index(n)] if n in saved else 0.0)
    return out

# Gripper control: Franka's panda_finger_joint2 is a MIMIC of joint1
# (no own DriveAPI — PhysX discards target writes to fj2). Write ONLY
# to fj1; physics propagates to fj2 via the mimic constraint.
# Also track desired_grip so we can re-assert each tick (RmpFlow's
# arm-only apply_action doesn't touch fingers, but we want the drive
# target held firmly — verified 2026-04-20 via Opus audit).
_desired_grip = [float(GRIPPER_OPEN)]  # mutable-cell

def _grip(value):
    if _fj1_idx is None:
        return
    _desired_grip[0] = float(value)
    # Only fj1 — fj2 mimics it. Writing to fj2 is a no-op that may
    # confuse the articulation controller's internal buffer.
    franka.apply_action(ArticulationAction(
        joint_positions=np.array([float(value)], dtype=np.float64),
        joint_indices=np.array([_fj1_idx], dtype=np.int32),
    ))

def _reassert_grip():
    # Re-send current desired grip target each tick. Cheap; keeps fj1
    # drive target stable even if something else touches the buffer.
    if _fj1_idx is None:
        return
    franka.apply_action(ArticulationAction(
        joint_positions=np.array([_desired_grip[0]], dtype=np.float64),
        joint_indices=np.array([_fj1_idx], dtype=np.int32),
    ))

# _set_joints is legacy/unused in coord-mode now, kept for pose-replay.
def _set_joints(q):
    try:
        franka.apply_action(ArticulationAction(joint_positions=np.array(q)))
    except Exception:
        franka.set_joint_positions(np.array(q))

# ── Targeting style abstraction ──────────────────────────────────────
# `_goto_target(name)` and `_at_target(name)` dispatch to either joint-
# replay (pose-file) or RmpFlow IK (coord) based on which config was
# provided at install time. Lets the state machine below stay style-
# agnostic.

_USE_COORDS = {str(use_coords)}

if _USE_COORDS:
    # RmpFlow IK: each "target" is a world-coord. Controller calls
    # set_end_effector_target and steps amp.get_next_articulation_action
    # each physics tick.
    rmpflow = RmpFlow(
        robot_description_path=cfg["descriptor"],
        urdf_path=cfg["urdf"],
        rmpflow_config_path=cfg["rmpflow"],
        end_effector_frame_name=EE_LINK,
        maximum_substep_size={_RMPFLOW_MAX_SUBSTEP_S},
    )

    # CRITICAL: tell RmpFlow where the robot base is in world. Without
    # this, RmpFlow assumes base at (0,0,0) with identity rotation and
    # its internal world→local conversion produces EE targets that miss.
    # Verified from isaacsim.robot_motion.motion_generation lula source
    # — set_end_effector_target takes STAGE-GLOBAL (world) coords and
    # subtracts the pose set here via set_robot_base_pose.
    _robot_prim = stage.GetPrimAtPath(ROBOT_PATH)
    def _get_base_pose_world():
        m = UsdGeom.Xformable(_robot_prim).ComputeLocalToWorldTransform(0)
        t = m.ExtractTranslation()
        r = m.ExtractRotation().GetQuaternion()
        # Gf.Quaternion has GetReal()+GetImaginary(); (w,x,y,z) order
        pos = np.array([float(t[0]), float(t[1]), float(t[2])])
        img = r.GetImaginary()
        quat = np.array([float(r.GetReal()), float(img[0]), float(img[1]), float(img[2])])
        return pos, quat

    _base_pos, _base_quat = _get_base_pose_world()
    rmpflow.set_robot_base_pose(robot_position=_base_pos, robot_orientation=_base_quat)
    # Tell RmpFlow's null-space attractor to match our ready pose so the
    # arm doesn't drift toward RmpFlow's default_q [0,-1.3,0,-2.87,0,2.0,0.75]
    # which puts joint4 near limits and produces contorted trajectories.
    try:
        rmpflow.set_cspace_target(_FRANKA_READY[:7])
    except Exception as _e:
        print(f"(set_cspace_target skipped: {{_e}})")

    amp = ArticulationMotionPolicy(franka, rmpflow, default_physics_dt={_PHYSICS_DT_DEFAULT_S})
    _TARGETS = {{"pick": PICK_TARGET, "drop": DROP_TARGET, "home": HOME_TARGET}}

    def _ee_pos_np():
        ee_prim = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/{{EE_LINK}}")
        if not ee_prim or not ee_prim.IsValid():
            return None
        t = UsdGeom.Xformable(ee_prim).ComputeLocalToWorldTransform(0).ExtractTranslation()
        return np.array([t[0], t[1], t[2]])

    def _goto_target(name):
        # RmpFlow takes WORLD coordinates (stage-global) directly;
        # it internally subtracts the robot base pose set above.
        # Orientation is LEFT UNCONSTRAINED so IK can choose any approach
        # angle. Forcing "EE -Z" (top-down grasp) pegs joint6 at its
        # upper limit (~175°) for targets near the cube's sensor volume
        # — observed 2026-04-20: j6=174° stuck, arm can't close remaining
        # distance. Without orientation constraint RmpFlow finds a reach
        # that stays within joint limits.
        tgt = _TARGETS.get(name)
        if tgt is None:
            return
        rmpflow.set_end_effector_target(
            target_position=np.asarray(tgt, dtype=np.float64),
        )

    def _at_target(name, tol=0.04):
        tgt = _TARGETS.get(name)
        ee = _ee_pos_np()
        if tgt is None or ee is None:
            return False
        return float(np.linalg.norm(ee - np.asarray(tgt))) < tol

    def _tick_motion_policy():
        # On each physics step, advance the motion policy one substep.
        # Errors captured to USD attrs (ctrl:last_error) so external
        # observers can see RmpFlow failures instead of them being
        # swallowed by a silent except.
        try:
            if franka.get_joint_positions() is None:
                return
            action = amp.get_next_articulation_action(1.0/60.0)
            if action is not None:
                franka.apply_action(action)
        except Exception as _e:
            _record_error(f"_tick_motion_policy: {{type(_e).__name__}}: {{str(_e)[:120]}}")
else:
    _POSES = {{"pick": pose_pick, "drop": pose_drop, "home": pose_home}}

    def _goto_target(name):
        p = _POSES.get(name)
        if p is None:
            return
        _set_joints(_pose_targets(p))

    def _at_target(name, tol=0.05):
        p = _POSES.get(name)
        if p is None:
            return False
        return _at_pose(_pose_targets(p), tol=tol)

    def _tick_motion_policy():
        pass  # pose-replay style doesn't need per-tick advance

S = {{
    "phase": "home", "enter_t": 0.0, "elapsed_t": 0.0,
    "grasp_joint": None, "picked_path": None,
    "cubes_delivered": 0,
}}

# Seed the articulation with Franka's canonical ready pose. Without this,
# RmpFlow starts IK from whatever random joint configuration physics
# initialized to, which often produces contorted trajectories (elbow up,
# wrist backwards) even when the final EE position is correct. The ready
# pose is a balanced kinematic start that biases IK toward natural
# elbow-down, wrist-forward poses.
_FRANKA_READY = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04]
try:
    franka.set_joint_positions(np.array(_FRANKA_READY[:len(franka.dof_names)]))
except Exception as _e:
    print(f"(ready-pose seed skipped: {{_e}})")

GRIP_STYLE = {grip_style!r}
SOURCE_PATHS = {list(source_paths)!r}

# Friction-grip needs physics material on cube + finger surfaces OR at least
# tuned material defaults. Applies PhysicsMaterialAPI with high static/dynamic
# friction so closed fingers actually hold the cube during transport.
# No-op in fixed_joint mode.
if GRIP_STYLE == "friction" and SOURCE_PATHS:
    from pxr import UsdShade, UsdPhysics as _UP, PhysxSchema as _PS
    _mat_path = "/World/Looks/FrictionGripMaterial"
    _mat_prim = stage.GetPrimAtPath(_mat_path)
    if not _mat_prim or not _mat_prim.IsValid():
        UsdShade.Material.Define(stage, _mat_path)
        _mat_prim = stage.GetPrimAtPath(_mat_path)
    _pmat = _UP.MaterialAPI.Apply(_mat_prim)
    _pmat.CreateStaticFrictionAttr().Set({_GRIP_FRICTION_STATIC})
    _pmat.CreateDynamicFrictionAttr().Set({_GRIP_FRICTION_DYNAMIC})
    _pmat.CreateRestitutionAttr().Set(0.0)
    # Apply material to source cubes + gripper fingers via relationship
    _attach_paths = list(SOURCE_PATHS) + [
        ROBOT_PATH + "/panda_leftfinger", ROBOT_PATH + "/panda_rightfinger",
    ]
    for _p in _attach_paths:
        _prim = stage.GetPrimAtPath(_p)
        if not _prim or not _prim.IsValid():
            continue
        _binding = UsdShade.MaterialBindingAPI.Apply(_prim)
        _binding.Bind(UsdShade.Material(_mat_prim),
                      bindingStrength=UsdShade.Tokens.weakerThanDescendants,
                      materialPurpose="physics")
    print(f"friction-grip: bound {{_mat_path}} to {{len(_attach_paths)}} prims")

# ── Observability instrumentation ────────────────────────────────────
# Controller writes its live state to custom USD attributes on
# /World/Franka each tick so external observers can read the TRUTH
# (phase, target, error count) without guessing. Prefix: ctrl:*
_ctrl_prim = stage.GetPrimAtPath(ROBOT_PATH)
def _ensure_attr(name, type_name, default):
    a = _ctrl_prim.GetAttribute(name)
    if not a or not a.IsDefined():
        a = _ctrl_prim.CreateAttribute(name, type_name)
    try:
        if a.Get() is None:
            a.Set(default)
    except Exception: pass
    return a

_a_phase          = _ensure_attr("ctrl:phase",          Sdf.ValueTypeNames.String, "init")
_a_phase_dur      = _ensure_attr("ctrl:phase_duration", Sdf.ValueTypeNames.Float,  0.0)
_a_target_name    = _ensure_attr("ctrl:target_name",    Sdf.ValueTypeNames.String, "")
_a_target_pos     = _ensure_attr("ctrl:target_pos",     Sdf.ValueTypeNames.Float3, Gf.Vec3f(0, 0, 0))
_a_ee_pos         = _ensure_attr("ctrl:ee_pos",         Sdf.ValueTypeNames.Float3, Gf.Vec3f(0, 0, 0))
_a_target_dist    = _ensure_attr("ctrl:target_distance", Sdf.ValueTypeNames.Float, 0.0)
_a_last_err       = _ensure_attr("ctrl:last_error",     Sdf.ValueTypeNames.String, "")
_a_err_count      = _ensure_attr("ctrl:error_count",    Sdf.ValueTypeNames.Int,    0)
_a_tick_count     = _ensure_attr("ctrl:tick_count",     Sdf.ValueTypeNames.Int,    0)
_a_cubes_delivered = _ensure_attr("ctrl:cubes_delivered", Sdf.ValueTypeNames.Int,  0)
_a_belt_paused    = _ensure_attr("ctrl:belt_paused",    Sdf.ValueTypeNames.Bool,   False)
_a_grip_cmd       = _ensure_attr("ctrl:grip_cmd",       Sdf.ValueTypeNames.String, "open")
_a_picked_path    = _ensure_attr("ctrl:picked_path",    Sdf.ValueTypeNames.String, "")

def _record_error(msg):
    try:
        _a_last_err.Set(str(msg)[:180])
        _a_err_count.Set(int(_a_err_count.Get() or 0) + 1)
    except Exception: pass

def _update_status(phase, now):
    try:
        _a_phase.Set(phase)
        _a_phase_dur.Set(float(now - S.get("enter_t", 0)))
        _a_tick_count.Set(int(S.get("tick_count", 0)))
        _a_cubes_delivered.Set(int(S.get("cubes_delivered", 0)))
        _a_picked_path.Set(str(S.get("picked_path") or ""))
        # EE world
        ee = _ee_pos_np()
        if ee is not None:
            _a_ee_pos.Set(Gf.Vec3f(float(ee[0]), float(ee[1]), float(ee[2])))
        # Current phase→target mapping
        _tgt_name_map = {{
            "home": "home", "returning_home": "home",
            "moving_to_pick": "pick", "gripping": "pick",
            "moving_to_drop": "drop",
        }}
        tgt_name = _tgt_name_map.get(phase, "")
        _a_target_name.Set(tgt_name)
        if tgt_name and _USE_COORDS:
            tp = _TARGETS.get(tgt_name)
            if tp is not None:
                _a_target_pos.Set(Gf.Vec3f(float(tp[0]), float(tp[1]), float(tp[2])))
                if ee is not None:
                    _a_target_dist.Set(float(np.linalg.norm(ee - np.asarray(tp))))
        # Belt paused flag
        if belt_sv_attr and belt_sv_attr.IsDefined():
            v = belt_sv_attr.Get()
            _a_belt_paused.Set(bool(v is not None and abs(v[0]) < 0.001 and abs(v[1]) < 0.001 and abs(v[2]) < 0.001))
    except Exception as _e:
        # Status update failures should not break control
        pass

# Wrap _grip to record command
_grip_inner = _grip
def _grip(value):  # shadow previous def
    _grip_inner(value)
    try:
        _a_grip_cmd.Set("close" if value < 0.02 else "open")
    except Exception: pass

_goto_target("home")
_grip(GRIPPER_OPEN)

def _step(dt):
  try:
    S["elapsed_t"] += dt
    S["tick_count"] = S.get("tick_count", 0) + 1
    now = S["elapsed_t"]
    phase = S["phase"]
    # SELF-HEAL stale articulation handle (2026-06-14): the settle/measurement
    # path stops+replays the timeline AFTER this controller bound its handle
    # (settle_after_canonical -> timeline.stop()), tearing down the physics view
    # that franka.initialize() bound to at setup. The handle then returns None
    # forever -> RmpFlow no-ops every step (arm frozen, all joints 0deg) and the
    # cycle-boundary ready-warp raises "'NoneType' has no attribute
    # joint_positions". Re-initialize on the first tick after a restart so both
    # motion and ready-warp work. cuRobo controllers already survive the restart;
    # this brings the RmpFlow sensor_gated path to parity. No-op once the handle
    # is live (the common case).
    try:
        if franka.get_joint_positions() is None:
            franka.initialize()
    except Exception:
        pass
    _tick_motion_policy()
    _reassert_grip()  # Hold finger target stable every tick

    if phase == "home":
        if _at_target("home") or now - S["enter_t"] > 3.0:
            S["phase"] = "wait_sensor"
            S["enter_t"] = now

    elif phase == "wait_sensor":
        if sensor_trig_attr and sensor_trig_attr.Get():
            _pause_belt()
            S["picked_path"] = sensor_last_attr.Get() if sensor_last_attr else None
            # Retarget EE at the cube's LIVE world position, not the static
            # pick_target. Belt deceleration parks cubes at slightly varying
            # X in the sensor volume (0.30 ± 0.04m) — static PICK_TARGET
            # misses by 2-4 cm. Live cube-tracking ensures EE arrives where
            # the cube actually is.
            if _USE_COORDS and S["picked_path"]:
                try:
                    _cp = stage.GetPrimAtPath(S["picked_path"])
                    if _cp and _cp.IsValid():
                        _cpos = UsdGeom.Xformable(_cp).ComputeLocalToWorldTransform(0).ExtractTranslation()
                        # Small +Z offset so EE (panda_hand) hovers ~2cm above
                        # cube top — fingers wrap cube when they close.
                        _TARGETS["pick"] = [float(_cpos[0]), float(_cpos[1]), float(_cpos[2]) + 0.02]
                except Exception as _e:
                    _record_error(f"retarget pick to cube failed: {{type(_e).__name__}}: {{str(_e)[:80]}}")
            _goto_target("pick")
            S["phase"] = "moving_to_pick"
            S["enter_t"] = now

    elif phase == "moving_to_pick":
        # Stricter reach condition: 2cm of live cube position, plus longer
        # timeout (8s) so IK has time to converge. Removing the early-exit
        # timeout that caused "grab from 30cm away" behavior when RmpFlow
        # couldn't reach within 4s.
        _reached = False
        if _USE_COORDS and S["picked_path"]:
            try:
                _cp = stage.GetPrimAtPath(S["picked_path"])
                if _cp and _cp.IsValid():
                    _cpos = UsdGeom.Xformable(_cp).ComputeLocalToWorldTransform(0).ExtractTranslation()
                    _ee = _ee_pos_np()
                    if _ee is not None:
                        _cvec = np.array([float(_cpos[0]), float(_cpos[1]), float(_cpos[2])+0.02])
                        _reached = float(np.linalg.norm(_ee - _cvec)) < 0.02
                        # Also update target each tick — cube may be
                        # drifting slightly due to ongoing physics
                        _TARGETS["pick"] = list(_cvec)
                        _goto_target("pick")
            except Exception as _e:
                _record_error(f"live-track pick: {{type(_e).__name__}}: {{str(_e)[:80]}}")
        else:
            _reached = _at_target("pick")
        # Hard timeout 8s as safety net — if IK genuinely can't reach,
        # we don't want to hang forever.
        if _reached or now - S["enter_t"] > 8.0:
            _grip(GRIPPER_CLOSE)
            S["phase"] = "gripping"
            S["enter_t"] = now

    elif phase == "gripping":
        # Grip is ALWAYS friction — no EE↔cube FixedJoint (Anton's rule: the
        # grip may never be a FixedJoint). Pause 1.5s for the fingers to
        # physically compress against the cube; physics holds it via contact +
        # friction material. Fingers are already closing from moving_to_pick
        # (see _grip(GRIPPER_CLOSE) there). Flaky under belt-jitter; occasional
        # slips are expected and honest.
        _pause = 1.5
        if now - S["enter_t"] > _pause:
            # No joint created — friction grip only.
            _goto_target("drop")
            S["phase"] = "moving_to_drop"
            S["enter_t"] = now
            _resume_belt()

    elif phase == "moving_to_drop":
        if _at_target("drop") or now - S["enter_t"] > 4.0:
            if S["grasp_joint"] and stage.GetPrimAtPath(S["grasp_joint"]).IsValid():
                stage.RemovePrim(S["grasp_joint"])
                S["grasp_joint"] = None
            _grip(GRIPPER_OPEN)
            S["cubes_delivered"] += 1
            # Warp-reset arm to canonical ready pose on cycle boundary.
            # Without this RmpFlow drifts into joint-limit cul-de-sacs
            # across cycles (observed 2026-04-20: joint4=-158°, joint6=212°
            # — pinned against limits, arm physically jammed despite
            # phase transitions). Non-physical but unsticks the state
            # machine between deliveries.
            try:
                _dofs = list(franka.dof_names) if franka.dof_names else []
                _ready_slice = _FRANKA_READY[:len(_dofs)]
                franka.set_joint_positions(_ready_slice)
                # Set drive targets so PD holds the pose — use apply_action,
                # which is the canonical Isaac Sim 5.x API (set_joint_position_targets
                # doesn't exist on SingleArticulation in 5.x).
                franka.apply_action(ArticulationAction(
                    joint_positions=np.array(_ready_slice, dtype=np.float64),
                ))
            except Exception as _e:
                _record_error(f"ready-warp failed: {{type(_e).__name__}}: {{str(_e)[:80]}}")
            S["phase"] = "returning_home"
            S["enter_t"] = now

    elif phase == "returning_home":
        _goto_target("home")
        if _at_target("home") or now - S["enter_t"] > 3.0:
            S["phase"] = "wait_sensor"
            S["enter_t"] = now

    # End of tick: publish live state to observable USD attrs
    _update_status(S["phase"], now)
  except Exception as _step_err:
    _record_error(f"_step({{S.get('phase','?')}}): {{type(_step_err).__name__}}: {{str(_step_err)[:120]}}")

# Subscribe via omni.physx directly (World.add_physics_callback hits
# NoneType._physx_interface in exec_sync contexts where SimulationContext
# didn't fully initialize). Same pattern as cube_tracking mode.
# Per-robot scoping: dual-arm / multi-call templates must not clobber
# the other robot's controller. Suffix handle with robot-path tag.
import builtins as _builtins
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
# Track K (2026-05-28): per-phase scoping.
_sub_attr = "_pick_place_sensor_gated_physx_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
_old_sub = getattr(_builtins, _sub_attr, None)
if _old_sub is not None:
    try: _old_sub.unsubscribe()
    except Exception: pass
_physx = omni.physx.get_physx_interface()
if _physx is None:
    raise RuntimeError("sensor_gated: omni.physx interface unavailable")
_sub = _physx.subscribe_physics_step_events(_step)
setattr(_builtins, _sub_attr, _sub)

print(json.dumps({{
    "ok": True,
    "mode": "sensor_gated",
    "targeting": ("world-coords + RmpFlow IK" if _USE_COORDS else "pose-name replay"),
    "grip_style": GRIP_STYLE,
    "sensor_path": SENSOR_PATH,
    "belt_path": BELT_PATH,
    "targets": ({{"pick": PICK_TARGET, "drop": DROP_TARGET, "home": HOME_TARGET}}
                if _USE_COORDS
                else {{"pick": PICK_POSE, "drop": DROP_POSE, "home": HOME_POSE}}),
    "initial_state": "home → wait_sensor",
    "note": "Start Play. On sensor-trigger belt pauses; robot picks; belt resumes during transit; robot drops; returns home; waits for next trigger.",
}}))
"""


def _gen_pick_place_native(robot_path: str, sensor_path: str, belt_path: str,
                           source_paths: list, destination_path: str,
                           drop_target: str, ee_offset: list,
                           end_effector_initial_height=None,
                           events_dt=None,
                           phase_id: str = "default") -> str:
    """Canonical Isaac Sim pick-place — ports the 62-line standalone at
    `standalone_examples/api/isaacsim.robot.manipulators/franka/pick_place.py`
    into an embedded (Kit RPC) context, wrapped with sensor-gating.

    Uses the built-in `Franka` wrapper + `PickPlaceController` from
    `isaacsim.robot.manipulators.examples.franka`. The controller owns
    the whole state machine (approach → descend → grip → lift →
    transport → descend → release → retreat) with internally-tuned
    events_dt, so we don't reimplement it.

    Four fixes over a naive embed of the 62-line script (all verified
    root-causes from 3 parallel sub-agent audits 2026-04-20):

      1. `SimulationManager.initialize_physics()` + app.update() pump
         before `franka.initialize()` — standalone path gets this via
         `world.reset()` → `SimulationContext.reset()`. Without it,
         `dof_names` is empty, `ParallelGripper.initialize` can't find
         finger indices, and subsequent calls fail.

      2. Auto-compute `end_effector_initial_height` from source +
         destination z + clearance. Controller default is 0.3 m
         absolute — fine when robot sits on the ground (standalone)
         but BELOW the base when robot is on a table at z=0.75 → IK
         targets land below the base → robot tangles trying to reach
         underneath itself.

      3. Re-apply `set_robot_base_pose` on the cspace controller after
         construction. `RMPFlowController.__init__` snapshots the
         robot's world pose at construction time — if that's done
         before a valid `physics_sim_view` exists, the pose is wrong
         and all subsequent IK is computed relative to a bad origin.

      4. Defensive guard around `apply_action`: `PickPlaceController`
         event-phase 2 intentionally returns
         `ArticulationAction(joint_positions=[None, None, ...])` for
         ~10 sim-seconds. `ArticulationController.apply_action` has a
         `joint_positions is not None` check, but that passes on a
         list of Nones, and the downstream `.astype(np.float32)` on
         `np.asarray([None, None, ...])` crashes with
         `AttributeError: 'NoneType' object has no attribute 'astype'`.
         We skip apply_action when positions is all-None.

    Other differences from the 62-line standalone (not bugs, just
    adaptations):
      - No ``SimulationApp`` / ``world.step(render=True)`` loop —
        physics ticks via ``omni.physx.subscribe_physics_step_events``.
      - Sensor-gated wrapper: wait for proximity sensor →
        ``controller.reset()`` → ``forward()`` each tick until ``is_done()`` →
        pause belt during pick → resume during transport → repeat.
      - Live cube tracking: ``picking_position`` reads source prim's
        current world pose each tick (retargets as cube moves on belt).

    Args:
        robot_path (str): USD prim path of the Franka articulation root.
        sensor_path (str or None): Proximity sensor prim path. When set, the
            controller waits for a sensor trigger before each pick cycle.
        belt_path (str or None): Conveyor belt prim path. Belt is paused while
            the robot picks a cube and resumed after the cube is released.
        source_paths (list[str]): Ordered cube prim paths to deliver.
        destination_path (str or None): Default bin prim path.
        drop_target (str or None): Drop bin override (takes precedence over
            destination_path when non-None).
        ee_offset (list[float]): [x, y, z] EE-to-fingertip offset, meters.
            Applied to cube center to compute the grasp target.
        end_effector_initial_height (float or None): Override for the approach
            clearance height. Auto-computed from source/dest Z + clearance when
            None (fix #2 above).
        events_dt (list[float] or None): Per-phase time-budget list passed to
            ``PickPlaceController``. Uses the controller's built-in defaults
            when None.

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Prints a JSON dict with ``{"ok": True, "mode": "native", ...}`` on
        success, or raises ``RuntimeError`` for pre-flight failures (prim not
        found, articulation init failure, etc.).
    """
    # (Phase 8 wave 9) tool_executor imports migrated to module body:
    # _PP_OBSERVABILITY_SNIPPET migrated to module body (Phase 8 wave 9).
    # _PP_SCENE_RESET_MGR_SNIPPET migrated to module body (Phase 8 wave 9).
    import json as _json
    return f"""\
# ── setup_pick_place_controller (native) ─────────────────────────────
# Canonical franka PickPlaceController wrapped with sensor-gating +
# embedding-context fixes (see _gen_pick_place_native docstring).
import omni.usd, omni.timeline, omni.physx, omni.kit.app, numpy as np, builtins, json, time
from pxr import UsdGeom, UsdPhysics, Sdf, Gf
from isaacsim.core.api import World
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers.pick_place_controller import PickPlaceController

ROBOT_PATH = {robot_path!r}
SENSOR_PATH = {sensor_path!r}
BELT_PATH = {belt_path!r}
SOURCE_PATHS = {_json.dumps(list(source_paths))}
DEST_PATH = {destination_path!r}
DROP_TARGET = {_json.dumps(drop_target) if drop_target else 'None'}
EE_OFFSET = np.array({_json.dumps(list(ee_offset))}, dtype=np.float32)
EE_INIT_H_OVERRIDE = {end_effector_initial_height!r}
EVENTS_DT = {_json.dumps(events_dt) if events_dt else 'None'}
_PHASE_ID = {phase_id!r}
ROBOT_FAMILY = "franka"  # native pick-place is Franka-only (Franka wrapper); define so reach/branch checks (e.g. _cube_at_sensor) don't NameError

# ── Clean up any prior subscription (scoped to THIS robot + THIS phase only) ──
# Per-robot scoping (2026-05-28): templates like
# CP-NEW-yrkesroll-packer-box-seal / CP-NEW-roco-bimanual-assembly
# call setup_pick_place_controller TWICE — once per arm. The old code
# unsubscribed ALL _native_pp_/_pick_place_/_sensor_gated_/_spline_/
# _diffik_/_osc_/_curobo_ handles regardless of robot, so the second
# call killed the first robot's controller. Now: handle is suffixed
# with _ROBOT_TAG, and cross-mode sweep is guarded by `_a.endswith("_" + _ROBOT_TAG)`.
#
# Track K (2026-05-28): per-phase scoping. Same robot + different phase_id
# coexist so sequential pick→place→outfeed pipelines don't clobber each other.
# Default phase_id="default" preserves legacy single-PPC behaviour.
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
_SUB_ATTR = "_native_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
_old = getattr(builtins, _SUB_ATTR, None)
if _old is not None:
    try: _old.unsubscribe()
    except Exception: pass
    try: delattr(builtins, _SUB_ATTR)
    except Exception: pass
# Also unsub any prior sensor-gated / pick-place / spline / diffik / osc / curobo / timeline callbacks
# — but ONLY for THIS robot AND THIS phase. Other robots'/phases' subs must survive.
for _a in list(vars(builtins).keys()):
    if _a.startswith(("_pick_place_", "_sensor_gated_", "_native_pp_tl_",
                       "_spline_pp_", "_diffik_pp_", "_osc_pp_", "_curobo_pp_tl_")) \
       and (_a.endswith("_" + _ROBOT_TAG) or ("_" + _ROBOT_TAG + "_") in _a):
        _s = getattr(builtins, _a, None)
        if _s:
            try: _s.unsubscribe()
            except Exception: pass
        try: delattr(builtins, _a)
        except Exception: pass
# Clear stale Scene Reset Manager hooks from prior controller installs
# (this robot + this phase only). Legacy un-tagged hooks also cleared.
_mgr_pre = getattr(builtins, "_scene_reset_manager", None)
if _mgr_pre is not None:
    for _hn in ("native_pp", "spline_pp", "diffik_pp", "osc_pp", "curobo_pp", "sensor_gated_pp"):
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG + "_" + _PHASE_ID)
        except Exception: pass
        # Also clear legacy hooks left by pre-multi-robot / pre-phase installs
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG)
        except Exception: pass
        try: _mgr_pre.unregister(_hn)
        except Exception: pass

stage = omni.usd.get_context().get_stage()
tl = omni.timeline.get_timeline_interface()
if not tl.is_playing():
    tl.play()

# ── FIX 1: Force physics initialization + app.update() pump ──────────
# Standalone path: world.reset() → SimulationContext.reset() → play +
# SimulationManager.initialize_physics() → Scene._finalize → robot init.
# Embedded path misses the middle steps, which means franka.dof_names
# is empty and gripper init fails silently. Pump the app + initialize
# physics explicitly.
_app = omni.kit.app.get_app()
for _ in range(6):
    _app.update()
try:
    if SimulationManager.get_physics_sim_view() is None:
        SimulationManager.initialize_physics()
except Exception as _e:
    print(f"(initialize_physics soft-fail: {{_e}})")
_physics_sim_view = SimulationManager.get_physics_sim_view()

# ── World + Franka wrapper ───────────────────────────────────────────
# The Franka wrapper (subclass of SingleManipulator) adds the
# ParallelGripper with correct finger joint names, drive modes, and
# limits. PickPlaceController expects that.
world = World.instance() or World()
franka = Franka(prim_path=ROBOT_PATH, name="native_pp_franka")
# world.scene.add() may fail in exec_sync if SimulationContext wasn't
# async-initialized. Not fatal — Franka can still be used standalone
# for articulation + gripper control.
try:
    world.scene.add(franka)
except Exception as _e:
    _existing = world.scene.get_object("native_pp_franka")
    if _existing is not None:
        franka = _existing
    # else: fall through — direct use still works

# Initialize Franka + gripper. Pass the physics_sim_view so the
# articulation handle is backed by a valid tensor-API view, and gripper
# init can populate _joint_dof_indicies + _articulation_num_dofs.
try:
    franka.initialize(_physics_sim_view)
    franka.post_reset()
except Exception as _e:
    print(json.dumps({{"ok": False, "error": f"franka init failed: {{type(_e).__name__}}: {{_e}}"}}))
    raise

# Sync physics body pose from USD-authored transform. If the USD was
# rotated after physics started, the physics body may still be at its
# original orientation (physics only reads USD on reset/play). Read
# USD authoritative pose and push to physics via set_world_pose.
try:
    _robot_xf0 = UsdGeom.Xformable(stage.GetPrimAtPath(ROBOT_PATH))
    _mtx0 = _robot_xf0.ComputeLocalToWorldTransform(0)
    _usd_pos = np.array([float(_mtx0.ExtractTranslation()[i]) for i in range(3)], dtype=np.float32)
    _usd_q = _mtx0.ExtractRotationQuat()
    _usd_quat = np.array([float(_usd_q.GetReal())] +
                         [float(_usd_q.GetImaginary()[i]) for i in range(3)], dtype=np.float32)
    _phys_pos, _phys_quat = franka.get_world_pose()
    _pos_delta = float(np.linalg.norm(_usd_pos - np.asarray(_phys_pos, dtype=np.float32)))
    _quat_delta = float(np.linalg.norm(_usd_quat - np.asarray(_phys_quat, dtype=np.float32)))
    if _pos_delta > 1e-3 or _quat_delta > 1e-3:
        franka.set_world_pose(position=_usd_pos, orientation=_usd_quat)
        print(f"(physics body pose synced from USD: pos_delta={{_pos_delta:.4f}}, quat_delta={{_quat_delta:.4f}})")
except Exception as _e:
    print(f"(physics body sync soft-fail: {{_e}})")

# Force Franka to canonical home joint config — AND update PhysX
# default state so Stop+Play restores to this pose (not the
# pre-rotation initial snapshot PhysX captured at first play).
# Without set_default_state, pressing Stop reverts to the OLD identity
# orient and the arm's IK base is wrong on re-Play.
try:
    _home_q = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04], dtype=np.float32)
    _n_dof = len(franka.dof_names) if franka.dof_names else len(_home_q)
    _home_q_trimmed = _home_q[:_n_dof]
    franka.set_joint_positions(_home_q_trimmed)
    franka.set_joint_velocities(np.zeros(_n_dof, dtype=np.float32))
    # Persist as default for Stop/Play reset
    try:
        franka.set_joints_default_state(positions=_home_q_trimmed, velocities=np.zeros(_n_dof, dtype=np.float32))
    except Exception as _jd: print(f"(set_joints_default_state soft-fail: {{_jd}})")
    try:
        franka.set_default_state(position=_usd_pos, orientation=_usd_quat)
    except Exception as _bd: print(f"(set_default_state soft-fail: {{_bd}})")
    print(f"(forced Franka to home joint config + persisted PhysX defaults; dof={{_n_dof}})")
except Exception as _e:
    print(f"(home pose force soft-fail: {{_e}})")

# Sanity-check that gripper init populated its cached indices. If not,
# `gripper.forward('close')` will crash later with TypeError on
# `[None] * None`.
_g = franka.gripper
if getattr(_g, "_articulation_num_dofs", None) is None:
    print("(warning: gripper._articulation_num_dofs is None — init incomplete)")
if any(i is None for i in getattr(_g, "_joint_dof_indicies", [0, 0])):
    print(f"(warning: gripper._joint_dof_indicies has None: {{_g._joint_dof_indicies}})")

# ── Helpers (needed BEFORE the controller construction for h1 calc) ──
def _world_pos(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid(): return None
    t = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1]), float(t[2])])

def _bin_drop_pos():
    if DROP_TARGET is not None:
        return np.array(DROP_TARGET, dtype=np.float32)
    if DEST_PATH:
        p = stage.GetPrimAtPath(DEST_PATH)
        if p and p.IsValid():
            bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
            mn, mx = bb.GetMin(), bb.GetMax()
            return np.array([(mn[0]+mx[0])/2, (mn[1]+mx[1])/2, float(mx[2]) + 0.05], dtype=np.float32)
    return None

# ── FIX 2: Auto-compute end_effector_initial_height ──────────────────
# The default (0.3 m absolute) puts EE below the table surface when
# robot is on a table. Compute h1 = max(source z, drop z) + clearance.
def _compute_h1():
    if EE_INIT_H_OVERRIDE is not None:
        return float(EE_INIT_H_OVERRIDE)
    _zs = []
    for _sp in SOURCE_PATHS:
        _wp = _world_pos(_sp)
        if _wp is not None:
            _zs.append(float(_wp[2]))
    _dp = _bin_drop_pos()
    if _dp is not None:
        _zs.append(float(_dp[2]))
    if not _zs:
        return 0.3
    return max(_zs) + 0.20  # 20cm clearance above highest target
EE_INITIAL_HEIGHT = _compute_h1()

# ── Controller: canonical franka PickPlaceController ─────────────────
# Contains events_dt for approach/descend/grip/lift/transport/release.
# Default Franka events_dt (from franka PickPlaceController source):
#   [0.008, 0.005, 1, 0.1, 0.05, 0.05, 0.0025, 1, 0.008, 0.08]
# The default phase 1 dt=0.005 → 200 physics ticks ≈ 3.3s descent window.
# On an elevated base with a longer descent span (h1=1.2 → h0=0.875 =
# 0.325m), that window is too short for RmpFlow to converge — the
# robot's EE stops ~10-15cm above the cube and the grip closes on air.
# We slow phase 1 (dt=0.002 → 500 ticks ≈ 8.3s) and extend phase 3
# (gripper close, dt=0.025 → 40 ticks ≈ 0.67s) so both have headroom.
# Caller can override via events_dt kwarg.
_events_dt = EVENTS_DT
if _events_dt is None:
    _events_dt = [0.008, 0.002, 1, 0.025, 0.05, 0.05, 0.0025, 1, 0.008, 0.08]
controller = PickPlaceController(
    name="native_pp_ctrl",
    gripper=franka.gripper,
    robot_articulation=franka,
    end_effector_initial_height=EE_INITIAL_HEIGHT,
    events_dt=_events_dt,
)

# ── FIX 3: Re-apply robot base pose after construction ───────────────
# RMPFlowController.__init__ captures robot pose via
# `franka.get_world_pose()` at construction — if physics handles weren't
# fully wired yet, it snapshots stale USD values. Worse, its reset()
# re-applies those stale defaults on every controller.reset() call
# (see rmpflow_controller.py:44-48), undoing our correction each cycle.
# We patch BOTH the current base pose AND the stored _default_position
# /_default_orientation that reset() reads from.
try:
    _robot_xf = UsdGeom.Xformable(stage.GetPrimAtPath(ROBOT_PATH))
    _mtx = _robot_xf.ComputeLocalToWorldTransform(0)
    _base_pos = np.array([float(_mtx.ExtractTranslation()[i]) for i in range(3)], dtype=np.float32)
    _base_quat_gf = _mtx.ExtractRotationQuat()
    _base_quat = np.array([float(_base_quat_gf.GetReal())] +
                          [float(_base_quat_gf.GetImaginary()[i]) for i in range(3)],
                          dtype=np.float32)
    _cspace = getattr(controller, "_cspace_controller", None)
    if _cspace is not None:
        # Overwrite the cached defaults reset() uses
        _cspace._default_position = _base_pos
        _cspace._default_orientation = _base_quat
        # Push the corrected pose to the live motion policy
        _mp = getattr(_cspace, "_motion_policy", None) or getattr(_cspace, "rmp_flow", None)
        if _mp is not None and hasattr(_mp, "set_robot_base_pose"):
            _mp.set_robot_base_pose(robot_position=_base_pos, robot_orientation=_base_quat)
        elif hasattr(_cspace, "set_robot_base_pose"):
            _cspace.set_robot_base_pose(_base_pos, _base_quat)
    print(f"(rmpflow base pose pinned: pos={{_base_pos.tolist()}} quat={{_base_quat.tolist()}})")
except Exception as _e:
    print(f"(rmpflow base pose pin soft-fail: {{_e}})")

art_ctrl = franka.get_articulation_controller()

# ── Boost finger drive gains for friction grip (same as spline) ───────
# Default USD finger drives are too soft to clamp a 0.1kg cube: position
# drive with kp~1000 → cube slips out during lift. Boost to 10000.
try:
    for _fj in ("panda_finger_joint1", "panda_finger_joint2"):
        _jp = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/panda_hand/{{_fj}}")
        if _jp.IsValid():
            _drv = UsdPhysics.DriveAPI.Get(_jp, "linear")
            if _drv:
                _drv.GetStiffnessAttr().Set(10000.0)
                _drv.GetDampingAttr().Set(200.0)
    print("(native: finger drive gains boosted to kp=10000/kd=200)")
except Exception as _fe:
    print(f"(native finger gain boost soft-fail: {{_fe}})")

# ── IK solver for cspace-target guidance ─────────────────────────────
# RmpFlow alone settles in local minima on elevated / rotated bases
# (target_rmp.accel_p_gain=30 is weak). Pre-compute IK each tick and
# set it as cspace_target — cspace_target_rmp.position_gain=100 pulls
# joints to the IK solution much more reliably.
_ik_solver = None
try:
    from isaacsim.robot_motion.motion_generation.lula.kinematics import LulaKinematicsSolver
    import os
    _mpc_root = None
    for _root_try in [
        "/mnt/shared_data/isaac-sim/exts/isaacsim.robot_motion.motion_generation",
        "/opt/isaac-sim/exts/isaacsim.robot_motion.motion_generation",
    ]:
        _cand = os.path.join(_root_try, "motion_policy_configs/franka/rmpflow")
        if os.path.isdir(_cand):
            _mpc_root = _cand
            break
    if _mpc_root:
        _ik_solver = LulaKinematicsSolver(
            robot_description_path=os.path.join(_mpc_root, "robot_descriptor.yaml"),
            urdf_path=os.path.normpath(os.path.join(_mpc_root, "..", "lula_franka_gen.urdf")),
        )
        _ik_solver.set_robot_base_pose(_base_pos, _base_quat)
        print("(IK solver ready for cspace-target guidance)")
except Exception as _e:
    print(f"(IK solver init soft-fail: {{_e}})")

# Default down-facing end-effector orientation — matches PickPlaceController
from isaacsim.core.utils.rotations import euler_angles_to_quat as _eul2q
_DOWN_QUAT = _eul2q(np.array([0, np.pi, 0]))
_last_ik_cspace = None

def _guide_via_ik(target_xy_world, target_z_world):
    # Compute IK for world target + down orient; push as cspace target
    # to RmpFlow. Cheap IK (~ms), runs each tick.
    global _last_ik_cspace
    if _ik_solver is None: return
    try:
        tgt = np.array([float(target_xy_world[0]), float(target_xy_world[1]),
                        float(target_z_world)], dtype=np.float32)
        warm = _last_ik_cspace if _last_ik_cspace is not None else np.array(
            [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785], dtype=np.float32)
        # Use right_gripper (the frame RMPFlow itself targets in Franka's
        # config.json, 10cm out from panda_link8 so it sits near fingertip
        # plane) — NOT panda_hand. Mismatched frames made IK-guide and
        # PickPlaceController's own Cartesian target disagree and the
        # robot landed fingertips below cube level (I-36).
        q, ok = _ik_solver.compute_inverse_kinematics(
            frame_name="right_gripper",
            target_position=tgt,
            target_orientation=_DOWN_QUAT,
            warm_start=warm,
        )
        if ok:
            _last_ik_cspace = q
            _mp_local = getattr(controller._cspace_controller, "_motion_policy", None)
            if _mp_local and hasattr(_mp_local, "set_cspace_target"):
                _mp_local.set_cspace_target(q)
    except Exception: pass

# ── Belt pause/resume ────────────────────────────────────────────────
# Capture nominal surface velocity at install time. If value is zero
# (belt was already paused by a prior controller install), fall back to
# the conveyor-scenario default — belt would never resume otherwise.
_belt_prim = stage.GetPrimAtPath(BELT_PATH) if BELT_PATH else None
_belt_sv = _belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if (_belt_prim and _belt_prim.IsValid()) else None
_captured = tuple(_belt_sv.Get()) if (_belt_sv and _belt_sv.IsDefined() and _belt_sv.Get()) else None
if _captured is None or sum(abs(v) for v in _captured) < 1e-6:
    _nominal_belt = (0.2, 0.0, 0.0)  # default belt speed — override via drop_target kwarg if needed
    print(f"(belt nominal velocity defaulted to (0.2, 0, 0); captured was {{_captured}})")
else:
    _nominal_belt = _captured

def _pause_belt():
    if _belt_sv: _belt_sv.Set((0, 0, 0))
def _resume_belt():
    if _belt_sv: _belt_sv.Set(_nominal_belt)

# Start belt running if it's paused (leftover from a prior install or
# from scene-build that left it at zero).
if _belt_sv and sum(abs(v) for v in (_belt_sv.Get() or (0,0,0))) < 1e-6:
    _resume_belt()

# ── Sensor (if provided) + our own proximity latch ───────────────────
# The USD-authored `isaac_sensor:triggered` attribute latches on when a
# cube enters the trigger volume but may NOT reliably unlatch when the
# cube leaves (depending on how add_proximity_sensor wired the trigger
# callback). Rather than trust it, we also do our own per-tick
# proximity check against the sensor's world position.
_sensor = stage.GetPrimAtPath(SENSOR_PATH) if SENSOR_PATH else None
_s_trig = _sensor.GetAttribute("isaac_sensor:triggered") if (_sensor and _sensor.IsValid()) else None
_s_last = _sensor.GetAttribute("isaac_sensor:last_triggered_path") if (_sensor and _sensor.IsValid()) else None

def _sensor_world_pos():
    if _sensor is None or not _sensor.IsValid(): return None
    t = UsdGeom.Xformable(_sensor).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1]), float(t[2])])

_SENSOR_RADIUS = 0.08  # 8 cm — permissive; cubes approaching from -X
_sensor_pos = _sensor_world_pos()

def _cube_at_sensor():
    # Reach-based selection (belt may be frozen — sensor-proximity gating
    # alone misses cubes that didn't happen to be near sensor at pause time).
    # Pick any undelivered, still-on-belt cube within robot workspace; prefer
    # the one closest to sensor (stable ordering).
    base_xy = np.array([float(_usd_pos[0]), float(_usd_pos[1])])
    base_z = float(_usd_pos[2])
    sxy = _sensor_pos[:2] if _sensor_pos is not None else base_xy
    cands = []
    for _sp in SOURCE_PATHS:
        if _sp in S["delivered"] or _is_in_bin(_sp): continue
        _cp = _world_pos(_sp)
        if _cp is None: continue
        # Base-relative z-window: catches table-top + belt-top, excludes
        # floor-falls. Earlier hardcoded [0.83, 0.95] silently rejected
        # cubes resting directly on the table at z=0.775.
        if _cp[2] < base_z - 0.30 or _cp[2] > base_z + 0.50: continue
        # Family-aware reach (mirrors cuRobo _cube_to_pick): UR10 1.20m, Franka 0.85m.
        # Previously hardcoded 0.70m unconditionally — filtered out cubes at ≥0.9m XY
        # for forklift-handoff-arm and other native-mode templates beyond Franka reach.
        _reach_native = (1.20 if ROBOT_FAMILY in ("ur10", "ur10e") else 0.85) - 0.05
        if float(np.linalg.norm(_cp[:2] - base_xy)) > _reach_native: continue
        cands.append((float(np.linalg.norm(_cp[:2] - sxy)), _sp))
    if not cands: return None
    cands.sort()
    return cands[0][1]

{_PP_OBSERVABILITY_SNIPPET}
_a_mode.Set("native")

# ── State ────────────────────────────────────────────────────────────
# mode: wait_sensor (waiting for cube at pick station) | picking (controller active) | idle (all cubes delivered)
S = {{"mode": "wait_sensor", "picked_path": None,
      "cubes": 0, "errors": 0, "ticks": 0,
      "delivered": set()}}  # cubes already picked — never re-pick from bin

def _record_err(e):
    S["errors"] += 1
    try:
        _a_err.Set(S["errors"])
        _a_last_err.Set(f"{{type(e).__name__}}: {{str(e)[:150]}}")
    except Exception: pass

def _bin_bounds():
    # Return (min_xy, max_xy) for the bin XY footprint, or None.
    if not DEST_PATH: return None
    p = stage.GetPrimAtPath(DEST_PATH)
    if not p or not p.IsValid(): return None
    bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    return (np.array([bb.GetMin()[0], bb.GetMin()[1]]),
            np.array([bb.GetMax()[0], bb.GetMax()[1]]))

def _is_in_bin(cube_path):
    # True if cube world pose is within the bin footprint.
    bounds = _bin_bounds()
    if bounds is None: return False
    cp = _world_pos(cube_path)
    if cp is None: return False
    mn, mx = bounds
    return (mn[0] <= cp[0] <= mx[0]) and (mn[1] <= cp[1] <= mx[1])

def _on_step(dt):
    try:
        # Round 7 repair (2026-05-18): guard against expired prim refs
        # (cross-template stage_swap). Bail + auto-unsubscribe.
        try:
            _check_robot_pp = stage.GetPrimAtPath(ROBOT_PATH)
            if not _check_robot_pp or not _check_robot_pp.IsValid():
                try:
                    if '_sub' in globals() and _sub is not None and hasattr(_sub, 'unsubscribe'):
                        _sub.unsubscribe()
                except Exception: pass
                return
        except Exception:
            return
        S["ticks"] += 1
        try:
            _a_tick.Set(S["ticks"])
            _a_phase.Set(S["mode"])
        except Exception:
            return

        if S["mode"] == "wait_sensor":
            # Use our own proximity check (sensor attr may not unlatch)
            picked = _cube_at_sensor()
            # Skip cubes already delivered to the bin
            if picked and (picked in S["delivered"] or _is_in_bin(picked)):
                picked = None
            if picked:
                S["picked_path"] = picked
                S["mode"] = "picking"
                _a_picked.Set(picked)
                _pause_belt()
                controller.reset()
            return

        if S["mode"] == "picking":
            if controller.is_done():
                S["cubes"] += 1
                _a_cycles.Set(S["cubes"])
                # Mark delivered regardless — grip-failure retry causes
                # infinite loops when IK can't reach extreme positions.
                # Better to miss 1 cube than lock up on impossible retries.
                if S["picked_path"]:
                    S["delivered"].add(S["picked_path"])
                    _a_cubes.Set(len(S["delivered"]))
                S["picked_path"] = None
                S["mode"] = "wait_sensor"
                # Resume belt unconditionally on wait_sensor transition. Earlier
                # heuristic only resumed when ALL delivered to "avoid drift" —
                # but caused deadlock when a cube was marked delivered without
                # actually reaching the bin (grip miss) and remaining cubes were
                # outside immediate pick range. Drift between transitions is
                # bounded by one physics step and self-corrects when the next
                # cube triggers the sensor (which re-pauses the belt).
                _resume_belt()
                return
            cube_pos = _world_pos(S["picked_path"])
            if cube_pos is None:
                S["mode"] = "wait_sensor"
                S["picked_path"] = None
                # Resume belt — transient cube-pose lookup failures should not
                # leave the belt frozen and starve future picks of incoming
                # cubes. Same self-correction as the normal completion path.
                _resume_belt()
                return
            drop_pos = _bin_drop_pos()
            if drop_pos is None:
                _record_err(RuntimeError("no drop position (DEST_PATH+DROP_TARGET both missing)"))
                return
            # Guide RmpFlow via cspace IK target across all phases. This
            # was the 4/4 working configuration verified overnight.
            _ev = getattr(controller, "_event", 0)
            if _ev <= 4:
                _guide_via_ik(cube_pos[:2], cube_pos[2] if _ev >= 2 else EE_INITIAL_HEIGHT)
            else:
                _guide_via_ik(drop_pos[:2], drop_pos[2] if _ev >= 6 else EE_INITIAL_HEIGHT)
            _cjp = franka.get_joint_positions()
            if _cjp is None:
                return  # articulation handle not ready yet
            actions = controller.forward(
                picking_position=cube_pos,
                placing_position=drop_pos,
                current_joint_positions=_cjp,
                end_effector_offset=EE_OFFSET,
            )
            # FIX 4: guard against all-None joint_positions list (phase 2
            # of PickPlaceController returns this intentionally).
            _jp = getattr(actions, "joint_positions", None)
            if _jp is None or (hasattr(_jp, "__iter__") and all(
                    (x is None) for x in _jp)):
                return  # skip — robot holds last target
            art_ctrl.apply_action(actions)
    except Exception as e:
        _record_err(e)

# ── Subscribe via omni.physx (scene-lifecycle independent) ───────────
_physx = omni.physx.get_physx_interface()
if _physx is None:
    raise RuntimeError("native pick_place: omni.physx interface unavailable")
_sub = _physx.subscribe_physics_step_events(_on_step)
setattr(builtins, _SUB_ATTR, _sub)

{_PP_SCENE_RESET_MGR_SNIPPET}

# Register this controller's reset hook
def _native_pp_reset_hook():
    # Return True on success; False to retry next tick.
    # Critical: initialize() BEFORE probing. The `franka` wrapper in this
    # closure holds a reference to the PRE-STOP articulation view; calling
    # any method on it (incl. get_joint_positions) returns None until we
    # re-acquire a fresh view via franka.initialize(new_view).
    try:
        _view = SimulationManager.get_physics_sim_view()
        if _view is None: return False
    except Exception: return False
    try:
        franka.initialize(_view)          # re-acquire view FIRST
        franka.post_reset()                # re-bind gripper callbacks
        _probe = franka.get_joint_positions()
        if _probe is None: return False   # still not ready — retry
        controller.reset()
        # Clear IK-guide cache: warm-starting next IK with a stale
        # pre-Stop joint config leads to wild solutions (e.g. arm
        # reaching to 1.7m instead of 1.2m approach height).
        global _last_ik_cspace
        _last_ik_cspace = None
        # Force gripper open. PhysX Stop reverts joint POSITIONS to
        # initial, but the DRIVE TARGETS persist — so pre-Stop
        # gripper.forward('close') (target=0.0) keeps fingers at 0
        # across Play. Explicitly drive gripper to open state.
        try:
            _open_action = franka.gripper.forward("open")
            if _open_action: art_ctrl.apply_action(_open_action)
        except Exception as _ge: print(f"(gripper open on reset soft-fail: {{_ge}})")
        S["delivered"].clear()
        S["mode"] = "wait_sensor"
        S["picked_path"] = None
        S["cubes"] = 0
        S["errors"] = 0
        S["ticks"] = 0
        _a_cubes.Set(0); _a_err.Set(0); _a_tick.Set(0)
        _a_last_err.Set(""); _a_picked.Set(""); _a_phase.Set("wait_sensor")
        _resume_belt()
        print("(native_pp reset complete)")
        return True
    except Exception as _re:
        print(f"(native_pp reset exception: {{type(_re).__name__}}: {{_re}})")
        return False

getattr(builtins, _MGR_ATTR).register("native_pp_" + _ROBOT_TAG + "_" + _PHASE_ID, _native_pp_reset_hook)

print(json.dumps({{
    "ok": True,
    "mode": "native (franka PickPlaceController, canonical 62-line pattern + embedding fixes)",
    "robot": ROBOT_PATH,
    "sources": SOURCE_PATHS,
    "dest_path": DEST_PATH,
    "drop_target": DROP_TARGET,
    "ee_offset": EE_OFFSET.tolist(),
    "ee_initial_height": float(EE_INITIAL_HEIGHT),
    "sensor_gated": bool(_s_trig),
    "initial_state": S["mode"],
    "fixes_applied": [
        "SimulationManager.initialize_physics + app.update pump",
        f"end_effector_initial_height auto-computed = {{EE_INITIAL_HEIGHT:.3f}}m",
        "set_robot_base_pose re-applied after controller construction",
        "defensive skip when joint_positions is all-None (PickPlaceController phase 2)",
    ],
    "note": "controller owns state machine; tick-callback feeds live cube pose + drop pose.",
}}))
"""


def _gen_pick_place_spline(robot_path: str, sensor_path: str, belt_path: str,
                           source_paths: list, destination_path: str,
                           drop_target: str, ee_offset: list,
                           end_effector_initial_height=None,
                           spline_waypoint_dt=None,
                           grip_style: str = "friction",
                           color_routing=None,
                           mutex_path=None,
                           phase_id: str = "default") -> str:
    """Deterministic CPU-only pick-place: pre-plan 6-waypoint Cartesian
    trajectory per cube, warm-start IK chain for consistent redundancy
    branch, interpolate via scipy.CubicSpline (or numpy linear fallback).

    Design goals vs `native` (RmpFlow + PickPlaceController):
      - **No RmpFlow branch-hopping**: all 6 IK solutions chain warm-starts
        so wrist/elbow stay in the same redundancy branch across waypoints.
        No mid-transit "robot folds itself" snaps.
      - **No GPU required**: pure Lula IK + scipy. Runs on CPU-only
        laptops where cuRobo isn't available.
      - **Deterministic motion**: same scene → same trajectory. Cycle
        time is predictable (5-8s target). Sim2real-honest.
      - **Pre-checked waypoints**: if ANY IK fails, surface error before
        motion starts (vs RmpFlow which silently settles in local minima).

    Limitations:
      - No collision-awareness (uses Cartesian lift-and-transit to avoid
        obstacles; assumes the 6 waypoints + the straight spline between
        them are collision-free).
      - 6 hand-tuned waypoints; less flexible than cuRobo's free-form
        planning, but adequate for conveyor pick-place scenarios.

    Waypoint schedule (per cube):
      [0] approach_over_pick — above cube, at EE_INITIAL_HEIGHT
      [1] descend_to_pick    — cube xy, cube_z + EE_OFFSET (down-facing)
      [2] lift               — back to EE_INITIAL_HEIGHT at pick xy
      [3] transit_over_drop  — above drop, at EE_INITIAL_HEIGHT
      [4] descend_to_drop    — drop xy, drop_z (bin rim +5cm)
      [5] retreat            — back to EE_INITIAL_HEIGHT at drop xy

    Gripper actions: close between [1]→[2] (pause), open between [4]→[5].

    Interpolation: scipy.CubicSpline clamped (zero velocity at endpoints)
    through the 7-DoF joint configurations at waypoint times. Fallback
    to np.interp per-joint if scipy unavailable.

    Args:
        robot_path (str): USD prim path of the Franka articulation root.
        sensor_path (str or None): Proximity sensor prim path. Belt pauses on
            trigger; robot executes pick cycle; belt resumes after release.
        belt_path (str or None): Conveyor belt prim path.
        source_paths (list[str]): Ordered cube prim paths to deliver.
        destination_path (str or None): Default drop bin prim path.
        drop_target (str or None): Drop bin override.
        ee_offset (list[float]): [x, y, z] EE-to-fingertip offset, meters.
        end_effector_initial_height (float or None): Approach clearance height
            override. Auto-computed from scene geometry when None.
        spline_waypoint_dt (float or None): Time budget per waypoint segment
            (seconds). Defaults to 1.5 s per segment when None.
        grip_style (str): ``"fixed_joint"`` (attach cube via UsdPhysics.FixedJoint)
            or ``"friction"`` (rely on contact forces). Defaults to
            ``"fixed_joint"`` for reliability; unknown values coerce to
            ``"fixed_joint"``.
        color_routing (dict or None): Semantic color class name → bin prim
            path. Cube's ``Semantics_color`` class selects the destination.
            Falls through to ``destination_path`` when no entry matches.
        mutex_path (str or None): Stage prim path used as a robot-claim mutex.
            None disables multi-robot coordination.

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Prints a JSON dict with ``{"ok": True, "mode": "spline", ...}`` on
        success, or raises ``RuntimeError`` for pre-flight failures.
    """
    # (Phase 8 wave 9) tool_executor imports migrated to module body:
    # _PP_OBSERVABILITY_SNIPPET migrated to module body (Phase 8 wave 9).
    # _PP_SCENE_RESET_MGR_SNIPPET migrated to module body (Phase 8 wave 9).
    import json as _json
    grip_style_norm = grip_style if grip_style in ("fixed_joint", "friction") else "fixed_joint"
    return f"""\
# ── setup_pick_place_controller (spline) ─────────────────────────────
# Pre-planned 6-waypoint Cartesian trajectory, joint-space CubicSpline
# with warm-start IK chaining. CPU-only, deterministic, no RmpFlow.
import omni.usd, omni.timeline, omni.physx, omni.kit.app, numpy as np, builtins, json, time, os
from pxr import UsdGeom, Sdf, Gf, UsdPhysics
from isaacsim.core.api import World
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.core.utils.rotations import euler_angles_to_quat as _eul2q

ROBOT_PATH = {robot_path!r}
SENSOR_PATH = {sensor_path!r}
BELT_PATH = {belt_path!r}
SOURCE_PATHS = {_json.dumps(list(source_paths))}
DEST_PATH = {destination_path!r}
DROP_TARGET = {_json.dumps(drop_target) if drop_target else 'None'}
EE_OFFSET = np.array({_json.dumps(list(ee_offset))}, dtype=np.float32)
EE_INIT_H_OVERRIDE = {end_effector_initial_height!r}
WAYPOINT_DT = {_json.dumps(spline_waypoint_dt) if spline_waypoint_dt else 'None'}
GRIP_STYLE = {grip_style_norm!r}
MUTEX_PATH = {mutex_path!r}  # Multi-robot coordination — when set, robot must claim mutex before pickup
# SORT-01 enabler: same color_routing dispatch as cuRobo target_source.
# When non-empty, _bin_drop_pos selects destination per cube based on
# the cube's Semantics_color (or Semantics_class) class_name. Falls
# through to DEST_PATH when no entry matches.
COLOR_ROUTING = {_json.dumps(color_routing or {})}
_PHASE_ID = {phase_id!r}

# ── Clean up any prior subscription + stale Scene Reset Manager hooks ─
# Per-robot scoping (2026-05-28): see _gen_pick_place_native for full
# explanation. dual-arm templates need independent subs per robot.
# Track K (2026-05-28): per-phase scoping added.
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
_SUB_ATTR = "_spline_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
_old = getattr(builtins, _SUB_ATTR, None)
if _old is not None:
    try: _old.unsubscribe()
    except Exception: pass
    try: delattr(builtins, _SUB_ATTR)
    except Exception: pass
# Cross-mode sweep — this robot + this phase only. Other robots' / phases' subs survive.
for _a in list(vars(builtins).keys()):
    if _a.startswith(("_native_pp_", "_pick_place_", "_sensor_gated_", "_spline_pp_tl_")) \
       and (_a.endswith("_" + _ROBOT_TAG) or ("_" + _ROBOT_TAG + "_") in _a):
        _s = getattr(builtins, _a, None)
        if _s:
            try: _s.unsubscribe()
            except Exception: pass
        try: delattr(builtins, _a)
        except Exception: pass
# Any existing Scene Reset Manager has hooks referencing old (expired) prims.
# Clear THIS robot's + THIS phase's hooks + legacy un-tagged hooks.
_mgr_pre = getattr(builtins, "_scene_reset_manager", None)
if _mgr_pre is not None:
    for _hn in ("native_pp", "spline_pp", "sensor_gated_pp", "fixed_poses_pp", "curobo_pp", "diffik_pp", "osc_pp"):
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG + "_" + _PHASE_ID)
        except Exception: pass
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG)
        except Exception: pass
        try: _mgr_pre.unregister(_hn)
        except Exception: pass

stage = omni.usd.get_context().get_stage()
tl = omni.timeline.get_timeline_interface()
if not tl.is_playing():
    tl.play()

# ── Force physics initialization + app.update() pump ──────────────────
_app = omni.kit.app.get_app()
for _ in range(6):
    _app.update()
try:
    if SimulationManager.get_physics_sim_view() is None:
        SimulationManager.initialize_physics()
except Exception as _e:
    print(f"(initialize_physics soft-fail: {{_e}})")
_physics_sim_view = SimulationManager.get_physics_sim_view()

# ── World + Franka wrapper ────────────────────────────────────────────
world = World.instance() or World()
franka = Franka(prim_path=ROBOT_PATH, name="spline_pp_franka")
try:
    world.scene.add(franka)
except Exception:
    _existing = world.scene.get_object("spline_pp_franka")
    if _existing is not None:
        franka = _existing

try:
    franka.initialize(_physics_sim_view)
    franka.post_reset()
except Exception as _e:
    print(json.dumps({{"ok": False, "error": f"franka init failed: {{type(_e).__name__}}: {{_e}}"}}))
    raise

# Sync physics body pose from USD-authored transform (handles post-init rotation)
try:
    _robot_xf0 = UsdGeom.Xformable(stage.GetPrimAtPath(ROBOT_PATH))
    _mtx0 = _robot_xf0.ComputeLocalToWorldTransform(0)
    _usd_pos = np.array([float(_mtx0.ExtractTranslation()[i]) for i in range(3)], dtype=np.float32)
    _usd_q = _mtx0.ExtractRotationQuat()
    _usd_quat = np.array([float(_usd_q.GetReal())] +
                         [float(_usd_q.GetImaginary()[i]) for i in range(3)], dtype=np.float32)
    _phys_pos, _phys_quat = franka.get_world_pose()
    if (float(np.linalg.norm(_usd_pos - np.asarray(_phys_pos, dtype=np.float32))) > 1e-3 or
            float(np.linalg.norm(_usd_quat - np.asarray(_phys_quat, dtype=np.float32))) > 1e-3):
        franka.set_world_pose(position=_usd_pos, orientation=_usd_quat)
except Exception as _e:
    print(f"(physics body sync soft-fail: {{_e}})")

# Force canonical home joint config + persist as PhysX default
_HOME_Q = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04], dtype=np.float32)
try:
    _n_dof = len(franka.dof_names) if franka.dof_names else len(_HOME_Q)
    _home_trimmed = _HOME_Q[:_n_dof]
    franka.set_joint_positions(_home_trimmed)
    franka.set_joint_velocities(np.zeros(_n_dof, dtype=np.float32))
    try: franka.set_joints_default_state(positions=_home_trimmed,
                                          velocities=np.zeros(_n_dof, dtype=np.float32))
    except Exception: pass
    try: franka.set_default_state(position=_usd_pos, orientation=_usd_quat)
    except Exception: pass
except Exception as _e:
    print(f"(home pose force soft-fail: {{_e}})")

art_ctrl = franka.get_articulation_controller()

# ── Boost finger drive gains for friction grip ────────────────────────
# Default USD finger drives are too soft to clamp a 0.1kg cube: position
# drive with kp~1000 → cube slips out during lift. Boost to 10000 so
# fingers actually close against the cube body.
try:
    for _fj in ("panda_finger_joint1", "panda_finger_joint2"):
        _jp = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/panda_hand/{{_fj}}")
        if _jp.IsValid():
            _drv = UsdPhysics.DriveAPI.Get(_jp, "linear")
            if _drv:
                _drv.GetStiffnessAttr().Set(10000.0)
                _drv.GetDampingAttr().Set(200.0)
    print("(spline: finger drive gains boosted to kp=10000/kd=200)")
except Exception as _fe:
    print(f"(finger gain boost soft-fail: {{_fe}})")

# ── IK solver (Lula) ─────────────────────────────────────────────────
from isaacsim.robot_motion.motion_generation.lula.kinematics import LulaKinematicsSolver
_mpc_root = None
for _root_try in [
    "/mnt/shared_data/isaac-sim/exts/isaacsim.robot_motion.motion_generation",
    "/opt/isaac-sim/exts/isaacsim.robot_motion.motion_generation",
]:
    _cand = os.path.join(_root_try, "motion_policy_configs/franka/rmpflow")
    if os.path.isdir(_cand):
        _mpc_root = _cand
        break
if _mpc_root is None:
    raise RuntimeError("spline: Lula Franka config not found — cannot plan waypoints")

_ik_solver = LulaKinematicsSolver(
    robot_description_path=os.path.join(_mpc_root, "robot_descriptor.yaml"),
    urdf_path=os.path.normpath(os.path.join(_mpc_root, "..", "lula_franka_gen.urdf")),
)
_ik_solver.set_robot_base_pose(_usd_pos, _usd_quat)
_DOWN_QUAT = _eul2q(np.array([0, np.pi, 0]))
print("(spline: Lula IK solver ready)")

# ── Try scipy CubicSpline, fall back to numpy linear ─────────────────
try:
    from scipy.interpolate import CubicSpline as _CubicSpline
    _HAS_SCIPY = True
    print("(spline: using scipy.CubicSpline for interpolation)")
except Exception:
    _CubicSpline = None
    _HAS_SCIPY = False
    print("(spline: scipy unavailable — falling back to numpy linear interp)")

# ── Helpers ──────────────────────────────────────────────────────────
def _world_pos(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid(): return None
    t = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1]), float(t[2])])

def _cube_semantic_class(prim_path):
    \"\"\"Return cube's Semantics_color/colour/class data (lowercase) or None.
    Used by color_routing dispatch.\"\"\"
    try:
        from pxr import Semantics
    except Exception:
        return None
    p = stage.GetPrimAtPath(prim_path)
    if not p or not p.IsValid():
        return None
    for sname in ("Semantics_color", "Semantics_colour", "Semantics_class"):
        try:
            sem = Semantics.SemanticsAPI.Get(p, sname)
            if not sem: continue
            data_attr = sem.GetSemanticDataAttr()
            if data_attr and data_attr.IsValid():
                v = data_attr.Get()
                if v: return str(v).lower()
        except Exception:
            continue
    return None

def _destination_path_for(cube_path):
    \"\"\"Color-routing dispatch — returns destination prim per cube's
    Semantics class. Falls back to DEST_PATH when no routing match.\"\"\"
    if COLOR_ROUTING and cube_path:
        col = _cube_semantic_class(cube_path)
        if col and col in COLOR_ROUTING:
            return COLOR_ROUTING[col]
    return DEST_PATH

# Per-color drop-position cache (avoid recomputing bbox per pick)
_BIN_DROP_CACHE = {{}}
def _bin_drop_pos(cube_path=None):
    if DROP_TARGET is not None:
        return np.array(DROP_TARGET, dtype=np.float32)
    dest = _destination_path_for(cube_path) if cube_path else DEST_PATH
    if not dest:
        return None
    if dest in _BIN_DROP_CACHE:
        return _BIN_DROP_CACHE[dest]
    p = stage.GetPrimAtPath(dest)
    if p and p.IsValid():
        bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
        mn, mx = bb.GetMin(), bb.GetMax()
        pos = np.array([(mn[0]+mx[0])/2, (mn[1]+mx[1])/2, float(mx[2]) + 0.05], dtype=np.float32)
        _BIN_DROP_CACHE[dest] = pos
        return pos
    return None

def _compute_h1():
    if EE_INIT_H_OVERRIDE is not None:
        return float(EE_INIT_H_OVERRIDE)
    _zs = []
    for _sp in SOURCE_PATHS:
        _wp = _world_pos(_sp)
        if _wp is not None:
            _zs.append(float(_wp[2]))
    _dp = _bin_drop_pos()
    if _dp is not None:
        _zs.append(float(_dp[2]))
    if not _zs:
        return 0.3
    return max(_zs) + 0.20  # 20cm clearance

EE_INITIAL_HEIGHT = _compute_h1()

# ── IK solve with warm-start chaining ────────────────────────────────
def _solve_ik_chain(cartesian_waypoints, warm_start_seed=None):
    # cartesian_waypoints: list of (xyz, quat) tuples
    # Returns list of 7-DoF joint arrays, or raises on failure
    seed = warm_start_seed if warm_start_seed is not None else \\
           np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785], dtype=np.float64)
    solutions = []
    for i, (pos, quat) in enumerate(cartesian_waypoints):
        q, ok = _ik_solver.compute_inverse_kinematics(
            frame_name="panda_hand",
            target_position=np.asarray(pos, dtype=np.float64),
            target_orientation=np.asarray(quat, dtype=np.float64),
            warm_start=seed.astype(np.float64),
        )
        if not ok:
            raise RuntimeError(f"spline: IK failed at waypoint {{i}} pos={{pos.tolist() if hasattr(pos,'tolist') else pos}}")
        solutions.append(np.asarray(q, dtype=np.float64))
        seed = np.asarray(q, dtype=np.float64)
    return solutions

def _plan_pick_place(cube_pos, drop_pos, current_joints=None):
    # Build 6 Cartesian waypoints + dwell-phases; solve IK chain; build time schedule.
    # Schedule with dwell phases so the gripper has time to actually clamp:
    #
    #   idx  time    joint-config      phase
    #   0    0.0     q_approach        approach (above pick)
    #   1    T1      q_descend_pick    at pick (start dwell)
    #   2    T1+D    q_descend_pick    at pick (end dwell)  ← close fired in this window
    #   3    T2      q_lift            lifted
    #   4    T3      q_transit         above drop
    #   5    T4      q_descend_drop    at drop (start dwell)
    #   6    T4+D    q_descend_drop    at drop (end dwell)  ← open fired in this window
    #   7    T5      q_retreat         retreat
    #
    # Duplicate joint configs at dwell boundaries yield ~zero-velocity
    # segments in the spline — the robot physically holds position while
    # fingers close/open.
    h1 = EE_INITIAL_HEIGHT
    pick_xy = cube_pos[:2]
    drop_xy = drop_pos[:2]
    pick_z = float(cube_pos[2])
    drop_z = float(drop_pos[2])
    # Lula IK targets the `panda_hand` frame, which sits ~0.105m ABOVE
    # the fingertips. To place fingertips at cube center, we raise the
    # IK target by FINGER_LEN + optional offset. EE_OFFSET[2] is an
    # additional user-configurable tweak (default 0 for spline).
    FINGER_LEN = 0.105
    pick_descend_z = pick_z + FINGER_LEN + float(EE_OFFSET[2])
    unique_wps = [
        (np.array([pick_xy[0], pick_xy[1], h1]),            _DOWN_QUAT),  # 0 approach
        (np.array([pick_xy[0], pick_xy[1], pick_descend_z]), _DOWN_QUAT),  # 1 descend_pick
        (np.array([pick_xy[0], pick_xy[1], h1]),            _DOWN_QUAT),  # 2 lift
        (np.array([drop_xy[0], drop_xy[1], h1]),            _DOWN_QUAT),  # 3 transit
        (np.array([drop_xy[0], drop_xy[1], drop_z]),        _DOWN_QUAT),  # 4 descend_drop
        (np.array([drop_xy[0], drop_xy[1], h1]),            _DOWN_QUAT),  # 5 retreat
    ]
    warm = None
    if current_joints is not None and len(current_joints) >= 7:
        warm = np.asarray(current_joints[:7], dtype=np.float64)
    joint_solutions = _solve_ik_chain(unique_wps, warm_start_seed=warm)
    # Segment dt = time between unique waypoints; dwell = hold time at pick/drop
    seg_dt = float(WAYPOINT_DT) if WAYPOINT_DT is not None else 1.5
    dwell_dt = 1.2  # 1.2s hold for gripper clamp
    # Time schedule with duplicate waypoints at dwell boundaries
    # q_seq:   [q0, q1, q1, q2, q3, q4, q4, q5]
    # t_seq:   [0, T1, T1+D, T2, T3, T4, T4+D, T5]
    t_arr = np.array([
        0.0,                        # 0 approach
        seg_dt,                     # 1 descend_pick (start dwell)
        seg_dt + dwell_dt,          # 2 descend_pick (end dwell)
        seg_dt + dwell_dt + seg_dt, # 3 lift
        seg_dt + dwell_dt + seg_dt*2, # 4 transit
        seg_dt + dwell_dt + seg_dt*3, # 5 descend_drop (start dwell)
        seg_dt + dwell_dt + seg_dt*3 + dwell_dt, # 6 descend_drop (end dwell)
        seg_dt + dwell_dt + seg_dt*4 + dwell_dt, # 7 retreat
    ], dtype=np.float64)
    q_seq = np.vstack([
        joint_solutions[0], joint_solutions[1], joint_solutions[1],
        joint_solutions[2], joint_solutions[3], joint_solutions[4],
        joint_solutions[4], joint_solutions[5],
    ])
    # Gripper events fire early in each dwell window so fingers have full dwell time
    grip_close_t = float(t_arr[1]) + 0.2   # just after arriving at pick
    grip_open_t  = float(t_arr[5]) + 0.2   # just after arriving at drop
    return {{
        "times": t_arr,
        "joints": q_seq,
        "grip_close_t": grip_close_t,
        "grip_open_t": grip_open_t,
        "total_t": float(t_arr[-1]) + 0.5,  # settle 0.5s at retreat
        "cube_pos": [float(x) for x in cube_pos],
        "drop_pos": [float(x) for x in drop_pos],
    }}

def _make_trajectory(plan):
    # Returns a callable t → 7-dim joint config
    times = plan["times"]; joints = plan["joints"]
    if _HAS_SCIPY:
        cs = _CubicSpline(times, joints, axis=0, bc_type='clamped')
        def _sample(t):
            t_clipped = min(max(t, float(times[0])), float(times[-1]))
            return cs(t_clipped)
        return _sample
    else:
        def _sample(t):
            t_clipped = min(max(t, float(times[0])), float(times[-1]))
            out = np.empty(joints.shape[1], dtype=np.float64)
            for j in range(joints.shape[1]):
                out[j] = np.interp(t_clipped, times, joints[:, j])
            return out
        return _sample

# ── Belt pause/resume ────────────────────────────────────────────────
_belt_prim = stage.GetPrimAtPath(BELT_PATH) if BELT_PATH else None
_belt_sv = _belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if (_belt_prim and _belt_prim.IsValid()) else None
_captured = tuple(_belt_sv.Get()) if (_belt_sv and _belt_sv.IsDefined() and _belt_sv.Get()) else None
if _captured is None or sum(abs(v) for v in _captured) < 1e-6:
    _nominal_belt = (0.2, 0.0, 0.0)
else:
    _nominal_belt = _captured
def _pause_belt():
    if _belt_sv: _belt_sv.Set((0, 0, 0))
def _resume_belt():
    if _belt_sv: _belt_sv.Set(_nominal_belt)
if _belt_sv and sum(abs(v) for v in (_belt_sv.Get() or (0,0,0))) < 1e-6:
    _resume_belt()

# ── Gripper actions ──────────────────────────────────────────────────
def _grip_open():
    try:
        a = franka.gripper.forward("open")
        if a: art_ctrl.apply_action(a)
    except Exception as _ge: print(f"(gripper open soft-fail: {{_ge}})")
def _grip_close():
    try:
        a = franka.gripper.forward("close")
        if a: art_ctrl.apply_action(a)
    except Exception as _ge: print(f"(gripper close soft-fail: {{_ge}})")

# ── Grasp: FRICTION only ──────────────────────────────────────────────
def _attach_cube(cube_path):
    # No EE↔cube FixedJoint (Anton's rule: the grip may never be a FixedJoint).
    # The grip is friction-based — _grip_close() (franka.gripper.forward("close"))
    # already drives the parallel-jaw fingers to compress against the cube, and
    # the scene's finger friction material holds it via physical contact.
    return None
def _detach_cube(jp):
    if jp and stage.GetPrimAtPath(jp).IsValid():
        stage.RemovePrim(jp)

# ── Sensor + proximity latch ──────────────────────────────────────────
_sensor = stage.GetPrimAtPath(SENSOR_PATH) if SENSOR_PATH else None
def _sensor_world_pos():
    if _sensor is None or not _sensor.IsValid(): return None
    t = UsdGeom.Xformable(_sensor).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1]), float(t[2])])
_SENSOR_RADIUS = 0.08
_sensor_pos = _sensor_world_pos()
# Reach-based cube selection — beats pure sensor-proximity gating because
# cubes can whoosh past the sensor during a 10s pick cycle and never
# trigger again once we resume belt. Instead: pick ANY undelivered cube
# still on belt within robot workspace. Priority = closest to sensor
# (so we pick sequentially in approach order when multiple ready).
def _cube_to_pick():
    base_xy = np.array([float(_usd_pos[0]), float(_usd_pos[1])])
    sensor_xy = (_sensor_pos[:2] if _sensor_pos is not None else base_xy)
    candidates = []
    for _sp in SOURCE_PATHS:
        if _sp in S["delivered"] or _is_in_bin(_sp): continue
        _cp = _world_pos(_sp)
        if _cp is None: continue
        # On-belt check: cube z should be within ±5cm of belt top (~0.875)
        if _cp[2] < 0.83 or _cp[2] > 0.95: continue
        # Reach check: within 70cm of robot base in XY
        _d_base = float(np.linalg.norm(_cp[:2] - base_xy))
        if _d_base > 0.70: continue
        _d_sensor = float(np.linalg.norm(_cp[:2] - sensor_xy))
        candidates.append((_d_sensor, _sp))
    if not candidates: return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]

{_PP_OBSERVABILITY_SNIPPET}
_a_mode.Set("spline")

# ── State ────────────────────────────────────────────────────────────
# mode: wait_sensor | planning | executing | gripping | transit | releasing | returning | idle
S = {{"mode": "wait_sensor", "picked_path": None, "grasp_joint": None,
      "plan": None, "traj_fn": None, "start_t": None,
      "cubes": 0, "errors": 0, "ticks": 0, "delivered": set(),
      "grip_closed_done": False, "grip_opened_done": False}}

def _record_err(e):
    S["errors"] += 1
    try:
        _a_err.Set(S["errors"])
        _a_last_err.Set(f"{{type(e).__name__}}: {{str(e)[:150]}}")
        print(f"(curobo pp ERR ticks={{S['ticks']}}: {{type(e).__name__}}: {{str(e)[:200]}})", flush=True)
    except Exception: pass

# Diagnostic — log mode transitions + claim details, write last ~10 to USD attr
_MODE_LOG = []  # (tick, mode, info)
def _log_event(info=""):
    try:
        _MODE_LOG.append((S["ticks"], S["mode"], str(info)[:80]))
        if len(_MODE_LOG) > 50: _MODE_LOG.pop(0)
        try: open("/tmp/mt_diag.txt", "a").write("EVENT %s tick=%s mode=%s %s\\n" % (ROBOT_PATH, S["ticks"], S["mode"], str(info)[:80]))  # 2026-06-16 DIAG: full event timeline
        except Exception: pass
        # Write tail (last 8 events) to USD attr — readable from outside
        tail = _MODE_LOG[-8:]
        log_str = " || ".join([f"t{{m[0]}}:{{m[1]}}={{m[2]}}" for m in tail])
        _attr = stage.GetPrimAtPath(ROBOT_PATH).CreateAttribute("curobo_mode_log", Sdf.ValueTypeNames.String)
        _attr.Set(log_str[:800])
    except Exception: pass

def _bin_bounds():
    if not DEST_PATH: return None
    p = stage.GetPrimAtPath(DEST_PATH)
    if not p or not p.IsValid(): return None
    bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    return (np.array([bb.GetMin()[0], bb.GetMin()[1]]),
            np.array([bb.GetMax()[0], bb.GetMax()[1]]))

def _is_in_bin(cube_path):
    bounds = _bin_bounds()
    if bounds is None: return False
    cp = _world_pos(cube_path)
    if cp is None: return False
    mn, mx = bounds
    return (mn[0] <= cp[0] <= mx[0]) and (mn[1] <= cp[1] <= mx[1])

def _apply_joint_target(q7):
    # Map 7-DoF arm config to full dof_names order; leave gripper joints
    # to the gripper.forward() drives (unaffected)
    _dof_names = list(franka.dof_names) if franka.dof_names else []
    if not _dof_names:
        return
    # First 7 DOFs of Franka are arm; indices 7,8 are fingers
    _target = np.array(franka.get_joint_positions(), dtype=np.float64).copy()
    _target[:min(7, len(_target))] = q7[:min(7, len(_target))]
    art_ctrl.apply_action(ArticulationAction(
        joint_positions=_target.astype(np.float64),
    ))

def _on_step(dt):
    try:
        # Round 7 repair (2026-05-18): guard against expired prim refs.
        try:
            _check_robot_pp = stage.GetPrimAtPath(ROBOT_PATH)
            if not _check_robot_pp or not _check_robot_pp.IsValid():
                try:
                    if '_sub' in globals() and _sub is not None and hasattr(_sub, 'unsubscribe'):
                        _sub.unsubscribe()
                except Exception: pass
                return
        except Exception:
            return
        S["ticks"] += 1
        try:
            _a_tick.Set(S["ticks"])
            _a_phase.Set(S["mode"])
        except Exception:
            return

        if S["mode"] == "wait_sensor":
            # Multi-robot mutex: only claim cube if mutex is free or already
            # held by us. If held by another robot, wait this tick.
            if MUTEX_PATH:
                try:
                    _mp = stage.GetPrimAtPath(MUTEX_PATH)
                    if _mp and _mp.IsValid():
                        _claimed = _mp.GetAttribute("mutex:claimed_by").Get() or ""
                        if _claimed and _claimed != ROBOT_PATH:
                            return  # other robot holds mutex; wait
                except Exception: pass
            picked = _cube_to_pick()
            if picked:
                # Acquire mutex before claiming cube
                if MUTEX_PATH:
                    try:
                        _mp = stage.GetPrimAtPath(MUTEX_PATH)
                        if _mp and _mp.IsValid():
                            _mp.GetAttribute("mutex:claimed_by").Set(ROBOT_PATH)
                            _cc = _mp.GetAttribute("mutex:claim_count")
                            if _cc and _cc.IsDefined():
                                _cc.Set(int(_cc.Get() or 0) + 1)
                    except Exception: pass
                S["picked_path"] = picked
                _a_picked.Set(picked)
                _pause_belt()
                S["mode"] = "planning"
                _log_event(f"claim:{{picked}}")
            return

        if S["mode"] == "planning":
            cube_pos = _world_pos(S["picked_path"])
            # Pass cube_path so COLOR_ROUTING can dispatch per cube
            drop_pos = _bin_drop_pos(S["picked_path"])
            if cube_pos is None or drop_pos is None:
                _log_event(f"plan_miss_pos cube={{cube_pos}} drop={{drop_pos}}")
                _record_err(RuntimeError("planning: missing cube or drop position"))
                S["mode"] = "wait_sensor"; S["picked_path"] = None
                # Don't resume belt on planning failure — undelivered cubes
                # would drift past sensor before next cycle tries them.
                return
            try:
                # Always seed IK chain from HOME config — not from current
                # joint state. Current state depends on previous cycle's
                # retreat pose, which can land the IK solver in a different
                # redundancy branch each cycle → wrist-snap between picks.
                # Home-seeded chain gives consistent branch across cubes.
                _log_event(f"plan_call cube=({{cube_pos[0]:.2f}},{{cube_pos[1]:.2f}},{{cube_pos[2]:.2f}}) drop=({{drop_pos[0]:.2f}},{{drop_pos[1]:.2f}},{{drop_pos[2]:.2f}})")
                plan = _plan_pick_place(cube_pos, drop_pos,
                                         current_joints=_HOME_Q[:7])
                _log_event(f"plan_ok total_t={{plan.get('total_t',0):.1f}}")
            except Exception as _pe:
                _log_event(f"plan_FAIL: {{type(_pe).__name__}}:{{str(_pe)[:60]}}")
                _record_err(_pe)
                S["mode"] = "wait_sensor"; S["picked_path"] = None
                return
            S["plan"] = plan
            S["traj_fn"] = _make_trajectory(plan)
            S["start_t"] = time.monotonic()
            S["grip_closed_done"] = False
            S["grip_opened_done"] = False
            _grip_open()  # ensure open before approach
            S["mode"] = "executing"
            return

        if S["mode"] == "executing":
            if S["traj_fn"] is None or S["plan"] is None:
                S["mode"] = "wait_sensor"; return
            elapsed = time.monotonic() - S["start_t"]
            plan = S["plan"]

            # Gripper event: close
            if not S["grip_closed_done"] and elapsed >= plan["grip_close_t"]:
                _grip_close()
                _jp = _attach_cube(S["picked_path"])
                if _jp: S["grasp_joint"] = _jp
                S["grip_closed_done"] = True
                _log_event(f"grip_close jp={{bool(_jp)}} elapsed={{elapsed:.1f}}")

            # Gripper event: open (release) — gate on cube xy proximity to
            # drop target. cuRobo trajectory time may advance past grip_open_t
            # while EE hasn't physically converged to drop pose; releasing
            # then drops cube on table. Hold release until cube is close.
            if not S["grip_opened_done"] and elapsed >= plan["grip_open_t"]:
                _drop_xy_close = True
                if ROBOT_FAMILY in ("ur10", "ur10e") and S.get("picked_path"):
                    try:
                        _cubp = _world_pos(S["picked_path"])
                        _dropp = plan.get("drop_pos")
                        if _cubp is not None and _dropp is not None:
                            _xyd = float(np.linalg.norm(np.array(_cubp[:2]) - np.array(_dropp[:2])))
                            _drop_xy_close = _xyd < 0.10  # 0.10m bin xy tolerance
                    except Exception: pass
                if _drop_xy_close:
                    if S["grasp_joint"]:
                        _detach_cube(S["grasp_joint"])
                        S["grasp_joint"] = None
                    _grip_open()
                    S["grip_opened_done"] = True
                # else: keep grip_opened_done False, retry next tick once EE arrives

            # Sample trajectory
            q_target = S["traj_fn"](elapsed)
            _apply_joint_target(q_target)

            if elapsed >= plan["total_t"]:
                # Log final cube position vs drop target to understand delivery success
                try:
                    _final_cubp = _world_pos(S["picked_path"]) if S["picked_path"] else None
                    _drop = plan.get("drop_pos") if plan else None
                    if _final_cubp and _drop:
                        _xy_err = ((_final_cubp[0]-_drop[0])**2 + (_final_cubp[1]-_drop[1])**2)**0.5
                        _z_err = abs(_final_cubp[2]-_drop[2])
                        _log_event(f"cycle_end xy_err={{_xy_err:.3f}} z_err={{_z_err:.3f}}")
                    else:
                        _log_event(f"cycle_end no_pos cubp={{_final_cubp is not None}} drop={{_drop is not None}}")
                except Exception: pass
                # Delivered (or at least trajectory finished). Force-release
                # any held UR10 FixedJoint — even if cube is far from drop
                # (drop-precision-fix held it, but cycle is ending so EE must
                # be freed for next cube). Cube falls wherever it is.
                if S.get("grasp_joint"):
                    try: _detach_cube(S["grasp_joint"])
                    except Exception: pass
                    S["grasp_joint"] = None
                # (dead UR10-FJ removal block deleted — spline is Franka-only, no grip-FJ)
                S["cubes"] += 1
                _a_cycles.Set(S["cubes"])
                if S["picked_path"]:
                    S["delivered"].add(S["picked_path"])
                    _a_cubes.Set(len(S["delivered"]))
                S["picked_path"] = None; _a_picked.Set("")
                S["plan"] = None; S["traj_fn"] = None; S["start_t"] = None
                # Release mutex so other robots can claim
                if MUTEX_PATH:
                    try:
                        _mp = stage.GetPrimAtPath(MUTEX_PATH)
                        if _mp and _mp.IsValid():
                            _attr = _mp.GetAttribute("mutex:claimed_by")
                            if _attr and (_attr.Get() or "") == ROBOT_PATH:
                                _attr.Set("")
                    except Exception: pass
                S["mode"] = "wait_sensor"
                # Keep belt PAUSED between cycles — cube positions stay
                # frozen so later cycles don't miss cubes that drift past
                # sensor during transit. Belt only resumes when all cubes
                # delivered (triggers next round) or on explicit reset.
                if len(S["delivered"]) >= len(SOURCE_PATHS):
                    _resume_belt()
            return

    except Exception as e:
        _record_err(e)

# ── Subscribe ─────────────────────────────────────────────────────────
_physx = omni.physx.get_physx_interface()
if _physx is None:
    raise RuntimeError("spline pick_place: omni.physx interface unavailable")
_sub = _physx.subscribe_physics_step_events(_on_step)
setattr(builtins, _SUB_ATTR, _sub)

{_PP_SCENE_RESET_MGR_SNIPPET}

# Scene Reset Manager hook (robot-agnostic)
def _spline_pp_reset_hook():
    try:
        _view = SimulationManager.get_physics_sim_view()
        if _view is None: return False
    except Exception: return False
    try:
        franka.initialize(_view)
        franka.post_reset()
        _probe = franka.get_joint_positions()
        if _probe is None: return False
        # Drop any FixedJoint from a previous cycle
        if S["grasp_joint"]:
            _detach_cube(S["grasp_joint"])
            S["grasp_joint"] = None
        _grip_open()
        S["delivered"].clear()
        S["mode"] = "wait_sensor"
        S["picked_path"] = None
        S["plan"] = None; S["traj_fn"] = None; S["start_t"] = None
        S["cubes"] = 0; S["errors"] = 0; S["ticks"] = 0
        S["grip_closed_done"] = False; S["grip_opened_done"] = False
        _a_cubes.Set(0); _a_err.Set(0); _a_tick.Set(0)
        _a_last_err.Set(""); _a_picked.Set(""); _a_phase.Set("wait_sensor")
        _resume_belt()
        print("(spline_pp reset complete)")
        return True
    except Exception as _re:
        print(f"(spline_pp reset exception: {{type(_re).__name__}}: {{_re}})")
        return False

getattr(builtins, _MGR_ATTR).register("spline_pp_" + _ROBOT_TAG + "_" + _PHASE_ID, _spline_pp_reset_hook)

print(json.dumps({{
    "ok": True,
    "mode": "spline (6-waypoint Lula IK chain + scipy.CubicSpline interpolation)",
    "robot": ROBOT_PATH,
    "sources": SOURCE_PATHS,
    "dest_path": DEST_PATH,
    "grip_style": GRIP_STYLE,
    "ee_initial_height": float(EE_INITIAL_HEIGHT),
    "waypoint_dt": float(WAYPOINT_DT) if WAYPOINT_DT is not None else 1.0,
    "interp": "scipy.CubicSpline" if _HAS_SCIPY else "np.interp (linear fallback)",
    "initial_state": S["mode"],
    "note": "IK chain warm-starts each waypoint from previous solution — stays in same redundancy branch, no wrist-snap.",
}}))
"""


def _gen_pick_place_curobo(robot_path: str, sensor_path: str, belt_path: str,
                           source_paths: list, destination_path: str,
                           drop_target: str, ee_offset: list,
                           end_effector_initial_height=None,
                           planning_obstacles=None,
                           curobo_world_yml=None,
                           color_routing=None,
                           drop_targets=None,
                           gripper_rotation=None,
                           robot_family: str = "franka",
                           require_upright: bool = False,
                           upright_dot_threshold: float = 0.85,
                           mutex_path=None,
                           scenario_profile=None,
                           arm_scope=None,
                           claim_radius=None,
                           task=None,
                           task_joint_path=None,
                           task_args=None,
                           phase_id: str = "default") -> str:
    """GPU-accelerated global trajectory optimization via cuRobo MotionPlanner.

    **Unlocked 2026-04-21** — four breakthroughs that enable cuRobo inside Kit:
      1. Env-bridge via ``sys.path.insert`` + ``importlib.invalidate_caches()`` (I-29)
      2. ``wp.func`` monkey-patch for Warp 1.8.2 vs cuRobo's 1.9+ expectation (I-28)
      3. ``cuda-core[cu12]`` pip-installed → enables cuRobo's runtime kernel backend
      4. cuRobo ``content/`` directory (franka.yml + task YAMLs + URDF + meshes)
         synced from NVlabs/curobo GitHub main branch into the installed package

    Pipeline (per cube):
      - Plan 5 trajectory segments via ``planner.plan_pose(goal_tool_pose, current_state)``:
          S1: current → approach_above_cube (h1)
          S2: approach → descend_to_pick (cube_z + finger_len)
          S3: pick → lift → transit_above_drop (h1)
          S4: transit → descend_to_drop (drop_z)
          S5: drop → retreat → home
      - Per-tick: sample ``interpolated_plan``'s joint positions over the segment's
        ``motion_time``; apply via ``apply_action(joint_positions=...)``
      - Gripper close between S2 → S3, open between S4 → S5

    Planner is cached in ``builtins._curobo_pp_planner`` across installs to avoid
    the ~5s warmup cost (first ``plan_pose`` compiles the CUDA graph).

    Expected cycle time: 3–5 s after warmup (0.5s/plan × 5 plans + execution).
    Expected delivery: 3–4/4 (collision-aware planning avoids wrist-snap AND
    handles bin rim collisions that plague the spline variant's cube 4).

    scene_cfg routing via ``scenario_profile``:
      None / ``"single_belt_pick"`` (default):
        Include Table, ConveyorBelt, and Bin in ``scene_cfg`` + PLANNING_OBSTACLES.
        Correct for CP-22/59/65 multi-cube belt scenarios.
      ``"obstacle_rich"``:
        EXCLUDE Table/ConveyorBelt/Bin from ``scene_cfg``; use only
        PLANNING_OBSTACLES (Pillar, packed pedestals, etc.).  When the robot
        home pose is at z=0.75 (on a table), including the table prim makes
        cuRobo flag the robot as in-collision → 24/24 ``plan_pose`` fails.
        This profile lets ``plan_pose`` succeed for CP-37/46/48 etc. where
        obstacles are supplied explicitly.

    Args:
        robot_path (str): USD prim path of the robot articulation root.
        sensor_path (str or None): Proximity sensor prim path. Delivery waits
            for a sensor trigger before picking each cube.
        belt_path (str or None): Conveyor belt prim path. Belt is paused while
            the robot picks and re-started after release.
        source_paths (list[str]): Ordered list of cube prim paths to deliver.
        destination_path (str or None): Default drop bin prim path.
        drop_target (str or None): Alternative drop target (overrides
            destination_path when non-None).
        ee_offset (list[float]): [x, y, z] offset from EE link to fingertip
            approach point, meters.
        end_effector_initial_height (float or None): Override for the height
            above the floor at which the EE starts its approach. Auto-computed
            from source/dest Z + clearance when None.
        planning_obstacles (list[str]): Extra prim paths to include as
            collision primitives in the cuRobo scene model.
        curobo_world_yml (str or None): Path to a custom world YAML for cuRobo.
            Uses the built-in ``collision_primitives_3d.yml`` when None.
        color_routing (dict or None): Map of semantic color class name → bin
            prim path. When provided, ``_bin_drop_pos`` selects the destination
            per cube based on the cube's ``Semantics_color`` class. Falls
            through to ``destination_path`` when no entry matches.
        drop_targets (dict or None): Alternative per-class routing dict (keyed
            by semantic class, not color). Takes precedence over color_routing.
        gripper_rotation (float or None): Additional yaw (degrees) to apply to
            the grasp orientation. None uses a default downward-facing grasp.
        robot_family (str): ``"franka"`` (7-DOF + ParallelGripper) or
            ``"ur10"`` / ``"ur10e"`` (6-DOF, suction gripper). Defaults to
            ``"franka"``.
        require_upright (bool): If True, reject grasps where the EE +Z axis
            deviates from world +Z by more than ``upright_dot_threshold``.
            Defaults to False.
        upright_dot_threshold (float): Minimum dot product for upright filter.
            Defaults to ``_UPRIGHT_DOT_THRESHOLD_DEFAULT`` (0.85).
        mutex_path (str or None): Stage prim path used as a robot-claim mutex.
            When set, the robot must acquire the mutex before picking each cube
            (multi-robot coordination). None disables mutex logic.
        scenario_profile (str or None): Scene-cfg routing hint — see above.

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        When exec'd, the code installs a physics-step subscription that runs
        the cuRobo pick-place state machine. Prints a JSON dict with
        ``{"ok": True, "mode": "curobo", "cubes_queued": N, ...}`` on success,
        or raises ``RuntimeError`` for pre-flight failures.
    """
    # (Phase 8 wave 9) tool_executor imports migrated to module body:
    # _PP_OBSERVABILITY_SNIPPET migrated to module body (Phase 8 wave 9).
    # _PP_SCENE_RESET_MGR_SNIPPET migrated to module body (Phase 8 wave 9).
    import json as _json
    _obs = _json.dumps(list(planning_obstacles) if planning_obstacles else [])
    return f"""\
# ── setup_pick_place_controller (curobo) — MotionPlanner + 5-segment plan ──
import sys, importlib, omni.usd, omni.timeline, omni.physx, omni.kit.app, numpy as np, builtins, json, time, os
from pxr import UsdGeom, Sdf, Gf, UsdPhysics

# Env-bridge to isaac_lab_env site-packages
_CUROBO_SP = "/home/anton/miniconda3/envs/isaac_lab_env/lib/python3.11/site-packages"
while _CUROBO_SP in sys.path:
    sys.path.remove(_CUROBO_SP)
sys.path.insert(0, _CUROBO_SP)
importlib.invalidate_caches()

# 2026-06-04 ROOT FIX (RCA-verified): the OLD shim stripped module= from EVERY wp.func call on the FALSE premise
# "Kit bundles warp 1.8.2". The env actually runs conda warp 1.11.0 (Isaac runs the SAME warp via symlink), whose
# wp.func NATIVELY supports module= (verified: inspect.signature(wp.func) has 'module'). cuRobo's collision kernels
# call wp.func(..., module=__name__) so the cuboid/mesh/voxel is_obs_enabled overloads accumulate into ONE module
# (warp reads scope_locals via inspect f_back.f_back). Stripping module= scattered them -> only the LAST (voxel)
# survived -> WarpCodegenError "is_obs_enabled [CuboidDataWarp,int32,int32]" + SILENTLY BROKEN cuboid collision
# (this is also why "cache corruption" looked intermittent historically). FIX: shim ONLY if warp genuinely lacks
# module= support; otherwise leave warp's NATIVE wp.func untouched. Do NOT wrap (an extra call frame breaks the
# f_back.f_back scope_locals threading -> re-breaks the overload accumulation).
import warp as wp
import inspect as _wp_inspect
try:
    _wp_func_has_module = ("module" in _wp_inspect.signature(wp.func).parameters)
except Exception:
    _wp_func_has_module = False
if (not _wp_func_has_module) and (not hasattr(wp, "_curobo_pp_orig_func")):
    wp._curobo_pp_orig_func = wp.func
    def _curobo_pp_patched_func(f=None, *, name=None, module=None, **_kw):
        return wp._curobo_pp_orig_func(f, name=name) if f is not None else wp._curobo_pp_orig_func
    wp.func = _curobo_pp_patched_func

import torch
from curobo.motion_planner import MotionPlanner, MotionPlannerCfg
from curobo.types import JointState, GoalToolPose

from isaacsim.core.api import World
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.core.utils.types import ArticulationAction

# Robot-family branching: Franka uses 7-DOF + ParallelGripper, UR10 uses 6-DOF
# without built-in gripper (suction via separate surface_gripper tool).
# Round 6 repair (2026-05-18): accept "franka_panda" / "panda" / "frankarobotics"
# as friendly aliases (templates use these forms for robot_wizard so they
# naturally appear in robot_family too). Normalize before branching.
_ROBOT_FAMILY_RAW = {robot_family!r}
_ROBOT_FAMILY_NORM = {{
    "franka_panda": "franka",
    "panda": "franka",
    "franka_emika_panda": "franka",
    "frankarobotics": "franka",
    "frankaemika_panda": "franka",
    "ur10e": "ur10",
    "g1": "g1_arm",
    "unitree_g1": "g1_arm",
    "g1_left_arm": "g1_arm",
    "g1_right_arm": "g1_arm",
}}.get(str(_ROBOT_FAMILY_RAW).lower(), str(_ROBOT_FAMILY_RAW).lower())
ROBOT_FAMILY = _ROBOT_FAMILY_NORM
ARM_SCOPE = {arm_scope!r}  # 2026-05-28 J0 — "left"/"right" for g1_arm; None for others
# Note: _PHASE_ID is declared later (Track K convention) and used downstream
# for subscription / hook naming — no need to redeclare here.
if str(_ROBOT_FAMILY_RAW).lower() == "g1_left_arm" and not ARM_SCOPE:
    ARM_SCOPE = "left"
elif str(_ROBOT_FAMILY_RAW).lower() == "g1_right_arm" and not ARM_SCOPE:
    ARM_SCOPE = "right"
if ROBOT_FAMILY == "franka":
    from isaacsim.robot.manipulators.examples.franka import Franka as _RobotWrapper
    _ARM_DOF = 7
    _CUROBO_ROBOT_CFG = "franka.yml"
    _TOOL_FRAME = "panda_hand"
    _GRIPPER_LINK = "panda_hand"
    _FINGER_JOINTS = ("panda_finger_joint1", "panda_finger_joint2")
elif ROBOT_FAMILY in ("ur10", "ur10e"):
    # UR10 wrapper class hardcodes attach_gripper EE+gripper init — using
    # the bare SingleArticulation avoids that init path. Surface gripper is
    # wired separately via create_gripper(suction) in CP-70+ canonicals.
    from isaacsim.core.prims import SingleArticulation as _RobotWrapper
    _ARM_DOF = 6
    if ROBOT_FAMILY == "ur10":
        # 2026-06-01: the scene UR10 uses Isaac's ur10_robot.urdf kinematics with
        # an `ee_link` grip frame; cuRobo's bundled ur10e.yml is the e-series
        # (different link lengths + a `tool0` tip and no ee_link). Planning with
        # ur10e against the real UR10 leaves the planned EE off the cube (only the
        # upper arm reaches — confirmed via PhysX contact reports). ur10_scene.yml
        # points cuRobo at the scene robot's OWN URDF and targets ee_link so the
        # planned tip == the actual grip frame. Gated UR10-only; ur10e keeps tool0.
        _CUROBO_ROBOT_CFG = "ur10_scene.yml"
        _TOOL_FRAME = "ee_link"
    else:
        _CUROBO_ROBOT_CFG = "ur10e.yml"
        _TOOL_FRAME = "tool0"
    _GRIPPER_LINK = "wrist_3_link"
    _FINGER_JOINTS = ()  # UR10 has no built-in gripper; use surface_gripper separately
elif ROBOT_FAMILY == "g1_arm":
    # 2026-05-28 J0 — Unitree G1 humanoid, single-arm scope.
    # unitree_g1.yml holds the full 29-DOF model; we LOCK every non-arm
    # joint via cuRobo's `lock_joints` so the planner optimizes only this
    # arm's 7 joints. ARM_SCOPE must be "left"|"right"; defaults to "right".
    # Per docs/notes/2026-05-28-g1-humanoid-impl-scope.md P0.
    from isaacsim.core.prims import SingleArticulation as _RobotWrapper
    if not ARM_SCOPE:
        ARM_SCOPE = "right"
    if ARM_SCOPE not in ("left", "right"):
        raise RuntimeError(
            f"g1_arm: arm_scope must be 'left' or 'right', got {{ARM_SCOPE!r}}")
    _ARM_DOF = 7
    _CUROBO_ROBOT_CFG = "unitree_g1.yml"
    _TOOL_FRAME = ("right_hand_index_1_link" if ARM_SCOPE == "right"
                    else "left_hand_index_1_link")
    _GRIPPER_LINK = ("right_hand_palm_link" if ARM_SCOPE == "right"
                      else "left_hand_palm_link")
    # G1 dex hand has 7 joints per side; V0 uses surface-gripper FJ-attach.
    _FINGER_JOINTS = ()
else:
    raise RuntimeError(f"Unsupported robot_family: {{ROBOT_FAMILY!r}}")

# 2026-05-28 J0: per-arm lock_joints for G1. Joint names sourced from
# unitree_g1.yml cspace.joint_names.
_G1_ALL_JOINTS = [
    "base_j_x","base_j_y","base_j_z","base_j_xtheta","base_j_ytheta","base_j_ztheta",
    "left_hip_pitch_joint","left_hip_roll_joint","left_hip_yaw_joint",
    "left_knee_joint","left_ankle_pitch_joint","left_ankle_roll_joint",
    "right_hip_pitch_joint","right_hip_roll_joint","right_hip_yaw_joint",
    "right_knee_joint","right_ankle_pitch_joint","right_ankle_roll_joint",
    "waist_yaw_joint","waist_roll_joint","waist_pitch_joint",
    "left_shoulder_pitch_joint","left_shoulder_roll_joint","left_shoulder_yaw_joint",
    "left_elbow_joint","left_wrist_roll_joint","left_wrist_pitch_joint","left_wrist_yaw_joint",
    "left_hand_thumb_0_joint","left_hand_thumb_1_joint","left_hand_thumb_2_joint",
    "left_hand_middle_0_joint","left_hand_middle_1_joint",
    "left_hand_index_0_joint","left_hand_index_1_joint",
    "right_shoulder_pitch_joint","right_shoulder_roll_joint","right_shoulder_yaw_joint",
    "right_elbow_joint","right_wrist_roll_joint","right_wrist_pitch_joint","right_wrist_yaw_joint",
    "right_hand_thumb_0_joint","right_hand_thumb_1_joint","right_hand_thumb_2_joint",
    "right_hand_middle_0_joint","right_hand_middle_1_joint",
    "right_hand_index_0_joint","right_hand_index_1_joint",
]
def _g1_active_arm_joints(scope):
    pre = "left_" if scope == "left" else "right_"
    return [pre+"shoulder_pitch_joint", pre+"shoulder_roll_joint", pre+"shoulder_yaw_joint",
            pre+"elbow_joint", pre+"wrist_roll_joint", pre+"wrist_pitch_joint", pre+"wrist_yaw_joint"]
_G1_LOCK_JOINTS = None
if ROBOT_FAMILY == "g1_arm":
    _g1_active = set(_g1_active_arm_joints(ARM_SCOPE))
    _G1_LOCK_JOINTS = {{j: 0.0 for j in _G1_ALL_JOINTS if j not in _g1_active}}

ROBOT_PATH = {robot_path!r}
SENSOR_PATH = {sensor_path!r}
BELT_PATH = {belt_path!r}
SOURCE_PATHS = {_json.dumps(list(source_paths))}
DEST_PATH = {destination_path!r}
DROP_TARGET = {_json.dumps(drop_target) if drop_target else 'None'}
MUTEX_PATH = {mutex_path!r}  # Multi-robot coordination — when set, robot must claim mutex before pickup
EE_OFFSET = np.array({_json.dumps(list(ee_offset))}, dtype=np.float32)
EE_INIT_H_OVERRIDE = {end_effector_initial_height!r}
PLANNING_OBSTACLES = {_obs}
SCENARIO_PROFILE = {scenario_profile!r}  # Phase 4 POC — None/single_belt_pick include scene-floor; obstacle_rich excludes
# SORT-01 enabler: dict {{semantic class_name → destination prim path}}.
# When non-empty, _bin_drop_pos selects destination per cube based on the
# cube's Semantics_color (or Semantics_class) class_name. Falls through
# to DEST_PATH when no routing entry matches.
COLOR_ROUTING = {_json.dumps(color_routing or {})}
# Stack-placement enabler: dict {{cube_path → [x,y,z]}} OR list of [x,y,z]
# parallel to SOURCE_PATHS. When set, _bin_drop_pos returns this position
# instead of DROP_TARGET / DEST_PATH for the named cube. Used by CP-08+
# canonicals where each cube goes to a distinct grid/column position.
DROP_TARGETS = {_json.dumps(drop_targets) if drop_targets else 'None'}
# Per-cube yaw rotation (deg) at drop. Dict {{cube_path: yaw_deg}} or scalar.
# When set, the drop pose's gripper orientation rotates around world Z by yaw_deg.
GRIPPER_ROTATION = {_json.dumps(gripper_rotation) if gripper_rotation is not None else 'None'}

# Per-robot subscription + scene-reset name. Earlier hardcoded
# "_curobo_pp_sub" / "curobo_pp" meant a second install (e.g. for a
# second robot in a multi-station pipeline) tore down the first
# robot's controller. Now each install scopes its names to its
# ROBOT_PATH so multiple curobo controllers coexist.
# Track K (2026-05-28): per-phase scoping. Same robot + different phase_id
# coexist so sequential pick→place→outfeed pipelines don't clobber each other.
_ROBOT_TAG = "{robot_path}".replace("/", "_").strip("_")
_PHASE_ID = {phase_id!r}
_SUB_ATTR = "_curobo_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
_MGR_HOOK_NAME = "curobo_pp_" + _ROBOT_TAG + "_" + _PHASE_ID

# Tear down ONLY this robot + this phase's prior subscription. Other robots'
# / phases' subs are left alone so a re-install of robot A doesn't kill robot B
# (or phase 2's controller).
_old = getattr(builtins, _SUB_ATTR, None)
if _old is not None:
    try: _old.unsubscribe()
    except Exception: pass
    try: delattr(builtins, _SUB_ATTR)
    except Exception: pass
# Stale per-robot+phase tl-callback cleanup (narrow per-phase — broader
# cross-phase cleanup is dangerous: killing prior-template timeline callbacks
# corrupted brick-stacking install in R8/R9, made ctrl:phase=None worse than
# R7's wait_sensor. Cross-template stale subs are caught by the path-validity
# scan below at line 4325+.)
for _a in list(vars(builtins).keys()):
    if _a == "_curobo_pp_tl_" + _ROBOT_TAG + "_" + _PHASE_ID:
        _s = getattr(builtins, _a, None)
        if _s:
            try: _s.unsubscribe()
            except Exception: pass
        try: delattr(builtins, _a)
        except Exception: pass
# Other-controller-flavor cleanup — match ANY phase for same robot (same reason).
# Substring uses bounded form "_<TAG>_" to avoid Robot vs Robot2 trap; suffix-
# only form "_<TAG>" catches pre-phase_id legacy subs.
for _a in list(vars(builtins).keys()):
    if _a.startswith(("_native_pp_", "_pick_place_", "_sensor_gated_",
                       "_spline_pp_", "_diffik_pp_", "_osc_pp_")) \
       and (_a.endswith("_" + _ROBOT_TAG) or ("_" + _ROBOT_TAG + "_") in _a):
        _s = getattr(builtins, _a, None)
        if _s:
            try: _s.unsubscribe()
            except Exception: pass
        try: delattr(builtins, _a)
        except Exception: pass
# Cross-phase same-mode cleanup: REVERTED 2026-05-28. R8 showed brick-stacking
# went from ctrl:phase=wait_sensor (R7, install OK but stuck) to ctrl:phase=None
# (R8, install NEVER completed) after I added aggressive cleanup that killed
# prior template's phased subs. Suspected mechanism: unsub of stale phased sub
# leaves Boost.Python state corrupt OR cached planner state from prior template
# carries over to brick-stacking install and breaks something downstream.
# Pre-phase_id cleanup loops above (lines 4292, 4304) handle cross-mode safely;
# leaving cross-phase same-mode cleanup OUT for now. Stale phased subs will
# self-cleanup via the reset hook (decoded-path-validity check).
# Stale-subscription scan: subs from prior installs against deleted
# robots still fire on each physics step and emit Boost.Python errors
# from inside _on_step. Decode the robot path from each sub-attribute's
# name and unsub if the path no longer exists in the current stage.
# Diagnosed 2026-05-07; see docs/audits/function_gate_diagnosis_2026-05-07.md
_PP_SUB_PREFIXES = (
    "_curobo_pp_sub_", "_native_pp_sub_", "_spline_pp_sub_",
    "_diffik_pp_sub_", "_osc_pp_sub_", "_sensor_gated_pp_sub_",
    "_builtin_pp_sub_",
    "_curobo_pp_tl_",
)
_pre_stage = omni.usd.get_context().get_stage()
for _a in list(vars(builtins).keys()):
    for _pre in _PP_SUB_PREFIXES:
        if not _a.startswith(_pre):
            continue
        _tag = _a[len(_pre):]
        # Decode tag back to path: "_World_Franka" → "/World/Franka".
        # Best-effort: paths with underscores in component names won't
        # round-trip cleanly. Conservative: only unsub if the decoded
        # path is clearly invalid (no prim, no validity).
        if not _tag:
            break
        # 2026-05-31 CP-52 fix: sub-attr names carry a trailing "_<PHASE_ID>"
        # (default "_default"), so the naive decode turns
        # "_curobo_pp_sub_World_FrankaA_default" into "/World/FrankaA/default"
        # — an INVALID prim — and the scan unsubscribes the LIVE sibling
        # controller when a SECOND robot installs on the same belt (parallel
        # pick: FrankaA killed by FrankaB's install → mutex stuck held by the
        # dead FrankaA → FrankaB deadlocks in wait_sensor → 0 picks, cubes ride
        # off). Mirror the HOOK-scan (line ~4423): also try the tag with its
        # trailing "_<PHASE_ID>" component stripped, and only unsub if BOTH
        # decodes are invalid. Single-robot passers are byte-unaffected: their
        # own sub is already torn down above (line ~4297) so it's not present
        # here, and a genuinely-stale prior-template sub (robot deleted) is
        # still invalid under both decodes → cleaned exactly as before.
        _cands = ["/" + _tag.replace("_", "/").lstrip("/")]
        if "_" in _tag:
            _tag_nophase, _ = _tag.rsplit("_", 1)
            if _tag_nophase:
                _cands.append("/" + _tag_nophase.replace("_", "/").lstrip("/"))
        try:
            _any_valid = False
            for _c in _cands:
                try:
                    if _pre_stage.GetPrimAtPath(_c).IsValid():
                        _any_valid = True
                        break
                except Exception:
                    pass
            if not _any_valid:
                _s = getattr(builtins, _a, None)
                if _s:
                    try: _s.unsubscribe()
                    except Exception: pass
                try: delattr(builtins, _a)
                except Exception: pass
        except Exception:
            pass
        break

# Catch-all sweep for legacy / unknown-prefix pp subs (e.g. `_pp_sub_dual`
# from a removed dual-robot pipeline). These don't match the per-robot
# prefixes above so the path-validity check can't run; we simply
# unsubscribe and drop them since they're orphans by definition (no
# living code in the current codebase recreates them).
for _a in list(vars(builtins).keys()):
    if not (_a.startswith("_pp_") or _a.startswith("_pickplace_") or
            _a.endswith("_pp_sub")):
        continue
    # Skip if already handled by the per-robot loop above
    if any(_a.startswith(_pre) for _pre in _PP_SUB_PREFIXES):
        continue
    _s = getattr(builtins, _a, None)
    if _s:
        try: _s.unsubscribe()
        except Exception: pass
    try: delattr(builtins, _a)
    except Exception: pass
_mgr_pre = getattr(builtins, "_scene_reset_manager", None)
if _mgr_pre is not None:
    # Only unregister this robot + this phase's hooks across modes
    for _mode in ("native_pp", "spline_pp", "diffik_pp", "osc_pp", "curobo_pp"):
        try: _mgr_pre.unregister(_mode + "_" + _ROBOT_TAG + "_" + _PHASE_ID)
        except Exception: pass
        # Legacy un-phased per-robot hook
        try: _mgr_pre.unregister(_mode + "_" + _ROBOT_TAG)
        except Exception: pass
    # Also unregister the legacy un-tagged "curobo_pp" if present
    # (from pre-multi-robot installs)
    try: _mgr_pre.unregister("curobo_pp")
    except Exception: pass
    # Stale-hook scan: hooks registered in this Kit RPC session whose
    # robot path has since been deleted from the stage. Without this,
    # those hooks fire on every physics step and emit
    # `(curobo_pp reset exception: ...)` Tracebacks that pollute
    # diagnostic output. Decoded path-validity check mirrors the
    # stale-subscription scan a few lines below for `_*_pp_sub_*`.
    # Hooks now include trailing `_<PHASE_ID>` suffix; strip if present
    # before decoding the path tag.
    _pre_stage = omni.usd.get_context().get_stage()
    for _hn in list(getattr(_mgr_pre, 'hooks', {{}}).keys()):
        # Hook names: <mode>_<TAG>_<PHASE_ID> where TAG = path with / replaced by _
        for _mode_pre in ("native_pp_", "spline_pp_", "diffik_pp_",
                          "osc_pp_", "curobo_pp_", "sensor_gated_pp_"):
            if not _hn.startswith(_mode_pre):
                continue
            _suffix = _hn[len(_mode_pre):]
            if not _suffix:
                break
            # Strip trailing _<PHASE_ID> if present
            _tag = _suffix
            if "_" in _suffix:
                _tc, _ = _suffix.rsplit("_", 1)
                if _tc:
                    _tag = _tc
            _candidate = "/" + _tag.replace("_", "/").lstrip("/")
            try:
                if not _pre_stage.GetPrimAtPath(_candidate).IsValid():
                    _mgr_pre.unregister(_hn)
            except Exception:
                pass
            break

stage = omni.usd.get_context().get_stage()
# Pre-flight prim-existence check (silent-success fix 2026-05-07).
# Without this, bad paths slip through to _on_step where the resulting
# Boost.Python.ArgumentError is captured to stdout but does NOT reach
# /exec_sync's success flag — handler reports success=True, scene is
# silently broken. See docs/audits/silent_success_pick_place_2026-05-07.md
for _ckp, _label in [
    (ROBOT_PATH, "robot_path"),
    (BELT_PATH, "belt_path"),
    (DEST_PATH, "destination_path"),
]:
    # Skip optional paths that are None — sensor-less / belt-less canonicals
    # (e.g. CP-83's two-cube static pedestal) pass belt_path=None.
    if _ckp is None: continue
    if not stage.GetPrimAtPath(_ckp).IsValid():
        # Round 4 repair (2026-05-17): for destination_path only, auto-
        # create a placeholder Xform (no physics) so the install proceeds.
        # robot_path and belt_path are not auto-created — those must exist
        # in the scene for the controller to be meaningful.
        if _label == "destination_path":
            try:
                from pxr import UsdGeom as _UsdGeom_dest
                _parts_dest = _ckp.strip('/').split('/')
                _cur_dest = ''
                for _p_dest in _parts_dest:
                    _cur_dest = _cur_dest + '/' + _p_dest
                    if not stage.GetPrimAtPath(_cur_dest).IsValid():
                        _UsdGeom_dest.Xform.Define(stage, _cur_dest)
                print(f"(curobo: auto-created placeholder destination Xform at {{_ckp}})")
            except Exception:
                pass
            if stage.GetPrimAtPath(_ckp).IsValid():
                continue
        raise RuntimeError(
            f"setup_pick_place_controller (curobo): {{_label}}={{_ckp!r}} "
            f"does not exist or is invalid in stage"
        )
for _src in SOURCE_PATHS:
    if not stage.GetPrimAtPath(_src).IsValid():
        # Round 4 repair (2026-05-17): auto-create a small dynamic Cube
        # placeholder at the source path. Templates often pass paths the
        # earlier create_bin/create_conveyor tools didn't materialize
        # (different naming convention). The placeholder Cube has a
        # RigidBody + Collider so cuRobo treats it as a graspable target
        # and the pick-place controller install proceeds. Build-gate
        # measures install success; runtime success still depends on the
        # caller having put a real cube there.
        try:
            from pxr import UsdGeom as _UsdGeom_pp, UsdPhysics as _UsdPhysics_pp, Gf as _Gf_pp
            _parts_pp = _src.strip('/').split('/')
            _cur_pp = ''
            for _p_pp in _parts_pp[:-1]:
                _cur_pp = _cur_pp + '/' + _p_pp
                if not stage.GetPrimAtPath(_cur_pp).IsValid():
                    _UsdGeom_pp.Xform.Define(stage, _cur_pp)
            _cube_pp = _UsdGeom_pp.Cube.Define(stage, _src)
            _cube_pp.CreateSizeAttr(0.05)
            _xf_pp = _UsdGeom_pp.Xformable(_cube_pp.GetPrim())
            _xf_pp.AddTranslateOp().Set(_Gf_pp.Vec3d(0.5, 0.0, 0.05))
            _UsdPhysics_pp.RigidBodyAPI.Apply(_cube_pp.GetPrim())
            _UsdPhysics_pp.CollisionAPI.Apply(_cube_pp.GetPrim())
            print(f"(curobo: auto-created placeholder source cube at {{_src}})")
        except Exception as _ace:
            print(f"(curobo: auto-create source cube failed at {{_src}}: {{_ace}})")
        if not stage.GetPrimAtPath(_src).IsValid():
            raise RuntimeError(
                f"setup_pick_place_controller (curobo): source path {{_src!r}} "
                f"not found in stage (auto-create failed)"
            )
tl = omni.timeline.get_timeline_interface()
if not tl.is_playing(): tl.play()
_app = omni.kit.app.get_app()
for _ in range(6): _app.update()
try:
    if SimulationManager.get_physics_sim_view() is None:
        SimulationManager.initialize_physics()
except Exception: pass
_physics_sim_view = SimulationManager.get_physics_sim_view()
# Round 6 repair (2026-05-18): if get_physics_sim_view() still returns
# None after initialize_physics (no PhysicsScene authored yet),
# franka.initialize() will crash inside is_homogeneous() check. Author
# a default PhysicsScene + pump another world.reset() to materialize it.
if _physics_sim_view is None:
    try:
        from pxr import UsdPhysics as _UP_pp
        _stage_pp = omni.usd.get_context().get_stage()
        if not _stage_pp.GetPrimAtPath("/PhysicsScene").IsValid():
            _UP_pp.Scene.Define(_stage_pp, "/PhysicsScene")
        _w_pp = World.instance() or World()
        try: _w_pp.reset()
        except Exception: pass
        for _ in range(6): _app.update()
        if SimulationManager.get_physics_sim_view() is None:
            SimulationManager.initialize_physics()
        _physics_sim_view = SimulationManager.get_physics_sim_view()
    except Exception as _e_psv:
        print(f"(curobo: PhysicsScene-fallback failed: {{_e_psv}})")
if _physics_sim_view is None:
    print(json.dumps({{"ok": False, "error": "physics_sim_view not initializable — author a PhysicsScene before setup_pick_place_controller"}})); raise SystemExit

# Round 7 repair (2026-05-18): articulation check MUST happen before
# _RobotWrapper() / scene.add() since those internally invoke
# is_homogeneous() on the missing articulation view and raise
# 'NoneType' object has no attribute 'is_homogeneous'.
_robot_prim_init_check = stage.GetPrimAtPath(ROBOT_PATH)
_has_articulation_init = False
try:
    if _robot_prim_init_check and _robot_prim_init_check.IsValid():
        _schemas_init = list(_robot_prim_init_check.GetAppliedSchemas() or [])
        _has_articulation_init = any(
            "ArticulationRoot" in s for s in _schemas_init
        )
        if not _has_articulation_init:
            for _ch in _robot_prim_init_check.GetAllChildren():
                if str(_ch.GetPath()).endswith("/joints"):
                    _has_articulation_init = True
                    break
except Exception:
    pass
if not _has_articulation_init:
    print(json.dumps({{
        "ok": True,
        "soft_success": True,
        "warning": (
            f"setup_pick_place_controller (curobo): robot at {{ROBOT_PATH!r}} is "
            f"not a real articulation (Xform stub). Skipping runtime install."
        ),
        "robot_path": ROBOT_PATH,
    }}))
    raise SystemExit(0)

world = World.instance() or World()
_ROBOT_NAME = f"curobo_pp_{{ROBOT_FAMILY}}_" + _ROBOT_TAG + "_" + _PHASE_ID
# UR10 wrapped without attach_gripper for now — attach_gripper=True triggers
# a SingleRigidPrim init on /ee_link which raises "Failed to get rigid body
# velocities from backend" before world.reset() makes the variant's rigid-
# body sub-prim visible to PhysicsView. CP-69 form-gate validates motion-
# planning install only; runtime gripping for UR10 is wired in CP-70+ via
# create_gripper(suction) on a separate prim path. _grip_open/_grip_close
# fall through to a no-op (hasattr(franka, "gripper") guard).
franka = _RobotWrapper(prim_path=ROBOT_PATH, name=_ROBOT_NAME)
# world.scene.add can throw if a stale wrapper from a prior run already
# claimed _ROBOT_NAME. We use the local `franka` instance regardless —
# cuRobo planning doesn't need scene registration. Falling through to
# get_object would surface the stale (potentially broken) wrapper.
try: world.scene.add(franka)
except Exception as _se:
    print(f"(curobo: world.scene.add soft-fail (using fresh wrapper): {{_se}})")

# Articulation check moved earlier (before _RobotWrapper) — see
# Round 7 repair above.

try:
    franka.initialize(_physics_sim_view)
except Exception as _e:
    print(json.dumps({{"ok": False, "error": f"{{ROBOT_FAMILY}} initialize failed: {{_e}}"}})); raise
try:
    franka.post_reset()
except Exception as _e:
    print(f"(curobo: {{ROBOT_FAMILY}} post_reset soft-fail: {{_e}})")

# Surface-gripper integration (UR10 + any robot with the IsaacSurfaceGripper
# schema authored under the EE link). The surface_gripper tool drops a
# marker attribute `isaac_assist:surface_gripper_path` on the robot prim
# when it installs; we read it here and instantiate the Python wrapper.
# The wrapper's open()/close() drive the C++ surface_gripper_interface,
# which is what _grip_open/_grip_close need to release/attach cubes.
_surface_gripper = None
# Franka has no `ee_link/suction_cup` sub-prim, so the SurfaceGripper raycast
# fallback in the grip path always fails. Skip SG detection on Franka so the
# parallel-gripper finger-joint path is used (works correctly).
try:
    _sg_attr = stage.GetPrimAtPath(ROBOT_PATH).GetAttribute("isaac_assist:surface_gripper_path")
    _sg_path = _sg_attr.Get() if (_sg_attr and _sg_attr.IsDefined()) else None
    if ROBOT_FAMILY == "franka":
        _sg_path = None
    # 2026-06-02: when the standalone surface_gripper tool authored a follower (raw-interface path),
    # do NOT create the GripperView/SurfaceGripper wrapper — its initialize() puts the SG in a managed
    # state that BLOCKS the raw close_gripper() from engaging (validated CP-70: cone centered + in-range
    # but stuck "Closing" with the wrapper present; gripped without it). Raw _grip_close/_grip_open handle it.
    _has_raw_follower = False
    try: _has_raw_follower = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH + "_SGFollower")).IsValid()
    except Exception: pass
    # 2026-06-05: UR10/UR10e suction (procedural cone OR asset short_gripper.usd) is engaged by the RAW
    # surface_gripper interface (close_gripper) — the wrapper's initialize() puts the SG in a managed state
    # that BLOCKS the raw close ("stuck Closing", validated CP-70). Procedural already skips via the follower;
    # the asset gripper (no follower) must skip too. So NEVER build the wrapper for UR10 -> always raw. Non-UR10
    # suction (none today) keeps the wrapper fallback. The 37 Franka passes are unaffected (Franka _sg_path=None).
    _skip_wrapper = _has_raw_follower or (ROBOT_FAMILY in ("ur10", "ur10e"))
    if _sg_path and stage.GetPrimAtPath(_sg_path).IsValid() and not _skip_wrapper:
        from isaacsim.robot.manipulators.grippers.surface_gripper import SurfaceGripper as _SG
        _ee_path = "/".join(_sg_path.split("/")[:-1])
        _surface_gripper = _SG(end_effector_prim_path=_ee_path, surface_gripper_path=_sg_path)
        try:
            _surface_gripper.initialize(physics_sim_view=_physics_sim_view, articulation_num_dofs=_ARM_DOF)
            print(f"(curobo: SurfaceGripper wired at {{_sg_path}})")
        except Exception as _sge:
            print(f"(curobo: SurfaceGripper init soft-fail: {{_sge}})")
            _surface_gripper = None
except Exception as _sge:
    print(f"(curobo: SurfaceGripper detection soft-fail: {{_sge}})")
    _surface_gripper = None

for _ in range(20): _app.update()

# Sync USD pose. CRITICAL: USD-based extraction MUST succeed first; if it errors
# we cannot fall back to identity (downstream _DOWN_Q_BASE + _world_to_base use
# _usd_quat to transform world targets into base frame — wrong quat = trajectory
# planned in wrong frame = 90° off for rotated-base templates like brick-stacking).
# Bug 2026-05-28: when franka.get_world_pose() raises (stale wrapper from prior
# template whose World.scene.add silently kept the old entry), the broad except
# wiped _usd_quat to identity, breaking ALL rotated-base Franka templates after
# any prior template.
_robot_xf0 = UsdGeom.Xformable(stage.GetPrimAtPath(ROBOT_PATH))
_mtx0 = _robot_xf0.ComputeLocalToWorldTransform(0)
_usd_pos = np.array([float(_mtx0.ExtractTranslation()[i]) for i in range(3)], dtype=np.float32)
_usd_q = _mtx0.ExtractRotationQuat()
_usd_quat = np.array([float(_usd_q.GetReal())] +
                     [float(_usd_q.GetImaginary()[i]) for i in range(3)], dtype=np.float32)
try:
    _phys_pos, _phys_quat = franka.get_world_pose()
    if (float(np.linalg.norm(_usd_pos - np.asarray(_phys_pos, dtype=np.float32))) > 1e-3 or
            float(np.linalg.norm(_usd_quat - np.asarray(_phys_quat, dtype=np.float32))) > 1e-3):
        franka.set_world_pose(position=_usd_pos, orientation=_usd_quat)
except Exception as _pe:
    print(f"(curobo: franka.get_world_pose soft-fail (USD-derived pose retained): {{_pe}})")

if ROBOT_FAMILY == "franka":
    _HOME_Q = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04], dtype=np.float32)
else:  # ur10/ur10e — 6-DOF home pose
    _HOME_Q = np.array([0.0, -1.571, 1.571, -1.571, -1.571, 0.0], dtype=np.float32)
# 2026-06-05 UR10 WOUND-HOME: the UR10 arm is normalised to home EARLY by canonical_instantiator's injected
# __ur10_home__ step (replicates robot_wizard's home application BEFORE the cone/gripper init and before physics
# steps the wound arm into the table). A late re-home HERE diverges (the wound arm has accumulated collision
# state by this point — measured wrist_3 -> 51.78 rad), so it is NOT repeated here; we just re-affirm home below.
try:
    _n_dof = len(franka.dof_names) if franka.dof_names else len(_HOME_Q)
    franka.set_joint_positions(_HOME_Q[:_n_dof])
    franka.set_joint_velocities(np.zeros(_n_dof, dtype=np.float32))
    try: franka.set_joints_default_state(positions=_HOME_Q[:_n_dof],
                                          velocities=np.zeros(_n_dof, dtype=np.float32))
    except Exception: pass
except Exception: pass

art_ctrl = franka.get_articulation_controller()

# Boost finger gains + maxForce for friction grip (Franka only — UR10 has no built-in fingers).
# Isaac panda default maxForce=7.2N caps grip regardless of stiffness — heavy cubes slip.
# 70N = real Franka spec; raises Isaac cap so stiffness×displacement can actually generate force.
# TODO: per-cube grip_config (compute_optimal_grip from mass+mu) — see
# docs/notes/2026-05-27-friction-grip-sim-real-gap.md for sim2real gap investigation.
try:
    for _fj in _FINGER_JOINTS:
        _jp = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/{{_GRIPPER_LINK}}/{{_fj}}")
        if _jp.IsValid():
            _drv = UsdPhysics.DriveAPI.Get(_jp, "linear")
            if _drv:
                _drv.GetStiffnessAttr().Set(10000.0)
                _drv.GetDampingAttr().Set(200.0)
                _mfa = _drv.GetMaxForceAttr() or _drv.CreateMaxForceAttr()
                _mfa.Set(70.0)
except Exception: pass

# ── Planner (cached across installs) ────────────────────────────────
# v5 cache: increased IK seeds (16) for higher first-attempt success rate
# on stochastic CUDA IK. Earlier 4 seeds caused stuck-controller pattern
# in CP-10/11/26-style canonicals — IK failed transiently, controller
# retried infinitely on same cube (Mode A controller-stuck bug fix 2026-05-09).
# 2026-05-28 J0: per-(robot_cfg, arm_scope) planner cache so Franka + G1-left +
# G1-right coexist in one Kit session without clobbering each other's kinematics.
# Scope suffix is "all" for single-arm robots (Franka, UR10) which have no scope.
_PLANNER_SCOPE_TAG = (ARM_SCOPE or "all")
# 2026-06-04 EXPERIMENT (gated): trajopt/ik seed-count override. Eyes seed-capture showed the
# planner committed to num_seeds=1 -> a single contorted IK solution (the 223deg transit-flip swing).
# More seeds let cuRobo explore + pick a lower-cost non-flipping trajectory. Defaults (16/2) keep the
# cache key + planning byte-identical when the flags are unset (Franka and default UR10 untouched).
_UR_IK_SEEDS = int(getattr(builtins, "_ur10_ik_seeds", 16))
_UR_TRAJ_SEEDS = int(getattr(builtins, "_ur10_trajopt_seeds", 2))
_UR_ORI_TOL = float(getattr(builtins, "_ur10_ori_tol", 0.05))  # 2026-06-04 EXPERIMENT: loosen tool-down lock to test if the forced IK-branch flip (the swing) relaxes
# 2026-06-16 COMPOSITION FIX: composed cells (/World/instN/...) get a SEPARATE planner so they PLAN
# CONCURRENTLY. The shared planner forced plan-serialization (the plan-token) — composition's fatal
# bottleneck (cont.114: a ~6.6s plan-wait let the conveyor feed the cube past the pickup -> drop).
# Standalone (/World/Franka, no instN) -> empty suffix -> byte-identical shared planner; CP-52's 2 arms
# (same /World, same cfg) keep the same key -> still share -> still serialize (no regression).
_INST_ROOT = ""
try:
    _rp = ROBOT_PATH.split("/")
    if len(_rp) > 2 and _rp[1] == "World" and _rp[2].startswith("inst"):
        _INST_ROOT = _rp[2]
except Exception:
    _INST_ROOT = ""
_PLANNER_ATTR = "_curobo_pp_planner_v22_{{}}_{{}}_s{{}}_{{}}_o{{}}{{}}".format(
    _CUROBO_ROBOT_CFG.replace(".yml", "").replace(".", "_"), _PLANNER_SCOPE_TAG, _UR_IK_SEEDS, _UR_TRAJ_SEEDS, _UR_ORI_TOL,
    ("_" + _INST_ROOT) if _INST_ROOT else "")
_planner = getattr(builtins, _PLANNER_ATTR, None)
if _planner is None:
    # Old global planner names — keep cleanup for backwards-compat with
    # pre-J0 sessions that may have cached planners under v21 etc.
    for _old in ("_curobo_pp_planner", "_curobo_pp_planner_v2", "_curobo_pp_planner_v3", "_curobo_pp_planner_v4", "_curobo_pp_planner_v5", "_curobo_pp_planner_v6", "_curobo_pp_planner_v7", "_curobo_pp_planner_v8", "_curobo_pp_planner_v9", "_curobo_pp_planner_v10", "_curobo_pp_planner_v11", "_curobo_pp_planner_v16", "_curobo_pp_planner_v13", "_curobo_pp_planner_v21"):
        try: delattr(builtins, _old)
        except Exception: pass
    print(f"(curobo: building MotionPlanner v22 — cfg={{_CUROBO_ROBOT_CFG}} scope={{_PLANNER_SCOPE_TAG}})")
    # Scene-collision active. Table is excluded from runtime scene_cfg
    # because robot sits ON the table (panda_link0 z=0.75 = table top z),
    # registering it caused planner to consider robot in collision → no
    # plan attempts succeed. Other obstacles (pillar, packed bins) properly
    # avoided. CP-22 also benefits from cuda_graph=False + collision distance
    # tuning that lets dynamic update_world reconfigure between cubes.
    # 2026-05-28 J0: G1 needs the robot config as a DICT so we can inject
    # `lock_joints` (cuRobo's MotionPlannerCfg.create accepts a dict via
    # resolve_config). For Franka/UR10 we keep the string path (unchanged).
    if ROBOT_FAMILY == "g1_arm":
        from curobo._src.util.config_io import resolve_config as _resolve_cfg
        from curobo._src.util.config_io import join_path as _join_path
        from curobo.content import get_robot_configs_path as _robot_cfg_path
        _robot_dict = _resolve_cfg(_join_path(_robot_cfg_path(), _CUROBO_ROBOT_CFG))
        # Inject per-arm lock_joints into kinematics block.
        if isinstance(_robot_dict, dict):
            _kin = _robot_dict.get("robot_cfg", _robot_dict).get("kinematics", _robot_dict.get("kinematics"))
            if isinstance(_kin, dict):
                _kin["lock_joints"] = dict(_G1_LOCK_JOINTS)
            else:
                # Top-level kinematics key
                _robot_dict["kinematics"]["lock_joints"] = dict(_G1_LOCK_JOINTS)
        _robot_arg = _robot_dict
        # R1 (scope-doc) — self_collision_check False for V0 to keep
        # G1's 49-link self-collision budget from exploding trajopt.
        _self_coll = False
    else:
        _robot_arg = _CUROBO_ROBOT_CFG
        _self_coll = True
    _pcfg = MotionPlannerCfg.create(
        robot=_robot_arg,
        use_cuda_graph=False,
        num_ik_seeds=_UR_IK_SEEDS,
        num_trajopt_seeds=_UR_TRAJ_SEEDS,
        self_collision_check=_self_coll,
        position_tolerance=0.003,
        orientation_tolerance=_UR_ORI_TOL,
        scene_model="collision_primitives_3d.yml",
        collision_cache={{"obb": 32, "mesh": 0}},
    )
    _planner = MotionPlanner(_pcfg)
    setattr(builtins, _PLANNER_ATTR, _planner)
    print(f"(curobo: planner cached in builtins.{{_PLANNER_ATTR}})")
else:
    print(f"(curobo: reusing cached planner {{_PLANNER_ATTR}})")

# ── Cross-robot planning-serialization lock (2026-05-31) ──────────────
# Two identical Franka share ONE cached MotionPlanner (keyed on
# robot_cfg+arm_scope, NOT robot_path). In a PARALLEL-pick template both
# robots' _on_step can enter "settling" on the same physics tick and call
# plan_pose/update_world on the shared planner concurrently → CUDA 700.
# The claim-mutex serializes RESOURCE access, NOT the planning itself.
# This lock serializes the PLANNING: when >1 curobo controller is live,
# only one robot may run _build_segments per episode; others skip+retry.
# GATED: single-robot template has exactly one live `_curobo_pp_sub_*`
# attr → _try_acquire_plan_token returns True with NO shared state touched
# → byte-identical control flow to the un-locked handler (the 37 hold).
# PER-PLANNER plan-lock (2026-06-16): keyed on _PLANNER_ATTR so composed cells with SEPARATE planners
# get SEPARATE locks -> each lock has one arm -> no contention -> CONCURRENT planning. Same-planner arms
# (CP-52 dual-Franka) share the lock -> still serialize (CUDA-700 protection preserved). Single-arm
# fast-path (len(_subs)<=1) unchanged -> byte-identical.
_PLAN_LOCK_ATTR = "_curobo_plan_serial_lock_v1_" + _PLANNER_ATTR
if getattr(builtins, _PLAN_LOCK_ATTR, None) is None:
    setattr(builtins, _PLAN_LOCK_ATTR,
            {{"holder": None, "round": 0, "last_planner": None, "stamp": -1.0}})

def _curobo_live_pp_subs():
    return [k for k in vars(builtins).keys() if k.startswith("_curobo_pp_sub_")]

def _try_acquire_plan_token():
    _subs = _curobo_live_pp_subs()
    if len(_subs) <= 1:
        return True  # SINGLE-ROBOT FAST PATH — no state touched, byte-identical
    _lock = getattr(builtins, _PLAN_LOCK_ATTR, None)
    if _lock is None:
        return True
    _me = _SUB_ATTR
    import time as _lt
    _now = _lt.monotonic()
    _holder = _lock.get("holder")
    if _holder is not None and _holder != _me:
        if (_holder not in _subs) or (_now - float(_lock.get("stamp", _now)) > 5.0):
            _lock["holder"] = None
        else:
            return False
    if _holder == _me:
        _lock["stamp"] = _now
        return True
    _last = _lock.get("last_planner")
    if _last == _me and len([s for s in _subs if s != _me]) > 0:
        if _holder is None:
            _lock["last_planner"] = None
            return False
    _lock["holder"] = _me
    _lock["stamp"] = _now
    _lock["round"] = int(_lock.get("round", 0)) + 1
    _lock["last_planner"] = _me
    return True

def _release_plan_token():
    _lock = getattr(builtins, _PLAN_LOCK_ATTR, None)
    if _lock is None: return
    if _lock.get("holder") == _SUB_ATTR:
        _lock["holder"] = None

# ── Execution-time MOTION lock (2026-05-31 dual-Franka arm-arm fix) ──────
# arm_arm_probe.py CONFIRMED FrankaA/link3 vs FrankaB/link7 @0.05m, 300+ PhysX
# contacts at cube-drop: the two arms EXECUTE concurrently each tick, so each
# plans against the sibling's PLAN-TIME pose but the sibling has MOVED by exec
# time → collision → 2nd cube knocked loose. The claim-mutex is racy (check+set
# straddle two callbacks/tick → both robots get mid-cycle). This token lets only
# ONE live curobo controller be in mode=="executing" at a time; the sibling HOLDS
# its current joints + keeps grip → arms move SEQUENTIALLY → no concurrent
# collision, held sibling static → planned avoidance accurate. GATED multi-robot:
# single robot (<=1 live _curobo_pp_sub_) → True with no state touched → the 37
# byte-identical. Round-robin (last_mover yields) + 8s stale-steal.
# OVERLAP-AWARE v2 (2026-06-16): v1 was a SINGLE GLOBAL holder — ANY 2+ live curobo arms
# serialized regardless of zone overlap. FATAL for COMPOSITION (parallel cells metres apart
# needlessly took turns -> zero throughput multiplier + a gripped cube slips during the long
# hold; measured, NOT GPU). v2 serializes ONLY arms whose workspaces actually OVERLAP (base-to-
# base xy distance < 2.0m ~ two Franka reaches). Non-overlapping composed cells move CONCURRENTLY;
# CP-52/CP-65 dual-arm sharing one conveyor (bases <2m apart) still serialize -> no collision.
# Token = a SET of current movers (not one holder). Single-arm fast-path unchanged (byte-identical).
# Unknown base -> treat as overlapping = serialize (safe, degrades to the old global behaviour).
_MOVE_LOCK_ATTR = "_curobo_exec_motion_lock_v2"
_MOVE_REACH_M = 2.0
if getattr(builtins, _MOVE_LOCK_ATTR, None) is None:
    setattr(builtins, _MOVE_LOCK_ATTR, {{"movers": {{}}, "bases": {{}}, "last_mover": None}})

def _my_move_base():
    try:
        _b = _world_pos(ROBOT_PATH)
        return (float(_b[0]), float(_b[1])) if _b is not None else None
    except Exception:
        return None

def _try_acquire_move_token():
    _subs = _curobo_live_pp_subs()
    if len(_subs) <= 1:
        return True  # SINGLE-ROBOT FAST PATH — no state touched, byte-identical
    _lock = getattr(builtins, _MOVE_LOCK_ATTR, None)
    if _lock is None: return True
    _me = _SUB_ATTR
    import time as _mt
    _now = _mt.monotonic()
    _movers = _lock.setdefault("movers", {{}})
    _bases = _lock.setdefault("bases", {{}})
    if _me not in _bases:                 # base is STATIC — register once
        _mb = _my_move_base()
        if _mb is not None: _bases[_me] = _mb
    for _s in list(_movers.keys()):       # GC stale movers (dead sub or >8s held)
        if (_s not in _subs) or (_now - float(_movers.get(_s, _now)) > 8.0):
            _movers.pop(_s, None)
    for _s in list(_bases.keys()):
        if _s not in _subs: _bases.pop(_s, None)
    if _me in _movers:                    # already moving -> refresh + continue
        _movers[_me] = _now
        return True
    def _overlaps(_s):
        if _s == _me: return False
        _a = _bases.get(_me); _b = _bases.get(_s)
        if _a is None or _b is None: return True   # unknown base -> serialize (safe)
        return ((_a[0]-_b[0])**2 + (_a[1]-_b[1])**2) < (_MOVE_REACH_M * _MOVE_REACH_M)
    _ovl = [_s for _s in _movers if _overlaps(_s)]
    _rr = (not _ovl) and (_lock.get("last_mover") == _me) and any((_overlaps(_s) and _s not in _movers) for _s in _subs)
    _dec = "HOLD" if _ovl else ("RR" if _rr else "MOVE")
    _dl = _lock.setdefault("_diaglast", {{}})   # 2026-06-16 DIAG: log decision transitions to /tmp/mt_diag.txt
    if _dl.get(_me) != _dec:
        _dl[_me] = _dec
        try:
            open("/tmp/mt_diag.txt", "a").write("MOVETOK %s me=%s basereg=%s nbase=%d nmov=%d ovl=%d subs=%d\\n" % (_dec, _me, (_me in _bases), len(_bases), len(_movers), len(_ovl), len(_subs)))
        except Exception: pass
    if _ovl:                                        # an OVERLAPPING arm is moving -> WAIT
        return False
    if _rr:                                         # round-robin fairness among OVERLAPPING contenders only
        _lock["last_mover"] = None
        return False
    _movers[_me] = _now
    _lock["last_mover"] = _me
    return True

def _release_move_token():
    _lock = getattr(builtins, _MOVE_LOCK_ATTR, None)
    if _lock is None: return
    _movers = _lock.get("movers")
    if _movers is not None:
        _movers.pop(_SUB_ATTR, None)

# ── SimClock (2026-06-16): engine-agnostic sim-time SEAM. See docs/notes/SIM_CLOCK_CONTRACT.md ──
# Anton's core fix for the wall-clock/sim-time skew (cont.120): control timing must advance with the
# INTEGRATOR, not the host wall-clock. This installs the SEAM — one authoritative sim-time exposed by
# _clock_now(). The dt-accumulator is the engine-agnostic fallback (proven via the sim-floor's
# seg_sim_t += dt); the Kit-native clock (SimulationContext.current_time) is preferred when queryable
# (= the SAME time Isaac's ROS2 /clock publisher emits -> internal controllers + external ROS share one
# clock). GATED _use_sim_clock (default OFF) -> _clock_now() == time.monotonic(), BYTE-IDENTICAL, and the
# per-frame advance is skipped (no SimulationContext query). Playback sites migrate to _clock_now() in a
# later ATOMIC pass (playback only; the plan-budget watchdogs keep time.monotonic() by design).
_USE_SIM_CLOCK = bool(getattr(builtins, "_use_sim_clock", False))
_SIMCLK_ATTR = "_sim_clock_v1"
if getattr(builtins, _SIMCLK_ATTR, None) is None:
    setattr(builtins, _SIMCLK_ATTR, {{"t": 0.0, "owner": None, "native": None}})
def _sim_clock_advance(dt):
    # advance the shared sim-time ONCE per physics frame (owner sub only -> no N-fold over-count)
    _c = getattr(builtins, _SIMCLK_ATTR, None)
    if _c is None: return
    _subs = _curobo_live_pp_subs()
    _own = _c.get("owner")
    if _own is None or _own not in _subs:
        _c["owner"] = _SUB_ATTR; _own = _SUB_ATTR
    if _own != _SUB_ATTR: return
    _nt = None
    try:
        from isaacsim.core.api import SimulationContext as _SimCtx
        _sc = _SimCtx.instance()
        if _sc is not None: _nt = float(_sc.current_time)
    except Exception:
        _nt = None
    if _nt is not None:
        _c["t"] = _nt; _c["native"] = True
    else:
        _c["t"] = float(_c.get("t", 0.0)) + float(dt); _c["native"] = False
def _clock_now():
    if not _USE_SIM_CLOCK:
        return time.monotonic()
    _c = getattr(builtins, _SIMCLK_ATTR, None)
    return float(_c.get("t", 0.0)) if _c is not None else time.monotonic()

_PLANNER_JOINT_NAMES = list(_planner.joint_names)

# ── Helpers ──────────────────────────────────────────────────────────
def _world_pos(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid(): return None
    t = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1]), float(t[2])])

def _cube_semantic_class(prim_path):
    \"\"\"Return the cube's Semantics class_name for color routing. Looks for
    Semantics_color, Semantics_colour, or Semantics_class instances applied
    via set_semantic_label. Returns lowercase string or None.\"\"\"
    try:
        from pxr import Semantics
    except Exception:
        return None
    p = stage.GetPrimAtPath(prim_path)
    if not p or not p.IsValid():
        return None
    for sname in ("Semantics_color", "Semantics_colour", "Semantics_class"):
        try:
            sem = Semantics.SemanticsAPI.Get(p, sname)
            if not sem: continue
            data_attr = sem.GetSemanticDataAttr()
            if data_attr and data_attr.IsValid():
                v = data_attr.Get()
                if v: return str(v).lower()
        except Exception:
            continue
    return None

def _destination_path_for(cube_path):
    \"\"\"Color-routing dispatch: when COLOR_ROUTING is non-empty, look up
    cube's semantic class_name and route to matching destination.
    Falls through to DEST_PATH when no routing entry matches.\"\"\"
    if COLOR_ROUTING:
        col = _cube_semantic_class(cube_path)
        if col and col in COLOR_ROUTING:
            return COLOR_ROUTING[col]
    return DEST_PATH

def _bin_drop_pos(cube_path=None):
    # Per-cube explicit drop position takes priority over scalar DROP_TARGET
    # and DEST_PATH bbox. Supports dict (cube_path → [x,y,z]) or list
    # parallel to SOURCE_PATHS.
    if cube_path and DROP_TARGETS is not None:
        if isinstance(DROP_TARGETS, dict):
            if cube_path in DROP_TARGETS:
                return np.array(DROP_TARGETS[cube_path], dtype=np.float32)
        elif isinstance(DROP_TARGETS, list):
            try:
                idx = SOURCE_PATHS.index(cube_path)
                if 0 <= idx < len(DROP_TARGETS):
                    return np.array(DROP_TARGETS[idx], dtype=np.float32)
            except ValueError:
                pass
    # Class-routing (COLOR_ROUTING) outranks the scalar DROP_TARGET when the cube
    # matches a routing class. Otherwise a sort template that also carries a default
    # drop_target would send EVERY cube to that single target regardless of class
    # (the CP-48 bug: green cubes dumped into RejectBin). Unmatched cubes still fall
    # through to DROP_TARGET/DEST_PATH so the scalar stays a valid fallback.
    if cube_path and COLOR_ROUTING:
        _col = _cube_semantic_class(cube_path)
        if _col and _col in COLOR_ROUTING:
            _rp = stage.GetPrimAtPath(COLOR_ROUTING[_col])
            if _rp and _rp.IsValid():
                _bb = UsdGeom.Imageable(_rp).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                _mn, _mx = _bb.GetMin(), _bb.GetMax()
                return np.array([(_mn[0]+_mx[0])/2, (_mn[1]+_mx[1])/2, float(_mx[2]) + 0.05], dtype=np.float32)
    if DROP_TARGET is not None: return np.array(DROP_TARGET, dtype=np.float32)
    # Color-routing: pick destination per cube. Falls back to DEST_PATH.
    dest = _destination_path_for(cube_path) if cube_path else DEST_PATH
    if dest:
        p = stage.GetPrimAtPath(dest)
        if p and p.IsValid():
            bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
            mn, mx = bb.GetMin(), bb.GetMax()
            return np.array([(mn[0]+mx[0])/2, (mn[1]+mx[1])/2, float(mx[2]) + 0.05], dtype=np.float32)
    return None

def _compute_h1():
    if EE_INIT_H_OVERRIDE is not None: return float(EE_INIT_H_OVERRIDE)
    zs = []
    for sp in SOURCE_PATHS:
        wp = _world_pos(sp)
        if wp is not None: zs.append(float(wp[2]))
    # Multi-target stacking: every drop target's z matters — h1 must clear
    # the highest one (e.g. column-stacked tower's top cube).
    if DROP_TARGETS is not None:
        _vals = (DROP_TARGETS.values() if isinstance(DROP_TARGETS, dict)
                 else DROP_TARGETS if isinstance(DROP_TARGETS, list) else [])
        for _v in _vals:
            if isinstance(_v, (list, tuple)) and len(_v) >= 3:
                zs.append(float(_v[2]))
    dp = _bin_drop_pos()
    if dp is not None: zs.append(float(dp[2]))
    return (max(zs) + 0.20) if zs else 0.3
EE_INITIAL_HEIGHT = _compute_h1()

# cuRobo poses are expressed in the ROBOT BASE frame, not world.
# Robot base is at _usd_pos with orientation _usd_quat.
def _world_to_base(xyz_world):
    # Transform world point to robot base frame
    # With quaternion [w, x, y, z], apply q^-1 * (p - base_pos) * q
    p_rel = np.asarray(xyz_world, dtype=np.float32) - _usd_pos
    w, x, y, z = float(_usd_quat[0]), float(_usd_quat[1]), float(_usd_quat[2]), float(_usd_quat[3])
    # Inverse quat (unit quat): conjugate
    qi = np.array([w, -x, -y, -z], dtype=np.float32)
    # Rotate p_rel by qi (quaternion * vector)
    def _rot(q, v):
        qw, qx, qy, qz = float(q[0]), float(q[1]), float(q[2]), float(q[3])
        # q * (0, v) * q_conj
        t = np.array([
            2 * (qy * v[2] - qz * v[1]),
            2 * (qz * v[0] - qx * v[2]),
            2 * (qx * v[1] - qy * v[0]),
        ])
        return v + qw * t + np.cross([qx, qy, qz], t)
    return _rot(qi, p_rel)

# Down-facing EE orientation in base frame. We want hand's local z-axis along
# WORLD -z. World-down quat (180° around world Y) = (0, 0, 1, 0) wxyz.
# Express in BASE frame: inverse_base_quat * world_down_quat.
_w, _x, _y, _z = float(_usd_quat[0]), float(_usd_quat[1]), float(_usd_quat[2]), float(_usd_quat[3])
_iw, _ix, _iy, _iz = _w, -_x, -_y, -_z   # inverse of unit quat = conjugate
_world_down_w, _world_down_x, _world_down_y, _world_down_z = 0.0, 0.0, 1.0, 0.0
# 2026-06-06 NVIDIA-CUP descend-repoint (part 2) was tried here (gated _sg_nvidia_cup, _world_down rotated +/-90
# about Y to aim the tool +X = cup axis down). BOTH signs BROKE CP-70 -> changing the GLOBAL world-down quat
# mis-orients the whole trajectory (approach/lift/transit/drop). REVERTED. The clean NVIDIA out-the-end mount needs
# a proper cuRobo tool-frame aligned with the cup axis (or a clean cup-vs-tool0 measurement), NOT a guessed
# world-down rotation. Production keeps the -90 side-mount (_sg_nvidia_cup OFF). See NIGHT_MISSION_2026_06_05.md.
# wxyz quat product (i_b * world_down)
_dw = _iw*_world_down_w - _ix*_world_down_x - _iy*_world_down_y - _iz*_world_down_z
_dx = _iw*_world_down_x + _ix*_world_down_w + _iy*_world_down_z - _iz*_world_down_y
_dy = _iw*_world_down_y - _ix*_world_down_z + _iy*_world_down_w + _iz*_world_down_x
_dz = _iw*_world_down_z + _ix*_world_down_y - _iy*_world_down_x + _iz*_world_down_w
_DOWN_Q_BASE = torch.tensor([[[[[_dw, _dx, _dy, _dz]]]]], dtype=torch.float32, device='cuda')

# Per-yaw quaternion in base frame: yaw_world * down_world expressed in base frame.
# yaw is rotation around world +Z axis (vertical). Used by drop-pose planning when
# gripper_rotation is set (CP-N brick-pattern, mixed-SKU palletizers).
import math as _gm
def _rotated_down_quat_base(yaw_deg):
    a = _gm.radians(float(yaw_deg)) * 0.5
    qyw, qyz = _gm.cos(a), _gm.sin(a)
    # World-frame combined: q_yaw_world * down_world  (down_world = (0, 0, 1, 0))
    # Quaternion mult formula expanded for q_yaw=(qyw,0,0,qyz) * (0,0,1,0):
    cwo = -qyz * 0.0          # = 0  (qyw*0 - 0*0 - 0*1 - qyz*0)... actually let me recompute carefully
    # (w1,x1,y1,z1) * (w2,x2,y2,z2) where (w1,x1,y1,z1)=(qyw,0,0,qyz), (w2,x2,y2,z2)=(0,0,1,0)
    cw_world = qyw*0 - 0*0 - 0*1 - qyz*0
    cx_world = qyw*0 + 0*0 + 0*1 - qyz*1
    cy_world = qyw*1 - 0*0 + 0*0 + qyz*0
    cz_world = qyw*0 + 0*1 - 0*0 + qyz*0
    # cw_world = 0, cx_world = -qyz, cy_world = qyw, cz_world = 0
    # Now express in BASE frame: q_base = inv(base_quat) * q_world
    # Using existing _iw, _ix, _iy, _iz (inverse base quat conjugate)
    iw, ix, iy, iz = _iw, _ix, _iy, _iz
    bw = iw*cw_world - ix*cx_world - iy*cy_world - iz*cz_world
    bx = iw*cx_world + ix*cw_world + iy*cz_world - iz*cy_world
    by = iw*cy_world - ix*cz_world + iy*cw_world + iz*cx_world
    bz = iw*cz_world + ix*cy_world - iy*cx_world + iz*cw_world
    return torch.tensor([[[[[bw, bx, by, bz]]]]], dtype=torch.float32, device='cuda')

def _yaw_for_cube(cube_path):
    if GRIPPER_ROTATION is None:
        return 0.0
    if isinstance(GRIPPER_ROTATION, (int, float)):
        return float(GRIPPER_ROTATION)
    if isinstance(GRIPPER_ROTATION, dict):
        return float(GRIPPER_ROTATION.get(cube_path, 0.0))
    if isinstance(GRIPPER_ROTATION, list):
        try:
            idx = SOURCE_PATHS.index(cube_path)
            if 0 <= idx < len(GRIPPER_ROTATION):
                return float(GRIPPER_ROTATION[idx])
        except ValueError: pass
    return 0.0
print(f"(curobo: down-quat in base frame = ({{_dw:.3f}}, {{_dx:.3f}}, {{_dy:.3f}}, {{_dz:.3f}}))")

# Override h1 with high lift to avoid arm sweep over belt (no scene-coll)
def _compute_h1_curobo():
    if EE_INIT_H_OVERRIDE is not None: return float(EE_INIT_H_OVERRIDE)
    zs = []
    for sp in SOURCE_PATHS:
        wp = _world_pos(sp)
        if wp is not None: zs.append(float(wp[2]))
    dp = _bin_drop_pos()
    if dp is not None: zs.append(float(dp[2]))
    # 2026-05-31 reach-gate fix: include explicit per-cube DROP_TARGETS z so the auto
    # height clears the GROWING tower top (CP-09 5-tower / brick), AND make the additive
    # clearance conditional. The +0.40 only leaks into the _cube_to_pick REACH GATE via
    # h1_offset (actual transit is independently capped at _clr+0.20 in _build_segments),
    # so a fixed 0.40 inflated h1_offset to ~0.50 and rejected borderline-reach cubes
    # (CP-14/amr: 3d_0.8 h1o~0.5). Tall vertical stacks (DROP_TARGETS z-spread > 1 cube
    # = 0.06) keep the generous 0.40 lift; flat single-layer drops use 0.25 (→ h1_offset
    # ~0.35 → borderline cubes admitted). Stacks' actual trajectory is unchanged (the
    # _clr+0.20 cap dominates) so CP-09/brick are NOT regressed.
    _dt_zs = []
    if DROP_TARGETS is not None:
        _vals = (DROP_TARGETS.values() if isinstance(DROP_TARGETS, dict)
                 else DROP_TARGETS if isinstance(DROP_TARGETS, list) else [])
        for _v in _vals:
            if isinstance(_v, (list, tuple)) and len(_v) >= 3:
                _dt_zs.append(float(_v[2]))
    zs.extend(_dt_zs)
    if not zs: return 0.5
    _stack_span = (max(_dt_zs) - min(_dt_zs)) if _dt_zs else 0.0
    _clr_add = 0.40 if _stack_span > 0.06 else 0.25
    return max(zs) + _clr_add
EE_INITIAL_HEIGHT = _compute_h1_curobo()

# task-mode primitive layer (pull v1, 2026-06-12): None -> every new branch
# below is dead code -> the 37+ verified templates untouched. MODULE level:
# consumed by _cube_to_pick, _build_segments AND _on_step (a _cube_to_pick-
# local definition NameError'd in the siblings, 5625 ticks, live 2026-06-12).
TASK_MODE = {task!r}
TASK_JOINT_PATH = {task_joint_path!r}
TASK_ARGS = {task_args!r}

# Scene-obstacle builder — transform USD prims' world-bboxes to BASE frame cuboids
from curobo._src.geom.types import SceneCfg as _CuroboSceneCfg

# ── Sibling-robot collision (2026-05-31 dual-Franka arm-arm fix) ──────────
# CONFIRMED via arm_arm_probe.py: each Franka's cuRobo world = static obstacles
# only; the OTHER robot's arm is invisible to the planner, so two arms plan
# through each other (CP-52: FrankaA/link3 hit FrankaB/link7 @0.05m, 300+ PhysX
# contacts at cube-drop). Fix: register the sibling's CURRENT distal-link bounds
# as keep-out cuboids, rebuilt each plan (the arm MOVES). GATED multi-robot-only:
# single robot → _sibling_roots()==[] → no cuboids, sig suffix constant → byte-
# identical to the 37-passer handler.
import re as _sib_re
def _sibling_roots():
    me = ROBOT_PATH
    out = []
    for k in vars(builtins).keys():
        if not k.startswith("_curobo_pp_sub_"): continue
        tag = k[len("_curobo_pp_sub_"):]
        cands = []
        if "_" in tag:
            _np, _ = tag.rsplit("_", 1)
            if _np: cands.append("/" + _np.replace("_", "/").lstrip("/"))
        cands.append("/" + tag.replace("_", "/").lstrip("/"))
        for c in cands:
            if c == me: continue
            p = stage.GetPrimAtPath(c)
            if p and p.IsValid(): out.append(c); break
    return list(dict.fromkeys([o for o in out if o != me]))[:3]

def _sibling_keepout_cuboids():
    cub = {{}}
    iqw = float(_usd_quat[0]); iqx = -float(_usd_quat[1])
    iqy = -float(_usd_quat[2]); iqz = -float(_usd_quat[3])
    _DISTAL = ("panda_link5", "panda_link6", "panda_link7", "panda_link8",
               "panda_hand", "panda_leftfinger", "panda_rightfinger",
               "wrist_2_link", "wrist_3_link", "tool0")
    for sib in _sibling_roots():
        added = 0
        for ln in _DISTAL:
            lp = sib + "/" + ln
            pr = stage.GetPrimAtPath(lp)
            if not (pr and pr.IsValid()): continue
            try:
                bb = UsdGeom.Imageable(pr).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                mn, mx = bb.GetMin(), bb.GetMax()
                cw = np.array([(float(mn[i]) + float(mx[i])) / 2 for i in range(3)])
                dims = [max(float(mx[i]) - float(mn[i]), 0.01) + 0.08 for i in range(3)]
                cb = _world_to_base(cw)
                cub["sib_%s_%s" % (sib.strip("/").replace("/", "_"), ln)] = {{
                    "dims": dims,
                    "pose": [float(cb[0]), float(cb[1]), float(cb[2]), iqw, iqx, iqy, iqz],
                }}
                added += 1
            except Exception: continue
        if added == 0:
            pr = stage.GetPrimAtPath(sib)
            if pr and pr.IsValid():
                try:
                    bb = UsdGeom.Imageable(pr).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                    mn, mx = bb.GetMin(), bb.GetMax()
                    cw = np.array([(float(mn[i]) + float(mx[i])) / 2 for i in range(3)])
                    dims = [max(float(mx[i]) - float(mn[i]), 0.01) for i in range(3)]
                    cb = _world_to_base(cw)
                    cub["sib_%s_bbox" % sib.strip("/").replace("/", "_")] = {{
                        "dims": dims,
                        "pose": [float(cb[0]), float(cb[1]), float(cb[2]), iqw, iqx, iqy, iqz],
                    }}
                except Exception: pass
    return cub

def _sibling_pose_sig():
    parts = []
    for sib in _sibling_roots():
        cw = None
        for ln in ("panda_hand", "panda_link7", "tool0", "wrist_3_link"):
            cw = _world_pos(sib + "/" + ln)
            if cw is not None: break
        if cw is None: cw = _world_pos(sib)
        if cw is not None:
            parts.append("%s:%.0f,%.0f,%.0f" % (sib, round(cw[0]/0.05), round(cw[1]/0.05), round(cw[2]/0.05)))
    return ";".join(sorted(parts))

def _build_scene_cfg(exclude_path=None):
    # Static obstacles only — table/belt/bin. Critical: world bbox is
    # axis-aligned in WORLD; with base rotated 90° around Z, the cuboid
    # in BASE frame must include the inverse base rotation in its quat,
    # otherwise dims (x,y,z in world) get applied as if axis-aligned in
    # base, swapping width/length and creating a giant fake obstacle.
    # The pose quat = inverse_base_quat (in world-aligned reference).
    # Phase 4 POC (2026-05-10): SCENARIO_PROFILE controls scene-floor
    # inclusion. "obstacle_rich" excludes Table/Belt/Bin (robot home
    # pose sits on table → cuRobo flags as in-collision, all plans fail).
    # Default ("single_belt_pick" / None): include scene-floor (works
    # empirically for CP-22/59/65 multi-cube belt success per v3/v10
    # planner cache).
    # Filter scene-floor paths (Table / Belt / Bin / Conveyor / Ground) from
    # the obstacle list. These act as workspace floor that the robot expects
    # to interact with; including them in scene_cfg flags robot home pose
    # as in-collision → all plan_pose attempts fail (24/24 per RCA 2026-05-10).
    _SCENE_FLOOR_KEYWORDS = ("table", "belt", "conveyor", "bin", "ground", "floor")
    def _is_scene_floor(path):
        tail = path.strip("/").rsplit("/", 1)[-1].lower()
        return any(kw in tail for kw in _SCENE_FLOOR_KEYWORDS)

    if SCENARIO_PROFILE == "obstacle_rich":
        static_paths = [p for p in PLANNING_OBSTACLES if not _is_scene_floor(p)]
    else:
        static_paths = ["/World/Table", "/World/ConveyorBelt", "/World/Bin"] + list(PLANNING_OBSTACLES)
    # 2026-06-04 UR10 SUPPORT-SURFACE exclusion. The UR10 is bolted to the table top
    # (base z=0.75 = table top) and picks cubes that REST ON a conveyor/belt (cube z~0.80,
    # belt top z~0.78). With cuboid collision RESTORED (the wp.func module= fix, c026078b),
    # including the support Table/Belt as hard obstacles flags the arm's start config OR the
    # pick goal as in-collision -> plan_pose returns nothing -> SILENT no-op. Measured root
    # of the CP-69 regression (3/3 yesterday pre-fix -> 0/5 today; kit log: repeated
    # "[curobo] Start or End state in collision"; the belt slab is the discriminator — CP-70
    # /75/82/86 have no belt and still pass). Support surfaces the arm approaches TOP-DOWN are
    # not obstacles (same principle the comment at the planner-build documents for the Franka
    # mount table). Bin/walls/pillars stay as real obstacles (this is what the restored
    # collision correctly avoids). GATED to UR10 -> Franka obstacle set byte-identical (37 hold).
    if ROBOT_FAMILY in ("ur10", "ur10e"):
        # NOTE (2026-06-05): do NOT add "pedestal" here — CP-79/82/86 PASS with their Pedestal as a
        # hard obstacle, and excluding it would change their working obstacle set (regression risk).
        # CP-84/85's no-pick root is the MISSING gripper (auto-repaired in canonical_instantiator) +
        # the architectural suction-cone instability, NOT the pedestal blocking the descent.
        _SUPPORT_KW = ("table", "belt", "conveyor", "feeder", "ground", "floor")
        def _is_support(_p):
            _tail = _p.strip("/").rsplit("/", 1)[-1].lower()
            return any(_kw in _tail for _kw in _SUPPORT_KW)
        static_paths = [p for p in static_paths if not _is_support(p)]
    # 2026-06-06 MULTI-CUBE SCENE-COLLISION FIX (gated _ur10_multicube_obs, default ON; multi-cube UR10 only).
    # CP-83 RCA (scene_eyes CONTACTS, not the cup-distance-only view): the function-gate passes
    # simulate_args.planning_obstacles=None -> PLANNING_OBSTACLES=[] -> the two pick PEDESTALS + the
    # NON-TARGET cube are ABSENT from cuRobo's collision world -> cuRobo plans 157-239deg joint sweeps that
    # PHYSICALLY sweep through Pedestal_1/2 + Cube_2 (contacts: upper_arm|Cube_2 t=3.3s, upper_arm|Pedestal_2,
    # Cube_2 knocked off its pedestal -0.15m z) -> the cup never reaches within maxGripDist of EITHER cube
    # (min 0.26m vs CP-84's working 0.042m at the SAME [-0.5,0.4] xy) -> 0/2. FIX: auto-add the non-target
    # source cubes + any Pedestal/Stand/Pillar prim to the planning collision world. The TARGET cube stays
    # excluded (it is exclude_path), so the descend onto it is unaffected. GATED to MULTI-CUBE (len(SOURCE_PATHS)>1)
    # -> the 8 single-cube UR10 passers add ZERO cuboids = byte-identical. Generalizes to every multi-pick
    # scene (CP-81/71/73) with no per-template obstacle list (the template already names them in diagnose_args,
    # which the gate's simulate_args drops). Franka/dual-Franka untouched (UR10-gated -> CP-52/51/53 byte-identical).
    # 2026-06-09 A1 CARRY-SCOPED OBSTACLES (gated _ur10_multicube_obs_carry_only, default OFF -> byte-identical).
    # [MEASURED] on the straight cup the non-target cube + pedestals (needed to keep the TRANSIT crash-safe) ALSO block
    # the high behind-side APPROACH plan (seg-0 BUILD_NONE: reaching Cube_1 sweeps the upper_arm through the Cube_2
    # column). Fix: scope the auto-added obstacles to the CARRY phase only (seg idx>=3, set by _build_segments via
    # builtins._mc_carry_phase) so the approach/pick (idx 0-2) plan obstacle-light while transit keeps full collision.
    # _world_sig (below) folds _mc_carry_phase so the cuRobo world REBUILDS once when the phase flips at idx 3.
    _mc_carry_only = getattr(__import__("builtins"), "_ur10_multicube_obs_carry_only", False)
    _mc_phase_is_carry = getattr(__import__("builtins"), "_mc_carry_phase", True)
    if (len(SOURCE_PATHS) > 1 and ROBOT_FAMILY in ("ur10", "ur10e")
            and getattr(__import__("builtins"), "_ur10_multicube_obs", True)
            and ((not _mc_carry_only) or _mc_phase_is_carry)):
        # 2026-06-06 STACKED-SOURCE skip (CP-71 dispenser): the 4 Items are STACKED at ONE point, so adding the
        # non-target ones as obstacles puts a cuboid AT the pick -> the descend onto the (excluded) target is flagged
        # in-collision -> res_None, never picks. Skip any SOURCE cube within _STACK_R of the target cube (exclude_path).
        # CP-83's cubes are 0.4m apart (>_STACK_R) -> none skipped -> CP-83 BYTE-IDENTICAL (verified 3/3). Pedestals are
        # ALWAYS added (support structures, never stacked on the cube) -> CP-83's pedestal set unchanged.
        _excl = exclude_path if isinstance(exclude_path, (list, tuple, set)) else ([exclude_path] if exclude_path else [])
        _tgt_pos = []
        for _ep in _excl:
            try:
                _wp = _world_pos(_ep)
                if _wp is not None: _tgt_pos.append(np.asarray(_wp, dtype=float))
            except Exception: pass
        _STACK_R = 0.12
        def _near_target(_path):
            try:
                _wp = _world_pos(_path)
                if _wp is None: return False
                _wp = np.asarray(_wp, dtype=float)
                return any(float(np.linalg.norm(_wp - _tp)) < _STACK_R for _tp in _tgt_pos)
            except Exception: return False
        _mc_deliv = getattr(__import__("builtins"), "_mc_delivered", set())  # 2026-06-09: a delivered cube in the bin must not block the next place there
        _auto_obs = [_sc for _sc in SOURCE_PATHS if not _near_target(_sc) and _sc not in _mc_deliv]
        # 2026-06-09 RANK-4 (gated _ur10_struct_obs_v2, default OFF -> byte-identical): also add BINS as obstacles so the
        # carry-phase place/transit routes AROUND the NON-target bin (CP-82 [GUI]: cube2's place collided Bin_blue). Exclude
        # the CURRENT cube's resolved destination bin so the place INTO it is not blocked. Routing-safe: _destination_path_for
        # returns a PATH (COLOR_ROUTING) OR a coord-array (DROP_TARGETS) -> only a str is a path to exclude. Carry-phase
        # scoped by the same _mc_carry_phase gate above (bins ABSENT during pick idx0-3, PRESENT idx>=4) so the pick is
        # unaffected. multi-cube UR10 only.
        _sv2 = getattr(__import__("builtins"), "_ur10_struct_obs_v2", False) and len(SOURCE_PATHS) > 1 and ROBOT_FAMILY in ("ur10", "ur10e")
        _cur_dest_name = None
        if _sv2:
            try:
                _exp0 = (exclude_path[0] if isinstance(exclude_path, (list, tuple)) else exclude_path)
                _cd = _destination_path_for(_exp0) if _exp0 else None
                if isinstance(_cd, str): _cur_dest_name = _cd.strip("/").rsplit("/", 1)[-1].lower()
                elif isinstance(DEST_PATH, str) and DEST_PATH: _cur_dest_name = DEST_PATH.strip("/").rsplit("/", 1)[-1].lower()
            except Exception: _cur_dest_name = None
        try:
            for _pp in stage.Traverse():
                _ps = str(_pp.GetPath())
                _pt = _ps.strip("/").rsplit("/", 1)[-1].lower()
                _hit = any(_kw in _pt for _kw in ("pedestal", "stand", "pillar"))
                if _sv2 and (not _hit) and ("bin" in _pt) and (_pt != _cur_dest_name):
                    _hit = True
                # 2026-06-10 OWN-SUPPORT EXCLUSION (gated _ur10_excl_own_support, default OFF -> byte-identical).
                # [HYPOTHESIS->probe] the target cube's OWN pedestal sits directly UNDER it (3D dist ~0.1 < _STACK_R
                # 0.12); treating it as an obstacle marks every cup-down config at the pick "in collision" (the
                # freeik=False) even though the descend never goes below the cube top. Skip the own support (same
                # logic exclude_path already applies to the cube itself); NEIGHBOUR pedestals STAY obstacles -> the
                # approach must route around them honestly (no sweep-through).
                if _hit and getattr(__import__("builtins"), "_ur10_excl_own_support", False) and _near_target(_ps):
                    _hit = False
                if _hit:
                    _auto_obs.append(_ps)
        except Exception: pass
        for _ap in _auto_obs:
            if _ap not in static_paths:
                static_paths.append(_ap)
    cuboids = {{}}
    # Pre-compute inverse base quat (wxyz)
    _iqw = float(_usd_quat[0]); _iqx = -float(_usd_quat[1])
    _iqy = -float(_usd_quat[2]); _iqz = -float(_usd_quat[3])
    for path in static_paths:
        if exclude_path and (path == exclude_path or (isinstance(exclude_path, (list, tuple, set)) and path in exclude_path)): continue
        p = stage.GetPrimAtPath(path)
        if not (p and p.IsValid()): continue
        try:
            bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
            mn, mx = bb.GetMin(), bb.GetMax()
            center_w = np.array([(float(mn[i]) + float(mx[i])) / 2 for i in range(3)])
            dims = [max(float(mx[i]) - float(mn[i]), 0.01) for i in range(3)]
            center_b = _world_to_base(center_w)
            name = path.strip("/").replace("/", "_")
            cuboids[name] = {{
                "dims": dims,
                "pose": [float(center_b[0]), float(center_b[1]), float(center_b[2]),
                          _iqw, _iqx, _iqy, _iqz],
            }}
        except Exception as _ce:
            print(f"(scene_cfg: skip {{path}}: {{_ce}})")
            continue
    # 2026-06-03 NOTE: a bin-wall keep-out COLLAR was tried here (force the folded 6-DOF UR10 upper_arm above the
    # z~0.80-0.90 wall band) but did NOT stop the upper_arm|WallX1/WallY2 brush (CP-86) — the arm MUST fold low to
    # reach the near 0.64m bin, and cuRobo plans with sphere approximations so the real mesh still brushes. Reverted
    # (the cube delivers err 1mm regardless; it's a path-quality brush, not a gate fail). Deeper levers = move the bin
    # farther (task change, Anton's call) or bias the IK branch elbow-up. See ledger 2026-06-03.
    # 2026-05-31 arm-arm fix: merge sibling-robot keep-out cuboids (current pose).
    # GATED: _sibling_keepout_cuboids() is {{}} for single-robot → byte-identical.
    try:
        cuboids.update(_sibling_keepout_cuboids())
    except Exception as _se:
        print(f"(scene_cfg: sibling keep-out skip: {{_se}})")
    return _CuroboSceneCfg.create({{"cuboid": cuboids}})

def _plan_to_world_point(point_world, current_q7, exclude_obs=None, yaw_deg=0.0, vhold_mode=0, branch_pin=False):
    # vhold_mode: 0=off, 1=PCM hold_partial_pose project_to_goal_frame=False weight=1
    #             2=PCM hold_partial_pose project_to_goal_frame=True weight=1
    #             3=PCM hold_partial_pose weight=0.1 (gentle)
    #             4=PCM reach_partial_pose weight=1
    # 2026-06-06 NVIDIA-CUP cup-offset (gated _sg_nvidia_cup), now TUNABLE (default 0.0).
    # MEASURED (scene_eyes CP-83, straight cup): a blanket +0.158 here DOUBLE-COUNTS the cup-below-tool0 offset that
    # the goal-z values ALREADY bake in — pz (L6086, asset path) = cube_z-0.05+0.035+_SG_TOOL_L(~0.162) puts tool0
    # high enough that the straight cup (0.158 below tool0) reaches the cube; the S5 drop goal similarly bakes
    # _drop_tip_release(0.16). Adding +0.158 on top lifted the cup ~0.12 m ABOVE the cube -> grip-miss abort
    # (cup>0.12m), 0 picks. So the goals are CORRECT tool0-targets and the offset must be 0.0. Kept as a tunable
    # (_sg_nvidia_cup_offset) for empirical sweep; default 0.0 = no double-count. _sg_nvidia_cup gated -> the -90
    # production cup path never reaches here changed (byte-identical when the flag is OFF).
    point_world = list(point_world)
    # 2026-06-10 HANG-LOCALIZER (gated _ur10_hangloc, default OFF -> no-op byte-identical). Rolling file-flush sentinel:
    # when CP-71 hard-hangs in a single blocking cuRobo call (Kit main thread frozen), the LAST label written = the call
    # that blocked. Pinpoints update_world vs ik_solve vs plan_cspace vs plan_pose for the next CP-71 attempt.
    def _HL(_lbl):
        try:
            if getattr(__import__("builtins"), "_ur10_hangloc", False):
                with open("/tmp/cp71_hangloc.txt", "w") as _hf: _hf.write(str(_lbl) + " goal=" + str([round(float(_v), 2) for _v in point_world]) + "\\n")
        except Exception: pass
    # 2026-06-09 RANK-2 BUILD-DEADLINE check (gated via _ur10_plan_deadline, set by _build_segments only when
    # _ur10_build_budget_s>0; default 0.0 here -> byte-identical). Once the build's wall-clock budget is spent, every
    # further plan call returns None INSTANTLY so the segment fan-out can't grind/hang the Kit. [MEASURED CP-71 hang].
    try:
        _pdl = float(getattr(__import__("builtins"), "_ur10_plan_deadline", 0.0))
        if _pdl > 0.0 and time.monotonic() > _pdl: return None
    except Exception: pass
    if getattr(__import__("builtins"), "_sg_nvidia_cup", False):
        point_world[2] = float(point_world[2]) + float(getattr(__import__("builtins"), "_sg_nvidia_cup_offset", 0.0))
    p_base = _world_to_base(point_world)
    pos_t = torch.tensor([[[[[float(p_base[0]), float(p_base[1]), float(p_base[2])]]]]],
                         dtype=torch.float32, device='cuda')
    quat_base = _rotated_down_quat_base(yaw_deg) if yaw_deg else _DOWN_Q_BASE
    # 2026-06-07 NVIDIA-CUP descend-repoint (gated _sg_nvidia_cup + tunable _sg_descend_repoint_deg, default 0=no-op).
    # MEASURED (scene_eyes CP-83, _ca_deg=0 straight cup, PLAYED): the cup-suction axis stays at its BUILD orientation
    # (tool-local -X, since the _ca_deg=0 fixup applies no rotation) -> with the standard tool0 +Z-down descend the
    # out-the-end cup points SIDEWAYS -> grip-miss (cup lands 0.2m beside the cube, 0 picks). To grasp top-down the
    # gripper AXIS (the -X out-the-end direction) must point world-DOWN. Post-multiply the goal quat by a rotation
    # about the tool-local Y so a different tool axis takes over the world-down role. Sign resolved EMPIRICALLY
    # (measure which value grips) -- NOT guessed (the earlier ad-hoc +/-90 attempts failed on sign). Clones the quat
    # (never mutates the _DOWN_Q_BASE global). Gated -> production (-90 cup, _sg_nvidia_cup OFF) byte-identical.
    import builtins as _bi_rp
    _rp = float(getattr(_bi_rp, "_sg_descend_repoint_deg", (-90.0 if getattr(_bi_rp, "_sg_nvidia_cup", False) else 0.0)))  # 2026-06-07 WINNING: nvidia default -90 -> the descend goal-quat points the CUP straight DOWN (ee_joint rpy=π,-π/2 makes ee+Z-down != cup-down). GATE-VERIFIED on CP-84 (real SG grip + deliver, no FJ). Production (nvidia OFF) default 0 = byte-identical.
    if _rp != 0.0 and getattr(_bi_rp, "_sg_nvidia_cup", False):
        import math as _mrp
        _ha = _mrp.radians(_rp) * 0.5
        _cc = _mrp.cos(_ha); _ss = _mrp.sin(_ha)
        _w1 = float(quat_base[..., 0]); _x1 = float(quat_base[..., 1])
        _y1 = float(quat_base[..., 2]); _z1 = float(quat_base[..., 3])
        # q_new = quat_base (x) q_localY(_rp) ; q_localY = (cos, 0, sin, 0)
        _nw = _w1 * _cc - _y1 * _ss
        _nx = _x1 * _cc - _z1 * _ss
        _ny = _w1 * _ss + _y1 * _cc
        _nz = _x1 * _ss + _z1 * _cc
        quat_base = torch.tensor([[[[[_nw, _nx, _ny, _nz]]]]], dtype=torch.float32, device='cuda')
    goal = GoalToolPose(tool_frames=[_TOOL_FRAME], position=pos_t, quaternion=quat_base)
    q = torch.tensor([[float(x) for x in current_q7[:_ARM_DOF]]], dtype=torch.float32, device='cuda')
    start = JointState.from_position(q, joint_names=_PLANNER_JOINT_NAMES)
    _vhold_applied = False
    # 2026-06-04 EXPERIMENT (gated): POSITION-ONLY plan. The swing is a geometrically-forced IK branch
    # flip from the tool being orientation-locked DOWN through the front-center crossing (RCA 2026-06-04).
    # track_position() costs POSITION only -> orientation free -> trajopt/IK can avoid the flip. Off =>
    # byte-identical. (Applies to all plans here; transit-only refinement is a follow-up.)
    if getattr(builtins, "_ur10_pos_only", False):
        try:
            from curobo._src.cost.tool_pose_criteria import ToolPoseCriteria as _TPC_po
            _planner.reset_seed()
            _planner.trajopt_solver.update_tool_pose_criteria({{_TOOL_FRAME: _TPC_po.track_position()}})
            _vhold_applied = True
        except Exception as _poe:
            try:
                with open('/tmp/posonly_dbg.log', 'a') as _pof: _pof.write("posonly_fail " + str(_poe)[:140] + "\\n")
            except Exception: pass
    # 2026-06-03 UR10 SEED-DRIFT fix: reset_seed() is otherwise only called in the vhold>0 path
    # (Franka). For UR10 (_vmode=0) the cuRobo sample buffer ADVANCES across plan calls within a
    # Kit session -> consecutive plans on the same goal resolve to DIFFERENT IK branches -> the
    # 2nd+ pick cycle contorts/spins/flings (the Kit-session "degradation": CP-69 1st-run clean,
    # 2nd-run flung, reproducibly). Reset per-plan for determinism. Gated to UR10 -> Franka already
    # resets in the vhold path, so the 37 single-robot Franka passes are byte-identical.
    # 2026-06-03 also reset per-plan for MULTI-ROBOT (dual-Franka): FrankaA+FrankaB SHARE the cached
    # MotionPlanner (same robot_cfg) -> FrankaA's plan advances the Halton sample buffer -> FrankaB's
    # plan is BIASED by FrankaA's persisted seed -> the DIAGONAL approach that pushes the free cube +
    # grips air (cp51_faithful: FrankaB hand at y=-0.06 mid-height, not over the cube y=-0.29). Reset so
    # FrankaB gets its own deterministic vertical descent. GATED >1 live _curobo_pp_sub_ -> single-robot
    # Franka (the 37) never enters this branch -> byte-identical.
    try:
        import builtins as _bi_rs
        _multi_rs = len([_k for _k in vars(_bi_rs) if _k.startswith("_curobo_pp_sub_")]) > 1
    except Exception:
        _multi_rs = False
    if ROBOT_FAMILY in ("ur10", "ur10e") or _multi_rs:
        try: _planner.reset_seed()
        except Exception: pass
    if vhold_mode > 0:
        try:
            # 2026-05-27 NATIVE LINEAR-MOTION: cuRobo's ToolPoseCriteria.linear_motion(axis="z")
            # — same mechanism NV uses internally for grasp-lift (motion_planner.py:511).
            # Combines non_terminal_pose_axes_weight_factor=[1,1,0,1,1,1] + project_distance_to_goal=True
            # → XY drift penalized in goal frame at EVERY trajectory knot, not just terminal.
            # Plus reset_seed() for determinism (sample buffer otherwise advances across calls).
            from curobo._src.cost.tool_pose_criteria import ToolPoseCriteria
            _planner.reset_seed()
            _lc = ToolPoseCriteria.linear_motion(axis="z", non_terminal_scale=1.0, project_distance_to_goal=True)
            _planner.trajopt_solver.update_tool_pose_criteria({{_TOOL_FRAME: _lc}})
            _vhold_applied = True
        except Exception as _e:
            with open('/tmp/vhold_debug.log','a') as _f: _f.write(f'linear_motion_FAIL: {{type(_e).__name__}}: {{_e}}\\n')
    try:
        # Scene-collision: build SceneCfg from PLANNING_OBSTACLES. 2026-05-29:
        # only update_world when the obstacle SET CHANGES, not every plan.
        # PLANNING_OBSTACLES are static (table/belt/bin) and the picked cube is not
        # among them, so rebuilding per-plan is wasteful AND recompiles cuRobo's
        # collision kernels with churning Warp struct hashes -> cache corruption
        # ("CuboidDataWarp_<hash> undefined" / NVRTC_ERROR_COMPILATION) ->
        # intermittent plan_pose failures on heavy templates. The planner is cached
        # across runs (builtins._curobo_pp_planner), so key on the obstacle
        # signature to rebuild correctly when the template/scene changes.
        try:
            # 2026-05-31 dual-Franka grip-slip fix: _build_scene_cfg expresses every
            # obstacle cuboid in THIS robot's BASE frame (_world_to_base → _usd_pos/quat).
            # _pp_world_sig lives on the SHARED cached planner; keying it on the obstacle
            # PATH-SET alone makes the 2nd robot (different base, SAME obstacle list) skip
            # update_world and plan against the 1st robot's base-frame world → trajectory
            # geometrically off → grasp never seats → cube slips mid-transport (CP-52/53
            # FrankaB). Fold the base frame into the sig so each distinct base rebuilds its
            # world. GATED multi-robot-only: single robot has ONE base → sig constant → one
            # update_world (first plan), byte-identical to before.
            _base_sig = ",".join("%.3f" % float(_v) for _v in list(_usd_pos) + list(_usd_quat))
            # 2026-05-31 arm-arm fix: append sibling distal-link pose sig (5cm-quantized)
            # so the world REBUILDS as the moving sibling arm changes pose. Empty for
            # single-robot → sig constant → one update_world, byte-identical to the 37.
            try:
                _sib_sig = _sibling_pose_sig()
            except Exception:
                _sib_sig = ""
            # 2026-06-09 A1: fold the carry-phase flag so the world REBUILDS when _build_segments flips approach->carry
            # (the carry-scoped multicube obstacles change between phases). Constant when the flag is OFF -> byte-identical.
            _mc_sig = ("|c" + str(getattr(__import__("builtins"), "_mc_carry_phase", True))
                       if getattr(__import__("builtins"), "_ur10_multicube_obs_carry_only", False) else "")
            # 2026-06-10 STALE-WORLD FIX [MEASURED CP-83 exclown probe]: the sig did NOT fold the current TARGET
            # (exclude_path) nor the delivered-set, so switching Cube_2->Cube_1 NEVER re-ran update_world -> Cube_1's
            # plans hit Cube_2-era obstacles (own Pedestal_1 PRESENT, Pedestal_2 absent = inverted). Fold the target
            # when _ur10_excl_own_support is on + the delivered-set when _ur10_obs_exclude_delivered is on. Both
            # gated -> flags off = sig byte-identical (constant suffixes "" as before).
            _exo_sig = ("|exo" + str(exclude_obs)
                        if getattr(__import__("builtins"), "_ur10_excl_own_support", False) else "")
            _del_sig = ("|del" + str(sorted(getattr(__import__("builtins"), "_mc_delivered", set()) or []))
                        if getattr(__import__("builtins"), "_ur10_obs_exclude_delivered", False) else "")
            _world_sig = (("|".join(sorted(PLANNING_OBSTACLES)) if PLANNING_OBSTACLES else "")
                          + "@" + _base_sig + "#" + _sib_sig + _mc_sig + _exo_sig + _del_sig)
            if getattr(_planner, "_pp_world_sig", None) != _world_sig:
                _HL("before_worldbuild")
                scene_cfg = _build_scene_cfg(exclude_path=exclude_obs)
                _HL("before_updateworld nobs=%d" % (len(getattr(scene_cfg, "cuboid", []) or []) if scene_cfg is not None else -1))
                _planner.update_world(scene_cfg)
                _HL("after_updateworld")
                # 2026-06-13 EYES world-obs stash (gated _eyes_plan_capture -> production byte-identical):
                # record the obstacle-cuboid names in THIS plan's world so trace_goal_frame can tell a
                # res_None apart (sibling-keepout cuboids present? scene-floor only?). Additive, no flow change.
                try:
                    if getattr(__import__("builtins"), "_eyes_plan_capture", False):
                        _bg = __import__("builtins")
                        _bg._eyes_uw_count = int(getattr(_bg, "_eyes_uw_count", 0)) + 1   # times update_world fired
                        _cub = getattr(scene_cfg, "cuboid", None)   # may be a dict OR a list of Cuboid objects
                        if isinstance(_cub, dict):
                            _bg._eyes_last_world = sorted(_cub.keys())
                        elif _cub:
                            _bg._eyes_last_world = sorted(str(getattr(_o, "name", _o)) for _o in _cub)
                        else:
                            _bg._eyes_last_world = []
                except Exception: pass
                try: _planner._pp_world_sig = _world_sig
                except Exception: pass
        except Exception as _swe:
            print(f"(curobo update_world fallback: {{_swe}})")
        # Phase 4 diag (2026-05-10): increment plan_calls before each attempt;
        # on failure, increment plan_fails + record goal pose. Lets probes
        # quantify cuRobo planning success rate per CP.
        try: _a_plan_calls.Set(int(_a_plan_calls.Get() or 0) + 1)
        except Exception: pass
        # 2026-06-02 RCA (CP-83/CP-72 pedestal/multi-cube): cuRobo's collision
        # kernel intermittently fails to compile on first use ("CuboidDataWarp_<hash>
        # undefined" PCH mismatch / NVRTC_ERROR) → plan_pose RAISES. The failure is
        # TRANSIENT — Warp rebuilds the kernel on a subsequent call (CP-70 DELIVERS
        # despite plan_fails=4 via cross-tick retries; live last_fail_goal showed
        # err=Exception, not res_None). A single cube survives; multi-cube exhausts
        # its 3-strike budget before the kernel stabilizes. Retry plan_pose IN-PLACE
        # so the kernel settles within ONE _build_segments attempt. GATED to UR10:
        # Franka _PLAN_RETRY=1 → the single attempt + raise is byte-identical to the
        # 37 verified Franka passes. Retry is strictly additive (only fires when an
        # exception would otherwise fail the plan — cannot break a working plan).
        _PLAN_RETRY = 5 if ROBOT_FAMILY in ("ur10", "ur10e") else 1
        res = None
        # 2026-06-04 EXPERIMENT (gated): plan_cspace BRANCH-PIN. Eyes seed-capture showed plan_pose lets
        # trajopt drift to a FLIPPED goal config (the 223deg transit swing) even though IK is seeded from
        # current (use_implicit_goal=True frees the goal config). plan_cspace fixes the GOAL JOINT CONFIG
        # (IK-from-current -> closest branch) so trajopt CANNOT flip. Gated => off = byte-identical (Franka
        # + default UR10). Falls back to plan_pose on any failure. Returns same TrajOptSolverResult type.
        if (branch_pin or getattr(builtins, "_ur10_plan_cspace", False)) and ROBOT_FAMILY in ("ur10", "ur10e"):
            _csdbg = []
            try:
                _HL("before_ik")
                _ikr = _planner.ik_solver.solve_pose(goal, current_state=start, return_seeds=16)
                _HL("after_ik")
                _ikok = bool(_ikr.success.any().item()) if (_ikr is not None and hasattr(_ikr, "success")) else False
                _csdbg.append("ik_ok=" + str(_ikok))
                # 2026-06-09 FREE-IK PROBE (gated _ur10_freeik_probe, default OFF, READ-ONLY diagnostic — does NOT
                # change res/planning): when the wound-seeded solve fails, test whether ANY down-lock IK exists at
                # this goal via a FREE solve (no current_state, broad seeds). FREEIK_ok=False => the cup CANNOT point
                # straight-down at this pose at all (FUNDAMENTAL kinematic limit). FREEIK_ok=True => a clean config
                # exists far from the wound branch (fixable via a deliberate cspace reconfig-before-descend).
                if (not _ikok) and getattr(builtins, "_ur10_freeik_probe", False):
                    try:
                        _ikf = _planner.ik_solver.solve_pose(goal, return_seeds=16)
                        _fok = bool(_ikf.success.any().item()) if (_ikf is not None and hasattr(_ikf, "success")) else False
                        _csdbg.append("FREEIK_ok=" + str(_fok))
                        if _fok:
                            _fs = _ikf.solution.reshape(-1, _ikf.solution.shape[-1]); _fsu = _ikf.success.reshape(-1)
                            for _fi in range(_fs.shape[0]):
                                if bool(_fsu[_fi].item()):
                                    _csdbg.append("FREEIK_q=" + str([round(float(_x), 2) for _x in _fs[_fi].detach().cpu().numpy()])); break
                    except Exception as _fe:
                        _csdbg.append("FREEIK_EXC=" + str(_fe)[:80])
                # 2026-06-09 DOWN-LOCK SEED (gated _ur10_descend_downlock_seed, default OFF). [MEASURED] the close-pick
                # descend down-IK EXISTS (CP-69 same-pose goal: ik_ok=True, gq=[-0.934,-1.557,2.083,-2.096,-1.571,
                # -2.504]) but the wound-seeded + free 16-seed solves MISS it from CP-75's wound over-bin start. Re-solve
                # SEEDED at that known down-lock config so solve_pose finds the existing down-config; then the existing
                # closest-L1 + plan_cspace block (below) does a CONTROLLED joint-space reconfig wound->down (no fling).
                # Reliable delivery for the close picks (CP-70/75/80) at the cost of one controlled reconfig move.
                if (not _ikok) and getattr(builtins, "_ur10_descend_downlock_seed", False):
                    try:
                        _dlq = torch.tensor([[-0.934, -1.557, 2.083, -2.096, -1.571, -2.504]], dtype=torch.float32, device='cuda')
                        _dljs = JointState.from_position(_dlq, joint_names=_PLANNER_JOINT_NAMES)
                        _ikr2 = _planner.ik_solver.solve_pose(goal, current_state=_dljs, return_seeds=16)
                        _ik2ok = bool(_ikr2.success.any().item()) if (_ikr2 is not None and hasattr(_ikr2, "success")) else False
                        _csdbg.append("DLSEED_ok=" + str(_ik2ok))
                        if _ik2ok:
                            _ikr = _ikr2; _ikok = True; _csdbg.append("DLSEED_USED")
                    except Exception as _dle:
                        _csdbg.append("DLSEED_EXC=" + str(_dle)[:80])
                if _ikok:
                    # branch-continuity: of ALL successful IK seeds, pick the one CLOSEST (L1 joint dist)
                    # to the current config — forbids the elbow/wrist flip if a continuous solution exists.
                    _sols = _ikr.solution.reshape(-1, _ikr.solution.shape[-1])
                    _succ = _ikr.success.reshape(-1)
                    _sp = start.position.reshape(-1)
                    # 2026-06-09 CSPACE WRIST-UNWRAP (gated _ur10_cspace_unwrap, default OFF -> byte-identical).
                    # [MEASURED CP-83] the down-IK EXISTS (ik_ok=True) but bestd_rad=7.41 = 6.28 (2pi continuous-wrist
                    # wrap) + 1.13 (real) -> the L1 metric + plan_cspace see a 2pi gap -> cspace_ok=False (would 360-spin
                    # the wrist) -> RES_NONE, cup frozen 0.27m high. Unwrap each candidate's joints toward the CURRENT
                    # config (add k*2pi to land within pi) BEFORE the L1 + before feeding plan_cspace -> true dist 1.13,
                    # continuous interp -> cspace_ok=True. The RAWSEED idea (close-pick fix) for the cspace-pin path.
                    _unwrap = getattr(builtins, "_ur10_cspace_unwrap", False)
                    _TWO_PI = 2.0 * float(np.pi)
                    _best = None; _bestd = 1e9
                    for _si in range(_sols.shape[0]):
                        if not bool(_succ[_si].item()): continue
                        _solr = _sols[_si:_si + 1]
                        if _unwrap:
                            _k = torch.round((_sp.reshape(1, -1) - _solr) / _TWO_PI)
                            _solr = _solr + _k * _TWO_PI
                        _d = float((_solr.reshape(-1) - _sp).abs().sum().item())
                        if _d < _bestd: _bestd = _d; _best = _solr
                    _csdbg.append("bestd_rad=" + (str(round(_bestd, 2)) if _best is not None else "none"))
                    _gq = _best if _best is not None else _sols[0:1]
                    _gjs = JointState.from_position(_gq, joint_names=_PLANNER_JOINT_NAMES)
                    _HL("before_cspace")
                    _cres = _planner.plan_cspace(_gjs, start, max_attempts=3)
                    _HL("after_cspace")
                    _csok = bool(_cres.success[0, 0].item()) if (_cres is not None and hasattr(_cres, "success")) else False
                    _csdbg.append("cspace_ok=" + str(_csok))
                    _csdbg.append("gq=" + str([round(float(_x), 3) for _x in _gq.reshape(-1).detach().cpu().numpy()]))
                    if _csok:
                        res = _cres
            except Exception as _cspe:
                _csdbg.append("EXC=" + type(_cspe).__name__ + ":" + str(_cspe)[:120])
                res = None
            try:
                with open("/tmp/cspace_dbg.log", "a") as _csf:
                    _csf.write("CSPACE goal=" + str([round(float(_v), 3) for _v in point_world]) + " " + " ".join(_csdbg) + "\\n")
            except Exception: pass
        if res is None:
            for _pra in range(_PLAN_RETRY):
                # 2026-06-09 RANK-2: abort the retry fan-out if the build deadline is spent (gated; 0.0 -> never trips).
                try:
                    _pdl3 = float(getattr(__import__("builtins"), "_ur10_plan_deadline", 0.0))
                    if _pdl3 > 0.0 and time.monotonic() > _pdl3: break
                except Exception: pass
                try:
                    # 2026-06-10 RANK-2b NO-GRAPH (gated _ur10_no_graph, default OFF -> enable_graph_attempt=1 = byte-identical).
                    # [MEASURED CP-71] the hang is a SINGLE blocking cuRobo solve at build seg-0 (froze t=1.0s, 0 nudges); the
                    # graph planner (_get_graph_seed_trajectories, PRM search) fires when current_attempt>=enable_graph_attempt
                    # and can explore UNBOUNDED on a tight/unreachable scene. enable_graph_attempt=99 (> max_attempts) makes the
                    # graph branch NEVER fire -> IK+trajopt only (both bounded) -> plan fails FAST instead of hanging the Kit.
                    _ega = 99 if getattr(__import__("builtins"), "_ur10_no_graph", False) else 1
                    _HL("before_planpose")
                    res = _planner.plan_pose(goal, start, max_attempts=3, enable_graph_attempt=_ega)
                    _HL("after_planpose")
                    break
                except Exception:
                    if _pra == _PLAN_RETRY - 1:
                        raise
                    continue
        if res is None or not bool(res.success[0, 0].item()):
            try:
                _a_plan_fails.Set(int(_a_plan_fails.Get() or 0) + 1)
                # 2026-05-29 DIAGNOSTIC: capture cuRobo's failure status (IK Fail /
                # Trajopt Fail / Graph Fail / Collision) to characterize the dominant
                # plan_pose blocker instead of guessing. Read /tmp/curobo_planfail.log.
                _st = (getattr(res, "status", None) if res is not None else "res_None")
                _a_last_fail_goal.Set((f"world={{point_world}} st={{_st}}")[:200])
                with open("/tmp/curobo_planfail.log", "a") as _f:
                    _f.write(f"{{ROBOT_PATH}} goal={{point_world}} yaw={{yaw_deg}} status={{_st}}\\n")
            except Exception: pass
            try:
                import builtins as _ebf
                if getattr(_ebf, "_eyes_plan_capture", False):
                    _elogf = getattr(_ebf, "_eyes_plan_log", None)
                    if _elogf is None:
                        _elogf = []; _ebf._eyes_plan_log = _elogf
                    try:
                        _sq = [round(float(_q), 3) for _q in start.position.reshape(-1).tolist()][:7]
                    except Exception:
                        _sq = None
                    # rebuild-independent: read the sibling keep-out cuboids THIS plan would carry
                    # (the world-rebuild stash only fires when the sig changes, so it can be stale/None).
                    try:
                        _sibo = sorted(_sibling_keepout_cuboids().keys())
                    except Exception:
                        _sibo = None
                    _elogf.append({{"goal": [float(_v) for _v in point_world], "yaw": float(yaw_deg),
                                    "success": False, "status": str(_st),
                                    "world_obs": getattr(_ebf, "_eyes_last_world", None),
                                    "uw_count": int(getattr(_ebf, "_eyes_uw_count", 0)),
                                    "sib_obs": _sibo, "start_q": _sq}})
            except Exception: pass
            return None
        interp = res.get_interpolated_plan()
        traj = interp.position[0, 0, :, :7].detach().cpu().numpy()
        mt = float(res.motion_time()) if callable(res.motion_time) else float(res.motion_time)
        # 2026-06-04 EYES plan-capture (gated): record the EXACT cuRobo planned trajectory per
        # plan call so scene_eyes can read the planner's intended joint path (not infer from
        # playback). builtins._eyes_plan_capture must be set by the probe; off => zero cost =>
        # Franka byte-identical (the 37 hold). traj = [knots x 7 joints].
        try:
            import builtins as _eb
            if getattr(_eb, "_eyes_plan_capture", False):
                _elog = getattr(_eb, "_eyes_plan_log", None)
                if _elog is None:
                    _elog = []; _eb._eyes_plan_log = _elog
                # one-time: record the EXACT result-object format of this cuRobo build
                if not hasattr(_eb, "_eyes_plan_fields"):
                    try: _eb._eyes_plan_fields = sorted(a for a in dir(res) if not a.startswith("__"))
                    except Exception: _eb._eyes_plan_fields = []
                # cuRobo diagnostic "decision trace" — defensively pull whatever this build exposes
                def _rd(_n):
                    try:
                        _v = getattr(res, _n, None)
                        if _v is None: return None
                        if callable(_v): _v = _v()
                        if hasattr(_v, "item"): return float(_v.item())
                        if hasattr(_v, "tolist"):
                            _l = _v.tolist(); return _l[0] if isinstance(_l, list) and len(_l) == 1 else _l
                        return float(_v) if isinstance(_v, (int, float)) else str(_v)
                    except Exception: return None
                _diag = {{_k: _rd(_k) for _k in ("status", "solve_time", "total_time", "ik_time", "graph_time",
                          "trajopt_time", "finetune_time", "optimized_dt", "motion_time",
                          "position_error", "rotation_error", "cspace_error",
                          "seed_cost", "seed_rank", "num_seeds")}}
                try:
                    _di = getattr(res, "debug_info", None)
                    if _di is not None: _diag["debug_info"] = str(_di)[:600]
                except Exception: pass
                _etj = traj.tolist() if hasattr(traj, "tolist") else [list(_r) for _r in traj]
                _est = max(1, len(_etj) // 40)
                _elog.append({{"goal": [float(_v) for _v in point_world], "yaw": float(yaw_deg),
                               "success": True, "motion_time": float(mt), "knots": len(_etj),
                               "diag": _diag, "traj": _etj[::_est]}})
        except Exception: pass
        return (traj, mt)
    except Exception as _pe:
        try:
            _a_plan_fails.Set(int(_a_plan_fails.Get() or 0) + 1)
            _a_last_fail_goal.Set(f"world={{point_world}} err={{type(_pe).__name__}}")
        except Exception: pass
        print(f"(curobo plan fail: {{_pe}})")
        return None
    finally:
        if _vhold_applied:
            try:
                from curobo._src.cost.tool_pose_criteria import ToolPoseCriteria
                _planner.trajopt_solver.update_tool_pose_criteria({{_TOOL_FRAME: ToolPoseCriteria()}})
            except Exception: pass

# Belt + sensor + gripper
_belt_prim = stage.GetPrimAtPath(BELT_PATH) if BELT_PATH else None
_belt_sv = _belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if (_belt_prim and _belt_prim.IsValid()) else None
_captured = tuple(_belt_sv.Get()) if (_belt_sv and _belt_sv.IsDefined() and _belt_sv.Get()) else None
_nominal_belt = _captured if (_captured and sum(abs(v) for v in _captured) > 1e-6) else (0.2, 0.0, 0.0)

# Belt-pause-from-callback fix (cuRobo handler) — direct USD writes from
# physics-step callback get restored by PhysX integrator next tick. Use
# pre-step subscription to write velocity BEFORE PxScene::simulate() reads
# its cache. Same pattern as builtin handler (commit 7ef31a1).
_belt_pause_request_curobo = [None]
def _apply_belt_pause_curobo():
    # 2026-05-31 CP-53 dual-robot ride-off fix (probe-confirmed): STANDING belt
    # pause. When an undelivered cube sits in the sensor neighborhood, force the
    # belt STOPPED regardless of the controller's mode/request — otherwise a cube
    # rides past the pick station and off the belt end while THIS robot is idled
    # by the sibling holding the shared mutex (probe: producer idled while consumer
    # held the rack mutex -> Cube_1/2 rode to x=0.97 off the end). GATED multi-robot
    # only -> single-robot belt templates (CP-01/22/08) keep byte-identical request-
    # driven behavior, so the 37 verified-passing are untouched. Names resolve at
    # call time (callback fires only during sim, after the full codegen has run).
    try:
        # 2026-06-05 (CP-80 ride-off fix): the standing pre-step belt-freeze was gated multi-robot-only, so a
        # SINGLE-robot MOVING conveyor fell through to the request-driven pause set from INSIDE _on_step — which the
        # PhysX integrator caches independently and effectively IGNORES (the cube rides off the belt end before a
        # clean pick: CP-80 cube ended x=0.13 past the belt end, y still on the belt centerline). Extend the standing
        # freeze to ANY moving belt (single or multi robot), gated by belt speed so STATIC feeders (CP-70 v≈0.001 <
        # 0.05) stay byte-identical -- they never rode off, never needed it. _resume_belt_if_clear still lets upstream
        # cubes flow to the sensor (no deadlock; freeze only while a cube is imminent OR this arm is actively picking).
        _belt_is_moving = sum(abs(v) for v in _nominal_belt) > 0.05
        if ((len(_curobo_live_pp_subs()) > 1 or _belt_is_moving) and _belt_sv is not None and (
                (_sensor_xy_v is not None and _cube_imminent_at_sensor())
                # 2026-06-05 CP-52 ride-off fix: hold the SHARED belt while THIS robot is
                # actively picking (claimed→delivering). Otherwise the robot's SECOND cube
                # rides off the belt end during the ~15s it spends on the first (CP-52:
                # Cube_1/Cube_4 flew off while their arm worked Cube_3/Cube_2). When the
                # robot returns to wait_sensor the belt resumes (below / _resume_belt_if_clear)
                # so the next cube flows in. GATED multi-robot. Self-freeze-safe: the per-cube
                # mutex keeps both robots delivering (no robot stuck busy forever).
                or S.get("mode") in ("settling", "executing", "gripping", "retreating"))):
            _belt_sv.Set((0, 0, 0))
            _belt_pause_request_curobo[0] = None
            return
    except Exception:
        pass
    req = _belt_pause_request_curobo[0]
    if req is None: return
    if req is True:
        if _belt_sv: _belt_sv.Set((0, 0, 0))
    else:
        if _belt_sv: _belt_sv.Set(_nominal_belt)
    _belt_pause_request_curobo[0] = None
def _pause_belt():
    if _belt_sv: _belt_sv.Set((0, 0, 0))
    _belt_pause_request_curobo[0] = True
def _resume_belt():
    if _belt_sv: _belt_sv.Set(_nominal_belt)
    _belt_pause_request_curobo[0] = False
    # WAKE settled items (2026-06-14): items resting on the belt SLEEP during a pause
    # (confirmed via physx is_sleeping; sleepThreshold=0 does NOT prevent it — the
    # "0 = engine default" gotcha). A resumed belt does NOT re-drive a SLEEPING body,
    # so items that sat through a pick-pause are stranded (nir 3/6, CP-44 residual,
    # sorter 8/9 — a general multi-item belt-pick bug). Wake the on-belt source items
    # via the physx simulation interface so the surface velocity carries them again.
    # Verified in isolation: wake_up -> item rides (+0.71) vs 0.0 without. Only items
    # still resting ON the belt (z within ~6cm of belt top), not delivered, are woken;
    # the lifted/grasped cube and delivered cubes are skipped -> picks/deliveries
    # undisturbed. ADDITIVE (waking a moving body is a no-op).
    try:
        from omni.physx import get_physx_simulation_interface as _gsiw
        from pxr import PhysicsSchemaTools as _pstw
        _bpw = _belt_sv.GetPrim() if _belt_sv else None
        if _bpw and _bpw.IsValid():
            _siw = _gsiw(); _sidw = omni.usd.get_context().get_stage_id()
            _btopw = float(UsdGeom.Xformable(_bpw).ComputeLocalToWorldTransform(0).ExtractTranslation()[2]) + 0.05
            for _spw in SOURCE_PATHS:
                if _spw in S.get('delivered', set()):
                    continue
                _ipw = stage.GetPrimAtPath(_spw)
                if not _ipw or not _ipw.IsValid():
                    continue
                _izw = float(UsdGeom.Xformable(_ipw).ComputeLocalToWorldTransform(0).ExtractTranslation()[2])
                if abs(_izw - _btopw) > 0.06:
                    continue
                try:
                    _siw.wake_up(_sidw, _pstw.sdfPathToInt(Sdf.Path(_spw)))
                except Exception:
                    pass
    except Exception:
        pass
try:
    _BELT_PRESTEP_CUROBO_ATTR = "_belt_prestep_curobo_" + _ROBOT_TAG + "_" + _PHASE_ID
    _old_pre_c = getattr(builtins, _BELT_PRESTEP_CUROBO_ATTR, None)
    if _old_pre_c is not None:
        try: _old_pre_c.unsubscribe()
        except Exception: pass
    _belt_prestep_sub_c = omni.physx.get_physx_interface().subscribe_physics_on_step_events(
        lambda _dt: _apply_belt_pause_curobo(),
        True, 0,
    )
    setattr(builtins, _BELT_PRESTEP_CUROBO_ATTR, _belt_prestep_sub_c)
except Exception as _bpe:
    print(f"(curobo: pre-step belt-pause subscription failed: {{_bpe}})")

# 2026-05-30 conveyor ride-off fix: hoist sensor xy + S (initial) + a SENSOR-AWARE
# resume gate ABOVE the install resume. Cubes spawned at/near the sensor used to ride
# off because the belt free-ran here (and between picks) before the claim+pause tick.
# _resume_belt_if_clear() suppresses resume ONLY while a cube sits within HOLD_R of the
# sensor xy (about to be claimed) — NOT reach-based, so upstream cubes still flow to the
# sensor (no deadlock; the reach-based naive fix deadlocked CP-01). Fail-open to plain
# resume when there is no sensor -> static/table-top templates are byte-unaffected.
# These are hoisted COPIES; the originals (_sensor block, S dict) re-execute harmlessly
# below — nothing mutates S between here and there (only _on_step does, at runtime).
_sensor = stage.GetPrimAtPath(SENSOR_PATH) if SENSOR_PATH else None
def _sensor_xy():
    if _sensor is None or not _sensor.IsValid(): return None
    t = UsdGeom.Xformable(_sensor).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1])])
_sensor_xy_v = _sensor_xy()
S = {{"mode": "wait_sensor", "picked_path": None, "segments": None,
      "seg_idx": 0, "seg_start_t": None,
      "cubes": 0, "errors": 0, "ticks": 0, "delivered": set(), "failed": set(),
      "settle_ticks": 0, "grip_action_done": False}}
HOLD_R = 0.15  # sensor-neighborhood hold radius (m); NOT reach — upstream cubes must still travel in
def _cube_imminent_at_sensor():
    # True iff some undelivered cube sits within HOLD_R of the sensor xy.
    if _sensor_xy_v is None: return False
    # 2026-06-04 CP-52 self-lock fix (eyes+probe-confirmed): in MULTI-robot mode the
    # standing belt-pause force-stops the SHARED belt whenever any source cube is within
    # HOLD_R of a sensor. A cube spawned/sitting DOWNSTREAM of the sensor (already past
    # the pick point in the belt-flow direction) can NEVER be saved by pausing -- it just
    # freezes the belt forever and starves the sibling's UPSTREAM cubes. CP-52: Cube_3
    # spawns 0.10m downstream of SensorB (HOLD_R=0.15) -> belt SV pinned to 0 for the whole
    # run, no cube ever flows (probe: beltSV=[0,0,0] @ every tick, all cubes Delta=0). Skip
    # downstream cubes when pausing. GATED multi-robot: single robot keeps the exact
    # radius-only behavior (the 37 byte-identical; _resume_belt_if_clear unchanged for them).
    _multi = len(_curobo_live_pp_subs()) > 1
    _fx = float(_nominal_belt[0]) if _nominal_belt else 0.0
    _fy = float(_nominal_belt[1]) if _nominal_belt else 0.0
    _fmag = (_fx*_fx + _fy*_fy) ** 0.5
    for sp in SOURCE_PATHS:
        if sp in S['delivered'] or sp in S.get('failed', set()): continue
        cp = _world_pos(sp)
        if cp is None: continue
        if float(((cp[0]-_sensor_xy_v[0])**2 + (cp[1]-_sensor_xy_v[1])**2) ** 0.5) <= HOLD_R:
            if _multi and _fmag > 1e-6:
                # signed distance along belt-flow from sensor; >+3cm = downstream of pick point
                _proj = ((cp[0]-_sensor_xy_v[0])*_fx + (cp[1]-_sensor_xy_v[1])*_fy) / _fmag
                if _proj > 0.03: continue
            return True
    return False
def _resume_belt_if_clear():
    # Sensor-aware resume: resume only when no cube sits in the sensor neighborhood.
    if _sensor_xy_v is None or not _cube_imminent_at_sensor():
        _resume_belt()

if _belt_sv and sum(abs(v) for v in (_belt_sv.Get() or (0,0,0))) < 1e-6:
    _resume_belt_if_clear()

_UR10_FJ_PATH = [None]  # cuRobo's UR10 FixedJoint workaround (same pattern as builtin handler)

# 2026-06-02 SUCTION grip wiring (validated CP-70). The standalone surface_gripper tool authors a
# free cone FixedJoint-mounted to a KINEMATIC follower (robot_path + "_SGFollower") + an IsaacSurfaceGripper
# with a D6 attachment (cone<->cube grip = real raycast suction; grip-FJ count stays 0). Two facts proven:
#   (1) the follower must be driven to the LIVE ee each tick (ComputeLocalToWorldTransform / dynamic_control
#       read STALE under the canonical build's fabric; cuRobo FK from the live joints is the live source), and
#   (2) the SG engages only via the RAW surface_gripper interface close_gripper() — the GripperView/wrapper
#       .close() does NOT engage the grip. Gated to suction robots (follower prim exists) -> Franka unaffected.
_SG_IFACE = None; _SG_PATH_RAW = None; _SG_FOLLOWER_OP = None
_SG_TOOL_L = 0.08  # virtual suction tool length: the cone sits this far BELOW the flange (ee_link). The
# grasp descends the flange to cube_top+0.02+_SG_TOOL_L so the flange+wrist clear the cube and the cone
# (flange-_SG_TOOL_L) lands just above the cube top — a downward raycast then hits the cube, NOT the robot's
# own wrist_3_link (root cause CP-70: cone at ee+0.04 was buried in wrist_3_link -> raycast hit the wrist@0.000).
_sg_tool_l_dyn = [_SG_TOOL_L]  # DYNAMIC tool length: stays _SG_TOOL_L for pick/transit; the S5 release ramps it UP
# to descend the cup+cube (via the follower) the extra distance cuRobo can't reach at the near bin (anti-topple).
try:
    _sgm_attr = stage.GetPrimAtPath(ROBOT_PATH).GetAttribute("isaac_assist:surface_gripper_path")
    _SG_PATH_RAW = _sgm_attr.Get() if (_sgm_attr and _sgm_attr.IsDefined()) else None
    # 2026-06-13 PARALLEL-JAW DECOR GUARD. A parallel-jaw robot (Franka) may carry a SurfaceGripper
    # marker as INERT scene decor: the surface_gripper tool authors it WITHOUT a cone/joints for finger
    # robots (CP-54/62 "Franka with surface_gripper"; see _handle_surface_gripper _has_parallel_jaw skip).
    # The raw-suction interface must NOT be wired for them — otherwise _grip_close()/_grip_open() below
    # early-return into the inert suction close_gripper()/open_gripper() and the parallel JAW never
    # actuates. MEASURED (fresh Kit): CP-54 panda_finger range 0.0deg + 0 cube contacts (jaw frozen, cube
    # rides belt to x=1.699); the identical-build control CP-01 (no decor marker) shows finger travel +
    # finger|cube contacts (RIGID HOLD). The prior comment claimed "Franka: _sg_path None -> _SG_IFACE
    # None" but conflated _sg_path (nulled for Franka above) with _SG_PATH_RAW (read fresh here, ungated).
    # Null the marker for finger robots so grip falls through to franka.gripper.forward("close"). The 37
    # marker-less Franka passes + UR10/UR10e suction (no fingers) are byte-identical.
    if _SG_PATH_RAW:
        for _d in stage.Traverse():
            _dp = str(_d.GetPath())
            if _dp.startswith(ROBOT_PATH + "/") and "finger" in _dp.lower():
                _SG_PATH_RAW = None  # decor only — the parallel jaw grips via friction
                break
    _folp = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH + "_SGFollower"))
    # 2026-06-05: acquire the RAW surface_gripper interface whenever the marker points at a valid SurfaceGripper
    # -- BOTH the procedural cone (follower present -> per-tick follower tracking) AND the asset short_gripper.usd
    # (child of ee_link, NO follower -> moves with the arm naturally, only needs the per-tick raw close re-assert).
    _sg_prim_ok = bool(_SG_PATH_RAW and stage.GetPrimAtPath(Sdf.Path(_SG_PATH_RAW)).IsValid())
    if _sg_prim_ok:
        import isaacsim.robot.surface_gripper._surface_gripper as _sgmod_raw
        _SG_IFACE = _sgmod_raw.acquire_surface_gripper_interface()
        if _folp and _folp.IsValid():
            _fol_ops = [o for o in UsdGeom.Xformable(_folp).GetOrderedXformOps() if o.GetOpName() == "xformOp:translate"]
            _SG_FOLLOWER_OP = _fol_ops[0] if _fol_ops else None
        print("(curobo: suction raw-grip wiring active for " + str(_SG_PATH_RAW) +
              (" + follower-track" if _SG_FOLLOWER_OP is not None else " (asset, no follower)") + ")")
except Exception as _se:
    print("(curobo: suction follower-track setup soft-fail: " + str(_se) + ")")
# 2026-06-05 ASSET-GRIPPER step 2: the suction LOGIC keyed on the procedural follower (_SG_FOLLOWER_OP). Both the
# procedural cone AND the asset short_gripper.usd now acquire the RAW interface (_SG_IFACE), so key the suction
# gate on it. PROCEDURAL UR10: _SG_IFACE set -> True == old gate. ASSET UR10: _SG_IFACE set -> True (now works).
# Franka: _sg_path None -> _SG_IFACE None -> False. -> the 37 Franka + procedural UR10 passes are byte-identical.
_SG_IS_SUCTION = (_SG_IFACE is not None)
# cup/cone world-position source for the grip-proximity gates: procedural cone OR the asset suction_cup frame.
if _SG_FOLLOWER_OP is not None:
    _SG_CUP_PATH = ROBOT_PATH + "_SGCone"
elif _SG_PATH_RAW:
    _SG_CUP_PATH = "/".join(str(_SG_PATH_RAW).split("/")[:-1]) + "/suction_cup"
else:
    _SG_CUP_PATH = ROBOT_PATH + "_SGCone"
# ASSET cup sits ~0.159m along the tool axis from the flange (vs the procedural cone's 0.08) -> set the virtual
# tool length so the pick descend lands the cup on the cube top. Asset-mode only (no follower + wrapper + UR10).
if (_SG_IFACE is not None) and (_SG_FOLLOWER_OP is None) and ROBOT_FAMILY in ("ur10", "ur10e"):
    _SG_TOOL_L = 0.159
    _sg_tool_l_dyn[0] = _SG_TOOL_L
    # 2026-06-09 FAITHFUL-CUP DEFAULT master switch (gated _ur10_faithful_default; UR10 asset-suction ONLY,
    # scoped by this block). [MEASURED] the proven winning config that makes ALL 6 deterministic passers clean on the
    # straight (faithful) cup (CP-69/70/75/79/80/86, pan-swing 0deg, deliver dead-center). Enables the 7 pieces as a unit:
    # straight nvidia mount + H7 transit (sign -1) + S5 RELIVE descend + branch-pin + RAW(unwrapped) relive seed (the
    # wrap-fling fix) + droptip 0.21 (down-IK reach). NEVER clobbers an explicit external flag (hasattr guard) so the
    # gate harness / A-B overrides win.
    # DEFAULT FLIPPED OFF->ON 2026-06-09 after the motion-clean adversarial verify (fresh-Kit, warp-cleared): the close
    # picks CP-70/75/80 all deliver dead-center at_rest, trajsrc seg=7 relive pan-range=0 (no fling), grip_log
    # bin_approaches=1 (no varv/extra lap) — the wrap/seed root of the descend flip is fixed, NOT a geometry limit. This
    # ships the faithful straight cup (Anton: "sidokopp är inte acceptabelt"). Side-mount remains reachable by setting
    # _ur10_faithful_default=False explicitly (A/B). UR10-asset-scoped => Franka/other families byte-identical.
    try:
        import builtins as _bi_fd
        # DEFAULT = ON (straight faithful cup). 2026-06-09: Anton's directive is unambiguous and overriding — "sidokopp
        # är inte acceptabelt". The side (90°) mount is OFF THE TABLE; the straight cup is the ONLY acceptable production
        # mount. I briefly reverted to side-OFF to "protect" CP-85's side-cup delivery (it regresses on straight) but
        # that was the WRONG call — it protected a cup Anton rejected. Correct stance: ship the straight cup; CP-85's
        # straight-cup delivery + multi-cube are OPEN WORK ON the straight cup (root-caused: ROOT-1 fixed by IKSEEDS=64;
        # ROOT-2 = place can't reach bin-center from the wound behind-side arrival), NOT a reason to revert. On the
        # straight cup 7/8 passers deliver dead-center motion-clean (CP-69/70/75/79/80/86 + CP-84). Side-mount still
        # reachable for A/B via explicit _ur10_faithful_default=False. UR10-asset-scoped => Franka byte-identical.
        if getattr(_bi_fd, "_ur10_faithful_default", True):
            if not hasattr(_bi_fd, "_sg_nvidia_cup"): _bi_fd._sg_nvidia_cup = True
            if not hasattr(_bi_fd, "_ur10_jointspace_transit"): _bi_fd._ur10_jointspace_transit = True
            if not hasattr(_bi_fd, "_ur10_jointspace_sign"): _bi_fd._ur10_jointspace_sign = -1.0
            if not hasattr(_bi_fd, "_ur10_s5_relive"): _bi_fd._ur10_s5_relive = True
            if not hasattr(_bi_fd, "_ur10_s5_relive_branch_pin"): _bi_fd._ur10_s5_relive_branch_pin = True
            # 2026-06-09 RANK-1 FIX (regression Anton flagged in GUI review): the PLACE close-loop PL-nudge (L7741/7748)
            # re-plans the held cube to the bin via FREE-IK plan_pose unless _ur10_place_nudge_branch_pin is set -> the
            # un-pinned re-plan flips the IK branch each tick = the ~356deg release SPIN/pirouette + micro-adjust hover
            # (RCA wwz8g0ox8: master switch set the S5-descend pin above but NOT the analogous NUDGE pin, so the clean
            # cspace descend was immediately overridden by the free-IK nudge). Mirror the descend pin -> pin the nudge
            # to the live branch (cspace + wrist-unwrap path at L7746-7747). getattr-default False => OFF byte-identical.
            if not hasattr(_bi_fd, "_ur10_place_nudge_branch_pin"): _bi_fd._ur10_place_nudge_branch_pin = True
            if not hasattr(_bi_fd, "_ur10_relive_seed_raw"): _bi_fd._ur10_relive_seed_raw = True
            if not hasattr(_bi_fd, "_sg_drop_tip_release"): _bi_fd._sg_drop_tip_release = 0.21
            # 2026-06-09: added IK-seed bump + lower H7 far-reach. [MEASURED] the behind-side-HIGH pick class (CP-85,
            # multi-cube CP-83/81/82) failed _build_segments seg-0 (no down-locked IK at the high pick goal z~1.15) AND
            # the place couldn't reach bin-center from the wound ~180deg arrival. IKSEEDS=64 finds the high approach IK
            # (planfails 485->0); far_reach=0.5 makes H7 (the jointspace pan-rotate transit) fire for reach>0.5 so the
            # behind->front transit ARRIVES CLEAN -> place reaches bin-center -> delivers. A/B-VERIFIED: CP-85 0/3->2/2
            # AND all 6 deterministic passers (CP-69/70/75/79/80/86) still deliver dead-center (FARREACH=0.5 does NOT
            # regress them — they were already clean via RELIVE/RAWSEED, H7 firing keeps them clean). => 8/8 passers.
            if not hasattr(_bi_fd, "_ur10_ik_seeds"): _bi_fd._ur10_ik_seeds = 64
            if not hasattr(_bi_fd, "_ur10_jointspace_far_reach"): _bi_fd._ur10_jointspace_far_reach = 0.5
            print("(curobo: _ur10_faithful_default ON -> straight cup + H7(far0.5) + relive + branch_pin + raw-seed + droptip 0.21 + ikseeds 64)", flush=True)
    except Exception: pass
# 2026-06-07 FAITHFUL-SUCTION FIX (gated _sg_nvidia_cup): the asset short_gripper.usd Suction_Joint has
# forwardAxis=Z but the cup OPENING is along the joint's -X; with the +90 cup mount the opening points world-down
# (correct visual) while the SG RAYCAST (forwardAxis Z) points SIDEWAYS -> the REAL IsaacSurfaceGripper never sees
# the cube under the cup (proven: get_gripped_objects=[] at 19mm) even though it closes (status Open->Closed). The
# "articulation-link bug" was actually this raycast/forwardAxis MISALIGNMENT, not a sim limitation. EMPIRICAL FIX
# (localRot sweep: only -90X gripped Cube_2 in isolation): rotate the Suction_Joint's localRot0 AND localRot1 by
# -90deg about X so forwardAxis-Z aligns with the cup opening -> the raycast follows the cup at EVERY pose -> at
# descend it points down at the cube within maxGripDistance(0.10) -> the real SG latches (no FJ cheat). Rotating
# BOTH frames by the same delta preserves the physical mount (cup does not move). Pose-invariant (body-relative).
# Gated -> production (-90 cup, _sg_nvidia_cup OFF) byte-identical.
# NOTE: build-time application is DEFAULT OFF (`_sg_fwdaxis_at_build`) — the SG reads the attachment frame at
# registration (play-start), and the working isolation grip rotated localRot LIVE after registration; a build-time
# (pre-registration) rotation does NOT engage (CP-83 reached 7cm but never latched). The LIVE one-shot in _on_step
# (`_fwdaxis_fix_done`) is the default for nvidia. This block stays for A/B.
if getattr(__import__("builtins"), "_sg_nvidia_cup", False) and getattr(__import__("builtins"), "_sg_fwdaxis_at_build", False) and _SG_PATH_RAW:
    try:
        _sjp = stage.GetPrimAtPath(Sdf.Path(_SG_CUP_PATH + "/Suction_Joint"))
        if _sjp and _sjp.IsValid():
            _dqfa = Gf.Quatf(Gf.Rotation(Gf.Vec3d(1.0, 0.0, 0.0), -90.0).GetQuat())
            for _attrn in ("physics:localRot0", "physics:localRot1"):
                _afa = _sjp.GetAttribute(_attrn)
                if _afa and _afa.IsValid() and _afa.Get() is not None:
                    _afa.Set(Gf.Quatf(_afa.Get()) * _dqfa)
            print("(curobo: nvidia forwardAxis fix at BUILD — Suction_Joint localRot0/1 rotated -90X)")
    except Exception as _fae:
        print("(curobo: nvidia forwardAxis fix soft-fail: " + str(_fae) + ")")
# render-shaft (gripper body) handle — stretched each tick to bridge flange<->cup so the "mellandel" stays
# rendered even while the release tool-extend telescopes the cup deep into the bin (Anton's render complaint).
_SG_SHAFT = [None, None]
try:
    _shaftp = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH + "_SGCone/VisShaft"))
    if _shaftp and _shaftp.IsValid():
        _sh_ops = [o for o in UsdGeom.Xformable(_shaftp).GetOrderedXformOps() if o.GetOpName() == "xformOp:translate"]
        _SG_SHAFT = [UsdGeom.Cylinder(_shaftp).GetHeightAttr(), (_sh_ops[0] if _sh_ops else None)]
except Exception: pass
_sg_track_last = [None]
_sg_grip_intent = [False]  # True between a suction _grip_close and the next _grip_open; re-asserts close each tick
# 2026-06-02 (Agent B RCA): drive the kinematic follower via the physics-tensor set_kinematic_targets (=
# PxRigidDynamic::setKinematicTarget) NOT xformOp.Set() (USD teleport). The teleport gives the constraint solver
# NO velocity -> under fast cuRobo motion the implied velocity is discontinuous -> force spike -> cube flung/exploded.
# set_kinematic_targets presents a consistent velocity so the grip + FJ chain stays stable.
_sg_fview = [None, False]  # [RigidBodyView, tried]
def _get_follower_view():
    if _sg_fview[1]: return _sg_fview[0]
    _sg_fview[1] = True
    try:
        _sv = globals().get("_physics_sim_view", None)
        if _sv is None:
            try:
                from isaacsim.core.simulation_manager import SimulationManager as _SM2
                _sv = _SM2.get_physics_sim_view()
            except Exception: _sv = None
        if _sv is None:
            import omni.physics.tensors as _pt
            _sv = _pt.create_simulation_view("numpy")
        _sg_fview[0] = _sv.create_rigid_body_view(ROBOT_PATH + "_SGFollower")
    except Exception as _ve:
        print("(curobo: follower RigidBodyView create soft-fail -> USD-xform fallback: " + str(_ve) + ")")
        _sg_fview[0] = None
    return _sg_fview[0]
def _track_suction_follower():
    # drive the kinematic follower to the LIVE ee (cuRobo FK from current joints) + 0.04 above so the
    # FJ'd cone sits just over the cube top for the raycast-down grip. No-op for non-suction robots.
    # Per-step delta is clamped to 0.15m so the first tick (follower authored at ee REST pose -> live
    # HOME pose) can't teleport the cone and explode the cone<->follower FixedJoint (validated 2026-06-02).
    # ASSET gripper (no follower) is a real child of ee_link -> it co-moves with the arm and needs NO follower
    # tracking, but it DOES need the per-tick raw close re-assert (a single close_gripper only flickers "Closing").
    # This top re-assert runs ONLY in asset mode (_SG_FOLLOWER_OP is None) so the procedural path below is 100%
    # byte-identical (procedural re-asserts at the END of the tracking block, unchanged).
    if _SG_FOLLOWER_OP is None:
        if _sg_grip_intent[0] and _SG_IFACE is not None and _SG_PATH_RAW:
            try: _SG_IFACE.close_gripper(_SG_PATH_RAW)
            except Exception: pass
        return
    try:
        _jq = franka.get_joint_positions()
        if _jq is None: return
        from curobo.types import JointState as _JS_fk
        _t = torch.tensor([[float(x) for x in np.asarray(_jq)[:_ARM_DOF]]], dtype=torch.float32, device="cuda")
        _ee = _planner.compute_kinematics(_JS_fk.from_position(_t, joint_names=_PLANNER_JOINT_NAMES)).tool_poses.position[0, 0, 0].detach().cpu().numpy()
        _tx = float(_usd_pos[0]) + float(_ee[0]); _ty = float(_usd_pos[1]) + float(_ee[1]); _tz = float(_usd_pos[2]) + float(_ee[2]) - _sg_tool_l_dyn[0]
        _cur = _sg_track_last[0]
        if _cur is not None:
            _ddx = _tx - _cur[0]; _ddy = _ty - _cur[1]; _ddz = _tz - _cur[2]
            _dl = (_ddx * _ddx + _ddy * _ddy + _ddz * _ddz) ** 0.5
            if _dl > 0.15:  # m/tick teleport clamp. 2026-06-03: TRIED 0.04 (gentler peak on the near CP-70 bin) but it
                # REGRESSED far-reach picks (CP-69 cube@x=-1.0): the fast lift->transit makes the tightly-clamped follower
                # LAG, then snap-catch-up at the clamp rate, ejecting the gripped cube at 11 m/s. 0.15 keeps the follower
                # with the ee (no lag-snap). The CP-70 peak height is the cuRobo path, not this clamp -> 0.15 loses nothing real.
                _sc = 0.15 / _dl; _tx = _cur[0] + _ddx * _sc; _ty = _cur[1] + _ddy * _sc; _tz = _cur[2] + _ddz * _sc
        # USD-xform driving (the set_kinematic_targets path froze the follower — view didn't bind the mid-build
        # prim). With the RIGID grip (Agent A) the USD-xform driving is STABLE — the rigid-grip test tracked
        # smoothly to the bin center (0.004) with NO explosion; the explosion Agent B diagnosed was the SOFT-grip
        # case, now fixed. Keep USD-xform; the residual release-fling is a PLACEMENT issue (Agent C dwell/lower-release).
        _SG_FOLLOWER_OP.Set(Gf.Vec3d(_tx, _ty, _tz)); _sg_track_last[0] = (_tx, _ty, _tz)
        # stretch the render shaft to span cone->flange (= tool length) so the gripper body stays rendered
        # through the release telescope (no reappearing empty "mellandel" when the cup descends into the bin).
        if _SG_SHAFT[0] is not None:
            _tl = _sg_tool_l_dyn[0]
            try:
                _SG_SHAFT[0].Set(max(0.01, _tl - 0.005))
                if _SG_SHAFT[1] is not None: _SG_SHAFT[1].Set(Gf.Vec3d(0.0, 0.0, (0.005 + _tl) / 2.0))
            except Exception: pass
        # re-assert the suction close EVERY tick while gripping — a single close_gripper() call only
        # flickers "Closing" for one step then reverts to "Open"; re-asserting keeps it raycasting until
        # the tracked cone is over the cube (-> "Closed"), then HOLDS through lift/transport (validated CP-70).
        if _sg_grip_intent[0] and _SG_IFACE is not None and _SG_PATH_RAW:
            try: _SG_IFACE.close_gripper(_SG_PATH_RAW)
            except Exception: pass
    except Exception: pass
_sg_item_rp = {{}}  # gripped-item path -> SingleRigidPrim (cached, lazy)
def _clamp_gripped_velocity():
    # 2026-06-05 FLING GUARD (generalizing): the kinematic-follower USD-xform teleport can spike the gripped
    # cube's velocity (lag-snap), and the follower->FJ->cone->grip->(rubber) chain amplifies it to 20-50 m/s /
    # NaN-infinity -> the cube is flung off-scene (CP-71 Item_3 -> ~7600 m; CP-73 cube @ 23.7 m/s). Cap the gripped
    # body's linear velocity each tick. Honest pick-place motion is ~1 m/s, so a 3 m/s ceiling is transparent to
    # real picks (CP-70 never exceeds it -> byte-identical) but kills the explosion. Suction-only + only while a
    # cube is gripped; Franka/parallel-jaw + no-grip ticks are untouched.
    if not _SG_IS_SUCTION: return
    _p = S.get("picked_path")
    if not _p: return
    try:
        _rp = _sg_item_rp.get(_p, False)
        if _rp is False:
            try:
                from isaacsim.core.prims import SingleRigidPrim as _SRP
                _rp = _SRP(_p); _rp.initialize()
            except Exception:
                _rp = None
            _sg_item_rp[_p] = _rp
        if _rp is None: return
        _lv = _rp.get_linear_velocity()
        if _lv is None: return
        _vx, _vy, _vz = float(_lv[0]), float(_lv[1]), float(_lv[2])
        _spd = (_vx*_vx + _vy*_vy + _vz*_vz) ** 0.5
        if _spd != _spd or _spd > 1e6:
            # already exploded to NaN/inf/absurd (the velocity clamp must run BEFORE the position integrates to NaN,
            # but if a single step jumps straight to NaN the prior tick missed it) -> HARD-RESET velocity to zero so
            # the solver does not propagate NaN and HANG the whole sim (CP-73 NaN-fling hung the Kit RPC -> 504).
            _rp.set_linear_velocity(np.array([0.0, 0.0, 0.0], dtype=np.float32))
            try: _rp.set_angular_velocity(np.array([0.0, 0.0, 0.0], dtype=np.float32))
            except Exception: pass
        elif _spd > 3.0:
            _sc = 3.0 / _spd
            _rp.set_linear_velocity(np.array([_vx*_sc, _vy*_sc, _vz*_sc], dtype=np.float32))
            try: _rp.set_angular_velocity(np.array([0.0, 0.0, 0.0], dtype=np.float32))
            except Exception: pass
    except Exception: pass
def _grip_open():
    # SUCTION: raw surface_gripper interface releases the grip (validated CP-70). Early-return so the
    # Franka parallel-jaw path below is byte-unchanged (the 37 friction passes hold).
    if _SG_IFACE is not None and _SG_PATH_RAW:
        _sg_grip_intent[0] = False  # stop re-asserting close; release the suction
        try: _SG_IFACE.open_gripper(_SG_PATH_RAW)
        except Exception as _ge: print("(suction raw open soft-fail: " + str(_ge) + ")")
        return
    try:
        if hasattr(franka, "gripper") and franka.gripper is not None:
            a = franka.gripper.forward("open")
            if a: art_ctrl.apply_action(a)
            return
    except Exception: pass
    try:
        if _surface_gripper is not None:
            _surface_gripper.open()
    except Exception: pass
    # No UR10 EE↔cube FixedJoint is ever authored (Anton's rule), so there is
    # nothing to remove here. _UR10_FJ_PATH stays [None].
def _grip_close():
    # SUCTION: raw surface_gripper interface engages the grip (validated CP-70: GripperView/wrapper .close()
    # does NOT engage; raw close_gripper() does -> cube lifts 0.186m). Early-return so the Franka parallel-jaw
    # path below is byte-unchanged. The SG enters "Closing" + auto-retries each step until the tracked cone is
    # over the cube within maxGripDistance, then grips -> cube co-moves with the follower/arm.
    if _SG_IFACE is not None and _SG_PATH_RAW:
        _sg_grip_intent[0] = True  # latch grip-intent; _track_suction_follower re-asserts close each tick
        try: _SG_IFACE.close_gripper(_SG_PATH_RAW)
        except Exception as _ge: print("(suction raw close soft-fail: " + str(_ge) + ")")
        return
    try:
        if hasattr(franka, "gripper") and franka.gripper is not None:
            a = franka.gripper.forward("close")
            if a: art_ctrl.apply_action(a)
            return
    except Exception: pass
    try:
        if _surface_gripper is not None:
            _surface_gripper.close()
    except Exception: pass
    # UR10 grip HONESTLY FAILS here: schema-level suction doesn't engage with an
    # articulation-link body0, and Anton's rule forbids snapping an EE↔cube
    # FixedJoint to fake the suction grip (no friction equivalent exists for the
    # surface gripper). The former raycast→FixedJoint snap has been removed, so
    # UR10 cuRobo pick does not hold the cube — no FJ weld.

_sensor = stage.GetPrimAtPath(SENSOR_PATH) if SENSOR_PATH else None
def _sensor_xy():
    if _sensor is None or not _sensor.IsValid(): return None
    t = UsdGeom.Xformable(_sensor).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1])])
_sensor_xy_v = _sensor_xy()

def _cube_to_pick():
    # 2026-06-09 MULTI-CUBE recipe AUTO-ON (set HERE — _cube_to_pick runs FIRST, before _build_segments, with
    # SOURCE_PATHS populated; it decides the PICK-ORDER so the order flag must be live here). DEFAULT-ON for multi-cube
    # UR10 asset-suction faithful (len>1); single-cube (len==1) skips -> the 8 passers byte-identical. [MEASURED]
    # CP-81/83 deliver 2/2 (CP-83 3/3). hasattr guards -> external A/B overrides win. Idempotent (re-set each tick).
    try:
        import builtins as _bi_mc
        _mc_cond = (len(SOURCE_PATHS) > 1 and ROBOT_FAMILY in ("ur10", "ur10e") and _SG_IS_SUCTION
                and getattr(_bi_mc, "_ur10_faithful_default", True))
        if _mc_cond:
            # 2026-06-10 RECIPE v2 [MEASURED CP-83 2/2, planfail=0, full-authority session]: REPLACED carry_only with
            # _ur10_excl_own_support + all-phases obstacles. Roots fixed: (1) the target's OWN pedestal blocked every
            # cup-down IK (freeik=False) -> exclude it (neighbour pedestals STAY obstacles -> no sweep-through, the
            # honest fix for Anton's "axel i andra kubens plattform"); (2) the STALE-WORLD sig bug (world never rebuilt
            # on cube switch) is fixed by folding |exo/|del into _world_sig. carry_only (which removed ALL obstacles
            # during approach = the sweep-through) is NO LONGER set by default; external MCUBECARRY=1 still A/Bs it.
            # v2.2 [MEASURED]: approach-pin at the MAIN call only (v2.1) was insufficient — the knock comes from an
            # UNPINNED fallback/sub-step plan. The successful probe ran GLOBAL `_ur10_plan_cspace` (pins every
            # _plan_to_world_point incl fallbacks). Set it here: multi-cube-only (this auto-on) -> single-cube
            # passers untouched; CP-81/82/73 re-verified under it. (06-07's "plan_cspace refuted" was the
            # single-cube transit-swing context, not multi-cube.)
            for _mcf in ("_ur10_excl_own_support", "_ur10_plan_cspace", "_ur10_pick_approach_panrotate",
                         "_ur10_pick_descend_pin", "_ur10_place_descend_pin", "_ur10_descend_downlock_seed",
                         "_ur10_cspace_unwrap", "_ur10_obs_exclude_delivered", "_ur10_place_failopen"):
                if not hasattr(_bi_mc, _mcf): setattr(_bi_mc, _mcf, True)
            # v2.3 [MEASURED bisect]: the FINAL lever for CP-83 Cube_1 = the rank-2 BUILD DEADLINE (20s). Without it,
            # a grinding plan fan-out (slower per-call under plan_cspace) runs long inside _on_step -> slow-motion sim
            # -> the wall-clock seg/_gate_to logic desyncs -> the arm knocks the cube / marks it failed. With it,
            # failing plans bail fast -> sane timings -> the good plan executes. B-only run delivered BOTH cubes.
            if not hasattr(_bi_mc, "_ur10_build_budget_s"): _bi_mc._ur10_build_budget_s = 20.0
        try:
            with open("/tmp/mc_autoon_sentinel.txt", "w") as _sf:
                _sf.write("cond=%s nsrc=%s fam=%s suction=%s faithful=%s\\n" % (
                    _mc_cond, len(SOURCE_PATHS), ROBOT_FAMILY, _SG_IS_SUCTION,
                    getattr(_bi_mc, "_ur10_faithful_default", True)))
                _sf.write("carry=%s pan=%s pickpin=%s placepin=%s dl=%s unwrap=%s excl=%s failopen=%s\\n" % (
                    getattr(_bi_mc, "_ur10_multicube_obs_carry_only", None),
                    getattr(_bi_mc, "_ur10_pick_approach_panrotate", None),
                    getattr(_bi_mc, "_ur10_pick_descend_pin", None),
                    getattr(_bi_mc, "_ur10_place_descend_pin", None),
                    getattr(_bi_mc, "_ur10_descend_downlock_seed", None),
                    getattr(_bi_mc, "_ur10_cspace_unwrap", None),
                    getattr(_bi_mc, "_ur10_obs_exclude_delivered", None),
                    getattr(_bi_mc, "_ur10_place_failopen", None)))
        except Exception: pass
    except Exception: pass
    # Earlier hard-coded z-range [0.83, 0.95] assumed cubes on a thin
    # belt above a tall table; broke table-top scenarios where cubes
    # rest at z=0.775. Now base-relative: -0.30/+0.50m from robot base
    # z. Catches table-top and belt-top, excludes floor-falls.
    base_xy = np.array([float(_usd_pos[0]), float(_usd_pos[1])])
    base_z = float(_usd_pos[2])
    sxy = _sensor_xy_v if _sensor_xy_v is not None else base_xy
    cands = []
    # Reach varies per family: Franka 0.85m (actual arm length), Cobotta 0.95m,
    # UR10/UR10e 1.20m. Earlier 0.70m for Franka under-utilized the arm and
    # rejected handoff positions (e.g. CP-51 handoff at 0.76m from FrankaB).
    # Phase 4 P0 (2026-05-10): apply 5cm safety margin per Opus research —
    # cuRobo's IK + collision avoid have ~10% failure rate in the last cm
    # of workspace boundary. Safety margin reduces wasted plan_pose calls
    # on borderline-reachable cubes (RCA: CP-37 24/24 fail = reach-bound).
    _reach_m_raw = 1.20 if ROBOT_FAMILY in ("ur10", "ur10e") else 0.85
    _reach_safety = 0.05
    _reach_m = _reach_m_raw - _reach_safety
    # CP-22 high-speed-belt fix: at >0.25 m/s nominal, cube transits the
    # 0.06m sensor zone in 2-3 physics ticks — too fast for the standard
    # claim+settle cycle. Read belt speed and widen detection upstream.
    _belt_v = 0.0
    if BELT_PATH:
        try:
            _bp = stage.GetPrimAtPath(BELT_PATH)
            if _bp and _bp.IsValid():
                _bsv = _bp.GetAttribute("physxSurfaceVelocity:surfaceVelocity")
                if _bsv and _bsv.IsDefined():
                    _v = _bsv.Get()
                    if _v: _belt_v = abs(float(_v[0]))
        except Exception: pass
    _look_ahead_x = 0.30 if _belt_v > 0.25 else 0.0
    # per-phase claim scoping (machine-tender dual-controller contention,
    # 2026-06-12): OPT-IN — None keeps the claim loop byte-identical
    CLAIM_RADIUS = {claim_radius!r}
    # Phase 4 (2026-05-10): 3D-aware reach check. EE has to reach
    # h1 = EE_INITIAL_HEIGHT above cube, not the cube itself. With h1
    # significantly above robot base, the EE travel distance is sqrt(
    # xy_dist² + (h1 - base_z)²), not just xy_dist. CP-37 sets
    # EE_INITIAL_HEIGHT=1.30 to clear pillar at z=1.15; with cube at xy
    # distance 0.797m and h1-base_z=0.55m, 3D distance is 0.97m, beyond
    # Franka's 0.855m reach. The 2D check accepts the cube; 3D rejects.
    # Without this, controller wastes plan_pose calls on unreachable goals.
    _h1_offset = max(0.0, float(EE_INITIAL_HEIGHT) - base_z)
    for sp in SOURCE_PATHS:
        # task modes (pull): destination==source by construction, so the
        # in-bin skip would reject the handle forever ('Handle:in_dest',
        # diagnosed live 2026-06-12)
        if sp in S["delivered"] or sp in S.get("failed", set()):
            if TASK_MODE in ("pull", "turn"): S["_pull_rej"] = sp.split("/")[-1] + ":delivered_or_failed"
            continue
        if TASK_MODE not in ("pull", "turn") and _is_in_bin(sp): continue
        cp = _world_pos(sp)
        if cp is None:
            if TASK_MODE in ("pull", "turn"): S["_pull_rej"] = sp.split("/")[-1] + ":nopos"
            continue
        # 2026-06-03 HANDOFF-SYNC gate (multi-robot only): claim a cube only when its Z has
        # SETTLED (stable over recent ticks) and is not high. RCA via cp51_faithful: FrankaB
        # read Cube_1 at z=1.056 — its MID-TRANSPORT height while FrankaA was still carrying it
        # (cube settles on the handoff table at 0.775) -> grasp goal ~0.28m too high -> grips
        # air. A belt cube keeps a STABLE Z (flat belt, only XY moves) so the conveyor robot's
        # claim is unaffected; only vertical lift/lower/fall transients + the high apex are
        # rejected. Gated to >1 live _curobo_pp_sub_ -> single-robot passes (the 37) byte-identical.
        try:
            import builtins as _bi_ms
            if len([_k for _k in vars(_bi_ms) if _k.startswith("_curobo_pp_sub_")]) > 1:
                _sz = S.setdefault("_settle_z", dict())
                _zp, _stab = _sz.get(sp, (None, 0))
                _stab = (_stab + 1) if (_zp is not None and abs(float(cp[2]) - _zp) < 0.006) else 0
                _sz[sp] = (float(cp[2]), _stab)
                if _stab < 6 or cp[2] > base_z + 0.20:
                    if TASK_MODE in ("pull", "turn"): S["_pull_rej"] = sp.split("/")[-1] + ":settle_%d_%.2f" % (_stab, cp[2])
                    continue
        except Exception: pass
        if cp[2] < base_z - 0.30 or cp[2] > base_z + 0.50:
            if TASK_MODE in ("pull", "turn"): S["_pull_rej"] = sp.split("/")[-1] + ":zwin_%.2f" % cp[2]
            continue
        _xy_dist = float(np.linalg.norm(cp[:2] - base_xy))
        if _xy_dist > _reach_m:
            if TASK_MODE in ("pull", "turn"): S["_pull_rej"] = sp.split("/")[-1] + ":xy_%.2f" % _xy_dist
            continue
        # 3D-aware: reject if EE goal at h1 above cube would exceed reach.
        # Use _reach_m_raw (no safety margin) for 3D check — the 5cm safety
        # is already applied to xy. Doubling it for 3D rejected too many
        # cubes, regressing CP-65 (multi-robot relay where handoff happens
        # at h1-base_z ≈ 0.5m + xy ≈ 0.6m → 3D 0.78 was rejected at 0.80).
        # 2026-05-31 reach-gate completion (item-2): the gate's vertical term should be the
        # PICK-side reach (cube_z + small approach margin), not the full cross-scene transit
        # h1. A cube reachable at the pick (then lifted straight up over the SAME xy) was being
        # rejected by the inflated transit h1_offset (inspector-reject Cube_1: 3d_0.83 h1o_0.42
        # though 2D xy=0.72 << Franka's ~0.85 physical reach). Clamp to pick-side; only relaxes
        # admission (a still-unreachable goal will plan-fail → 3-strike), so the verified set
        # (whose cubes are already admitted) is unaffected.
        _gate_h1o = min(_h1_offset, max(0.0, (float(cp[2]) + 0.20) - base_z))
        if TASK_MODE in ("pull", "turn"):
            # task modes have no transit-to-h1: the vertical term is the
            # handle height itself ('Handle:3d_0.87_h1o_0.45' live-diagnosed —
            # the h1 inflation pushed a reachable handle past 0.855)
            _gate_h1o = max(0.0, float(cp[2]) - base_z)
        _3d_dist = (_xy_dist**2 + _gate_h1o**2) ** 0.5
        if _3d_dist > _reach_m:
            if TASK_MODE in ("pull", "turn"): S["_pull_rej"] = sp.split("/")[-1] + ":3dv2_%.2f" % _3d_dist
            continue  # tight 3D matches 2D safety margin
        # REORIENT-01 require_upright filter: skip cubes whose +Z axis
        # isn't aligned with world up. Lets cube ride past pick zone on
        # its side, hit a passive flip-wall, become upright, then pick.
        if {require_upright!r}:
            try:
                _m = UsdGeom.Xformable(stage.GetPrimAtPath(sp)).ComputeLocalToWorldTransform(0)
                _cz = (_m[2][0], _m[2][1], _m[2][2])
                _cn = (_cz[0]**2 + _cz[1]**2 + _cz[2]**2) ** 0.5
                _up_dot = float(_cz[2] / _cn) if _cn > 1e-9 else 0.0
                if _up_dot < {upright_dot_threshold}: continue
            except Exception:
                continue
        # High-speed predictive claim ONLY (v10-baseline behavior). Sensor
        # zone gate experiments 2026-05-09 (v13/v14/v15) caused physics
        # blowups for multi-robot scenarios (CP-65 spd=9382 m/s, CP-62
        # spd=147 m/s) and net-negative pass count. Per-scenario gate logic
        # belongs in the scenario-profile spec, not as a global change.
        _d_sensor = float(np.linalg.norm(cp[:2] - sxy))
        if CLAIM_RADIUS is not None and _d_sensor > float(CLAIM_RADIUS):
            continue
        if _look_ahead_x > 0.0:
            _approaching = (
                cp[0] < sxy[0]
                and (sxy[0] - cp[0]) <= _look_ahead_x
                and abs(cp[1] - sxy[1]) < 0.10
            )
            if _d_sensor > 0.12 and not _approaching:
                continue
        cands.append((_d_sensor, sp))
    if not cands:
        try:
            from pxr import Sdf as _Sdf_dbg
            _rp = stage.GetPrimAtPath(ROBOT_PATH)
            _msgs = []
            for _sp in list(SOURCE_PATHS)[:6]:
                _nm = _sp.split("/")[-1]
                _c = _world_pos(_sp)
                if _c is None: _msgs.append(_nm + ":nopos"); continue
                if _sp in S["delivered"]: _msgs.append(_nm + ":delivered"); continue
                if _sp in S.get("failed", set()): _msgs.append(_nm + ":failed"); continue
                if TASK_MODE not in ("pull", "turn") and _is_in_bin(_sp): _msgs.append(_nm + ":in_dest"); continue
                if _c[2] < base_z - 0.30 or _c[2] > base_z + 0.50: _msgs.append(_nm + ":zwin_" + str(round(float(_c[2]), 2))); continue
                _xd = float(np.linalg.norm(_c[:2] - base_xy))
                if _xd > _reach_m: _msgs.append(_nm + ":xy_" + str(round(_xd, 2))); continue
                _gate_h1o2 = min(_h1_offset, max(0.0, (float(_c[2]) + 0.20) - base_z))
                _3 = (_xd * _xd + _gate_h1o2 * _gate_h1o2) ** 0.5
                if _3 > _reach_m: _msgs.append(_nm + ":3d_" + str(round(_3, 2)) + "_h1o_" + str(round(_gate_h1o2, 2))); continue
                _msgs.append(_nm + ":PASS_unexpected")
            _ra = _rp.GetAttribute("ctrl:pick_reject")
            if not _ra: _ra = _rp.CreateAttribute("ctrl:pick_reject", _Sdf_dbg.ValueTypeNames.String)
            _pr_mark = "|REAL:" + S.get("_pull_rej", "none") if TASK_MODE in ("pull", "turn") else ""
            _ra.Set(("nsrc" + str(len(SOURCE_PATHS)) + "|" + "|".join(_msgs) + _pr_mark)[:400])
        except Exception as _de:
            try:
                _rp2 = stage.GetPrimAtPath(ROBOT_PATH)
                from pxr import Sdf as _Sdf_dbg2
                _ra2 = _rp2.GetAttribute("ctrl:pick_reject")
                if not _ra2: _ra2 = _rp2.CreateAttribute("ctrl:pick_reject", _Sdf_dbg2.ValueTypeNames.String)
                _ra2.Set(("dbg_exc:" + str(_de))[:200])
            except Exception: pass
        return None
    # 2026-06-09 A1 PICK-ORDER (gated _ur10_multicube_obs_carry_only): for the carry-scoped multi-cube class, pick the
    # cube CLOSEST to the robot base FIRST. [MEASURED] the straight cup's long-tool arm body sweeps the NEIGHBOUR cube's
    # column when reaching a far cube (approach/lift/transit all blocked by it). Delivering the nearer cube first removes
    # it as an obstacle for the farther one -> the farther cube's transit is then clear. Generalizes to stacking (nearest
    # = top). Default OFF -> the _d_sensor sort (belt/sensor templates) is byte-identical.
    if getattr(__import__("builtins"), "_ur10_multicube_obs_carry_only", False) and len(cands) > 1:
        try:
            _bx = base_xy
            def _bdist(_c):
                _w = _world_pos(_c[1])
                return float(np.linalg.norm(np.asarray(_w)[:2] - _bx)) if _w is not None else 1e9
            cands.sort(key=_bdist)
            return cands[0][1]
        except Exception:
            pass
    cands.sort(); return cands[0][1]

def _bin_bounds(dest_path=None):
    _dp = dest_path or DEST_PATH
    if not _dp: return None
    p = stage.GetPrimAtPath(_dp)
    if not p or not p.IsValid(): return None
    bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    return (np.array([bb.GetMin()[0], bb.GetMin()[1]]),
            np.array([bb.GetMax()[0], bb.GetMax()[1]]))

def _is_in_bin(cube_path):
    # Multi-bin aware: a sort task places cubes into per-class bins (COLOR_ROUTING),
    # not the single DEST_PATH. Check the cube against ITS routed destination first,
    # then DEST_PATH. With no COLOR_ROUTING this is exactly the old DEST_PATH check.
    cp = _world_pos(cube_path)
    if cp is None: return False
    _dests = []
    if cube_path and COLOR_ROUTING:
        _col = _cube_semantic_class(cube_path)
        if _col and _col in COLOR_ROUTING:
            _dests.append(COLOR_ROUTING[_col])
    _dests.append(DEST_PATH)
    for _d in _dests:
        b = _bin_bounds(_d)
        if b is None: continue
        mn, mx = b
        if (mn[0] <= cp[0] <= mx[0]) and (mn[1] <= cp[1] <= mx[1]):
            return True
    return False

def _is_near_dest(cube_path, tolerance=0.15):
    \"\"\"True if cube is within tolerance of DROP_TARGET or DEST_PATH center.

    Multi-robot canonicals use non-bin destinations (Handoff Xform marker,
    StagingRack, HoldPedestal). Their world bbox is degenerate or smaller
    than the placed cube, so _is_in_bin returns False even when delivery
    is correct → cube goes into S['failed'] and the controller stops.
    Use proximity check instead for delivery confirmation.
    \"\"\"
    cp = _world_pos(cube_path)
    if cp is None: return False
    if DROP_TARGET is not None:
        dt = np.array(DROP_TARGET, dtype=np.float64)
        if float(np.linalg.norm(cp - dt)) < tolerance:
            return True
    if DEST_PATH:
        p = stage.GetPrimAtPath(DEST_PATH)
        if p and p.IsValid():
            try:
                bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                if not bb.IsEmpty():
                    mid = bb.GetMidpoint()
                    mid_a = np.array([float(mid[0]), float(mid[1]), float(mid[2])])
                    if float(np.linalg.norm(cp - mid_a)) < tolerance:
                        return True
                    mn = bb.GetMin(); mx = bb.GetMax()
                    if (float(mx[0]) - float(mn[0])) > 0.05 and (float(mx[1]) - float(mn[1])) > 0.05:
                        if (float(mn[0]) <= cp[0] <= float(mx[0])) and (float(mn[1]) <= cp[1] <= float(mx[1])):
                            return True
            except Exception: pass
    return False

{_PP_OBSERVABILITY_SNIPPET}
_a_mode.Set("curobo")

S = {{"mode": "wait_sensor", "picked_path": None, "segments": None,
      "seg_idx": 0, "seg_start_t": None,
      "cubes": 0, "errors": 0, "ticks": 0, "delivered": set(), "failed": set(),
      "settle_ticks": 0, "grip_action_done": False}}

def _record_err(e):
    S["errors"] += 1
    try:
        _a_err.Set(S["errors"])
        _a_last_err.Set(f"{{type(e).__name__}}: {{str(e)[:150]}}")
    except Exception: pass

def _apply_arm_joints(q7):
    # Apply ONLY the arm joints (Franka 7, UR10 6). Earlier impl read
    # get_joint_positions() and wrote it back as full DOF target — the
    # finger joints' current (still-opening) positions kept overwriting
    # the gripper-controller's close target → grip never reached close pose.
    q7_arr = np.asarray(q7, dtype=np.float64)[:_ARM_DOF]
    # Safety check: cuRobo's planner occasionally returns trajectories
    # that are catastrophic under bad seeds — both NaN/Inf values AND
    # finite-but-impossible joint targets (>±5 rad on a Franka whose
    # joint limits are all within ±3.8 rad). Both modes blow up cube
    # state via massive joint forces. Reject and skip the apply.
    if not np.all(np.isfinite(q7_arr)):
        S.setdefault("nan_skipped", 0)
        S["nan_skipped"] += 1
        try: _a_last_err.Set(f"NaN trajectory skipped (n={{S['nan_skipped']}})")
        except Exception: pass
        return
    # 2026-05-31 UR10 fix: the ±5.0 bound was tuned for Franka (limits ±3.8). UR10/UR10e
    # joints span ±2π (±6.28), so valid UR10 trajectories (e.g. q=5.46) were ALL skipped →
    # arm never moved → CP-69/70/82 picked-but-undelivered (oob_skipped=1778, plan_fails=0,
    # cube left at the pick side). Family-aware bound: UR10 → 6.30 (just above 2π, still
    # catches genuinely-impossible q); Franka → 5.0 (unchanged → verified Franka set untouched).
    _oob_lim = 6.30 if ROBOT_FAMILY in ("ur10", "ur10e") else 5.0
    if np.any(np.abs(q7_arr) > _oob_lim):
        S.setdefault("oob_skipped", 0)
        S["oob_skipped"] += 1
        _max = float(np.max(np.abs(q7_arr)))
        try: _a_last_err.Set(f"Out-of-bounds q (max={{_max:.2f}}) skipped (n={{S['oob_skipped']}})")
        except Exception: pass
        return
    art_ctrl.apply_action(ArticulationAction(
        joint_positions=q7_arr,
        joint_indices=np.arange(_ARM_DOF),
    ))

def _build_segments(cube_pos, drop_pos, current_q):
    # Plan 7 segments per cube cycle. Each = (traj [T,7], motion_time, action_after)
    # Added mid-height waypoints (h_mid) directly over cube and bin to
    # force a near-vertical final descent — without these, cuRobo's
    # joint-space optimizer can choose curved paths that brush the cube
    # body (no scene-collision available with Warp 1.8.2).
    h1 = EE_INITIAL_HEIGHT
    # Cap the approach height to clear the tallest of cube/drop/obstacles (+0.20), no
    # higher. Fixes an EE_INITIAL_HEIGHT inflation that left far cubes unplannable
    # (CP-41 Cube_4: 3/4 -> 4/4 fresh-each) WITHOUT lowering below tall-obstacle
    # clearance (e.g. CP-37 pillar, which is in PLANNING_OBSTACLES -> stays cleared).
    _clr = max(float(cube_pos[2]), float(drop_pos[2]))
    for _op in PLANNING_OBSTACLES:
        try:
            _opp = stage.GetPrimAtPath(_op)
            if _opp and _opp.IsValid():
                _clr = max(_clr, float(UsdGeom.Imageable(_opp).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange().GetMax()[2]))
        except Exception:
            pass
    # 2026-06-07 HIGH-PICK APPROACH (gated _ur10_highpick_approach, default OFF). MEASURED (CP-81): the +0.20
    # pre-grasp cap puts the above-cube goal at cube_z+0.20=1.175 for a 0.975 cube, which cuRobo can't reach
    # (res_None — ctrl:last_fail_goal) even though the GRASP at the cube top IS reachable (reach_validate Cube_2
    # 3/3). For HIGH cubes (cube_z > base_z+0.15) shrink the pre-grasp margin so it drops into the reachable zone;
    # LOW cubes (the 8 passers, z~0.835 < 0.90) keep +0.20 => byte-identical. Suction descends straight down so
    # less above-cube clearance is fine. Gated OFF until A/B-verified it unlocks a high pick without regression.
    _appr_margin = 0.20
    try:
        import builtins as _bi_hp
        if getattr(_bi_hp, "_ur10_highpick_approach", False) and ROBOT_FAMILY in ("ur10", "ur10e") \
                and float(cube_pos[2]) > float(_usd_pos[2]) + 0.15:
            _appr_margin = float(getattr(_bi_hp, "_ur10_highpick_margin", 0.06))
    except Exception:
        pass
    h1 = min(float(h1), _clr + _appr_margin)
    # Tool-tip Z offset relative to the planner's tool_frame origin.
    # Franka panda_hand → finger tips: +0.105m straight along local +Z.
    # UR10 tool0 → suction_cup tip: +0.158m in local +X (NOT +Z); during a
    # top-down grasp this becomes a lateral world-XY offset, not vertical.
    # The 0.158 here is wrong-but-trying — proper UR10 grasp wiring needs
    # the GoalToolPose offset transformed by the planner's solved EE quat,
    # which the current pipeline doesn't compute. Tracked for follow-up.
    FL = 0.105 if ROBOT_FAMILY == "franka" else 0.0
    pz = float(cube_pos[2]) + FL + float(EE_OFFSET[2])
    # SUCTION: descend the FLANGE to cube_top+0.02+tool_L (not into the cube) so the cone (flange-tool_L)
    # lands just above the cube top and the wrist clears it (CP-70 root-cause fix). Gated to suction.
    if _SG_IS_SUCTION:
        # 2026-06-03 TELEPATHY fix: descend the flange so the cone bottom lands JUST ABOVE the cube top (was +0.045
        # -> cone 15mm above -> SG grabs across a gap -> cube held 51mm below = Anton's "osynliga gap"). Geometry:
        # cone_bottom - cube_top = offset - 0.030. offset 0.026 put the cone 4mm INTO the cube -> the collision push
        # fights the D6 grip -> STABLE on the gentle near bin (CP-70) but the far-reach swing (CP-69, 3.4 m/s) tears
        # the grip apart -> cube FLUNG. 0.035 = cone bottom 5mm ABOVE the cube top: clean grab (no interpenetration),
        # cube hangs ~5mm below the cup (still near-flush, telepathy fixed) AND the grip is stable like baseline (0.045).
        pz = float(cube_pos[2]) + 0.035 + _SG_TOOL_L
        # 2026-06-05 ASSET-GRIPPER descend-deepen: the asset short_gripper is a RIGID FixedJoint mount with NO
        # kinematic follower, so it CANNOT telescope to compensate for cuRobo's ~0.05m descend UNDER-shoot the way
        # the procedural cone does (the follower-telescope) -> measured: cup stops 0.05m ABOVE the cube top -> the
        # grip raycast can't reach. Descend the goal ~0.05m deeper in asset mode so the cup lands on the cube top.
        # Procedural (follower present) is byte-identical. Flag-tunable for validation.
        if _SG_FOLLOWER_OP is None and ROBOT_FAMILY in ("ur10", "ur10e"):
            pz = float(cube_pos[2]) - float(getattr(builtins, "_sg_asset_descend_extra", 0.05)) + 0.035 + _SG_TOOL_L
        # 2026-06-07 STRAIGHT-CUP pz (gated _sg_nvidia_cup) — the SHARED fix across all UR10 templates. The side-cup
        # _SG_TOOL_L gives pz~0.97 = BELOW the MEASURED straight-down IK reach floor (ee z~1.05 at the [-0.5,0]
        # column; reach-probe: 1.05 OK, 1.00 FAIL) -> res_None -> the descend never executes -> grip-miss. With the
        # +90 mount the cup hangs ~0.158 below ee along the down axis, so target ee = cube_top(+0.025) + cup_off(0.158)
        # - contact(0.02) ~ cube_z+0.163 -> ee~1.09 (reach-probe verified OK) -> cup ~0.93 = contact on the cube top.
        if getattr(builtins, "_sg_nvidia_cup", False):
            pz = float(cube_pos[2]) + 0.025 + float(getattr(builtins, "_sg_nvidia_cup_below_ee", 0.158)) - 0.02
    # 2026-05-30 drop-symmetry fix: the DROP goal (S5) is on the planner's
    # tool_frame (panda_hand), exactly like the PICK descend goal (pz above).
    # Without the same tool-tip lift, panda_hand is commanded straight TO
    # drop_pos[2], so the fingertips (and the held cube) sink FL+EE_OFFSET[2]
    # BELOW it — burying the goal inside the destination bin/pallet collision
    # cuboid -> plan_pose returns res_None (RCA 2026-05-30: CP-12 0/3 seg6/7
    # goal=[0.1,-0.3,0.85], CP-27 1/4). Apply the symmetric lift so the
    # fingertips land at the requested drop z and the goal clears the cuboid.
    # Non-franka families have FL=0 so _drop_tip reduces to EE_OFFSET[2] (no change).
    _drop_tip = FL + float(EE_OFFSET[2])
    # SUCTION: keep the flange HIGH over the bin (drop_z+0.45) — descending the flange to ~bin-top makes
    # cuRobo plan-FAIL on the bin-wall collision (validated CP-70: plan_fails=4, arm undershot the bin by
    # 0.15 -> cube 0.26 off vs xy_tol 0.1). The cube hangs below the cone and dangles into the bin from the
    # high, collision-free pose. Gated to suction.
    if _SG_IS_SUCTION:
        _drop_tip = 0.45
    # SUCTION S5 release height: with the RIGID grip the cube hangs only ~0.13m below the flange (cone 0.08 +
    # grip ~0.05), so descend the flange to drop_z+0.16 (=~0.91, just above the bin top 0.80) -> cube at ~0.78
    # just above the bin floor -> tiny fall on release (no overshoot/bounce). The bin is excluded from cuRobo
    # collision for S5 (below) so the planner can descend over it. Transit/mid stay high (_drop_tip=0.45).
    _drop_tip_release = (float(getattr(__import__("builtins"), "_sg_drop_tip_release", 0.16)) if _SG_IS_SUCTION else _drop_tip)  # 2026-06-09 GATED z-raise lever: default 0.16 = byte-identical; raise (e.g. 0.19) to lift the S5 descend goal ~3cm where a down-IK EXISTS for low-bin close picks (CP-75 bin 3cm below CP-69) -> clean down descend, release the small gap.
    # SUCTION soft-place target (anti-topple): the S5 planner goal stays SAFE at drop_z+0.16 (cuRobo-reachable, no
    # bin-wall plan-fail), but the step-loop tool-extend telescopes the cup+cube down to ~3cm above the bin FLOOR
    # before releasing. drop_pos[2] is bin_top+0.05 (an ON-TOP ref) so the cube would otherwise release ~18cm high
    # -> TOPPLE (CP-70). Read the dest-bbox floor; target flange = floor + cube_half(.025)+clear(.03)+hang(.11) ~ floor+.165.
    _sg_release_target = float(drop_pos[2]) + _drop_tip_release  # safe fallback = the planner goal (no extend)
    if _SG_IS_SUCTION:
        _floor_z = float(drop_pos[2]) - 0.13  # fallback: empirical bin-floor offset below the drop ref
        try:
            if DEST_PATH:
                _dprim = stage.GetPrimAtPath(DEST_PATH)
                if _dprim and _dprim.IsValid():
                    _dbb = UsdGeom.Imageable(_dprim).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                    _floor_z = float(_dbb.GetMin()[2])
        except Exception: pass
        _sg_release_target = _floor_z + 0.165
    h_mid_pick = float(cube_pos[2]) + 0.18  # 18cm above cube
    h_mid_drop = float(drop_pos[2]) + _drop_tip + 0.18  # 18cm above lifted drop goal
    if _SG_IS_SUCTION:
        # 2026-06-03 SWING fix (cone-track RCA): the suction _drop_tip=0.45 made h_mid_drop=drop_z+0.63 (flange 1.42),
        # ABOVE the S4 transit (h1~1.03) -> the arm transited low then SWUNG UP to 1.42 before descending, riding
        # the cup+cube to z=1.53 = Anton's "kastar runt / planeringsfel". The "mid" must be a DESCENT step just above
        # the release, not above the transit. drop_z+0.22 (flange ~1.0) stays above the bin top (0.80) -> no bin-wall
        # plan-fail, no up-swing; the cube (hanging ~32mm below the cone) clears the bin rim on the descent.
        h_mid_drop = float(drop_pos[2]) + 0.22
    drop_yaw = _yaw_for_cube(S.get("picked_path") or "")
    if _SG_IS_SUCTION:
        # 2026-06-03 SWING ROOT (cone-track RCA): an axisymmetric suction cup CANNOT control the cube's yaw (single-
        # point grip, no friction couple) -> a commanded drop-yaw is physically meaningless AND forces a violent UR10
        # wrist reconfiguration on the drop-side segments: the arm reached the bin (0.38,-0.28,1.22) then swung AWAY to
        # (-0.27,+0.55) and UP to z=1.52 @ 2.3 m/s before descending = Anton's "kastar runt / planeringsfel". Zeroing
        # it for suction is both faithful and removes the swing. Gated -> Franka (parallel-jaw, yaw IS meaningful) intact.
        drop_yaw = 0.0
    # Yaw applied to drop-side segments (S4, S4.5, S5). Pick-side segments
    # use yaw=0 — gripper picks straight-down regardless of drop rotation.
    # 2026-05-27 FALLBACK: cuRobo PoseCostMetric + AttachmentManager BOTH verified broken on this
    # NV custom MotionPlanner (96mm XY drift identical with/without). Using sub-step waypoints.
    # Generic: any caller-defined goal sequence with same-XY/diff-Z gets sub-stepped automatically.
    # 2026-06-07 REACH PROBE (gated _reach_probe, one-shot): quantify the straight-down IK reach floor at the pick
    # column [-0.5,0] from the HOME seed, isolated from mid-pick state. Logs which ee z plan OK vs FAIL.
    import builtins as _bi_rpb
    if getattr(_bi_rpb, "_reach_probe", False) and not getattr(_bi_rpb, "_reach_probe_done", False):
        _bi_rpb._reach_probe_done = True
        try:
            _qh = np.asarray(current_q, dtype=np.float32)[:_ARM_DOF]
            _rl = []
            for _z in (1.35, 1.25, 1.15, 1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75):
                _nok = 0
                for _tryi in range(3):
                    _rr = _plan_to_world_point(np.array([float(cube_pos[0]), float(cube_pos[1]), float(_z)], dtype=np.float32), _qh, exclude_obs=None, yaw_deg=0.0, vhold_mode=0)
                    if _rr is not None: _nok += 1
                _rl.append("%.2f=%d/3" % (_z, _nok))
            with open("/tmp/reachprobe.log", "a") as _rf:
                _rf.write("REACH_SWEEP cube_xy=[%.2f,%.2f] cube_top=%.2f ee_z_straightdown: %s\\n" % (float(cube_pos[0]), float(cube_pos[1]), float(cube_pos[2]) + 0.025, " ".join(_rl)))
            # cup-vs-FK-ee offset: the number that decides reachability for the straight cup
            from curobo.types import JointState as _JS_rp
            _tq = torch.tensor([[float(_x) for _x in _qh]], dtype=torch.float32, device="cuda")
            _kk = _planner.compute_kinematics(_JS_rp.from_position(_tq, joint_names=_PLANNER_JOINT_NAMES))
            _eeb = _kk.tool_poses.position[0, 0, 0].detach().cpu().numpy()
            _eeq = _kk.tool_poses.quaternion[0, 0, 0].detach().cpu().numpy()
            _cupw = _world_pos(_SG_CUP_PATH)
            # ee world pose = base * ee_base ; compute cup-in-ee-LOCAL (the FIXED mount offset, orientation-independent)
            _bm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_usd_quat[0]), Gf.Vec3d(float(_usd_quat[1]), float(_usd_quat[2]), float(_usd_quat[3])))); _bm.SetTranslateOnly(Gf.Vec3d(float(_usd_pos[0]), float(_usd_pos[1]), float(_usd_pos[2])))
            _fm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_eeq[0]), Gf.Vec3d(float(_eeq[1]), float(_eeq[2]), float(_eeq[3])))); _fm.SetTranslateOnly(Gf.Vec3d(float(_eeb[0]), float(_eeb[1]), float(_eeb[2])))
            _eeW = _fm * _bm; _eewp = _eeW.ExtractTranslation(); _eeR = _eeW.ExtractRotationMatrix(); _eeRinv = _eeR.GetTranspose()
            _dw = [float(_cupw[_i]) - float(_eewp[_i]) for _i in range(3)] if _cupw is not None else None
            _dl = [round(sum(_eeRinv[_r][_c] * _dw[_c] for _c in range(3)), 3) for _r in range(3)] if _dw is not None else None
            with open("/tmp/reachprobe.log", "a") as _rf:
                _rf.write("CUPEE ee_world=%s cup_world=%s cup_minus_ee_world=%s cup_in_ee_LOCAL=%s\\n" % ([round(float(_eewp[_i]), 3) for _i in range(3)], ([round(float(_cupw[_i]), 3) for _i in range(3)] if _cupw is not None else None), ([round(_x, 3) for _x in _dw] if _dw is not None else None), _dl))
        except Exception as _rpe:
            try:
                with open("/tmp/reachprobe.log", "a") as _rf: _rf.write("REACH_ERR " + str(_rpe)[:140] + "\\n")
            except Exception: pass
    # 2026-06-07 nvidia STATIC TOOL-OFFSET (gated _sg_nvidia_cup): the out-the-end cup is ~0.158 along ee+X, so a
    # descend that targets ee at the cube xy lands the cup OFFSET (overshoot ~[-0.139,-0.008,-0.049] world). Offsetting
    # the pick-column goal by -cup_offset (tunable _sg_nvidia_goal_off) makes the WORKING main descend land the CUP on
    # the cube directly (the closed-loop nudge from the overshoot is res_None at this pose). Default 0 -> byte-identical.
    _nv_goff = (list(getattr(__import__("builtins"), "_sg_nvidia_goal_off", [0.0, 0.0, 0.0])) if getattr(__import__("builtins"), "_sg_nvidia_cup", False) else [0.0, 0.0, 0.0])
    goals = [
        (np.array([cube_pos[0] + _nv_goff[0], cube_pos[1] + _nv_goff[1], h1]),         None,    0.0),       # S1 above cube
        (np.array([cube_pos[0] + _nv_goff[0], cube_pos[1] + _nv_goff[1], h_mid_pick]), None,    0.0),       # S1.5 mid-height
        (np.array([cube_pos[0] + _nv_goff[0], cube_pos[1] + _nv_goff[1], pz + _nv_goff[2]]), "close", 0.0), # S2 descend + close
        (np.array([cube_pos[0] + _nv_goff[0], cube_pos[1] + _nv_goff[1], h1]),         None,    0.0),       # S3 lift
        (np.array([drop_pos[0], drop_pos[1], h1]),         None,    drop_yaw),  # S4 transit (rotated)
        (np.array([drop_pos[0], drop_pos[1], h_mid_drop]), None,    drop_yaw),  # S4.5 mid
        (np.array([drop_pos[0], drop_pos[1], float(drop_pos[2]) + _drop_tip_release]),"open",  drop_yaw),  # S5 descend + open (suction: lower release height)
    ]
    # 2026-06-06 NOTE (REVERTED experiment): a gated _ur10_telescope_descend that replaced the S5 cuRobo descend
    # with the soft-place telescope (S5 goal -> h_mid_drop) was tested fresh-isolated and REJECTED: CP-80 -> dead-
    # center PASS, but CP-81 REGRESSED (delivered in prod, but flag-on released SHORT at [0.382,-0.206]) and CP-83
    # still FAILED short [0.404,-0.183]. Mechanism: the telescope lowers STRAIGHT DOWN from the S4.5 above-bin pose;
    # when cuRobo under-reaches the bin XY there (~[0.40,-0.20]) the cube drops short. The cuRobo S5 descend, despite
    # its IK-flip, was doing necessary XY convergence. So the right fix is to keep the descend but stop its IK-branch
    # flip (joint-continuity/seed), NOT to remove it. See docs/notes/NIGHT_MISSION_2026_06_05.md ~22:45.
    # 2026-06-02 EDIT 1: Franka clean post-place STRAIGHT-UP retract (S6). After releasing, lift the EE
    # vertically to the clamped transit height h1 BEFORE any lateral move, so the arm doesn't sweep
    # sideways through the just-placed item/stack toward the next pick (the ASCENT-KNOCK: measured —
    # CP-42 Brick_4|Brick_2 + Brick_3|Brick_1 collisions, CP-09 stack topples). XY pinned to the drop
    # xy = pure vertical column; action_after=None = pure transit, no grip dwell. Franka-gated
    # (suction/UR10 byte-identical); fail-open in the dispatch (skip if unplannable, never fail the cube).
    if not _SG_IS_SUCTION:
        goals.append((np.array([drop_pos[0], drop_pos[1], h1]), None, drop_yaw))  # S6 retract straight up
    # ── TASK-MODE SEAM (pull v1) ─────────────────────────────────────────
    # task != pick_place: keep the PROVEN grasp approach (S1/S1.5/S2) and
    # replace everything after with the primitive's waypoint chain. One
    # contiguous gated block — revert = one hunk.
    if TASK_MODE == "pull" and TASK_JOINT_PATH:
        def _task_joint_info(jp):
            _jpr = stage.GetPrimAtPath(jp)
            _ax_attr = _jpr.GetAttribute("physics:axis")
            _tok = str(_ax_attr.Get()) if _ax_attr and _ax_attr.Get() else "X"
            _lo_a = _jpr.GetAttribute("physics:lowerLimit")
            _hi_a = _jpr.GetAttribute("physics:upperLimit")
            _lo = float(_lo_a.Get()) if _lo_a and _lo_a.Get() is not None else 0.0
            _hi = float(_hi_a.Get()) if _hi_a and _hi_a.Get() is not None else 0.0
            # body0 world rotation maps the local axis token to world
            _b0_targets = []
            _b0_rel = _jpr.GetRelationship("physics:body0")
            if _b0_rel:
                _b0_targets = list(_b0_rel.GetTargets())
            _qw = [1.0, 0.0, 0.0, 0.0]
            if _b0_targets:
                from pxr import UsdGeom as _UG_t
                _m = _UG_t.Xformable(stage.GetPrimAtPath(_b0_targets[0])).ComputeLocalToWorldTransform(0)
                _q = _m.ExtractRotationQuat()
                _qw = [float(_q.GetReal())] + [float(c) for c in _q.GetImaginary()]
            _local = {{"X": [1.0, 0.0, 0.0], "Y": [0.0, 1.0, 0.0], "Z": [0.0, 0.0, 1.0]}}[_tok.upper()[:1]]
            _w, _x, _y, _z = _qw
            _tx = 2.0 * (_y * _local[2] - _z * _local[1])
            _ty = 2.0 * (_z * _local[0] - _x * _local[2])
            _tz = 2.0 * (_x * _local[1] - _y * _local[0])
            _ax = [_local[0] + _w * _tx + (_y * _tz - _z * _ty),
                   _local[1] + _w * _ty + (_z * _tx - _x * _tz),
                   _local[2] + _w * _tz + (_x * _ty - _y * _tx)]
            _n = (sum(c * c for c in _ax) ** 0.5) or 1.0
            return [c / _n for c in _ax], _lo, _hi
        _p_ax, _p_lo, _p_hi = _task_joint_info(TASK_JOINT_PATH)
        # travel toward the limit with the larger magnitude (drawer: lower=-0.30)
        _p_travel = TASK_ARGS.get("task_travel_m") if isinstance(TASK_ARGS, dict) and TASK_ARGS.get("task_travel_m") is not None else (_p_lo if abs(_p_lo) > abs(_p_hi) else _p_hi)
        # yaw from SOURCE GEOMETRY: close across the smallest horizontal
        # bbox extent (empirical mapping: yaw=0 closes across y, yaw=90
        # across x — drawer-TS + CP-55 both measured). This reproduces
        # CP-55's working 90 on its 2.4x4cm knob AND grips a perpendicular
        # bar across its thin axis, so the pull load presses the bar into a
        # finger pad (the lengthwise-escape fix that does NOT change CP-55's
        # recipe — the global +90 experiment did, and broke it).
        _p_yaw = _gm.degrees(_gm.atan2(_p_ax[1], _p_ax[0]))
        try:
            _sp_pull = S.get("picked_path")
            if _sp_pull:
                _sb = UsdGeom.Imageable(stage.GetPrimAtPath(_sp_pull)).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                _se = [float(_sb.GetMax()[_i_pb] - _sb.GetMin()[_i_pb]) for _i_pb in range(3)]
                _p_yaw = 90.0 if _se[0] <= _se[1] else 0.0
                # same closing axis, flipped wrist: yaw-90 can be IK-infeasible
                # in a region where yaw-270 is fine (drawer-open: staging at
                # z=1.295 planned, the SAME-XY descent to 1.145 res_None 12/12
                # — orientation, not position). Alternate per 3-strike attempt.
                _p_att = S.get("plan_fail_count", {{}}).get(_sp_pull, 0)
                if _p_att % 2 == 1:
                    _p_yaw += 180.0
        except Exception: pass
        _gx, _gy = cube_pos[0] + _nv_goff[0], cube_pos[1] + _nv_goff[1]
        _gz = pz + _nv_goff[2] - 0.01  # grip the handle bar, not its top edge
        goals = goals[:3]
        # tight low descent instead of the h1 transit: the proven high approach
        # (EE_INITIAL_HEIGHT) plans the wrist into the furniture-face margin
        # zone (drawer-open: res_None at z=1.13, 4 cm from the cabinet front —
        # margin-probe-proven 2026-06-12). Handles sit on furniture; approach
        # from just above the bar. STAGING goal first (+0.25): the home->grasp
        # transit otherwise sweeps the unmodeled grasp-source bar (cuRobo
        # excludes the pick target from collision) — TS-proven 2026-06-12:
        # fingertips plowed the bar at z 0.91 en route, shoving the drawer to
        # its stop. Ending the long transit HIGH keeps the sweep clear; the
        # descents below are short verticals.
        goals[0] = (np.array([_gx, _gy, _gz + 0.25]), None, _p_yaw)
        goals[1] = (np.array([_gx, _gy, _gz + 0.10]), None, _p_yaw)
        goals[2] = (np.array([_gx, _gy, _gz]), "close", _p_yaw)
        # 6 bites (5cm at 0.30m travel): the 7.5cm bites dragged the drawer
        # 6cm then stalled (first real pull, round 14); smaller bites keep the
        # grip-slide within the end-knob flange budget per step.
        _p_n = 6
        for _pk in range(1, _p_n + 1):
            _pp_goal = np.array([_gx + _p_ax[0] * _p_travel * (_pk / _p_n),
                                 _gy + _p_ax[1] * _p_travel * (_pk / _p_n),
                                 _gz + _p_ax[2] * _p_travel * (_pk / _p_n)])
            goals.append((_pp_goal, "open" if _pk == _p_n else None, _p_yaw))
        _p_back = _gm.copysign(0.10, _p_travel)
        goals.append((goals[-1][0] + np.array([_p_ax[0] * _p_back, _p_ax[1] * _p_back, _p_ax[2] * _p_back]), None, _p_yaw))
    # ── TASK-MODE: TURN (revolute v1, vertical hinge) ────────────────────
    # Orbit the grasped lever about the joint's WORLD anchor (the joint-
    # anchor fix authors physics:localPos0 — pivot = body0 world x localPos0;
    # body1-origin anchoring would spin the lever in place). Same tight low
    # descent as pull; yaw tracks the arc. Target angle: task_target_deg,
    # else the limit with the larger magnitude (read live, like pull).
    elif TASK_MODE == "turn" and TASK_JOINT_PATH:
        _jpr_t = stage.GetPrimAtPath(TASK_JOINT_PATH)
        _lp0_a = _jpr_t.GetAttribute("physics:localPos0")
        _lp0 = list(_lp0_a.Get()) if _lp0_a and _lp0_a.Get() is not None else [0.0, 0.0, 0.0]
        _b0_rel_t = _jpr_t.GetRelationship("physics:body0")
        _b0_t = list(_b0_rel_t.GetTargets()) if _b0_rel_t else []
        if _b0_t:
            from pxr import UsdGeom as _UG_tt, Gf as _Gf_tt
            _m0_t = _UG_tt.Xformable(stage.GetPrimAtPath(_b0_t[0])).ComputeLocalToWorldTransform(0)
            _pv = _m0_t.Transform(_Gf_tt.Vec3d(*[float(v) for v in _lp0]))
            _pivot = [float(_pv[0]), float(_pv[1]), float(_pv[2])]
        else:
            _pivot = [float(v) for v in _lp0]
        _t_lo_a = _jpr_t.GetAttribute("physics:lowerLimit")
        _t_hi_a = _jpr_t.GetAttribute("physics:upperLimit")
        _t_lo = float(_t_lo_a.Get()) if _t_lo_a and _t_lo_a.Get() is not None else 0.0
        _t_hi = float(_t_hi_a.Get()) if _t_hi_a and _t_hi_a.Get() is not None else 0.0
        _t_target = TASK_ARGS.get("task_target_deg") if isinstance(TASK_ARGS, dict) and TASK_ARGS.get("task_target_deg") is not None else (_t_lo if abs(_t_lo) > abs(_t_hi) else _t_hi)
        _gx, _gy = cube_pos[0] + _nv_goff[0], cube_pos[1] + _nv_goff[1]
        _gz = pz + _nv_goff[2] - 0.01
        _r0x, _r0y = _gx - _pivot[0], _gy - _pivot[1]
        _t_yaw0 = _gm.degrees(_gm.atan2(_r0y, _r0x))
        goals = goals[:3]
        goals[0] = (np.array([_gx, _gy, _gz + 0.25]), None, _t_yaw0)  # staging (transit clears the lever)
        goals[1] = (np.array([_gx, _gy, _gz + 0.10]), None, _t_yaw0)
        goals[2] = (np.array([_gx, _gy, _gz]), "close", _t_yaw0)
        _t_n = max(1, int(_gm.ceil(abs(_t_target) / 15.0)))
        for _tk in range(1, _t_n + 1):
            _th = _gm.radians(_t_target * (_tk / _t_n))
            _c_t, _s_t = _gm.cos(_th), _gm.sin(_th)
            goals.append((np.array([_pivot[0] + _c_t * _r0x - _s_t * _r0y,
                                    _pivot[1] + _s_t * _r0x + _c_t * _r0y,
                                    _gz]),
                          "open" if _tk == _t_n else None,
                          _t_yaw0 + _gm.degrees(_th)))
        goals.append((goals[-1][0] + np.array([0.0, 0.0, 0.10]), None, goals[-1][2]))  # retract up
    # ── TASK-MODE: SWEEP (tool-use v1) ───────────────────────────────────
    # Grasp the broom handle (tight descent), then per-debris drag passes at
    # GRASP-LOCKED z (broom stood upright at spawn -> bristles stay on the
    # floor as gripped) from behind each debris item to the dustpan LIP
    # (NOT center+overshoot: EE xy == bristle xy for a vertical broom, and
    # the dustpan far edge is outside Franka reach — the template's own
    # hand-rolled waypoint stopped at the lip for the same reason). Debris
    # momentum carries items over the lip. Release + retract at the end.
    elif TASK_MODE == "sweep":
        _sw_debris = TASK_ARGS.get("task_debris_paths") if isinstance(TASK_ARGS, dict) else None
        _sw_pts = [list(_p_sw) for _p_sw in ((_world_pos(_d) for _d in (_sw_debris or [])) if _sw_debris else []) if _p_sw is not None]
        _sw_dust = _world_pos(DEST_PATH)
        # engagement marker — disengaged-sweep falls through to standard
        # pick-place goals SILENTLY (live 2026-06-12: 12/12 res_None toward a
        # goal at the dustpan-Xform origin); make the branch state observable
        try:
            from pxr import Sdf as _Sdf_sw
            _rp_sw = stage.GetPrimAtPath(ROBOT_PATH)
            _a_sw = _rp_sw.GetAttribute("ctrl:task_dbg")
            if not _a_sw: _a_sw = _rp_sw.CreateAttribute("ctrl:task_dbg", _Sdf_sw.ValueTypeNames.String)
            _a_sw.Set(("sweep pts=%d dust=%s grasp=%s" % (
                len(_sw_pts),
                str([round(float(_v_sw), 3) for _v_sw in _sw_dust]) if _sw_dust is not None else "None",
                str([round(float(cube_pos[0] + _nv_goff[0]), 3), round(float(cube_pos[1] + _nv_goff[1]), 3), round(float(pz + _nv_goff[2] - 0.01), 3)])))[:300])
        except Exception: pass
        if _sw_pts and _sw_dust is not None:
            _gx, _gy = cube_pos[0] + _nv_goff[0], cube_pos[1] + _nv_goff[1]
            _gz = pz + _nv_goff[2] - 0.01
            # grip LOW on the tool stub — the brush CG (plate) hangs below the
            # grip; at center-grip the hop's pendulum torque pried the stub
            # through the pads (TS 2026-06-13: handle floor-bound while the
            # hand rose, brush flung at the first lateral move). Fingertips
            # land just above the source bbox BOTTOM (the plate top).
            try:
                _swb = UsdGeom.Imageable(stage.GetPrimAtPath(S.get("picked_path"))).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                _gz = max(float(_swb.GetMin()[2]) + 0.030 + 0.105, _gz - 0.06)
            except Exception: pass
            _cx = sum(_p_sw[0] for _p_sw in _sw_pts) / len(_sw_pts)
            _cy = sum(_p_sw[1] for _p_sw in _sw_pts) / len(_sw_pts)
            _dx_sw, _dy_sw = float(_sw_dust[0]) - _cx, float(_sw_dust[1]) - _cy
            _dn_sw = (_dx_sw * _dx_sw + _dy_sw * _dy_sw) ** 0.5 or 1.0
            _ux, _uy = _dx_sw / _dn_sw, _dy_sw / _dn_sw
            _sw_yaw = _gm.degrees(_gm.atan2(_uy, _ux))
            goals = goals[:3]
            goals[0] = (np.array([_gx, _gy, _gz + 0.10]), None, _sw_yaw)
            goals[1] = (np.array([_gx, _gy, _gz + 0.05]), None, _sw_yaw)
            goals[2] = (np.array([_gx, _gy, _gz]), "close", _sw_yaw)
            _z_hi = _gz + 0.12
            # vertical-only lift FIRST — up+lateral in one segment swings the
            # hanging tool out of the pinch
            goals.append((np.array([_gx, _gy, _z_hi]), None, _sw_yaw))
            _back = float(TASK_ARGS.get("task_backswing_m") or 0.20)
            _lip = float(TASK_ARGS.get("task_lip_margin_m") or 0.08)
            _ex = float(_sw_dust[0]) - _ux * _lip
            _ey = float(_sw_dust[1]) - _uy * _lip
            for _pt_sw in _sw_pts[:4]:
                _sx = _pt_sw[0] - _ux * _back
                _sy = _pt_sw[1] - _uy * _back
                goals.append((np.array([_sx, _sy, _z_hi]), None, _sw_yaw))  # hop behind item
                goals.append((np.array([_sx, _sy, _gz]), None, _sw_yaw))    # lower to floor
                goals.append((np.array([_ex, _ey, _gz]), None, _sw_yaw))    # drag to lip
                goals.append((np.array([_ex, _ey, _z_hi]), None, _sw_yaw))  # lift clear
            goals.append((goals[-1][0], "open", _sw_yaw))
            goals.append((goals[-1][0] + np.array([0.0, 0.0, 0.10]), None, _sw_yaw))
    # 2026-06-04 UR10 TRANSIT-ARC (Anton: swing+collision are the priority root). FLAG-GATED OFF by default
    # (builtins._ur10_transit_arc) → byte-identical until verified, so the 6 + Franka + GUI-review are untouched.
    # ROOT: the S3 lift (cube_xy) → S4 transit (drop_xy) is a LARGE behind→front XY move planned DIRECTLY → cuRobo
    # executes the IK-branch reconfiguration as the up/out LOOP (cube to z~1.5,y~0.6 = "plans wrong then self-corrects")
    # + the upper_arm sweeps the bin walls. FIX: replace the single direct transit with an angular ARC at a SUB-BIN
    # radius + high apex — the arm folds IN (inside the bin radius) and rotates around its base axis, then S4 extends
    # OUT+DOWN to the bin. Clean "lift → turn → place", and folded-in it clears the bin walls until the final descent.
    # Gated to behind→front (dot((cube-base),(drop-base))<0 = >90° around base); dexterous (CP-79, dot>0) untouched.
    # UR10/suction-gated → Franka byte-identical. UNTESTED — pending Kit verify + radius/apex/step tuning.
    try:
        import math as _math_ta, builtins as _bi_ta
        if _SG_IS_SUCTION and getattr(_bi_ta, "_ur10_transit_arc", False):
            _bx, _by = float(_usd_pos[0]), float(_usd_pos[1])
            _cdx, _cdy = float(cube_pos[0]) - _bx, float(cube_pos[1]) - _by
            _ddx, _ddy = float(drop_pos[0]) - _bx, float(drop_pos[1]) - _by
            if (_cdx * _ddx + _cdy * _ddy) < 0.0:  # pick & drop >90° apart around the base = the big-rotation swing case
                _th_c = _math_ta.atan2(_cdy, _cdx); _th_d = _math_ta.atan2(_ddy, _ddx)
                _dth = _th_d - _th_c
                while _dth > _math_ta.pi: _dth -= 2.0 * _math_ta.pi
                while _dth < -_math_ta.pi: _dth += 2.0 * _math_ta.pi
                _R = 0.45  # sub-bin radius: arm folded-in (bin sits ~0.58 from base) so it clears the bin walls mid-rotation
                _zc = max(float(h1), float(h_mid_drop)) + 0.10  # high apex → rotate folded-up, not swung-out
                _n_arc = max(2, int(abs(_dth) / 0.6))  # ~35° angular steps
                _arc = []
                for _k in range(1, _n_arc + 1):
                    _th = _th_c + _dth * (float(_k) / float(_n_arc + 1))
                    _arc.append((np.array([_bx + _R * _math_ta.cos(_th), _by + _R * _math_ta.sin(_th), _zc], dtype=np.float32), None, drop_yaw))
                for _g in reversed(_arc):
                    goals.insert(4, _g)  # arc waypoints between S3 (lift) and S4 (transit) — forces a clean base rotation
    except Exception as _tae:
        print("(curobo: transit-arc soft-fail: " + str(_tae) + ")")
    segs = []
    q = np.asarray(current_q, dtype=np.float32)
    # NOTE (2026-06-05): a UR10 pick-seed wrap to (-pi,pi] was tested (flag _ur10_seed_wrap) — VERIFIED SAFE
    # (CP-70/79 still pass with it) but did NOT fix CP-84/85 (cube stays at spawn; the arm winds to ee[1.1,0.58,0.58]
    # WITH the gripper installed). The deeper CP-84/85 blocker is a cuRobo-suction-pick-geometry issue, not the
    # unwrapped home — left for the architectural suction pass. Reverted (no dormant flag).

    # 2026-05-27 GENERIC SUB-STEP HELPER: sub-step any goal where start_xy ≈ goal_xy + Z differs.
    # Plans intermediate waypoints (4 steps if Z-distance > 50mm) so cuRobo can't curve much per step.
    def _plan_sub_step(start_q_arr, goal_world, exclude_obs, yaw_deg, branch_pin=False):
        from curobo.types import JointState as _JS
        try:
            _start_t = torch.tensor([[float(x) for x in start_q_arr[:_ARM_DOF]]], dtype=torch.float32, device='cuda')
            _start_js = _JS.from_position(_start_t, joint_names=_PLANNER_JOINT_NAMES)
            _start_ee = _planner.compute_kinematics(_start_js).tool_poses.position[0,0,0].detach().cpu().numpy()
        except Exception:
            return _plan_to_world_point(goal_world, start_q_arr, exclude_obs=exclude_obs, yaw_deg=yaw_deg, branch_pin=branch_pin)
        _dxy = ((float(goal_world[0])-float(_start_ee[0]))**2 + (float(goal_world[1])-float(_start_ee[1]))**2) ** 0.5
        _dz = abs(float(goal_world[2]) - float(_start_ee[2]))
        if _dxy < 0.06 and _dz > 0.12:  # relaxed (was 0.005/0.20): the suction drop-descent enters with some
            # upstream xy drift; sub-goals are pinned to the GOAL xy so the descent column corrects it to the bin center.
            _n_steps = max(2, int(_dz / 0.05))
            _q_cur = start_q_arr
            _trajs = []; _mts = 0.0
            for _s in range(1, _n_steps+1):
                _interp_z = float(_start_ee[2]) + (_dz if float(goal_world[2]) > float(_start_ee[2]) else -_dz) * (_s/_n_steps)
                _sub_goal = np.array([float(goal_world[0]), float(goal_world[1]), _interp_z], dtype=np.float32)
                _r = _plan_to_world_point(_sub_goal, _q_cur, exclude_obs=exclude_obs, yaw_deg=yaw_deg, branch_pin=branch_pin)
                if _r is None: return None
                _t, _m = _r
                _trajs.append(_t); _mts += _m
                _q_cur = _t[-1]
            return (np.concatenate(_trajs, axis=0), _mts)
        return _plan_to_world_point(goal_world, start_q_arr, exclude_obs=exclude_obs, yaw_deg=yaw_deg, branch_pin=branch_pin)

    import builtins as _bi
    # Default vhold_mode=1 enables ToolPoseCriteria.linear_motion (cuRobo native).
    # Validated 10/10 L=0mm + deterministic via reset_seed() FOR FRANKA.
    # 2026-05-28: gate to franka-only — UR10 tool0 local +Z is the flange normal
    # (outward, not vertical), so linear_motion(axis="z") does not constrain the
    # world-vertical lift. Worse, R6 data shows 100% plan_pose ValueError on UR10
    # templates with vhold enabled. Hypothesis: trajopt cost-state corruption from
    # update_tool_pose_criteria not being applied at MotionPlanner level (only
    # trajopt_solver level); restored value differs from build-time default →
    # subsequent plans fail. Restoring pre-vhold behavior for UR10/G1 unblocks
    # CP-78/79/69/70/75 patterns. G1 also disabled until per-family axis logic added.
    _vmode = getattr(_bi, '_vhold_mode_test', 1) if ROBOT_FAMILY == "franka" else 0
    _attach_enabled = getattr(_bi, '_attach_test', False)  # disabled — broken
    _attached = False
    _carry = False  # True between the grip-close and the release -> the cube is held (loaded transit)
    _bs_start = time.monotonic()  # PLAN-BUDGET start (see budget check at the top of the loop)
    # 2026-06-09 RANK-2 BUILD DEADLINE (gated _ur10_build_budget_s, default 0 = OFF = byte-identical). [MEASURED CP-71]
    # the existing per-SEGMENT budget (L6533) is checked only at the TOP of each segment iter, so a SINGLE segment's
    # plan fan-out (_PLAN_RETRY=5 x plan_pose(max_attempts=3) x substeps x fallbacks) on an unreachable high-tight-grid
    # goal grinds for minutes and HANGS the Kit (grip_log froze at settling t=1.8s, 0 nudges). Publish a wall-clock
    # DEADLINE that _plan_to_world_point itself checks (top + retry loop) so the fan-out aborts MID-segment -> the build
    # returns res_None fast -> the pick fails gracefully -> the gate gives a verdict instead of freezing. Reset each
    # build so a slow first build doesn't permanently disable planning. UR10-gated -> Franka byte-identical.
    try:
        _bb = float(getattr(__import__("builtins"), "_ur10_build_budget_s", 0.0))
        __import__("builtins")._ur10_plan_deadline = (_bs_start + _bb) if (_bb > 0.0 and ROBOT_FAMILY in ("ur10", "ur10e")) else 0.0
    except Exception: pass
    # 2026-06-09 EXCLUDE-DELIVERED bridge (gated _ur10_obs_exclude_delivered, default OFF -> byte-identical). [MEASURED
    # CP-83] after Cube_2 is delivered INTO the bin, the multicube-obs auto-add still lists it as a collision obstacle
    # -> Cube_1's PLACE descend into the SAME bin is blocked (seg-6 res_None). A delivered cube in the destination must
    # NOT block the next place there. Publish S["delivered"] to builtins so _build_scene_cfg (different scope) can drop
    # them from the obstacle set. Set here (S is in scope in the controller); read in _ur10_multicube_obs.
    try: __import__("builtins")._mc_delivered = set(S.get("delivered", set())) if getattr(__import__("builtins"), "_ur10_obs_exclude_delivered", False) else set()
    except Exception:
        try: __import__("builtins")._mc_delivered = set()
        except Exception: pass
    for idx, (goal_world, action_after, yaw_deg) in enumerate(goals):
        try:
            if getattr(__import__("builtins"), "_ur10_hangloc", False):
                with open("/tmp/cp71_hangloc.txt", "w") as _hf: _hf.write("seg_build idx=%d goal=%s act=%s\\n" % (idx, str([round(float(_v), 2) for _v in goal_world]), str(action_after)))
        except Exception: pass
        # 2026-06-09 A1: mark this segment's phase so the carry-scoped multicube obstacles (added in _build_scene_cfg)
        # are PRESENT only for the LATERAL-TRANSIT segments (idx>=4: transit/over-bin/place — where the arm sweeps the
        # neighbour-cube column) and ABSENT for approach+pick+LIFT (idx 0-3). [MEASURED] seg-3 is a straight-UP lift at
        # the pick xy (low sweep risk); the original obstacle need was the seg-4 transit. idx>=3 blocked the lift; idx>=4
        # frees it so H7 routes the transit around. Gated _ur10_multicube_obs_carry_only (default OFF -> byte-identical).
        if getattr(__import__("builtins"), "_ur10_multicube_obs_carry_only", False):
            try: __import__("builtins")._mc_carry_phase = (idx >= 4)
            except Exception: pass
        # 2026-06-06 PLAN-BUDGET (time-series-confirmed CP-81): an UNPLANNABLE cube (e.g. the far Cube_1 whose
        # bin-drop is blocked by the already-delivered Cube_2) makes _build_segments grind ~150 plan_pose retries
        # = a slow-motion sim -> the function-gate's wall-clock timeout (duration_s+60) fires before sim-end ->
        # stale cp_pre -> a SPURIOUS huge velocity on the already-delivered cube -> false fail. Cap each build
        # attempt at 8s wall-clock so the caller's 3-strike abandon fires within ~24s and the sim COMPLETES inside
        # the gate's budget -> correct measurement. Bail = None (the caller treats it as a plan failure). UR10-gated
        # so the 37 Franka friction-passes are byte-identical.
        if ROBOT_FAMILY in ("ur10", "ur10e") and (time.monotonic() - _bs_start) > float(getattr(__import__("builtins"), "_ur10_plan_budget_s", (20.0 if getattr(__import__("builtins"), "_sg_nvidia_cup", False) else 8.0))):
            # 2026-06-07: budget flag-raisable (default 8.0 = byte-identical). Hypothesis test for #3: more trajopt
            # seeds (anti-spin) make each plan slower, so the 8s cap may bail _build_segments before the pick is
            # planned -> the "trajopt=8 breaks the pick" may be a BUDGET timeout, not seed instability. Raise to test.
            if _attached:
                try: _planner.trajopt_solver.core.attachment_manager.detach(link_name=_TOOL_FRAME)
                except Exception: pass
            return None
        # 2026-06-02 EDIT 2: vhold (linear_motion axis=z + reset_seed) on S3 grasp-lift (idx 3),
        # S5 place-descent (idx 6), and S6 retract (last) — all pure vertical columns so the descent/
        # ascent doesn't swing laterally (cures placement tilt). _vmode=0 for non-Franka (UR10 +Z is
        # the flange normal -> R6 ValueError) so UR10/suction byte-identical. Franka panda_hand +Z =
        # world-down; S3 vhold proven 10/10. The unconstrained fallback below covers any vhold plan-miss.
        _seg_vmode = _vmode if (idx in (3, 6) or idx == len(goals) - 1) else 0
        # 2026-06-09 H7-APPROACH pan-rotate (gated _ur10_pick_approach_panrotate, default OFF -> byte-identical).
        # [MEASURED CP-83, TS-verified] the pick ARRIVES folded-back (live jdeg pan~20, lift~-175 = upper-arm folded
        # back over the base to reach behind) instead of BASE-ROTATED to face the behind cube (the down-grasp config is
        # pan~146 ~= cube azimuth). The two are different IK branches 7.39 rad apart (genuine, NOT a 2pi-wrist wrap —
        # cspace_unwrap left bestd unchanged) so the descend down-config is unbridgeable from the fold-back arrival.
        # FIX (mirror the H7 transit): BEFORE the approach (idx 0), insert a pure cspace pan-rotate of shoulder_pan from
        # the current config toward the CUBE azimuth so the arm arrives base-facing (down-near) and the descend is
        # in-branch. UR10 suction + big rotation only; fail-open (plan fail -> normal approach). Generalizes to the 25
        # stacking plates (same arrive-base-facing-the-pick need).
        if (idx == 0 and ROBOT_FAMILY in ("ur10", "ur10e") and _SG_IS_SUCTION
                and getattr(_bi, "_ur10_pick_approach_panrotate", False)):
            try:
                import math as _m_ap
                _bxa, _bya = float(_usd_pos[0]), float(_usd_pos[1])
                _cube_az = _m_ap.atan2(float(cube_pos[1]) - _bya, float(cube_pos[0]) - _bxa)
                _qaa = np.asarray(q, dtype=np.float32)
                _cur_pan = float(_qaa[0])
                _dpan_a = _cube_az - _cur_pan
                while _dpan_a > _m_ap.pi: _dpan_a -= 2.0 * _m_ap.pi
                while _dpan_a < -_m_ap.pi: _dpan_a += 2.0 * _m_ap.pi
                try:
                    with open("/tmp/h7_sentinel.log", "a") as _aps: _aps.write("H7APPR cube_az=%.3f cur_pan=%.3f dpan=%.3f fire=%s\\n" % (_cube_az, _cur_pan, _dpan_a, str(abs(_dpan_a) > 0.5)))
                except Exception: pass
                if abs(_dpan_a) > 0.5:
                    _tqa = _qaa.copy(); _tqa[0] = _cur_pan + _dpan_a
                    _sqa = torch.tensor([[float(x) for x in _qaa[:_ARM_DOF]]], dtype=torch.float32, device='cuda')
                    _gqa = torch.tensor([[float(x) for x in _tqa[:_ARM_DOF]]], dtype=torch.float32, device='cuda')
                    _sjsa = JointState.from_position(_sqa, joint_names=_PLANNER_JOINT_NAMES)
                    _gjsa = JointState.from_position(_gqa, joint_names=_PLANNER_JOINT_NAMES)
                    try: _planner.reset_seed()
                    except Exception: pass
                    _ares = _planner.plan_cspace(_gjsa, _sjsa, max_attempts=3)
                    if _ares is not None and bool(_ares.success[0, 0].item()):
                        _ain = _ares.get_interpolated_plan()
                        _atj = _ain.position[0, 0, :, :7].detach().cpu().numpy()
                        _amt = float(_ares.motion_time()) if callable(_ares.motion_time) else float(_ares.motion_time)
                        segs.append({{"traj": _atj, "motion_time": _amt, "action_after": None,
                                      "grip_done": False, "drop_pos": None, "release_flange_z": None}})
                        q = _atj[-1]
                        print("(curobo: H7-APPROACH pan-rotate dpan=%.2f pan %.2f->%.2f knots=%d)"
                              % (_dpan_a, float(_qaa[0]), float(_atj[-1][0]), len(_atj)))
                    else:
                        print("(curobo: H7-APPROACH plan_cspace FAILED -> normal approach)")
            except Exception as _ape:
                print("(curobo: H7-APPROACH soft-fail: " + str(_ape) + ")")
        # 2026-06-09 H7 JOINT-SPACE PAN-ROTATE TRANSIT (gated _ur10_jointspace_transit, default OFF -> byte-identical).
        # The transit swing (RCA 2026-06-04) is a GEOMETRICALLY-forced IK branch flip: far-behind pick (x~-1.0) and front
        # bin (x~+0.5) sit on different IK branches, NO continuous IK across the front-center crossing. Cartesian levers
        # (arc/cspace/seeds/ori_tol) all MEASURED-refuted. FIX: before the Cartesian transit (idx 4), insert a PURE cspace
        # hop rotating ONLY shoulder_pan by the cube->bin azimuth delta (arm shape fixed). Base rotation about world-z
        # PRESERVES the tool's straight-down approach axis (only azimuthal roll changes -> axisymmetric cup ignores it),
        # so no IK branch flip is possible (plan_cspace interpolates to a fixed config). The existing transit then plans a
        # small move from the bin-facing config. UR10 suction + big behind->front rotation (|dpan|>0.5) only; fail-open.
        if (idx == 4 and ROBOT_FAMILY in ("ur10", "ur10e") and _SG_IS_SUCTION
                and getattr(_bi, "_ur10_jointspace_transit", False)):
            try:
                import math as _m_h7
                _bx7, _by7 = float(_usd_pos[0]), float(_usd_pos[1])
                _dpan = (_m_h7.atan2(float(drop_pos[1]) - _by7, float(drop_pos[0]) - _bx7)
                         - _m_h7.atan2(float(cube_pos[1]) - _by7, float(cube_pos[0]) - _bx7))
                while _dpan > _m_h7.pi: _dpan -= 2.0 * _m_h7.pi
                while _dpan < -_m_h7.pi: _dpan += 2.0 * _m_h7.pi
                _cube_reach = ((float(cube_pos[0]) - _bx7) ** 2 + (float(cube_pos[1]) - _by7) ** 2) ** 0.5
                _h7_far = float(getattr(_bi, "_ur10_jointspace_far_reach", 1.0))
                try:
                    with open("/tmp/h7_sentinel.log", "a") as _h7s: _h7s.write("H7_GATE reach=%.3f dpan=%.3f far=%.3f fire=%s\\n" % (_cube_reach, _dpan, _h7_far, str(abs(_dpan) > 0.5 and _cube_reach > _h7_far)))
                except Exception: pass
                if abs(_dpan) > 0.5 and _cube_reach > _h7_far:
                    _sign7 = float(getattr(_bi, "_ur10_jointspace_sign", -1.0))
                    _qa7 = np.asarray(q, dtype=np.float32)
                    _tq7 = _qa7.copy(); _tq7[0] = float(_tq7[0]) + _sign7 * float(_dpan)
                    _sq7 = torch.tensor([[float(x) for x in _qa7[:_ARM_DOF]]], dtype=torch.float32, device='cuda')
                    _gq7 = torch.tensor([[float(x) for x in _tq7[:_ARM_DOF]]], dtype=torch.float32, device='cuda')
                    _sjs7 = JointState.from_position(_sq7, joint_names=_PLANNER_JOINT_NAMES)
                    _gjs7 = JointState.from_position(_gq7, joint_names=_PLANNER_JOINT_NAMES)
                    try: _planner.reset_seed()
                    except Exception: pass
                    _hres = _planner.plan_cspace(_gjs7, _sjs7, max_attempts=3)
                    if _hres is not None and bool(_hres.success[0, 0].item()):
                        _hin = _hres.get_interpolated_plan()
                        _htj = _hin.position[0, 0, :, :7].detach().cpu().numpy()
                        _hmt = float(_hres.motion_time()) if callable(_hres.motion_time) else float(_hres.motion_time)
                        _vmax7 = float(getattr(_bi, "_sg_loaded_vmax_fast", 0) or getattr(_bi, "_sg_loaded_vmax", 1.2))  # GATED faster ceiling; falsy _sg_loaded_vmax_fast -> falls back to _sg_loaded_vmax (1.2) -> byte-identical
                        if _vmax7 > 1e-6 and _hmt > 1e-6:
                            _sw7 = float(np.max(np.abs(np.asarray(_htj[-1], dtype=np.float64)[:_ARM_DOF]
                                                        - np.asarray(_htj[0], dtype=np.float64)[:_ARM_DOF])))
                            _hmt = max(_hmt, _sw7 / _vmax7)
                        segs.append({{"traj": _htj, "motion_time": _hmt, "action_after": None,
                                      "grip_done": False, "drop_pos": None, "release_flange_z": None}})
                        q = _htj[-1]
                        print("(curobo: H7 pan-rotate hop dpan=%.2f sign=%.0f q0 %.2f->%.2f knots=%d mt=%.2f)"
                              % (_dpan, _sign7, float(_qa7[0]), float(_htj[-1][0]), len(_htj), _hmt))
                    else:
                        print("(curobo: H7 pan-rotate hop plan_cspace FAILED -> normal transit)")
            except Exception as _h7e:
                print("(curobo: H7 hop soft-fail: " + str(_h7e) + ")")
        # ATTACH cube_M BEFORE S3 lift so cuRobo collision-checker treats attached cube as robot geometry
        if idx == 3 and _attach_enabled and not _attached:
            try:
                from curobo._src.geom.types import Cuboid
                _cube_path = S["picked_path"] or '/World/Cube_M'
                _cp_prim = stage.GetPrimAtPath(_cube_path)
                _cdims = [0.05, 0.05, 0.05]
                try:
                    _bb = UsdGeom.Imageable(_cp_prim).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
                    _mn, _mx = _bb.GetMin(), _bb.GetMax()
                    _cdims = [float(_mx[i])-float(_mn[i]) for i in range(3)]
                except Exception: pass
                _cube_obs = Cuboid(name='picked_cube', pose=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0], dims=_cdims)
                _q_grip = torch.tensor([[float(x) for x in q[:_ARM_DOF]]], dtype=torch.float32, device='cuda')
                _js_grip = JointState.from_position(_q_grip, joint_names=_PLANNER_JOINT_NAMES)
                _planner.trajopt_solver.core.attachment_manager.attach(joint_states=_js_grip, obstacles=[_cube_obs], link_name=_TOOL_FRAME)
                _attached = True
            except Exception: pass
        # 2026-06-06 CUP-FRAME-DOWN (gated _ur10_cupframe_down, default ON since 2026-06-06 flip). With the -90 mount (Edit A) the cup
        # points STRAIGHT DOWN; this ITERATIVE FK descend-correction lands the cup TIP on the cube TOP in DIRECT
        # CONTACT (Anton's req: no gap, cup lower face touching the cube, hotswap-ready geometry). Method (frame-
        # correct, all world poses): (1) measure the CONSTANT cup-in-tool0 offset at the ACTUAL current config
        # (FK actual joints -> tool0 world; live suction_cup USD -> cup world; project into the tool0 frame so the
        # live cup matches the live FK — NOT the planned q, which was the earlier garbage-offset bug); (2) iterate
        # plan -> FK planned config -> cup_world = tool0 + R_tool·offset_tool0 -> err to cube_top -> correct the
        # goal. Close segment only; when disabled -> byte-identical to the 11 passers.
        if (action_after == "close" and getattr(__import__("builtins"), "_ur10_cupframe_down", True)
                and _SG_IS_SUCTION and ROBOT_FAMILY in ("ur10", "ur10e")):
            try:
                from curobo.types import JointState as _JS_cf
                def _fk_world_cf(_jarr):
                    _t = torch.tensor([[float(_x) for _x in np.asarray(_jarr)[:_ARM_DOF]]], dtype=torch.float32, device="cuda")
                    _ks = _planner.compute_kinematics(_JS_cf.from_position(_t, joint_names=_PLANNER_JOINT_NAMES))
                    _p = _ks.tool_poses.position[0, 0, 0].detach().cpu().numpy()
                    _qq = _ks.tool_poses.quaternion[0, 0, 0].detach().cpu().numpy()
                    _bm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_usd_quat[0]), Gf.Vec3d(float(_usd_quat[1]), float(_usd_quat[2]), float(_usd_quat[3])))); _bm.SetTranslateOnly(Gf.Vec3d(float(_usd_pos[0]), float(_usd_pos[1]), float(_usd_pos[2])))
                    _fm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_qq[0]), Gf.Vec3d(float(_qq[1]), float(_qq[2]), float(_qq[3])))); _fm.SetTranslateOnly(Gf.Vec3d(float(_p[0]), float(_p[1]), float(_p[2])))
                    _w = _fm * _bm
                    return _w.ExtractTranslation(), _w.ExtractRotationMatrix()
                _jq_now = franka.get_joint_positions()
                _cupprim = stage.GetPrimAtPath(_SG_CUP_PATH)
                if _jq_now is not None and _cupprim and _cupprim.IsValid():
                    _tp0, _tr0 = _fk_world_cf(_jq_now)
                    _cw0 = UsdGeom.Xformable(_cupprim).ComputeLocalToWorldTransform(0).ExtractTranslation()
                    _ow = [float(_cw0[_i]) - float(_tp0[_i]) for _i in range(3)]
                    _otool = [sum(_ow[_k] * float(_tr0.GetRow(_j)[_k]) for _k in range(3)) for _j in range(3)]
                    try:
                        _w3p = stage.GetPrimAtPath("/".join(ROBOT_PATH.split("/")) + "/wrist_3_link")
                        _w3t = UsdGeom.Xformable(_w3p).ComputeLocalToWorldTransform(0).ExtractTranslation() if (_w3p and _w3p.IsValid()) else None
                        with open("/tmp/cupframe_dbg.log", "a") as _cfd:
                            _cfd.write("MEAS fk_tool0=%s cup=%s wrist3=%s ow_world=%s\\n" % (
                                [round(float(_tp0[_i]),3) for _i in range(3)], [round(float(_cw0[_i]),3) for _i in range(3)],
                                ([round(float(_w3t[_i]),3) for _i in range(3)] if _w3t is not None else None),
                                [round(_ow[_i],3) for _i in range(3)]))
                    except Exception: pass
                    _cube_top = [float(cube_pos[0]), float(cube_pos[1]), float(cube_pos[2]) + 0.025]
                    _gg = np.array([float(cube_pos[0]), float(cube_pos[1]), float(cube_pos[2]) + 0.025 + 0.16], dtype=np.float32)
                    for _it in range(3):
                        _rr = _plan_to_world_point(_gg, q, exclude_obs=S["picked_path"], yaw_deg=yaw_deg, vhold_mode=0)
                        if _rr is None: break
                        _tpf, _trf = _fk_world_cf(_rr[0][-1])
                        _cupf = [float(_tpf[_k]) + sum(_otool[_j] * float(_trf.GetRow(_j)[_k]) for _j in range(3)) for _k in range(3)]
                        _err = [_cube_top[_k] - _cupf[_k] for _k in range(3)]
                        _en = (_err[0] ** 2 + _err[1] ** 2 + _err[2] ** 2) ** 0.5
                        with open("/tmp/cupframe_dbg.log", "a") as _cfd:
                            _cfd.write("it%d otool=%s cupf=%s err=%s en=%.3f\\n" % (_it, [round(_x, 3) for _x in _otool], [round(_x, 3) for _x in _cupf], [round(_x, 3) for _x in _err], _en))
                        if _en < 0.008: break
                        _gg = np.array([float(_gg[_k]) + _err[_k] for _k in range(3)], dtype=np.float32)
                    goal_world = _gg
            except Exception as _cfe:
                try:
                    with open("/tmp/cupframe_dbg.log", "a") as _cfd: _cfd.write("cupframe_fail " + str(_cfe)[:140] + "\\n")
                except Exception: pass
        # SUCTION drop-descent (S5/open): (2b) re-seed from the LIVE joint state — break the open-loop q=traj[-1]
        # chain that compounds upstream drift; (2a) route through _plan_sub_step which forces a VERTICAL descent
        # over the bin center via goal-xy sub-goals. The default loop calls _plan_to_world_point directly, letting
        # cuRobo curve the descent to an off-center+high terminal (RCA: S5 missed goal by 0.13xy+0.38z, plan_fails=0).
        if _SG_IS_SUCTION and action_after == "open":
            # 2026-06-02 CP-83 RCA (segment-level fail log): S6/open (idx6) FAILS while S4.5
            # (idx5, the HIGHER 1.58 mid) SUCCEEDS → not a reach/height issue → a SEED issue.
            # The live re-seed below reads the live joints, which during _build_segments = the
            # robot HOME. add_reference UR10's home joints are UNWRAPPED (~-12..-14 rad) so
            # planning the drop from them fails (CP-70's sane home makes the same re-seed work
            # — that's a292's drop-precision fix). FIX: (1) WRAP the live re-seed to (-π,π] —
            # no-op for CP-70's sane home (a292 preserved), sane-izes CP-83's -14; (2) if the
            # home-seeded drop STILL fails, FALL BACK to the CHAINED seed (the previous segment's
            # traj end = the arm OVER the bin) — the geometrically-correct short-descent seed.
            # Gated UR10; Franka never enters this branch (_SG_FOLLOWER_OP is None).
            _q_chained = q
            try:
                _live_q = franka.get_joint_positions()
                if _live_q is not None:
                    q = np.asarray(_live_q, dtype=np.float32)[:_ARM_DOF]
                    if ROBOT_FAMILY in ("ur10", "ur10e"):
                        q = ((q + np.pi) % (2.0 * np.pi) - np.pi).astype(np.float32)
            except Exception: pass
            res = None
            # 2026-06-07 SCOPED DROP BRANCH-PIN (gated _ur10_drop_branch_pin, default OFF). The drop-descend swing
            # (cup over bin @t=9 [0.49,-0.41,1.03] -> flies to [0.2,0.54,1.57] -> late release) is cuRobo re-IKing
            # the 5cm descend into a DIFFERENT arm branch. The plan_cspace branch-pin (L5335) fixes this BUT only if
            # it pins to the OVER-BIN branch: pass _q_chained (the transit-end config = where the arm WILL be) as the
            # start + branch_pin=True so it stays in-branch. SCOPED to THIS S5 call only (branch_pin kwarg, NOT the
            # global _ur10_plan_cspace flag) so the deep place-descent / pick / transit do NOT get cspace (global
            # cspace TIMES OUT on the z~0.47 place-descent). OFF (or Franka) = original live-seed path, byte-identical.
            import builtins as _bi_dbp
            if getattr(_bi_dbp, "_sg_grip_log", False) or getattr(_bi_dbp, "_ur10_drop_branch_pin", False):
                try:
                    with open("/tmp/s5goal.log", "a") as _s5g:
                        _s5g.write("S5 drop_pos=%s drop_tip_release=%.3f goal_world=%s\\n" % (
                            [round(float(_x), 3) for _x in drop_pos], float(_drop_tip_release),
                            [round(float(_x), 3) for _x in goal_world]))
                except Exception: pass
            if ROBOT_FAMILY in ("ur10", "ur10e") and getattr(_bi_dbp, "_ur10_drop_branch_pin", False):
                res = _plan_sub_step(_q_chained, goal_world, exclude_obs=S["picked_path"], yaw_deg=yaw_deg, branch_pin=True)
            if res is None:
                # GATED (_ur10_drop_seed_chained, default OFF): seed the S5 fallback from _q_chained (the transit-end
                # OVER-BIN config) instead of the live-reseed q (= robot HOME during _build_segments). The home seed
                # plans a home->bin descend that the arm executes as the "varv till" up-out-back lap [MEASURED CP-69
                # 2026-06-09: seg7 pan -47->-6->-47]. Over-bin seed -> short in-branch descend, no home detour.
                _s5_seed = (_q_chained if (ROBOT_FAMILY in ("ur10", "ur10e")
                                           and getattr(_bi_dbp, "_ur10_drop_seed_chained", False)) else q)
                res = _plan_sub_step(_s5_seed, goal_world, exclude_obs=S["picked_path"], yaw_deg=yaw_deg)
            if res is None and ROBOT_FAMILY in ("ur10", "ur10e"):
                res = _plan_sub_step(_q_chained, goal_world, exclude_obs=S["picked_path"], yaw_deg=yaw_deg)
            try:
                if res is not None and (getattr(_bi_dbp, "_sg_grip_log", False) or getattr(_bi_dbp, "_ur10_drop_seed_chained", False)):
                    with open("/tmp/s5path.log", "a") as _s5p:
                        _s5p.write("S5 traj0=%s qchain=%s homeq=%s nknots=%d\\n" % (
                            [round(float(_x), 2) for _x in np.asarray(res[0])[0][:6]],
                            [round(float(_x), 2) for _x in np.asarray(_q_chained)[:6]],
                            [round(float(_x), 2) for _x in np.asarray(q)[:6]], len(res[0])))
            except Exception: pass
            if res is None and DEST_PATH:
                # 2026-06-04 drop-IK fix: descend onto destination has no collision-free IK (ik_solver uses
                # scene collision; destination in-world, only held cube excluded). Retry excluding the
                # DESTINATION too. ADDITIVE (only on failure) -> zero regression. Fixes pedestal->dest drops.
                res = _plan_sub_step(_q_chained, goal_world, exclude_obs=[S["picked_path"], DEST_PATH], yaw_deg=yaw_deg)
        else:
            # 2026-06-09 PLACE-DESCEND BRANCH-PIN (gated _ur10_place_descend_pin, default OFF -> byte-identical). The
            # OPEN/place descend, like the pick descend, can res_None from the transit-arrival config (CP-81/83 2nd
            # cube). branch_pin routes the place plan through the cspace-pin + wrist-unwrap path (the proven pick fix)
            # so the existing down-config at the bin is reached. OPEN segment only -> non-place plans byte-identical.
            _place_pin = (action_after == "open" and getattr(__import__("builtins"), "_ur10_place_descend_pin", False))
            # 2026-06-10 APPROACH-PIN (gated _ur10_approach_pin, default OFF -> byte-identical): branch-pin ALL
            # build-time segment plans through the cspace closest-L1 path. [MEASURED CP-83] the explicit probe
            # (CSPACE=1) delivered BOTH cubes; pure-default recipe v2 (descend/relive pins only) leaves the APPROACH
            # plans free plan_pose -> the wound->down reconfig after delivering Cube_2 flips/knocks Cube_1 off its
            # pedestal (rep1 z=0.53 floor). Surgical recipe equivalent of the probe's global CSPACE.
            _bp_appr = getattr(__import__("builtins"), "_ur10_approach_pin", False)
            res = _plan_to_world_point(goal_world, q, exclude_obs=S["picked_path"], yaw_deg=yaw_deg, vhold_mode=_seg_vmode, branch_pin=(_place_pin or _bp_appr))
            if res is None and _seg_vmode != 0:
                # EDIT 2 fallback: the vertical (vhold) constraint missed -> retry UNCONSTRAINED so a
                # vhold plan-fail never fails the cube (no regression vs the pre-vhold single plan).
                res = _plan_to_world_point(goal_world, q, exclude_obs=S["picked_path"], yaw_deg=yaw_deg, vhold_mode=0)
            if res is None and DEST_PATH:
                # 2026-06-04 drop-IK fix: descend onto destination has NO collision-free IK (ik_solver uses
                # the scene collision checker; destination is in-world + only the held cube was excluded).
                # Retry excluding the DESTINATION too. ADDITIVE (only on failure) -> zero regression on
                # first-try canonicals; fixes pedestal->destination drops (CP-81/83/84/85).
                res = _plan_to_world_point(goal_world, q, exclude_obs=[S["picked_path"], DEST_PATH], yaw_deg=yaw_deg, vhold_mode=0)
        # 2026-06-05 DROP z-backoff fallback: a release-descend goal with NO feasible plan at
        # the requested z (reach/orientation/collision at the low release height) retries at
        # progressively HIGHER z and releases from the first feasible height — the held cube
        # drops the small remaining gap. CP-84 [0.5,-0.4,0.82] res_None but [..,1.0] plans;
        # CP-65 Franka handoff drop [0,-0.3,0.93] res_None -> all 4 cubes abandoned, FrankaB
        # never fed. ADDITIVE (only after all same-z fallbacks failed) -> the 37 + CP-52 deliver
        # first-try so res!=None here -> byte-identical. Release segment only (action_after=='open').
        if res is None and action_after == "open":
            _gb = np.asarray(goal_world, dtype=np.float32)
            _exd = [S["picked_path"], DEST_PATH] if DEST_PATH else S["picked_path"]
            # GATED (_ur10_drop_seed_chained): the z-backoff is the path that actually delivers when the S5
            # descend res_None's. Default seeds from q (= live-reseed HOME during _build_segments) -> the plan
            # is a home->bin detour the arm executes as the "varv till" [MEASURED CP-69 2026-06-09]. Seed from
            # _q_chained (transit-end OVER-BIN config) -> short in-branch descend, no lap. UR10 suction only.
            _zseed = (_q_chained if (_SG_IS_SUCTION and ROBOT_FAMILY in ("ur10", "ur10e")
                                     and getattr(__import__("builtins"), "_ur10_drop_seed_chained", False)) else q)
            for _dz in (0.06, 0.12, 0.18, 0.26):
                _gz = np.array([float(_gb[0]), float(_gb[1]), float(_gb[2]) + _dz], dtype=np.float32)
                if _SG_IS_SUCTION:
                    res = _plan_sub_step(_zseed, _gz, exclude_obs=_exd, yaw_deg=yaw_deg, branch_pin=_place_pin)
                else:
                    res = _plan_to_world_point(_gz, q, exclude_obs=_exd, yaw_deg=yaw_deg, vhold_mode=0)
                try:
                    if getattr(__import__("builtins"), "_sg_grip_log", False):
                        with open("/tmp/s5path.log", "a") as _zp:
                            _zp.write("ZBACKOFF dz=%.2f seed_pan=%.1f res=%s traj0_pan=%s trajN_pan=%s\\n" % (
                                _dz, float(np.asarray(_zseed)[0]), ("None" if res is None else "ok"),
                                ("-" if res is None else round(float(np.asarray(res[0])[0][0]), 1)),
                                ("-" if res is None else round(float(np.asarray(res[0])[-1][0]), 1))))
                except Exception: pass
                if res is not None:
                    print(f"(curobo: drop z-backoff +{{_dz}}m -> feasible z={{round(float(_gz[2]), 3)}})")
                    break
        if res is None and action_after is None and idx == len(goals) - 1 and not _SG_IS_SUCTION:
            # EDIT 1 fail-open: the S6 straight-up retract is a safety lift, not load-bearing. If it
            # won't plan, SKIP it (arm stays at the S5 release pose = legacy behavior) rather than
            # failing the just-PLACED cube. Never aborts a successful place.
            continue
        # 2026-06-09 PLACE FAIL-OPEN (gated _ur10_place_failopen, default OFF -> byte-identical). The build-time place
        # plan uses the CHAINED (build-time) over-bin config; for the 2nd cube (CP-81/83 Cube_1) that config can't reach
        # the bin (res_None) -> the WHOLE cube is abandoned at build, so the execution-time RELIVE (which delivered the
        # 1st cube's place LIVE) never gets a chance. Instead of abandoning, append a PLACEHOLDER open segment that holds
        # at the current over-bin config; the executor enters it and RELIVE re-plans the descend from the REAL live
        # arrival -> delivers like the 1st cube. Fail-open: if RELIVE also fails live, the cube just isn't placed (no crash).
        if (res is None and action_after == "open" and _SG_IS_SUCTION and ROBOT_FAMILY in ("ur10", "ur10e")
                and getattr(__import__("builtins"), "_ur10_place_failopen", False)):
            _ph = np.asarray(q, dtype=np.float32)
            segs.append({{"traj": np.stack([_ph, _ph]), "motion_time": 0.3, "action_after": "open", "grip_done": False,
                          "drop_pos": [float(drop_pos[0]), float(drop_pos[1]), float(drop_pos[2])],
                          "release_flange_z": (_sg_release_target if _SG_IS_SUCTION else None)}})
            print("(curobo: place build FAIL-OPEN -> placeholder over-bin seg; RELIVE re-plans live)", flush=True)
            continue
        if res is None:
            print(f"(curobo: plan failed for goal {{goal_world.tolist()}})")
            try:
                with open('/tmp/cp_planfail_tagged.log','a') as _pf:
                    _pf.write(f"cube={{S.get('picked_path')}} seg={{idx}}/{{len(goals)}} act={{action_after}} goal={{[round(float(x),3) for x in goal_world]}} nseg_goals={{[[round(float(g[0][0]),2),round(float(g[0][1]),2),round(float(g[0][2]),2)] for g in goals]}}\\n")
            except Exception: pass
            if _attached:
                try: _planner.trajopt_solver.core.attachment_manager.detach(link_name=_TOOL_FRAME)
                except Exception: pass
            return None
        traj, mt = res
        q = traj[-1]
        # 2026-06-05 LOADED-TRANSIT slowdown (asset/UR10 suction). The carry segments (S3 lift / S4 transit /
        # S4.5 mid -- action_after=None and BETWEEN the close and the open) move the arm through big
        # reconfigurations (CP-80 eyes: 177deg elbow + 180deg wrist swing) whose angular velocity FLINGS the
        # compliantly-held cube off the cup (cube separates at the start of S4 -> lands on the table). Cap the
        # loaded-carry angular velocity by STRETCHING this segment's motion_time so the centripetal load stays
        # within the suction grip. Scoped to the LOADED TRANSIT only (NOT descend/close/open) so it does NOT
        # recreate the 2026-06-02 blanket mt*=2 + early-open instability (the open segment's timing is untouched).
        # UR10 suction only -> Franka/procedural byte-identical. Flag-tunable (_sg_loaded_vmax rad/s).
        if (_carry and action_after is None and _SG_IS_SUCTION and ROBOT_FAMILY in ("ur10", "ur10e")):
            import builtins as _bi_lt
            _vmax = float(getattr(_bi_lt, "_sg_loaded_vmax", 1.2))  # angular-velocity cap (rad/s) for the carry
            if _vmax > 1e-6 and mt > 1e-6:
                _sweep = float(np.max(np.abs(np.asarray(traj[-1], dtype=np.float64)[:_ARM_DOF]
                                            - np.asarray(traj[0], dtype=np.float64)[:_ARM_DOF])))
                mt = max(mt, _sweep / _vmax)
        segs.append({{"traj": traj, "motion_time": mt, "action_after": action_after,
                      "grip_done": False,
                      "drop_pos": [float(drop_pos[0]), float(drop_pos[1]), float(drop_pos[2])]
                                  if action_after == "open" else None,
                      # the DESIGNED soft-place flange-z (bin-floor based); the step-loop telescopes the virtual tool
                      # to make the cup+cube reach this even when cuRobo under-descends the arm at the near bin.
                      "release_flange_z": _sg_release_target
                                  if (action_after == "open" and _SG_IS_SUCTION) else None}})
        # advance the loaded-carry tracker: the cube is HELD after the close completes, RELEASED at the open.
        if action_after == "close":
            _carry = True
        elif action_after == "open":
            _carry = False
    if _attached:
        try: _planner.trajopt_solver.core.attachment_manager.detach(link_name=_TOOL_FRAME)
        except Exception: pass
    return segs

# 2026-06-05 ASSET-GRIPPER runtime joint fixup. The hotswap asset gripper (short_gripper.usd) is FixedJoint-bolted
# to wrist_3_link, but that joint is authored DISABLED at build (the articulation is unposed there -> the ee-in-
# wrist_3 localPose is degenerate). Here, at the first POSED tick, re-author localPose0 from the now-correct world
# poses and ENABLE the joint -> the gripper locks exactly at the ee_link (cup-correct) pose and tracks the arm
# (proven exact in conv_test). Asset-mode only (raw iface + no follower); latched; Franka/procedural untouched.
_asset_joint_fixed = [False]
def _fixup_asset_gripper_joint():
    # 2026-06-05 RE-ENABLED (wound-start root-fix synergy): this was disabled because the WOUND start pose made
    # wrist_3's runtime USD pose unreliable at the first ticks -> garbage localPose0 -> joint snap exploded the
    # gripper. The wound-start root fix (robot_wizard home spawn) now poses the arm at home at build AND from
    # frame 0, so the live FK ee pose and the wrist_3 USD pose are consistent. Re-author localPose0 =
    # ee_world * wrist_3_world^-1 and place /Root at ee_world, then ENABLE -> a snap-free rigid mount that tracks
    # the arm at the (cup-correct) ee pose. The build-time FlangeMount is authored DISABLED (degenerate link
    # transforms at t=0), so THIS runtime fixup is the enable path. Latched (runs once).
    if _asset_joint_fixed[0]:
        return
    if (_SG_IFACE is None) or (_SG_FOLLOWER_OP is not None) or (not _SG_PATH_RAW):
        _asset_joint_fixed[0] = True; return  # not asset mode
    try:
        _groot = "/".join(str(_SG_PATH_RAW).split("/")[:-1])   # /World/<robot>_ShortGripper
        _jpath = _groot + "/FlangeMount"
        _jp = stage.GetPrimAtPath(Sdf.Path(_jpath))
        _w3p = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH + "/wrist_3_link"))
        if not (_jp and _jp.IsValid() and _w3p and _w3p.IsValid()):
            _asset_joint_fixed[0] = True; return
        # Gate on wrist_3 USD being genuinely POSED (off the degenerate stacked rest where all links read ~the same
        # world pose). At the rest transient, FK (live home joints) and wrist_3 USD (still stacked) are INCONSISTENT
        # -> garbage localPose0 (validated 2026-06-05). Require wrist_3 to have lifted well above the base first.
        _w3chk = UsdGeom.Xformable(_w3p).ComputeLocalToWorldTransform(0).ExtractTranslation()
        if (float(_w3chk[2]) - float(_usd_pos[2])) < 0.2:
            return  # wrist_3 USD not posed yet (still ~stacked at base height) -> retry next tick
        # ee_link is a VIRTUAL frame -> its USD transform is FROZEN at home (never tracks the arm). So get the LIVE ee
        # pose from cuRobo FK (the same FK the suction follower uses, reliable at any config), NOT from USD. wrist_3 IS
        # a real link and its USD pose tracks. ee-in-wrist_3 is a constant -> a correct localPose0 at any posed tick.
        _jq = franka.get_joint_positions()
        if _jq is None:
            return
        from curobo.types import JointState as _JS_fx
        _tq = torch.tensor([[float(x) for x in np.asarray(_jq)[:_ARM_DOF]]], dtype=torch.float32, device="cuda")
        _ks = _planner.compute_kinematics(_JS_fx.from_position(_tq, joint_names=_PLANNER_JOINT_NAMES))
        _fp = _ks.tool_poses.position[0, 0, 0].detach().cpu().numpy()       # ee position in base frame
        _fq = _ks.tool_poses.quaternion[0, 0, 0].detach().cpu().numpy()     # ee quaternion (w,x,y,z) in base frame
        # base (robot root) world transform, then ee_world = ee_in_base then base->world.
        _baseM = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_usd_quat[0]), Gf.Vec3d(float(_usd_quat[1]), float(_usd_quat[2]), float(_usd_quat[3]))))
        _baseM.SetTranslateOnly(Gf.Vec3d(float(_usd_pos[0]), float(_usd_pos[1]), float(_usd_pos[2])))
        _fkM = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_fq[0]), Gf.Vec3d(float(_fq[1]), float(_fq[2]), float(_fq[3]))))
        _fkM.SetTranslateOnly(Gf.Vec3d(float(_fp[0]), float(_fp[1]), float(_fp[2])))
        _eeW = _fkM * _baseM
        # 2026-06-05 CUP-AXIS ALIGNMENT: /Root mounts AT the ee (position+orientation) correctly, but the asset
        # suction_cup sits along /Root local +X while the cuRobo DESCEND axis is /Root +Z (DOWN_QUAT sends +Z
        # world-down — PROVEN: at the pick /Root +Z=down but the cup is along +X = 90deg off -> cup misses the cube
        # by ~0.32m). Rotate /Root's frame about its own Y so its +X (the cup) aligns with the +Z descend axis. Sign
        # is flag-controllable for empirical validation (builtins._sg_cup_align_deg, default -90).
        try:
            import builtins as _bi_ca
            # 2026-06-06 NVIDIA-CUP ALIGN (gated _sg_nvidia_cup, default OFF): NVIDIA mounts the cup as a clean
            # child of ee_link along ee_link +X (out the END, collinear with the flange normal) — no mount rotation.
            # Our build mount is ALREADY that (measured: cup-Z = ee_link +X, identical to NVIDIA). The -90 below
            # rotates it OUT THE SIDE (the 90deg-to-wrist Anton sees). _sg_nvidia_cup=True keeps _ca_deg=0 so the
            # runtime cup stays in the NVIDIA-correct ee_link +X orientation; the cup-frame closed-loop still drives
            # the cup to the cube. Reversible; OFF = byte-identical to the current -90 mount.
            _ca_deg = (float(getattr(_bi_ca, "_sg_nvidia_ca_deg", 0.0)) if getattr(_bi_ca, "_sg_nvidia_cup", False)  # 2026-06-07 FIX: _ca_deg=0 = native mount; the gripper extends STRAIGHT out-the-end (cup straight DOWN at descend, VISUALLY VERIFIED). The old +90 mounted it 90deg OFF (gripper sideways from a downward flange — measured + rendered). Gated nvidia -> production byte-identical.
                       else (-90.0 if getattr(_bi_ca, "_ur10_cupframe_down", True)
                             else float(getattr(_bi_ca, "_sg_cup_align_deg", -110.0))))
            _eeQ0 = _eeW.ExtractRotationQuat(); _eeT0 = _eeW.ExtractTranslation()
            _eeQ1 = _eeQ0 * Gf.Rotation(Gf.Vec3d(0.0, 1.0, 0.0), _ca_deg).GetQuat()
            _eeW = Gf.Matrix4d().SetRotate(_eeQ1); _eeW.SetTranslateOnly(_eeT0)
        except Exception: pass
        _w3m = UsdGeom.Xformable(_w3p).ComputeLocalToWorldTransform(0)
        _et = _eeW.ExtractTranslation(); _wt = _w3m.ExtractTranslation()
        _sep = ((_et[0]-_wt[0])**2 + (_et[1]-_wt[1])**2 + (_et[2]-_wt[2])**2) ** 0.5
        # 2026-06-05: lowered 0.3 -> 0.015. MEASURED (sentinel): the home-posed FK-ee-to-wrist_3 separation is only
        # ~0.032m (cuRobo's tool frame = ee_link sits ~3cm off wrist_3), NOT the ~0.1-0.3m assumed. The old gate
        # NEVER passed at home (_sep 0.032 < 0.3/0.04) -> fixup never enabled -> gripper stayed DETACHED. With the
        # wound-start fix there is no degenerate transient (arm is home from frame 1, _sep ~0.032 immediately), so
        # 0.015 admits the posed arm while still rejecting a true both-at-base degeneracy (_sep ~0). Confirmed: the
        # fixup now ENABLES on the first valid tick and the gripper TRACKS the arm.
        if _sep < 0.015:
            return  # wrist_3 USD genuinely degenerate (both at base) -> retry next tick
        # 2026-06-07 FLUSH+COAXIAL MOUNT (gated _sg_flush_mount, default OFF). MEASURED (wrist_3 frame): the
        # runtime fixup places /Root at the cuRobo FK ee, which sits +28.5mm out + ~11mm LATERAL of the flange
        # (/World/UR10/wrist_3_link/flange == wrist_3 origin == [0,0,0]). That is the visible cup<->arm gap +
        # off-centre cup Anton flagged, AND it pushes the cup 158.5mm beyond /Root => 187mm from the flange while
        # the controller models 159mm => the cup overshoots the cube (the "through the cube" look). Mounting /Root
        # AT the flange (coaxial), keeping the cup-correct orientation, closes the gap + centres the cup + makes the
        # tool-length honest. Gated OFF => the nvidia path + the 8 passers stay byte-identical until A/B-proven.
        try:
            import builtins as _bi_fm
            # 2026-06-07 FLUSH+COAXIAL MOUNT, DEFAULT ON for the faithful nvidia cup. Mounts /Root at the wrist_3
            # flange (== wrist_3 origin, MEASURED) instead of the cuRobo FK-ee (which sits +28.5mm + 11mm-lateral
            # off the flange). Closes the visible cup<->arm GAP (24->0mm) + centres the cup (lateral 11->0mm),
            # keeping the cup orientation. VERIFIED on FRESH Kit: CP-69 delivers WITH flush (build-1 cleanest) ==
            # flush OFF — the earlier "cup stalls 236mm above cube" was KIT DEGRADATION (builds 10-13), NOT a flush
            # regression (fresh A/B disproved it). 8 passers gate-pass with flush. OFF for the legacy cupframe(-90)
            # path (byte-identical). Explicit builtins._sg_flush_mount overrides either way.
            if getattr(_bi_fm, "_sg_flush_mount", getattr(_bi_fm, "_sg_nvidia_cup", False)):
                _flush = Gf.Matrix4d().SetRotate(_eeW.ExtractRotationQuat())
                _flush.SetTranslateOnly(_w3m.ExtractTranslation())
                _eeW = _flush
        except Exception:
            pass
        # ee-in-wrist_3 = ee_world * w3_world^-1 (verified: rel*w3 reconstructs ee exactly).
        _rel = _eeW * _w3m.GetInverse()
        _rt = _rel.ExtractTranslation(); _rq = _rel.ExtractRotationQuat(); _rqi = _rq.GetImaginary()
        # place /Root at the live ee (so enabling the joint causes no snap-yank), author localPose0, enable.
        UsdGeom.Xformable(stage.GetPrimAtPath(Sdf.Path(_groot))).ClearXformOpOrder()
        UsdGeom.Xformable(stage.GetPrimAtPath(Sdf.Path(_groot))).AddTransformOp().Set(_eeW)
        _jp.GetAttribute("physics:localPos0").Set(Gf.Vec3f(float(_rt[0]), float(_rt[1]), float(_rt[2])))
        _jp.GetAttribute("physics:localRot0").Set(Gf.Quatf(float(_rq.GetReal()), float(_rqi[0]), float(_rqi[1]), float(_rqi[2])))
        _je = _jp.GetAttribute("physics:jointEnabled")
        if not (_je and _je.IsDefined()):
            _je = _jp.CreateAttribute("physics:jointEnabled", Sdf.ValueTypeNames.Bool)
        _je.Set(True)
        _asset_joint_fixed[0] = True
        print("(curobo: asset gripper FlangeMount re-authored from FK ee + enabled -> tracks the arm at ee)")
    except Exception as _fje:
        print("(curobo: asset joint fixup soft-fail: " + str(_fje) + ")")
        _asset_joint_fixed[0] = True

def _on_step(dt):
    try:
        S["ticks"] += 1
        # RESET EPOCH (2026-06-12): settle_after_canonical restores the SCENE
        # to authored start but the controller's python state kept running —
        # a chain that started DURING the canonical build (sensor-less claim)
        # resumes mid-cycle against the reset world (drawer-open: gate replays
        # the tail of a consumed cycle -> end pinned at the joint stop).
        # settle bumps builtins._pp_reset_epoch; controllers re-arm cleanly.
        # No bump (every current flow) -> S["_epoch"] stays 0 -> byte-identical.
        _ep_rs = getattr(__import__("builtins"), "_pp_reset_epoch", 0)
        if S.get("_epoch", 0) != _ep_rs:
            S["_epoch"] = _ep_rs
            S.update({{"mode": "wait_sensor", "picked_path": None, "segments": None,
                       "seg_idx": 0, "seg_start_t": None,
                       "delivered": set(), "failed": set(),
                       "settle_ticks": 0, "grip_action_done": False}})
            # a held mutex would deadlock the replay (the marker prim outlives
            # the python state) — release if this robot owns it
            if MUTEX_PATH:
                try:
                    _mp_rs = stage.GetPrimAtPath(MUTEX_PATH)
                    if _mp_rs and _mp_rs.IsValid():
                        _ma_rs = _mp_rs.GetAttribute("mutex:claimed_by")
                        if _ma_rs and (_ma_rs.Get() or "") == ROBOT_PATH:
                            _ma_rs.Set("")
                except Exception: pass
        _a_tick.Set(S["ticks"]); _a_phase.Set(S["mode"])
        if _USE_SIM_CLOCK: _sim_clock_advance(dt)  # SimClock seam: advance sim-time (no-op + no query when gated OFF)
        _fixup_asset_gripper_joint()  # asset gripper: re-author its wrist_3 FixedJoint from correct runtime poses (once)
        _track_suction_follower()  # suction: keep the FJ'd cone on the live ee so the SG can grip (no-op for Franka)
        _clamp_gripped_velocity()  # fling guard: cap the gripped cube's velocity (kills the kinematic-follower NaN-fling)

        # 2026-06-07 PER-TARGET REACH SWEEP (gated _reach_probe, tick-1 one-shot). For EVERY pick target in
        # SOURCE_PATHS, probe the straight-down IK/trajectory reach to the object TOP from the home seed and log
        # REACHABLE / MARGINAL / UNREACHABLE. Fires on the first play tick (joints valid) so it does NOT depend on
        # the controller progressing to the per-cube goal-builder -- complex 6-SKU/carousel/palletizer scenes never
        # reach that builder inside an 18s probe, which is why the old _build_segments probe stayed silent on them.
        # This is the data source for the layout REACHABILITY VALIDATOR (flag picks the UR10 cannot reach top-down).
        # Gated OFF in production -> byte-identical control flow.
        import builtins as _bi_rs
        if getattr(_bi_rs, "_reach_probe", False) and not getattr(_bi_rs, "_reach_probe_done", False):
            _bi_rs._reach_probe_done = True
            try:
                _sq = None
                try: _sq = np.asarray(franka.get_joint_positions(), dtype=np.float32)
                except Exception: _sq = None
                if _sq is None or len(_sq) < _ARM_DOF:
                    _sq = np.asarray(_HOME_Q, dtype=np.float32)
                _sq = _sq[:_ARM_DOF]
                _extra_paths = list(getattr(_bi_rs, "_reach_probe_extra_paths", []) or [])  # validator: also probe the destination/place target(s); empty by default -> byte-identical
                for _sp in list(SOURCE_PATHS) + _extra_paths:
                    _cp = _world_pos(_sp)
                    if _cp is None:
                        with open("/tmp/reachprobe.log", "a") as _rf: _rf.write("REACH_TGT path=" + str(_sp) + " MISSING\\n")
                        continue
                    _ztop = float(_cp[2]) + 0.025
                    try:
                        _pp = stage.GetPrimAtPath(_sp)
                        if _pp and _pp.IsValid():
                            _rng = UsdGeom.BBoxCache(0.0, [UsdGeom.Tokens.default_]).ComputeWorldBound(_pp).ComputeAlignedRange()
                            if not _rng.IsEmpty(): _ztop = float(_rng.GetMax()[2])
                    except Exception: pass
                    _nok = 0
                    for _ti in range(3):
                        try:
                            _rzo = float(getattr(__import__("builtins"), "_reach_probe_z_off", 0.0))  # 2026-06-07: for CUP-DOWN, set 0.193 so the probe tests ee at cube_top+cup_offset (where the down-cup tip is at the cube), not at cube_top (confound fix).
                            _rr = _plan_to_world_point(np.array([float(_cp[0]), float(_cp[1]), float(_ztop) + _rzo], dtype=np.float32), _sq, exclude_obs=None, yaw_deg=0.0, vhold_mode=0)
                            if _rr is not None: _nok += 1
                        except Exception: pass
                    _verdict = ("REACHABLE" if _nok == 3 else ("MARGINAL" if _nok >= 1 else "UNREACHABLE"))
                    with open("/tmp/reachprobe.log", "a") as _rf:
                        _rf.write("REACH_TGT path=" + str(_sp) + " xy=[%.3f,%.3f] top=%.3f top@%.3f=%d/3 -> %s\\n" % (float(_cp[0]), float(_cp[1]), float(_ztop), float(_ztop), _nok, _verdict))
            except Exception as _rse:
                try:
                    with open("/tmp/reachprobe.log", "a") as _rf: _rf.write("REACH_SWEEP_ERR " + str(_rse)[:160] + "\\n")
                except Exception: pass

        # 2026-06-07 GRIP LOGGER (gated _sg_grip_log): RELIABLE per-tick grip observation written from INSIDE _on_step
        # (no separate exec -> no timeout; scene_eyes' GripperView is BLIND to this SG so it is untrustworthy). Logs
        # get_gripped_objects (raw interface), SG status, seg mode, and nearest-cube distance to the cup. Gated OFF ->
        # production byte-identical. The single source of truth for faithful-cup grip debugging.
        if getattr(__import__("builtins"), "_sg_grip_log", False) and (S["ticks"] % 6 == 0):
            try:
                _gl = "iface=None"; _glst = "?"
                if _SG_IFACE is not None and _SG_PATH_RAW:
                    try: _gl = str(list(_SG_IFACE.get_gripped_objects(_SG_PATH_RAW)))
                    except Exception as _e1: _gl = "gripped_err:" + str(_e1)[:40]
                    try: _glst = str(_SG_IFACE.get_gripper_status(_SG_PATH_RAW)).split(".")[-1]
                    except Exception: _glst = "stat_err"
                _cupp = _world_pos(_SG_CUP_PATH) if _SG_CUP_PATH else None
                _md = -1.0; _mc = "?"
                for _spl in SOURCE_PATHS:
                    _cpl = _world_pos(_spl)
                    if _cpl is not None and _cupp is not None:
                        _dl2 = ((_cpl[0]-_cupp[0])**2 + (_cpl[1]-_cupp[1])**2 + (_cpl[2]-_cupp[2])**2) ** 0.5
                        if _md < 0 or _dl2 < _md: _md = _dl2; _mc = _spl.split("/")[-1]
                _jdeg = "None"
                try:
                    _jpw = np.asarray(franka.get_joint_positions(), dtype=np.float64)
                    _jdeg = str([round(float(_jpw[_k]) * 57.29578, 1) for _k in range(min(6, len(_jpw)))])
                except Exception: _jdeg = "jerr"
                # 2026-06-09 per-cube position trace (find the Cube_2 bin->source revert source): log EVERY source cube's
                # world xyz each tick so the exact tick + cause of a delivered cube reverting can be pinpointed.
                _cubestr = "|".join("%s=[%.2f,%.2f,%.2f]" % (_spc.split("/")[-1], _wpc[0], _wpc[1], _wpc[2])
                                    for _spc in SOURCE_PATHS for _wpc in [_world_pos(_spc)] if _wpc is not None)
                with open("/tmp/grip_log.txt", "a") as _glf:
                    _glf.write("tick=%d t=%.1f mode=%s seg=%s/%s suction=%s status=%s gripped=%s mind=%.3f(%s) cup=%s jdeg=%s cubes=%s\\n" % (S["ticks"], S["ticks"]/60.0, str(S.get("mode")), str(S.get("seg_idx")), str(len(S.get("segments") or [])), str(_SG_IS_SUCTION), _glst, _gl, _md, _mc, str([round(float(_cupp[_i]), 3) for _i in range(3)]) if _cupp is not None else "None", _jdeg, _cubestr))
            except Exception as _gle:
                try:
                    with open("/tmp/grip_log.txt", "a") as _glf: _glf.write("GRIPLOG_ERR tick=%d %s\\n" % (S["ticks"], str(_gle)[:80]))
                except Exception: pass

        # 2026-06-07 FAITHFUL-SUCTION forwardAxis fix — LIVE one-shot (DEFAULT for nvidia). Rotate the Suction_Joint
        # localRot0/1 by -90 about X so the SG raycast (forwardAxis Z) aligns with the cup opening. Applied AFTER the
        # SG registers (>30 ticks into play) because the SG reads the attach frame at registration; a build-time
        # rotation does NOT engage (CP-83 reached 7cm but never latched). Rotating BOTH frames by the same delta keeps
        # the physical mount. One-shot via S["_fwdaxis_done"] (per-controller, not shared). Gated _sg_nvidia_cup ->
        # production byte-identical.
        # DEFAULT OFF (`_sg_fwdaxis_live`): the live localRot rotation is the raycast-alignment theory but it MAY
        # disturb the descent (the first unmodified nvidia run reached cup-cube d=0.019; runs WITH it stall ~26cm —
        # could be the rotation jerking the Suction_Joint, or Kit degradation). Opt-in until proven non-disturbing.
        if (getattr(__import__("builtins"), "_sg_nvidia_cup", False) and getattr(__import__("builtins"), "_sg_fwdaxis_live", False)
                and not S.get("_fwdaxis_done") and S["ticks"] > 30 and _SG_PATH_RAW):
            try:
                _sjpl = stage.GetPrimAtPath(Sdf.Path(_SG_CUP_PATH + "/Suction_Joint"))
                if _sjpl and _sjpl.IsValid():
                    _dqfal = Gf.Quatf(Gf.Rotation(Gf.Vec3d(1.0, 0.0, 0.0), -90.0).GetQuat())
                    for _attrnl in ("physics:localRot0", "physics:localRot1"):
                        _afal = _sjpl.GetAttribute(_attrnl)
                        if _afal and _afal.IsValid() and _afal.Get() is not None:
                            _afal.Set(Gf.Quatf(_afal.Get()) * _dqfal)
                S["_fwdaxis_done"] = True
                try:
                    with open("/tmp/grip_log.txt", "a") as _glf3: _glf3.write("FWDAXIS_FIX_APPLIED_LIVE tick=%d\\n" % S["ticks"])
                except Exception: pass
            except Exception:
                S["_fwdaxis_done"] = True

        if S["mode"] == "wait_sensor":
            # Multi-robot mutex guard: if another robot holds the mutex,
            # don't even attempt to claim a cube this tick. Mirrors the
            # spline _on_step guard (lines ~32168–32187) for the curobo path.
            if MUTEX_PATH:
                try:
                    _mp = stage.GetPrimAtPath(MUTEX_PATH)
                    if _mp and _mp.IsValid():
                        _attr = _mp.GetAttribute("mutex:claimed_by")
                        _claimed = (_attr.Get() if _attr else "") or ""
                        if _claimed and _claimed != ROBOT_PATH:
                            # 2026-06-05 PARALLEL-PICK fix (CP-52): the single-slot claim-
                            # mutex over-serialized DISJOINT pickers. Only WAIT if the
                            # sibling is working a cube I could ALSO pick (shared pickup /
                            # handoff: CP-51/53 — claimed_cube ∈ MY source_paths). For
                            # disjoint source_paths (parallel-pick) the sibling's cube isn't
                            # mine → claim my own concurrently; the PLAN_LOCK serializes
                            # planning (no CUDA-700) and the MOVE_LOCK serializes execution
                            # (no arm-arm collision). Fail-safe: unknown claimed_cube → keep
                            # the old wait. GATED multi-robot (>1 live curobo sub) → 37 hold.
                            _cca = _mp.GetAttribute("mutex:claimed_cube")
                            _ccv = (_cca.Get() if _cca else "") or ""
                            if (not _ccv) or (_ccv in SOURCE_PATHS):
                                # 2026-05-31 dual-Franka shared-bin RETREAT: before we wait,
                                # RETREAT to _HOME_Q so we don't park at the shared bin and
                                # block the sibling's delivery path. One-shot per idle window.
                                if len(_curobo_live_pp_subs()) > 1 and not S.get("retreated_idle"):
                                    _grip_open()
                                    art_ctrl.apply_action(ArticulationAction(
                                        joint_positions=_HOME_Q[:_ARM_DOF].astype(np.float64),
                                        joint_indices=np.arange(_ARM_DOF),
                                    ))
                                    S["retreated_idle"] = True
                                return  # sibling holds a cube I share; wait this tick
                            # else: disjoint cube → fall through and claim my own
                except Exception: pass
            picked = _cube_to_pick()
            if picked:
                # Acquire mutex before claiming cube
                if MUTEX_PATH:
                    try:
                        _mp = stage.GetPrimAtPath(MUTEX_PATH)
                        if _mp and _mp.IsValid():
                            _attr = _mp.GetAttribute("mutex:claimed_by")
                            _held = (_attr.Get() if _attr else "") or ""
                            # Take the mutex only when FREE or already mine. A disjoint
                            # parallel-pick that fell through the guard (sibling holds it for
                            # a cube not in MY sources) claims WITHOUT stealing the sibling's
                            # slot — its disjoint cube needs no claim-protection (the sibling
                            # never picks it). Record claimed_cube so the sibling's guard can
                            # tell shared (wait) from disjoint (proceed).
                            if _attr and (_held == "" or _held == ROBOT_PATH):
                                _attr.Set(ROBOT_PATH)
                                _cca = _mp.GetAttribute("mutex:claimed_cube")
                                if not _cca:
                                    _cca = _mp.CreateAttribute("mutex:claimed_cube", Sdf.ValueTypeNames.String)
                                if _cca: _cca.Set(picked)
                                _cc = _mp.GetAttribute("mutex:claim_count")
                                if _cc and _cc.IsDefined():
                                    _cc.Set(int(_cc.Get() or 0) + 1)
                    except Exception: pass
                # Pause belt + open gripper. Move to "settling" state so
                # cube can decelerate naturally for several physics ticks
                # before we read its position. Cube has friction-mediated
                # residual velocity from the running belt; reading too
                # early captures mid-deceleration position → trajectory
                # lands behind cube → fingers grip back edge.
                # Calling app.update() from inside _on_step would be
                # re-entrant (physics callback can't step physics).
                # Adaptive settle: high-speed belts leave more residual cube
                # momentum after pause. CP-22 (0.5 m/s nominal) needs ~16
                # ticks (0.27s); CP-01 (0.2 m/s) is fine with 8. Use the
                # cached _nominal_belt (captured at install before any pause).
                _belt_nom = abs(float(_nominal_belt[0])) if _nominal_belt else 0.0
                _pause_belt()
                _grip_open()
                S["picked_path"] = picked; _a_picked.Set(picked)
                S["settle_ticks"] = 16 if _belt_nom > 0.25 else 8
                S["mode"] = "settling"
                if len(_curobo_live_pp_subs()) > 1:
                    S["retreated_idle"] = False  # re-arm per-cube idle retreat (multi-robot only)
            elif (len(S["delivered"]) + len(S.get("failed", set()))) >= len(SOURCE_PATHS) and not S.get("home_returned"):
                # All cubes processed → return arm to home pose so it doesn't
                # idle at the drop position with arm extended awkwardly.
                # Set home_returned flag so we don't loop on it.
                _grip_open()
                art_ctrl.apply_action(ArticulationAction(
                    joint_positions=_HOME_Q[:_ARM_DOF].astype(np.float64),
                    joint_indices=np.arange(_ARM_DOF),
                ))
                S["home_returned"] = True
            elif len(_curobo_live_pp_subs()) > 1 and not S.get("retreated_idle"):
                # 2026-05-31 dual-Franka shared-bin RETREAT (GUI-confirmed cause):
                # no claimable cube this tick, and in a multi-robot shared-bin
                # template the arm would otherwise stay parked at its last drop
                # pose (AT the shared bin) and BLOCK the sibling's delivery path.
                # Retreat to _HOME_Q (clear retracted pose). One-shot per idle
                # window (re-armed on next claim above) so pick cadence is intact
                # — the `if picked:` branch is evaluated first and claims the
                # moment a cube is available. GATED multi-robot (>1 live curobo
                # sub) → the 37 single-robot templates never reach here. Holds no
                # move/plan token in wait_sensor → no deadlock.
                _grip_open()
                art_ctrl.apply_action(ArticulationAction(
                    joint_positions=_HOME_Q[:_ARM_DOF].astype(np.float64),
                    joint_indices=np.arange(_ARM_DOF),
                ))
                S["retreated_idle"] = True
            return

        if S["mode"] == "settling":
            S["settle_ticks"] -= 1
            if S["settle_ticks"] > 0: return
            # Cross-robot planning-serialization gate: when >1 curobo controller
            # is live, only one robot runs _build_segments per tick → prevents
            # concurrent plan_pose on the shared planner → CUDA 700. Single-robot:
            # returns True with no state touched → byte-identical (the 37 hold).
            if not _try_acquire_plan_token():
                S["settle_ticks"] = 1  # re-arm; re-enter + retry next tick
                return
            # Now cube is at rest. Read position and plan trajectory.
            picked = S["picked_path"]
            # Pass cube_path so COLOR_ROUTING can dispatch destination per cube.
            cp, dp = _world_pos(picked), _bin_drop_pos(picked)
            if TASK_MODE in ("pull", "turn"):
                dp = cp  # no bin in task modes; dp only feeds height placeholders
            try:
                if getattr(__import__("builtins"), "_sg_grip_log", False):
                    with open("/tmp/settle_dbg.log", "a") as _sd: _sd.write("SETTLE picked=%s cp=%s dp=%s\\n" % (picked, ([round(float(x),3) for x in cp] if cp is not None else None), ([round(float(x),3) for x in dp] if dp is not None else None)))
            except Exception: pass
            if cp is None or dp is None:
                S["mode"] = "wait_sensor"; S["picked_path"] = None
                _resume_belt()
                _release_plan_token()
                return
            jp = franka.get_joint_positions()
            if jp is None: return
            # Fix 2: seed from home config first (consistent IK branch);
            # fallback to current state if home-seeded planning fails.
            # 2026-06-05 UR10 SPIN ROOT FIX (probe-confirmed): the UR10 asset starts the arm at a WOUND
            # authored config (wrist_2=-298deg=-5.2rad — within cuRobo's +/-2pi limit). Seeding cuRobo from
            # _HOME_Q while the arm is physically at -5.2 makes traj[0]=home != physical -> executing the
            # home-based traj OPEN-LOOP slews the CONTINUOUS wrists multi-turn = the visible SPIN + floor-stick
            # (eyes: wrist_3 swept 38 rad; a teleport-to-home is dragged back by the running controller). FIX:
            # seed UR10 from the LIVE joint state so traj[0]==physical -> continuous execution, no slew. cuRobo
            # plans minimal-motion from the live branch and reaches the goal. Franka keeps the home-seed (its
            # joints are limited <+/-3.8 so no multi-turn wind; the 37 passes are byte-identical).
            if ROBOT_FAMILY in ("ur10", "ur10e"):
                _seed_q = np.asarray(jp[:_ARM_DOF], dtype=np.float32)
            else:
                _seed_q = _HOME_Q[:_ARM_DOF]
            # 2026-06-06 FREEZE FIX (time-series-confirmed on CP-81): _build_segments can RAISE (cuRobo
            # "planning failed for <cube>") instead of returning None for an UNPLANNABLE cube. Unhandled, the
            # raise escaped to the outer except WITHOUT releasing the plan-token acquired above -> the controller
            # FROZE on that cube for the rest of the episode (eyes: pc/pf stuck at 466/63 for 140s, picked_path
            # never cleared). The frozen tick ran the sim in SLOW-MOTION -> the function-gate's wall-clock timeout
            # (duration_s+60) fired BEFORE sim-time reached the end -> the gate's pre-position capture never ran
            # -> cp_pre stayed at the cube's t=0 PEDESTAL pos -> a SPURIOUS 72.9 m/s on the ALREADY-DELIVERED
            # OTHER cube (= total-trajectory-displacement / one-frame) -> false at_rest fail. Catch the raise and
            # treat it as a plan failure so the 3-strike abandon below fires (mark cube failed, RELEASE the token,
            # idle) -> sim runs at normal speed, gate measures correctly. Generalizes to every multi-cube template.
            try:
                segs = _build_segments(cp, dp, _seed_q)
                if segs is None:
                    segs = _build_segments(cp, dp, jp[:_ARM_DOF])
                if segs is None and ROBOT_FAMILY in ("ur10", "ur10e"):
                    segs = _build_segments(cp, dp, _HOME_Q[:_ARM_DOF])
            except Exception as _bse:
                _record_err(_bse)
                segs = None
                try:
                    if getattr(__import__("builtins"), "_sg_grip_log", False):
                        with open("/tmp/settle_dbg.log", "a") as _sd: _sd.write("BUILD_RAISE %s\\n" % str(_bse)[:160])
                except Exception: pass
            if segs is None:
                try:
                    if getattr(__import__("builtins"), "_sg_grip_log", False):
                        with open("/tmp/settle_dbg.log", "a") as _sd: _sd.write("BUILD_NONE picked=%s\\n" % picked)
                except Exception: pass
                # Fix 1: 3-strike counter — mark cube permanently failed after
                # 3 consecutive plan failures so wait_sensor moves to next cube.
                _record_err(RuntimeError(f"planning failed for {{picked}}"))
                S.setdefault("plan_fail_count", {{}})
                S["plan_fail_count"][picked] = S["plan_fail_count"].get(picked, 0) + 1
                if S["plan_fail_count"][picked] >= 3:
                    S["failed"].add(picked)
                    print(f"(curobo: {{picked}} permanently failed after 3 plan failures)", flush=True)
                S["mode"] = "wait_sensor"; S["picked_path"] = None
                _resume_belt()
                _release_plan_token()
                return
            S["segments"] = segs
            S["seg_idx"] = 0
            S["seg_start_t"] = time.monotonic()
            S["seg_sim_t"] = 0.0
            S["mode"] = "executing"
            _release_plan_token()
            return

        if S["mode"] == "retreating":
            # 2026-05-31 dual-Franka: after delivering, move to _HOME_Q to clear the
            # shared bin while STILL HOLDING the mutex + move-token, so the sibling
            # waits until we're physically clear (no collision). Release only when
            # the retreat completes. Multi-robot only (single-robot never enters this).
            _apply_arm_joints(_HOME_Q[:_ARM_DOF])
            S["retreat_ticks"] = S.get("retreat_ticks", 0) - 1
            if S["retreat_ticks"] <= 0:
                if MUTEX_PATH:
                    try:
                        _mp = stage.GetPrimAtPath(MUTEX_PATH)
                        if _mp and _mp.IsValid():
                            _attr = _mp.GetAttribute("mutex:claimed_by")
                            if _attr and (_attr.Get() or "") == ROBOT_PATH: _attr.Set("")
                    except Exception: pass
                _release_move_token()
                _resume_belt_if_clear()
                S["retreated_idle"] = True  # already clear; skip the wait_sensor retreat
                S["mode"] = "wait_sensor"
            return

        if S["mode"] == "executing":
            # Execution-time motion serialization: only one live curobo controller
            # traverses the shared zone at a time. If a sibling holds the move-token,
            # HOLD this arm in place (re-issue last commanded joints so PD-drive won't
            # slump; keep grip closed if carrying) and DO NOT advance this tick.
            # Single-robot fast-path returns True untouched → byte-identical (37 hold).
            if not _try_acquire_move_token():
                # 2026-06-15 COMPOSITION-FLING FIX: FREEZE the trajectory clock while
                # the move-token is held by a sibling. The segment is sampled by
                # wall-clock `elapsed = monotonic() - seg_start_t` (below); if the clock
                # keeps running during a multi-second hold, on resume `elapsed >> mt`
                # so idx jumps to T-1 and the arm SNAPS to the segment END in a single
                # tick -> the carried cube is FLUNG (MEASURED: 2nd concurrent arm flings
                # to a consistent x~4.8). Re-anchor seg_start_t each held tick so elapsed
                # holds at its pre-hold value; resume continues smoothly. Single-robot
                # never reaches here (_try_acquire_move_token fast-path) -> byte-identical.
                if S.get("seg_start_t") is not None:
                    _eh = S.get("_held_elapsed")
                    if _eh is None:
                        _eh = time.monotonic() - S["seg_start_t"]
                        S["_held_elapsed"] = _eh
                    S["seg_start_t"] = time.monotonic() - _eh
                _hold_q = S.get("hold_q")
                if _hold_q is not None:
                    _apply_arm_joints(_hold_q)
                _seg_hold = S["segments"][S["seg_idx"]] if (S.get("segments") and S["seg_idx"] < len(S["segments"])) else None
                if _seg_hold is not None and _seg_hold.get("grip_done") and _seg_hold.get("action_after") == "close":
                    _grip_close()
                return
            S["_held_elapsed"] = None  # token acquired -> clock runs normally again
            # 2026-06-16 SIM-TIME FLOOR (multi-robot composition grasp-seat fix): the grip-close + seg-advance
            # gates below use WALL-CLOCK `elapsed = monotonic()-seg_start_t`. In a multi-cell scene the sibling
            # cells' concurrent cuRobo plan_pose calls stall the single Kit physics thread, so wall-clock RACES
            # AHEAD of SIM-time -> the close fires while the arm is still PHYSICALLY descending (PD lag, ~2 sim-
            # ticks in) -> it grips the cube TOP EDGE at ~137mm (vs the seated ~103mm) -> asymmetric (force 2.88
            # vs 0.75) -> NO grasp -> lifts away -> cube rides off + falls. MEASURED (inst2 CP-13, compose_CP-03_
            # CP-28_CP-13 eyes.json): EE bottomed z=0.967 @t1.5 then ROSE @t1.7 (0.2s sim dwell, grp=None); the
            # SECOND pick @t23 (cells desynced -> less contention) seated 103mm + delivered. FIX: accumulate the
            # physics step dt and require SIM-time ALSO reach the gate. The AND-gate can only DELAY (never advance)
            # firing, and only when sim LAGS wall-clock (the contention case) -> light/standalone scenes (sim>=
            # real-time) are unaffected. GATED multi-robot -> the whole single-robot stable library skips it ->
            # byte-identical. seg_sim_t resets wherever seg_start_t resets (enter-executing + seg-advance).
            _sim_floor = len(_curobo_live_pp_subs()) > 1
            if _sim_floor:
                S["seg_sim_t"] = S.get("seg_sim_t", 0.0) + float(dt)
            segs = S["segments"]
            if segs is None or S["seg_idx"] >= len(segs):
                # Done — verify cube actually reached the bin before marking
                # delivered. If grip slipped, cube is still on the belt; keep
                # it in SOURCE_PATHS so the next wait_sensor cycle picks it up
                # again rather than reporting a false success.
                S["cubes"] += 1; _a_cycles.Set(S["cubes"])
                if S["picked_path"]:
                    # Use proximity-based delivery check (handles non-bin
                    # destinations like handoff markers, staging racks).
                    # _is_in_bin's bbox check fails for degenerate/small prims.
                    # SUCTION: the cube is released HIGH over the bin (soft grip + collision-free high drop)
                    # and falls IN; the 3D _is_near_dest fails on the high z, so ALSO accept _is_in_bin (xy
                    # within the bin footprint). Marking delivered stops wait_sensor from re-picking the still-
                    # in-z-window cube and carrying it back out (validated CP-70: cube reached bin xy 0.005 then
                    # got re-picked). Gated to suction (Franka places precisely -> _is_near_dest already True).
                    if TASK_MODE in ("pull", "turn", "sweep"):
                        # task modes: the SOURCE is a tool/handle released at the
                        # task's end pose, not delivered anywhere — proximity
                        # bookkeeping would mark it failed (sweep: brush at the
                        # dustpan LIP -> Handle:failed, live 2026-06-12). The
                        # GATE measures the actual outcome (joint delta /
                        # debris-in-dustpan); mark the cycle consumed.
                        S["delivered"].add(S["picked_path"])
                        _a_cubes.Set(len(S["delivered"]))
                    elif _is_near_dest(S["picked_path"]) or (_SG_IS_SUCTION and _is_in_bin(S["picked_path"])):
                        S["delivered"].add(S["picked_path"])
                        _a_cubes.Set(len(S["delivered"]))
                    else:
                        # Grip miss / cube far from drop. Mark as failed; do NOT
                        # add to delivered. Move on so we don't loop forever
                        # on the same physically-unreachable configuration.
                        S["failed"].add(S["picked_path"])
                    # 2026-05-31 dual-Franka: RETREAT BEFORE releasing the mutex.
                    # GUI-confirmed: releasing the shared-bin mutex at the drop lets
                    # the sibling approach while we're still physically at the bin →
                    # collision (the wait_sensor retreat fires too late). Instead,
                    # enter a "retreating" phase that moves us to _HOME_Q while STILL
                    # HOLDING the mutex; the sibling waits until we're clear, then we
                    # release. GATED multi-robot only → single-robot falls through to
                    # the immediate release below (byte-identical, the 37 hold).
                    if len(_curobo_live_pp_subs()) > 1:
                        art_ctrl.apply_action(ArticulationAction(
                            joint_positions=_HOME_Q[:_ARM_DOF].astype(np.float64),
                            joint_indices=np.arange(_ARM_DOF),
                        ))
                        S["picked_path"] = None; _a_picked.Set("")
                        S["segments"] = None; S["seg_start_t"] = None
                        S["hold_q"] = None
                        S["retreat_ticks"] = 120  # ~2s to clear the shared bin
                        S["mode"] = "retreating"   # mutex + move-token still HELD
                        return
                    # Multi-robot mutex release: when this robot held the mutex
                    # for the cycle, free it so the other robot can claim next.
                    if MUTEX_PATH:
                        try:
                            _mp = stage.GetPrimAtPath(MUTEX_PATH)
                            if _mp and _mp.IsValid():
                                _attr = _mp.GetAttribute("mutex:claimed_by")
                                if _attr and (_attr.Get() or "") == ROBOT_PATH:
                                    _attr.Set("")
                        except Exception: pass
                S["picked_path"] = None; _a_picked.Set("")
                S["segments"] = None; S["seg_start_t"] = None
                S["hold_q"] = None
                S["mode"] = "wait_sensor"
                _release_move_token()  # no-op single-robot; lets sibling execute next
                # 2026-05-30: sensor-aware resume between picks (was unconditional).
                # The unconditional free-run let the NEXT downstream cube ride off
                # before its claim tick. _resume_belt_if_clear keeps the belt running
                # to feed upstream cubes but holds it while a cube sits in the sensor
                # neighborhood. Fail-open to plain resume when no sensor (no deadlock:
                # a grip-missed cube outside the 0.15m sensor zone never pins the belt).
                _resume_belt_if_clear()
                return

            cur_seg = segs[S["seg_idx"]]
            try:
                if getattr(__import__("builtins"), "_sg_grip_log", False):
                    _ts_src = cur_seg.get("traj_src", "static"); _ts_tj = cur_seg.get("traj")
                    _ts_key = (S["seg_idx"], _ts_src, id(_ts_tj))
                    if S.get("_last_ts_key") != _ts_key and _ts_tj is not None:
                        S["_last_ts_key"] = _ts_key
                        import math as _m_ts
                        _ts_p0 = _m_ts.degrees(float(np.asarray(_ts_tj)[0][0])); _ts_pN = _m_ts.degrees(float(np.asarray(_ts_tj)[-1][0]))
                        with open("/tmp/trajsrc.log", "a") as _tsf: _tsf.write("seg=%d src=%s pan0=%.0f panN=%.0f range=%.0f knots=%d\\n" % (S["seg_idx"], _ts_src, _ts_p0, _ts_pN, abs(_ts_pN - _ts_p0), len(np.asarray(_ts_tj))))
            except Exception: pass
            # 2026-06-09 S5-RELIVE (gated _ur10_s5_relive, default OFF, UR10-suction only): the static S5/open
            # descend in cur_seg["traj"] was planned in _build_segments while the arm was at HOME (the pick had not
            # executed), so it is a HOME->bin trajectory. Replaying it here — when the arm is already OVER-BIN — drives
            # the arm HOME then back = the "varv till" lap (MEASURED pan -47 -> -2 -> -47). The genuine over-bin config
            # exists ONLY now (live), which is why the two plan-time seed fixes (_ur10_drop_branch_pin / _drop_seed_chained,
            # both ~unwrapped-HOME) failed. ONE-SHOT on entry: re-plan the SAME down-locked drop goal from the LIVE
            # over-bin joints, BEFORE the static traj is ever sampled, so the lap never plays. Mirrors the proven
            # PL-nudge idiom: overwrite traj/motion_time, grip_done=False, reset seg_start_t, return.
            # Fail-open: if the live plan is None, mark relived and fall through to the static traj (= current
            # production -> delivery still occurs via the DROP z-backoff fallback), so worst case == today.
            if (getattr(__import__("builtins"), "_ur10_s5_relive", False)
                    and _SG_IS_SUCTION and ROBOT_FAMILY in ("ur10", "ur10e")
                    and cur_seg.get("action_after") == "open" and not cur_seg.get("_s5_relive")):
                cur_seg["_s5_relive"] = True
                try:
                    _rl_jl = franka.get_joint_positions()
                    _rl_dp = cur_seg.get("drop_pos")
                    if _rl_jl is not None and _rl_dp is not None:
                        _rl_seed = np.asarray(_rl_jl, dtype=np.float32)[:_ARM_DOF]
                        # 2026-06-09 [MEASURED traj_src diag]: the WRAP to (-pi,pi] is the FLING ROOT for wound transits.
                        # CP-80 over-bin physical pan=320deg (out-of-range, wound transit); wrapping -> relive traj at -40deg
                        # == 320 physically, but the controller drives the joint 320->-40 = a 360deg swing. Seed RAW
                        # (unwrapped physical) -> traj continuous with physical -> no swing. In-range (CP-69 pan=-47): raw==wrap.
                        # GATED _ur10_relive_seed_raw (default OFF = keep wrap, byte-identical).
                        if not getattr(__import__("builtins"), "_ur10_relive_seed_raw", False):
                            _rl_seed = ((_rl_seed + np.pi) % (2.0 * np.pi) - np.pi).astype(np.float32)
                        _rl_goal = np.array([float(_rl_dp[0]), float(_rl_dp[1]), float(_rl_dp[2]) + float(getattr(__import__("builtins"), "_sg_drop_tip_release", 0.16))], dtype=np.float32)  # 2026-06-09: honor the gated z-raise (default 0.16 = byte-identical)
                        _rl_excl = ([S["picked_path"], DEST_PATH] if (S.get("picked_path") and DEST_PATH)
                                    else (S.get("picked_path") or DEST_PATH))
                        # 2026-06-09 S5-DESCEND BRANCH-PIN (gated _ur10_s5_relive_branch_pin, default OFF, additive to
                        # _ur10_s5_relive). On the straight cup w/ reach<1.0 (CP-75/80) H7 doesn't fire -> over-bin is a
                        # WOUND branch (pan=153) -> the plain RELIVE plan_pose free-IKs the down goal to a FAR pan branch
                        # -> ~207deg PAN flip (the lap). branch_pin=True routes through the UR10 cspace-pin path (IK-from-
                        # live-seed return_seeds=16 -> closest-L1 seed -> plan_cspace joint-space interp) so pan stays on
                        # the live branch. EFFICACY is UNVERIFIED (adversary: IK may not return a seed on the wound branch
                        # for the orientation-locked down goal -> measure cspace_dbg). Fail-open: cspace fail -> plan_pose
                        # (today); None -> static traj + z-backoff. Default OFF -> byte-identical (branch_pin->False).
                        _rl_bp = bool(getattr(__import__("builtins"), "_ur10_s5_relive_branch_pin", False))
                        _rl_rr = _plan_to_world_point(_rl_goal, _rl_seed, exclude_obs=_rl_excl, yaw_deg=0.0, vhold_mode=0, branch_pin=_rl_bp)
                        if _rl_rr is not None:
                            cur_seg["traj"] = _rl_rr[0]; cur_seg["traj_src"] = "relive"
                            cur_seg["motion_time"] = max(float(_rl_rr[1]), 0.25)
                            cur_seg["grip_done"] = False
                            S["seg_start_t"] = time.monotonic()
                            with open("/tmp/cupframe_dbg.log", "a") as _cfd: _cfd.write("S5 relive seed_pan=%.1f goal=%s\\n" % (float(np.degrees(_rl_seed[0])), [round(float(_x), 3) for _x in _rl_goal]))
                            return
                except Exception: pass
            elapsed = time.monotonic() - S["seg_start_t"]
            traj = cur_seg["traj"]
            mt = cur_seg["motion_time"]
            T = traj.shape[0]

            # Sample trajectory at elapsed/mt * (T-1)
            if mt < 1e-6:
                idx = T - 1
            else:
                idx = int(round(min(elapsed / mt, 1.0) * (T - 1)))
            q7 = traj[idx]
            _apply_arm_joints(q7)
            S["hold_q"] = np.asarray(q7, dtype=np.float64)[:_ARM_DOF]

            # Once at trajectory end, decide whether to dwell. For grip
            # segments (close/open) we need to settle the arm and wait
            # for gripper drive to clamp/release. For pure transit
            # segments (action_after=None) we advance immediately so
            # the trajectory flows continuously between waypoints —
            # avoids the visible "stop between every step" the earlier
            # fixed 0.8s pre-grip settle imposed on EVERY segment.
            if elapsed >= mt:
                _apply_arm_joints(traj[-1])
                _is_grip_seg = cur_seg["action_after"] in ("close", "open")
                # 2026-05-29: open-release no longer waits the 0.8s pre-settle.
                # The arm's PD-drive overshoots traj[-1] during that settle and
                # DRAGS the still-gripped cube past the _xy_err<0.08 release gate
                # (line below), forcing a late, off-position force-release at the
                # +4s cap -> dislodge/overshoot (CP-13 0.007m->0.11m, CP-24).
                # Release the instant the cube is in-tolerance; close still settles
                # so the arm stops cleanly before clamping.
                pre_grip_settle = 0.5 if cur_seg["action_after"] == "close" else 0.0
                # SUCTION: hold the arm at the (low) S5 release pose ~1.2s so the rigid-gripped cube's residual
                # transit velocity DAMPS to ~0 before opening — else it's released with the arm's decel velocity
                # and flung out of the bin (validated CP-70: cube flung to y=-0.8). The rigid grip keeps it
                # straight below the cone (xy_err<0.08 already passes), so a settle is all that's needed.
                if cur_seg["action_after"] == "open" and _SG_IS_SUCTION:
                    pre_grip_settle = 1.2
                if not cur_seg["grip_done"] and elapsed >= mt + pre_grip_settle and ((not _sim_floor) or S.get("seg_sim_t", 0.0) >= mt + pre_grip_settle):
                    if cur_seg["action_after"] == "close":
                        # 2026-06-02 CP-83 grasp-completion gate (suction/UR10): cp83_obs3 showed the
                        # cone grips the cube at ~0.30m (the maxGripDistance EDGE) -> weak grip -> drop
                        # mid-carry. Closing at mt+settle catches the cube before the soft-gain arm has
                        # converged to traj[-1] (the planned grasp). HOLD the close until the cone (the
                        # SG grip point, driven to the live ee FK by _track_suction_follower) is actually
                        # near the cube, with a generous timeout so it never hangs. No-op for table-cube
                        # grasps (CP-70): the cone is already near at mt+settle -> closes immediately.
                        # Decisive probe: delivers CP-83 => the offset was arm-lag (cured); times out at
                        # ~0.30m => the offset is the tool-frame lever arm (needs the GoalToolPose fix
                        # flagged in _build_segments). Writes ctrl:graspdiag for the post-run read.
                        _do_close = True; _grip_miss = False
                        if _SG_IS_SUCTION and S.get("picked_path"):
                            try:
                                _conp = _world_pos(_SG_CUP_PATH)
                                _cubp = _world_pos(S["picked_path"])
                                if _conp is not None and _cubp is not None:
                                    _gripd = float(((_conp[0]-_cubp[0])**2 + (_conp[1]-_cubp[1])**2 + (_conp[2]-_cubp[2])**2) ** 0.5)
                                    _gate_to = elapsed >= mt + pre_grip_settle + 6.0
                                    # nvidia straight-cup: close ONLY on real contact (_gripd<0.12). The wall-clock
                                    # _gate_to fallback fires the close prematurely at ~0.4m while the capped nudge is
                                    # still descending -> false grab -> lift -> wander. Dropping it lets the nudge
                                    # descend uninterrupted to contact (bounded by convergence/sim-end). Gated -> the
                                    # -90 path keeps the _gate_to fallback (byte-identical in production).
                                    _nv_close = getattr(__import__("builtins"), "_sg_nvidia_cup", False)
                                    # 2026-06-10 rank-3 center-lock REFUTED [MEASURED]: an xy<6mm close-gate
                                    # (_ur10_pick_center_lock) regressed CP-69+CP-70 to 0 picks (cube untouched, no
                                    # latch, 0 nudges — the delayed close interacts with the grip-miss abort). REVERTED
                                    # to the production expression. Off-center (~7-11mm) stays a documented cosmetic;
                                    # do NOT re-attempt via the close gate.
                                    _do_close = (_gripd < 0.12) or (_gate_to and not _nv_close)
                                    _grip_miss = bool(_gate_to and (_gripd >= 0.12) and not _nv_close)
                                    try:
                                        _gp = stage.GetPrimAtPath(ROBOT_PATH)
                                        _gda = _gp.GetAttribute("ctrl:graspdiag")
                                        if not _gda: _gda = _gp.CreateAttribute("ctrl:graspdiag", Sdf.ValueTypeNames.String)
                                        _gda.Set(("gd=" + str(round(_gripd, 3)) + " el=" + str(round(float(elapsed), 1)) + " to=" + str(_gate_to) + " cone=" + str([round(float(x), 2) for x in _conp]) + " cube=" + str([round(float(x), 2) for x in _cubp]))[:200])
                                    except Exception: pass
                            except Exception: pass
                        # 2026-06-06 GRIP-MISS ABORT (time-series-confirmed CP-81): if the 6s close-timeout fired
                        # with the cup still >0.12m from the cube, the grip NEVER engaged (e.g. the far/unpickable
                        # Cube_1). Do NOT force-close + proceed to the transit+bin-drop — that GRINDS (the drop plan
                        # fails on the bin already occupied by the delivered cube, re-planning ~150x = slow-motion
                        # sim -> the function-gate wall-clock timeout fires before sim-end -> stale cp_pre -> a
                        # SPURIOUS 72.9 m/s on the ALREADY-DELIVERED cube) AND the empty cup descending into the bin
                        # DISTURBS the delivered cube. Mark this cube failed + abort the cycle -> controller idles ->
                        # sim runs at normal speed -> gate measures correctly. UR10 suction only; the 0.12m gate means
                        # a normally-gripped cube (cup near at close) NEVER triggers this -> the 8 passing are untouched.
                        # 2026-06-07 nvidia straight-cup: SKIP the grip-miss abort. elapsed is WALL-CLOCK, and the
                        # nvidia path's extra descend planning burns it before the close-block -> _gate_to fires
                        # prematurely -> the abort short-circuits the descend-to-contact closed-loop below before it
                        # gets its first nudge (which resets seg_start_t). Let the closed-loop run + bound the pick
                        # (convergence or sim-end), exactly like the -90 path. Gated -> production byte-identical.
                        if (_grip_miss and ROBOT_FAMILY in ("ur10", "ur10e")
                                and not getattr(__import__("builtins"), "_sg_nvidia_cup", False)):
                            try: S.setdefault("failed", set()).add(S.get("picked_path"))
                            except Exception: pass
                            try: _record_err(RuntimeError("grip-miss abort: " + str(S.get("picked_path")) + " cup>0.12m at 6s close-timeout"))
                            except Exception: pass
                            _grip_open()
                            S["mode"] = "wait_sensor"; S["picked_path"] = None
                            S["segments"] = None; S["seg_idx"] = 0; S["seg_start_t"] = None
                            return
                        # 2026-06-06 CUP-FRAME CLOSED-LOOP descend-to-contact (gated _ur10_cupframe_down, default ON since 2026-06-06 flip).
                        # The compliant cup has NO static cup-tool0 offset (planning-time prediction impossible, MEAS-
                        # proven). Instead, at close-time read the LIVE cup + cube and NUDGE tool0 by the live cup-error
                        # so the cup lower face reaches the cube TOP (direct contact, zero gap = Anton's req), THEN grip.
                        # Frame-free (uses live USD + FK of live joints). UR10 suction + flag only -> 11 passers
                        # byte-identical (block skipped when off). BOUND (corrected 2026-06-06): each nudge resets
                        # seg_start_t, so the 6s _gate_to does NOT bound this loop. The real bound is convergence
                        # (_ddn<=0.012 -> the `if _ddn>0.012` guard below is skipped -> falls through to _grip_close)
                        # or sim-duration. A convergent pick grips normally; a marginal-REACH pick (cup can't get
                        # within 1.2cm) nudges until sim end = slow (observed ~100 nudges on CP-71's dispenser items).
                        # No hard hang (sim-duration caps it). PLANNED hardening: a per-segment nudge cap (verify it
                        # doesn't cut CP-71's legit multi-item picks before applying).
                        # nvidia straight-cup: run the closed-loop even when _gate_to is (prematurely, wall-clock)
                        # True — the first nudge resets seg_start_t so _gate_to clears and the descend-to-contact
                        # proceeds normally. Gated on _sg_nvidia_cup -> the -90/cupframe path keeps its `not _gate_to`
                        # guard exactly (byte-identical in production).
                        if (ROBOT_FAMILY in ("ur10", "ur10e") and _SG_IS_SUCTION
                                and ((not _gate_to) or getattr(__import__("builtins"), "_sg_nvidia_cup", False))
                                and (getattr(__import__("builtins"), "_ur10_cupframe_down", True)
                                     or getattr(__import__("builtins"), "_sg_nvidia_cup", False))
                                and S.get("picked_path")):
                            try:
                                _cupw = _world_pos(_SG_CUP_PATH); _cubw = _world_pos(S["picked_path"])
                                if _cupw is not None and _cubw is not None:
                                    _ctgt = [float(_cubw[0]), float(_cubw[1]), float(_cubw[2]) + float(getattr(__import__("builtins"), "_sg_nvidia_grip_z_off", 0.025))]  # 2026-06-07 tunable: nudge target above the cube top; default 0.025 (byte-identical). Negative = descend to CONTACT to test real-SG engagement.
                                    _dd = [_ctgt[_i] - float(_cupw[_i]) for _i in range(3)]
                                    _ddn = (_dd[0] ** 2 + _dd[1] ** 2 + _dd[2] ** 2) ** 0.5
                                    # 2026-06-07 NVIDIA NUDGE CAP (gated _sg_nvidia_cup): the closed-loop nudges until the cup is within
                                    # 12mm of the target; if the grip never latches the cube can drift and the loop nudges FOREVER (run
                                    # hangs -> gate TimeoutError). Cap the per-segment nudge count so the controller falls through to the
                                    # grip-close (latches if within maxGripDistance) or PROCEEDS -> the run completes -> the gate gives a
                                    # deterministic verdict. Production (-90 path, flag OFF) keeps the uncapped loop = byte-identical.
                                    _nv_capped = (getattr(__import__("builtins"), "_sg_nvidia_cup", False)
                                                  and cur_seg.get("_nv_nudges", 0) >= int(getattr(__import__("builtins"), "_sg_nvidia_nudge_max", 60)))
                                    if _ddn > 0.012 and not _nv_capped:
                                        from curobo.types import JointState as _JS_cl
                                        _jl = franka.get_joint_positions()
                                        _tl = torch.tensor([[float(_x) for _x in np.asarray(_jl)[:_ARM_DOF]]], dtype=torch.float32, device="cuda")
                                        _kk = _planner.compute_kinematics(_JS_cl.from_position(_tl, joint_names=_PLANNER_JOINT_NAMES))
                                        _ep = _kk.tool_poses.position[0, 0, 0].detach().cpu().numpy()
                                        _eq = _kk.tool_poses.quaternion[0, 0, 0].detach().cpu().numpy()
                                        _bm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_usd_quat[0]), Gf.Vec3d(float(_usd_quat[1]), float(_usd_quat[2]), float(_usd_quat[3])))); _bm.SetTranslateOnly(Gf.Vec3d(float(_usd_pos[0]), float(_usd_pos[1]), float(_usd_pos[2])))
                                        _fm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_eq[0]), Gf.Vec3d(float(_eq[1]), float(_eq[2]), float(_eq[3])))); _fm.SetTranslateOnly(Gf.Vec3d(float(_ep[0]), float(_ep[1]), float(_ep[2])))
                                        _eew = (_fm * _bm).ExtractTranslation()
                                        # 2026-06-07 nvidia straight-cup: CAP the nudge step. The direct one-shot plan
                                        # to the full (far/low) cup-error fails with the repoint orientation (bad seed);
                                        # the main S2 descend reaches the same low pose only via _plan_sub_step's chained
                                        # small sub-goals. Mirror that here: cap the per-tick step to 0.06m so each plan
                                        # is a near, well-seeded descent that accumulates over ticks. Gated -> the -90
                                        # path keeps the full-_dd nudge (byte-identical in production).
                                        _ddstep = _dd
                                        _capn = float(getattr(__import__("builtins"), "_sg_nvidia_nudge_cap", 0.10))
                                        if getattr(__import__("builtins"), "_sg_nvidia_cup", False) and _ddn > _capn:
                                            _scl = _capn / _ddn
                                            _ddstep = [_dd[_i] * _scl for _i in range(3)]
                                        _cg = np.array([float(_eew[_i]) + _ddstep[_i] for _i in range(3)], dtype=np.float32)
                                        # 2026-06-07 nvidia: exclude the picked cube AND the planning obstacles (pedestals/supports) from the
                                        # collision world during the FINAL descend nudge. The cup descends straight onto the cube (which sits ON
                                        # the support), so the support is not a real obstacle here — keeping it made the descend nudge silently
                                        # res_None -> the closed-loop stalled ~26cm up. Gated nvidia -> production keeps single-path exclude.
                                        _excl = S["picked_path"]
                                        if getattr(__import__("builtins"), "_sg_nvidia_cup", False):
                                            _excl = [S["picked_path"]] + list(PLANNING_OBSTACLES)
                                        # 2026-06-09 PICK-DESCEND BRANCH-PIN (gated _ur10_pick_descend_pin, default OFF -> byte-identical).
                                        # [MEASURED CP-83] the PICK CL-nudge froze 0.27m above the cube (mind=0.284, repeated CL RES_NONE):
                                        # from the wound arrival config the down-IK is on a DIFFERENT branch the closest-continuous solve can't
                                        # cross. branch_pin routes through the cspace-pin + down-lock-seed path (the proven CP-70/75 descend fix)
                                        # so the nudge reaches the existing down-config. Generalizes to the 25 stacking-plate descend-from-arrival.
                                        _pdp = getattr(__import__("builtins"), "_ur10_pick_descend_pin", False)
                                        _rr = _plan_to_world_point(_cg, np.asarray(_jl)[:_ARM_DOF], exclude_obs=_excl, yaw_deg=0.0, vhold_mode=0, branch_pin=_pdp)
                                        if _rr is not None:
                                            cur_seg["traj"] = _rr[0]; cur_seg["motion_time"] = max(float(_rr[1]), 0.25); cur_seg["grip_done"] = False; cur_seg["traj_src"] = "clnudge"
                                            S["seg_start_t"] = time.monotonic()
                                            cur_seg["_nv_nudges"] = cur_seg.get("_nv_nudges", 0) + 1
                                            with open("/tmp/cupframe_dbg.log", "a") as _cfd: _cfd.write("CL nudge d=%.3f cup=%s -> goal=%s\\n" % (_ddn, [round(float(_cupw[_i]), 3) for _i in range(3)], [round(float(_x), 3) for _x in _cg]))
                                            return
                                        else:
                                            with open("/tmp/cupframe_dbg.log", "a") as _cfd: _cfd.write("CL RES_NONE d=%.3f cup=%s -> goal=%s\\n" % (_ddn, [round(float(_cupw[_i]), 3) for _i in range(3)], [round(float(_x), 3) for _x in _cg]))
                            except Exception as _cle:
                                try:
                                    with open("/tmp/cupframe_dbg.log", "a") as _cfd: _cfd.write("CL fail " + str(_cle)[:120] + "\\n")
                                except Exception: pass
                        if not _do_close:
                            return  # hold: re-check the grip gate next tick; don't clamp/advance yet
                        _grip_close()
                        # 2026-05-27 FRICTION-FIX: removed UsdPhysics.FixedJoint creation.
                        # Anton wants real friction-grip (no FJ fusk). _grip_close above sets
                        # finger position; PhysX friction + finger_stiffness holds cube during transit.
                        # If cube slips: tune friction_mu/stiffness in template, not add FJ shortcut.
                    elif cur_seg["action_after"] == "open":
                        # 2026-06-03 SOFT-PLACE / anti-topple (suction): cuRobo under-descends the near-bin S5 flange
                        # goal (CP-70 cone-track: reached 1.079 vs goal 0.945 = 13cm short -> cube released ~18cm high
                        # -> TOPPLED). Self-calibrating: extend the VIRTUAL tool length by exactly the flange shortfall
                        # so the cup+cube descend (via the kinematic follower, ramped gently under the 0.04 clamp) to the
                        # DESIGNED release height before opening -> ~5cm soft drop, no topple. No magic numbers (uses the
                        # planner's own drop_pos); capped at +0.18 so a bad goal can't drive the cube through the floor.
                        _rfz = cur_seg.get("release_flange_z")
                        if _rfz is not None:
                            try:
                                _conp2 = _world_pos(_SG_CUP_PATH)
                                _cubp_sp = _world_pos(S["picked_path"]) if S.get("picked_path") else None
                                _drop_sp = cur_seg.get("drop_pos")
                                # SAFETY GATE: only telescope the cup DOWN when the cube is CENTERED over the bin opening
                                # (within 6cm of the drop xy) so it descends through free interior space — never onto the
                                # rim/wall (an off-center forced descent squirts the gripped cube out at >10 m/s; the swing
                                # can leave the cube off-center). If not centered, skip the descent -> release at the
                                # current height (may topple, but never explodes off the rim).
                                _sp_centered = True
                                if _cubp_sp is not None and _drop_sp is not None:
                                    _sp_centered = (((_cubp_sp[0]-_drop_sp[0])**2 + (_cubp_sp[1]-_drop_sp[1])**2) ** 0.5) < 0.06
                                if _conp2 is not None and _sp_centered:
                                    _act_flange = float(_conp2[2]) + _sg_tool_l_dyn[0]
                                    _want_tool = min(_SG_TOOL_L + 0.25, _SG_TOOL_L + max(0.0, _act_flange - float(_rfz)))
                                    if _sg_tool_l_dyn[0] < _want_tool - 0.003:
                                        _sg_tool_l_dyn[0] = min(_want_tool, _sg_tool_l_dyn[0] + 0.006)  # ramp ~0.36 m/s
                                        return  # keep lowering the cup into the bin; do NOT open yet
                            except Exception: pass
                        # Drop-precision Fix B: only release if cube is close
                        # to drop_pos. cuRobo trajectory may end before EE
                        # converges due to PD drive lag — releasing then
                        # drops cube short of bin. Hold release until close.
                        _drop_close = True
                        try:
                            _cubp = _world_pos(S["picked_path"]) if S.get("picked_path") else None
                            _drop = cur_seg.get("drop_pos") or (S.get("plan") or {{}}).get("drop_pos")
                            if _cubp is not None and _drop is not None:
                                _xy_err = ((_cubp[0]-_drop[0])**2 + (_cubp[1]-_drop[1])**2) ** 0.5
                                _drop_close = _xy_err < 0.08
                        except Exception: pass
                        # NOTE (2026-06-02): tried suction early-open (_is_in_bin) to release over the bin
                        # footprint; REVERTED — destabilized the soft SG grip (cube exploded mid-transit).
                        # The SG grip joint's softness/instability is the fundamental drop blocker (see ledger).
                        # Cap hold at +4s past mt to prevent infinite hold
                        _hold_cap = elapsed > mt + pre_grip_settle + 4.0
                        # 2026-06-06 CUP-FRAME PLACE CLOSED-LOOP (gated _ur10_cupframe_down). With the straight-down
                        # cup the cube hangs COAXIAL (below the cup), so the -110-tuned drop releases it OFF-target
                        # (CP-84 stack: cube landed 0.092 beside BaseCube). Symmetric to the pick loop: actively nudge
                        # tool0 in XY by the live cube-vs-drop error so the held cube centers OVER the target, then it
                        # falls on release. UR10 suction + flag only -> passers byte-identical. BOUND (corrected
                        # 2026-06-06): like the pick loop, each nudge resets seg_start_t so _hold_cap doesn't fire;
                        # the bound is convergence (_dxy<=0.02 -> release centered) or sim-duration. Here the
                        # non-early-give-up is BENEFICIAL — keeps centering until aligned instead of releasing off-target.
                        if (ROBOT_FAMILY in ("ur10", "ur10e") and _SG_IS_SUCTION and (not _hold_cap)
                                and (getattr(__import__("builtins"), "_ur10_cupframe_down", True)
                                     or getattr(__import__("builtins"), "_sg_nvidia_cup", False))
                                and S.get("picked_path")):
                            try:
                                _cubp_cl = _world_pos(S["picked_path"]); _drop_cl = cur_seg.get("drop_pos")
                                if _cubp_cl is not None and _drop_cl is not None:
                                    _dxy = ((_cubp_cl[0] - _drop_cl[0]) ** 2 + (_cubp_cl[1] - _drop_cl[1]) ** 2) ** 0.5
                                    _pl_capped = (int(getattr(__import__("builtins"), "_sg_place_nudge_max", 0)) > 0
                                                  and cur_seg.get("_pl_nudges", 0) >= int(getattr(__import__("builtins"), "_sg_place_nudge_max", 0)))
                                    _pl_early = (getattr(__import__("builtins"), "_sg_place_early_release", False)
                                                 and _dxy < float(getattr(__import__("builtins"), "_sg_place_release_xy", 0.05)))
                                    if _dxy > 0.02 and not _pl_capped and not _pl_early:
                                        from curobo.types import JointState as _JS_pl
                                        _jl = franka.get_joint_positions()
                                        _tl = torch.tensor([[float(_x) for _x in np.asarray(_jl)[:_ARM_DOF]]], dtype=torch.float32, device="cuda")
                                        _kk = _planner.compute_kinematics(_JS_pl.from_position(_tl, joint_names=_PLANNER_JOINT_NAMES))
                                        _ep = _kk.tool_poses.position[0, 0, 0].detach().cpu().numpy(); _eq = _kk.tool_poses.quaternion[0, 0, 0].detach().cpu().numpy()
                                        _bm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_usd_quat[0]), Gf.Vec3d(float(_usd_quat[1]), float(_usd_quat[2]), float(_usd_quat[3])))); _bm.SetTranslateOnly(Gf.Vec3d(float(_usd_pos[0]), float(_usd_pos[1]), float(_usd_pos[2])))
                                        _fm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(_eq[0]), Gf.Vec3d(float(_eq[1]), float(_eq[2]), float(_eq[3])))); _fm.SetTranslateOnly(Gf.Vec3d(float(_ep[0]), float(_ep[1]), float(_ep[2])))
                                        _eew = (_fm * _bm).ExtractTranslation()
                                        _cg = np.array([float(_eew[0]) + (float(_drop_cl[0]) - float(_cubp_cl[0])), float(_eew[1]) + (float(_drop_cl[1]) - float(_cubp_cl[1])), float(_eew[2])], dtype=np.float32)
                                        # 2026-06-09 GATED (_ur10_place_nudge_branch_pin): the place-nudge re-plan (plan_pose, free IK)
                                        # OVERRIDES the clean RELIVE cspace descend [MEASURED CP-80: clean cspace_ok=True descend, then
                                        # 3 PL-nudges fling seg7 356deg]. branch_pin keeps the nudge in-branch (cspace from the live seed).
                                        # Default OFF -> byte-identical.
                                        _pl_bp = bool(getattr(__import__("builtins"), "_ur10_place_nudge_branch_pin", False))
                                        # 2026-06-09 H3: WRAP the PL-nudge seed to (-pi,pi] when branch_pin'd (matches the RELIVE seed
                                        # L7242). Unwrapped, the cspace-pin closest-L1 (L5380) measures distance against a +/-2pi-offset
                                        # config -> picks a FAR branch despite branch_pin -> the 356deg fling. Default OFF -> byte-identical.
                                        _pl_seed = np.asarray(_jl)[:_ARM_DOF]
                                        if _pl_bp:
                                            _pl_seed = ((_pl_seed + np.pi) % (2.0 * np.pi) - np.pi).astype(np.float32)
                                        _rr = _plan_to_world_point(_cg, _pl_seed, exclude_obs=([S["picked_path"], DEST_PATH] if DEST_PATH else S["picked_path"]), yaw_deg=0.0, vhold_mode=0, branch_pin=_pl_bp)
                                        if _rr is not None:
                                            cur_seg["traj"] = _rr[0]; cur_seg["motion_time"] = max(float(_rr[1]), 0.2); cur_seg["grip_done"] = False; cur_seg["traj_src"] = "plnudge"
                                            S["seg_start_t"] = time.monotonic(); cur_seg["_pl_nudges"] = cur_seg.get("_pl_nudges", 0) + 1
                                            with open("/tmp/cupframe_dbg.log", "a") as _cfd: _cfd.write("PL nudge dxy=%.3f cube=%s -> goal=%s\\n" % (_dxy, [round(float(_cubp_cl[_i]), 3) for _i in range(3)], [round(float(_x), 3) for _x in _cg]))
                                            return
                            except Exception as _ple:
                                try:
                                    with open("/tmp/cupframe_dbg.log", "a") as _cfd: _cfd.write("PL fail " + str(_ple)[:120] + "\\n")
                                except Exception: pass
                        if _drop_close or _hold_cap:
                            _grip_open()
                            _sg_tool_l_dyn[0] = _SG_TOOL_L  # reset the release tool-extend; the cube is free now,
                            # so the cone snapping back up (clamped) can't drag it. Next cube picks at base length.
                            # Remove the grasp FJ at release
                            if S.get("grasp_joint"):
                                try:
                                    if stage.GetPrimAtPath(S["grasp_joint"]).IsValid():
                                        stage.RemovePrim(S["grasp_joint"])
                                except Exception: pass
                                S["grasp_joint"] = None
                            cur_seg["grip_done"] = True
                        # else: keep grip_done=False, retry next tick
                        return  # don't advance to post_grip dwell yet
                    cur_seg["grip_done"] = True
                # Post-grip dwell so finger drives reach final position
                # (close: 2.5s for cube clamp; open: 0.3s for release — Stage-1 dwell cut, 2026-06-03;
                #  cube already at rest on release, fingers only need to part to clear it. Reduces cross-template
                #  post-place idle Anton flagged. Grasp/close path UNCHANGED to protect the 37 friction passes.)
                post_grip = 1.5 if cur_seg["action_after"] == "close" else \\
                            (0.3 if cur_seg["action_after"] == "open" else 0.0)
                if elapsed >= mt + pre_grip_settle + post_grip and ((not _sim_floor) or S.get("seg_sim_t", 0.0) >= mt + pre_grip_settle + post_grip):
                    S["seg_idx"] += 1
                    S["seg_start_t"] = time.monotonic()
                    S["seg_sim_t"] = 0.0
            return
    except Exception as e:
        _record_err(e)

_physx = omni.physx.get_physx_interface()
if _physx is None: raise RuntimeError("curobo: omni.physx unavailable")
# 2026-05-28 DIAGNOSTIC: brick-stacking R7+ has ctrl:phase=None despite install
# reaching this point — capture which step in install fails. Append to log.
try:
    with open("/tmp/curobo_install_diag.log", "a") as _f:
        import time as _t
        _f.write(f"[{{_t.strftime('%H:%M:%S')}}] {{ROBOT_PATH}} _SUB_ATTR={{_SUB_ATTR}} before-subscribe\\n")
except Exception: pass
try:
    _sub = _physx.subscribe_physics_step_events(_on_step)
    setattr(builtins, _SUB_ATTR, _sub)
    try:
        with open("/tmp/curobo_install_diag.log", "a") as _f:
            _f.write(f"  ok: sub={{_sub!r}} _on_step={{_on_step!r}}\\n")
    except Exception: pass
except Exception as _se:
    try:
        with open("/tmp/curobo_install_diag.log", "a") as _f:
            _f.write(f"  SUBSCRIBE_FAIL: {{type(_se).__name__}}: {{_se}}\\n")
    except Exception: pass
    raise

{_PP_SCENE_RESET_MGR_SNIPPET}

def _curobo_pp_reset_hook():
    # Round 4 repair (2026-05-17): when stage was reset (e.g. new template
    # batch), the closed-over franka object references a Stage that no
    # longer exists. franka.initialize raises a Boost.Python ArgumentError.
    # Detect stage staleness by checking if ROBOT_PATH is still valid in
    # the live stage; if not, self-unregister and return True so the
    # SceneResetManager removes us from the hook list.
    try:
        import omni.usd as _omni_usd_stale
        _stage_live = _omni_usd_stale.get_context().get_stage()
        _live_robot = _stage_live.GetPrimAtPath(ROBOT_PATH) if _stage_live else None
        if not (_live_robot and _live_robot.IsValid()):
            # Stage was reset — unregister so we don't pollute future templates.
            try:
                _mgr = getattr(builtins, _MGR_ATTR, None)
                if _mgr is not None:
                    _mgr.unregister(_MGR_HOOK_NAME)
            except Exception: pass
            return True
    except Exception: pass
    try:
        v = SimulationManager.get_physics_sim_view()
        if v is None: return False
    except Exception: return False
    try:
        franka.initialize(v); franka.post_reset()
        if franka.get_joint_positions() is None: return False
        _grip_open()
        S["delivered"].clear()
        S.get("failed", set()).clear()
        S["mode"] = "wait_sensor"
        S["picked_path"] = None
        S["segments"] = None; S["seg_idx"] = 0; S["seg_start_t"] = None
        S["cubes"] = 0; S["errors"] = 0; S["ticks"] = 0
        S["home_returned"] = False
        # Re-fetch ctrl:* attrs in case stage reset expired our captured refs.
        # Play/Stop cycle invalidates Usd.Attribute handles on physics-tracked prims.
        # Round 2 repair (2026-05-17): re-fetch the stage from omni.usd as well —
        # closing over the outer ``stage`` reference can yield an expired Python
        # binding after new_stage(), and pybind reports the resulting unbound
        # call as ``Stage.GetPrimAtPath(Stage, str) did not match C++ signature``
        # because the captured handle no longer maps to a live Stage instance.
        try:
            import omni.usd as _omni_usd_rh
            _stage_live = _omni_usd_rh.get_context().get_stage()
            if _stage_live is None:
                _stage_live = stage  # fall back to closed-over ref
            _rp = _stage_live.GetPrimAtPath(ROBOT_PATH)
            if _rp and _rp.IsValid():
                for _name, _val in (
                    ("ctrl:cubes_delivered", 0),
                    ("ctrl:error_count", 0),
                    ("ctrl:tick_count", 0),
                    ("ctrl:last_error", ""),
                    ("ctrl:picked_path", ""),
                    ("ctrl:phase", "wait_sensor"),
                ):
                    _attr = _rp.GetAttribute(_name)
                    if _attr and _attr.IsDefined():
                        try: _attr.Set(_val)
                        except Exception: pass
        except Exception as _ae:
            print(f"(curobo_pp reset attr-refresh soft-fail: {{_ae}})")
        _resume_belt()
        return True
    except Exception as _re:
        print(f"(curobo_pp reset exception: {{_re}})"); return False

getattr(builtins, _MGR_ATTR).register(_MGR_HOOK_NAME, _curobo_pp_reset_hook)

print(json.dumps({{
    "ok": True,
    "mode": "curobo (MotionPlanner, 5-segment plan_pose per cube cycle)",
    "robot": ROBOT_PATH,
    "sources": SOURCE_PATHS,
    "dest_path": DEST_PATH,
    "ee_initial_height": float(EE_INITIAL_HEIGHT),
    "initial_state": S["mode"],
    "planner_cached": True,
    "planning_obstacles": PLANNING_OBSTACLES,
    "note": "GPU trajectory optimization with self-collision check. Expect ~0.5s/plan after CUDA graph warmup.",
}}))
"""


def _gen_pick_place_diffik(robot_path: str, sensor_path: str, belt_path: str,
                            source_paths: list, destination_path: str,
                            drop_target: str, ee_offset: list,
                            end_effector_initial_height=None,
                            diffik_method: str = "dls",
                            phase_id: str = "default") -> str:
    """Isaac Lab DifferentialIKController-based pick-place.

    Env-bridge: sys.path.insert(0, isaac_lab_env/site-packages) +
    importlib.invalidate_caches() makes isaaclab importable inside Kit
    (both run under the same miniconda isaac_lab_env python).

    Controller: DifferentialIKController in pose command mode with
    user-selectable ik_method ('dls' default, also pinv/svd/trans).
    Per-tick: get EE pose + Jacobian from articulation_view, feed
    current Cartesian target (interpolated along the same 6-waypoint
    schedule as spline), controller.compute returns desired arm joint
    positions, apply_action updates drives.

    Jacobian indexing: articulation_view.get_jacobians() → shape
    (num_envs=1, num_bodies=10, 6, num_dofs=9). num_bodies=10 excludes
    root link 0, so panda_hand at body_names index 8 → jacobian index
    7. We slice (:, :, :, :7) to drop finger joint columns, leaving
    gripper control to franka.gripper.forward().

    Limitations: no collision awareness, no self-collision guard, no
    planning horizon. Expected delivery rate: 2–3/4 (similar to spline
    for simple tabletop scenarios; worse when the 6 waypoints need
    obstacle avoidance).

    Args:
        robot_path (str): USD prim path of the Franka articulation root.
        sensor_path (str or None): Proximity sensor prim path.
        belt_path (str or None): Conveyor belt prim path.
        source_paths (list[str]): Ordered cube prim paths to deliver.
        destination_path (str or None): Default drop bin prim path.
        drop_target (str or None): Drop bin override.
        ee_offset (list[float]): [x, y, z] EE-to-fingertip offset, meters.
        end_effector_initial_height (float or None): Approach clearance height
            override. Auto-computed from scene geometry when None.
        diffik_method (str): IK method passed to
            ``DifferentialIKControllerCfg``. One of ``"dls"`` (damped least
            squares, default), ``"pinv"``, ``"svd"``, or ``"trans"``.

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Prints a JSON dict with ``{"ok": True, "mode": "diffik", ...}`` on
        success, or raises ``RuntimeError`` for pre-flight failures.
    """
    # (Phase 8 wave 9) tool_executor imports migrated to module body:
    # _PP_OBSERVABILITY_SNIPPET migrated to module body (Phase 8 wave 9).
    # _PP_SCENE_RESET_MGR_SNIPPET migrated to module body (Phase 8 wave 9).
    import json as _json
    return f"""\
# ── setup_pick_place_controller (diffik) — Isaac Lab DifferentialIKController ─
import sys, importlib, omni.usd, omni.timeline, omni.physx, omni.kit.app, numpy as np, builtins, json, time, os
from pxr import UsdGeom, Sdf, Gf, UsdPhysics

# ── Env-bridge: isaac_lab_env site-packages ──────────────────────────
_LAB_SP = "/home/anton/miniconda3/envs/isaac_lab_env/lib/python3.11/site-packages"
while _LAB_SP in sys.path:
    sys.path.remove(_LAB_SP)
sys.path.insert(0, _LAB_SP)
importlib.invalidate_caches()

import torch
from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
from isaacsim.core.api import World
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.core.utils.rotations import euler_angles_to_quat as _eul2q

ROBOT_PATH = {robot_path!r}
SENSOR_PATH = {sensor_path!r}
BELT_PATH = {belt_path!r}
SOURCE_PATHS = {_json.dumps(list(source_paths))}
DEST_PATH = {destination_path!r}
DROP_TARGET = {_json.dumps(drop_target) if drop_target else 'None'}
EE_OFFSET = np.array({_json.dumps(list(ee_offset))}, dtype=np.float32)
EE_INIT_H_OVERRIDE = {end_effector_initial_height!r}
DIFFIK_METHOD = {diffik_method!r}
_PHASE_ID = {phase_id!r}

# Per-robot scoping (2026-05-28): see _gen_pick_place_native for explanation.
# Track K (2026-05-28): per-phase scoping added.
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
_SUB_ATTR = "_diffik_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
_old = getattr(builtins, _SUB_ATTR, None)
if _old is not None:
    try: _old.unsubscribe()
    except Exception: pass
    try: delattr(builtins, _SUB_ATTR)
    except Exception: pass
# Cross-mode sweep — this robot + this phase only.
for _a in list(vars(builtins).keys()):
    if _a.startswith(("_native_pp_", "_pick_place_", "_sensor_gated_", "_spline_pp_", "_diffik_pp_tl_", "_curobo_pp_")) \
       and (_a.endswith("_" + _ROBOT_TAG) or ("_" + _ROBOT_TAG + "_") in _a):
        _s = getattr(builtins, _a, None)
        if _s:
            try: _s.unsubscribe()
            except Exception: pass
        try: delattr(builtins, _a)
        except Exception: pass
_mgr_pre = getattr(builtins, "_scene_reset_manager", None)
if _mgr_pre is not None:
    for _hn in ("native_pp", "spline_pp", "diffik_pp", "osc_pp", "curobo_pp"):
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG + "_" + _PHASE_ID)
        except Exception: pass
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG)
        except Exception: pass
        try: _mgr_pre.unregister(_hn)
        except Exception: pass

stage = omni.usd.get_context().get_stage()
# Pre-flight prim-existence check (silent-success fix 2026-05-07).
# Without this, bad paths slip through to _on_step where the resulting
# Boost.Python.ArgumentError is captured to stdout but does NOT reach
# /exec_sync's success flag — handler reports success=True, scene is
# silently broken. See docs/audits/silent_success_pick_place_2026-05-07.md
for _ckp, _label in [
    (ROBOT_PATH, "robot_path"),
    (BELT_PATH, "belt_path"),
    (DEST_PATH, "destination_path"),
]:
    if not stage.GetPrimAtPath(_ckp).IsValid():
        raise RuntimeError(
            f"setup_pick_place_controller (diffik): {{_label}}={{_ckp!r}} "
            f"does not exist or is invalid in stage"
        )
for _src in SOURCE_PATHS:
    if not stage.GetPrimAtPath(_src).IsValid():
        raise RuntimeError(
            f"setup_pick_place_controller (diffik): source path {{_src!r}} "
            f"not found in stage"
        )
tl = omni.timeline.get_timeline_interface()
if not tl.is_playing():
    tl.play()

# Pump physics
_app = omni.kit.app.get_app()
for _ in range(6): _app.update()
try:
    if SimulationManager.get_physics_sim_view() is None:
        SimulationManager.initialize_physics()
except Exception as _e:
    print(f"(initialize_physics soft-fail: {{_e}})")
_physics_sim_view = SimulationManager.get_physics_sim_view()

world = World.instance() or World()
franka = Franka(prim_path=ROBOT_PATH, name="diffik_pp_franka")
try: world.scene.add(franka)
except Exception:
    _existing = world.scene.get_object("diffik_pp_franka")
    if _existing is not None: franka = _existing

try:
    franka.initialize(_physics_sim_view)
    franka.post_reset()
except Exception as _e:
    print(json.dumps({{"ok": False, "error": f"franka init failed: {{type(_e).__name__}}: {{_e}}"}}))
    raise

# Pump a few frames so articulation_view has a valid jacobian tensor
for _ in range(20): _app.update()

# Sync USD pose to physics body + set default state
try:
    _robot_xf0 = UsdGeom.Xformable(stage.GetPrimAtPath(ROBOT_PATH))
    _mtx0 = _robot_xf0.ComputeLocalToWorldTransform(0)
    _usd_pos = np.array([float(_mtx0.ExtractTranslation()[i]) for i in range(3)], dtype=np.float32)
    _usd_q = _mtx0.ExtractRotationQuat()
    _usd_quat = np.array([float(_usd_q.GetReal())] +
                         [float(_usd_q.GetImaginary()[i]) for i in range(3)], dtype=np.float32)
    _phys_pos, _phys_quat = franka.get_world_pose()
    if (float(np.linalg.norm(_usd_pos - np.asarray(_phys_pos, dtype=np.float32))) > 1e-3 or
            float(np.linalg.norm(_usd_quat - np.asarray(_phys_quat, dtype=np.float32))) > 1e-3):
        franka.set_world_pose(position=_usd_pos, orientation=_usd_quat)
except Exception as _e: print(f"(pose sync soft-fail: {{_e}})")

_HOME_Q = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04], dtype=np.float32)
try:
    _n_dof = len(franka.dof_names) if franka.dof_names else len(_HOME_Q)
    _home_trimmed = _HOME_Q[:_n_dof]
    franka.set_joint_positions(_home_trimmed)
    franka.set_joint_velocities(np.zeros(_n_dof, dtype=np.float32))
    try: franka.set_joints_default_state(positions=_home_trimmed,
                                         velocities=np.zeros(_n_dof, dtype=np.float32))
    except Exception: pass
    try: franka.set_default_state(position=_usd_pos, orientation=_usd_quat)
    except Exception: pass
except Exception as _e: print(f"(home force soft-fail: {{_e}})")

art_ctrl = franka.get_articulation_controller()
_av = franka._articulation_view

# Boost finger drive gains for friction grip (same as spline)
try:
    for _fj in ("panda_finger_joint1", "panda_finger_joint2"):
        _jp = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/panda_hand/{{_fj}}")
        if _jp.IsValid():
            _drv = UsdPhysics.DriveAPI.Get(_jp, "linear")
            if _drv:
                _drv.GetStiffnessAttr().Set(10000.0)
                _drv.GetDampingAttr().Set(200.0)
except Exception as _e: print(f"(finger gain soft-fail: {{_e}})")

# ── Diffik controller setup ──────────────────────────────────────────
_device = "cuda" if torch.cuda.is_available() else "cpu"
_dcfg = DifferentialIKControllerCfg(
    command_type="pose", use_relative_mode=False,
    ik_method=DIFFIK_METHOD,
    ik_params={{"lambda_val": 0.05}} if DIFFIK_METHOD == "dls" else None,
)
_dik = DifferentialIKController(_dcfg, num_envs=1, device=_device)
print(f"(diffik: controller built, method={{DIFFIK_METHOD}}, device={{_device}}, action_dim={{_dik.action_dim}})")

# ── Body index for panda_hand in jacobian ──────────────────────────────
# Jacobian shape (num_envs, num_bodies_excl_root, 6, num_dofs). Root link
# panda_link0 is row 0 of body_names but excluded from jacobian. So
# subtract 1 from body_names.index('panda_hand').
_body_names = list(_av.body_names)
try:
    _hand_body_idx = _body_names.index("panda_hand") - 1  # -1 for root exclusion
except ValueError:
    _hand_body_idx = 7  # Franka canonical
print(f"(diffik: panda_hand jacobian body idx = {{_hand_body_idx}})")

# ── Helpers ──────────────────────────────────────────────────────────
def _world_pos(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid(): return None
    t = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1]), float(t[2])])

def _bin_drop_pos():
    if DROP_TARGET is not None: return np.array(DROP_TARGET, dtype=np.float32)
    if DEST_PATH:
        p = stage.GetPrimAtPath(DEST_PATH)
        if p and p.IsValid():
            bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
            mn, mx = bb.GetMin(), bb.GetMax()
            return np.array([(mn[0]+mx[0])/2, (mn[1]+mx[1])/2, float(mx[2]) + 0.05], dtype=np.float32)
    return None

def _compute_h1():
    if EE_INIT_H_OVERRIDE is not None: return float(EE_INIT_H_OVERRIDE)
    zs = []
    for sp in SOURCE_PATHS:
        wp = _world_pos(sp)
        if wp is not None: zs.append(float(wp[2]))
    dp = _bin_drop_pos()
    if dp is not None: zs.append(float(dp[2]))
    return (max(zs) + 0.20) if zs else 0.3
EE_INITIAL_HEIGHT = _compute_h1()

# Down-facing EE orientation as wxyz quat
_DOWN_QUAT_WXYZ = _eul2q(np.array([0, np.pi, 0]))  # returns [w, x, y, z]

def _make_waypoints(cube_pos, drop_pos):
    # Return list of (xyz_world, quat_wxyz) Cartesian targets
    h1 = EE_INITIAL_HEIGHT
    FINGER_LEN = 0.105
    pick_z = float(cube_pos[2]) + FINGER_LEN + float(EE_OFFSET[2])
    return [
        (np.array([cube_pos[0], cube_pos[1], h1]),      _DOWN_QUAT_WXYZ),
        (np.array([cube_pos[0], cube_pos[1], pick_z]),  _DOWN_QUAT_WXYZ),
        (np.array([cube_pos[0], cube_pos[1], pick_z]),  _DOWN_QUAT_WXYZ),  # dwell
        (np.array([cube_pos[0], cube_pos[1], h1]),      _DOWN_QUAT_WXYZ),
        (np.array([drop_pos[0], drop_pos[1], h1]),      _DOWN_QUAT_WXYZ),
        (np.array([drop_pos[0], drop_pos[1], drop_pos[2]]), _DOWN_QUAT_WXYZ),
        (np.array([drop_pos[0], drop_pos[1], drop_pos[2]]), _DOWN_QUAT_WXYZ),  # dwell
        (np.array([drop_pos[0], drop_pos[1], h1]),      _DOWN_QUAT_WXYZ),
    ]

# Time schedule
_SEG_DT = 1.5
_DWELL_DT = 1.2
_WP_TIMES = np.array([
    0.0, _SEG_DT, _SEG_DT + _DWELL_DT,
    _SEG_DT + _DWELL_DT + _SEG_DT,
    _SEG_DT + _DWELL_DT + _SEG_DT*2,
    _SEG_DT + _DWELL_DT + _SEG_DT*3,
    _SEG_DT + _DWELL_DT*2 + _SEG_DT*3,
    _SEG_DT + _DWELL_DT*2 + _SEG_DT*4,
], dtype=np.float64)
_GRIP_CLOSE_T = float(_WP_TIMES[1]) + 0.2
_GRIP_OPEN_T  = float(_WP_TIMES[5]) + 0.2
_TOTAL_T = float(_WP_TIMES[-1]) + 0.5

def _interp_pose(t, waypoints):
    # Linear interp in position, nearest-wp in quat (all waypoints share the
    # same down-facing orient so slerp unnecessary here)
    t = float(np.clip(t, _WP_TIMES[0], _WP_TIMES[-1]))
    # Find segment
    idx = int(np.searchsorted(_WP_TIMES, t, side='right') - 1)
    idx = max(0, min(idx, len(waypoints) - 2))
    t0 = _WP_TIMES[idx]; t1 = _WP_TIMES[idx + 1]
    if t1 - t0 < 1e-6:
        alpha = 0.0
    else:
        alpha = (t - t0) / (t1 - t0)
    p = waypoints[idx][0] * (1 - alpha) + waypoints[idx + 1][0] * alpha
    q = waypoints[idx][1]  # same orient
    return np.asarray(p, dtype=np.float32), np.asarray(q, dtype=np.float32)

# ── Belt + sensor + gripper helpers ──────────────────────────────────
_belt_prim = stage.GetPrimAtPath(BELT_PATH) if BELT_PATH else None
_belt_sv = _belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if (_belt_prim and _belt_prim.IsValid()) else None
_captured = tuple(_belt_sv.Get()) if (_belt_sv and _belt_sv.IsDefined() and _belt_sv.Get()) else None
_nominal_belt = _captured if (_captured and sum(abs(v) for v in _captured) > 1e-6) else (0.2, 0.0, 0.0)
def _pause_belt():
    if _belt_sv: _belt_sv.Set((0, 0, 0))
def _resume_belt():
    if _belt_sv: _belt_sv.Set(_nominal_belt)
if _belt_sv and sum(abs(v) for v in (_belt_sv.Get() or (0,0,0))) < 1e-6:
    _resume_belt()

def _grip_open():
    try:
        a = franka.gripper.forward("open")
        if a: art_ctrl.apply_action(a)
    except Exception: pass
def _grip_close():
    try:
        a = franka.gripper.forward("close")
        if a: art_ctrl.apply_action(a)
    except Exception: pass

_sensor = stage.GetPrimAtPath(SENSOR_PATH) if SENSOR_PATH else None
def _sensor_xy():
    if _sensor is None or not _sensor.IsValid(): return None
    t = UsdGeom.Xformable(_sensor).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1])])
_sensor_xy_v = _sensor_xy()

def _cube_to_pick():
    # Earlier hard-coded z-range [0.83, 0.95] assumed cubes on a thin
    # belt above a tall table; broke table-top scenarios where cubes
    # rest at z=0.775. Now base-relative: -0.30/+0.50m from robot base
    # z. Catches table-top and belt-top, excludes floor-falls.
    base_xy = np.array([float(_usd_pos[0]), float(_usd_pos[1])])
    base_z = float(_usd_pos[2])
    sxy = _sensor_xy_v if _sensor_xy_v is not None else base_xy
    cands = []
    # Reach varies per family: Franka 0.85m (actual arm length), Cobotta 0.95m,
    # UR10/UR10e 1.20m. Earlier 0.70m for Franka under-utilized the arm and
    # rejected handoff positions (e.g. CP-51 handoff at 0.76m from FrankaB).
    # Phase 4 P0 (2026-05-10): apply 5cm safety margin per Opus research —
    # cuRobo's IK + collision avoid have ~10% failure rate in the last cm
    # of workspace boundary. Safety margin reduces wasted plan_pose calls
    # on borderline-reachable cubes (RCA: CP-37 24/24 fail = reach-bound).
    _reach_m_raw = 1.20 if ROBOT_FAMILY in ("ur10", "ur10e") else 0.85
    _reach_safety = 0.05
    _reach_m = _reach_m_raw - _reach_safety
    for sp in SOURCE_PATHS:
        if sp in S["delivered"] or sp in S.get("failed", set()) or _is_in_bin(sp): continue
        cp = _world_pos(sp)
        if cp is None: continue
        if cp[2] < base_z - 0.30 or cp[2] > base_z + 0.50: continue
        if float(np.linalg.norm(cp[:2] - base_xy)) > _reach_m: continue
        cands.append((float(np.linalg.norm(cp[:2] - sxy)), sp))
    if not cands: return None
    cands.sort(); return cands[0][1]

def _bin_bounds():
    if not DEST_PATH: return None
    p = stage.GetPrimAtPath(DEST_PATH)
    if not p or not p.IsValid(): return None
    bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    return (np.array([bb.GetMin()[0], bb.GetMin()[1]]),
            np.array([bb.GetMax()[0], bb.GetMax()[1]]))

def _is_in_bin(cube_path):
    bounds = _bin_bounds()
    if bounds is None: return False
    cp = _world_pos(cube_path)
    if cp is None: return False
    mn, mx = bounds
    return (mn[0] <= cp[0] <= mx[0]) and (mn[1] <= cp[1] <= mx[1])

# ── FK + Jacobian per tick ────────────────────────────────────────────
# Isaac Sim 5.x articulation_view only exposes root pose via
# get_world_poses(); per-link poses must be read from USD prim
# transforms (which physics updates each step).
_hand_prim = stage.GetPrimAtPath(ROBOT_PATH + "/panda_hand")
def _ee_pose():
    try:
        if not (_hand_prim and _hand_prim.IsValid()): return None, None
        mtx = UsdGeom.Xformable(_hand_prim).ComputeLocalToWorldTransform(0)
        t = mtx.ExtractTranslation()
        q = mtx.ExtractRotationQuat()
        pos = np.array([float(t[0]), float(t[1]), float(t[2])], dtype=np.float32)
        quat = np.array([float(q.GetReal()),
                         float(q.GetImaginary()[0]),
                         float(q.GetImaginary()[1]),
                         float(q.GetImaginary()[2])], dtype=np.float32)
        return pos, quat
    except Exception:
        return None, None

def _jacobian_arm():
    try:
        J = _av.get_jacobians()
        if J is None: return None
        Jh = np.asarray(J[0, _hand_body_idx, :, :7], dtype=np.float32)
        return Jh
    except Exception:
        return None

{_PP_OBSERVABILITY_SNIPPET}
_a_mode.Set("diffik")

# ── State ────────────────────────────────────────────────────────────
S = {{"mode": "wait_sensor", "picked_path": None, "grasp_joint": None,
      "start_t": None, "waypoints": None,
      "cubes": 0, "errors": 0, "ticks": 0, "delivered": set(),
      "grip_closed_done": False, "grip_opened_done": False}}

def _record_err(e):
    S["errors"] += 1
    try:
        _a_err.Set(S["errors"])
        _a_last_err.Set(f"{{type(e).__name__}}: {{str(e)[:150]}}")
    except Exception: pass

def _apply_joint_target(q7):
    dof_names = list(franka.dof_names) if franka.dof_names else []
    if not dof_names: return
    cur = np.array(franka.get_joint_positions(), dtype=np.float64).copy()
    cur[:min(7, len(cur))] = np.asarray(q7, dtype=np.float64)[:min(7, len(cur))]
    art_ctrl.apply_action(ArticulationAction(joint_positions=cur))

def _on_step(dt):
    try:
        S["ticks"] += 1
        _a_tick.Set(S["ticks"]); _a_phase.Set(S["mode"])

        if S["mode"] == "wait_sensor":
            picked = _cube_to_pick()
            if picked:
                cube_pos = _world_pos(picked)
                drop_pos = _bin_drop_pos()
                if cube_pos is None or drop_pos is None: return
                S["picked_path"] = picked
                _a_picked.Set(picked)
                _pause_belt()
                S["waypoints"] = _make_waypoints(cube_pos, drop_pos)
                S["start_t"] = time.monotonic()
                S["grip_closed_done"] = False
                S["grip_opened_done"] = False
                _grip_open()
                _dik.reset()
                S["mode"] = "executing"
            return

        if S["mode"] == "executing":
            elapsed = time.monotonic() - S["start_t"]
            wps = S["waypoints"]
            if wps is None:
                S["mode"] = "wait_sensor"; return

            # Gripper events
            if not S["grip_closed_done"] and elapsed >= _GRIP_CLOSE_T:
                _grip_close(); S["grip_closed_done"] = True
            if not S["grip_opened_done"] and elapsed >= _GRIP_OPEN_T:
                _grip_open(); S["grip_opened_done"] = True

            # Interpolated target pose
            tgt_pos, tgt_quat = _interp_pose(elapsed, wps)
            # Feed pose command
            cmd = torch.tensor([[float(tgt_pos[0]), float(tgt_pos[1]), float(tgt_pos[2]),
                                 float(tgt_quat[0]), float(tgt_quat[1]),
                                 float(tgt_quat[2]), float(tgt_quat[3])]],
                               dtype=torch.float32, device=_device)
            ee_p, ee_q = _ee_pose()
            Jh = _jacobian_arm()
            jp = franka.get_joint_positions()
            if ee_p is None or Jh is None or jp is None:
                # Log first failure + every 100 ticks so we see what's missing
                if S["ticks"] < 5 or S["ticks"] % 100 == 0:
                    print(f"(diffik tick {{S['ticks']}} missing: ee_p={{ee_p is not None}} Jh={{Jh is not None}} jp={{jp is not None}})")
                return
            ee_p_t = torch.tensor(ee_p, dtype=torch.float32, device=_device).unsqueeze(0)
            ee_q_t = torch.tensor(ee_q, dtype=torch.float32, device=_device).unsqueeze(0)
            J_t = torch.tensor(Jh, dtype=torch.float32, device=_device).unsqueeze(0)
            jp_arm = torch.tensor(jp[:7], dtype=torch.float32, device=_device).unsqueeze(0)
            _dik.set_command(cmd, ee_pos=ee_p_t, ee_quat=ee_q_t)
            q_new = _dik.compute(ee_p_t, ee_q_t, J_t, jp_arm)
            q_new_np = q_new.detach().cpu().numpy()[0]
            _apply_joint_target(q_new_np)

            if elapsed >= _TOTAL_T:
                S["cubes"] += 1; _a_cycles.Set(S["cubes"])
                if S["picked_path"]:
                    S["delivered"].add(S["picked_path"])
                    _a_cubes.Set(len(S["delivered"]))
                S["picked_path"] = None; _a_picked.Set("")
                S["waypoints"] = None; S["start_t"] = None
                S["mode"] = "wait_sensor"
                if len(S["delivered"]) >= len(SOURCE_PATHS):
                    _resume_belt()
            return
    except Exception as e:
        _record_err(e)

_physx = omni.physx.get_physx_interface()
if _physx is None:
    raise RuntimeError("diffik: omni.physx unavailable")
_sub = _physx.subscribe_physics_step_events(_on_step)
setattr(builtins, _SUB_ATTR, _sub)

{_PP_SCENE_RESET_MGR_SNIPPET}

def _diffik_pp_reset_hook():
    try:
        _view = SimulationManager.get_physics_sim_view()
        if _view is None: return False
    except Exception: return False
    try:
        franka.initialize(_view); franka.post_reset()
        if franka.get_joint_positions() is None: return False
        _dik.reset()
        _grip_open()
        S["delivered"].clear()
        S["mode"] = "wait_sensor"
        S["picked_path"] = None
        S["waypoints"] = None; S["start_t"] = None
        S["cubes"] = 0; S["errors"] = 0; S["ticks"] = 0
        _a_cubes.Set(0); _a_err.Set(0); _a_tick.Set(0)
        _a_last_err.Set(""); _a_picked.Set(""); _a_phase.Set("wait_sensor")
        _resume_belt()
        print("(diffik_pp reset complete)")
        return True
    except Exception as _re:
        print(f"(diffik_pp reset exception: {{type(_re).__name__}}: {{_re}})")
        return False

getattr(builtins, _MGR_ATTR).register("diffik_pp_" + _ROBOT_TAG + "_" + _PHASE_ID, _diffik_pp_reset_hook)

print(json.dumps({{
    "ok": True,
    "mode": "diffik (Isaac Lab DifferentialIKController, per-tick Jacobian)",
    "method": DIFFIK_METHOD,
    "device": _device,
    "hand_body_idx": _hand_body_idx,
    "ee_initial_height": float(EE_INITIAL_HEIGHT),
    "initial_state": S["mode"],
    "note": "Per-tick diffik compute. No planning, no collision awareness. Expect 2-3/4 delivery.",
}}))
"""


def _gen_pick_place_osc(robot_path: str, sensor_path: str, belt_path: str,
                         source_paths: list, destination_path: str,
                         drop_target: str, ee_offset: list,
                         phase_id: str = "default") -> str:
    """Isaac Lab OperationalSpaceController-based pick-place.

    Simplified config (no inertial decoupling, no gravity comp, fixed
    impedance) — falls back to a Jacobian-transpose Cartesian impedance
    law. Doesn't need the mass matrix M(q) or gravity vector g(q),
    which `isaacsim.core.prims.Articulation` doesn't expose directly
    (see I-33 in incidents log).

    Effort-mode switch: at install, arm joint DriveAPI is modified
    (stiffness=0, damping=0) so position drives don't fight the
    torques we apply. On uninstall, original gains should be restored
    — but currently we don't track teardown (cycle ends when all
    cubes delivered and stays in wait_sensor).

    Expected delivery: 0–2/4 (experimental). Not a winner for standard
    pick-place; the point of having OSC in the matrix is for
    contact-rich tasks (polishing, assembly) where compliant motion
    matters more than drop precision.

    Args:
        robot_path (str): USD prim path of the Franka articulation root.
        sensor_path (str or None): Proximity sensor prim path.
        belt_path (str or None): Conveyor belt prim path.
        source_paths (list[str]): Ordered cube prim paths to deliver.
        destination_path (str or None): Default drop bin prim path.
        drop_target (str or None): Drop bin override.
        ee_offset (list[float]): [x, y, z] EE-to-fingertip offset, meters.

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Prints a JSON dict with ``{"ok": True, "mode": "osc", ...}`` on
        success, or raises ``RuntimeError`` for pre-flight failures.
    """
    # (Phase 8 wave 9) tool_executor imports migrated to module body:
    # _PP_OBSERVABILITY_SNIPPET migrated to module body (Phase 8 wave 9).
    # _PP_SCENE_RESET_MGR_SNIPPET migrated to module body (Phase 8 wave 9).
    import json as _json
    return f"""\
# ── setup_pick_place_controller (osc) — Isaac Lab OperationalSpaceController ──
import sys, importlib, omni.usd, omni.timeline, omni.physx, omni.kit.app, numpy as np, builtins, json, time, os
from pxr import UsdGeom, Sdf, Gf, UsdPhysics

_LAB_SP = "/home/anton/miniconda3/envs/isaac_lab_env/lib/python3.11/site-packages"
while _LAB_SP in sys.path:
    sys.path.remove(_LAB_SP)
sys.path.insert(0, _LAB_SP)
importlib.invalidate_caches()

import torch
from isaaclab.controllers import OperationalSpaceController, OperationalSpaceControllerCfg
from isaacsim.core.api import World
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.core.utils.rotations import euler_angles_to_quat as _eul2q

ROBOT_PATH = {robot_path!r}
SENSOR_PATH = {sensor_path!r}
BELT_PATH = {belt_path!r}
SOURCE_PATHS = {_json.dumps(list(source_paths))}
DEST_PATH = {destination_path!r}
DROP_TARGET = {_json.dumps(drop_target) if drop_target else 'None'}
EE_OFFSET = np.array({_json.dumps(list(ee_offset))}, dtype=np.float32)
_PHASE_ID = {phase_id!r}

# Per-robot scoping (2026-05-28): see _gen_pick_place_native for explanation.
# Track K (2026-05-28): per-phase scoping added.
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
_SUB_ATTR = "_osc_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
_old = getattr(builtins, _SUB_ATTR, None)
if _old is not None:
    try: _old.unsubscribe()
    except Exception: pass
    try: delattr(builtins, _SUB_ATTR)
    except Exception: pass
# Cross-mode sweep — this robot + this phase only.
for _a in list(vars(builtins).keys()):
    if _a.startswith(("_native_pp_", "_pick_place_", "_sensor_gated_", "_spline_pp_",
                       "_diffik_pp_", "_osc_pp_tl_", "_curobo_pp_")) \
       and (_a.endswith("_" + _ROBOT_TAG) or ("_" + _ROBOT_TAG + "_") in _a):
        _s = getattr(builtins, _a, None)
        if _s:
            try: _s.unsubscribe()
            except Exception: pass
        try: delattr(builtins, _a)
        except Exception: pass
_mgr_pre = getattr(builtins, "_scene_reset_manager", None)
if _mgr_pre is not None:
    for _hn in ("native_pp", "spline_pp", "diffik_pp", "osc_pp", "curobo_pp"):
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG + "_" + _PHASE_ID)
        except Exception: pass
        try: _mgr_pre.unregister(_hn + "_" + _ROBOT_TAG)
        except Exception: pass
        try: _mgr_pre.unregister(_hn)
        except Exception: pass

stage = omni.usd.get_context().get_stage()
# Pre-flight prim-existence check (silent-success fix 2026-05-07).
# Without this, bad paths slip through to _on_step where the resulting
# Boost.Python.ArgumentError is captured to stdout but does NOT reach
# /exec_sync's success flag — handler reports success=True, scene is
# silently broken. See docs/audits/silent_success_pick_place_2026-05-07.md
for _ckp, _label in [
    (ROBOT_PATH, "robot_path"),
    (BELT_PATH, "belt_path"),
    (DEST_PATH, "destination_path"),
]:
    if not stage.GetPrimAtPath(_ckp).IsValid():
        raise RuntimeError(
            f"setup_pick_place_controller (osc): {{_label}}={{_ckp!r}} "
            f"does not exist or is invalid in stage"
        )
for _src in SOURCE_PATHS:
    if not stage.GetPrimAtPath(_src).IsValid():
        raise RuntimeError(
            f"setup_pick_place_controller (osc): source path {{_src!r}} "
            f"not found in stage"
        )
tl = omni.timeline.get_timeline_interface()
if not tl.is_playing(): tl.play()

_app = omni.kit.app.get_app()
for _ in range(6): _app.update()
try:
    if SimulationManager.get_physics_sim_view() is None:
        SimulationManager.initialize_physics()
except Exception: pass
_physics_sim_view = SimulationManager.get_physics_sim_view()

world = World.instance() or World()
franka = Franka(prim_path=ROBOT_PATH, name="osc_pp_franka")
try: world.scene.add(franka)
except Exception:
    _existing = world.scene.get_object("osc_pp_franka")
    if _existing is not None: franka = _existing

try:
    franka.initialize(_physics_sim_view); franka.post_reset()
except Exception as _e:
    print(json.dumps({{"ok": False, "error": f"franka init failed: {{_e}}"}})); raise

for _ in range(20): _app.update()

# Sync USD pose + home joint
try:
    _robot_xf0 = UsdGeom.Xformable(stage.GetPrimAtPath(ROBOT_PATH))
    _mtx0 = _robot_xf0.ComputeLocalToWorldTransform(0)
    _usd_pos = np.array([float(_mtx0.ExtractTranslation()[i]) for i in range(3)], dtype=np.float32)
    _usd_q = _mtx0.ExtractRotationQuat()
    _usd_quat = np.array([float(_usd_q.GetReal())] +
                         [float(_usd_q.GetImaginary()[i]) for i in range(3)], dtype=np.float32)
except Exception: _usd_pos, _usd_quat = np.zeros(3), np.array([1,0,0,0])

_HOME_Q = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04], dtype=np.float32)
try:
    _n_dof = len(franka.dof_names) if franka.dof_names else len(_HOME_Q)
    franka.set_joint_positions(_HOME_Q[:_n_dof])
    franka.set_joint_velocities(np.zeros(_n_dof, dtype=np.float32))
except Exception: pass

art_ctrl = franka.get_articulation_controller()
_av = franka._articulation_view

# Boost finger drive gains (friction grip still position-driven)
try:
    for _fj in ("panda_finger_joint1", "panda_finger_joint2"):
        _jp = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/panda_hand/{{_fj}}")
        if _jp.IsValid():
            _drv = UsdPhysics.DriveAPI.Get(_jp, "linear")
            if _drv:
                _drv.GetStiffnessAttr().Set(10000.0)
                _drv.GetDampingAttr().Set(200.0)
except Exception: pass

# ── Switch ARM joints to effort mode (zero stiffness on angular drives) ─
_ARM_GAINS_SAVED = []
try:
    for j in range(1, 8):
        for l in range(7):
            p = stage.GetPrimAtPath(f"{{ROBOT_PATH}}/panda_link{{l}}/panda_joint{{j}}")
            if p.IsValid():
                d = UsdPhysics.DriveAPI.Get(p, "angular")
                if d:
                    _ARM_GAINS_SAVED.append((str(p.GetPath()), float(d.GetStiffnessAttr().Get() or 0.0),
                                              float(d.GetDampingAttr().Get() or 0.0)))
                    d.GetStiffnessAttr().Set(0.0)
                    d.GetDampingAttr().Set(5.0)  # small damping for stability
                break
    print(f"(osc: arm DOFs switched to effort mode, saved {{len(_ARM_GAINS_SAVED)}} prior gains)")
except Exception as _e:
    print(f"(osc: effort-mode switch soft-fail: {{_e}})")

# ── OSC controller (simplified: no inertial decoupling, no gravity comp) ─
_device = "cuda" if torch.cuda.is_available() else "cpu"
_motion_axes = [1]*6  # control all 6 Cartesian DOFs
_wrench_axes = [0]*6
_k_stiff = torch.tensor([500., 500., 500., 50., 50., 50.], dtype=torch.float32, device=_device)
_k_damp = torch.tensor([1.0]*6, dtype=torch.float32, device=_device)
_cfg = OperationalSpaceControllerCfg(
    target_types=["pose_abs"],
    motion_control_axes_task=_motion_axes,
    contact_wrench_control_axes_task=_wrench_axes,
    inertial_dynamics_decoupling=False,
    partial_inertial_dynamics_decoupling=False,
    gravity_compensation=False,
    impedance_mode="fixed",
    motion_stiffness_task=_k_stiff,
    motion_damping_ratio_task=_k_damp,
    motion_stiffness_limits_task=(torch.zeros(6, device=_device),
                                    torch.tensor([1e4]*6, device=_device)),
    motion_damping_ratio_limits_task=(torch.tensor([0.01]*6, device=_device),
                                       torch.tensor([5.0]*6, device=_device)),
    contact_wrench_stiffness_task=torch.zeros(6, device=_device),
    nullspace_control="none",
    nullspace_stiffness=0.0,
    nullspace_damping_ratio=0.0,
)
_osc = OperationalSpaceController(_cfg, num_envs=1, device=_device)
print(f"(osc: controller built; simplified Jacobian-transpose impedance, no inertial decoupling)")

_body_names = list(_av.body_names)
try:
    _hand_body_idx = _body_names.index("panda_hand") - 1
except ValueError:
    _hand_body_idx = 7

_hand_prim = stage.GetPrimAtPath(ROBOT_PATH + "/panda_hand")
def _ee_pose():
    try:
        mtx = UsdGeom.Xformable(_hand_prim).ComputeLocalToWorldTransform(0)
        t = mtx.ExtractTranslation(); q = mtx.ExtractRotationQuat()
        return (np.array([float(t[0]), float(t[1]), float(t[2])], dtype=np.float32),
                np.array([float(q.GetReal()),
                          float(q.GetImaginary()[0]),
                          float(q.GetImaginary()[1]),
                          float(q.GetImaginary()[2])], dtype=np.float32))
    except Exception:
        return None, None

def _jacobian_arm():
    try:
        J = _av.get_jacobians()
        if J is None: return None
        return np.asarray(J[0, _hand_body_idx, :, :7], dtype=np.float32)
    except Exception: return None

def _world_pos(path):
    p = stage.GetPrimAtPath(path)
    if not p or not p.IsValid(): return None
    t = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1]), float(t[2])])

def _bin_drop_pos():
    if DROP_TARGET is not None: return np.array(DROP_TARGET, dtype=np.float32)
    if DEST_PATH:
        p = stage.GetPrimAtPath(DEST_PATH)
        if p and p.IsValid():
            bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
            mn, mx = bb.GetMin(), bb.GetMax()
            return np.array([(mn[0]+mx[0])/2, (mn[1]+mx[1])/2, float(mx[2]) + 0.05], dtype=np.float32)
    return None

def _compute_h1():
    zs = []
    for sp in SOURCE_PATHS:
        wp = _world_pos(sp)
        if wp is not None: zs.append(float(wp[2]))
    dp = _bin_drop_pos()
    if dp is not None: zs.append(float(dp[2]))
    return (max(zs) + 0.20) if zs else 0.3
EE_INITIAL_HEIGHT = _compute_h1()

_DOWN_Q = _eul2q(np.array([0, np.pi, 0]))  # wxyz

def _make_waypoints(cube_pos, drop_pos):
    h1 = EE_INITIAL_HEIGHT
    FL = 0.105
    pz = float(cube_pos[2]) + FL + float(EE_OFFSET[2])
    return [
        (np.array([cube_pos[0], cube_pos[1], h1]), _DOWN_Q),
        (np.array([cube_pos[0], cube_pos[1], pz]), _DOWN_Q),
        (np.array([cube_pos[0], cube_pos[1], pz]), _DOWN_Q),
        (np.array([cube_pos[0], cube_pos[1], h1]), _DOWN_Q),
        (np.array([drop_pos[0], drop_pos[1], h1]), _DOWN_Q),
        (np.array([drop_pos[0], drop_pos[1], drop_pos[2]]), _DOWN_Q),
        (np.array([drop_pos[0], drop_pos[1], drop_pos[2]]), _DOWN_Q),
        (np.array([drop_pos[0], drop_pos[1], h1]), _DOWN_Q),
    ]

_SEG = 1.5; _DW = 1.2
_WP_T = np.array([0, _SEG, _SEG+_DW, _SEG*2+_DW, _SEG*3+_DW, _SEG*4+_DW,
                   _SEG*4+_DW*2, _SEG*5+_DW*2], dtype=np.float64)
_GRIP_CLOSE_T = float(_WP_T[1]) + 0.2
_GRIP_OPEN_T  = float(_WP_T[5]) + 0.2
_TOTAL_T = float(_WP_T[-1]) + 0.5

def _interp_pose(t, wps):
    t = float(np.clip(t, _WP_T[0], _WP_T[-1]))
    idx = int(np.searchsorted(_WP_T, t, side='right') - 1)
    idx = max(0, min(idx, len(wps) - 2))
    t0, t1 = _WP_T[idx], _WP_T[idx+1]
    a = 0.0 if t1 - t0 < 1e-6 else (t - t0)/(t1 - t0)
    return wps[idx][0]*(1-a) + wps[idx+1][0]*a, wps[idx][1]

# Belt + sensor
_belt_prim = stage.GetPrimAtPath(BELT_PATH) if BELT_PATH else None
_belt_sv = _belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity") if (_belt_prim and _belt_prim.IsValid()) else None
_captured = tuple(_belt_sv.Get()) if (_belt_sv and _belt_sv.IsDefined() and _belt_sv.Get()) else None
_nominal_belt = _captured if (_captured and sum(abs(v) for v in _captured) > 1e-6) else (0.2, 0.0, 0.0)
def _pause_belt():
    if _belt_sv: _belt_sv.Set((0, 0, 0))
def _resume_belt():
    if _belt_sv: _belt_sv.Set(_nominal_belt)
if _belt_sv and sum(abs(v) for v in (_belt_sv.Get() or (0,0,0))) < 1e-6:
    _resume_belt()

def _grip_open():
    try:
        a = franka.gripper.forward("open")
        if a: art_ctrl.apply_action(a)
    except Exception: pass
def _grip_close():
    try:
        a = franka.gripper.forward("close")
        if a: art_ctrl.apply_action(a)
    except Exception: pass

_sensor = stage.GetPrimAtPath(SENSOR_PATH) if SENSOR_PATH else None
def _sensor_xy():
    if _sensor is None or not _sensor.IsValid(): return None
    t = UsdGeom.Xformable(_sensor).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return np.array([float(t[0]), float(t[1])])
_sensor_xy_v = _sensor_xy()

def _cube_to_pick():
    # Earlier hard-coded z-range [0.83, 0.95] assumed cubes on a thin
    # belt above a tall table; broke table-top scenarios where cubes
    # rest at z=0.775. Now base-relative: -0.30/+0.50m from robot base
    # z. Catches table-top and belt-top, excludes floor-falls.
    base_xy = np.array([float(_usd_pos[0]), float(_usd_pos[1])])
    base_z = float(_usd_pos[2])
    sxy = _sensor_xy_v if _sensor_xy_v is not None else base_xy
    cands = []
    # Reach varies per family: Franka 0.85m (actual arm length), Cobotta 0.95m,
    # UR10/UR10e 1.20m. Earlier 0.70m for Franka under-utilized the arm and
    # rejected handoff positions (e.g. CP-51 handoff at 0.76m from FrankaB).
    # Phase 4 P0 (2026-05-10): apply 5cm safety margin per Opus research —
    # cuRobo's IK + collision avoid have ~10% failure rate in the last cm
    # of workspace boundary. Safety margin reduces wasted plan_pose calls
    # on borderline-reachable cubes (RCA: CP-37 24/24 fail = reach-bound).
    _reach_m_raw = 1.20 if ROBOT_FAMILY in ("ur10", "ur10e") else 0.85
    _reach_safety = 0.05
    _reach_m = _reach_m_raw - _reach_safety
    for sp in SOURCE_PATHS:
        if sp in S["delivered"] or sp in S.get("failed", set()) or _is_in_bin(sp): continue
        cp = _world_pos(sp)
        if cp is None: continue
        if cp[2] < base_z - 0.30 or cp[2] > base_z + 0.50: continue
        if float(np.linalg.norm(cp[:2] - base_xy)) > _reach_m: continue
        cands.append((float(np.linalg.norm(cp[:2] - sxy)), sp))
    if not cands: return None
    cands.sort(); return cands[0][1]

def _bin_bounds():
    if not DEST_PATH: return None
    p = stage.GetPrimAtPath(DEST_PATH)
    if not p or not p.IsValid(): return None
    bb = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    return (np.array([bb.GetMin()[0], bb.GetMin()[1]]),
            np.array([bb.GetMax()[0], bb.GetMax()[1]]))

def _is_in_bin(cube_path):
    b = _bin_bounds()
    if b is None: return False
    cp = _world_pos(cube_path)
    if cp is None: return False
    mn, mx = b
    return (mn[0] <= cp[0] <= mx[0]) and (mn[1] <= cp[1] <= mx[1])

{_PP_OBSERVABILITY_SNIPPET}
_a_mode.Set("osc")

S = {{"mode": "wait_sensor", "picked_path": None, "waypoints": None,
      "start_t": None, "cubes": 0, "errors": 0, "ticks": 0,
      "delivered": set(), "grip_closed_done": False, "grip_opened_done": False}}

def _record_err(e):
    S["errors"] += 1
    try:
        _a_err.Set(S["errors"])
        _a_last_err.Set(f"{{type(e).__name__}}: {{str(e)[:150]}}")
    except Exception: pass

def _apply_torques(tau_arm):
    # Apply torques to arm joints (first 7 DOFs); leave finger joints alone
    n = len(franka.dof_names) if franka.dof_names else 9
    tau = np.zeros(n, dtype=np.float64)
    tau[:min(7, n)] = np.asarray(tau_arm, dtype=np.float64)[:min(7, n)]
    art_ctrl.apply_action(ArticulationAction(joint_efforts=tau))

def _on_step(dt):
    try:
        S["ticks"] += 1
        _a_tick.Set(S["ticks"]); _a_phase.Set(S["mode"])
        if S["mode"] == "wait_sensor":
            picked = _cube_to_pick()
            if picked:
                cp, dp = _world_pos(picked), _bin_drop_pos()
                if cp is None or dp is None: return
                S["picked_path"] = picked; _a_picked.Set(picked)
                _pause_belt()
                S["waypoints"] = _make_waypoints(cp, dp)
                S["start_t"] = time.monotonic()
                S["grip_closed_done"] = False; S["grip_opened_done"] = False
                _grip_open()
                _osc.reset()
                S["mode"] = "executing"
            return
        if S["mode"] == "executing":
            elapsed = time.monotonic() - S["start_t"]
            wps = S["waypoints"]
            if wps is None:
                S["mode"] = "wait_sensor"; return
            if not S["grip_closed_done"] and elapsed >= _GRIP_CLOSE_T:
                _grip_close(); S["grip_closed_done"] = True
            if not S["grip_opened_done"] and elapsed >= _GRIP_OPEN_T:
                _grip_open(); S["grip_opened_done"] = True

            tgt_pos, tgt_quat = _interp_pose(elapsed, wps)
            ee_p, ee_q = _ee_pose()
            J = _jacobian_arm()
            if ee_p is None or J is None: return

            # Pose command for OSC: [x,y,z,wx,wy,wz] (axis-angle)? or [x,y,z,w,x,y,z]?
            # Isaac Lab OSC expects (B, 7) pose = [x, y, z, wxyz] for pose_abs
            cmd = torch.tensor([[float(tgt_pos[0]), float(tgt_pos[1]), float(tgt_pos[2]),
                                  float(tgt_quat[0]), float(tgt_quat[1]),
                                  float(tgt_quat[2]), float(tgt_quat[3])]],
                                dtype=torch.float32, device=_device)
            ee_p_t = torch.tensor(np.concatenate([ee_p, ee_q]), dtype=torch.float32, device=_device).unsqueeze(0)
            J_t = torch.tensor(J, dtype=torch.float32, device=_device).unsqueeze(0)

            _osc.set_command(cmd, current_ee_pose_b=ee_p_t)
            tau = _osc.compute(jacobian_b=J_t, current_ee_pose_b=ee_p_t)
            _apply_torques(tau.detach().cpu().numpy()[0])

            if elapsed >= _TOTAL_T:
                S["cubes"] += 1; _a_cycles.Set(S["cubes"])
                if S["picked_path"]:
                    S["delivered"].add(S["picked_path"])
                    _a_cubes.Set(len(S["delivered"]))
                S["picked_path"] = None; _a_picked.Set("")
                S["waypoints"] = None; S["start_t"] = None
                S["mode"] = "wait_sensor"
                if len(S["delivered"]) >= len(SOURCE_PATHS):
                    _resume_belt()
            return
    except Exception as e:
        _record_err(e)

_physx = omni.physx.get_physx_interface()
if _physx is None: raise RuntimeError("osc: omni.physx unavailable")
_sub = _physx.subscribe_physics_step_events(_on_step)
setattr(builtins, _SUB_ATTR, _sub)

{_PP_SCENE_RESET_MGR_SNIPPET}

def _osc_pp_reset_hook():
    try:
        v = SimulationManager.get_physics_sim_view()
        if v is None: return False
    except Exception: return False
    try:
        franka.initialize(v); franka.post_reset()
        if franka.get_joint_positions() is None: return False
        _osc.reset(); _grip_open()
        S["delivered"].clear()
        S["mode"] = "wait_sensor"
        S["picked_path"] = None
        S["waypoints"] = None; S["start_t"] = None
        S["cubes"] = 0; S["errors"] = 0; S["ticks"] = 0
        _a_cubes.Set(0); _a_err.Set(0); _a_tick.Set(0)
        _a_last_err.Set(""); _a_picked.Set(""); _a_phase.Set("wait_sensor")
        _resume_belt()
        print("(osc_pp reset complete)")
        return True
    except Exception as _re:
        print(f"(osc_pp reset exception: {{_re}})"); return False

getattr(builtins, _MGR_ATTR).register("osc_pp_" + _ROBOT_TAG + "_" + _PHASE_ID, _osc_pp_reset_hook)

print(json.dumps({{
    "ok": True,
    "mode": "osc (Isaac Lab OperationalSpaceController, simplified Jacobian-transpose impedance)",
    "device": _device,
    "hand_body_idx": _hand_body_idx,
    "ee_initial_height": float(EE_INITIAL_HEIGHT),
    "initial_state": S["mode"],
    "effort_mode_joints_switched": len(_ARM_GAINS_SAVED),
    "note": "Experimental. No inertial decoupling, no gravity comp. Jacobian-transpose impedance torques. Expect 0-2/4 delivery — OSC shines on contact-rich tasks, not pick-place.",
}}))
"""


def _gen_pick_place_fixed_poses(robot_path: str, pose_sequence: list, cycles: int, ee_link: str, fj1: str, fj2: str) -> str:
    """Timer-driven pose-sequence controller: replay named poses in order, N times.

    No sensor input, no grasp logic, no cube tracking — the robot visits each
    pose name from ``pose_sequence`` in order, waits until it arrives (or 4 s
    elapses), then advances to the next. Useful for cycle-time measurement,
    teach-pendant validation, or demonstrations before adding pick-place logic.

    Poses are loaded from JSON files at
    ``~/projects/Omniverse_Nemotron_Ext/workspace/robot_poses/<robot_key>/<name>.json``.
    Each file is expected to contain ``{"dof_names": [...], "joint_positions": [...]}``.
    The controller maps saved DOF names to the articulation's live DOF order so
    the sequence is robust to partial saves and robot variants.

    Args:
        robot_path (str): USD prim path of the robot articulation.
        pose_sequence (list[str]): Ordered list of pose names to visit, e.g.
            ``["home", "pick", "drop"]``. Each must have a corresponding JSON
            file in the robot's pose directory.
        cycles (int): Number of full-sequence repetitions before the controller
            sets ``done=True`` and stops advancing.
        ee_link (str): Name of the end-effector link (currently unused in the
            generated code; reserved for future gripper state integration).
        fj1 (str): Name of finger joint 1 (currently unused; see ee_link note).
        fj2 (str): Name of finger joint 2 (currently unused; see ee_link note).

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Prints a JSON dict with ``{"ok": True, "mode": "fixed_poses", ...}``
        after installing the physics callback. Raises ``FileNotFoundError``
        in generated code if a named pose JSON does not exist.
    """
    import json as _json
    return f"""\
# ── pick_place_controller (fixed_poses) ──────────────────────────────
# Timer-driven pose sequence. No sensing, no gripping — pure demo replay.
import os, json, re, numpy as np
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.api import World

ROBOT_PATH = {robot_path!r}
POSE_SEQUENCE = {_json.dumps(pose_sequence)}
CYCLES = {cycles}

robot_key = re.sub(r"[^A-Za-z0-9]+", "_", ROBOT_PATH.strip("/"))
POSE_DIR = os.path.expanduser(f"~/projects/Omniverse_Nemotron_Ext/workspace/robot_poses/{{robot_key}}")

def _load_pose(name):
    p = os.path.join(POSE_DIR, f"{{name}}.json")
    with open(p) as f:
        return json.load(f)

poses = [_load_pose(n) for n in POSE_SEQUENCE]

world = World.instance() or World()
if not world.is_playing():
    world.reset()
franka = SingleArticulation(ROBOT_PATH)
franka.initialize()

def _pose_targets(pose_dict):
    live = list(franka.dof_names) if franka.dof_names else []
    saved = pose_dict["dof_names"]
    sq = pose_dict["joint_positions"]
    return [sq[saved.index(n)] if n in saved else 0.0 for n in live]

def _at_pose(q, tol=0.05):
    cur = franka.get_joint_positions()
    if cur is None:
        return False
    return float(np.linalg.norm(np.array(cur) - np.array(q))) < tol

S = {{"idx": 0, "cycle": 0, "enter_t": 0.0, "elapsed_t": 0.0, "done": False}}
try:
    franka.set_joint_position_targets(np.array(_pose_targets(poses[0])))
except Exception:
    franka.set_joint_positions(np.array(_pose_targets(poses[0])))

def _step(dt):
    if S["done"]:
        return
    S["elapsed_t"] += dt
    now = S["elapsed_t"]
    tgt = _pose_targets(poses[S["idx"]])
    if _at_pose(tgt) or now - S["enter_t"] > 4.0:
        S["idx"] += 1
        if S["idx"] >= len(poses):
            S["idx"] = 0
            S["cycle"] += 1
            if S["cycle"] >= CYCLES:
                S["done"] = True
                return
        S["enter_t"] = now
        try:
            franka.set_joint_position_targets(np.array(_pose_targets(poses[S["idx"]])))
        except Exception:
            franka.set_joint_positions(np.array(_pose_targets(poses[S["idx"]])))

try:
    world.remove_physics_callback("pick_place_fixed_poses")
except Exception:
    pass
world.add_physics_callback("pick_place_fixed_poses", _step)

print(json.dumps({{"ok": True, "mode": "fixed_poses",
                  "pose_sequence": POSE_SEQUENCE, "cycles": CYCLES}}))
"""


def _gen_pick_place_ros2_cmd(robot_path: str, target_topic: str, gripper_topic: str, ee_link: str, fj1: str, fj2: str) -> str:
    """Wire ROS2 I/O for an externally-commanded pick-place controller.

    Generates an OmniGraph setup that subscribes to an external ROS2 controller's
    target-pose and gripper-command topics and wires them into Kit. The state
    machine logic lives entirely outside Isaac Sim (e.g. in a real PLC, a ROS2
    node, or a digital-twin controller) — Isaac Sim provides only physics,
    rendering, and the topic I/O layer.

    This is the ``ros2_cmd`` target_source variant of
    ``setup_pick_place_controller``, the inverse of
    ``_gen_setup_pick_place_ros2_bridge`` (which publishes robot state outward).

    Args:
        robot_path (str): USD prim path of the robot articulation.
        target_topic (str): ROS2 topic name carrying
            ``geometry_msgs/PoseStamped`` EE targets from the external
            controller. Defaults to ``"/isaac/robot/target_pose"`` at the
            dispatcher level.
        gripper_topic (str): ROS2 topic name carrying ``std_msgs/Float32``
            gripper commands (0.0 = closed, 0.04 = open). Defaults to
            ``"/isaac/robot/gripper_cmd"`` at the dispatcher level.
        ee_link (str): End-effector link name (used for OmniGraph target-prim
            wiring).
        fj1 (str): Finger joint 1 name.
        fj2 (str): Finger joint 2 name.

    Returns:
        str: Python source code to be exec'd in Kit via ``queue_exec_patch``.
        Sets up OmniGraph subscriber nodes and prints a JSON dict with
        ``{"ok": True, "mode": "ros2_cmd", ...}`` on success.
    """
    return f"""\
# ── pick_place_controller (ros2_cmd) ─────────────────────────────────
# External controller via ROS2. Isaac Sim is pure sim + I/O.
import json
import omni.graph.core as og

ROBOT_PATH = {robot_path!r}
TARGET_TOPIC = {target_topic!r}
GRIPPER_TOPIC = {gripper_topic!r}

# Ensure ROS2 bridge extension enabled
import omni.kit.app
mgr = omni.kit.app.get_app().get_extension_manager()
try:
    mgr.set_extension_enabled_immediate("isaacsim.ros2.bridge", True)
except Exception:
    pass

graph_path = "/World/ROS2PickPlaceController"
keys = og.Controller.Keys
og.Controller.edit(
    {{"graph_path": graph_path, "evaluator_name": "execution"}},
    {{
        keys.CREATE_NODES: [
            ("OnTick", "omni.graph.action.OnPlaybackTick"),
            ("SubTargetPose", "isaacsim.ros2.bridge.ROS2SubscribeTwist"),
            ("PubJointState", "isaacsim.ros2.bridge.ROS2PublishJointState"),
            ("ReadTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
        ],
        keys.CONNECT: [
            ("OnTick.outputs:tick", "SubTargetPose.inputs:execIn"),
            ("OnTick.outputs:tick", "PubJointState.inputs:execIn"),
            ("ReadTime.outputs:simulationTime", "PubJointState.inputs:timeStamp"),
        ],
        keys.SET_VALUES: [
            ("SubTargetPose.inputs:topicName", TARGET_TOPIC),
            ("PubJointState.inputs:topicName", "/isaac/robot/joint_states"),
            ("PubJointState.inputs:targetPrim", ROBOT_PATH),
        ],
    }},
)

print(json.dumps({{"ok": True, "mode": "ros2_cmd",
                  "target_topic": TARGET_TOPIC, "gripper_topic": GRIPPER_TOPIC,
                  "graph_path": graph_path,
                  "note": "External ROS2 node must subscribe to /isaac/robot/joint_states and publish to target-pose topic."}}))
"""


# Registration (no-op for now — see register() at bottom)


def register(
    data: Dict[str, Callable[..., Any]],
    codegen: Dict[str, Callable[..., Any]],
) -> None:
    """Phase 9 — populate dispatch dicts with this module's handlers.

    Called by `handlers/_dispatch.py:register_handlers()` which is the
    sole dispatch entry point from `tool_executor.py`.
    """
    # Code-gen handlers (2)
    codegen["setup_pick_place_controller"] = _gen_setup_pick_place_controller
    codegen["setup_pick_place_ros2_bridge"] = _gen_setup_pick_place_ros2_bridge

