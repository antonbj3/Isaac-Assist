# Expansion Direction Plan — toolify-then-scale

Status: DRAFT for Anton's review — 2026-06-03. Author: autonomous session.
Origin: Anton's strategic question — "should we plan the direction (≈200 new canonicals) and spec each with consistent structure re: tools, before grinding 100% on the current set?" + "tools can generate the USD code, de-abstract if you wish." Answer: **yes — but toolify the recurring 'body' patterns first, then scale; abstraction need not cost customizability because codegen tools emit editable USD.**

---

## 1. Where we are (verified, not inferred)

**Tool registry is large + tiered:** 407 registered tools. Tier-A high-level capability tools = 56 (scene: bins/conveyors/dispensers/kit-tray/rotary/heap/linear-axis; robot: wizard/import/anchor/assemble; gripper; pick-place +vision; sensors: vision-gate/proximity/F-T/barcode/NIR; compliance: admittance/impedance/insertion/bimanual/whole-body). Tier-B mid 70, Tier-C low-level USD primitives 37, + ~244 domain (diagnostics/training/sdg/...).

**Consistent on the BACKBONE, inconsistent on the BODY:**
- Backbone (deterministic, applied uniformly): `robot_wizard`, `set_physics_scene_config`, `move_to_pose`/`plan_trajectory`, `setup_pick_place_controller`. Real discipline.
- Body (un-abstracted, copy-pasted): scene baseline, rigid-body arrays, palletizer grids, materials. Measured: scene-build code is ~42% high-level-tool / ~58% raw USD. **200 templates hand-roll the DomeLight+Ground+Table baseline; 172 hand-roll the rigid-body init loop; 49 hard-code palletizer drop_target dicts.**

**The real cost is maintainability + drift, NOT a silent physics bug.** (Verified: only 8/172 RigidBodyAPI templates omit MassAPI, and they're mostly SDG/teleop/drawer where it's plausibly intentional — so the "forgot MassAPI → broken gravity everywhere" hazard is NOT real at scale.) The honest problem: "change table z" = edit 200 files; the same logical op is hand-rolled with slightly different API ordering / attribute style across 200 templates = accidental divergence with no single source of truth.

**The trade-off is THREE-way, not two-way:**
1. Parametric mechanism, no desired variation in *how* → **abstract** (the backbone won here).
2. Genuinely unique structure (tool-dock layouts, pallet geometry, fixtures) → **leave raw** (a tool would need a parameter surface as big as the code).
3. **Recurring with accidental drift** (scene baseline, rigid-body array) → currently raw, **should be toolified**. ← the actual problem, and where the CP-NEW expansion is concentrated (it looks like unique industrial geometry but is mostly category-3 with new coordinates).

---

## 2. Design principle (resolves determinism vs customizability)

Anton's point: **a high-level tool can GENERATE the USD code and let you de-abstract when you need to customize.** The registry already splits tools into "data" vs "codegen" (codegen tools emit code). So the rule for every new high-level tool:

> **Tool-first by default (deterministic, version-controlled, regression-tested); every codegen tool can emit its expanded USD (`--emit` / `expand=True`) so a template that needs a one-off tweak de-abstracts THAT element instead of hand-rolling from scratch.**

This means abstraction costs ~zero customizability: you compose tools for the 95% that is parametric, and drop to emitted-then-edited USD for the 5% that is genuinely unique — never copy-paste a baseline.

---

## 3. The toolify gate (when to abstract vs leave raw)

Promote a raw pattern to a high-level tool when **all three** hold:
1. **Recurrence ≥ ~10 templates** OR it sits in a safety/physics-correctness path (N=1 still justifies it there).
2. **Variation is parametric, not structural** — instances differ by values (positions, sizes, counts), not control flow. Litmus: can every existing instance be expressed as one signature WITHOUT a freeform `python_code` arg? Yes → toolify. No → leave raw.
3. **It encodes a correctness invariant** (required API set/order, snapshot-before-press sequencing, teleport-before-joint) whose silent mis-ordering breaks the sim.

Geometry that fails (2) — tool stands, pallets, fixtures, sheet layouts — **stays raw on purpose.** That flexibility is earned; don't bury it behind a 12-arg tool.

