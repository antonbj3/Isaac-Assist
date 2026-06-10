# End-to-End Trace — `sorter-color-3bin` (T2, Franka, sort)

**Persona:** sortation operator
**One-sentence request:** *"Franka color-sorts red/green/blue cubes into three bins"*
**Scenario id:** `sorter-color-3bin` · tier **T2** · robot **franka** · task **sort**

This document traces the COMPLETE sequence of actions — user, LLM, and system —
from the typed request to the gate verdict. Every step is tagged
`[USER]` / `[LLM]` / `[SYSTEM]` and `[CHEAP-static]` / `[EXPENSIVE-physics]`.
Each grounding cites `file:line`. Honesty notes (draft / missing tool / unverified)
are called out inline and collected at the end.

---

## 0. Template match (what the retrieval layer would land on)

Two real templates match the request; both are Franka 3-color RGB sorters:

| Template | What it is | Cubes | Gate status | File |
|---|---|---|---|---|
| **`CP-34`** | "Vision-driven 3-color sorter: 3 cubes (red, green, blue) on conveyor + camera." | 3 (1 each) | **function-gate ✓ (180s sim, cube delivered)** — `CP-34.json:82` | `workspace/templates/CP-34.json` |
| `CP-NEW-sorter-color-3lane` | "3-lane color sorter … RedBin/GreenBin/BlueBin … nine cubes in a repeating red/green/blue pattern (3 of each)." | 9 (3 each) | **drafted, function-gate ⏳** — `CP-NEW-sorter-color-3lane.json:430` | `workspace/templates/CP-NEW-sorter-color-3lane.json` |

**Match decision:** the literal "three bins" + sortation-operator persona points at
`CP-NEW-sorter-color-3lane` (it is the only template that physically builds three
*named, color-matched* bins for nine cubes). But it is a **draft** —
`"verified_status": "drafted-2026-05-16; form-gate-schema ✓; function-gate ⏳"`
(`CP-NEW-sorter-color-3lane.json:430`) and `motion_controllers.verified` is **empty**
(`:423`). The only **verified** 3-color RGB sorter is `CP-34`
(`function-gate ✓`, `CP-34.json:82`; `motion_controllers.verified=["curobo"]` `:104`).

This trace follows **`CP-NEW-sorter-color-3lane`** as the primary match (it is the
true target scene for the request) and uses **`CP-34`** as the verified fallback
the system would actually trust for a green light.

---

## 1. The full numbered narrative

### Step 1 — Operator types the request
- **[USER] [CHEAP-static]** The sortation operator types: *"Franka color-sorts
  red/green/blue cubes into three bins."*
- No simulation yet — pure text into the chat service.

### Step 2 — LLM parses intent + retrieves the canonical
- **[LLM] [CHEAP-static]** The model classifies the request as
  `pattern_hint: "sort"`, `destination_kind: "n_bins_routed"`,
  `n_destination_bins: 3`, `uses_color_routing: true`,
  `uses_vision_classifier_gate: true`
  (the `intent.structural_features` block, `CP-NEW-sorter-color-3lane.json:165-176`).
- Retrieval returns `CP-NEW-sorter-color-3lane` as the nearest structural match.
  Roles required: `primary_robot` (franka/ur10/ur5e), `input_conveyor`, `red_bin`,
  `green_bin`, `blue_bin`, `workpieces` (3–9 cubes, *"multiple of 3"* —
  `CP-NEW-sorter-color-3lane.json:227-236`).

### Step 3 — LLM binds roles to the operator's wording
- **[LLM] [CHEAP-static]** Robot = `franka_panda` (matches the request and the
  template default `role_defaults.primary_robot.class`,
  `CP-NEW-sorter-color-3lane.json:241`). Cube count defaults to **9** (3 red / 3
  green / 3 blue), the balanced split the role contract demands.
- The model emits the build program from `code` /`code_template`
  (`CP-NEW-sorter-color-3lane.json:21` / `:421`). The tool calls below are all
  **[CHEAP-static]** scene authoring — no physics is stepped yet.

### Step 4 — SYSTEM builds the scene skeleton (lights / ground / physics / table)
- **[SYSTEM] [CHEAP-static]** `create_prim` DomeLight + Ground; `apply_api_schema`
  PhysicsCollisionAPI; `set_physics_scene_config({enable_gpu_dynamics:False,
  broadphase_type:"MBP"})` — CPU dynamics for determinism on a small scene
  (`CP-NEW-sorter-color-3lane.json:20` rationale point 7).
