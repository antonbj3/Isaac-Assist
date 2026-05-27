# Overnight progress — 2026-05-28 night

**Goal**: Drive CP-NEW function-gate from 3/40 (7.5%) toward 100% via systematic fixes.

**Anton mandate**: autonomous, all night, commit per round, trust my own analysis (virtual_eyes not perfect).

## Baseline (start of night)

- 3/40 PASS = 7.5% (CP-NEW-brick-stacking, rtx-sponge-bowl, y-merge-singulation)
- Friction-default + FJ-default = identical pass rate → grip-style not the bottleneck
- 37 failures categorized:
  - A. Physics-blew-up (9)
  - B. Robot-never-moved (8)
  - C. Cubes-moved-but-robot-static (8)
  - E. Robot-grasped-but-misplaced (12)

## Plan (rounds, commit per round)

| # | Focus | Templates | Approach |
|---|---|---|---|
| 1 | sweep_cpnew tool: recognize routing/sorter success | ~3 (E3) | Honor `color_routing` map; check any bin not just DEST_PATH |
| 2 | cube_passes_sensor_zone_untriggered | ~11 | Auto-trigger sensor on cube arrival OR bypass sensor gate when SENSOR not actually testing it |
| 3 | gripper_freeze_above_cube | ~7 | Cure D-refined (gripper_offset on drop_pos.z, start at 0.05m) |
| 4 | cube_under_table / physics-blowup | ~9 | Bin-floor collider validation / cube-spawn separation |
| 5 | curobo_planner_high_fail_rate | ~5 | Planner config tweaks (num_seeds, attempts) |
| 6 | Re-sweep + measure delta |  | Full CP-NEW sweep, write final report |

## Methodology

- Per round: 30-90 min
- Commit per round (git revert-safe)
- Update this doc with findings after each round
- If stuck > 30 min on a round, skip to next
- Don't blindly trust virtual_eyes — cross-check with raw metrics

## Round log

### Round 1: Routing recognition — STARTED 01:15
