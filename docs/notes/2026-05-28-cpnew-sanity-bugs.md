# CP-NEW Sanity-Check: Build-Quality Bugs Blocking Function-Gate

**Date**: 2026-05-28
**Scope**: 60 CP-NEW templates (verified_status not stub/draft, OR contains `setup_pick_place_controller`, OR in the 8 known-pass list)
**Method**: Static JSON + regex analysis only — no Kit RPC, no template edits
**Source data**: `/tmp/cpnew_bugs_final.json`

---

## Summary

| Severity | Count | Templates |
|----------|-------|-----------|
| **Critical** (likely blocks function-gate) | **18** | bin-picking-with-flip, conveyor-tracking-moving-pick, gravity-dispenser-feeder, heap-zone-unstack, kitting-station-6sku, machine-tender-door-interlock, machine-tender-load-unload, oxe-sweep-into-dustpan, palletizer-mixed-sku, planning-10step-retry, sorter-color-3lane (KNOWN-PASS — see caveat), sorter-size-weight, wire-harness-route, yrkesroll-assembler-peg-bushing, yrkesroll-gripper-vacuum-pick, yrkesroll-machinist-cnc-load, yrkesroll-packer-box-seal, yrkesroll-quality-tech-fixture-gauge |
| **Major** (gate may pass but suboptimal) | **6** | 6dof-pose-estimate-pick, kit-prep-operator, kit-prep-vision-gate, moving-conveyor-pick, vacuum-gripper-sheet-pick, vision-depalletize (KNOWN-PASS) |
| **Minor** | **22** | 20× xy_tolerance missing, 6× xy_tolerance tight, 2× duration too long, 1× duration too short |
| **Cosmetic** | **3** | assembly-line-4robot-handoff, roco-bimanual-assembly, triple-arm-cell-handoff (multi-PPC on *different* robots — handler is per-robot, see Section 5) |
| **Clean** | **11** | adaptive-3finger-gripper, bin-picking-random-pose, controller-benchmark-shootout, forklift-handoff-arm, isaaclab-arena-lego, label-applicator-pose, palletizer-layer-stack, rtx-sponge-bowl (KNOWN-PASS), tray-stack-unstack, yrkesroll-inspector-reject-divert, yrkesroll-paint-sprayer-trajectory |

**Totals**: 60 templates checked, **49 with at least one finding**, **141 total findings** (105 if minor xy-tol-missing is treated as default-OK).

---

## Pattern 1 — `sim-cube-not-spawned` (60 instances across 14 templates) — CRITICAL

`simulate_args.cube_paths` lists a prim path that nothing in `code_template` ever creates (no `create_prim`, no f-string loop with that pattern, no `{{workpieces[N].path}}` direct ref in a `create_*` call, no role-defaults templating).

Function-gate `cube_paths` resolution will fail — the harness can't track an object that doesn't exist.

**Affected templates** (cube-count blocked / total in sim_args):

| Template | Missing / Total | Pattern |
|----------|-----------------|---------|
| gravity-dispenser-feeder | 10/10 | Items declared in sim_args; code only has `{{dispenser.path}}` — no per-item spawn loop |
| sorter-size-weight | 9/9 | Workpieces 1-9 in role_defaults but code_template only spawns indices 0-2 (LLM dropped the spawn loop) |
| sorter-color-3lane **[KNOWN-PASS]** | 6/9 | code_template spawns workpieces[0..2] only; original `code` field has full for-loop but template lost it |
| vision-depalletize **[KNOWN-PASS]** | 0/6 critical, 6 unclear | All paths exist via `box_paths = [{{workpieces[0..5].path}}]` then `for path in zip(box_paths, ...): create_prim(...)` — heuristic flagged unclear; on inspection this is fine |
| heap-zone-unstack | 8/8 | Items 1-8 in sim_args; code_template only declares `{{heap_zone.path}}` Xform |
| kitting-station-6sku | 6/6 | Cubes never get a create_prim |
| palletizer-mixed-sku | 6/6 | Boxes never created |
| wire-harness-route | 5/5 | WireSegments never created |
| oxe-sweep-into-dustpan | 4/4 | Debris items never created |
| yrkesroll-gripper-vacuum-pick | 4/4 | Items 1-4 never created |
| machine-tender-load-unload | 4/4 | Blanks never created |
| yrkesroll-packer-box-seal | 4/4 | Items + Lid never created |
| moving-conveyor-pick | 4/4 | Cubes never created |
| machine-tender-door-interlock | 3/3 | Blanks never created |
| 6dof-pose-estimate-pick | 3/3 (unclear) | sourceBin/Cube_N templated through workpieces but spawn path not direct |
| conveyor-tracking-moving-pick | 2/3 | role_defaults has 3 workpieces; only [0] indexed |
| vacuum-gripper-sheet-pick | 3/3 | Sheet_4/5/6 referenced but only spawned via incomplete logic |

