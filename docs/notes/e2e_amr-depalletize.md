# E2E trace — `amr-depalletize` (T6, carter+franka, mobile-manip)

> Persona: **AMR logistics coordinator.**
> One-sentence request: *"drive the Carter AMR to the cell, then an arm takes 3 boxes off the pallet it carried"*
>
> This document traces the COMPLETE sequence of actions — user, LLM, and system —
> required to take this request to a graded outcome in Isaac Assist, grounded in the
> real templates / handlers / gate. Each step is tagged
> `[USER]` / `[LLM]` / `[SYSTEM]` and `[CHEAP-static]` / `[EXPENSIVE-physics]`.

---

## 0. Template match (what the retriever lands on)

The request is a two-phase **mobile-manipulation** task: (a) a wheeled robot brings a
loaded pallet to a cell, then (b) a fixed arm depalletizes 3 boxes. No single canonical
is named `amr-depalletize`; the retriever scores three candidates:

| Template | file | why it (mis)matches |
|---|---|---|
| **`CP-NEW-forklift-handoff-arm`** | `workspace/templates/CP-NEW-forklift-handoff-arm.json` | **BEST MATCH.** wheeled-robot proxy carries a pallet of **3** workpiece cubes to a handoff zone, handshake gates a **Franka depalletize → outfeed**, then the wheeled robot navigates away. Its `forklift` role explicitly lists `"carter"` as an accepted constraint (`:177`). |
| `CP-NEW-vision-depalletize` | `workspace/templates/CP-NEW-vision-depalletize.json` | depalletize of a 2×3 box grid, BUT **static** pallet at a fixed pose, **no mobile robot, no Carter, no drive leg** — vision-guided picks only. |
| `CP-NEW-cart-handoff-amr` | `workspace/templates/CP-NEW-cart-handoff-amr.json` | arm RELEASES a cart onto an AMR that DEPARTS (`pattern_hint=navigate`); inverse topology, single cart, no depalletize. |

**Decision: `CP-NEW-forklift-handoff-arm` is the template match.** The persona says
"Carter AMR"; the LLM resolves `carter` into the template's `forklift` role
(role constraint set: `["wheeled_robot","forklift","jetbot","carter"]`, line 172-178).

### Honesty flags carried by the matched template (read these first)

The matched canonical is **`drafted`, function-gate ⏳ (never passed)** —
`verified_status: "drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳; …"`
(`CP-NEW-forklift-handoff-arm.json:137`). Specifically:

1. **The "drive to the cell" leg the persona asked for is NOT simulated.** The template's
   own design note (`:23`) says: *"the forklift starts already AT the handoff zone in this
   canonical to keep the canonical short; the navigate-back-to-depot at the end demonstrates
   the navigate axis."* So the Carter spawns **at** the cell at build time; the only
   `navigate_to` call drives it **away** to the depot AFTER the depalletize. The persona's
   primary verb ("drive the Carter to the cell") is **cosmetic / unmodeled**.
2. **"the pallet it carried" is a static co-placement, not a carried load.** A
   differential-drive proxy has no fork-lift prismatic joint; the pallet rides by friction
   above a dummy `/World/Forklift/Platform` Xform (`:22`, failure_mode `:129`). There is no
   FixedJoint binding the pallet to the AMR.
3. **Carter is a proxy shape, not a Carter mesh.** `create_wheeled_robot` at an empty path
   synthesizes a Jetbot-like primitive; the Nucleus forklift/Carter mesh is a
   `nucleus_only_asset` blocker (failure_mode `:135`).
4. **Far box is at the edge of / outside Franka reach.** `/World/Item_3` at x=1.10 m exceeds
   the Franka 0.85 m nominal reach (failure_mode `:130`). This is exactly what the cheap
   static pre-filter should catch (see Step 9).

---

## 1. Numbered narrative

### Phase A — Request intake & planning

**Step 1 — [USER] [CHEAP-static]**
User (logistics coordinator) types the one-sentence request into the chat:
*"drive the Carter AMR to the cell, then an arm takes 3 boxes off the pallet it carried."*

