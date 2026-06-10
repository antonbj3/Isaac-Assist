# X-05 Inert Tools Report
Generated: 2026-06-10  
Scope: handlers/sensors.py + handlers/robot.py  
Schema reference: tools/tool_schemas.py

---

## Section 1 — Five Known Examples: Classification

### 1. `create_bin` (robot.py:2013)
**Classification:** AUTHORING-ONLY  
The handler is a codegen function (`_gen_create_bin`) that emits Python constructing 5 USD Cube prims with CollisionAPI. All declared schema args (`prim_path`, `size`, `position`, `wall_thickness`) are fully consumed and baked into the generated code. No runtime read-back — the prims are static once authored.  
**Recommended action:** Mark `AUTHORING-ONLY` in docstring; no schema fix needed.

### 2. `configure_camera` (sensors.py:138)
**Classification:** AUTHORING-ONLY (+ DEPRECATED)  
Codegen that emits `.Set()` calls for focal_length, horizontal_aperture, vertical_aperture, clipping_range, focus_distance. All schema args consumed. No runtime read-back. The schema already labels it `[DEPRECATED — use set_camera_params instead]`.  
**Recommended action:** No schema fix needed. Remove from schema or add `deprecated: true` field.

### 3. `barcode_reader_sensor` (sensors.py:880)
**Classification:** AUTHORING-ONLY  
Creates a USD Xform prim with 4 attributes (`barcode:scan_radius`, `barcode:last_read`, `barcode:last_class`, `barcode:read_count`). All schema args consumed. Docstring is honest: "Runtime barcode reading would be a per-tick callback (controller-side, Sprint 3+)." No per-tick callback exists in any handler.  
**Recommended action:** Mark `AUTHORING-ONLY` explicitly in docstring; add note that barcode read polling requires Sprint-3 controller.

### 4. `register_moving_obstacle` (robot.py:4776)
**Classification:** AUTHORING-ONLY  
Writes a `curobo:moving_obstacles` StringArray USD attribute on the robot prim. Fully consumed args: `robot_path`, `obstacle_path`. Docstring says "Runtime usage requires controller integration that reads this attr each tick and updates plan_pose's obstacle list (Sprint 3+)." No controller-side polling has been implemented.  
**Recommended action:** Mark `AUTHORING-ONLY` in docstring; schema description already partially discloses this but could be clearer.

### 5. `sim_control` (diagnostics.py:2073)
**Classification:** FULLY FUNCTIONAL (NOT decorative)  
Codegen that emits `omni.timeline` play/pause/stop/step/reset calls. Both schema args (`action`, `step_count`) are correctly consumed. Real runtime behavior — timeline IS the sim control.  
**Recommended action:** None. This tool was misclassified as decorative; it works correctly.

---

## Section 2 — Systematic ARGS-IGNORED Scan

### sensors.py

| Tool | Schema Args | Ignored Args | Notes |
|------|-------------|--------------|-------|
| `add_sensor_to_prim` | prim_path, sensor_type, product_name, fov, resolution, range, fps | **product_name, range, fps** | Handler only reads prim_path, sensor_type, fov, resolution. product_name/range/fps never referenced in body. |
| `inspect_camera` | camera_path | — | All used. |
| `configure_camera` | camera_path, focal_length, horizontal_aperture, vertical_aperture, clipping_range, focus_distance | — | All conditionally consumed. |
| `set_camera_params` | camera_path, params, focal_length, horizontal_aperture, vertical_aperture, clipping_range, focus_distance, f_stop, projection | — | Handler uses nested `params` dict with per-key conditionals; top-level duplicates (focal_length etc.) appear as schema fallbacks. Acceptable. |
| `set_camera_look_at` | camera_path, target, up, eye | — | All used. |
| `add_proximity_sensor` | sensor_path, position, size, watched_path_pattern | — | All used. |
| `add_force_torque_sensor` | sensor_path, parent_path, threshold, noise_std, publish_topic | — | All used. |
| `add_vision_classifier_gate` | cube_paths, class_labels, camera_path, destination_map | — | All used. |
| `barcode_reader_sensor` | sensor_path, position, scan_radius | — | All used (but AUTHORING-ONLY). |
| `list_contacts` | prim_path, duration, min_impulse | — | All used. |
| `nir_material_sensor` | sensor_path, position, scan_radius | — | All used. |
| `overlap_box` | center, half_extents, rotation | — | All used. |
| `overlap_sphere` | center, radius | — | All used. |
| `raycast` | origin, direction, max_distance | — | All used. |
| `sweep_sphere` | start, end, radius | — | All used. |

