# Defensibility Audit — VERDICT

**Status:** NON-DESTRUCTIVE. This is a recommendation for Anton to review. **Nothing has been removed, moved, or modified.** All counts below are advisory.

**Date:** 2026-06-09
**Scope:** Isaac Assist template library — 355 templates classified (CP-NEW-* canonicals + lettered dialogue/advisory families A/AD/AL/AM/C/D/E/F/FX/G/J/K/L/M/P/R/S/T/Y).

---

## 1. Headline counts

| Verdict | Count | Meaning |
|---|---:|---|
| `non_build_advisory` | 246 | Builds no gradeable robot scene — dialogue, how-to, sensor/bridge config, RL/SDG/data pipelines, honesty probes, services/metrology. Not a function-gate canonical. |
| `keep_defensible` | 71 | Distinct, gradeable capability that occupies a real axis no green base already owns. |
| `revalidate_falsely_green` | 15 | Claims verified/green but the gate is lenient, single-target, oracle-routed, dry-run, or never run live. Must earn its place. |
| `prune_clone` | 15 | Duplicates an existing base's capability-tuple; the "new" dimension is metadata/benchmark/variant, not a new graded axis. |
| `prune_dead` | 8 | `stable_fail` / `env_blocked` with no path to green in the current env. |
| **TOTAL** | **355** | |

**Recommended (un-executed) actions:** PRUNE 23 (15 clone + 8 dead) · RE-VALIDATE 15 · KEEP 71 distinct canonicals · RECLASSIFY/RELOCATE 246 advisory.

---

## 2. PRUNE-CANDIDATE list (recommendation only — 23 templates)

> These are candidates Anton should review before any removal. Two buckets: **dead** (no path to green) and **clone** (capability already owned by a kept base).

### 2a. `prune_dead` (8) — broken / blocked, no path to green

| Template | Reason |
|---|---|
| CP-NEW-brick-stacking.json | `stable_fail`, persistent PhysX explosion (cube velocity >200k m/s on grasp); 3 variants tried, no path to green. |
| CP-NEW-cross-belt-sorter.json | Taxonomy's own cited broken example: 8-chute sorter builds OK but `stable_fail` (cubes fall through belt-to-belt junctions); no robot scene; un-gradeable. |
| CP-NEW-defect-sdg.json | Broken SDG stub (22 build errors, `configure_sdg`/`preview_sdg` may not exist), `env_blocked` fs:permission; no robot, no gradeable outcome. |
| CP-NEW-occupancy-map-nav.json | `env_blocked` on `isaacsim.asset.gen` — extension renamed/deprecated, absent in Isaac Sim 5.1; never built; superseded build path. |
| CP-NEW-operator-ergonomics.json | `stable_fail`, `env_blocked`: `OperatorAvatar.usd` SimReady asset missing from Isaac assets 5.0; scene never builds (16/19). |
| CP-NEW-sim2real-gap.json | BUILD 17/18 with `replay_rosbag` erroring (needs a rosbag asset that does not exist); superseded by sim2real-gap-injection; thin stub, never built green. |
| CP-NEW-tactile-insertion.json | `stable_fail` — PhysX instability blows cube velocity >200km/s on grip; superseded by working screw-driving / snap-fit / peg-bushing bases. |
| CP-NEW-zmq-stream-pointcloud.json | `env_blocked`: `isaacsim.bridge.zmq` not loadable in 5.1; ZMQ publisher cannot run; aspirational/un-verifiable backend. |

### 2b. `prune_clone` (15) — capability-tuple already owned by a kept base

