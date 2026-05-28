# Master-Plan Audit — Isaac Assist

Date: 2026-05-28
Author: Plan-consolidation audit (Opus 4.7)
Scope: Inventory every plan/spec/roadmap doc on disk; map coverage; identify
gaps; recommend whether to consolidate or stay distributed.

---

## §1 — What plans exist (inventory)

| Doc | Date | Horizon | Scope | Status |
|---|---|---|---|---|
| `docs/AUTONOMOUS_PLAN.md` | 2026-04-18 | session-level | Loop protocol: state-check → canary → expand/debug; commit/push discipline; abort conditions | **STALE** — Apr-era; baseline numbers and `feat/qa-runtime-bundle` branch reference are out of date, but the §1-§13 loop protocol is still the operational doctrine and is referenced by the cron-plan |
| `docs/specs/2026-05-15-autonomous-execution-plan.md` | 2026-05-15 | 6-week cron | 82-task cron-driven backlog (tracks A–G); 6-week ramp; halt-criteria (hit@1 ≥0.75 OR 50 yrkesroll OR 6 weeks); compute budget (~$69 LLM, 170 h wall) | **LIVE plan** — drives `config/cron_task_graph.yaml` |
| `config/cron_task_graph.yaml` | 2026-05-15 | machine | 82 task records with deps + agent_class + verification | LIVE |
| `docs/qa/all_controllers_to_4_of_4_plan.md` | 2026-04-21 | controller-targeted | 13-phase A–M plan (controllers: native/spline/curobo/diffik/osc/sensor_gated/cube_tracking/fixed_poses/ros2_cmd) → 4/4 cube delivery + video | **PARTIALLY LANDED** — spline/curobo/native covered; documents the friction-grip vs FJ debate (decided per `feedback_isaac_assist_no_fj_fusk`) |
| `docs/qa/PLAN_NEXT_STEPS.md` | 2026-05-05 | session-level | Fas A (verified expansion) + Fas B (tool audit) + Fas C (7 stacked PRs to Kimate) | **STALE** — Fas C cherry-pick approach superseded by IA-rev-2 merge cadence |
| `docs/qa/controller_matrix_plan.md` | 2026-04-20 | controller-build-out | 11 FAS plan to ship 4 new target_source values + auto-fallback + benchmark + CP-01 freeze | **MOSTLY LANDED** — see `controller_matrix.md` for status; `motion_controllers:` tag added to canonicals 2026-05-15 |
| `docs/qa/100PCT_DEFINITION.md` + `PATH_TO_100PCT.md` | 2026-05-17 | quality bar | Definition of "stable" canonical + path to fully-green corpus | LIVE doctrine |
| `docs/qa/QA_BACKLOG_2026-05-13.md` + `POST_MIGRATION_BACKLOG_2026-05-14.md` | 2026-05-13/14 | rolling backlog | QC findings + migration follow-ups | LIVE |
| `docs/research/2026-05-27-expansion-roadmap.md` | 2026-05-27 | 5-wave corpus | 272 → 1000 templates across 12 domains; W1–W5 wave plan; dependency graph; yrkesroll matrix; risk register | **LIVE roadmap** for corpus expansion |
| `docs/research/2026-05-27-canonical-taxonomy.md` | 2026-05-27 | schema migration | `<domain>.<robot>.<variant>.NNN` id scheme + `index_card{}` block + 12-domain enum + migration order (Cohort B → A → canary) | LIVE design |
| `docs/research/2026-05-27-integration-architecture.md` | 2026-05-27 | wiring | File-level plan for `planner/{funnel,router,index_card,hil,workflow_registry,legacy_id_map}.py` (9 new files, 9 modified, ~1400 LOC) | **LIVE design — not yet implemented** |
| `docs/research/2026-05-27-decisions.md` | 2026-05-27 | gate-decisions | D1–D8 hard decisions + first-10 actions + testable-vs-wishful assumption table | LIVE — D1–D8 await Anton sign-off |
| `docs/research/2026-05-27-llm-input-format.md` | 2026-05-27 | multimodal funnel | 3-stage retrieval design; confidence-floored HIL; modality producers; workflow Mode A vs Mode B | LIVE design |
| `docs/research/2026-05-27-sim2real-validation.md` | 2026-05-27 | sim2real bridge | G1–G6 gap taxonomy + T4–T6 validation tiers + protocol per canonical | LIVE design — extends roadmap §5 |
| `specs/IA_FULL_SPEC_2026-05-10.md` | 2026-05-10 | 7-epoch product spec | 106 phases across Epochs I–VII (foundation → multimodal → workflow → critic → capability → polish → convergence) | **LIVE — 99% landed** per `phase_metadata.yaml` (144/145 landed, only Phase 102 macOS/Win release skipped) |
| `specs/phase_metadata.yaml` | 2026-05-10 (live) | machine | 144 phase records with status/landed_date/files/loc/effort | LIVE |
| `config/canonical_backlog.yaml` | 2026-05-15 (live) | corpus backlog | 140 entries (67 drafted, 73 queued) for new canonicals | LIVE |