**sensors.py args-ignored tools: 1 (`add_sensor_to_prim` — 3 ignored args: product_name, range, fps)**

---

### robot.py

| Tool | Schema Args | Ignored Args | Notes |
|------|-------------|--------------|-------|
| `anchor_robot` | robot_path, anchor_surface_path, base_link_name, position | — | All used. |
| `verify_import` | articulation_path | — | Used. |
| `robot_wizard` | robot_name, asset_path, dest_path, position, orientation, robot_type, drive_stiffness, drive_damping, variants, home_joints | — | All consumed. |
| `tune_gains` | articulation_path, method, joint_name, kp, kd, test_mode | — | All consumed. |
| `assemble_robot` | base_path, attachment_path, base_mount, attach_mount | — | All consumed. |
| `create_gripper` | articulation_path, gripper_type, gripper_dof_names, open_position, closed_position | — | All consumed. |
| `create_wheeled_robot` | robot_path, drive_type, wheel_radius, wheel_base, wheel_dof_names, max_linear_speed, max_angular_speed | — | All consumed. |
| `navigate_to` | robot_path, target_position, planner | — | All consumed. |
| `create_conveyor` | prim_path, size, position, surface_velocity, speed, direction | — | All consumed. |
| `create_conveyor_track` | waypoints, belt_width, speed | — | All consumed. |
| `create_bin` | prim_path, size, position, wall_thickness | — | All consumed (AUTHORING-ONLY). |
| `move_to_pose` | articulation_path, target_position, target_orientation, planner, robot_type | — | All consumed. |
| `plan_trajectory` | articulation_path, waypoints, properties, position, orientation, planner, robot_type | — | All consumed. |
| `set_motion_policy` | articulation_path, policy_type, obstacle_name, obstacle_type, obstacle_dims, obstacle_position, joint_limit_buffers, robot_type | — | All consumed. |
| `solve_ik` | articulation_path, target_position, target_orientation, robot_type | — | All consumed. |
| `grasp_object` | robot_path, target_prim, grasp_type, grasp_file, approach_distance, lift_height | — | All consumed. |
| `define_grasp_pose` | robot_path, object_path, gripper_offset, approach_direction | — | All consumed. |
| `record_waypoints` | articulation_path, output_path, format | — | All consumed. |
| `start_teaching_mode` | articulation_path, mode, robot_type | — | All consumed. |
| `replay_trajectory` | articulation_path, trajectory_path, speed | — | All consumed. |
| `interpolate_trajectory` | articulation_path, waypoints, properties, joint_positions, method, num_steps, output_path, robot_type | — | All consumed. |
| `setup_whole_body_control` | articulation_path, locomotion_policy, arm_planner, ee_frame, robot_profile | — | All consumed. |
| `setup_rsi_from_demos` | demo_path, env_cfg, noise_std | — | All consumed. |
| `setup_multi_rate` | lower_rate_hz, upper_rate_hz, upper_dof | — | All consumed. |
| `record_trajectory` | articulation, duration, output_path, rate_hz | — | All consumed. |
| `import_robot` | file_path, format, dest_path | — | All consumed. |
| `teach_robot_pose` | robot_path, pose_name | — | All consumed. |
| `load_robot_pose` | robot_path, pose_name, interpolation_seconds | — | All consumed. |
| `generate_occupancy_map` | origin, dimensions, resolution, height_range | — | All consumed. |
| `create_behavior` | articulation_path, behavior_type, target_prim, params | — | All consumed. |
| `export_nav2_map` | output_path, resolution, origin, dimensions, height_range, occupied_thresh, free_thresh | — | All consumed. |
| `create_kit_tray` | tray_path, position, tray_size, slot_layout, slot_size, slot_spacing | — | All consumed. |
| `create_articulated_joint` | joint_path, body0_path, body1_path, joint_type, axis, limit_lower, limit_upper, drive_type | — | All consumed. |
| `create_rotary_table` | table_path, position, radius, height, angular_velocity_deg | — | All consumed. |
| `register_moving_obstacle` | robot_path, obstacle_path | — | All consumed (AUTHORING-ONLY). |
| `create_gravity_dispenser` | dispenser_path, target_xy, drop_height, n_items, item_size | — | All consumed. |
| `create_heap_zone` | heap_path, center, radius, n_items, item_size | — | All consumed. |
| `setup_cortex_behavior` | robot_path, robot_kind, behavior_module, obstacles | — | All consumed. |
| `setup_assembly_constraint` | peg_path, hole_path, tolerance, constraint_path | — | All consumed. |
| `create_recirculation_loop` | loop_path, center, length, width, velocity | — | All consumed. |
| `create_linear_axis_robot` | robot_path, slider_path, axis, limit_lower, limit_upper | — | All consumed. |
| `setup_grasp_pose_sampler` | sampler_path, target_path, n_samples, sampling_mode | — | All consumed. |
| `generate_robot_description` | articulation_path, robot_type | — | All consumed. |
| `apply_robot_fix_profile` | articulation_path, robot_name | — | All consumed. |
| `calibrate_physics` | real_data_path, articulation_path, parameters_to_calibrate, num_samples, num_workers, output_dir | — | All consumed. |
| `quick_calibrate` | real_data_path, articulation_path, include_masses, output_dir | — | All consumed. |
| `get_gripper_state` | articulation, gripper_joints, open_threshold, closed_threshold | — | All consumed. |
| `setup_isaac_ros_cumotion_moveit` | robot_path, output_dir, planner_id, max_planning_time, goal_tolerance_pos_m, goal_tolerance_orient_rad | — | All consumed (writes YAML file). |
| `setup_pick_place_with_vision` | robot_path, cube_paths, source_paths, class_labels, camera_path, destination_map, destination_path, sensor_path, belt_path, planning_obstacles | **destination_path** | Handler reads destination_path from args (line ~5857) but delegates to execute_tool_call for setup_pick_place_controller and does NOT forward destination_path in that call. The controller delegation only forwards destination_map and sensor/belt args. |
| `track_slot_occupancy` | tray_path, cube_paths | — | All consumed. |
| `setup_robot_handoff_signal` | handoff_path, position, robot_a, robot_b | — | All consumed. |
| `setup_robot_claim_mutex` | mutex_path, resource_path, robots | — | All consumed. |
| `surface_gripper` | robot_path, ee_link, grip_threshold, force_limit, torque_limit, graph_path | **torque_limit, graph_path** | torque_limit: read (6179) and returned (6636) but NEVER written to any USD attribute — force_limit covers both coaxialForceLimit and shearForceLimit; torque_limit is dead. graph_path: read (6180) but never used anywhere in generated code or return value. |
| `setup_zone_partition` | conveyor_path, n_zones, robots, base_path | — | All consumed. |
| `setup_nav_robot` | robot_path, occupancy_map, nav_topic, odom_topic | — | All consumed. |
| `visualize_behavior_tree` | network_name | — | Used. |
| `setup_ros2_control_compat` | robot_path, joint_states_topic, joint_commands_topic, controller_type | — | All consumed (but DESCRIPTION-ONLY: no OmniGraph nodes created; Kit code just prints a "run setup_ros2_bridge" note). |
| `place_on_top_of` | prim_path, target_prim_path, clearance, xy_align | — | All consumed. |
| `list_available_controllers` | (none) | — | No args. |

