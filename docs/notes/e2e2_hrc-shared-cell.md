# E2E Trace — [hrc-shared-cell]

**Scenario:** HRC / ur10 / human-collaboration + safety-stop
**Request (verbatim):** "a cobot assembles parts alongside a human worker, slowing/stopping when the human enters its zone"
**Date:** 2026-06-09
**Verdict:** **NEW CLASS-LEVEL GAP CONFIRMED.** There is no Speed-and-Separation-Monitoring (SSM) controller class, no human-as-dynamic-obstacle path, and no safety-distance gate class. The closest existing primitive (`add_proximity_sensor` + the door-interlock `sim_control(pause)` pattern) collapses a *continuous* safety behavior into a *binary, externally-scripted* one. This is the HRC analogue of the humanoid-cabinet finding: the whole HRC family is structurally unbuildable with today's verbs.

---

## 0. What the request actually demands (the three load-bearing requirements)

A real HRC "cobot alongside human" cell per ISO/TS 15066 Speed-and-Separation Monitoring requires THREE things this platform must model:

1. **A moving human** whose live position is sampled each tick (a dynamic agent, not a static prop).
2. **A continuous speed-scaling controller**: the robot's commanded velocity must be a *monotone function of separation distance* — full speed when clear, derate in a transition band, protective stop inside the minimum-separation distance Sₚ. This is a closed loop running INSIDE the motion controller.
3. **A safety gate**: the success/verdict must assert "minimum robot-to-human clearance never violated AND task still completed" — i.e. a separation-distance time-series + a violation count, not just "part reached bin".

None of the three exists. Details below, grounded in files.

---

## 1. Asset availability (one good surprise, two blockers)

| Need | Status | Evidence |
|---|---|---|
| Human worker model | **EXISTS** | `/home/anton/kimate_assets/assets/Characters_NVD/Assets/Characters/Reallusion/Worker/Worker.usd` (also Debra, Orc). Has `Motions/` + `Props/` + `Materials/` subdirs → it is a rigged SkelRoot character. |
| Walk/approach animation | **BLOCKER (partial)** | `asset_catalog.json` for Characters_NVD enumerates only `Idle` as a behavior. No walk cycle surfaced, no `omni.anim.people` command graph. The Worker can stand in the cell but there is no authored *approach* clip and no tool to drive one. |
| UR10 cobot | EXISTS | `robot_wizard(robot_name="ur10")` — robot.py:3940+; used verbatim in `CP-NEW-machine-tender-door-interlock.json`. NOTE: physically a UR10 is an *industrial* arm, not a collaborative (force-limited) cobot. The platform has no force-limited / power-and-force-limiting (PFL) robot model — the "cobot" identity is cosmetic. |
| Allegro / 3-finger hand (for assembly) | not found in this pass | `find … -iname '*allegro*'` empty under kimate_assets; assembly here would fall back to parallel-jaw / suction. |

So the human BODY is available, but it is a **static prop** with no motion path the toolset can author or drive.

---

## 2. The full user-action sequence (traced, marked)

Legend: `[USER]` / `[LLM]` / `[SYSTEM]` · `[CHEAP-static]` (USD authoring, no physics) / `[EXPENSIVE-physics]` (steps the timeline).

### Phase A — request → plan
1. **[USER]** types the request into Isaac Assist chat.
2. **[LLM]** `[CHEAP-static]` intent-classifies. There is no `hrc` / `safety` template (`grep -ilE 'human|cobot|safety|hrc|zone|speed.?separation' workspace/templates/` → zero true HRC hits; the matches are incidental words inside conveyor/sensor templates). The LLM has no canonical to clone. **First fork in the road: the planner must improvise a scene from primitives.** Closest reference it can pattern-match: `CP-NEW-machine-tender-door-interlock.json` (the only "stop on a signal" template).

