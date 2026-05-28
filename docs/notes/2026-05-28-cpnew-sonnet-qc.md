# CP-NEW Sonnet-Report QC (2026-05-28)

QC of four Sonnet-agent reports against the actual 145 CP-NEW template JSON files.
Read-only verification. No templates edited.

## Per-Report Verdicts

| Report | Verdict | Confidence |
|---|---|---|
| `2026-05-28-cpnew-canonical-overview.md` | **PARTIAL** | Cluster counts add to 147 (4-robot-handoff intentionally listed twice). SOC codes for 4+ yrkesroll templates are fabricated/wrong. Cluster contents and per-template descriptions broadly accurate. |
| `2026-05-28-cpnew-triage.md` | **PARTIAL** | The 9 VERIFIED count is generous — only 7 have actual `smoke-test ✓` (the borderline 2 are explicitly admitted). One template (`bin-picking-random-pose`) is listed in BOTH STUB and AMBIGUOUS. The 118+18 vs 145 math is wrong: 9+118+18 = 145 only if bin-picking-random-pose is double-counted. Heuristics are sound. |
| `2026-05-28-cpnew-duplicates.md` | **TRUSTWORTHY** with caveats | The structural overlap claims (Cluster 3-7) hold up. Cluster 7 misattributes `extends` — `yrkesroll-inspector-reject-divert` extends `CP-NEW-yrkesroll-quality-tech-fixture-gauge`, NOT `inspect-reject`. Cluster 6 (peg-bushing) glosses over a real SOC mismatch (51-2028 vs 51-2099). Shrinkage math 145→141 checks out IF the 4 merges are taken. |
| `2026-05-28-cpnew-vision-alignment.md` | **TRUSTWORTHY** with same SOC caveat | Strong/weak/ambiguous bucket assignments hold under spot-check. The "7 pure stubs" claim verified (all 7 have empty `structural_features` + `structural_tags`). 5 substantive benchmark templates confirmed. SOC code claims share the same fabrication problem as the overview. |

## Spot-Check Results

### Overview (5 cluster + 5 SOC samples)
- Cluster 5 (Vision/Inspection 9 templates): all 9 templates verified by name lookup. Correct.
- Cluster 4 (Assembly 8 templates): all 8 present. Correct.
- Cluster 14 yrkesroll SOC sample (7 templates with claimed codes):
  - `yrkesroll-machinist-cnc-load`: claimed **51-3093**, actual **51-4011** — WRONG
  - `yrkesroll-packer-box-seal`: claimed **51-9111**, actual **53-7064** — WRONG
  - `yrkesroll-paint-sprayer-trajectory`: claimed **51-9194**, actual **51-9123** — WRONG
  - `yrkesroll-quality-tech-fixture-gauge`: claimed **17-2112**, actual **51-9061** — WRONG
  - `yrkesroll-inspector-reject-divert`: claimed **17-2112**, actual **51-9061** — WRONG
  - `yrkesroll-gripper-vacuum-pick`: claimed **51-9111**, actual **51-9111** — correct
  - `yrkesroll-welder-mig-tack`: claimed **51-4121**, actual **51-4121** — correct
- Per-cluster differentiating-intent descriptions sampled (`bin-picking-random-pose`, `assembly-constraint-verify`, `palletizer-mixed-sku`): all match goal-text intent. Not boilerplate.

### Triage (8 samples)
- VERIFIED `3station-oee`, `cad-revision-drift`, `dr-curriculum`, `inspect-reject`, `multi-cam-triangulation`, `y-merge-singulation`, `controller-shootout-cp`: all 7 have `smoke-test ✓ N/N (Xs)` in `verified_status`. Confirmed.
- VERIFIED `dr-curriculum-trainer`: actual status is `form-gate-schema ✓; function-gate BLOCKED`. NO smoke-test. Report admits this is borderline.
- VERIFIED `machine-tender-load-unload`: actual status is `smoke-test pending`. NO smoke-test. Report admits borderline.
- STUB samples (`amr-pickup-handoff`, `brick-stacking`, `groot-load-eval-live`, `tactile-insertion`): all correctly classified per their `stable_fail` / `function-gate BLOCKED` signals.
- AMBIGUOUS `emergency-stop-state`, `iso10218-speed-separation`, `maniskill-pick-cube`: all three have real conflicting form-gate-pass-vs-no-runtime signals. Genuinely ambiguous.

