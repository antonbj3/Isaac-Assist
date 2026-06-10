# E2E Gap Findings (2nd-batch gap-scenario sweep) — Isaac Assist

**Date:** 2026-06-09
**Scope:** 17 *new* end-to-end gap scenarios run against the platform, across 7 domains the V2 inventory barely touches: service/domestic (4), datacenter (2), assembly/contact-rich (4: reorient, screw, snap-fit, weld-seam), dexterous (1), coating (1), flexible-cell (1), imitation-learning (1), HRC (1), mobility/legged (1).
**Method:** Each scenario was traced to actual handler code (file:line cited in the per-scenario `e2e2_*.md` notes). A finding is recorded as **NEW CLASS-LEVEL** only when it names a missing *architectural block* (a whole controller/gate/primitive CLASS that a task-FAMILY needs), not a single template. Every claim deduped against `TOOL_GAP_INVENTORY_V2.md` (V2). Effort key matches V2: **S** ≤ ~1 day glue, **M** = new handler + gate wiring, **L** = new subsystem, **research** = blocked on an absent dependency.
**Recurring shape:** all 17 are variants of the canonical humanoid-cabinet discovery — *"pick-place + delivery-gate breaks on X → needs a new controller class AND a new gate class for X."* The 2nd batch shows X is not one thing (articulated doors) but a **category**: articulated joints, deformables, continuous paths, force/torque terminal-conditions, in-hand grasp quality, moving destination frames, external human input, legged runtime.

---

## 1. Ranked NEW CLASS-LEVEL gaps

Ranked by **domain-blast** = number of distinct task-families/domains the missing block gates (each family below maps to dozens-to-hundreds of authored or Kimate-asset templates). Where V2 already *names part* of the block, the delta is called out explicitly — the recurring delta is **V2 names the controller but never the matching gate class**, so even a correct controller would be unmeasurable (silent false-positive).

### EC-1 — Articulated-joint manipulation as a CATEGORY (controller + state-gate + anti-oracle) — **blast: 6+ families**
The single highest-blast finding. V2's **M10** names *one* sub-case (revolute hinged door, "open_door / articulated_pull") and its **kernel** (`sub_phase_70c_articulated_drag_controller.py`) is landed but **its handler `articulated_pull.py` was never built** (grep: 0 callers) — so even M10 is wired to nothing. The 2nd batch proves articulation is a **category with at least three distinct controller sub-classes plus shared gate/anti-oracle infrastructure that V2 entirely omits**:
- **EC-1a Translate-handle-along-arc/line** (door/drawer/rack-pull) — M10's case; still un-handlered.
- **EC-1b Axial in-place twist** (knob/dial/valve/faucet/rotary-switch) — *grasp point lies ON the rotation axis → pure EE roll, ~zero XYZ translation*. A Cartesian-waypoint drag (the drawer-open spline) **cannot** track it (nothing to chase in XYZ); the M10 kernel is metres-only (grep rad/angular/torque = 1, a docstring). Needs a `wrist_roll_twist` controller. (from `svc-stovetop-knob`; real `knob_front_left_joint` PhysicsRevoluteJoint, axis=X, 0–180°.)
- **EC-1c Sequenced / nested / passive-driven articulation** (fridge = revolute door → prismatic shelf → place on moving shelf, while a 2nd arm holds the door) — a **constraint-aware controller that drives PASSIVE joints by contact force**, not joint-target teleport. (from `svc-fridge-place`; Lightwheel fridge RevoluteJoints carry **no DriveAPI** → free-swinging, so the only "open" tool `set_joint_targets` teleports them = sim2real cheat, **same banned family as FixedJoint-grip**.)

Shared infrastructure **all three need and none of which exists**:
- **Articulation-angle / joint-state SUCCESS GATE** — *completely absent.* Every gate (`gate_one.py`, `FunctionGateArgs` `_models.py:351`, `simulate_traversal_check`) is delivery-XY + upright-dot only. There is no `joint_path + target_angle + tolerance_deg` verdict anywhere → every drawer/knob/door/valve/rack task is ungradeable or false-passable. CP-NEW-drawer-open ships `simulate_args=null` (un-gated); CP-NEW-robohive-door-open had to *invent* a bespoke `success_criterion=joint_angle`. **This gate-blindness is the load-bearing delta V2's M10 misses.**
- **Anti-oracle contact-correlation guard** — `set_joint_targets` (physics.py:174) writes the joint's own DriveAPI target → joint moves *without the robot touching it* (revolute analogue of the banned FixedJoint-grip). Needs EE-contact + correlated wrist motion to count.
- **Articulated-state-gated sequencer** — condition controller-2 on controller-1 reaching a JOINT position (e.g. DrawerJoint ≥ 0.25 m), not a robot-done flag. `pose_sequence` (pick_place.py:8929) is sensorless pose replay; composing two pick-place calls just races them.

**Families gated:** stovetop/oven/valve/faucet (twist) · fridge/oven/dishwasher-rack/filing-cabinet/tool-chest (nested) · cabinet/drawer (pull) · **Kimate's 243 articulated appliances**. **Effort:** M per controller sub-class (kernel exists for 1a); **M** for the shared joint-state gate (highest ROI — one gate unblocks the whole category); **S** anti-oracle guard. **Sources:** svc-fridge-place, svc-stovetop-knob, svc-cabinet-fetch, svc-dishwasher-load.

