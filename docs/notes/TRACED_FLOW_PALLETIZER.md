# Traced Flow — One Palletizer Request, End-to-End

**The point of this document:** make the Isaac Assist pipeline *well-defined* by
following one concrete request through every stage, with real `file:line`
citations, concrete numbers, and a marker at each step of **[STATIC / cheap]** vs
**[DYNAMIC / expensive]**. The headline lesson is **where the static "scene-eyes"
loop catches a layout problem before the expensive physics gate ever runs.**

---

## The request

> A palletizer operator says: *"Build me a UR10 cell that stacks a 2×3 layer of
> boxes from the infeed conveyor onto a pallet."*

Matching canonical: **`CP-NEW-palletizer-layer-stack`**
(`workspace/templates/CP-NEW-palletizer-layer-stack.json`).

---

## Stage 0 — what "well-defined" means here

The pipeline never turns the prompt into free-form English and back. It turns text
into a **typed `LayoutSpec`** (an *intent*), uses that to **retrieve** a verified
canonical, runs a **cheap static check** (reach/constraint) to reject bad layouts,
**builds** the scene by executing the canonical's tool sequence, then runs an
**expensive dynamic gate** (live physics) to confirm delivery, with a **diagnose**
leg to localize failures. Five distinct concerns, five distinct artifacts.

| Stage | Artifact | Cost |
|---|---|---|
| 1 Intake | `LayoutSpec` (intent only) | **STATIC** (regex/LLM, ms) |
| 2 Retrieval | canonical template dict | **STATIC** (embedding query, ms) |
| 3 Static check | per-target REACHABLE/UNREACHABLE | **cheap-ish** (one IK probe per target) |
| 4 Fix loop | adjusted positions | **STATIC** (arithmetic) |
| 5 Build | instantiated USD scene | mixed (scene authoring, no long sim) |
| 6 Dynamic gate | `success: bool` | **EXPENSIVE** (240 s live physics) |
| 7 Diagnose | root_cause + recommendation | cheap (reads recorded state) |

---

## Stage 1 — Intake: text → `LayoutSpec` (intent only)   **[STATIC / cheap]**

**File:** `service/isaac_assist_service/multimodal/text_modality.py`

The text-prompt modality is the producer. It does **not** emit objects or
bindings — only `intent`. From the module docstring
(`text_modality.py:1-24`): *"A text prompt becomes a `LayoutSpec` containing only
`intent` (no objects, no bindings)… objects and bindings remain empty; canonical
template's authored positions become bindings at exec time via code_template
substitution."*

Entry point: `produce_layout_spec_from_text(prompt)` (`text_modality.py:213-245`).
It calls an extractor (rule-based default, LLM optional) and wraps the result:

```python
return LayoutSpec(
    intent=intent,
    source=Source(modality="text", confidence=confidence, ...),
    objects=[],          # text path → no positional objects
    bindings=None,       # filled later from the template's role_defaults
    revision=1,
)
```

### What the extractor produces for our prompt

Rule-based path `extract_intent_rules` (`text_modality.py:186-210`):

- **pattern_hint** — `_detect_pattern_hint` (`:77-83`). "stacks … boxes … onto a
  pallet" — none of the narrow rules fire ("stack" is not a keyword; the
  `pick_place` catchall regex at `:73` matches `pick.{0,15}place` / `move.*bin`,
  not "stack onto pallet"), so it **defaults to `pick_place`** (the documented
  broadest default, `:78-79`).
- **counts** — `_detect_counts` (`:156-170`). "UR10" matches the robot noun-pattern
  (`:160` `(?:robot|franka|ur5e|kinova|arm)` — note "ur10" itself is not in the
  pattern, but "cell"/"robot" phrasing varies; the practical signal is the
  conveyor). "conveyor" matches `:161` → `conveyors=1`. "boxes" is **not** in the
  cube noun-pattern (`:162` `cube|block|workpiece|part`), so `cubes` stays 0.
