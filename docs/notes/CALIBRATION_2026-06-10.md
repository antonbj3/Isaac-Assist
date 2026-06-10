# Calibration sweep findings — 2026-06-10 [P1-15, first measured data]

20 templates, static_eyes pair-verdicts vs live function gate, serial warm-Kit batch
(rows: `data/calibration/calib_2026-06-10.jsonl`; runner: `scripts/qa/calibration_run.py`).

## Headline results

1. **UR10 cluster 13/13 gate=True** (CP-69/70/71/73/75/79/80/81/82/83/84/85/86) — the
   Phase-0.1 goal shows green in a single-run sweep. Passes ran EARLY in the batch and
   survived any warm-Kit effect ("stable-OK across a batch = robust"). Ledger-recorded
   as measured n=1/m=1; N-of-M re-validation (P0-06) still the bar for "stable".
2. **Franka legacy set 6/6 gate=False — FULLY DISPROVEN (same day): all 6 pass on
   fresh/near-fresh Kit, incl. CP-58 whose LEGACY claim was function-gate ✗ (now
   delivers). 19/19 measured passes total today. Original quarantine reasoning:** They ran LAST (batch positions 14-19) after 13 UR10 builds = the
   documented warm-Kit false-FAIL pattern. Hypotheses in order: (a) Kit-session
   degradation; (b) real regression (UR10-track pick_place changes or the P0-18 port);
   (c) extractor artifact. **DECIDED (same day): fresh-Kit CP-01 alone = GATE
   success=True, cube dead-center at rest → hypothesis (a) CONFIRMED — warm-Kit
   degradation artifact, NOT a regression; the P0-18 legacy path is exonerated.
   The remaining 5 re-run on near-fresh Kit (any fail gets an individual fresh run).**
   Never conclude on a batch verdict — demonstrated live, again.
3. **CP-PRECISION-BIN gate=None** — gate output unparsed; investigate separately.

## Calibration verdicts (what the data says about the pairs)

- **NO pair clears a skip threshold on this data.** geometry:pass occurred with
  gate=True (13) AND gate=False (6) — geometric soundness does not predict gate
  outcome; controller behavior dominates. **SKIP stays OFF** (the dual_verify
  invariant holds; the ~3.5-4x throughput hypothesis is NOT supported at n=20).
- **RETRACTED (same day): the claimed "CP-02 static win" was itself an artifact.**
  CP-02 passes the gate on near-fresh Kit (cube at rest in target) — so the static
  delivery:fail was the EXTRACTOR mis-parsing the drop/destination (wrong bin or
  stale drop coordinate), not a true pre-build rejection. Extractor gap #4. The
  honest score for this sweep: static_eyes produced zero confirmed true-rejections
  and one false-fail — the value demonstrated today is the DIVERGENCE-localizes-
  blame property, not pre-build rejection. Calibration is for finding exactly this.
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

## N-of-M batch closeout (same day, nofm_validate, fresh-Kit per template)

**Delivery axis: 18/18 gate=True.** Faithfulness axis (scene_timeseries):
**16/18** — two real findings the gate alone missed:
- **CP-71 ts=FAIL**: Items 3-4 IN_FLIGHT/OFF_TARGET/TOPPLED while the lenient
  ANY-delivered gate passes on Items 1-2 — **P0-18 hole (b) demonstrated live.**
  Re-gate CP-71 with completeness="all" once templates adopt the new args.
- **CP-09 ts=FAIL**: 5-cube tower topple + NON_RIGID_GRIP (known-hard class).
Quality warns on passers: NON_RIGID_GRIP on Franka first-cubes (the documented
first-carry jerk — real, delivers anyway) + STACK_DRIFT/MISALIGNED on stacks.

**Refinement queued:** ledger rows tag their source (nofm_gate vs
nofm_scene_timeseries) so the axes are separable, but the per-template n/m now
mixes them — split `verification.function_gate` vs `verification.faithfulness`
records (small P0-19 follow-up) so "mixed" isn't ambiguous.

## Honest re-gate — first 4 of the falsely-green 15 (eftermiddag)

Args configured per template (completeness/targets), fresh-Kit per run, both axes ledgered:

| Template | Honest gate | Faithfulness (TS) | Verdict |
|---|---|---|---|
| CP-NEW-barcode-scanner-divert | **PASS** (6/6 per-item lane oracle) | OK (drift warns) | **Earns green** |
| CP-NEW-inspect-reject | **FAIL** | OK-ish (stochastic run) | Red cube ends in a 5-cube TOWER in PassBin (transitive raycast) — routing never happens |
| CP-NEW-y-merge-singulation | **FAIL** | FAIL (5/6 FLUNG/TOPPLED) | Falsely-green confirmed |
| CP-NEW-kit-prep-vision-gate | **FAIL** | FAIL (5/5 ALOFT/ON_FLOOR) | Falsely-green confirmed |

Measurement holes closed en route: gate_one dropped the whole P0-18 arg surface
(completeness/targets/routing — EVERY prior gate_one run was legacy any-delivered);
gate_one cube_path fallback; nofm unparseable-gate logging; honest_gate transitive-support
misroute labeling (tower-in-bin). CP-71 same afternoon: honest FAIL 2/2 with
completeness=all (was an 18/18 batch "pass").
