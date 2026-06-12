"""Pure waypoint-chain generators for the manipulation primitives
(pull/turn/sweep) — the task-mode layer on the cuRobo phase machine.

NO Kit imports: everything here is plain math so it is l0-testable and can
be source-embedded into generated Kit-side code. The phase machine consumes
``goals = [(xyz, action_after, yaw_deg), ...]`` — these helpers produce the
task-specific tail of that list (the proven S1/S1.5/S2 grasp approach stays
untouched; design: primitive-layer RCA 2026-06-12).
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Goal = Tuple[List[float], Optional[str], float]


def _quat_rotate(q_wxyz: Sequence[float], v: Sequence[float]) -> List[float]:
    """Rotate vector v by quaternion (w, x, y, z)."""
    w, x, y, z = q_wxyz
    # t = 2 * cross(q.xyz, v)
    tx = 2.0 * (y * v[2] - z * v[1])
    ty = 2.0 * (z * v[0] - x * v[2])
    tz = 2.0 * (x * v[1] - y * v[0])
    # v' = v + w*t + cross(q.xyz, t)
    return [
        v[0] + w * tx + (y * tz - z * ty),
        v[1] + w * ty + (z * tx - x * tz),
        v[2] + w * tz + (x * ty - y * tx),
    ]


def axis_token_to_world(token: str, body0_quat_wxyz: Sequence[float]) -> List[float]:
    """Map a UsdPhysics joint axis token ("X"/"Y"/"Z") through body0's world
    rotation to a world-space unit vector."""
    local = {"X": [1.0, 0.0, 0.0], "Y": [0.0, 1.0, 0.0], "Z": [0.0, 0.0, 1.0]}[token.upper()]
    v = _quat_rotate(body0_quat_wxyz, local)
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def pull_pick_yaw(axis_world: Sequence[float]) -> float:
    """Yaw (deg) aligning the finger-closing axis with the pull axis so pull
    force transfers through normal contact (form closure), not friction."""
    return math.degrees(math.atan2(axis_world[1], axis_world[0]))


def pull_goal_chain(grasp_xyz: Sequence[float], axis_world: Sequence[float],
                    travel_m: float, n_steps: int = 4,
                    backoff_m: float = 0.10) -> List[Goal]:
    """Waypoints pulling a grasped handle ``travel_m`` along ``axis_world``
    (signed — caller decides direction from the joint limits), releasing on
    the last pull waypoint, then backing off clear of the handle."""
    yaw = pull_pick_yaw(axis_world)
    goals: List[Goal] = []
    for k in range(1, n_steps + 1):
        pos = [grasp_xyz[i] + axis_world[i] * travel_m * (k / n_steps)
               for i in range(3)]
        goals.append((pos, "open" if k == n_steps else None, yaw))
    end = goals[-1][0]
    goals.append(([end[i] + axis_world[i] * math.copysign(backoff_m, travel_m)
                   for i in range(3)], None, yaw))
    return goals


def arc_goal_chain(grasp_xyz: Sequence[float], pivot_xyz: Sequence[float],
                   delta_deg: float, step_deg: float = 15.0,
                   yaw0_deg: float = 0.0) -> List[Goal]:
    """Waypoints rotating the grasp point about a WORLD-Z hinge at
    ``pivot_xyz`` by ``delta_deg`` (signed), gripper yaw tracking the arc.
    v1 limitation by design: vertical hinge axes only."""
    r = [grasp_xyz[0] - pivot_xyz[0], grasp_xyz[1] - pivot_xyz[1]]
    n = max(1, math.ceil(abs(delta_deg) / step_deg))
    goals: List[Goal] = []
    for k in range(1, n + 1):
        th = math.radians(delta_deg * (k / n))
        c, s = math.cos(th), math.sin(th)
        pos = [pivot_xyz[0] + c * r[0] - s * r[1],
               pivot_xyz[1] + s * r[0] + c * r[1],
               grasp_xyz[2]]
        goals.append((pos, "open" if k == n else None,
                      yaw0_deg + math.degrees(th)))
    return goals


def sweep_goal_chain(debris_centroid_xy: Sequence[float],
                     dustpan_xy: Sequence[float], n_passes: int,
                     pass_spacing_m: float, ee_z_low: float, ee_z_high: float,
                     overshoot_m: float = 0.10,
                     backswing_m: float = 0.25) -> List[Goal]:
    """Parallel drag passes pushing floor debris toward the dustpan: per
    pass lift -> behind-debris start (laterally offset) -> descend ->
    drag through to the dustpan + overshoot -> lift."""
    dx = dustpan_xy[0] - debris_centroid_xy[0]
    dy = dustpan_xy[1] - debris_centroid_xy[1]
    dn = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dn, dy / dn          # drag direction
    px, py = -uy, ux                   # lateral (pass offset) direction
    yaw = math.degrees(math.atan2(uy, ux))
    goals: List[Goal] = []
    for j in range(n_passes):
        off = (j - (n_passes - 1) / 2.0) * pass_spacing_m
        sx = debris_centroid_xy[0] - ux * backswing_m + px * off
        sy = debris_centroid_xy[1] - uy * backswing_m + py * off
        ex = dustpan_xy[0] + ux * overshoot_m + px * off
        ey = dustpan_xy[1] + uy * overshoot_m + py * off
        goals.append(([sx, sy, ee_z_high], None, yaw))   # approach above
        goals.append(([sx, sy, ee_z_low], None, yaw))    # descend
        goals.append(([ex, ey, ee_z_low], None, yaw))    # drag
        goals.append(([ex, ey, ee_z_high], None, yaw))   # lift
    goals.append((list(goals[-1][0]), "open", yaw))      # release broom pose
    return goals