**Step 2 — [SYSTEM] [CHEAP-static]**
The chat service ingests the turn, runs retrieval over `workspace/templates/*`, and surfaces
the three candidates above. `resolve.py` role-resolution maps the spoken nouns to roles:
`Carter → forklift` role, `arm → static_arm` (franka), `pallet → pallet`,
`3 boxes → workpieces` (`min:1,max:6`, `param_name:"n_items"`). Top hit:
`CP-NEW-forklift-handoff-arm`.

**Step 3 — [LLM] [CHEAP-static]**
The LLM reads the template `goal` + `thoughts` and forms a plan. It must reconcile two gaps
against the request: (i) the persona wants the Carter to **drive in** (template starts it
parked at the cell), (ii) the persona names **Carter** specifically (template default class is
the generic `wheeled_robot` proxy). The LLM decides to instantiate the template, set the
forklift class to `carter`, and ADD a drive-in leg — surfacing the first missing-capability
problems (Step 4).

**Step 4 — [LLM] [CHEAP-static] — TOOL GAPS surfaced at plan time**
To honor "drive the Carter **to** the cell carrying the pallet," the LLM looks for tools that
do not exist (confirmed absent by grep over `service/.../chat/tools/`):
  - `attach_payload` / `load_pallet` / `attach_to_amr` / `carry_payload` — **MISSING.** No tool
    binds a pallet as a rideable load on a mobile base. Closest available primitive is
    `create_articulated_joint(joint_type="fixed", …)` (`_models.py:4110`), which the LLM *could*
    hand-wire as a FixedJoint pallet↔Carter — but the template does not, and the gate never
    checks it.
  - `simulate_navigation_check` / `verify_amr_at_goal` / `verify_nav_goal` — **MISSING.** There
    is **no navigation function-gate.** The only graders are `simulate_traversal_check`,
    `verify_pickplace_pipeline`, `verify_import` (`_models.py`). The drive-in/out legs can only
    be spot-checked with `get_world_transform` (a manual ±5 cm read, NOT enforced).
  - `setup_mobile_manipulator` / `dock_amr` / `compose_templates` / `chain_canonical` /
    `multi_stage_gate` — **MISSING.** There is no first-class mobile-manipulation composition,
    no docking primitive, and **no multi-stage gate** that could score "navigate THEN
    depalletize" as one outcome. The two phases cannot be graded together.
  - `wait_for_handoff_state` / `poll_attribute` — **MISSING.** The handoff handshake
    (`handoff:state idle→placed→complete`) is toggled **unconditionally** by `set_attribute`;
    nothing polls/blocks on it. A real controller would await `state=='placed'` before
    depalletizing and `state=='complete'` before departing (failure_mode `:132`).

The LLM proceeds with the template as-is (it is the only path that reaches a gate at all),
and notes the unmodeled drive-in leg in its reasoning.

### Phase B — Scene build (CHEAP, static authoring; no physics stepping)

`execute_template_canonical(tpl)` runs the template `code`. Each tool below is a code-gen /
authoring call — **static, no timeline play**.

**Step 5 — [SYSTEM]/[LLM] [CHEAP-static] — world skeleton**
`create_prim` DomeLight + Ground + Table; `apply_api_schema` PhysicsCollisionAPI;
`set_physics_scene_config({"enable_gpu_dynamics": False, "broadphase_type": "MBP"})` — CPU
dynamics for determinism (`code` lines, template `:30`).

**Step 6 — [SYSTEM] [CHEAP-static] — spawn the Franka arm**
`robot_wizard(robot_name="franka", dest_path="/World/Franka", position=[0,0,0.75])`.
Handler: `handlers/robot.py:_gen_robot_wizard` (`:810`), registry
`handlers/_shared.py:_ROBOT_WIZARD_REGISTRY["franka"]` → `franka_panda`
(`:155`, home_joints + gripper profile). Arm spawns posed at home on a 0.75 m table.