- **features** — `_detect_features` (`:114-125`). "infeed conveyor" fires
  `uses_conveyor_transport=True` (`_FEATURE_RULES`, `:93-95`). No color/upright/
  footprint/human keywords → those stay False.

Resulting intent (≈):

```
pattern_hint = "pick_place"
counts       = {conveyors: 1}            # boxes/UR10 not keyword-matched
features     = {uses_conveyor_transport: True}
tags         = []
```

The typed shapes are defined in `multimodal/types.py`: `PatternHint`
(`types.py:46-54` — closed enum, discriminated **by simulation success-criterion
shape**, not surface description), `StructuralFeatures` (`:116-148`), `Intent`
(`:187-209`), `LayoutSpec` (`:307-348`).

> If the LLM extractor is wired (`extract_intent_llm`, `text_modality.py:324-350`,
> schema at `:252-304`), it would more reliably emit
> `structural_tags=["isaac:industry.palletizing", "isaac:placement.grid_2x3", …]`
> and `has_grid_placement` — exactly the tags the canonical declares in its
> `intent` block (`CP-NEW-palletizer-layer-stack.json:104-122`). The rule-based
> path is the offline/fallback floor.

---

## Stage 2 — Retrieval: intent → canonical   **[STATIC / cheap]**

**File:** `service/isaac_assist_service/chat/tools/template_retriever.py`

Retrieval is **structural-filter-first, similarity-tiebroken** (spec §8.1).

1. **Stage-1 hard filter** — `filter_templates_by_intent(spec_intent)`
   (`template_retriever.py:507-547`): keep templates whose `intent.pattern_hint`
   equals the spec's (`pick_place`), whose `structural_features` are compatible
   (`_features_compatible`, `:444-486` — spec requires `uses_conveyor_transport`
   ⇒ template must have it; the palletizer template **does**, see
   `CP-NEW-palletizer-layer-stack.json:111`), and whose counts are within
   tolerance (`_counts_compatible`, `:489-504`).
2. **Stage-2 embedding** — among Stage-1 survivors, rank by similarity to the
   **original prompt** (not the fingerprint — R15 fix, `:654-659`) over the
   ChromaDB index built from `goal + thoughts + tools_used`
   (`_build_index`, `:106-154`).
3. **Null-signal guard** — `_spec_is_null_signal` (`:550-598`): a bare
   all-defaults `pick_place` spec bypasses Stage-1 and goes full-corpus, so a
   weak rule-based extraction doesn't over-filter. Our spec has
   `uses_conveyor_transport=True` and `conveyors=1`, so it is **not** null-signal
   and Stage-1 runs.

Either the hard path (`retrieve_with_intent_filter`, `:601-756`) or the soft-boost
hybrid (`retrieve_with_intent_soft_filter`, `:785-880`, env
`MULTIMODAL_TEXT_INTENT=soft`) returns
`[{template, task_id, distance, similarity}, …]`. The palletizer template's `goal`
("Build a 2x3 layer-stack palletizer: a UR10 robot picks uniform 0.10m boxes from
an infeed conveyor and places them in a 2-column × 3-row grid …",
`json:3`) is a near-verbatim match to the prompt → top hit, high similarity.

**If similarity > 0.85**, the orchestrator takes the **hard-instantiate** path
(`canonical_instantiator.py:18-26` docstring): execute the template's verified
tool sequence directly instead of an LLM tool-loop.

### What the matched canonical contains

`CP-NEW-palletizer-layer-stack.json`:

- **roles** (`:123-159`): `primary_robot` (constraints `ur10/ur5e/franka_panda`,
  disambiguator `longer_reach_preferred`), `input_conveyor`,
  `primary_destination` (`platform`/`pallet`), `workpieces` (1–6 boxes).
- **role_defaults** (`:160-300`): concrete authored positions — robot base
  `[0,0,0.75]`, conveyor at `y=0.45`, **pallet at `[0,-0.55,0.775]`** (0.55 m
  *behind* the base), and the six `workpieces` each carrying a baked
  `drop_target`.
