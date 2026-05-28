"""Insertion-controller composite handler.

Implements `setup_insertion_controller(robot_path, target_path, strategy, ...)`
— a Tier-D composite that unifies the four hand-rolled descent gestures used
across CP-NEW insertion templates (`narrow-clearance-insertion`,
`screw-driving-impedance`, `bottle-cap-tighten`, `snap-fit`) into one call.

Strategies:
    spiral_search     — planar XY oscillation layered on Z descent
                        (lateral-dominant peg-in-hole, narrow clearance)
    helical_screw     — coupled Δz + Δrz per waypoint, ~1.25 turns
                        (M3-M6 screw-driving, torque-gated seat)
    snap_fit          — pure Z press-and-click, no rotation
                        (clamshell snap-fit, contact-event-gated)
    impedance_descent — single-phase vertical compliance descent
                        (bottle cap tighten + final rotational seat)

The composite internally composes three CRM tools:
  1. ``setup_impedance_controller`` (CRM-B1) with strategy-tuned Kx/Dx/Kr/Dr.
  2. ``set_compliance_params`` (CRM-B2) to persist the merged state.
  3. ``follow_trajectory_with_compliance`` (CRM-C4) with the
     strategy-specific trajectory waypoints generated from
     (start_pose, target_pose, n_waypoints, descent_height, ...).

dry_run=True (default) returns a structured plan dict combining the three
sub-calls' results. dry_run=False raises NotImplementedError (the three
sub-calls themselves require Kit RPC + ros2_control bridge per their
existing live-mode contracts).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

from service.isaac_assist_service.observability.handler_telemetry import (
    with_telemetry,
)

from .compliance import (
    _handle_follow_trajectory_with_compliance,
    _handle_set_compliance_params,
    _handle_setup_impedance_controller,
)


# ---------------------------------------------------------------------------
# Strategy registry — each entry carries default impedance gains + the
# trajectory generator. Templates may still override gains via kwargs.

_STRATEGY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # Lateral-dominant peg-in-hole (narrow-clearance-insertion)
    # X/Y SOFT (peg shimmies into hole), Z STIFF (push through wall friction).
    "spiral_search": {
        "Kx": [15.0, 15.0, 200.0],
        "Dx": [3.0, 3.0, 25.0],
        "Kr": [40.0, 40.0, 40.0],
        "Dr": [4.0, 4.0, 4.0],
        "compliance_controller": "cartesian_impedance",
        "compliance_handoff_at": 0.0,
        "velocity_scaling": 0.10,
        "timeout_s": 45.0,
        "spiral_amplitude_m": 0.002,
        "n_waypoints": 10,
    },
    # Coupled helical descent (M3-M6 screw-driving)
    # X/Y rigid (axial centering), Z translational + Z rotational SOFT
    # (descent under force cap + driver-bit slip as torque builds).
    "helical_screw": {
        "Kx": [300.0, 300.0, 40.0],
        "Dx": [30.0, 30.0, 6.0],
        "Kr": [20.0, 20.0, 8.0],
        "Dr": [2.5, 2.5, 1.2],
        "compliance_controller": "cartesian_impedance",
        "compliance_handoff_at": 0.0,
        "velocity_scaling": 0.20,
        "timeout_s": 30.0,
        "total_rotation_deg": 450.0,
        "n_waypoints": 6,
    },
    # Press-and-click (clamshell snap-fit)
    # X/Y rigid (axial alignment), Z SOFT (surrender to force cap),
    # all rotation rigid (no twist allowed).
    "snap_fit": {
        "Kx": [400.0, 400.0, 60.0],
        "Dx": [40.0, 40.0, 7.0],
        "Kr": [40.0, 40.0, 40.0],
        "Dr": [4.0, 4.0, 4.0],
        "compliance_controller": "cartesian_impedance",
        "compliance_handoff_at": 0.0,
        "velocity_scaling": 0.15,
        "timeout_s": 15.0,
        "n_waypoints": 3,
    },
    # Single-phase impedance descent (bottle cap tighten + finger-tight)
    # X/Y rigid (alignment), Z softened, partial rotational seat.
    "impedance_descent": {
        "Kx": [300.0, 300.0, 80.0],
        "Dx": [30.0, 30.0, 10.0],
        "Kr": [30.0, 30.0, 15.0],
        "Dr": [3.0, 3.0, 2.0],
        "compliance_controller": "cartesian_impedance",
        "compliance_handoff_at": 0.5,
        "velocity_scaling": 0.30,
        "timeout_s": 30.0,
        "total_rotation_deg": 90.0,
        "n_waypoints": 3,
    },
}


# ---------------------------------------------------------------------------
# Trajectory generators


def _gen_spiral_search(
    start_xyz: List[float],
    target_xyz: List[float],
    n_waypoints: int,
    spiral_amplitude_m: float,
) -> List[Dict[str, Any]]:
    """Generate spiral-search descent waypoints — XY oscillates on Z descent.

    XY radius decays as the peg drops so the spiral converges on the hole
    centre as Z approaches the target.
    """
    waypoints: List[Dict[str, Any]] = []
    sx, sy, sz = start_xyz
    tx, ty, tz = target_xyz
    for i in range(n_waypoints):
        t = i / max(1, n_waypoints - 1)
        # Linear Z descent
        z = sz + (tz - sz) * t
        # Decaying spiral around the line from start to target
        decay = 1.0 - t
        angle = 2.0 * math.pi * 1.5 * t  # ~1.5 turns over descent
        cx = sx + (tx - sx) * t
        cy = sy + (ty - sy) * t
        x = cx + spiral_amplitude_m * decay * math.cos(angle)
        y = cy + spiral_amplitude_m * decay * math.sin(angle)
        waypoints.append({
            "pose": {
                "position": [float(x), float(y), float(z)],
                "orientation": [1.0, 0.0, 0.0, 0.0],
            }
        })
    return waypoints


def _gen_helical_screw(
    start_xyz: List[float],
    target_xyz: List[float],
    n_waypoints: int,
    total_rotation_deg: float,
) -> List[Dict[str, Any]]:
    """Generate coupled Δz + Δrz waypoints — screw-driving helical descent."""
    waypoints: List[Dict[str, Any]] = []
    sx, sy, sz = start_xyz
    tx, ty, tz = target_xyz
    for i in range(n_waypoints):
        t = i / max(1, n_waypoints - 1)
        x = sx + (tx - sx) * t
        y = sy + (ty - sy) * t
        z = sz + (tz - sz) * t
        # Rotation around world Z, parameterised by half-angle for quaternion.
        angle_rad = math.radians(total_rotation_deg) * t
        half = angle_rad * 0.5
        qw = math.cos(half)
        qz = math.sin(half)
        waypoints.append({
            "pose": {
                "position": [float(x), float(y), float(z)],
                "orientation": [float(qw), 0.0, 0.0, float(qz)],
            }
        })
    return waypoints


def _gen_snap_fit(
    start_xyz: List[float],
    target_xyz: List[float],
    n_waypoints: int,
) -> List[Dict[str, Any]]:
    """Generate press-and-click waypoints — pure Z descent, no rotation.

    Default 3 waypoints: hover, contact, seated. Identity quaternion throughout.
    """
    waypoints: List[Dict[str, Any]] = []
    sx, sy, sz = start_xyz
    tx, ty, tz = target_xyz
    for i in range(n_waypoints):
        t = i / max(1, n_waypoints - 1)
        # Lock XY to target (snap-fit assumes pre-aligned EE above target)
        x = tx if i > 0 else sx
        y = ty if i > 0 else sy
        z = sz + (tz - sz) * t
        waypoints.append({
            "pose": {
                "position": [float(x), float(y), float(z)],
                "orientation": [1.0, 0.0, 0.0, 0.0],
            }
        })
    return waypoints


def _gen_impedance_descent(
    start_xyz: List[float],
    target_xyz: List[float],
    n_waypoints: int,
    total_rotation_deg: float,
) -> List[Dict[str, Any]]:
    """Generate single-phase impedance descent — Z translation + optional rotational seat."""
    waypoints: List[Dict[str, Any]] = []
    sx, sy, sz = start_xyz
    tx, ty, tz = target_xyz
    for i in range(n_waypoints):
        t = i / max(1, n_waypoints - 1)
        x = sx + (tx - sx) * t
        y = sy + (ty - sy) * t
        z = sz + (tz - sz) * t
        angle_rad = math.radians(total_rotation_deg) * t
        half = angle_rad * 0.5
        qw = math.cos(half)
        qz = math.sin(half)
        waypoints.append({
            "pose": {
                "position": [float(x), float(y), float(z)],
                "orientation": [float(qw), 0.0, 0.0, float(qz)],
            }
        })
    return waypoints


# ---------------------------------------------------------------------------
# Strategy dispatch


def _generate_trajectory(
    strategy: str,
    start_xyz: List[float],
    target_xyz: List[float],
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Dispatch to the strategy-specific waypoint generator."""
    n_waypoints = int(cfg.get("n_waypoints", 6))
    if strategy == "spiral_search":
        return _gen_spiral_search(
            start_xyz,
            target_xyz,
            n_waypoints,
            float(cfg.get("spiral_amplitude_m", 0.002)),
        )
    if strategy == "helical_screw":
        return _gen_helical_screw(
            start_xyz,
            target_xyz,
            n_waypoints,
            float(cfg.get("total_rotation_deg", 450.0)),
        )
    if strategy == "snap_fit":
        return _gen_snap_fit(start_xyz, target_xyz, n_waypoints)
    if strategy == "impedance_descent":
        return _gen_impedance_descent(
            start_xyz,
            target_xyz,
            n_waypoints,
            float(cfg.get("total_rotation_deg", 0.0)),
        )
    raise ValueError(f"unknown strategy: {strategy!r}")


