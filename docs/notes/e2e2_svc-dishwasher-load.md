# E2E Trace — svc-dishwasher-load

**Scenario ID:** svc-dishwasher-load
**Domain:** service / domestic
**Robot:** franka (Panda, fixed-base arm)
**Task:** load-into-rack
**User request:** "load plates into a pulled-out dishwasher rack"
**Date:** 2026-06-09

---

## 0. What "the target scene" actually is (ground truth from assets)

The request has a hidden articulation problem baked into the noun "pulled-out rack". Kimate's assets contain a genuinely articulated dishwasher:

`/home/anton/kimate_assets/assets/ArtVIP/Articulated_objects/major_appliances/dishwasher/dishwasher_2/model_dishwasher_2.usda`

Its joint topology (grepped from the USDA):
- L48-49: prim is a `PhysicsArticulationRootAPI` + `PhysxArticulationAPI` (real articulation, not a static mesh).
- L218 `PhysicsRevoluteJoint "RevoluteJoint_dishwasher_2_middle"` — **the door**, axis X, `lowerLimit=0 upperLimit=90` deg, drive stiffness 20 / damping 10, targetPosition 90.
- L362 `PhysicsPrismaticJoint "PrismaticJoint_dishwasher_2_up"` — **the upper rack**, axis Y, `lowerLimit=-0.2 upperLimit=0` (20 cm of pull-out travel), drive stiffness 10 / damping 10.
- L416 `PhysicsPrismaticJoint "PrismaticJoint_dishwasher_2_down"` — **the lower rack**, identical 20 cm Y slider.

So "pulled-out rack" is literally `PrismaticJoint_dishwasher_2_up` driven to its `lowerLimit` (−0.2 m). The plate destination is a *slotted tine grid*, not a bin: `…/Interactive_scene/kitchen/platerack/platerack.usd` (USD crate, body `PlateRack_…` with `FixedJoint` + convex-hull tines) is the geometry a real rack slot looks like. Plates rest **between** vertical tines, edge-on, not flat in a tub.

This is the dishwasher analogue of the humanoid-cabinet trace: the destination is an **articulated, movable, slotted** surface, and there are TWO articulations in series (door revolute + rack prismatic) that must be actuated before a single plate can be placed.

---

## 1. The complete user-action sequence to reach target + outcome

Legend: **[USER]** / **[LLM]** / **[SYSTEM]** ; **[CHEAP-static]** = USD authoring / planning, no physics stepping ; **[EXPENSIVE-physics]** = requires PhysX stepping (sim_control / controller run / gate).

### Step 1 — Request
- **[USER]** "load plates into a pulled-out dishwasher rack"

### Step 2 — Intent classification
- **[LLM] [CHEAP-static]** The router pattern-matches to `pattern_hint: "pick_place"` (the only place→destination pattern it owns). It tags `isaac:robot.franka`, `isaac:robot.fixed_base.arm`, `isaac:topology.single_station`, and — if it is honest about the noun — `isaac:articulation.prismatic` + `isaac:fixture.articulated`. The closest canonicals it can retrieve:
  - `CP-NEW-machine-tender-load-unload.json` — "load blank INTO a CNC fixture" (but fixture is a *static* `Cube` prim, see its `code`: `/World/CNCMachine/BasePlate` is a non-articulated box).
  - `CP-NEW-drawer-open.json` — "Franka pulls open a kitchen-cabinet drawer (prismatic joint along Y, ~30 cm travel)".
  - `CP-NEW-robohive-door-open.json` — Franka arc-pulls a revolute door handle past 60°.
- The retrieval is correct but **no single template chains "pull the rack open" THEN "load plates into the slots"** (grep for that goal-pair across all 504 templates returns empty).

### Step 3 — Scene authoring (build the dishwasher + plates)
- **[LLM]→[SYSTEM] [CHEAP-static]** Tool calls:
  - `add_reference` / `add_usd_reference` → reference `model_dishwasher_2.usda` into `/World/Dishwasher` (handler `scene_authoring._gen_add_reference`).
  - `robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[…])` (handler `robot.py`) — proven path, used by both CNC and door templates.
  - Author N plate prims. **GAP-1 surfaces here:** a "plate" is a thin disc/box; the pipeline only has `create_prim(prim_type="Cube"/"Cylinder")`. There is no plate/dish workpiece asset wired and no thin-rigid-body grasp profile. Plates get approximated as thin cubes (same shortcut every template uses — see CNC "blank" = 0.10 m cube).
  - `set_physics_scene_config(enable_gpu_dynamics=False, broadphase=MBP)` — CPU dynamics, required for deterministic articulation (both drawer-open and door-open templates force this).

### Step 4 — **Pull the rack out** (the first articulation)
This is where the trace forks from any working canonical.

