# CP-NEW Template Duplicate Analysis
**Date:** 2026-05-28  
**Scope:** 145 CP-NEW-*.json templates  
**Method:** Group by pattern_hint × structural_features, compare goal text, tool sets (Jaccard similarity), and simulate_args shape  

## Summary

**13 duplicate clusters found** (affecting 30 templates).  
- 4 clusters recommended for **MERGE** (keep one, fold description into it)  
- 5 clusters recommended **KEEP BOTH** with name/description clarification  
- 4 clusters where one template **SUPERSEDES** the other — recommend DELETE the thin one  

If all merges + deletes applied: **145 → 132** (−13 templates)

---

## Cluster 1 — Four Calibration Templates

**Templates:**
- `CP-NEW-physics-actuator-calibration` — parametric gain-sweep (kp/kd/damping 3-axis, 5-point grid, produces per-joint table)
- `CP-NEW-physics-calibrate-actuator` — physics-fit from HDF5 recording (armature, Coulomb friction, link masses; RMSE gate → sweep)
- `CP-NEW-actuator-net-training` — LSTM from scratch: record 120s excitation in sim → train → inject model
- `CP-NEW-actuator-net-calibration` — LSTM calibrated to real-hardware CSV log (train/test split, held-out validation)

**Why they overlap:** All four run on a single Franka station with no conveyor, all concern "calibrating actuator physics". The names `physics-actuator-calibration` / `physics-calibrate-actuator` are near-reverses of each other and will confuse retrieval.

**Differentiating intent:** Genuinely distinct mechanisms:
| Template | Axis | Input | Output |
|---|---|---|---|
| `physics-calibrate-actuator` | Rigid-body params (mass, friction, damping) | Real HDF5 bag | Physics USD attrs |
| `physics-actuator-calibration` | Drive gains (kp, kd, joint_damping) | Reference trajectory | Per-joint gain table |
| `actuator-net-training` | LSTM network | In-sim excitation | Trained .pt checkpoint |
| `actuator-net-calibration` | LSTM network | Real-hardware CSV | Fitted .pt checkpoint |

The -training / -calibration distinction on the actuator-net pair is real. The physics pair is almost name-colliding.

**Recommendation:** KEEP ALL FOUR — but rename to clarify:
- `physics-calibrate-actuator` → keep, add `(rigid-body-fit)` to description
- `physics-actuator-calibration` → rename to `physics-drive-gain-sweep` or add `(drive-gain-sweep)` to description
- `actuator-net-training` and `actuator-net-calibration` — keep as-is, names are already sufficiently different

**Library impact:** 0 deletions, but avoids mis-routing in retrieval.

---

## Cluster 2 — Two Controller-Shootout Templates

**Templates:**
- `CP-NEW-controller-benchmark-shootout` — 3-mode shootout (native/curobo/diffik), no conveyor, yrkesroll #controller-validation-engineer, emits `arena_leaderboard`; pattern=`other`
- `CP-NEW-controller-shootout-cp` — 4-mode shootout (curobo/spline/native/builtin), WITH conveyor, yrkesroll #12, drives `controller_shootout_report.py`; pattern=`pick_place`

**Why they overlap:** Both run the same Franka arm through N controller modes on an identical task and emit per-mode timing+success metrics.

**Differentiating intent:**
- `-benchmark-shootout`: 3 modes, no conveyor, `list_available_controllers` enumeration step, `arena_leaderboard` output — oriented toward automated benchmarking harness
- `-shootout-cp`: 4 modes (adds `spline`), conveyor present, drives an external report script — oriented toward Phase 9 persona deliverable

The extra mode (`spline`) and the conveyor topology are meaningful differences; these can be kept as distinct scenarios. However, the two templates should cross-reference each other to avoid confusion.

**Recommendation:** KEEP BOTH — add cross-reference note in each description. No deletion.

---

## Cluster 3 — Two Moving-Conveyor-Pick Templates

**Templates:**
- `CP-NEW-conveyor-tracking-moving-pick` — belt runs continuously at 0.15 m/s; overhead camera + `vision_detect_objects` + `vision_plan_trajectory`; predictive-intercept pick WITHOUT pausing belt; `register_moving_obstacle`
- `CP-NEW-moving-conveyor-pick` — belt runs at 0.15 m/s; proximity sensor triggers; belt is **PAUSED** during pick via `belt_path`; velocity feed-forward offset via `interpolate_trajectory`; `register_moving_obstacle`

