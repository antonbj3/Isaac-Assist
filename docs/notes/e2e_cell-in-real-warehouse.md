# E2E trace — `cell-in-real-warehouse`

**Scenario id:** `cell-in-real-warehouse`  **Tier:** T6  **Robot:** ur10  **Task:** palletize-in-env
**Persona:** production engineer
**Request (verbatim):** *"drop a UR10 palletizing cell into the real `full_warehouse.usd` environment next to a rack"*

Generated 2026-06-09. Every file:line, asset path, and tool-existence claim below was confirmed by
`grep`/`ls` against the live repo + on-disk Isaac 5.0 assets. Where a template is a **draft** or a tool
is **missing**, it is called out — nothing is assumed to work.

---

## TL;DR — the honest verdict up front

- **The literal request is not buildable today as stated.** No template in the 504-file library references
  the real `full_warehouse.usd` env, and the pipeline's collision/planning model **cannot ingest** a 6.7 MB
  composed env mesh — cuRobo obstacles are per-prim **world-bbox AABB cuboids**, not meshes
  (`pick_place.py:4972` "*transform USD prims' world-bboxes to BASE frame cuboids*", `:5001`
  `_sibling_keepout_cuboids`). So "the real warehouse" collapses to either one giant bounding box or nothing.
- **The closest real template is `CP-NEW-palletizer-layer-stack.json`** — and it is a **draft**
  (`verified_status: "drafted-2026-05-16 … form-gate ⏳; function-gate ⏳"`, **both gates unrun**), and it
  builds its "warehouse" out of **primitive `Cube`s on a bare floor** — there is no environment at all.
- **The capability the request needs — "drop an authored cell into a *referenced* real environment, snapped
  next to a named rack, and validate it there" — does not exist.** Four tools are confirmed missing
  (`grep` = 0 hits): `place_on_shelf` / `rack_place`, `snap_next_to` / `place_next_to`,
  `setup_amr_with_manipulator` (not needed here but the same gap class), and any
  `validate_scene_in_env` / `place_cell_in_environment`.
- **The static-eyes pre-filter (`scripts/qa/scene_validate.py`) would catch the most likely failure cheaply:**
  the rack is solid, so a cell snapped flush against it puts the pallet (place target) or infeed cubes
  **outside the UR10's 1.30 m reach** or **inside the rack volume** → `REACH` / `TARGET_REACH` /
  `INTERPENETRATION` violation, **before** the expensive 240 s physics gate ever runs.

---

## Roles & legend

- **[USER]** — the production engineer typing / clicking.
- **[LLM]** — Claude (this assistant) acting for the user inside Isaac Assist: tool-calling, codegen, reasoning.
- **[SYSTEM]** — the service / Kit RPC / handlers / gates executing deterministically.
- **[CHEAP-static]** — geometry/reach/fit reasoning, no physics stepping (ms–seconds; `scene_validate.py`
  does a ~2.5 s passive settle but **no controller sim**).
- **[EXPENSIVE-physics]** — full controller + cuRobo + PhysX play, 90–240 s of stepping (`gate_one.py` →
  `simulate_traversal_check`).

---

## The target scene (what "done" means)

A UR10 palletizing cell — UR10 on a 0.75 m pedestal, infeed conveyor, a 0.70×0.50 m pallet, 6× 0.10 m boxes,
a pick proximity sensor — **positioned inside `full_warehouse.usd`, on the floor, beside one of the warehouse's
pallet racks**, with the arm picking boxes off the conveyor and laying a 2×3 layer on the pallet. The cell
geometry is exactly `CP-NEW-palletizer-layer-stack`; the **new** part is "*in the real env, next to a rack.*"

Assets all confirmed on disk:
- Env: `…/Isaac/5.0/Isaac/Environments/Simple_Warehouse/full_warehouse.usd` (6,739,907 bytes) ✓
- Racks: `…/NVIDIA/Assets/ArchVis/Industrial/Racks/RackLarge_A1..A9.usd` ✓ (also baked into the env)
- Robot: `…/Collected_Robots/ur10.usd` ✓