### EC-2 — Reach-into-cavity → grasp → extract-OUT (non-top-down pick + containment/extraction gate) — **blast: 5+ families**
Distinct from EC-1 (opening the enclosure) and from V2's place-INSIDE traces: this is the **retrieval** class. `setup_pick_place_controller` is **top-down ONLY** (APPROACH z+0.12 → DESCEND straight-down → GRASP → LIFT z+0.20; pick_place.py:392,754,776) with **no `approach_direction` and no WITHDRAW leg** — an item under a cabinet overhang or between drawer walls is unreachable (descend collides with the body). Needs:
- **Non-top-down pick controller** with a WITHDRAW leg (pull grasped item out along the open-axis *before* lifting), tilt/side entry.
- **Containment/extraction GATE** — scores "item that started INSIDE an enclosure is now OUTSIDE its AABB, at rest on the counter, enclosure still open." Today's gate scores delivered-TO-a-bbox only → the entire retrieve-from-enclosure family is **structurally unscorable**.

**Families gated:** drawer-fetch, fridge-retrieve, dishwasher-unload, oven-retrieve, deep-tote-pick, machine-enclosure part-retrieval, mug-from-cabinet. **Effort:** M (controller) + M (gate). **Source:** svc-cabinet-fetch.

### EC-3 — Continuous surface-process: trajectory-follow controller + path-integral gate + TCP recorder — **blast: 10+ families**
Highest blast by raw family count. Every shipped controller is a discrete **waypoint/grasp** machine scored on **terminal object state**; surface processes are **continuous-trajectory** machines scored on a **path-integral** property (cross-track error, coverage %, constant travel-speed, contact-force window) that **no composition of pick-place/move_to_pose/plan_trajectory can produce**. Three coupled missing classes, one per layer, and shipping any one alone passes **zero** tasks:
- **`follow_cartesian_path` / `surface_process_follow` CONTROLLER** — drive a multi-segment path to completion at commanded speed, holding tool orientation. `move_to_pose` rmpflow pulls `get_next_articulation_action()` **ONCE** and applies a single action with **no convergence loop** (robot.py:2393-2396) → a 14-waypoint raster collapses into near-stationary jitter; `lula_rrt` plans but "caller must replay" and nothing replays it; `linear_motion` is an internal cuRobo lift-constraint inside pick-place, not an external path-follower. **A rigid/standoff seam-follow (laser/plasma cut, paint, dispense) needs only cuRobo — already live, ships now, NO torque bridge.**
- **`simulate:surface_coverage` / `path_tracking` GATE** — `verifier_registry` knows only `cube_delivered`/`upright_at_rest`/`human_safety_zone`. A spray gun held 0.10 m above a panel never enters its bbox → a **flawless raster and a frozen robot both score success=False** (false-negative-by-construction). Templates carry `coverage_grid`/`min_coverage_fraction`/`max_deviation_mm`/`weave_amplitude_mm` — **zero registered readers**. The `WeldSeamSpec`/`score_scenario`/`update_seam_progress` machinery exists **unwired** (sub_phase_99:73,215,255).
- **`record_tcp_trajectory` DATA primitive** — `record_trajectory` (robot.py:3779) is **joint-space only**; coverage needs end-effector/tool-tip world poses (FK replay). Templates' own failure-mode admits "if the consumer skips FK the coverage check is meaningless."

**Families gated:** seam weld, spray-paint/powder-coat/plating, deburr, polish, sand, sealant/glue bead, laser/plasma/water-jet cut, NDT/inspection-scan (differ only in contact-mode rigid/standoff/compliant and coverage geometry 1-D/2-D/3-D). A near-1:1 template (`CP-NEW-yrkesroll-paint-sprayer-trajectory`) is parked at "function-gate pending Kit RPC" precisely because the execution+grading half of this class doesn't exist. **Effort:** L (controller, but rigid-mode ships with no torque bridge) + M (gate) + S (TCP recorder). **Note:** also surfaces a `project_standoff_along_normal`/raycast-to-surface geometry primitive (constant-Z hardcode misses tilted/curved panels). **Sources:** e2e2_weld-seam, spray-coat.

### EC-4 — Force/torque-TERMINATED actuation: drive-and-stop-on-wrench controller + seat/torque verifier + retry-loop — **blast: 8+ families**
Pick-place's terminal condition is a **POSE** (body at rest in bbox); fastening/seating's terminal condition is a **FORCE/TORQUE EVENT** (wrench reaches cap / click). The platform has **neither** a controller that drives-and-stops on a wrench cap **nor** a verifier that grades "stopped because the cap was reached at correct depth." Three coupled classes:
- **Force-gated / closed-loop assembly CONTROLLER** (`press_until_seated` / `setup_seat_controller` / `drive_joint_to_torque`) — take `seat_predicate + max_attempts + force_cap + backoff` and run descend→sense→(seated? stop : back-off + re-align + re-descend). `setup_insertion_controller` runs the descent **ONCE**, no `max_attempts`/reseat arg (insertion.py:276/449). The intended home (impedance/admittance/compliance stack) is **100% dry_run** — live mode raises `NotImplementedError` (insertion.py:351; all of compliance.py), **blocked on the absent ros2_control torque bridge = V2 P10** for the *compliant* case. **But the discrete-joint case is buildable in pure PhysX today** (revolute velocity-drive + per-step `appliedJointTorque` watchdog) — *highest-blast cheapest missing capability*, converts a whole authored template family from plan-only to real with no bridge.
- **Seat/click/torque GATE** (`verify_seat` / `simulate_assembly_check` / `verify_torque_terminated_gesture`) — emit `{seated, click_detected, final_z, impulse_peak_Ns, attempts}` from the `PhysxContactReportAPI` impulse stream. `verify_args.expected_wrist_torque_target_nm` / `expected_flush_threshold_z_m` / `expected_z_force_cap_n` are **DEAD fields, zero consumers**. No gate scores a seat → all 6+ force-gated-insert templates are unscorable on their real criterion and false-positive any near-XY drop.
- **`loop_until` / `retry_until_predicate` control primitive** — a predicate-terminated attempt-budget loop. `execute_contact_sequence_plan` carries `retry_count` (contact_sequence.py:118) but `execute_plan` **never consumes it** (dead); `execute_with_retry` (workflow.py:930) retries broken CODE, not failed seats. This generalizes V2's Tier-4 leaf `loop_workflow` to **predicate-terminated**.

