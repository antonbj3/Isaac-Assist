# E2E trace — `dual-arm-handoff` (T5, dual-franka, task=handoff)

**Persona:** assembly cell operator
**One-sentence request:** *"Franka A picks a part and hands it to Franka B which places it"*
**Scenario id:** `dual-arm-handoff`

## Template match (grounding)

`grep -rl -i "handoff" workspace/templates/` + goal inspection resolves the request to a single
exact template:

- **`workspace/templates/CP-51.json`** — goal (line 27):
  *"Build a robot-to-robot handoff station: 2 Frankas, robot A picks cubes from conveyor + drops at
  handoff station, robot B picks from handoff + drops in bin. Uses setup_robot_handoff_signal to
  define the handoff position. Realizes research scenario #11 'Fixed-Point Robot-to-Robot Handoff'."*
- `structural_tags` (lines 16-25): `isaac:topology.handoff_station`, `isaac:topology.multi_robot`,
  `isaac:coordination.handoff_signal`, `isaac:robot.franka_panda`, `isaac:n_stations.2`.
- `extends: "CP-02"` (single-robot belt relay → two-robot handoff).

**Honesty flags on this template (read before trusting the trace):**
- `verified_status` (line 90): **`draft; passes=12 n=27 wilson_lower=0.2759; was form-gate-pending;
  demoted 2026-05-15`** — i.e. it passes the function-gate ~44% of runs (12/27), 95% Wilson lower
  bound 0.28. NOT a stable canonical.
- `migration_deferred.reason = "draft"` (line 146): *"handoff role type not yet in schema; zero QA
  runs"* for the migrated form.
- `diagnose_args.has_mutex = false` (line 116): no runtime mutual exclusion.
- `extension_notes` (line 83): *"Runtime claim coordination NOT implemented — robots may race; future
  work needs setup_robot_claim_mutex + controller hooks."*
- **Internal contradiction in the template itself:** the executed `code` (line 43) puts FrankaB at
  `[0.5, -0.2, 0.75]`, but `thoughts` (line 42), `failure_modes` (lines 86-87) and `diagnose_args`
  (lines 107-112) all reason about FrankaB at `[0.7, 0, 0.75]`. The reach analysis in §6 below is
  done against the *as-coded* base (the one that actually instantiates).

---

## Legend
`[USER]` / `[LLM]` / `[SYSTEM]` = actor. `[CHEAP-static]` = USD/geometry read, no physics step.
`[EXPENSIVE-physics]` = plays the timeline / steps PhysX (the slow path; Kit is single-tenant —
see MEMORY: *Kit RPC is single-tenant*).

---

## Numbered narrative

### 1. [USER] [CHEAP-static] — Operator states the goal
The assembly-cell operator types: *"Franka A picks a part and hands it to Franka B which places it."*
No coordinates, no asset paths, no reach numbers — natural language only. This is one user-action step.

### 2. [LLM] [CHEAP-static] — Intent → pattern + structural features
The LLM parses the request into the intent shape that CP-51 encodes (`intent.structural_features`,
lines 4-15): `pattern_hint = "pick_place"`, `n_robot_stations = 2`, `n_handoffs = 1`,
`destination_kind = "single_bin"`, `is_serial_pipeline = true`, `has_handoff_signals = true`,
`handoff_signals_advisory_only = true`, `n_workpieces = 1`. The retrieval layer matches this to
`CP-51` (nearest canonical). The operator does nothing here.

### 3. [USER] [CHEAP-static] — Operator confirms / accepts the proposed cell
The operator accepts "two Frankas + conveyor + handoff marker + bin" (or supplies a tweak, e.g.
"part starts on the left conveyor"). Second user-action step. From here the LLM executes the
template's `code` block (line 43) as a tool sequence.

### 4. [LLM]→[SYSTEM] [CHEAP-static] — Build the static scene (no physics steps yet)
The LLM issues the tool calls from CP-51 `code`. Every one resolves to a real handler (grep-confirmed):
- `create_prim` (×N), `set_attribute`, `apply_api_schema`, `bulk_set_attribute`
  → `handlers/robot.py`, `handlers/_models.py`.
- `set_physics_scene_config(config={enable_gpu_dynamics:False, broadphase:"MBP"})`
  → `handlers/_models.py`. *Configures* PhysX; does not step it.
- `robot_wizard(robot_name="franka_panda", dest_path="/World/FrankaA", position=[-0.7,0,0.75], …)`
  and again for `/World/FrankaB` at `[0.5,-0.2,0.75]`
  → `handlers/robot.py`. (MEMORY: robot_wizard spawns the arm in a clean HOME pose, avoiding the
  wound-start asset bug.)