- **Option A — actuate the joint directly [LLM]→[SYSTEM] [EXPENSIVE-physics]:**
  `set_joint_targets(articulation_path="/World/Dishwasher", joint_name="PrismaticJoint_dishwasher_2_up", target_position=-0.2)` then `sim_control(step, …)` to let the drive pull the rack to its limit.
  - This **exists and is real**: `physics._gen_set_joint_targets` (handler L1+) walks the prim tree, detects `PrismaticJoint` → `linear` drive, applies `DriveAPI`, sets `TargetPosition`. So the **rack CAN be opened without the robot**.
  - But this is a cheat for the *stated* task: the user said the rack is *pulled out* (present tense, by a hand/agent). Authoring it as a joint-target teleport is "honest-enough" for set-up, but if the intent is the **robot** pulls the rack, see Option B.

- **Option B — robot pulls the rack handle [LLM]→[SYSTEM] [EXPENSIVE-physics]:**
  This is the `CP-NEW-drawer-open` pattern, and it reveals the controller gap. That template's `tools_used` is `["robot_wizard","create_prim","set_attribute","apply_api_schema","setup_pick_place_controller","verify_pickplace_pipeline"]` — i.e. it **repurposes `setup_pick_place_controller` to grab a handle and drag it**. There is no closed-loop pull controller in the dispatch path. The actual math kernel for this — `sub_phase_70c_articulated_drag_controller.py` (a PD law + force ramp + safety limiter "for drag-along-articulated-joint tasks (drawer-open, door-hinge, slider)") — is **orphaned**: its own docstring says *"Live Isaac Sim integration stays scaffold; this module is the math kernel that the handler in handlers/articulated_pull.py will call."* and `handlers/articulated_pull.py` **does not exist** (`find` returns nothing; grep for `sub_phase_70c|DRAGController` across `chat/` returns nothing). So the controller class is written but wired to nothing.

### Step 5 — **Place a plate into a slot** (load-into-rack)
- **[LLM]→[SYSTEM] [EXPENSIVE-physics]** `setup_pick_place_controller(robot_path="/World/Franka", target_source="curobo", source_paths=[plates], destination_path="/World/Dishwasher/.../UpperRack", drop_target=[x,y,z], planning_obstacles=[…dishwasher body, open door…])`.
  - **GAP-2 (drop is to a coordinate, not a moving frame):** the drop runtime bakes `DEST_PATH`/`DROP_TARGET` as fixed values at controller-setup time (pick_place.py L600-610, L69-70: `DEST_PATH = {destination_path!r}`, `DROP_TARGET = {drop_target!r}`). There is **no re-read of the rack's live world transform**. If the rack is still settling on its prismatic drive, or if a later plate needs the rack indexed, the drop point is stale. The only mode that re-reads a moving prim is `cube_tracking` for the *pick* source — there is no `dest_tracking` for a moving destination.
  - **GAP-3 (no slotted/oriented placement):** a dishwasher slot demands the plate go in **edge-on, vertical, between two tines**, with sub-cm lateral tolerance. `setup_pick_place_controller` drops the workpiece **flat, gripper-down**, onto the top face of a destination prim. There is no `place_orientation` / `slot_insert` / tine-collision-aware approach. Grep confirms no `slot|tine|between|rack-aware` logic anywhere in pick_place.py. This is the **same architectural shortfall the humanoid-cabinet trace found** (pick-place assumes a flat open bin), now in the orientation axis: pick-place is a *top-down-into-open-volume* primitive; a rack slot is a *side-in-between-obstacles* insertion. That is the `insertion` controller's job (peg-in-hole family) — but insertion is not wired to pick-place's source/dest plumbing, and the tines are part of the *destination* collision body, so cuRobo will treat the slot walls as obstacles to avoid rather than a target to thread.

### Step 6 — Settle + gate (score the outcome)
- **[SYSTEM] [EXPENSIVE-physics]** `settle_after_canonical` then `simulate_traversal_check` via `gate_one.py`.
  - **GAP-4 (the gate cannot score this task):** the delivery verdict is `_cube_support` (diagnostics.py L4076) — it raycasts **straight down** from below the plate and asks "is the support prim == `target_path` or a descendant?". For a plate standing **edge-on between tines**, the downward ray either (a) misses everything and returns floor/None, or (b) hits a tine that *is* a descendant of the rack and falsely reads "delivered" even if the plate is leaning/dropped. The bbox-containment + `require_upright` (`local +Z · world +Z ≥ 0.95`) checks **invert** the correct answer here: a correctly-loaded plate is **NOT upright** (it stands on edge), so `require_upright=True` would **fail a correct load** and `require_upright=False` can't distinguish "slotted" from "dumped on top". The `CP-NEW-drawer-open` template tellingly has `simulate_args: null` — it is **not gated at all** because the existing gate has no verdict for "joint pulled to limit + object slotted". The only articulated template that IS gated, `CP-NEW-robohive-door-open`, had to invent a **separate** `success_criterion: "joint_angle"` path (`joint_success_deg: 60.0`) — proving the delivery gate genuinely cannot express articulation/insertion success.

