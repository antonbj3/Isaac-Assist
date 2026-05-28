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

## Round 1: Routing-aware sweep_cpnew — DONE (~01:15)
- Result: 3/40 → 7/40 (+4 unlocks: controller-shootout, inspect-reject, sorter-color-3lane, vision-depalletize). Templates were succeeding; my sweep tool was just too strict.
- Commit: `adf84144 fix(sweep_cpnew): routing-aware success`

## Round 2: World-translate fix — DONE (~03:35)
- Hypothesis: `_safe_set_translate` set LOCAL despite docstring promising WORLD → cubes spawned inside transformed parents got double-translated.
- Verified live: cube spawn at intended world (-0.08, 0.34, 0.95) under SourceBin at (0, 0.42, 0.80) ended up at (-0.08, 0.76, 1.75) = bin+bin+offset.
- Fix: subtract parent's world translation when prim is parented.
- Result: 7/40 → 8/40 (+1 unlock: 3station-oee). Physics improvements on bin-picking-random-pose (Cube_1 max_speed 4.33→0.59 m/s, settled in bin instead of ejected to Ground). Cubes 2-6 still don't get xform set — separate bug (possibly apply_api_schema resetting xformOpOrder).
- Commit: `d6cda14b fix(_safe_set_translate)`

## Round 3: Split world-aware / local-aware — DONE (~04:05)
- Refined Round 2 to protect sensor mount semantics (lidar/camera offsets parented under robot frame want LOCAL, not WORLD).
- Split into `_safe_set_translate` (local, default) + `_safe_set_world_translate` (subtracts parent). create_prim uses world variant.
- Verified: CP-NEW-brick-stacking PASS after Kit restart (Round 2 result preserved, no sensor regression).
- Commit: `f7df7901 refactor(_safe_set_translate): split`

## Investigation: cube_under_table + curobo_planner_fail patterns (~04:10)
- 6 templates flagged `cube_under_table`: scattered physics failures, cubes escaping containers to (x>1m, y>3m) or extreme positions (-626km!). Not unifiable per-template, requires individual debugging.
- 5 templates flagged `curobo_planner_fail`: mislabeled — actually physics blowup not planner failure (Cube_1 at -626km is numerical explosion, not planner issue).
- Pattern: virtual_eyes heuristics are imperfect. Need to verify with raw metrics before treating as ground truth.

## Investigation: cube_floats_no_gravity (~04:15)
- 5 templates flagged. Looked at bin-picking-random-pose: cubes 2-6 have NO transform (final_pos = parent_pos), support=None = no rigidBody apply succeeded.
- Hypothesis: apply_api_schema in rapid succession (5×6=30 calls) might miss some, leaving cubes without physics. OR something in apply_api_schema resets xform ops.
- Not investigated further this session.

## Final status (overnight)
- **Start: 3/40 PASS (7.5%)**
- **End: 8/40 PASS (20%) — +5 templates / +12.5pp**
- 3 commits applied (revertable)
- Speedup mods + grip_config + friction-default + maxForce=70 already landed pre-night

## Remaining work for tomorrow
- Investigate why cubes 2-6 in bin-picking lack transforms (apply_api_schema interaction?)
- Per-template debugging of remaining 32 fails
- Vision-API quota templates (~10) require external service or local mock
- Multi-stage canonicals (passive robot waiting for upstream signal) need orchestrator scenario-profile

## Critical finding — apply_api_schema masks create_prim failures (~04:25)

`_gen_apply_api_schema` at scene_authoring.py:1215-1222 has auto-create-placeholder
fallback: if target prim doesn't exist, it walks the path and creates Xforms.
This MASKS silent create_prim failures.

For bin-picking-random-pose: cubes 2-6 likely had create_prim fail (timing? race?),
then apply_api_schema(PhysicsRigidBodyAPI) created placeholder Xform with no
translate/no Cube geometry. Hence final_pos=parent_pos and support=None.

Diagnostic suggestion (next session):
1. Wrap apply_api_schema with a "strict" mode that fails when prim missing
2. Add diagnostic logging: every time placeholder is created, emit warning
3. Identify which templates trigger placeholder creation in current sweep
4. Find why create_prim fails on rapid-sequence nested paths

Quick test (didn't run tonight): bin-picking-random-pose with just 2 cubes
instead of 6 — does the rate of placeholder creation drop?
