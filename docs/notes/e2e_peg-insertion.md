# E2E Trace — peg-insertion (T5 / franka / insertion)

**Scenario id:** `peg-insertion`
**Tier:** T5 (force-gated compliant insertion + conditional retry — the hardest assembly class)
**Robot:** Franka Panda
**Task:** insertion
**Persona:** assembler (ONET SOC 51-2099, Assemblers and Fabricators, All Other)
**One-sentence request:** *"insert a peg into a bushing and stop if force exceeds 15N, retry on a snap-fit click"*

---

## 0. Template match (grounding)

`grep -rilE "peg|insert|bushing|snap.?fit|force" workspace/templates/` surfaces the family. The request is a **hybrid of three real templates** — no single canonical implements it end-to-end:

| Request clause | Closest real template | What it actually carries |
|---|---|---|
| "insert a peg into a bushing" | **`CP-NEW-yrkesroll-assembler-peg-bushing.json`** (assembler persona, pattern_hint `insert`, `franka_panda`, single station) | full pick + transit + insert per peg, 3-peg cadence, `success_rate` metric |
| "stop if force exceeds **15N**" | **`CP-NEW-screw-driving-impedance.json`** (`add_force_torque_sensor threshold=15.0` — line 28) | the peg-bushing template's cap is **20 N** (goal line 3), NOT 15 N → the request is a **delta** off the nearest template |
| "retry on a **snap-fit click**" | **`CP-NEW-yrkesroll-assembler-snap-fit.json`** (`get_contact_report` transient-impulse detection) | detects the click signature; has **no retry loop** |

**Primary match chosen:** `CP-NEW-yrkesroll-assembler-peg-bushing.json` (topology + robot + insertion gesture), **parameter-overridden** to a 15 N cap, with the snap-fit template's `get_contact_report` click-detection grafted in. The "retry-on-click" control loop matches **no template and no tool** (see §8).

`verified_status` on both source templates: *"drafted-2026-05-16; form-gate-schema pending lint; function-gate pending Kit RPC + ros2_control bridge."* **This canonical has never had a verified live run.** Everything below the build phase is `dry_run=True` config-emission, not physics.

---

## 1. Full numbered narrative — the complete action sequence

Tags: **[USER]/[LLM]/[SYSTEM]** for the actor; **[CHEAP-static]** = no physics step (prim authoring, config dicts, reach/fit math) / **[EXPENSIVE-physics]** = a Kit `play()`→step→`stop()` loop.

### Phase A — request → intent (no scene yet)

1. **[USER]** types the one-sentence request into the chat surface: *"insert a peg into a bushing and stop if force exceeds 15N, retry on a snap-fit click."* — **[CHEAP-static]** *(USER action step 1)*

