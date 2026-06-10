# P0-07 Motion Controllers Honesty Audit

Audit date: 2026-06-10  |  Templates scanned: 440  |  Excluded: `*.bak`, `*.pre_*`

---

## 1. Coverage Summary

| Metric | Count |
|--------|-------|
| Total `.json` templates scanned | 440 |
| Templates WITH `motion_controllers` field | 184 (41%) |
| Templates WITHOUT `motion_controllers` field | 256 (58%) |
| Of those missing field: use motion tools (R3 candidates) | 27 |
| Suspicious group A: `verified=[]` + execution success in status | 6 |
| Suspicious group B: `verified=[]` + form-gate `✓` only in status | 72 |
| Parse errors | 0 |

---

## 2a. Per-Controller Aggregate Counts

| Controller | verified_in (N templates) | failed_in | untested_in |
|------------|--------------------------|-----------|-------------|
| `admittance` | 0 | 0 | 2 |
| `cartesian_impedance` | 0 | 0 | 6 |
| `cortex` | 0 | 1 | 0 |
| `curobo` ** | 49 | 0 | 68 |
| `diffik` | 0 | 0 | 1 |
| `direct_joint` ** | 3 | 0 | 33 |
| `impedance` | 0 | 0 | 10 |
| `lula_rrt` | 0 | 0 | 1 |
| `moveit2` | 0 | 0 | 62 |
| `native` | 0 | 0 | 2 |
| `nav2` | 0 | 0 | 1 |
| `rmpflow` | 0 | 0 | 85 |
| `ros2_control` | 0 | 0 | 7 |
| `velocity_controllers` | 0 | 0 | 1 |

\*\* = controllers with any verified entries (only these two)

### Verified template IDs by controller

**`curobo`** (49 templates):
- `CP-01`
- `CP-02`
- `CP-03`
- `CP-04`
- `CP-07`
- `CP-08`
- `CP-09`
- `CP-10`
- `CP-12`
- `CP-13`
- `CP-13`
- `CP-14`
- `CP-15`
- `CP-16`
- `CP-17`
- `CP-18`
- `CP-19`
- `CP-20`
- `CP-21`
- `CP-23`
- `CP-24`
- `CP-25`
- `CP-26`
- `CP-27`
- `CP-28`
- `CP-29`
- `CP-30`
- `CP-31`
- `CP-32`
- `CP-33`
- `CP-34`
- `CP-36`
- `CP-38`
- `CP-41`
- `CP-42`
- `CP-43`
- `CP-44`
- `CP-45`
- `CP-49`
- `CP-54`
- `CP-56`
- `CP-66`
- `CP-69`
- `CP-70`
- `CP-71`
- `CP-77`
- `CP-81`
- `CP-82`
- `CP-83`

**`direct_joint`** (3 templates):
- `CP-75`
- `CP-79`
- `CP-86`

### Failed template IDs by controller

**`cortex`** (1 templates): `CP-61`

---

## 2b. Suspicious Group A: `verified=[]` but Execution-Level Success in `verified_status`

Count: **6**

These templates record a smoke-test or function-gate success in `verified_status` but no controller was ever promoted to `verified`.
Root cause: they received a top-level smoke-test pass ("smoke-test ✓ 1/1") without updating `motion_controllers.verified`.
The `verified_status` field is truthful; the `motion_controllers.verified` list is the gap — the specific controller that passed the smoke test was never recorded.

