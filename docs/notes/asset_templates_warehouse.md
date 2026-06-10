# Asset Templates — Warehouse Infrastructure

Category: **WAREHOUSE INFRASTRUCTURE**
Generated: 2026-06-09. Verified against on-disk Isaac 5.0 assets + the live tool surface
(`service/isaac_assist_service/chat/tools/handlers/` + `tool_schemas.py`, ~407 tools).

All asset paths below were confirmed with `ls`. All tool existence/absence was confirmed
with `grep` over the handler `register(data, codegen)` maps. Nothing here is assumed.

---

## 1. Verified assets on disk

Root: `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/`

### Warehouse infrastructure pack — `NVIDIA/Assets/ArchVis/Industrial/`
| Asset family | Path (relative to root) | Count | Notes |
|---|---|---|---|
| Racks (loaded) | `NVIDIA/Assets/ArchVis/Industrial/Racks/RackLarge_A1..A9.usd`, `RackLong_A1..A9.usd`, `RackSmall_A1..A9.usd` | **27** | Matches prompt's "27". These are the pre-stocked pallet-rack variants. |
| Shelves (empty racks) | `.../Industrial/Shelves/RackLargeEmpty_A1..A2.usd`, `RackLongEmpty_A1..A2.usd`, `RackSmallEmpty_A1..A2.usd` | 6 | Empty bays — the replenishment **targets**. |
| Railing / fencing | `.../Industrial/Railing/{CornerRail_A1,MetalFencing_A1..A3,RampLong_A1,RampShort_A1}.usd` | 6 | Aisle barriers + dock ramps (RampLong/RampShort serve as the dock approach). |
| Pallets (industrial) | `.../Industrial/Pallets/Pallet_{A1,B1,C1}.usd` | 3 | Also `Isaac/Props/Pallet/pallet.usd` (+ `pallet_holder*.usd`, `o3dyn_pallet.usd`). |
| Piles (pre-stacked loads) | `.../Industrial/Piles/Pallets_A1..A5.usd`, `WarehousePile_A1..A7.usd` | 12 | Pre-built pallet stacks for depalletize sources. |
| Cardboard boxes | `.../Industrial/Containers/Cardboard/Cardbox_{A,B,C,D}{1,2,3}.usd` | 12 | Depalletize / shelf-pick payloads. |
| KLT bins | `Isaac/Props/KLT_Bin/small_KLT.usd` (+ `_visual.usd`, `_visual_collision.usd`) | 3 | Standard tote — the canonical AMR / shelf payload. |
| Forklift (prop) | `Isaac/Props/Forklift/forklift.usd` (+ `S_ForkliftFork.usd`) | — | Static prop; **not articulated/drivable.** |
| Forklift (drivable robot) | `Isaac/Robots/IsaacSim/ForkliftB/forklift_b.usd` (+ `forklift_b_sensor.usd`), `ForkliftC/forklift_c.usd`; ROS sample `Samples/ROS2/Robots/forklift_b_ROS.usd` | — | Use **forklift_b** when the forklift must drive/lift; the Props one is scenery only. |
| AMR (nova_carter) | `Isaac/Robots/NVIDIA/NovaCarter/nova_carter.usd`; ROS sample `Samples/ROS2/Robots/Nova_Carter_ROS.usd`; nav sample `Samples/OmniGraph/nova_carter_drive_to_goal.usd` | — | The warehouse AMR base. |
| Full warehouse env | `Isaac/Environments/Simple_Warehouse/{full_warehouse,warehouse,warehouse_with_forklifts,warehouse_multiple_shelves}.usd` | 4 | Ready-made backdrops; also `.../Stages/IsaacWarehouse.usd`. |

### Simple_Warehouse component props (alternative, lower-poly) — `Isaac/Environments/Simple_Warehouse/Props/`
`SM_RackShelf_01.usd`, `SM_RackFrame_03.usd`, `SM_RackPile_{03,04,06}.usd`, `SM_Rackshield.usd`,
`SM_WallWire_*.usd` (wire fencing), `SM_CardBoxA_01_*.usd` (hundreds), barrels, bottles, etc.

### Assets that DO NOT exist (do not reference)
- **Dock door** — no `DockDoor/RollUp/RollerDoor/BayDoor/SectionalDoor/LoadingDock` asset anywhere
  in 5.0. The "dock" in dock-depalletize is realized as a **RampLong_A1 + a pallet pile at the bay
  edge**, not a powered door. Templates below model the dock geometrically, never via a door asset.
- `Modular_Warehouse` / `Digital_Twin_Warehouse` env dirs are **material/texture-only** on this disk
  (no `.usd` stages). Use `Simple_Warehouse` or `.../Industrial/Stages/IsaacWarehouse.usd`.

---

## 2. Tool surface — what exists vs. what's missing

Confirmed by grep over `handlers/*.py` `register(data, codegen)` maps.