**Root cause hypothesis**: LLM template-extraction step (Phase 18b-ish) stripped Python for-loops when converting `code` -> `code_template`. The role_defaults list is correct, but the spawn iteration code went missing.

**Recommendation**:
- **Template fix** preferred — add `{{#each workpieces}}create_prim(prim_path="{{this.path}}", ...){{/each}}` blocks in the affected templates (modeled on `CP-NEW-bin-picking-random-pose.json` which uses this pattern correctly).
- **Handler change** *not* recommended — silently spawning missing prims would mask real authoring bugs.

---

## Pattern 2 — `sim-cube-unclear-spawn` (37 instances across 8 templates) — MAJOR

Path is referenced via `{{workpieces[N].path}}` somewhere in code, but not directly inside a `create_*` call (e.g., placed in a list literal but the spawn loop is templated or implicit).

Many of these are **likely fine in practice** (the templated list gets iterated by a Python for-loop after substitution), but the heuristic can't confirm. Examples:
- `vision-depalletize` ✓ confirmed OK on manual read — uses `box_paths = [...]` then `for path in zip(box_paths, ...): create_prim`
- `kit-prep-operator`, `kit-prep-vision-gate` — same pattern as vision-depalletize, likely OK
- `6dof-pose-estimate-pick`, `machine-tender-*`, `yrkesroll-packer-box-seal` — need eyeballing

**Recommendation**: Spot-audit each in a focused round; downgrade to clean once confirmed. No handler change.

---

## Pattern 3 — `multi-PPC-same-robot` (8 instances) — CRITICAL

Two or more `setup_pick_place_controller` calls in the same template targeting the same robot. The handler (`handlers/pick_place.py:976` for `builtin`, `:4125` for `curobo`) uses a per-robot subscription tag `_<flavor>_pp_sub_<ROBOT_TAG>` and **explicitly tears down the prior subscription for the same robot**.

So only the LAST call's controller survives. Earlier calls' work is silently discarded.

| Template | PPC calls | Same-robot multi-call rationale |
|----------|-----------|--------------------------------|
| planning-10step-retry | **8** | LLM split into 8 sequential pick-place "steps" — only #8 runs |
| yrkesroll-quality-tech-fixture-gauge | 6 | Same robot, 6 phases — only #6 runs |
| yrkesroll-assembler-peg-bushing | 3 | Same robot, 3 phases |
| bin-picking-with-flip | 2 | Pick → flip → re-pick on same arm; #2 wipes #1 |
| machine-tender-door-interlock | 2 | Load + unload phases |
| machine-tender-load-unload | 2 | Same |
| yrkesroll-machinist-cnc-load | 2 | Same |
| yrkesroll-packer-box-seal | 2 | Same |

**Recommendation**: This is a multi-issue:
- **Template fix** (preferred for most): collapse the N PPC calls into a single one with the full `drop_targets` dict — bin-picking-random-pose uses this pattern. The PPC handler is designed to cycle through `source_paths` and place each at its drop_target.
- **Handler change** for genuinely-phased templates (machine-tender load+unload): add `phase_id`/`sub_id` kwarg to PPC so phases get separate subscriptions on the same robot. This is non-trivial — the function-gate observe window already wraps a single cycle.
- For `planning-10step-retry` specifically: this template's intent (10-step retry) probably requires different scaffolding entirely; flag for redesign.

---

## Pattern 4 — `multi-PPC-different-robots` (4 instances) — COSMETIC (not a bug)

Multi-arm templates correctly use one PPC per robot:
- 3station-oee (3 robots) **[KNOWN-PASS]**
- assembly-line-4robot-handoff (4 robots)
- triple-arm-cell-handoff (3 robots)
- roco-bimanual-assembly (2 robots)

Verified against `handlers/pick_place.py:973` — `_SUB_ATTR = "_builtin_pp_sub_" + _ROBOT_TAG`. Each robot has an independent subscription slot, so per-robot teardown does not interfere with siblings.

**Recommendation**: **Documentation update** only. Add a header comment in `pick_place.py` clarifying that the same-robot teardown is *intentional* (prevents stale subs), and note that multi-arm templates are first-class. Static-analysis sweeps should skip same-robot detection across distinct robot paths.

---

