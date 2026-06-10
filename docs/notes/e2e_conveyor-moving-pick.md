# E2E trace — `conveyor-moving-pick` (T3, UR10, conveyor-pick)

**Scenario id:** `conveyor-moving-pick`
**Tier:** T3
**Robot:** UR10
**Task:** conveyor-pick
**Persona:** line operator
**One-sentence request:** *"UR10 picks cubes off a moving conveyor into a bin as they pass"*

This document traces the COMPLETE sequence of actions the line operator (and the LLM acting for them) takes
to reach the target scene, every tool call, where the **static-eyes pre-filter** catches a problem before
the expensive physics gate runs, the **gate success-criterion** (the outcome), and every tool that *would*
be needed but **does not exist**. Each step is marked `[USER]`/`[LLM]`/`[SYSTEM]` and
`[CHEAP-static]`/`[EXPENSIVE-physics]`.

---

## 0. Which real template does this resolve to?

Three library templates match "moving conveyor pick" (grep on `workspace/templates/`):

| Template | Robot (role_defaults) | Strategy | Status |
|---|---|---|---|
| `CP-73.json` | **ur10** | belt-pause + proximity-sensor, cuRobo (Cortex layer **removed**) | `form-gate ✓; function-gate ✗ (UR10 surface-gripper limitation)` |
| `CP-NEW-moving-conveyor-pick.json` (A39) | franka | belt-PAUSE + `interpolate_trajectory` feed-forward | `form-gate OK; interpolate_trajectory vestigial` |
| `CP-NEW-conveyor-tracking-moving-pick.json` (A108) | franka | belt-RUNNING + vision predictive-intercept | `drafted; function-gate ⏳ (needs live Kit + Gemini-ER)` |

**Honest call:** the scenario specifies **UR10**, so the matching canonical is **`CP-73`** (`task_id: CP-73`,
`workspace/templates/CP-73.json:1`, goal at `:goal` realizes `#33 demo_ur10_conveyor`). The two `CP-NEW-*`
moving-pick templates *allow* `ur10` only as a **role constraint** (`roles.primary_robot.constraints` lists
`["franka_panda","franka","ur10"]`, `CP-NEW-moving-conveyor-pick.json:122-132`), but their
`role_defaults.primary_robot.class` is **`franka`** (`:167-182`) — instantiating either for a UR10 ask means
the LLM must override the default robot class, which is unverified. So the trace below uses CP-73 as the
ground-truth target scene and notes where the operator's phrasing ("as they pass" = belt *not* paused) pulls
toward the A108 vision-tracked pattern that has **no UR10 default and no runtime tooling**.

CP-73 layout (from `CP-73.json` code): UR10 base `[0,0,0.75]` on a table; `ConveyorBelt`
`size=[2.5,0.4,0.05] surface_velocity=[0.2,0,0]`; 4 cubes spawned upstream at x∈[-1.6,-1.0] on the belt;
`PickSensor` at `[0.0,0.4,0.835]`; output `Bin` at `[0.5,-0.3,0.75]`.

---

## 1. Numbered narrative — full traced flow

### Step 1 — Operator states the goal
**[USER] [CHEAP-static]**
Operator types: *"UR10 picks cubes off a moving conveyor into a bin as they pass."*
No tool call. This is the natural-language request the LLM must turn into a scene + controller wiring.
The phrase **"as they pass"** is semantically the belt-RUNNING (A108) pattern, but the only UR10-grounded
realization is CP-73's belt-PAUSE controller. This mismatch is carried forward as risk.

### Step 2 — LLM parses intent → structural features
**[LLM] [CHEAP-static]**
The LLM maps the request to the `intent` block shape: `pattern_hint=pick_place`, `n_robot_stations=1`,
`destination_kind=single_bin`, `uses_conveyor_transport=true`, `has_moving_belt_pick=true`,
robot family `ur10`. Structural tags resolve toward `isaac:industry.conveyor_pick` +
`isaac:transport.belt_to_bin` + `isaac:robot.fixed_base.arm`. Retrieval over these tags returns CP-73 as the
UR10 match (the two `CP-NEW` moving-pick templates carry `isaac:robot.franka`).

### Step 3 — LLM emits the scene skeleton
**[LLM] → [SYSTEM] [CHEAP-static]**
The LLM emits the static scene-build tool calls. Each is a real handler (`exec_sync` into Kit, authored USD,
no timeline play). Grounded against `CP-73.json` code:
- `create_prim` DomeLight / Ground / Table, `set_attribute`, `apply_api_schema(PhysicsCollisionAPI)`
- `set_physics_scene_config(config={enable_gpu_dynamics:False, broadphase_type:MBP})`
  (CPU determinism for belt contact)
