# Traced Flows — Three More Requests, End-to-End

**Companion to `TRACED_FLOW_PALLETIZER.md`.** Same discipline: follow one
one-sentence request through every stage (intake → retrieve → static-eyes →
build → gate → diagnose), with real `file:line` citations, concrete numbers, and
a **[CHEAP-static]** / **[EXPENSIVE-physics]** marker at each step. The recurring
lesson is **where the static "scene-eyes" pre-filter (`reach_validate.py`) saves
the 180–300 s physics gate** — and, equally important, **where it cannot** because
the relevant target was never declared to the probe.

Three personas, three *distinct capabilities* that stress the pipeline in
different ways:

| # | Persona | Distinct capability | Where static-eyes helps / fails |
|---|---|---|---|
| 1 | Quality inspector | a **SENSOR** decides routing; gate must grade MISROUTED vs DELIVERED | probes only PassBin picks — **blind to the reject path** |
| 2 | CNC machinist | same robot, **MULTI-PHASE** (load→dwell→unload) cycle | probes infeed+outfeed, **NOT the chuck** (the inner reach) |
| 3 | AMR + arm depalletize | **mobile base + manipulation** in one scene | probes the arm's picks; **AMR park pose is hand-placed, not validated** |

The five-stage cost table from the palletizer doc holds for all three:

| Stage | Artifact | Cost |
|---|---|---|
| 1 Intake | `LayoutSpec` (intent only) | **[CHEAP-static]** (regex/LLM, ms) |
| 2 Retrieval | canonical template dict | **[CHEAP-static]** (embedding query, ms) |
| 3 Static reach | per-target REACHABLE/UNREACHABLE | **cheap-ish** (one IK probe per target) |
| 4 Fix loop | adjusted positions | **[CHEAP-static]** (arithmetic) |
| 5 Build | instantiated USD scene | mixed (authoring, no long sim) |
| 6 Dynamic gate | `success: bool` | **[EXPENSIVE-physics]** (180–300 s live) |
| 7 Diagnose | root_cause + recommendation | cheap (reads recorded state) |

---
---

## FLOW 1 — Quality inspector (vision-reject)

> *"Camera classifies parts on the belt as good/defect and routes defects to a
> reject lane."*

**Matched canonical:** **`CP-NEW-inspect-reject`**
(`workspace/templates/CP-NEW-inspect-reject.json`). Goal (`json:3`): *"vision-gated
inspection station: cubes pass under camera, vision classifier identifies good vs
defective, divert chute steers good cubes to PassBin, defective to RejectBin.
Realizes Phase 9 yrkesroll #7 (quality engineer persona)."*

The **distinct capability**: routing is decided by a *per-item class*, not a fixed
destination. Five cubes, four green ("good") + one red ("defect", `Cube_3`,
`json:16`). The controller dispatches `green → PassBin`, `red → RejectBin`.

### Stage 1 — Intake   **[CHEAP-static]**

`text_modality.produce_layout_spec_from_text` (`text_modality.py:213`). "classifies
… good/defect … routes defects to a reject lane" trips:
- `_detect_pattern_hint` — "routes"/"reject lane" is **sort**-shaped, but the
  rule-based extractor has no "reject" keyword, so it falls to the `pick_place`
  default unless the LLM extractor fires. The **canonical itself** declares
  `pattern_hint="sort"` (`json:42`), so a soft/LLM extraction that emits
  `routing_axis=semantic_class` is what cleanly aligns. **[gap: rule-based path
  under-classifies "reject" → relies on LLM extractor for the clean `sort` hint.]**
- "camera"/"vision"/"classifies" → the structural signal the template carries as
  `isaac:vision.inspect_and_reject` (`json:54`).
- "belt" → `uses_conveyor_transport=True` (`json:48`).

### Stage 2 — Retrieval   **[CHEAP-static]**

`template_retriever.retrieve_with_intent_*`. Stage-1 structural filter keeps
templates with `destination_kind="n_bins_routed"` + `routing_axis="semantic_class"`
(`json:46-47`) — a narrow shape that **only the inspect/sort family** carries, so
`CP-NEW-inspect-reject` and `CP-NEW-sorter-color-3lane` are the survivors; the
"reject"/"defect" wording in the prompt embedding-ranks `inspect-reject` top.

The matched canonical's relevant pieces:
- **roles** (`json:57-111`): `primary_robot` (franka/ur5e/kinova), `input_conveyor`,
  **`pass_bin` AND `reject_bin`** (two destinations — the routing fork),
  `inspect_camera`, `pick_sensor`, `workpieces` (1–8).
- **role_defaults** (`json:112-246`): PassBin at `[0.5, -0.4, 0.75]`, **RejectBin at
  `[-0.5, -0.4, 0.75]`** (mirror side), camera at `[0, 0.4, 1.20]` looking straight
  down at the belt top `z=0.78` (`json:172-184`), five cubes on the belt at
  `x ∈ {-1.0, -0.8, -0.6, -0.4, -0.2}, y=0.4, z=0.835`, with `Cube_3` (`x=-0.6`)
  tagged `color:"red"` (`json:218-226`).

### Stage 3 — Static reach   **[CHEAP-static, with a blind spot]**

`scripts/qa/reach_validate.py`. The probe reads `simulate_args.cube_paths`
(`reach_validate.py:70`) and probes each as a pick, plus `target_path` as one
extra place-probe (`:87`, `_reach_probe_extra_paths`).

For this template, `simulate_args` (`json:23-32`):
```json
"cube_paths": ["/World/Cube_1","/World/Cube_2","/World/Cube_4","/World/Cube_5"],
"target_path": "/World/PassBin",
"duration_s": 180
```