Plus ~25 round-by-round migration audit docs (`docs/research/2026-05-15-round*.md`,
`2026-05-16-opus-audit-*.md`, `2026-05-17-*.md`) — these are session-by-session
QC trails, not plans.

---

## §2 — What's covered (mapped to topic)

| Topic | Owner doc(s) | Coverage |
|---|---|---|
| Operational loop (state-check, canary, debug) | `AUTONOMOUS_PLAN.md` | COMPLETE — 13 sections cover every operational decision |
| 6-week cron backlog | `2026-05-15-autonomous-execution-plan.md` + `cron_task_graph.yaml` | COMPLETE — 82 tasks, halting criteria, compute budget, dispatcher rules |
| Codebase decomposition (tool_executor monolith) | `IA_FULL_SPEC_2026-05-10.md` Epoch I (Phases 1–18) | COMPLETE — landed; `tool_executor.py` is now 2,418 LOC dispatch shim |
| Multimodal foundation (Block 1A) | `IA_FULL_SPEC_2026-05-10.md` Epoch II (Phases 19–32) | LANDED — codegen + REST + Kit mirror live |
| Multimodal → canonical EXECUTION bridge (Block 1B) | `2026-05-28-multimodal-canonical-flow.md` (§5 Bridge-1) + `2026-05-27-integration-architecture.md` | DESIGNED — not implemented (see §3.A below) |
| Workflow lifecycle, critic, governance | `IA_FULL_SPEC_2026-05-10.md` Epochs III–IV (Phases 33–58) | LANDED |
| Capability surface (Phases 59–82) | `IA_FULL_SPEC_2026-05-10.md` Epoch V | LANDED — incl Phase 79 humanoid WBC (skeleton-level) |
| Polish + release (Phases 83–106) | `IA_FULL_SPEC_2026-05-10.md` Epoch VI–VII | LANDED except Phase 102 (macOS/Win, user-skipped) |
| Motion-controller matrix (10 controllers × 4/4 delivery) | `controller_matrix_plan.md` + `all_controllers_to_4_of_4_plan.md` | LANDED for spline/curobo/native/sensor_gated; friction-grip standard decided per `feedback_isaac_assist_no_fj_fusk`; cuRobo vertical-lift solved 2026-05-27 |
| Canonical taxonomy + naming | `2026-05-27-canonical-taxonomy.md` | DESIGNED — D1 awaiting sign-off |
| Corpus expansion 272 → 1000 templates | `2026-05-27-expansion-roadmap.md` | DESIGNED — W1 unblocked once D1–D8 approved |
| Index-card / retrieval / funnel | `2026-05-27-llm-input-format.md` + `2026-05-27-integration-architecture.md` | DESIGNED — none of `planner/funnel.py`, `planner/router.py`, `planner/index_card.py` exists on disk |
| HIL question surfaces | `2026-05-27-llm-input-format.md` §4 + `integration-architecture.md` §3.5 | DESIGNED — no `/hil/*` routes exist |
| Sim2real validation tiers (T4–T6) | `2026-05-27-sim2real-validation.md` | DESIGNED — extends `expansion-roadmap.md` §5 |
| CP-NEW triage state (145 templates) | `2026-05-28-cpnew-triage.md` + `cpnew-canonical-overview.md` + `cpnew-vision-alignment.md` + `cpnew-duplicates.md` + `cpnew-sanity-bugs.md` | COMPLETE — 9 VERIFIED / 118 STUB / 18 AMBIGUOUS; 12 prune candidates; 8 same-robot multi-PPC bugs |
| Friction-grip vs FJ decision | `feedback_isaac_assist_no_fj_fusk` (memory) + `2026-05-27-friction-grip-sim-real-gap.md` | DECIDED — friction-only standard, no FJ shortcuts |
| Industrial-expansion track (Phases 6/8/9/10) | `IA_FULL_SPEC_2026-05-10.md` + `project_isaac_assist_industrial_expansion` (memory) | LANDED per memory; 24 yrkesroll-canonical templates drafted |