- handlers: `resolve.py` dispatches `create_prim`, `create_conveyor`, `create_bin`, `robot_wizard`,
  `setup_pick_place_controller`; `sensors.py` dispatches `add_proximity_sensor`.

### Step 4 — LLM spawns the UR10
**[LLM] → [SYSTEM] [CHEAP-static]**
`robot_wizard(robot_name="ur10", dest_path="/World/UR10", position=[0,0,0.75], orientation=...)`.
`robot_wizard` (`handlers/resolve.py`) applies UR10 `home_joints` + `ee_link`. This is the
documented-correct UR10 spawn path: a raw `add_reference(ur10.usd)` would start the arm **wound**
(wrist_2 ≈ −298°) per the UR10 wound-start root cause; `robot_wizard` avoids it.

### Step 5 — LLM creates the moving conveyor
**[LLM] → [SYSTEM] [CHEAP-static]**
`create_conveyor(prim_path="/World/ConveyorBelt", position=[...], size=[2.5,0.4,0.05],
surface_velocity=[0.2,0,0])`.
The handler writes a PhysX `physxSurfaceVelocity:surfaceVelocity` attribute on the belt prim. A separate
codegen path `create_conveyor_track` (`robot.py:1854`) tries to enable the `isaacsim.conveyor` extension and
**soft-falls-back** to the `physxSurfaceVelocity` attribute if `OgnIsaacConveyor` is not registered
(`robot.py:1916`). So the belt is a kinematic surface-velocity drag, not a true belt-segment graph — adequate
for the cube to ride, fragile for high-fidelity tracking.

### Step 6 — LLM creates the output bin
**[LLM] → [SYSTEM] [CHEAP-static]**
`create_bin(prim_path="/World/Bin", position=[0.5,-0.3,0.75], size=[0.30,0.30,0.15])` (`handlers/resolve.py`).

### Step 7 — LLM spawns the workpieces (cubes) on the belt
**[LLM] → [SYSTEM] [CHEAP-static]**
Loop: `create_prim(Cube, position=[x,0.4,0.835], size=0.05)` for x∈[-1.6,-1.4,-1.2,-1.0];
`apply_api_schema(PhysicsRigidBodyAPI / CollisionAPI / MassAPI / PhysxRigidBodyAPI)` each;
`bulk_set_attribute(sleepThreshold=0.0)` (prevents the cubes freezing on the belt);
`apply_physics_material("rubber")` (ride the belt without slipping).

### Step 8 — LLM adds the proximity pick sensor
**[LLM] → [SYSTEM] [CHEAP-static]**
`add_proximity_sensor(sensor_path="/World/PickSensor", position=[0.0,0.4,0.835], size=[0.06,0.06,0.06])`
(`handlers/sensors.py`). Gates each pick cycle on cube arrival at x≈0.

### Step 9 — LLM wires the pick-place controller (the load-bearing call)
**[LLM] → [SYSTEM] [CHEAP-static authoring, EXPENSIVE at play]**
```
setup_pick_place_controller(
    robot_path="/World/UR10", robot_family="ur10", target_source="curobo",
    sensor_path="/World/PickSensor", belt_path="/World/ConveyorBelt",
    source_paths=["/World/Cube_1".."Cube_4"], destination_path="/World/Bin",
    drop_target=[0.5,-0.3,0.95],
    planning_obstacles=["/World/Table","/World/ConveyorBelt","/World/Bin"])
```
`handlers/pick_place.py:329-331` accepts `sensor_path` + `belt_path`. The belt-pause is **really
implemented** but via a workaround: writing `physxSurfaceVelocity` from inside a physics callback fails, so
the handler defers the write to a pre-step subscription (`_belt_pause_request` flag →
`_apply_belt_pause_outside_callback` → `_pause_belt`/`_resume_belt`, `pick_place.py:1296-1341`). On
`sensor_path` trigger the controller pauses the belt, cuRobo plans to the now-stationary cube, grips, lifts,
places in the bin, then resumes the belt.

> **Note on the CP-73 design choice:** the template's own comment says the Cortex layer was **removed** —
> `setup_cortex_behavior` + `setup_pick_place_controller` both write joint targets to the same UR10
> articulation → undefined behavior. So this is a "reduced-fidelity realization of #33 (Cortex obstacle
> awareness deferred)" (`CP-73.json` code comment). The operator's mental model ("picks as they pass,
> belt running") is **not** what executes: the belt pauses per pick.

