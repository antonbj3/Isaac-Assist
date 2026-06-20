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

### 48h ENGINE rhythm (self-sustaining via keepalive)
generate (black-box workflow, sparing on cc) -> ground top demands in Kit -> BUILD tractable + Kit-verify +
commit per capability + ledger -> re-test -> escalate to the next prober round. cc weekly hard-stop 94%
(currently ~15%); pace the big workflows (~4% each). Each round leaves committed value (survives keepalive wakes).
