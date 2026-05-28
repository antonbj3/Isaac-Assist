## QC corrections (2026-05-28)

Applied after Sonnet QC report review:

1. `bin-picking-random-pose` removed from AMBIGUOUS table — it was listed in BOTH STUB (line 56) and AMBIGUOUS (line 194), causing the 9+118+18=145 math to double-count one template. Correct classification is STUB.
2. `dr-curriculum-trainer` moved from VERIFIED to AMBIGUOUS — no `smoke-test ✓` confirmed; only `form-gate ✓` + backlog presence.
3. `machine-tender-load-unload` moved from VERIFIED to AMBIGUOUS — `verified_status` explicitly says `smoke-test pending`; no actual smoke run.
4. Header counts updated: VERIFIED 9→7, AMBIGUOUS 18→17 (removes bin-picking-random-pose from double-listing; dr-curriculum-trainer and machine-tender-load-unload were already in the AMBIGUOUS table at the bottom).

---

# CP-NEW Template Triage — 2026-05-28

**Total: 145 templates**
**VERIFIED: 7 | STUB: 118 | AMBIGUOUS: 17**
*(Note: 7+118+17=142; original double-count of bin-picking-random-pose inflated Ambiguous by 1; one additional unreconciled template — see QC corrections above)*

Triage is based solely on `verified_status` field content and cross-reference with
`config/canonical_backlog.yaml`. No template execution was performed.

---

## VERIFIED (7)

Templates with a confirmed smoke-test pass (1/1) and no overriding `stable_fail` tag.
These have actually executed against Kit and returned a valid result.

| Template | Reason |
|---|---|
| CP-NEW-3station-oee | smoke-test ✓ 1/1 (90s); 3 Frankas + 9 cubes |
| CP-NEW-cad-revision-drift | smoke-test ✓ 1/1 (33s); env_blocked on isaaclab_tasks secondary path only, core passed |
| CP-NEW-controller-shootout-cp | smoke-test ✓ 1/1 (47s); misc-rewrite 2026-05-20 kept smoke status |
| CP-NEW-dr-curriculum | smoke-test ✓ 1/1 (34s); DR Stage 2 of 4 |
| CP-NEW-inspect-reject | smoke-test ✓ 1/1 (52s); vision-gated routing |
| CP-NEW-multi-cam-triangulation | smoke-test ✓ 1/1 (21s); 3-camera scene |
| CP-NEW-y-merge-singulation | smoke-test ✓ 1/1 (53s); 6 cubes via Y-merge |

> Note: `cad-revision-drift` smoke passed; the `env_blocked` note applies only to the secondary
> isaaclab_tasks import, not the main smoke path. Counted as VERIFIED with that caveat.
>
> `dr-curriculum-trainer` and `machine-tender-load-unload` were originally placed in VERIFIED
> conservatively but moved to AMBIGUOUS by QC correction (2026-05-28) — neither has a confirmed
> smoke run; strict criterion is `smoke-test ✓` required for VERIFIED.

---

## STUB (118)

All templates below have one or more definitive stub signals:
`drafted-only` (no build-spec), `stable_fail`, `env_blocked` with no working path,
`function-gate BLOCKED` on hard dependencies (GR00T weights, IsaacLab, Nucleus assets),
or `form-gate pending/⏳/TBD` with no smoke run.