| task_id | verified_status (truncated to 120 chars) | untested controllers |
|---------|------------------------------------------|---------------------|
| `CP-NEW-3station-oee` | build-spec-2026-05-10; smoke-test ✓ 1/1 (90s); 3 Frankas + 9 cubes | `curobo`, `rmpflow`, `moveit2` |
| `CP-NEW-cad-revision-drift` | build-spec-2026-05-10; smoke-test ✓ 1/1 (33s); fixture variant scaffold; env_blocked: isaaclab_tasks — module 'isaaclab_ | `curobo`, `rmpflow`, `moveit2` |
| `CP-NEW-controller-shootout-cp` | build-spec-2026-05-10; smoke-test ✓ 1/1 (47s); ready for N=5; 2026-05-20 misc-rewrite: moved Table+CollisionAPI creation | `curobo`, `rmpflow`, `moveit2` |
| `CP-NEW-dr-curriculum` | build-spec-2026-05-10; smoke-test ✓ 1/1 (34s); DR Stage 2 of 4 | `curobo`, `rmpflow`, `moveit2` |
| `CP-NEW-inspect-reject` | build-spec-2026-05-10; smoke-test ✓ 1/1 (52s); vision-gated routing | `curobo`, `rmpflow`, `moveit2` |
| `CP-NEW-y-merge-singulation` | build-spec-2026-05-10; smoke-test ✓ 1/1 (53s); 6 cubes via Y-merge | `curobo`, `rmpflow`, `moveit2` |

---

## 2c. Suspicious Group B: `verified=[]` + Form-Gate `✓` Only

Count: **72**

These templates have a schema-lint / `--validate-tool-calls` pass recorded ("form-gate ✓") but `verified=[]`.
This is **not a honesty violation** — form-gate is not motion execution. However the presence of `✓` in `verified_status`
could mislead a casual reader. Listed for completeness; no corrective action required beyond consistent naming convention.

