# ROS2 Strategy — Isaac Assist

> Consolidated "where our ROS2 thinking is" doc. Synthesizes three grounded code/doc audits
> (capability surface, sim2real/production-parity role, strategic fit + gaps).
> All claims cite `file:line`. Last verified: 2026-06-09.

---

## 1. STATEMENT — ROS2's intended role

**ROS2 is the project's designated *production execution path* and sim2real bridge — not merely an
alternate controller backend.** The architecture, written verbatim in code, is *Isaac-as-digital-twin*:
Isaac Sim provides only physics + rendering + topic I/O, while the controller/state-machine lives
**outside** Kit in a real ROS2 stack (MoveIt2 / Nav2 / ros2_control), and that same external stack drives
the arm in sim *and* on real hardware. This is stated literally in `_gen_pick_place_ros2_cmd`'s docstring:
*"The state machine logic lives entirely outside Isaac Sim (e.g. in a real PLC, a ROS2 node, or a
digital-twin controller) — Isaac Sim provides only physics, rendering, and the topic I/O layer"*
(`service/isaac_assist_service/chat/tools/handlers/pick_place.py:9043`). This is the architectural
inversion vs cuRobo: cuRobo (`target_source="curobo"`) plans trajectories *inside* Kit on the GPU and is
sim-only with no hardware counterpart, and remains the **verified production path today**; `ros2_cmd`
makes Kit a dumb I/O endpoint subscribing to externally-computed targets and is the **production-shaped but
production-unverified** path of tomorrow. Bottom line: ROS2 is production-*shaped* but production-*unverified*
— the bridge-build + topic-I/O + offline-gap-measurement layers are real and Kit-exercised, but the
digital-twin loop is open at exactly the point that matters (no real-driver layer, no T5 hardware run, no
function-gate that proves a ROS2-commanded robot completes a physics task).

---

## 2. Capability surface — EXISTS / SCAFFOLD / VERIFIED / ABSENT

Grading key:
- **EXISTS + VERIFIED** — real code, iterated against a live Kit / deps installed and runnable.
- **EXISTS (unverified)** — real code, dispatched/wired, but no passing function-gate; relies on
  external infra or correct Kit env.
- **SCAFFOLD** — compiles/registers but core logic absent, dry-run-only, or `NotImplementedError` in live mode.
- **DEAD** — code-complete but inert at runtime (missing dependency).
- **ABSENT** — does not exist in this repo.