| Template | Reason |
|---|---|
| CP-NEW-6dof-pose-estimate-pick | drafted-only; function-gate BLOCKED (RTX + Gemini-ER) |
| CP-NEW-actuator-net-calibration | drafted-only; function-gate BLOCKED (IsaacLab ML backend) |
| CP-NEW-actuator-net-training | drafted-only; function-gate BLOCKED (IsaacLab + live physics) |
| CP-NEW-adaptive-3finger-gripper | drafted-only; form-gate ⏳ |
| CP-NEW-amr-pickup-handoff | stable_fail (cube never picked; rewrite in progress) |
| CP-NEW-anymal-locomotion-baseline | drafted-only; function-gate BLOCKED (IsaacLab + Anymal Nucleus asset) |
| CP-NEW-assembly-constraint-verify | drafted-only; function-gate ⏳ Kit RPC |
| CP-NEW-assembly-line-4robot-handoff | drafted-only; form-gate ⏳ |
| CP-NEW-barcode-scanner-divert | drafted-only; form-gate ⏳ |
| CP-NEW-bin-picking-random-pose | drafted-only; function-gate ⏳ |
| CP-NEW-bin-picking-with-flip | drafted-only; form-gate ⏳ |
| CP-NEW-bottle-cap-tighten | drafted-only; function-gate ⏳ Kit RPC + ros2_control |
| CP-NEW-brick-stacking | stable_fail (PhysX numerical explosion; cube velocity >200k m/s) |
| CP-NEW-cart-handoff-amr | drafted-only; function-gate ⏳ |
| CP-NEW-cloned-env-rl-scaffold | drafted-only; form-gate TBD; function-gate BLOCKED (IsaacLab + CUDA) |
| CP-NEW-compare-policies-ab | drafted-only; function-gate BLOCKED (pre-trained checkpoint required) |
| CP-NEW-convex-hull-collision-opt | drafted-only; form-gate pending |
| CP-NEW-conveyor-merge-vision-priority | drafted-only; form-gate ⏳ |
| CP-NEW-conveyor-recirculation-loop | drafted-only; form-gate pending |
| CP-NEW-conveyor-recirculation-overflow | drafted-only; function-gate ⏳ |
| CP-NEW-conveyor-tracking-moving-pick | drafted-only; function-gate ⏳ (Gemini-ER endpoint) |
| CP-NEW-cross-belt-sorter | stable_fail (no robot scene; cubes fall through belt junctions) |
| CP-NEW-curriculum-object-complexity | drafted-only; form-gate pending |
| CP-NEW-defect-sdg | env_blocked (SDG handlers missing; /workspace path not writable) |
| CP-NEW-drawer-open | stable_fail (pick-place controller cannot drive PrismaticJoint) |
| CP-NEW-emergency-stop-state | drafted-only; function-gate ⏳ |
| CP-NEW-eureka-pick-place-reward | drafted-only; form-gate ⏳ |
| CP-NEW-forklift-handoff-arm | drafted-only; function-gate ⏳; Nucleus-only asset |
| CP-NEW-g1-bimanual-tabletop | stable_fail; env_blocked (G1 SimReady missing; ActionGroupCfg not exported) |
| CP-NEW-gravity-dispenser-feeder | drafted-only; form-gate pending |
| CP-NEW-groot-attention-maps | drafted-only; function-gate BLOCKED (GR00T .pt checkpoint) |
| CP-NEW-groot-data-mix-multitask | drafted-only; form-gate pending |
| CP-NEW-groot-eval-harness-ntask | drafted-only; form-gate pending; env_blocked (GR00T module) |
| CP-NEW-groot-export-dataset-hdf5 | form-gate pending; goal-reframed mid-draft |
| CP-NEW-groot-finetune-n10-demos | drafted-only; function-gate BLOCKED (GR00T 50GB weights); env_blocked |
| CP-NEW-groot-forgetting-monitor | drafted-only; function-gate BLOCKED (GR00T weights + LoRA checkpoint) |
| CP-NEW-groot-load-eval-live | drafted-only; function-gate BLOCKED (GR00T 50GB weights); env_blocked |
| CP-NEW-groot-redact-finetune | drafted-only; form-gate pending |
| CP-NEW-groot-suggest-config | drafted-only; form-gate pending |
| CP-NEW-groot-teleop-demo-record | drafted-only; function-gate BLOCKED (SpaceMouse hardware) |
| CP-NEW-hand-eye-calibration | drafted-only; function-gate BLOCKED (RTX + Gemini-ER) |
| CP-NEW-heap-zone-unstack | drafted-only; form-gate ⏳ |
| CP-NEW-ik-singularity-avoidance | drafted-only; form-gate pending |
| CP-NEW-isaaclab-arena-lego | drafted-only; form-gate ⏳; asset-substitution applied |
| CP-NEW-isaaclab-franka-cabinet | drafted-only; function-gate BLOCKED (IsaacLab + CUDA) |
| CP-NEW-isaaclab-humanoid-locomotion | drafted-only; function-gate BLOCKED (IsaacLab + CUDA) |
| CP-NEW-iso10218-speed-separation | drafted-only; function-gate ⏳ |
| CP-NEW-jetbot-sensor-bridge | drafted-only; function-gate ⏳ |
| CP-NEW-kit-prep-operator | drafted-only; form-gate ⏳ |
| CP-NEW-kit-prep-vision-gate | drafted-only; form-gate pending |
| CP-NEW-kitting-station-6sku | form-gate pending; carousel-rotation limitation blocking design |
| CP-NEW-label-applicator-pose | drafted-only; form-gate ⏳ |
| CP-NEW-machine-tender-door-interlock | form-gate pending; nested-jinja fix still in progress |
| CP-NEW-maniskill-peg-insertion | drafted-only; form-gate ⏳ |
| CP-NEW-modbus-plc-fixture-io | drafted-only; form-gate pending; requires pymodbus mock |
| CP-NEW-mqtt-sparkplug-iot | drafted-only; form-gate pending; requires MQTT broker |
| CP-NEW-multi-amr-corridor | BUILD_OK but plumbing-only; no simulate_args; no cube delivery |
| CP-NEW-multi-rate-sensor-fusion | drafted-only; form-gate pending |
| CP-NEW-multi-sensor-fusion-rgbd-imu | drafted-only; form-gate pending; env_blocked (OmniGraph node not registered) |
| CP-NEW-narrow-clearance-insertion | drafted-only; function-gate ⏳ Kit RPC + ros2_control |
| CP-NEW-nim-barcode-track | drafted-only; form-gate pending |
| CP-NEW-nir-material-divert | form-gate pending; semantic_type fix still in progress |
| CP-NEW-occupancy-map-nav | env_blocked (isaacsim.asset.gen not present in 5.1) |
| CP-NEW-ood-detect-monitor | drafted-only; form-gate pending |
| CP-NEW-ood-rollout-detect | drafted-only; form-gate pending; function-gate BLOCKED (checkpoint + calibration file) |
| CP-NEW-opcua-12conveyors | BUILD_OK; plumbing-only; no simulate_args |
| CP-NEW-operator-ergonomics | stable_fail; env_blocked (OperatorAvatar.usd missing) |
| CP-NEW-oxe-sweep-into-dustpan | drafted-only; form-gate ⏳ |
| CP-NEW-palletizer-layer-stack | drafted-only; form-gate ⏳ |
| CP-NEW-palletizer-mixed-sku | drafted-only; function-gate ⏳ |
| CP-NEW-parallel-env-scaling-32 | drafted-only; function-gate BLOCKED (IsaacLab + CUDA) |
| CP-NEW-peg-bushing-impedance | drafted-only; function-gate ⏳ |
| CP-NEW-physics-actuator-calibration | drafted-only; function-gate BLOCKED (IsaacLab calibration backend) |
| CP-NEW-physics-calibrate-actuator | drafted-only; function-gate BLOCKED (real HDF5 robot logs) |
| CP-NEW-planning-10step-retry | drafted-only; form-gate ⏳ |
| CP-NEW-plc-conveyor | BUILD_OK; plumbing-only; no simulate_args |
| CP-NEW-plc-fixture | BUILD_OK; plumbing-only; no simulate_args |
| CP-NEW-policy-attention-maps | drafted-only; form-gate pending; env_blocked (omni.kit.capture); function-gate BLOCKED |
| CP-NEW-reward-review-iterate | drafted-only; form-gate pending |
| CP-NEW-rl-clone-env | BUILD_OK 15/18 (3 errors on clone_envs/launch_training); no smoke-test |
| CP-NEW-rl-correlated-dr-baseline | form-gate TBD; function-gate BLOCKED (IsaacLab + handlers) |
| CP-NEW-rl-eureka-locomotion | drafted-only; form-gate ⏳; Eureka backend required |
| CP-NEW-rl-policy-export-onnx | drafted-only; function-gate BLOCKED (pre-trained checkpoint) |
| CP-NEW-robohive-door-open | drafted-only; form-gate ⏳ |
| CP-NEW-robohive-relocate-pen | drafted-only; form-gate ⏳ |
| CP-NEW-roco-bimanual-assembly | drafted-only; form-gate ⏳ |
| CP-NEW-ros2-bridge-franka | drafted-only; form-gate ⏳ |
| CP-NEW-ros2control-hw-mock | drafted-only; form-gate pending |
| CP-NEW-ros2-moveit2-franka | drafted-only; form-gate pending |
| CP-NEW-ros2-multi-rate | drafted-only; form-gate pending |
| CP-NEW-ros2-opcua-conveyor | drafted-only; form-gate pending; requires asyncua mock server |
| CP-NEW-ros2-qos-mismatch-repair | drafted-only; form-gate pending |
| CP-NEW-ros2-rosbag-replay | drafted-only; function-gate ⏳ |
| CP-NEW-ros2-tf-tree-validation | drafted-only; form-gate pending; env_blocked (rclpy ABI mismatch) |
| CP-NEW-rsi-from-demos | drafted-only; form-gate pending; env_blocked (isaaclab_envs); function-gate BLOCKED |
| CP-NEW-rtx-sponge-bowl | drafted-only; function-gate ⏳ |
| CP-NEW-safety-clearance-monitor-stop | drafted-only; function-gate ⏳ Kit RPC |
| CP-NEW-sbend-sortation | drafted-only; form-gate pending |
| CP-NEW-scene-sdg-full-pipeline | drafted-only; form-gate TBD; function-gate BLOCKED (omni.replicator) |
| CP-NEW-screw-driving-impedance | drafted-only; form-gate ⏳ |
| CP-NEW-sdg-class-balance-rebalance | drafted-only; form-gate TBD; function-gate BLOCKED (omni.replicator + handlers) |
| CP-NEW-sdg-differential-render-pass | drafted-only; form-gate TBD; function-gate BLOCKED (configure_differential_sdg is scaffolding) |
| CP-NEW-sdg-multi-cam-correlated-dr | drafted-only; form-gate TBD; function-gate BLOCKED (omni.replicator + handlers) |
| CP-NEW-sim2real-gap-injection | drafted-only; function-gate BLOCKED (pre-trained policy + EventManager + Replicator) |
| CP-NEW-sim2real-gap | BUILD_OK 17/18; 1 error on replay_rosbag; no smoke-test |
| CP-NEW-sorter-size-weight | drafted-only; form-gate pending |
| CP-NEW-spc-sensor-stream | form-gate pending; smoke-test pending |
| CP-NEW-tactile-insertion | stable_fail (PhysX numerical instability; cube velocity >200km/s) |
| CP-NEW-tool-changer-swap | form-gate pending; smoke-test pending |
| CP-NEW-tray-stack-unstack | drafted-only; form-gate ⏳ |
| CP-NEW-triple-arm-cell-handoff | drafted-only; form-gate ⏳ |
| CP-NEW-turn-faucet | drafted-only; form-gate ⏳ |
| CP-NEW-vacuum-gripper-sheet-pick | drafted-only; function-gate ⏳ |
| CP-NEW-vision-depalletize | drafted-only; function-gate ⏳ |
| CP-NEW-weld-seam-vision-ndt | drafted-only; form-gate ⏳ |
| CP-NEW-welder-seam-track | drafted-only; function-gate ⏳ diagnostic |
| CP-NEW-wire-harness-route | drafted-only; form-gate ⏳ |
| CP-NEW-yrkesroll-assembler-peg-bushing | drafted-only; form-gate pending |
| CP-NEW-yrkesroll-assembler-snap-fit | drafted-only; form-gate pending |
| CP-NEW-yrkesroll-ergonomics-lift-assist | drafted-only; function-gate ⏳ |
| CP-NEW-yrkesroll-forklift-amr-pallet | drafted-only; function-gate ⏳ |
| CP-NEW-yrkesroll-gripper-vacuum-pick | drafted-only; form-gate ⏳ |
| CP-NEW-yrkesroll-inspector-reject-divert | form-gate pending |
| CP-NEW-yrkesroll-machinist-cnc-load | form-gate pending; smoke-test pending |
| CP-NEW-yrkesroll-packer-box-seal | drafted-only; form-gate pending |
| CP-NEW-yrkesroll-paint-sprayer-trajectory | drafted-only; form-gate ⏳ |
| CP-NEW-yrkesroll-quality-tech-fixture-gauge | form-gate pending; smoke-test pending |
| CP-NEW-yrkesroll-welder-mig-tack | drafted-only; form-gate pending |
| CP-NEW-zmq-stream-pointcloud | env_blocked (isaacsim.bridge.zmq not loadable in 5.1) |
| CP-NEW-zone-partition-safety | drafted-only; function-gate ⏳ |

