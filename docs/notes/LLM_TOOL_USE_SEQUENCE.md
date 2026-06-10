# How the LLM Uses the Tools — Authoritative End-to-End Sequence (Isaac Assist)

> **Scope.** This is the single canonical reference for *how a user request flows through Isaac Assist's
> tools*, from intake to verified scene. It unifies three grounded segments: the **layout entry points**
> (where the 2D `LayoutSpec` IR enters across its four roles), the **single-scene LLM tool-use loop** (one
> sentence -> verified single cell), and the **multi-cell decompose+compose loop** (built on top).
>
> **Branch reality (READ FIRST).** Two branches diverge and neither is whole:
> - **Working tree `refactor/2026-05-12-foundation-night-1`** has the **execution bridge** (`binding_adapter.py`
>   + `routes.py:488` -> `execute_template_canonical`) but **NOT** the IR-space static-reasoning / relation stack.
> - **`origin/master`** has `relation_reasoning.py` + `cosmos3_adapter.py` + `asset_resolution.py` + the cosmos
>   intake routes, but those are **NOT merged** into the working tree (confirmed: `git show
>   origin/master:.../relation_reasoning.py` exists; the file is absent on disk in the working tree).
>
> Every step below carries an **EXISTS / PARTIAL / BUILD / MERGE** tag so this doc doubles as a readiness map.
> The target design that needs both branches is `docs/notes/LAYOUT_REASONING_SURFACE.md`.

---

## 0. The `LayoutSpec` IR and its FOUR roles

`LayoutSpec` (`multimodal/types.py:307`) is **one CAS-versioned pydantic object per session** (`revision`,
`types.py:345`). The *same persisted object* is read/written by four distinct roles — they are **stacked, not
parallel copies**:

| Role | Name | What it is | Where it fires |
|------|------|-----------|----------------|
| **ROLE 1** | **USER INPUT -> LayoutSpec** | intake: NL text / drag-drop / sketch / photo / voice / viewport produce a spec | at request arrival |
| **ROLE 2** | **LLM reasoning surface** | 6 LLM tools read/mutate/critique the same spec (symmetric with user gestures) | during the agentic loop |
| **ROLE 3** | **retrieved-canonical binding** | `ratify` maps user objects onto a template's named roles, then substitutes user geometry into the canonical | at build time |
| **ROLE 4** | **composed multi-cell / relational** | relation graph derives 3D Z-offsets, verifies physical soundness, places cells in one frame | multi-object / multi-cell |

Because all four read/write **one** CAS-guarded object, an LLM `update_layout_spec` and a user drag-drop PATCH are
*symmetric* — same `save_with_cas`, same revision counter, mutually visible.

---

## 1. TOP-LEVEL DECISION TREE — given a user request, which path fires

```
                        ┌─────────────────────────────────────────┐
                        │  USER REQUEST ARRIVES                    │
                        └───────────────────┬─────────────────────┘
                                            │
            ┌───────────────────────────────┼───────────────────────────────┐
            │                                │                               │
       (A) TEXT chat               (B) CANVAS / SPA                 (C) PHOTO / SKETCH /
       (production path)            (drag-drop or LLM               VIEWPORT
            │                        proposing geometry)                 │
            │                                │                           │
   ROLE 1-text intake               ROLE 1-dragdrop intake        ROLE 1-cosmos/vlm intake
   produce_layout_spec              patch_canvas (routes.py:157)  ┌─ cosmos: EXISTS on
   _from_text -> INTENT ONLY        FULL geometry (TypedObject    │   origin/master ONLY
   (objects=[], bindings=None)      2D pos/size) -> save_with_cas │   (/cosmos/observe[_viewport],
   orchestrator.py:971-972          EXISTS (backend wired)        │   /cosmos/propose) — MERGE
            │                                │                    └─ vlm/voice: producers
            │                                │                        EXIST, NO route — BUILD
            ▼                                ▼                           │
   ┌──────────────────┐         ┌──────────────────────┐                │
   │ retrieve top      │         │ ROLE 2: LLM + user    │◄──────────────┘
   │ template (Chroma) │         │ co-author the IR      │   (persisted as reviewable
   │ orchestrator.py   │         │ read/update/query_    │    proposal; relations -> ROLE 4
   │ :975, :1002       │         │ layout_metric (loop)  │    normalize on master)
   └────────┬─────────┘         └──────────┬───────────┘
            │                              │
   ┌────────▼─────────┐          ┌─────────▼──────────────┐
   │ CONFIDENCE GATE  │          │ [ROLE 4 if relations:   │
   │ top_sim ≥ 0.45   │          │  relation-normalize +   │
   │ AND margin ≥ 0.20│          │  verify_relation_geom]  │
   │ orchestrator     │          │  EXISTS on master ONLY  │
   │ .py:1009         │          └─────────┬──────────────┘
   └───┬──────────┬───┘                    │
   confident   NOT confident       on BUILD ▼
       │            │              ┌──────────────────────────┐
       ▼            ▼              │ ROLE 3 (LIVE on /build):   │
  HARD-          AGENTIC          │ ratify -> bindings_to_role │
  INSTANTIATE    tool loop        │ _dict -> execute_template_ │
  execute_       (LLM authors     │ canonical(role_bindings)   │
  template_      its own chain;   │ routes.py:441/487/488       │
  canonical(     templates as     │ EXISTS (route path only)    │
  top[template]) few-shot)        └────────────┬───────────────┘
  ROLE 3 does                                  │
  NOT fire                                      ▼
  (no geometry;                          live Kit verify
  role_bindings                          (form gate + function gate)
  =None)
       │
       ▼
  ════════════════════════════════════════════════════════════════════
       ▲                                          ▲
       │  IS THE REQUEST MULTI-CELL?               │
       │  (≥2 distinct robots/patterns/cells)      │
       └──────────────────────────────────────────┘
                          │
                  YES ────┴──── NO
                  │             │
   ┌──────────────▼───┐    ┌────▼──────────────────┐
   │ MULTI-CELL LOOP   │   │ SINGLE-SCENE LOOP      │
   │ (§3)              │   │ (§2)                   │
   │ ── DECOMPOSE      │   │ canonical hard-        │
   │    GO/NO-GO first │   │ instantiate +          │
   │ ── NOT BUILT      │   │ verify ladder          │
   │    (Phase 4)      │   │ ── HALF BUILT          │
   └──────────────────┘    └───────────────────────┘
```

