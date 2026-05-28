# Tool-Library Gap Inventory — 2026-05-28

**Scope**: Audit LLM tool library against the 158-template `CP-NEW-*` canonical library and the 326 other templates (A-, AD-, AL-, AM-, C-, D-, E-, F-, FX-, G-, J-, K-, L-, M-, P-, R-, S-, T-, Y- prefixes).

**Method**: Reverse-engineered tool registry from `handlers/_dispatch.py` + per-module `register(data, codegen)` calls. Cross-referenced with `tools_used` arrays in every `workspace/templates/*.json`. Identified gaps via cluster `tools_used` vs registered set, plus per-cluster `verified_status` blockers.

---

## 1. Inventory Table — Tool Category to Handler Module

| Category | Module | Data-handlers | Codegen | Notes |
|---|---|---|---|---|
| Scene authoring (prims, references, materials) | `scene_authoring.py` | 41 | 39 | Biggest module; baseline USD ops |
| Pick-place dispatchers (native/builtin/curobo) | `pick_place.py` | 0 | 2 | Code-only; `_handle_setup_pick_place_*` actually lives in `robot.py` |
| Robot setup (wizards, joints, WBC, kinematics) | `robot.py` | 31 | 32 | Largest module 6978 lines |
| Sensors (raycast, overlap, F/T, barcode, NIR) | `sensors.py` | 9 | 5 | Pre-built composites for industrial |
| Physics (gains, compliance, materials, scene cfg) | `physics.py` | 19 | 17 | Includes `setup_impedance_controller` / `setup_admittance_controller` |
| Vision (Gemini-ER, detect, plan, classifier gate) | `vision.py` | 17 | 8 | LLM-driven; no SAM2/CLIP local fallback |
| SDG (DR, COCO/YOLO, balance) | `sdg.py` | 3 | 10 | Heavy codegen, light runtime |
| Training (IsaacLab, GR00T, Eureka, actuator-net) | `training.py` | 34 | 10 | Includes all GR00T evaluate/finetune/load tools |
| ROS2 diagnostics (TF, QoS, control yaml) | `ros2.py` | 3 | 6 | Augmented by 11 ros2-live + 13 bridge tools |
| Compliance (impedance/admittance lifecycle) | `compliance.py` | 5 | 0 | Lifecycle-only; setup lives in `physics.py` |
| Contact-sequence execution | `contact_sequence.py` | 1 | 0 | Just `execute_contact_sequence_plan` (unused in any template) |
| Arena (IsaacLab-Arena variants) | `arena.py` | 1 | 3 | Mostly unused except `arena_leaderboard` |
| Animation (timeline, audio, keyframes) | `animation.py` | 0 | 5 | All codegen; rarely used |
| Rendering (cameras, viewport, HDRI, capture) | `rendering.py` | 0 | 8 | All codegen; capture handlers in vision |
| Teleop (SpaceMouse, validation, mapping) | `teleop.py` | 1 | 7 | Specialized for GR00T data collection |
| Workflow (start, edit, approve, cancel) | `workflow.py` | 15 | 0 | 100% unused in templates (all 15) |
| Resolve (spatial / semantic resolvers) | `resolve.py` | 13 | 0 | 12 of 13 are unused; only `place_on_top_of` used (2 templates) |
| Diagnostics (physics, performance, domain-gap) | `diagnostics.py` | 29 | 19 | Cloud/async also live here, 5+ unused |
| Scene blueprints (broken-scene, blueprints) | `scene_blueprints.py` | 13 | 3 | Mostly unused as standalone tools |
| **Bridges** (`bridge_tools.py`) | extern reg | 13 | 0 | Modbus, OPC-UA, MQTT Sparkplug, OpenPLC |
| **Multimodal** (`multimodal_handlers.py`) | extern reg | 6 | 0 | Layout-spec read/update/commit/apply |
| **ros-mcp live** | extern reg | 11 | 0 | Stubbed `None` when `ros-mcp` not installed |

**Totals**: ~234 data-handlers + ~174 codegen-handlers ≈ **407 unique tool names registered**. Templates reference **301 unique tools** across all 484 files; **125 registered tools are never used in any template**.