- **code_template** (`:301`): the parametric build, with `{{role.field}}`
  placeholders and a `{{#each workpieces}}` loop that spawns each box and fills
  `drop_targets[path] = drop_target`.
- **The 2×3 grid drop targets** (baked at author time from
  `compute_stack_placement(target='/World/Pallet', pattern='grid_2x3', n_items=6,
  cube_size=0.10, spacing=0.12, anchor='top')`, `json:17` thoughts §2 and
  `:228-298`):

  | Box | drop_target [x, y, z] |
  |---|---|
  | Box_1 | `[-0.12, -0.47, 0.875]` |
  | Box_2 | `[ 0.12, -0.47, 0.875]` |
  | Box_3 | `[-0.12, -0.55, 0.875]` |
  | Box_4 | `[ 0.12, -0.55, 0.875]` |
  | Box_5 | `[-0.12, -0.63, 0.875]` |
  | Box_6 | `[ 0.12, -0.63, 0.875]` |

  (2 columns at x = ±0.12; 3 rows at y = −0.47/−0.55/−0.63; all at the single-layer
  drop height z = pallet_top 0.800 + box/2 0.075 = **0.875**.)

`compute_stack_placement` is a **pure-Python, no-sim** geometry tool
(`service/isaac_assist_service/chat/tools/handlers/scene_authoring.py:5454-5631`):
it reads the pallet's world bbox (`ComputeWorldBound`, `:5559-5560`), centers the
grid on `(cx, cy)` (`:5602-5603`), and sets `base_z = target_top_z +
first_cube_size*0.5` for `anchor='top'` (`:5577`). It is a **STATIC** layout
producer — exactly the "compute from numbers" half of the system.

---

## Stage 3 — Static reach check: the cheap pre-filter   **[STATIC, the key step]**

**File:** `scripts/qa/reach_validate.py`

This is the **static "scene-eyes"** step — it catches a layout problem **without
the expensive physics gate**. Run:

```
conda run -n isaac_lab_env python scripts/qa/reach_validate.py CP-NEW-palletizer-layer-stack
```

### What it does (and why it must be LIVE, not a formula)

The validator builds the scene, then probes **each declared target with the
suction cup pointing straight down at the real grasp height** and returns a
per-target REACHABLE/UNREACHABLE verdict the generation pipeline can gate on
(`reach_validate.py:1-34` docstring).

Crucially, the docstring is explicit that a **radius envelope is the wrong model**
(`:21-24`): *"straight-down reachability is non-convex AND conflates kinematics
with scene collision … A radial formula mispredicts; only a probe against the
real scene is correct."*

I verified this concretely. A naive spherical-radius test (`dist ≤ UR10 reach
1.3 m`, the reach constant at `pick_place.py:1380`) says **every** drop target is
in-envelope:

```
Box_1: horiz=0.485 3d=0.501 within R(1.3)? True
Box_3: horiz=0.563 3d=0.577 within R(1.3)? True
Box_6: horiz=0.641 3d=0.653 within R(1.3)? True
```

So a formula would **pass** the layout — a false negative on the real failure.
The actual problem is geometric: the pallet sits **0.55–0.63 m directly behind the
base** at a drop height z = 0.875 that is only **0.125 m above the robot's base
plane (z = 0.75)**. To point the cup *straight down* over a point behind the
shoulder and descend to a box top, the wrist must reach a near-singular
elbow/shoulder branch — and the live IK probe is what discovers there is **no
straight-down solution from the home seed**.

### The probe mechanics

The validator sets builtins flags then builds (`reach_validate.py:88-98`):
`_reach_probe=True`, `_sg_descend_repoint_deg=-90` (points the cup down — because
`ee+Z-down != cup-down` due to `ee_joint rpy=π,-π/2`), and
`_reach_probe_z_off=0.193` (the cup tip sits ~0.193 m below ee, so the probe tests
`ee` at `box_top + 0.193`). It also probes the destination via
`_reach_probe_extra_paths` (`:87`).

