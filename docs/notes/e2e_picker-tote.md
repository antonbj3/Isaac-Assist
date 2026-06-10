# E2E trace — [picker-tote] Franka bin-pick, no fixed list

- **Scenario id:** picker-tote
- **Tier:** T1
- **Robot:** franka
- **Task:** bin-pick (tote -> bin, loose items, no fixed list)
- **Persona:** warehouse picker
- **One-sentence request:** "Franka picks loose YCB items out of a tote into a bin, no fixed list"
- **Matched template:** `workspace/templates/CP-NEW-bin-picking-random-pose.json`
  (found via `grep -ilE "tote|bin.?pick|loose|no.?fixed.?list" workspace/templates/*.json`; this is the **only** library template that combines `franka` + bin-to-bin + runtime candidate discovery with **no pre-built source list** — `intent.structural_features.has_runtime_candidate_discovery: true`, template line 114).
- **Gate driver:** `scripts/qa/gate_one.py` -> `simulate_traversal_check` (`service/.../handlers/diagnostics.py:3920`).
- **Static-eyes pre-filter:** `scripts/qa/scene_validate.py` (standalone QA script — REACH / INTERPENETRATION / SUPPORT, post-settle, **no physics rollout**).

> **HONESTY HEADLINE (read first).** The persona asks for *loose **YCB** items*. The matched template spawns **6 identical 0.05 m `Cube` prims** (template lines 209-288), **not YCB meshes**. There is **no YCB / mesh-import tool in the entire tool surface** (confirmed missing below). So the closest real capability is "Franka discovers and bin-picks unknown-pose **cubes** out of a tote", and the YCB-specific part of the request is **unsatisfiable today**. The template's own `verified_status` ends with `function-gate ⏳` (template line 298) — i.e. it is a **draft whose function-gate has never been confirmed to pass**.

---

## Legend

- `[USER]` warehouse-picker action · `[LLM]` model acting for the user · `[SYSTEM]` harness / Kit / gate
- `[CHEAP-static]` no physics rollout (template fill, prim authoring, scene query, AABB read, static-eyes) · `[EXPENSIVE-physics]` PhysX settle and/or the cuRobo + simulated traversal gate

---

## Numbered narrative (user-action steps numbered; LLM/SYSTEM sub-steps lettered)

### 1. `[USER]` — submit the request  ·  `[CHEAP-static]`
The picker types: *"Franka picks loose YCB items out of a tote into a bin, no fixed list."*
Implicit constraints the user expects honoured: **unknown set of items** (no enumerated SKU list), **unstructured tote** (random poses), **bin destination**, **YCB objects** (real grocery meshes).

  - 1a. `[LLM]` `[CHEAP-static]` Parse intent -> `pattern_hint: pick_place`, single fixed-base arm, source=tote/bin, dest=bin, candidate set discovered at runtime. This matches `intent.structural_tags` `isaac:industry.bin_picking` + `isaac:sensing.overlap_sphere` (template lines 116-125).
  - 1b. `[LLM]` `[CHEAP-static]` **First honesty fork — YCB.** The model should recognise "YCB" demands grocery meshes (cracker box, mustard, mug…). `grep -rin "ycb" service/.../handlers/` returns **nothing**; there is **no YCB catalog, no mesh importer**. Honest move: tell the user it will substitute uniform box workpieces (cubes) and flag YCB as unsupported. (Risk: a less-honest run silently downgrades YCB -> Cube and never says so.)

### 2. `[USER]` — accept the cube substitution (or insist on YCB)  ·  `[CHEAP-static]`
For the trace we take the **honest, completable** path: user accepts box/cube workpieces. (If the user insists on YCB, the flow **dead-ends at step 2** — see "Tool gaps" — because nothing can load a YCB mesh as a graspable rigid body that the cube-based grasp/drop math supports.)

  - 2a. `[LLM]` `[CHEAP-static]` Retrieve the canonical: `CP-NEW-bin-picking-random-pose`. Confirm `roles`: `primary_robot` (franka/ur10), `source_bin`, `destination_bin`, `workpieces` cube×{1..6}, `unordered: true` (template lines 127-164) — the role schema literally encodes "no fixed list".