**robot.py args-ignored tools: 2**
- `surface_gripper` — 2 ignored args: `torque_limit`, `graph_path`
- `setup_pick_place_with_vision` — 1 ignored arg: `destination_path` (read but not forwarded to the controller call)

---

## Section 3 — Additional DESCRIPTION-ONLY Classification

| Tool | Classification | Notes |
|------|---------------|-------|
| `setup_ros2_control_compat` | DESCRIPTION-ONLY | Kit-side code reads args and prints a message; no OmniGraph nodes are authored. Explicitly tells caller to "Run setup_ros2_bridge(...)" instead. |
| `setup_robot_handoff_signal` | AUTHORING-ONLY | Writes USD attrs; "Runtime claim/release requires controller hooks." |
| `setup_robot_claim_mutex` | AUTHORING-ONLY | Writes USD attrs; mutex semantics require Sprint-3 controller integration. |
| `setup_nav_robot` | AUTHORING-ONLY | Writes nav:* USD attrs; "Runtime nav execution requires Nav2 + ROS2 bridge integration." |
| `setup_grasp_pose_sampler` | AUTHORING-ONLY | Writes grasp:* USD attrs; "Actual SDG execution at runtime requires Replicator pipeline." |
| `setup_assembly_constraint` | AUTHORING-ONLY | Writes assembly:* USD attrs; "Runtime (Sprint 3+) would create FixedJoint." |