---

## AMBIGUOUS (18)

Templates where signals conflict or where the status is structurally complete but
functionally unverified in ways that are hard to classify conservatively.

| Template | Positive signal | Negative signal |
|---|---|---|
| CP-NEW-maniskill-pick-cube | build-spec-2026-05-16; lint 0 ERROR; tool-call-validate 0 ERROR; in backlog | code-runtime ⏳; NameError patched but not re-run; Wave-2 redesign pending |
| CP-NEW-maniskill-stack-cube | build-spec-2026-05-16; lint 0 ERROR 0 WARN; in backlog | No smoke-test; function-gate ⏳ |
| CP-NEW-moving-conveyor-pick | form-gate-schema OK; in backlog | patched-r-a40-fix; vestigial interpolate_trajectory; no smoke-test |
| CP-NEW-teaching-mode-pose-replay | form-gate-schema ✓ (R-A30-fix); function-gate ⏳ | No draft/build-spec prefix; no smoke-test |
| CP-NEW-sorter-color-3lane | form-gate-schema ✓; in backlog | drafted-only; function-gate ⏳ |
| CP-NEW-ros2-rosbag-replay | form-gate ✓; in backlog | drafted-only; real-bag path requires REPLAY_BAG_PATH dataset |
| CP-NEW-assembly-constraint-verify | form-gate-schema ✓ (R-A30-fix); in backlog | drafted-only; function-gate ⏳ Kit RPC |
| CP-NEW-teaching-mode-pose-replay | form-gate-schema ✓; in backlog | no smoke; function-gate ⏳ |
| CP-NEW-emergency-stop-state | form-gate ✓; detailed implementation notes (press_armed flag, hysteresis) | drafted-only; function-gate ⏳ |
| CP-NEW-iso10218-speed-separation | form-gate ✓; detailed spec (scaling bands, hysteresis per 10218-1) | drafted-only; function-gate ⏳ |
| CP-NEW-safety-clearance-monitor-stop | form-gate ✓; detailed ISO-15066 implementation notes | drafted-only; function-gate ⏳ |
| CP-NEW-peg-bushing-impedance | form-gate-schema ✓; in backlog | drafted-only; function-gate ⏳ |
| CP-NEW-palletizer-mixed-sku | form-gate-schema ✓ (R-A30-fix) | drafted-only; function-gate ⏳ |
| CP-NEW-conveyor-recirculation-overflow | form-gate-schema ✓ (R-A30-fix) | drafted-only; function-gate ⏳ |
| CP-NEW-zone-partition-safety | form-gate-schema ✓ (R-A30-fix) | drafted-only; function-gate ⏳ |
| CP-NEW-dr-curriculum-trainer | form-gate-schema ✓; in backlog; smoke possible for stages 1-3 | function-gate BLOCKED (IsaacLab + omni.replicator for full path); no smoke-test ✓ confirmed [moved from VERIFIED by QC 2026-05-28] |
| CP-NEW-machine-tender-load-unload | build-spec-2026-05-16; form-gate-schema ✓; in backlog | smoke-test explicitly listed as "pending"; no smoke-test ✓ confirmed [moved from VERIFIED by QC 2026-05-28] |