### 3. `[USER]` — confirm cell layout (tote near robot, drop bin behind)  ·  `[CHEAP-static]`
User accepts the default warehouse cell. `[LLM]` fills `role_defaults` (template lines 165-289):
Franka at `[0,0,0.75]` on a 0.75 m table; **SourceBin (tote)** `[0,0.42,0.80]` 0.35³ open-top; **OutfeedBin** `[0,-0.48,0.80]`; 6 cubes spawned at staggered offsets so they **tumble to random poses** under gravity.

### 4. `[SYSTEM] + [LLM]` — instantiate the scene skeleton  ·  `[CHEAP-static]`
`execute_template_canonical(tpl)` (driven by `gate_one.py:64`) runs the `code_template` (template lines 290+). All authoring tools below **exist** (each confirmed by a real handler def, not just a description string):

| # | Tool | `[tag]` | Handler (real def) |
|---|------|---------|--------------------|
| 4a | `create_prim` (DomeLight, Ground, Cell, Table) | static | `tool_executor.py` |
| 4b | `apply_api_schema` (CollisionAPI on Ground/Table) | static | `tool_descriptions_polish.py` |
| 4c | `set_physics_scene_config` (`enable_gpu_dynamics:False`, MBP) | static | (config write) |
| 4d | `robot_wizard` (spawn Franka at home pose) | static | `handlers/robot.py` path |
| 4e | `create_bin` (SourceBin tote) | static | `handlers/robot.py:_gen_create_bin` |
| 4f | `create_bin` (OutfeedBin) | static | `handlers/robot.py` |
| 4g | `create_prim`×6 `Cube` + `apply_api_schema`×(Rigid/Collision/Mass/PhysxRigid) | static | `tool_executor.py` |
| 4h | `bulk_set_attribute` (sleepThreshold=0) | static | `handlers/scene_authoring.py` |
| 4i | `apply_physics_material` ("rubber") | static | `handlers/...polish_b3` |
| 4j | `add_proximity_sensor` (ArrivalSensor in outfeed) | static | `handlers/sensors.py` |

> Authoring authors **kinematic state only** — no dynamics have stepped yet. All `[CHEAP-static]`.

### 5. `[SYSTEM]` — settle the tote (passive dynamics)  ·  `[EXPENSIVE-physics]`
`settle_after_canonical(tpl)` (`gate_one.py:68`) **plays PhysX** so the 6 cubes fall and tumble into their **random resting poses** inside the tote. This is the first expensive step and the moment the "unstructured, no fixed list" property physically materialises. `sleepThreshold=0` + rubber material = deterministic pile (template `thoughts` §8).

### 6. `[LLM]` — runtime candidate **discovery** (the "no fixed list" mechanism)  ·  `[CHEAP-static]`
This is what distinguishes the canonical from a palletizer:
  - 6a. `overlap_sphere(center=[0,0.42,0.92], radius=0.22)` — **real PhysX AABB scene query** (`handlers/sensors.py:_handle_overlap_sphere`, builds an `overlap_sphere` report callback that collects every collider path). Returns colliders inside the tote volume. **EXISTS, genuine.**
  - 6b. `[LLM]` filter hits to `/World/SourceBin/Cube_*` (drop wall prims); fall back to the static `cube_paths` list if the query is empty (template lines, fallback `if not _candidates`). So the list is **discovered**, not pre-declared.
  - 6c. `get_bounding_box` per candidate (`handlers/scene_authoring.py`) -> sort by `max_z` descending = **pick topmost first** (avoids grasping a buried cube). `[CHEAP-static]` AABB read.

### 7. `[LLM]` — register grasps  ·  `[CHEAP-static]`
  - 7a. `define_grasp_pose(approach=[0,0,-1], offset=[0,0,0.05])` per candidate — writes a real `workspace/grasp_poses/Cube_N.isaac_grasp` YAML (`handlers/robot.py:_gen_define_grasp_pose`). **EXISTS, but advisory:** cuRobo uses its own pose target; the YAML is not consumed by the executor (template `thoughts` §4, `failure_modes[1]`). Honest label: *grasp spec is written but does not drive motion.*
  - 7b. `setup_grasp_pose_sampler(n_samples=60, antipodal)` — **MARKER STUB.** Handler docstring (`handlers/robot.py:_handle_setup_grasp_pose_sampler`): *"Stores config attrs on a marker prim. Actual SDG execution at runtime requires Replicator pipeline."* So no grasp library is actually sampled — this step is **cosmetic / SDG-prep only** and contributes nothing to this run. (Capability **unverified / non-functional** in-line.)