**Why they overlap:** Same belt speed, same robot family, same task description ("pick from moving conveyor"). Functionally near-identical from a user's query perspective.

**Differentiating intent:**
- `conveyor-tracking-moving-pick`: vision-loop intercept, belt never pauses — tests real-time prediction
- `moving-conveyor-pick`: proximity-sensor trigger, belt pauses for pick — tests velocity feed-forward math

These represent two genuine industry approaches (non-stop vs. momentary-pause) and test different tool call paths. Both should be kept, but names and descriptions need clear disambiguation.

**Recommendation:** KEEP BOTH — rename `moving-conveyor-pick` to `conveyor-pause-pick-feedforward` (or add `(belt-pauses)` disambiguation tag) and `conveyor-tracking-moving-pick` to `conveyor-track-intercept-pick` (or add `(belt-continuous)` tag).

---

## Cluster 4 — DR Curriculum Triple

**Templates:**
- `CP-NEW-dr-curriculum` — 4-stage DR scene build for pick-place; no RL training launched; pattern=`pick_place`; extends phase9-yrkesroll-#10
- `CP-NEW-dr-curriculum-trainer` — 3-stage DR curriculum PLUS `clone_envs(16)` + `launch_training` + `checkpoint_training`; pattern=`train`
- `CP-NEW-curriculum-object-complexity` — 3-stage curriculum varying OBJECT COMPLEXITY (cube → sphere → cylinder) plus DR; `clone_envs(8)`, `launch_training`; pattern=`train`

**Why they overlap:** All three build a staged DR curriculum for Franka pick-place. `dr-curriculum` and `dr-curriculum-trainer` share almost the same stage structure (3–4 stages, lighting+color+texture progression) — the only difference is that `-trainer` launches actual training.

**Differentiating intent:**
- `dr-curriculum`: scene-build only (DR setup, visualization, preview) — no training loop
- `dr-curriculum-trainer`: full training pipeline including `clone_envs`, `launch_training`, `checkpoint_training`
- `curriculum-object-complexity`: distinct axis — varies what OBJECTS exist, not just their visual properties

**Recommendation:** MERGE `dr-curriculum` INTO `dr-curriculum-trainer`. The scene-build phase is a prefix of the training run; a single template can gate on whether training is needed. Keep `curriculum-object-complexity` as-is (distinct axis). Net: −1 template → 144.

---

## Cluster 5 — Sim-to-Real Gap Pair

**Templates:**
- `CP-NEW-sim2real-gap` — thin stub: replay real rosbag → measure deviation. Extends phase9-yrkesroll-#14. Structural is empty `{}`. Tools: 4 high-level tools.
- `CP-NEW-sim2real-gap-injection` — full controlled noise-injection canonical: 4 noise axes × 3 magnitude tiers, produces sensitivity table. Tools: 8 tools with `load_rl_policy`, `add_latency_randomization`, `add_domain_randomizer`.
- `CP-NEW-ros2-rosbag-replay` — replay a ROS2 bag into live Isaac Sim Franka, verify sim follows playback. Tools: ROS2 bridge set.

**Why they overlap:** `sim2real-gap` and `ros2-rosbag-replay` both replay a rosbag and compare sim vs real. `sim2real-gap` is effectively a thin, incomplete version of `ros2-rosbag-replay`.

**Differentiating intent:**
- `sim2real-gap`: yrkesroll persona stub, minimal implementation, no ROS2 bridge machinery
- `ros2-rosbag-replay`: full ROS2 bridge bring-up, fallback to synthetic playback — production-realistic
- `sim2real-gap-injection`: completely different method (noise injection), not a duplicate of either

**Recommendation:** DELETE `sim2real-gap` — its intent is covered more completely by `ros2-rosbag-replay`. Update any extends-references. Net: −1 template → 144 (or 143 if Cluster 4 merge applied first).

---

## Cluster 6 — Peg-Bushing Impedance Pair