---

## 4. Plan — three phases (toolify → spec → scale)

### Phase 0 — Toolify the "body" backbone (BEFORE the next expansion wave)
Build these high-level codegen tools (ranked by recurrence × leverage), each with `expand=True` USD-emit for de-abstraction:
1. **`create_scene_baseline(intensity, ground_scale, table_size, table_height, physics_config)`** — 200 templates. Highest blast radius, lowest risk; encodes the DomeLight+Ground+Table+physics ordering.
2. **`create_rigid_body_array(prim_type, positions, size, mass, profile='rigid_light|rigid_heavy|static')`** — 172 templates. Absorbs the init loop; the `profile` preset makes the required API set a single source of truth.
3. **`compute_palletizer_grid(pallet_size, layers, per_layer, pattern='brick|grid', anchor)` → drop_targets** — 49 templates currently hard-type coordinate dicts; generate them instead.
4. **`setup_physics_callback(kind='graded_response|state_machine|contact_monitor', params)`** — wraps the 3 safety canonicals' hand-written `run_usd_script` callbacks (ISO-10218 SSM, e-stop) so the scaling table / e-stop baseline is version-controlled + cross-checked against verify_args inside the tool, not manually mirrored.

**Migration is incremental + reversible:** new tools emit the SAME USD the templates build today, so migrating a template = replace ~10 raw lines with 1 tool-call and diff the emitted USD against the original (regression-safe). Do NOT mass-migrate blind; migrate a cluster, verify on the gate, repeat.

LEAVE RAW (fails gate criterion 2): unique workpiece/fixture geometry. Add one thin helper `bulk_set_semantic_label(prims, label)` (the 20× call is parametric).

### Phase 1 — The consistent template spec ("the mall")
A single canonical template structure every new canonical follows:
- **Build order:** `create_scene_baseline` → robot (`robot_wizard`/`import_robot`) → workpieces (`create_rigid_body_array` + `compute_palletizer_grid`) → scene elements (Tier-A `create_*`) → controller (`setup_pick_place_controller`/vision/compliance) → sensors/gates.
- **Mandatory fields:** `goal` (a TASK, not an implementation detail — see §6 purge criteria), `intent` (robot/gripper/task/feed/perception tags), `code_template` (interpolated, tool-composed), `verify_args`, `simulate_args` (target_path, duration, cube_paths), `motion_controllers` honesty record.
- **Custom escape-hatch:** when a scene element has no Tier-A tool, emit-then-edit via `expand=True`, never copy-paste a baseline.
- **Naming:** capability-descriptive (`CP-NEW-<robot>-<gripper>-<task>-<variant>`), not numeric-only.