### 8. `[SYSTEM]` — **STATIC-EYES PRE-FILTER** (catch problems before the expensive gate)  ·  `[CHEAP-static]`
Run `scripts/qa/scene_validate.py CP-NEW-bin-picking-random-pose`. It builds+settles once, parks the arm at home (unsubscribes the pick controller, `scene_validate.py:70-75`), reads **actual post-settle geometry**, and checks three classes with **NO traversal rollout**:

  - 8a. **REACH** (`scene_validate.py:258-285`) — each cube's center vs Franka reach `0.855 m` + a vertical z-window. Tote far corner ≈ 0.51 m horizontal -> **inside reach**; cubes sit at z≈0.80-1.04, above the 0.75 m base -> in the vertical window. Also checks **TARGET_REACH** (lines 287-307): OutfeedBin at y=-0.48 -> ~0.51 m -> reachable to place. *Expected verdict: REACH clean.* **This is where an out-of-reach tote OR an out-of-reach drop bin would be caught for ~2.5 s of settle instead of a 180 s physics gate.**
  - 8b. **INTERPENETRATION** (`scene_validate.py:309-322`) — pairwise cube-AABB overlap >50%. This is the **highest-value catch here:** if the 6 cubes were spawned too tightly and PhysX explodes/collapses them into one clump, they are "not individually pickable". The static-eyes flags `INTERPENETRATION: Cube_i & Cube_j overlap ...` **before** the gate wastes a run on a scene where discovery returns one fused blob. (This is the documented dispenser-clump failure class — see MEMORY: CP-71 cup-reach / clump.)
  - 8c. **SUPPORT** (`scene_validate.py:324-367`) — each cube must rest on a surface (gap to nearest surface below in `[-0.02, 0.10]`), not floating, not buried through the tote floor. Catches a cube that spawned above the pile and never settled, or one that fell **through** a too-thin (10 mm) tote wall. *Expected verdict: SUPPORT clean if walls hold.*
  - 8d. `print("VERDICT", "CLEAN" if not V else "FAIL")` (`scene_validate.py:371`). **CLEAN -> proceed to the expensive gate. FAIL -> stop here, fix the scene, never pay for the physics gate.** This is the cheap/expensive firewall.

  > Honest caveat: `scene_validate.py` is a **standalone script, NOT an LLM-callable tool** — `grep` confirms no `scene_validate`/`check_reachability`/`static_eyes`/`form_gate` is registered as a tool. So in a live LLM session the model **cannot call** the static-eyes pre-filter itself; only the harness/operator runs it. The one related capability the LLM *can* call is `check_collisions` (`handlers/...polish.py`), which is narrower (self-collision/pairwise), not the full reach/fit envelope.

### 9. `[LLM]` — configure the motor controller  ·  `[CHEAP-static]`
  - 9a. Build `drop_targets` = every sorted cube -> a point above the OutfeedBin interior floor (z≈0.89; template spreads them on a small grid in `code_template`).
  - 9b. `setup_pick_place_controller(target_source="curobo", source_paths=sorted_cube_paths, destination_path=/World/OutfeedBin, drop_targets=..., planning_obstacles=[Table, OutfeedBin], sensor_path=ArrivalSensor)` (`handlers/pick_place.py`). **EXISTS** — the real cuRobo executor. Subscribes a per-step callback; **no motion yet** at config time -> still `[CHEAP-static]`.

### 10. `[SYSTEM]` — **THE EXPENSIVE GATE** (cuRobo pick-place + simulated traversal)  ·  `[EXPENSIVE-physics]`
`gate_one.py:79` calls `simulate_traversal_check` with the template's own `verify_args`/`simulate_args` (template lines 55-85):
`target_path=/World/OutfeedBin`, all 6 `cube_paths`, `duration_s=180`, `xy_tolerance=0.14`.
PhysX rolls forward up to 180 s while cuRobo plans collision-free pick/transit/place cycles for each height-ranked cube. **This is the only place the robot actually moves**, and the most expensive step in the whole flow.

### 11. `[SYSTEM]` — gate verdict (THE OUTCOME / success-criterion)  ·  `[EXPENSIVE-physics]`
Criterion, `handlers/diagnostics.py:4446-4449`:

```python
if len(cube_paths) > 1:               # this template: 6 cubes
    success = bool(delivered) and upright_ok
else:
    success = bool(in_xy and above_floor and at_rest and upright_ok)
```

