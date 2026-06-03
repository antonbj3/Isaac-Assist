# R6 Sweep Failure Postmortem — 9 Expected-Unlock Templates

**Date**: 2026-05-28
**R6 sweep**: `workspace/qa_runs/r6_100750.jsonl` (40 records, 3 honest_pass)
**R5 baseline**: `workspace/qa_runs/r5_075558.jsonl` (40 records, 2 honest_pass)
**Delta**: +1 unlock (`CP-NEW-brick-stacking`). 9 templates targeted by today's fixes → **0 unlocked**.

## TL;DR

Of the 9 templates the fixes were supposed to unlock:

- **2 never ran in R6 at all** — `conveyor-recirculation-loop` and `machine-tender-door-interlock` are filtered out of the sweep by `filter_delivery_pattern` (`pattern_hint: "other"`, not in {`pick_place`, `sort`, `insert`, `reorient`, `navigate`}). The fixes built scenes that the harness *cannot grade*. Pure wasted commit.
- **6 of 7 templates that did run produced identical cube counts, identical max speeds, identical final positions R5→R6.** The `{{#each workpieces}}` spawn fixes had **zero observable effect** on physics state.
- **1 template (`isaaclab-arena-lego`) shows clear physics evidence the fix helped** — but still doesn't pass.

## Per-Template Diagnosis

### 1. `CP-NEW-bin-picking-random-pose` — vision-pipeline blocker (unchanged)

| Metric | R5 | R6 |
|---|---|---|
| n_cubes spawned | 6 | 6 |
| max_speed | 1.39 | 1.39 |
| in_target_ever | 0/6 | 0/6 |
| ee_min_z | — | 1.34 (never descended below table) |
| pattern: `never_picked` | yes | **yes (all 6 cubes)** |

**Remaining blocker**: vision pipeline. Cubes spawn correctly in `/World/SourceBin`, fall to floor, settle. Robot EE stays at `z=1.34` (rest pose). `setup_grasp_pose_sampler` requires vision/pose-estimation that isn't wired. Function-gate reports `never_in_xy` — robot never reached any cube XY.
**Fix-effectiveness**: The proper-`#each` Python-validity fix (commit `ac8a3037`) was a **correctness fix** (earlier `342e202d` was guaranteed to TypeError-crash); the scene now executes without exception. But cube count didn't change R5→R6, meaning the pre-fix already spawned 6 cubes via some other path. The "fix" prevented a future crash but had **no pass-rate impact** because the blocker is upstream of physics.

**Category**: **L (SAM2/perception)** — needs grasp-pose-from-pixels.

### 2. `CP-NEW-palletizer-layer-stack` — physics blowup, robot never moved

| Metric | R5 | R6 |
|---|---|---|
| n_cubes | 6 | 6 |
| max_speed | 1.70 | 1.70 |
| ee_min_z | None | **None (no EE telemetry)** |

`Box_1` is at spawn x=-1.60, but **5 of 6 boxes end at x≈1.4–1.8** — they slid ~3 m away from spawn during settle, ending on `/World/Ground` not on any pallet. Robot is UR10 with surface_gripper; **no ee_min_z recorded** → controller never executed a single trajectory step.

**Remaining blocker**: scene-physics + controller-never-fired. The robot family + surface gripper attach during scene build, but the controller call_step doesn't actually drive the arm. Could be motion-planner failure or a missing trigger.
**Fix-effectiveness**: Stub→full build (commit `ac8a3037`) is **architecturally useful** (scene exists, gripper exists, controllers exist) but produced **zero motion** — no observable improvement on any physics metric.

**Category**: **I (stub build-out incomplete)** — need controller fire diagnosis.

### 3. `CP-NEW-conveyor-recirculation-loop` — **never ran in R6**

Excluded by `filter_delivery_pattern` (intent.pattern_hint = `"other"`). The stub build-out is invisible to the function-gate sweep.