**Step 7 — [SYSTEM] [CHEAP-static] — spawn the Carter proxy**
`create_wheeled_robot(robot_path="/World/Forklift", drive_type="differential",
wheel_radius=0.05, wheel_base=0.20)`. Handler:
`handlers/robot.py:_gen_create_wheeled_robot` (`:1517`) — builds a `DifferentialController`
+ `drive()` clamp helper around `isaacsim.robot.wheeled_robots.WheeledRobot`.
**Caveat:** this only creates a *controller* over an articulation assumed to exist at the
path; at an empty path Kit synthesizes a Jetbot-like primitive — **not** the Carter mesh
(failure_mode `:135`). If the LLM instead routes Carter through `robot_wizard(robot_name="carter")`,
the registry resolves `carter → nova_carter`, `robot_type:"mobile"`
(`_shared.py:246, 211-215`) and loads `nova_carter.usd` (Nucleus). Either way the
"Carter at the cell" pose is authored by `set_attribute("xformOp:translate",[0.55,0,0.05])`
— i.e. the Carter is **placed at the cell**, it does not drive there.

**Step 8 — [SYSTEM] [CHEAP-static] — nav stack, pallet, 3 boxes, outfeed, depot, handoff**
- `setup_nav_robot("/World/Forklift", "/forklift/cmd_vel", "/forklift/odom")`
  (`handlers/robot.py:_handle_setup_nav_robot` `:6780`).
- `create_prim("/World/Forklift/Platform", Xform, z=0.45)` — dummy raised forks.
- `create_prim("/World/Pallet", Cube, [0.55,0,0.475])` + PhysicsCollisionAPI. **Static
  co-placement above the platform — friction-only, no FixedJoint** (the carried-load fiction).
- 3 workpieces `/World/Item_1..3` at x∈{0.45,0.55,0.65} world (template `code`) — note the
  `code` block and `role_defaults`/`thoughts` disagree on the exact x offsets (`thoughts` says
  world {0.90,1.00,1.10}); the executed `code` uses {0.45,0.55,0.65}. Each gets
  RigidBody/Collision/Mass/PhysxRigidBody APIs.
- `create_prim("/World/Outfeed", Cube, [0,-0.50,0.78])` — drop fixture (a static cube, NOT a
  moving conveyor; failure_mode `:134`).
- `create_prim("/World/Depot", Cube, [-1.0,0,0.025])` — return pose marker.
- `setup_robot_handoff_signal("/World/HandoffMarker", robot_a=Forklift, robot_b=Franka)`
  then `set_attribute(handoff:state="placed")` — **unconditional toggle**, the
  "pallet is ready" signal (no polling host; Step 4 gap).
- `prim_exists("/World/Forklift")` + `get_world_transform("/World/Pallet")` — cheap
  existence/pose snapshots.

### Phase C — Static pre-filter (the CHEAP eyes, BEFORE the expensive gate)

**Step 9 — [LLM]/[SYSTEM] [CHEAP-static] — `diagnose_scene_feasibility` (NO physics)**
This is the **static-eyes pre-filter**. It runs deterministic geometric checks on the *built*
scene to predict whether `simulate_traversal_check` would pass, without paying for the
60–240 s sim:
> *"PRE-FLIGHT CONSTRAINT VALIDATOR — runs deterministic geometric checks on a built scene
> to predict whether simulate_traversal_check would succeed, BEFORE running expensive
> 60-180s sim."* — `handlers/_models.py:368` (`DiagnoseSceneFeasibilityArgs`).

Called from the template's `diagnose_args` (`:110`):
`robot_path=/World/Franka, robot_base=[0,0,0.75],
obstacles=[/World/Pallet,/World/Forklift,/World/Outfeed]`. It does **IK-reach** on the pick
poses and **path-clearance** against the obstacle set (`handlers/diagnostics.py:138-169`,
verdicts `feasible` / `infeasible` / `overconstrained`).

