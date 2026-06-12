"""l0 for the pure manipulation-primitive waypoint generators."""
import math

import pytest

pytestmark = pytest.mark.l0

from service.isaac_assist_service.chat.tools.handlers.manip_primitives import (
    arc_goal_chain, axis_token_to_world, pull_goal_chain, pull_pick_yaw,
    sweep_goal_chain)

IDENT = [1.0, 0.0, 0.0, 0.0]
ROT90Z = [math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4)]  # 90deg about Z


def test_axis_token_identity_and_rotated():
    assert axis_token_to_world("X", IDENT) == pytest.approx([1, 0, 0])
    assert axis_token_to_world("Z", IDENT) == pytest.approx([0, 0, 1])
    # body0 rotated 90deg about Z: local X -> world Y
    assert axis_token_to_world("X", ROT90Z) == pytest.approx([0, 1, 0], abs=1e-9)


def test_pull_pick_yaw():
    assert pull_pick_yaw([1, 0, 0]) == pytest.approx(0.0)
    assert pull_pick_yaw([0, 1, 0]) == pytest.approx(90.0)
    assert pull_pick_yaw([-1, 0, 0]) == pytest.approx(180.0)


def test_pull_goal_chain_monotone_and_release():
    goals = pull_goal_chain([0.0, 0.0, 0.9], [1, 0, 0], travel_m=-0.30,
                            n_steps=4, backoff_m=0.10)
    xs = [g[0][0] for g in goals]
    # monotone toward the limit (negative travel)
    assert all(b < a + 1e-12 for a, b in zip(xs, xs[1:]))
    # zero orthogonal drift, constant z
    assert all(g[0][1] == 0.0 and g[0][2] == 0.9 for g in goals)
    # release on the LAST pull waypoint, then a backoff goal
    assert goals[3][1] == "open" and goals[4][1] is None
    assert goals[3][0][0] == pytest.approx(-0.30)
    assert goals[4][0][0] == pytest.approx(-0.40)  # backoff continues along pull dir
    # yaw aligned with the pull axis
    assert all(g[2] == pytest.approx(0.0) for g in goals)


def test_arc_goal_chain_radius_invariant_and_yaw_tracking():
    grasp, pivot = [0.05, 0.35, 0.905], [0.0, 0.35, 0.905]
    goals = arc_goal_chain(grasp, pivot, delta_deg=90.0, step_deg=15.0)
    assert len(goals) == 6
    r0 = math.hypot(grasp[0] - pivot[0], grasp[1] - pivot[1])
    for k, (pos, act, yaw) in enumerate(goals, start=1):
        r = math.hypot(pos[0] - pivot[0], pos[1] - pivot[1])
        assert r == pytest.approx(r0, abs=1e-9)          # radius invariant
        assert yaw == pytest.approx(15.0 * k)            # yaw == theta_k
        assert pos[2] == grasp[2]                        # planar
    assert goals[-1][1] == "open" and all(g[1] is None for g in goals[:-1])
    # endpoint at target angle: 90deg about pivot from +X -> +Y
    assert goals[-1][0][0] == pytest.approx(pivot[0], abs=1e-9)
    assert goals[-1][0][1] == pytest.approx(pivot[1] + r0)


def test_arc_negative_delta():
    goals = arc_goal_chain([0.1, 0.0, 0.9], [0.0, 0.0, 0.9], delta_deg=-30.0)
    assert goals[-1][2] == pytest.approx(-30.0)
    assert len(goals) == 2


def test_sweep_goal_chain_structure():
    goals = sweep_goal_chain([0.55, 0.30], [0.85, 0.30], n_passes=3,
                             pass_spacing_m=0.08, ee_z_low=0.05, ee_z_high=0.25)
    # 4 goals per pass + final release
    assert len(goals) == 3 * 4 + 1
    for j in range(3):
        approach, descend, drag, lift = goals[j * 4: j * 4 + 4]
        assert approach[0][2] == 0.25 and descend[0][2] == 0.05
        assert drag[0][2] == 0.05 and lift[0][2] == 0.25
        # drag travels toward dustpan (+x here) with overshoot
        assert drag[0][0] > descend[0][0]
        assert drag[0][0] == pytest.approx(0.95)  # 0.85 + 0.10 overshoot
        # lateral offsets symmetric around the centroid line
        assert descend[0][1] == pytest.approx(0.30 + (j - 1) * 0.08)
    assert goals[-1][1] == "open"
    # drag direction yaw (toward +x) == 0
    assert all(g[2] == pytest.approx(0.0) for g in goals)
