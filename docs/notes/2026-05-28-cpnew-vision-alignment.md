# CP-NEW Vision-Alignment Assessment
Date: 2026-05-28
Scope: 145 CP-NEW-* templates evaluated for alignment with the project's retrieval-reasoning vision.

---

## Project Vision Recap

The goal is a database of representative robotics workflows that an LLM can retrieve when given a
natural-language query (text, voice, image, sketch), then reason about the delta between the
retrieved template and the user's actual request. Templates are the "corpus" — their `goal` +
`intent.pattern_hint` + `structural_tags` are what the retriever embeds and the LLM reads.
Templates that lack a distinctive, natural query surface poison the index; templates that are clear
and grounded in real industrial practice multiply retrieval precision.

**Templates assessed:** 145 (145 CP-NEW-*.json files confirmed on disk)

---

## 1. Strong-Alignment Section (approx. 65 templates)

These templates exemplify the vision: a real-world workflow that a practitioner would plausibly
query, a distinctive `goal` that encodes both the task and its differentiating constraint, and
`structural_tags` that support soft-filter retrieval.

**Best exemplars (would survive any prune):**

- `bin-picking-random-pose` — overlap_sphere + antipodal sampler + unstructured bin. A user typing
  "pick from messy bin" lands here. Tags distinguish from structured pick.
- `conveyor-tracking-moving-pick` — predictive intercept, belt never pauses, velocity feedforward.
  Distinctively described. Contrasts correctly with `moving-conveyor-pick`.
- `narrow-clearance-insertion` — 0.3 mm radial clearance, lateral-dominant impedance, spiral
  search. Exact parameterisation means retriever can resolve "tight peg" queries to this, not the
  looser impedance demo.
- `palletizer-layer-stack` — 2x3 grid, drop_targets dict, proximity sensor trigger. Clean,
  industrial, retrievable by "UR10 stack boxes on pallet."
- `spc-sensor-stream` — Shewhart control chart, 20-workpiece process-level monitoring. Unique in
  the library; "statistical process control" maps here and nowhere else.
- `yrkesroll-assembler-peg-bushing` — full pick+transit+insert cadence, 3-peg production metric.
  Genuinely distinct from the single-peg stub and the benchmark eval version.
- `yrkesroll-machinist-cnc-load` — door-open/fixture-load/machining-dwell/unload cycle. Real CNC
  tending workflow; matches "robot load CNC machine" exactly.
- `yrkesroll-welder-mig-tack` — discrete dwell + marker spawn at 4 tack spots. Correctly
  distinguished from continuous seam follow.
- `yrkesroll-paint-sprayer-trajectory` — boustrophedon raster, 80% coverage metric, standoff.
  Unique motion pattern in the library; maps to "robot spray paint panel."
- `weld-seam-vision-ndt` — NDT coverage scan at 10 frames/cm, defect classification per seam
  segment. Real inspection workflow distinct from the welding templates.
- `robohive-door-open` — arc pull on revolute door, primitive-built scene, correctly distinguishes
  from cabinet drawer and faucet rotation. Benchmark-grounded goal.
- `oxe-sweep-into-dustpan` — broom tool proxy, debris push en masse. Different motion class from
  pick_place; maps OXE task correctly.
- `safety-clearance-monitor-stop` + `iso10218-speed-separation` — ISO 15066 SSM. The graded
  velocity scaling template (10218) is distinctly described from the binary-stop template (15066).
- `assembly-line-4robot-handoff` — claim-mutex + handoff-signal sequencing across 4 Frankas.
  Distinctive multi-robot workflow.
- `roco-bimanual-assembly` — hold-and-fasten with dual Frankas and shared claim zone. Named after
  a real benchmark challenge.
- `maniskill-peg-insertion` — ManiSkill v3 eval dict format, depth-threshold success criterion,
  contact assertion. Actually implements benchmark metric shape.
- `rtx-sponge-bowl` — OXE RT-1 task 0042, specific arXiv reference, sim2real framing.
- `yrkesroll-ergonomics-lift-assist` — force-shared lift with human proxy, correct SOC 53-7062.
- `actuator-net-calibration` — real hardware CSV, episode-ID split (leakage guard). Distinctly
  different from the from-scratch recording version.
- `sim2real-gap-injection` — controlled noise-axis sensitivity table. Retriever can route "how
  sensitive is my sim to mass noise" here and not to the single-point gap measurement.