### Outcome
**Build succeeds; task is unsatisfiable end-to-end with current tools.**
- The dishwasher references and articulates (assets are real and correctly jointed). ✔
- The rack CAN be pulled out via `set_joint_targets` (static set-up) — so the *scene state* "pulled-out rack" is reachable [CHEAP-static]. ✔
- The robot **cannot reliably load a plate into a slot**: no edge-on/slotted insertion controller, drop is a stale coordinate not a live rack frame, and plates are stand-in cubes. ✘
- Even if a plate landed correctly, **the gate would mis-score it** (downward-raycast + upright-dot verdict is wrong for edge-on slotted placement). So you cannot even *measure* success. ✘ — this is the most damaging failure: it is silent.

---

## 2. NEW tool gaps (not already in TOOL_GAP_INVENTORY_V2)

The inventory already covers: runtime belt-speed control (Tier 1), articulated-cart/base-arm parenting (Tier 2), faithful adaptive-gripper grasp synthesis (research). The following are NEW and specific to load-into-articulated-slotted-fixture:

1. **`set_destination_frame` / `dest_tracking` mode** — a place-side analogue of `cube_tracking`: re-read the destination prim's *live* world transform each frame so a drop into a prim that is still moving (settling prismatic rack, indexed rack, conveyor-mounted tray) lands at the right place. Today only the *source* can be tracked. (S/M — mirror existing cube_tracking.)
2. **Slotted / edge-on insertion place-mode** (`place_orientation` + tine-aware approach) — drop a workpiece **into a gap between obstacles at a commanded orientation** instead of flat onto a top face. The closest existing primitive (`insertion`, peg-in-hole) is not wired to pick_place source/dest plumbing and treats slot walls as avoid-obstacles. (L — new controller wiring.)
3. **Articulation-state gate verdict** (`joint_position` / `joint_pulled_to_limit` success criterion in `simulate_traversal_check`) — generalize the `robohive-door-open` `joint_angle` special-case into a first-class gate mode usable by any drawer/rack/door task, AND a `slotted` delivery verdict that does not assume downward-support + uprightness. (M — the door template proves the data is reachable; it just isn't a reusable gate mode.)
4. **Plate/dish thin-workpiece profile + grasp** — a thin-disc rigid body with an edge-grasp pose, so the manipuland isn't a cube stand-in. (S asset glue + M grasp.)

## 3. THE class-level finding

**load-into-rack is a NEW controller class: "actuate-then-insert into an articulated, slotted, movable fixture" — and the gate has no verdict for it.**

The humanoid-cabinet trace showed pick-place breaks on an articulated *door* (revolute, must be opened first → needs a revolute-pull controller). This dishwasher trace shows the **next, strictly harder member of the same family**, and isolates TWO orthogonal missing pieces that a whole task-family needs:

- **(a) A composite "manipulate-articulation → then place" controller.** The pieces exist but are not composed: `set_joint_targets`/`create_articulated_joint` (open the rack), the orphaned Phase-70c PD drag controller (robot-pulls the rack — kernel written, handler `articulated_pull.py` never built), and `setup_pick_place_controller` (place the object). No dispatcher chains "pull joint to limit → place into the now-exposed surface → optionally close". Every articulated-load task (dishwasher rack, oven rack, fridge drawer, filing cabinet, tool-chest drawer, autoclave tray — the 243 articulated appliances in Kimate's assets are *all* this shape) needs this composite class.

- **(b) Pick-place's "flat-drop-into-open-bin" assumption fails again, now on the orientation axis.** A rack slot is a *side-in, edge-on, between-tines* insertion, not a top-down-into-volume drop. This is the **same root** the humanoid-cabinet trace named ("pick-place assumes an open bin") but it proves the assumption is **two-dimensional**: pick-place breaks both when the destination must be *opened* (articulation axis) AND when the object must be *threaded in at a non-flat orientation* (insertion axis). A single "slotted-insertion place-mode" closes the second axis for the whole rack/tray/dish-drainer/cutlery-basket family.

- **(c) The gate is blind to all of the above.** `simulate_traversal_check`'s downward-raycast + upright-dot verdict structurally cannot score "joint pulled to limit" or "object slotted edge-on" — it will silently false-pass (ray hits a tine that descends from the target) or false-fail (correct edge-on plate is not upright). `CP-NEW-drawer-open` having `simulate_args: null` and `robohive-door-open` needing a bespoke `joint_angle` criterion are the existing evidence that the gate class itself is missing, not just a controller.

**One-line:** load-into-rack reveals a missing **"articulated-fixture insertion" controller class** (compose joint-actuation + slotted-insertion place) AND a missing **gate class** (`joint_state` + `slotted` verdicts) — a whole family of domestic/industrial appliance-loading tasks (every one of Kimate's 243 articulated appliances) needs both, and today pick-place + the downward-support gate silently produce un-scorable, unsatisfiable runs.
