# CP-NEW Canonical Library — Overview

**145 templates** in `workspace/templates/CP-NEW-*.json`.  
Generated as LLM expansion during the industrial-expansion track (Phases 6/8/9/10), mostly stubs. Many are structurally complete (valid JSON, full field set) but few have been function-gate verified in live Kit. Source: `scripts/qa/function_gate_*.py`.

---

## 1. Bin-Picking Variants (6)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `bin-picking-random-pose` | Franka picks 6 cubes from unstructured bin, places to outfeed | Random orientation → overlap_sphere candidate discovery + antipodal grasp sampler | pick_place |
| `bin-picking-with-flip` | Franka picks upside-down parts, re-orients before place | Required flip/re-grasp before deposit — gripper must rotate wrist | pick_place |
| `6dof-pose-estimate-pick` | 6-DoF pose estimation pipeline → grasp registration → pick | Full pose estimation stack (define_grasp_pose + pose sampler) as first-class citizen | pick_place |
| `heap-zone-unstack` | Pick topmost item from an unsorted heap (no structured bin) | Free-heap unstructured pile: no bin walls, topmost detection via overlap + BBox height | pick_place |
| `vacuum-gripper-sheet-pick` | Franka + OgnSurfaceGripper picks flat sheet/label from feeder | Vacuum suction only — thin flat workpiece, no parallel-jaw viable | pick_place |
| `vision-depalletize` | Vision-detected pallet items → divert to outfeed | Camera-guided pallet layer enumeration, not fixed source list | pick_place |

---

## 2. Conveyor / Sortation (12)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `conveyor-tracking-moving-pick` | Franka intercepts cube on running belt (no pause) | Predictive intercept: velocity feedforward + register_moving_obstacle per cycle | pick_place |
| `moving-conveyor-pick` | Variant: pick from belt without pausing | Simpler moving-pick without full predictive trajectory | pick_place |
| `conveyor-merge-vision-priority` | Two belts merge; vision assigns priority lane | Vision-priority arbitration at merge point | sort |
| `conveyor-recirculation-loop` | Failed-sort items recirculate for retry | Closed-loop recirculation: items that miss divert re-enter | sort |
| `conveyor-recirculation-overflow` | Recirculation but overflow bin when buffer full | Buffer capacity gate: overflow divert when queue saturates | sort |
| `cross-belt-sorter` | Cross-belt sorter: lateral pushers route items | Physical actuator divert model (not robot arm), push-mechanism | sort |
| `sbend-sortation` | S-bend conveyor geometry sortation | Curved belt topology: items navigate S-curve to divert lane | sort |
| `y-merge-singulation` | Y-junction singulates arriving parts into single file | Back-pressure singulation at Y-merge | sort |
| `sorter-color-3lane` | 3-lane color sorter (R/G/B → 3 bins) | 3-class color routing in parallel lanes | sort |
| `sorter-size-weight` | Sort by size OR mass (dual axis) | Mass-aware classification beyond color/label — mass sensor gate | sort |
| `barcode-scanner-divert` | Barcode scan → NIM inference → route | NIM barcode microservice drives divert decision | sort |
| `nir-material-divert` | NIR spectroscopy classifies material → divert | Spectral material ID (not vision/color) — distinct sensor modality | sort |

---

## 3. Palletizing / Stacking (4)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `palletizer-layer-stack` | UR10 builds 2×3 layer grid on pallet from infeed belt | Grid placement math + drop_targets dict dispatch + UR10 reach envelope | pick_place |
| `palletizer-mixed-sku` | UR10 sorts 2 SKU types onto same pallet, split zones | Dual-zone pallet: semantic class → color_routing → left/right zone | sort |
| `tray-stack-unstack` | UR10 destacks 5 trays, z-adaptive per pick | Z-adaptive pick height (get_world_transform between cycles) prevents gripper-in-air | pick_place |
| `brick-stacking` | Franka places single brick on baseplate (V0) | V0 stub for pyramid 3-2-1; validates single-brick place; pyramid has PhysX instability | pick_place |

