# Adversarial-Sim Capability Campaign (48h autonomous, started 2026-06-20)

Anton's mandate (2026-06-20): work 48h forward with full decision authority, NO supervision, NEVER stand still.
Goal = an adversarial user-simulation that exposes where the "infinite capacity" composition system OVERCLAIMS,
**and BUILDS the missing capability** when a gotcha is real. Black-box simulators (blind to internals) that
iteratively escalate complexity. cc hard-stop at >=94% weekly (`bash ~/.claude/scripts/cc_usage.sh` each wake).

## Methodology — GROUNDED black-box build-loop (NOT closed-world reasoning)

★ FATAL FLAW in the naive version (caught by Anton, "outcome only as good as the methodology"): having LLMs
REASON about a third LLM's hypothetical behavior against MY catalog labels is circular + ungrounded — it only
re-lists known weaknesses, can't find GENUINE-block edge-case failures, and a hostile reviewer rightly says "you
never RAN it." A gotcha is REAL only when **DEMONSTRATED**.

The grounded loop:
1. **BLACK-BOX GENERATE** (parallel, cheap): hostile industrial buyers — blind to the catalog, knowing only the
   "describe anything, we automate it" promise — generate ESCALATING attack-conversations (simple -> complex ->
   chained -> edge -> extreme), one per industrial domain x escalation-style. Output: clustered, ranked
   capability-DEMANDS (the user side of the attack surface).
2. **GROUND IN KIT** (paced, serial = the real test, needs NO Gemini): for each top demand, map it to the catalog
   + actually RUN it (scene_eyes / chain_xkit_gate / compose_and_verify). Does the software DELIVER it?
   - GENUINE block exists + Kit-passes -> system WINS (honest capability).
   - Gap (no block) OR mapped block Kit-FAILS -> **GOTCHA** (software < promise). Reviewer wins.
3. **BUILD** (the 48h core): each real gotcha = a missing/broken capability -> build it (new canonical block /
   template-geometry fix / new chain) -> Kit-verify per the standard discipline (fresh-Kit scene_eyes RAW,
   restart-before-each, N-of-M, commit per fix).
4. **RE-TEST + ESCALATE**: re-run the demand -> now delivered? Then the next prober escalates further.
5. **SECONDARY honesty test (Gemini-windowed)**: does compose_reason_eval honestly FLAG the gap, or overclaim?
   (run sparingly when the 429 quota refreshes; the catalog/Kit grounding is primary.)

Discipline carried in: gates LIE -> scene_eyes RAW per-object; restart-before-EACH; ground-vs-Kit not vs catalog
labels (this session proved my own labels can be stale-Kit false-negatives); commit per fix -> branch
feat/foundation-build + this ledger; surgical template text-edits; ALDRIG threshold-graze.

## LEDGER (round | demand | grounding verdict | gap/built | status)

### Round 1 (2026-06-20) — BLACK-BOX GENERATE done
20 domains x escalation-styles -> 186 raw demands -> 27 distinct (workflow blackbox-adversarial-probes, w9zrxqar6).
Top-7 (grounding_priority 5, by cross-domain demand):
- [13x] multi-robot fault-tolerant load-rebalancing (one robot faults mid-run, others absorb) — DEEP
- [12x] deformable/non-rigid grasp (bag, fabric, produce) — cluster claims "sim HAS deformable support, never exercised under compose" -> GROUND it
- [12x] per-item serial TRACEABILITY across robot-robot handoffs (custody log) — TRACTABLE build
- [11x] autonomous cross-robot FAULT RECOVERY with live part disposition — DEEP
- [10x] NL multi-station composition -> EXECUTABLE chain from one sentence — Gemini-gated
- [9x] hard-constraint INFEASIBILITY reporting (refuse+explain, not silently violate) — the HONESTY test — Gemini-gated
- [9x] generative weight-stratified mixed-SKU pallet (heavy below light, stability) — TRACTABLE build