---

## 2. Coverage Matrix — Canonical Cluster vs Tool Availability

| Cluster | Templates | Coverage | Gaps |
|---|---|---|---|
| **Bin-picking** (6) | ✓ complete | `setup_pick_place_controller` + `overlap_sphere` + `define_grasp_pose` + `setup_grasp_pose_sampler` + `add_proximity_sensor` | Random-orient antipodal still depends on Gemini-ER for pose |
| **Conveyor/sortation** (12) | ✓ complete | `create_conveyor` + `register_moving_obstacle` + `setup_pick_place_controller` + vision/barcode/NIR sensors | None blocking; cross-belt sorter has no dedicated lateral-pusher tool, hand-rolled in code_template |
| **Palletizing** (4) | ✓ complete | `compute_stack_placement` + `setup_pick_place_controller` (UR10) + `create_bin` | None blocking |
| **Assembly/insertion** (8) | ⚠️ partial | `setup_impedance_controller` + `set_compliance_params` + `add_force_torque_sensor` + `setup_assembly_constraint` | **No spiral-search-descent tool** (handrolled in narrow-clearance template); no helical-screw motion tool; no snap-fit press-and-click detector |
| **Vision/QC** (9) | ⚠️ partial | `vision_detect_objects` + `vision_analyze_scene` + `vision_plan_trajectory` + `add_vision_classifier_gate` + `set_semantic_label` | Gemini quota-bound; **no SAM2/CLIP local fallback**, no 3-cam triangulation tool (handrolled), no SPC chart emitter |
| **GR00T foundation** (10) | ⚠️ runtime-blocked | `load_groot_policy` + `evaluate_groot` + `finetune_groot` + `monitor_forgetting` + `suggest_data_mix` + `suggest_finetune_config` | **No `groot_inference_step` runtime tool** (rollout-time policy.step); function-gate BLOCKED on N1.6-3B weights + HF token + 12 GB VRAM |
| **RL training** (13) | ⚠️ scaffold-only | `clone_envs` + `launch_training` + `create_isaaclab_env` + `checkpoint_training` + `get_training_status` + `pause_training` + `eureka_*` | **No `run_rollout_episode` / `step_env` / `reset_env` runtime tools** — entirely subprocess-launched, no in-process train loop |
| **IsaacLab built-ins** (4) | ⚠️ env-blocked | `create_isaaclab_env` + `launch_training` | BLOCKED on IsaacLab install + rsl_rl / skrl + Nucleus G1/Anymal asset (canonical-side, not tool-side) |
| **Yrkesroll** (11) | ✓ for 9, ⚠️ for 2 | Pattern: `robot_wizard` + `setup_pick_place_controller` + role-specific composite | Ergonomics (HFE) **needs OperatorAvatar SimReady asset**; forklift needs Nucleus asset (workaround=wheeled_robot_proxy) |
| **Bimanual/multi-robot** (4) | ❌ partial | `setup_robot_claim_mutex` + `setup_robot_handoff_signal` + `setup_whole_body_control` (config-emitter only) | **No `setup_humanoid_pick_place` / no humanoid branch in `setup_pick_place_controller`** — only franka/ur10/ur10e/cobotta_pro_900; G1 falls back to one-arm-at-a-time fake; no `phase_id` kwarg for parallel dual-arm |
| **Safety/Ergonomics** (5) | ✓ structural | E-stop, SSM, zone-partition via `setup_zone_partition` + clearance monitor | Ergonomics blocked on avatar asset; no built-in HFE-posture-monitor tool |
| **AMR/Mobile** (6) | ⚠️ partial | `create_wheeled_robot` + `setup_nav_robot` + `navigate_to` + `generate_occupancy_map` + `export_nav2_map` + `register_moving_obstacle` | **No `setup_amr_with_manipulator` composite** — arm-on-AMR is hand-wired (no `mobile_manipulation_controller`); fleet/swarm has no `setup_fleet_coordinator` |
| **Household benchmarks** (8) | ⚠️ thin | Mostly free-form `setup_pick_place_controller` + benchmark-format eval | No `run_arena_benchmark` execution runtime in the tool layer for `maniskill-*` family; eval scoring scattered |
| **SDG** (4) | ✓ structural | `create_sdg_pipeline` + `configure_sdg` + `benchmark_sdg` + `preview_sdg` + `add_domain_randomizer` + `apply_dr_preset` + `configure_correlated_dr` + `configure_differential_sdg` + `enforce_class_balance` | env_blocked on `omni.replicator` extension |
| **ROS2 integration** (8) | ✓ + bridges | 24 ROS2-related (3 diag + 6 codegen + 11 live + 4 bridge bindings) | rclpy ABI mismatch with Kit Python; rosbag replay needs real asset |
| **Industrial bridges** (5) | ✓ complete | Modbus/OPC-UA/MQTT Sparkplug/OpenPLC `attach/detach/diagnose/pause/resume` | All bridges plumbed; templates pending live broker for function-gate |
| **Tooling/diagnostics** (8) | ✓ complete | `check_singularity` + `compute_convex_hull` + `multi_rate_sensor_fusion` etc. | None blocking |
| **Misc** (specialized hardware) | ⚠️ partial | `tool-changer-swap` uses `create_articulated_joint` + relationship; `adaptive-3finger-gripper` uses raw `set_joint_targets` | **No `swap_tool_at_changer` composite**; **no `setup_3finger_adaptive_grasp` composite** |

