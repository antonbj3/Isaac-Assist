# Implementation Plan — Isaac Assist (checkable backlog)

**Consolidated 2026-06-10** — the v3/v4 delta sections are folded IN PLACE (each item below is the
corrected, current version; the old delta appendices are retired). Statuses reflect reality as of
consolidation. Strategy/rationale: `MASTER_EXECUTION_PLAN.md`. Research/doc index: local-only at
`docs/research/RESEARCH_INDEX.md` (git-ignored — internal research never ships).

Each item: ID, concrete task, files touched, done-when criterion, dependencies. **Order is by
dependency**; `∥` = parallel within a phase.
Convention: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (note why).

**Two tracks (formerly "Session A/B"):**
- **UR10 track** — owns P0-01..06 + the UR10 cluster (CP-69..86). Nobody else touches those files.
- **Foundation track** — everything UR10-independent: static_eyes/dual-verify (P1), honesty fixes
  (P0-18..20), toolify (P2). Does NOT wait for UR10 or the branch merge.
- Shared-working-tree rule: commit ONLY your own files (`git add <explicit>`, never `-A`/stash);
  branches push to the `anton` remote; master changes via PR (master is protected).

---

## PHASE 0 — Close the control spine + harden the foundation

### 0a. UR10 → N-of-M-stable 13/13 [UR10 track]
- [ ] **P0-01** CP-71 gravity-dispenser: items fall to floor before pick. *touches:* `handlers/robot.py` (create_gravity_dispenser), template. *done:* 3/3 fresh-Kit deliver.
- [ ] **P0-02** CP-73 conveyor gate-infra (504/timeout; robot delivers). *touches:* `gate_one.py`, template `duration_s`. *done:* gate returns a real verdict 3/3.
- [ ] **P0-03** CP-81/82 layout reach (primary cube y≈0.55 unreachable). *touches:* template `role_defaults` (move −y), `reach_validate.py`. *done:* reach_validate REACHABLE 3/3 + gate pass.
- [ ] **P0-04** CP-83 multi-cube low-z reach. *touches:* template, `_ur10_multicube_obs`. *done:* 3/3 deterministic.
- [ ] **P0-05** ∥ H7 swing: Anton GUI review of `_ur10_jointspace_transit`; decide default-ON scoped to far-pick (reach>0.85). *done:* decision recorded + flag set.
- [x] **P0-06** *(08f6b357 + batch: 18/18 delivery, 16/18 faithfulness — CP-71/CP-09 TS-fynd)* N-of-M re-validation harness for the 13-cluster (fresh-Kit per run). *touches:* `scripts/qa/`. *done:* one command → N-of-M verdicts for all 13.

### 0b. De-scope the fuzzy backends (honesty)
- [x] **P0-07** *(97c7f953)* Audit `motion_controllers.untested` tags across templates → report of declared-not-verified controllers.
- [x] **P0-08** *(97c7f953; 28 invisible templates got honest fields)* Mark untested tags `declared-not-verified` so retrieval/UI stop implying 15 working paths. *done:* only cuRobo+direct_joint read as verified.
- [ ] **P0-09** Retire templates STILL cortex-calling in the active set to `_retired/` on master. **NOT CP-73** (its Cortex layer is already removed — CP-73 is a P0-02 fix target; CP-72 already retired). *done:* no cortex-calling template in the active gate set.

### 0c. Branch re-convergence — port master→working. **Gates Phase 3 + 6 ONLY (not Phases 1-2).**
- [ ] **P0-10** ∥ Copy `relation_reasoning.py` (664 LOC) master→working. *done:* imports resolve, tests pass.
- [ ] **P0-11** ∥ Copy `asset_resolution.py` (408 LOC). *done:* `resolve_object_asset` importable.
- [ ] **P0-12** ∥ Copy `cosmos3_adapter.py` + `cosmos3_runtime.py`. *done:* imports resolve.
- [ ] **P0-13** ∥ Copy `mcp_floorplan_tools.py` (2898 LOC). *done:* MCP tools register.
- [ ] **P0-14** Hand-merge `instantiator.py` — the ONE real architectural conflict (master's reasoning-driven vs working's codegen). **SAFETY:** tag/backup working HEAD; gate the merged path behind a mode flag (mature `pick_place.py` stays DEFAULT); abort criterion; **EXIT = no UR10 13-cluster regression (N-of-M), not smoke.** Baseline named: `origin/master` (+243 from merge-base; working HEAD +1207). *done:* both paths present, flag-gated, 13-cluster green.
- [ ] **P0-15** Hand-merge `multimodal_handlers.py` — re-add the `asset_resolutions` payload. *done:* `/build` returns asset_resolutions.
- [ ] **P0-16** Smoke-test unified tree: `/canvas/build`, retrieval, `execute_template_canonical`, asset resolve. *needs:* P0-10..15.
- [ ] **P0-17** Agree merge cadence + catalog-of-record with Kimate. (Schema question is ANSWERED — his bundled catalogs match the resolver schema verbatim; remaining: cadence + ownership.) *done:* written agreement.