| Layer / Tool | Grade | Evidence (`file:line`) |
|---|---|---|
| 4 OmniGraph bridge profiles (`franka_moveit2`, `ur10e_moveit2`, `jetbot_nav2`, `amr_full`) | **EXISTS + VERIFIED (bridge-build)** — iterated vs live Kit, "Round 2-9 repair" comments 2026-05-17/18 | `handlers/ros2.py:33-122`, `:598-755` |
| `setup_ros2_bridge` (full bridge from profile; AMENT precheck, idempotent graph-delete, per-attr try/except) | **EXISTS + VERIFIED (build only)** — robust, 9 repair rounds; not function-gate verified | `handlers/ros2.py:598` |
| `configure_ros2_bridge` (per-sensor: camera/lidar/imu/clock/joint_state; 5.x `bridge` vs 6.x `nodes` ns) | **EXISTS (partial)** — lidar/imu/odom skip prim-wire (need downstream sensor-reader graph) | `handlers/ros2.py:207` |
| `configure_ros2_time` (sim_time/real_time/scaled `/clock`, `useSimTime`) | **EXISTS + WIRED** | `handlers/ros2.py:492` |
| `fix_ros2_qos` (patch QoS on existing pub node; presets; honestly **raises** if no node) | **EXISTS + WIRED** | `handlers/ros2.py:416`, presets `:21`, raise `:482` |
| `show_tf_tree` (TF pub graph + `isaacsim.ros2.tf_viewer` reader) | **EXISTS + WIRED** | `handlers/ros2.py:129` |
| `replay_rosbag` (`subprocess.Popen(['ros2','bag','play',…,'--clock'])` + timeline) | **EXISTS** — shells to `ros2` CLI; needs ROS2 in Kit env | `handlers/ros2.py:758` |
| `diagnose_ros2` (7-check in-Kit health scan: Context/distro/clock/use_sim_time/domain/QoS/dangling-exec) | **EXISTS + WIRED, substantive** | `handlers/ros2.py:800` |
| `emit_ros2_control_yaml` (colcon-buildable `topic_based_ros2_control` YAML for external workspace) | **EXISTS** — config emitter; joints hardcoded `panda_joint1-7` (Franka-only) | `handlers/ros2.py:1007`, joints `:1037` |
| `precheck_ros2_environment` (AMENT_PREFIX_PATH + ROS_DOMAIN_ID + TCP-probe rosbridge :9090) | **EXISTS + WIRED** | `handlers/ros2.py:1069` |
| ros2.py registration (9 handlers) | wired | `handlers/ros2.py:1111-1131` |
| `target_source="ros2_cmd"` pick-place I/O graph (`ROS2SubscribeTwist` in + `ROS2PublishJointState` out) | **SCAFFOLD** — compiles, but cmd→motion link (sub→IK/ArticulationController) **absent**; type-mismatched (Twist for a pose target); no canonical uses it; no gate | `pick_place.py:556-562` (dispatch), `:9038-9116`; closing note `:9115` |
| `setup_pick_place_ros2_bridge` (publishes robot state outward — inverse of `ros2_cmd`) | **EXISTS** | `pick_place.py:1574` |
| Live rosbridge tools (11: connect/list/get topics+types/subscribe_once/publish/publish_sequence/services/nodes) | **DEAD** — code-complete but `ros-mcp` **NOT installed** → all 11 register as `None` | `ros_mcp_tools.py`; `handlers/_dispatch.py:90-113`; defaults `config.py:82-83` |
| `setup_isaac_ros_cumotion_moveit` (writes `planning_pipeline.yaml`, `CumotionPlannerManager` plugin) | **EXISTS + WIRED** — emits config; *"Does NOT start MoveIt2 — user's external launch"* | `handlers/robot.py:5753-5818` |
| `setup_ros2_control_compat` (standardizes topic names) | **EXISTS + WIRED but thin** — **creates no nodes**; prints "run setup_ros2_bridge" | `handlers/robot.py:6911` |
| `export_nav2_map` (`map.pgm` + `map.yaml` from scene occupancy) | **EXISTS** — config artifact; **no Nav2 runtime / no bringup handler** | `handlers/robot.py:4344` |
| `measure_sim_real_gap` (offline file-vs-file traj comparator: per-joint mean/max + EE drift mm + hints) | **EXISTS + WIRED** — does NOT touch ROS2 itself; no real trajectories exist to feed it | `handlers/diagnostics.py:3761`, reg `:5862` |
| Modbus-TCP bridge (`modbus_tcp_bridge_attach/detach`, `diagnose_modbus_bridge`) | **EXISTS + WIRED + RUNNABLE** — real `pymodbus.ModbusTcpClient` poll; **pymodbus 3.11.4 installed**; server-mode unimpl | `bridge_tools.py:54-106`, reg `:759`; `:63-65` |
| OPC-UA / MQTT-Sparkplug / OpenPLC bridges | **EXISTS + WIRED** — real `asyncua.Client` / `paho.mqtt` workers; deps installed; **docstring `[STUB; phase later]` is STALE** (handlers fully implemented) | `bridge_tools.py:497`, `:667`, `:712`; stale label `:5-6` |
| `IndustrialBridge` (sub_phase_31b, 4 protocols, `BRIDGE_PRESETS`) | **SCAFFOLD** — dry-run-only, `NotImplementedError` live, **not wired to chat/LLM** | `multimodal/sub_phase_31b_industrial_bridges_full.py:14-15,218-221` |
| `MoveItCuMotionBridge` (sub_phase_81c, planner backends moveit_pilz/ompl/cumotion/curobo_v2) | **SCAFFOLD** — mock-only, `NotImplementedError` live, **not wired to chat** | `multimodal/sub_phase_81c_moveit_cumotion_bridge.py:351-385` |
| Real-robot driver layer (`libfranka` / `ur_rtde` / `ROBOT_IP`) | **ABSENT** — only a string in an error message | `handlers/compliance.py:382`; `sim2real-validation.md:77` |
| Real-rollout recorder (`record_real_rollout.py`) + HIL conformance suite (`hw_validation_suite.py`) | **ABSENT** — "STUB by absence" | `sim2real-validation.md:95-96` |
| `add_camera_noise_model` (G3 sensor-parity) | **ABSENT** — "STUB by absence" | `sim2real-validation.md:95` |
| `create_ros2_scene_harness` / `mcp_floorplan_tools.py` MCP | **ABSENT** — 0 grep hits anywhere; cited only as a port candidate in plan docs | `MASTER_EXECUTION_PLAN.md:37`, `IMPLEMENTATION_PLAN.md` |
| Live `rclpy` on host | **ABSENT** — not installed; `ros2-tf-tree-validation` `env_blocked: rclpy_abi` (humble cpython-311 vs Kit 3.10) | `sim2real-validation.md:3` |