So the probe checks: the **four green cubes** can be picked off the belt, and
**PassBin** is reachable straight-down. The Franka base is at `[0,0,0.75]` with reach
~0.85 m; the belt pick station and PassBin at `[0.5,-0.4]` are well inside the dense
front annulus → expect **REACHABLE** for all four picks. Verdict is PICK-based
(`reach_validate.py:140-150`); PassBin's straight-down column is a WARNING only
(`:153-154`), since a drop happens *above* the bin.

**The blind spot (a real gap, honestly flagged in the template at `json:39`):**
> *"Red cube (Cube_3) reach RejectBin: not validated by gate (gate only checks
> PassBin); need separate test for reject path."*

Because `Cube_3` and `RejectBin` are **absent from `simulate_args`**, the static
probe **never tests whether the reject path is reachable**. RejectBin sits at
`[-0.5, -0.4]` — the *opposite* side of the Franka from PassBin. For a front-facing
Franka this is the far/contralateral annulus and is plausibly the harder reach, yet
**neither the static probe nor the gate covers it**. This is the canonical case
where static-eyes *could* save the gate but isn't pointed at the right target. The
fix is a one-line static change: add `/World/Cube_3` to a reach-only probe list and
`/World/RejectBin` as an extra path — *before* paying for any sim.

### Stage 4 — Fix loop   **[CHEAP-static]**

If a reach probe with `Cube_3`+`RejectBin` came back UNREACHABLE (contralateral
side), the static fix is arithmetic on `role_defaults`: pull `RejectBin` from
`[-0.5,-0.4]` toward the front-right annulus (e.g. `[0.45, 0.25]`) or swap to a
longer-reach UR10 (the `primary_robot` constraint set already allows `ur5e`; a UR10
variant would widen the annulus). No physics needed to decide the direction.

### Stage 5 — Build   **[mixed]**

`execute_template_canonical` → role-substitute `code_template` (`json:247`). The
tool sequence (`json:4-14` + code):
```
DomeLight / Ground / Table / set_physics_scene_config(CPU, MBP)
robot_wizard(franka_panda, /World/Franka, pos=[0,0,0.75], orient=[0.7071,0,0,0.7071])
create_conveyor(/World/ConveyorBelt, pos=[0,0.4,0.78], vel=[0.15,0,0])
# 5× cube + create_material(green|red) + assign_material + 4 physics APIs
bulk_set_attribute(sleepThreshold=0.0)              # belt-resume wake fix (json:247 comment)
create_bin(/World/PassBin,  [0.5,-0.4,0.75])
create_bin(/World/RejectBin,[-0.5,-0.4,0.75])
configure_camera(/World/InspectCamera, pos=[0,0.4,1.20], look_at=[0,0.4,0.78], fov=60)
add_proximity_sensor(/World/PickSensor, [0.4,0.4,0.835])
setup_pick_place_controller(
    robot=/World/Franka, target_source="curobo",
    sensor=/World/PickSensor, belt=/World/ConveyorBelt,
    source_paths=[Cube_1..Cube_5], destination_path=/World/PassBin,
    color_routing={"green":"/World/PassBin", "red":"/World/RejectBin"},   # the routing fork
    planning_obstacles=[Table, ConveyorBelt, PassBin, RejectBin])
```

**Where the SENSOR actually decides routing** — and where the Gemini gap lives:

- `configure_camera` is **codegen-only scene authoring**
  (`sensors.py:138 _gen_configure_camera`) — it places a USD camera. It does *not*
  classify anything.
- The runtime class→destination dispatch is **inside the controller**, not the
  camera. `color_routing` is consumed by `setup_pick_place_controller`
  (`pick_place.py:456`, `:497` pass `color_routing=args.get("color_routing")`). The
  generated controller body holds `COLOR_ROUTING = {…}` (`pick_place.py:3166`,
  `:4133`) and, per pick, calls `_destination_path_for(cube_path)`
  (`pick_place.py:3345-3352`):
  ```python
  def _destination_path_for(cube_path):
      if COLOR_ROUTING and cube_path:
          col = _cube_semantic_class(cube_path)        # reads USD Semantics_color
          if col and col in COLOR_ROUTING:
              return COLOR_ROUTING[col]
      return DEST_PATH                                 # fallback = PassBin
  ```
  `_cube_semantic_class` (`pick_place.py:3323-3343`) reads the cube's
  `Semantics_color` / `Semantics_colour` / `Semantics_class` USD attribute. **So
  routing is driven by a USD semantic label, not by a live camera frame** in the
  built scene — the "camera" is cosmetic at gate time.

**The Gemini-quota / local-vision gap (concrete):** the *actual* VLM classifier is
a separate tool, `vision_detect_objects` (`vision.py:1313`), and the agent-side
class-routing helper `add_vision_classifier_gate` (`sensors.py:562`). Both call
`_get_vision_provider()` (`_shared.py:515`). The provider policy (`_shared.py:518-573`):
- `IA_VISION_PROVIDER=gemini` → `GeminiVisionProvider` — **needs a Gemini API key
  and burns quota** (`vision.py:1329-1336` captures the viewport and calls
  `vp.detect_objects`).
- `IA_VISION_PROVIDER=sam_clip|local` → local `SamClipVisionProvider`
  (`_shared.py:545-549`) — **no quota, but needs the SAM2 weights on disk**; if
  missing it logs and falls back to Gemini (`:550-557`).
- `auto` (default) → local SAM+CLIP **iff** `SAM_CHECKPOINT.exists()`
  (`_shared.py:559-568`), else Gemini.