### 0d. Measurement-honesty fixes [Foundation track — unblocks everything downstream]
- [x] **P0-18** *(6154b88e — ported from Opus worktree after deep QC: wrong base, broken import, dup raycast all caught)* **Honest delivery gate** — `simulate_traversal_check` has THREE leniency holes making multi-item templates falsely-green: (a) one `target_path` → 2/3-way sorts unscorable (per-bin multi-target gate); (b) "AT LEAST ONE delivered = PASS" (picker-tote 6, dispenser 10, kitting) → completeness mode (N-of-M / all-required); (c) templates EXCLUDE the hard cube from `cube_paths` (inspector excludes the red reject cube) → lint that every declared workpiece is graded. *blast-6+, the #1 measurement gap. The 15 revalidate_falsely_green templates (PRUNE_AUDIT_VERDICT) re-gate on this.*
- [x] **P0-19** *(291cc659 ledger + 8ade3b04 backfill 228; X-10 per-run extras)* Structured `verified_status` — `{function_gate:{status,n,m,wilson_lower,last_run_sha}}` + re-validation ledger; "a merge re-gates the affected corpus" = a Phase-0 exit.
- [x] **P0-20** *(c43b79e1)* Version-control `/home/anton/.isaac_qa/run/scene_timeseries.py` into `scripts/qa/` (untracked today; the diagnose-loop substrate; invisible to a fresh checkout / Kimate).

---

## PHASE 1 — The verification ladder ★ [Foundation track — STARTED]

### 1a. Foundations
- [x] **P1-01** *(630ceca2 — all 60 classes populated, fallback emptied)* `height_m` on `object_palette.ObjectClass` — **field ADDED (2026-06-09)**; per-class values NOT yet populated (interim heights live in `_CLASS_HEIGHTS_M` fallback inside static_eyes — **two sources of truth, debt**: populate PALETTE, then shrink the fallback). *done-when:* every palette class has height_m set; fallback dict only covers true unknowns.

### 1b. static_eyes — **CORE BUILT + TESTED (2026-06-09/10)**
- [x] **P1-02** `Layout` input + `StaticEyesReport` output — `service/isaac_assist_service/multimodal/static_eyes.py`.
- [x] **P1-03..07** The checks: tiered reach-shell (gross-fail / comfortable-pass / **uncertain** below-base-z or near-radius), 3D-AABB interpenetration, support (rest/float/buried), fit, drop_in_container, occlusion (advisory), footprint/cell-bounds. Assembled over `ContactReachabilityValidator` + PALETTE, no Kit.
- [~] **P1-08** Machine-actionable fixes — `{action, path, constraint, suggest_position, human}` DONE + convergence proven by test. **Missing: an explicit per-check `confidence` float** (the `uncertain` status partially covers it; add for dual-verify integration).
- [x] **(tests)** `tests/test_static_eyes.py` — 6/6 l0 green (clean-PASS, out-of-reach+convergent-fix, clump, drop-miss, below-base→UNCERTAIN, reach_diagnostics shape).
- [x] **P1-09** *(c6041973 — live-smoked CP-70 2/2)* Tier-2 reach: thin wrapper shelling to `reach_validate.py` single-IK probe ONLY for the `uncertain` band (Kit+cuRobo, no settle; N-of-M). *coordinate Kit use with the UR10 track.*
- [x] **P1-10** *(36a8cfa8 — audit 0 ghosts)* Register `static_eyes` as an LLM-callable data tool. *touches:* `tool_schemas.py`, a handler, `no_handler_tools.json`. **CI: tools-resolve green + l0 — the gate hard-fails on a schema with no handler.**
- [x] **P1-11** *(4cec6f72)* Wire into `verifier_registry.py` form_gate — `reach_diagnostics()` already produces the `verify:reach` arg shape; fill the L336 stub. *done:* form_gate runs static_eyes.

