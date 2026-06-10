# E2E trace — gravity-dispenser feeder (T3, ur10, dispenser-pick)

**Scenario id:** `gravity-dispenser`
**Persona:** feeder operator
**One-sentence request:** "parts drop from a gravity dispenser and a robot picks them as they land"
**Matched template:** `workspace/templates/CP-NEW-gravity-dispenser-feeder.json`
**Matched via:** `grep -rilE "dispenser|gravity" workspace/templates/` → single live hit `CP-NEW-gravity-dispenser-feeder.json` (plus its `.pre_scene_rewrite_bak`). This is the only gravity-dispenser canonical in the 504-file library.

> **HONESTY HEADER — read before trusting this trace**
> 1. **Robot mismatch.** The scenario asks for **ur10**. The matched template is authored for **Franka** end-to-end: `robot_wizard(robot_name="franka")`, `robot_kind: "franka"` in `verify_args.stages` (line 57), `role_defaults.primary_robot.class="franka"`, and `roles.primary_robot.constraints=["franka_panda","ur5e"]` (line 129) — **ur10 is not even an allowed role constraint.** There is no ur10 variant of this template. A ur10 run is unverified and would require re-authoring the layout (ur10 reach 1.30 vs franka 0.855 → different base placement, different cup-down approach, different grip path).
> 2. **Template is a DRAFT.** `verified_status: "drafted-2026-05-16-A24; form-gate pending"` (line 237). `motion_controllers.verified: []`, `untested: ["curobo"]` (lines 230-235). It has never passed the function gate.
> 3. **Stated success criterion is fiction relative to the real gate.** Template says "8 of 10 parts arrive in bin" (`min_parts_delivered: 8`, line 62; `min_items_delivered: 8`, line 79). The **actual gate** (`simulate_traversal_check`, `diagnostics.py:4446-4449`) for a multi-cube scene scores `success = bool(delivered) and upright_ok` — **ANY ONE** of the 10 items delivered + primary upright. The 8/10 threshold is **not enforced by the code that returns the gate verdict.**
> 4. **Capability gaps.** "as they land" / "vibratory conveyor" / "part-present event" / "singulation" map to tools that **do not exist** (confirmed by grep, see §Tool gaps). The template approximates them with `create_conveyor` + `add_proximity_sensor` + `sensor_gated` controller mode.

Tier classification: **T3** — multi-tool composite (10 declared tools), novel feeder physics (gravity drop + async arrival), sensor-gated control loop. Not atomic (T1), not a simple single-pick (T2).

---

## Cast (grounded)

| Element | Path | Tool | Handler / proof |
|---|---|---|---|
| Gravity dispenser (10× 0.06 m cubes) | `/World/Dispenser` | `create_gravity_dispenser` | `robot.py:4858` `_handle_create_gravity_dispenser` — REAL |
| Infeed conveyor (carries part to sensor) | `/World/InfeedBelt` | `create_conveyor` | `tool_schemas.py:3840` — REAL (but **omitted from `tools_used`** at lines 4-15 — template bug) |
| Singulation proximity sensor | `/World/SingulationSensor` | `add_proximity_sensor` | `sensors.py:333` `_gen_add_proximity_sensor` — REAL trigger-volume (PhysxTriggerAPI + per-step overlap_box) |
| Output bin | `/World/OutputBin` | `create_bin` | REAL |
| Arm | `/World/Franka` (template) / **should be `/World/UR10`** | `robot_wizard` | REAL |
| Controller | sensor_gated loop | `setup_pick_place_controller(target_source="sensor_gated")` | `pick_place.py:532` → `_gen_pick_place_sensor_gated` at `pick_place.py:1696` — REAL |

---

## Numbered narrative — the COMPLETE sequence

Legend: `[USER]` human feeder operator · `[LLM]` model acting for the user · `[SYSTEM]` service/gate/Kit · `[CHEAP-static]` no physics (USD geometry / IK probe / schema) · `[EXPENSIVE-physics]` runs Kit physics steps.

### Phase A — request & retrieval

**1. [USER] [CHEAP-static]** The feeder operator types the request: *"parts drop from a gravity dispenser and a robot picks them as they land."* Mentions a ur10 in their cell. (USER-ACTION STEP 1)

**2. [LLM] [CHEAP-static]** The model parses intent → `pattern_hint: "pick_place"`, structural features `has_gravity_dispenser`, `has_sensor_gate`, `uses_conveyor_transport` (template `intent` block, lines 106-124). Retrieval over the template library matches `CP-NEW-gravity-dispenser-feeder` on the `isaac:feeder.gravity_dispenser` + `isaac:sensor.proximity_singulation` structural tags (lines 116-123).