- `sdg-multi-cam-correlated-dr` — 4-camera copula-correlated lighting. Novel SDG variant.
- `barcode-scanner-divert` + `nir-material-divert` — distinct sensor modalities for routing.
- `groot-load-eval-live` + `groot-finetune-n10-demos` — GR00T smoke-test and full pipeline,
  both grounded in real VRAM / LoRA training parameters.
- `anymal-locomotion-baseline` — IsaacLab frozen reward, explicitly an experimental control.
- `rl-policy-export-onnx` — train-to-deploy pipeline step; maps to "export policy for robot."
- `planning-10step-retry` — long-horizon orchestration with sub-goal retries. Unique in library.

Also strong: `vacuum-gripper-sheet-pick`, `peg-bushing-impedance` (illustrative single-peg),
`screw-driving-impedance`, `wire-harness-route`, `palletizer-mixed-sku`, `tray-stack-unstack`,
`sorter-color-3lane`, `sorter-size-weight`, `conveyor-recirculation-loop`, `ros2-moveit2-franka`,
`modbus-plc-fixture-io`, `amr-pickup-handoff`, `occupancy-map-nav`, `controller-benchmark-shootout`
(3-controller, well-described), `hand-eye-calibration`, `tool-changer-swap`, `machine-tender-door-interlock`.

**Count: ~65 templates clearly vision-aligned.**

---

## 2. Weak-Alignment Section (approx. 30 templates)

These are LLM-generated filler: thin goals, zero or minimal `structural_features`, boilerplate
language, or a near-duplicate of a better-described sibling. They add index noise.

**7 pure stubs (no structural_features, no structural_tags):**
- `brick-stacking` — single-brick "V0" with known PhysX explosion failure. Goal is 289 chars,
  says "Realizes Phase 10 yrkesroll #20 (construction / DIY persona)" — the yrkesroll attribution
  is a stretch. No retrieval surface.
- `defect-sdg` — 242 chars, SDG handlers missing (`env_blocked`). Zero tags to differentiate from
  the full `scene-sdg-full-pipeline`.
- `drawer-open` — stable_fail (controller cannot drive PrismaticJoint). 231 chars, placeholder.
- `g1-bimanual-tabletop` — stable_fail (G1 asset missing). 253 chars.
- `sim2real-gap` — 226 chars, no tags. Overshadowed by `sim2real-gap-injection` which is far
  better described.
- `rl-clone-env` — 203 chars, no tags. Direct redundant stub of `cloned-env-rl-scaffold` (A97),
  which is 4x longer and properly tagged.
- `operator-ergonomics` — 209 chars, no tags. Overshadowed by `yrkesroll-ergonomics-lift-assist`
  which has proper force-sharing description.

**Near-duplicate pairs where the weaker adds no retrieval value:**
- `controller-shootout-cp` (272 chars, 4 modes, pattern_hint=pick_place wrongly, stub-level goal)
  vs `controller-benchmark-shootout` (rich, 3 modes, correct tags). Keep the latter, prune the
  former.
- `dr-curriculum` (231 chars, minimal tags) vs `dr-curriculum-trainer` (full pipeline with analyze
  + clone + launch + checkpoint). Keep trainer; prune curriculum as it adds nothing the trainer
  doesn't cover.
- `ood-detect-monitor` vs `ood-rollout-detect` — these are genuinely distinct (single-shot vs
  per-step online). Both are retriever-visible for different OOD queries. Keep both.
- `physics-calibrate-actuator` vs `physics-actuator-calibration` — different enough (physical
  constants vs gain sweep) to keep, but names are collision-prone.

**Other thin templates (goal < 250 chars, pattern_hint=other, no structural_features):**
- `multi-amr-corridor` — 169 chars, says "Realizes Phase 10 yrkesroll #16." Nav2 awareness not
  guaranteed. Stub.
- `cross-belt-sorter` — 202 chars, `stable_fail` (cubes fall through belt junctions). Broken and
  thin.
- `yrkesroll-inspector-reject-divert` — wraps `inspect-reject` with a persona framing but adds
  no new retrieval signal over the base template.
- `yrkesroll-gripper-vacuum-pick` — thin persona wrap over `vacuum-gripper-sheet-pick`.
- `yrkesroll-forklift-amr-pallet` — wraps `forklift-handoff-arm` with persona; asset-gated stub.
- `groot-redact-finetune` / `groot-export-dataset-hdf5` — both are data-pipeline admin tasks
  (PII redaction, JSONL export) that no user would naturally query for as "a robotics scenario."
  They validate code plumbing, not robot workflows.