**Families gated:** screw-driving, bottle-cap-tighten, peg-bushing, snap-fit ("press until click, retry if not"), tactile-insertion, narrow-clearance, turn-faucet, nut/valve roles. **Effort:** **M** for the PhysX discrete-joint controller + torque gate (no bridge needed — do this first); compliant-force variant is **research** (P10). **Delta vs V2:** V2 line 159 files this as a single Tier-4 low-blast leaf; the trace shows it is **class-level** (controller + gate + loop), not a leaf. **Sources:** e2e2-screw-driving, e2e2-snap-fit.

### EC-5 — Grip-preserving in-air reorient controller + axis-aware pose-target gate — **blast: 5+ families**
V2 **inventory line 162** names *only* a `setup_reorient_controller`/flip-station gap and **entirely misses the gate-blindness half**. The 2nd batch shows the two gaps **combine into a silent false-positive**:
- **CONTROLLER:** no grip-preserving in-air reorient. The only "active flip" template (A69) is built on `move_to_pose` = a single-shot reactive RMPflow nudge (one joint action, applied once; robot.py:2393-2396) with no convergence loop and no grip-hold through rotation; pick-place's only orientation knob is world-Z drop-yaw (pick_place.py:4139). Neither can roll/pitch a HELD part to a target quat.
- **GATE:** success is `require_upright = cube_up.world_up ≥ 0.95` (diagnostics.py:4443-4449) — a single scalar dot that **accepts a part flipped about the WRONG axis** (180° about Z = same face up), or never flipped at all (identity already upright), **identically** to a correct 180°-about-Y flip. A69's `expected_final_rotation_quat` / `flip_target_orientation` / `target_rotation_tolerance_deg` keys are **DEAD** (no reader).
- Combined effect: the controller can't complete the flip **and** the gate can't detect that it didn't → **green PASS on a flip that never physically happened.**

**Families gated:** turn-over, present-face-B, set-on-edge, rotate-to-mate, regrasp-to-reorient (assembly/kitting). **Effort:** M (controller) + S→M (axis-aware pose gate). Also surfaces: grip-persistence-across-controller-recalls / first-class `place_down` primitive, and a two-stage regrasp variant (set on fixture, re-approach) for the unreachable-far-face case. **Source:** reorient-flip.

### EC-6 — Dexterous actuated-finger grasp EXECUTION + INTEGRITY gate — **blast: 4+ families**
V2 **M8** names the *controller* ("3-finger / multi-finger adaptive grasp", research). The 2nd batch shows M8 is **incomplete on two of three coupled pieces**: it does NOT name the **finger-closing primitive** nor the **in-hand-quality gate class** — and without the gate, even a correct controller is **unmeasurable**. The whole stack treats the EE as an **oracle**: `grasp_object` Step-3 "close gripper" is a literal `print()` (robot.py:2844), it hardcodes `load_supported_motion_policy_config('Franka','RMPflow')` for **every** robot, `setup_pick_place_controller` raises "Unsupported robot_family" on anything but franka/ur10/g1_arm (so allegro/robotiq/shadow are **unreachable**), and the G1 dex hand has 7 finger joints but `_FINGER_JOINTS=()` (welded shut, never actuated). Three missing pieces:
- **Multi-finger CONTROLLER family** driving N finger joints (Allegro USD exists; the hand must be its **own articulation + cuRobo config**, NOT a child of `panda_hand` — that corrupts the Franka articulation = PhysX blowup, which is why `CP-NEW-adaptive-3finger-gripper.json:25` **intentionally deletes its own fingers**).
- **Finger-closing PRIMITIVE** + extended `.isaac_grasp` schema carrying preshape / contact-set / per-finger force (today: parallel-jaw/suction posing only, robot.py:3035).
- **Grasp-INTEGRITY GATE** — score in-hand pose stability + contact-set coverage + orientation preservation, NOT delivered-XY. `grip_latched` reads the suction-FJ log an articulated-finger grasp never writes (diagnostics.py:3435-3514). **Grasp success is scored by where the object LANDS, never by HOW it was held** → a green `delivered_ok` run with zero fingers closed.

**Families gated:** 3-finger/Allegro/Shadow/Robotiq wrap grasps, in-hand reorientation, irregular/non-convex grasping, force/compliance grasping. **Effort:** research (controller, = M8) + L (primitive+schema) + L (integrity gate). **Note:** no template/object represents an irregular/non-convex graspable part (grep rubik=0) even though `simplify_collision` can author SDF/convex-decomp colliders (capability exists, unused). **Source:** three-finger-grasp.