2. **[LLM]** parses intent. Extracts: `pattern_hint=insert`, robot=`franka_panda` (default for insertion/assembler), force cap = **15 N** (overrides the template's 20 N), a runtime **stop-on-force** semantic, and a **retry-on-click** loop. Maps to structural tags `isaac:topology.insertion`, `isaac:assembly.force_gated`, `isaac:compliance.cartesian_impedance`, `isaac:sensor.contact_report`. — **[CHEAP-static]**

3. **[SYSTEM]** retrieval ranks `CP-NEW-yrkesroll-assembler-peg-bushing` top (matches insert + franka + single-station + force-gated), with `snap-fit` and `screw-driving-impedance` as near-siblings. — **[CHEAP-static]**

### Phase B — scene build (CHEAP-static authoring through Kit RPC)

The LLM replays the matched template's `code` block. Each call is `exec_sync` against Kit but only **authors USD prims / config** — no `play()`, so no physics is stepped. Source: template `code` field; handlers confirmed present in `service/isaac_assist_service/chat/tools/handlers/`.

4. **[LLM]→[SYSTEM]** `create_prim` DomeLight + Ground + Table; `apply_api_schema(PhysicsCollisionAPI)`; `set_physics_scene_config({enable_gpu_dynamics:False, broadphase:MBP})` (CPU-deterministic, required for reliable contact reports). — **[CHEAP-static]** *(USER action step 2 — "build the station")*

5. **[LLM]→[SYSTEM]** `robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0,0,0.75], orientation=[0.7071,0,0,0.7071])`. (Handler `robot.py`; note the project-wide lesson that raw `add_reference` spawns the arm wound — `robot_wizard` spawns at home joints.) — **[CHEAP-static]**

6. **[LLM]→[SYSTEM]** `create_prim("/World/Bushing", Cube, pos=[0,-0.25,0.795], scale=[0.10,0.10,0.04])` + `PhysicsCollisionAPI` (static by **absence** of RigidBodyAPI). Bore top rim z=0.815; seated peg-centre z=0.810. — **[CHEAP-static]**
   - *Honesty:* the bushing is a **solid Cube with no hollow bore** (template `failure_modes[1]`). The peg lands on the fixture top face; "seated" is approximated by final-Z, not by entry into a real bore. No `setup_assembly_constraint` is declared.

7. **[LLM]→[SYSTEM]** `create_prim("/World/InfeedTray", ...)` + 3× peg `Cylinder` (r=0.012, h=0.07) at y=0.05/0.10/0.15, each with `PhysicsRigidBodyAPI + CollisionAPI + MassAPI + PhysxRigidBodyAPI`, mass 0.025 kg, `apply_physics_material("rubber")`. For the request's single-peg framing, only `Peg_1` is load-bearing; the other two are cadence scaffolding. — **[CHEAP-static]**

8. **[LLM]→[SYSTEM]** `bulk_set_attribute(sleepThreshold=0.0)` and `solverPositionIterationCount=16` on pegs+bushing (prevents the awake/asleep oscillation that blows peg velocity to >200 km/s during grip — template `failure_modes[0]`). — **[CHEAP-static]**

9. **[LLM]→[SYSTEM]** `add_force_torque_sensor(sensor_path="/World/Franka/FtSensor", parent_path="/World/Franka/panda_hand", threshold=15.0, noise_std=0.05)`. **← the request's 15 N override** (template default 20 N). Handler: `handlers/sensors.py`. — **[CHEAP-static]**
   - *Honesty:* this **authors a sensor prim with a threshold attribute. It does NOT install a runtime guard.** The sensor reports breach; nothing auto-pauses the trajectory (template `failure_modes[6]`: "the sensor reports breach but does NOT auto-pause the trajectory"). See §8.

10. **[LLM]→[SYSTEM]** `add_proximity_sensor("/World/PickSensor", ...)` over the tray for pick detection; **[snap-fit graft]** `apply_api_schema("/World/Bushing", "PhysxContactReportAPI")` so the click transient can be read. — **[CHEAP-static]**

### Phase C — controller config (CHEAP-static — every call is dry_run, emits a config dict only)

This is the **critical honesty boundary**. `grep -n "dry_run\|NotImplemented" handlers/compliance.py` confirms every compliance handler **raises `NotImplementedError` when `dry_run=False`** (`compliance.py:185-190, 398-404, 536-537`) — *"requires Kit RPC + ros2_control bridge … Use dry_run=True to receive the config dict."* There is no ros2_control bridge in the repo (`grep ros2_control handlers/` → only the NotImplementedError strings).

11. **[LLM]→[SYSTEM]** `setup_impedance_controller(robot_path="/World/Franka", Kx=[300,300,80], Kr=[30,30,30], Dx=[30,30,10], Dr=[3,3,3], torque_mode=True, dry_run=True)`. Returns `{success:True, dry_run:True, ...config...}`. Z-stiffness soft (80) so the wrist surrenders to the force cap; X/Y stiff to keep the peg axially aligned. **No torque is applied to any joint.** — **[CHEAP-static]** *(USER action step 3 — "set up the compliant insert")*

12. **[LLM]→[SYSTEM]** `set_compliance_params(... dry_run=True)` — mirrors the gains into an in-memory dict. — **[CHEAP-static]**

### Phase D — STATIC-EYES PRE-FILTER (CHEAP-static — catches problems *before* the expensive gate)

Before any physics, the static validators read the **post-settle actual geometry** and check reach/fit/support with pure math. These run a ~2.5 s passive settle (150 `app.update()` with the arm parked) but **no controller execution** — they are the cheap gate that catches the failure the expensive gate would otherwise burn 240 s to discover.

13. **[SYSTEM]** `scripts/qa/scene_validate.py CP-NEW-yrkesroll-assembler-peg-bushing` — three checks (`scene_validate.py:1-23`):
    - **REACH:** is `/World/Peg_1` (and the bushing drop target [0,-0.25,0.810]) inside the Franka reachable shell? Uses `ROBOT_REACH["franka_panda"]=0.855` (`scene_validate.py:32`), mirroring the controller's own gate in `handlers/diagnostics.py verify_pickplace_pipeline`. Peg at [0.30,0.05,~0.79] dist from base [0,0,0.75] ≈ 0.30 m → **reachable**. Bushing at [0,-0.25,0.81] ≈ 0.26 m → **reachable**. **PASS.**
    - **INTERPENETRATION:** are the 3 pegs clumped into one point (the dispenser-clump class)? Pegs are 5 cm apart on the tray → **PASS.**
    - **SUPPORT:** does each peg rest on the tray (not floating / not buried)? Peg-centre z=0.7925 = tray-top 0.7575 + half-height 0.035 → **PASS.**
    - **Where it would catch a problem:** had the LLM placed the bushing drop target at the request-realistic *full-insertion* depth (peg fully through a real bore, e.g. z=0.78, ~0.27 m but angled below the base), or had it parameterized a peg out past 0.855 m, **REACH fails here in <5 s** and the run is rejected before the 240 s physics gate. This is the cheap-catches-expensive saving. — **[CHEAP-static]** *(USER action step 4 — "check it's reachable before running")*

14. **[SYSTEM]** *(optional)* `scripts/qa/reach_validate.py` runs the live-cuRobo IK pre-flight (`solve_ik` at the seated waypoint [0,-0.25,0.810]). Template `failure_modes[2]` explicitly recommends this: *"solve_ik pre-flight at [0.0,-0.25,0.810] before installing the impedance controller."* If IK fails at the seated z, the insert would stall and final-Z would read above threshold → caught now, not at the gate. — **[CHEAP-static]**

### Phase E — pick + transit (the only part that runs real physics + motion)

15. **[LLM]→[SYSTEM]** `define_grasp_pose(object_path="/World/Peg_1", approach_direction=[0,0,-1])` then `setup_pick_place_controller(target_source="curobo", source_paths=["/World/Peg_1"], destination_path="/World/Bushing", drop_target=[0.0,-0.25,0.835], planning_obstacles=["/World/Table","/World/Bushing","/World/InfeedTray"], approach_height=0.12, lift_height=0.12, phase_id="phase1")`. cuRobo plans pick → lift → transit → hover 20 mm above the rim. This **does** drive the articulation. — **[CHEAP-static]** to author, **[EXPENSIVE-physics]** when stepped by the gate. *(USER action step 5 — "run the insertion")*
    - `motion_controllers.untested: [curobo, impedance, cartesian_impedance]` — no verified run exists for this template; cuRobo pick under Kit RPC is the project's chronic-risk surface (Warp cache → plan_pose fails).

### Phase F — the compliant press (what the request actually asks for — and what does NOT execute)

16. **[LLM]→[SYSTEM]** `follow_trajectory_with_compliance(trajectory=[hover 0.835 → rim 0.820 → seated 0.810], compliance_handoff_at=0.33, compliance_controller="cartesian_impedance", velocity_scaling=0.15, dry_run=True)`. — **[CHEAP-static]**
    - *Honesty (the core gap):* `dry_run=True` → this returns a **trajectory config dict, no motion**. `dry_run=False` → **`NotImplementedError`** (`compliance.py`). So the *defining gesture of the request* — the force-capped compliant descent — **does not physically run anywhere in the current system.** The 15 N cap is never enforced because the controller that would honor it is unimplemented.

17. **[LLM]→[SYSTEM]** `get_joint_torques(articulation="/World/Franka")` — post-hoc read of wrist torque (template's stand-in for the force check). **[snap-fit graft]** `get_contact_report("/World/Bushing", max_contacts=50)` — scans for the click signature (impulse spike >0.5 N·s then drop). In dry_run these read whatever static state exists; with no compliant descent stepped, **there is no click to detect.** — **[CHEAP-static]**

18. **[LLM]→[SYSTEM]** `get_world_transform("/World/Peg_1")` — confirm final-Z below 0.815 seated threshold. — **[CHEAP-static]**

### Phase G — the "retry on snap-fit click" loop (NO IMPLEMENTATION)

19. **[LLM]** *would* need to: detect the click via `get_contact_report`, decide insertion failed (clip stalled, prong hit a side wall), and **re-issue the press** — a conditional control loop. **No tool exists for this** (see §8). The LLM can only emit the calls in sequence; there is no force-guarded / retry-on-event primitive to bind them into a real closed loop. — **[CHEAP-static]** *(USER action step 6 — "and retry if it clicks/fails")*

### Phase H — the gate (EXPENSIVE-physics — the actual outcome measurement)

20. **[SYSTEM]** `scripts/qa/gate_one.py CP-NEW-yrkesroll-assembler-peg-bushing`: build → settle → `simulate_traversal_check(cube_path="/World/Peg_1", target_path="/World/Bushing", duration_s=240)`. This is the **only** expensive-physics outcome check. Handler `_handle_simulate_traversal_check` (`diagnostics.py:3920`) runs `play()→step→stop` for up to 240 s. — **[EXPENSIVE-physics]**

---

## 2. Gate success-criterion (the OUTCOME)

From `diagnostics.py:3968-3982` (`_handle_simulate_traversal_check` docstring) — `success=True` iff the **primary cube is delivered**: `cube_final` XY is inside the target bbox (expanded by `xy_tolerance=0.01`) **AND** `above_floor` (final Z ≥ target-min-Z − floor_tol) **AND** `at_rest` (`cube_speed < 0.05`). Multi-run: `success` iff `n_ok*2 ≥ n_runs` (majority). Status bucket: `stable_ok` / `flaky` / `stable_fail`.

**This is a pick-place delivery gate.** It measures *did the peg end up at the bushing XY, above floor, at rest.* It has **no concept** of:
- the **15 N force cap** (no force channel in the verdict),
- the **compliant descent** (the gate only sees final cube pose),
- the **snap-fit click** (no contact-report term in the criterion),
- the **retry loop** (single delivery check).

So even a "PASS" here would **not** confirm the request was honored — it confirms only that a peg reached the bushing footprint. The template's own richer contract — `production_metrics.success_rate = pegs_seated_within_3mm_and_below_0.815 / 3, expected=1.0` (`settle_state.production_metrics`) — is an **aspirational contract, not a measurement** (template `failure_modes[8]`).

---

## 3. Predicted outcome (honest)

- **Static pre-filter (Phase D):** **PASS** — geometry is reachable, unclumped, supported. (Cheap; ~5 s.)
- **Expensive gate (Phase H):** **uncertain → likely `stable_fail` or `flaky`.** The insert depends on cuRobo IK at the seated waypoint on an untested template, and the "delivery" the gate looks for is a peg dropped at the bushing XY by the pick-place controller (Phase E), **not** the compliant press (Phase F, which never runs). If pick-place's `drop_target=[0,-0.25,0.835]` lands the peg in-XY and it settles at rest above floor → the gate can read PASS **while the actual force-cap-and-retry behavior was never exercised** (a known false-positive shape: the gate "lies" relative to the request's real semantics).
- **Request fidelity:** **NOT satisfied.** "Stop if force exceeds 15 N" and "retry on snap-fit click" are scene/config metadata with **no executor**. The honest verdict is *capability-unverified*, gated behind the ros2_control bridge + a retry/force-guard tool that do not exist.

---

## 4. CHEAP-static vs EXPENSIVE-physics ledger

| Phase | Steps | Class | Physics stepped? |
|---|---|---|---|
| A intent | 1-3 | CHEAP-static | no |
| B scene build | 4-10 | CHEAP-static | no (prim authoring) |
| C controller config | 11-12 | CHEAP-static | no (dry_run config dicts) |
| **D static-eyes pre-filter** | **13-14** | **CHEAP-static** | settle only, no controller — **catches reach/fit/support before the gate** |
| E pick+transit author | 15 | CHEAP-static to author | physics only when the gate steps it |
| F compliant press | 16-18 | CHEAP-static | **never** (dry_run / NotImplementedError) |
| G retry loop | 19 | — | **no tool** |
| **H gate** | **20** | **EXPENSIVE-physics** | **yes — the only 240 s play loop** |

---

## 5. Tool gaps — needed by the request but MISSING (grep-confirmed)

Confirmed by `grep -rilE` over `service/isaac_assist_service/chat/tools/handlers/` (empty result = absent):

1. **Force-guarded / abort-on-threshold trajectory** — no `abort_on_force` / `pause_on_force` / `force_guard` / `stop_on_threshold` / `monitor_force` handler. The 15 N cap is an **authored sensor attribute with no runtime enforcement**. The nearest existing tools are inert: `add_force_torque_sensor` only authors the prim+threshold; `monitor_joint_effort` (`diagnostics.py:857`) is a **code-gen probe that prints effort and auto-stubs missing prims** — it does not abort or pause a trajectory.

2. **Retry-on-event control loop** — no `retry_on` / `insertion_retry` / `snap_retry` / `guarded_move` handler. `execute_with_retry` (`workflow.py:930`) exists but is the **LLM code-patch error-fix loop** (retry on a Python exception during authoring), NOT a physics retry-on-contact-event. There is no primitive to bind `get_contact_report` → decide → re-press into a closed loop.

3. **Live compliant insertion executor** — `setup_impedance_controller`, `set_compliance_params`, `follow_trajectory_with_compliance`, `setup_insertion_controller` all **raise `NotImplementedError` when `dry_run=False`** (`compliance.py:185, 398, 536`; `insertion.py:25`). Blocked on the **ros2_control bridge**, which is **not present** in the repo (only referenced in error strings: `compliance.py:188, 257`).

4. **Real hollow-bore bushing geometry** — bushing is a solid Cube; no `setup_assembly_constraint` is declared. Real insertion fidelity needs a mesh import (`add_usd_reference` of a bored bushing) or `create_deformable_mesh`. Template `failure_modes[1]`.

5. **Force/contact-aware gate** — `simulate_traversal_check` is delivery-only; there is **no gate that scores force-cap compliance or the snap-click signature.** The request's outcome is structurally unmeasurable by the current gate.

---

## 6. Honesty summary

- **Template status:** both source templates are **drafts** (`drafted-2026-05-16`), form-gate-schema lint pending, function-gate never run. `motion_controllers.verified=[]`.
- **The defining behaviors of the request do not execute:** force-capped compliant descent (`dry_run`/`NotImplementedError`), and retry-on-click (no tool).
- **15 N is a delta** off the nearest peg-bushing template (which uses 20 N); the value matches the screw-driving sibling — the LLM would have to override the cap, which is just changing an inert authored attribute.
- **A gate PASS would be a false positive** relative to the request: it certifies "peg reached bushing XY, at rest, above floor," not "stopped at 15 N and retried on a click."
- **Verdict: capability-unverified.** The cheap static-eyes pre-filter (reach/fit/support) is the one part that genuinely runs and genuinely guards; everything that makes this a T5 insertion task is scaffolding awaiting the ros2_control bridge plus two missing runtime tools (force-guard, retry-on-event).