### Phase 2 — Taxonomy → the ~200 target set
The number falls out of the meaningful cross-product, weighted to the under-built gaps (measured: suction thin = 14 pick_place / 3 sort / **0 reorient**; **3-finger absent from the gate**; reorient thin = 4, all parallel-jaw). Axes:
- **Robot:** Franka, UR10, multi-robot/handoff, gantry, humanoid.
- **Gripper:** parallel-jaw (saturated), **suction** (expand — Anton's direction: faithful seal, compliant mount, no kinematic-teleport oracle), **3-finger** (new), tool-changer.
- **Task:** pick-place, palletize/stack, sort/route, **reorient/flip** (expand), kitting, insertion/assembly, inspect-reject, machine-tend.
- **Feed:** static, conveyor, gravity, rotary.
- **Perception:** none, color, material (barcode/NIR), vision-classifier, multi-cam.
- **Industrial/yrkesroll depth:** ROS2-production parity, PLC/Modbus/OPC-UA/MQTT bridges, role canonicals (welder, packer, forklift/AMR, inspector, quality-tech) — each built on Phase-0 tools, not raw.

Each target canonical = one row in the taxonomy, spec'd against the Phase-1 mall.

---

## 5. Why this also serves "100% function gate"
- Pruning indefensible templates (done: 9 archived, 121→112) makes 100% = "100% of distinct capabilities," not API-clones.
- Phase-0 toolification removes the accidental-drift surface that makes the gate fragile to maintain, and standardizes the physics/scene construction the eyes grade.
- Then 100% is a meaningful, holdable target on a coherent set — and expansion scales deterministically instead of 3×-ing the copy-paste body.

## 6. Recommended sequencing decision for Anton
**Pause net-new CP-NEW industrial/yrkesroll templates until Phase-0 tools 1–3 ship.** Every template added before toolifying re-pays the baseline+rigid-body tax in copy-paste and enlarges the eventual migration. Tools 1–3 are pure category-3 wins: they increase determinism with zero loss of customizability (the variation they absorb is accidental, not intentional). Phase-0 first, then mall, then the 200.

---

## 7. Bidirectional abstraction — troubleshooting must be abstracted too (Anton, 2026-06-03)

> **⚠️ STATUS UPDATE 2026-06-23 — §7–9 PLAN EXECUTED; THE DIAGNOSE LOOP IS CLOSED. Do not re-derive "the LLM is blind" from the present-tense below.** The "build diagnose_task_outcome to close the loop" plan in §7–9 was carried out. The LLM-callable diagnostic stack now exists, is registered, and is verified working:
> - `observe_scene` — LIVE scene_eyes (`scripts/qa/scene_eyes.py --attach`) on the LLM's own built scene → the EXACT QA truth tool, no analysis divergence (handler `diagnostics.py:_handle_observe_scene`, built for "#28 gap 2, Anton").
> - `diagnose_task_outcome` — the §9 WHY-classifier, productized in `qa/task_outcome.py` (P2-06); reads a recorded `ts_<template>.json` and grades each object DELIVERED_CLEAN / TOPPLED_IN_DEST / RODE_OFF_BELT / NOT_PICKED / FLUNG_TO_FLOOR / DROP_IMPRECISE_OR_EJECT from raw motion. Verified sane on 159 saved artifacts + `tests/test_task_outcome.py`.
> - `static_eyes` (pre-build no-Kit geometry), `diagnose_pick_execution` (controller-side ctrl:* localizer), `trace_goal_frame` (planner goal trace), `verify_pickplace_pipeline` (gate). 51 observation/verify tools registered in total.
>
> So §7–9's "no task-level tool exists / the loop is NOT closed / greenlight-ready but unbuilt" is **stale plan-tense, not current state**. An Explore survey on 2026-06-23 mis-read this doc as a live gap and reported "the LLM can BUILD but cannot OBSERVE" — wrong. Lesson (the doc's own §8 standing note): verify each old-research claim against the live system before it becomes a plan dependency. The genuinely-open links below (PERCEIVE multimodal wiring, conveyor-sync handler fix §8.2, body toolify §4) are real; the DIAGNOSE link is **closed**.

The product's user is an LLM; it must be able to TROUBLESHOOT, not just build. Abstraction does not hurt that — IF it is **bidirectional**. Verified gap: 56 high-level CONSTRUCTION tools, but diagnostics are infra-level (check_collisions, diagnose_physics_error, check_tf_health, check_vram, inspect_graph) + pass/fail gates (verify_pickplace_pipeline / function-gate). **No task-level "why did the pick-place / grasp / delivery fail" tool exists.** Construction is abstracted; diagnosis is not. ~~[2026-06-03]~~ → **RESOLVED 2026-06-23: `diagnose_task_outcome` + `observe_scene` now provide exactly this task-level WHY (see the §7 banner).** (All of review-#2's RCA — +Y place-bias, belt ride-off, grasp-eject — was done MANUALLY by reading scene_timeseries; the LLM cannot do that as a tool today.)