### EC-7 — Moving-destination place-mode + slotted/edge-on insertion (dishwasher/oven-rack family) — **blast: 4+ families**
The strictly-harder successor to EC-1/EC-2: actuate an articulation, *then* insert into the **slotted, moving** fixture. Three orthogonal gaps:
- **`set_destination_frame` / dest-tracking place-mode** — re-read a MOVING destination prim's live world transform each frame (place-side analogue of `cube_tracking`, which only tracks the pick SOURCE). Drop is baked as **stale** `DEST_PATH`/`DROP_TARGET` coords at setup (pick_place.py:600,69-70) → a pulled-out prismatic rack invalidates the target.
- **Slotted / edge-on insertion place-mode** (`place_orientation` + tine-aware approach) — pick-place only drops flat/gripper-down onto a top face; a rack slot is **side-in, edge-on, between-tines** insertion on the ORIENTATION axis. The insertion controller is not wired to pick-place source/dest plumbing and treats slot walls as avoid-obstacles.
- **Gate inverts** — `_cube_support` raycasts straight DOWN + `require_upright` ≥0.95; both **INVERT** for an edge-on slotted plate (a correct plate is NOT upright; the ray hits a tine that descends from the target → silent **false-pass**).

Pieces to chain it exist but **are not composed**: `set_joint_targets` (open rack) + the **orphaned** Phase-70c PD drag controller + `setup_pick_place_controller` (place) — no dispatcher links them. **Families gated:** dishwasher-load, oven-rack, fridge-drawer, autoclave-tray, cutlery-basket (every slotted articulated fixture). **Effort:** M (dest-tracking) + M (slotted place-mode) + M (orientation-aware gate). Also needs a thin-disc/plate workpiece profile (plates are stand-in cubes today). **Source:** svc-dishwasher-load.

### EC-8 — Horizontal two-rail slide-insert (rack-bay) controller + slot-engagement gate — **blast: 4+ families**
INSERTION breaks on a rack BAY the way pick-place broke on a door. The entire `setup_insertion_controller` family (insertion.py:50-108: spiral_search/helical_screw/snap_fit/impedance_descent) assumes a **single-axis VERTICAL descent** (tool-down quat + monotone-Z) into a side-unconstrained hole. A rack bay is a different kinematic class: **HORIZONTAL** insertion axis, level cantilevered carried body, **TWO parallel prismatic rail constraints co-satisfied** (yaw+roll≈0), long push under sustained force to a hard backstop, control point at the server's FAR edge (not the gripper frame). Needs:
- **`slide_insert` / `rack_insert` CONTROLLER** (level horizontal travel, two-rail co-constraint, far-edge tool-offset, push-to-backstop with force cap) — effort L.
- **`verify_slot_engagement` GATE** (both rails engaged + body level + at backstop + no protrusion) — `gate_one.py` only knows delivered/under_target so a roughly-parked primitive false-PASSes — effort M.
- **`check_dual_rail_alignment`** sub-primitive (yaw+roll+lateral co-alignment) — effort S-M.
- **UR10 level-carry EOAT** (fork or dual-cup bar) — a single suction cup can't hold a 1U chassis level & cantilevered — effort M.

**Families gated:** drawer/tray into slotted cabinet, PCB card into edge connector, magazine into feeder, cassette into load-lock, pallet into drive-in racking, book onto a tight shelf. **Effort:** L+M+S. **Distinct from** V2 M14 (`place_on_shelf`, slot-Z math) and P11 (generic mesh grader). **Source:** dc-rack-stack.

### EC-9 — 1D deformable-linear-object (DLO/cable) grasp-follow controller + connector mate-seat — **blast: 3+ families**
The deformable counterpart to the articulated-door finding: pick-place fundamentally breaks on deformables. `create_deformable_mesh` (physics.py:642) only makes a **2D cloth sheet** (the `rope_nylon` preset is a `PhysxDeformableSurfaceAPI` sheet, not a 1D Cosserat/PhysX-rope rod); no rod-chain generator. The runtime grasp `_attach_cube_to_ee` (pick_place.py:709) **welds to a rigid body center** via `get_world_pose()` — a deformable has no rigid center, so grasp-on-deformable **cannot compose**. The nearest canonical (`CP-NEW-wire-harness-route`) **self-admits it DELETES the cable into rigid rods** ("PhysX deformable-wire numerically unstable, velocity blow-up under grip"). Three coupled missing classes:
- **DLO grasp-follow CONTROLLER** (1D rod generator + grasp-and-follow a deformable) — blocks cable/hose/rope/suture/belt-thread/cloth-drape/gasket-o-ring.
- **Connector/port mate-and-seat CONTROLLER + mate-detection GATE** — `insertion.py` has only peg/screw/snap/cap strategies; no keyed-connector-into-socket model; no gate reads "mated/seated/latched" (it grades one rigid-body AABB center). Blocks RJ45/fiber/USB/power-connector, blind-mate backplanes, hot-swap blade/drive.
- **Datacenter asset/resolver class** — see EC-10.

**Effort:** research (deformable rod is a PhysX-stability research item) + M (connector controller+gate). **Source:** dc-cable-route.

### EC-10 — Datacenter / articulated-asset INTEGRITY pre-flight + name→USD resolver — **blast: 3+ domains (datacenter + all articulated-appliance domains)**
A cross-cutting **silent-empty-stage** hazard. Two reinforcing facts:
- **`Datacenter_NVD` is materials-only** — 15 `.mdl` skins, **ZERO geometry USD** (`find -name '*.usd*'` = 0); `asset_catalog.json` names Rack_42U / Fiber_Patch_Panel / DGX servers whose `usd_paths` point at an **absent** tree. No name→USD resolver for datacenter nouns. Hard blocker for the entire datacenter domain.
- **Articulated USDs silently yield 0 joints/0 rigids** — 8/9 local fridges have **EMPTY `resource/` dirs** → `Usd.Stage.Open` succeeds with an invisible un-articulated stub (missing sublayers are *warnings, not errors*). `build_scene_from_blueprint` **silently returns on missing-on-disk asset** (scene_blueprints.py:364-367) → an empty stage that *looks authored*.