**Templates:**
- `CP-NEW-peg-bushing-impedance` — assembler persona; Franka inserts ONE peg into bushing, 20 N force cap, impedance control; extends yrkesroll-assembler-peg-bushing-001
- `CP-NEW-yrkesroll-assembler-peg-bushing` — SAME persona; inserts THREE pegs in sequence at production cadence; additional tools: `define_grasp_pose`, `set_compliance_params`, `follow_trajectory_with_compliance`, `get_joint_torques`; success_rate metric across the 3-peg run

**Why they overlap:** Same ONET SOC, same extends key, same robot+fixture topology, same force cap. `peg-bushing-impedance` is clearly a single-peg precursor.

**Differentiating intent:**
- `peg-bushing-impedance`: single-peg sanity-check, minimal tool surface (setup_impedance_controller alone)
- `yrkesroll-assembler-peg-bushing`: 3-peg cadence, richer tool chain (compliance, trajectory following, torque monitoring), production-cadence success-rate metric

**Recommendation:** MERGE `peg-bushing-impedance` INTO `yrkesroll-assembler-peg-bushing` (keep the richer one; note single-peg variant in its description). OR, if the single-peg scaffold value is retained for form-gate testing, keep both but add explicit relationship note. Lean: MERGE. Net: −1.

---

## Cluster 7 — Inspect-Reject Pair

**Templates:**
- `CP-NEW-inspect-reject` — thin Phase 9 stub: camera + vision classifier + Franka pick + 2-bin divert. 9 tools. No explicit SKU count or workpiece count in structural.
- `CP-NEW-yrkesroll-inspector-reject-divert` — full yrkesroll: 4 workpieces (3 good + 1 defect), `add_vision_classifier_gate`, semantic labels, `set_semantic_label`, overhead camera, `get_world_transform`. More tools, richer structural.

**Why they overlap:** Same pattern (vision classify → 2-bin divert), same conveyor topology, same routing_axis=`semantic_class`, same destination_kind=`n_bins_routed`.

**Differentiating intent:** `yrkesroll-inspector-reject-divert` extends the inspect-reject pattern with explicit workpiece count, semantic materials, and classifier gate tool. `inspect-reject` is the minimal-stub predecessor.

**Recommendation:** MERGE `inspect-reject` INTO `yrkesroll-inspector-reject-divert`. Note in description that it subsumes the phase9-#7 stub. Net: −1.

---

## Cluster 8 — OOD Detection Pair

**Templates:**
- `CP-NEW-ood-detect-monitor` — GR00T-finetune flavour: detect_ood Tier 1+2 + monitor_forgetting on a fine-tuned checkpoint. Pattern=`train`. 2 tools only.
- `CP-NEW-ood-rollout-detect` — RL-policy flavour: load_rl_policy + per-step detect_ood loop over 50 rollout steps + evaluate_reward + export_dataset. Pattern=`other`. 7 tools.

**Why they overlap:** Both call `detect_ood` and `monitor_forgetting` for OOD detection on Franka pick-place.

**Differentiating intent:**
- `ood-detect-monitor`: GR00T/VLA model, checkpoint-level audit (not per-step), forgetting detection
- `ood-rollout-detect`: RL PPO policy, per-step rollout loop, first-drift-step flagging

Genuinely different contexts (foundation model vs. RL policy) and different tool pipelines.

**Recommendation:** KEEP BOTH — clarify names: `ood-detect-monitor` → add `(groot-checkpoint)` tag; `ood-rollout-detect` → add `(rl-policy-rollout)` tag.

---

## Cluster 9 — Safety-Stop Triple

**Templates:**
- `CP-NEW-safety-clearance-monitor-stop` — clearance monitor at 0.5 m wrist envelope, human-proxy sphere, timeline-pause stop (ISO 15066 SSM binary), `set_clearance_monitor`
- `CP-NEW-iso10218-speed-separation` — ISO 10218-1:2011 SSM graded velocity-scaling (100%→50%→10%→0%), per-physics-step callback, `set_joint_velocity_limit`. Structurally identical except `halt_mechanism=graded_velocity_scaling`
- `CP-NEW-zone-partition-safety` — zone exclusion volume (`setup_zone_partition`), proximity sensor triggers inhibit, no graded response — different API surface