---

## 4. Assembly / Insertion (8)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `assembly-constraint-verify` | Peg-in-bushing with API validation — no robot motion | Exercises setup_assembly_constraint → validate_assembly_constraint pipeline (no pick) | other |
| `assembly-line-4robot-handoff` | 4 Frankas in serial pipeline with claim-mutex handoffs | Multi-robot serial handoff: claim_mutex + handoff_signal sequencing | pick_place |
| `narrow-clearance-insertion` | 0.3 mm radial clearance peg insertion with lateral-dominant impedance | Tight clearance: lateral stiffness very low so peg shimmies in; spiral search descent | insert |
| `peg-bushing-impedance` | Franka peg into bushing with 20 N F/T cap | Single-peg impedance demo (illustrative), no production cadence | insert |
| `screw-driving-impedance` | Franka helical descent (Z+Z-rotation) to drive M3–M6 screw | Coupled translation + rotation under impedance — torque-limited tighten | insert |
| `wire-harness-route` | Franka routes rigid-segment harness through 6 clip waypoints | Ordered sequential clip waypoints; rigid proxy (not deformable) | other |
| `bottle-cap-tighten` | Franka press + 90° twist to seat bottle cap | Press + rotational seat under impedance; rotational_seat gesture | insert |
| `maniskill-peg-insertion` | ManiSkill v3 PegInsertionSide-v0 benchmark format | Benchmark-compatible metric dict {success_rate, depth_threshold, contact} | insert |

---

## 5. Vision / Inspection / QC (9)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `inspect-reject` | Vision classify → good/defect → PassBin/RejectBin | Basic 2-class vision gate (quality persona stub) | sort |
| `kit-prep-vision-gate` | Post-kitting overhead camera counts occupied slots → re-pick | Vision completeness check triggers re-pick loop | pick_place |
| `defect-sdg` | SDG pipeline generating labeled defect images | Generate training data for defect detectors specifically | other |
| `weld-seam-vision-ndt` | Vision locates weld seam for NDT scan path | Non-destructive testing: vision → scan path, not manipulation | other |
| `multi-cam-triangulation` | 3-camera stereo triangulation of object pose | Multi-view triangulation canonical (sensor geometry exercise) | other |
| `spc-sensor-stream` | Raycast gauge samples 20 workpieces; Shewhart control chart | Statistical Process Control: process-level monitoring across sequence, not per-item | other |
| `ood-detect-monitor` | Monitor inference for out-of-distribution inputs | OOD flag via distribution shift detector during live rollout | other |
| `ood-rollout-detect` | Detect OOD during RL rollout execution | Rollout-time OOD (separate from monitor at inference) | other |
| `nim-barcode-track` | NIM microservice tracks barcode across frames | NIM API call for barcode — exercises NIM inference bridge | other |

---

## 6. GR00T Foundation Model (10)

All these are advisory-mode or offline — no live robot physics required in most.

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `groot-load-eval-live` | Zero-shot baseline eval of GR00T N1.6-3B on Isaac-GR00T-PickCube | Smoke-test: VRAM check → load → evaluate 10 episodes. Pre-req before finetune | train |
| `groot-finetune-n10-demos` | LoRA finetune on 10 demos → evaluate success_rate ≥ 0.50 | Full finetune pipeline: config suggest → data mix → LoRA 5k steps → eval | train |
| `groot-teleop-demo-record` | Human teleop recording session: 5 HDF5 episodes via SpaceMouse | Recording infrastructure: robomimic schema, WebSocket bridge, validate HDF5 | other |
| `groot-export-dataset-hdf5` | Redact + export JSONL corpus + SDG frames to dir | Data privacy + export plumbing validation (SDG output, not GR00T HDF5) | train |
| `groot-redact-finetune` | Redact PII/keys from raw teleop JSONL before export | Privacy gate only — exercises redact → stats pipeline | train |
| `groot-data-mix-multitask` | suggest_data_mix for 3-task corpus → sampling schedule | Multi-task continual-learning data mix recommendation | train |
| `groot-eval-harness-ntask` | Evaluate 5 canonical GR00T tasks → compare_policies aggregate | N-task sweep harness (vs single-task load-eval-live) | train |
| `groot-forgetting-monitor` | Analyze checkpoint for VQA regression + attention maps | Standalone forgetting audit without requiring training run | train |
| `groot-suggest-config` | Auto-suggest LoRA hyperparams for RTX 5070 + 10 demos | Advisory-only config recommendation (no training) | train |
| `groot-attention-maps` | Extract DiT attention maps from failed pick — visualise patch weights | GR00T interpretability: which visual patches drove failure | train |

