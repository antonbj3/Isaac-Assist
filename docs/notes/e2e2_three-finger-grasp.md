# E2E Trace — Three-Finger Grasp of an Irregular Object (Rubik cube)

**Scenario id:** `three-finger-grasp`
**Domain:** dexterous manipulation
**Robot:** Allegro / 3-finger hand (requested) → **Franka parallel-jaw (what the pipeline actually delivers)**
**Task:** a 3-finger hand grasps an irregular object (a Rubik cube) and places it
**User request (verbatim):** "a 3-finger hand grasps an irregular object (a Rubik cube) and places it"

This trace simulates the COMPLETE user→LLM→system action sequence to reach the target
scene and the OUTCOME, grounded in the real templates, handlers, and gate. Every step is
marked `[USER]`/`[LLM]`/`[SYSTEM]` and `[CHEAP-static]`/`[EXPENSIVE-physics]`.

---

## 0. Closest real template + the load-bearing truth in its own `code` field

`grep` for the closest match yields exactly one canonical:

- `workspace/templates/CP-NEW-adaptive-3finger-gripper.json` — "Adaptive 3-finger
  gripper (Robotiq-style proxy) on a Franka arm picks three differently-shaped
  workpieces." This IS the canonical for this request family (`task_id`
  `CP-NEW-adaptive-3finger-gripper`, a.k.a. A119).

The decisive evidence is inside that template's own executable `code` field
(`CP-NEW-adaptive-3finger-gripper.json:25`), which **deletes its own premise**:

> "# 3-finger adaptive gripper proxy: adaptive grasp is expressed via SEMANTICS only…
> The cuRobo controller already grips with the real `panda_finger_joint1/2` friction
> jaw, so authoring rigid-body Cube fingers + force-driven prismatic joints onto
> `panda_hand` adds zero grasp value and **corrupts the Franka articulation (PhysX
> blowup at sim start)**. The physics finger/joint authoring is therefore
> intentionally omitted."

So the "3-finger adaptive gripper" canonical, at runtime, is a **2-DOF Franka
parallel jaw** moving three Cylinder/Cube workpieces. The three fingers, the 120°
palm, the prismatic joints, the per-object `finger_opening_targets`, the asymmetric
rod cradle — all of it is **JSON metadata that never reaches PhysX**. This is the
scenario's central finding, and it generalizes.

---

## 1. The full traced flow

### Step 1 — User prompt
`[USER]` `[CHEAP-static]`
> "a 3-finger hand grasps an irregular object (a Rubik cube) and places it"

### Step 2 — LLM intent classification
`[LLM]` `[CHEAP-static]`
The planner classifies this as `pattern_hint: "pick_place"` (the intent block of
`CP-NEW-adaptive-3finger-gripper.json:143`). It tags
`isaac:end_effector.three_finger_adaptive`, `isaac:gripper.three_finger_robotiq_proxy`,
`isaac:grasp.per_object_finger_opening`. The closest canonical retrieved is A119.
**First silent reduction:** "3-finger dexterous grasp" → "pick_place" pattern. The
taxonomy has no dexterous/in-hand pattern; pick_place is the only attractor.

### Step 3 — Robot resolution (`robot_wizard`)
`[LLM]→[SYSTEM]` `[CHEAP-static]`
The LLM wants an Allegro / 3-finger hand. It calls `robot_wizard(robot_name="allegro", …)`.

- The asset **exists**:
  `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Robots/WonikRobotics/AllegroHand/allegro.usd`
  (also Robotiq `2F-85`/`2F-140`/`Hand-E`/`3F` under `.../Robotiq`, and
  `.../ShadowRobot/ShadowHand`). **The asset is NOT the gap.**
