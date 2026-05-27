# CP-NEW canonical sweep — baseline (2026-05-27)

**Goal**: measure pass-rate across CP-NEW canonicals (145 templates) to find which work + identify failure patterns en route to 100%.

**Scope**: `scripts/review/sweep_cpnew.py` — filtered to 40 templates where `pattern_hint ∈ {pick_place, sort, insert, reorient, navigate}` AND `simulate_args.target_path` + `cube_paths` present (=observe_one's delivery criterion applies). The other 105 templates have other success semantics (train/RL, OEE, calibration, etc.) — not measured here.

## Final result: **3/40 PASS (7.5%)**

### Passing templates (all `pick_place`, short cycle)

| Template | Elapsed | Notes |
|---|---|---|
| CP-NEW-brick-stacking | 55.2s | simple multi-cube stack |
| CP-NEW-rtx-sponge-bowl | 14.4s | shortest cycle |
| CP-NEW-y-merge-singulation | 16.8s | merge sortation |

### Per pattern_hint

| pattern | pass/total |
|---|---|
| pick_place | 3/26 (12%) |
| sort | 0/8 |
| reorient | 0/4 |
| insert | 0/1 |
| navigate | 0/1 |

### Failure signature distribution

| Reason | Count |
|---|---|
| not_under_target + never_in_xy + gate:support_under_target | **34/37** (92%) |
| not_under_target + gate:support_under_target | 2/37 |
| not_under_target + gate:support_under_target + gate:no_blowup | 1/37 |

**Dominant pattern**: robot never picks cube. `cube_in_target_ever=False` means cube position NEVER entered target bbox during the full `duration_s` simulation. Setup_pick_place_controller may have run, but the controller never initiated pickup — likely because:
- Multi-stage canonical waiting on sensor/vision trigger
- Required external orchestrator not active
- Controller bound to robot type that doesn't match cube setup
- Tool-call dispatcher returned controller object but its physics-step callback never fired

## Baseline comparison

| Source | Date | N | Pass | Rate |
|---|---|---|---|---|
| function_gate_shadow_sweep | 2026-05-19 | 37 | 5 | 13.5% |
| cpnew_sweep_2026-05-27 (this) | 2026-05-27 | 40 | 3 | 7.5% |

**Different template selection** — shadow_sweep used the agents-touched filter (`*_rewrite_bak`), this used pattern_hint filter. Overlap unknown without join. Likely different sample, not regression.

## maxForce-fix impact

**Zero direct impact** on this sweep. All 37 fails are "never_in_xy" — robot didn't even attempt pickup. The maxForce-fix only helps post-grip slip during transport. None of these fails reach the grip phase.

The fix WOULD help canonicals where:
- Robot attempted pickup ✓
- Grip succeeded ✓
- Cube held briefly ✓
- Cube slipped during transport (heavy cube + low maxForce cap)

None observed in this batch.

## Top failures to investigate

Easy wins likely in `pick_place` group (3/26 passing means 23 candidates):

1. CP-NEW-3station-oee (240s timeout — multi-station OEE)
2. CP-NEW-6dof-pose-estimate-pick — vision-required pose
3. CP-NEW-adaptive-3finger-gripper — non-standard gripper
4. CP-NEW-bin-picking-* (2 templates) — random pose bin picking
5. CP-NEW-conveyor-* (3 templates) — conveyor sync
6. CP-NEW-forklift-handoff-arm — multi-robot handoff
7. CP-NEW-kit-prep-* (2 templates) — kitting
8. CP-NEW-palletizer-* (2 templates) — palletizing
9. CP-NEW-yrkesroll-* (6 templates) — industrial yrkesroller

## Recommended next steps

### Path A: Investigate why 92% never-pick happens
Pick 1 representative failing template (e.g. CP-NEW-conveyor-recirculation-overflow). Trace:
- Does setup_pick_place_controller get called?
- Does the physics-callback fire?
- What does the controller's state machine look like at t=0, t=30, t=180?
- Is there a sensor/vision dependency not met?

Likely single root cause across many templates (orchestrator wiring, sensor trigger, controller selection). One fix → many unlock.

### Path B: Define per-pattern success criteria  
For `sort`, `insert`, `reorient`, `navigate` — observe_one's "cube reached bin floor" doesn't always apply. Build pattern-specific checkers.

### Path C: Hand-pick high-value templates and fix them
Cherry-pick 3-5 yrkesroll templates (industrial-expansion priority) and individually debug each to PASS.

### Path D: Re-baseline against the original 144/145 claim
Memory says "IA rev.2 closed at 144/145 (99%)". That stat used a different measurement (unit tests? scripts/qa/function_gate_*.py?). Identify the original metric — maybe we're using wrong tool.

## Files

- Sweep script: `scripts/review/sweep_cpnew.py`
- Raw results: `workspace/qa_runs/cpnew_sweep_20260527_191618.jsonl`
- This doc: `docs/notes/2026-05-27-cpnew-sweep-baseline.md`