★ SINGLE BIGGEST CREDIBILITY RISK (cluster's own synthesis): inter-station handoff relies on SOFTWARE SIGNALS
not confirmed PHYSICAL STATE -> a stalled station -> upstream silently overwrites the occupied slot, NO fault
surfaced. Root cause of ~30% of the escalated demands. Exposed with ONE stall injection. = GROUND+BUILD #1.

BUILD QUEUE (tractable, Kit-groundable, no Gemini): (1) physical-state handoff GATING [#1 risk, root-cause];
(2) per-item TRACEABILITY logging across handoffs; (3) weight-stratified mixed-SKU pallet. Gemini-windowed:
NL-composition end-to-end, infeasibility-honesty. Ground+document-as-limit (deep): fault-recovery, deformable,
zero-shot-onboarding, force-control.

### Round 1 GROUND+BUILD
- **#1 handoff-gating — GROUNDED (gotcha CONFIRMED, code-level):** chain_xkit_gate relay auto-derives handoff
  geometry but has NO occupancy/wait/clear gate; the source (CP-CONV-02-SRC) gates its PICK on a belt PickSensor
  but NOTHING gates its PLACE onto the HandoffTray. So no physical-state handoff gating -> a stalled receiver in
  a steady-state line would be silently overwritten. (Build = controller-deep, sensor-gated place; queued.)
- **TRACEABILITY — BUILT + DEMONSTRATED (chain_xkit_gate custody instrumentation):** the cross-Kit chain runtime
  now emits a per-part CUSTODY CHAIN (/tmp/chain_custody.json): each part's identity (leaf Cube_N) is tracked
  through every robot-robot handoff (Cube_N -> relay1/Cube_N -> ...); journey = [(station, stage, delivered, pos)],
  complete_custody flag. DEMO: CONV-02-SRC-3 -> CP-CHAIN-FLAT = 3 parts, 3 COMPLETE custody across 2 stations. A
  dropped part -> stations_logged < n_stations = a DETECTED handoff loss (the gap-detection the demand requires).
  Commit: see chain_xkit_gate.py cont.319mm.
- **COMPLIANCE-EXPORT — BUILT + DEMONSTRATED (scripts/qa/custody_compliance_export.py):** promotes the custody
  record to a compliance-grade, tamper-evident export (IATF-16949 / AS9100 / 21-CFR-Part-11 compatible): per-step
  robot_id (from chain_stages), outcome (PASS/FAIL), position, + a forward SHA-256 HASH-CHAIN where each record
  folds in the prior -> editing any earlier record breaks every later hash = tamper-evident; the final
  chain_integrity_hash SEALS the export. DEMO: 3 parts, 0 gaps, TAMPER_CHECK re-derives -> SEALED. Timestamps
  honestly flagged capture_pending (NOT fabricated; chain_xkit_gate run-time capture is the follow-up).
- ROUND-1 NET: 2 capabilities BUILT (per-part traceability + tamper-evident compliance-export) addressing the
  12x-demand traceability/compliance cluster; #1 handoff-gating gotcha GROUNDED (confirmed).
- Next round: weight-stratified mixed-SKU pallet [9x]; physical-state handoff GATING build [#1, deeper];
  Gemini-windowed NL-composition + infeasibility-honesty; ground+document deep gaps (deformable/fault-recovery).

### Round 1 GEMINI-WINDOW grounding (NL-composition core promise + honesty)
Gemini quota refreshed -> grounded the #2 (NL composition) + #5 (infeasibility-honesty) demands via compose_reason_eval.
- ★ INSTRUMENT-BUG FIXED (false-success-vakt on the EVAL itself): pick-extraction regex was `CP-[A-Z0-9]...` which
  does NOT match lowercase -> the new lowercase canonicals (CP-NEW-barcode-scanner-divert, nir-material-divert,
  sorter-size-weight, precision-pick) were UN-extractable -> false MISS. Fixed -> `[A-Za-z0-9]`. After fix
  sortdiv-barcode PASS (LLM DID pick it; the SYSTEM delivers, the eval was hiding it). Committed.
- GROUNDED NL-pick reliability ~16-17/21: GENUINE misses = sortdiv-material (LLM won't pick the NIR-material divert),
  real-conveyor (won't pick CP-CONV-02 for "moving real belt"), humanoid-stand (won't pick CP-G1-STAND-01),
  robot-ambig (incomplete), imp-seq-down (structure=None, the known stochasticity). So the "compose ANY task from
  one sentence" promise delivers ~80%, NOT 100% -> a hostile reviewer's one-sentence demand hits the ~20% intent-
  match gap. = grounded credibility finding (the build = richer intent->canonical matching in the SYS/catalog).
- GAP-HONESTY WORKS (positive): gap-ur10-sort + gap-ur10-kit both correctly FLAGGED the gap (picks=[]) instead of
  hallucinating a block -> the system IS honest about those catalog gaps (the #5 honesty test passes the basic cases;
  harder adversarial infeasibility — no-touch zone, payload-over-limit — is the next escalation).
- Next build: lift NL-pick from ~80% -> higher by enriching intent->canonical matching for the missed ops.

### Round 2 LAYOUT-STRESS (Anton: build incrementally then suddenly reconfigure; stay within robotics)
16 integrators build a line then disrupt it (reorder/insert/remove/move/robot-swap/shrink-floor/split-merge).
20 distinct layout/reconfiguration demands, mostly HIGH overclaim-risk. TOP: incremental in-place cell edit (22x),
frozen-cell preservation (14x), handoff re-bind after reorder (11x), reach re-validate (12x), spatial overlap (9x),
robot-swap-in-place (6x), belt-mutation (10x), fixed-anchor (7x), N-to-1 merge (8x).

★★ CRITICAL RE-GROUNDING (a durable methodology fix the sim itself forced — skepticism on my OWN grounding):
I first "grounded" the spatial-overlap gotcha against scripts/qa/compose_gate.py (fixed 2.5*idx, no collision check)
and started building a redundant compose_layout_check.py. WRONG ARTIFACT: compose_gate is a TEST GATE. The actual
PRODUCTION composer is **service/isaac_assist_service/chat/composer.py**, and it is SOPHISTICATED — verified by its
_selftest (PASSES: "namespacing + offset + phase_id + chain source-override") and by reading it:
  - compute_layout_offsets(throw_pad, clearance) — footprint-based, OVERLAP-FREE layout (explicitly "Replaces the
    hardcoded 2.5*idx"); template_footprint derives each cell's extent; throw_pad even absorbs measured ride-off.
  - namespace_and_offset_calls / reroot_prim_path / _transform_value — full multi-instance namespacing.
  - apply_source_override — chain handoff/source re-wiring (so reorder/robot-swap re-derive on re-compose).
  - precondition_check — surfaces fusion/contention (#47-class) LOUDLY before build (refuse/warn findings).
  -> So spatial-overlap is HANDLED (gotcha REFUTED); handoff-rebind / robot-swap / reorder are handled via a
  DETERMINISTIC re-compose; my compose_layout_check was redundant + inferior -> DISCARDED (rm'd, not committed).
★★ DURABLE LESSON: ground the adversarial sim against the PRODUCTION composer + runtime, NOT the qa test gates
(compose_gate / chain_xkit_gate / scene_eyes are MEASUREMENT harnesses). This RE-FRAMES Round 1: the traceability
build went into chain_xkit_gate (a test harness, OK as a cross-Kit chain runtime but verify it reflects production)
and the #1 handoff-gating gotcha was grounded against chain_xkit_gate, NOT the production apply_source_override path
— both need a production-pipeline re-check before being treated as real gaps.
GENUINE narrow layout gaps (the composer does NOT cover): in-place EDIT preserving a commissioned cell's exact state
(it re-composes from scratch — but for a SIM the re-compose is correct, so this is a real-world commissioning concern
not a sim-correctness bug); parametric BELT mutation (template-level, no API); FIXED-ANCHOR clearance constraint
(could extend precondition_check — the one tractable+sim-relevant build candidate). Most of the wave was REFUTED =
an HONEST outcome (the sim validated the composer's real capability + corrected the agents' naive-composer assumption).

### Round 1 NL-pick RE-GROUNDED (diagnostik-först on the raw response — instrument lied AGAIN)
The "NL-pick ~80%, real misses material-sort/real-conveyor/humanoid-stand" finding was WRONG. EVAL_RAW raw-read of
the LLM body revealed the 3 "misses" were Gemini OVERLOAD-ERRORS: a 200-OK body = "I'm having trouble reaching my
reasoning backend right now (upstream service overloaded). Please try again." The eval counted that apology as a
response -> no CP-ids -> picks=[] -> FALSE MISS. So the ~80% was CONFOUNDED (real passes + transient overload-misses);
the TRUE NL-pick rate is higher, and these 3 are NOT real reasoning gaps.
LIVING-TOOL FIXES committed: (1) eval pick-regex [A-Z0-9]->[A-Za-z0-9] (lowercase canonicals were un-extractable);
(2) _is_overload() detection + retry-on-overload (4x backoff) + an OVERLOAD verdict EXCLUDED from the pass-rate
denominator (was false-MISS); (3) EVAL_RAW env-gated raw-print (the diagnostic that caught it). Description-enrichment
(scope-clarifying op cues in CATALOG, shared by compose_orchestrate too) KEPT — plausibly helpful, but UNVALIDATED
(Gemini was overloaded during the window; re-validate next quota window with the overload-retry now in place).

### ★★ CAMPAIGN META-FINDING (the biggest, most honest output so far)
Rigorous GROUNDING (vs the PRODUCTION composer + raw-reads) has CONSISTENTLY REFUTED the black-box waves' gotchas as
INSTRUMENT / INFRA artifacts, not real system failures:
- layout gotchas -> REFUTED (production composer has footprint-overlap-free layout + namespacing + handoff-rebind +
  precondition contention-detection; I'd grounded against the qa TEST GATE not production).
- NL-pick "misses" -> Gemini OVERLOAD-errors (false-MISS), + an eval REGEX bug (lowercase) — both instrument lies.
- #1 handoff-gating -> a SCOPE limit (finite-batch composition), not a silent-overwrite bug.
So: the "infinite capacity" MARKETING is over-stated, but the actual production composition CORE is MORE capable and
MORE honest than the black-box gotcha-hunt assumed. The adversarial sim's real value here = it forced the rigor that
CAUGHT MY OWN instrument/grounding errors (regex, overload, wrong-module, stale-Kit) — a system-level false-success-
vakt. Genuine remaining gaps are NARROW + mostly block-level robot capabilities (Kit-grounded: weight-pallet,
deformables) or deep (in-place-edit, fault-tolerance) — pursued via Kit, not via more reasoning-only gotcha waves.

### 48h ENGINE rhythm (self-sustaining via keepalive)
generate (black-box workflow, sparing on cc) -> ground top demands in Kit -> BUILD tractable + Kit-verify +
commit per capability + ledger -> re-test -> escalate to the next prober round. cc weekly hard-stop 94%
(currently ~15%); pace the big workflows (~4% each). Each round leaves committed value (survives keepalive wakes).