| Template | Reason |
|---|---|
| CP-NEW-cad-revision-drift.json | Franka-jaw single-cube pick into a bin; the "drift" delta is a prop value the gate cannot see; `env_blocked` on `isaaclab_tasks.envs`; persona tag, no distinct graded capability. |
| CP-NEW-controller-benchmark-shootout.json | Same Franka pick-place into OutfeedBin ×3 under different controller modes; identical graded outcome; clones controller-shootout-cp. |
| CP-NEW-controller-shootout-cp.json | Reference controller-shootout (same scene, 4 modes); per-mode timing is a benchmark variant of one delivery capability; duplicates controller-benchmark-shootout. |
| CP-NEW-conveyor-recirculation-overflow.json | Recirculation TOPOLOGY already owned by conveyor-recirculation-loop; the pick half is a saturated window-pick into AcceptBin; overflow is one feature on an existing base. |
| CP-NEW-curriculum-object-complexity.json | 3-stage object-complexity RL curriculum; near-duplicate of dr-curriculum-trainer (object shape vs randomization params); same DR-curriculum-into-training base. |
| CP-NEW-dr-curriculum-trainer.json | 3-stage DR curriculum + IsaacLab training on a Franka+bin scene; superset of the green dr-curriculum with training bolted on, `BLOCKED` on IsaacLab runtime (only new claim unverifiable). |
| CP-NEW-isaaclab-arena-lego.json | Franka snap-stack of 4 brick-PROXY plain cubes into a column; capability-tuple identical to the green column-stack center (CP-13-class); "arena" is research metadata. |
| CP-NEW-machine-tender-load-unload.json | UR10 infeed→CNC→outfeed load/unload is a UR10 pick-place handoff at the saturated center; its distinct add (dwell, OPC-UA interlock) is owned by the door-interlock sibling. |
| CP-NEW-maniskill-pick-cube.json | ManiSkill PickCube parity: standard Franka tabletop jaw pick; identical to the saturated Franka-cube-static REF; benchmark wrapper is metadata. |
| CP-NEW-maniskill-stack-cube.json | ManiSkill StackCube parity: Franka cube-on-cube; same z-aware stack capability as the green column-2cube REF (CP-13-class). |
| CP-NEW-moving-conveyor-pick.json | Franka belt-synced pick into a bin is the conveyor-sync REF (CP-12-class); `interpolate_trajectory` feed-forward annotated vestigial; no distinct axis. |
| CP-NEW-ood-rollout-detect.json | Per-step OOD detector over a Franka rollout; same `detect_ood`+`monitor_forgetting` capability as ood-detect-monitor with eval glue; builds no scene. |
| CP-NEW-peg-bushing-impedance.json | Franka impedance peg-into-bushing; same tuple as yrkesroll-assembler-peg-bushing; narrow-clearance-insertion already covers the compliant-insertion base. |
| CP-NEW-physics-calibrate-actuator.json | Sim-actuator calibration vs HDF5; same `create_calibration_experiment`/`validate_calibration`/get-set drive-gains tuple as physics-actuator-calibration; no scene built. |
| CP-NEW-rtx-sponge-bowl.json | Plain Franka jaw pick of a sponge into a bowl; OXE-relabel of the saturated Franka-cube center; workpiece type is not graded. |

---

## 3. RE-VALIDATE list (`revalidate_falsely_green` — 15 templates)

> These templates **claim verified/green** but the success signal is structurally lenient: single-target gate where the distinct capability is multi-target, oracle-routed, dry-run/config-only, sequential-not-parallel, or never run live. They need a **real multi-target / live gate** before they earn a green status. Do not delete — fix the gate or downgrade the claim.