### Phase B — scene authoring (all CHEAP-static)
3. **[LLM→SYSTEM]** `create_prim` DomeLight + Ground + Table `[CHEAP-static]` (scene_authoring.py).
4. **[LLM→SYSTEM]** `robot_wizard(robot_name="ur10", dest_path="/World/UR10", position=[0,0,0.75])` `[CHEAP-static]` — robot.py:3940+. (Spawns the arm at home joints; the wound-start fix applies.)
5. **[LLM→SYSTEM]** `add_usd_reference(path=".../Worker/Worker.usd", prim_path="/World/Worker", position=[1.5,0,0])` `[CHEAP-static]` — tool_schemas.py:8638. Worker stands 1.5 m away. **This is where it starts to break: the Worker is referenced as a static rigid prop. Nothing will move it toward the robot.**
6. **[LLM→SYSTEM]** parts to assemble: `create_prim` cubes + `apply_api_schema` rigid/collision `[CHEAP-static]`.
7. **[LLM→SYSTEM]** the safety zone. The ONLY available primitive is `add_proximity_sensor(sensor_path="/World/SafetyZone", position=[…], size=[…])` `[CHEAP-static]` — sensors.py:333. This authors an invisible trigger Cube + a PhysX per-step overlap_box callback that sets `isaac_sensor:triggered` (bool) when any rigid body whose path startswith a pattern enters (sensors.py:411–454).
   - **Gap #1 surfaces here:** the sensor watches `rigid_body` paths (`hit.rigid_body`, sensors.py:422). A referenced **SkelRoot character is not a single rigid body** — it has no PhysX rigid-body root the overlap_box returns. So even if the Worker DID move, the proximity sensor would likely **never trigger on it**. The sensor was built for cubes on belts, not for articulated/skeletal humans.