---

## 7. RL Training / Domain Randomization (13)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `curriculum-object-complexity` | 3-stage progressive DR curriculum: cube → +sphere → +mesh | Object-complexity curriculum gated by analyze_randomization | train |
| `dr-curriculum` | Generic DR curriculum (short/stub) | Short stub version | train |
| `dr-curriculum-trainer` | Structured DR curriculum with training loop | More complete DR trainer with launch_training integration | train |
| `cloned-env-rl-scaffold` | clone_envs scaffold for parallel RL — minimal base | Minimal clone_envs setup canonical (not task-specific) | train |
| `rl-clone-env` | clone_envs + launch_training pattern | clone_envs invocation as distinct canonical from scaffold | train |
| `parallel-env-scaling-32` | 32-env Franka reach: measure FPS throughput | Throughput benchmark — sim-step FPS, not policy learning | train |
| `rl-correlated-dr-baseline` | Baseline with correlated noise axes (not independent DR) | Correlated DR: axes vary together — isolates correlation effect on transfer | train |
| `rl-eureka-locomotion` | Eureka reward generation for wheeled robot locomotion | LLM-generated reward (Eureka) for locomotion — wheeled Jetbot | train |
| `rl-policy-export-onnx` | Export trained policy to ONNX for deployment | Policy export pipeline: train → checkpoint → ONNX | train |
| `eureka-pick-place-reward` | Eureka reward auto-generation for Franka pick-place | LLM reward generation for manipulation (not locomotion) | train |
| `reward-review-iterate` | Inspect reward function → iterate design | Reward design feedback loop (human-in-the-loop reward engineering) | train |
| `compare-policies-ab` | A/B compare two checkpoints on the same task | Policy A vs policy B: compare_policies on fixed task | train |
| `rsi-from-demos` | Reward Shaping from Imitation (RSI) via demo replay | Demo-guided reward shaping — imitation signal bootstraps RL | train |

---

## 8. IsaacLab Built-in Tasks (4)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `anymal-locomotion-baseline` | IsaacLab Anymal-C velocity-tracking baseline (64 envs) | Quadruped frozen reward — experimental CONTROL for Eureka experiments | train |
| `isaaclab-humanoid-locomotion` | IsaacLab generic Humanoid (21-DoF) velocity-tracking (32 envs) | Bipedal balance difficulty vs quadruped; harder early training | train |
| `isaaclab-franka-cabinet` | IsaacLab FrankaCabinet drawer-open RL (32 envs) | Contact-rich articulated object manipulation, not free-space | train |
| `isaaclab-arena-lego` | IsaacLab-Arena brick-proxy sequential stack (4 bricks) | Sequential z-increment stack with IsaacLab-Arena composable spec | pick_place |

---

## 9. Actuator Calibration / Sim-to-Real (6)