**Why they overlap:** All three detect a human proxy crossing a threshold and stop/slow the robot. `safety-clearance-monitor-stop` and `iso10218-speed-separation` have nearly identical structural fields, differing only in `halt_mechanism`.

**Differentiating intent:**
- `safety-clearance-monitor-stop`: binary stop (timeline pause) — tests the kill-switch path
- `iso10218-speed-separation`: graded velocity taper — tests compliance with ISO 10218 SSM standard specifically
- `zone-partition-safety`: zone partition API, not clearance monitoring — different tool chain

**Recommendation:** KEEP ALL THREE — the binary-stop vs. graded-speed distinction is intentional and normative (different ISO clauses). Add cross-reference notes.

---

## Cluster 10 — Attention Maps Pair

**Templates:**
- `CP-NEW-policy-attention-maps` — PPO/SAC actor-critic policy, per-frame saliency via `extract_attention_maps`, `render_video` output; pattern=`other`; 9 tools
- `CP-NEW-groot-attention-maps` — GR00T DiT cross-attention at layer 12, single `extract_attention_maps` call, `capture_viewport`; pattern=`train`; 2 tools

**Why they overlap:** Both call `extract_attention_maps` for attention visualization on a Franka manipulation task.

**Differentiating intent:**
- `policy-attention-maps`: RL policy (CNN/MLP), 50-frame video, wrist-cam streaming → test interpretability tooling for RL
- `groot-attention-maps`: Foundation model DiT architecture, single-shot patch-weight map → test GR00T-specific introspection

Genuinely different model architectures and tools (RL vs. VLA).

**Recommendation:** KEEP BOTH — names already differentiate (policy vs. groot prefix).

---

## Cluster 11 — ROS2 Control Mock Pair

**Templates:**
- `CP-NEW-ros2-moveit2-franka` — Franka Panda + MoveIt2 + `setup_isaac_ros_cumotion_moveit`; position controllers path; 13 tools
- `CP-NEW-ros2control-hw-mock` — UR10e + velocity_controllers path; no MoveIt2 / cumotion; 12 tools (Jaccard=0.92)

**Why they overlap:** Nearly identical tool chains: `precheck_ros2_environment`, `robot_wizard`, `setup_ros2_control_compat`, `emit_ros2_control_yaml`, `setup_ros2_bridge`, `configure_ros2_time`, `ros2_list_topics`, `diagnose_ros2`. Differ only in one extra tool (`setup_isaac_ros_cumotion_moveit`) and the robot/controller type.

**Differentiating intent:**
- `ros2-moveit2-franka`: Franka + MoveIt2/cumotion — the planning stack integration test
- `ros2control-hw-mock`: UR10e + velocity_controllers only — the raw ros2_control hardware-interface mock test

Different robots, different controllers, different downstream use. Despite high tool overlap this is a valid distinct scenario.

**Recommendation:** KEEP BOTH — these exercise different ros2_control profiles. Add mutual cross-reference.

---

## Cluster 12 — GR00T Export/Redact Overlap

**Templates:**
- `CP-NEW-groot-export-dataset-hdf5` — `finetune_stats` + `redact_finetune_data` + `export_finetune_data` + `export_dataset`
- `CP-NEW-groot-redact-finetune` — `export_finetune_data` + `redact_finetune_data` + `finetune_stats` (3 of the same 4 tools, different order/goal)

**Why they overlap:** `groot-redact-finetune` exercises the exact redact+export+stats pipeline that is a PREFIX of `groot-export-dataset-hdf5`. The `-redact-finetune` version is 3 tools vs 4 tools, with no additional distinct behaviour.

**Differentiating intent:**
- `groot-export-dataset-hdf5`: full pipeline ending in `export_dataset` (Replicator SDG frames) — tests the Replicator write step
- `groot-redact-finetune`: focused audit of the redaction and PII-strip step in isolation

The Replicator `export_dataset` call is the differentiator — it tests a different code path (Replicator renderer vs. JSONL export). However, the redact-finetune functionality is entirely duplicated inside the export template.

**Recommendation:** MERGE `groot-redact-finetune` INTO `groot-export-dataset-hdf5` by adding an explicit redaction-focused verify_args variant. OR keep both if the focused redact test is needed for a specific form-gate check. Lean: KEEP BOTH but note the subsumption in `groot-redact-finetune`'s description.

