# Asset Templates — WORKPIECES + PARTS

Category proposal: canonical templates where the **workpiece is a real NVIDIA 5.0
mesh asset** (irregular grasp, real bolt→nut insertion, reorient/flip a real
part, in-hand regrasp) — NOT a synthetic `Cube` prim.

Generated 2026-06-09. All asset paths verified with `ls`; all tool
existence/state verified with `grep` against
`service/isaac_assist_service/chat/tools/handlers/` + `tool_schemas.py` (438
tools in schema).

---

## 0. Why this category is new

Audited every template in `workspace/templates/` (442 active):

```
grep -lE "Props/(YCB|Factory|Mugs|Food|Beaker|Rubiks|Flip_Stack|Blocks)" *.json
  → ZERO hits
```

**Not a single existing template references a real Props mesh asset as the
manipulated workpiece.** Every "workpiece" today is a procedural `create_prim
(prim_type="Cube")` — including the one template that *names* itself for parts
work, `CP-NEW-bin-picking-with-flip`, which flips a 0.06 m synthetic cube. The
whole graspable-asset library (50 YCB, 12 Factory bolt/nut pairs, 4 Mugs,
Flip_Stack assembly parts, Rubik's, Beaker, Food) is unused by the canonical
set. This category fills that gap.

---

## 1. Verified assets on disk

Root: `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/`

| Group | Verified path (example) | Notes |
|---|---|---|
| **YCB** | `YCB/Axis_Aligned/...usd` (visual) and `YCB/Axis_Aligned_Physics/...usd` (with collision/RB) | 25 visual + physics-variant subset. Graspables: `005_tomato_soup_can`, `010_potted_meat_can`, `003_cracker_box`, `004_sugar_box`, `008_pudding_box`, `009_gelatin_box`, `025_mug`, `061_foam_brick`, `036_wood_block`, `011_banana`, `006_mustard_bottle`, `051_large_clamp`, `024_bowl`, `037_scissors`, `035_power_drill` |
| **Factory bolts** | `Factory/factory_bolt_m{4,8,12,16,20}_{loose,tight}/factory_bolt_*.usd` | 5 sizes × loose/tight = 10 bolt USDs |
| **Factory nuts** | `Factory/factory_nut_m{4,8,12,16,20}_{loose,tight}/factory_nut_*.usd` | 5 sizes × loose/tight = 10 nut USDs. **Matched bolt/nut pairs → real threaded insertion** |
| **Blocks** | `Blocks/nvidia_cube.usd`, `Blocks/DexCube/dex_cube_instanceable.usd`, `Blocks/{red,green,blue,yellow}_block.usd` | DexCube = standard RL grasp cube |
| **Mugs** | `Mugs/SM_Mug_{A2,B1,C1,D1}.usd` | handled mugs → irregular/handle grasp |
| **Rubik's** | `Rubiks_Cube/rubiks_cube.usd` | textured cube, reorient/in-hand target |
| **Beaker** | `Beaker/beaker_500ml.usd` | thin-wall cylinder, lab pick |
| **Food** | `Food/mac_n_cheese_centered.usd` | boxed item |
| **Flip_Stack** | `Flip_Stack/{large,small}_corner_bracket.usd`, `t_connector.usd`, `angled_connector.usd`, `caster.usd`, `bearing_pin.usd`, `screw_m3.usd`, `flip_stack.usd` | **Real assembly parts** — brackets, T/angle connectors, caster, bearing pin → reorient/flip + peg-pin insertion |

Multi-finger hand assets (verified, for adaptive-grasp templates):
`Robots/Robotiq/2F-85`, `2F-140`, `Hand-E` (parallel adaptive);
`Robots/WonikRobotics/AllegroHand/allegro_hand.usd` (4-finger);
`Robots/ShadowRobot/ShadowHand/shadow_hand.usd` (5-finger dexterous).
**Note:** the Robotiq *3-Finger* adaptive gripper is NOT on disk — only the
2-finger 2F-85/2F-140/Hand-E. Closest real >2-finger adaptive hand = Allegro.

---

## 2. Tool surface — status of the four flagged tools

Verified by reading handlers, not assuming.

| Tool | Status | Evidence |
|---|---|---|
| **grasp-pose-sampler** | **PARTIAL** | `setup_grasp_pose_sampler` exists (`robot.py:5374`, schema has `sampling_mode: [antipodal, top_down, parallel_jaw]`) but only **writes config attrs onto a marker prim** — docstring: *"Actual SDG execution at runtime requires Replicator pipeline."* It does NOT read mesh geometry or emit usable grasp candidates. `define_grasp_pose` (`robot.py:3035`) writes a **static hard-coded** YAML (object centroid + fixed approach/offset), no geometry sampling. A real mesh-aware antipodal sampler that returns ranked grasp candidates is **missing**. |
| **setup_insertion_controller** | **PARTIAL (plan-only, NOT live)** | EXISTS at `insertion.py:276` with Pydantic model + 4 strategies (`spiral_search`, `helical_screw`, `snap_fit`, `impedance_descent`). BUT `dry_run=False raises NotImplementedError` (line 352): *"live mode requires Kit RPC + ros2_control bridge + torque-mode robot."* It composes `setup_impedance_controller` + `follow_trajectory_with_compliance`, which themselves have no live execution. So for the function-gate it produces a plan dict only — **no real bolt actually threads into a real nut**. |
| **3-finger adaptive grasp** | **MISSING** | `create_gripper` (`robot.py`) supports only `gripper_type ∈ [parallel_jaw, suction]` — no multi-finger/adaptive type. Motion controllers (`setup_pick_place_controller`, `move_to_pose`) only support arms in `_SUPPORTED_MOTION_ROBOTS = {franka, ur10, ur5e, ur3e, cobotta, rs007n, dofbot, kawasaki, flexiv_rizon}` — all parallel-jaw. Allegro/Shadow/Robotiq-3F are absent from every controller registry. A 4-finger grasp can only be driven raw via `set_joint_targets` (live, `physics.py`) at DOF level with no grasp synthesis. No `adaptive_grasp`, `three_finger`, `close_hand` tool exists. |
| **reorient/flip station** | **MISSING (ad-hoc only)** | No `setup_reorient_controller` / `flip_station` / `regrasp` / `in_hand` tool (grep = 0). The one flip template fakes it: pick → `move_to_pose` 180° wrist roll at a transit waypoint → place, graded by `target_rotation_tolerance_deg`. There is no controller that plans a regrasp or a passive flip-fixture interaction. |

Supporting tools that DO exist and ARE used (codegen-dispatched, verified):
`add_reference` + `add_usd_reference` (live USD-reference authoring with
`FileNotFoundError` guards → real assets loadable), `robot_wizard`,
`create_bin`, `setup_pick_place_controller`, `move_to_pose`, `plan_trajectory`,
`define_grasp_pose`, `apply_physics_material`, `add_proximity_sensor`,
`get_world_transform` (live, `scene_authoring.py`), `check_collisions` (live,
`diagnostics.py`), `set_joint_targets` (live, `physics.py`), `create_gripper`,
`gripper_open`/`gripper_close`, `get_gripper_state`, `apply_api_schema`,
`bulk_set_attribute`, `set_physics_scene_config`.

---

## 3. Honest-eyes GO/NO-GO risk (the load-bearing caveat)

**Real-mesh grasp is the central honest-eyes risk for this whole category.**
Every existing pick/place canonical succeeds because the workpiece is a 60 mm
axis-aligned cube: the parallel jaws find two flat antipodal faces, contact is
clean, and the grader reads a simple AABB arrival. Swapping in a real mesh
breaks each of those assumptions:

- **Irregular geometry → no guaranteed antipodal face.** A mug (handle), a
  banana, a bolt shank, a corner bracket has no pair of parallel flats at the
  centroid. `define_grasp_pose`'s centroid+fixed-offset YAML will aim the jaws
  at empty space or a curved surface → the part squirts out of the gripper.
  This is the same parallel-jaw-geometry root already documented for tight-bin
  / flat-stack false-successes (see MEMORY `honest_eyes_jaw_root`).
- **The grader lies in BOTH directions on real meshes.** AABB/position-only
  gates report a false PASS when a part is wedged against a wall at the right
  XY but never gripped, and a false FAIL when an irregular part is delivered
  but settles in an orientation the AABB rejects. Per MEMORY, gates chronically
  false-positive; **confirm with PhysX contacts + actual mesh pose via
  `scene_timeseries` / `scene_eyes`, not delivered-counts.**
- **Insertion has no live execution.** `setup_insertion_controller` is
  plan-only — a "bolt-into-nut" template can be authored and will produce a
  clean plan dict, but nothing threads in sim. Grading insertion success
  requires either the (missing) live impedance bridge or a geometric proxy
  (bolt-axis colinear with nut-bore + depth), which must be built. **Do not
  mark an insertion template GO on a plan dict.**

**GO/NO-GO policy for this category:**
- **GO now** (parallel-jaw + real mesh, position-graded with contact
  confirmation): YCB box/can picks, foam-brick, wood-block, mug-by-body — these
  have at least one graspable parallel-face pair. Gate on contact + pose.
- **NO-GO until a real grasp sampler lands** (irregular/no-antipodal): mug-by-
  handle, banana, bolt-shank pick, bare bracket. Honest-eyes will fail or lie.
- **NO-GO until insertion goes live**: any bolt→nut threading verdict.
- **NO-GO until a multi-finger controller lands**: any Allegro/Shadow/3-finger
  template — driveable only as a DOF-replay demo, not a closed-loop grasp.

Tier each template accordingly below.

---

## 4. Proposed templates

IDs use the `WP-NN` prefix (WorkPiece) to keep them distinct from the `CP-*`
cube set. Schema mirrors existing templates: `task_id, goal, tools_used,
thoughts, code, settle_state, verify_args, simulate_args, diagnose_args,
failure_modes, motion_controllers, verified_status`.

### Tier A — GO now (real mesh, parallel-jaw, has antipodal faces)

- **WP-01 — YCB soup-can bin pick.** `add_usd_reference`
  `YCB/Axis_Aligned_Physics/005_tomato_soup_can.usd` into a KLT bin; Franka
  parallel-jaw side-grasp on the cylinder body (two antipodal tangent faces);
  `setup_pick_place_controller` → dest bin. Gate: contact + dest AABB + upright.
- **WP-02 — YCB cracker-box repack.** Reference `003_cracker_box` (large flat
  box); top-down jaw grasp on the two long faces; place into a packing tray.
  Closest to existing cube picks → lowest honest-eyes risk in the set.
- **WP-03 — foam-brick + wood-block sort by material.** `061_foam_brick` and
  `036_wood_block` into two routed bins; exercises real-mesh mass/friction
  difference under the same jaw grasp. `apply_physics_material` per part.

### Tier B — NO-GO until grasp sampler lands (irregular / no clean antipodal)

- **WP-04 — Mug grasp-by-handle.** `add_usd_reference` `Mugs/SM_Mug_B1.usd`;
  the *point* is the handle grasp — there is no centroid antipodal pair, so
  `define_grasp_pose` is insufficient. **Drives the requirement for a real
  geometry-aware grasp sampler.** Authored now, gated NO-GO.
- **WP-05 — Banana / irregular YCB pick.** `011_banana` — curved, thin, the
  canonical "no parallel face" case. Same sampler dependency.
- **WP-06 — Flip_Stack corner-bracket pick.** `large_corner_bracket.usd` —
  L-shaped, grasp must target one leg, not the centroid.

### Tier C — NO-GO until setup_insertion_controller goes live (real insertion)

- **WP-07 — M8 bolt → M8 nut threading.** Reference `factory_bolt_m8_tight.usd`
  + `factory_nut_m8_tight.usd` (matched pair, real threads). Pick the bolt,
  align over the nut bore, `setup_insertion_controller(strategy="helical_screw")`.
  Today returns a plan dict only → honest verdict needs the live impedance
  bridge OR a geometric colinear-axis+depth proxy. **Primary driver for making
  `setup_insertion_controller` live.**
- **WP-08 — Bearing-pin into bracket bore (Flip_Stack).** `bearing_pin.usd`
  into `large_corner_bracket.usd` hole; `strategy="spiral_search"` peg-in-hole.
  Same live-insertion dependency.
- **WP-09 — M16 loose→tight bolt seat.** Uses the `loose` variant as start and
  `tight` as the seated reference; tests the helical descent + torque-gate
  contract. Plan-only today.

### Tier D — NO-GO until a multi-finger controller lands (adaptive grasp)

- **WP-10 — Allegro 4-finger Rubik's cube envelope grasp.** Reference
  `WonikRobotics/AllegroHand/allegro_hand.usd` + `Rubiks_Cube/rubiks_cube.usd`;
  power-wrap grasp. No controller path → driveable only as a `set_joint_targets`
  DOF-replay demo. **Primary driver for a multi-finger / adaptive-grasp tool.**
- **WP-11 — In-hand reorient (regrasp) of a Rubik's cube.** Allegro/Shadow
  finger-gaiting reorient. Depends on BOTH a multi-finger controller AND a
  reorient/flip tool. Authored as the north-star, gated NO-GO.

### Tier E — Reorient/flip-station (ad-hoc today, needs a real tool)

- **WP-12 — Flip a real part with a passive flip fixture.** Use
  `Flip_Stack/flip_stack.usd` (a real flip-station asset!) to reorient
  `t_connector.usd` from lying to upright via fixture interaction rather than a
  wrist roll. **First template to use a real flip-station asset** instead of the
  `move_to_pose`-roll hack; drives a `setup_reorient_controller` requirement.

---

## 5. New tools required (consolidated)

| Tool to build | Needed by | Why current state insufficient |
|---|---|---|
| **`setup_grasp_pose_sampler` (real, geometry-aware)** | WP-04..06, all irregular | Existing one only writes marker attrs; no mesh → grasp candidates. Need antipodal/surface sampling that returns ranked, reachable grasps. |
| **`setup_insertion_controller` (live execution)** | WP-07..09 | Exists but `dry_run=False` raises `NotImplementedError`; no Kit-RPC/impedance bridge → no real threading/insertion in sim. |
| **3-finger / multi-finger adaptive grasp controller** | WP-10..11 | `create_gripper` only does `parallel_jaw`/`suction`; no controller for Allegro/Shadow/Robotiq-3F. DOF-level `set_joint_targets` only. |
| **`setup_reorient_controller` / flip-station** | WP-11..12 | No reorient/flip/regrasp tool; flip is faked via `move_to_pose` roll. Real flip-fixture asset (`flip_stack.usd`) unused. |
| **Real-mesh grasp/insertion verifier (honest-eyes)** | ALL | Position-only AABB grader lies on irregular meshes. Need contact + mesh-pose (and colinear-axis+depth for insertion) verdicts. |