# ---------------------------------------------------------------------------
# Main composite handler


@with_telemetry
async def _handle_setup_insertion_controller(
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Dispatch handler for `setup_insertion_controller`.

    Composes setup_impedance_controller + set_compliance_params +
    follow_trajectory_with_compliance into a single call, parameterised
    by ``strategy``.

    Args (from tool call):
        robot_path:           USD path to robot articulation root (required).
        target_path:          USD path to insertion target (peg-hole, bottle
                              neck, tapped plate, bottom shell). Optional —
                              only used for plan-dict traceability.
        strategy:             One of {"spiral_search", "helical_screw",
                              "snap_fit", "impedance_descent"} (required).
        start_pose:           [x, y, z] hover-above-target start position.
                              Required for trajectory generation.
        target_pose:          [x, y, z] final seated position. Required.
        target_frame:         Tool frame for impedance controller (default
                              "tool0"; templates pass "panda_hand").
        Kx, Kr, Dx, Dr:       Override strategy-default gains (3-vectors).
        compliance_handoff_at: Override strategy-default handoff fraction.
        compliance_controller: Override strategy-default mode.
        velocity_scaling, timeout_s: Override strategy-default trajectory args.
        n_waypoints:          Override strategy-default waypoint count.
        spiral_amplitude_m:   spiral_search only — XY oscillation amplitude.
        total_rotation_deg:   helical_screw / impedance_descent only.
        dry_run:              True (default) → return composite plan dict.

    Returns dict with success: bool combining the three sub-call results
    plus a strategy-specific summary block.
    """
    robot_path: str = args.get("robot_path", "")
    if not robot_path:
        return {"success": False, "error": "robot_path is required"}

    strategy: str = args.get("strategy", "")
    if strategy not in _STRATEGY_DEFAULTS:
        return {
            "success": False,
            "error": (
                f"strategy must be one of "
                f"{sorted(_STRATEGY_DEFAULTS.keys())!r}; got {strategy!r}."
            ),
            "valid_strategies": sorted(_STRATEGY_DEFAULTS.keys()),
        }

    start_pose = args.get("start_pose")
    target_pose = args.get("target_pose")
    if not (isinstance(start_pose, list) and len(start_pose) == 3):
        return {
            "success": False,
            "error": "start_pose must be a 3-element [x, y, z] list",
        }
    if not (isinstance(target_pose, list) and len(target_pose) == 3):
        return {
            "success": False,
            "error": "target_pose must be a 3-element [x, y, z] list",
        }

    cfg = dict(_STRATEGY_DEFAULTS[strategy])
    # Caller overrides — selective, only override known cfg keys
    for key in (
        "Kx", "Kr", "Dx", "Dr",
        "compliance_controller", "compliance_handoff_at",
        "velocity_scaling", "timeout_s",
        "n_waypoints", "spiral_amplitude_m", "total_rotation_deg",
    ):
        if args.get(key) is not None:
            cfg[key] = args[key]

    target_frame: str = args.get("target_frame", "tool0")
    dry_run: bool = bool(args.get("dry_run", True))

    if not dry_run:
        raise NotImplementedError(
            "setup_insertion_controller live mode requires Kit RPC + "
            "ros2_control bridge + torque-mode robot (composes "
            "setup_impedance_controller + follow_trajectory_with_compliance "
            "which both require the same bridge). Use dry_run=True to "
            "receive the composite plan dict for offline inspection."
        )

    # ---- Step 1: install impedance controller ----
    install_res = await _handle_setup_impedance_controller({
        "robot_path": robot_path,
        "target_frame": target_frame,
        "Kx": cfg["Kx"],
        "Kr": cfg["Kr"],
        "Dx": cfg["Dx"],
        "Dr": cfg["Dr"],
        "null_space_stiffness": float(args.get("null_space_stiffness", 0.5)),
        "null_space_damping": float(args.get("null_space_damping", 0.5)),
        "torque_mode": True,
        "dry_run": True,
    })
    if not install_res.get("success"):
        return {
            "success": False,
            "error": "setup_impedance_controller sub-call failed",
            "install_result": install_res,
        }

    # ---- Step 2: persist params via set_compliance_params ----
    params_res = await _handle_set_compliance_params({
        "robot_path": robot_path,
        "stiffness_xyz": cfg["Kx"],
        "damping_xyz": cfg["Dx"],
        "stiffness_rot": cfg["Kr"],
        "damping_rot": cfg["Dr"],
        "dry_run": True,
    })
    if not params_res.get("success"):
        return {
            "success": False,
            "error": "set_compliance_params sub-call failed",
            "install_result": install_res,
            "params_result": params_res,
        }

    # ---- Step 3: generate trajectory + invoke follow_trajectory_with_compliance ----
    trajectory = _generate_trajectory(
        strategy,
        list(start_pose),
        list(target_pose),
        cfg,
    )
    traj_res = await _handle_follow_trajectory_with_compliance({
        "trajectory": trajectory,
        "robot_path": robot_path,
        "compliance_handoff_at": float(cfg["compliance_handoff_at"]),
        "compliance_controller": str(cfg["compliance_controller"]),
        "timeout_s": float(cfg["timeout_s"]),
        "velocity_scaling": float(cfg["velocity_scaling"]),
        "dry_run": True,
    })
    if not traj_res.get("success"):
        return {
            "success": False,
            "error": "follow_trajectory_with_compliance sub-call failed",
            "install_result": install_res,
            "params_result": params_res,
            "trajectory_result": traj_res,
        }

    # ---- Compose return dict ----
    return {
        "success": True,
        "dry_run": True,
        "robot_path": robot_path,
        "target_path": args.get("target_path"),
        "strategy": strategy,
        "n_waypoints": len(trajectory),
        "start_pose": list(start_pose),
        "target_pose": list(target_pose),
        "gains": {
            "Kx": cfg["Kx"], "Dx": cfg["Dx"],
            "Kr": cfg["Kr"], "Dr": cfg["Dr"],
        },
        "compliance_controller": cfg["compliance_controller"],
        "compliance_handoff_at": cfg["compliance_handoff_at"],
        "trajectory": trajectory,
        "install_result": install_res,
        "params_result": params_res,
        "trajectory_result": traj_res,
    }


# ---------------------------------------------------------------------------
# Public signature (high-level callers / tests use this)


async def setup_insertion_controller(
    robot_path: str,
    strategy: str,
    start_pose: List[float],
    target_pose: List[float],
    target_path: Optional[str] = None,
    target_frame: str = "tool0",
    Kx: Optional[List[float]] = None,
    Kr: Optional[List[float]] = None,
    Dx: Optional[List[float]] = None,
    Dr: Optional[List[float]] = None,
    null_space_stiffness: float = 0.5,
    null_space_damping: float = 0.5,
    compliance_controller: Optional[str] = None,
    compliance_handoff_at: Optional[float] = None,
    velocity_scaling: Optional[float] = None,
    timeout_s: Optional[float] = None,
    n_waypoints: Optional[int] = None,
    spiral_amplitude_m: Optional[float] = None,
    total_rotation_deg: Optional[float] = None,
    dry_run: bool = True,
) -> dict:
    """Composite — install impedance controller, persist params, run
    strategy-specific trajectory under cartesian_impedance compliance.

    Replaces the 50+ line hand-rolled setup_impedance_controller +
    set_compliance_params + follow_trajectory_with_compliance blocks in
    CP-NEW-narrow-clearance-insertion, CP-NEW-screw-driving-impedance,
    CP-NEW-bottle-cap-tighten, and CP-NEW-yrkesroll-assembler-snap-fit.

    See `_handle_setup_insertion_controller` for arg details.
    """
    return await _handle_setup_insertion_controller({
        "robot_path": robot_path,
        "strategy": strategy,
        "start_pose": start_pose,
        "target_pose": target_pose,
        "target_path": target_path,
        "target_frame": target_frame,
        "Kx": Kx,
        "Kr": Kr,
        "Dx": Dx,
        "Dr": Dr,
        "null_space_stiffness": null_space_stiffness,
        "null_space_damping": null_space_damping,
        "compliance_controller": compliance_controller,
        "compliance_handoff_at": compliance_handoff_at,
        "velocity_scaling": velocity_scaling,
        "timeout_s": timeout_s,
        "n_waypoints": n_waypoints,
        "spiral_amplitude_m": spiral_amplitude_m,
        "total_rotation_deg": total_rotation_deg,
        "dry_run": dry_run,
    })


# ---------------------------------------------------------------------------
# Dispatch registration


def register(
    data: Dict[str, Callable[..., Any]],
    codegen: Dict[str, Callable[..., Any]],
) -> None:
    """Register the insertion composite into the dispatch table."""
    data["setup_insertion_controller"] = _handle_setup_insertion_controller