**Resolution of the branch decision (which role(s) fire and in what order):**

- **(A) TEXT chat (production today):** ROLE 1-text **always** fires but is **intent-only** — a *retrieval key*,
  no geometry. On a confident canonical match -> **hard-instantiate from `role_defaults`**; **ROLE 3 binding does
  NOT fire** (there is no user geometry to bind). On no confident match -> agentic loop where the LLM *may* use
  ROLE 2 tools.
- **(B) CANVAS:** ROLE 1-dragdrop and/or ROLE 2 author the IR (full geometry); ROLE 2 static-checks iterate
  (flat-2D today; the trustworthy 3D ROLE 4 verdict only once merged); on build the **`/build` route fires ROLE 3**
  (ratify -> bind -> `execute_template_canonical` *with* the user geometry).
- **(C) PHOTO/SKETCH/VIEWPORT:** ROLE 1 via cosmos/vlm populates `objects` (+relations -> ROLE 4 normalization),
  persisted as a reviewable proposal; user/LLM refine via ROLE 2; then ROLE 3 build. **Not live in the working
  tree** (cosmos is on master; vlm/voice producers are unwired).

**Net order when fully wired:**
`ROLE 1 (intake) -> [ROLE 4 relation-normalize if relations] -> ROLE 2 (LLM iterate + static-check) -> ROLE 3
(ratify -> bind -> build) -> live Kit verification.`

---

## 2. THE SINGLE-SCENE LLM TOOL-USE LOOP (one sentence -> verified single cell)

**Key truth:** the production single-scene loop in `orchestrator.py` is the **HARD-INSTANTIATE path, not an
LLM-authored build.** For a one-sentence prompt that strongly matches a canonical (CP-NN), the orchestrator
*pre-executes* the template, *pre-runs* the form gate, *filters build tools out* of the LLM schema, and only then
calls the LLM — whose role collapses to **"report the pre-computed verdict + optionally call the function gate +
apply one targeted fix."**

The verification ladder the design names (**form_gate -> static_eyes -> dual-verify -> function_gate -> diagnose**)
is **only half built**: `verify_pickplace_pipeline` (form gate) and `simulate_traversal_check` (function gate) are
live, registered tools; `static_eyes` is a **spec-only façade** (not a tool, not a script — only `reach_validate.py`
exists as the live cuRobo probe it would call), dual-verification is unbuilt, and `diagnose_task_outcome` is
**docs-only** (zero code refs — confirmed by grep).