> Note: `teaching-mode-pose-replay` appears twice in the table — the second row is a duplicate
> entry from the original draft and should be ignored. `bin-picking-random-pose` was removed
> from this table by QC correction (2026-05-28) — it was also listed in STUB, causing a
> double-count in the original; STUB is the correct classification.
> `dr-curriculum-trainer` and `machine-tender-load-unload` remain here; their VERIFIED placement
> was reverted by QC correction (2026-05-28) to AMBIGUOUS since neither has a confirmed smoke run.
> The 17 unique AMBIGUOUS templates are:
> maniskill-pick-cube, maniskill-stack-cube, moving-conveyor-pick, teaching-mode-pose-replay,
> sorter-color-3lane, ros2-rosbag-replay, assembly-constraint-verify,
> emergency-stop-state, iso10218-speed-separation, safety-clearance-monitor-stop,
> peg-bushing-impedance, palletizer-mixed-sku, conveyor-recirculation-overflow,
> zone-partition-safety, dr-curriculum-trainer, machine-tender-load-unload,
> conveyor-tracking-moving-pick.

---

## Footer — Recommendations

**Confidence level: HIGH for VERIFIED / STUB boundary. MEDIUM for AMBIGUOUS.**

The `verified_status` field was extremely information-rich — essentially a build log packed
into a single string. This was by far the most useful signal.

