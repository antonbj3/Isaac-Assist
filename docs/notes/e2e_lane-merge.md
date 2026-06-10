# E2E Trace — `lane-merge` (T3, franka, merge-singulate)

**Persona:** sortation operator
**One-sentence request:** *"two infeed belts merge and singulate parts onto one outfeed"*
**Scenario id:** `lane-merge` · **Tier:** T3 · **Robot:** franka · **Task:** merge-singulate

**Matched template:** `workspace/templates/CP-NEW-y-merge-singulation.json`
(grep for `merge|singulat|lane|infeed` over `workspace/templates/` returns this as the only base FIFO-merge template; `CP-NEW-conveyor-merge-vision-priority.json` is the *priority-ordered* sibling and is **not** the match here — the request says "singulate", not "prioritize red over blue").

**Honesty up front:**
- The template is a **build-spec draft** (`verified_status: "build-spec-2026-05-10; smoke-test ✓ 1/1 (53s)"`). The smoke test only proved the scene *builds and one cube traverses*, not that singulation works.
- The template **openly admits V0 has no singulation logic** (`thoughts[1]`: *"For V0: no actual claim-mutex on merge; cubes physically jam if conflict. Tests merge geometry + physics."*).
- The task verb "**singulate**" therefore is **structurally unimplemented** — the dedicated tools that would enforce one-at-a-time release at the merge **do not exist** (see Tool Gaps). The gate does not measure singulation, so a passing gate here **does not** mean parts were singulated.

---

## Legend
- `[USER]` operator action · `[LLM]` model acting for the user · `[SYSTEM]` service/Kit/gate
- `[CHEAP-static]` deterministic, no physics step (geometry/IK/retrieval) · `[EXPENSIVE-physics]` runs the PhysX/cuRobo sim loop

---

## Numbered narrative

### 1. `[USER]` — issue the request `[CHEAP-static]`
Sortation operator types: *"two infeed belts merge and singulate parts onto one outfeed."*
No prim paths, no robot named, no counts. This is a T3 natural-language ask — the LLM must resolve it to a canonical.

### 2. `[LLM]` — interpret intent and retrieve a template `[CHEAP-static]`
The LLM parses the request to structural intent: `pattern_hint: pick_place`, `topology.y_merge`, `transport.conveyor`, single station, single bin. It queries the template index (`service/isaac_assist_service/chat/tools/template_retriever.py`, `role_index.py`) and ranks `CP-NEW-y-merge-singulation` top on the `isaac:topology.y_merge` + `transport.conveyor` tags (template `intent.structural_tags`).
This is pure retrieval — no Kit, no physics.

### 3. `[LLM]` — bind roles to the operator's request `[CHEAP-static]`
The template's `roles` block is filled from `role_defaults`:
- `primary_robot` → `franka_panda` @ `[0.5,0,0.75]`, quat `[0.7071,0,0,0.7071]` (scenario robot = franka ✓; constraints also allow `ur5e`/`kinova_gen3`).
- `merge_conveyor` → `/World/BeltMerge` @ `[0.05,0.40,0.78]`, size `[0.9,0.5,0.05]`, surface vel `[0.15,0,0]`.
- `primary_destination` → `/World/Bin` @ `[0.5,-0.5,0.75]` (the single "outfeed" bin).
- `pick_sensor` → `/World/PickSensor` @ `[0.4,0.40,0.835]`.
- `workpieces` → 6 cubes (3 left lane `Cube_L1..3`, 3 right lane `Cube_R1..3`); `roles.workpieces` allows `min:2 max:8` via `n_cubes`.
The "two infeed belts" become `/World/BeltLeft` (`y=0.20`, vel `[0.15,+0.035,0]`) and `/World/BeltRight` (`y=0.60`, vel `[0.15,-0.035,0]`), both angling toward the merge centerline `y=0.40`.

### 4. `[LLM]` — emit the build program (the `code_template`) `[CHEAP-static]`
The LLM renders `code_template` with the bound roles into a concrete tool-call sequence. Every tool it calls is a **real, registered handler** (verified by grep):
| Tool (template `tools_used`) | Handler | Exists? |
|---|---|---|
| `create_prim` | `handlers/workflow.py` | ✅ |
| `set_attribute` | `handlers/scene_authoring.py` | ✅ |
| `apply_api_schema` | `handlers/scene_authoring.py` | ✅ |
| `set_physics_scene_config` | `handlers/physics.py` | ✅ |
| `create_conveyor` | `handlers/robot.py:1744` `_gen_create_conveyor` | ✅ |
| `create_bin` | `handlers/_models.py` | ✅ |
| `robot_wizard` | `handlers/robot.py:810` `_gen_robot_wizard` | ✅ |
| `add_proximity_sensor` | `handlers/sensors.py:333` `_gen_add_proximity_sensor` | ✅ |
| `bulk_set_attribute` | `handlers/_models.py` | ✅ |
| `setup_pick_place_controller` | `handlers/pick_place.py:293` `_gen_setup_pick_place_controller` | ✅ |