Four of these are near-duplicates with distinct pipelines — easy to confuse.

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `actuator-net-training` | Record sim excitation → train LSTM actuator-net from scratch | From-scratch recording + LSTM training (no real hardware log) | train |
| `actuator-net-calibration` | Load real hardware CSV → 80/20 split → fit LSTM with held-out validation | Real-log calibration with leakage guard (episode-id split) | train |
| `physics-calibrate-actuator` | quick_calibrate fits physical constants (armature, Coulomb friction, link masses) | Parametric physical constants, not neural | train |
| `physics-actuator-calibration` | Sweep kp/kd/damping gains (3 axes × 5 grid) → validate RMSE | Control-loop GAIN tuning (not physical constants, not neural) | other |
| `sim2real-gap` | Replay real rosbag → measure joint RMSE vs sim | Rosbag replay gap measurement (single-point, no injection) | train |
| `sim2real-gap-injection` | One-axis-at-a-time noise injection sweep (4 axes × 3 tiers) | Controlled sensitivity table: isolates each noise axis independently | other |

---

## 10. Synthetic Data Generation (SDG) (4)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `scene-sdg-full-pipeline` | Full YOLOv8 SDG pipeline: 200 frames, 4 DR axes, COCO output | End-to-end SDG with benchmark_sdg throughput measurement | other |
| `sdg-class-balance-rebalance` | 3-class SDG with enforce_class_balance (strict per-frame quota) | Per-frame class quota enforcement with up-to-8 retries per frame | other |
| `sdg-differential-render-pass` | 100 paired frames: baseline + perturbed (pose frozen, DR on light/material) | Paired contrastive dataset — same pose, different illuminant/material | other |
| `sdg-multi-cam-correlated-dr` | 4-camera simultaneous capture with copula-correlated lighting DR | Multi-view with lighting correlation across cameras (warm dim stays warm across all 4) | other |

---

## 11. ROS2 Integration (8)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `ros2-bridge-franka` | Basic Franka joint_states/commands bridge at 60 Hz | Minimal ROS2 bridge smoke-test (pre-req for all others) | other |
| `ros2-moveit2-franka` | Full MoveIt2 + cumotion plugin setup for Franka | cumotion planning_pipeline YAML + OmniGraph bind | other |
| `ros2control-hw-mock` | UR10e as ros2_control velocity_controllers hardware mock | velocity_controllers branch (not joint_trajectory_controller) + UR10e | other |
| `ros2-multi-rate` | Multi-sensor bridge attempt (camera 30 Hz + joints) | Exercises multi-rate aspirations; per-sensor rate NOT actually supported | other |
| `ros2-rosbag-replay` | Replay ROS2 bag into Franka; verify tracking | Bag-replay imitation-seed harness with fallback to synthetic sequence | other |
| `ros2-qos-mismatch-repair` | Detect BEST_EFFORT vs RELIABLE mismatch → fix → verify | Before/after QoS health delta as deliverable | other |
| `ros2-tf-tree-validation` | TF tree health diagnostic — no motion commanded | Pure TF diagnostic: show_tf_tree + check_tf_health + diagnose_ros2 | other |
| `ros2-opcua-conveyor` | Bidirectional OPC-UA bridge for single conveyor (PLC cmd ↔ sim state) | Bidirectional control (vs read-only fan-out in opcua-12conveyors) | other |

---

## 12. Industrial Protocol Bridges (5)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `modbus-plc-fixture-io` | Modbus TCP bridge for 3 digital I/O points (clamp/light/speed) | Pure PLC I/O validation — no robot | other |
| `mqtt-sparkplug-iot` | MQTT Sparkplug-B bridge for 3 IoT data points | Sparkplug-B protocol specifically (not generic MQTT) | other |
| `opcua-12conveyors` | OPC-UA read-only fan-out to 12 conveyor run/stop attributes | Scale test: 12 nodes, 1 bridge — read-only | other |
| `plc-conveyor` | Modbus TCP pause/resume signal drives belt stop (<250 ms) | PLC-in-the-loop latency check on conveyor | other |
| `plc-fixture` | Modbus clamp signal gates Franka insert timing | Robot action gated on PLC I/O (not just bridge validation) | pick_place |

---

## 13. AMR / Mobile Robot (6)