- `create_conveyor(/World/ConveyorBelt, pos=[-0.7,0.4,0.78], size=[3,0.4,0.05], surface_velocity=[0.2,0,0])`
  → `handlers/resolve.py`.
- `create_prim(/World/Cube_1, pos=[-2.0,0.4,0.835], size=0.05)` + rigid-body/collision/mass APIs +
  `apply_physics_material(material="rubber")` → `handlers/physics.py`.
- `create_bin(/World/Bin, pos=[0.7,-0.5,0.75], size=[0.3,0.3,0.15])` → `handlers/resolve.py`.
- `add_proximity_sensor(/World/SensorA …)`, `add_proximity_sensor(/World/SensorB …)`
  → `handlers/sensors.py`.

All `[CHEAP-static]`: prims, schemas, attributes — geometry only.

### 5. [LLM]→[SYSTEM] [CHEAP-static] — Create the handoff station (PASSIVE marker)
`setup_robot_handoff_signal(handoff_path="/World/Handoff", position=[0,-0.3,0.825],
robot_a="/World/FrankaA", robot_b="/World/FrankaB")`
→ `_handle_setup_robot_handoff_signal`, `handlers/robot.py:6037`.
This **only writes string/state attributes** on a marker prim (`diagnostics`: lines 6043-6047):
`handoff:state` (`idle`/`placed`/`picked`), `handoff:current_cube`, `handoff:position`,
`handoff:robot_a`, `handoff:robot_b`. **It installs no controller and no runtime sequencing.** The
handoff is advisory metadata, exactly as `intent.handoff_signals_advisory_only = true` (line 12)
declares. **This is the central capability gap of the scenario** (see §11).

### 6. [LLM]→[SYSTEM] [CHEAP-static] — Install the two pick-place controllers
- FrankaA: `setup_pick_place_controller(robot_path="/World/FrankaA", target_source="curobo",
  sensor_path="/World/SensorA", belt_path="/World/ConveyorBelt", source_paths=["/World/Cube_1"],
  destination_path="/World/Handoff", drop_target=[0,-0.3,0.825],
  planning_obstacles=["/World/Table","/World/ConveyorBelt","/World/Handoff","/World/Bin"])`
- FrankaB: same tool, `robot_path="/World/FrankaB"`, `sensor_path="/World/SensorB"`,
  `source_paths=["/World/Cube_1"]`, `destination_path="/World/Bin"`, `drop_target=[0.7,-0.5,0.85]`.

→ `_handle_setup_pick_place_controller` registers in `handlers/resolve.py`; the per-robot tick
logic generates in `handlers/pick_place.py` (`_gen_setup_pick_place_controller`, line 293; builtin
dispatch line 909). Each controller subscribes its own per-robot tick (`_curobo_pp_sub_<tag>`).
**Neither call passes `mutex_path`** — the controller *supports* `mutex_path`
(`pick_place.py:457,503`) but CP-51 omits it. So both controllers target the *same cube*
`/World/Cube_1` with no claim arbitration → the documented race (`failure_modes[0]`, line 85). The
only thing keeping them apart is the spatial separation of the two proximity sensors (SensorA at
x=-0.3, SensorB at x=0/handoff): A fires while the cube is on the belt, B fires once it is at the
handoff marker. This is geometric luck, not coordination.

### 7. [LLM]→[SYSTEM] [CHEAP-static] **STATIC-EYES PRE-FILTER #1 — per-stage reach + handoff continuity**
Before paying for physics, the LLM runs `verify_pickplace_pipeline` with CP-51's own
`verify_args.stages` (lines 60-76):
- stage 0 → FrankaA: pick `/World/ConveyorBelt`, place `/World/Handoff`
- stage 1 → FrankaB: pick `/World/Handoff`, place `/World/Bin`

→ `_handle_verify_pickplace_pipeline`, `diagnostics.py:5239`. Per stage it reads world bboxes,
computes nearest-point-on-bbox distance from each robot base, and compares to
`_ROBOT_REACH_M["franka_panda"] = 0.855` (`handlers/resolve.py`; mirrored in
`scripts/qa/scene_validate.py:31`). It also runs the **handoff-continuity check**
(`diagnostics.py` ~line 5462-5480): the gap from stage 0's *place* point to stage 1's *pick* point,
and — if that gap is bridged by a moving belt — whether an active `PhysxSurfaceVelocityAPI`
conveyor spans it.

Analytic distances (computed cheaply from the *as-coded* geometry, no Kit):