### 1c. dual-verification
- [x] **P1-12** *(1f546414)* The 4 metric pairs (reach/delivery/support/geometry): static source, physics source, agreement band. *spec:* `docs/research/DUAL_VERIFICATION_SPEC.md` (local-only).
- [x] **P1-13** *(1f546414 — SKIP hard-gated behind calibration)* Skip-or-gate policy: PASS+high-conf→SKIP; PASS+low-conf→GATE; FAIL→REJECT. *done:* a `decide(report)→action` fn.
- [x] **P1-14** *(1f546414)* Fidelity-tier tagging (SYNTHETIC/INFERRED/ESTIMATED/MEASURED, weakest wins) on every verdict.
- [~] **P1-15** *(runner e5eecba6+1f830087; 20-template sweep RUNNING)* Calibration FIRST: both layers on the UR10-cluster + CP-NEW sample → per-pair confusion matrices → bands at the false-PASS percentile. *done:* `data/calibration/` versioned. **The ~3.5-4× reduction is a HYPOTHESIS this measures (collapses to ~1.9× under the reach-divergence finding) — P1-17 may not claim it before this runs.**
- [ ] **P1-16** N-of-M on disagreement (tier-dependent run counts).
- [ ] **P1-17** Measure the throughput win. *needs:* P1-15. *done:* a measured number.

### 1d. Relation edge — **LOAD-BEARING for the asset tier** (ABOM graph SKIPPED; this is a small typed field, not a graph)
- [x] **P1-18** *(d1c227cb)* `Relation` model `{type, from_id, to_id, category, reason, severity}` in `types.py`; retype `constraints`; version 1.0→1.1 **with a migration for existing specs**. (~40 LOC)
- [x] **P1-19** *(d1c227cb)* Validator rule (unknown-id + SEQUENCE cycle check). *touches:* `multimodal/validate.py`.
- [x] **P1-20** *(d1c227cb — relation fails route to geometry pair)* static_eyes verifies *declared* relations instead of guessing from geometry. *needs:* P1-08, P1-18.

---

## PHASE 2 — Toolify the body + close the diagnose loop