---

## NUMBERED NARRATIVE

### 1. [USER] [CHEAP-static] — states the goal
> "Drop a UR10 palletizing cell into the real `full_warehouse.usd` environment next to a rack."

A T6 ("cell-in-real-environment") ask: it is *not* a bare-floor canonical — it explicitly wants the **shipped
warehouse env** as the backdrop and a **named, existing rack** as the spatial anchor.

### 2. [LLM] [CHEAP-static] — retrieve the nearest template
The LLM searches the library for a palletizing cell. `grep -il palletiz` over `workspace/templates/` returns
`CP-NEW-palletizer-layer-stack.json` and `CP-NEW-palletizer-mixed-sku.json`. The layer-stack one is the
structural match (UR10, conveyor infeed, pallet, grid placement; `intent.structural_tags` include
`isaac:robot.ur10`, `isaac:industry.palletizing`, `isaac:placement.grid_2x3`).
**Template match: `CP-NEW-palletizer-layer-stack.json`.**

### 3. [LLM] [CHEAP-static] — read the template and notice it is a DRAFT
The LLM opens the template. Two load-bearing facts:
- `verified_status`: `"drafted-2026-05-16-patched-r-a-fix-2; rebuilt-2026-05-28 …; form-gate ⏳; function-gate ⏳"`
  → **never passed either gate.** This is an unverified draft, not a stable canonical.
- The scene is **all `create_prim(... "Cube")` on `/World/Ground`** — `Table`, `ConveyorBelt`, `Pallet`,
  6 `Box_*`, `PickSensor`. **There is no environment.** The "warehouse" is implied, never instantiated.

Honest read: the retrieved template gives the **cell**, but contributes **nothing** toward "the real env."

### 4. [LLM] [CHEAP-static] — confirm whether ANY template puts a cell in the real env
The LLM greps the whole library:
```
grep -lE "Environments/Simple_Warehouse|full_warehouse\.usd|Isaac/Environments" workspace/templates/*.json
→ (no matches)
```
**Zero templates reference the real environment USD.** Even the warehouse-flavoured ones fake it:
`CP-NEW-occupancy-map-nav.json` builds "*Warehouse shelf racks*" as four `create_prim` `Cube`s with a comment,
not a single `add_reference`. The only template that `add_reference`s a `warehouse.usd` is **`AD-05.json`**,
and that is an **intentional failure-mode** template whose own code says
`# → FileNotFoundError: add_reference: asset not found: '/home/alex/scenes/warehouse.usd'`.
**Conclusion: the "cell-in-real-env" pattern has no precedent in the library. The LLM is composing new.**

### 5. [LLM] [CHEAP-static] — confirm `add_reference` itself exists (the one primitive that does)
```
grep "add_reference" handlers/scene_authoring.py
→ scene_authoring.py:932 def _gen_add_reference(args)   ;  :6156 codegen["add_reference"] = …
```
`add_reference` **EXISTS** and the codegen pattern is real — templates `CP-80/81/83/84/85` already use
`add_reference(prim_path="/World/UR10", reference_path="…/Collected_Robots/ur10.usd")` to spawn the UR10.
So the LLM *can* `add_reference` the env USD. The question is whether anything downstream can cope with it.

### 6. [LLM] [CHEAP-static] — search for the tools the request actually needs, and find them MISSING
For "drop a cell *next to a rack*" the LLM looks for spatial-anchor + env-fit tooling. `grep` over every
handler `register`/codegen/data map and `tool_schemas.py` (~407 tools) returns **0 hits** for all of:

| Needed capability | Tool name(s) searched | Hits | Status |
|---|---|---|---|
| Snap the cell beside a named rack | `snap_next_to`, `place_next_to`, `align_to_rack` | 0 | **MISSING** |
| Place payload into a rack bay/level | `place_on_shelf`, `rack_place`, `shelf_place` | 0 | **MISSING** |
| Find clear floor beside the rack | `find_free_floor_space`, `env_floor_query` | 0 | **MISSING** |
| Validate the cell *inside* the env | `validate_scene_in_env`, `place_cell_in_environment`, `instantiate_in_environment` | 0 | **MISSING** |
| Mobile-manipulator stand-up (adjacent gap class) | `setup_amr_with_manipulator` | 0 | **MISSING** (per `asset_templates_warehouse.md` §2) |