| stage | leg | from | to | dist (m) | reach 0.855 |
|---|---|---|---|---|---|
| 0 | A pick | base [-0.7,0,0.75] | belt closest-approach (cube travels in on y=0.4) | 0.41 | OK |
| 0 | A place | base [-0.7,0,0.75] | Handoff [0,-0.3,0.825] | 0.77 | OK |
| 1 | B pick | base [0.5,-0.2,0.75] | Handoff [0,-0.3,0.825] | 0.52 | OK |
| 1 | B place | base [0.5,-0.2,0.75] | Bin [0.7,-0.5,0.75] | 0.36 | OK |
| — | handoff continuity | stage0.place `/World/Handoff` | stage1.pick `/World/Handoff` | 0.00 | OK (same prim) |

**Result: this static pre-filter PASSES for the as-coded scene.** The handoff is a *shared single
prim* (`/World/Handoff`), so place→pick continuity is trivially zero-gap — exactly the case the
pre-filter is built to validate. The `failure_modes` warning *"Bin at 0.99m, at reach LIMIT, may
fail planning"* (line 87) is **stale**: it was computed for FrankaB at base `[0.7,0]`; the executed
code uses `[0.5,-0.2]`, where B→Bin is only 0.36 m. The static-eyes pass is honest here, but it can
*only* see reach/continuity — it cannot see that there is no runtime arbitration of the shared cube
(that is a control-flow property, invisible to a geometry read).

### 8. [LLM]→[SYSTEM] [CHEAP-static] **STATIC-EYES PRE-FILTER #2 — scene_validate (reach / interpenetration / support / instability)**
`scripts/qa/scene_validate.py` runs 5 geometry checks after a ~2.5 s *passive* settle with the arms
parked (this settle plays the timeline but the arms don't move — it is the cheapest physics touch,
used only to let the cube rest on the belt; classed `[CHEAP-static]` relative to the full gate):
- **REACH** (line 280-285): each declared pick within the nearest arm's reachable shell; belt-borne
  cubes get the `belt_reachable` closest-approach exception (line 173).
- **TARGET_REACH** (line 305): the place target (`/World/Bin`) within the *nearest* robot's shell —
  here FrankaB, 0.36 m, OK.
- **INTERPENETRATION** (line 309): only one workpiece (`n_workpieces=1`) → trivially clean.
- **SUPPORT** (line 324): Cube_1 must rest on a surface (belt top) — OK.
- **PHYSICS_INSTABILITY** (line 255): no spawn-overlap ejection expected.

**Result: `VERDICT CLEAN` expected** for CP-51's as-coded geometry. NOTE the blind spot:
`scene_validate.py` only reads `simulate_args` (`cube_path` + `target_path=/World/Bin`). It never
sees `/World/Handoff` as an intermediate target, and it `nearest_robot()`-attributes the Bin to
FrankaB only. So the *intermediate* leg (A→Handoff) is validated by pre-filter #1 (stages) but NOT
by #2. Neither static pass detects the race / no-arbitration problem.

### 9. [LLM]→[SYSTEM] [EXPENSIVE-physics] — Settle, then play the cell
`settle_after_canonical(tpl)` then the controllers tick. This is the first heavy step: PhysX runs,
cuRobo plans (`target_source="curobo"`), the belt carries `Cube_1` from x=-2.0 toward FrankaA's
SensorA zone. FrankaA picks, transits, drops at `/World/Handoff` `[0,-0.3,0.825]`. The cube now sits
at the marker; FrankaB's SensorB fires; FrankaB picks from the handoff and drops toward
`/World/Bin`. `[EXPENSIVE-physics]` — single-tenant Kit, ~120 s sim (`simulate_args.duration_s=120`).
Failure surface here (from `failure_modes`, lines 84-88 + the draft pass-rate): cuRobo plan failures,
the unarbitrated race (both controllers may claim Cube_1 in the same window), grip not latching, or
the cube tipping at the handoff drop.

### 10. [SYSTEM]→[LLM] [EXPENSIVE-physics] **THE GATE — `simulate_traversal_check` (the OUTCOME)**
Run via `scripts/qa/gate_one.py CP-51`, which calls `simulate_traversal_check` with CP-51's own
`simulate_args`: `cube_path="/World/Cube_1"`, `target_path="/World/Bin"`, `duration_s=120`
(`gate_one.py:71-79`). Handler: `_handle_simulate_traversal_check`, `diagnostics.py:3920`.

**Gate success-criterion (the outcome).** CP-51 has **one** workpiece, so the single-cube branch
fires (`diagnostics.py:4446-4449`):