| Template | Gate weakness blocking the claim |
|---|---|
| CP-NEW-assembly-line-4robot-handoff.json | Gate is a single `/World/FinalBin` xy-tolerance delivery; cannot see whether the 3 inter-station handoffs occurred; back-pressure/mutex advisory-only; `motion_controllers.verified` empty. |
| CP-NEW-barcode-scanner-divert.json | 3-lane SKU router scored by a single scalar `target_path=/World/LaneA`; no MISROUTED guard → a degenerate route-all-to-LaneA scores green; `verified` empty. |
| CP-NEW-conveyor-merge-vision-priority.json | Has `per_class_expected`+`release_protocol`+arrival-order criterion, but the scalar gate is a single DeliveryBin; priority/arrival-order needs a live release-protocol harness not in the spine. |
| CP-NEW-groot-teleop-demo-record.json | `success_criterion` 'files==5 AND all_valid' can PASS on a hardware-absent host with 5 zero-length action timeseries (`validate_teleop_demo` accepts T=0); operator-empty, structurally lenient. |
| CP-NEW-inspect-reject.json | green→PassBin / red→RejectBin graded by a single `target_path=PassBin` excluding the red cube; failure_modes admit "Red cube reach RejectBin: not validated by gate" — the routing decision is invisible. |
| CP-NEW-kit-prep-vision-gate.json | `verify_args` stages only Part_1→KitTray and gate `target_path=KitTray` cannot read per-slot occupancy/re-pick — the vision-completeness add is unverified; `verified` empty. |
| CP-NEW-mixed-ur10-franka.json | Self-labeled SMOKE TEST / UNVERIFIED; null verify_args, null failure_modes, no intent, `motion_controllers=None`; coexistence claim unmeasured; duplicates single-robot bases. |
| CP-NEW-multi-amr-corridor.json | Claims BUILD_OK 21/21 but explicitly has no `simulate_args` and `motion_controllers=None`; the navigate+avoid+handoff capability is build-only, never function-gate measured. |
| CP-NEW-multi-sensor-fusion-rgbd-imu.json | Tri-modal pose-fusion graded by per-modality variance, but `env_blocked` (`isaacsim.sensors.ReadCameraPose` OmniGraph node not registered in 5.1) → the diagnostic gate can't currently execute. |
| CP-NEW-safety-clearance-monitor-stop.json | Claims form-gate ✓ but the load-bearing signal (pause-on-breach callback within 1s) is function-gate ⏳ never confirmed live; safety stop asserted, not measured; `verified` empty. |
| CP-NEW-triple-arm-cell-handoff.json | Single-tenant Kit RPC means the 3 arms execute SEQUENTIALLY not in parallel; strict A→B→C ordering + handoff markers are 'advisory' — the multi-arm coordination is not exercised. |
| CP-NEW-welder-seam-track.json | ALL compliance calls run `dry_run=True` (config only) pending a ros2_control torque bridge; seam-deviation<2mm is diagnostic-only, never exercised live. |
| CP-NEW-y-merge-singulation.json | smoke ✓ 1/1 is only a 53s 6-cube spawn; the singulation/alternation invariant (no double-stacking at merge) is NOT graded. |
| CP-NEW-yrkesroll-ergonomics-lift-assist.json | Force-shared cobot+human-proxy lift is `dry_run=True` config-only; status admits it needs a Workpiece↔HumanProxy joint/kinematic-sync to demonstrate the shared lift quantitatively. |
| CP-NEW-zone-partition-safety.json | Form-gate-schema ✓ but `check_robot_velocity_zero_after_entry` on breach is function-gate ⏳ never run live; velocity-cap-on-entry asserted via config flags, not a measured stop. |

**Pattern:** the dominant failure mode is the **single-`target_path` lenient trap** — a multi-target routing/sorting/handoff capability scored by one scalar delivery, so a degenerate route-all-to-one strategy scores green. The fix is a multi-target oracle gate (`per_bin_expected` / `routed_bins` / MISROUTED guard), the same pattern the kept sorter-color-3lane / yrkesroll-inspector-reject-divert bases already use correctly. The secondary mode is **dry-run/config-only safety & compliance** claims that are asserted but never run live.

---

## 4. KEEP list summary (`keep_defensible` — 71 templates, by capability)

These occupy distinct, gradeable axes no green base already owns. Grouped by capability frontier:

- **Mobile-manipulation (A1, absent axis):** amr-pickup-handoff, cart-handoff-amr, forklift-handoff-arm, yrkesroll-forklift-amr-pallet, g1-bimanual-tabletop (G1 humanoid family).
- **Multi-arm coordination:** roco-bimanual-assembly (claim-mutex), plus the dual-arm/bimanual cuRobo compose in g1-bimanual-tabletop.
- **Grasp-topology frontier:** adaptive-3finger-gripper (3-finger A2), label-applicator-pose / vacuum-gripper-sheet-pick / yrkesroll-gripper-vacuum-pick (suction × thin-flat / mixed-SKU), tool-changer-swap (A2 tool-changer).
- **Reorient / pose-change (A3 thin):** bin-picking-with-flip, robohive-relocate-pen, heap-zone-unstack.
- **Clutter / heap / bin-feed (A4):** bin-picking-random-pose, heap-zone-unstack.
- **Feed-topology (A4):** conveyor-recirculation-loop (lap-crossing), gravity-dispenser-feeder, kitting-station-6sku (rotary carousel), conveyor-tracking-moving-pick (predictive intercept).
- **Force/torque-gated contact-rich (A3 insert, force-curve gate):** bottle-cap-tighten, maniskill-peg-insertion, narrow-clearance-insertion, screw-driving-impedance, yrkesroll-assembler-peg-bushing, yrkesroll-assembler-snap-fit (contact/click).
- **Articulated-mechanism manipulation:** drawer-open (prismatic, currently stable_fail but distinct + diagnostic gate), robohive-door-open (revolute arc-pull), turn-faucet (revolute angle).
- **Multi-target routing/sorting with genuine oracle:** sorter-color-3lane, sorter-size-weight (sensor-fusion), nir-material-divert, nim-barcode-track, yrkesroll-inspector-reject-divert, yrkesroll-quality-tech-fixture-gauge.
- **Kitting / palletize placement math (A3/A4):** kit-prep-operator, palletizer-layer-stack, palletizer-mixed-sku, yrkesroll-packer-box-seal, vision-depalletize.
- **Coverage / continuous-trajectory process:** oxe-sweep-into-dustpan, wire-harness-route, weld-seam-vision-ndt, yrkesroll-paint-sprayer-trajectory, yrkesroll-welder-mig-tack, teaching-mode-pose-replay, tray-stack-unstack (z-adaptive).
- **Safety (graded velocity scaling, not enable=false):** iso10218-speed-separation, emergency-stop-state (defensible-but-watch: gain-zeroing not a verified Cat-0 stop).
- **Motion diagnostics:** ik-singularity-avoidance, planning-10step-retry (long-horizon retry), assembly-constraint-verify (constraint-validation gate).
- **Calibration / multi-rate sensing (A5):** hand-eye-calibration, multi-rate-sensor-fusion.
- **ROS2 / bridge cross-cut (A7):** jetbot-sensor-bridge, ros2-bridge-franka, ros2control-hw-mock, ros2-moveit2-franka, ros2-multi-rate, ros2-opcua-conveyor, ros2-qos-mismatch-repair, ros2-rosbag-replay, ros2-tf-tree-validation, opcua-12conveyors, machine-tender-door-interlock (OPC-UA), plc-conveyor / plc-fixture (Modbus).
- **Train-domain reference builds (build a real robot scene):** dr-curriculum (green DR-curriculum REF), rl-clone-env, rl-correlated-dr-baseline, rl-eureka-locomotion (Jetbot family).
- **Yrkesroll machine-tend / process:** yrkesroll-machinist-cnc-load.

**Note:** several KEEP entries are distinct-but-not-yet-green (e.g. drawer-open `stable_fail` needs a constraint-aware controller; emergency-stop-state needs a verified mid-trajectory stop). They are kept because the **axis** is defensible, but they carry follow-up work, not a green claim.

---

## 5. Lettered-family verdict