So a vision-driven build is **quota-fragile**: no Gemini key *and* no local SAM2
weights ⇒ the only working path is the **USD-color fast path**, which
`add_vision_classifier_gate` tries *first* and which "**bypassed VLM**" when colors
are authored (`sensors.py:732`, `:742` falls back to VLM on failure). This template
sidesteps the VLM entirely at gate time by **authoring `red`/`green` materials +
relying on `Semantics`-based `color_routing`** (`json:35` extension_notes: *"vision_detect_objects
called once at canonical-build time to verify class mapping; runtime dispatch uses
semantic labels"*). The honest read: **the canonical demonstrates the routing
plumbing, but the "vision" is a color-introspection shortcut, not a live classifier
under load** — and a true camera-in-the-loop run is gated on Gemini quota or local
SAM2 weights being present.

### Stage 6 — Dynamic gate: grade MISROUTED vs DELIVERED   **[EXPENSIVE-physics]**

`scripts/qa/gate_one.py` → `diagnostics.py::_handle_simulate_traversal_check`. Runs
the template's own `simulate_args` (180 s).

**How the gate distinguishes MISROUTED from DELIVERED — and its honest limit.**
The gate only scores the cubes in `cube_paths` against `target_path`
(`diagnostics.py:4419-4434`): per cube `cp_delivered = in_xy(PassBin±xy_tol) AND
above_floor AND at_rest`. Multi-cube success is **ANY listed cube delivered**
(`diagnostics.py:4446-4447`):
```python
if len(cube_paths) > 1:
    success = bool(delivered) and upright_ok    # ANY of the 4 green in PassBin
```

The routing semantics fall out of **which cubes are listed**:
- `cube_paths` = the **four green** cubes (`json:24-29`); `target_path = PassBin`.
- A **correctly routed red** `Cube_3` lands in **RejectBin** — and since `Cube_3`
  is **not in `cube_paths`**, it neither helps nor hurts the score. Correct.
- A **misrouted green** (one that wrongly goes to RejectBin) shows up as that
  cube's `delivered=False` in `per_cube_status` (`diagnostics.py:4491-4513`) — it's
  not in PassBin's bbox, so `in_xy=False`. With the lenient ANY-rule, the gate
  still passes if *any* other green seated, so a single green misroute is
  **masked** by the ANY-delivered criterion.
- A **misrouted red** (red wrongly into PassBin) is **invisible** — red isn't in
  `cube_paths`, and the gate never inspects RejectBin's contents at all.

So the gate measures **"≥1 good part reached the pass lane,"** not **"every part
reached its *correct* lane."** Grading the **reject path** (red actually landed in
RejectBin, and no green leaked into it) requires a **second gate invocation** with
`cube_paths=["/World/Cube_3"]`, `target_path="/World/RejectBin"` — exactly the
"separate test for reject path" the template flags at `json:39`. **[gap: routing
correctness is a two-gate measurement; the canonical ships only the pass-lane half.]**

### Stage 7 — Diagnose   **[cheap]**

`diagnose_pick_execution` reads the controller's `ctrl:*` USD records (delivered
count, plan_fails, `pick_reject`). For a misroute, the tell is a cube whose
`per_cube_status` says `in_xy=False, above_floor=True, at_rest=True` (it seated
*somewhere*, just not PassBin) → root cause = wrong-lane dispatch, which points back
at `color_routing` / the cube's `Semantics_color` label, not a motion failure.

### One-line flow

```
"camera classifies good/defect, routes defects to reject lane"
 1. text → LayoutSpec{sort, vision.inspect_and_reject, conveyor}   [CHEAP]  text_modality.py:213
 2. retrieve → CP-NEW-inspect-reject (n_bins_routed + semantic_class)  [CHEAP]  template_retriever.py
 3. reach_validate → 4 GREEN picks + PassBin REACHABLE; **Cube_3/RejectBin NEVER probed**  [CHEAP, blind]  reach_validate.py:70,87
 4. (fix) if reject path needed: pull RejectBin to front annulus / UR10  [CHEAP arithmetic]
 5. build → camera + 2 bins + color_routing controller; routing = USD Semantics, NOT live VLM  [mixed]  pick_place.py:3345
 6. gate → simulate(cube_paths=4 green, PassBin, 180s); success=ANY green seated; MISROUTED-red invisible  [EXPENSIVE]  diagnostics.py:4446
 7. diagnose → per_cube in_xy=False+at_rest ⇒ wrong-lane dispatch (color_routing/Semantics)  [cheap]
```
**Gap summary:** vision is a color-introspection shortcut (Gemini quota / local
SAM2 weights gate a *real* classifier); the static probe and the single gate both
**ignore the reject lane** — routing correctness needs a second, reject-targeted gate.

---
---

## FLOW 2 — CNC machinist (multi-phase tending)

> *"Load a raw blank, open the machine door, wait for machining, unload — repeat 4
> times."*

**Matched canonical:** **`CP-NEW-machine-tender-load-unload`**
(`workspace/templates/CP-NEW-machine-tender-load-unload.json`). Goal (`json:3`):
*"CNC machine-tender: a UR10 picks raw blanks from an infeed conveyor, loads each
blank into a CNC fixture, waits a fixed simulated machining dwell (30 s via
step-count), then unloads the finished part to an outfeed conveyor … ONET SOC
51-3093."*

The **distinct capability**: **one robot, MULTI-PHASE** — `pick_from_infeed →
load_to_fixture → DWELL → unload_to_outfeed`, repeated per blank. This is the only
flow of the three where the *same* articulation hosts *two* sequential controllers,
which is exactly where the **`phase_id`** mechanism earns its keep.

### Stage 1 — Intake   **[CHEAP-static]**