### EXISTS (use directly)
| Tool | Handler | Role in these templates |
|---|---|---|
| `create_wheeled_robot` | `robot.py` (codegen) | Differential/AMR base — wheel_radius/wheel_base/wheel_dof_names. |
| `setup_nav_robot` | `robot.py` (data) | Wires nav/goal-driving onto a wheeled base (`nav_diff` param seen in handler). |
| `generate_occupancy_map` | `robot.py` (codegen) | 2D occupancy map (PNG+YAML) for path-planning — used in `F-04`. |
| `navigate_to` | `robot.py` (codegen) | Drive AMR to a pose/marker. |
| `move_to_pose` | `robot.py` (codegen) | Lower-level base/EE pose move. |
| `setup_pick_place_controller` | `pick_place.py` (codegen) | Arm pick→place (cuRobo/RMPflow); the manipulation half of an AMR+arm. |
| `setup_robot_handoff_signal` / `setup_robot_claim_mutex` | `robot.py` (data) | AMR↔arm / multi-robot coordination (used in `CP-NEW-cart-handoff-amr`). |
| `grasp_object` | (data) | Attach/weld grasp for cart/tote handoff. |
| `place_on_top_of` | `robot.py` (data) | Spatial-language placement resolver (object → on top of surface). |
| `compute_stack_placement` | `scene_authoring.py` | Computes shelf/stack slot coordinates from bbox. |
| `track_slot_occupancy` | `robot.py` (data) | Tracks which rack/shelf slots are filled — replenishment gate. |
| `add_reference` / `add_usd_reference` | scene | Spawn the rack/shelf/pallet/forklift/nova_carter USDs. |
| `create_prim` / `teleport_prim` / `get_world_transform` / `get_bounding_box` | scene | Geometry + placement plumbing. |
| `setup_zone_partition` | `robot.py` (data) | Partition aisles / pick zones for multi-AMR. |

### MISSING (must compose or build)
| Tool | Status | Mitigation |
|---|---|---|
| **`setup_amr_with_manipulator`** | **MISSING** (grep: 0 hits in any handler or schema) | Compose: `create_wheeled_robot` (base) + `add_reference`(arm USD) parented to the base + `setup_nav_robot` + `setup_pick_place_controller`. No single tool stands up a mobile manipulator; the cart-handoff template already proves the compose pattern (separate AMR + static arm, coordinated by handoff signal). A real mobile-manipulator (arm rigidly on the moving base, shared TF tree) needs a **new tool** — flagged below as the primary build item. |
| **shelf-placement** (e.g. `place_on_shelf` / `rack_place` / `shelf_place`) | **MISSING** (grep: 0 hits) | **PARTIAL** coverage today via `compute_stack_placement` + `place_on_top_of` + `teleport_prim`, but none is rack-bay-aware (no slot indexing into RackLarge/RackLong levels). A dedicated `place_on_shelf(rack_path, level, slot, payload_path)` that reads the rack's level/bay frames would remove per-template hardcoded shelf-Z math. Recommended new tool. |
| **occupancy-map nav (end-to-end)** | **PARTIAL** | `generate_occupancy_map` produces the map; `setup_nav_robot`+`navigate_to` drive. There is **no** single "plan a route over the occupancy map and execute" tool — templates chain map→nav manually. Acceptable, but a `plan_route_on_occupancy` convenience tool would help AMR-to-rack logistics. |

---

## 3. Proposed templates

Tiers: **canonical** = fully specified, buildable today with existing tools;
**compose** = buildable today but stitches multiple tools (no single primitive);
**blocked** = needs a new tool before it can be authored cleanly.

### WH-SHELF-01 — Shelf pick/place (fixed arm at a rack bay)
- **Robot:** fixed-base arm (`franka_panda` | `ur10` | `kinova_gen3`).
- **Assets:** `RackLargeEmpty_A1.usd` (target empty rack) + `RackLarge_A1.usd` (source stocked rack) + `KLT_Bin/small_KLT.usd` payloads (or `Cardbox_A1`).
- **Task:** arm picks 3 KLT totes off a source rack level and places them into the matching empty bay on the target rack; `track_slot_occupancy` flips each slot idle→filled.
- **Tools:** `add_reference`(racks), `add_reference`/`create_prim`(totes), `get_bounding_box`+`compute_stack_placement`(derive bay slot Z/Y), `setup_pick_place_controller`(target_source='curobo', planning_obstacles=[both racks]), `track_slot_occupancy`.
- **Tier:** canonical. **Capability:** shelf-placement (via compute_stack_placement; no native tool).

### WH-RACK-02 — Rack replenishment (refill empty bays to a target level)
- **Robot:** fixed-base arm.
- **Assets:** `RackLongEmpty_A1.usd` (under-stocked) + a `Piles/Pallets_A1.usd` or `Cardbox_*` staging buffer + KLT/cardbox payloads.
- **Task:** arm continuously moves boxes from the staging pile onto the empty rack until every bay slot reads filled; `track_slot_occupancy` is the success gate (replenish until N slots occupied).
- **Tools:** `add_reference`, `compute_stack_placement`, `setup_pick_place_controller`, `track_slot_occupancy`, `setup_zone_partition`(staging vs rack).
- **Tier:** canonical. **Capability:** shelf-placement + occupancy-as-gate.