The per-target sweep fires on the first physics tick
(`pick_place.py:6911-6950`): for every source path it computes the box top
(`_ztop`, `:6934-6939`), then calls the cuRobo planner **3 times**
(`_plan_to_world_point(...)`, `:6942-6946`) at `[x, y, ztop + 0.193]` with the cup
down, and emits:

```python
_verdict = ("REACHABLE" if _nok == 3 else ("MARGINAL" if _nok >= 1 else "UNREACHABLE"))
# REACH_TGT path=… xy=[x,y] top=Z top@Z=n/3 -> VERDICT
```

(`pick_place.py:6948-6950`). The validator parses these `REACH_TGT` lines
(`reach_validate.py:117-129`) and the **layout verdict is PICK-based**: REACHABLE
iff every probed pick is reachable and none missing (`:144-150`); the
destination's straight-down column is a **WARNING only**, because a drop happens
*above* a container so probing its top column straight-down is a noisy proxy
(`:141-154`).

### The concrete verdict for this layout

A live reach-probe log on disk from a UR10-behind-the-base scene
(`/tmp/reachprobe.log`) shows exactly the predicted signature — drop/place targets
behind the base probe **0/3**:

```
REACH_TGT path=… xy=[-0.500,0.400] top=0.950 top@0.950=0/3 -> UNREACHABLE
REACH_TGT path=… xy=[-0.500,0.000] top=0.950 top@0.950=0/3 -> UNREACHABLE
REACH_TGT path=/World/Bin xy=[0.500,-0.400] top=0.900 top@0.900=0/3 -> UNREACHABLE
```

**Verdict for the palletizer drop column:** the six pallet targets at
`y = −0.47…−0.63` (behind the base, low) probe **UNREACHABLE straight-down** —
`n_ok = 0/3`, no IK solution from the home seed for a cup-down descend. This is
the static catch: *the layout places drop targets the UR10 cannot reach top-down*,
**discovered by one IK probe per target instead of a 240-second physics run.**

> **Necessary, not sufficient** (`reach_validate.py:12-18`): REACHABLE means a
> grasp-pose IK exists from the home seed; it does **not** guarantee the gate
> passes (the multi-segment descend can still fail). And the probe is stochastic
> (cuRobo Halton seeds) — use N-of-M for a stable verdict. But UNREACHABLE here is
> a hard, cheap **reject** signal.

---

## Stage 4 — The fix loop: move the drop column into the envelope   **[STATIC]**

The fix is pure arithmetic on `role_defaults` — **no physics**. The unreachable
column is *behind* the base and *low*. Two levers, both static:

1. **Move the pallet from behind to the side/front of the base**, where the UR10's
   straight-down annulus is dense. E.g. pallet center
   `[0, -0.55, 0.775]` → **`[0.55, 0.0, 0.775]`** (in front) or
   `[0.45, -0.30, 0.775]` (front-right, matching the known-good UR10 bin pose
   `[0.5, -0.3/-0.4]` used across the passing CP-NN set).
2. **Re-run `compute_stack_placement`** with the new pallet center → the six grid
   offsets stay the same shape but recenter on the reachable pallet. The new
   `drop_targets` are written back into `workpieces[*].drop_target`.

**Before → After** (Box_1 as example):

| | pallet center | Box_1 drop_target | reach (cup-down 3-seed) |
|---|---|---|---|
| Before | `[0, -0.55, 0.775]` | `[-0.12, -0.47, 0.875]` | **0/3 UNREACHABLE** |
| After (front) | `[0.55, 0, 0.775]` | `[0.43, +0.08, 0.875]` | expected REACHABLE (front annulus, the CP-69/70/75/79/80/84/85/86 PASS region) |

