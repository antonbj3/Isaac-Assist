# E2E Trace: reorient-flip (assembly / franka / "flip a part 180° to present its other face")

Scenario id: **reorient-flip**
Domain: assembly · Robot: franka · Task: reorient/flip
Request (verbatim): *"flip a part 180 degrees to present its other face for the next operation"*

> KEY DELIVERABLE up front: this scenario reveals a **NEW CLASS-LEVEL gap**. The
> existing tool-gap inventory (line 162) names a missing `setup_reorient_controller`
> but frames it as a *flip-station / passive-flip* problem. The real architectural
> hole this trace exposes is two-fold and deeper:
> 1. **No grip-preserving in-air reorient controller.** The one "active flip"
>    template (A69) is built on `move_to_pose`, which is a **single-shot reactive
>    RMPflow nudge** — it computes ONE joint action and applies it once
>    (`robot.py:2393-2396`). It cannot converge a 180° wrist roll, and it has **no
>    mechanism to keep the part gripped through the rotation**.
> 2. **The gate has no "which-face-is-presented" verifier.** Success is
>    `require_upright` = `cube_up · world_up ≥ 0.95` (`diagnostics.py:4443-4449`).
>    That accepts a part that was never flipped, a part flipped about the WRONG
>    axis, or any of 4 yaw orientations — as long as +Z still points up. "Present
>    the *other face*" is precisely the orientation the gate is blind to.
> A whole family of assembly tasks ("turn over", "present face B", "rotate to mate
> orientation", "set the part on edge", regrasp-to-reorient) needs both a
> **reorient controller class** and a **pose-target / face-presentation gate class**.

---

## 0. Closest real templates (grounding)

Two templates in `workspace/templates/` claim the reorient/flip pattern. Both are
the closest match to this request; neither is verified.

| Template | Approach | Verified? | File |
|---|---|---|---|
| **CP-05** | PASSIVE flip-wall: cube starts on its side, belt drives it into a static wall that tips it upright; Franka then picks the already-upright cube | `build-spec-2026-05-08; physics-tuning-required; visual delivery + orientation test **pending**` | `workspace/templates/CP-05.json` |
| **CP-NEW-bin-picking-with-flip** (A69) | ACTIVE flip: Franka picks a part lying on its side, does a "mid-air 180° wrist roll" via `move_to_pose`, places upright | `drafted-2026-05-16; form-gate-schema ⏳; function-gate ⏳` (NEVER run) | `workspace/templates/CP-NEW-bin-picking-with-flip.json` |

A69 is the on-point match for *"flip a part to present its other face."* The trace
below follows A69, because the passive flip-wall (CP-05) cannot, by construction,
present a chosen face — it only rights whatever face the geometry happens to tip to.

---

## 1. Full user-action → outcome sequence

Legend: **[USER]** human action · **[LLM]** model tool-calls · **[SYSTEM]** Kit/handler/gate.
Cost: **[CHEAP-static]** = USD authoring / codegen, no physics step · **[EXPENSIVE-physics]** = stepped sim.

### Phase A — request & retrieval
1. **[USER]** types: *"flip a part 180 degrees to present its other face for the next operation."* **[CHEAP-static]**
2. **[SYSTEM]** retrieval matches `intent.pattern_hint="reorient"` → surfaces A69 (`CP-NEW-bin-picking-with-flip`); `structural_tags: isaac:reorient.explicit_waypoint`. **[CHEAP-static]**
3. **[LLM]** adopts A69's tool plan: `tools_used = [create_prim, set_attribute, apply_api_schema, robot_wizard, create_bin, define_grasp_pose, set_physics_scene_config, apply_physics_material, bulk_set_attribute, add_proximity_sensor, setup_pick_place_controller, move_to_pose, get_world_transform, check_collisions]`. **[CHEAP-static]**

### Phase B — scene authoring (all CHEAP-static, no physics)
4. **[LLM]** `create_prim` ground/table/cell; `set_physics_scene_config(enable_gpu_dynamics=False, broadphase=MBP)` → CPU dynamics for deterministic flip. **[CHEAP-static]**
5. **[LLM]** `robot_wizard(franka @ [0,0,0.75])`. **[CHEAP-static]** → handler `robot.py` spawns Franka (avoids the wound-start asset bug; see MEMORY).
6. **[LLM]** `create_bin` SourceBin `[0,0.40,0.80]`, DestBin `[0,-0.45,0.80]`. **[CHEAP-static]**
7. **[LLM]** `create_prim` Workpiece (0.06 m cube) at `[0,0.40,0.835]`, `set_attribute(xformOp:orient = [0.7071,0.7071,0,0])` → +90° about X → **part lying on its side**. `apply_api_schema` rigid/collision/mass + `apply_physics_material("rubber")` + `bulk_set_attribute(sleepThreshold=0, enableCCD=True)`. **[CHEAP-static]**
   - ⚠️ A69's own failure_modes flag this exact step: some Cube prims author `xformOp:rotateXYZ` not `:orient`, silently ignoring the rotation → part stays identity → "flip" is a no-op the gate may still pass.
8. **[LLM]** `add_proximity_sensor` inside DestBin; `define_grasp_pose(approach=[0,0,-1], offset=[0,0,0.04])` → writes advisory YAML (NOT used by cuRobo for motion — see A69 note). **[CHEAP-static]**

### Phase C — the "flip" (this is where the class-gap lives)
9. **[LLM]** `setup_pick_place_controller(target_source="curobo", source=[Workpiece], drop_targets={Workpiece:[0,0,1.20]}, planning_obstacles=[Table,SourceBin,DestBin], phase_id="phase1")`. **[CHEAP-static codegen → EXPENSIVE at run]**
   - Handler `pick_place._gen_setup_pick_place_controller` (`pick_place.py:293`). cuRobo transit picks the part and lifts to the "flip pre-position" above the base. Grip is the standard pick_place grip (distance-retention FixedJoint family).
10. **[LLM]** `check_collisions(/World/Franka)` — guards wrist-over-base self-clash at the flip waypoint. **[CHEAP-static]** (geometry query)
11. **[LLM]** `move_to_pose(articulation=/World/Franka, target_position=[0,0,1.20], target_orientation=[0,1,0,0], planner="rmpflow")` — *the flip itself.* **[CHEAP-static codegen]**
    - **CLASS-GAP #1.** `robot._gen_move_to_pose` (`robot.py:2227`). The rmpflow branch (`robot.py:2335-2398`) does exactly:
      ```
      action = amp.get_next_articulation_action()   # ONE action  (robot.py:2393)
      art.apply_action(action)                       # applied once (robot.py:2396)
      ```
      It does **not** loop to convergence, does **not** step physics toward the
      target, and has **no grip-hold / re-assert during the rotation**. A 180°
      wrist roll under a single reactive RMPflow tick = a small nudge. The part's
      fate during the roll is governed solely by whatever grip
      `setup_pick_place_controller` left behind (a distance-retention joint that
      A69's own failure_modes admit "may slip" or that a fresh controller call may
      "open the gripper to re-grasp"). There is **no `setup_reorient_controller`**
      that (a) holds the grip rigidly, (b) drives a *continuous* SLERP of EE
      orientation to the flip target, (c) verifies the part rotated WITH the EE.
12. **[LLM]** `get_world_transform(Workpiece)` — read pose mid-flip. **[CHEAP-static]**
13. **[LLM]** `setup_pick_place_controller(... drop_targets={Workpiece:[0,-0.45,0.86]}, phase_id="phase2")` — place into DestBin. **[EXPENSIVE-physics at run]**
    - A69 failure_modes line 5 admits the **risk that this second call resets the controller and drops the grasped cube** (re-grasp at Source). There is no first-class "continue-holding / place-down" primitive; the template *hopes* the controller persists the grip across calls.

### Phase D — gate / outcome
14. **[SYSTEM]** Function-gate runs `simulate` (`diagnostics.py` `_handle_simulate_*`, scripted via `scripts/qa/gate_one.py`). **[EXPENSIVE-physics]** — steps the sim to `duration_s=180`, reads final cube pose.
15. **[SYSTEM]** Verdict (`diagnostics.py:4443-4449`):
    ```
    upright_dot = cube_up · world_up
    upright_ok  = (not require_upright) or upright_dot >= upright_tol   # 0.95
    success     = in_xy AND above_floor AND at_rest AND upright_ok      # single-cube
    ```
    - **CLASS-GAP #2.** A69's verify_args/simulate_args carry
      `flip_target_orientation=[0,1,0,0]`, `expected_final_rotation_quat=[1,0,0,0]`,
      `target_rotation_tolerance_deg=5.0`. **No handler reads any of these keys.**
      `grep` for `expected_final_rotation_quat` / `flip_target_orientation` /
      `target_rotation_tolerance_deg` across the handlers and verifier_registry
      returns NOTHING in the verdict path. The gate's only orientation concept is
      `require_upright` (a single scalar dot with world-up). It cannot tell:
      - a part that flipped 180° about Y (correct — other face now up) **from**
      - a part that flipped 180° about Z (wrong — SAME face up, just yawed) **from**
      - a part that never flipped at all (identity was already upright).
      All three score `upright_dot ≈ 1.0` → all PASS. "Present the *other face*" is
      structurally unverifiable with today's gate.

### Outcome
- **Form-gate**: passes (all tools in A69 exist; codegen is well-formed).
- **Function-gate**: A69 has **never been run** (`function-gate ⏳`). Re-deriving from the
  code: the place leg can deliver the part into DestBin (position criterion met) and
  the part can end +Z-up (`upright_ok` met) **without the flip ever physically
  completing** — because the single-shot `move_to_pose` can't complete it and the
  gate can't detect that it didn't. So the gate would likely **falsely PASS** while
  the "other face" is NOT presented. This is the worst kind of gap: green light, wrong
  physics — the same false-positive family flagged repeatedly in MEMORY.

---

## 2. Tool/handler gaps (NEW — not just re-reporting inventory line 162)

| Gap | Class? | Evidence (file:line) | Why existing tools don't cover it |
|---|---|---|---|
| **`setup_reorient_controller`** — grip-locked, continuous-SLERP in-air reorient that drives EE orientation to a target while holding the part rigidly and verifying part-follows-EE | **CONTROLLER CLASS** | `robot.py:2393-2396` (move_to_pose is single-shot, no grip-hold) | `move_to_pose` = 1 reactive tick, no convergence, no grip. `setup_pick_place_controller` only does world-Z yaw at drop (`gripper_rotation`, `pick_place.py:4139-4141`) — no pitch/roll, can't flip. |
| **Pose-target / face-presentation gate** — verify final orientation vs an expected quaternion within `target_rotation_tolerance_deg`, axis-aware ("which face is up/forward") | **GATE CLASS** | `diagnostics.py:4443-4449` (only `require_upright`); A69 keys `expected_final_rotation_quat`/`flip_target_orientation`/`target_rotation_tolerance_deg` are **dead** (no reader) | `require_upright` is a single dot-with-world-up scalar → blind to which face / which yaw. Inventory line 162 names a *controller* gap but NOT this *gate* gap. |
| **Grip-persistence guarantee across controller re-calls / "place-down" primitive** | controller-mode | A69 failure_modes #5 (2nd `setup_pick_place_controller` "may open gripper"); no `grasp_object(release)` / `place_down` continuation in `pick_place.py` | Today the template *hopes* phase2 keeps the grip; no first-class "keep holding, set down at orientation Q" call. |
| **`xformOp:orient` vs `:rotateXYZ` author-and-confirm helper** | authoring | A69 failure_modes #6 (orient silently ignored → flip is a no-op) | `set_attribute` doesn't verify the rotation channel actually took; a silently-ignored orient makes the whole scenario a false pass. |
| **Two-stage regrasp (place-on-fixture, re-approach from new side) reorient** — the >180°-of-wrist-range or jaw-can't-reach-both-faces case | **CONTROLLER CLASS (sibling)** | no handler; A69 only does the *easy* in-air-wrist-roll case | Parallel-jaw + 7-DOF Franka can't always reach a part's far face in one grasp; needs set-down + re-grasp. No primitive exists. |

---

## 3. NEW CLASS-LEVEL finding (the headline)

**"Reorient/flip to present a chosen face" is unsupported at the class level on BOTH
the controller axis and the verification axis — and the two gaps reinforce each
other into a silent false-positive.**

- Controller axis: there is no grip-preserving reorient controller. `move_to_pose`
  is a single-shot reactive nudge (`robot.py:2393-2396`) with no convergence loop and
  no grip management; `setup_pick_place_controller`'s only orientation knob is a
  world-Z drop-yaw (`pick_place.py:4139`). Neither can roll/pitch a *held* part to a
  target orientation.
- Verification axis: the gate's only orientation predicate is `require_upright`
  (`diagnostics.py:4443-4449`) — a scalar dot with world-up. It cannot distinguish
  "other face now presented" from "same face, never flipped" or "flipped about the
  wrong axis." A69's `expected_final_rotation_quat` / `flip_target_orientation` /
  `target_rotation_tolerance_deg` keys exist in the template but have **no reader** in
  any handler.

This is directly analogous to the **humanoid-cabinet trace** that showed pick-place
fundamentally breaks on articulated doors: there, the missing class was a
*revolute-pull controller*; here, the missing classes are a **reorient controller**
(hold-grip + continuous-orientation drive) and a **pose-target / face-presentation
gate** (axis-aware orientation verdict, not a single up-dot). A whole family —
turn-over, present-face-B, set-on-edge, rotate-to-mate, regrasp-to-reorient (the
assembly/kitting backbone) — needs both. The closest existing template (A69) papers
over the controller gap with single-shot `move_to_pose` and, because the gate is
orientation-blind beyond up-dot, would likely **score a green PASS on a flip that
never physically happened.**

Recommended minimal builds: (1) `setup_reorient_controller` (cuRobo SLERP to target
EE quat + rigid grip-hold + part-follows-EE assertion); (2) extend the gate's
`simulate` to read `expected_final_rotation_quat` + `target_rotation_tolerance_deg`
and compute geodesic quaternion error (face-aware), replacing the up-dot-only
predicate for reorient tasks. Both are prerequisites before any "flip"/"present-face"
template can be honestly verified.