### Step 10 — STATIC-EYES PRE-FILTER runs BEFORE the expensive gate ★
**[SYSTEM] [CHEAP-static]** — `scripts/qa/scene_validate.py`
Builds + settles the scene (no pick-sim), reads ACTUAL post-settle prim geometry, runs three checks whose
math mirrors the controller's own reach gate (`ROBOT_REACH` table, `scene_validate.py:32`,
ur10=**1.30 m**):

1. **REACH** (`:258-285`) — each cube vs nearest arm's reachable shell.
   The conveyor-aware branch `belt_reachable()` (`:173-185`) is the key: a cube at x=-1.6 is **2.0 m+** from
   the UR10 base and would naively flag REACH, but because it sits on a belt whose `surface_velocity`
   forward vector carries it toward the base, `belt_reachable` projects the cube's travel and passes it
   **iff** the closest-approach distance ≤ reach. **This is where the pre-filter catches the classic
   conveyor false-positive before wasting a 180 s sim run.** The belt surface velocity is captured
   pre-settle (`_belt_cap`, `:78-84`) because the controller's pause callback would otherwise zero it during
   the settle play and hide the real belt.
   - z-window: ur10 `ZLO=-0.15` (`:278`) — a top-down UR10 suction arm can't angle far below its mount; the
     cube top at z≈0.835 vs UR10 base z=0.75 gives dz≈+0.085, inside the window. (This is the same
     dz that makes CP-70 pass and unclamped reaches fail.)
2. **TARGET REACH** (`:287-307`) — Bin top at `[0.5,-0.3,0.90]`, distance from UR10 base ≈ 0.60 m ≤ 1.30 →
   place reachable. `belt_delivers()`/`HAS_MOBILE` exceptions don't apply (static bin).
3. **INTERPENETRATION** (`:309-322`) — 4 cubes spawned 0.2 m apart on the belt → no >50% AABB overlap → clean.
4. **SUPPORT** (`:324+`) — each cube rests on the belt top (gap in [-0.02,0.10]) → clean.

**Outcome of static-eyes for CP-73:** geometry **clean** (reach satisfied via belt-carry, target reachable,
no clump, supported). The pre-filter does **not** flag this scene — correctly, because the *failure is
controller-side, not geometric*. This matches the scene-validator sweep finding: "core CP-NN scenes 100%
sound → gate failures are controller-side."

> A *complementary* cheap check, `scripts/qa/reach_validate.py`, runs live-cuRobo IK reachability per pick
> (still no full physics pick). It would confirm the cubes are IK-reachable at their belt-carried pose.

### Step 11 — EXPENSIVE physics gate runs ★
**[SYSTEM] [EXPENSIVE-physics]** — `scripts/qa/gate_one.py` → `simulate_traversal_check`
Builds the canonical, settles, then plays the timeline for `simulate_args.duration_s = 180 s` (CP-73) and
samples cube vs target. **Gate success-criterion** (`handlers/diagnostics.py:3968`, `gate_one.py:79-88`):

> **success = the primary cube (Cube_1) is delivered** — `in_target_xy` (final XY inside Bin bbox) **AND**
> `above_floor` (final Z ≥ target min Z − floor_tol) **AND** `at_rest` (speed < threshold). For multi-run,
> success = `n_ok*2 ≥ n_runs` (majority). Multi-cube templates use the lenient "ANY cube delivered +
> primary upright" criterion per the gate-criterion note.

This is the **outcome** the whole flow is judged on: at least Cube_1 ends up resting inside the Bin while the
belt keeps a non-zero surface velocity at sim-end.

### Step 12 — Actual outcome (honest)
**[SYSTEM] [EXPENSIVE-physics]**
CP-73 `verified_status`: `form-gate ✓; function-gate ✗ (Cortex+conveyor — multi-cube limitation +
belt-pause bug)`. Its failure mode #3 names the root: *"Same UR10 surface-gripper limitation as CP-69 —
function-gate deferred."* So the **realistic outcome is a GATE FAIL / unverified**: the scene builds, the
static-eyes pass, the belt-pause fires, cuRobo plans — but the UR10 `IsaacSurfaceGripper` does not reliably
hold the cube through carry, the documented UR10 conveyor blocker.

> **Grip-integrity caveat (carries over from the UR10 cluster work):** where UR10 picks *do* pass on sibling
> templates, it is via a kinematic-follower suction mount (`pick_place.py:5771,5795,5846`) that is
> **functionally weld-equivalent** (near-zero compliance) — `honest_pass=False` even when `under_target=True`.
> Faithful compliant suction on a moving belt is an open RESEARCH item, not a verified capability here.

---

## 2. Tools needed but MISSING (grep-confirmed)

The operator's literal request — pick **as they pass**, belt **running** — requires runtime vision-tracking
+ predictive intercept (the A108 pattern) or live belt control. Grep over
`service/isaac_assist_service/chat/tools/` confirms these are **not registered tools** (0 hits each):