| # | Actor | Action | Tools | Layout role | LLM decision | EXISTS / BUILD | Evidence |
|---|-------|--------|-------|-------------|--------------|----------------|----------|
| 1 | USER | Sends a one-sentence scene prompt to the route handler -> `ChatOrchestrator.handle_message` | — | none | none | EXISTS | `orchestrator.py:683-706` |
| 2 | SYSTEM | Slash-command interception (`/note`, `//help`); normal prompt falls through | `parse_slash`, `execute_slash` | none | none | EXISTS | `orchestrator.py:719-741` |
| 3 | LLM | INTENT CLASSIFY (fast LLM) -> `{intent, multi_step, complexity, confidence}` | `classify_intent` | none | classify intent + complexity; flags downstream gates | EXISTS | `orchestrator.py:743-756` |
| 4 | LLM | NEGOTIATOR GATE (only if `complexity=='complex'`, not a question, prior turn not a clarification): one missing-input check; if needed, ask ONE round and END turn | `negotiate`, `format_clarification_reply` | none | ask vs proceed | EXISTS | `orchestrator.py:758-820` |
| 5 | SYSTEM | AUTO TURN-SNAPSHOT for mutating intents when Kit alive (root-layer USDA -> `/undo`) | `turn_snapshot.capture`, `is_kit_rpc_alive` | none | none | EXISTS | `orchestrator.py:822-851` |
| 6 | SYSTEM | Gather LIVE scene context + RAG/KB (retrieve_context, patterns, learnings, deprecations) | `get_stage_context`, `retrieve_context`, `find_matching_patterns`, `deprecations_index.lookup` | none | none | EXISTS | `orchestrator.py:853-898, 1131-1151` |
| 7 | SYSTEM | **TEXT->INTENT for retrieval:** `produce_layout_spec_from_text(user_message)` -> LayoutSpec with **only `intent` populated** (objects=[], bindings=None). **The ONLY appearance of LayoutSpec in the chat loop — a retrieval filter, NOT binding.** | `produce_layout_spec_from_text` | **ROLE 1 intent-only** (pattern_hint + counts) used as a soft-filter retrieval key — no objects, no bindings, no ratify | none (deterministic) | EXISTS + WIRED | `orchestrator.py:958-994`; `text_modality.py:213-243` |
| 8 | SYSTEM | RETRIEVE CANONICAL from ChromaDB: `retrieve_with_intent_soft_filter` (default) -> top_k=3 scored; compute `top_sim`, `second_sim`, `margin` | `retrieve_with_intent_soft_filter`, `retrieve_templates_with_scores` | intent_dump is the soft-filter signal over embedding similarity | none (ranking deterministic) | EXISTS | `orchestrator.py:969-1008`; `template_retriever.py` |
| 9 | SYSTEM | **CONFIDENCE GATE:** `confident_match = enabled AND top_sim ≥ 0.45 AND margin ≥ 0.20` | — | none | branch (threshold code, NOT the LLM): hard-instantiate vs few-shot agentic | EXISTS | `orchestrator.py:1009-1015` (gate), `:921` (`CANONICAL_MIN_SIM=0.45`) |
| 10 | SYSTEM | **INSTANTIATE (tool-call capture):** `execute_template_canonical(top['template'])` — execs template code in a sandbox, **CAPTURES** every tool call, applies role substitution (**authored `role_defaults`, NOT LayoutSpec bindings — `role_bindings=None`**), runs UR10 auto-repairs, REPLAYS each captured call via `execute_tool_call` | `execute_template_canonical`, `execute_tool_call` (per call) | **ROLE 3 absent:** `effective = role_bindings or role_defaults` falls to authored defaults; **`ratify` bypassed** | none (deterministic replay) | EXISTS (chat path uses no bindings) | `orchestrator.py:1031` (no role_bindings); `canonical_instantiator.py:760` (fallback), `:764-811` |
| 11 | SYSTEM | SETTLE: `settle_after_canonical` stops timeline, restores cube positions + conveyor velocities to authored values (controller install may have drifted them) | `settle_after_canonical`, `kit_tools.exec_sync` | none | none | EXISTS | `orchestrator.py:1039-1045`; `canonical_instantiator.py:193` |
| 12 | SYSTEM | **FORM-GATE PRE-CHECK (the live "static_eyes pre-check"):** `execute_template_verify` runs `verify_pickplace_pipeline` (reach + bridge + controller). Phase-1.5 optionally merges `diagnose_scene_feasibility` per stage to flip `pipeline_ok=False`. **This is Kit-side, NOT the no-Kit static_eyes façade.** | `execute_template_verify`, `verify_pickplace_pipeline`, `diagnose_scene_feasibility` (opt) | verifies instantiated layout pick/place reach + cube-source bridge | none (pre-executed FOR the LLM) | EXISTS | `orchestrator.py:1046-1057`; `canonical_instantiator.py:282-324`; `diagnostics.py:99-169` |
| 13 | SYSTEM | ADVISORY FORM-GATE (constraint detection): a 2nd `verify_pickplace_pipeline` inside `execute_template_canonical` logs out-of-reach pick/place as advisory (never blocks) — catches the CP-84/85 out-of-reach class | `verify_pickplace_pipeline` | reach/workspace constraint detection — live analogue of static_eyes' reach:shell check | none (advisory log) | EXISTS | `canonical_instantiator.py:1084-1122` (`form_gate` advisory) |
| 14 | SYSTEM | TOOL-SUBSET REPLACE + DIRECTIVE: build tools **REMOVED** from the LLM schema (`selected_tools <- ALLOWED_AFTER_INSTANTIATE`); `format_instantiation_summary` injects "Scene already built — do NOT rebuild; VERIFICATION ONLY" with exact prim paths + pre-run form-gate result + `simulate_args` | `format_instantiation_summary` | exact instantiated prim paths surfaced so the LLM references them verbatim | none (deterministic schema filter) | EXISTS | `orchestrator.py:1058-1071, 1185-1195`; `canonical_instantiator.py:74` (ALLOWED_AFTER_INSTANTIATE) |
| 15 | **LLM** | **READ THE VERDICT + DECIDE:** enters the tool loop (max 10 rounds) seeing the pre-run form-gate as ground truth; reads `pipeline_ok` + `issues[]` | `llm_provider.complete` (filtered tools) | LLM reasons over the verdict against listed paths | **form gate ok -> proceed to function gate; failed -> pick ONE targeted fix.** *(This is the real "fix.suggest_position" step — but NO structured suggest_position exists; only `issues[]` text.)* | EXISTS | `orchestrator.py:1274-1334` |
| 16 | **LLM** | **FUNCTION GATE (build/confirm):** calls `simulate_traversal_check` (Kit physics, ~minutes) with the canonical's `simulate_args` (cube_path + target_path + duration_s) to confirm the cube arrives | `simulate_traversal_check`, `execute_tool_call` | none (dynamic physics verdict) | decide whether to run the gate + with what args (default to `simulate_args`) | EXISTS | `orchestrator.py:1348-1484`; `diagnostics.py:5864`; `gate_one.py:84-93` |
| 17 | LLM | **DUAL-VERIFY (skip-or-gate) — NOT IMPLEMENTED:** spec would tag each pair {reach,delivery,support,geometry} with confidence+fidelity_tier and skip the gate on high-confidence static PASS. Today verify (pre-done) + simulate run **unconditionally** | — | spec: static-vs-physics divergence per metric pair decides skip vs escalate | spec decision (does not exist in code) | **BUILD** | `DUAL_VERIFICATION_SPEC.md §2`; `MASTER_EXECUTION_PLAN.md` Phase 1.3 |
| 18 | **LLM** | **ON FAILURE, ADJUST (targeted fix, not rebuild):** pick ONE allow-listed fix tool — `teleport_prim`, `set_attribute`/`set_physics_params`, `set_drive_gains`/`set_joint_targets` — and re-verify. Build tools are physically absent from the schema | `teleport_prim`, `set_attribute`, `set_drive_gains`, `set_joint_targets`, `set_physics_params`, `rebind_role` | `rebind_role` would re-ratify a binding, but the chat loop has no persisted spec; practical fix is `teleport_prim` on the instantiated path | choose single most-likely root cause; apply ONE concrete fix. **The LLM derives the coordinate itself (no machine-actionable suggest_position).** | EXISTS | `canonical_instantiator.py:74` (allow-list); `orchestrator.py:1255-1261` (directive); `multimodal_handlers.py:408-472` (rebind_role) |
| 19 | SYSTEM | LOOP SAFETY: 6-consecutive-failed-patch spam-halt (forces reasoned summary, tools disabled) + `MAX_TOOL_ROUNDS=10`. **NO bounded static-iteration loop** (STATIC_EYES §4 "cap N≈4, re-call static_eyes" is unimplemented — the tool doesn't exist) | — | none | none (deterministic halts) | EXISTS (loop); static-loop **BUILD** | `orchestrator.py:1491-1524` (spam halt); `config.py:89` (`MAX_TOOL_ROUNDS=10`) |
| 20 | LLM | **DIAGNOSE_TASK_OUTCOME + iterate — DOCS-ONLY, NOT BUILT:** the planned terminal classifier (DELIVERED_CLEAN / MISROUTED / TOPPLED… WHY-verdict) has **zero code refs**. Live substitutes: `diagnose_scene_feasibility` (pre-flight) + `diagnose_pick_execution` (localize) | `diagnose_scene_feasibility`, `diagnose_pick_execution` | none | from the localize verdict, choose the next targeted fix and loop to verify | **BUILD** (`diagnose_task_outcome`); LOCALIZE leg EXISTS | grep: `diagnose_task_outcome` 0 code refs; `MASTER_EXECUTION_PLAN.md` Phase 2.3; `tool_schemas.py:757, 803-813` |
| 21 | SYSTEM | **POST-LOOP HONESTY CONTRACT (the real "verified" guarantee):** anti-fabrication, anti-silent-execution, anti-ghosting, menu-path validation, and **VERIFY-BEFORE-ASSERT** — auto-invokes `prim_exists`/`count_prims_under_path`/`get_world_transform`/`list_applied_schemas`/`get_attribute` to cross-check the reply against ground truth, appending warnings on mismatch | `prim_exists`, `count_prims_under_path`, `get_world_transform`, `list_applied_schemas`, `get_attribute` | none (post-hoc claim verification) | none (deterministic) | EXISTS | `orchestrator.py:1555-1611, 1656-1735, 1737-1914` |
| 22 | SYSTEM | Return `{intent, reply, tool_calls, code_patches}`; emit `agent_reply` trace; persist turn to history | — | none | none | EXISTS | `orchestrator.py:690-701` |

**Why ROLE 3 binding does not fire in chat:** the text intake (step 7) is intent-only (objects=[]) so there is no
geometry to bind, and step 10 calls `execute_template_canonical(top['template'])` with `role_bindings=None`
(`orchestrator.py:1031`). The bridge that *would* bind user geometry exists, but only on the canvas `/build`
**route** (`routes.py:488`), and the `apply_layout_spec_to_scene` **tool** stops at `ratify`
(`multimodal_handlers.py:301`). **MUST BUILD: bring the tool to `/build` parity.**

---

## 3. THE MULTI-CELL DECOMPOSE+COMPOSE LOOP (built on top of §2)

**Key truth:** *multi-canonical composition does not exist today.* The pipeline is single-template end to end. The
per-cell ingredients (retrieve, ratify, static-eyes, function gate, diagnose — all already template/path-scoped)
exist; the **composition layer is Phase 4, not started.** And it is **gated behind a go/no-go measurement first**:
can the LLM even decompose?

| # | Actor | Action | Tools | Layout role | LLM decision | EXISTS / BUILD | Evidence |
|---|-------|--------|-------|-------------|--------------|----------------|----------|
| 1 | USER | Speaks the high-level multi-cell spec ("3-cell warehouse: UR10 palletizing, Franka kitting 4 SKUs, Carter AMR moving pallets"); enters via `produce_layout_spec_from_text` | `produce_layout_spec_from_text` | **ROLE 1 INTAKE** (raw NL); layout not yet created | none (user input) | EXISTS (but extractor collapses it) | `text_modality.py:213-245` |
| 2 | SYSTEM | **The entry-point bug:** the rule extractor collapses the 3-cell paragraph into ONE muddled Intent (single `pattern_hint` — pick_place wins; kitting + AMR-navigate **LOST**, IR has no 2nd/3rd-pattern slot; counts summed; features OR'd) | `extract_intent_rules` | **layout DEGRADATION:** 3 cells -> one flat spec; composition silently lost | none (the *absence* of a decision is the gap) | EXISTS, single-intent only | `types.py:187-209` (one pattern_hint); `types.py:307-348` (flat bindings, no cell list) |
| 3 | **LLM** | **DECOMPOSE into a cell-DAG:** emit `composition` list of `{cell_id, role, retrieve_query}` (A=palletize, B=kitting, C=amr_logistics) + relations (amr_route A.pallet_out -> B.tray_in via C). **The SELECTION-DECOMPOSE decision.** | **none — no tool exists.** `pipeline.plan` (`pipeline.py:425`) is a phase-SEQUENCER for ONE known robot, NOT a cell-decomposer | **layout DECOMPOSITION:** split one muddled spec into N per-cell sub-specs | **CORE UNSOLVED:** which canonicals to select + how to combine. **Phase 4.1 makes it a GO/NO-GO MEASUREMENT first** (≥X% correct decomposition via `direct_eval.py`). Failure = model-capability finding, not plumbing | **BUILD** | `pipeline.py:425-460`; `MASTER_EXECUTION_PLAN.md:60-63`; `direct_eval.py` has ZERO composition awareness (grep) |
| 4 | SYSTEM | Resolve each cell canonical: run the EXISTING ChromaDB retriever once per `retrieve_query`. A=palletizer (clean hit), B=Franka multi-SKU (thin — 4-SKU kitting is a compose gap), C=AMR-pallet + navigate_to (nav exists; pallet-carry + handoff is the gap) | `retrieve_templates_with_scores`, `_load_template` | per-cell template BINDING source; still per-cell, no shared frame | none at retrieval (SELECT was step 3) | EXISTS per cell | `orchestrator.py:1002-1031` (singular); `routes.py:432-433` |
| 5 | SYSTEM | Ratify each cell independently: `ratify` maps that cell's objects onto its template roles -> per-cell `role_bindings` (A: ur10 + conveyor + pallet + 6 boxes; B: franka + 4 SKUs + tray; C: carter + pallet + route) | `ratify`, `parse_template_roles` | per-cell ROLE LAYOUT; works today but **ONLY per-cell** — no object holds all three cells' bindings | SYSTEM auto-bind + disambiguators; LLM only on `needs_choice` ambiguity. Intra-cell, never cross-cell | EXISTS per cell | `ratify.py:436-470, 503-555` |
| 6 | **LLM** | **LAYOUT cells in ONE shared frame:** assign each cell a `cell_origin` + `prim_prefix` (CellA @ 0,0,0; CellB @ 6,0,0; CellC corridor), route the AMR corridor, reason about handoff alignment (pallet-output Z vs AMR deck). **Cascade-propagation origin.** | **none.** `_extract_prim_paths` (`canonical_instantiator.py:1132`) FINDS paths; **rewrite (prefix + translate by cell_origin) + singleton de-dup do NOT exist.** `compute_stack_placement` is INTRA-cell only | **THE CENTRAL layout role:** the coordinate + namespace problem — place whole cell subtrees at distinct origins so shared singletons (Ground, DomeLight) + robot bases don't collide | LLM + arithmetic: where each cell begins, corridor clear of footprints, handoff Z alignment | **BUILD (Phase 4.2, ~600 LOC, biggest build)** | LayoutSpec has NO cell fields (`types.py:307-348`); `execute_template_canonical` no offset/prefix param (`canonical_instantiator.py:764-813`); `MASTER_EXECUTION_PLAN.md:64` |
| 7 | SYSTEM | **STATIC-EYES per cell** (no-physics geometric verifier): form_gate then static_eyes probing reach for A's pallet column, B's 4 SKU picks + tray drops, **at the COMPOSED coordinates** (after the cell_origin offset) | `static_eyes` (validators), `reach_validate.py:175` (live cuRobo oracle) | layout PRE-FILTER: catches per-cell faults before expensive sim — free because validators are per-path scoped | none (deterministic) | EXISTS per cell (offset-aware probe = small new wiring) | `STATIC_EYES_SPEC.md`; `reach_validate.py:175`; `verifier_registry.py:120,133` |
| 8 | SYSTEM | **INTER-CELL static checks via the Relation edge:** (1) AMR route-clear (corridor polyline ∌ either footprint bbox), (2) handoff pose-equality (A pallet-output world pose ≈ AMR pickup, XY+Z deck), (3) no-cell-overlap (bbox A ⊥ bbox B after offsets) | **none.** Three new cheap geometry checks (~50 LOC each). `navigate_to` A* grid answers path-exists | inter-cell layout VERIFICATION (route, handoff, overlap) — inter-cell analogue of the per-cell reach probe | none (deterministic, feeds the iterate loop) | **BUILD (Phase 4.3)** | `MASTER_EXECUTION_PLAN.md:65`; `verifier_registry.py` registers only form_gate + function_gate; `relation_reasoning.py` supplies the handoff substrate (on master, **MERGE**) |
| 9 | **LLM** | **ITERATE the layout statically** until all cells + links pass: pure arithmetic on `cell_origin` + `role_defaults`. Move A's pallet to the front PASS annulus, nudge B east when corridor blocked, raise pallet-output / lower AMR deck on Z mismatch. Each iter = a few IK probes + bbox/polyline tests, **NOT a 240s sim** | `static_eyes` + `reach_validate` (re-run) + the 3 inter-cell checks; `compute_stack_placement` for grid recompute | layout FIX LOOP: the cheap cascade-iterate that makes a composed scene affordable | LLM chooses the fix (which `cell_origin` to nudge, which station Z) from static-eyes suggestions + dual-verification divergence | EXISTS per cell; inter-cell wrapper **BUILD** | `DUAL_VERIFICATION_SPEC.md`; `TRACED_FLOW_COMPLEX_SCENE.md` step 7 |
| 10 | SYSTEM | **COMPOSE + BUILD:** instantiate all 3 canonicals into ONE stage. Per cell in DAG order: render `code_template` with `role_bindings`, **RE-NAMESPACE every authored path under `prim_prefix`, TRANSLATE every position by `cell_origin`, DE-DUP singletons** (first cell owns Ground/DomeLight/physics_scene), install all controllers, dispatch via `execute_tool_call` | `execute_template_canonical` (runs ONE template today), `instantiate_role_based_code`, `_extract_prim_paths` for the rewrite. **`compose_and_build` does NOT exist** | **layout MATERIALIZATION:** namespaced + offset per-cell layouts -> one shared stage. The rewrite/translate/dedup is the single highest-leverage missing piece | SYSTEM (DAG-order build); build-order matters (singleton ownership; Kit single-tenant -> sequential) | **BUILD (Phase 4.2)** | `canonical_instantiator.py:764-813` (singular, World-rooted, no offset); `routes.py:488-491` (called once). **RISK:** 3 physics callbacks = the CP-52 dual-arm exec-gate/mutex root generalized; `settle_after_canonical` (`:193`) has no sibling knowledge -> install-all-then-settle-ONCE |
| 11 | SYSTEM | **VERIFY:** per-cell function gate (`gate_one.py` at namespaced paths) **PLUS the INTEGRATION gate:** play the WHOLE composed scene for the longest-DAG-path duration and assert the AMR provably carries a pallet A -> B (reaches A.pallet_out, payload-attaches, final XY within tol of B.tray_in, still on deck, at-rest), confirmed with honest-eyes contacts (carried, not teleported/FJ-welded) | `gate_one.py:12` (per-template, EXISTS), `simulate_traversal_check` (cp_in_xy/cp_above/cp_at_rest), `scene_eyes.py` honest-eyes. **Integration gate does NOT exist** | layout PROOF (physics): confirms the composed layout functions, including the cross-cell handoff wired in step 6 | none (gate verdict); the run is the longest DAG path, not the sum of cell durations | per-cell EXISTS; integration gate **BUILD (Phase 4.4)** | `gate_one.py:12`; `diagnostics.py:4419-4434`; `MASTER_EXECUTION_PLAN.md:66`; honest-eyes: memory `feedback_isaac_assist_virtual_eyes_scene_data` + CP-70 zero-compliance caveat |
| 12 | **LLM** | **DIAGNOSE + ISOLATE:** if integration fails because cell B kitting fails (Franka can't seat SKU-3), localize to **cell B ALONE** — read its controller records via `diagnose_pick_execution` scoped to the cell-B subtree + `scene_eyes` time-series, fix B only (move SKU-3 pick or tray slot into envelope, re-reach_validate B) **WITHOUT re-running A and C** | `diagnose_pick_execution` (`diagnostics.py:3344`, per-path scoped, EXISTS), `scene_eyes.py`. **The do-not-re-run-siblings cache does NOT exist** | layout LOCALIZED REPAIR: re-fix one cell in place; per-path diagnose isolates cleanly because gate + diagnose are already per-path scoped | LLM chooses the cell-B-local fix from the diagnose readout; decision stays inside the `prim_prefix` subtree | per-cell diagnose EXISTS; **sibling-isolate cache = the ONE genuinely new back-end (BUILD)** | `diagnostics.py:3344`; `workflow_checkpoint_store.py`/`workflow_rollback.py` are LIFECYCLE (approval) checkpoints, NOT physics-stage snapshots |

---

## 4. RESOLUTION OF THE FOUR LAYOUT ENTRY POINTS (when each fires, in what order)

The four roles are **stacked, not mutually exclusive** — they fire in sequence on the canvas/cosmos path and a
*subset* fires on the chat path. Mapping:

```
ROLE 1 (INTAKE)            ROLE 2 (LLM SURFACE)        ROLE 3 (BINDING)            ROLE 4 (COMPOSED)
─────────────────         ─────────────────────      ─────────────────────      ─────────────────────
text   → intent-only      read_layout_spec            ratify (routes.py:441)     normalize_spatial_relations
  (orch:971, WIRED)         (mm_handlers:74)            ↓                          predict_relation_positions
drag   → full geom        update_layout_spec          bindings_to_role_dict      verify_relation_geometry
  (routes:157, WIRED)       (:110, _apply_mut:559)     (binding_adapter:86)        (relation_reasoning.py)
sketch → full geom        query_layout_metric         ↓                          ↓
photo  → full geom          (:329, flat-2D ONLY)      execute_template_          3D Z-offsets + physical-
  (vlm_modality, NO ROUTE) commit_layout_spec          canonical(role_bindings)   soundness diagnostics
voice  → intent-only        (:190, telemetry no-op)    (routes:488, canonical_    (instantiator.instantiate
  (voice_modality, NO RTE) apply_layout_spec_to_       instantiator:811/741/602)  on master:1094)
cosmos → full + relations   scene (:213, RATIFY-ONLY)
  (/cosmos/*, MASTER ONLY)  rebind_role (:408)

EXISTS+WIRED: text, drag    EXISTS in working tree     EXISTS on /build ROUTE     EXISTS on origin/master
BUILD: sketch/photo/voice   (flat-2D verdict only)     only; NOT in chat;          ONLY — absent from
  intake routes                                        TOOL stops at ratify        working tree; not an
MERGE: cosmos (master)                                 → BUILD parity              LLM tool result anywhere
                                                                                   → MERGE + expose
```

**Firing order (fully wired):** ROLE 1 (intake) -> [ROLE 4 relation-normalize if relations present] -> ROLE 2 (LLM
iterate + static-check) -> ROLE 3 (ratify -> bind -> build) -> live Kit verify.

**Stacked vs mutually exclusive:**
- **ROLE 1 intake variants are mutually exclusive per request** (a request arrives as text OR drag OR photo…), but
  *successive turns* can mix them (drag-drop then chat).
- **ROLE 2 stacks on top of ROLE 1** — the LLM reads/mutates whatever ROLE 1 produced (same object).
- **ROLE 3 is downstream of ROLE 1+2** at build time; it consumes the spec's `bindings`.
- **ROLE 4 stacks under ROLE 2** (relation normalization happens before the LLM critiques) and feeds ROLE 3's
  positions.
- **Chat shortcut:** the production chat path uses **ROLE 1 (intent-only) -> [skip 2/4] -> hard-instantiate with
  authored defaults (ROLE 3 binding DOES NOT fire)**. That is the single biggest divergence from the canvas path.

---

## 5. READINESS MAP (EXISTS vs BUILD vs MERGE — consolidated)

| Capability | Status | Anchor |
|-----------|--------|--------|
| ROLE 1 text intake (intent-only) | **EXISTS + WIRED** | `orchestrator.py:971`; `text_modality.py:213` |
| ROLE 1 drag-drop intake (full geom) | **EXISTS** (backend) | `routes.py:157` |
| ROLE 1 sketch/photo/voice producers | **EXISTS, NO ROUTE -> BUILD** | `vlm_modality.py:95/167/185`; `voice_modality.py:20` |
| ROLE 1 cosmos photo+viewport intake | **EXISTS on master -> MERGE** | `origin/master:routes.py:283/340/382` |
| ROLE 2 six LLM tools (read/update/commit/apply/query/rebind) | **EXISTS** | `multimodal_handlers.py:612`; `tool_schemas.py:9676+` |
| ROLE 2 static verdict (`query_layout_metric`) | **EXISTS but FLAT-2D ONLY (Z-blind)** | `multimodal_handlers.py:329-405` |
| ROLE 3 binding bridge on `/build` route | **EXISTS (route only)** | `routes.py:441/487/488`; `binding_adapter.py:86` |
| ROLE 3 binding in chat (`apply_layout_spec_to_scene` + orchestrator) | **PARTIAL -> BUILD parity** | `multimodal_handlers.py:301` (ratify-only); `orchestrator.py:1031` (no bindings) |
| ROLE 4 relation reasoning (predict/verify/normalize) | **EXISTS on master -> MERGE + expose as tool result** | `origin/master:relation_reasoning.py`; `instantiator.py:1094` |
| Form gate (`verify_pickplace_pipeline`) | **EXISTS** | `canonical_instantiator.py:282`; `diagnostics.py` |
| Function gate (`simulate_traversal_check`) | **EXISTS** | `diagnostics.py:5864`; `gate_one.py` |
| `static_eyes` (no-Kit façade) | **SPEC-ONLY -> BUILD** | `STATIC_EYES_SPEC.md`; zero code refs |
| Dual-verification (skip-or-gate) | **SPEC-ONLY -> BUILD** | `DUAL_VERIFICATION_SPEC.md`; Phase 1.3 |
| `diagnose_task_outcome` (WHY classifier) | **DOCS-ONLY (0 code refs) -> BUILD** | `MASTER_EXECUTION_PLAN.md` Phase 2.3 |
| Multi-cell DECOMPOSE | **NOT BUILT (Phase 4.1 = go/no-go eval first)** | `MASTER_EXECUTION_PLAN.md:60-63` |
| `cell_origin`/`prim_prefix` layout + namespace rewrite | **NOT BUILT (Phase 4.2, ~600 LOC)** | `canonical_instantiator.py:764-813` (no offset param) |
| Inter-cell static checks | **NOT BUILT (Phase 4.3)** | `MASTER_EXECUTION_PLAN.md:65` |
| Integration gate | **NOT BUILT (Phase 4.4)** | `MASTER_EXECUTION_PLAN.md:66` |
| Sibling-isolate physics checkpoint | **NOT BUILT (the one genuinely new back-end)** | `workflow_checkpoint_store.py` is lifecycle-only |

---

## 6. OPEN QUESTIONS / UNSOLVED LEVERS (flagged honestly)

1. **Branch re-convergence is the precondition for Roles 1-cosmos and 4.** `relation_reasoning.py`,
   `asset_resolution.py`, `cosmos3_adapter.py`, the master instantiator relation/verify body, and the master
   routes (cosmos intake + `relation_verification`/`asset_resolutions` payload) are on `origin/master` and
   **absent** from the working tree (confirmed: `git show origin/master:.../relation_reasoning.py` exists, on-disk
   `ls` fails). **Which branch is canonical, and what is the merge order?** (`LAYOUT_REASONING_SURFACE.md` §5 step 1
   calls this the first task.)

2. **Can the LLM actually decompose?** Phase 4.1 demands a SELECT-DECOMPOSE **go/no-go eval** (extending
   `direct_eval.py`, which today has zero composition awareness) measuring decompose-correctness on held-out
   composed specs **BEFORE any plumbing**. Failure here is a model-capability finding (tie to fine-tune), not a
   build task. This eval does not exist yet.

3. **ROLE 2 static verdict trustworthiness.** `query_layout_metric reachable` is flat-2D (Z-blind, no reach shell,
   no scene collision) and will green-light unreachable straight-down picks (the documented CP-NEW failure mode).
   The plan is a `static_eyes` super-metric = `verify_relation_geometry` (Tier B) + 3D-shell reach approx + 3D-AABB
   collision, fed by asset-bbox stamp-back. None of Tier B/C is exposed as an LLM tool result yet. **Build as an
   extension of `query_layout_metric` or a new `static_check` tool?**

4. **ROLE 3 in the chat path.** Should the orchestrator (`orchestrator.py:1031`) pass `role_bindings`, and should
   `apply_layout_spec_to_scene` (`multimodal_handlers.py:213`) call the same Bridge-1 path as `routes.py:488` so the
   LLM build and canvas build are one code path? The text intake is intent-only, so there is no geometry to bind —
   **does a chat-side path need a geometry-bearing LayoutSpec first?**

5. **Multiple-physics-callback contention is the deepest non-plumbing multi-cell risk.** 3 controllers ticking one
   world step are the CP-52 dual-arm exec-gate / mutex-starvation root generalized to N cells. The 2-arm version was
   solved (per-cube mutex + belt fixes); whether that discipline generalizes is unproven — exactly why the expensive
   **integration gate cannot be skipped** even after all cheap static-eyes pass.

6. **Relations are not yet a typed IR model.** `LayoutSpec.constraints` is `Optional[List[Dict]]` and
   `relation_reasoning` reads them duck-typed. ROLE 4 needs a typed `Relation` model + `add_relation`/`remove_relation`
   mutation ops in `_apply_mutations` + a canvas edge affordance, so canvas+LLM emit relations through the same
   validated path as objects. Also: `role.outputs`/`template.outputs` typing is undefined — handoff relations
   (`amr_route A.pallet_out -> B.tray_in`) need a typed role I/O schema across CP templates.

7. **The do-not-re-run-siblings isolate-rebuild (multi-cell step 12) is the one genuinely new physics back-end:**
   either a cell-subtree teardown+rebuild OR a physics-stage checkpoint/restore. `workflow_checkpoint_store.py` and
   `workflow_rollback.py` are lifecycle (approval) checkpoints, not physics-stage snapshots — no existing primitive
   covers this.

8. **`commit_layout_spec` is a telemetry no-op** (`multimodal_handlers.py:190`) — proposed/committed lives in SPA
   state. If the LLM-authoring loop needs a durable accepted-revision marker, that must be added.

9. **`static_eyes` / `fix.suggest_position` / `diagnose_task_outcome` are the three named-but-unbuilt links in the
   single-scene ladder.** Today the LLM gets only `verify_pickplace_pipeline`'s `issues[]` text and must derive its
   own teleport/set_attribute coordinates; there is no bounded static-iteration loop and no consolidated outcome
   classifier (only the LOCALIZE leg `diagnose_pick_execution` exists).
