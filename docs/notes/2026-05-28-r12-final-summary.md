# R12 Final Session Summary — 2026-05-28

**For Anton's morning review.**

## Bottom line

| Run | PASS / 40 | Notes |
|---|---|---|
| R6 baseline (10:07) | 7 | Pre-fixes |
| R6 re-eval with new gate | 9 | gate fix alone |
| R12 actual (15:54 launch, 18:05 done) | **8** | +1 net vs R6 strict, -1 vs R6 with new gate |

**R12 PASS templates (8):**

| Template | Reason | Status |
|---|---|---|
| 3station-oee | ok_routed(1) | R6 stable |
| inspect-reject | ok_routed(1) | R6 stable |
| isaaclab-arena-lego | ok | NEW today (baseplate widen) |
| kit-prep-operator | ok_partial(2/5) | NEW today (gate fix) |
| rtx-sponge-bowl | ok | R6 stable |
| sorter-color-3lane | ok_routed(3) | R6 stable |
| sorter-size-weight | ok_routed(5/9,gr=3) | NEW today (gate fix) |
| y-merge-singulation | ok | R6 stable |

**R6 PASS that REGRESSED in R12 (-2):**
- brick-stacking — ctrl:phase=None (install fails entirely)
- controller-shootout-cp — install OK but cubes don't deliver

## Root cause of regression

Commit `5e748297` (feat(K): phase_id kwarg for same-robot multi-stage PPC) introduced `_PHASE_ID` suffix to `_SUB_ATTR` naming. Prior-template's phased subs survive in `builtins` past their template's life. When new template installs, the install code fails somewhere between cleanup and `_physx.subscribe_physics_step_events`, leaving ctrl:phase=None.

Attempted fixes that DIDN'T work:
1. Broader cleanup pattern (Loop 1+2) — caused worse breakage
2. Cross-phase same-mode cleanup loop — same
3. Loop 1 narrow revert — no effect
4. `_ensure_attr` defensive re-acquire — broke 3station-oee
5. `_PHASE_ID` strip from sub names — broke 3station-oee

Final state: reverted last 2 commits. R12 = handler at state after my Loop 1 revert (533a9b41).

## What's fixed (effective in R12)

### Handler-level
- `9a9f455e` friction-grip default + maxForce=70 (eliminates FJ-fusk)
- `ea5713cf` scene_observer early-exit (47% sweep speedup)
- `d6cda14b` + `f7df7901` `_safe_set_world_translate` (split)
- `cf1b5e90` sweep_cpnew routing-aware + source-residual + partial-delivery gates
- `cee5cfcb` USD-color introspection fast path
- `337227f1` per-robot scoped subscription tag (still in effect)
- `555dd991` vhold gate to Franka-only (UR10 path uses vmode=0 now)

### Sweep gate fix
- Partial-delivery uses scene-level honesty (no_telepathic_fj + no_blowup + ee_never_underground), not primary-cube honest_pass
- Routing-aware also allows ground residuals if routed_moved > ground_count

### Template fixes (committed but not all unlocked)
- vision-depalletize: drop_targets staggered + Pallet removed from obstacles (still FAIL — sensor wait issue)
- bin-picking-random-pose: drop_targets staggered + source_bin removed (still FAIL — CAT-A)
- 6dof-pose-estimate-pick: drop_targets staggered + source_bin removed (still FAIL — solve_ik path)
- yrkesroll-packer-box-seal: infeed_bin removed from obstacles (still FAIL)
- yrkesroll-assembler-peg-bushing: infeed_tray removed (still FAIL)
- vacuum-gripper-sheet-pick: stack_holder removed (still FAIL — surface_gripper + PPC incompat)
- heap-zone-unstack: drop_targets staggered (still FAIL — create_heap_zone tool)
- moving-conveyor-pick: cube spawn_x clamped to belt (still FAIL)
- bin-picking-with-flip: source_bin removed (still FAIL)
- arena-lego: baseplate +Y + widen (PASS ✓)

## Categories of remaining failures

| Bucket | Count | Blocker |
|---|---|---|
| CAT-A (controller never engages) | 8-10 | _cube_to_pick rejects, solve_ik fails, or controller install regression from phase_id |
| UR10 100% plan_fail (now timeout post-vhold) | 4 | Some other UR10-specific issue beyond vhold |
| Custom-tool templates (create_heap_zone, create_recirculation_loop, etc.) | 5 | Tool quality issues |
| Stub templates (no real cubes) | 2-3 | kitting-station-6sku Carousel, etc. |
| Non-robot templates (no Franka in role) | 2 | sbend-sortation, conveyor-merge-vision-priority |
| Vision-pipeline dependent | 3 | bin-picking-random-pose, 6dof, vision-depalletize |
| Misc per-template | 5 | yrkesroll-* needs deeper rework |

## Honest assessment

### What went well
- Gate fix correctly unlocked 2 partial-delivery templates (kit-prep-operator, sorter-size-weight)
- Arena-lego baseplate widen worked
- UR10 vhold gate (no regression on Franka, may help UR10 in future runs)
- Many template fixes committed (will benefit future iterations even if not all unlocked now)

### What did NOT go well
- Couldn't fix the brick-stacking regression caused by phase_id commit
- 4 sweep iterations (R7→R8→R9→R10→R11→R12) burned ~7 hours of Kit time
- Several handler experiments REGRESSED templates (R11 broke 3station-oee briefly)
- My CAT-D + CAT-B template fixes had ZERO effect on the targeted templates (deeper issues)

### Lesson learned
Per memory `feedback_diagnostic_first_then_fix.md`: I should have INSTRUMENTED first (added live print() in _cube_to_pick to see WHY controller doesn't engage). Instead I made guess-based handler edits and introduced multiple regressions. Each regression cost a sweep run (~2h).

## Next session priorities

1. **DIAGNOSE first**: add live print() instrumentation to _cube_to_pick + _on_step install. Get ground truth on WHY 8 CAT-A templates have plan_calls=0.
2. **Fix brick-stacking regression**: needs deep debug of phase_id-related install failure. May need to fully revert 5e748297 + manually re-implement phase_id more carefully.
3. **UR10 vhold validation**: vhold fix is in place but UR10 templates still fail (timeout vs ValueError). May need to investigate WHY vhold gate didn't unlock them.
4. **Custom-tool templates**: write tests/diagnostics for create_heap_zone, create_recirculation_loop, surface_gripper to understand failure modes.

## Files changed this session

22 commits between R6 (10:07) and R12 launch (15:54):
- 8 template-level fixes (CAT-D drop_targets, CAT-B obstacles)
- 6 handler experiments (vhold, phase_id revert attempts, defensive ensure_attr, all reverted)
- 1 sweep gate improvement (scene-level honesty partial-delivery)
- Documentation

Tip commit: `6aafed90` (Revert "fix(_ensure_attr): defensive re-acquire on expired prim handle")

## Status of running processes

- Kit RPC alive on port 8001
- No sweeps running
- All work committed to branch `refactor/2026-05-12-foundation-night-1`
