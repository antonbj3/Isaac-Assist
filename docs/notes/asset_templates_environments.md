# Asset Templates — FULL ENVIRONMENTS / SCENES

Category: drop a robot cell INTO a real pre-built environment USD (vs. building a floor
from primitives), and the multi-cell **T7** scenes that compose several cells inside one
real warehouse.

All asset paths below were verified with `ls` against the mount; all tool claims were
verified with `grep` against `service/isaac_assist_service/chat/tools/tool_schemas.py`
and the handler files. Mount root used:

```
/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/
```

---

## 1. Verified environment assets on disk

| Asset (relative to mount root) | Bytes | Verified | Role in templates |
|---|---|---|---|
| `Isaac/Environments/Simple_Warehouse/full_warehouse.usd` | 6.7 MB | OK | Large furnished warehouse — racking, floor, lights. Anchor for T6/T7. |
| `Isaac/Environments/Simple_Warehouse/warehouse.usd` | 1.6 MB | OK | Minimal warehouse shell. |
| `Isaac/Environments/Simple_Warehouse/warehouse_multiple_shelves.usd` | 2.3 MB | OK | Aisles of shelving — picking / AMR routes. |
| `Isaac/Environments/Simple_Warehouse/warehouse_with_forklifts.usd` | 10 KB | OK | Shell + forklift props (thin layer; references props). |
| `Isaac/Environments/Digital_Twin_Warehouse/small_warehouse_digital_twin.usd` | — | OK | Scanned real-facility digital twin — sim-to-real anchor. |
| `Isaac/Environments/Hospital/hospital.usd` | — | OK | Hospital interior — service-robot / delivery cell. |
| `Isaac/Environments/Office/office.usd` | — | OK | Office interior — desk-side / service cell. |
| `Isaac/Environments/Simple_Room/simple_room.usd` | — | OK | Small lit room — tabletop cell with realistic walls/lighting. |
| `Isaac/Environments/Grid/default_environment.usd` | — | OK | Grid floor + dome light (the canonical "default" stage). |
| `Isaac/Environments/Grid/gridroom_black.usd` / `gridroom_curved.usd` | — | OK | Neutral SDG / calibration backdrops. |
| `Isaac/Samples/Scene_Blox/Warehouse_Tiles/` (`empty.usd`, `empty_straight.usd`, `empty_cross.usd`, `single_shelf.usd`, `double_shelf_a.usd`, `double_shelf_b.usd`, `building_center.usd`, `building_end.usd`, `lights.usd`, `cameras.usd`) | — | OK | **Tile kit** — compose a bespoke warehouse from modular tiles; each tile is a cell-slot. |
| `Isaac/Environments/Modular_Warehouse/{Library,Props}` | — | OK | Component library (no top-level `.usd`; sub-assets only). |

Note: this is the **5.0** mount. Several tool descriptions and example URLs cite
`omniverse://localhost/NVIDIA/Assets/Isaac/5.1/...`; templates must point at the local
**5.0** filesystem paths above, not the 5.1 Nucleus URLs in the docstrings.

---

## 2. The tool surface for environment loading + cell anchoring

### EXISTS — load / reference a real environment USD
- **`add_reference`** (`tool_schemas.py:83`) — *"Add a USD file reference to an existing
  prim (load external assets, robots, environments)."* Drops the whole environment under
  one Xform. This is the **primary load-environment mechanism** for the
  drop-cell-into-environment templates. Honesty-checked (raises `FileNotFoundError` if
  the path is missing — see `AD-05`).
- **`add_usd_reference`** (`tool_schemas.py:8638`) — full `Usd.References` surface:
  `ref_prim_path` (reference a subtree, e.g. one aisle), `layer_offset_seconds`,
  `instanceable` (point-instancing for repeated tiles). Use for tile-kit composition and
  for referencing only part of a big environment.
- **`open_stage`** (`tool_schemas.py:9441`) — opens the environment USD **as the root
  stage** (destroys current stage). Use when the environment IS the scene and the cell is
  authored on top via an edit layer; *not* used when composing several cells, because it
  replaces rather than nests.