---

## Summary Table

| Tool | Class | Ignored Args |
|------|-------|-------------|
| `create_bin` | AUTHORING-ONLY | — |
| `configure_camera` | AUTHORING-ONLY + DEPRECATED | — |
| `barcode_reader_sensor` | AUTHORING-ONLY | — |
| `register_moving_obstacle` | AUTHORING-ONLY | — |
| `sim_control` | FULLY FUNCTIONAL | — |
| `add_sensor_to_prim` | ARGS-IGNORED | product_name, range, fps |
| `surface_gripper` | ARGS-IGNORED | torque_limit, graph_path |
| `setup_pick_place_with_vision` | ARGS-IGNORED | destination_path |
| `setup_ros2_control_compat` | DESCRIPTION-ONLY | — |

**Total ARGS-IGNORED tools found: 3**  
**Total ignored args: 6** (product_name, range, fps, torque_limit, graph_path, destination_path)

---

## Recommended Actions

| Tool | Action |
|------|--------|
| `add_sensor_to_prim` | Wire `product_name` to a `lookup_product_spec` call that auto-populates fov/resolution/range/fps; or remove `product_name`/`range`/`fps` from schema if they will never be implemented. |
| `surface_gripper` | Wire `torque_limit` to `isaac:axialForceLimit` or a dedicated torque-limit attribute in the generated code; remove `graph_path` from schema (the OmniGraph path is never created by this tool — it's a holdover from an earlier design). |
| `setup_pick_place_with_vision` | Forward `destination_path` to the inner `execute_tool_call("setup_pick_place_controller", ...)` call, or remove it from the schema if `destination_map` supersedes it. |
| `configure_camera` | Remove from schema (already deprecated; `set_camera_params` is the replacement). |
| `setup_ros2_control_compat` | Add `DESCRIPTION-ONLY` to docstring; or upgrade to emit actual OmniGraph nodes. |
| `barcode_reader_sensor`, `register_moving_obstacle`, `setup_robot_handoff_signal`, `setup_robot_claim_mutex`, `setup_nav_robot`, `setup_grasp_pose_sampler`, `setup_assembly_constraint` | Add `authoring-only: runtime integration pending` note to schema description. |
