# Tool Gap Inventory V2 — Isaac Assist

**Date:** 2026-06-09
**Scope:** Consolidated, deduplicated, and ranked tool-gap inventory across 7 asset-category passes (ROBOTS+EOAT, CONVEYORS, CONTAINERS, WORKPIECES, WAREHOUSE, ENVIRONMENTS, SENSORS) and 17 end-to-end scenario passes.
**Method:** Raw needs from all passes were deduplicated (many tools surfaced under several names — e.g. `pause_conveyor` / `stop_conveyor` / `set_belt_speed` / `set_conveyor_velocity` are ONE gap). Each MISSING claim was re-verified by grep against `handlers/` + `tool_schemas.py` (see Verification). Blast radius = number of distinct source passes (max 24) that named the gap, weighted by how load-bearing it is. Effort: **S** ≤ ~1 day glue, **M** = new handler + gate wiring, **L** = new subsystem, **research** = blocked on an absent dependency (e.g. ros2_control bridge, faithful suction model).

---

## A. EXISTS — confirmed live, no action

These were surfaced as "needs" but already have a handler + schema. Use as-is.

| Tool | Where |
|---|---|
| `setup_pick_place_controller` (franka/ur10/ur10e/cobotta/g1 branches, belt_path pause, color_routing) | pick_place.py:293; schema tool_schemas.py:3921 |
| `list_available_controllers` | tool_schemas.py:3994 |
| `surface_gripper` (UR10 suction + IsaacSurfaceGripper) | robot.py:6153; schema :2525 |
| `robot_wizard` / `import_robot` / `anchor_robot` | robot.py:3940+; registry _shared.py:155+ |
| `navigate_to` / `create_wheeled_robot` / `setup_nav_robot` / `generate_occupancy_map` | robot.py ~7292-7319; F-04.json live |
| `create_conveyor` / `create_conveyor_track` / `create_rotary_table` / `create_gravity_dispenser` / `create_recirculation_loop` | robot.py:1744/1854/4685/4858; _models.py |
| `add_proximity_sensor` (belt-pause/gate trigger) | tool_schemas.py:4001 |
| `create_bin` (primitive cubes) / `create_kit_tray` / `track_slot_occupancy` | tool_schemas.py:3875/2577/2597 |
| `compute_stack_placement` (palletize/kit layout; covers `compute_palletizer_grid`) | scene_authoring.py:5454; schema :7158 |
| `add_reference` / `add_usd_reference` (THE asset-resolution path) | tool_schemas.py:83 / :8638 |
| `get_bounding_box` / `get_world_transform` / `teleport_prim` | tool_schemas.py:6470/6442/359 |
| `open_stage` / `add_sublayer` / `set_edit_target` / `set_environment_background` | tool_schemas.py:9441/7930/7837 |
| `activate_area` (activate_robot_cell) / `clone_envs` / `clone_prim` | tool_schemas.py:5247/3389/113 |
| `setup_robot_handoff_signal` (passive attrs) / `setup_robot_claim_mutex` | robot.py:6037/7294 |
| `add_vision_classifier_gate` / `barcode_reader_sensor` / `nir_material_sensor` / `add_force_torque_sensor` (build-time authoring) | sensors.py:562/880/1005/473 |
| `setup_pick_place_with_vision` / `add_sensor_to_prim` | tool_schemas.py:2611/254 |
| `setup_admittance_controller` / `setup_impedance_controller` (dry_run plan only) | tool_schemas.py:1938 |
| `setup_assembly_constraint` / `validate_assembly_constraint` | tool_schemas.py (grep 1 each) |
| local SAM2+CLIP vision provider (offline classification) | multimodal/vision_sam_clip.py; weight present 184MB |
| `place_on_top_of` / `set_semantic_label` / `check_collisions` | tool_schemas.py |
| low-level joint verbs `create_articulated_joint` / `apply_api_schema` | robot.py:7273; scene_authoring.py:1084/1118 |

---

## B. PARTIAL — exists but functionally incomplete

Ranked by blast radius. These are cheaper to finish than to build new (the skeleton + registration already exist).