**3. [LLM] [CHEAP-static]** **First honesty fork.** The template's `roles.primary_robot.constraints` = `["franka_panda","ur5e"]` (line 129). The user said **ur10**, which is NOT in the allowed set. A faithful LLM should surface: *"the only gravity-dispenser canonical is Franka-authored; ur10 is out-of-constraint and unverified."* In practice the role-resolver either (a) substitutes ur10 into `role_defaults.primary_robot` (geometry then wrong — ur10 base at the Franka spot `[0.55,0.40,0.75]` with 1.30 m reach over-reaches the 0.63 m pick) or (b) keeps Franka and ignores the user's robot. Both are degraded. **This trace continues with the template AS WRITTEN (Franka)** and flags the ur10 delta at each geometry step.

### Phase B — scene authoring (the LLM emits tool calls)

The LLM replays the template `code` / `code_template` (lines 17 / 229). Each call below is a discrete LLM action; SYSTEM executes it in Kit.

**4. [USER] [CHEAP-static]** Operator confirms "yes, build it" (single approval of the proposed plan). (USER-ACTION STEP 2)

**5. [LLM]→[SYSTEM] [CHEAP-static]** `create_prim` DomeLight + `set_attribute` intensity 1000; `create_prim` Ground + `apply_api_schema` PhysicsCollisionAPI. Pure USD authoring, no physics.

**6. [LLM]→[SYSTEM] [CHEAP-static]** `set_physics_scene_config({enable_gpu_dynamics:False, broadphase_type:"MBP"})`. CPU MBP chosen to stabilise the gravity drops (template thoughts §5). Config write only.

**7. [LLM]→[SYSTEM] [CHEAP-static]** `create_prim BeltTable` + collision; `create_conveyor /World/InfeedBelt` pos `[0,0,0.78]` size `[0.35,1.5,0.05]` surface_velocity `[0,0.15,0]`. Belt surface lands at z≈0.805 (thoughts §2).

**8. [LLM]→[SYSTEM] [CHEAP-static]** `create_gravity_dispenser(/World/Dispenser, target_xy=[0,-0.55], drop_height=1.45, n_items=10, item_size=0.06)`. Handler `robot.py:4858` authors an UNSCALED `/World/Dispenser` Xform, a visual `/Housing` (no collision), and **spawns the 10 items on a flat XY grid** (`robot.py:4925-4941`, `_cols=ceil(sqrt(10))=4`, spacing `item_size*2`) each with RigidBody+Collision+Mass. **Note the handler's drop_height clamp** (`robot.py:4887`): values < 0.6 snap to 1.1 — here 1.45 passes unchanged. **At authoring time the items have not fallen yet** — they exist at spawn z. This is geometry only → CHEAP.

**9. [LLM]→[SYSTEM] [CHEAP-static]** `add_proximity_sensor(/World/SingulationSensor, position=[0,0.65,0.845], size=[0.38,0.08,0.10], watched_path_pattern="/World/Dispenser")`. Handler `sensors.py:333` creates an invisible trigger Cube (guide purpose) + PhysxTriggerAPI + a per-physics-step overlap_box callback that sets `isaac_sensor:triggered`. **Honesty note:** `watched_path_pattern="/World/Dispenser"` (line 16 of the goal text) — the items are children `/World/Dispenser/Item_*`, so the pattern matches. Template `failure_modes[5]` (line 104) flags exactly this path-pattern risk.

**10. [LLM]→[SYSTEM] [CHEAP-static]** `create_prim RobotTable` + collision; `robot_wizard(robot_name="franka", dest_path="/World/Franka", position=[0.55,0.40,0.75], orientation=[0.707,0,0,0.707])`. **ur10 delta:** if substituted, `robot_wizard("ur10",...)` would spawn a UR10 whose raw asset starts WOUND (per MEMORY: wrist_2≈-298°) and whose cup-down frame needs `_ur10_cupframe_down` handling — none of which this Franka-tuned layout accounts for.

**11. [LLM]→[SYSTEM] [CHEAP-static]** `create_bin(/World/OutputBin, position=[0.55,0.65,0.78], size=[0.25,0.25,0.18])`. (Template `thoughts` §6 and a `failure_modes` entry disagree on bin xy — text says `[0.40,0.40]` but the live `code` uses `[0.55,0.65]`; the executed value is `[0.55,0.65,0.78]`, line 219. Stale-comment drift — flagged.)