**Three layers of troubleshooting that abstraction ENABLES when bidirectional:**
1. **Prevention** — high-level tools encode correct patterns → fewer failures (can't forget the API set if `assign_physics_profile` owns it). Abstraction shrinks the debug surface.
2. **Task-level diagnosis (the missing half)** — the LLM must diagnose at the same level it builds, in task terms. Promote the eyes (`scene_timeseries.py`) to a first-class tool **`diagnose_task_outcome(target_paths, duration)` → per-object {delivered, err_xy, tilt, drift, grip_rigidity, state} + the WHY (reach / grasp-eject / collision / drop-precision / belt-ride-off / misroute)**. This is the single highest-value missing tool: it makes the LLM self-sufficient at the RCA a human did all night, and a trustworthy task-level WHY *is* the honest-eyes mandate productized (no false-positive success).
3. **De-abstraction drill-down** — when task-level diagnosis isn't enough, `expand=True` emits the concrete USD to inspect. The escape-hatch.

**Design principle (add to the toolify gate):** every CONSTRUCTION abstraction ships with a DIAGNOSTIC counterpart at the same abstraction level — tools come in pairs, build + diagnose. A capability tool without a matching task-level diagnostic is incomplete: the LLM could create the failure but not explain it.

**Implication for Phase-0 ordering:** `diagnose_task_outcome` (eyes-as-a-tool) is co-equal priority with `create_scene_baseline` — it is the troubleshooting backbone the whole expansion (and the LLM's autonomy) depends on. Build it alongside the construction tools, not after.

---

## 8. How the LLM works against the scene — the loop, current-state, skeptical (Anton, 2026-06-03)

**Caveat first (Anton's guard):** older research (2026-05-21 vision-diagnostics, 2026-05-27 llm-input-format/integration) describes INTENT as of 2–3 weeks ago. The current state DIVERGES — treat those docs as hypotheses, verify per-item before relying. Everything below is verified against the codebase NOW or flagged as unverified.

**The loop the LLM must run against a scene:**
```
PERCEIVE → RETRIEVE/RATIFY → BUILD → SIMULATE → DIAGNOSE → ITERATE
```

Verified status of each stage (skeptical):
| Stage | Mechanism | Verified status NOW |
|---|---|---|
| PERCEIVE | multimodal → LayoutSpec IR (text/voice/photo/sketch/viewport) | EXISTS but ~31% of 159 files carry scaffold/stub/TODO; instantiator has `dry_run`. **Partially live** (old doc's "Production" overstates). Per-modality wiring UNVERIFIED. |
| RETRIEVE/RATIFY | template retrieval + confidence-gate + ratify/HIL | exists; hit@1≈0.83 on a 30-prompt bench (2026-05-27, **re-verify — bench is stale**). |
| BUILD | 407 registered tools | real but **125 unused (a third dead)**; the "body" (scene baseline/rigid-body/palletizer) is ~58% raw copy-paste (verified §1). |
| SIMULATE | Kit RPC, single-tenant | the serial bottleneck (1 run at a time) — shaped this whole session. |
| **DIAGNOSE** | ~~scene_observer.py + scene_timeseries.py, QA-only~~ → **CLOSED 2026-06-23** | **LLM-callable now: `observe_scene` (=live scene_eyes --attach), `diagnose_task_outcome` (scene_timeseries WHY-classifier, P2-06), `static_eyes`, `diagnose_pick_execution`, `trace_goal_frame`.** The loop IS closed; the LLM sees what the gold-gate sees. (Was the weakest link in the 2026-06-03 draft.) |
| ITERATE | de-abstract (codegen emit USD) + re-run | escape-hatch partially present (codegen tools); no in-loop diagnose to drive it. |

**The single highest-leverage near-term move is CLOSING THE LOOP at DIAGNOSE — above even the construction toolify.** Reason: without an LLM-callable diagnostic, the LLM cannot troubleshoot *anything* autonomously — the entire review-#2 RCA (place-bias, belt ride-off, grasp-eject) was done by a human reading positions. Construction abstractions make building cleaner, but the product's value ("an LLM that works against the scene") is gated on the LLM being able to OBSERVE and EXPLAIN, not just build.

**Decision (skeptical, near-term, in priority order):**
1. **Close the loop:** resolve the two diagnostic surfaces (scene_observer 2299L vs scene_timeseries 531L — are they redundant or complementary? — itself a question to answer, don't assume) into ONE LLM-callable `diagnose_task_outcome` tool returning per-object {delivered, err, tilt, drift, grip, state} + the WHY. This is the bidirectional-abstraction linchpin (§7) AND the honest-eyes mandate productized.
2. **Toolify the body** (§4 Phase-0) — determinism + maintainability for scale; do NOT mass-build new canonicals first.
3. **Prune** (done: 121→112) — keeps "100%" meaningful.
4. **THEN** the consistent mall (§4 Phase-1) + the ~200 expansion (§4 Phase-2), each built on a closed, tooled loop.

**Skeptic's standing note:** don't let a grand vision (200 canonicals, full multimodal) outrun the verified loop. The loop has a broken link (diagnose) and a partially-scaffold link (perceive). Fix/verify those before scaling — a bigger library on an open loop just multiplies the un-diagnosable surface. Verify each old-research claim against the live system before it becomes a plan dependency.

### 8.1 Current-state corrections (Anton, 2026-06-03 — supersede the §8 draft where they conflict)
- **DIAGNOSE is a SUCCESSION, not two surfaces to consolidate.** Yesterday's work moved binary pattern-detectors (`scene_observer.py`, prior gen) → **time-series grading (`scene_timeseries.py`, current)** = the "continuous not binary" theme. scene_timeseries IS the live eyes; the binary approach is superseded. So the loop-closing tool = the time-series reader made LLM-callable, NOT a merge of the two.
- **The lever is CORRECT DATA-READING, not vision.** Anton: "vision fungerar sisådär; är dataavläsningen korrekt så bör det vara bättre, generellt." Verified all session: the CP-27 static-surface finding, conveyor-sync, grasp-eject RCAs all came from reading the time-series RIGHT — not from vision; and the "gates lie" false-positives come from data-reading being WRONG. So the primary diagnostic is correct programmatic time-series reading (positions/contacts/state); vision (SAM2/VLM, 2026-05-21 research) is a so-so complement only for the 3-4 render-state/asset-identity gaps.
- **PERCEIVE (IR/Multimodal/LayoutSpec): UNCERTAIN.** Even the lead has no current perspective. NOT a plan dependency; assess standalone before anything leans on it. De-emphasized in the loop until verified.

**Revised linchpin:** close the loop with ONE LLM-callable diagnostic that is the correct-data-reading TIME-SERIES grader (scene_timeseries productized into `diagnose_task_outcome`), vision optional. The whole value is "read the data right" — which is simultaneously the honest-eyes / no-false-positive guarantee. Everything else (toolify body, mall, 200 expansion) sits downstream of a closed, correct-reading loop.

### 8.2 Correction (2026-06-03 ~08:24, skeptic-tested): static-respawn is NOT a reliable conveyor fix
§4/§6 floated "static-respawn (belt≈0)" as the reliable fallback for conveyor-sync ride-off. TESTED on CP-12 → TIMEOUT/HANG (the
static belt hangs the sensor-gated controller; no cube reaches the sensor). CP-27 works static but CP-12 hangs → layout-dependent,
NOT universal. So the conveyor-sync ride-off (the dominant gate blocker — CP-12/inspect-reject/nir-material/palletizer-mixed-sku
all fail by item-rides-off-while-robot-busy) has **NO reliable per-template fix; it requires a HANDLER fix** (widen the claim
window / belt-index pause-on-claim in pick_place.py's _next_cube / _cube_to_pick). This SHARPENS the conveyor question: it's not
"thin vs static-respawn" — it's "fix the sensor-gate claim logic once (handler) vs accept conveyor as a thin slice." Anton's call.

---

## 9. Spec: `diagnose_task_outcome` — the loop-closing tool (✅ SHIPPED — was "greenlight-ready, 2026-06-03")

> **✅ BUILT & REGISTERED (2026-06-23 verification).** This spec was implemented: `service/isaac_assist_service/qa/task_outcome.py` (`classify_timeseries` + `diagnose`, the §9.1 WHY-classifier productized), handler `_handle_diagnose_task_outcome` (diagnostics.py), schema `diagnose_task_outcome` (tool_schemas.py), unit test `tests/test_task_outcome.py`. The live complement `observe_scene` (scene_eyes --attach) was added for the in-loop case. The spec below is now DESIGN HISTORY, not a TODO.

The #1 action (§8). Productize `scene_timeseries.py` (the current time-series eyes) into a registered LLM-callable tool so the LLM
diagnoses in task terms — the RCA a human did all night, as one tool-call. Vision optional (correct-data-reading is the lever).

**Interface:** `diagnose_task_outcome(target_paths|cube_paths: list, duration_s: int, expand: bool=False) -> report`
- Plays the current stage `duration_s`, logs per-tick {pos, up, spd, vz, contacts} + init pos (already done by scene_timeseries).
- Returns structured `report` (below). `expand=True` also returns the raw per-tick series + contact log for drill-down (de-abstraction §2).

**Per-object report (from scene_timeseries metrics — already computed):**
`{name, delivered: bool, final_pos, err_xy, settled_tilt°, impact_vz, drift, stack_align(mm,score), grip_rigidity(carry_jerk+grip_gap), containment(±, kind), bin, state, why}`

**`why` taxonomy (STATE + cause, derived from the time-series — the correct-data-reading classifier):**
| why | derivation (from raw data, NOT controller self-report) |
|---|---|
| DELIVERED_CLEAN | in dest footprint, seated, tilt<thresh, no flags |
| NOT_PICKED / NEVER_CLAIMED | z never rises > spawn+0.10 AND final≈spawn (robot never engaged) |
| RODE_OFF_BELT | on a belt + final_x past belt-exit (conveyor-sync: crossed sensor while robot busy) — the dominant blocker |
| GRASP_FAIL_UNGRASPABLE | EE reached cube but z never rises (jaw<SKU, or grip-miss) |
| GRASP_EJECT_PLACE_BIAS | lifted then lands off-target with the systematic +Y offset (grasp-close squeeze-out) |
| COLLISION_DISTURBED | a previously-placed cube's pos shifts when a later cube is placed (2nd-cube-push) |
| DROP_IMPRECISE | placed but err_xy>thresh / on-rim (not seated) |
| MISROUTED | seated in a bin that is NOT its color/class's required bin (sort) — false-positive guard |
| TOPPLED / NON_RIGID_GRIP / LOOSE_GRIP | delivered but tilt>thresh / in-air jitter / cup-cube gap |
| CONTROLLER_HANG | no cube engaged for the whole window + EE static/looping (sensor-gate-no-arrival, plan-fail) |

**Honest-eyes guarantee:** grades on RAW positions/contacts, never the controller's success flag; a cube in the wrong bin reads
MISROUTED (not "delivered"); a cube that never moved reads NOT_PICKED (not "0 displacement = success"). This is the no-false-
positive contract — the same correctness that makes the gate trustworthy.

**Implementation:** lift `scene_timeseries.py::_report` into a `data` handler; add a thin WHY-classifier layer mapping the existing
metrics → the taxonomy above (the rules are exactly the RCA logic used in the 2026-06-03 session). Register it; the function-gate
calls it instead of the standalone script. Effort: low (the metrics exist; it's wiring + the WHY-classifier). Validate by re-grading
the session's saved ts_*.json against the hand-RCA'd verdicts (CP-12 RODE_OFF_BELT, CP-09 COLLISION_DISTURBED, CP-13 GRASP_EJECT_
PLACE_BIAS, CP-50 DELIVERED_CLEAN×4) — they must match.

### 9.1 VALIDATED — WHY-classifier prototype works (2026-06-03 ~08:35)
Prototype `~/.isaac_qa/run/why_classify.py` (standalone, does NOT touch the production handler) implements the §9 WHY-taxonomy
purely from RAW positions/contacts in the saved time-series. Run on this session's ts_*.json, the WHY matched the hand-RCA exactly:
CP-50 4×DELIVERED_CLEAN, CP-19 6×DELIVERED_CLEAN, CP-47 2×DELIVERED_CLEAN, CP-12 Cube_3=RODE_OFF_BELT (conveyor-sync cause derived
from final_x-past-belt-exit + z-never-rose), CP-27 Cube_4=TOPPLED_IN_DEST. So the loop-closing tool is PROVEN implementable +
correct — the WHY is derived from data (honest-eyes contract), not the controller's self-report. Productizing = lift the metrics
from scene_timeseries._report + this classifier into a registered handler. Greenlight-ready.