| # | Tool | What's missing | Blast | Effort |
|---|---|---|---|---|
| P1 | `setup_pick_place_controller` robot auto-detect (:175) | franka fallback footgun for non-first-class arms (silently mis-plans) | high (all non-franka specs) | S |
| P2 | `create_gripper` | only `{parallel_jaw, suction}`; defaults to panda finger DOF names → must override for non-Franka jaws; no 3-finger | 3 (xArm/Lite6/EOAT) | S |
| P3 | `compute_stack_placement` | assumes square footprint; needs additive `item_footprint=[w,d]` for rectangular nesting (CT-05) | 2 | S |
| P4 | `belt_pause_resume` | lives INSIDE pick_place controller (`_belt_pause_request`); no standalone operator tool → see M1 | 6+ (every conveyor template) | S→M |
| P5 | `setup_pick_place_with_vision` | `build_color_routing_from_vision` v1 camera-x-vs-image-x axis pairing fails at arbitrary angles | 4 (vision sorts) | M |
| P6 | `setup_grasp_pose_sampler` | marker stub — writes config attrs, no mesh→candidate SDG generation | 3 (picker-tote, workpieces) | L |
| P7 | `define_grasp_pose` | advisory YAML cuRobo never consumes — does not steer the grasp | 2 | M |
| P8 | `setup_bimanual_pick_place_controller` | V0 = 2 sequential per-arm curobo, HARD-LOCKED to unitree_g1.yml; no H1/GR-1/Digit branch | 2 (A08, C04) | M |
| P9 | `grasp_object` | parallel-jaw RmpFlow only; not dexterous | 2 | L |
| P10 | `setup_insertion_controller` / `setup_admittance` / `setup_impedance` | `dry_run=False` raises NotImplementedError — live mode blocked on **absent ros2_control bridge** | 2 (peg, CRM) | research |
| P11 | honest-eyes mesh/insertion grader | scene_eyes/scene_timeseries give contacts + cube/EE pose but no mesh-pose or insertion-depth grader; position-only AABB gate chronically false-positives | high (every irregular-part task) | L |
| P12 | `barcode_reader_sensor` runtime args | `scan_volume` / `read_attribute` passed by templates but silently dropped (only `scan_radius` honoured) | 2 | S |

---

## C. MISSING — ranked by blast radius (build these)