Needs **`verify_articulation(path, min_joints)`** / **`assert_assets_present`** — a catalog-vs-payload + min-joints integrity preflight **surfaced to the planner**, so the LLM doesn't build on a broken/empty appliance. **Effort:** S. **#1 honesty pre-flight for the whole articulated-appliance + datacenter program.** **Sources:** svc-fridge-place, dc-rack-stack, dc-cable-route.

### EC-11 — Mid-task tool-changer / EOAT swap controller + "which-tool-mounted" gate — **blast: 3+ families**
The entire tool-changer / EOAT-changeover family has **no controller** that performs a swap as a temporal physics sequence and **no gate** that scores "which tool is mounted." Every swap template degenerates to **build-time teleport + FixedJoint weld + a delivery-gate masquerade** (cube-reaches-flange-bbox; `target_path=/World/UR10/tool0` → a `set_attribute(xformOp:translate)` teleport trivially yields success=True even if the jaw never released or the arm never moved). Three coupled missing primitives:
- **TC1 `swap_eoat` controller** — a play-until-arrive state machine (sibling of `setup_pick_place_controller`); `move_to_pose` is single-tick reactive so the arm never reaches the dock.
- **TC2 local-frame-correct mount** — `create_articulated_joint(fixed)` sets only Body0/Body1 rels, **no localPose baking** (robot.py:4604-4606) → tools float; the bake fix exists **only inside the `surface_gripper` path** (robot.py:6360) — needs lifting into a generic `mount_tool` / `bake_local_frame` verb.
- **TC3 `verify_tool_mounted` GATE** — assert exactly-one active flange FixedJoint + expected tool mounted + other tool seated in dock under physics. `verifier_registry` (512 lines) has **no** joint-identity/tool-mounted check; `verify_args` keys `expected_active_joint`/`expected_mounted_tool`/`expected_parked_tool` have **ZERO consumers**. **TC3 is also the #1 honesty gap for the whole `pattern_hint='other'` canonical family**, which currently all pass the function-gate on a teleport-gameable delivery proxy.

The sibling `CP-NEW-adaptive-3finger-gripper.json` independently **DELETED its physics fingers** to route around the same missing **flange-attach-under-physics** capability — corroborates EC-6. **Effort:** M→L (controller) + S (mount bake) + M (gate). **Source:** tool-changer-swap.

### EC-12 — Speed-and-Separation-Monitoring HRC subsystem (per-robot derate + walking-human + safety gate) — **blast: 4+ families**
The HRC analogue of articulated-door. Today safety is **binary + global + externally-scripted** (proximity bool → `sim_control(pause)` freezes the *whole universe*, human + robot together); real HRC is **continuous + per-robot + closed-loop** on a moving agent's live distance. A coupled new subsystem of three classes:
- **C-A SSM controller** — scale the cuRobo/RmpFlow command **per-tick** as a monotone function of robot↔human separation (full speed → linear derate → protective stop). No controller in pick_place.py exposes this; the proximity sensor is only a pick GO/NO-GO gate.
- **C-B dynamic-human-agent** (`setup_human_walker` / `move_agent_along_path`) — drive a `Characters_NVD` SkelRoot along a waypoint path **AND give it a PhysX presence collider** so distance queries see it. `set_keyframe` only slides a transform; catalog has only an Idle clip (no locomotion); `add_proximity_sensor` matches `hit.rigid_body` so a SkelRoot character **never triggers it**.
- **C-C safety/separation GATE** (`simulate_safety_check`) — assert `min_separation ≥ Sp` + zero protective-distance violations + zero human collisions alongside task completion. `simulate_traversal_check` scores part-delivery only → a "pass" can include **the arm passing through the human**.

Also: no force-limited/PFL cobot body (the "UR10 cobot" is industrial physics with cosmetic naming; no ISO/TS 15066 contact-force cap). **Families gated:** cobot handover, shared workspace, pedestrian-in-AMR-path, stop-when-person-enters. **Effort:** M (SSM controller) + M (human walker + collider) + M (safety gate). **Source:** hrc-shared-cell.

### EC-13 — Legged-locomotion DEPLOYMENT runtime: policy-inference controller + terrain primitive + reached-goal gate — **blast: 5+ families**
The architecture has **only ever served legged locomotion on the TRAINING side, never DEPLOYMENT** — every trained quadruped/biped policy in the library is **undeployable**. Three coupled new classes:
- **Legged-locomotion CONTROLLER** — per-physics-step velocity-command→joint-target loop running a trained RL policy on a floating-base articulation. `load_rl_policy` is **metadata-only** (`rl:policy_loaded=False`, no inference loop; training.py:3263-3304, docstring admits "runtime policy execution requires controller integration"). The motion-controller registry is **fixed-base-arm only** (rmpflow/cuRobo/direct_joint/linear_motion); "gait" appears only in diagnostic strings. `navigate_to` is **wheeled-only** (DifferentialController) AND an open-loop scaffold that hardcodes start-at-origin and never reads live robot pose.
- **Uneven-TERRAIN primitive** (`create_terrain(rough|stairs|slope, amplitude, slope_deg)` with collision geometry) — only a material-roughness shader float exists + a dead DR-range string `terrain_height_m`.
- **Traversal / reached-goal GATE** (`base_reached_goal(robot, goal_xy, tol)` + upright/no-fall predicate) — `gate_one.py` is pick-place-only; `scene_validate.py:154-155` **explicitly DROPS legged robots** from its only spatial check.

