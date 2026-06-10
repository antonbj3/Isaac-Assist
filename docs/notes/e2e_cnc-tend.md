# E2E Trace — `cnc-tend` (T5, UR10, machine-tend)

**Scenario id:** `cnc-tend`
**Tier:** T5
**Robot:** UR10
**Task:** machine-tend (CNC load/cycle/unload)
**Persona:** CNC machinist (ONET SOC 51-4011 "Machinists")
**One-sentence request:** *"load a raw blank, open the machine door, wait for machining, unload, repeat 4x"*

**Matched template:** `workspace/templates/CP-NEW-yrkesroll-machinist-cnc-load.json`
(found via `grep -rliE "machine.tend|cnc|spindle|chuck|tend" workspace/templates/`; the two
siblings `CP-NEW-machine-tender-load-unload.json` (no door) and
`CP-NEW-machine-tender-door-interlock.json` (OPC-UA safety guard, not a work cycle) are the
near-misses the template's own `goal` explicitly distinguishes itself from —
`CP-NEW-yrkesroll-machinist-cnc-load.json:3`.)

**Template status (BE HONEST — this is a DRAFT):**
`"verified_status": "build-spec-2026-05-16; form-gate-schema pending; smoke-test pending"`
(`CP-NEW-yrkesroll-machinist-cnc-load.json:333`). Never smoke-tested. The sibling
`machine-tender-load-unload` is the only one with `form-gate-schema ✓`, and even it is
`smoke-test pending`. `motion_controllers.verified` is **empty** — both curobo and rmpflow are
`untested` for this template (`:334-340`).

---

## Legend
- `[USER]` machinist intent / a thing the human operator does or says
- `[LLM]` the model acting for the user (tool calls it emits)
- `[SYSTEM]` Kit / handler / gate runs on its own
- `[CHEAP-static]` no physics; USD geometry / IK / reach math (ms–seconds)
- `[EXPENSIVE-physics]` timeline plays, PhysX steps (10s–180s of sim wall time)

---

## 0. Scene anchors (ground truth from the template)

| prim | path | pos | note |
|---|---|---|---|
| UR10 base | `/World/UR10` | `[0,0,0.75]` | on a 0.75 m table; reach ≈1.30 m |
| CNC body | `/World/CNCBody` | `[0.60,0,1.05]` | visual housing, collider |
| **Door** | `/World/CNCBody/Door` | closed `[0.40,0,0.95]` / open `[0.40,0,1.30]` | **sliding-translate proxy, NOT a joint** |
| Fixture | `/World/CNCFixture` | `[0.40,0,0.80]` (top 0.81) | clamp-jaw stand-in; **no clamp** |
| Spindle | `/World/Spindle` | `[0.40,0,1.10]` | visual Cylinder, **no collider** |
| Infeed pallet | `/World/InfeedPallet` | `[0.40,0.50,0.80]` | bin (raw stock source) |
| Outfeed pallet | `/World/OutfeedPallet` | `[0.40,-0.50,0.80]` | bin (finished destination) |
| **Raw blank** | `/World/RawStock` | `[0.40,0.50,0.835]` | **single** 0.05 m cube, 0.5 kg, rubber |

Reach check (computed against base `[0,0,0.75]`, reach 1.30): infeed dist 0.64, fixture 0.40,
outfeed 0.64, spindle 0.53 — **all reachable, all dz within the +0.60/−0.15 z-window.** So the
plain reach/support/interpenetration static-eyes pass clean; the real pre-flight catch is on the
**collision** axis (door in the corridor — see §3).

---

## THE NUMBERED FLOW

### Phase A — User states intent, LLM retrieves the template

**1. [USER] [CHEAP-static]** Machinist types the request:
*"load a raw blank, open the machine door, wait for machining, unload, repeat 4x."*

**2. [LLM] [CHEAP-static]** Intent classification → `pattern_hint: pick_place`, structural tags
`isaac:industry.cnc_tending`, `isaac:yrkesroll.machinist`, `isaac:robot.ur10`,
`isaac:pattern.door_cycle` (`CP-NEW-yrkesroll-machinist-cnc-load.json:121-139`). Retrieval lands
on `CP-NEW-yrkesroll-machinist-cnc-load`.
> **HONESTY — request vs template mismatch #1:** the user says **"repeat 4x"**. The template
> has **exactly one** workpiece (`RawStock`, `grep -oE "RawStock[0-9]*"` → single name) and
> `intent.structural_features.n_workpieces: 1`, `n_handoffs: 2` (`:130`,`:124`). The 4× loop is
> **not modeled.** There is **no loop / iterate / repeat_cycle tool** (confirmed missing below),
> so the LLM would have to *unroll* the cycle by re-emitting the whole tool sequence 4× over 4
> distinct blank prims it must also author. The canonical as written does ONE cycle.