- [ ] **P2-01** Semantic-USD-diff verifier (byte-diff fails — baselines differ in API ordering/style; compare resolved prim graph + attrs with float tolerance). *done:* "same scene, different source text" reads equivalent.
- [x] **P2-02** ∥ `create_scene_baseline(...)` + `expand=True`. *(895d00ea)*
- [x] **P2-02b** **Build the `expand=True` codegen CONTRACT itself** — `chat/tools/expand.py`: `expand_tool_call` + `expand_sequence` (L1↔L2 rows). *(314d476e)*
- [x] **P2-03** ∥ `create_rigid_body_array(..., asset_ref=None)` + `expand=True` — primitive when asset_ref absent, add_reference when present; full verified physics stack (RB/Collision/Mass/PhysxRB + sleepThreshold=0 + material db) identical on both branches.
- [x] **P2-04** ∥ landed as explicit `bbox` arg on existing `compute_stack_placement` (no clone tool — one grid math): bbox supplied = pure no-Kit path for planning/asset-swap; absent = legacy live path unchanged. *(3d00164f)*
- [!] **P2-05** ∥ `setup_physics_callback(kind, params)` — **DESCOPED 2026-06-10 (evidence):** corpus scan found only 2 templates hand-rolling physics callbacks (the ISO-10218 safety pair), each a bespoke monitor body around a 2-line subscription idiom; callback machinery otherwise lives in handlers already. 2 instances ≠ the systemic-drift bar that justified P2-02..04 (~170-200 templates). Revisit if the safety-template family grows (then: kind='speed_separation'|'clearance_stop'|'custom').
- [x] **P2-06** *(0b119803 — live-validated on all 88 recorded artifacts; +DISPLACED_NOT_DELIVERED class + running-min pick detection from CP-71 findings)* `diagnose_task_outcome` — productize the (now-versioned, P0-20) `scene_timeseries.py::_report`. **Its real emitted states are ALOFT/FLUNG/TOPPLED/NOT_SEATED/ON_BELT/MISROUTED/...; the 5-name WHY-taxonomy (DELIVERED_CLEAN etc.) is a thin NEW classifier layer to build (only MISROUTED overlaps) — not free repackaging.** CI: handler + l0 tests. *needs:* P0-20.
- [ ] **P2-11b** CONTENT_DRIFT repair list (drift audit 2026-06-10): 27 templates where code_template builds a POORER scene than `code` declares (missing semantics/physics-materials/whole sensor+SDG pipelines — the kit-prep class; vision gates structurally cannot pass). Per template: regenerate ct from code (re-placeholder) OR retire ct. **4 are UR10-track (CP-65/67/73/83) — coordinate, do not touch.** 1 PARSE_FAIL. Tool: `scripts/qa/audit_code_template_drift.py` (lint-ready; CI-gate once drained).
- [ ] **P2-11** Sensor→controller routing bridge — sorts secretly route off the USD-Semantics oracle (sensors decorative, blast-4); wire a real runtime sensor-read → controller route.
- [x] **P2-07..09** Migrate the base clusters, semantic-diff verified each. **88/90 DONE in 4 waves (… + 05d0b9b3 deterministic-build mode: timeline-stop+ticks + writeback-exclusion, CP-52 self-diff 62→0). 2 principled deferrals: CP-68 (runtime belt-velocity toggle), CP-NEW-kit-prep-vision-gate (UNSEEDED random SKU semantics — template reproducibility defect, own finding). Was: 79/89 in 3 waves (0c08bed3, 140f07a2, 5d97a25c) — every migration proven ZERO_DELTA vs final emission. 6 tool/diff/harness corrections driven by the diff; zombie-Kit VRAM-starvation class found+fixed. Remaining 10: the multi-robot/belt family whose builds are NONDETERMINISTIC (CP-52 self-diff proof: 62 runtime-state attrs vary build-to-build) — needs a deterministic-build harness mode (stop timeline pre-export), then the same driver.**
- [x] **P2-10** Re-gate migrated bases. **8-template sample PASS (2026-06-10 kväll/natt): CP-01/03/13/22/46/52/66/09 — all gates green; every TS profile matches its pre-migration baseline incl the known defects (CP-52 dual-arm topples, CP-09 tower) = no behavioral delta. Combined with 89/89 ZERO_DELTA (construction-safe), P2-10's no-regression criterion is met; full-corpus re-gate intentionally NOT run (the verification model makes it redundant).**

---

## PHASE 3 — The asset bridge (GO/NO-GO on the asset tier) — *gated on 0c*

- [ ] **P3-10** Mount Kimate's package — `ASSETS_ROOT_PATH=/home/anton/kimate_assets/assets` (symlink; keep the NVIDIA mount). One-pass prep: merge the 10 bundled `asset_catalog.json` + localize dead `/home/kimate/...` `usd_path` (`relative_path` is the portable key). Schema adopted verbatim (verified matching).
- [ ] **P3-01** ∥ Catalog generator for the 176GB NVIDIA mount → same schema. *done:* Props/Warehouse/Robots/Environments covered.
- [ ] **P3-03..05** ∥ Wire `asset_resolution` behind `create_bin` / `create_conveyor` / `create_rigid_body_array` (name in, real USD out, path hidden from the LLM). *needs:* P0-11.
- [ ] **P3-06** bbox-derived layout: derive drop_target/grasp from the resolved bbox, not hardcoded. *needs:* P1-01.
- [ ] **P3-13** Relational propagation for the asset-swap CASCADE: a resolved bbox shifts an anchor → re-derive dependents through the Relation graph (graft onto Kimate's `relation_reasoning.py`, don't duplicate); static_eyes verifies; on conflict FLAG for the LLM. *needs:* P1-18, P1-20. *Sufficient for T1-T5.*
- [ ] **P3-11** Belt-control standalone (`set_conveyor_velocity`/`pause_conveyor`, blast-6, S) + `attach_payload` (S) — cheap front-loaded wins.
- [ ] **P3-07** Asset-pilot = **WP-02 cracker-box** (lowest-risk real-mesh; de-risks the 19-strong T6 wave). *needs:* P3-10/P3-03/P3-06.
- [ ] **P3-08** ★ GO/NO-GO: can honest-eyes grade a real-mesh grip? (Pull a cheap spike of this EARLY — before Phase 3 if possible.) *done:* recorded verdict; NO → asset tier blocked, surface to Anton.
- [ ] **P3-09** ★ GO/NO-GO: compliant suction grip on a real mesh? *done:* recorded verdict.