- Handlers: `create_prim`, `apply_api_schema`, `set_physics_scene_config`
  (`set_physics_scene_config` → `tool_descriptions_polish_b5.py`).

### Step 5 — SYSTEM spawns the Franka on the table
- **[SYSTEM] [CHEAP-static]** `robot_wizard(robot_name="franka_panda",
  dest_path="/World/Franka", position=[0,0,0.75],
  orientation=[0.7071,0,0,0.7071])` — base at z=0.75, facing +Y toward the
  conveyor. Handler: `robot_wizard` → `handlers/resolve.py`.
  - *Why `robot_wizard` and not a raw `add_reference`:* per project memory the
    raw `add_reference(ur10.usd)` starts an arm WOUND; `robot_wizard` spawns from
    home_joints. For Franka this matters less, but the template standardizes on it.

### Step 6 — SYSTEM builds the infeed conveyor
- **[SYSTEM] [CHEAP-static]** `create_conveyor(prim_path="/World/ConveyorBelt",
  position=[0,0.40,0.78], size=[3.0,0.3,0.05], surface_velocity=[0.12,0,0])` —
  belt in front (y=+0.40), top at z=0.805, 0.12 m/s feed
  (`CP-NEW-sorter-color-3lane.json:20` point 3). Handler: `create_conveyor` →
  `handlers/resolve.py`.

### Step 7 — SYSTEM creates the three color materials
- **[SYSTEM] [CHEAP-static]** `create_material` ×3 (OmniPBR MatRed/MatGreen/MatBlue
  with RGB diffuse). Handler registered in `tool_descriptions_polish.py`.

### Step 8 — SYSTEM spawns 9 cubes, colors + labels them, adds physics
- **[SYSTEM] [CHEAP-static]** Loop over `_cube_colors =
  [red,green,blue,red,green,blue,red,green,blue]`
  (`CP-NEW-sorter-color-3lane.json:21`): per cube — `create_prim` (size 0.06,
  spaced 0.20 m from x=-1.40), `assign_material`, **`set_semantic_label`**
  (`"red cube"`/`"green cube"`/`"blue cube"` — the routing key), `apply_api_schema`
  ×4 (RigidBody/Collision/Mass/PhysxRigidBody), and
  `set_attribute(physxRigidBody:sleepThreshold=0.0)`.
  - Spawn x starts at **-1.40** not -1.60: the template comment records the fix
    *"(was -1.60 which put Cube_1 and Cube_4 outside the belt edge → floor drop)"*
    (`CP-NEW-sorter-color-3lane.json:21`). This is a **known prior failure already
    patched in the draft**.
  - Handlers: `set_semantic_label` → `handlers/vision.py`; `assign_material` →
    `tool_descriptions_polish.py`.

### Step 9 — SYSTEM builds the three destination bins behind the robot
- **[SYSTEM] [CHEAP-static]** `create_bin` ×3: RedBin x=-0.40, GreenBin x=0.00,
  BlueBin x=+0.40, all at y=-0.45, z=0.75, size 0.28×0.28×0.15
  (`CP-NEW-sorter-color-3lane.json:21`). The template's own reach math:
  *"Maximum horizontal distance = sqrt(0.40² + 0.45²) = 0.60 m — inside 0.85 m
  reach"* (`:20` point 2). Handler: `create_bin` → `handlers/resolve.py`.

### Step 10 — SYSTEM places the overhead classification camera
- **[SYSTEM] [CHEAP-static]** `create_prim` Camera at [0,0.40,1.30];
  `set_camera_look_at(target=[0,0.40,0.8375], up=[0,0,1])` — straight down over
  the pick point. Handler: `set_camera_look_at` → `handlers/sensors.py`.
  - *Honesty note:* `CP-34` (the verified template) instead uses a side-elevated
    camera at **[0,1.5,1.5]** with the comment *"verified working (CP-16 probe
    2026-05-08 detected cubes)"* (`CP-34.json:21`, `:303`). The 3-lane draft's
    overhead [0,0.40,1.30] placement is **not** independently camera-probe-verified;
    its failure-mode list flags *"Vision classification fails in headless mode …
    requires a render context"* (`CP-NEW-sorter-color-3lane.json:158`).