So the LLM must **hand-compute** the cell's world offset next to the rack from bounding boxes
(`get_bounding_box` / `get_world_transform` exist) and `teleport_prim` the whole cell — there is **no
rack-aware placement primitive.** This is the central tool gap.

### 7. [LLM] [CHEAP-static] — author the composed plan (codegen)
The LLM emits code that, conceptually:
1. `add_reference(prim_path="/World/Env", reference_path="…/Simple_Warehouse/full_warehouse.usd")` — spawn env.
2. `get_bounding_box("/World/Env/…/Rack…")` — read a rack's world AABB to anchor against. **Caveat:** rack prim
   paths inside `full_warehouse.usd` are not known a-priori; the LLM would have to traverse the stage to find
   a rack, and there is **no tool that enumerates "the racks in this env"** (another facet of the missing
   `env_floor_query`).
3. Re-emit the `CP-NEW-palletizer-layer-stack` body, but **offset every prim** (`UR10`, `Table`, `Pallet`,
   `ConveyorBelt`, `Box_*`, `PickSensor`) by a world translation that places the cell on the floor flush
   beside the chosen rack — done by hand-adding the offset into each `position=`, since `snap_next_to` is missing.
4. `setup_pick_place_controller(robot_family="ur10", target_source="curobo", planning_obstacles=[…])`.

**Honest flag — the planning_obstacles trap:** the natural instinct is to add `"/World/Env"` to
`planning_obstacles` so cuRobo avoids the rack. But the obstacle builder transforms each prim's **world-bbox
into a single BASE-frame cuboid** (`pick_place.py:4972`, `:5001-5030` `_sibling_keepout_cuboids` →
`ComputeWorldBound(...).ComputeAlignedRange()`). Referencing the whole env yields **one enormous AABB cuboid**
spanning the entire warehouse — which would make the arm's collision world a solid block and **every plan fail**.
The LLM must instead pass only the **specific rack prim** (still just its AABB box) — acceptable for a boxy
rack, but it means the cell must sit **outside** that AABB, i.e. genuinely beside the rack, not overlapping it.

### 8. [SYSTEM] [CHEAP-static] — instantiate the canonical (build, no physics)
`canonical_instantiator.execute_template_canonical(tpl)` runs the codegen against a fresh Kit stage
(`omni.usd … new_stage()`), returning `{"instantiated": True/False, "errors": …}`. The env `add_reference`
resolves (the 6.7 MB USD loads), the cell prims are created at their offset poses.
**Risk at this step:** if the offset math is wrong, the cell prims can spawn **inside** the rack mesh →
no build error (USD doesn't care), the problem only surfaces in the next two checks.

### 9. [SYSTEM/LLM] [CHEAP-static] — the STATIC-EYES PRE-FILTER (`scripts/qa/scene_validate.py`)
This is the cheap gate that should run **before** spending 240 s of physics. It builds + does a ~2.5 s
**passive** settle with the arm **parked** (it unsubscribes the pick controller, `scene_validate.py:71-77`),
then reads **actual post-settle geometry** and checks three classes. Mechanics that matter here:

- **Robot detection** (`:128-150`): traverses all prims; UR10 detected by name/ArticulationRoot →
  `family="ur10"`, `reach = 1.30 m` (`ROBOT_REACH`, `:33`), `base = robot prim transform origin` (`:120`).
  The warehouse env adds hundreds of rack/shelf/box prims — none match the arm heuristic, so they're correctly
  ignored as robots (and humans/legged bots are explicitly dropped, `:152-156`).
- **REACH** (`:262-286`): each box's post-settle center vs UR10 base; flags if `dist > 1.30 m` (and no belt
  carries it in, `belt_reachable`) or `dz` outside the UR10 z-window `[-0.15, +0.60]` (`ZLO["ur10"]=-0.15`).