`text_modality`. "load … wait … unload … repeat" → `pattern_hint="pick_place"`
(`json:104`). The template's distinguishing structural features (`json:105-112`):
`has_machining_dwell=True`, `n_conveyors=2`, `destination_kind="fixture"`,
`n_handoffs=2` (the load and the unload are counted as two transfers). Tags include
`isaac:industry.machine_tending` and **`isaac:pattern.load_wait_unload`**
(`json:118-119`) — a shape no other canonical carries, so retrieval is unambiguous.

### Stage 2 — Retrieval   **[CHEAP-static]**

Stage-1 filter on `has_machining_dwell` + `n_conveyors=2` + dual-conveyor topology
narrows to the machine-tender family (`CP-NEW-machine-tender-load-unload`,
`CP-NEW-machine-tender-door-interlock`, `CP-NEW-yrkesroll-machinist-cnc-load`); the
"wait for machining"/"unload"/"repeat" wording embeds closest to the
load-wait-unload canonical.

Relevant `role_defaults` (`json:177-302`):
- UR10 base `[0,0,0.75]`, orientation `[1,0,0,0]` (**identity** — a 2026-05-28
  patch, `json:324-330`: non-identity UR10 base rotation makes cuRobo `plan_pose`
  fail; all working UR10 templates use identity).
- **InfeedBelt** at `y=+0.50`, **OutfeedBelt** at `y=-0.50` (`json:193-228`) — picks
  in front (+y), drops behind (−y).
- **CNC fixture** `BasePlate` at `[0, 0.18, 0.77]` (`json:229-241`), boxed by
  Left/Back/Right walls — the "machine" the blank is loaded *into*.
- 4 blanks staggered on the infeed at `x ∈ {-1.2,-0.9,-0.6,-0.3}, y=0.50, z=0.855`
  (`json:268-301`).
- Two proximity sensors: **PickSensor** above the infeed pick zone `[0.25,0.50,0.855]`
  and **UnloadSensor** above the fixture `[0,0.15,0.9]` (`json:242-267`).

### Stage 3 — Static reach: must reach BOTH the infeed AND the chuck   **[CHEAP-static, with a gap]**

This is the flow where reach matters in **two places**: the **infeed pick station**
(+y, far) *and* the **chuck/fixture** (the inner load target). A naïve formula again
lies — the UR10 nominal reach is ~1.3 m (stated in the template's own design
`thoughts`, `json:16` §2), and every target here is < 0.6 m horizontally, so a
radius test passes everything. But the
*straight-down cup* reach into a **walled fixture** (Left/Back/Right walls at
`z≈0.81`, fixture interior ~0.28 m wide) is a collision-constrained descend that
only a live probe resolves.

**What `reach_validate.py` actually probes — and what it misses.** It reads
`simulate_args` (`json:71-81`):
```json
"target_path": "/World/OutfeedBelt",
"cube_paths": ["/World/Blank_1","/World/Blank_2","/World/Blank_3","/World/Blank_4"],
"duration_s": 300, "xy_tolerance": 0.1
```
- **Picks probed:** the 4 blanks — but at their **t=0 spawn positions on the infeed**
  (`x=-1.2…-0.3`), *not* at the PickSensor station `x=0.25` where the belt actually
  delivers them. The validator detects the conveyor and emits a WARNING
  (`reach_validate.py:151-152`: *"dynamic_feed:conveyor — picks probed at t=0
  spawn; verify the fixed pick STATION position"*) — i.e. it **knows** the
  spawn-pose probe is conservative for a belt feed. So the infeed reach is probed,
  but with a documented caveat.
- **Extra place-probe:** `target_path = OutfeedBelt` → the **outfeed drop** is
  probed straight-down (`reach_validate.py:87`, WARNING-only per `:153`).
- **The chuck is NEVER probed.** `/World/CNCMachine/BasePlate` — the *inner* load
  target, the harder reach (a cup-down descend **into** a 3-walled box) — is **not
  in `simulate_args`**. The static probe therefore validates infeed→outfeed but is
  **blind to the load-into-fixture reach**, which is the geometrically tightest move
  in the whole cycle. **[gap: the inner target (chuck) is the critical reach and the
  probe doesn't see it; needs `_reach_probe_extra_paths` to include
  `/World/CNCMachine/BasePlate` at the `drop_target=[0,0.18,0.84]` pose.]**

The template *does* declare a richer `verify_args.stages` (`json:54-69`):
`InfeedBelt → CNCMachine/BasePlate`, then `CNCFixture → OutfeedBelt` (note: stage-2
`pick_path="/World/CNCFixture"` is a **stale path** — the actual prim is
`/World/CNCMachine/BasePlate`; a real bug in the verify_args, `json:64` vs `json:230`).
That two-stage verify is the right *shape* for both-target reach, but it's a
form-gate schema check, not the live IK probe.

### Stage 4 — Fix loop   **[CHEAP-static]**

If a chuck-targeted probe came back MARGINAL/UNREACHABLE (the walls block a
straight-down cup descend), the static levers are: lower the wall height
(`LeftWall`/`RightWall` scale-z from 0.06), widen the fixture, or nudge the fixture
center `[0,0.18,0.77]` toward the base. All arithmetic on `role_defaults`, no sim.

### Stage 5 — Build: where `phase_id` prevents controller aliasing   **[mixed]**

`execute_template_canonical` renders `code_template` (`json:303`). The build is
ordinary up to the **two sequential `setup_pick_place_controller` calls on the same
UR10**:

```
# PHASE 1 — load infeed → fixture
setup_pick_place_controller(
    robot=/World/UR10, robot_family="ur10e",
    sensor=/World/PickSensor, belt=/World/InfeedBelt,
    source_paths=blank_paths, destination_path=/World/CNCMachine/BasePlate,
    pick_target=[0.25,0.50,0.855], drop_target=[0.0,0.18,0.84],
    planning_obstacles=[Table, InfeedBelt, OutfeedBelt, CNCMachine/BasePlate],
    phase_id="phase1")                                   # ← phase tag

sim_control(action="step", step_count=1800)              # 30 s @ 60 Hz machining DWELL

add_proximity_sensor(/World/UnloadSensor, [0,0.18,0.87])
# PHASE 2 — unload fixture → outfeed
setup_pick_place_controller(
    robot=/World/UR10, robot_family="ur10e",
    sensor=/World/UnloadSensor, belt=/World/OutfeedBelt,
    source_paths=blank_paths, destination_path=/World/OutfeedBelt,
    pick_target=[0.0,0.18,0.84], drop_target=[0.25,-0.50,0.855],
    planning_obstacles=[...],
    phase_id="phase2")                                   # ← different phase tag
```

**Why `phase_id` is load-bearing here (the multi-phase same-robot capability).**
Both controllers bind the *same* articulation `/World/UR10`. The install routine
tears down prior subscriptions so a fresh controller doesn't double-step the robot
(`pick_place.py:2486-2517`). The subscription attribute is keyed by **both** the
robot tag **and** the phase id (`pick_place.py:2487`):
```python
_ROBOT_TAG = ROBOT_PATH.replace("/", "_").strip("_")
_SUB_ATTR  = "_native_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID
```
and the cross-mode sweep only unsubscribes handles matching **this** robot **and**
this phase (`:2496-2505`, guarded by `_a.endswith("_"+_ROBOT_TAG)`). The design
comment is explicit (`pick_place.py:395-399`):
> *"Same robot can host multiple sequential controllers (phase1 picks, phase2
> places, phase3 transports). Without phase_id, each install would clobber the
> previous one's subscription. Missing phase_id = 'default' (legacy single-PPC)."*