**All 246 `non_build_advisory` templates build NO gradeable robot scene.** They are the lettered dialogue/advisory families plus the no-robot CP-NEW pipelines:

- **CP-NEW non-build pipelines (within the 246):** the actuator-net / RL-training / policy-eval / Eureka-reward / GR00T / SDG-Replicator / bridge-validation / mesh-QA workflows — deliverable is a model/dataset/config/report, not a graded robot task; most are function-gate BLOCKED on IsaacLab/GR00T weights/Replicator/GPU.
- **Lettered families (all 246 of the lettered ones are non_build_advisory):**
  - **A-* (11):** hobbyist how-to snippets & knowledge lookups.
  - **AD-* (23):** honesty/verify-before-claim probes — read-only, no build.
  - **AL-* (10):** enterprise-architect design/ops advisories.
  - **AM-* (10):** founder onboarding / troubleshooting dialogue.
  - **C-* (3), D-* (14):** physics/sensor/ROS2-bridge config & diagnostic dialogues.
  - **E-* (11), F-* (10):** demo-readiness QA & facility-scale digital-twin advisories.
  - **FX-* (5):** single-tool "right primitive" teaching tasks (anchor/DR/bulk-op/query).
  - **G-* (6):** robot-less primitive-placement / coordinate-math exercises.
  - **J-* (10):** education/course-scaffolding advisories.
  - **K-* (12), L-* (11):** systems-engineering / CAD-metrology / clearance-analysis services (import robots but run NO motion controller — pick/place are TCP-frame names, confirmed in code).
  - **M-* (17):** IsaacLab RL config / debug / deployment-export advisories.
  - **P-* (12):** Priya SDG dialogues (writer/DR/material config).
  - **R-* (11):** Raj integrator dialogues (import/train-kickoff/packaging).
  - **S-* (12):** Sarah ROS2/Nav2 navigation-bridge diagnostics.
  - **T-* (14):** Thomas compliance / ISO standards / determinism advisories.
  - **Y-* (10):** Yuki look-dev / lighting / render-output dialogues.

**Recommendation:** These 246 are **legitimate dialogue/advisory canonicals** (honesty probes, persona Q&A, config snippets, services analysis) — they are NOT junk and several are referenced by the QA/test suite (e.g. C-01/C-03 by `variance_probe.py` / `test_tool_honesty_round2.py`; D-01/D-07/E-01/FX-01/FX-05/R-01/S-01/T-01 by test fixtures). However, they are categorically different from function-gate robot canonicals and should **move out of `workspace/templates/` into a sibling `workspace/advisory/` (or `dialogue/`) directory** so the function-gate / defensibility metrics measure only the ~86 build-canonicals (71 keep + 15 re-validate). **Before relocating, grep the test/QA suite for path references and update them** — do not break the fixtures. This is a reclassification recommendation, not a removal.

---

## 6. Verdict — library health

The library is **structurally healthy but heavily diluted**: of 355 templates only ~86 are build-canonicals (71 distinct-defensible + 15 falsely-green), while 246 (69%) are non-build dialogue/advisory canonicals that should be partitioned into a separate `advisory/` tree so the function-gate metrics stop being diluted, and only 23 (6.5%) are genuine prune candidates (15 clones of an existing base + 8 dead/blocked with no path to green). The defensible core is genuinely broad — mobile-manip, multi-arm, force-gated insertion, articulated mechanisms, multi-target routing, bridges, and train-domain builds all have real distinct bases — but the **15 falsely-green templates are the real risk**: they advertise capabilities (routing, handoff, safety-stop, singulation) that the single-target/dry-run gate cannot actually measure, and must be re-gated with a multi-target oracle or downgraded before they count toward coverage. **Recommended (un-executed) actions: PRUNE 23, RE-VALIDATE 15, RECLASSIFY/RELOCATE 246 advisory, KEEP 71 distinct canonicals — pending Anton's review; nothing has been changed.**