---

## PHASE 4 — Composition + the DECOMPOSE/SELECT lever

- [ ] **P4-02** ★ **DECOMPOSE/SELECT go/no-go FIRST (before plumbing).** SELECTION/DECOMPOSE eval: composed specs → multiple canonicals + hard-negatives, scored via `direct_eval.py`. **DoD = ≥X% correct decomposition on a held-out set.** Model can't decompose → model-capability finding (tie to X-03), not plumbing.
- [ ] **P4-01** Composition-IR (cells + offsets + inter-cell relations). *specs:* `TRACED_FLOW_COMPLEX_SCENE.md`, `COMPOSITION_AND_BRANCH_AUDIT.md`.
- [ ] **P4-03** Namespace rewrite per instance (reuse role-substitution + `_extract_prim_paths`). *done:* no prim-path collisions between 2 templates.
- [ ] **P4-04** Per-instance `origin_offset`.
- [ ] **P4-05** Controller isolation (distinct `phase_id`/robot paths; per-robot+phase sub keys don't clobber).
- [ ] **P4-06** ONE deferred `world.reset()` (templates currently reset+re-seed each → races).
- [ ] **P4-07** `compose_and_build` wrapper. *needs:* P4-03..06. CI: handler + l0.
- [ ] **P4-08** Inter-cell static checks via the Relation edge (AMR route clear, handoff pose-equality). *needs:* P1-20.
- [ ] **P4-09** Integration gate — physics-verify the composed scene (multi-callback contention = the CP-52 mutex root generalized; ONLY physics reveals it; dual-verify cannot skip this one).
- [ ] **P4-10** Per-cell isolate-rebuild (fix cell B without re-running A/C). *done:* a stage-checkpoint mechanism.
- [ ] **P4-11** Multi-robot mutex/handoff track (CP-51/52/53/65) — **promoted ahead of its dependents; T5/T7 + composition block on it.**
- [ ] **P4-12** 2-cell composition end-to-end. *needs:* P4-07, P4-09.
- [ ] **P4-13** (PORT-WHEN-TRIGGERED) Internal constraint-layout SOLVER port for automatic cascade re-arrangement. **TRIGGER: static_eyes reports cascade conflicts on T6-T7 scenes that P3-13 propagation + LLM-fix can't resolve cheaply, frequently enough to warrant automation.** Sources + full port detail live in local research notes (`docs/research/`, git-ignored — internal; see the local RESEARCH_INDEX). Deferred because: conflict frequency unknown; the solver's 2D→3D mapping is UNPROVEN; it overlaps static_eyes (adds only the SOLVE step). Captured fully so the trigger is the memory.

---

## PHASE 5 — The robot + complexity ladder (gap-weighted corpus)

### 5a. Capability tools
- [ ] **P5-01** Local SAM2/CLIP vision (unblocks 4 roles; kills the Gemini-quota constraint).
- [ ] **P5-02** `setup_insertion_controller(strategy=spiral|helical|snap_fit|bayonet)` via **WP-08 peg-in-hole** (cheapest high-value; unifies 4 hand-coded gestures).
- [ ] **P5-03** Mobile-manip composite (`setup_amr_with_manipulator` + `mobile_manipulation_plan`) via **WH-MM-05**.
- [ ] **P5-04** ∥ 3-finger adaptive grasp via **WP-10 Allegro Rubik**.
- [ ] **P5-05** Faithful suction (compliant mount, no kinematic-teleport oracle) — research, Anton's call.
- [ ] **P5-06** Widen `_reach_probe_extra_paths` to inner targets (reject bin / chuck / post-nav pallet — the cross-cutting blind spot).
- [ ] **P5-18** YCB/mesh loader (none exists — "pick YCB items" is literally unsatisfiable today).

### 5b. Missing controller + GATE classes (EC-1..14, `E2E_GAP_FINDINGS.md`) — **build the PAIR, never the controller alone**
- [ ] **P5-19** **EC-1: articulated-joint manipulation as a CATEGORY** — revolute-door, prismatic-drawer, axial-twist-knob (wrist-roll, ~zero XYZ), nested-fridge (door→prismatic-shelf→moving-frame place), reach-into-cavity-extract (withdraw leg). Drive PASSIVE joints by contact force, not teleport. `articulated_pull.py` was never built though the Phase-70c kernel exists. + swept-arc/clearance pre-filter for static_eyes. **PREREQ for P5-16.**
- [ ] **P5-22** **The cheap gate classes (highest ROI):** `verify_articulation` pre-flight (S), `articulation_angle` joint-state gate (M), `pattern_hint`-based gate-verdict dispatch (S→M) — de-falses flip/twist/seat/coverage/tool-swap at once. *(Complementary to P0-18: P0-18 fixes the delivery-gate's holes; P5-22 adds verdict classes for NEW verbs.)*
- [ ] **P5-23** EC-3 continuous surface-process: path-follow controller + path-integral COVERAGE gate + TCP recorder (weld/paint/deburr/polish/cut — 10+ families; the torque bridge is the gap).
- [ ] **P5-24** EC-4 force/torque-terminated actuation (screw/snap/press — 8+ families; **the discrete-joint half is buildable in pure PhysX TODAY**).
- [ ] **P5-25** EC rest: deformable/1D-DLO grasp-follow + connector mate-gate; grip-preserving reorient + orientation gate; tool-changer swap + which-tool-mounted gate; HRC human-tracking + speed-separation gate; quadruped locomotion runtime.
- [ ] **P5-20** Navigation function-gate (`verify_amr_at_goal`) — the AMR nav leg is UNGRADED today. + fleet coordinator for T7.
- [ ] **P5-21** Env-fit gate (`place_cell_in_environment`) — dropping a cell into a real env USD has no collision/fit validation (cuRobo ingests only AABB cuboids).

### 5c. Robot rungs + domains
- [ ] **P5-07** Multi-arm handoff canonicals. *needs:* P4-11.
- [ ] **P5-08** Carter/AMR nav+logistics canonicals. *needs:* P5-20.
- [ ] **P5-09** Mobile-manip canonicals. *needs:* P5-03.
- [ ] **P5-10** Humanoid G1 bimanual (Kimate's CAD parts are buildable source, NOT a SimReady drop-in — Nucleus-G1 dependency stands).
- [ ] **P5-16** `service/domestic` domain (open-drawer / load-dishwasher / fetch-from-fridge — 243 articulated appliances + interactive kitchens). *needs:* P5-19, P5-22.
- [!] **P5-17** `datacenter` domain — **BLOCKED: `Datacenter_NVD` is materials-only, ZERO server/rack/port geometry. Source assets first.**

### 5d. Corpus growth + retrieval
- [ ] **P5-11** `variants.spec` schema + Cartesian generator (≤15 bases, ≤500 children/wave; bases re-pass function gate; variants form-gate + sampled function-gate + dual-verify). *spec:* `CANONICAL_TAXONOMY.md §4`.
- [ ] **P5-12** Author the T2-T7 bases, gap-weighted (the defensible slice; 66-template backlog placed T1=12..T7=7 in `ASSET_TEMPLATE_BACKLOG.md`). SATURATED rows: 1 REF, generator-only expansion.
- [ ] **P5-13** ∥ Grow `retrieval_eval_set.json` 33→200 (SE+EN). *start early.*
- [ ] **P5-15** Retrieval DoD — **rescoped:** production single-template retrieval is ALREADY semantic ChromaDB (hit@1 0.84, past 0.7); do NOT "upgrade Jaccard" (`role_retriever` is an unused side-path). The DoD is **composed-spec cell selection + hard-negative rejection** on a multi-canonical eval set. `index_card.defends` is on 0/440 — populate first if used for ranking. *(replaces old P5-14.)*

---

## PHASE 6 — The product loop

- [ ] **P6-01** Activate sketch/photo intake (bind `vision_real_gemini.py` to `from_sketch`/`from_photo` — pre-wired, 0 callers). *done:* image → LayoutSpec over HTTP.
- [ ] **P6-02** ∥ Voice intake (STT → text → LayoutSpec).
- [ ] **P6-03** Cosmos perception → LayoutSpec → static_eyes. *needs:* 0c merge.
- [ ] **P6-07** **Chat/canvas unify** — production chat hard-instantiates from authored `role_defaults` (Role-3 binding NEVER fires; `orchestrator.py:1031` passes no `role_bindings`); the rich layout loop is canvas-only. Wire ONE Bridge-1 path (orchestrator passes role_bindings; `apply_layout_spec_to_scene` calls the same path as `routes.py:488`). Needs a geometry-bearing LayoutSpec on the chat side. Replace the flat-2D `query_layout_metric` with the static_eyes verdict.
- [ ] **P6-04** Full closed loop: perceive → retrieve → decompose → compose → static_eyes → build(assets) → dual-verify → diagnose. *needs:* Phases 1-4.
- [ ] **P6-05** Self-correction: on diagnose failure the LLM re-plans (swap canonical / move pick / re-grade) without a human.
- [ ] **P6-06** North-Star acceptance: "3-cell warehouse…" → verified multi-cell scene + passing decompose/select eval.

---

## Cross-cutting tracks

- [ ] **X-01** Throughput: baseline = `simulate_args.duration_s` median **90s** (not 180s). The `*_with_restart.py` harnesses do BATCH restart — build a genuine per-run harness (~100s Kit-boot budget) or adopt honest N-of-M batch-averaging. **BREV/multi-Kit REQUIRES a rented A100/H100 MIG (cost line)** — local multi-Kit is a measured 2.4-2.7× SLOWDOWN.
- [ ] **X-02** Persist L1 (tool-seq) + L2 (`expand=True` USD; *needs P2-02b*) + L3 (gate+eyes outcome) per template+run; extend `turn_recorder.py` (only L1 captured today), versioned JSONL.
- [ ] **X-03** Fine-tune export pipeline (README §9.4) consumes L1/L2/L3 → local Nemotron/qwen model.
- [ ] **X-04** Kimate integration: catalog-of-record, Cosmos/resolver merges, branch cadence.
- [ ] **X-05** Inert-tool audit — tools that author USD / accept args but have NO runtime behavior (`create_bin` codegen-only, `configure_camera`, `barcode_reader_sensor`, `register_moving_obstacle`, `sim_control`). Inventory → wire runtime OR mark `authoring-only` honestly.
- [ ] **X-06** Per-template SIM2REAL tag (2nd fidelity axis, distinct from measurement tier): faithful-grip? sensor-vs-oracle? real-mesh? authored maxForce? (maxForce gap is concrete: handler hard-codes stiff/damping, no maxForce → heavy parts don't grip.) Tie to T0-T6 + `measure_sim_real_gap`.
- [ ] **X-07** Synthetic `scripted_demonstrator`/`teleop_mock` (EC-14, M) + `actions`-schema fix — unblocks GR00T/imitation HARDWARE-FREE; builds the LeRobot-v2 `actions` slot a future mocap intake writes into. **Markerless mocap (MAMMA) = WATCH-ITEM — REINFORCED 2026-06-10: MAMMA's license explicitly forbids commercial use (incl. training on its synthetic dataset), and the leading mocap vendor was acquired (single-cam product ≠ MAMMA replacement). A license-clean commercial stack exists at 25-40mm accuracy (mapped in local research).**, deferred to the G1 rung.
- [ ] **X-09 Platform track (added 2026-06-10; conductor-QC'd 2026-06-10 eve — the research UNDERSTATED the true cost):**
  (a) **Import-surface port to Kit 110 = genuinely small** (QC-verified: 287 `isaacsim.*` refs already done — not the claimed ~450; real legacy ≈ 5 imports: diagnostics.py L4302/4327 (research's L4249/4274 moved by P0-18), 2 friction_paradigm scripts, launch_isaac.sh ext-names; `exts/isaac_6.0` exists).
  (b) **⛔ FULL runtime upgrade is NOT "days" — it is BLOCKED until two preconditions hold** (this is the remembered reason we never upgraded): (1) **cuRobo-on-6.0 compatibility verified** — we run pip `isaacsim-5.1.0.0` + `curobo-0.2` + the hand-built Warp-1.11 symlink chain (extscache→isaacsim/warp→site-packages), which a 6.0 install breaks by construction; cuRobo's Isaac support lags releases; (2) **a budgeted re-validation of the verified corpus** — PhysX behavior shifts between majors → all 52 verified templates + the 5.1-tuned workarounds (suction raycast, maxForce, settle tunings) decay to unmeasured (the verification ledger exists for exactly this). Treat as: import-port whenever convenient; runtime upgrade = its own gated project with go/no-go on (1).
  (c) **DECISION (protocolled): do NOT port to cuMotion/Motion Generation API now** — 6.0 integration Experimental, proprietary C++ rewrite (Isaac ROS license; raw cuRobo = Apache 2.0), batch-IK/MPPI/collision-sphere parity missing — and (b)(1) makes the cuRobo coupling argument STRONGER. **Re-evaluate at 6.1.**
- [ ] **P2-12** WorldBinding-style auto-sync USD→cuRobo collision world — generalizes `_ur10_multicube_obs`: sync scene transforms/obstacles into the planner's collision world automatically (steal the 6.0 WorldBinding *pattern*, not the dependency). **Structurally kills the stale-world bug class** (CP-83's STALE-WORLD sig was exactly this). ⚠️ Touches `pick_place.py` = UR10-track files → coordinate + full 13-cluster N-of-M regression required. *Phase 0/2 boundary.*
- [x] **P2-13** *(docs/notes/CONTROLLER_BACKEND_CONTRACT.md, 2026-06-10 natt)* Controller-backend CONTRACT SPEC (design-first, NO refactor) — the 10 `target_source` variants are string-dispatched codegen generators (`pick_place.py:293`), not runtime objects, so a MotionPolicy-style ABC is a category shift. Step 1 = a written interface contract (get_active_joints / compute_targets / update_world / set_base_pose equivalents at the codegen level + what each backend guarantees); ONLY then decide whether a thin runtime wrapper earns its keep. This is the stated PREREQ for the GR00T-runtime architectural call + a future Motion-Gen-API adapter (6.1) + per-backend `motion_controllers` honesty.
- [x] **X-10** Per-run verdict log (delta on P0-19) — `record_gate_run(extras=...)` now carries per-RUN training-grade context (`verdict_vector`, `snapshot_hash`, `gate_score`, `kit_session_age_s` — degradation-poisoned rows become distrustable). Typed verdicts beat raw logs for future verdict→fix dispatch/auto-repair. *Done 2026-06-10, 7/7 l0.*
- [ ] **X-08 ROS2** (from `ROS2_STRATEGY.md`): (a) promote ROS2 to a NAMED production backend with its own verification tier, SYNTHETIC-tagged until proven, OFF the critical path; (b) close the `ros2_cmd` loop (compiles but never wires command→motion; 0 ROS2 templates pass a physics gate — graded structurally with `simulate_args:null`) via a mock-node → `simulate_traversal_check` function-gate; (c) real-robot driver/recorder layer + the rclpy ABI fix (humble cp311 vs Kit 3.10). *(REAL today: 4 OmniGraph profiles, clock/QoS/TF/diagnose, Modbus-TCP, `measure_sim_real_gap`.)* *2026-06-10: ISO 10218:2025 leaves AI/LLM validation unaddressed → the deterministic template+gate contract is certification-valuable; strengthens this positioning.*

---

## Changelog
- **2026-06-09:** v1 plan → adversarial review (46 confirmed findings) → v3 (10 must-fixes) → v4 deltas (sequence/gap-batch/ROS2/mocap/sim2real fold-in).
- **2026-06-10:** consolidation — deltas folded in place; statuses updated (static_eyes core BUILT, 6/6 l0; height_m field added); session labels → tracks; P5-17 marked blocked; P5-14 retired into P5-15; ROS2 items consolidated to X-08.

## How to use this
- Pick the lowest-numbered unblocked item in your track. Foundation track's current head: **P1-09/P1-10/P1-11** (finish static_eyes integration) + **P0-18..20** (honesty fixes) + **P1-12..15** (dual-verify).
- Done = the *done:* criterion met AND (control-touching) fresh-Kit N-of-M survives AND (new tools) tools-resolve CI green.
- Update the checkbox + leave a one-line note (commit sha / verdict) — the backlog is an honest record.