---

## 3. Top 10 Tool Gaps — Prioritized by Leverage

Sorted by `(templates_unlocked) × (1/effort)`. Effort scale: **S** = 1-2 days, **M** = 3-7 days, **L** = > 1 week.

### Gap 1 — `setup_humanoid_pick_place(robot_path, hand, target_path, drop_path, gait="stand")` — **L**
- **Unlocks**: 2 templates direct (`g1-bimanual-tabletop`, future H1/Figure02 canonicals), **enables entire bimanual class scale-up** (~5 future templates planned but not authored because the gap is known)
- **Why high leverage**: `setup_pick_place_controller` explicitly raises `unsupported robot_family` for non-franka/ur10/cobotta. Humanoid path is dead-end without this. WBC config-emitter exists (`setup_whole_body_control`) but is config-only, not runtime.
- **Dependencies**: Pink-IK or Pinocchio install; G1 SimReady asset (Nucleus); humanoid kinematic profile in `_WHOLE_BODY_PROFILES` table

### Gap 2 — `groot_inference_step(policy_handle, obs_dict) -> action_dict` — **M**
- **Unlocks**: 5 templates direct (`groot-load-eval-live`, `groot-finetune-n10-demos`, `groot-eval-harness-ntask`, `groot-attention-maps`, future GR00T rollouts), enables runtime VLA evaluation
- **Why**: Currently `evaluate_groot` is opaque — it runs the whole eval loop subprocess. No way to hold the policy in-process and step it per-frame. Blocks attention-map per-step extraction and any GR00T-in-the-loop canonical (GR00T as a controller, not a benchmark)
- **Dependencies**: GR00T N1.6-3B weights + HF token + 12 GB VRAM (canonical-side, but the *tool* can be authored with stub-mode fallback)

### Gap 3 — `step_env(env_handle, action) -> (obs, reward, done, info)` + `reset_env(env_handle) -> obs` + `run_rollout_episode(env, policy, max_steps)` — **M**
- **Unlocks**: 6+ RL templates (`cloned-env-rl-scaffold`, `eureka-pick-place-reward`, `parallel-env-scaling-32`, `compare-policies-ab`, `rl-correlated-dr-baseline`, `rl-policy-export-onnx`), enables Eureka reward-eval loop, enables OOD-detection in rollout
- **Why**: `launch_training` is subprocess-only. There's no way to drive an env from inside a tool-call, so policy-eval/OOD-detect/reward-iterate canonicals all become "fork subprocess, wait, parse log" instead of crisp step-eval-step loops. All 4 IsaacLab built-in templates would benefit
- **Dependencies**: IsaacLab installed; rsl_rl or skrl backend; clear handle-lifetime model (env_handle dict)