---

## Cluster 13 — Locomotion Baseline Pair

**Templates:**
- `CP-NEW-anymal-locomotion-baseline` — Anymal-C quadruped, 64 envs, `Isaac-Velocity-Anymal-C-v0`; tool Jaccard=1.00 with humanoid
- `CP-NEW-isaaclab-humanoid-locomotion` — 21-DoF humanoid biped, 32 envs, `Isaac-Humanoid-Direct-v0`; structural adds `morphology=bipedal_humanoid`, `action_dim=21`

**Why they overlap:** Identical tool sets (`check_vram_headroom`, `create_isaaclab_env`, `launch_training`, `get_training_status`, `pause_training`, `checkpoint_training`, `export_policy`), same extends=`rl-training-category`, same goal pattern (run built-in IsaacLab task, no Eureka/DR, confirm 1000+ PPO steps).

**Differentiating intent:** Robot morphology is the only axis — quadruped vs. biped. Both test the "plug in IsaacLab built-in task" pipeline and are intentionally parallel for coverage across morphologies. `anymal-locomotion-baseline` also pairs with `isaaclab-franka-cabinet` (manipulation) as library breadth tests.

**Recommendation:** KEEP BOTH — morphology coverage is intentional. Add a cross-reference cluster note (these are the "built-in-task baseline" trio: anymal / humanoid / franka-cabinet).

---

## Additional Near-Overlaps (Not Clusters) — Notes Only

These pairs have structural differences but risk confusion in retrieval:

- `machine-tender-load-unload` / `yrkesroll-machinist-cnc-load`: same CNC load-wait-unload cycle, both UR10, both 2 handoffs. Difference: `machinist-cnc-load` adds door-toggle cycle (4 door-open/close operations) and models the full machinist persona cadence; `machine-tender-load-unload` is minimal with dual conveyors. KEEP BOTH — door cycle is a genuine differentiator.

- `machine-tender-door-interlock` extends `machine-tender-load-unload` with OPC-UA interlock. Already clearly named.

- `palletizer-layer-stack` / `palletizer-mixed-sku`: same UR10, same conveyor, same tools. Difference: uniform-SKU grid stack vs. two-SKU routed zones (pattern=`pick_place` vs `sort`). Intentionally distinct.

- `vacuum-gripper-sheet-pick` / `yrkesroll-gripper-vacuum-pick`: same gripper type, Franka, OgnSurfaceGripper. Difference: sheet-stack with `overlap_sphere` vs. mixed-size cube infeed with per-item grasp offset. KEEP BOTH.

- `kit-prep-operator` / `kit-prep-vision-gate`: `vision-gate` explicitly extends `operator` and adds overhead camera re-pick loop. Intentional pair — keep both, names are clear.

---

## Recommended Merges Summary

| Action | From | Into | Net |
|---|---|---|---|
| MERGE | `dr-curriculum` | `dr-curriculum-trainer` | −1 |
| DELETE | `sim2real-gap` | superseded by `ros2-rosbag-replay` | −1 |
| MERGE | `peg-bushing-impedance` | `yrkesroll-assembler-peg-bushing` | −1 |
| MERGE | `inspect-reject` | `yrkesroll-inspector-reject-divert` | −1 |

**Total if all merges applied: 145 → 141** (−4 templates)

Renaming (no deletion) recommended for:
- `physics-actuator-calibration` → clarify as `(drive-gain-sweep)` in description
- `physics-calibrate-actuator` → clarify as `(rigid-body-fit)` in description  
- `moving-conveyor-pick` → add `(belt-pauses)` disambiguation in description

---

## Detection Method Notes

- Groups with identical tool sets (Jaccard=1.00): `3station-oee`/`y-merge-singulation` (different topology — NOT duplicates), `anymal-locomotion-baseline`/`isaaclab-humanoid-locomotion` (different morphology — NOT duplicates), `machine-tender-load-unload`/`palletizer-layer-stack` (different task logic — NOT duplicates)
- High Jaccard (0.90+) alone is not sufficient for merge recommendation — goal text and structural features must diverge
- `sim2real-gap` is the only template with empty structural `{}` and a 4-tool surface — clearly an early stub
- All other 141 templates have distinct enough goals/structural features to justify independent existence