**Families gated:** quadruped-walks-to-goal, Anymal-on-stairs, Go1-up-slope, Spot-patrol, biped-walk-across-room DEPLOY. **Effort:** L (policy-inference controller) + M (terrain) + M (gate). **Asset reality:** all quadrupeds are Nucleus-only; the local drop has zero quadruped robots and mostly flat grounds. **Retrieval gap:** train-vs-deploy locomotion map to identical tags — need a `mobility.legged.runtime` / `rl.locomotion.deploy` discriminator. **Source:** quadruped-terrain.

### EC-14 — External human-input / device-driver controller class + in-sim mock (teleop) — **blast: 3+ families (whole imitation-learning branch)**
Every other controller family (cuRobo, RMPflow, pick_place, nav2/Lula, suction) closes its loop **inside Kit**; teleop is the **first task family whose defining input originates OUTSIDE the process** (SpaceMouse/USB-HID, Quest3/WebXR, VisionPro/CloudXR, keyboard) — and there is **no abstraction for an external action source and no mock of one**. The fix is one new primitive — **`scripted_demonstrator` / `teleop_mock`** — that in direct-eval drives the articulation through a real expert pick-place trajectory (reuse the pick-place controller as the expert) and **records the resulting joint targets AS the missing `actions` dataset**. That single primitive: populates `actions` (fixing the schema split below), gives the function-gate something to score, and converts the **whole GR00T-finetune branch** (groot-finetune-n10-demos, groot-export-dataset-hdf5, groot-redact-finetune, groot-data-mix-multitask — all CONSUME this corpus) from "trains on no-ops" to "trains on synthetic-expert demos." `CP-NEW-teaching-mode-pose-replay` is the near-miss that proves the gap — the platform **already improvised** a non-human action source because no proper one exists. Until this class exists, every teleop/imitation canonical can ONLY pass structurally with empty data or fail honestly with real data — **there is no honest-pass path**. **Effort:** M. **Source:** teleop-demo.

---

## 2. Genuinely-NEW tool gaps (not in V2)

Grouped; each is a concrete handler/gate/primitive. "Δ V2" notes where it sharpens (not duplicates) an existing V2 line. All file:line refs are from the per-scenario traces.

### Gates / verifiers (the dominant new category — V2's gate coverage is M2 sort-accuracy only)
- **`articulation_angle` success gate** — `joint_path + target_angle + tolerance_deg` verdict. *Completely absent*; every drawer/knob/door/valve/rack task is ungradeable. (svc-stovetop-knob, svc-fridge-place) — **the single highest-leverage new gate.**
- **Containment/extraction gate** — "item started INSIDE enclosure → now OUTSIDE its AABB at rest, enclosure still open." (svc-cabinet-fetch)
- **Moving-target-frame containment gate** — `simulate_traversal_check` freezes target AABB once (diagnostics.py:4436); a pulled-out prismatic shelf invalidates it (false-pos item-on-floor / false-neg item-on-moved-shelf). (svc-fridge-place)
- **Slotted / orientation-aware place gate** — `_cube_support` straight-down raycast + `require_upright≥0.95` INVERT for an edge-on plate (false-pass on tine-hit, false-fail on correctly-edged plate). (svc-dishwasher-load)
- **Seat/click gate** (`verify_seat` / `simulate_assembly_check`) — `{seated, click_detected, final_z, impulse_peak_Ns, attempts}` from `PhysxContactReportAPI`. (e2e2-snap-fit) Δ V2 P11 grades mesh-pose, not a seat event.
- **Torque-terminated-gesture verifier** (`verify_torque_terminated_gesture`) — `expected_wrist_torque_target_nm`/`expected_z_force_cap_n` are dead. (e2e2-screw-driving) Δ V2 P11.
- **Axis-aware pose-target gate** — `expected_final_rotation_quat` within `target_rotation_tolerance_deg`, axis-aware (current `require_upright` accepts wrong-axis/no-flip). (reorient-flip) Δ V2 line 162 names only the controller.
- **Grasp-integrity gate** — in-hand pose stability + contact-set coverage + orientation preservation (not delivered-XY); `grip_latched` reads a suction-FJ log a finger grasp never writes. (three-finger-grasp) Δ V2 M8 names only the controller.
- **`verify_slot_engagement` / rack-bay gate** — both rails engaged + body level + at backstop + no protrusion. (dc-rack-stack) Δ V2 M14.
- **`verify_tool_mounted` gate (TC3)** — exactly-one active flange FixedJoint + expected/parked tool under physics. **#1 honesty gap for the `pattern_hint='other'` family.** (tool-changer-swap)
- **`simulate:surface_coverage` / `path_tracking` gate** — coverage-grid / cross-track-error / travel-speed; `WeldSeamSpec`/`score_scenario` exists unwired. (weld-seam, spray-coat)
- **`simulate_safety_check` / min-clearance gate** — separation distance + protective-stop + human-collision metric. (hrc-shared-cell)
- **Traversal / `base_reached_goal` gate** — `scene_validate.py:154-155` drops legged robots; no base-reached-goal verdict. (quadruped-terrain)
- **Connector mate-detection gate** — assert "connector latched"; gate reads one rigid AABB center, structurally can't. (dc-cable-route)
- **Gate verdict-shape dispatch on `intent.pattern_hint` (G5)** — `gate_one.py` unconditionally runs `simulate_traversal_check` (delivery geometry) on in-place fasten/insert/coating templates → structural false-positive. **Cross-cutting fix that de-falses many families.** (e2e2-screw-driving)