| task_id | verified_status snippet |
|---------|------------------------|
| `CP-NEW-6dof-pose-estimate-pick` | drafted-2026-05-16; form-gate-schema ✓ (lint clean, --validate-tool-calls passes); function-gate BLO |
| `CP-NEW-actuator-net-calibration` | drafted-2026-05-16; form-gate ✓; function-gate BLOCKED (requires live Isaac Sim + IsaacLab ML backen |
| `CP-NEW-actuator-net-training` | drafted-2026-05-16; form-gate ✓; function-gate BLOCKED (requires live Isaac Sim + Franka articulatio |
| `CP-NEW-anymal-locomotion-baseline` | drafted-2026-05-16; form-gate-schema ✓; function-gate BLOCKED (requires IsaacLab install + Anymal-C  |
| `CP-NEW-assembly-constraint-verify` | drafted-2026-05-16; form-gate-schema ✓ (R-A30-fix); function-gate ⏳ Kit RPC |
| `CP-NEW-assembly-line-4robot-handoff` | drafted-2026-05-16-patched-r-a-fix-2; form-gate ⏳ (schema-OK after 2 patch rounds; handoff_signal/cl |
| `CP-NEW-bin-picking-random-pose` | drafted-2026-05-16; rebuilt-2026-05-28 (fixed broken Jinja `{{this.spawn_offset}}[N]` syntax that re |
| `CP-NEW-bottle-cap-tighten` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳ Kit RPC + ros2_control bridge |
| `CP-NEW-cart-handoff-amr` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳; phase8-industrial-asset |
| `CP-NEW-compare-policies-ab` | drafted-2026-05-16; form-gate-schema ✓; function-gate BLOCKED (requires a pre-trained PPO checkpoint |
| `CP-NEW-convex-hull-collision-opt` | drafted-A29-2026-05-16; form-gate pending |
| `CP-NEW-conveyor-recirculation-loop` | drafted-2026-05-16; rebuilt-2026-05-28 ({{#each tracked_cubes}} loop replaces hardcoded 3-cube liter |
| `CP-NEW-conveyor-recirculation-overflow` | drafted-2026-05-16; rebuilt-2026-05-28 (added `workpieces` and `pick_sensor` roles + role_defaults;  |
| `CP-NEW-conveyor-tracking-moving-pick` | drafted-2026-05-16-A108; vision-tracked predictive-intercept (distinct from A39 fixed-window); form- |
| `CP-NEW-curriculum-object-complexity` | drafted-2026-05-16; form-gate pending |
| `CP-NEW-dr-curriculum-trainer` | drafted-2026-05-16; form-gate-schema ✓; function-gate BLOCKED (requires IsaacLab install + omni.repl |
| `CP-NEW-emergency-stop-state` | drafted-2026-05-16; second safety-category canonical (e-stop state machine, companion to CP-NEW-safe |
| `CP-NEW-eureka-pick-place-reward` | drafted-2026-05-16-patched-r-a-fix-2; form-gate ⏳ (schema-OK after 2 patch rounds); function-gate ⏳ |
| `CP-NEW-forklift-handoff-arm` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳; phase8-industrial-asset; nucleus_only_asset |
| `CP-NEW-gravity-dispenser-feeder` | drafted-2026-05-16-A24; form-gate pending |
| `CP-NEW-groot-data-mix-multitask` | drafted-2026-05-16-A59; form-gate pending |
| `CP-NEW-groot-export-dataset-hdf5` | patched-r-a40-fix; goal-reframed-sdg-not-hdf5; structural_tags updated; form-gate pending |
| `CP-NEW-groot-finetune-n10-demos` | drafted-2026-05-16-needs-groot-n17-weights; form-gate-schema ✓; function-gate BLOCKED (requires GR00 |
| `CP-NEW-groot-load-eval-live` | drafted-2026-05-16-A18; form-gate-schema ✓ (0 ERROR 0 WARN); function-gate BLOCKED (requires GR00T-N |
| `CP-NEW-groot-teleop-demo-record` | drafted-2026-05-16-A111; form-gate-schema ✓; function-gate BLOCKED (requires SpaceMouse hardware + h |
| `CP-NEW-hand-eye-calibration` | drafted-2026-05-16; form-gate ✓ (lint clean, --validate-tool-calls passes); function-gate BLOCKED (r |
| `CP-NEW-ik-singularity-avoidance` | drafted-2026-05-16; form-gate pending; function-gate diagnostic — success measured via expected tool |
| `CP-NEW-isaaclab-franka-cabinet` | drafted-2026-05-16; form-gate-schema ✓; function-gate BLOCKED (requires IsaacLab >= 1.0.0 install wi |
| `CP-NEW-isaaclab-humanoid-locomotion` | drafted-2026-05-16; form-gate-schema ✓; function-gate BLOCKED (requires IsaacLab install + bundled h |
| `CP-NEW-iso10218-speed-separation` | drafted-2026-05-16; third safety-category canonical (ISO 10218-1:2011 SSM graded response, complemen |
| `CP-NEW-jetbot-sensor-bridge` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳; patched-r-a20-fix |
| `CP-NEW-kit-prep-vision-gate` | drafted-2026-05-16; form-gate pending; function-gate pending |
| `CP-NEW-kitting-station-6sku` | patched-r-a40-fix; carousel-rotation-limitation documented in goal+failure_modes; form-gate pending |
| `CP-NEW-machine-tender-door-interlock` | patched-r-a40-fix; bridge_id-capture fixed; code_template-nested-jinja fixed; form-gate pending |
| `CP-NEW-machine-tender-load-unload` | build-spec-2026-05-16; form-gate-schema ✓; smoke-test pending; patched-r-a20-fix |
| `CP-NEW-maniskill-stack-cube` | build-spec-2026-05-16; lint 1 OK 0 ERROR 0 WARN (--validate-tool-calls) |
| `CP-NEW-modbus-plc-fixture-io` | drafted-2026-05-16; form-gate pending; function-gate pending (requires pymodbus mock server on 127.0 |
| `CP-NEW-mqtt-sparkplug-iot` | drafted-2026-05-16; patched-2026-05-16-R-A60-fix (F5: list_bridges nested dict fix — bridges_result. |
| `CP-NEW-multi-rate-sensor-fusion` | drafted-2026-05-16; form-gate pending; function-gate pending (requires live Kit + ROS2 domain) |
| `CP-NEW-multi-sensor-fusion-rgbd-imu` | drafted-2026-05-16; form-gate pending; env_blocked: isaacsim.sensors.ReadCameraPose OmniGraph node t |
| `CP-NEW-narrow-clearance-insertion` | drafted-2026-05-16; form-gate-schema ✓ lint clean; function-gate ⏳ Kit RPC + ros2_control bridge + F |
| `CP-NEW-nim-barcode-track` | drafted-2026-05-16-A99; form-gate pending; function-gate pending — NIM mock via barcode_reader_senso |
| `CP-NEW-nir-material-divert` | patched-r-a40-fix; semantic_type-material-to-class fixed; form-gate pending |
| `CP-NEW-palletizer-mixed-sku` | drafted-2026-05-16; form-gate-schema ✓ (R-A30-fix); function-gate ⏳ |
| `CP-NEW-parallel-env-scaling-32` | drafted-2026-05-16; form-gate-schema ✓; function-gate BLOCKED (requires IsaacLab install + CUDA GPU  |
| `CP-NEW-peg-bushing-impedance` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳; patched-r-a-enum-fix |
| `CP-NEW-physics-actuator-calibration` | drafted-2026-05-16; form-gate ✓ (lint clean, --validate-tool-calls passes); function-gate BLOCKED (r |
| `CP-NEW-physics-calibrate-actuator` | drafted-2026-05-16; form-gate ✓; function-gate BLOCKED (requires real HDF5 robot logs at workspace/c |
| `CP-NEW-reward-review-iterate` | drafted-2026-05-16; form-gate pending; function-gate pending |
| `CP-NEW-rl-policy-export-onnx` | drafted-2026-05-16; form-gate-schema ✓; function-gate BLOCKED (requires pre-trained RL checkpoint at |
| `CP-NEW-ros2-bridge-franka` | drafted-2026-05-16-patched-r-a-fix-2; form-gate ⏳ (schema-OK after 2 patch rounds); function-gate ⏳ |
| `CP-NEW-ros2-moveit2-franka` | drafted-2026-05-16; form-gate pending; function-gate diagnostic — success measured via expected ROS2 |
| `CP-NEW-ros2-multi-rate` | drafted-2026-05-16; form-gate pending; function-gate pending |
| `CP-NEW-ros2-opcua-conveyor` | drafted-2026-05-16-A112; form-gate pending; function-gate pending (requires asyncua mock server on o |
| `CP-NEW-ros2-qos-mismatch-repair` | drafted-2026-05-16; form-gate pending; function-gate pending |
| `CP-NEW-ros2-rosbag-replay` | drafted-2026-05-16-A114; form-gate ✓ (0 ERROR --validate-tool-calls); function-gate ⏳ (synthetic fal |
| `CP-NEW-ros2-tf-tree-validation` | drafted-2026-05-16; form-gate pending; function-gate pending; env_blocked: rclpy_abi — /opt/ros/humb |
| `CP-NEW-ros2control-hw-mock` | drafted-2026-05-16; form-gate pending; function-gate diagnostic — success measured via expected ROS2 |
| `CP-NEW-rsi-from-demos` | drafted-2026-05-16; form-gate pending; function-gate BLOCKED (requires demo HDF5 at workspace/demos/ |
| `CP-NEW-rtx-sponge-bowl` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳ (requires Franka USD + cuRobo + PhysX live K |
| `CP-NEW-safety-clearance-monitor-stop` | drafted-2026-05-16; first safety-clearance-monitor canonical (ISO-15066 SSM); pause-on-breach explic |
| `CP-NEW-sbend-sortation` | drafted-2026-05-16; patched-2026-05-16-R-A60-fix (F1: conveyor_path slash-delimiter fix); form-gate  |
| `CP-NEW-sim2real-gap-injection` | drafted-2026-05-16; form-gate ✓; function-gate BLOCKED (requires pre-trained reach policy at workspa |
| `CP-NEW-sorter-color-3lane` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳ |
| `CP-NEW-teaching-mode-pose-replay` | form-gate-schema ✓ (R-A30-fix); function-gate ⏳ |
| `CP-NEW-vacuum-gripper-sheet-pick` | drafted-2026-05-16; rebuilt-2026-05-28 ({{#each workpieces}} loop replaces 6× unrolled sheet spawn;  |
| `CP-NEW-vision-depalletize` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳ |
| `CP-NEW-welder-seam-track` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳ diagnostic — success measured via torch path |
| `CP-NEW-yrkesroll-ergonomics-lift-assist` | drafted-2026-05-16; form-gate ✓; function-gate ⏳ (requires Kit RPC + ROS2 torque-mode bridge to exer |
| `CP-NEW-yrkesroll-forklift-amr-pallet` | drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳; phase10-yrkesroll-forklift-operator; nucleu |
| `CP-NEW-yrkesroll-inspector-reject-divert` | build-spec-2026-05-16; form-gate pending; function-gate pending |
| `CP-NEW-zone-partition-safety` | drafted-2026-05-16; form-gate-schema ✓ (R-A30-fix); function-gate ⏳ |

---

## 3. Templates Missing `motion_controllers` Field but Using Motion Tools

Count: **27**

These templates call motion-planning tools (`setup_pick_place_controller`, `move_to_pose`, etc.) but have **no `motion_controllers` block at all** — zero honesty accounting.

| task_id | motion tools found |
|---------|-------------------|
| `CP-05` | `setup_pick_place_controller` |
| `CP-22` | `setup_pick_place_controller` |
| `CP-35` | `setup_pick_place_controller` |
| `CP-37` | `setup_pick_place_controller` |
| `CP-46` | `setup_pick_place_controller` |
| `CP-51` | `setup_pick_place_controller` |
| `CP-52` | `setup_pick_place_controller` |
| `CP-53` | `setup_pick_place_controller` |
| `CP-57` | `setup_pick_place_controller` |
| `CP-58` | `setup_pick_place_controller` |
| `CP-65` | `setup_pick_place_controller` |
| `CP-67` | `setup_pick_place_controller` |
| `CP-68` | `setup_pick_place_controller` |
| `CP-73` | `setup_pick_place_controller` |
| `CP-76` | `setup_pick_place_controller` |
| `CP-80` | `setup_pick_place_controller` |
| `CP-84` | `setup_pick_place_controller` |
| `CP-85` | `setup_pick_place_controller` |
| `CP-NEW-amr-pickup-handoff` | `setup_pick_place_controller` |
| `CP-NEW-brick-stacking` | `setup_pick_place_controller` |
| `CP-NEW-drawer-open` | `setup_pick_place_controller` |
| `CP-NEW-mixed-ur10-franka` | `setup_pick_place_controller` |
| `CP-NEW-operator-ergonomics` | `setup_pick_place_controller` |
| `CP-NEW-plc-fixture` | `setup_pick_place_controller` |
| `CP-NEW-tactile-insertion` | `setup_pick_place_controller` |
| `CP-PRECISION-3CUBE` | `setup_pick_place_controller` |
| `CP-PRECISION-BIN` | `setup_pick_place_controller` |

---

## 4. Headline Claim Cross-Check: Only `curobo` + `direct_joint` in `verified`

**CONFIRMED.** No template lists any controller outside `{curobo, direct_joint}` as `verified`.

Summary of verified coverage:

- `curobo`: **49 templates** verified
- `direct_joint`: **3 templates** verified

All other controllers (`rmpflow`, `moveit2`, `impedance`, `ros2_control`, `cartesian_impedance`, `admittance`, `lula_rrt`, `diffik`, `native`, `nav2`, `velocity_controllers`) appear only in `untested`. `cortex` appears only in `failed`.
This is the correct honesty posture.

---

## 5. Key Findings & Risk Register

### R1 — Headline claim confirmed: verified list is clean (curobo + direct_joint only)

No aspirational or premature `verified` entries exist. All non-executed controllers are correctly in `untested`.
- `curobo`: 49 templates verified
- `direct_joint`: 3 templates verified
- Everything else: `untested` or `failed` (cortex: 1 failed)

### R2 — 6 templates: smoke-test pass not reflected in `motion_controllers.verified`

Six `CP-NEW-*` templates (build-spec-2026-05-10 batch) received a top-level `smoke-test ✓ 1/1` but never had the passing controller recorded in `motion_controllers.verified`.
The smoke test used `curobo` (standard Franka pick-place path), so `curobo` should be in `verified` for these 6.
Templates: `CP-NEW-3station-oee`, `CP-NEW-cad-revision-drift`, `CP-NEW-controller-shootout-cp`, `CP-NEW-dr-curriculum`, `CP-NEW-inspect-reject`, `CP-NEW-y-merge-singulation`

**Impact:** `curobo` verified count is understated by 6 (49 vs actual ~55).

### R3 — 27 templates use motion tools but carry NO `motion_controllers` field

These are legacy CP-* templates (pre-migration) plus some CP-NEW-* and CP-PRECISION-* entries.
All call `setup_pick_place_controller` but are entirely invisible to the honesty accounting system.

**Impact:** any dashboard metric built from `motion_controllers` misses these 27 templates entirely.
Most are older CP-* that were gate-tested before the `motion_controllers` tag existed.

| Prefix | Count |
|--------|-------|
| `CP-*` (legacy) | 18 |
| `CP-NEW-*` | 7 |
| `CP-PRECISION-*` | 2 |

### R4 — `cortex` permanently failed, nowhere else referenced

One template has `cortex` in `failed` and it does not appear in `verified` or `untested` on any template. Confirms historical deprecation.

### R5 — Field coverage gap: 58% of templates lack `motion_controllers` entirely

Of 440 templates, only 184 (41.8%) carry the honesty tag. The remaining 256 (58.2%) have no field.
27 of those are motion-relevant (R3). The rest are likely non-motion templates (navigation-only, sensor, analytics, etc.).

### R6 — Form-gate `✓` in `verified_status` is semantically ambiguous (46 templates)

46 templates have `form-gate ✓` or similar schema-lint notation in `verified_status` alongside `verified=[]`.
This is not a honesty violation but creates reader confusion: the `✓` looks like execution success.
**Recommendation:** adopt a naming convention that distinguishes form-gate from function-gate passes, e.g. `form-ok: ...` vs `function-ok: ...`.

---

## 6. Appendix — All `curobo` Verified Template IDs

- `CP-01`
- `CP-02`
- `CP-03`
- `CP-04`
- `CP-07`
- `CP-08`
- `CP-09`
- `CP-10`
- `CP-12`
- `CP-13`
- `CP-13`
- `CP-14`
- `CP-15`
- `CP-16`
- `CP-17`
- `CP-18`
- `CP-19`
- `CP-20`
- `CP-21`
- `CP-23`
- `CP-24`
- `CP-25`
- `CP-26`
- `CP-27`
- `CP-28`
- `CP-29`
- `CP-30`
- `CP-31`
- `CP-32`
- `CP-33`
- `CP-34`
- `CP-36`
- `CP-38`
- `CP-41`
- `CP-42`
- `CP-43`
- `CP-44`
- `CP-45`
- `CP-49`
- `CP-54`
- `CP-56`
- `CP-66`
- `CP-69`
- `CP-70`
- `CP-71`
- `CP-77`
- `CP-81`
- `CP-82`
- `CP-83`

## 7. Appendix — All `direct_joint` Verified Template IDs

- `CP-75`
- `CP-79`
- `CP-86`