### Phase B — Scene build (all CHEAP-static authoring)

The instantiator runs `execute_template_canonical(tpl)` then `settle_after_canonical(tpl)`
(`scripts/qa/gate_one.py:64,68`). Every call below is a registered handler (all 11 confirmed
to have `_gen_*`/`_handle_*` definitions — see Tool Inventory).

**3. [LLM][SYSTEM] [CHEAP-static]** `create_prim` DomeLight + `set_attribute` intensity; `create_prim`
Ground + `apply_api_schema(PhysicsCollisionAPI)`; `create_prim` Table + collider.
Handlers: `scene_authoring.py:627` (create_prim), `:781` (set_attribute), `:1084` (apply_api_schema).

**4. [LLM][SYSTEM] [CHEAP-static]** `set_physics_scene_config({enable_gpu_dynamics: False, broadphase: MBP})`
→ CPU-deterministic (`physics.py:407`).

**5. [LLM][SYSTEM] [CHEAP-static]** `robot_wizard(robot_name="ur10", dest_path="/World/UR10",
position=[0,0,0.75])` (`robot.py:810`). NB this template uses raw `robot_wizard`; per MEMORY the
clean UR10 spawn replaces a wound-start `add_reference` — the wizard path gives home joints.

**6. [LLM][SYSTEM] [CHEAP-static]** `create_prim` CNCBody (Cube) + collider + grey display color.