---

## §3 — What's NOT covered (gap analysis)

### A. Multimodal LayoutSpec → CP-NEW canonical execution bridge

**Source:** `2026-05-28-multimodal-canonical-flow.md` §3 (load-bearing missing wire).
**Status:** Design exists in `2026-05-27-integration-architecture.md` §3.1–3.7;
zero implementation. Decisions D1–D8 still await Anton sign-off.

**What's missing on disk:**
- `service/isaac_assist_service/planner/funnel.py`
- `service/isaac_assist_service/planner/router.py`
- `service/isaac_assist_service/planner/index_card.py`
- `service/isaac_assist_service/planner/hil.py`
- `service/isaac_assist_service/planner/workflow_registry.py`
- `service/isaac_assist_service/planner/legacy_id_map.py`
- `service/isaac_assist_service/planner/domain_router.py`
- `chat/routes.py` `/hil/*` endpoints
- `scripts/{extract_index_cards.py,rename_canonicals.py,rebuild_template_index.py}`
- `execute_template_canonical` does NOT accept `role_bindings`
- Canvas `/build` ratifies but never calls `execute_template_canonical`
- `apply_layout_spec_to_scene` tool handler ratifies but never executes
- Sketch/photo VLM functions exist but have ZERO HTTP entry points

**No existing plan doc owns this work as a phase/track.** The integration
architecture is a research doc, not a phase plan. Cron-plan §1 halt-criterion
mentions "MULTIMODAL_TEXT_INTENT=on" (t25) but does NOT cover the funnel,
router, HIL surface, or canonical-execution bridge.

### B. Humanoid pick controller — three sub-tracks

**Source:** Anton's gap-statement today; `IA_FULL_SPEC_2026-05-10.md` Phase 79
("Whole-body control: humanoid loco-manipulation") is the only mention, and
it's listed as `landed` per `phase_metadata.yaml` despite the controller not
existing as a `setup_pick_place_controller` `target_source` value. Phase 79
landed a skeleton; per Anton's gap-statement none of the three production
paths exist:

| Sub-track | Plan coverage | Gap |
|---|---|---|
| **cuRobo per-arm** (bimanual via two single-arm planners with mutual obstacle volumes) | `IA_FULL_SPEC_2026-05-10.md` Phase 63 (`execute_contact_sequence_plan`) §"Risk" mentions per-arm strategy; no implementation phase | NOT IMPLEMENTED — `controller_matrix.md` lists cuRobo as single-arm only |
| **GR00T policy** for humanoid pick | `IA_FULL_SPEC_2026-05-10.md` Phase 62 (single-command GR00T finetune) + canonical-overview §6 (10 GR00T templates) | TOOLING exists; no GR00T-as-controller path in `setup_pick_place_controller`; no humanoid policy weights downloaded |
| **IsaacLab WBC + RL** | Phase 79 landed-as-skeleton + 4 IsaacLab canonicals all `function-gate BLOCKED` per triage | NOT WIRED — no `target_source=wbc_rl` mode; gated on Anymal/G1 Nucleus assets per memory |

Roadmap §3 puts "Anymal/G1 humanoid locomotion" in W4 (post-PhysX-fix);
no architectural plan for humanoid-pick-controller integration into the
controller matrix. The 4 candidate templates (`g1-bimanual-tabletop`,
`anymal-locomotion-baseline`, `isaaclab-humanoid-locomotion`,
`isaaclab-franka-cabinet`) are all stable_fail or function-gate BLOCKED.

### C. 118-stub CP-NEW template build-out

**Source:** `2026-05-28-cpnew-triage.md` — 118 STUB / 18 AMBIGUOUS / 9 VERIFIED.
**Coverage:** `expansion-roadmap.md` discusses **adding** templates (272 → 1000)
but does NOT explicitly cover **stub-to-verified upgrades** of the 118
existing CP-NEW stubs. `canonical_backlog.yaml` (140 entries) is mostly
queued/drafted, not the stub-fix backlog.