| task_id | What it is | Differentiating challenge | Pattern |
|---|---|---|---|
| `amr-pickup-handoff` | Nova Carter docks → Franka loads onboard bin → Carter departs | Arm-to-AMR handoff: arm drops into moving AMR's bin | other |
| `cart-handoff-amr` | Franka places cart onto Jetbot; Jetbot navigates 1.5 m | Cart transfer via handoff:state attribute toggle | navigate |
| `forklift-handoff-arm` | Wheeled-robot proxy carries pallet → Franka depalletizes 3 items | Forklift→arm depalletize: mobile source, stationary picker | pick_place |
| `multi-amr-corridor` | 3 Nova Carter AMRs navigate corridor with avoidance | Fleet navigation collision-avoidance (stub — nav2 awareness not guaranteed) | other |
| `occupancy-map-nav` | Generate 2D occupancy map → export Nav2 PGM → navigate Carter | Full occupancy map workflow: generate → export → plan → navigate | navigate |
| `jetbot-sensor-bridge` | Jetbot multi-sensor ROS2 bridge: lidar/camera/IMU/odom + cmd_vel | Mobile robot sensor array bridge with TF chain validation | other |

---

## 14. Yrkesroll (Occupation-Anchored) — 11 core + others embedded

| task_id | ONET SOC | What it is | Differentiating challenge |
|---|---|---|---|
| `yrkesroll-assembler-peg-bushing` | 51-2099 | 3-peg sequential cadence (pick → transit → insert), success-rate metric | Production-cadence framing (vs single-peg peg-bushing-impedance) |
| `yrkesroll-assembler-snap-fit` | 51-2099 | Snap-fit clip insertion: lateral push until tactile click | Snap engagement: lateral force not vertical insert |
| `yrkesroll-ergonomics-lift-assist` | HFE | Human avatar + lift-assist robot, posture check | Ergonomics: human model + shared workspace force monitoring |
| `yrkesroll-forklift-amr-pallet` | logistics | AMR carries pallet, Franka picks, handoff signal | Forklift persona (maps to forklift-handoff-arm pattern) |
| `yrkesroll-gripper-vacuum-pick` | 51-9111 | Vacuum gripper label pick (thin flat part) | Vacuum modality canonical for operator persona |
| `yrkesroll-inspector-reject-divert` | 17-2112 | Vision classify → reject divert (quality inspector persona) | Inspector persona framing on inspect-reject pattern |
| `yrkesroll-machinist-cnc-load` | 51-3093 | UR10 load-wait-unload CNC cycle | Machine tender persona (maps to machine-tender-load-unload) |
| `yrkesroll-packer-box-seal` | 51-9111 | Pack items into box + apply lid | Pack + seal sequence |
| `yrkesroll-paint-sprayer-trajectory` | 51-9194 | UR10 follows paint-spray trajectory across panel | Continuous path motion (not point-to-point pick-place) |
| `yrkesroll-quality-tech-fixture-gauge` | 17-2112 | Raycast gauge measures fixture tolerances | SPC persona: gauge + tolerance check (not sorting) |
| `yrkesroll-welder-mig-tack` | 51-4121 | UR10 MIG tack weld at 3 seam points | Tack welding: discrete spot stops (vs seam-track continuous) |

---

## 15. Bimanual / Multi-Robot (4)

| task_id | What it is | Differentiating challenge |
|---|---|---|
| `g1-bimanual-tabletop` | Unitree G1 humanoid: both hands reach two cubes | Humanoid whole-body control (WBC) — G1 SimReady asset | pick_place |
| `roco-bimanual-assembly` | 2 Frankas: Left holds workpiece, Right fastens on top | Hold-and-fasten: shared claim-mutex on center hold zone | pick_place |
| `triple-arm-cell-handoff` | 3 Frankas in shared cell with handoff chain | 3-arm (not 2 or 4) shared workspace coordination | pick_place |
| `assembly-line-4robot-handoff` | 4 Frankas serial pipeline (also in Assembly group above) | 4-station serial with claim-mutex (see Assembly section) | pick_place |