### Gap 4 — `setup_amr_with_manipulator(amr_path, arm_path, mount_offset)` + `mobile_manipulation_plan(target_pose)` — **M**
- **Unlocks**: 4-5 templates (`amr-pickup-handoff`, `forklift-handoff-arm`, `cart-handoff-amr`, future AMR-mounted-arm canonicals like medical-AMR, kitting-AMR)
- **Why**: AMR templates hand-wire the arm-on-AMR mount as raw `FixedJoint` between arm base and AMR top; no composite that handles "navigate-then-pick" coordination. `navigate_to` + `setup_pick_place_controller` exist separately but no co-planner. Mobile manipulation is a known industry-significant niche
- **Dependencies**: cuRobo (for arm), nav2-equivalent (in tools already); base→arm coordinate-frame handling

### Gap 5 — `add_sam2_segmentation_classifier(model="sam2.1-hiera-tiny")` + local CLIP fallback — **M**
- **Unlocks**: 4 templates direct (`inspect-reject`, `kit-prep-vision-gate`, `vision-depalletize`, `6dof-pose-estimate-pick`), 5+ future vision-driven sortation
- **Why**: Vision cluster currently hard-depends on Gemini-Robotics-ER (quota-limited, costs scale). SAM2 + CLIP is the local-runnable alternative — runs on RTX 5070, no API quota. Already in the `cpnew-vision-alignment.md` and `multimodal-canonical-flow.md` followups
- **Dependencies**: SAM2 weights (HF ~150 MB), CLIP weights, torch backend; vision.py already structured for plug-in classifiers

### Gap 6 — `setup_insertion_controller(strategy="spiral_search"|"helical_screw"|"snap_fit")` — **S**
- **Unlocks**: 4 templates direct (`narrow-clearance-insertion`, `screw-driving-impedance`, `bottle-cap-tighten`, `assembler-snap-fit`), unifies 4 distinct hand-rolled descent gestures
- **Why**: `narrow-clearance-insertion.thoughts` shows the spiral-search descent gesture is **hand-coded in code_template as a 10-waypoint trajectory**. Same with helical screw, snap-fit press-and-click. A single `setup_insertion_controller(strategy)` would replace ~50 lines of duplicated logic per template, plus enable a 5th `bayonet_twist` strategy template
- **Dependencies**: Already have `setup_impedance_controller` + `set_compliance_params` + `follow_trajectory_with_compliance` — this is a composite wrapping them

### Gap 7 — `setup_dual_arm_coordinator(left_arm, right_arm, mode="leader_follower"|"parallel")` + `phase_id` kwarg on `setup_pick_place_controller` — **S**
- **Unlocks**: 3 templates direct (`roco-bimanual-assembly`, `triple-arm-cell-handoff`, `assembly-line-4robot-handoff`), enables multi-robot temporal coordination
- **Why**: Current `setup_robot_claim_mutex` + `setup_robot_handoff_signal` are coarse — they gate per-cycle not per-phase. Bimanual hold-and-fasten needs Left to STAY HOLDING while Right runs full pick-place. Adding `phase_id` to controller setup lets multiple controllers coexist without aliasing
- **Dependencies**: None new — coordination layer over existing controllers

### Gap 8 — `setup_cross_belt_sorter(belt_path, lanes, divert_actuators)` — **S**
- **Unlocks**: 1 template direct (`cross-belt-sorter`), 2 future variants (`y-merge-singulation`, `sbend-sortation`)
- **Why**: Cross-belt sorter currently hand-codes lateral pusher physics with raw `apply_force` calls. A composite that wires Replicator-randomized divert actuators + per-lane occupancy sensors would unify the sortation family
- **Dependencies**: None new

### Gap 9 — `setup_swap_at_tool_changer(arm_path, dock_path, tools=[...])` + `setup_adaptive_3finger_grasp(grasp_topology="parallel"|"tripod"|"power")` — **S**
- **Unlocks**: 2 templates direct (`tool-changer-swap`, `adaptive-3finger-gripper`), enables EE-swap-mid-task canonicals (medical, manufacturing)
- **Why**: Tool-changer is a one-off hand-coded sequence; adaptive 3-finger is raw `set_joint_targets` mash. Composites would standardize and unlock multi-tool workflow templates
- **Dependencies**: None new

