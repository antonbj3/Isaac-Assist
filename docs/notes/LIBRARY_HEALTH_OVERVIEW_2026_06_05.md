# Canonical library health — overview for review (2026-06-05, autonomous run)

Measured this run with the grader (scene_timeseries, now robust to missing primary_robot) + scene_eyes
(virtual-eyes motion/IK probe). Honest delivery counts; roots verified, not guessed.

## Headline
**Single-robot Franka templates mostly WORK. Failures concentrate in three HARD classes:**
UR10 reach-envelope, suction-cone physics, and multi-robot handoff. Cheap wins are scarce — the
remaining failures need architectural decisions or the plannability constraint, not per-template hacks.

## By cluster
| Cluster | Result | Notes |
|---|---|---|
| **UR10 suction-arm** (13) | **6/13 deliver** | CP-69(swing)/70/75/79/82/86 OK. 7 hard (below). |
| **Conveyor-sync** (CP-12, 3station-oee, inspect-reject) | **good** | CP-12 2/3, 3station 6/7, inspect-reject 5/5. Failures = 1 cube rides off belt (subtle timing). |
| **Dual-Franka handoff** (CP-51/52/53) | **0/3** | multi-robot relay/mutex broken (CP-51/53 pick-then-fling; CP-52 never picks = idle, likely mutex deadlock). |
| **Stacking** (CP-01, CP-04) | **4/4 each ✅** | single-robot Franka stacking solid. CP-05 (flip) grader-empty — verify separately. |

## The three hard classes + recommendation
1. **UR10 reach/orientation ENVELOPE** (CP-69 swing, CP-83, CP-84, CP-85). Drop/transit goals at/beyond
   what the arm can reach flange-down (CP-84 drop IK-infeasible, measured). Levers tried + failed:
   plan_cspace, more seeds, ori_tol, position-only, destination-exclude. → **Highest-leverage fix = the
   PLANNABILITY CONSTRAINT** ([[project_isaac_assist_plannability_telemetry_direction]]): flag these at
   gen-time (path-aware max-joint-sweep / min-manipulability) like out-of-reach is flagged, + template
   redesign (pick closer / drop in-envelope) or a non-suction tool-offset. GENERALIZES to LLM scenes.
2. **Suction-cone PHYSICS** (CP-80/81): the dynamic cone on the kinematic follower blows up (CP-81 cone
   flung to z=-0.43 @ 11 m/s). = architectural faithful-suction work, Anton's-call ([[feedback_isaac_assist_no_fj_fusk]]).
3. **Multi-robot dual-Franka** (CP-51/52/53): handoff-sync / shared-mutex. CP-52's never-moved (idle, not
   fling) is the most tractable entry (possible deadlock). Needs dedicated multi-robot claim-logic work.

## Lower-priority / risky-marginal
- Conveyor belt-edges (CP-12 Cube_3, 3station Cube_7 ride off): the cuRobo path ALREADY has belt-hold
  logic (_resume_belt_if_clear / _cube_imminent_at_sensor); the failures are subtle (cube drifts past the
  hold radius while the robot is busy). Fixing risks the multi-robot/conveyor templates for 1 cube → low
  risk/reward without broad regression coverage.
- CP-71 (dispenser-fill: cubes fall to floor), CP-73 (Cortex-BT: needs a different verifier), CP-05 (flip:
  grader-empty) — characterization gaps, not confirmed bugs.

## Fixes LANDED this run (committed)
- cuRobo support-surface exclusion → CP-69 no-op→delivers.
- grader robustness (auto-detect articulation when primary_robot unset + None-safe paths) → ALL templates
  now measurable (was Sdf.Path(None) crash on CP-80/84/85).
- destination-exclude fallback on drop-IK failure (additive, zero-regression).
- scene_eyes virtual-eyes tool + full UR10 swing RCA (docs/notes/UR10_SWING_RCA_2026_06_04.md).

## Recommended priority for review
1. Decide on the **plannability constraint** (systematic fix for the UR10 envelope class + generalizes).
2. Decide on **faithful suction-cone physics** (architectural; unblocks CP-80/81 + the UR10 suction set).
3. Dedicated **multi-robot claim/handoff** pass (CP-51/52/53), starting with CP-52's deadlock.
4. Single-robot Franka library is in good shape — maintain.