**The `phase_id` gap (honest):** the mechanism makes the two installs *coexist*
without unsubscribing each other — but **coexistence is not sequencing**. There is
no controller-side state machine that says *"finish all of phase1, then start
phase2."* The template fakes the ordering with a blocking `sim_control(step,
step_count=1800)` between the two installs — but the template's own
`failure_modes` flag the fragility (`json:96-101`):
> *"sim_control(step) may not advance controller state machine — dwell step_count
> may need tuning per Hz"* and *"dual setup_pick_place_controller calls share robot
> articulation path — second call may overwrite first controller binding."*

So `phase_id` *scopes the subscriptions* (no aliasing of callbacks), but **the two
phases still race on the single articulation** if phase1 hasn't finished its picks
when phase2 installs. The "repeat 4 times" cadence (4 blanks) compounds it: there is
no per-blank phase loop, just one phase1 (picks all 4 → fixture) and one phase2
(unloads all 4 → outfeed), with a single global dwell — **not** a true
load/dwell/unload *per part*. This is the controller-aliasing-on-multi-phase
limitation in the prompt: `phase_id` prevents *subscription* clobber, not
*execution* interleaving. **`verified_status`** is honest about maturity
(`json:314`): *"build-spec-2026-05-16; form-gate-schema ✓; smoke-test pending"* —
i.e. the multi-phase cycle has **not** been gate-verified.

### Stage 6 — Dynamic gate   **[EXPENSIVE-physics]**

`simulate_traversal_check` with `target_path=OutfeedBelt`, `cube_paths`=4 blanks,
`duration_s=300`, `xy_tolerance=0.1` (`json:71-81`). Multi-cube ANY-rule
(`diagnostics.py:4446`): success = **≥1 blank reaches the outfeed**. Note the
**target is a moving belt**, not a bin — the template flags this as a failure mode
(`json:99`: *"outfeed destination_path is a moving belt … drop_target needs
override if blank must land at specific x"*), so `at_rest` may never trigger as the
belt carries the part. The gate measures *"a part made it through the full
load→dwell→unload cycle to the outfeed,"* which is the right success shape, but the
300 s budget is the most expensive of the three flows — and it's the run the
**unprobed chuck reach** could doom from geometry alone.

### Stage 7 — Diagnose   **[cheap]**

`diagnose_args` (`json:82-95`) pre-wires `robot_path`, `obstacles`
(`CNCMachine/BasePlate`, both belts), `sensor_path=PickSensor`, `robot_base`. A
non-delivery reads as: did phase1 even seat a blank in the fixture (check blank z
near 0.84 mid-run), or did phase2's install clobber phase1 before it finished
(the binding-overwrite failure mode)? The `ctrl:*` records + `plan_fails` localize
load-fail vs unload-fail without re-simulating.

### One-line flow

```
"load blank, open door, wait machining, unload, repeat 4×"
 1. text → LayoutSpec{pick_place, machine_tending, load_wait_unload, 2 conveyors}  [CHEAP]  text_modality.py:213
 2. retrieve → CP-NEW-machine-tender-load-unload (has_machining_dwell, n_conveyors=2)  [CHEAP]
 3. reach_validate → 4 infeed picks (t=0 spawn, conveyor WARNING) + OutfeedBelt; **CHUCK never probed**  [CHEAP, inner-reach blind]  reach_validate.py:70,151
 4. (fix) if chuck unreachable: lower walls / widen fixture / move toward base  [CHEAP arithmetic]
 5. build → UR10 + 2 belts + walled fixture; PHASE1(load,phase_id) + DWELL(step 1800) + PHASE2(unload,phase_id)  [mixed]  pick_place.py:2487
        phase_id scopes SUBSCRIPTIONS (no callback clobber) but NOT execution sequencing  pick_place.py:395
 6. gate → simulate(4 blanks → OutfeedBelt, 300s); success=ANY blank through full cycle  [EXPENSIVE]  diagnostics.py:4446
 7. diagnose → load-fail vs unload-fail vs phase2-clobbers-phase1 (ctrl:* + plan_fails)  [cheap]