### Gap 10 — `run_arena_benchmark(task="maniskill:PickCube-v0", seed_list, episodes)` + `compute_benchmark_eval_dict()` — **S**
- **Unlocks**: 5 templates direct (`maniskill-pick-cube`, `maniskill-stack-cube`, `maniskill-peg-insertion`, `robohive-door-open`, `robohive-relocate-pen`), enables benchmark-parity canonicals to actually run
- **Why**: Household/benchmark templates currently invoke benchmark via free-form code_template; no shared runtime tool for "run N episodes, collect eval dict per benchmark spec". Reduces benchmark-canonical divergence
- **Dependencies**: IsaacLab-Arena install; benchmark format adapters

---

## 4. Recommended — Next 3 to Build (within 2 weeks)

Pick those with HIGH leverage AND existing-component composability (avoid new ML model deps):

### #1 — `setup_insertion_controller(strategy)` (Gap 6, **S**)
- Pure composite over existing tools, fastest ROI
- Unlocks 4 templates immediately + standardizes the entire assembly-insertion family
- No new dependency. Pattern matches `setup_pick_place_controller`'s strategy-dispatch architecture
- Concrete impact: narrow-clearance, screw-driving, bottle-cap, snap-fit all switch from 50-line hand-coded gestures to single tool-call

### #2 — `setup_humanoid_pick_place` + humanoid branch in `setup_pick_place_controller` (Gap 1, **L** but high-leverage)
- Unblocks entire bimanual/humanoid cluster which is currently `stable_fail` on principle (PICK-CONTROLLER-SKIP)
- Build as a separate handler (`setup_humanoid_pick_place`) first, then later merge into the main dispatcher
- Anchor implementation on G1 (the only humanoid with confirmed asset path); Pink-IK or basic per-arm IK as fallback
- Concrete impact: g1-bimanual-tabletop goes from `stable_fail` to runnable; enables 5+ future bimanual canonicals

### #3 — `add_sam2_segmentation_classifier` + local CLIP fallback (Gap 5, **M**)
- Eliminates the Gemini quota constraint that limits vision-driven sortation
- SAM2 weights are 150 MB, runs on the RTX 5070, no recurring API cost
- Vision module already has plug-in handler structure; this is a new model backend not a new API
- Concrete impact: 4 vision templates run on local stack; future expansion of vision-driven sortation no longer quota-bound

These three are picked because (a) all three have direct template unlocks (≥ 2 templates each), (b) none are blocked by new infrastructure beyond model downloads, and (c) they map to known cross-conversation friction (vision quota, humanoid PICK-CONTROLLER-SKIP, assembly hand-coded gestures).

---

## 5. Anti-Pattern Findings — Tools We Have But Rarely Use

**125 registered tools never used in any template.** Biggest categories:

### 5a. `resolve_*` family — **12 of 13 unused**
- `resolve_constraint_phrase`, `resolve_context_reference`, `resolve_coordinate_reference`, `resolve_count_vagueness`, `resolve_material_properties`, `resolve_prim_reference`, `resolve_relational_property`, `resolve_robot_class`, `resolve_sequence_phrase`, `resolve_size_adjective`, `resolve_skill_composition`, `resolve_success_condition`
- Only `place_on_top_of` is used (2 templates)
- Per `project_isaac_assist_typed_resolvers` memory, these were a pilot for "spatial-language → coordinates"; only `place_on_top_of` made it past pilot. Consider: deprecate or document as advisory-only

### 5b. `workflow_*` family — **15 of 15 unused**
- All workflow orchestration (`start_workflow`, `approve_workflow_checkpoint`, `edit_workflow_plan`, `cancel_workflow`, `get_workflow_status`, `list_workflows`, etc.)
- Suggests the canonical authoring pattern bypasses the workflow layer entirely. Either the templates aren't using workflows or the workflow layer is unfinished