**7. [LLM][SYSTEM] [CHEAP-static]** `create_prim` Door (Cube) at closed `[0.40,0,0.95]` + collider;
`set_attribute(xformOpOrder=["xformOp:translate"])` (defensive op-stack so the slide animates —
template failure_mode #5, `:117`); display color green (= closed).

**8. [LLM][SYSTEM] [CHEAP-static]** `create_prim` Fixture (flat Cube) + collider.

**9. [LLM][SYSTEM] [CHEAP-static]** `create_prim` Spindle (Cylinder), display color only —
**no PhysicsCollisionAPI** (template failure_mode #7, `:119`: cuRobo may swing through it).

**10. [LLM][SYSTEM] [CHEAP-static]** `create_bin` InfeedPallet, `create_bin` OutfeedPallet (`robot.py:2013`).

**11. [LLM][SYSTEM] [CHEAP-static]** `create_prim` RawStock (0.05 cube) + the four physics schemas
(`PhysicsRigidBodyAPI/CollisionAPI/MassAPI/PhysxRigidBodyAPI`); `set_attribute(physics:mass=0.5)`;
`apply_physics_material("rubber")` (`physics.py:331`); `bulk_set_attribute(sleepThreshold=0.0)`
(`scene_authoring.py:2951`).

### Phase C — Static pre-flight (the CHEAP gate that should run BEFORE the expensive one)

**12. [SYSTEM] [CHEAP-static] — static-eyes constraint validator** (`scripts/qa/scene_validate.py`).
Builds+settles, parks the arm at HOME, reads ACTUAL post-settle geometry, runs three axes:
REACH, INTERPENETRATION, SUPPORT.
- REACH (UR10 reach 1.30, `scene_validate.py:32`): infeed/fixture/outfeed/spindle all `dist ≤ 0.64`,
  `dz` within `[-0.15, +0.60]` → **CLEAN.**
- INTERPENETRATION: single workpiece → no pairs → **CLEAN.**
- SUPPORT: RawStock rests on infeed pallet floor → **CLEAN.**
- **Verdict: CLEAN** — this validator alone would NOT catch the real risk, because it parks the arm
  and never plans a path through the *closed door*.

**13. [LLM/SYSTEM] [CHEAP-static] — `diagnose_scene_feasibility`** (`service/.../diagnose/tool.py:197`),
the handler-level reach/collision/fit pre-filter. Template ships `diagnose_args` with
`robot_path`, `robot_base:[0,0,0.75]`, and obstacles including **`/World/CNCBody/Door`**
(`:95-111`). Metric axes: `reach`, `collision`, `clearance`, `singular` (`diagnose/metrics.py`).
> **THIS is where the cheap filter earns its keep.** With the door at its **closed** pose
> `[0.40,0,0.95]` it sits directly in the vertical pick corridor — between fixture top (z=0.81)
> and spindle (z=1.10) at x=0.40. A pick-pose IK + collision probe at the fixture with the door
> listed as an obstacle returns a **collision/clearance violation** → `verdict: infeasible`.
> That predicts, in <1 s, the EXPENSIVE failure the template documents as failure_mode #1
> (`:113`): *"Door not open when robot reaches for fixture — collision: if the door-open
> set_attribute has not advanced one render frame before pick-place planning, cuRobo sees the
> door closed and fails IK / reports collision."*
> **Caveat (honest):** `diagnose_scene_feasibility` static-checks **only if a pose is provided**;
> with no `pick_pose`/`drop_pose` it returns a tolerant neutral `feasible` (`tool.py:229-243`).
> The CP templates compute poses at runtime, so unless the caller passes explicit poses the
> pre-filter degrades to a no-op here — the door-collision catch is **available but not
> guaranteed to fire** the way the args are currently wired.

### Phase D — PHASE 1: open door, load blank (the work begins)

**14. [USER→LLM] [CHEAP-static]** "Open the door." → `set_attribute(Door, xformOp:translate=[0.40,0,1.30])`
+ color red (`=open`). **No real joint** — pure translate write.
> **Mitigation the template itself prescribes (failure_mode #1):** insert
> `sim_control(action="step", step_count=2)` so the open pose advances one render frame before
> cuRobo plans. The shipped `code` does NOT include that step between open and PPC — a latent bug.

**15. [LLM][SYSTEM] [CHEAP-static→ then physics]** `setup_pick_place_controller(robot_path=/World/UR10,
target_source="curobo", robot_family="ur10", source_paths=[/World/RawStock],
destination_path=/World/CNCFixture, planning_obstacles=[Table, CNCBody, Spindle, Infeed, Outfeed],
phase_id="phase1")` (`pick_place.py:293`; `phase_id` plumbed at `:399`). Planning (IK/trajopt) is
cheap-ish; the actual pick/carry/place executes under the played timeline = physics.
> **HONESTY:** `Spindle` is in `planning_obstacles` but has **no collider** (step 9) → cuRobo may
> ignore it and swing the arm through the spindle column (failure_mode #7). UR10 transit-swing is
> a known open issue in this codebase (H7 swing fix is curobo-side, partial).

**16. [SYSTEM] [CHEAP-static]** `get_world_transform(/World/RawStock)` — verify blank landed on fixture
(`scene_authoring.py:3798`).

### Phase E — PHASE 2: close door, run the machining cycle

**17. [USER→LLM] [CHEAP-static]** "Close the door." → `set_attribute(Door, translate=[0.40,0,0.95])` + green.

**18. [USER→LLM] [EXPENSIVE-physics]** "Wait for machining." → `sim_control(action="step", step_count=300)`
= 5 s sim-time @ 60 Hz (`diagnostics.py:2073`). The blank is held on the fixture by **gravity +
rubber friction only**.
> **HONESTY — failure_mode #4 (`:116`):** there is **no clamp**. No `PhysicsFixedJoint` locks
> RawStock to the fixture. 5 s usually survives, but articulation vibration can knock the blank
> loose. The "future work" note proposes adding a fixed joint during the dwell — but **no
> `clamp_workpiece` / `attach_to_articulation` tool exists**; the only path is the low-level
> `apply_api_schema(PhysicsFixedJoint)` verb (`scene_authoring.py:1118`), which the template does
> not use. So the clamp is genuinely UNMODELED.
> The spindle never moves and never cuts — "machining" is a 300-step dwell with a visual cylinder.

### Phase F — PHASE 3: open door, unload to outfeed

**19. [USER→LLM] [CHEAP-static]** "Open the door." → `set_attribute(Door, translate=[0.40,0,1.30])` + red.

**20. [LLM][SYSTEM] [EXPENSIVE-physics]** Second `setup_pick_place_controller(... source=[/World/RawStock],
destination_path=/World/OutfeedPallet, phase_id="phase2")`. Dual-PPC on one articulation is the
verified pattern from `machine-tender-load-unload` (failure_mode #6, `:118`); `phase_id` keeps the
second controller's subscription from clobbering the first (`pick_place.py:397-399`).

**21. [SYSTEM] [CHEAP-static]** `get_world_transform(/World/RawStock)` — verify it reached outfeed.

**22. [USER→LLM] [CHEAP-static]** "Return to safe state." → `set_attribute(Door, translate=[0.40,0,0.95])`
+ green. Door cycle sequence per `settle_state.door_state_sequence` (`:27-33`):
`closed → open_for_load → closed_for_cycle → open_for_unload → closed_safe` (4 toggles).

### Phase G — Steps 14–22 ×4 (the user's "repeat 4x")

**23. [USER] [—]** "Repeat 4×." Steps 14–22 would re-run for blanks 2, 3, 4.
> **HONESTY — request mismatch #2 (the big one):** the template models **one** cycle on **one**
> blank. There is **no repeat/loop tool** (`loop_workflow`, `repeat_cycle`, `machining_cycle` all
> confirmed MISSING). The LLM would have to: author 3 more blank prims, then re-emit the full
> open→PPC→close→sim_control→open→PPC→close sequence 3 more times, each with a fresh `phase_id`.
> Whether 4 sequential `setup_pick_place_controller` installs on one UR10 articulation stay stable
> is **unverified** (the precedent covers 2, not 8). The "4x" is the part of the user's request
> the canonical does NOT cover.

### Phase H — THE GATE (the outcome / EXPENSIVE-physics)

**24. [SYSTEM] [EXPENSIVE-physics] — function gate** (`scripts/qa/gate_one.py` →
`simulate_traversal_check`, handler `diagnostics.py:3920`). Runs with the template's own
`simulate_args`: `cube_path=/World/RawStock`, `target_path=/World/OutfeedPallet`,
`duration_s=180`, `xy_tolerance=0.12` (`:88-94`). Plays the timeline up to 180 s sim-time and
samples the cube.

**GATE SUCCESS CRITERION (the outcome — exact, single-cube path):**
```
success = in_target_xy AND above_floor AND at_rest AND upright_ok
```
(`diagnostics.py` generated code line ~370):
- `in_target_xy` — RawStock XY inside OutfeedPallet bbox expanded by `xy_tolerance=0.12`
- `above_floor` — cube Z ≥ pallet floor − `floor_tolerance` (0.10 default)
- `at_rest` — `cube_speed < 0.05 m/s`
- `upright_ok` — trivially True (`require_upright` not set in simulate_args)

i.e. **the blank ends up resting, settled, inside the outfeed pallet.** That is the entire
machine-tend outcome the gate scores.

> **HONESTY — the gate ignores most of the task:**
> - The gate **never reads the door.** `simulate_args.expected_door_cycles: 2` (`:93`) is declared
>   but **no handler reads `expected_door_cycles` / `door_path` / `door_state`** anywhere
>   (grep over `diagnostics.py` → zero hits). The door cycle is **completely unverified** by the
>   gate. A scene that delivered the cube with the door welded shut would still PASS.
> - The gate **never verifies the machining dwell, the fixture hold, or the clamp.**
> - The gate scores **one cube to outfeed.** It has **no notion of "4×."** Even run as written,
>   passing means a single blank reached the outfeed pallet.

**25. [SYSTEM]** Verdict printed as JSON `success=True|False`. For this DRAFT template, run with
`gate_one.py CP-NEW-yrkesroll-machinist-cnc-load`, the outcome is **UNVERIFIED** — never
smoke-tested (`:333`), no controller marked verified, and two latent bugs in the shipped `code`
(missing `sim_control(step=2)` frame-advance after door-open; spindle obstacle without a collider).
**Predicted live outcome:** the static `diagnose_scene_feasibility` collision catch (step 13) and
failure_mode #1 both point at a door-collision plan-fail on phase-1 pick unless the frame-advance
mitigation is added; if that's patched, single-cycle delivery is plausible but the 4× loop is
out of scope.

---

## Where the CHEAP static-eyes pre-filter catches the EXPENSIVE failure

| risk | caught by | axis | when |
|---|---|---|---|
| Door closed in pick corridor → cuRobo collision/IK-fail at fixture | `diagnose_scene_feasibility` (`diagnose/tool.py:197`, metrics `collision`/`clearance`) **IF a pick_pose is passed** | CHEAP-static, <1 s | step 13, BEFORE 180 s sim |
| Blank out of reach / floating / clumped | `scene_validate.py` REACH/SUPPORT/INTERPEN | CHEAP-static, ~3 s | step 12 — here returns CLEAN |
| Spindle has no collider → arm swings through | NOT caught statically (visual-only prim); only a played sim shows it | EXPENSIVE | not pre-filtered |
| No clamp → blank drifts during dwell | NOT caught statically (needs physics) | EXPENSIVE | not pre-filtered |

The static filter's win here is the **door-collision** prediction: a sub-second IK+collision probe
replaces a 180 s play that would dead-end on phase-1 pick — **provided** the caller supplies poses
(otherwise `diagnose_scene_feasibility` no-ops, `tool.py:229-243`).

---

## TOOL INVENTORY

### Tools the flow needs that DO exist (all 11 in `tools_used` confirmed registered, file:line)
| tool | handler |
|---|---|
| create_prim | `scene_authoring.py:627` |
| set_attribute | `scene_authoring.py:781` |
| apply_api_schema | `scene_authoring.py:1084` |
| robot_wizard | `robot.py:810` |
| create_bin | `robot.py:2013` |
| set_physics_scene_config | `physics.py:407` |
| apply_physics_material | `physics.py:331` |
| bulk_set_attribute | `scene_authoring.py:2951` |
| setup_pick_place_controller | `pick_place.py:293` (phase_id `:399`) |
| sim_control | `diagnostics.py:2073` |
| get_world_transform | `scene_authoring.py:3798` |
| simulate_traversal_check (gate) | `diagnostics.py:3920` |
| diagnose_scene_feasibility (pre-flight) | `diagnose/tool.py:197` |

### Tools that would be needed but DO NOT EXIST (grep-confirmed missing)
- **`open_door` / `articulate_door` / `set_joint_position` / `drive_joint`** — there is NO
  articulated-door tool. The door is faked with `set_attribute(xformOp:translate)`; it is a
  translate-write, not a real prismatic joint, so it can't be driven, can't report state, and the
  gate can't read it. (`set_joint_targets`/`set_joint_limits` exist in `physics.py:174/297` for
  *robot* joints, but nothing opens a *door*.)
- **`clamp_workpiece` / `attach_to_articulation` / `add_fixed_joint`** — NO workpiece-clamp tool.
  The fixture hold during machining is unmodeled (gravity+friction). The only fixed-joint path is
  the low-level `apply_api_schema(PhysicsFixedJoint)` schema verb (`scene_authoring.py:1118`),
  which is not a task-level clamp and the template doesn't use it.
- **`machining_cycle` / `spindle_cycle`** — NO machining-process tool. "Machining" = a bare
  `sim_control(step=300)` dwell with a static visual cylinder. No material removal, no spindle
  motion, no cycle-complete signal.
- **`loop_workflow` / `repeat_cycle` / iterate** — NO loop primitive. The user's **"repeat 4x"**
  has no tool support; the LLM must unroll it by hand over 4 manually-authored blanks.
- **Door-cycle verification in the gate** — `simulate_traversal_check` has no door/cycle-count
  parameter; `expected_door_cycles` is declared in `simulate_args` but **read by nothing**.

---

## Honest bottom line
- **Template is a DRAFT:** build-spec only, form-gate-schema pending, **never smoke-tested**, zero
  verified motion controllers (`CP-NEW-yrkesroll-machinist-cnc-load.json:333-340`).
- **Request coverage:** "load a blank" ✓, "open the door" ✓ (as a translate proxy, not a joint),
  "wait for machining" ✓ (as a 300-step dwell, no real cut, **no clamp**), "unload" ✓, **"repeat
  4x" ✗ — modeled as a single cycle on a single blank with no loop tool.**
- **Gate outcome scored = ONE cube settled inside `/World/OutfeedPallet`** (in_xy ∧ above_floor ∧
  at_rest). The door cycle, the dwell, the fixture/clamp, and the 4× repeat are **all outside the
  gate's success criterion.**
- **Cheap-before-expensive win:** `diagnose_scene_feasibility`'s collision/clearance axis can
  predict the door-collision plan-fail (failure_mode #1) in <1 s — but only if pick/drop poses are
  passed; with runtime-computed poses it currently no-ops.