```python
if len(cube_paths) > 1:
    success = bool(delivered) and upright_ok          # multi-cube: ANY cube in target
else:
    success = bool(in_xy and above_floor and at_rest and upright_ok)   # CP-51 path
```
where (lines 4436-4444): `in_xy` = Cube_1 final XY inside the `/World/Bin` bbox (± `xy_tol`);
`above_floor` = final z ≥ bin_min_z − `floor_tol`; `at_rest` = speed < `rest_speed`;
`upright_ok` = True (CP-51 sets no `require_upright`). **PASS ⇔ `Cube_1` ends up resting inside the
`/World/Bin` bbox and is not moving.** `gate_one.py` prints `GATE success=True/False`.

**Honest measured outcome:** `verified_runs` (lines 136-144) = **12 PASS / 27 runs, Wilson lower
0.276** → roughly a coin-flip-down gate. Status `draft`, demoted 2026-05-15. So the *expected*
outcome on any single run is **PASS ~44% of the time, FAIL ~56%**, dominated by the unarbitrated
race + cuRobo plan flakiness on the two-arm pipeline.

### 11. [SYSTEM]→[LLM] [EXPENSIVE-physics] — What the gate CANNOT see (critical honesty point)
The gate is **robot-agnostic and leg-agnostic**: it tracks only `Cube_1`'s final position vs the
`/World/Bin` bbox. It does **not** verify that the handoff happened. A run where FrankaA reaches
past the marker and drops `Cube_1` straight into the Bin (no FrankaB involvement), or where FrankaB
alone grabs the cube off the belt, would **score the identical PASS**. There is no per-robot
delivery attribution and no `handoff:state` transition assertion in `simulate_traversal_check`
(grep of `diagnostics.py` for `delivered_by` / `per_robot` / `leg` → none). So a green gate on CP-51
does **not** prove "A handed to B" — only "the cube reached the bin."

---

## Tools needed but MISSING (grep-confirmed absent in `service/isaac_assist_service/`)

The scenario *as the operator means it* ("A **hands it to** B") needs runtime two-arm
coordination and handoff-aware verification. None of these exist:

| missing tool | what the scenario needs it for | grep |
|---|---|---|
| `setup_robot_handoff_controller` / `enforce_handoff_sequence` | runtime "A finishes place → B may pick" gating; today `setup_robot_handoff_signal` writes passive `handoff:state` attrs that no controller reads | MISSING |
| `verify_handoff_pipeline` / `simulate_handoff_check` | a gate that asserts the cube actually transited A→Handoff→B→Bin (handoff:state idle→placed→picked) and was delivered *by FrankaB* | MISSING |
| `diagnose_handoff_execution` | localize a failed handoff (did A reach the marker? did B claim before A released? did the cube tip at the marker?) | MISSING |
| `setup_dual_arm_coordination` / `bimanual_coordinate` / `wait_for_robot_done` | mutual-exclusion / barrier so the two PP controllers don't race the shared `Cube_1` (CP-51 passes no `mutex_path`; `setup_robot_claim_mutex` exists but is NOT wired into CP-51 — `has_mutex=false`) | MISSING |

Existing-but-unused lever: `setup_robot_claim_mutex` (`handlers/_models.py`) is implemented and the
PP controller accepts `mutex_path` (`pick_place.py:457,503`) — wiring it into CP-51 is the
`extension_notes` "future work" and would likely lift the 12/27 pass rate, but it is **not present
in this template's `code`**.

False-friend (looks relevant, is not): `compliance.py` `compliance_handoff_at` — that is a
rigid→compliant *force-control trajectory* fraction, unrelated to robot-to-robot handoff.

---

## Summary

- **Template:** `workspace/templates/CP-51.json` (exact match; **draft**, 12/27 gate pass).
- **User-action steps:** 3 (state goal → confirm cell → accept run). Steps 4-11 are LLM/SYSTEM.
- **Static-eyes catches before the expensive gate:** per-stage reach + handoff continuity
  (`verify_pickplace_pipeline`, `diagnostics.py:5239`) and `scene_validate.py` (5 geometry checks) —
  both PASS for the as-coded geometry; they would have caught a too-far handoff/bin or a floating
  cube *without paying for physics*, but they are structurally blind to the no-arbitration race.
- **Gate / outcome:** `simulate_traversal_check` (`diagnostics.py:3920`), single-cube criterion
  `success = in_xy AND above_floor AND at_rest AND upright_ok` (line 4449) → **PASS ⇔ Cube_1 rests
  inside `/World/Bin`**. Robot-agnostic: it does NOT prove the handoff occurred.
- **Honest gaps:** (1) handoff is a passive metadata marker, no runtime sequencing; (2) two
  controllers race the same cube with no mutex; (3) no handoff-aware verifier exists; (4) the gate
  cannot attribute delivery to FrankaB; (5) the template's own FrankaB base coords contradict between
  `code` and `thoughts`/`failure_modes`.
