# Master Execution Plan — Isaac Assist

**Converged 2026-06-09, consolidated 2026-06-10.** Bakes in: the adversarial review's 10 must-fixes,
Kimate's asset package (two new domains + Phase-3 de-risk), the assets/e2e/tool-gap pass, the gap-batch
EC-classes, ROS2/mocap/sim2real, and the chat/canvas-unify finding. Schedulable: phases are
dependency-gated and the parallel-track reality is encoded. **The checkable backlog lives in
`IMPLEMENTATION_PLAN.md`; the full research/doc index is local-only at `docs/research/RESEARCH_INDEX.md`
(git-ignored — internal research never ships).**

## North Star
A user gives a high-level spec ("a 3-cell warehouse: UR10 palletizing, Franka kitting, Carter AMR between them")
and the system **perceives → retrieves → DECOMPOSES → composes → static-checks → builds (real assets) →
dual-verifies → diagnoses → iterates** until every robot provably completes its task. The corpus is both the
retrieval substrate and the training substrate.

## Parallelization map (two tracks)
- **UR10 track: UR10 → 13/13 (Phase 0.1).** Owns the UR10 cluster CP-69/70/71/73/75/79/80/81/82/83/84/85/86 and its files (`pick_place.py`, `gate_one.py`, `scene_eyes.py`…). Do not duplicate or archive these.
- **Foundation track: everything UR10-independent** — `static_eyes` (Phase 1, **core BUILT + 6/6 l0 tested 2026-06-10**), dual-verify, the measurement-honesty fixes (0.4), toolify (Phase 2). NOT blocked by UR10 or the branch merge (review-verified).
- **Branch re-convergence (Phase 0.3) gates ONLY Phase 3 (asset-resolution wiring) + Phase 6 (Cosmos)** — NOT Phases 1-2.
- **Shared-working-tree rule:** the two tracks share one git index — commit only your own files (never `git add -A`/stash); branches → the `anton` remote; master changes via PR (master is protected; Anton has write).

## Cross-cutting principles
- **Verification ladder:** form-gate → **static_eyes (cheap, no Kit)** → **dual-verify** → function-gate (physics) → diagnose.
- **Two tiers coexist:** primitives verify CONTROL; assets add REALISM. Build assets ON TOP, never convert.
- **Fidelity-tag every verdict** (SYNTHETIC/INFERRED/ESTIMATED/MEASURED, weakest wins). A "pass" declares cheap-estimated vs physics-proven.
- **Keep both code levels** (`expand=True` — to be BUILT, it does not exist yet): L1 tool-seq + L2 raw USD + L3 outcome = training data.
- **Build toward the measured gaps** (suction-thin, 3-finger-absent, reorient-thin, mobile-manip-absent, real-asset-absent, service/datacenter-new), not the saturated Franka-cube center.
- **Flag architectural calls, don't grind** (faithful suction, multi-robot mutex, GR00T runtime).
- **Measurement honesty is a feature:** several "verified" templates are falsely-green (sorts route off the USD-Semantics oracle, sensors decorative; multi-way sorts are structurally unscorable by the single-target gate). Fixing the gate is Phase-0/1 work, not optional.
- **★ Controller and gate come in PAIRS** (gap-batch's sharpest finding): the project keeps building a CONTROLLER for a new capability but never the matching GATE CLASS, so the delivery-XY gate silently green-passes a task (flip / twist / seat / coverage / tool-swap / door-open) that never physically happened. Every new controller class ships with its verdict class. The cheapest high-ROI wins are the missing gate classes themselves (`verify_articulation`, `articulation_angle`, a `pattern_hint`-based gate-verdict dispatch) — they de-false many families at once.
- **★ Two ORTHOGONAL fidelity axes — never conflate them:** (a) MEASUREMENT fidelity = how it was verified (static estimate → physics, the SYNTHETIC→MEASURED tiers); (b) SIM2REAL fidelity = how faithful the physics itself is to reality (faithful grip? real sensor vs oracle? real mesh vs cube? authored maxForce?). A template can be MEASURED-in-physics and STILL have a large sim2real gap (weld-grip, oracle-sensor). Minimizing sim2real is first-class — it's gated by the existing T0-T6 tiers + `measure_sim_real_gap`, and it matters extra because the corpus is TRAINING DATA (sim-faithful transfers; sim-isms don't). Tag every template on BOTH axes.