**Remaining blocker**: harness scope. Either re-tag `pattern_hint` to `navigate`/`sort`, or wire a lap-marker grader (template's own `verified_status` says "function-gate pending live Kit (requires lap-marker crossing detector wired into simulate harness)").
**Fix-effectiveness**: Commit `ac8a3037` built scene structure; **cannot be measured by current sweep**.

**Category**: **K (phase_id / grader)** — needs new grader.

### 4. `CP-NEW-sorter-size-weight` — partial delivery (5/9), but primary cube never moved

| Metric | R5 | R6 |
|---|---|---|
| n_cubes | 9 | 9 |
| in_target_ever | 5/9 | **5/9** (identical) |
| primary `Cube_1` final | x=-1.65, z=0.525 (Ground) | x=-1.65, z=0.525 (Ground) |
| ee_min_z | — | 0.93 |

5 cubes ARE in target bin (`/World/LightBin/Floor`, `under_target=True`) but the **primary cube** (`Cube_1`) sat on Ground and was never picked. Strict gate scores primary; it fails. Function-gate sees these 5 in-targets but they fail the `_cube_actually_moved` check (must move ≥15 cm from spawn). Cube_2-6 already spawn at the wrong place inside `LightBin` (spawn x≈-1.4 → final x≈+0.35 — they DID move, but the gate logic checks displacement-from-spawn ≥ 0.15 m). Worth re-examining: this template may pass the routing-aware path if the gate counted them.

**Remaining blocker**: gate semantics + primary-cube. Robot only picks one cube (probably last in workpieces list); primary points at unmoved cube.
**Fix-effectiveness**: `{{#each workpieces}}` commit `1ff04d2b` — **R5 already had 9 cubes**. Fix changed nothing observable.

**Category**: spec/grader mismatch — could be reclassified as **K (phase_id)** if primary is changed.

### 5. `CP-NEW-machine-tender-load-unload` — controller never fired

| Metric | R5 | R6 |
|---|---|---|
| n_cubes | 4 | 4 |
| ee_min_z | None | **None** |
| Blank_1 final | x=1.30, z=0.61 (Ground) | x=1.30, z=0.61 (Ground) |

UR10 robot — same as palletizer: scene builds, but **no EE motion recorded**. Blanks slid ~2.5 m on settle and ended on Ground.

**Remaining blocker**: UR10 controller-never-fired + initial blank placement that lets them slide (no fixture/bin walls).
**Fix-effectiveness**: `1ff04d2b` — already had 4 cubes in R5. Fix had **no effect**.

**Category**: **I (build-out)** — UR10 controller wiring.

### 6. `CP-NEW-moving-conveyor-pick` — 1 cube reached target, primary picked but dropped

| Metric | R5 | R6 |
|---|---|---|
| n_cubes | 4 | 4 |
| in_target_ever | 1/4 | **1/4** (identical) |
| primary `Cube_1` final | (0.73, 0.32, 0.53) Ground | **(0.18, -0.27, 0.95) Table** |
| max_speed | 1.59 | 1.50 |

**This is the only template showing real R5→R6 evolution**: Cube_1 in R5 ended on Ground at (0.73, 0.32), in R6 ended on Table at (0.18, -0.27, 0.95). `cube_in_target_ever=True` for Cube_1. `virtual_eyes` reports `delivered_then_dislodged: detected: true`. Robot picked Cube_1, moved it into target, then it fell off.

**Remaining blocker**: friction/grip release timing OR slick target surface. Cube made it to target, then physics dislodged it.
**Fix-effectiveness**: `1ff04d2b` — **possible weak signal** that fix helped (final position is now Table-not-Ground), but R5 already showed `in_target_ever=1` so the gripper-touch happened before today's fix. Net: marginal.

**Category**: H (multimodal) **only if** we also fix the dislodge — otherwise tune friction/dwell.

### 7. `CP-NEW-machine-tender-door-interlock` — **never ran in R6**

Excluded by `filter_delivery_pattern` (pattern_hint = `"other"`). Same diagnosis as #3.

**Category**: **K (phase_id / grader)**.

### 8. `CP-NEW-isaaclab-arena-lego` — **fix demonstrably helped** but still fails

| Metric | R5 | R6 |
|---|---|---|
| n_cubes | 4 | 4 |
| max_speed | **0.00** | **0.38** ← cubes now move! |
| in_target_ever | **0/4** | **2/4** ← bricks now reach target! |
| Brick_1 final | (-0.08, 0.26, 0.79) | **(0.085, 0.636, 0.802)** ← moved |
| ee_min_z | — | 0.88 (descended) |

The baseplate-Y move (`y=-0.30 → +0.55`) put bricks IN FRONT of Franka where the gripper can reach. R5: bricks frozen at spawn (max_speed=0.00 ⇒ static or undriven). R6: 2 bricks reached the target XY. Still doesn't pass gates because `support_under_target=False` (bricks landed on `/World/Ground`, not on the baseplate target).

**Remaining blocker**: support-detection or baseplate-position. Bricks delivered to target XY but landed on Ground (baseplate may be below them; check baseplate height vs brick drop trajectory).
**Fix-effectiveness**: **CLEAR PHYSICS IMPACT** — fix `fe561ddb` is correct and progressed the canonical. One more iteration (raise baseplate z, or shrink xy_tolerance check) should pass it.

**Category**: **I (build-out, almost done)** — close, needs baseplate-height tune.

### 9. `CP-NEW-yrkesroll-packer-box-seal` — robot never moved

| Metric | R5 | R6 |
|---|---|---|
| n_cubes | 4 | 4 |
| max_speed | 0.31 | **0.29** (essentially 0 — settling) |
| in_target_ever | 0/4 | **0/4** |
| ee_min_z | — | 0.87 (didn't descend to items) |
| Item_1 final | (0.25, 0.30, 0.80) bin floor | (0.25, 0.30, 0.81) bin floor |

Items spawn in InfeedBin, settle, nothing moves them. Lid sits on Table. Robot EE at z=0.87 (rest).

**Remaining blocker**: the 2-PPC → 1-PPC collapse (commit `1c56a590`) probably introduced a controller-routing bug — single PPC with `drop_targets dict` may not be a supported signature in `setup_pick_place_controller`. Controller never fires.
**Fix-effectiveness**: Architectural cleanup, **no positive physics signal**. Possibly regressed (need diff vs R5 to confirm controller was firing before).

**Category**: **I (build-out)** — verify drop_targets dict pattern is supported by handler.

---

## Next-Track Categorization

| Track | Templates | Rationale |
|---|---|---|
| **K (phase_id / grader)** | conveyor-recirculation-loop, machine-tender-door-interlock, sorter-size-weight | Sweep can't measure them (pattern_hint=other) or grades wrong primary cube |
| **I (stub build-out)** | palletizer-layer-stack, machine-tender-load-unload, isaaclab-arena-lego, yrkesroll-packer-box-seal | Scene exists, controller wiring/positioning needs work |
| **L (SAM2/perception)** | bin-picking-random-pose | Vision pipeline blocks pose-sampler |
| **H (multimodal)** | moving-conveyor-pick | Picked-then-dislodged; needs friction/dwell tuning OR multimodal confirmation |

## Honest Fix-Effectiveness Assessment

| Commit | Template(s) | Useful? | Pass impact |
|---|---|---|---|
| `342e202d` | bin-picking-random-pose (broken `#each`) | NO — generated TypeError-crash code | 0 (would crash if it ran) |
| `ac8a3037` | bin-picking, palletizer, recirculation | Correctness-useful (fixed the crash above); built 2 new stubs | 0 unlocks. Recirculation invisible to grader. |
| `1ff04d2b` | sorter, machine-tender-LU, moving-conveyor, door-interlock | **Mostly NO observable effect** — R5 already had matching cube counts; this fix replaced a working path with a "cleaner" path | 0 unlocks |
| `1c56a590` | packer-box-seal (2-PPC → 1-PPC) | Architecturally cleaner; possibly regressed controller fire | 0 unlocks |
| `fe561ddb` | arena-lego (baseplate Y move) | **YES — clear physics improvement** (0→2 in_target, cubes moved) | 0 unlocks but **measurably closer** |

### Useful (architecture/correctness) but no pass-rate impact
- `ac8a3037` (prevented future crash + built 2 stubs; one stub is invisible to grader)
- `1c56a590` (cleaner PPC structure; controller may have regressed)

### Real progress signal
- `fe561ddb` (arena-lego): only commit with clear physics evidence. One tuning iteration from pass.

### No-op (or regression)
- `1ff04d2b`: the "`{{#each workpieces}}` to 4 truly-broken templates" diagnosis was likely **wrong** — R5 already produced the same cube counts, so the templates were not broken on spawn. Real blockers are downstream (controller fire, primary-cube selection, surface-gripper wiring).

### Single biggest miss
Two of the 9 targeted templates (**22%**) **physically cannot pass the R6 sweep** because the sweep filters them out by `pattern_hint`. Before any more "build out the stubs" work, the harness either needs `pattern_hint: navigate/sort/...` retags or a new grader path. Build-out without a measurement path is wasted token spend.

### Root cause of the disconnect
The Round 1 "spawn bug" hypothesis came from reading templates and inferring that missing `create_prim` calls = missing cubes. But cube counts in R5 already matched the workpiece declarations — meaning the engine auto-stubbed bare Xforms (or some other path filled them in) and **the real blockers were never in spawn**. Future patch-rounds should diff R(n-1) physics state *before* picking a fix, not after.