| Missing tool | Why the flow needs it | grep result |
|---|---|---|
| `deregister_moving_obstacle` | drop a picked/delivered cube from cuRobo's obstacle list between cycles | MISSING |
| `update_moving_obstacle` | refresh a tracked cube's pose each tick (the static registration goes stale) | MISSING |
| `track_object` / `predict_intercept` | per-cycle vision tracking + lead-the-target intercept for belt-RUNNING pick | MISSING |
| `get_object_velocity` / `estimate_belt_velocity` | feed `predicted_x = cube_x + v·t_dive` from measured belt speed | MISSING |
| `pause_conveyor` / `resume_conveyor` / `set_conveyor_velocity` | first-class belt control (today it's an internal `_pause_belt` side-effect of `belt_path`, not an operator-callable tool) | MISSING |
| `wait_for_sensor_trigger` | explicit arrival-gate primitive (today only implicit via `sensor_path`) | MISSING |

**Partial / stub capabilities (exist but do not do what the request implies):**
- `register_moving_obstacle` **exists** (`robot.py:4776`) but only **writes a USD attribute**
  (`curobo:moving_obstacles`); its own docstring says *"Runtime usage requires controller integration that
  reads this attr each tick … (Sprint 3+)"* (`robot.py:4785`) — i.e. the per-tick dynamic-obstacle replan is
  **not wired**. Both moving-pick templates document this as a known gap (register all cubes once, can't
  deregister).
- `vision_detect_objects` / `vision_plan_trajectory` **exist** as handlers (arg models `_models.py:4085-4087`,
  handler `vision.py`) but need a **live Gemini-ER endpoint**; A108 is `function-gate ⏳ (needs live Kit +
  Gemini-ER endpoint)` and there is **no runtime predictive-intercept/visual-servo loop tool** in
  `handlers/*.py` (grep `servo|conveyor_track|predictive` returns only the `create_conveyor_track` codegen,
  not a tracking loop).
- `interpolate_trajectory` **exists** (`robot.py:3477` codegen) but is **vestigial** in the A39 template (its
  return value is not consumed; cuRobo replans independently — `CP-NEW-moving-conveyor-pick.json`
  `verified_status: interpolate_trajectory-vestigial-annotated`).

---

## 3. Summary of marks

| # | Actor | Cost | Action |
|---|---|---|---|
| 1 | USER | CHEAP-static | State the goal |
| 2 | LLM | CHEAP-static | Parse intent → structural features → retrieve CP-73 |
| 3 | LLM→SYS | CHEAP-static | Scene skeleton (light/ground/table/physics-config) |
| 4 | LLM→SYS | CHEAP-static | `robot_wizard` UR10 (avoids wound-start) |
| 5 | LLM→SYS | CHEAP-static | `create_conveyor` (surface-velocity drag) |
| 6 | LLM→SYS | CHEAP-static | `create_bin` |
| 7 | LLM→SYS | CHEAP-static | Spawn 4 cubes + physics APIs + rubber material |
| 8 | LLM→SYS | CHEAP-static | `add_proximity_sensor` arrival gate |
| 9 | LLM→SYS | CHEAP→EXPENSIVE | `setup_pick_place_controller` (belt-pause, cuRobo) |
| 10 | SYSTEM | **CHEAP-static** | **STATIC-EYES pre-filter** (reach via `belt_reachable`, target-reach, interpenetration, support) → CLEAN |
| 11 | SYSTEM | **EXPENSIVE-physics** | **GATE** `simulate_traversal_check` 180 s, criterion = primary cube delivered (in_xy ∧ above_floor ∧ at_rest) |
| 12 | SYSTEM | EXPENSIVE-physics | Outcome: **function-gate ✗** (UR10 surface-gripper limitation; grip weld-equivalent where it passes) |

**Step_count (USER-action steps): 1** (the operator's single natural-language request; all subsequent steps
are LLM/SYSTEM). The LLM emits ~7 tool calls (steps 3–9); the harness runs 2 verification stages (10 cheap,
11 expensive).

**Bottom line:** the static-eyes pre-filter correctly passes CP-73's geometry (the belt-carry reach branch is
exactly the cheap check that prevents a false "out of reach" fail before the 180 s sim). The expensive gate
then exposes the real, controller-side blocker — UR10 suction grip on a (paused) belt — which is the
documented `function-gate ✗`. The operator's literal "as they pass / belt running" intent is **not buildable
as a verified UR10 flow today**: it needs the A108 vision predictive-intercept pattern, which has **no UR10
default** and depends on **6+ missing runtime tools** plus a live Gemini-ER endpoint.
