# E2E Trace — Screw-Driving (drive a screw into a threaded hole, stop at a torque limit)

**Scenario id:** e2e2-screw-driving
**Request (verbatim):** "drive a screw into a threaded hole and stop at a torque limit"
**Robot:** franka_panda
**Domain:** assembly / contact-rich insertion (fastening)
**Date:** 2026-06-09
**Closest real template:** `workspace/templates/CP-NEW-screw-driving-impedance.json` (exact match — a template for this exact request already exists)

---

## 0. TL;DR verdict

There is a **dedicated, well-authored template** for this exact request
(`CP-NEW-screw-driving-impedance.json`) and a **dedicated composite handler**
(`handlers/insertion.py::setup_insertion_controller(strategy="helical_screw")`).
But the entire capability is **plan-only (dry_run)** and the success that the
request asks for — *"stop at a torque limit"* — is **never physically produced
or graded** by anything in the pipeline. The screw is a rigid Cylinder that is
never gripped, never turned, never threaded; the "torque limit" is a numeric
field in `verify_args` that no verifier reads; and the function-gate that
actually decides PASS/FAIL grades **pick-and-place cube delivery geometry**
(`in_xy and above_floor and at_rest`), which is the wrong verdict shape for an
in-place fastening task.

This trace reveals a **NEW CLASS-LEVEL gap**: the platform has no
**torque/force-terminated actuation class** — no primitive that *spins a joint
under a torque cap and stops when the cap is reached*, and no verifier that
asserts a *gesture terminated on a force/torque threshold*. Screw-driving,
nut-running, bottle-cap-tighten, valve-seating, and clutch/friction-fit
fastening are a whole family that needs this, and none of them can produce a
real outcome today. This is distinct from the already-inventoried P10
("`setup_insertion_controller` dry_run") and P11 ("no insertion-depth grader").

---

## 1. The full user-action sequence (target scene + outcome)

Legend: **[USER]** human turn · **[LLM]** assistant tool-planning turn ·
**[SYSTEM]** Kit / handler / gate machinery.
Cost tag: **[CHEAP-static]** = USD authoring or pure-Python plan dict, no
physics stepping · **[EXPENSIVE-physics]** = PhysX simulation / settle / gate.

### Phase A — request → retrieval → template selection

1. **[USER]** "drive a screw into a threaded hole and stop at a torque limit."
2. **[SYSTEM] [CHEAP-static]** Retrieval (`chat/tools/template_retriever.py` +
   `multimodal/role_template_index.py`) embeds the request and matches
   `intent.structural_tags` on the template corpus. This request hits
   `isaac:industrial.screw_driving`, `isaac:operation.fasten`,
   `isaac:assembly.torque_gated`, `isaac:gesture.helical_descent`,
   `isaac:fastener.m3_m6` → **`CP-NEW-screw-driving-impedance.json`** is the
   top hit (`intent.pattern_hint = "insert"`, template lines 85–112).
3. **[LLM] [CHEAP-static]** Reads the template `code` block (lines 32) and
   `role_defaults` (lines 144–180) and emits the tool calls below. This is the
   "happy path" — the LLM does not have to invent the scene; the canonical
   instantiator (`chat/canonical_instantiator.py`) can hard-instantiate it.

### Phase B — scene authoring (all CHEAP-static, no physics)

Each call below is a real registered handler. Tags are the verified state.

4. **[LLM]→[SYSTEM] [CHEAP-static]** `create_prim` DomeLight + Ground + Table
   — `handlers/scene_authoring.py` (`create_prim` registered, schema
   `tool_schemas.py`). Pure USD authoring. ✔ EXISTS.