- **`add_sublayer`** (`tool_schemas.py:7930`) + **`set_edit_target`** — attach an override
  layer above a referenced/opened environment so cell edits live in their own layer
  (non-destructive composition; the recommended pattern for "environment base layer +
  cell override layer").
- **`load_payload`** / **`list_payloads`** (`tool_schemas.py:8770` / `8724`) — deferred
  loading of heavy environment subtrees; pair with `add_usd_reference` when only part of
  `full_warehouse.usd` needs to be in memory.
- **`set_environment_background`** (`tool_schemas.py:7837`) — HDRI dome / solid backdrop;
  complements (does not replace) a geometry environment USD.

### EXISTS — anchor a cell inside the loaded environment
- **`get_world_transform`** (`tool_schemas.py:6442`) + **`get_bounding_box`** — read the
  environment's authored frame / floor extents so the cell origin is **derived from the
  environment**, not hardcoded. This is how a cell "knows where the floor is."
- **`teleport_prim`** (`tool_schemas.py:359`) — move the cell's root Xform (and props) to
  the chosen anchor pose inside the environment (`position` + `rotation_euler`).
- **`anchor_robot`** (`tool_schemas.py:192`) — fix a stationary arm (`fixedBase=True`,
  deletes rootJoint), optionally to an `anchor_surface_path` and `position` — i.e. bolt
  the arm to the environment floor/table at the anchor pose.
- **`activate_area`** / `activate_robot_cell` (`tool_schemas.py:5247`) — deactivate every
  prim outside `prim_scope` so physics/render only run for the one cell. **Load-bearing
  for big environments** (`full_warehouse.usd` is a 50K+ prim stage). Reversible via
  `set_active_state`.
- **`clone_prim`** (`tool_schemas.py:113`) / **`clone_envs`** (`tool_schemas.py:3389`) —
  GPU `GridCloner` for replicating a cell across the environment (e.g. N identical pick
  stations down an aisle, RL-style), with optional inter-clone collision filtering.

### MISSING / PARTIAL — multi-cell composition (Phase 4, the T7 blocker)
This is the named gap. Confirmed by `grep`:
- **`compose_scene` does NOT exist** (recommended ~200-LOC tool — none found).
- **`load_environment`, `drop_robot_cell`, `anchor_cell`, `place_cell`,
  `add_environment`, `compose_cells`, `merge_canonical` do NOT exist.**
- **`sub_stages`** (the composition primitive named in every roadmap doc) is carried by
  **0 templates on disk**.
- Build route, retrieval, and instantiator are all single-template:
  `multimodal/routes.py:394-507` (`POST /{sid}/build` → one `template_id`),
  `chat/canonical_instantiator.py:741-813` (`execute_template_canonical(template, ...)`,
  singular).
- `gate_one.py` / `reach_validate.py` loop **per template** — there is **no cross-cell
  integration gate**.

Roadmap evidence: `docs/notes/MASTER_EXECUTION_PLAN.md:65` (Phase 4 — Composition),
`docs/notes/IMPLEMENTATION_PLAN.md:98` (P4-01 Composition-IR), and the end-to-end trace
`docs/notes/TRACED_FLOW_COMPLEX_SCENE.md` ("Multi-canonical composition is NOT possible
today").

**The composition mechanism is the build-once infrastructure (~600 LOC) that, per cell,
must:** namespace each canonical instance under its own subtree / `prim_prefix`; apply a
per-cell `cell_origin` offset (derived from the environment frame via
`get_world_transform` / `get_bounding_box`); keep distinct `phase_id` / robot paths;
**defer a single `world.reset()` to the very end** (each canonical currently
resets+re-seeds → would race — the CP-52 mutex-starvation root generalized); then run a
**cross-cell integration gate** in one physics scene.

---

## 3. How a cell anchors inside a pre-built environment (the recipe)

1. **Load environment as base.** `add_reference("/World/Env", "<env>.usd")` (nested,
   composable) — or `add_usd_reference` with `ref_prim_path` to pull only an aisle. Use
   `open_stage` only when the environment is the sole scene.
2. **Override layer.** `add_sublayer("<cell_overrides>.usda")` + `set_edit_target` so all
   cell edits are non-destructive over the environment.
3. **Read the environment frame.** `get_bounding_box("/World/Env")` /
   `get_world_transform` → floor height + a clear footprint → compute `cell_origin`
   (derived, not hardcoded).
4. **Instantiate the cell** (an existing canonical: arm + props + controller) under its own
   namespace, e.g. `/World/CellA/...`.
5. **Anchor it.** `teleport_prim("/World/CellA", position=cell_origin, rotation_euler=...)`;
   `anchor_robot` for the arm to the floor/table at the anchor pose.
6. **Isolate for physics.** `activate_area(prim_scope="/World/CellA")` so the 50K-prim
   warehouse doesn't drown the solver during the per-cell gate.
7. **(T7 only) Repeat per cell** at distinct origins, then defer one `world.reset()` and
   run the **integration gate** — **MUST BUILD** (Phase 4).

---

## 4. Proposed templates

Tiers per `CANONICAL_TAXONOMY.md:108`: **T6 = real-asset-cell** (one cell in a real
environment, composition NOT required), **T7 = multi-cell-warehouse** (composition
required → blocked on Phase 4). Templates follow the on-disk schema
(`task_id`, `goal`, `tools_used`, `intent`, `roles`, `role_defaults`, `simulate_args`,
`verify_args`, `diagnose_args`, `motion_controllers`, `verified_status`).

### Tier T6 — drop ONE cell into a real environment (buildable today)

- **ENV-T6-01 — UR10 palletize cell inside `full_warehouse.usd`**
  `add_reference` the warehouse, read its frame, drop a UR10 + infeed conveyor + KLT bins
  in a clear floor footprint, `anchor_robot`, `activate_area` to isolate, run the existing
  pick-place gate. Assets: `full_warehouse.usd`. Robot: UR10. Capability: load-env + anchor
  + isolate.

- **ENV-T6-02 — Franka kitting cell inside `warehouse_multiple_shelves.usd`**
  Anchor a Franka kitting station in an aisle between shelves; shelves are static
  obstacles for the reach probe. Assets: `warehouse_multiple_shelves.usd`. Robot: Franka.

- **ENV-T6-03 — Carter AMR aisle navigation in `warehouse_with_forklifts.usd`**
  Drop a Nova Carter, generate an occupancy map of the referenced warehouse, navigate an
  aisle with forklift props as obstacles. Assets: `warehouse_with_forklifts.usd`. Robot:
  Carter. Capability: load-env + occupancy-map + nav (no arm anchor).

- **ENV-T6-04 — Sim-to-real pick cell in the Digital-Twin warehouse**
  Anchor a Franka pick station inside `small_warehouse_digital_twin.usd` (scanned real
  facility) with a matching HDRI via `set_environment_background` — the sim-to-real anchor
  template. Assets: `small_warehouse_digital_twin.usd`. Robot: Franka.

- **ENV-T6-05 — Hospital service-robot delivery cell**
  Reference `hospital.usd`; Carter/mobile base delivers a tray between two rooms; corridor
  geometry is the navmesh source. Assets: `hospital.usd`. Robot: Carter.

- **ENV-T6-06 — Office desk-side assist cell**
  Reference `office.usd`; anchor a small arm at a desk; `activate_area` isolates the one
  workstation from the whole floor. Assets: `office.usd`. Robot: Franka/small arm.

- **ENV-T6-07 — Simple-Room realistic tabletop**
  `add_reference` `simple_room.usd` for real walls + lighting instead of a primitive
  ground plane; anchor a tabletop pick-place on the room floor. Assets: `simple_room.usd`.
  Robot: Franka. Capability: env-as-backdrop swap for the default-grid baseline.

### Tier T7 — multi-cell composition in one real environment (blocked on Phase 4)

Each requires the **composition mechanism** (`compose_scene` / `sub_stages` /
per-cell `cell_origin` + `prim_prefix` + deferred single `world.reset()` + cross-cell
integration gate) — none of which exist on disk yet.

- **ENV-T7-01 — North-Star 3-cell warehouse** (the canonical Phase-4 acceptance case)
  Inside `full_warehouse.usd`: UR10 palletize cell + Franka kitting cell + Carter AMR
  ferrying pallets between them. Three canonicals → one stage → one physics scene → AMR
  handoff relation → integration gate. Assets: `full_warehouse.usd` + UR10/Franka/Carter.
  Capability: **compose + namespace + anchor-per-cell + inter-cell route + integration
  gate** (all MUST-BUILD).

- **ENV-T7-02 — Scene-Blox tile-composed warehouse**
  Build a bespoke warehouse from `Warehouse_Tiles/` (`empty_straight`, `empty_cross`,
  `single_shelf`, `double_shelf_a`, `building_center/end`, `lights`, `cameras`) via
  `add_usd_reference(instanceable=True)`, then drop a pick cell per shelf tile. Assets:
  Scene_Blox tile kit. Capability: tile composition + per-tile cell anchor.

- **ENV-T7-03 — Dual-aisle multi-AMR logistics**
  `warehouse_multiple_shelves.usd` with two pick cells on opposite aisles and two Carters
  on a shared loop — exercises the multi-robot mutex/handoff hardening (Phase 4.4, the
  CP-51/52/53/65 root) at environment scale. Assets: `warehouse_multiple_shelves.usd`.

- **ENV-T7-04 — Replicated pick stations down an aisle**
  `clone_envs` / `clone_prim` (GridCloner) replicate one anchored pick cell N times along
  an aisle in `full_warehouse.usd` with inter-clone collision filtering — the bridge from
  T6 single-cell to T7 multi-cell that needs the least new infrastructure. Assets:
  `full_warehouse.usd`.

---

## 5. Tool gap summary (what blocks T7)

| Tool / mechanism | Purpose | Status |
|---|---|---|
| `add_reference` / `add_usd_reference` | Load a real environment USD under an Xform | EXISTS |
| `open_stage` | Open environment as root stage | EXISTS |
| `add_sublayer` / `set_edit_target` | Non-destructive cell-override layer over the env | EXISTS |
| `get_world_transform` / `get_bounding_box` | Derive cell origin from the environment frame | EXISTS |
| `teleport_prim` / `anchor_robot` | Anchor the cell + bolt the arm at the anchor pose | EXISTS |
| `activate_area` (`activate_robot_cell`) | Isolate one cell in a 50K-prim env for physics | EXISTS |
| `clone_envs` / `clone_prim` | Replicate a cell across the environment (GridCloner) | EXISTS |
| `compose_scene` / `sub_stages` / cell-DAG decompose | Place N canonicals in one frame, namespaced, with inter-cell relations | **MISSING (Phase 4)** |
| Per-cell `cell_origin` + `prim_prefix` + deferred single `world.reset()` | Compose without reset/seed races | **MISSING (Phase 4)** |
| Cross-cell integration gate | Prove the composed scene in one physics run | **MISSING (Phase 4)** |