```
**Gap summary:** static-eyes probes infeed+outfeed but **not the chuck** (the
tightest, walled, inner reach); `phase_id` de-aliases subscriptions but the two
phases still race on one articulation, there's no per-part load/dwell/unload loop,
and the cycle is **smoke-pending, not gate-verified** (`json:314`).

---
---

## FLOW 3 — AMR logistics + arm depalletize

> *"Drive the AMR to the cell, have an arm take 3 boxes off the pallet it carried."*

**Matched canonical:** **`CP-NEW-forklift-handoff-arm`**
(`workspace/templates/CP-NEW-forklift-handoff-arm.json`). Goal (`json:3`):
*"Forklift→arm depalletize handoff: a wheeled-robot proxy ('Forklift') … carrying a
Pallet slab loaded with 3 workpiece cubes … signals 'ready' via handoff:state.
A stationary Franka depalletizes each item from the pallet → outfeed conveyor …
Forklift Nucleus asset is unavailable; this canonical uses the wheeled-robot+raised-Xform
proxy."* (Closest "AMR" sibling is `CP-NEW-cart-handoff-amr` / `CP-NEW-amr-pickup-handoff`,
but those are *navigate*-success; this one is *pick_place*-success — the arm drives
the outcome, which matches "have an arm take 3 boxes off.")

The **distinct capability**: **mobile base + manipulation** coordinated in one scene
via a handoff handshake. This is where the **mobile-manipulation gap** is most
visible — there is no fused mobile-manipulator primitive; the arm and the AMR are
**two separate robots** with the pallet **hand-wired** between them.

### Stage 1 — Intake   **[CHEAP-static]**

`text_modality`. "drive the AMR to the cell" → navigate signal; "arm take 3 boxes
off the pallet" → depalletize/pick_place. The template resolves the tension by
declaring `pattern_hint="pick_place"` with `uses_mobile_pallet_source=True` and
`uses_handoff_signal=True` (`json:148-157`) — the success criterion is
**arm-driven** (items on outfeed), with the AMR navigate as a structural feature
stacked on top (`json:19`: *"Success criterion is workpiece-delivered-to-final-destination
… the forklift navigate + handoff handshake are structural features stacked on top
of the depalletize base pattern."*).

### Stage 2 — Retrieval   **[CHEAP-static]**

Stage-1 filter on the unusual combo `uses_mobile_pallet_source +
uses_handoff_signal + n_robot_stations=2` (`json:150-157`) plus tags
`isaac:robot.mobile.wheeled` + `isaac:topology.forklift_to_arm_depalletize` +
`isaac:multi_robot.handoff` (`json:159-169`) is a near-unique shape →
`CP-NEW-forklift-handoff-arm` tops over the navigate-success AMR siblings (the
template's `thoughts` §2-3 explicitly disambiguate from `CP-NEW-cart-handoff-amr`
and `CP-NEW-vision-depalletize`, `json:20-21`).

`role_defaults` (`json:238-357`):
- **Forklift** (wheeled_robot proxy) start `[0.55, 0, 0.05]`, depot `[-1.0, 0]`,
  raised `Platform` Xform at offset `[0,0,0.45]` (`json:239-260`).
- **Pallet** slab at `[0.55, 0, 0.475]`, scale `[0.30,0.20,0.025]` → top z=0.50
  (`json:276-288`).
- **3 items** at world `x ∈ {0.45, 0.55, 0.65}, y=0, z≈0.53-0.54` on the pallet top
  (`json:289-317`). (Note: the `code` body uses `0.540` and item x `{0.45,0.55,0.65}`,
  `json:30`; the `role_defaults` say `0.53` — a minor authored/code drift.)
- **Franka** arm at `[0,0,0.75]` (`json:261-275`), reach ~0.85 m.
- **Outfeed** static cube fixture at `[0,-0.50,0.78]`, drop pose `[0,-0.50,0.85]`
  (`json:318-335`).
- **HandoffMarker** at `[0.6,0,0.55]` (`json:336-343`); **Depot** at `[-1.0,0]`.

### Stage 3 — Static reach: is the pallet reachable after the AMR parks?   **[CHEAP-static]**

This is *the* question for mobile manipulation: the arm's reachability **depends on
where the AMR parked**. `reach_validate.py` reads `simulate_args` (`json:100-109`):
```json
"target_path": "/World/Outfeed",
"cube_paths": ["/World/Item_1","/World/Item_2","/World/Item_3"],
"duration_s": 240, "xy_tolerance": 0.18
```
- **Picks probed:** the 3 items at their pallet poses `x ∈ {0.45,0.55,0.65}`
  (the `code` positions). From the Franka base at `[0,0,0.75]`, these are
  0.45–0.65 m horizontal — **inside** the 0.85 m reach, so the *near/mid* items
  probe REACHABLE.
- **The far-corner reach is the documented risk.** The template's `thoughts` §6
  (`json:24`) and `failure_modes` (`json:130`) call out that with the pallet at the
  *role_defaults* x=1.0 layout, `Item_3` at world x=1.10 is **1.10 m from the base —
  outside the 0.85 m Franka reach**, so *"native target_source may reject the IK for
  Item_3 at build time."* The `code` body uses a closer pallet (x=0.55), pulling the
  far item to x=0.65 (reachable) — so the *as-coded* scene is reachable, but the
  *parameterized* layout is on the edge. The reach probe is what tells you which
  side of the edge a given pallet-park pose lands on.

**The mobile-manipulation gap (honest, and the crux of this flow):** the reach
probe validates the arm's picks **against the pallet at its authored static pose** —
but **nothing validates that the AMR actually parked there.** The pallet "rides on
the forklift" by **static co-placement, not a FixedJoint** (`json:22`, `json:129`):
> *"differential-drive proxies don't expose a real forks-prismatic-joint … the
> pallet is co-placed above the raised /World/Forklift/Platform Xform and stays put
> by friction."*

And the AMR **starts already at the handoff zone** (`json:23`: *"the forklift starts
already AT the handoff zone in this canonical to keep the canonical short"*) — the
only `navigate_to` is the **departure** to depot *after* the depalletize
(`json:30`, end of `code`). So "drive the AMR to the cell" is **not actually
simulated as an arrival**; the scene is authored with the AMR already parked. There
is **no `setup_amr_with_manipulator` tool** — confirmed: `grep -rn
setup_amr_with_manipulator service/` returns **nothing** (only an
`advanced_user_sim.py:61` test-axis label "mobile manipulation"). The arm-on/near-AMR
relationship is **hand-wired**: a `create_wheeled_robot` (`robot.py:1517`
`_gen_create_wheeled_robot`), a separate `robot_wizard(franka)`, a `Pallet` cube
co-placed by `set_attribute(xformOp:translate)`, and a `setup_robot_handoff_signal`
(`robot.py:6037`) that just toggles a USD `handoff:state` attribute
(`placed`→`complete`) with **no polling** (`json:26`: *"The handoff toggle inside
the canonical is unconditional (no polling); a real controller would gate the
depalletize loop on state=='placed'."*).

So: **static-eyes CAN answer "is the pallet reachable after the AMR parks"** — but
only because the park pose is *baked*, not driven. If a real navigate-IN were added,
the park pose would be the AMR's *final odometry*, and the reach probe would need to
run **after** navigation settles, against the **then-current** pallet world
transform — which the current pipeline does not do. **[gap: no fused
mobile-manipulator; AMR park pose is authored not navigated; pallet rides by
co-placement not a joint; reach is validated against a static pallet, so a real
arrival-then-pick is unverified.]**

### Stage 4 — Fix loop   **[CHEAP-static]**

The template *gives* the fix directions in `failure_modes` (`json:130`): if a
far item is out of reach, **move the pallet closer** (pallet x=0.85 instead of 1.0)
**or swap to a UR10** (reach 1.30 m). Both are arithmetic edits to `role_defaults`
(`pallet.position`, `static_arm.class`) — decided from the per-item reach verdict,
no sim. For the mobile case specifically, the static fix is to **set the AMR park
pose** such that the pallet lands in the arm's dense annulus — a layout decision the
reach probe scores directly.

### Stage 5 — Build: hand-wired mobile-manipulation   **[mixed]**

`execute_template_canonical` renders `code_template` (`json:358`). The sequence
(`json:30`):
```
Ground / Table / set_physics_scene_config(CPU, MBP)
robot_wizard(franka, /World/Franka, [0,0,0.75])                     # the manipulator
create_wheeled_robot(/World/Forklift, differential, wheel_r=0.05, wheel_base=0.20)  # the base
set_attribute(/World/Forklift, xformOp:translate, [0.55,0,0.05])    # PARKED pose (authored, not driven)
setup_nav_robot(/World/Forklift, /forklift/cmd_vel, /forklift/odom)
create_prim(/World/Forklift/Platform, Xform, [0,0,0.45])           # raised "forks" — visual only
create_prim(/World/Pallet, Cube, [0.55,0,0.475])                   # CO-PLACED, no FixedJoint to forklift
3× create_prim(Item_i) + 4 physics APIs
create_prim(/World/Outfeed, [0,-0.50,0.78])                        # static drop fixture
create_prim(/World/Depot, [-1.0,0,0.025])
setup_robot_handoff_signal(/World/HandoffMarker, [0.6,0,0.55], robot_a=Forklift, robot_b=Franka)
set_attribute(/World/HandoffMarker, handoff:state, "placed")        # unconditional toggle (no poll)
prim_exists(/World/Forklift); get_world_transform(/World/Pallet)    # pre-checks
3× apply_physics_material(rubber) + bulk_set(sleepThreshold=0, mass=0.1)
setup_pick_place_controller(
    robot=/World/Franka, target_source="native",
    source_paths=[Item_1,Item_2,Item_3], destination_path=/World/Outfeed,
    drop_targets={Item_1:[0,-0.5,0.85], Item_2:[…], Item_3:[…]},
    end_effector_offset=[0,0.005,0])                                # native Franka path