**What it catches here (cheaply, the whole point):** the depalletize pick of the FAR box.
Per failure_mode `:130`, `/World/Item_3` sits ~1.10 m from the Franka base (per `thoughts`
geometry), beyond the **Franka 0.855 m reach** (`scripts/qa/scene_validate.py:ROBOT_REACH`
`franka_panda=0.855`; mirrors the controller's own reach gate). The pre-filter returns
`infeasible`/`overconstrained` for that stage → the LLM is told **before** spending 240 s of
physics that the far box is unreachable. Cheap fix the LLM applies: move the pallet closer
(x 1.0→0.85) or swap to a UR10 (reach 1.30 m) — both named in failure_mode `:130`.

A complementary offline static check is `scripts/qa/scene_validate.py` (REACH /
INTERPENETRATION / SUPPORT on post-settle geometry) and `scripts/qa/reach_validate.py`.

**What the static pre-filter CANNOT catch (and nothing else does either):**
- the **navigation** legs (drive-in the persona asked for, drive-out to depot) — no nav grader
  exists (Step 4);
- the **pallet-rides-on-Carter** fiction holding under acceleration (no FixedJoint;
  failure_mode `:129`) — only a physics run on a *moving* base would expose it, and this
  canonical only moves the base when the pallet is already empty;
- the **handoff race** (`navigate_to`/`state="complete"` fire before the last box lands
  because `setup_pick_place_controller` is async; failure_mode `:132`).

### Phase D — Depalletize controller + the EXPENSIVE physics gate

**Step 10 — [SYSTEM]/[LLM] [CHEAP-static] — register the pick-place cycle**
`apply_physics_material(rubber)` on each item; `bulk_set_attribute(sleepThreshold=0, mass=0.1)`;
then
`setup_pick_place_controller(robot_path="/World/Franka", target_source="native",
source_paths=[Item_1,Item_2,Item_3], destination_path="/World/Outfeed",
drop_targets={each→[0,-0.50,0.85]}, end_effector_offset=[0,0.005,0])`.
Handler: `handlers/pick_place.py`. This **registers** the controller (returns immediately,
async) — it does not itself step physics. `motion_controllers.untested:["native","curobo","direct_joint"]`
(`:138-146`) — i.e. **no controller is verified** for this template yet.

**Step 11 — [SYSTEM] [CHEAP-static] — handshake complete + depart**
`set_attribute(handoff:state="complete")` then
`navigate_to(robot_path="/World/Forklift", target_position=[-1.0,0.0], planner="direct")`
(`handlers/robot.py:_gen_navigate_to` `:1594`; `direct` = reactive
`WheelBasePoseController`+`DifferentialController` per physics step; `astar` exists but builds
an *empty* occupancy grid unless populated, `:1641-1648`). **This is the only modeled drive
and it sends the Carter AWAY, after depalletize** — the inverse of the persona's "drive to the
cell." Its arrival at the depot is **ungraded** (Step 4: no nav gate; `get_world_transform` is
the only read).

**Step 12 — [SYSTEM] [EXPENSIVE-physics] — settle**
`settle_after_canonical(tpl)` plays a short warm-up so the 3 boxes rest on the pallet before
grading (`gate_one.py:settle_after_canonical`, ~30 s timeout). First physics stepping of the run.

**Step 13 — [SYSTEM] [EXPENSIVE-physics] — THE FUNCTION GATE**
`simulate_traversal_check` with the template's own `simulate_args` (`:100`):
`target_path="/World/Outfeed", cube_paths=[Item_1,Item_2,Item_3], duration_s=240,
xy_tolerance=0.18`. Handler: `handlers/diagnostics.py:_handle_simulate_traversal_check`
(`:3920`). It plays the timeline for **240 sim-seconds**, samples each cube before/at stop,
and evaluates three criteria (`:3925-3928, 3968-3982`).

### Gate success criterion (the OUTCOME, stated exactly)

For each tracked cube, at sim end:
- **`in_target_xy`** — cube final XY inside `/World/Outfeed` bbox, **expanded by
  `xy_tolerance=0.18 m`**;
- **`above_floor`** — cube Z ≥ target bbox min-Z − `floor_tolerance` (default 0.10 m);
- **`at_rest`** — cube speed < `rest_speed_threshold` (default 0.05 m/s).