No invented tools in the build path — the scaffold is sound.

### 5. `[SYSTEM]` — instantiate the canonical into Kit `[CHEAP-static]` (authoring) → `[EXPENSIVE-physics]` (settle)
`service/isaac_assist_service/chat/canonical_instantiator.py::execute_template_canonical` runs the rendered program in the Kit RPC. Authoring the prims (lights, ground, table, 3 conveyors, 6 cubes, bin, sensor, robot) is cheap USD authoring. The crucial details from the build:
- `set_physics_scene_config({enable_gpu_dynamics:False, broadphase_type:"MBP"})` → **CPU determinism** (so the merge outcome is repeatable).
- `robot_wizard(franka_panda, ...)` spawns the arm with a clean home pose (NOT a raw `add_reference`, avoiding the wound-start asset class of UR10 bugs — this is a franka so that root doesn't apply).
- `bulk_set_attribute(... sleepThreshold=0.0)` on all 6 cubes — the documented conveyor-sleep fix so an upstream cube doesn't freeze during a belt-pause.
- `solverPositionIterationCount=16` on the left-lane cubes for contact stability at the junction.
Then `settle_after_canonical` steps physics briefly to let cubes rest on the belts — the first cheap-ish physics touch.

### 6. `[LLM]` — wire the pick-place controller `[CHEAP-static]`
`setup_pick_place_controller(robot_path=/World/Franka, target_source="curobo", sensor_path=/World/PickSensor, belt_path=/World/BeltMerge, source_paths=[all 6 cubes], destination_path=/World/Bin, planning_obstacles=[Table, BeltMerge, Bin])`.
The controller is **belt-aware** (sensor-triggered pick at the merge end) and routes any sensed cube to the single bin. `motion_controllers.verified: []` — **curobo is `untested` on this template** (honest: unverified capability).

### 7. `[SYSTEM]` — STATIC-EYES PRE-FILTER (the cheap gate before the expensive one) `[CHEAP-static]`
Before paying for the 180s sim, the static validator runs — **no physics step**:

- **Tool:** `diagnose_scene_feasibility` (`handlers/diagnostics.py`, args schema `_models.py:368` "PRE-FLIGHT CONSTRAINT VALIDATOR — runs deterministic geometric checks … BEFORE running expensive 60-180s sim"). Wired into the pipeline via `verify_pickplace_pipeline(feasibility=True)` (`_models.py:347`, `diagnostics.py:138`).
- **Standalone mirror:** `scripts/qa/scene_validate.py` (REACH / target-reach / interpenetration / support / instability), with a **belt-aware** reach model (`belt_reachable`, `belt_delivers`) so a cube currently upstream on a moving belt is **not** falsely flagged out-of-reach.

What it checks for THIS scene (Franka base `[0.5,0,0.75]`, `franka_panda` reach = **0.855 m**, `scene_validate.ROBOT_REACH`):
- **Pick zone** `/World/PickSensor` `[0.4,0.40,0.835]` → distance to base = **0.421 m ≤ 0.855** → **REACH-OK**.
- **Closest merge-belt approach** `(0.50,0.40,0.835)` → **0.409 m** → in-envelope; the belt carries cubes from `x=-0.40` (far) into reach, so the belt-aware check passes upstream cubes too.
- **Place / bin** `/World/Bin` `[0.5,-0.5,0.75]` → distance = **0.500 m ≤ 0.855** → **REACH-OK**.
- **Interpenetration / support / instability:** the 6 cubes rest on belt tops (`z=0.835` on belt surface `z≈0.805`); no overlap; bin and table have collision APIs. No static violation.

**What the static-eyes pre-filter CATCHES here:** if the LLM had bound the bin or the merge sensor outside the 0.855 m shell (e.g. dropped the bin at `[0.5,-0.9,...]` → 0.9 m, OUT-OF-REACH), `diagnose_scene_feasibility` flips `pipeline_ok=false` and **the expensive sim never runs** (`feasibility` infeasible "flips pipeline_ok=false BEFORE expensive sim", `_models.py:347`). For the as-authored geometry it **passes** — correctly, the cell is geometrically buildable and reachable.

**What the static-eyes pre-filter CANNOT see (the honest gap):** singulation is a *physics-time, multi-body interaction* at the merge junction (two cubes arriving simultaneously, pushing each other off the belt edge — `failure_modes[2]`). A geometry/IK pre-filter has **no model of dynamic contention**, so it cannot pre-flag the one thing the task verb actually asks for. This is exactly where the cheap gate is blind and only the expensive gate (or a real singulation tool that doesn't exist) could speak.

### 8. `[SYSTEM]` — THE EXPENSIVE FUNCTION-GATE `[EXPENSIVE-physics]`
Authoritative check = `scripts/qa/gate_one.py` → `simulate_traversal_check` (`handlers/diagnostics.py:3920`, `_handle_simulate_traversal_check`), driven by the template's own `simulate_args`:
```
cube_paths = [Cube_L1, Cube_L2, Cube_L3, Cube_R1, Cube_R2, Cube_R3]
target_path = /World/Bin
duration_s  = 180
(no xy_tolerance, no floor_tolerance override, no require_upright)
```
This runs the full 180 s PhysX + cuRobo loop: belts carry cubes through the Y-merge, the sensor fires at the pick zone, the Franka picks whatever arrives and drops to the bin. Single-tenant Kit — must run sequentially (no parallel `simulate_traversal_check`).

### 9. `[SYSTEM]` — GATE SUCCESS-CRITERION / OUTCOME `[EXPENSIVE-physics]`
**Multi-cube mode** (`cube_paths` present, takes precedence over `cube_path`). Per the handler docstring (`diagnostics.py:3920+`): *"Success fires if **ANY cube** reaches the target bbox."* With defaults `floor_tolerance=0.10`, `xy_tolerance=0.0`, `require_upright=False`:

> **PASS ⇔ at least ONE of the 6 cubes lands inside the `/World/Bin` world bbox (within 10 cm floor slack) within 180 s, and is at rest.**

`gate_one.py` prints `GATE success=true/false`. `success=True` ⇒ gate PASS.

**Expected outcome (honest):** the *build* is sound and reach-feasible, so **one cube reaching the bin is plausible → the gate likely reports PASS**. But:
- The gate's **ANY-cube** lenience means it is **satisfied by a single delivery** and **says nothing about singulation** — the exact capability the operator asked for. A scene where two cubes jam and shove a third off the belt (`failure_modes[2]`, that cube is *lost*) can **still PASS** as long as one survivor reaches the bin. This is a known false-positive class for merge/sort tasks (the gate measures delivery, not order/one-at-a-time).
- curobo is `untested` on this template, so a `plan_pose`/IK-context failure at the pick is an open risk that would only surface at this expensive step (post-mortem via `diagnose_pick_execution`, `_models.py:2572`).

---

## Tool Gaps — needed for true "singulate" but DO NOT EXIST
Grep-confirmed missing across `service/isaac_assist_service/chat/tools/` (handlers + schemas):
- `claim_merge_slot` / `merge_arbiter` / `singulation_gate` — **MISSING**. No tool enforces one-cube-at-a-time release at the merge junction.
- `assign_merge_priority` / alternation arbiter — **MISSING**. No FIFO/alternation ordering primitive (the priority *sibling* template fakes ordering by pinning low cubes with `set_linear_velocity` vel=0 — a hold hack, not a singulator, and it's a *different* template).
- `set_belt_pause` / `pause_conveyor` / `stop_conveyor` / `set_conveyor_velocity` / `set_belt_speed` — **MISSING**. No stop-and-go belt-metering tool to gap parts before the merge.
- `release_metering` / `singulate` — **MISSING**.

**Note on `mutex_path`:** `handlers/pick_place.py` (lines 457/503/3161/3653) has a `mutex_path` — but grep confirms it is a **multi-ROBOT claim mutex** (one arm waits while another holds the claim), **not** a per-cube merge singulator. It does not gate belt flow or arbitrate cube arrival order at a junction. So even that nearest-neighbor primitive does not implement the task verb.

**Consequence:** the "singulate" half of `merge-singulate` is **scaffolding only**. The template tests *merge geometry + physics*; achieving real singulation needs at least one of the missing tools above. Honest status: **capability unverified / structurally absent.**

---

## Summary
- **Template:** `CP-NEW-y-merge-singulation.json` (build-spec draft; smoke ✓1/1; singulation explicitly deferred to "V0 no claim-mutex").
- **Build tools:** all 8 exist as real handlers — the scene assembles.
- **Static-eyes pre-filter (`diagnose_scene_feasibility` / `scene_validate.py`):** PASSES — pick 0.421 m, bin 0.500 m, both ≤ Franka 0.855 m; belt-aware reach OK. It *would have caught* an out-of-reach bin/sensor before the 180 s sim, but is structurally blind to merge-junction contention.
- **Expensive gate (`simulate_traversal_check`, 180 s):** **PASS ⇔ ANY of 6 cubes reaches `/World/Bin`.** Likely PASS — but lenient ANY-cube criterion does **not** verify singulation and can pass even when a cube is shoved off the belt and lost.
- **Missing tools:** no merge arbiter / singulation gate / belt-metering / alternation primitive exists. The "singulate" capability is unimplemented.