**Three sub-buckets of the 118:**
- (A) Hard-blocked on missing infra (GR00T 50 GB weights, IsaacLab+CUDA,
  Nucleus assets) — ~35 templates — explicit defer
- (B) `env_blocked` / `stable_fail` with known root cause — ~12 templates
  — needs targeted fixes
- (C) `drafted` with `form-gate ⏳` — ~71 templates — needs form-gate
  pass + smoke run

**Missing plan elements:** no triage-doc-derived backlog as a track in the
cron-plan; `2026-05-28-overnight-progress.md` ran ad-hoc fixes
(3/40 → 8/40 on a 40-template subset) without a structured plan.
`2026-05-28-cpnew-vision-alignment.md` recommends 12 prunes + ~15 metadata
strengthenings — also unplanned.

### D. `phase_id` / `sub_id` kwarg for multi-stage same-robot PPC

**Source:** `2026-05-28-cpnew-sanity-bugs.md` §"Pattern 3" — 8 templates
blocked because `setup_pick_place_controller` uses per-robot subscription
tags (`_<flavor>_pp_sub_<ROBOT_TAG>`) and tears down prior subscriptions
on the same robot. Same-robot multi-PPC silently kills earlier phases.

**Blocked templates (8):** `machine-tender-load-unload`,
`machine-tender-door-interlock`, `yrkesroll-assembler-peg-bushing` (3 phases),
`yrkesroll-quality-tech-fixture-gauge` (6 phases),
`yrkesroll-machinist-cnc-load` (2 phases),
`yrkesroll-packer-box-seal` (2 phases),
`bin-picking-with-flip` (2 phases),
`planning-10step-retry` (8 phases — whole template design broken).

**No plan doc owns this.** Recommendation in the sanity-bugs note says
"Handler change … add `phase_id`/`sub_id` kwarg — non-trivial — the
function-gate observe window already wraps a single cycle" — explicitly
deferred. Affects production-realistic yrkesroll templates (cnc-load,
packer, machine-tender, peg-bushing).

### E. SAM2 + CLIP for non-color templates (vision-API quota)

**Source:** `2026-05-28-overnight-progress.md` line 76 — "Vision-API quota
templates (~10) require external service or local mock".

**No plan doc owns the SAM2/CLIP local-deploy or quota strategy.**
Affects templates that need semantic segmentation beyond color-based routing
(non-trivial subset of `inspect.*`, `sort.*`, `bin-picking.*` variants).

### F. Per-template architectural rewrites backlog

**Source:** `2026-05-28-cpnew-sanity-bugs.md` §"Recommendation" table:
- 6 templates need same-robot multi-PPC collapse (HIGH)
- 3 templates need active-cube-set redefinition (HIGH) —
  triple-arm-cell-handoff, roco-bimanual-assembly, assembly-line-4robot
- 6 templates need duration extension (HIGH) — long-horizon GR00T runs
- 1 template needs Clip_4 spawn fix
- 1 whole-template redesign — `planning-10step-retry`

Plus `2026-05-28-cpnew-vision-alignment.md` recommends:
- 12 templates to prune/merge
- ~15 templates to strengthen with structural_features + structural_tags
- 3 missing high-priority additions (pick.ur10.table-surface, one `compose.*`
  workflow, 3 missing SOC roles)

**No plan doc owns this.** This is a discrete, fully-scoped backlog (~30
items) sitting on top of the 5-wave roadmap but invisible to it.

### G. False-negative function-gate fixes (test-doctrine, not template-bugs)

**Source:** `2026-05-28-gate-false-negatives.md` — separate from §F.
The function-gate verifier itself has heuristics that produce false negatives.
No plan doc owns the verifier-hardening track distinct from template fixes.

---

## §4 — Recommendation: minimal consolidation, not full rewrite

### Verdict: **add a new top-level consolidation doc + 2 missing track-plans, keep the rest distributed.**

The existing plan ecosystem is dense and mostly accurate:
- `IA_FULL_SPEC_2026-05-10.md` covers the 106-phase product spec and is
  99% landed — keep as-is, treat as historical-record-now-mostly-done.
- `expansion-roadmap.md` covers corpus growth — keep as the W1–W5 roadmap.
- `autonomous-execution-plan.md` covers the cron-driven 82-task backlog —
  keep as the operational driver.