**12. [LLM]→[SYSTEM] [CHEAP-static]** `setup_pick_place_controller(robot_path="/World/Franka", target_source="sensor_gated", sensor_path="/World/SingulationSensor", belt_path="/World/InfeedBelt", pick_target=[0,0.65,0.845], drop_target=[0.55,0.65,0.97], home_target=[0.55,0.20,1.05], grip_style="friction", planning_obstacles=[BeltTable,RobotTable,InfeedBelt,OutputBin])`. Dispatcher `pick_place.py:532` routes `mode=="sensor_gated"` → `_gen_pick_place_sensor_gated` (`pick_place.py:1696`), which returns Python source (queued via `queue_exec_patch`) that: runs the belt continuously, waits for the sensor `triggered` attr, pauses the belt, RmpFlow-IK to pick_target, closes gripper (friction), resumes belt, IK to drop_target, releases, returns home, repeats. **Code generation only — no physics yet → CHEAP.**

### Phase C — STATIC EYES pre-filter (cheap, catches problems BEFORE the gate)

This is the load-bearing cost-saver: geometry/IK checks with **no physics stepping**.

**13. [SYSTEM] [CHEAP-static]** `scripts/qa/scene_validate.py` — builds the scene, does a SHORT passive settle, then runs three static checks (`scene_validate.py:7-9`): **REACH** (each pick/place within the arm's reachable shell), **SUPPORT**, **INTERPENETRATION/instability**. Reach shell from `ROBOT_REACH` (`scene_validate.py:32`): `franka=0.855`, **`ur10=1.30`**.
  - *Franka math:* base `[0.55,0.40,0.75]` → pick_target `[0,0.65,0.845]`: planar Δ≈√(0.55²+0.25²)=**0.60 m**, well inside 0.855. drop_target `[0.55,0.65,0.97]`: Δ≈0.25 m. Both PASS reach statically. (Matches template `failure_modes[3]`, line 102.)
  - *ur10 substitution delta:* same targets sit at radius 0.60 m — **inside** 1.30 but now potentially TOO CLOSE / below-base for a cup-down UR10 (the non-convex straight-down reach floor, see `reach_validate.py` caveat). Static reach would likely PASS but is **not predictive** for ur10 cup-down — only the live cuRobo probe is.

**14. [SYSTEM] [CHEAP-static]** `scripts/qa/reach_validate.py` (UR10 cup-down IK probe, only meaningful for ur10) — a single-IK cuRobo probe of each declared pick target with the cup pointing down. Its own header (`reach_validate.py:12-20`) warns: **REACHABLE is necessary, not sufficient**, and it is **stochastic** (Halton seeds) → use N-of-M. For Franka this step is skipped/N-A.
  - **Where the cheap filter EARNS its keep:** the dispenser handler's `drop_height < 0.6 → 1.1` clamp (`robot.py:4887`) plus `reach_validate` together caught the historical CP-71 failure where items spawned at z≈0.15 — far below the arm — and the gate scored 0. The static reach/clamp check rejects "items below the reachable shell" **without paying for a 240 s physics gate.** That same class of bug is the #1 risk here (a mis-passed `drop_height` or a too-tall settled tower → top item out of cup reach).

**15. [SYSTEM] [CHEAP-static]** `scripts/qa/scene_validate.py` interpenetration/instability check — confirms the 10 spawned items are not interpenetrating at spawn (the old CP-71 "crushed-chip clump" bug, fixed by the unscaled-parent rewrite at `robot.py:4890-4896`). Static AABB overlap, no physics.

> **If any static check fails here, the pipeline stops and re-authors (move base / fix drop_height / re-grid items) WITHOUT ever running the expensive gate.** That is the entire point of the pre-filter.

### Phase D — EXPENSIVE physics gate (the outcome)

**16. [SYSTEM] [EXPENSIVE-physics]** `scripts/qa/gate_one.py` builds the canonical, settles, then runs `simulate_traversal_check` with the template's own `simulate_args` (lines 64-82): `target_path=/World/OutputBin`, `cube_paths=[Item_1..Item_10]`, `n_items_total=10`, `min_items_delivered=8`, **`duration_s=240`**, `xy_tolerance=0.13`. This steps Kit physics for up to 240 simulated seconds: gravity drops each part → belt conveys → sensor triggers → arm picks → drops in bin → repeats. **This is the ONLY expensive step** (240 s of dynamics + IK per cycle × up to 10 cycles).

**17. [SYSTEM] [EXPENSIVE-physics]** Gate verdict computed in `diagnostics.py:4413-4449`. For each of the 10 `cube_paths` it checks `in_xy` (within bin AABB ± 0.13), `above_floor`, and `at_rest`; a cube is `delivered` if all three hold (`diagnostics.py:4431`). **Because `len(cube_paths)>1`, the success rule is `success = bool(delivered) and upright_ok`** (`diagnostics.py:4446-4447`) — i.e. **AT LEAST ONE of the 10 parts in the bin, at rest, primary upright.**

---

## THE GATE SUCCESS-CRITERION (the outcome), stated plainly

- **What the code actually enforces (authoritative, `diagnostics.py:4446-4449`):** multi-cube ⇒ **≥1 of the 10 items delivered into `/World/OutputBin` (inside AABB±0.13, above floor, at rest) AND primary item upright.** That is the gate PASS/FAIL the runner reads.
- **What the template CLAIMS (`verify_args.min_parts_delivered=8` line 62; `simulate_args.min_items_delivered=8` line 79; thoughts §8):** 8 of 10. **This threshold is carried in the args but is NOT the rule applied by `simulate_traversal_check`'s returned `success`.** A run delivering 1 part would register the gate as PASS while violating the template's stated 8/10 intent. **Honesty: the 8/10 number is aspirational, not gated.**

### Predicted OUTCOME (honest)

- **As Franka (template as written):** static reach PASSES (§13). The likely physics outcome is a **partial pass** — some parts singulate and reach the bin (gate `success=True` on ≥1), but **full 8/10 is unverified** (`verified_status: form-gate pending`, never run). Dominant physics risks, all pre-flagged in `failure_modes` (lines 98-104): part **bounce** on the 1.45 m drop missing the sensor; belt **overshoot** past the y=0.65 sensor before the pick cycle completes; **double-dispense** racing the gate; friction-grip flakiness (`grip_style="friction"`, the honest-but-flaky path per `pick_place.py` docstring).
- **As ur10 (the requested robot):** **unverified and likely FAIL or false-pass.** No ur10 layout exists; the cup-down approach, wound-start asset, and grip path are untuned for this scene. `reach_validate` would gate the picks but its verdict is stochastic and "necessary not sufficient." This is an **open re-authoring task, not a runnable canonical.**

---

## Tool gaps — capabilities the request implies that DO NOT EXIST

Confirmed missing via `grep -rln '"<name>"' service/.../tools/` (0 registered-schema hits each):

| Implied by request | Missing tool (0 hits) | Approximated by |
|---|---|---|
| "vibratory conveyor" (template thoughts say vibratory) | `create_vibratory_conveyor`, `add_vibratory_feeder` | plain `create_conveyor` (constant surface_velocity, no vibration) |
| "picks them **as they land**" (true async catch) | `wait_for_part`, `detect_part_landed`, `async_arrival_source` | `sensor_gated` belt-pause loop — robot picks at a FIXED station after the part is carried there, NOT a true land-and-catch |
| singulation as a first-class op | `create_singulator`, `singulation_gate` | belt + proximity sensor + `belt_path` pause |
| part-present **event** primitive | `add_part_present_event` | `add_proximity_sensor` binary `triggered` attr (polled per physics step) |
| bulk hopper | `create_hopper` | `create_gravity_dispenser` (pre-spawned stacked/grid cubes) |

**Also note:** `create_conveyor` IS used in the executed `code` but is **absent from the template's `tools_used` array** (lines 4-15) — a template-manifest bug. And `create_gravity_dispenser` is "first use in library" per the goal (line 3) — this is the only template exercising it, so its multi-item delivery path is **thinly tested**.

---

## Where the cheap filter beats the expensive gate (summary)

- **Static reach (`scene_validate.py` REACH, §13)** rejects pick/place targets outside the arm shell — for ~milliseconds of geometry math — before paying for a **240 s** physics gate.
- **`drop_height` clamp (`robot.py:4887`) + reach probe** catch the "items spawn below the reachable shell" class (the CP-71 root) statically.
- **Interpenetration check (§15)** catches crushed/clumped spawns statically (the other CP-71 root).
- Only after all three pass does Phase D spend the expensive `simulate_traversal_check` budget. The honest verdict for THIS scenario: **template is a Franka draft that has never passed the form gate, the requested ur10 has no verified layout, the "8/10" success number is not what the gate enforces (it enforces ≥1), and the core "land-and-catch / vibratory / singulation" verbs map to tools that do not exist.**