- `nim-barcode-track` — thin; duplicates barcode aspect already covered in `barcode-scanner-divert`
  without adding a distinct retrieval surface.
- `ood-rollout-detect` — well-described goal, but `advisory_only` topology means no Kit scene.
  More a developer tool than a retrieval target.

**Count: ~30 templates are weak-alignment (filler, stubs, or broken).**

---

## 3. Ambiguous Middle (approx. 50 templates)

Structurally valid JSON, distinctive intent, but either not function-gated or gated on unavailable
assets (GR00T weights, Nucleus, IsaacLab). These are vision-aligned in concept but not yet
library-grade. The `2026-05-28-cpnew-triage.md` lists 118 stubs; many of these fall here rather
than in the "weak" bucket because their goals are specific enough to be retrievable once verified.

Examples: `bin-picking-with-flip`, `conveyor-merge-vision-priority`, `assembly-constraint-verify`,
all 10 GR00T finetune templates, `anymal-locomotion-baseline`, `ros2-rosbag-replay`.

---

## 4. Yrkesroll Review

11 core yrkesroll templates. Assessment:

**Grounded (ONET SOC confirmed, task maps to actual job duties):**
- `yrkesroll-assembler-peg-bushing` (SOC 51-2099) — peg insertion cadence is the core competency.
- `yrkesroll-machinist-cnc-load` (SOC 51-4011) — CNC tending cycle matches the O*NET task list.
- `yrkesroll-welder-mig-tack` (SOC 51-4121) — MIG tack welding discrete dwell pattern is correct.
- `yrkesroll-paint-sprayer-trajectory` (SOC 51-9123) — boustrophedon raster is how spray painting
  is actually programmed.
- `yrkesroll-quality-tech-fixture-gauge` (SOC 17-2112) — gauge + control chart (SPC) matches.
- `yrkesroll-packer-box-seal` (SOC 51-9111) — pack + seal sequence is the occupation's core task.
- `yrkesroll-ergonomics-lift-assist` (SOC 53-7062) — lift-assist maps to material-mover role.

**Thin / arbitrary:**
- `yrkesroll-assembler-snap-fit` — same SOC as peg-bushing; only adds a lateral-push gesture
  difference. At stub depth (form-gate pending), adds marginal retrieval signal over the peg variant.
- `yrkesroll-inspector-reject-divert` — duplicates `inspect-reject` without adding any new
  occupational framing beyond the SOC tag.
- `yrkesroll-gripper-vacuum-pick` — thin persona wrap, goal is identical in substance to
  `vacuum-gripper-sheet-pick`.
- `yrkesroll-forklift-amr-pallet` — asset-gated stub, SOC tagged as "logistics" (no specific code).

**Missing SOC representation that would advance the vision:** The taxonomy document (§7) already
identifies 28 missing codes. High-priority by query frequency: 53-7062 hand-loader, 17-3026 QC
tech, 51-9032 cutting operator, 51-4011 CNC machinist (covered), 51-8021 stationary engineer.

---

## 5. Benchmark Integrity

**Substantive (implement actual benchmark metric shape):**
- `maniskill-peg-insertion` — ManiSkill v3 PegInsertionSide-v0: success_rate + depth_threshold +
  contact_observed keys. Explicit source URL. Benchmark metric is the success criterion.
- `robohive-door-open` — primitive-built scene, revolute joint, 60-degree threshold, explicitly
  distinguishes from IsaacLab cabinet (RL training) and faucet (in-place rotation). Substantive.
- `rtx-sponge-bowl` — OXE task 0042, arXiv 2310.08864 cited. The sim simplification (rubber prim
  vs real sponge) is acknowledged.
- `anymal-locomotion-baseline` — IsaacLab env_id required, frozen reward as experimental control.
  Substantive if IsaacLab is available.
- `isaaclab-franka-cabinet` — contact-rich articulated drawer, uses `create_isaaclab_env` binding.
  Correctly distinct from `drawer-open` (primitive-built, scripted motion).

**Superficial namespace squatting:**
- `maniskill-pick-cube` — wraps `run_arena_benchmark` against `Isaac-PickCube-Franka-v0` with
  success_rate >= 0 as the criterion (smoke-pass only; real threshold deferred). This is an
  infrastructure smoke-test, not a ManiSkill benchmark implementation. No ManiSkill-format metric
  dict emitted.