Because this is **multi-cube**, the gate passes if **AT LEAST ONE** cube is `delivered` — where per-cube `delivered = in_xy AND above_floor AND at_rest` (`diagnostics.py:4419-4434`):
- **in_xy** = final XY inside OutfeedBin AABB **±0.14 m** (`xy_tolerance`),
- **above_floor** = final z ≥ bin floor − `floor_tol`,
- **at_rest** = speed < `rest_speed` at sim end,
- **upright_ok** = `True` here (`require_upright` defaults `False`, `diagnostics.py:4022,4444`).

`gate_one.py:88` prints `GATE success=<bool>`; **`success=True` => gate PASS**.

> **Lenient-gate honesty note (per MEMORY `gate_criterion`):** ONE of six cubes reaching the bin = PASS. This is a known false-positive risk for "empty the whole tote": the gate does **not** require all 6 emptied, and `define_grasp_pose`/`setup_grasp_pose_sampler` being advisory/stub means a PASS does not certify the grasp-discovery story end-to-end. Treat a green gate as "the pick-place loop delivered ≥1 discovered cube", not "the tote was cleared".

### 12. `[USER]` — receive the outcome  ·  `[CHEAP-static]`
Picker is shown: the cell, the discovery step that found N cubes with no list, and the gate verdict. **Honest delivered scope:** "Franka discovered unknown-pose **cubes** in the tote via a live scene query and bin-picked them; gate confirms ≥1 delivered." **Not delivered:** real YCB meshes; a guarantee the tote is emptied; a functioning antipodal grasp-sampler.

---

## Tool gaps (every tool needed that does NOT exist — grep-confirmed)

`grep` over `service/isaac_assist_service/chat/tools/` returned **MISSING** for all of:

1. **`import_ycb` / `load_ycb` / `spawn_ycb`** — no YCB-object loader. **This is the gap that breaks the literal request.** (`add_reference` exists and could in principle reference a `.usd`, but there is **no YCB asset-path catalog** and the grasp/drop math is cube-AABB-based, so a YCB mesh is not actually pickable through this pipeline.)
2. **`import_mesh` / `create_mesh` / `import_obj` / `load_asset` / `spawn_asset`** — no general mesh/OBJ importer for arbitrary loose items.
3. **No LLM-callable static-eyes tool** — `scene_validate` / `check_reachability` / `reachability_check` / `static_eyes` / `form_gate` / `check_fit` are all **MISSING as tools**. The reach/fit/interpenetration pre-filter exists **only** as the standalone `scripts/qa/scene_validate.py`; the LLM cannot invoke it mid-session (it can only call the narrower `check_collisions`).

Tools the request implicitly wants but are only partial:
4. **`setup_grasp_pose_sampler`** exists but is a **marker stub** (no real SDG sampling) — so "figure out a grasp for an arbitrary loose item" is **unverified/non-functional** for novel geometry.
5. **`define_grasp_pose`** exists but is **advisory** (writes YAML cuRobo never reads) — does not actually steer the grasp.

## Draft / unverified flags

- Template `verified_status`: `drafted-2026-05-16; rebuilt-2026-05-28 ...; form-gate-schema ✓; function-gate ⏳` (template line 298) — **function-gate never confirmed PASS.**
- `motion_controllers.verified: []`, `untested: ["curobo"]` (template lines 291-296) — **no controller verified** on this scene.
- Workpieces are **cubes, not YCB** (template lines 209-288) — the central honesty gap vs the persona request.
- Multi-cube gate = **≥1 of 6 delivered** = lenient; a green gate ≠ tote emptied.

## Bottom line

The library has a real, well-formed "unknown-pose, no-fixed-list, runtime-discovery" Franka bin-pick canonical (`CP-NEW-bin-picking-random-pose`), and the discovery (`overlap_sphere`) + executor (`setup_pick_place_controller` cuRobo) + gate (`simulate_traversal_check`, ≥1-of-N delivered) chain is genuine and runnable. The **static-eyes pre-filter would cheaply catch the dominant failure here — a collapsed/exploded cube clump (INTERPENETRATION) or a too-thin tote wall (SUPPORT) — before the 180 s physics gate.** But the persona's specific **"YCB items" cannot be honoured**: no YCB/mesh-import tool exists, the grasp-sampler is a stub, and the workpieces are cubes. And the template itself is a **draft with an unconfirmed function-gate**.