set_attribute(/World/HandoffMarker, handoff:state, "complete")      # fires BEFORE last item lands (race)
navigate_to(/World/Forklift, [-1.0,0.0], planner="direct")          # the ONLY real navigation: departure
```

Two build-time honesty notes the template self-flags:
- **Handoff race** (`json:132`): `set_attribute("complete")` + `navigate_to` fire
  *immediately* after `setup_pick_place_controller` returns — but the controller is
  **async** (runs over many physics ticks), so the forklift's `handoff:state` flips
  to `complete` and it departs **before the last item lands on the outfeed**. *"A
  real controller would poll item-on-outfeed state."*
- **Forklift is a Jetbot-shaped primitive** (`json:135`): `create_wheeled_robot` at
  an empty path synthesizes a Jetbot-like shape, not a forklift mesh — *"semantic-only
  (proxy for footprint), not visually accurate"*; the proper backing
  (`warehouse_with_forklifts.usd`) is a `nucleus_only_asset` blocker.

`verified_status` (`json:137`): *"drafted-2026-05-16; form-gate-schema ✓;
function-gate ⏳"* — i.e. **the dynamic gate has never confirmed this one**; it's a
draft with a passing *schema* check only.

### Stage 6 — Dynamic gate   **[EXPENSIVE-physics]**

`simulate_traversal_check` with `target_path=Outfeed`, `cube_paths`=3 items,
`duration_s=240`, **`xy_tolerance=0.18`** (`json:100-108`). The generous 0.18 m
tolerance is deliberate (`json:28`): the outfeed surface is 0.40×0.30 m and 3 items
may stack loosely. Multi-cube ANY-rule (`diagnostics.py:4446`): success = **≥1 item
on the outfeed**. The 240 s budget covers all 3 depalletize cycles. Crucially, the
gate scores **only the arm's deliveries** — the AMR's departure-navigate is *not*
graded (consistent with the arm-driven success criterion), so a forklift that drives
off mid-cycle (the race) doesn't fail the gate as long as the arm seated an item
first.

### Stage 7 — Diagnose   **[cheap]**

`diagnose_args` (`json:110-125`) wires `robot_path=Franka`, `obstacles`
(Pallet, Forklift, Outfeed), plus `handoff_path`, `forklift_path`, `depot_path`. A
non-delivery localizes as: far-item IK reject (the documented reach failure → static
fix: move pallet / swap arm), or the held item knocked the pallet (Pallet is in the
obstacle set), or the forklift departed early and the pallet slid (co-placement +
race). The `with_contacts` re-step reports colliding pairs without a full re-sim.

### One-line flow

```
"drive AMR to cell, arm takes 3 boxes off the pallet it carried"
 1. text → LayoutSpec{pick_place, mobile_pallet_source, handoff_signal, 2 stations}  [CHEAP]  text_modality.py:213
 2. retrieve → CP-NEW-forklift-handoff-arm (forklift_to_arm_depalletize, multi_robot.handoff)  [CHEAP]
 3. reach_validate → 3 items REACHABLE from Franka @ pallet's AUTHORED pose; far-corner is the edge  [CHEAP]  reach_validate.py:70
        **but AMR park pose is baked, not navigated — arrival-then-pick is unverified**
 4. (fix) far item out of reach → pallet x→0.85 OR swap Franka→UR10 (template gives both)  [CHEAP arithmetic]  json:130
 5. build → robot_wizard(franka) + create_wheeled_robot(forklift) + Pallet CO-PLACED (no joint)
        + handoff toggle (no poll) + native PPC; navigate_to = departure ONLY  [mixed]  robot.py:1517,6037
        **NO setup_amr_with_manipulator — arm+base hand-wired**
 6. gate → simulate(3 items → Outfeed, 240s, xy_tol=0.18); success=ANY item on outfeed; AMR nav ungraded  [EXPENSIVE]  diagnostics.py:4446
        verified_status: function-gate ⏳ (never gate-confirmed)  json:137
 7. diagnose → far-item IK reject / pallet-slide-from-race / contact pairs (with_contacts)  [cheap]
