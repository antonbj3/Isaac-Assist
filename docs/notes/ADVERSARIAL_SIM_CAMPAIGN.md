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

### Round 1 (2026-06-20)
- BLACK-BOX GENERATE: workflow blackbox-adversarial-probes (20 domains x escalation-styles) — RUNNING.
- Next: cluster -> ground top demands in Kit -> build the gaps.