- `controller_matrix_plan.md` is mostly landed — close out + retire.
- `AUTONOMOUS_PLAN.md` operational loop is still doctrine — keep.

But six gaps (A–F above) have **no owner** and are forming an invisible
backlog. The minimal fix: **one consolidated master plan doc** that:

1. Indexes the existing plan docs (the §1 table here).
2. Calls out the 6 gap topics as new tracks (H, I, J, K, L, M below).
3. Sequences them against the existing roadmap's wave gates.

### Recommended consolidation doc structure

`docs/specs/2026-05-28-master-plan-consolidation.md`:

| Phase | Topic | Owner doc (or "TBD: NEW") | Status |
|---|---|---|---|
| 0 | Loop protocol + state-check + canary | `AUTONOMOUS_PLAN.md` | LIVE doctrine |
| 1 | IA core foundation (Epochs I–IV) | `IA_FULL_SPEC_2026-05-10.md` Phases 1–58 | LANDED |
| 2 | Capability surface (Phases 59–82) | `IA_FULL_SPEC_2026-05-10.md` Epoch V | LANDED |
| 3 | Polish + release (Phases 83–106) | `IA_FULL_SPEC_2026-05-10.md` Epochs VI–VII | LANDED except 102 |
| 4 | Motion-controller matrix | `controller_matrix_plan.md` + cuRobo vertical-lift solved 2026-05-27 | LANDED — close out |
| 5 | 6-week cron backlog (82 tasks) | `2026-05-15-autonomous-execution-plan.md` + `cron_task_graph.yaml` | LIVE — partial |
| 6 | Canonical taxonomy + index-card migration | `2026-05-27-canonical-taxonomy.md` + decisions D1–D8 | DESIGNED — awaiting D-approval |
| 7 | Corpus expansion W1–W5 (272 → 1000) | `2026-05-27-expansion-roadmap.md` | DESIGNED — gated on Phase 6 |
| 8 | Sim2real validation tiers T4–T6 | `2026-05-27-sim2real-validation.md` | DESIGNED — extends Phase 7 |
| **H** | **Multimodal LayoutSpec → canonical bridge** | **NEW** — needs phase plan derived from `2026-05-28-multimodal-canonical-flow.md §5` + `2026-05-27-integration-architecture.md §3` | NOT STARTED |
| **I** | **CP-NEW 118-stub build-out** (triage-driven) | **NEW** — needs phase plan derived from `2026-05-28-cpnew-triage.md` + per-template architectural rewrites from `cpnew-sanity-bugs.md` + `cpnew-vision-alignment.md` | AD-HOC overnight runs only |
| **J** | **Humanoid pick controller** (cuRobo per-arm / GR00T / WBC+RL — 3 sub-tracks) | **NEW** — needs phase plan; Phase 79 skeleton is the only existing landing | NOT STARTED |
| **K** | **Multi-PPC `phase_id` kwarg** (unblocks 8 yrkesroll templates) | **NEW** — single architectural task; should land before I/H | NOT STARTED |
| **L** | **SAM2 + CLIP local-deploy** (unblocks ~10 vision-quota templates) | **NEW** — single-track infra task | NOT STARTED |
| **M** | **Verifier-hardening** (function-gate false-negative fixes) | **NEW** — narrow track derived from `2026-05-28-gate-false-negatives.md` | NOT STARTED |

### Sequencing recommendation

Hard prereqs:
- **K before I** (collapsing same-robot multi-PPC unblocks 8 stub fixes).
- **M before W1 gate** (per `expansion-roadmap.md` gate-to-W2 — false-positive
  function-gate ruins the auto-pass tier).
- **D1–D8 approved before Phase 6/7/H** (taxonomy migration before expansion).
- **Phase 6 (taxonomy) before H** (index_card schema is the foundation for
  funnel/router; H builds on top).

Parallel-safe:
- L (SAM2/CLIP) is independent of everything; fan-out as cheap.
- J (humanoid) is independent of I/K/M (humanoid uses different controller
  family entirely); can run as its own track.
- M (verifier-hardening) parallelizes with K (template-handler) and L (SAM2).