In **multi-cube mode (`cube_paths`)** — which this template uses — **`success=True` fires if
ANY one cube lands in the outfeed bbox** and is above-floor & at-rest
(`:3941-3942` "Success fires if ANY cube reaches the target bbox"). For a multi-run
(`n_runs>1`) the verdict is a majority: `success = n_ok*2 >= n_runs`, classified
`stable_ok` / `flaky` / `stable_fail`. The single authoritative runner is
`scripts/qa/gate_one.py`.

> **Outcome honesty:** a `success=True` here means **≥1 of the 3 boxes reached the outfeed**.
> It says **nothing** about whether the Carter "drove to the cell," whether the pallet was
> ever truly *carried*, whether all 3 boxes were unloaded, or whether the Carter reached its
> depot. The persona's headline action (the AMR drive) is **outside the graded outcome**.

---

## 2. Predicted outcome

- **Gate result: UNVERIFIED, likely FAIL or at best partial as drafted.** The template is
  `function-gate ⏳` with **zero verified motion controllers** (`:138`). The far-box reach
  violation (Step 9) would, on the `thoughts` geometry, make Item_3 unpickable; under the
  ANY-cube criterion the gate could still flip `success=True` if Item_1 (nearest, well within
  reach) is delivered — a classic **lenient-gate partial** that masks the unreachable box and
  the entire unmodeled navigation story. Honest verdict: the *depalletize half* is plausibly
  partially-passable after the cheap reach fix; the *AMR-drive half the persona actually asked
  for is not modeled and not gradable at all.*
- **What the cheap static eyes bought:** the reach failure on the far box is caught by
  `diagnose_scene_feasibility` (Step 9) for ~0 s of physics, instead of discovering it after a
  240 s sim.

---

## 3. Tool-gap inventory (confirmed MISSING by grep)

| Need (for this exact request) | Tool that would do it | Status |
|---|---|---|
| Bind the pallet as a rideable load on the Carter | `attach_payload` / `load_pallet` / `attach_to_amr` / `carry_payload` | **MISSING** (workaround: hand-wire `create_articulated_joint(joint_type="fixed")`, which the template does NOT do) |
| Grade "Carter reached the cell" / depot | `simulate_navigation_check` / `verify_amr_at_goal` / `verify_nav_goal` | **MISSING** (only `simulate_traversal_check` exists — cube-into-bin) |
| First-class mobile-manipulation / docking | `setup_mobile_manipulator` / `dock_amr` | **MISSING** |
| Compose two canonicals (navigate THEN depalletize) into one graded run | `compose_templates` / `chain_canonical` / `multi_stage_gate` | **MISSING** (gate scores a single pick-place stage only) |
| Block the depalletize on the handoff signal / poll an attribute | `wait_for_handoff_state` / `poll_attribute` | **MISSING** (handoff toggled unconditionally) |

---

## 4. Capability honesty summary

- **Template:** `CP-NEW-forklift-handoff-arm` — **DRAFT**, function-gate never passed,
  Carter realized as a Jetbot-like **proxy** (Nucleus mesh = `nucleus_only_asset` blocker).
- **"Drive the Carter to the cell"** (the persona's headline verb): **NOT MODELED** — Carter
  spawns at the cell; the only `navigate_to` drives it *away* afterward, and that leg is
  **ungraded**.
- **"The pallet it carried"**: **friction co-placement, not a carried load** — no FixedJoint,
  no payload-attach tool.
- **"Takes 3 boxes off the pallet"**: modeled as a Franka native pick-place; **far box likely
  outside reach** (cheap static pre-filter catches it); gate passes on **ANY one** box, so a
  green gate ≠ all 3 unloaded.
- **Static-eyes pre-filter** (`diagnose_scene_feasibility`, `scene_validate.py`) earns its keep
  by catching the reach violation pre-physics; it is **blind to the navigation, carried-load,
  and handoff-race** failure modes — and no other gate covers them either.

*Step count (user-action steps `[USER]`): 1 — the single one-sentence request (Step 1).*