The loop is: **build → reach_validate → (UNREACHABLE) → recompute positions →
build → reach_validate → REACHABLE → proceed.** Each iteration costs one IK probe
per target, **not** a physics gate. The LLM (or a static auto-resolver) only needs
the per-target `xy` + verdict to know *which* targets to move and *which*
direction (toward the dense front annulus). This is the loop that **saves the
expensive gate**: every UNREACHABLE layout is rejected before any 240 s sim.

> Note: the canonical's own `verified_status`
> (`CP-NEW-palletizer-layer-stack.json:310`) records the *related* fix already
> applied — the UR10 base orientation was reverted from a 90°-Z rotation
> `[0.7071,0,0,0.7071]` to identity `[1,0,0,0]` after "cuRobo plan_pose ValueError
> 30/30" — and notes the form-gate (⏳) and function-gate (⏳) are still pending.
> The pallet-position fix above is the next item in that same chain.

---

## Stage 5 — Build: instantiate the (fixed) canonical   **[mixed]**

**File:** `service/isaac_assist_service/chat/canonical_instantiator.py`

`execute_template_canonical(template)` (`:764-...`):

1. **Choose the path** (`:803-813`): because this template has all three of
   `code_template` + `roles` + `role_defaults`, it takes the **role-based path** →
   `instantiate_role_based_code(template, role_bindings)` (`:741-761`), which calls
   `substitute_role_placeholders(code_template, role_defaults)`
   (`:602-...`). The `{{#each workpieces}}` block (`_expand_each_blocks`, `:400-...`)
   unrolls into six `create_prim` + `drop_targets[path]=...` statements; scalar
   `{{primary_robot.position}}` etc. substitute to Python literals.
   (Text-modality `bindings=None`, so `role_bindings` is None and the **authored
   role_defaults** supply the positions — exactly as the text-modality contract
   promised in Stage 1.)
2. **Capture phase** (`:921-957`): the rendered code is `exec`'d in a **sandbox**
   (`_SAFE_BUILTINS` only, `:106-114`) where every tool name is replaced by a
   **no-op capturer** (`_make_capturer`, `:901-907`) that records
   `(tool_name, kwargs)` into `captured` instead of executing. Statements are
   exec'd one at a time via `ast` so a validation-`raise` in the template body
   doesn't abort the whole capture (`:948-957`).
3. **Dispatch phase**: the captured calls are replayed through the **real**
   `execute_tool_call`, producing the USD scene.

The resulting **tool-call sequence** (from `tools_used`, `json:4-16`, and the
`code_template`):

```
create_prim(DomeLight) / set_attribute(intensity)
create_prim(Ground) + apply_api_schema(PhysicsCollisionAPI)
create_prim(Table) + apply_api_schema
set_physics_scene_config(enable_gpu_dynamics=False, broadphase=MBP)   # CPU determinism
robot_wizard(robot_name="ur10", dest="/World/UR10", pos=[0,0,0.75], orient=[1,0,0,0])
create_conveyor("/World/ConveyorBelt", pos=[0,0.45,0.78], vel=[0.15,0,0])
# {{#each workpieces}} → 6×:
  create_prim(Box_i, Cube, pos=…, size=0.10) + 4× apply_api_schema(Rigid/Collision/Mass/Physx)
  drop_targets[Box_i] = <its grid drop_target>     # the 6 drop targets, baked
bulk_set_attribute(box_paths, sleepThreshold=0.0)
apply_physics_material(box_i, "rubber")
create_prim(Pallet, pos=[0,-0.55,0.775], scale=[0.35,0.25,0.025]) + apply_api_schema
add_proximity_sensor("/World/PickSensor", pos=[0.35,0.45,0.855], size=[0.12]*3)
surface_gripper(robot="/World/UR10", ee_link="/World/UR10/ee_link", force=200)   # UR10 has no gripper
setup_pick_place_controller(
    robot="/World/UR10", target_source="curobo", robot_family="ur10",
    sensor=PickSensor, belt=ConveyorBelt, source_paths=box_paths,
    destination="/World/Pallet", drop_targets=drop_targets,
    planning_obstacles=["/World/Table","/World/ConveyorBelt","/World/Pallet"])
```