### Phase C — the controller (the architectural wall)
8. **[LLM→SYSTEM]** `setup_pick_place_controller(robot_path="/World/UR10", robot_family="ur10", sensor_path="/World/SafetyZone", source_paths=[parts], destination_path=…)` `[CHEAP-static]` (authors the controller code) → then runtime is `[EXPENSIVE-physics]` (pick_place.py:293, on_step loop ~1432–1520, sensor-gated industrial variant ~1703–1900).
   - **Gap #2 — the controller reads the sensor as a GO/NO-GO PICK GATE, never as a SPEED SCALER.** The industrial sensor-gated controller (pick_place.py:1703 "belt runs continuously until a proximity sensor … to trigger; then picks") and the latch logic at 2809–2852 use `isaac_sensor:triggered` to decide *whether a cube is at the pick station* — it gates **which cube to grab**, not **how fast to move**. There is NO codepath where an external sensor scales the arm's joint velocity or commanded EE speed. `grep -nE 'speed|scale|max_vel' pick_place.py` finds only belt velocity, cube-velocity damping, and FixedJoint stiffness — never "robot speed as a function of separation".
   - The cuRobo / RmpFlow motion generators run at a fixed planning velocity. There is no per-tick "set max velocity = f(distance)" hook. Slowing the robot would require re-planning with a derated velocity scale every tick (cuRobo doesn't expose this online) or PD-scaling joint targets — neither is wired.

### Phase D — making the human move (no path exists)
9. **[LLM→SYSTEM]** to satisfy "when the human ENTERS its zone," the human must traverse from 1.5 m → inside the zone. Options the toolset offers:
   - `set_keyframe(prim_path="/World/Worker", attr="xformOp:translate", time=…, value=…)` `[CHEAP-static]` — animation.py:81. **This works only as a keyframed prim translate.** It teleport-interpolates the whole SkelRoot's transform — the character slides like a statue on rails, no leg motion (the catalog has only `Idle`, no locomotion clip). Acceptable as a crude "approaching mass" *only if* the human is also given a rigid body so the proximity sensor can see it — but a kinematic-keyframed prim is not a PhysX rigid body, re-triggering Gap #1.
   - `play_animation` (animation.py:143) just plays the timeline; it does not author motion.
   - **Gap #3 — no human-trajectory / waypoint-walk verb.** There is no `move_prim_along_path`, no `setup_human_walker`, no `omni.anim.people` command injection. The platform cannot make the human *approach and retreat* as a controllable agent. Compare: M3 in TOOL_GAP_INVENTORY_V2 is `setup_amr_with_manipulator` — there is an analogous, unbuilt `human_agent` need here.

### Phase E — "stop" semantics (binary, global, externally scripted)
10. The door-interlock template (`CP-NEW-machine-tender-door-interlock.json`) is the precedent for "stop on signal." Its mechanism (from its own `thoughts` + `code`): a script writes `door_closed:bool = False`, then calls `sim_control(action="pause")` — **pausing the ENTIRE simulation**, then `sim_control(action="play")` to resume. The "guard" is a discrete, externally-orchestrated whole-sim freeze, NOT the robot autonomously derating.
    - **Gap #4 — "stop" = pause-the-universe, not "robot enters protective stop while human keeps moving."** A real safety stop halts the ROBOT while the human continues. `sim_control(pause)` freezes human + robot + physics together — physically meaningless for HRC. And there is no graduated *slow-down*: `sim_control` offers pause/play/step; the only "scaled" knob is `ConfigureRos2Time(mode="scaled", time_scale=…)` (_models.py:1945) which rescales the **published ROS2 /clock for everything**, not the robot's speed relative to a moving human. No per-robot velocity-override verb exists (`set_joint_velocity_limit` physics.py:604 sets a static URDF-style limit at build time, not a live closed-loop scale).

### Phase F — the gate / verdict (wrong success criterion)
11. **[LLM→SYSTEM]** `simulate_traversal_check(cube_paths=[parts], target_path=…, duration_s=…)` `[EXPENSIVE-physics]` — diagnostics.py:3920. Pass criteria (docstring 3925–3982): cube XY inside target bbox, above floor, at rest, optional upright. **n_runs** majority vote.
    - **Gap #5 — the gate has NO safety dimension.** It scores only "part delivered." It does not sample robot-to-human distance, has no `min_clearance` field, no "separation never < Sₚ" assertion, no "robot velocity ≤ derated limit while human in band" check, no collision-with-human count. A run where the UR10 **swings straight through the Worker's torso** and still drops the part in the bin scores `success=True`. The gate is structurally blind to the only thing the user asked for. (This is exactly the false-positive family the MEMORY notes warn about — gates lie — but here it's not a bug, it's an *absent metric class*.)

---

## 3. OUTCOME (what the user would actually see)

- A UR10 picks parts and places them while a Worker statue stands (or slides, if keyframed) nearby.
- The arm does **not** slow down or stop as the human nears — there is no codepath for it to. Best case the LLM scripts a `sim_control(pause)` at a hardcoded sim-time (copying door-interlock's `interlock_fire_at_s`), producing a **canned, time-triggered whole-sim freeze** that is unrelated to actual separation distance and freezes the human too.
- The proximity "safety zone" sensor most likely **never fires on the human** (SkelRoot ≠ rigid body, Gap #1), so even the binary interlock is driven by a scripted timer, not by the human's position.
- The gate returns `success=True` if a part lands in the bin, regardless of whether the arm passed through the human.
- **Net:** a plausible-looking demo that satisfies *zero* of the three real HRC requirements. A 6-agent GUI review would flag "robot ignores the human entirely; the human is a prop." Honest verdict: **the scenario cannot be faithfully built today.**

---

## 4. NEW CLASS-LEVEL GAP (the key deliverable)

This scenario reveals a coherent **missing subsystem**, not a one-off tool. It is the HRC analogue of the humanoid-cabinet → revolute-pull finding. Three coupled new classes:

### C-A. Speed-and-Separation-Monitoring controller class — `setup_ssm_controller` / `setup_safety_speed_scaling`
A controller wrapper that, each physics tick, (1) reads the live distance from the robot's swept volume / EE to a designated dynamic agent, (2) maps it through an ISO/TS-15066 band: `d > d_full → scale 1.0; Sₚ < d ≤ d_full → scale linearly to 0; d ≤ Sₚ → protective stop (robot only)`, (3) applies the scale to the underlying cuRobo/RmpFlow command (derated max joint velocity or interpolated target). **This is the missing controller CLASS** — every HRC, cobot-handover, shared-workspace, and "stop when person enters" task needs it. None of pick_place.py's controllers expose an online speed scale.

### C-B. Dynamic-human-agent class — `setup_human_walker` / `move_agent_along_path` + rigid presence
A verb that (1) drives a Characters_NVD SkelRoot along a waypoint path (locomotion clip OR root-translate with a presence collider), and (2) gives it a PhysX presence body/collider so proximity sensors and distance queries can SEE it. Fixes Gap #1 (SkelRoot invisible to overlap_box) and Gap #3 (no approach trajectory) together. Generalizes to: pedestrian-in-AMR-path, worker-at-machine, teleop-bystander — a whole "people in the scene" family currently impossible.

### C-C. Safety / separation gate class — `simulate_safety_check` (or `min_clearance` field on the gate)
A verdict that, alongside task completion, samples robot↔human separation across the run and asserts: `min_separation_observed ≥ Sₚ` (zero protective-distance violations), `robot_speed ≤ derated_limit whenever d in transition band`, and `collision_with_human_count == 0`. Without this, the platform **cannot measure** safety, so even a correct controller couldn't be validated. This is a measurement-honesty gap of the same severity as M2 (per-bin sort gate) in TOOL_GAP_INVENTORY_V2, but for the entire HRC family.

**Why this is class-level, not incremental:** today's stack models safety as *binary + global + externally-scripted* (`proximity bool` → `sim_control(pause)`). Real HRC is *continuous + per-robot + closed-loop on a moving agent's live distance*. Bridging that is a new control loop, a new agent type, and a new metric — a subsystem, exactly like revolute-pull was for articulated doors.

---

## 5. Tool gaps (NEW — not in TOOL_GAP_INVENTORY_V2)

1. **`setup_ssm_controller` / online robot speed-scaling hook** — no controller in pick_place.py scales arm velocity from a live external signal; sensor is a pick-GO/NO-GO gate only (pick_place.py:1703, 2809-2852). (class C-A)
2. **`setup_human_walker` / `move_agent_along_path`** — no verb drives a SkelRoot character along a path; `set_keyframe` (animation.py:81) only slides a transform, catalog has only `Idle` (no locomotion clip), no `omni.anim.people`. (class C-B)
3. **Proximity sensor cannot detect SkelRoot/articulated humans** — `add_proximity_sensor` overlap_box matches `hit.rigid_body` (sensors.py:422); a referenced character has no rigid-body root → never triggers. Needs a presence-collider or a SkelRoot-aware distance query.
4. **`simulate_safety_check` / `min_clearance` gate field** — `simulate_traversal_check` (diagnostics.py:3920) scores only part-delivery; no separation-distance, protective-stop, or human-collision metric. A pass can include the arm passing through the human. (class C-C)
5. **No force-limited / PFL cobot model** — "UR10 cobot" is industrial-arm physics with cosmetic naming; no power-and-force-limiting body or contact-force cap. Needed for ISO/TS 15066 PFL mode (the *other* HRC collaboration mode besides SSM).
6. **"Stop" is pause-the-universe** — `sim_control` offers pause/play/step (freezes human+robot together); `ConfigureRos2Time(time_scale)` rescales global /clock, not per-robot speed. No "robot-only protective stop while human keeps moving" primitive.

---

## 6. Citations (file:line)
- Worker asset: `/home/anton/kimate_assets/assets/Characters_NVD/Assets/Characters/Reallusion/Worker/Worker.usd` (+ `Motions/`, catalog `asset_catalog.json` → only `Idle`)
- UR10 spawn: `service/.../handlers/robot.py:3940` (`robot_wizard`)
- Proximity sensor + rigid-body-only matching: `service/.../handlers/sensors.py:333` (def), `:411-454` (step callback), `:422` (`hit.rigid_body`)
- Pick-place controller, sensor-as-pick-gate: `service/.../handlers/pick_place.py:1703` (industrial sensor-gated variant), `:2809-2852` (sensor latch / cube selection)
- Build-time joint velocity limit (NOT a live scale): `service/.../handlers/physics.py:604`
- Keyframe (slides transform, no locomotion): `service/.../handlers/animation.py:81`
- Door-interlock precedent (binary pause/resume): `workspace/templates/CP-NEW-machine-tender-door-interlock.json` (goal + thoughts §3 + code `sim_control(action="pause"/"play")`)
- ROS2 time_scale (global, not per-robot): `service/.../handlers/_models.py:1945`
- Gate, no safety metric: `service/.../handlers/diagnostics.py:3920` (`simulate_traversal_check`), pass criteria docstring `:3925-3982`