---

## 16. Safety & Ergonomics (5)

| task_id | What it is | Differentiating challenge |
|---|---|---|
| `safety-clearance-monitor-stop` | Wrist-envelope clearance monitor → timeline pause on breach | ISO 15066 SSM: halt via timeline.pause (not E-stop) |
| `emergency-stop-state` | Boolean USD attr E-stop → drive gains zeroed | E-stop via drive_gain=0 (not timeline pause, not velocity cap) |
| `iso10218-speed-separation` | Graded velocity scaling: 1m→100%, 0.5m→50%, 0.3m→0% | Continuous graded response — unique among safety canonicals |
| `zone-partition-safety` | Exclusion zone + proximity sensor + watchdog | Zone-based (not clearance-based) inhibit |
| `operator-ergonomics` | Human Avatar + Franka shared workspace; posture check | Ergonomics specialist persona (HFE) — stub |

---

## 17. Household / Research Benchmarks (8)

| task_id | What it is | Source benchmark |
|---|---|---|
| `maniskill-pick-cube` | ManiSkill2 PickCube-v0 parity via run_arena_benchmark | ManiSkill2 / IsaacLab-Arena |
| `maniskill-stack-cube` | ManiSkill2 StackCube-v0 — place_on_top_of spatial resolver | ManiSkill2 |
| `maniskill-peg-insertion` | ManiSkill v3 PegInsertionSide-v0 format (also in Assembly) | ManiSkill v3 |
| `robohive-door-open` | RoboHive door-open (revolute joint) | RoboHive |
| `robohive-relocate-pen` | RoboHive pen relocation (dexterous regrasp) | RoboHive |
| `rtx-sponge-bowl` | Open X-Embodiment sponge→bowl (RT-1 task 0042) | RT-X / OXE |
| `oxe-sweep-into-dustpan` | Open X-Embodiment sweep-into-dustpan | OXE |
| `turn-faucet` | Turn faucet handle (revolute dexterous grasp) | Generic household |

---

## 18. Specialized / Hardware / Tooling (13)

| task_id | What it is | Why it's there |
|---|---|---|
| `drawer-open` | Primitive-built cabinet drawer, spline waypoint pull | Waypoint-based articulated object (vs IsaacLab RL cabinet) |
| `tactile-insertion` | Tactile-sensor-guided peg insertion | Tactile sensor modality (not F/T wrist) |
| `teaching-mode-pose-replay` | Programmatic waypoint capture + replay (no human) | Waypoint record-replay without SpaceMouse/human input |
| `adaptive-3finger-gripper` | 3-finger adaptive gripper grasps irregular object | Non-parallel-jaw gripper modality |
| `tool-changer-swap` | UR10 swaps end-effector at tool-changer dock | Tool-change: detach EE + attach new EE mid-task |
| `hand-eye-calibration` | Eye-in-hand + eye-to-hand calibration pipeline | Camera-robot extrinsic calibration (not motion task) |
| `ik-singularity-avoidance` | Plan near-singular configuration, measure condition number | Singularity diagnostics: check_singularity in planning loop |
| `gravity-dispenser-feeder` | Gravity dispenser drops parts → singulation → pick | Asynchronous part arrival from bulk feeder |
| `label-applicator-pose` | Vacuum pick label → press onto workpiece ±2 mm / ±2° | Tight-tolerance pose-critical vacuum placement |
| `machine-tender-load-unload` | UR10 load blank → wait machining dwell → unload | Load-wait-unload CNC cycle with dual conveyor |
| `machine-tender-door-interlock` | OPC-UA door signal gates robot motion (safety interlock) | OPC-UA boolean interlock pattern (extends machine-tender) |
| `kitting-station-6sku` | Rotary carousel presents 6 SKUs → UR10 kits | create_rotary_table first use; static template for index 0 only |
| `welder-seam-track` | UR10 follows weld seam with vision correction | Continuous seam tracking with vision_plan_trajectory feedback |