**Two ROS2 layers, restated for clarity:**
1. **OmniGraph code-gen** (builds ROS2 bridge graphs *inside* Kit) — real, production-shaped, robust;
   **unverified by any function-gate**.
2. **Live rosbridge tools** (talk to a running ROS2 system over WebSocket) — real code but **inert**
   (`ros-mcp` uninstalled). The live path deliberately uses **rosbridge WebSocket, not in-process rclpy**,
   precisely *because* rclpy ABI (humble cpython-311) is incompatible with Kit Python 3.10.

MoveIt2 / Nav2 / ros2_control "integration" is almost entirely **YAML/config emission for an external,
user-run stack** — Isaac Sim provides topic I/O only; it does not run MoveIt2 or Nav2 itself.

---

## 3. The sim2real story — Isaac-as-twin + the T0-T6 ladder

The whole sim2real validation ladder is built on ROS2 as the data-acquisition and execution plumbing
(`docs/research/2026-05-27-sim2real-validation.md`).

**Why the bridge shrinks the sim2real gap (when it works):** the bridge topic names match the
`topic_based_ros2_control` / `TopicBasedSystem` standard (`handlers/ros2.py:1051-1053`;
`emit_ros2_control_yaml` `:1007-1065`), which is *exactly what real `franka_ros2_control` /
`ur_robot_driver` consume* — *"the bridge is already in the right shape"* (`sim2real-validation.md:77,90`).
So the same ROS2 interface that drives the twin can drive the physical arm; the digital twin and the real
cell speak one protocol.

**The ladder (`sim2real-validation.md:22-36`):**

| Tier | Meaning | ROS2 role | Status |
|---|---|---|---|
| T0-T3 | sim-only: form-gate → function-gate → Anton spot-check → manual | none | exists for non-ROS2 canonicals |
| **T4** | "sim2real-ready": declared `real_robot_compatible`, has tolerances + failure-modes (pure metadata gate) | declares ROS2 compat | **DESIGNED, partial — the honest ceiling today** (`:140`) |
| **T5** | single-hardware-validated: real arm executes the template's ROS2 codegen path, recorded via `/joint_states`+`/tf`→HDF5, replayed `replay_rosbag(sync_mode='sim_time')`, gated by `measure_sim_real_gap` RMSE ≤ tol | ROS2 is the execution + recording plumbing | **ABSENT / ASPIRATIONAL — zero hardware runs** |
| **T6** | ≥2 robot families hardware-validated | same | **ABSENT** |

**How `measure_sim_real_gap` fits:** it is a *purely offline file-vs-file comparator*
(`handlers/diagnostics.py:3761`, reg `:5862`) — loads two trajectory files, computes per-joint mean/max
error + EE cartesian drift (mm), picks the worst joint, emits hints (>5° joint → friction/damping
mismatch; >10mm EE → compliance, `:3826-3831`). It does **not** touch ROS2. ROS2 is the *plumbing that
produces the trajectories* it consumes: real reference recorded off `franka_moveit2` (`/joint_states` +
`/tf_static` → HDF5), `replay_rosbag` re-runs it in sim, then the comparator scores the gap
(`sim2real-validation.md:54-61`).

**The honest ceiling:** *"T4 is the honest ceiling for sim-only signal"* (`:140`). T5/T6 are entirely
roadmap — there is no real-robot integration code (no libfranka/ur_rtde imports, no ROBOT_IP handling),
*"the lab work starts at zero on the driver side"* (`:77`). The physics gap is also concretely unclosed:
Isaac PhysX needs ~3× the analytically-predicted gripper force to hold a cube (G4 contact-physics gap),
and the production handler doesn't even set `maxForce`
(`docs/notes/2026-05-27-friction-grip-sim-real-gap.md`).

---

## 4. Honest gap list — DECLARED vs VERIFIED ROS2 execution

This is the central tension: handlers are written and dispatch, but **nothing is function-gate verified**.