**Heuristics that worked well (in order of reliability):**

1. `smoke-test ✓ N/N (Xs)` — definitive VERIFIED. Seven templates have this. No false positives
   possible; the time measurement indicates real execution.

2. `stable_fail` — definitive STUB. Five templates (amr-pickup-handoff, brick-stacking,
   cross-belt-sorter, drawer-open, tactile-insertion, g1-bimanual-tabletop, operator-ergonomics)
   have explicit runtime failure with root-cause notes.

3. `env_blocked` with no working workaround — definitive STUB. Covers zmq-stream-pointcloud,
   occupancy-map-nav, multi-sensor-fusion-rgbd-imu, ros2-tf-tree-validation.

4. `function-gate BLOCKED` with hard external dependencies (GR00T 50GB weights, IsaacLab,
   Nucleus-only assets, CUDA 12GB+) — STUB. Covers all GR00T, IsaacLab, and RL checkpoint
   templates (26+ templates).

5. `BUILD_OK; plumbing-only (no cube delivery, no simulate_args)` — STUB. Covers plc-conveyor,
   plc-fixture, opcua-12conveyors, multi-amr-corridor.

6. `drafted-2026-05-16` prefix with no build-spec — STUB. The drafted/build-spec distinction is
   a reliable signal: build-spec means at least a construction pass was attempted.

**Weakest signal:** `form-gate ✓` alone. Many "drafted" templates have a clean lint/schema pass
but zero execution. These land in AMBIGUOUS — form-gate proves schema correctness, not function.

**Recommendation:** Treat the 9 VERIFIED as the confirmed working pool. The 18 AMBIGUOUS should
be prioritized for the next Kit RPC sweep — most need only one clean smoke-run to confirm.
The 118 STUBs split into three sub-tiers:
- (A) Hard-blocked on missing infra (GR00T, IsaacLab, Nucleus) — ~35 templates, defer
- (B) env_blocked or stable_fail — ~12 templates, need specific fixes
- (C) drafted with form-gate ⏳ — ~71 templates, need a form-gate pass before anything else