### Controllers / actuation primitives
- **`wrist_roll_twist` / `turn_knob` axial-twist controller** — grip on the rotation axis, command EE roll to track a RevoluteJoint (±90-180°, ~zero translation). (svc-stovetop-knob)
- **Sequenced-articulation / passive-joint-by-contact controller** — pull-door→pull-shelf→place, driving passive (no-DriveAPI) joints by contact force not teleport. (svc-fridge-place)
- **`reach_in_and_extract` controller** — non-top-down approach + WITHDRAW leg (pull out along open-axis before lift). (svc-cabinet-fetch)
- **Articulated-state-gated sequencer** — condition controller-2 on controller-1 reaching a JOINT position (not a robot-done flag). (svc-cabinet-fetch)
- **`set_destination_frame` / dest-tracking place-mode** — re-read a MOVING dest prim's live transform each frame (place-side `cube_tracking`). (svc-dishwasher-load)
- **Slotted / edge-on insertion place-mode** (`place_orientation` + tine-aware approach) — side-in between-tines, not top-down drop. (svc-dishwasher-load)
- **`slide_insert` / `rack_insert`** — horizontal two-rail slide-in, far-edge control point, push-to-backstop. (dc-rack-stack)
- **`setup_reorient_controller`** — grip-locked continuous-SLERP in-air reorient holding part rigidly to a target quat. (reorient-flip) Δ V2 line 162 (names it but no gate; this adds the controller spec + asserts part-follows-EE).
- **`drive_joint_to_torque` / `spin_under_torque_cap`** — spin a joint and stop on a torque cap; **buildable in pure PhysX, no ros2_control**. (e2e2-screw-driving)
- **`press_until_seated` / `setup_seat_controller`** — descend→sense→reseat with `max_attempts`/`force_cap`/`backoff`. (e2e2-snap-fit)
- **`loop_until` / `retry_until_predicate`** primitive — predicate-terminated attempt budget (existing `retry_count`/`execute_with_retry` are dead/code-only). (e2e2-snap-fit) Δ V2 Tier-4 `loop_workflow` (generalizes to predicate-terminated).
- **`follow_cartesian_path` / `surface_process_follow`** — multi-waypoint path-follower run to completion (move_to_pose is single-tick). **Rigid mode ships with no torque bridge.** (spray-coat, weld-seam)
- **`project_standoff_along_normal` / raycast-to-surface** — surface-normal lookup for tilted/curved standoff (constant-Z hardcode misses). (spray-coat)
- **DLO 1D-rod generator + grasp-follow controller** — `create_deformable_mesh` is 2D-sheet only; grasp welds to rigid center only. (dc-cable-route)
- **Connector/port mate-and-seat controller** — keyed connector into socket (insertion has only peg/screw/snap/cap). (dc-cable-route)
- **`swap_eoat` / tool-changeover controller (TC1)** + **`mount_tool` / `bake_local_frame` (TC2)** — play-until-arrive swap + generic local-frame baking lifted out of the surface_gripper path. (tool-changer-swap)
- **SSM speed-scaling controller (C-A)** + **`setup_human_walker` / `move_agent_along_path` (C-B)**. (hrc-shared-cell)
- **Legged-locomotion policy-inference controller** + **`create_terrain` primitive**. (quadruped-terrain)
- **`scripted_demonstrator` / `teleop_mock`** — drive the articulation through an expert trajectory, record joint targets as `actions`. (teleop-demo)
- **`attach_tool` / EOAT-bit mount (G3)** + **negative-space / boolean-subtract primitive (G4)** — fix a driver bit to panda_hand + author a real threaded hole (create_prim is solid-only). (e2e2-screw-driving)

### Data / asset / integrity primitives
- **`verify_articulation(path, min_joints)`** + **`assert_assets_present`** — articulated-USD + catalog-vs-payload integrity pre-flight (empty `resource/` dirs and materials-only packs build silent stubs). (svc-fridge-place, dc-rack-stack) — **S, do early.**
- **`record_tcp_trajectory`** — FK end-effector world poses (record_trajectory is joint-space only). (spray-coat)
- **`check_dual_rail_alignment`** — yaw+roll+lateral co-alignment sub-primitive. (dc-rack-stack)
- **UR10 level-carry EOAT** (fork / dual-cup bar) — single cup can't carry a 1U chassis level. (dc-rack-stack)
- **name→USD resolvers**: drawer/cabinet (Sektion), datacenter rack/server/port, pot/kitchenware, plate/thin-disc workpiece profile. (svc-cabinet-fetch, dc-cable-route, svc-stovetop-knob, svc-dishwasher-load)
- **Anti-oracle contact-correlation guard** — `set_joint_targets` writes the joint's own DriveAPI target (no robot contact) = revolute analogue of the banned FixedJoint-grip. (svc-stovetop-knob, svc-fridge-place)
- **Static pre-filter articulation-state axis** — `scene_validate`/`reach_validate` judge one frozen frame → false-block a closed-drawer item; need a reach-probe at the OPEN joint state. (svc-cabinet-fetch) Δ V2 M6.
- **`xformOp:orient` vs `rotateXYZ` author-and-confirm helper** — orient silently ignored on some prims → flip becomes a no-op the gate may still pass. (reorient-flip)
- **teleop HDF5 schema fixes** — record writes `obs/*` but no `actions`; validator REQUIRES `actions` → a real file fails its own validator; per-call finalize leaks buffers; `frequency_hz` vs `fps` key mismatch; `check_teleop_hardware` false-positives device presence. (teleop-demo)