- **TARGET_REACH** (`:289-309`): the **pallet top-center** must be within 1.30 m of the base, else
  "*arm can pick but never place*". This is the check most likely to fire for "next to a rack": if the engineer
  (or the LLM's offset) snaps the cell so the pallet ends up behind/beside the rack out at >1.30 m, this fires.
- **INTERPENETRATION** (`:311-320`): pairwise box AABB overlap (>50% + 2 cm floor) — catches boxes clumped
  or, with the rack included as a pick by accident, a box buried in the rack.

**This is where the env-fit problem is caught cheaply.** A rack is a solid ~1 m-deep volume; "flush next to a
rack" naturally pushes either the pallet or the infeed conveyor out past the 1.30 m shell, **or** the cell
overlaps the rack AABB. `scene_validate.py` prints a `TARGET_REACH:` / `REACH:` violation and exits non-zero —
**no expensive sim is spent.** The fix is a static nudge (move the cell's anchor offset so pallet+conveyor sit
inside the reach shell *and* clear of the rack AABB), then re-run the cheap check. Iterate here, not in physics.

> **Honest limitation of the pre-filter for THIS scenario:** `scene_validate.py` does **not** check
> "is the cell *inside the rack mesh*" beyond pick-object AABB overlap — it has **no whole-cell-vs-env
> collision pass** (it only pairwise-overlaps declared *pick objects*). A UR10 pedestal clipping a rack
> upright, or the conveyor stand intersecting a shelf leg, would **pass** the static-eyes filter and only
> surface as a cuRobo plan-fail or a visible clip in the gate/GUI. That whole-cell-fit check is the
> `validate_scene_in_env` tool that does **not exist** (step 6).

### 10. [SYSTEM] [EXPENSIVE-physics] — the FUNCTION GATE (`scripts/qa/gate_one.py` → `simulate_traversal_check`)
If static-eyes is clean, the function gate builds, settles, then **plays the full controller** for
`simulate_args.duration_s = 240 s` (`CP-NEW-palletizer-layer-stack` declares 240 s) with
`cube_paths = [Box_1..Box_6]`, `target_path = /World/Pallet`, `xy_tolerance = 0.08`.

**Gate success-criterion (the OUTCOME)** — from `diagnostics.py`:
- This is a **multi-cube** scene (6 boxes), so (`diagnostics.py:4447`):
  `success = bool(delivered) and upright_ok` — i.e. **ANY one box** landed inside the pallet bbox (±0.08 m XY),
  above the pallet floor (`above_floor`), at rest (`speed < rest_speed`), with the primary cube upright
  (`upright_dot ≥ upright_tol`). (Single-cube scenes need the one cube delivered; multi-cube is lenient-ANY.)
- The summary line: `GATE success=True/False` (`gate_one.py:88`). `success=True ⇒ gate PASS`.

**Honest expectation for THIS template at the gate:** even on a bare floor, this draft has **never been
gate-run** (`function-gate ⏳`) and carries the **UR10 suction-grip + transit-swing** risk that the whole UR10
cluster shares (see MEMORY: grip-not-holding, 360-spin, late-release). In the **real env**, two extra hazards
stack on top: (a) cuRobo planning around the rack AABB cuboid can force long joint sweeps / plan-fails near the
reach boundary, and (b) any pedestal/rack clip from step 9's blind spot manifests as a plan-fail. So a realistic
first-run outcome is **gate FAIL or stochastic** until the cell offset is tuned and the UR10 grip caveats are in
play. The gate measures **delivery**, and the controller — not the scene — is the usual UR10 bottleneck.

### 11. [LLM] [CHEAP-static] — diagnose on failure (read data, don't guess)
On a gate FAIL the LLM runs the read-only diagnostic chain (`diagnose_scene_feasibility →
simulate_traversal_check → diagnose_pick_execution`, `diagnostics.py:3531`) which reports
`ctrl:cubes_delivered`, `root_cause ∈ {carried_but_not_delivered, delivered_ok, …}` (`:3505-3515`). This tells
the LLM whether the failure is **reach/fit** (→ re-nudge the cell offset, back to step 9) or **grip/transit**
(→ a UR10 controller caveat, out of scope of scene authoring). This is cheap and must precede any code change.

### 12. [USER] [CHEAP-static] — review & accept
The production engineer inspects the result (screenshot / GUI). Acceptance is **visual + the gate verdict**:
boxes laid on the pallet, cell sitting cleanly beside the rack, arm not clipping the rack. Given the open
items (draft template, missing env-fit tooling, UR10 grip caveats), realistic acceptance is **partial** —
"cell builds in the env and lays at least one box, pending a real `place_next_to` + whole-cell env-collision
validator for production trust."

---

## Where the cheap pre-filter saves the expensive gate (the key economy)

```
[USER ask] →2 retrieve →3 read(draft) →6 (missing tools) →7 author offset
                                                              │
                                                  8 [CHEAP] build in Kit
                                                              │
                                          9 [CHEAP] scene_validate.py  ←── iterate here
                                       REACH / TARGET_REACH / INTERPEN          (seconds)
                                                   │  clean?
                                          ┌────────┴────────┐
                                       NO │                 │ YES
                              (nudge offset, re-9)           ▼
                                                10 [EXPENSIVE] gate_one 240 s
                                                   success = ANY box on pallet
                                                   + primary upright
```
The `TARGET_REACH`/`REACH` violation in step 9 is exactly the "cell snapped too tight against a solid rack"
failure — caught in seconds of static geometry, so the 240 s physics gate is spent only on a cell that is
already geometrically feasible.

---

## Tool gaps (confirmed missing — `grep` = 0 hits each)

1. **`snap_next_to` / `place_next_to` / `align_to_rack`** — no rack-relative placement primitive; the cell
   offset must be hand-computed from `get_bounding_box`. *This is the literal "next to a rack" capability.*
2. **`place_on_shelf` / `rack_place`** — no rack-bay-aware placement (irrelevant to floor-cell here, but the
   same missing-spatial-anchor family; flagged in `docs/notes/asset_templates_warehouse.md` §2).
3. **`validate_scene_in_env` / `place_cell_in_environment`** — no whole-cell-vs-environment collision/fit
   validator. `scene_validate.py` only AABB-overlaps *pick objects*; a pedestal/conveyor clipping a rack
   upright passes the static filter and is caught only by a cuRobo plan-fail or the human's eyes.
4. **`env_floor_query` / `find_free_floor_space` / rack-enumeration** — no tool returns "the racks in this env"
   or "clear floor beside rack X"; the LLM must traverse the stage blind.
5. **cuRobo env ingestion** — *not a named tool but a capability gap:* `planning_obstacles` are per-prim
   **world-bbox cuboids** (`pick_place.py:4972`/`:5001`), so a referenced 6.7 MB env mesh cannot be a faithful
   obstacle; only a single rack's AABB box can be passed. No mesh/voxel env-collision path for the planner.

## Honesty ledger

- **Template `CP-NEW-palletizer-layer-stack` is a DRAFT** — `form-gate ⏳; function-gate ⏳`, never passed
  either gate; and it builds **no environment** (bare-floor `Cube`s). It supplies the *cell*, nothing else.
- **No library template puts any cell into the real `full_warehouse.usd`** (`grep` = 0). The only `add_reference`
  of a `warehouse.usd` is `AD-05`, an *intentional FileNotFoundError* example.
- **The env USD and racks exist on disk** (verified by `ls`), so the *assets* are real — the *tooling* to place
  and validate a cell against them is what's missing.
- **The UR10 grip/transit caveats** (suction weld-equivalence, transit-swing, late-release) from prior sessions
  apply to the gate outcome and are **unverified for this template** (`motion_controllers.verified: []`).
- **Outcome is therefore "partial / unverified"**, not a clean pass — buildable as a hand-composed offset cell,
  blocked from production-trust by the five tool gaps above.