- `maniskill-stack-cube` — uses `place_on_top_of` spatial resolver. The ManiSkill framing in the
  name implies metric parity with the StackCube-v0 leaderboard, but without the stochastic episode
  reset and per-episode success tracking that ManiSkill requires, it is a loose analog.
- `oxe-sweep-into-dustpan` — the OXE connection is accurately described (rigid proxy, no
  deformable bristles). Arguably honest, but the simplification is large enough that a user
  comparing to OXE baselines would find it misleading. The goal text does note the simplification.
- `robohive-relocate-pen` — not inspected; if it uses primitive-built dexterous regrasp with
  no dexterous hand asset it is likely superficial.
- `isaaclab-arena-lego` — IsaacLab-Arena composable spec, 4-brick sequential stack. Depends on
  IsaacLab-Arena package availability. Not verified.
- `isaaclab-humanoid-locomotion` — requires Nucleus humanoid asset. Unverified stub.

**Summary:** 5 benchmark templates are substantive; 4-6 are superficial namespace claims.

---

## 6. Recommendations

### Prune (delete or merge into better-described sibling)
These actively harm retrieval precision by creating false matches or index noise:

1. `rl-clone-env` — merge into `cloned-env-rl-scaffold` (A97 is a strict superset).
2. `dr-curriculum` — superseded by `dr-curriculum-trainer`; keep trainer only.
3. `controller-shootout-cp` — superseded by `controller-benchmark-shootout`; prune the stub.
4. `operator-ergonomics` — superseded by `yrkesroll-ergonomics-lift-assist`.
5. `sim2real-gap` — superseded by `sim2real-gap-injection` (the single-point version has no tags
   and adds no retrieval surface not already in the injection sweep).
6. `brick-stacking` — stable_fail + known PhysX explosion. Remove until V1 physics is stable.
7. `g1-bimanual-tabletop` — stable_fail + missing Nucleus asset. Remove until asset available.
8. `cross-belt-sorter` — stable_fail (cubes fall through); remove until belt physics fixed.
9. `drawer-open` — stable_fail (controller cannot drive PrismaticJoint); blocked until fixed.
10. `yrkesroll-inspector-reject-divert` — zero retrieval delta over `inspect-reject`. Merge.
11. `yrkesroll-gripper-vacuum-pick` — zero retrieval delta over `vacuum-gripper-sheet-pick`. Merge.
12. `groot-redact-finetune` + `groot-export-dataset-hdf5` — admin/plumbing tasks, not robot
    workflows. Move to a `tooling/` namespace outside the retrieval corpus.

### Strengthen (add structural_features + structural_tags before next indexing run)
These are vision-aligned in concept but not retrievable due to missing metadata:
- `multi-amr-corridor`, `defect-sdg`, `tactile-insertion`, `3station-oee`, `multi-cam-triangulation`
  (all have verified smoke runs but thin intent blocks).
- All 10 GR00T templates: add `user_intent_examples` with Swedish phrasings before indexing.
- `maniskill-pick-cube` + `maniskill-stack-cube`: either implement proper ManiSkill metric dicts or
  rename to `arena-pick-cube` / `arena-stack-cube` to avoid false benchmark claims.

### Highest-priority additions (gaps that hurt retrieval most)
- Missing: a basic `pick.ur10.table-surface` canonical (all pick templates are Franka-heavy).
- Missing: a `compose.*` multi-stage workflow template (pick→inspect→sort→palletize) — the vision
  roadmap lists these as W4 but retrieval needs at least one composed workflow to demonstrate the
  pattern.
- Missing: SOC roles for hand-loader (53-7062), QC tech (17-3026), cutting operator (51-9032).

---

## Footer

| Section | Count |
|---|---|
| Strong-alignment (vision-exemplary) | ~65 |
| Weak-alignment (filler/stubs/broken) | ~30 |
| Ambiguous (concept-valid, unverified) | ~50 |
| Yrkesroll grounded | 7 of 11 |
| Yrkesroll thin/arbitrary | 4 of 11 |
| Benchmark substantive | 5 of 11 benchmark templates |
| Benchmark superficial | 4-6 of 11 benchmark templates |
| Recommended prune (delete or merge) | 12 |
| Recommended strengthen (add metadata) | ~15 |

Net library after prune: 133 templates with cleaner index signal. The strong-alignment cluster
of ~65 is sufficient to demonstrate retrieval quality across all major domains; the remaining 50+
ambiguous templates will join them as they clear function-gate verification.