---

# THE SEQUENCE

## PHASE 0 — Close the control spine + harden the foundation
0.1 **[Session A] UR10 → N-of-M-stable 13/13.** Roots: CP-71 (gravity dispenser), CP-73 (conveyor gate-infra), CP-81/82 (layout reach), CP-83 (multi-cube). H7 swing: Anton GUI review → default-ON scoped to far-pick.
0.2 **De-scope the fuzzy backends.** Mark the ~11 untested `motion_controllers` tags `declared-not-verified`. Retire templates that are STILL cortex-tagged in the active set (NOT CP-73 — its Cortex layer was already removed; CP-73 is a fix target under 0.1, not a retire target).
0.3 **Branch re-convergence (gates Phase 3 + 6 ONLY).** Port master→working: 5 clean-add modules (`relation_reasoning.py`, `asset_resolution.py`, `cosmos3_adapter/runtime`, `mcp_floorplan_tools.py`); hand-merge `instantiator.py` + `multimodal_handlers.py`. **SAFETY (required):** tag/backup working HEAD; gate the merged `instantiator.py` behind a mode flag so the mature `pick_place.py` path stays DEFAULT until the reasoning path re-passes the UR10 13-cluster + conveyor_pick_place; define an abort criterion; EXIT gate = no 13-cluster regression (N-of-M), not smoke. Name the baseline: `origin/master` (+243 from merge-base; working HEAD +1207). Coordinate cadence with Kimate.
0.4 **Measurement-honesty fixes (unblock everything downstream):**
  - **Honest delivery gate (P0-18, three holes)** — `simulate_traversal_check`: (a) one `target_path` → multi-way sorts unscorable (per-bin gate); (b) "at least ONE delivered = PASS" on multi-item templates → completeness mode; (c) templates exclude the hard cube from `cube_paths` → lint that every declared workpiece is graded. (#1 measurement gap; the 15 falsely-green re-gate on this.)
  - **Structured `verified_status`** — replace free-text prose with a machine-readable `{function_gate:{status,n,m,wilson_lower,last_run_sha}}` so the DoD is queryable and decays are visible. Add a re-validation ledger + "a merge re-gates the affected corpus" exit.
  - **Version-control `scene_timeseries.py`** into `scripts/qa/` (currently in `~/.isaac_qa/run/`, untracked, invisible to a fresh checkout / to Kimate). It is the diagnose-loop substrate.

## PHASE 1 — The verification ladder ★ (Session B starts NOW, parallel to UR10)
1.1 Add `height_m` to `object_palette.ObjectClass`.
1.2 **`static_eyes`** — assemble over existing pure-Python validators (`spawn_validator_contact_reachability.py`, `sub_phase_72c_blueprint_validator.py`, `scene_validate.py`). Each check → `(status, confidence, reason, fix.suggest_position)`. Tiered reachability (free shell → uncertain band → live single-IK probe). **Register as an LLM-callable tool** (it is only a script today — blast-6 gap). **CI: add the schema + handler + l0 tests so the tools-resolve gate stays green** (it hard-fails the build on a schema with no handler).
1.3 **dual-verification** — 4 metric pairs (reach/delivery/support/geometry); skip-or-gate policy; fidelity tiers; calibrate divergence bands on the UR10-cluster + CP-NEW sample. **The ~3.5-4× gate-reduction is a HYPOTHESIS the calibration MEASURES (P1-15) before P1-17 claims it** (collapses to ~1.9× under the spec's reach-divergence finding).
1.4 **Relation edge** on LayoutSpec (typed `{type,from,to,category,reason,severity}`, ~40 LOC; ABOM graph SKIPPED). With a 1.0→1.1 migration for existing specs. **LOAD-BEARING for the asset tier (NOT optional):** asset-swap changes an object's real dimensions, which CASCADES to everything positioned relative to it (drop_target, robot reach, feeding conveyor, neighbor clearance, workpiece fit). Hardcoded absolute positions — and even per-object bbox reads — can't propagate that. Positions must be RELATIONAL (`drop_target above bin.opening`, `conveyor.end feeds bin`, `bin_2 beside bin_1`) so dependents RE-DERIVE when an anchor's bbox resolves. **Phase 3 depends on this.**

## PHASE 2 — Toolify the body + close the diagnose loop
2.1 **Semantic-USD-diff verifier** (byte-diff fails — baselines differ in API ordering; compare resolved prim graph + attr values, float tolerance).
2.2 The 4 body tools + **build the `expand=True` contract** (0 in code today — it must be built, not assumed): `create_scene_baseline`, `create_rigid_body_array(asset_ref)`, `compute_palletizer_grid(bbox)`, `setup_physics_callback`.
2.3 **`diagnose_task_outcome`** — productize the now-versioned `scene_timeseries.py::_report`. Its real emitted states are ALOFT/FLUNG/TOPPLED/NOT_SEATED/MISROUTED/...; the 5-name WHY-taxonomy (DELIVERED_CLEAN/...) is a THIN NEW classifier layer to build (only MISROUTED overlaps), not free repackaging. CI: register handler + l0 tests.
2.4 **Sensor→controller routing bridge** — today all sorts secretly route off the USD-Semantics oracle (sensors decorative, blast-4). Wire a real runtime sensor-read → controller route.
2.5 Migrate the ~15 base templates (semantic-diff verified). Bases first.

## PHASE 3 — The asset bridge (pulled FORWARD by Kimate's package)
3.1 **Mount Kimate's package** — `ASSETS_ROOT_PATH=/home/anton/kimate_assets/assets` (symlink, keep the NVIDIA mount live too). One-pass prep: merge the 10 bundled `asset_catalog.json` files + localize the absolute `usd_path` (dead `/home/kimate/...` paths; `relative_path` is the portable key). The bundled schema `{name,usd_path,relative_path,category,tags}` IS the resolver's schema — adopt verbatim; sync with Kimate that this is the catalog of record.
3.2 Wire `asset_resolution` behind `create_bin`/`create_conveyor`/`create_rigid_body_array` (name in, real USD out). **bbox-derived layout WITH cascade propagation:** resolve each asset's real bbox → propagate through the Relation graph (1.4) so dependent positions (drop_target/reach/feed/neighbors) re-derive → static_eyes verifies the whole scene → if the cascade conflicts (resized object collides a neighbor or falls out of reach), run a RE-ARRANGE pass. **Port candidate: a prior internal constraint-layout solver (stress-majorization placement + hard non-overlap projection + a feasibility oracle)** — exactly this relational-placement-under-constraints machinery already exists in-house, not greenfield. Full port details in local research notes (`docs/research/`, git-ignored — internal, never shipped).
3.3 **Belt-control standalone tools** (`set_conveyor_velocity`/`pause_conveyor`, blast-6, S) + **`attach_payload`** (S) — cheap front-loaded wins.
3.4 **Asset-pilot = WP-02 cracker-box** (the lowest-risk real-mesh pilot; de-risks the 19-strong T6 wave). **GO/NO-GO: can honest-eyes grade a real-mesh grip (+ compliant suction)?** Pull a cheap version of this spike to Phase 0/1. If NO → the asset tier is blocked; surface to Anton.

## PHASE 4 — Composition + the DECOMPOSE/SELECT lever (the user's core concern)
4.1 **★ DECOMPOSE/SELECT measurement FIRST (a go/no-go BEFORE plumbing).** The hard part is the LLM choosing+combining the right canonicals, not the plumbing. Build a SELECTION/DECOMPOSE eval: prompts mapping to MULTIPLE canonicals (3-cell → [palletizer,kitting,amr]) + hard-negative near-misses, scored on decompose-correctness + per-step tool-chain via `direct_eval.py`. **P4-02 DoD = ≥X% correct decomposition on a held-out composed-spec set.** If the model can't decompose, that's a model-capability finding (tie to X-03 fine-tune), not a plumbing task. (Note: production template-retrieval is ALREADY semantic ChromaDB at hit@1 0.84 — the gap is composed-spec SELECTION, not single-template retrieval.)
4.2 **Composition mechanism (~600 LOC, AFTER 4.1 passes):** namespace per-instance subtree + `origin_offset` + controller isolation (per-instance phase_id/robot paths) + one DEFERRED `world.reset()`. `compose_scene` + `sub_stages` (blast-3, L — the biggest build).
4.3 Inter-cell static checks via the Relation edge (route clear, handoff pose-equality).
4.4 **Integration gate (cannot be skipped)** — multiple physics callbacks = the CP-52 mutex root generalized; only physics reveals it.
4.5 **Multi-robot mutex/handoff = its own gated track, promoted ahead of its dependents** (CP-51/52/53/65). T5/T7 + composition explicitly block on it.

## PHASE 5 — The robot + complexity ladder (the corpus, gap-weighted)
5.1 **Capability tools (ASSET_TEMPLATE_BACKLOG priority):** `setup_insertion_controller(strategy)` via **WP-08 peg-in-hole** (cheapest, one bridge unblocks 4); **`setup_amr_with_manipulator`** via **WH-MM-05** (fills the absent mobile-manip axis, retro-promotes 2); multi-finger grasp via **WP-10 Allegro Rubik** (fills absent 3-finger axis); local SAM2/CLIP vision; **YCB/mesh loader** (no loader exists — "pick YCB items" is literally unsatisfiable today); faithful suction (research). Widen `_reach_probe_extra_paths` to inner targets (reject bin/chuck/post-nav pallet — cross-cutting blind spot).
5.1b **★ MISSING CONTROLLER + GATE CLASSES (gap-batch EC-1..EC-14 — `E2E_GAP_FINDINGS.md`).** Pick-place breaks on whole CATEGORIES, each needing a controller class AND a matching gate class: **EC-1 articulated-joint manipulation** (revolute-door / prismatic-drawer / axial-twist-knob / nested-fridge / reach-into-cavity-extract — gates 6+ families + Kimate's 243 appliances; the `articulated_pull.py` handler was never built though the kernel exists) + the gates `verify_articulation`(S), `articulation_angle`(M); **EC-3 continuous surface-process** (path-follow + path-integral coverage gate + TCP recorder — gates 10+ families: weld/paint/deburr/polish/cut); **EC-4 force/torque-terminated actuation** (fastening — 8+ families; the discrete-joint half is buildable in pure PhysX TODAY); deformable/1D-DLO grasp-follow (cable); grip-preserving reorient + orientation gate. Build the controller+gate PAIR, never the controller alone. These gate the service/domestic + assembly + dexterous tracks.
5.2 **Robot rungs:** multi-arm → Carter/AMR → mobile-manip → humanoid (G1 CAD parts are buildable source, NOT a SimReady drop-in — Nucleus-G1 dependency stands) → quadruped (8 terrains from Kimate's pack unblock legged-nav).
5.3 **NEW domains from Kimate's package** (impossible on the industrial-only mount): **`service/domestic`** (open-drawer, load-dishwasher, fetch-from-fridge — 243 articulated appliances + interactive kitchens) and **`datacenter`** (rack-and-stack, cable routing, server swap) — **⚠️ BLOCKED: `Datacenter_NVD` in Kimate's package is materials-only, ZERO server/rack/port geometry; this domain needs assets sourced before it can be built.** Add to the taxonomy as deferred. Plus HRC/ergonomics (the cataloged `Worker` actor) and teleop→imitation-learning (the kitchen-teleop scene). **★ PREREQUISITE: an articulated-mechanism controller (revolute/prismatic-pull).** Pick-place fundamentally breaks on doors/drawers (the humanoid-cabinet trace: the state machine LIFTS the door instead of swinging the hinge). All 243 articulated appliances hit this — the service/domestic domain cannot work without this controller class (P5-19). Also gap-gated: a navigation function-gate (the AMR nav leg is ungraded today) and an env-fit gate (dropping a cell into a real environment USD has no collision/fit validation).
5.4 **Complexity ladder T1→T7** via `variants.spec` Cartesian expansion (≤15 bases, ≤500 children/wave; bases re-pass the function gate, variants form-gate + sampled function-gate + dual-verify). 66-template backlog already placed T1=12/T2=14/T3=9/T4=5/T5=4/T6=17/T7=7. SATURATED rows (RG-A01/02/03) = keep 1 REF, expand only via the generator.
5.5 **Retrieval (rescoped):** production is already semantic ChromaDB (hit@1 0.84, past 0.7). Do NOT "upgrade Jaccard" (`role_retriever` is an unused side-path). Re-aim the DoD at **composed-spec cell selection + hard-negative rejection** on a multi-canonical eval set. If `index_card.defends` is wanted for ranking, add "populate it on N templates" (it's on 0/440 today).

## PHASE 6 — The product loop
Full 5-path intake (activate sketch/photo/voice; Cosmos perception, gated on the 0.3 merge) → retrieve → decompose → compose → static_eyes → build(assets) → dual-verify → diagnose → self-correct. **DoD = "build me a 3-cell warehouse…" → verified multi-cell scene + a passing decompose/select eval.**

## Cross-cutting tracks
- **Throughput (corrected):** serial-wall baseline from `simulate_args.duration_s` median **90s** (not 180s). The `*_with_restart.py` harnesses do BATCH restart — either build a genuine per-run harness (~100s Kit-boot budget) or adopt N-of-M batch-averaging and stop calling it "restart-per-run." **X-01 BREV/multi-Kit REQUIRES a rented A100/H100 MIG (cost line)** — local multi-Kit is a measured 2.4-2.7× SLOWDOWN dead-end.
- **Training substrate:** version `scene_timeseries.py`; build the `expand=True` L2 capture; extend `turn_recorder.py` to write L2+L3 with a versioned JSONL schema (only L1 captured today).
- **Testing/CI:** every new tool schema needs a handler + l0 tests + `no_handler_tools.json` update so the tools-resolve CI gate stays green. Make "tools-resolve green + l0 pass" an explicit done-criterion on the new-tool items.
- **Corpus health:** the defensibility audit (running) produces a prune-candidate + re-validate list (un-executed; Anton reviews). Honest reframe: "create ~795 new + re-validate ~440 existing," not "build 1000 from zero."
- **Kimate integration:** catalog-of-record contract, Cosmos/asset merges, branch cadence.
- **Platform track (X-09):** Isaac Sim 6.0/Kit 110 port = small + gated (never mid-run); cuMotion = protocolled NO until 6.1 (Experimental + proprietary license + feature gaps). WorldBinding-style USD→planner world-sync (P2-12) kills the stale-world bug class.
- **PROJECT BOUNDARY:** CAD→SimReady tooling = a SEPARATE project (serves the YCB/mesh-loader gap + 'G1 CAD parts are buildable source' from outside). Commercial directions are staged in local research (git-ignored), not in this plan.
- **ROS2 = the production / sim2real bridge** (`ROS2_STRATEGY.md`): Isaac-as-digital-twin, external ROS2/MoveIt2/PLC drives sim + real. A named first-class backend with its OWN verification tier, tagged SYNTHETIC until a self-contained `ros2_cmd` function-gate closes the loop. OFF the North Star critical path; gated behind the controller + lab-driver work.
- **sim2real fidelity:** per-template sim2real tag (the 2nd axis) + the synthetic `scripted_demonstrator`/teleop-mock (X-07) to unblock GR00T/imitation hardware-free. Markerless mocap (MAMMA, `MARKERLESS_MOCAP_RELEVANCE.md`) = WATCH-ITEM, deferred to the G1 rung.
- **Chat/canvas unify** (`LLM_TOOL_USE_SEQUENCE.md`): production chat builds from authored defaults (no geometry binding); the rich layout loop is canvas-only. Unify via one Bridge-1 path (P6-07).

## Immediate next actions (parallel, schedulable — updated 2026-06-10)
1. **[UR10 track] UR10 → 13/13** (0.1) — in flight.
2. **[Foundation] Finish static_eyes integration** — core is BUILT + 6/6 l0 green; remaining: P1-10 tool registration (+tools-resolve CI), P1-11 verifier_registry wiring, P1-09 tier-2 reach probe (coordinate Kit with the UR10 track).
3. **[Foundation] Phase-0 honesty fixes** (0.4): the honest delivery gate (P0-18, three holes) + structured verified_status (P0-19) + version `scene_timeseries.py` (P0-20).
4. **[Foundation] dual-verification** (P1-12..15) — calibration before any throughput claim.
5. **Branch re-convergence with the safety net** (0.3) — gates Phase 3/6; behind the mode flag, after/with UR10-track coordination.
6. **DECOMPOSE/SELECT go/no-go eval** (P4-02) — answer the core question BEFORE composition plumbing.