### Duplicates (top 4 merges)
- Cluster 4 (DR curriculum trio): `dr-curriculum` is 231-char goal, no training tools. `dr-curriculum-trainer` is 879-char with `launch_training` + `clone_envs` + `checkpoint_training`. Trainer IS a structural superset of curriculum. Merge claim valid.
- Cluster 5 (sim2real-gap → ros2-rosbag-replay): Different tool sets. sim2real-gap has `measure_sim_real_gap` + `compare_sim_real_video` that rosbag-replay LACKS. Calling it "superseded" oversimplifies — they share replay primitives but emit different metrics. DELETE recommendation is a judgment call, not a clean overlap.
- Cluster 6 (peg-bushing-impedance → yrkesroll-assembler-peg-bushing): yrkesroll has richer compliance/torque tools; impedance has assembly_constraint tools yrkesroll lacks. SOC codes differ (51-2028 vs 51-2099). Merge weakens both.
- Cluster 7 (inspect-reject → yrkesroll-inspector-reject-divert): yrkesroll actually extends `yrkesroll-quality-tech-fixture-gauge`, NOT `inspect-reject`. Pattern-overlap is real but the extends-chain claim is wrong.

### Vision-Alignment (8 samples)
- 7 pure stubs claim (`brick-stacking`, `defect-sdg`, `drawer-open`, `g1-bimanual-tabletop`, `sim2real-gap`, `rl-clone-env`, `operator-ergonomics`): all 7 have `structural_features={}` AND `structural_tags=[]`. Verified.
- 5 substantive benchmarks (`maniskill-peg-insertion`, `robohive-door-open`, `rtx-sponge-bowl`, `anymal-locomotion-baseline`, `isaaclab-franka-cabinet`): all 5 have detailed multi-paragraph goals with explicit benchmark refs (arXiv IDs, env IDs, success-criterion keys). Confirmed substantive.
- Yrkesroll grounded count (7/11): the 7 listed all have ONET SOC codes IN their `goal` text. Verified.
- BUT the SPECIFIC SOC codes the report assigns are wrong in the same way as the overview (see above).

## Confirmed Errors / Fabrications

1. **Multiple SOC code fabrications** (Overview + Vision-Alignment): At least 5 of 11 yrkesroll templates have wrong SOC codes in the reports vs actual JSON. Pattern is the SOC codes were guessed or pulled from a non-template source.
2. **`bin-picking-random-pose` listed in BOTH STUB and AMBIGUOUS** in the triage report (lines 56 + 194). The 9/118/18 = 145 math only adds up if you double-count it.
3. **`yrkesroll-inspector-reject-divert` extends-chain wrong** in duplicates Cluster 7: real `extends = CP-NEW-yrkesroll-quality-tech-fixture-gauge`, not `inspect-reject`. Affects the merge recommendation's premise.
4. **VERIFIED inflation**: triage claims 9 VERIFIED but only 7 have `smoke-test ✓`. The 2 borderline (`dr-curriculum-trainer`, `machine-tender-load-unload`) have no actual smoke run. Report flags this in a note but still counts them.
5. **Overview cluster sum is 147**, not 145 (footer doesn't reconcile this; `assembly-line-4robot-handoff` is intentionally double-listed in groups 4 and 15, and per-table headers double-count `peg-bushing-impedance` in groups 4+yrkesroll, etc.).

## Recommendations

- **Trust as-is**: Duplicates report (the structural overlap analysis is sound; just discount the extends-chain claim in Cluster 7 and treat SOC mismatch in Cluster 6 as evidence to keep both).
- **Trust as-is, ignore SOC**: Vision-alignment report. Bucket assignments and benchmark/yrkesroll counts are sound; the specific SOC codes for yrkesroll are unreliable.
- **Patch and re-use**: Triage report. The signal-mining logic is excellent. Fix the bin-picking-random-pose double-listing and explicitly demote the 2 no-smoke borderlines to AMBIGUOUS for clean math (7/118/20).
- **Patch and re-use**: Overview. Cluster contents and intent descriptions are good. ALL yrkesroll SOC codes need re-verification against `goal` text (preferably regex-extracted from JSON, not guessed). Reconcile the 147 vs 145 cluster-count math.
- **No Opus re-run needed**: the analytical work is sound; the failures are factual-recall mistakes (SOC codes, extends-fields, count math). A single targeted patch pass against the JSON suffices.
- **User-level review**: the four MERGE recommendations in the duplicates report should NOT be auto-applied. Each merge weakens at least one signal (SOC variant, distinct tool subset, or distinct benchmark intent). Treat duplicates report as a "review-then-merge" list, not a directive.