The **drop_targets dict** (the 6 grid positions from Stage 2 /
`compute_stack_placement`) is what makes each cube go to a *distinct* grid slot
rather than all to the pallet bbox-center; the controller falls through
`drop_targets[cube] → drop_target → destination_path` per
`tool_schemas.py:3979`. After build, `settle_after_canonical`
(`canonical_instantiator.py:193-...`) restores authored cube positions /
conveyor velocities disturbed by the controller's install-time timeline play.

After hard-instantiate, the **only** tools left in the LLM schema are
verify/inspect/fix tools (`ALLOWED_AFTER_INSTANTIATE`, `:74-103`) — the build
tools are gone; the agent's job collapses to *verify and report*.

---

## Stage 6 — Dynamic gate: live physics confirms delivery   **[DYNAMIC / EXPENSIVE]**

**File:** `scripts/qa/gate_one.py` → handler
`diagnostics.py::_handle_simulate_traversal_check` (`:3920-...`).

```
python scripts/qa/gate_one.py CP-NEW-palletizer-layer-stack
```

`gate_one.py` builds + settles, then calls `simulate_traversal_check` with the
template's **own** `simulate_args` (`gate_one.py:71-80`) — using the template's
`duration_s`, not the grader's fixed 90 s. For this template
(`json:71-83`):

```json
"simulate_args": {
  "target_path": "/World/Pallet",
  "cube_paths": ["/World/Box_1", … "/World/Box_6"],
  "duration_s": 240,
  "xy_tolerance": 0.08
}
```

The gate **plays the timeline for 240 sim-seconds** and samples each cube's world
position (`diagnostics.py:3920-3928`, `4308-4434`). Per cube it evaluates three
criteria (`:4419-4434`):

- `cp_in_xy` — final XY inside the pallet bbox **expanded by `xy_tolerance=0.08`**,
- `cp_above` — final Z ≥ pallet bbox min − `floor_tolerance` (default 0.10),
- `cp_at_rest` — speed < `rest_speed_threshold` (default 0.05 m/s, via the robust
  rolling-window velocity, `:4393-4410`).

`cp_delivered = in_xy AND above AND at_rest`.

### Success criterion for a 2×3 palletize (multi-cube)

`diagnostics.py:4446-4449`:

```python
if len(cube_paths) > 1:
    success = bool(delivered) and upright_ok      # ANY cube delivered
else:
    success = bool(in_xy and above_floor and at_rest and upright_ok)
```

Because `cube_paths` has 6 entries, this is the **multi-cube** rule:
**`success = ANY box delivered to the pallet (in_xy + above_floor + at_rest)`**,
with `upright_ok` (here `require_upright=False`, so always True). This is the
documented lenient multi-cube gate (ANY-delivered) — a deliberate guard against
the gate false-negativing sort/deliver-one-of-many tasks. The richer per-box
breakdown is in `per_cube_status` / `delivered_cubes` / `per_cube_support`
(`:4491-4513`), and the shadow `delivered_ever` field
(`:4451-4455`) catches "delivered then dislodged by the next cycle" — important
for a 6-cube stack where Box_1 can be nudged by Box_6's drop.

This is the **expensive** step. It runs **only if Stage 3 passed** — which is the
whole reason the static reach check exists: a layout whose drop column probes
0/3 UNREACHABLE never reaches this 240 s sim.

---

## Stage 7 — Diagnose: localize a non-seating box   **[cheap, post-run]**

If the gate returns `success=False` (e.g., only Box_1–Box_3 seat, Box_4–Box_6 miss
the far row), the diagnose leg localizes **without re-simulating**.