1. **No ROS2 *physics* function-gate (the #1 gap).** Every `CP-NEW-ros2-*` / `CP-NEW-{modbus,opcua,mqtt,plc}-*`
   template (~14-24 of the 449/504-template store) carries
   `verified_status: "form-gate pending; function-gate pending"` — **zero are function-gate verified**.
   ROS2 success is graded *structurally*: `verify_args` for `CP-NEW-ros2-moveit2-franka` has `stages: []`,
   `simulate_args: null`, and grades on `expected_topics` + `expected_yaml_files` + `diagnose_ros2` QoS
   health. No template has shown a ROS2-commanded robot actually completing a physics task
   (cube delivery / `simulate_traversal_check`). This is a **diagnostic gate masquerading as verification.**

2. **`ros2_cmd` is plumbing-only.** The generated graph wires `ROS2SubscribeTwist` + a joint-state
   publisher but does **not** wire the subscribed pose into IK / `ArticulationController` — the command→motion
   link is left to the (absent) external node (`pick_place.py:9115`). It is also type-mismatched
   (`ROS2SubscribeTwist` for a documented `PoseStamped` pose target) and **never instantiated by any
   canonical** (grep: appears only in handler/schema/model files).

3. **Live ROS2 surface is DEAD / rclpy is ABI-blocked.** `ros-mcp` is not installed → all 11 rosbridge
   tools register as `None` (`_dispatch.py:90-113`); `rclpy` is not installed at all. In-process live ROS2
   is blocked by the humble-cpython-311 vs Kit-3.10 ABI mismatch, which is *why* the live path routes
   through rosbridge WebSocket (`sim2real-validation.md:3`).

4. **Absent real-robot driver + recorder layer.** No `libfranka`/`ur_rtde`/`ROBOT_IP`; the T5 recorder
   (`record_real_rollout.py`) and HIL suite are "STUB by absence" (`sim2real-validation.md:95-96`).
   Without these, T5/T6 — the tiers customers pay for — cannot produce a single artifact.

5. **MoveIt2 / cuMotion emitters untested against a live node.** `setup_isaac_ros_cumotion_moveit`
   (`robot.py:5753-5818`) and `sub_phase_81c_moveit_cumotion_bridge.py` emit configs but are *"untested
   against live MoveIt2 node"* (`sim2real-validation.md:91`). The `franka_moveit2` chain is the
   highest-value bridge canonical and is unproven end-to-end.

6. **Stale STUB labels + missing harness = false capability map.** `bridge_tools.py:5-6` calls OPC-UA/MQTT
   `[STUB; phase later]` when `_handle_opcua_bridge_attach` (`:497`) and `_handle_mqtt_sparkplug_bridge_attach`
   (`:667`) are fully implemented (false negative); `create_ros2_scene_harness` / `mcp_floorplan_tools.py`
   are cited in the master plan (`:37`) but **absent from this branch** pending Phase-0.3 merge
   (false positive).

**Asymmetry worth noting:** the *industrial-protocol* side is further along than the *robot-arm* side —
Modbus-TCP is actually live and runnable (pymodbus installed), whereas the arm's ROS2 loop has its
hardware end unplugged.

---

## 5. Plan deltas + recommendation

### Where ROS2 items slot into the master plan

- **Corpus axis (required, now).** ROS2 tool-call sequences ARE corpus rows the model must learn — *"the
  corpus is both the retrieval substrate and the training substrate"* (`MASTER_EXECUTION_PLAN.md:13`).
  `CP-NEW-ros2-moveit2-franka.tools_used` is a 13-tool faithful chain
  (`precheck_ros2_environment → robot_wizard → setup_ros2_control_compat → emit_ros2_control_yaml →
  setup_isaac_ros_cumotion_moveit → setup_ros2_bridge → configure_ros2_time → ros2_list_topics →
  diagnose_ros2`). The expansion roadmap places a `bridge.ros2 → bridge.moveit2 → bridge.nav2` dependency
  chain across waves W2-W4 (`expansion-roadmap.md:12,54,156`).
- **Phase 5 / cross-cutting (sim2real).** All ROS2 *execution/verification* work belongs here, gated behind
  the controller + lab-driver work — **not pulled forward onto the North Star critical path.** The sim2real
  doc reserves Priority-50 T5 slots for `bridge.ros2.{franka-moveit2,ur10e-moveit2,carter-nav2}`
  (`sim2real-validation.md:133`); the 5-step software-first plan (`:166-176`) — schema fields + recorder +
  T5 driver — has steps 1/4/5 doable pre-hardware.
- **Verification ladder.** ROS2 templates currently stop at a **diagnostic gate** (topic-presence + YAML +
  QoS), which is a *form/structural* check, NOT the physics function-gate
  (`MASTER_EXECUTION_PLAN.md:22`). A true `ros2_cmd` function-gate needs a live external node/PLC, which the
  rclpy-ABI block + absent driver layer prevent in-process — so a `ros2_cmd`-driven scene is currently
  **un-function-gateable** without external infra (or a self-loop mock).

### Recommendation

**Promote ROS2 to a named first-class *production* execution backend with its own verification tier, but
keep it OFF the North Star critical path until the function-gate gap closes.** ROS2 is the deployment story
(Isaac-as-twin → ROS2 drives real hardware) and a required corpus axis — it is NOT "just an alt backend."
But its current "verified" claim is a *diagnostic* gate masquerading as verification, and the master plan's
honesty principle (*"several 'verified' templates are falsely-green,"* `MASTER_EXECUTION_PLAN.md:28`)
applies directly: every `CP-NEW-ros2-*` should carry a `fidelity-tag` of SYNTHETIC/INFERRED, **never
MEASURED**, until a real ROS2-loop function-gate exists.

### Top concrete deltas (priority order)

1. **Build a self-contained `ros2_cmd` function-gate (cleanest first move).** Spawn a mock external ROS2
   controller (or the `ros2_cmd` self-loop) that drives `setup_pick_place_controller(target_source="ros2_cmd")`
   and assert cube delivery via the existing `simulate_traversal_check`. Needs no external broker; converts
   the entire ROS2 row from SYNTHETIC → MEASURED in one stroke, and is the one test that proves the bridge
   actually closes the loop. (`pick_place.py:9038`, `CP-NEW-ros2-moveit2-franka.verify_args`.)
2. **Resolve the rclpy ABI question.** Either ship a matched-ABI rclpy build, or formally bless
   rosbridge-only as the live path and de-scope rclpy templates (`sim2real-validation.md:3,355`). Install
   `ros-mcp` (in `requirements.txt:12` but absent from env) to bring the 11 live tools out of `None`-sentinel
   death.
3. **Stand up the real-robot driver + recorder layer.** Implement the software-first steps from
   `sim2real-validation.md:166-176` (schema fields + `record_real_rollout.py` + T5 driver) so T5/T6 can
   produce a first artifact pre-hardware.
4. **Prove the MoveIt2/cuMotion emitter against a live node** (the franka_moveit2 chain is highest-value).
5. **Fix the capability map:** correct the stale `bridge_tools.py:5-6` STUB docstring (OPC-UA/MQTT are real),
   and tag `create_ros2_scene_harness` ABSENT/blocked-on-Phase-0.3 instead of implying it ships here.

---

## Key files

- `service/isaac_assist_service/chat/tools/handlers/ros2.py:33-122,207,416,492,598,758,800,1007,1069,1111-1131`
- `service/isaac_assist_service/chat/tools/handlers/pick_place.py:310-312,365,556-562,1574,9038-9116`
- `service/isaac_assist_service/chat/tools/handlers/robot.py:4344,5753-5818,6911,7291,7296`
- `service/isaac_assist_service/chat/tools/handlers/diagnostics.py:3761,5862`
- `service/isaac_assist_service/chat/tools/bridge_tools.py:5-6,54-106,497,667,712,759`
- `service/isaac_assist_service/chat/tools/ros_mcp_tools.py`
- `service/isaac_assist_service/chat/tools/handlers/_dispatch.py:90-113`
- `service/isaac_assist_service/multimodal/sub_phase_31b_industrial_bridges_full.py:14-15,218-221`
- `service/isaac_assist_service/multimodal/sub_phase_81c_moveit_cumotion_bridge.py:351-385`
- `workspace/templates/CP-NEW-ros2-moveit2-franka.json` (verify_args)
- `docs/research/2026-05-27-sim2real-validation.md:3,22-36,54-61,77,90,91,95-96,133,140,166-176,355`
- `docs/notes/2026-05-27-friction-grip-sim-real-gap.md`
- `docs/notes/MASTER_EXECUTION_PLAN.md:13,22,28,37`
- `docs/research/2026-05-27-expansion-roadmap.md:12,54,156`