### 5c. `cloud_*` family — **4 of 5 unused** (only `cloud_estimate_cost` used in 2)
- `cloud_launch`, `cloud_status`, `cloud_teardown`, `cloud_download_results` all unused
- Cloud-burst training/rendering scaffolding exists but no canonicals exercise it. Either revive or remove

### 5d. `arena_*` family — **2 of 3 unused**
- Only `arena_leaderboard` used (2 templates). `create_arena`, `create_arena_variant` unused
- Suggests Arena composer is incomplete or the canonicals work around it with direct env build

### 5e. Diagnostics duplicates
- `diagnose_domain_gap`, `diagnose_performance`, `diagnose_whole_body`, `diagnose_physics_error` — all registered but unused
- `diagnose_ros2` IS used (8 templates) — others may need promotion or removal

### 5f. Near-duplicate setup tools — consolidation candidates
- `setup_pick_place_controller` (141 uses), `setup_pick_place_with_vision` (rare), `setup_pick_place_ros2_bridge` (rare): the latter two look like specialized wrappers — could be options/strategies on the main tool, reducing surface area
- `vision_analyze_scene` vs `vision_detect_objects` vs `vision_bounding_boxes`: three Gemini-driven vision tools that differ mainly in output shape. Could unify into `vision_query(mode="analyze"|"detect"|"bbox")`
- `create_conveyor` (107 uses) vs `create_conveyor_track` (rare): probably duplicate — verify

---

## 6. Long-Tail Backlog — Low ROI per Effort

Gaps that exist but aren't worth filling soon:

- **`apply_force` runtime exposure** — registered, never used; physics injection has security implications, leave it
- **`debug_draw` / `debug_graph` / `explain_graph`** — debug helpers, no template needs them
- **`add_default_light`** — covered by `create_prim` with light schemas
- **`merge_meshes` / `compute_convex_hull` / `simplify_mesh`** — geometry processing; one template uses `compute_convex_hull` (collision-opt), rest are pre-emptive
- **`build_scene_from_blueprint` / `generate_scene_blueprint` / `validate_scene_blueprint`** — blueprint compiler chain never adopted; templates author scenes directly
- **`export_scene_package` / `export_stage` / `export_template`** — export tooling, no canonical exercises round-trip
- **`load_payload` / `flatten_layers` / `set_variant` / `list_variant_sets` / `list_payloads`** — advanced USD layer-ops; canonicals stay in single-stage
- **`download_asset` / `list_local_files`** — pre-flight asset management, not exercised by templates
- **`watch_changes` / `list_opened_stages`** — IDE/inspection utilities
- **`get_*` lookups (12+ unused)** — `get_active_state`, `get_angular_velocity`, `get_kind`, `get_inertia`, `get_center_of_mass`, `get_articulation_mass`, etc. — read-side utility flood; templates use a smaller working set (`get_world_transform`, `get_joint_positions`, `get_joint_torques`, `get_gripper_state`)

**Recommendation**: Leave these registered (low cost to keep, may be useful for future templates) but skip new long-tail work. Focus net-new tool effort on the Top 10 gaps section.

---

## Footer

- **Inventory file**: `/home/anton/projects/Omniverse_Nemotron_Ext/docs/notes/2026-05-28-tool-gap-inventory.md` (this file)
- **Companion overview**: `/home/anton/projects/Omniverse_Nemotron_Ext/docs/notes/2026-05-28-cpnew-canonical-overview.md`
- **Handler modules**: `/home/anton/projects/Omniverse_Nemotron_Ext/service/isaac_assist_service/chat/tools/handlers/*.py`
- **Schemas**: `/home/anton/projects/Omniverse_Nemotron_Ext/service/isaac_assist_service/chat/tools/tool_schemas.py` (9870 lines)
- **Pydantic models**: `/home/anton/projects/Omniverse_Nemotron_Ext/service/isaac_assist_service/chat/tools/handlers/_models.py` (4384 lines)
- **Dispatch entry**: `/home/anton/projects/Omniverse_Nemotron_Ext/service/isaac_assist_service/chat/tools/handlers/_dispatch.py`
