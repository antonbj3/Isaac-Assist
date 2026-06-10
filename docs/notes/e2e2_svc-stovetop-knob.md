# E2E Trace — `svc-stovetop-knob`

**Scenario ID:** svc-stovetop-knob
**Domain:** service / domestic
**Robot:** Unitree G1 (humanoid, bimanual)
**Task:** place + turn-knob ("place a pot on a stovetop and turn the control knob")
**Tier:** T-articulated-revolute (two-segment: free-space place THEN constrained revolute actuation)
**Date:** 2026-06-09

---

## 0. TL;DR verdict

This scenario is a **compound task with a hard split down the middle**:

1. **Segment A — "place a pot on a stovetop"** is a *covered pattern*. It is ordinary free-space
   pick-place onto a flat support surface. The g1 bimanual controller
   (`setup_bimanual_pick_place_controller`, humanoid.py:23) + the cube-delivery function gate
   handle this class (modulo the well-known g1-asset-on-Nucleus and dexhand-grasp caveats).

2. **Segment B — "turn the control knob"** is **NOT covered by any controller, template, or gate
   in the system.** The stovetop assets ship with **real `PhysicsRevoluteJoint` knobs**
   (verified below), so this is not a cosmetic decal — turning the knob is a genuine
   articulated-revolute manipulation problem. There is **no codegen tool that grasps an object and
   drives the robot end-effector through a coordinated revolute arc**, and the function gate has **no
   concept of joint-angle success** — it only scores cube-in-bin delivery.

**The NEW class-level gap this trace reveals:** the existing inventory already names *M10
articulated-door / revolute-pull*, but M10 is scoped to a **door swung about a hinge offset from the
grasp** (translate-the-handle-along-an-arc). A **stovetop knob is a different geometric class: an
in-place axial twist** — the grasp point sits *on the rotation axis*, travel is ±90–180° of pure
roll about the tool's own approach axis, with near-zero translation. That needs a **wrist-roll /
axial-twist controller class** (grip on-axis, command end-effector roll to track the knob's revolute
target, hold position constant), plus an **angle-delta success gate**. Neither exists, and neither is
covered by the linear PD drag kernel that backs M10. See §6.

---

## 1. Assets — grounding the scene (REAL, verified)

Kimate's asset drop ships multiple stovetop USDs with articulated knobs:

```
/home/anton/kimate_assets/assets/Lightwheel_sOM9ISVOqp_Stovetop002/Stovetop002.usd
/home/anton/kimate_assets/assets/Lightwheel_0C4CVSunff_Stovetop026/Stovetop026.usd
/home/anton/kimate_assets/assets/Lightwheel_SlbHVrcLVz_Stovetop006/Stovetop006.usd
/home/anton/kimate_assets/assets/Lightwheel_2p9pxB1AzJ_Stove070/Stove070.usd
/home/anton/kimate_assets/assets/Lightwheel_7FiXNFBS97_Stove074/Stove074.usd
/home/anton/kimate_assets/assets/Lightwheel_oz5iukPxYq_KitchenRoom/Stovetop012   (in a full kitchen)
```

`Stovetop002.usd` traversed (USD crate 0.8.0):
- **4 real revolute knobs**, each its own articulated joint:
  `/root/Stovetop002_knob_front_left/knob_front_left_joint` (+ front_right, rear_left, rear_right)
  → `PhysicsRevoluteJoint`, with `DriveAPI` applied (4 drives total).
- Knob joint parameters (front_left):
  - `physics:axis = X`
  - `physics:lowerLimit = 0.0`, `physics:upperLimit = 180.0` (degrees of valid travel)
  - `drive:X:physics:type = force`, `maxForce = 10000`, `stiffness = 0.0`, `damping = 0.05`,
    `targetPosition = 0.0`, `targetVelocity = 0.0`
- 4 `burner_on_*` Cylinder "Site" prims under `/root/Stovetop002/Sites/` — these are the
  semantic markers a real task would use to confirm "burner is on" once the corresponding knob
  has been rotated.