## Pattern 5 — `sim-target-not-spawned` (1 instance) — CRITICAL

| Template | target_path | Issue |
|----------|-------------|-------|
| wire-harness-route | `/World/Clip_4` | Routing target Clip_4 declared in role_defaults but never `create_prim`'d in code_template |

**Recommendation**: Template fix — add a `create_prim` (or `create_bin`) call for `/World/Clip_4` in the routing wave.

---

## Pattern 6 — `sim-target-unclear-spawn` (2 instances) — MAJOR

| Template | target_path | Notes |
|----------|-------------|-------|
| kit-prep-vision-gate | `/World/KitTray` | Templated as `{{kit_tray.path}}` somewhere but not directly in a `create_*` call — likely OK but worth a manual look |
| kitting-station-6sku | `/World/KitTray` | Same pattern |

**Recommendation**: Manual confirm. If genuinely templated through a list+loop, it's fine — same false-positive class as pattern 2.

---

## Pattern 7 — `xy-tol-missing` (20 instances) — MINOR

Pick-place templates without explicit `simulate_args.xy_tolerance`. Function-gate defaults vary; the 8 known-pass templates also lack this (so it's not strictly required for pass). However, tight defaults could cause flakiness.

**Affected**: amr-pickup-handoff, barcode-scanner-divert, bottle-cap-tighten, brick-stacking **[KNOWN-PASS]**, cad-revision-drift, controller-shootout-cp **[KNOWN-PASS]**, conveyor-recirculation-overflow, dr-curriculum, drawer-open, inspect-reject **[KNOWN-PASS]**, multi-cam-triangulation, nir-material-divert, operator-ergonomics, peg-bushing-impedance, plc-fixture, robohive-relocate-pen, tactile-insertion, wire-harness-route, y-merge-singulation **[KNOWN-PASS]**, 3station-oee **[KNOWN-PASS]**.

**Recommendation**: **Documentation** — note the simulator's default xy_tolerance in the canonical-authoring guide. **No template edit** needed if default is sane (≥10 cm).

---

## Pattern 8 — `xy-tol-tight` (6 instances) — MINOR

Templates with `xy_tolerance < 0.05` m. Likely to flake even on a working controller.

| Template | xy_tol |
|----------|--------|
| yrkesroll-assembler-peg-bushing | 0.01 |
| yrkesroll-assembler-snap-fit | 0.01 |
| yrkesroll-welder-mig-tack | 0.02 |
| kit-prep-operator | 0.04 |
| kit-prep-vision-gate | 0.04 |
| yrkesroll-packer-box-seal | 0.04 |

The 0.01 m tolerances were probably copied from real assembly-spec tolerances but the function-gate xy check resolves cube-centroid-to-target-centroid in world units; 1 cm rarely survives PhysX settling + planner drift.

**Recommendation**: **Template fix** — raise to 0.05–0.10 m for function-gate pass; gate the real <1cm spec in a separate assembly-precision metric.

---

## Pattern 9 — `duration-too-long` / `duration-too-short` (3 instances) — MINOR

- `planning-10step-retry`: 700s — clearly excessive; symptom of the 8-PPC bug.
- `wire-harness-route`: 360s — borderline; reasonable if routing has 5 segments.
- `yrkesroll-ergonomics-lift-assist`: 12s — way too short for any pick-place; will time out before EE reaches target.

**Recommendation**: Template fix for the two outliers. `wire-harness-route` 360s likely OK once spawn bug is fixed.

---

## Per-Template Quick Index

### Critical (likely blocks function-gate even with handler fixes)

| Template | Bugs | Root cause |
|----------|------|------------|
| `bin-picking-with-flip` | multi-PPC × 2, sim-cube-unclear × 1 | 2 PPCs same robot |
| `conveyor-tracking-moving-pick` | sim-cube × 2, unclear × 1, wp-defaults-unrefed | code_template only spawns workpieces[0] |
| `gravity-dispenser-feeder` | sim-cube × 10 | code never spawns Items 1-10 |
| `heap-zone-unstack` | sim-cube × 8 | code never spawns HeapZone items |
| `kitting-station-6sku` | sim-cube × 6, sim-target × 1 | Cubes + KitTray never created |
| `machine-tender-door-interlock` | multi-PPC × 2, sim-cube-unclear × 3 | 2 PPCs same robot |
| `machine-tender-load-unload` | multi-PPC × 2, sim-cube-unclear × 3 | 2 PPCs same robot |
| `oxe-sweep-into-dustpan` | sim-cube × 4 | Debris items never spawned |
| `palletizer-mixed-sku` | sim-cube × 6, wp-defaults-unrefed | Boxes never created |
| `planning-10step-retry` | multi-PPC × 8, duration 700s | Whole template design broken |
| `sorter-color-3lane` **[KNOWN-PASS]** | sim-cube × 6, wp-defaults-unrefed | code_template spawns only 3/9 cubes — yet passes; likely because gate counts any single delivery |
| `sorter-size-weight` | sim-cube × 9, wp-defaults-unrefed | Same as sorter-color but no known-pass |
| `wire-harness-route` | sim-cube × 5, sim-target × 1, duration 360s | Segments + Clip_4 missing |
| `yrkesroll-assembler-peg-bushing` | multi-PPC × 3, xy-tol 0.01 | 3 PPCs same robot |
| `yrkesroll-gripper-vacuum-pick` | sim-cube × 4 | Items never spawned |
| `yrkesroll-machinist-cnc-load` | multi-PPC × 2 | 2 PPCs same robot |
| `yrkesroll-packer-box-seal` | multi-PPC × 2, sim-cube × 4, xy-tol 0.04 | Items + Lid never spawned, 2 PPCs |
| `yrkesroll-quality-tech-fixture-gauge` | multi-PPC × 6 | 6 PPCs same robot |

### Known-pass — sanity caveats

| Template | Status | Caveat |
|----------|--------|--------|
| `3station-oee` | ✓ pass | 3 robots × 1 PPC each (intended) |
| `brick-stacking` | ✓ pass | xy_tolerance missing (acceptable default) |
| `controller-shootout-cp` | ✓ pass | xy_tolerance missing |
| `inspect-reject` | ✓ pass | xy_tolerance missing |
| `rtx-sponge-bowl` | ✓ pass | Clean |
| `sorter-color-3lane` | ✓ pass | code_template spawns only cubes[0..2] of 9 declared — passes because color-routing only needs 1 successful pick-routed. Long tail untested |
| `vision-depalletize` | ✓ pass | All boxes spawned via list+for-loop; heuristic false-positive |
| `y-merge-singulation` | ✓ pass | xy_tolerance missing |

---

## Recommendations Summary

| Action | Templates count | Priority |
|--------|----------------|----------|
| **Template fix: re-add spawn loops** (sim-cube-not-spawned) | 14 | HIGH — biggest unlock |
| **Template fix: collapse same-robot multi-PPC into one call with drop_targets** | 6 (planning-10step-retry needs redesign) | HIGH |
| **Template fix: raise tight xy_tolerance to 0.05** | 4 | MEDIUM |
| **Template fix: fix wire-harness-route Clip_4 spawn + duration** | 1 | MEDIUM |
| **Template fix: yrkesroll-ergonomics-lift-assist duration 12s → 60s+** | 1 | MEDIUM |
| **Manual review of "unclear-spawn" pattern** | 6 | LOW — likely false positives |
| **Documentation: clarify multi-robot PPC pattern** in pick_place.py header | — | LOW |
| **Documentation: xy_tolerance default** in canonical-authoring guide | — | LOW |
| **Handler change: phase_id for genuine same-robot phasing** (machine-tender) | — | DEFER |

### Expected unlocks if all 14 sim-cube-spawn fixes + 6 collapsible multi-PPC fixes applied

- **20 templates** moved out of "critical" — function-gate path becomes runnable.
- Subset that actually passes still depends on reach-envelope, planning-obstacle, contact-physics tuning (out of static-analysis scope).
- Realistic upper bound: **+12 to +15 templates** to function-gate-pass list (some will still fail on physics issues unrelated to spawn/PPC).
- Lower bound: **+5 to +8** if reach/physics issues dominate.

---

## Method notes & limitations

- Static analysis only — did not exec code_template via Mustache renderer + Python AST.
- "sim-cube-not-spawned" uses heuristic spawn-detection (literal, f-string, role-templating with direct create_* binding, list-then-loop pattern). False positives possible when spawn-loop is too far from the path-list assignment.
- Did NOT check reach-envelope (robot_base_xy vs target_xy distance) — that's planning-obstacle / handler-side.
- Did NOT check planning_obstacles completeness — heuristic difficult without robot family.
- Did NOT verify `verify_args.stages` correctness — out of scope per task spec (focus was simulate_args + code).
- Multi-PPC re-classification verified by reading `handlers/pick_place.py:973, 4120` — `_SUB_ATTR` is per-robot.
- Bug data: `/tmp/cpnew_bugs_final.json`. Sev-grouping: `/tmp/cpnew_bug_groups.json`.