### Step 11 — SYSTEM arms the pick proximity sensor
- **[SYSTEM] [CHEAP-static]** `add_proximity_sensor(sensor_path="/World/PickSensor",
  position=[0.30,0.40,0.8375], size=[0.07,0.07,0.07],
  watched_path_pattern="/World/Cube_")` — fires when a cube reaches the pick
  station. Handler: `add_proximity_sensor` → `handlers/sensors.py`.

### Step 12 — SYSTEM runs the vision classifier gate (builds the routing table)
- **[SYSTEM] [CHEAP-static]** `add_vision_classifier_gate(cube_paths=[9 cubes],
  class_labels=["red cube","green cube","blue cube"], camera_path="/World/SortCamera",
  destination_map={"red cube":RedBin,"green cube":GreenBin,"blue cube":BlueBin})`
  (`CP-NEW-sorter-color-3lane.json:21`). Handler:
  `_handle_add_vision_classifier_gate` → `handlers/sensors.py:562`.
  - **Reality of this step (grounded):** for color-shaped labels the handler takes
    a **deterministic USD-color fast path** — it reads each cube's bound material
    `diffuseColor` directly and skips the VLM entirely
    (`sensors.py:615-650`, log *"USD-color introspection succeeded … bypassed VLM"*
    at `sensors.py:732`). Only if labels aren't color-coded or a cube has no bound
    material does it fall back to a viewport capture + VLM (`sensors.py:742`,
    `:775-883` left-to-right heuristic). So in THIS scene the "vision" gate is in
    practice a static material read — which is why the headless-render failure mode
    (`:158`) is dodged for RGB but would bite a genuinely vision-only variant.
  - This step is still **[CHEAP-static]**: no timeline play, just USD reads.

### Step 13 — SYSTEM installs the pick-place controller with 3-way color routing
- **[SYSTEM] [CHEAP-static]** `setup_pick_place_controller(robot_path="/World/Franka",
  target_source="curobo", sensor_path=PickSensor, belt_path=ConveyorBelt,
  source_paths=[9 cubes], destination_path=GreenBin,
  color_routing={"red cube":RedBin,"green cube":GreenBin,"blue cube":BlueBin},
  planning_obstacles=[Table,ConveyorBelt,RedBin,GreenBin,BlueBin])`
  (`CP-NEW-sorter-color-3lane.json:21`). Handler: `setup_pick_place_controller`
  → `handlers/resolve.py`.
  - **Critical routing-key invariant:** the `color_routing` keys MUST byte-match the
    `set_semantic_label` class names (`"red cube"`, not `"red"`). The template's
    #1 failure mode warns *"color_routing keys must EXACTLY match (space-separated
    'red cube', not 'red')"* (`CP-NEW-sorter-color-3lane.json:157`). Note the
    verified `CP-34` uses the **short** keys `"red"/"green"/"blue"`
    (`CP-34.json:69`) with matching short labels — the two templates use different
    key conventions, so cross-borrowing the routing dict is a silent-mis-route trap.
  - Installing the controller does NOT move the arm — it registers a per-step
    callback. Still static.

---

### Step 14 — STATIC-EYES PRE-FILTER (cheap reach/collision/fit, no physics)
- **[SYSTEM] [CHEAP-static]** Before paying for the physics gate, the scene is run
  through the static constraint validator **`scripts/qa/scene_validate.py`**. It
  builds + settles passively (arm parked at HOME, controller unsubscribed —
  `scene_validate.py:70-75`) and reads ACTUAL post-settle geometry, then checks
  five classes that recur in generated scenes (`scene_validate.py:1-23`):
  1. **PHYSICS_INSTABILITY** — any pick that travelled >1 m during the passive
     settle was ejected by a spawn-overlap explosion (`scene_validate.py:247-255`).
     *This is exactly the "-1.60 → floor drop" class the draft already fixed at
     Step 8.* Had the LLM regressed that x-offset, this check catches it here for
     **free** instead of after a 270 s physics run.
  3. **REACH** — every cube vs its nearest arm's reachable shell;
     `ROBOT_REACH["franka_panda"]=0.855` (`scene_validate.py:32`), with a
     family z-window `franka: zlo=-0.45` (`scene_validate.py:278`). A cube on the
     moving belt upstream is treated as reachable because the belt carries it in
     (`belt_reachable`, `scene_validate.py:173-185`).
  4. **TARGET_REACH** — each of the 3 bins' top-center must be placeable; bins at
     `dist = sqrt(0.40²+0.45²) = 0.60 m < 0.855 m` pass cleanly
     (`scene_validate.py:289-307`). **This is where an out-of-reach bin is caught
     before the gate** — e.g. if a UR5e variant kept bins at x=±0.40 the
     template's own note says to pull them to x=±0.30
     (`CP-NEW-sorter-color-3lane.json:159`); the validator would flag
     `TARGET_REACH` otherwise.
  5. **INTERPENETRATION** — gross 3-axis cube overlap (>50% + 2 cm), the
     "9 cubes collapsed into one point" class (`scene_validate.py:309-322`).
  6. **SUPPORT** — each cube rests on the belt, not floating/buried
     (`scene_validate.py:324-338`).