---

## 19. Diagnostics / Benchmarking / Physics Tools (8)

| task_id | What it is | Why it's there |
|---|---|---|
| `controller-benchmark-shootout` | native vs curobo vs diffik on same task (3-controller) | Controller architecture comparison — yrkesroll validation eng |
| `controller-shootout-cp` | 4-mode controller shootout (curobo/spline/native/builtin) | Earlier stub; overlaps with above (4 modes not 3) |
| `convex-hull-collision-opt` | check_collision_mesh → compute_convex_hull → simplify → fix | Collision mesh optimization pipeline (first library use) |
| `planning-10step-retry` | 3-block tower build: 10 steps, sub-goal checks, execute_with_retry | Long-horizon orchestration with structured retry — first in library |
| `multi-rate-sensor-fusion` | setup_multi_rate + F/T wrist + ROS2 bridge | Multi-rate VecEnv wrapper first use — sensor fusion setup |
| `multi-sensor-fusion-rgbd-imu` | RGB 30 Hz + depth 30 Hz + IMU 200 Hz fusion → fused < best-modality variance | Tri-modal sensor fusion (not just multi-rate; modality averaging) |
| `3station-oee` | 3-station serial line with OEE metric emitter | Manufacturing engineer persona with OEE logging |
| `cad-revision-drift` | Same canonical built twice (rev_a vs rev_b geometry) | CAD revision drift test: controller robustness to geometry changes |

---

## 20. Other Misc (3)

| task_id | What it is | Why it's there |
|---|---|---|
| `zmq-stream-pointcloud` | ZMQ PUB stream from synthetic LiDAR → verify subscriber | Non-ROS2 sensor bridge (ZMQ); exercises Phase 6 bridge variant |
| `policy-attention-maps` | RL policy (PPO/SAC, not GR00T) saliency map → MP4 overlay | Generic RL interpretability (vs groot-attention-maps for VLA) |
| `kit-prep-operator` | Franka picks 5 distinct parts from 5 bins → 5-slot kit tray | 5-source kitting baseline (no vision gate; see kit-prep-vision-gate) |

---

## Footer: Observations & Gaps

**Distribution:** Heavily weighted toward RL/training (40+), ROS2/integration (13), assembly/insertion (8), and yrkesroll stubs (11). Conveyor/sort and bin-picking are well-covered. Household manipulation has thin coverage (8 templates, mostly benchmark parity checks). Multi-robot is sparse (4 bimanual, one 4-arm).

**Stub depth:** GR00T templates (10) are structurally complete with realistic failure_modes but most require NVIDIA Nucleus assets or HuggingFace weights not locally available. Yrkesroll templates tend to be shorter with less code_template detail than the A-series canonicals they duplicate.

**Near-duplicates:**
- `physics-calibrate-actuator` vs `physics-actuator-calibration` vs `actuator-net-training` vs `actuator-net-calibration` — four distinct calibration philosophies but confusable names
- `controller-benchmark-shootout` vs `controller-shootout-cp` — overlapping scope, different mode count (3 vs 4)
- `dr-curriculum` vs `dr-curriculum-trainer` — stub vs more complete version
- `sim2real-gap` vs `sim2real-gap-injection` — single-point vs sensitivity sweep (correctly distinct)
- `conveyor-tracking-moving-pick` vs `moving-conveyor-pick` — both moving-belt picks; former is more elaborated with predictive intercept

**Verified vs unverified:** Only the A-series canonicals (Phase A pipeline) have function-gate verification. Most CP-NEW templates are generated scaffolding — treat `failure_modes` fields as design intent, not verified behavior. Check `scripts/qa/function_gate_*.py` for what has actually been run.

**Missing domains:** No thermal/camera-shutter simulation, no FEM/deformable object (deformable wire intentionally excluded as PhysX-unstable), no multi-layer SDG pipelines beyond 4-camera. Industrial arc welding, CNC machining physics, and fluid dispensing are represented only by stubs.