So the asset designer's intent is explicit: **rotate `knob_front_left_joint` from 0° toward 180° →
the front-left burner turns on.** The success signal is a joint-angle delta, NOT a workpiece pose.

Pot asset: no dedicated "pot" USD found in the drop; a pot would be substituted with a primitive
cylinder + RigidBody/Collision APIs (same pattern the drawer-open canonical uses for its cabinet),
or pulled from `SimReady_Furniture_Misc` / kitchen assets. This is a minor scene-build gap, not the
crux.

g1 hand reality: the `g1` robot family is registered (robot.py:431, robot.py:3968 `g1.usd`), and an
`allegro` dexhand family exists (robot.py:~470). But the g1 grasp path used by
`setup_bimanual_pick_place_controller` is surface-gripper **FixedJoint-attach** (humanoid.py:37
explicitly: *"G1 dex hand grasp dynamics V0 uses surface-gripper FJ-attach; real dex grasping
deferred"*). FJ-attach can fake "holding the pot"; it **cannot apply a roll torque to a knob** —
you cannot twist a small knob with a weld that has no wrist-roll command driving it.

---

## 2. Closest existing templates (grep'd `workspace/templates/`)

| Template | Relevance | What it proves |
|---|---|---|
| `CP-NEW-g1-bimanual-tabletop.json` | **Robot match.** Only g1 manipulation canonical. | g1 bimanual = sequential per-arm cuRobo pick-place to a bin. **Pick-place ONLY.** No knob/turn. Asset still blocked on Nucleus G1 (`migration_deferred.reason = asset_blocked_on_nucleus_only`). |
| `CP-NEW-drawer-open.json` | **Closest TASK shape** (articulated mechanism). | Franka pulls a **prismatic** drawer by reusing `setup_pick_place_controller(target_source="spline")` to drag the handle. `verified_status`: *"gate **stable_fail** (pick-place controller **cannot drive PrismaticJoint**; needs **constraint-aware controller**)."* The system **already knows** pick-place breaks on articulated joints. |
| `CP-NEW-isaaclab-franka-cabinet.json` | Articulated-drawer, RL route. | Solves the drawer by **PPO RL training** on IsaacLab's bundled `Isaac-Franka-Cabinet-Direct-v0`, NOT by a manipulation controller. Success = `steps>=1000 + checkpoint + drawer-joint *readable*` — it explicitly **does not assert the drawer opens**. `motion_controllers.untested = [admittance, impedance, direct_joint]`. |

**No template exists for "turn a knob", "twist", "rotate a control", "valve", or any in-place axial
revolute actuation.** The drawer canonicals are the nearest neighbors and they are about *linear
pull*, not *axial twist*.

---

## 3. The user-action sequence (full trace)

Legend: `[USER]` / `[LLM]` / `[SYSTEM]` ; cost: `[CHEAP-static]` (USD authoring, no physics step) /
`[EXPENSIVE-physics]` (timeline plays, PhysX solves).

### Phase 0 — request
1. `[USER]` "place a pot on a stovetop and turn the control knob" `[CHEAP-static]`
2. `[LLM]` Retrieval over the canonical library. Query embeds to `pick_place` + an
   `articulation/turn` intent. Nearest hits: `CP-NEW-g1-bimanual-tabletop` (robot+place),
   `CP-NEW-drawer-open` (articulated mechanism). **No exact match for the turn half** → the LLM
   composes. `[CHEAP-static]`

### Phase 1 — scene authoring (CHEAP, all static USD)
3. `[LLM→SYSTEM]` `create_prim` DomeLight, Ground, kitchen floor. `[CHEAP-static]`
4. `[LLM→SYSTEM]` `import_robot(file_path="G1", format="asset_library", dest_path="/World/G1")`
   then `teleport_prim` to stand in front of the counter (mirrors g1-bimanual-tabletop code).
   `[CHEAP-static]`  → **CAVEAT: g1 SimReady asset gated on Nucleus** (template `verified_status`:
   *"G1 SimReady asset missing on local Nucleus"*). On a no-Nucleus machine this **fails here**,
   before any of the interesting physics.
5. `[LLM→SYSTEM]` Reference the stovetop:
   `import_robot`/`create_reference` of `Stovetop002.usd` at counter height (it is itself an
   *articulation*, so it loads with its 4 revolute knob joints + drives intact). `[CHEAP-static]`
6. `[LLM→SYSTEM]` `create_prim` a pot (cylinder) + `apply_api_schema` RigidBody/Collision/Mass.
   `[CHEAP-static]`
7. `[LLM→SYSTEM]` `set_physics_scene_config(enable_gpu_dynamics=False, broadphase="MBP")` —
   CPU dynamics, the convention every articulated-joint canonical uses for stable joint sim.
   `[CHEAP-static]`

### Phase 2 — controller install
8. `[LLM→SYSTEM]` **Segment A (place the pot):**
   `setup_bimanual_pick_place_controller(robot_path="/World/G1", robot_family="g1_arm",`
   `left_arm_sources=["/World/Pot"], left_destination=<burner_center_on_stovetop>, plant_feet=True,`
   `planning_obstacles=[stovetop body])` (humanoid.py:23 → composes 2× `_gen_pick_place_curobo`).
   `[CHEAP-static]` (installs the state machine; physics runs in Phase 3).
9. `[LLM→SYSTEM]` **Segment B (turn the knob):** *This is where composition fails.* The LLM has no
   `turn_knob` / `twist` / `rotate_object` / `open_door` tool. The reachable options, all wrong:
   - **(a) `setup_pick_place_controller(target_source="spline", source=knob)`** — the
     drawer-open pattern. Grasps the knob, drags it along *Cartesian spline waypoints*. A knob's
     surface barely translates (it spins in place); a straight/curved Cartesian drag does not track a
     pure-roll revolute joint → the gripper slips off or fights the joint limit. This is the exact
     `stable_fail` the drawer canonical documents — and **worse for revolute** because there is no
     net translation to chase.
   - **(b) `set_joint_targets(articulation_path="/World/Stovetop002_knob_front_left",`
     `joint_name="knob_front_left_joint", target_position=90)`** (physics.py:174, registered
     `_models.py:4019). This **writes the knob's own DriveAPI target** — the **knob turns by itself**
     with the robot uninvolved. It is an **author-side oracle write, not a manipulation.** It makes
     the burner "on" without the G1 ever touching the knob. Honest label: a cheat, the same family as
     the banned FixedJoint-grip teleport.
   - **(c) `execute_contact_sequence_plan` with a `twist` step + `target_torque_Nm`**
     (contact_sequence.py:24, `_normalize_step` step_type="twist"). This applies a torque between two
     prims but is **not coupled to a robot wrist-roll command and not aware of the revolute joint's
     axis/limit** — it is a generic contact-force applicator, not a grip-and-rotate controller.
   The LLM most plausibly emits **(a)** (closest retrieved precedent) and silently falls into the
   known articulated-joint failure, or **(b)** and produces a **false success** (burner on, robot
   never turned it). `[CHEAP-static]`

### Phase 3 — simulate / gate (EXPENSIVE)
10. `[SYSTEM]` Play timeline for `duration_s` (~120–180s sim). `[EXPENSIVE-physics]`
    - Segment A: g1 reaches, FJ-attaches the pot, carries it over, releases on the burner. Plausibly
      works (subject to g1-asset + FJ-grasp caveats).
    - Segment B: per Phase-2(a), the spline drag does NOT rotate `knob_front_left_joint` off 0°.
11. `[SYSTEM]` **Function gate** (`scripts/qa/gate_one.py` → `_models.py:351` FunctionGateArgs →
    diagnostics.py delivery check). The gate samples **cube/object position vs `target_path` + upright
    dot** (diagnostics.py:4022 `require_upright`, :4431 `cp_delivered`). It has **no `joint_position`
    / `angle_delta` field at all.** `[EXPENSIVE-physics]`

---

## 4. Outcome

- **Segment A (place pot):** likely PASS *if* the g1 asset resolves and FJ-grasp holds — but the
  function gate is built for `cube_path` delivery; a "pot resting centered on the burner" reads as a
  place-on-support, which the gate's `under_target`/support-descendant logic can approximate. So A is
  *gradeable* by the current gate.
- **Segment B (turn knob):** **FAIL or FALSE-PASS, and ungradeable either way.**
  - If the LLM uses the spline-drag (3.9a): the knob joint stays at 0°, burner stays off → real
    failure, but **the gate cannot see it** (no angle metric), so it reports on the pot only.
  - If the LLM uses `set_joint_targets` (3.9b): knob reaches 90°, burner "on" → **the gate still has
    no angle check**, AND the success is a **non-manipulation oracle write** — a sim2real cheat. Even
    a hand-rolled "knob reached target" assertion would pass on a write the robot never performed.
- **Net:** The system can *build* the scene and *place* the pot, but **cannot make the G1 turn the
  knob via genuine manipulation, and cannot measure whether a knob was turned.** The interesting half
  of the request is unserviced.

---

## 5. Tool / capability gaps (NEW — not just re-reporting the inventory)

1. **`turn_knob` / `axial_twist` controller (NEW CLASS — see §6).** Grip an object *on its rotation
   axis* and command end-effector **roll** to track a `RevoluteJoint` target through ±θ, holding XYZ
   constant. Distinct from M10 (door-swing-about-offset-hinge) and from the linear drag kernel.
2. **Angle-delta / articulation-state success gate.** The function gate
   (`FunctionGateArgs`, `_models.py:351`) is delivery-only (position + upright). There is **no
   `joint_path` + `target_angle` + `tolerance_deg` verdict** anywhere. Without it, *every* "open
   drawer / turn knob / open door / turn valve" task is either ungradeable or false-passable via the
   `set_joint_targets` oracle. (Inventory's M10 mentions a door-position gate as a sub-bullet; the
   **revolute-twist angle gate as a first-class gate class is not built.**)
3. **Anti-oracle guard for articulation tasks.** `set_joint_targets` (physics.py:174) can move the
   knob *without the robot*, the revolute analogue of the banned FJ-grip teleport. An honest-eyes
   check must require **robot-end-effector contact + wrist-roll motion correlated with the joint
   advancing**, not just final joint angle.
4. **Compound place-then-actuate sequencing.** The request is two phases on the same scene
   (place pot → then turn knob). There is no canonical that chains a free-space place into an
   articulated actuation; bimanual is *sequential pick-place of two cubes to a bin*, not
   *place-A-then-manipulate-B-differently*.
5. **Pot/kitchenware container resolver** (minor): no pot asset; falls back to primitive cylinder.
   Adjacent to inventory's Tier-3 "container name→USD" but for kitchenware, not totes.

---

## 6. NEW CLASS-LEVEL ARCHITECTURAL GAP (the key deliverable)

> **Pick-place and the existing articulated-pull plan both break on an *in-place axial-twist*
> revolute joint (knob/dial/valve). This is a distinct controller class from the door-swing M10:
> the grasp point lies ON the rotation axis, travel is pure end-effector ROLL (±90–180°) with
> ~zero translation, so any Cartesian-waypoint drag (the drawer-open `spline` route) cannot track
> it, and the linear PD drag kernel (`sub_phase_70c_articulated_drag_controller.py`, metres-only,
> zero rotational logic) cannot drive it. A whole family — stovetop knobs, oven dials, valve
> handles, rotary switches, door handles (lever-press-then-rotate), faucet taps, dishwasher
> dials — needs a `wrist_roll_twist` controller + an `articulation_angle` success gate +
> an anti-oracle contact correlation. None of the three exists.**

Why this is genuinely a new class, not the inventory's M10:

| | M10 door / drawer-pull (inventory) | **NEW: axial-knob-twist** |
|---|---|---|
| Joint | Revolute hinge OR prismatic slide, **offset from grasp** | Revolute, **grasp ON the axis** |
| EE motion | Translate handle along an **arc/line** (large XYZ travel) | **Roll in place** (≈0 XYZ travel, large Δroll) |
| Kernel fit | Linear PD drag along axis (kernel exists, unwired) | **No kernel** — drag kernel is metres-only, no angular term (`grep -c rad\|angular = 1`, a docstring) |
| Failure of pick-place | Slips because joint constrains motion | Slips **worse** — nothing to chase in XYZ |
| Gate | door-position/containment (sub-bullet of M10) | **angle-delta gate, unbuilt** |

The **humanoid-cabinet trace** previously revealed "pick-place breaks on articulated **doors**." This
stovetop trace sharpens it: **pick-place breaks on articulated joints *as a category*, and within
that category the *axial twist* sub-class needs its own controller** — you cannot reach it by tuning
the door-swing path, because the door path is fundamentally a translation-along-arc primitive and the
knob needs a roll-in-place primitive.

**Minimum viable build (cheapest first):**
- `articulation_angle` success gate: read `RevoluteJoint` position at sim end, assert
  `|θ_final − θ_target| <= tol_deg` AND robot EE was in contact + wrist-roll moved. (Closes the
  measurement hole for the *entire* articulated family at once — highest ROI.)
- `turn_knob(robot_path, knob_path, joint_name, target_angle_deg)` codegen: approach knob along its
  axis, close gripper, then command EE roll to track the joint target (drive the *robot*, let joint
  physics follow), holding position. Reuse cuRobo for the approach; the twist is a wrist-DOF roll
  ramp, not a Cartesian spline.
- Anti-oracle: forbid `set_joint_targets` from being the thing that "turns" the knob in a
  manipulation task; require contact + correlated motion.

---

## 7. Citations

- Stovetop assets + 4 real revolute knob joints / drives:
  `/home/anton/kimate_assets/assets/Lightwheel_sOM9ISVOqp_Stovetop002/Stovetop002.usd`
  (`/root/Stovetop002_knob_front_left/knob_front_left_joint`, `PhysicsRevoluteJoint`, axis=X,
  limits 0–180°, force-drive maxForce=10000).
- g1 bimanual controller: `service/isaac_assist_service/chat/tools/handlers/humanoid.py:23`
  (`_gen_setup_bimanual_pick_place_controller`); FJ-grasp caveat humanoid.py:37.
- g1 family register / `g1.usd`: `handlers/robot.py:431`, `robot.py:3968`. allegro dexhand: robot.py:~470.
- Closest task template (prismatic, **stable_fail on articulated joint**):
  `workspace/templates/CP-NEW-drawer-open.json` (`verified_status`: pick-place cannot drive
  PrismaticJoint; needs constraint-aware controller).
- Robot match template: `workspace/templates/CP-NEW-g1-bimanual-tabletop.json`
  (`migration_deferred.reason = asset_blocked_on_nucleus_only`).
- RL route on articulated drawer: `workspace/templates/CP-NEW-isaaclab-franka-cabinet.json`
  (`motion_controllers.untested = [admittance, impedance, direct_joint]`).
- Low-level joint-target write (the oracle): `handlers/physics.py:174` `_gen_set_joint_targets`,
  registered `physics.py:2505`, schema `_models.py:4019`.
- Contact "twist" step (generic torque, not a grip-rotate controller):
  `handlers/contact_sequence.py:24` `_handle_execute_contact_sequence_plan`, `:105` `_normalize_step`.
- Linear-only drag kernel (M10 backing, **no angular term**):
  `service/isaac_assist_service/multimodal/sub_phase_70c_articulated_drag_controller.py`
  (`DRAGControllerConfig` metres/force only; `grep -c 'rad|angular|revolute|torque' = 1`, docstring).
  Not referenced by any codegen handler (grep `chat/` = 0 hits).
- Function gate (delivery-only, no angle metric): `scripts/qa/gate_one.py`;
  `handlers/_models.py:351` FunctionGateArgs (`require_upright`, `upright_tolerance_dot`);
  delivery logic `handlers/diagnostics.py:4022`, `:4431`.
- Existing inventory (M10 door, distinct from this): `docs/notes/TOOL_GAP_INVENTORY_V2.md:123-126`.