- But `robot_wizard`'s registry only resolves arms. The only `"allegro"` entry in
  the codebase is a **fix-profile**, not a spawn key
  (`handlers/robot.py:451-470`): it is a list of `known_issues`
  ("Very small link masses cause solver instability", "CollisionAPI often missing
  on fingertip links") and `drive_gains` — diagnostic hints, no USD path, no
  controller.
- `allegro` is **absent** from `_SUPPORTED_MOTION_ROBOTS`
  (`handlers/robot.py:525-528` = `{franka, ur10, ur5e, ur3e, cobotta, rs007n,
  dofbot, kawasaki, flexiv_rizon}` — every entry is an arm; no hand).

So the practical path the canonical itself takes (`CP-NEW-adaptive-3finger-gripper.json:25`)
is `robot_wizard(robot_name="franka", …)` at `[0,0,0.75]`. **The hand is silently
swapped for a parallel-jaw arm.** Build-gate `[CHEAP-static]` passes.

### Step 4 — Irregular object (the Rubik cube)
`[LLM]→[SYSTEM]` `[CHEAP-static]`
A faithful Rubik cube is a non-convex 3×3 with recessed grooves — the irregularity
is the whole point. The pipeline CAN author non-convex collision:
`simplify_collision` (`handlers/physics.py:931-999`) accepts
`approximation ∈ {convexHull, convexDecomposition, meshSimplification,
boundingSphere, boundingCube, sphereFill, sdf, none}`. So `sdf` or
`convexDecomposition` would give a faithful concave collider.

But the canonical (`CP-NEW-adaptive-3finger-gripper.json:25`) authors a **`prim_type="Cube"`,
scale `[0.02,0.02,0.02]`** with the default convex box collider. **Second silent
reduction:** "irregular Rubik cube" → "smooth 0.04 m primitive Cube." No template
in `workspace/templates/` references "rubik" or "irregular"
(`grep -rln rubik` over templates and service = 0 hits). Irregular/non-convex
graspable objects are unrepresented in the canonical library.

### Step 5 — Grasp pose definition (`define_grasp_pose`)
`[LLM]→[SYSTEM]` `[CHEAP-static]`
`define_grasp_pose(robot_path="/World/Franka", object_path="/World/SmallCube",
gripper_offset=[0,0,0.025], approach_direction=[0,0,-1])`
(`CP-NEW-adaptive-3finger-gripper.json:25`; handler
`handlers/robot.py:3035 _gen_define_grasp_pose`). This writes a
`.isaac_grasp` YAML holding only a 6-DoF approach transform + a `gripper_offset`.
There is **no finger configuration, no contact-point set, no grasp-force field, no
hand preshape** — the schema is parallel-jaw / suction posing only. The per-object
`finger_opening_targets` dict (`-0.018` pinch / `-0.030` wrap / asymmetric rod) lives
only in `role_defaults.workpieces[*].finger_openings` JSON and is never written into
the grasp file.

### Step 6 — The "grasp" (`grasp_object`)
`[LLM]→[SYSTEM]` `[EXPENSIVE-physics]` (motion) but `[CHEAP-static]` (the actual grip)
This is the most load-bearing handler in the trace:
`handlers/robot.py:2844 _gen_grasp_object`, `grasp_type="from_file"` branch.
The generated runtime code is a 4-step RmpFlow sequence:

```
# Step 1: Move to approach position   → RmpFlow set_end_effector_target(approach_pos)
# Step 2: Approach grasp position      → RmpFlow set_end_effector_target(grasp_pos)
# Step 3: Close gripper                → print("Step 3: Closing gripper")   ← (!!)
# Step 4: Lift                         → RmpFlow set_end_effector_target(lift_pos)
```

**Step 3 — "close gripper" — is a literal `print()` statement.** No finger joint is
driven, no `panda_finger_joint1/2` target is set, no contact is established. The
object is not actually held by any closure. Two further hard facts:
- The RmpFlow config is **hardcoded `load_supported_motion_policy_config('Franka',
  'RMPflow')`** regardless of the robot — an Allegro/UR10/anything at `robot_path`
  still loads the Franka policy.
- If `robot_path` is not an articulation, the handler emits a `soft_success` JSON
  and `raise SystemExit(0)` (`handlers/robot.py` Round-7 repair block) — the
  build-gate passes while runtime grasping is a no-op.

### Step 7 — Adaptive finger driving (`set_joint_targets`)
`[LLM]→[SYSTEM]` `[CHEAP-static, no-op]`
The canonical loops `set_joint_targets(articulation_path="/World/Franka",
joint_name="Finger_A_Joint", target_position=-0.018)` etc.
(`handlers/physics.py:174 _gen_set_joint_targets`). But **`Finger_A_Joint`,
`Finger_B_Joint`, `Finger_C_Joint` were never authored** (Step 3 of the canonical
deleted the finger/joint creation to avoid the PhysX blowup). Driving a
non-existent joint is a no-op (or a soft-fail). The "adaptive opening" — the entire
named differentiator of A119 — does nothing at runtime.

### Step 8 — Transport (`setup_pick_place_controller`, curobo)
`[LLM]→[SYSTEM]` `[EXPENSIVE-physics]`
`setup_pick_place_controller(robot_path="/World/Franka", target_source="curobo",
robot_family="franka", source_paths=[…], destination_path="/World/OutfeedBin", …)`
(`handlers/pick_place.py:3972` curobo branch). The `robot_family` switch
(`pick_place.py:4017-4087`) supports exactly three families, and **all three grip
with something other than fingers**:

- `franka` → `_FINGER_JOINTS = ("panda_finger_joint1","panda_finger_joint2")` — a
  2-DOF parallel jaw (`pick_place.py:4044`).
- `ur10`/`ur10e` → `_FINGER_JOINTS = ()` — "UR10 has no built-in gripper; use
  surface_gripper separately" (suction FJ-attach) (`pick_place.py:4083`).
- `g1_arm` → the G1 dex hand **has 7 joints per side**, but `_FINGER_JOINTS = ()`
  with the comment "**G1 dex hand has 7 joints per side; V0 uses surface-gripper
  FJ-attach**" (`pick_place.py:4081`). Even the one humanoid hand in the codebase
  is **welded shut and FJ-attached**, never actuated.
- Anything else → `raise RuntimeError(f"Unsupported robot_family")`
  (`pick_place.py:4087`). `allegro`/`robotiq`/`shadow` hit this raise.

So the actual hold during transport is the Franka parallel jaw closing on a smooth
box. The cuRobo plan moves it to the outfeed bin. This is real physics — but it is
2-finger physics on a convex primitive, not a 3-finger wrap on a Rubik cube.

### Step 9 — Gate / verdict
`[SYSTEM]` `[EXPENSIVE-physics]` then `[CHEAP-static]` scoring
`simulate_args` = `{target_path:"/World/OutfeedBin", cube_paths:[…3 workpieces…],
duration_s:180, xy_tolerance:0.1}` (`CP-NEW-adaptive-3finger-gripper.json:111`).
The function-gate verdict (`scripts/qa/gate_one.py`; diagnostic at
`handlers/diagnostics.py:3450-3520`) is built from `ctrl:cubes_delivered`,
`ctrl:picked_path`, and a `grip_latched` flag parsed from the **suction** grip log
(`gripped=[...]`, `diagnostics.py:3435-3448`). The pass criterion is **position-only**:
did the workpiece end up inside the bin XY-tolerance, primary upright. There is:
- **No in-hand pose / orientation-preservation check** (a Rubik cube's grasp
  correctness — was it gripped without rotating the faces — is invisible).
- **No finger-contact-set check** (3 contact patches at 120° vs a 2-point pinch).
- **No grip-integrity check that applies to articulated fingers** — `grip_latched`
  reads the suction-FJ log, which an articulated-finger grasp never writes.

### Step 10 — Outcome
`[SYSTEM]` `[CHEAP-static]`
The gate reports **PASS / `delivered_ok`** (`diagnostics.py:3514`): a smooth 0.04 m
box was carried to the bin by a Franka 2-finger jaw. The user's actual request —
**a 3-finger hand wrapping an irregular Rubik cube** — was satisfied at the level of
JSON tags and `print("Step 3: Closing gripper")`, and at no level of physics. The
green checkmark is a **false positive for the dexterous request**.

---

## 2. Tool / capability gaps surfaced (with file:line)

| Gap | Evidence | New? |
|---|---|---|
| `grasp_object` Step-3 "close gripper" is a `print()` — no closure of ANY gripper | `handlers/robot.py:2844`, from_file branch "Step 3: Closing gripper" | refines P9 |
| `grasp_object` hardcodes `('Franka','RMPflow')` for every robot | `handlers/robot.py` ~2900 | refines P9 |
| curobo controller raises on any non-{franka,ur10,g1} family; `allegro`/`robotiq`/`shadow` unreachable | `handlers/pick_place.py:4087` | confirms M8 |
| G1 dex hand has 7 finger joints but `_FINGER_JOINTS=()` — welded/FJ, never actuated | `handlers/pick_place.py:4081` | **NEW (specific)** |
| `"allegro"` registry entry is a fix-profile only (known_issues + drive_gains), no USD path, no spawn | `handlers/robot.py:451-470` | **NEW** |
| `_SUPPORTED_MOTION_ROBOTS` contains zero hands | `handlers/robot.py:525-528` | confirms M8 |
| `define_grasp_pose` YAML has no finger config / contact set / preshape / force | `handlers/robot.py:3035`; `.isaac_grasp` schema | **NEW** |
| Canonical deletes its own finger authoring to avoid "PhysX blowup at sim start" — articulating a child hand on `panda_hand` corrupts the Franka articulation | `CP-NEW-adaptive-3finger-gripper.json:25` | **NEW (root cause)** |
| Gate verdict is delivered-position only; no in-hand-pose / contact-set / orientation-preservation; `grip_latched` is suction-FJ specific | `handlers/diagnostics.py:3435-3514`; `simulate_args` xy_tolerance only | **NEW (gate class)** |
| No template/object represents an irregular / non-convex graspable object (`grep rubik`=0); canonical uses smooth primitives even though `simplify_collision` could author `sdf`/`convexDecomposition` | `grep` over templates; `handlers/physics.py:931-999` (capability exists, unused) | **NEW** |

---

## 3. The NEW CLASS-LEVEL architectural gap

Existing inventory (`docs/notes/TOOL_GAP_INVENTORY_V2.md`) already lists **M8**
(a multi-finger adaptive grasp *controller*) and **P9** (`grasp_object` is
parallel-jaw-only). This trace confirms those, but it isolates a **deeper, distinct
class-level gap that M8 alone does not cover** — directly analogous to how the
humanoid-cabinet trace revealed that pick-place breaks on articulated doors:

> **There is no actuated-finger / closed-loop grasp EXECUTION + VERIFICATION class.
> The entire stack treats the end-effector as an oracle that either (a) prints
> "close gripper" (RmpFlow grasp_object), (b) closes a 2-DOF parallel jaw, or
> (c) FixedJoint-welds the object to the wrist (suction, and even the G1 dex hand).
> Grasp success is scored by where the object LANDS, never by HOW it was held.**

This breaks a whole family of tasks, not just this one:
- **3-finger / Allegro / Shadow / Robotiq-3F wrap grasps** (this scenario)
- **In-hand manipulation / reorientation** (turn the Rubik cube in-hand)
- **Irregular / non-convex object grasping** (the contact set, not the bin, is the metric)
- **Force/compliance-controlled grasping** (egg, deformable, fragile)
- **Any task where the grasp itself — not the transport — is the skill being measured**

It has **three structural components**, all missing, all needed together:

1. **A `dexterous_grasp` / multi-finger CONTROLLER class** that drives N finger
   joints (Allegro 16-DOF, Robotiq-3F 11-DOF, Shadow 24-DOF) instead of raising
   `Unsupported robot_family` (`pick_place.py:4087`). The asset is present
   (`.../WonikRobotics/AllegroHand/allegro.usd`) — the controller is not. Note the
   canonical's discovered blocker: a finger hand cannot simply be welded as a child
   of `panda_hand` (it corrupts the Franka articulation —
   `CP-NEW-adaptive-3finger-gripper.json:25`); the hand must be spawned as its own
   articulation with its own cuRobo/IK config, i.e. a genuine new robot family, not
   a proxy bolt-on.

2. **A grasp PRIMITIVE that actually closes fingers**: replace
   `grasp_object` Step-3 `print("Closing gripper")` with a real per-joint
   close-to-contact loop, and extend the `.isaac_grasp` schema
   (`_gen_define_grasp_pose`, `robot.py:3035`) to carry finger preshape, contact
   points, and per-finger force targets — none of which the parallel-jaw/suction
   YAML can express.

3. **A grasp-INTEGRITY GATE class** (the part M8 doesn't name): a verifier that
   scores grasp quality by **in-hand pose stability, contact-set coverage, and
   object orientation preservation**, not by delivered-XY. The current verdict
   (`diagnostics.py:3450-3514`, `grip_latched` from the suction log) is
   structurally blind to whether a 3-finger wrap actually formed — so it will keep
   stamping PASS on the Franka-jaw substitute. Without this gate, even a correct
   dexterous controller could not be measured as correct.

**Honest bottom line:** for the literal request, the pipeline produces a green,
delivered-to-bin run in which **no 3-finger hand exists, no fingers close, and the
object is a smooth box** — a class-level false positive. The missing piece is not a
single tool but an **actuated-finger grasp execution-and-verification class**
(controller + finger-closing primitive + in-hand-quality gate), with irregular /
non-convex graspable objects as the natural test fixture it requires.