**`diagnose_task_outcome` / `_handle_diagnose_pick_execution`**
(`diagnostics.py:3344-...`): a *pure read* of the controller's own `ctrl:*` USD
records off the robot prim (`:3368-3378`) — `ctrl:cubes_delivered`,
`ctrl:cycles_attempted`, `ctrl:plan_calls`, `ctrl:plan_fails`,
`ctrl:last_fail_goal`, `ctrl:pick_reject`, `ctrl:graspdiag` — plus a tail of the
plan-fail / grip / settle logs. It maps those facts to a `root_cause` +
`recommendation`. Optionally (`with_contacts=true`, `:3380-3401`) it re-steps the
live scene briefly with a PhysX contact subscription to report colliding pairs
(e.g. `Box_5|Box_4` — grid-slot overlap, the failure mode the template itself
flags at `json:100`: "0.10 m boxes at 0.12 m col-spacing leaves only 0.02 m
clearance").

**`scene_eyes.py`** (the "virtual eyes," `scripts/qa/scene_eyes.py:1-26`) is the
richer probe: a **live-physics time-series at 0.1 s resolution** of the tool pose
(suction cone, full quaternion), **every articulation joint angle**, the
suction **elongation** (follower↔cone gap in mm — the visible "förlängning" / late
grip), and **every cube position**, with **PhysX contacts**. For a non-seating box
it shows *why*: e.g. wrist 360°-spin during transit (branch discontinuity), late
release dropping the box short of the far row, or the held box knocking a neighbor.

The diagnose loop is **cheap** (reads recorded state / a ~2 s contact re-step), and
its output feeds back into either the Stage-4 static fix (move a target) or a
controller-side fix — closing the loop:

```
feasibility(Stage 3) → gate(Stage 6) → localize(Stage 7) → fix → rebuild
```

---

## The whole flow, one line per stage

```
"UR10 cell, stack 2×3 boxes from infeed conveyor onto a pallet"
  │
  1. text_modality.produce_layout_spec_from_text  → LayoutSpec{intent: pick_place,
        conveyor=1, uses_conveyor_transport}  [STATIC]                  text_modality.py:213
  │
  2. template_retriever.retrieve_with_intent_*    → CP-NEW-palletizer-layer-stack
        (Stage-1 structural filter + Stage-2 embedding), sim>0.85       template_retriever.py:601
        template carries roles/role_defaults/code_template + 6 baked drop_targets
        from compute_stack_placement(grid_2x3)  [STATIC]               scene_authoring.py:5454
  │
  3. reach_validate CP-NEW-palletizer-layer-stack → drop column behind base
        (y=-0.47..-0.63, z=0.875) probes cup-down 0/3 → UNREACHABLE     reach_validate.py / pick_place.py:6948
        (radius test would FALSELY pass — non-convex+collision)  [STATIC, the catch]
  │
  4. fix: move pallet behind→front [0,-0.55]→[0.55,0]; recompute grid
        → REACHABLE  [STATIC arithmetic, one IK probe/target — NOT a sim]
  │
  5. execute_template_canonical → role-substitute code_template, sandbox-capture,
        dispatch real tools → UR10 + conveyor + 6 boxes + pallet + sensor +
        setup_pick_place_controller(drop_targets={6 grid slots})        canonical_instantiator.py:764
  │
  6. gate_one → simulate_traversal_check(cube_paths=6, target=Pallet, 240s, xy_tol=0.08)
        success = ANY box delivered (in_xy+above_floor+at_rest)  [DYNAMIC/EXPENSIVE]  diagnostics.py:4446
  │
  7. on fail: diagnose_pick_execution (read ctrl:*) + scene_eyes (live time-series,
        contacts) → root_cause → back to step 4 or controller fix  [cheap]  diagnostics.py:3344
```

**Where the static-eyes loop saves the expensive gate:** Stage 3. The palletizer's
authored drop column is geometrically behind/below the UR10 and probes
**UNREACHABLE straight-down** — a fact a spherical-radius formula misses
(everything is < 1.3 m) but the **live single-IK-per-target probe** catches in
seconds. Rejecting that layout *before* Stage 6 avoids a 240-second × N-iteration
physics sim that was doomed from the geometry alone.