- **Outcome of the pre-filter on this scene:** with the patched x=-1.40 spawn and
  0.60 m bins, all five checks are expected to pass — *no* violation, so the run
  proceeds to the expensive gate. The value is asymmetric: it costs ~2.5 s of
  passive settle and would have **saved a 270 s physics run** on the pre-patch
  (-1.60) version, or on any LLM re-bind that puts a bin out of reach.
- **Honesty note:** `scene_validate.py` is a **bench script, not an LLM-callable
  tool** — there is no registered `static_eyes_check` / `reach_check` / `fit_check`
  handler (confirmed missing, see Tool gaps). The LLM cannot invoke this pre-filter
  itself mid-conversation; it runs in the QA/bench harness around the model.

---

### Step 15 — EXPENSIVE physics gate: `simulate_traversal_check`
- **[SYSTEM] [EXPENSIVE-physics]** The authoritative function-gate
  (`scripts/qa/gate_one.py`) plays the timeline for the template's
  `duration_s = 270` (`CP-NEW-sorter-color-3lane.json:127`) and calls
  `simulate_traversal_check` with the template's own `simulate_args`
  (`gate_one.py:71-80`). Handler: `_handle_simulate_traversal_check` →
  `diagnostics.py:3920`.
- The controller's per-step callback now actually drives the Franka: cuRobo plans
  pick → lift → route-by-color → place, cube after cube, as the belt feeds them.
  This is the only **[EXPENSIVE-physics]** step in the whole flow.

### Step 16 — Gate scores the outcome (the success-criterion)
- **[SYSTEM] [EXPENSIVE-physics]** Per `diagnostics.py:3920-3983`, for each tracked
  cube the gate samples world position just before stop and at stop and evaluates
  **three** criteria against the target bbox:
  - `in_target_xy` — cube XY inside `target_path` bbox (expanded by
    `xy_tolerance=0.09`, `CP-NEW-sorter-color-3lane.json:128`)
    (`diagnostics.py:3975`),
  - `above_floor` — cube Z ≥ bin floor − `floor_tolerance` (default 0.10)
    (`diagnostics.py:3976`),
  - `at_rest` — cube speed < `rest_speed_threshold` (default 0.05)
    (`diagnostics.py:3977`).
  - **Success rule (multi-cube):** *"Success fires if ANY cube reaches the target
    bbox"* (`diagnostics.py:3941`, `:3968-3969`). With `n_runs=1` the verdict is the
    primary cube; `gate_one.py:87` reads `verdict["success"]`.

  **→ GATE SUCCESS-CRITERION (the OUTCOME):** `success == True`, i.e. **at least one
  cube comes to rest inside `target_path`'s bounding box (XY within +0.09 m, Z
  within floor tolerance, speed < 0.05 m/s).** `gate_one.py` prints
  `GATE success=True` on pass.

### Step 17 — Honest gap between the gate and the actual ask
- **[SYSTEM] [CHEAP-static]** The request is *sort red→red, green→green,
  blue→blue into three bins*. The template encodes that intent in
  `simulate_args.routed_target_paths=[RedBin,GreenBin,BlueBin]` and
  `per_bin_expected={red:3,green:3,blue:3}` (`CP-NEW-sorter-color-3lane.json:111,
  129-133`). **But the gate handler does not read those keys.** Grep confirms
  `per_bin_expected` / `routed_target_paths` appear ONLY in sweep/calibration
  scripts (`scripts/deploy/brev/run_distributed_sweep.py:160`,
  `scripts/review/calibrate_verifier.py:59`) — **never** in
  `diagnostics.py`. `gate_one.py:73-78` forwards only
  `cube_path / target_path / duration_s / cube_paths / color_routing`. So the live
  gate verifies *"≥1 cube landed in ONE bin (`target_path=RedBin`,
  `simulate_args.target_path` `:110`)"* — it does **not** verify per-color routing
  accuracy or that all 9 cubes reached their correct bins. **The color-sort
  correctness — the actual point of the scenario — is NOT measured by the gate.**