### WH-DOCK-03 — Dock depalletize (de-stack a pallet pile at the bay)
- **Robot:** fixed-base arm (or `forklift_b` for the heavy variant, see WH-DOCK-03b).
- **Assets:** `Piles/WarehousePile_A1.usd` or `Piles/Pallets_A2.usd` (pre-stacked pallet) at the bay edge + `Railing/RampLong_A1.usd` (dock ramp = the "dock", since no door asset exists) + `KLT_Bin` / `Cardbox_*` as the de-stacked units + destination conveyor or buffer.
- **Task:** arm removes boxes top-down from the pallet pile and feeds them to a conveyor/buffer; layer-by-layer depalletize.
- **Tools:** `add_reference`(pile+ramp), `get_bounding_box`(layer detection), `setup_pick_place_controller`, optionally `create_conveyor`(exists, used in CP-01) as the takeaway.
- **Tier:** canonical. **Note:** "dock door" is geometric only — RampLong_A1, never a door asset.

### WH-DOCK-03b — Forklift dock depalletize (heavy, drivable forklift)
- **Robot:** `ForkliftB/forklift_b.usd` (drivable; NOT the static `Props/Forklift/forklift.usd`).
- **Assets:** `Piles/Pallets_A3.usd` + `Industrial/Pallets/Pallet_A1.usd` + `RampLong_A1.usd`.
- **Task:** forklift drives to the dock, inserts forks under a pallet, lifts, carries to a rack/staging zone.
- **Tools:** `add_reference`(forklift_b), `setup_nav_robot`/`navigate_to`(drive to pallet), fork lift via articulation drive (`create_articulated_joint`/`set_attribute` on the fork prismatic DOF), `grasp_object`(pallet attach).
- **Tier:** compose. **Capability:** wheeled-robot nav (exists) + fork-DOF actuation (manual, no forklift-specific tool).

### WH-AMR-04 — AMR-to-rack logistics (nova_carter ferries totes between racks)
- **Robot:** `nova_carter.usd` (AMR base).
- **Assets:** `RackLarge_A1.usd` (pick rack) + `RackLargeEmpty_A1.usd` (drop rack) + `KLT_Bin/small_KLT.usd` payload + `Railing/MetalFencing_A1.usd` (aisle bounds) inside `Simple_Warehouse/full_warehouse.usd`.
- **Task:** generate occupancy map of the warehouse, AMR navigates from pick rack to drop rack carrying a tote (load via `grasp_object`/attach), unloads, returns. Multi-cycle.
- **Tools:** `add_reference`(nova_carter+racks+fencing), `create_wheeled_robot`/`setup_nav_robot`, `generate_occupancy_map`, `navigate_to`(rack markers), `grasp_object`(tote on deck), `setup_robot_handoff_signal`(load/unload sync).
- **Tier:** canonical (AMR transport only; no on-board arm). **Capability:** occupancy-map nav (exists) + nav stack (exists).

### WH-MM-05 — Mobile-manipulator rack pick (AMR + arm) — BLOCKED on new tool
- **Robot:** mobile manipulator = `nova_carter` base + `ur10`/`franka` arm rigidly mounted.
- **Assets:** `RackLong_A1.usd` (pick from) + `RackLongEmpty_A1.usd` (place to) + `KLT_Bin` payload.
- **Task:** AMR drives to rack bay (occupancy-map nav), arm picks a tote off the shelf, AMR drives to the destination rack, arm places it into the empty bay.
- **Tools needed:** `setup_amr_with_manipulator` (**MISSING**) to bind arm→moving base with one TF tree + shared planning; then `generate_occupancy_map`, `navigate_to`, `setup_pick_place_controller`, `track_slot_occupancy`.
- **Tier:** blocked. **Today's workaround:** compose base+arm manually and treat as two coordinated robots (the `CP-NEW-cart-handoff-amr` pattern) — but the arm does not ride the base correctly without the missing tool, so the clean mobile-manip template waits on it.

---

## 4. Build recommendations (ordered)
1. **`setup_amr_with_manipulator`** — highest leverage; unblocks WH-MM-05 and the whole mobile-manipulator class. Bind an arm USD to a `create_wheeled_robot` base as one articulation/TF tree, expose a unified planning interface.
2. **`place_on_shelf(rack_path, level, slot, payload_path)`** — rack-bay-aware placement reading RackLarge/RackLong level frames; removes hardcoded shelf-Z math from WH-SHELF-01 / WH-RACK-02 / WH-MM-05. Today only `compute_stack_placement`+`place_on_top_of` exist (slot-blind).
3. **`plan_route_on_occupancy`** (nice-to-have) — single map→route→execute for AMR-to-rack; today chained manually from `generate_occupancy_map`+`navigate_to`.

All five templates are authorable today **except WH-MM-05** (blocked) and the forklift-fork DOF
in WH-DOCK-03b (manual articulation, no forklift tool). Asset paths are all verified on disk;
no dock-door asset exists — model the dock with `RampLong_A1` + a pallet pile.
