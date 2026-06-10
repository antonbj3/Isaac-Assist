# Measurement & diagnosis tools — the map (2026-06-10)

Inventoried from the live repo. Four layers by COST, plus the LLM-callable surface.

## Layer 1 — STATIC (no Kit, milliseconds)
| Tool | What it answers | Status |
|---|---|---|
| `multimodal/static_eyes.py` | layout geometrically sound? (reach-shell/clump/support/fit/drop/relations) + actionable fixes | **LLM-tool ✓** (`static_eyes`) |
| `qa/semantic_usd_diff.py` | are two USD stages the same scene? (migration safety) | module+tests |
| `scripts/qa/lint_gate_coverage.py` | does the template grade ALL its workpieces? | report-only CLI |

## Layer 2 — LIVE PROBES (Kit, no full sim, ~10-60s)
| Tool | What it answers |
|---|---|
| `scripts/qa/reach_validate.py` | per-target cuRobo IK verdict, cup-down (REACHABLE = necessary-not-sufficient) |
| `scripts/qa/tier2_reach_probe.py` | N-of-M aggregation of the above (the dual-verify PROBE action) |
| `scripts/qa/scene_validate.py` | post-build/settle constraint check (reach/interpen/support/instability) |
| `scripts/qa/belt_probe.py` | conveyor/belt behavior probe |

## Layer 3 — FULL-SIM GRADERS (Kit + physics, minutes)
| Tool | What it answers | Distinction |
|---|---|---|
| `scripts/qa/gate_one.py` | THE final verdict: delivered? (cube_final positions + at_rest) | verdict-only, **NOT a time-series** |
| `scripts/qa/scene_timeseries.py` | graded TIME-SERIES: per-cube states over time (SEATED/FLUNG/TOPPLED/MISROUTED…) + contacts + primary EE | grader+TS in one; `_report` = the diagnose-loop substrate |
| `scripts/qa/scene_eyes.py` | rich live probe: joints, EE quat, plans, grip-latch/release TIMELINE, contacts, velocities | the "WHY did the motion look wrong" tool (caught the cup-gap/late-release class) |
| `scripts/qa/function_gate_suite.py` / `_consistency.py` | batch verdicts / N-run pass-rate with Wilson CI | batch drivers |
| `scripts/qa/calibration_run.py` | static-vs-gate divergence rows (P1-15) | calibration |

**Rule (project memory + today re-proven): review the TIME-SERIES on every measurement —
gate verdicts alone miss the faithfulness axis (the 9/13 visually-broken-passers lesson).**

## Layer 4 — LLM-CALLABLE diagnose/measure tools (registered handlers)
`diagnose_pick_execution` (reads ctrl: records, no re-sim) · `diagnose_physics_error` ·
`diagnose_performance` · `diagnose_training` · `diagnose_domain_gap` · `diagnose_whole_body` ·
`measure_sim_real_gap` (offline comparator) · `measure_distance` · `check_physics_health` ·
`check_collisions` / `check_collision_mesh(es)` · `check_path_clearance` · `check_singularity` ·
`check_tf_health` · `check_vram_headroom` · `simulate_traversal_check` (the gate as a tool) ·
`static_eyes` (new today).

**The five `multimodal/diagnose_*.py` modules** (cycle_time, energy, physics_stability,
sensor_coverage, workspace_util) — scene-level analytics ("the variants"): each computes one
metric family from the stage/spec; several are thin/spec-stage rather than production-deep.

## The scratch generation (the lesson)
Session tools that lived in `/tmp` or `~/.isaac_qa/run/` — `ik_probe*.py`, `cup_detector.py`,
`robust_check.sh`, `gate_full.py`, `why_classify.py`, `scene_timeseries.py` — were invisible to
the repo. P0-20 versioned the two load-bearing ones (scene_timeseries, why_classify); the rest
are session-scratch by nature. New rule of thumb: a measurement tool used twice gets versioned.

## Where this is heading (planned)
- **P2-06 `diagnose_task_outcome` — BUILT (2026-06-10)**: LLM-callable, reads the recorded
  `ts_*.json`, classifies per-object WHY (DELIVERED_CLEAN/NOT_PICKED/RODE_OFF_BELT/
  DISPLACED_NOT_DELIVERED/FLUNG/TOPPLED/DROP_IMPRECISE) from raw motion; live-validated
  on all 88 artifacts. In Layer 4 now.
- **P0-06 N-of-M harness** — gate_one + scene_timeseries per run, both fed into the
  verification ledger (`extras.verdict_vector` + `kit_session_age_s`) so every measured row
  carries delivery AND faithfulness.
- **P5-22 gate classes** — `verify_articulation`, `articulation_angle`, pattern_hint-dispatch
  (new verdict classes for non-pick-place verbs).