### Confirms (NOT new) — explicitly dedup'd to V2
- Live insertion/impedance/admittance/compliance `dry_run=False` → `NotImplementedError`, blocked on absent **ros2_control torque bridge** = **V2 P10** (insertion.py:351, all of compliance.py). (weld-seam, snap-fit, screw-driving)
- Drawer/prismatic-pull controller absence + M10 kernel-without-handler = **V2 M10** (but V2 misses the joint-state gate — see EC-1). (svc-cabinet-fetch, svc-dishwasher-load)
- Multi-call controller race (pose_sequence sensorless) = the CP-52 / **V2 M11** handoff-race root, new trigger = a joint position. (svc-cabinet-fetch)

---

## 3. Plan deltas (new backlog items + domain prerequisites)

### New highest-ROI backlog items (cheapest-first, dedup'd against V2's build order)

1. **B-EC10 `verify_articulation` + `assert_assets_present` (S)** — integrity pre-flight. Blocks **silent-empty-stage** across datacenter + all 243 articulated appliances. Cheapest, broadest honesty win in this batch; ship before any articulated/datacenter scenario authoring. *Prereq for: every EC-1/EC-2/EC-7/EC-9/EC-10 scenario.*
2. **B-EC1-GATE `articulation_angle` joint-state gate (M)** — one gate makes the ENTIRE articulated-joint category (door/drawer/knob/valve/rack) gradeable. Highest gate-ROI in the batch; **must precede** any articulation controller work or it lands unmeasurable (the M10 trap).
3. **B-EC4-PHYSX `drive_joint_to_torque` + torque-terminated gate (M, no bridge)** — converts the whole force/torque-fastening family (screw/cap/nut/valve) from plan-only to real **without** the ros2_control bridge. Explicitly carve this out of V2 P10 (which lumps it with the bridge-blocked compliant case).
4. **B-EC5-GATE axis-aware pose-target gate (S→M)** — closes the reorient silent-false-positive; pairs with the line-162 controller V2 already lists.
5. **B-GATE-DISPATCH gate verdict-shape dispatch on `pattern_hint` (S→M, cross-cutting)** — stop running pick-place delivery geometry on insert/fasten/coating/twist templates. **De-falses many families at once**; foundational for EC-3/EC-4/EC-5/EC-7/EC-8/EC-11.
6. **B-EC3 `follow_cartesian_path` + `surface_coverage` gate + `record_tcp_trajectory` (L+M+S)** — rigid/standoff mode ships with cuRobo only (no bridge). Unblocks the 10-family surface-process domain incl. the parked paint-sprayer template.
7. **B-EC2 / B-EC7 / B-EC8** controllers+gates (reach-extract / dest-tracking-slotted / rack-slide) — the service + datacenter manipulation depth; do after the articulation gate + integrity pre-flight land.
8. **B-EC6 grasp-integrity gate (L)** — name it explicitly as a sibling of V2 M8 so the dexterous-controller research doesn't ship unmeasurable.
9. **B-EC11 / B-EC12 / B-EC13 / B-EC14** (tool-swap / HRC-SSM / legged-deploy / teleop-mock) — each a multi-class subsystem; sequence after the cheap gates, by domain priority.

### Domain prerequisites (hard blockers — author no scenarios in these domains until satisfied)
- **Datacenter:** geometry USD for rack/server/port does not exist on disk (`Datacenter_NVD` materials-only) **and** no name→USD resolver. *No datacenter scenario is buildable until assets + resolver land* (gate this behind B-EC10's `assert_assets_present`).
- **Service/domestic articulated appliances:** 8/9 local fridges have empty `resource/` dirs; gate all 243-appliance authoring behind `verify_articulation`.
- **Legged-deploy:** all quadrupeds Nucleus-only; local drop has none, grounds mostly flat. Needs asset acquisition + `create_terrain` before the policy-inference controller is exercisable.
- **HRC:** Characters catalog has only an Idle clip (no locomotion) and SkelRoot has no PhysX collider → the human is invisible to proximity sensors; B-EC12's human-walker+collider is a prereq for *any* faithful HRC scene.
- **Compliant-force assembly (snap-fit/peg/tactile/weld-compliant):** still blocked on the absent **ros2_control torque bridge** (V2 P10) — only the **discrete-joint PhysX** subset (B-EC4-PHYSX) is buildable now.

### Taxonomy / retrieval delta
- Add discriminators so retrieval doesn't conflate capability tiers: `mobility.legged.runtime` vs `rl.locomotion` (train-vs-deploy), and `pattern_hint` values for **twist / surface-process / force-terminated / reorient / retrieve-from-enclosure** so the gate-dispatch (item 5) and the form-gate can route correctly.

---

### Cross-reference
Per-scenario traces with full file:line evidence (all 16 present in `docs/notes/`): `e2e2_svc-fridge-place.md`, `e2e2_svc-dishwasher-load.md`, `e2e2_svc-cabinet-fetch.md`, `e2e2_svc-stovetop-knob.md`, `e2e2_dc-rack-stack.md`, `e2e2_dc-cable-route.md`, `e2e2_reorient-flip.md`, `e2e2_screw-driving.md`, `e2e2_snap-fit.md`, `e2e2_weld-seam.md`, `e2e2_spray-coat.md`, `e2e2_tool-changer-swap.md`, `e2e2_teleop-demo.md`, `e2e2_hrc-shared-cell.md`, `e2e2_quadruped-terrain.md`, `e2e2_three-finger-grasp.md`. Dedup base: `TOOL_GAP_INVENTORY_V2.md`.