```
**Gap summary:** no fused mobile-manipulator (`setup_amr_with_manipulator` does not
exist); the AMR **arrival** isn't simulated (it starts parked, only departs); the
pallet rides by **co-placement, not a FixedJoint**; the handoff is an unconditional
toggle with a **departure race**; and `function-gate ⏳` — static-eyes validates the
arm's picks against a *static* pallet, but a real *navigate-then-depalletize* is
unverified.

---
---

## Cross-cutting: where static-eyes saves the gate, and where it can't

| Flow | Static-eyes verdict on the as-shipped scene | Saves the gate? |
|---|---|---|
| Palletizer (companion doc) | drop column behind base probes **0/3 UNREACHABLE** | **Yes** — rejects a doomed 240 s sim |
| 1 Inspect-reject | 4 green picks + PassBin REACHABLE | **Partly** — reject lane (Cube_3/RejectBin) **never probed**; routing correctness is a 2nd gate |
| 2 CNC machinist | infeed picks (t=0, conveyor WARNING) + outfeed REACHABLE | **Partly** — the **chuck** (inner, walled reach) **never probed**; multi-phase race unverified |
| 3 AMR + arm | 3 items REACHABLE from arm @ authored pallet pose | **For the picks, yes** — but AMR **arrival** isn't simulated; pallet is co-placed not jointed |

**The unifying lesson.** `reach_validate.py` is only ever as good as
`simulate_args.cube_paths` + `target_path` — it probes **exactly the picks and the
one destination the template declares**, plus a conveyor WARNING. Every gap above is
the same shape: **a critical reach target (the reject bin, the chuck, the
post-navigation pallet pose) is not in `simulate_args`, so the cheap probe is blind
to it and the expensive gate inherits the blind spot.** The cheapest, highest-leverage
fix across all three is to **widen `_reach_probe_extra_paths`** to include the inner
targets (RejectBin, CNCMachine/BasePlate) and to **re-probe after any navigation
settles** — turning a static blind spot into a static reject, before any 180–300 s
physics run.

### Honest maturity ledger (don't overclaim)

| Template | `verified_status` | Gate-confirmed? |
|---|---|---|
| `CP-NEW-inspect-reject` | smoke-test ✓ 1/1 (52 s), vision-gated routing (`json:258`) | pass-lane only; **reject path unverified** |
| `CP-NEW-machine-tender-load-unload` | build-spec; form-gate-schema ✓; **smoke-test pending** (`json:314`) | **No** — multi-phase cycle not gated |
| `CP-NEW-forklift-handoff-arm` | drafted; form-gate-schema ✓; **function-gate ⏳** (`json:137`) | **No** — draft, never function-gated |

All three are **drafts or smoke-only**; none is a triple-perfect function-gate pass.
The traces describe the *intended* end-to-end flow and the *real* plumbing
(`color_routing`, `phase_id`, the handoff toggle), with each gap marked where the
capability is a stub, a shortcut, or unverified.