Blast radius is the count of distinct source passes that need it (✚ = also raises the whole platform's measurement honesty). Build order is **cheapest-first within each blast tier** so early wins unblock the most templates per day of work.

### Tier 1 — highest blast (5+ passes)

**M1. `set_conveyor_velocity` / `pause_conveyor` / `resume_conveyor` (standalone belt control)**
- Purpose: change/pause/stop belt speed at runtime without a robot controller. Enables robot-free accumulation, sensor-gate metering, lane-merge gapping, stop-and-go singulation.
- Dedup of: `pause_conveyor`, `stop_conveyor`, `set_belt_speed`, `set_conveyor_velocity`, `set_belt_pause`, `release_metering`.
- **Blast: 6** (conveyors, conveyor-moving-pick, lane-merge, gravity-dispenser, nir-material-sort, sorter-color-3bin).
- Effort: **S**. The logic already exists internally as `_belt_pause_request` in pick_place.py:1296; lift it to a standalone handler that writes the same drive attrs (PhysxSurfaceVelocityAPI) on `belt_path`. Highest ROI: one small handler unblocks six scenarios.

**M2. Multi-target / per-bin sort-accuracy gate (`simulate_sort_check` / `verify_routing` / `per_bin_gate`)**
- Purpose: assert EACH class reached its CORRECT bin (PassBin AND RejectBin, sku_b→LaneB AND sku_c→LaneC). Today `simulate_traversal_check` (SimulateTraversalCheckArgs:356) has a SINGLE `target_path` → 3-way and 2-way sorts are structurally unscorable; the only gate scores "any-one-cube-in-the-one-bin".
- Dedup of: `verify_sort_accuracy`, `per_bin_gate`, `simulate_sort_check`, `verify_routing`, `validate_sort_accuracy`, `check_routing_correct`, multi-target `simulate_traversal_check`, defect-rate/classification-accuracy metric, `route_by_sensor` verdict, multi-bin per-leg gate, two-destination routing gate.
- **Blast: 6** (sorter-color-3bin, nir-material-sort, barcode-divert, inspector-vision-reject, lane-merge, conveyors CV-07). ✚ This is the #1 measurement-honesty gap for the entire sortation family.
- Effort: **M**. Generalize `target_path: str` → `targets: List[{path, expected_class}]`, loop the existing AABB+settle logic per target, emit a confusion-style verdict. No new physics.

### Tier 2 — high blast (3–4 passes)

**M3. `setup_amr_with_manipulator` (ride an arm on a moving base as one TF tree)**
- Purpose: bind an arm USD to a wheeled base so the arm correctly rides the moving base (base-park → arm-pick → base-move). Composing create_wheeled_robot + add_reference(arm) + setup_nav_robot + setup_pick_place_controller does NOT make the arm ride the base.
- Dedup of: `setup_amr_with_manipulator`, `setup_mobile_manipulator`, `dock_amr`, mobile-manipulator stand-up.
- **Blast: 4** (warehouse WH-MM-05, robots C01/C02/C03, amr-depalletize, cell-in-real-warehouse). Brief calls this the highest-ROI robot gap: assets + base-nav + arm controller all exist, only the articulation/parenting glue is missing.
- Effort: **M**. Parent arm root under base link via `create_articulated_joint`(fixed) (already exists) + re-anchor nav frame; the hard part is keeping cuRobo's base frame in sync with the moving base each tick.

**M4. `attach_payload` / `carry_payload` (weld a rideable load onto a base/EE)**
- Purpose: bind a pallet/shelf/rack as a rideable load on a mobile base or carried object on an arm. Needed for AMR depalletize-carry and goods-to-person rack-lift.
- Dedup of: `attach_payload`, `load_pallet`, `attach_to_amr`, `carry_payload`, `weld_payload`, `payload_parent`, `parent_prim`, `create_fixed_joint`, `lift_shelf`, `carry_rack`, `shelf_carry`, `rack_lift`, `attach_to`.
- **Blast: 4** (amr-depalletize, goods-to-person-fleet, robots mobile-manip, warehouse). Shares the FixedJoint substrate with M3.
- Effort: **S**. Thin wrapper over existing `apply_api_schema(PhysicsFixedJoint)` / `create_articulated_joint` with a release verb. Build alongside M3.

**M5. Runtime sensor-read + sensor→controller routing bridge**
- Purpose: a per-tick reader that turns a sensor signal into a class label and feeds it to the controller's per-cube class source — closing the sensor→bin loop. Today every "sensor" (barcode/NIR/vision-classifier) is build-time-only ("Sprint 3+"); routing reads USD `Semantics_class` directly (`_cube_semantic_class` pick_place.py:3323), an oracle, so the sensor is decorative.
- Dedup of: `read_nir_sensor`, `classify_material`, `route_by_sensor`, runtime barcode-decode, live vision→routing binding, sensor→controller routing bridge.
- **Blast: 4** (nir-material-sort, barcode-divert, inspector-vision-reject, conveyors CV-07). ✚ Without this, NO sensor-driven divert is real — all sort templates secretly route off the oracle.
- Effort: **M**. Add a pre-step subscription that polls `barcode:last_class` / `nir:last_material` / vision gate output and writes the controller's per-cube class attr. Pair with M2 to actually score it.

**M6. LLM-callable static pre-filter (`scene_validate` / `check_reachability` / `check_fit`)**
- Purpose: expose the existing `scripts/qa/scene_validate.py` (REACH / TARGET_REACH / INTERPEN / SUPPORT / physics-instability + footprint-fit/fits-in-slot) as an LLM-callable handler so the model can cheaply pre-filter before the expensive gate. Today it exists only as a bench script; the LLM can only call the narrower `check_collisions`.
- Dedup of: `scene_validate`, `check_reachability`, `reachability_check`, `static_eyes`, `form_gate`, `check_fit`, `fits_in_slot`, `footprint_fit`, sheet-flatness/footprint-fit pre-check, `validate_scene_in_env`, whole-cell-vs-env validator.
- **Blast: 4** (picker-tote, packer-suction-sheet, sorter-color-3bin, cell-in-real-warehouse). ✚ Also drains expensive-gate spend platform-wide.
- Effort: **S→M**. Wrap the existing script as a handler (S); make it env-aware and humanoid-reach-aware (M, the script currently SKIPS reach for g1/unitree).

**M7. `compose_scene` + `sub_stages` (multi-cell composition)**
- Purpose: place N canonicals in one frame, namespaced per cell (`prim_prefix`/`cell_origin`), with inter-cell relations (AMR handoff), and ONE deferred `world.reset()` so per-canonical reset+re-seed does not race (the CP-52 mutex-starvation root, generalized).
- Dedup of: `compose_scene`, `sub_stages`, `compose_templates`, `chain_canonical`, `multi_stage_gate`, `compose_cells`, `place_cell`, cross-cell integration gate.
- **Blast: 3** (environments T7, cell-in-real-warehouse, amr-depalletize). The ~200-LOC composition tool flagged as not-existing in TRACED_FLOW_COMPLEX_SCENE.md; Phase 4 of MASTER_EXECUTION_PLAN.
- Effort: **L**. New subsystem: namespacing, per-cell offset, deferred reset, plus a cross-cell gate that proves the composed scene in ONE physics run. The single biggest build, but only 3 scenarios depend on it — do it AFTER the cheap Tier-1/2 wins.

**M8. 3-finger / multi-finger adaptive grasp controller**
- Purpose: closed-loop adaptive grasp on Allegro/Shadow/Robotiq-3F/Dex3/Dex5 for irregular real parts. `create_gripper` supports only parallel_jaw/suction; `_SUPPORTED_MOTION_ROBOTS` is all parallel-jaw; dex hands driveable only via raw `set_joint_targets`.
- Dedup of: `setup_dexterous_grasp`, `three_finger`, `adaptive_grasp`, `close_hand`, `multi_finger`.
- **Blast: 3** (robots C05/C07, workpieces, picker-tote). USDs on disk; no synthesis/controller.
- Effort: **research**. Needs a grasp-synthesis + adaptive-close control loop (depends on P6/P11 too). Highest-effort manipulation gap; defer.

### Tier 3 — medium blast (2 passes)

**M9. `step_rotary_table` / `advance_carousel` / `rotate_to_index` + `refresh_pick_targets`**
- Purpose: index a carousel/turntable to present the next SKU at the handoff, then push the post-rotation child world positions back into the installed cuRobo controller. The passive revolute joint is built (create_rotary_table) but never stepped; nothing re-feeds targets.
- Dedup of: `step_rotary_table`, `advance_carousel`, `rotate_to_index`, `refresh_pick_targets`, `recompute_pick_targets`.
- **Blast: 2** (kitting-carousel, conveyors rotary). Effort: **M** (revolute drive step exists; the target-refeed into the live controller is the new part).

**M10. Articulated-door / revolute-pull controller (`open_door` / `articulated_pull`)**
- Purpose: swing a real RevoluteJoint hinge (PD/force-ramp) instead of faking the door via a translate-write. The math kernel `sub_phase_70c_articulated_drag_controller.py` is landed but no codegen/tool calls it; pick_place.py has no door/hinge/revolute branch.
- Dedup of: `open_door`, `articulate_door`, `articulated_pull` handler.
- **Blast: 2** (cnc-tend door, humanoid-cabinet). Plus a door-aware/containment gate (reads RevoluteJoint position + item-entered-interior) and a swept-arc static pre-filter. Effort: **M** (kernel exists; wire codegen + a revolute+containment gate).

**M11. `setup_robot_handoff_controller` / `enforce_handoff_sequence` + handoff gate**
- Purpose: runtime "A done → B may pick" gating with a barrier/mutex, plus a gate asserting the cube transited A→Handoff→B→Bin and was delivered BY robot B. `setup_robot_handoff_signal` writes passive `handoff:state` attrs no controller reads; `setup_robot_claim_mutex` exists but CP-51 passes none.
- Dedup of: `setup_robot_handoff_controller`, `enforce_handoff_sequence`, `verify_handoff_pipeline`, `diagnose_handoff_execution`, `setup_dual_arm_coordination`, `wait_for_robot_done`, `wait_for_handoff_state`, `poll_attribute`.
- **Blast: 2** (dual-arm-handoff, amr-depalletize). Effort: **M** (mutex + signal building blocks exist; add a blocking poll + robot-attributed gate).

**M12. Belt-pickup support tools (moving-obstacle lifecycle + velocity + intercept)**
- Purpose: drop delivered cubes from the cuRobo obstacle list between cycles (`deregister_moving_obstacle`), push per-tick obstacle pose (`update_moving_obstacle` — today `register_moving_obstacle` only writes a static attr, runtime read is "Sprint 3+"), read belt/object velocity, and lead-the-target.
- Dedup of: `deregister_moving_obstacle`, `update_moving_obstacle`, `track_object`, `predict_intercept`, `get_object_velocity`, `estimate_belt_velocity`, `wait_for_sensor_trigger`.
- **Blast: 2** (conveyor-moving-pick, lane-merge). Effort: **M** (dereg is S; per-tick obstacle/velocity feed + intercept is M). `wait_for_sensor_trigger` alone is **S** — `add_proximity_sensor` + `sensor_path` already exist, just need a blocking poll.

**M13. Container asset-resolution behind `create_bin` (name→USD)**
- Purpose: resolve a friendly container name (KLT / euro_tote / wooden_crate / cardbox / pallet) to the real USD, apply a physics variant, return measured bbox + interior floor. Today `create_bin` emits only primitive Cubes; 0/440 templates reference a real KLT/crate/tote.
- **Blast: 2** (containers, cell-in-real-warehouse). Effort: **S** — a name→path lookup table feeding the existing `add_reference` + `get_bounding_box`. Cheap; do early.

**M14. `place_on_shelf` / `rack_place` (rack-bay-aware placement)**
- Purpose: slot-indexed placement into RackLarge/RackLong levels without hardcoded shelf-Z math. Partial coverage today via compute_stack_placement + place_on_top_of + teleport_prim (slot-blind).
- Dedup of: `place_on_shelf`, `rack_place`, `shelf_place`, `snap_next_to`, `place_next_to`, `align_to_rack`.
- **Blast: 2** (warehouse, cell-in-real-warehouse). Effort: **M** (rack-geometry introspection → slot centers, then reuse place_on_top_of).

### Tier 4 — low blast (1 pass each) — batch or defer

| Tool | Purpose | Scenario | Effort |
|---|---|---|---|
| `import_mesh` / `import_ycb` / `load_obj` (general mesh/YCB loader) | spawn arbitrary loose items | picker-tote | M |
| pose-tolerance verifier (`verify_pose_delta`, 2mm/2°) | compare placed-part pose vs target | packer-suction-sheet | S |
| `create_belt_diverter` / `pneumatic_pusher` | robot-free pop-up/swing deflect to cross belt | conveyors | M |
| `create_lane_merge` / merge arbiter / `claim_merge_slot` / `assign_merge_priority` | Y-junction controlled interleave + FIFO singulation | lane-merge | M |
| `create_singulator` / `create_hopper` / `create_vibratory_conveyor` / `wait_for_part`(land-and-catch) | true singulation / vibratory feed / land-and-pick | gravity-dispenser | M |
| `clamp_workpiece` (fixture hold) | clamp during machining (apply_api_schema FixedJoint exists, unused) | cnc-tend | S |
| `machining_cycle` / `spindle_cycle` | real cut/spindle/cycle-complete signal vs bare dwell | cnc-tend | M |
| `loop_workflow` / `repeat_cycle` | "repeat 4×" primitive (LLM unrolls today) | cnc-tend | S |
| force-guarded / abort-on-threshold trajectory + retry-on-event | enforce force cap; retry on contact event | peg-insertion | M |
| faithful suction-seal feasibility model (normals not AABB) | grip fidelity assertion | packer-suction-sheet | research |
| 6-DoF metric pose estimator (FoundationPose/MegaPose) + depth/point-cloud seg | true 6-DoF for bin-pick/depalletize | sensors | research |
| `setup_reorient_controller` / flip-station | regrasp/passive-flip reorient (Flip_Stack asset unused) | workpieces | research |
| FLEET subsystem: `fleet_manager`/`dispatch`/`assign_task`/`queue_task`/`traffic_control`/`claim_lane`/`reserve_lane`/`amr_dock`/`charge_robot`/`create_shelf`/`create_rack` | multi-robot scheduling + traffic + docking + racks | goods-to-person-fleet | L |
| `simulate_navigation_check` / `verify_amr_at_goal` | navigation function-gate (both AMR drive legs ungraded today) | amr-depalletize | M |
| cuRobo mesh-env ingestion (planning_obstacles as meshes not AABB cuboids) | faithful obstacle from referenced full_warehouse.usd | cell-in-real-warehouse | research |
| `vision_completeness_check` / `verify_kit_complete` | first-class kit-completeness (compose from gate+slot today) | kitting-carousel | S |
| `mount_eoat` / `attach_gripper` (weld stand-alone EOAT onto tool0 + mimic joints) | mount Robotiq/xArm/Lite6 EOAT (C06) | robots | M |

---

## D. Recommended build order (cheapest-first, ROI-weighted)

1. **M1** belt control (S, blast 6) — one handler, six scenarios.
2. **M13** container name→USD (S, blast 2) — table lookup, unblocks the whole CONTAINERS category.
3. **M4** attach_payload (S, blast 4) — FixedJoint wrapper, prerequisite for M3.
4. **M6** static pre-filter as handler (S→M, blast 4 ✚) — wrap existing script; cuts gate spend everywhere.
5. **M2** multi-target sort gate (M, blast 6 ✚) — generalize target_path → targets[].
6. **M5** sensor→controller routing bridge (M, blast 4 ✚) — makes M2's score real.
7. **M3** AMR-with-manipulator (M, blast 4) — builds on M4.
8. **M12** belt-pickup support (dereg=S first, intercept=M, blast 2).
9. **M9 / M10 / M11 / M14** (M each, blast 2) — carousel, door, handoff, rack-place.
10. **M7** compose_scene (L, blast 3) — big build, only after cheap wins land.
11. **M8** dexterous grasp + research items (P10 live insertion, faithful suction, 6-DoF pose, FLEET, mesh-env ingestion) — defer; each is research or L with blast ≤3.

---

## E. Verification (greps run 2026-06-09)

All MISSING tools returned **0 handler/schema hits** under
`service/isaac_assist_service/chat/tools/handlers/` + `tool_schemas.py`:
`setup_amr_with_manipulator`, `compose_scene`/`sub_stages`, dexterous/3-finger grasp, `mount_eoat`/`attach_gripper`, standalone conveyor velocity/pause, diverter/pusher/lane_merge/singulator, container name→USD (KLT/tote/crate), per-bin sort-accuracy gate, runtime sensor-read/route_by_sensor, moving-obstacle update/dereg, handoff controller, articulated door, fleet/*, attach_payload, place_on_shelf, nav check gate, mesh/YCB importers, LLM-callable scene_validate, pose-tolerance verifier, 6-DoF pose net.

Confirmed building blocks that make several gaps **S/M instead of L**:
`create_articulated_joint` + `apply_api_schema(FixedJoint)` (robot.py:7273, scene_authoring.py:1084/1118) → M3/M4/M10/clamp;
`setup_robot_handoff_signal` + `setup_robot_claim_mutex` (robot.py:6037/7294) → M11;
`add_proximity_sensor` + `sensor_path` (tool_schemas.py:4001/3947) → wait_for_sensor;
`create_rotary_table` revolute joint → M9;
internal `_belt_pause_request` (pick_place.py:1296) → M1;
`SimulateTraversalCheckArgs.target_path` is single-string (_models.py:356) → M2 is a list-generalization, not new physics.

Research-blocked (absent dependency, not buildable cheaply):
live insertion/compliance — `dry_run=False` raises NotImplementedError, blocked on **absent ros2_control bridge** (insertion.py:352, compliance.py:186/256);
faithful suction (OgnSurfaceGripper AABB-proximity, no normals);
6-DoF metric pose net; cuRobo mesh-env ingestion (planning_obstacles are per-prim AABB cuboids, pick_place.py:4972/5001).
