# Calibration sweep findings — 2026-06-10 [P1-15, first measured data]

20 templates, static_eyes pair-verdicts vs live function gate, serial warm-Kit batch
(rows: `data/calibration/calib_2026-06-10.jsonl`; runner: `scripts/qa/calibration_run.py`).

## Headline results

1. **UR10 cluster 13/13 gate=True** (CP-69/70/71/73/75/79/80/81/82/83/84/85/86) — the
   Phase-0.1 goal shows green in a single-run sweep. Passes ran EARLY in the batch and
   survived any warm-Kit effect ("stable-OK across a batch = robust"). Ledger-recorded
   as measured n=1/m=1; N-of-M re-validation (P0-06) still the bar for "stable".
2. **Franka legacy set 6/6 gate=False** (CP-01/02/09/13/22/58) — **QUARANTINED, not
   ledger-recorded.** They ran LAST (batch positions 14-19) after 13 UR10 builds = the
   documented warm-Kit false-FAIL pattern. Hypotheses in order: (a) Kit-session
   degradation; (b) real regression (UR10-track pick_place changes or the P0-18 port);
   (c) extractor artifact. **Fresh-Kit CP-01 single-run in flight decides.** Never
   conclude on a batch verdict.
3. **CP-PRECISION-BIN gate=None** — gate output unparsed; investigate separately.

## Calibration verdicts (what the data says about the pairs)

- **NO pair clears a skip threshold on this data.** geometry:pass occurred with
  gate=True (13) AND gate=False (6) — geometric soundness does not predict gate
  outcome; controller behavior dominates. **SKIP stays OFF** (the dual_verify
  invariant holds; the ~3.5-4x throughput hypothesis is NOT supported at n=20).
- **One true static win:** CP-02 static delivery:fail + gate:False — static_eyes
  correctly rejected pre-build (drop aimed outside the destination). Every such
  template skips a doomed ~5-min gate run.
- **The divergence localizes blame** (spec §1.2): static-PASS + gate-FAIL = a
  CONTROLLER/runtime problem, not layout. This applies to the entire Franka-fail
  set if the fresh run confirms the fails.

## Extractor gaps to fix before the next sweep

- `support` unknown 20/20 — the extractor parses no support surfaces (Table parse
  missing) → the support pair is blind. Add table/fixture extraction.
- `no_drop_target` on stacking templates (CP-09/13/58) — stacking has no bin; the
  delivery pair needs a stack-target form (or stays honest-unknown for stacks).
- `robot_base_assumed` on add_reference robots (5 UR10 templates) — parse the
  follow-up translate op instead of assuming [0,0,0.75].

## Ledger semantics note

For the 13 measured passes, `record_gate_run` replaced the backfilled
`legacy_claim` with the measured record — intended: measurement supersedes claim.
The quarantined 6 keep their backfill (claims stand until honest measurement).