Recommended execution order from today:
1. **Anton signs D1–D8.** Unblocks Phases 6/7/H. (~30 min Anton).
2. **K + M + L fan out** as independent Sonnet/Opus tracks (no Kit-RPC
   collisions — K touches `handlers/pick_place.py`, M touches verifier,
   L touches new SAM2/CLIP plumbing).
3. **Phase 6 lands** (Cohort B rename + index_card extraction).
4. **H starts** (Bridge-1 first per `multimodal-canonical-flow.md §5` —
   4 changes, no new modules; full funnel/router after).
5. **W1 starts** per `expansion-roadmap.md` once K + M land + Phase 6
   completes.
6. **J (humanoid) runs in parallel** but is a longer-horizon track —
   needs cuRobo per-arm implementation + GR00T weights download + Anymal/G1
   Nucleus access.
7. **I (118 stub build-out)** runs in waves correlated with W1–W5 — each
   wave includes stub-upgrade slots alongside new template creation.

### Why not full rewrite

The existing docs are well-structured for their scope and were authored
recently. A full rewrite would lose the per-doc detail (e.g. risk registers,
test matrices, agent-class budgets) and add document-maintenance load. The
consolidation should be **an index + 6 new track-plans**, not a replacement.

---

## §5 — Draft outline for the consolidation doc

Proposed structure for `docs/specs/2026-05-28-master-plan-consolidation.md`:

```
# Isaac Assist Master Plan — Consolidated Index
Date: 2026-05-28

## §1 — Plan inventory (the §1 table from this audit)
## §2 — Currently-active tracks (5/6 cron + W1–W5 roadmap)
## §3 — Phase ledger (table mapping Phase 0–13 to owner-docs)
## §4 — New track-plans (one per gap H/I/J/K/L/M)
   §4.H — Multimodal LayoutSpec → canonical bridge
        - Bridge-1 (4-change Sonnet task; smoke test)
        - Funnel+router land (per integration-arch §3.1–3.7)
        - HIL surface (TUI + canvas SPA per integration-arch §3.5)
   §4.I — CP-NEW 118-stub build-out
        - Bucket A (35 infra-blocked) — defer
        - Bucket B (12 env_blocked/stable_fail) — per-template root-cause fixes
        - Bucket C (71 drafted + form-gate ⏳) — form-gate pass sweep
        - Plus 12 prunes + 15 metadata-strengthenings from vision-alignment
        - Plus 17 per-template architectural rewrites from sanity-bugs
   §4.J — Humanoid pick controller (3 sub-tracks)
        - J1: cuRobo per-arm bimanual (extends Phase 63 contact-sequence)
        - J2: GR00T policy as setup_pick_place_controller target_source
        - J3: IsaacLab WBC + RL (extends Phase 79 from skeleton to working)
   §4.K — Multi-PPC phase_id kwarg
   §4.L — SAM2 + CLIP local-deploy for vision-quota
   §4.M — Verifier hardening (gate false-negative fixes)
## §5 — Sequencing + dependency graph (the §4 ordering above)
## §6 — Approval gates (D1–D8 from decisions doc; new D9–D14 from §4)
## §7 — Halt-criteria proposal (extending cron-plan §1.1–1.4 with H/J coverage)
```

The doc is **~500 lines target** — narrative index + 6 new track-plans
at ~50 lines each. Existing docs remain untouched; this is the single
"where do I look for X" entry point.

---

## §6 — Open questions for Anton

1. **Sign D1–D8** to unblock Phase 6 + 7 + H. Without this, the master
   plan can't sequence anything past §4 cron-tracks-already-in-flight.
2. **Confirm J (humanoid) is in or out** of the next-6-week window.
   It's a longer-horizon track; if Anton wants it parallel-tracked,
   we add the J1/J2/J3 phase plans. If deferred, we mark "future"
   and skip the J authoring effort.
3. **Confirm K (`phase_id` kwarg) priority** vs continuing W1 prep.
   K unblocks 8 yrkesroll templates that are exactly the production-realistic
   ones the corpus needs. Recommendation: K first, then W1.
4. **Approve L (SAM2 + CLIP)** as own track or fold into I-bucket-A
   (infra-blocked defer)? Recommendation: own track — different team-shape,
   different infra (model downloads + GPU).
5. **Approve consolidation doc** (`docs/specs/2026-05-28-master-plan-
   consolidation.md`) authoring as the next session's deliverable.
   Estimated ~500 LOC, no new code, ~3 h Opus authoring.