### Step 18 — Final verdict surfaced to the operator
- **[SYSTEM] [CHEAP-static]** `gate_one.py:88` emits
  `CP-NEW-sorter-color-3lane: GATE success=<bool> …`. On `True`, the operator is
  told the sorter "works"; given Step 17, that means *one* cube was delivered to
  one bin, not that all three colors sorted correctly.

---

## 2. Outcome (honest)

- **Build (Steps 4–13): expected to succeed.** Every tool the template calls
  exists and is a registered handler (verified: `robot_wizard`, `create_conveyor`,
  `create_bin`, `set_camera_look_at`, `add_proximity_sensor`, `set_semantic_label`,
  `assign_material`, `create_material`, `set_physics_scene_config`,
  `add_vision_classifier_gate`, `setup_pick_place_controller`).
- **Static pre-filter (Step 14): expected PASS** — patched -1.40 spawn + 0.60 m
  bins satisfy REACH / TARGET_REACH / SUPPORT / INTERPENETRATION / INSTABILITY.
- **Physics gate (Steps 15–16): UNVERIFIED for this template.**
  `CP-NEW-sorter-color-3lane` is `function-gate ⏳` with NO verified motion
  controller (`:423,430`). The closest **verified** evidence is the sibling
  `CP-34` (3 cubes, `function-gate ✓`, `cube_final=(-0.42,-0.40,0.785) in Bin`,
  `CP-34.json:82`). So a green light on the *exact* 9-cube 3-bin scene is
  **plausible but unproven**; the trustworthy fallback is the 3-cube `CP-34`.
- **Gate vs. ask mismatch (Step 17): real.** Even a `success=True` proves only
  *one cube → one bin*, not *correct per-color sort*. The `per_bin_expected`
  intent is authored but unenforced.

---

## 3. Tool gaps (grep-confirmed missing)

These would be needed to fully verify *this* scenario but have **no handler**
(`grep "def _handle_<t>" service/.../tools/` → none):

- **`static_eyes_check` / `reach_check` / `fit_check`** — the static pre-filter
  (Step 14) exists only as the bench script `scripts/qa/scene_validate.py`; the LLM
  cannot call reach/collision/fit checks mid-build to self-correct before the
  expensive gate.
- **`per_bin_gate` / `validate_sort_accuracy` / `simulate_sort_check`** — no gate
  reads `per_bin_expected` / `routed_target_paths`; per-color sort correctness
  (the scenario's whole point) is unmeasurable through the registered tools
  (Step 17). `simulate_traversal_check` is single-target, ANY-cube.
- **`verify_routing_table`** — nothing validates that `color_routing` keys
  byte-match the `set_semantic_label` class names; the #1 documented failure mode
  (`CP-NEW-sorter-color-3lane.json:157`) is left to manual review.
- **`measure_sort_throughput`** — the belt-cadence-vs-cycle-time starvation risk
  (`:160`, 0.6 s inter-arrival) has no measurement tool.

(`add_vision_classifier_gate` and `setup_pick_place_with_vision` DO exist —
`sensors.py:562`, `robot.py` — and are NOT gaps.)

---

## 4. Drafts / unverified flags (collected)

- `CP-NEW-sorter-color-3lane` is a **draft**: `function-gate ⏳`,
  `motion_controllers.verified=[]` (`:423,430`).
- Overhead camera [0,0.40,1.30] is **not camera-probe-verified** (vs `CP-34`'s
  verified [0,1.5,1.5]); headless-render failure mode flagged (`:158`) — mitigated
  only because the RGB labels trigger the USD-color fast path (`sensors.py:615`).
- Routing-key convention differs between the two matching templates
  (`"red cube"` vs `"red"`) — a cross-borrow silent-misroute trap (`:157`).
- The gate does not enforce per-color routing; `per_bin_expected` is authored but
  ignored by `diagnostics.py`.