5. **[LLM]→[SYSTEM] [CHEAP-static]** `set_physics_scene_config(enable_gpu_dynamics=False, broadphase=MBP)` — `handlers/physics.py`. ✔ EXISTS.
6. **[LLM]→[SYSTEM] [CHEAP-static]** `robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0,0,0.75], orientation=[0.707,0,0,0.707])` — `handlers/robot.py:3940+`. ✔ EXISTS, spawns Franka at home joints (the wound-start fix from the UR10 work doesn't apply to Franka).
7. **[LLM]→[SYSTEM] [CHEAP-static]** `create_prim TappedPlate` (solid Cube) + `apply_api_schema PhysicsCollisionAPI` + `set_attribute physics:approximation=convexHull`. ✔ EXISTS.
8. **[LLM]→[SYSTEM] [CHEAP-static]** `create_prim TappedHole` (narrow Cylinder r=0.003, h=0.024) co-located **inside** the plate volume + collision/convexHull. ✔ EXISTS. **⚠ KEY SCENE LIE #1:** the "tapped hole" is a *solid* cylinder, not a subtracted cavity. There is no boolean-subtraction / negative-space primitive (`create_prim` only makes solid prims). The screw physically *cannot enter* — it can only contact the hole-top surface. (Template's own `failure_modes[1]` admits this, lines 72.)
9. **[LLM]→[SYSTEM] [CHEAP-static]** `create_prim Screw` (Cylinder r=0.0025, h=0.025) + loop `apply_api_schema` for RigidBody/Collision/Mass/PhysxRigidBody + `set_attribute physics:mass=0.005` + `apply_physics_material steel` + `bulk_set_attribute sleepThreshold=0, solverPositionIterationCount=16`. ✔ all EXIST.
10. **[LLM]→[SYSTEM] [CHEAP-static]** `add_force_torque_sensor(sensor_path="/World/Franka/FtSensor", parent_path="/World/Franka/panda_hand", threshold=15.0, noise_std=0.03)` — `handlers/sensors.py:473`. ✔ EXISTS **as a build-time authoring stub** (writes sensor config attrs). It is *not* a live force-reading stream during the gate sim. (Inventory section A correctly tags it "build-time authoring".)

### Phase C — the actuation (THE request) — all dry_run, no physics

11. **[LLM]→[SYSTEM] [CHEAP-static]** `monitor_joint_effort(articulation_path="/World/Franka", duration_seconds=30.0)` — `handlers/diagnostics.py:857 (_gen_monitor_joint_effort)`. This is **codegen** that builds a PhysX `subscribe_to_physics_step_events` callback recording joint efforts. ✔ EXISTS but: it only *records* effort history into a buffer; it does **not** terminate motion at a torque cap. It is a passive logger, not a controller, and it is never run during the gate (the gate runs its own `simulate_traversal_check`, not this monitor).
12. **[LLM]→[SYSTEM] [CHEAP-static]** **`setup_insertion_controller(robot_path="/World/Franka", strategy="helical_screw", start_pose=[0,-0.25,0.815], target_pose=[0,-0.25,0.800], target_path="/World/TappedHole", target_frame="panda_hand", total_rotation_deg=450, dry_run=True)`** — `handlers/insertion.py:276`. This is the heart of the request. What it actually does (verified by reading the handler):
    - Looks up `_STRATEGY_DEFAULTS["helical_screw"]` (insertion.py:68–79): Kx=[300,300,40], Kr=[20,20,8], 6 waypoints, 450° total Z-rotation.
    - Composes 3 sub-calls, **all dry_run=True**: `setup_impedance_controller` → `set_compliance_params` → `follow_trajectory_with_compliance` (insertion.py:360–420).
    - `_gen_helical_screw` (insertion.py:149–175) generates 6 pose waypoints, each coupling Δz (−2.5mm) with a quaternion advancing 75° about world-Z. **It returns a list of pose dicts. It never touches PhysX.**
    - **`dry_run=False` raises `NotImplementedError`** (insertion.py:351–358): *"live mode requires Kit RPC + ros2_control bridge + torque-mode robot."*
    - Returns a plan dict (`success: True, dry_run: True, trajectory: [...]`).
13. **[LLM]→[SYSTEM] [CHEAP-static]** Success probes `get_world_transform(Screw)`, `get_world_transform(TappedPlate)`, `get_joint_torques("/World/Franka")` — `handlers/physics.py:2158`. `get_joint_torques` reads `state:angular:physics:appliedJointTorque` off each joint via `queue_exec_patch`. ✔ EXISTS and is *live-readable*, BUT with no controller having driven the arm, the wrist torque reads its settle value (~0), never the "1.0 N·m cap."

### Phase D — the gate (the actual PASS/FAIL) — EXPENSIVE-physics

14. **[SYSTEM] [EXPENSIVE-physics]** The function-gate (`scripts/qa/gate_one.py`) is what assigns the real verdict. It: `new_stage()` → `execute_template_canonical(CP-NEW-screw-driving-impedance)` → `settle_after_canonical()` → **`simulate_traversal_check`** with `simulate_args` (`cube_path="/World/Screw", target_path="/World/TappedHole", duration_s=180`).
15. **[SYSTEM] [EXPENSIVE-physics]** `simulate_traversal_check` (`handlers/diagnostics.py:~3968`, success math at **diagnostics.py:4449**) steps PhysX for `duration_s`, then for a **single-cube** template computes:
    `success = in_xy and above_floor and at_rest and upright_ok`
    i.e. *did the Screw rigid body end up inside the TappedHole's XY bbox, above the floor, and at rest, standing upright.*
16. **[SYSTEM] [EXPENSIVE-physics]** **OUTCOME:** With **no controller ever stepping the arm** (everything in Phase C was dry_run), the Franka does not move, does not grasp the Screw, does not drive it. The Screw sits at its spawn pose `[0,-0.25,0.808]` (its `settle_state`, template line 33–37). That spawn pose **is** inside the TappedHole XY bbox, above the floor, at rest, and upright — so `simulate_traversal_check` likely returns **`success: True` by accident of placement**, while *zero screw-driving happened*. This is a **false-positive of exactly the family MEMORY warns about** ("gates lie / chronic false positives"). The verdict does not even look at `appliedJointTorque`, `screw.z` vs flush, or anything torque-related.

### Phase E — what the user asked for vs what they get

17. **[USER] expectation:** screw rotates down into the hole; motion stops the instant wrist torque hits the limit; a report of "seated at T N·m."
18. **[SYSTEM] reality:** a plan dict describing a helical trajectory + a pick-place geometry gate that ignores torque entirely. No screw rotates. No torque cap is enforced or detected. **The single most load-bearing word in the request — "stop at a torque limit" — has no executable or gradable representation.**

---

## 2. Grounding — file:line citations

| Claim | Evidence |
|---|---|
| Exact template exists | `workspace/templates/CP-NEW-screw-driving-impedance.json:1-182` |
| Success defined as screw.z<flush AND wrist-torque==cap | template `goal` line 3; `verify_args` lines 38–53 (`expected_wrist_torque_target_nm:1.0`, `expected_flush_threshold_z_m:0.786`) |
| Helical strategy & gains | `handlers/insertion.py:68-79` (`helical_screw` defaults), `:149-175` (`_gen_helical_screw`) |
| Composite is dry_run-only; live raises | `handlers/insertion.py:351-358` (`NotImplementedError`) |
| All 3 sub-controllers are dry_run-only | `handlers/compliance.py:185-191, 398-405, 537-539, 677-682, 1013-1021` (every live path raises `NotImplementedError`) |
| FT sensor is build-time authoring, not a live stream | `handlers/sensors.py:473`; inventory §A "build-time authoring" |
| `monitor_joint_effort` is a passive logger, not a stopper | `handlers/diagnostics.py:857` (`_gen_monitor_joint_effort`) |
| `get_joint_torques` is live but reads settle value (~0) here | `handlers/physics.py:2158` |
| Gate grades pick-place delivery geometry | `scripts/qa/gate_one.py:1-9` (runs `simulate_traversal_check`); success math `handlers/diagnostics.py:4449` |
| No torque-stop / spin-drive / tool-attach primitive | grep over `handlers/` for `torque_stop|drive_to_torque|spin_joint|velocity_drive|attach_tool|tool_changer|spindle|continuous_rotation` → **0 hits** |
| Tapped hole is solid, not subtracted | template `failure_modes[1]` line 72; `create_prim` makes solid prims only |
| ros2_control bridge present only as ext stub | `exts/isaac_6.0/.../ros2_control_bridge.py` + `tests/test_ros2_control_bridge.py`; never wired to handlers (handlers all still raise NotImplementedError) |
| Kimate assets: only decorative screw meshes, no driver/bit/torque-tool | `kimate_assets/assets/Collected_nova_carter/Parts/M4x8_Button_Head_Hex_Screw__JFD.usd` etc.; no screwdriver/spindle/EOAT-bit asset anywhere under `kimate_assets/assets` |

---

## 3. Tool gaps surfaced (NEW — not the ones already in TOOL_GAP_INVENTORY_V2)

The inventory already has **P10** (`setup_insertion_controller` dry_run blocked
on ros2_control) and **P11** (no insertion-depth grader). The following are
**distinct, newly surfaced** by tracing *this* request to its outcome:

- **G1 — `drive_joint_to_torque` / `spin_under_torque_cap` (torque-terminated actuation primitive).** The request is "spin until torque limit." Nothing spins a joint and stops on a torque/force threshold. `monitor_joint_effort` only *records*; the impedance stack only *plans*. This is the missing **actuation class**, independent of whether ros2_control ever lands — it can be done in pure PhysX with a velocity-drive on a revolute joint plus a per-step `appliedJointTorque` watchdog. **Blast: screw-driving, nut-running, valve-seat, bottle-cap, clutch/friction-fit.**
- **G2 — `verify_torque_terminated_gesture` / torque-stop verifier class.** No verifier asserts "the gesture terminated because torque reached cap (within tolerance) AND depth ≤ flush." `verify_args` carries `expected_wrist_torque_target_nm`, `expected_flush_threshold_z_m`, `expected_z_force_cap_n` — **all dead fields no code reads** (grep: zero consumers in `scripts/qa/` or `verifier_registry.py`). The gate substitutes pick-place delivery geometry, producing a structural false-positive. **Blast: every force/torque-gated assembly template.**
- **G3 — `attach_tool` / EOAT bit/spindle mount primitive.** A screwdriver task needs a driver bit rigidly fixed to `panda_hand` and a screw coupled to the bit tip. There is no tool-attach / fixed-joint-to-EE / tool-changer primitive exposed (only the banned suction-FJ hack inside pick_place). The screw is never even grasped. **Blast: any "robot wields a tool" task — driver, wrench, gluegun, deburr, polish, weld-torch.**
- **G4 — negative-space / boolean-subtract primitive for true insertion targets.** `create_prim` only authors solid geometry; a "threaded hole" can only be faked as a co-located solid cylinder the screw cannot enter. Without a mesh-subtract (or a thread-helix collision asset) there is no surface for real thread engagement — torque can only ever come from surface contact, not threading. **Blast: peg-in-hole, screw, dowel, connector-insert, bearing-press.**
- **G5 — `simulate_traversal_check` is mis-dispatched for in-place fastening.** The gate runner (`gate_one.py`) unconditionally calls the pick-place delivery checker even for a 0-handoff in-place fastening template whose `pattern_hint="insert"`. The gate needs **verdict-shape dispatch on `intent.pattern_hint`** (insert/fasten ≠ deliver). Today insertion templates are graded by the wrong gate. **Blast: every `pattern_hint ∈ {insert, fasten}` template.**

---

## 4. THE class-level finding (key deliverable)

**This scenario reveals a missing CONTROLLER CLASS *and* a missing GATE CLASS,
analogous to how the humanoid-cabinet trace proved pick-place breaks on
articulated doors.**

The pick-place paradigm (approach → grasp → carry → place → release, graded by
"did the body arrive in the target bbox at rest") is the platform's *only*
real, physics-backed, gradable controller+gate pair. **Fastening is a
fundamentally different control class:** the terminal condition is not a
*pose* (cube in bbox) but a *force/torque event* (wrench reaches cap). The
platform has:

1. **No torque/force-terminated actuation** (G1) — a controller that *drives
   under a wrench cap and stops on the cap*. The impedance stack is the
   intended home for this but is 100% dry_run; even when un-stubbed it plans
   compliance, it does not implement "rotate the screw and halt at T N·m."
2. **No force/torque-terminated verifier** (G2) — a gate that grades *"the
   gesture stopped because the cap was reached at the right depth."* Every
   force/torque field in the templates is inert; the only live gate measures
   delivery geometry and silently passes a scene where nothing happened.

Until both exist, **the entire torque/force-gated fastening family**
(`CP-NEW-screw-driving-impedance`, `CP-NEW-bottle-cap-tighten`,
`CP-NEW-peg-bushing-impedance`, `CP-NEW-yrkesroll-assembler-snap-fit`,
`CP-NEW-tactile-insertion`, `CP-NEW-narrow-clearance-insertion`,
`CP-NEW-turn-faucet`, valve/nut-runner roles) is **structurally unexecutable
and ungradable** — they retrieve, hard-instantiate, and emit a clean plan dict,
then get a *pick-place* PASS/FAIL that has nothing to do with whether the
fastening physically succeeded. The honest status of this whole family is
"authored, plan-only, falsely-gradable," not "working."

The good news: unlike faithful-suction (which needs a research-grade compliant
contact model), **G1+G2 are buildable in pure PhysX without the ros2_control
bridge**: a revolute velocity-drive + per-step `appliedJointTorque` watchdog
for the controller, and a verifier that reads the same `appliedJointTorque`
timeseries + screw-z vs flush. That makes torque-terminated fastening the
cheapest large-blast capability the platform is currently missing — and the one
that would convert an entire authored template family from "plan-only" to
"real."

---

## 5. Outcome statement (for the schema)

The request retrieves a purpose-built template and a purpose-built composite
handler, authors a complete, correct static scene cheaply, and emits a valid
helical-descent **plan dict** — then **nothing physical happens**: the screw is
never gripped or turned, the torque limit is never enforced or detected, and the
function-gate returns a likely **false-positive PASS** by grading pick-place
delivery geometry of an un-driven, already-in-place screw. The load-bearing
clause "stop at a torque limit" has **no executable controller and no verifier**
anywhere in the system.
