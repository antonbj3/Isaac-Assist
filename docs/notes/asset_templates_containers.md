# Asset Templates — CONTAINERS (bins / crates / pallets / totes)

Category proposal: real-NVIDIA-asset container templates for palletize, kitting,
bin-pick, and pack. Every container is a **fixed-bbox real USD asset** referenced
via `add_reference`; layout is **bbox-derived** (read the container's world bbox
once with `get_bounding_box`, then compute placements with
`compute_stack_placement`). This replaces the primitive 5-cube `create_bin`
proxy currently used by all 440 templates.

Date: 2026-06-09. Verified against assets on disk + tool surface (`grep`/`ls`).

---

## 1. Real container assets confirmed on disk

Root: `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/`
Runtime URI prefix (templates use `omniverse://localhost/NVIDIA/Assets/Isaac/5.0/` or the local mount; both resolve to the same tree).

### KLT bins (small load carrier) — VDA/VDMA standard
- `Isaac/Props/KLT_Bin/small_KLT.usd` (physics)
- `Isaac/Props/KLT_Bin/small_KLT_visual.usd` (render-only)
- `Isaac/Props/KLT_Bin/small_KLT_visual_collision.usd` (visual + convex collision)
- bbox ≈ **0.30 × 0.20 × 0.15 m** (USDC binary; read exact extent at runtime via `get_bounding_box`).

### Crates
- **Plastic, dimensioned-in-name** (best for bbox-derived layout — dims live in the filename, no USD read needed):
  - `Isaac/Props/PackingTable/props/SM_Crate_A07_Yellow_01/SM_Crate_A07_Yellow_01.usd` (+ `_physics.usd`)
  - `Isaac/Props/PackingTable/props/SM_Crate_A08_Blue_01/SM_Crate_A08_Blue_01.usd` (+ `_physics.usd`)
- **Plastic warehouse crates** (Simple_Warehouse): `Isaac/Environments/Simple_Warehouse/Props/SM_CratePlastic_{A,B,C}_0{1..5}.usd` (+ `SM_CratePlasticNote_*`)
- **Wooden crates** (ArchVis Industrial): `NVIDIA/Assets/ArchVis/Industrial/Containers/Wooden/WoodenCrate_{A1,A2,B1,B2,C1,D1}.usd`

### Cardboard / boxes
- `NVIDIA/Assets/ArchVis/Industrial/Containers/Cardboard/Cardbox_{A1..A3,B1..B3,C1..C3,D1..D3}.usd`
- `Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxA_01_*.usd` (hundreds of instances)
- `NVIDIA/Assets/DigitalTwin/Assets/Warehouse/Storage/Boxes/Box_A0{1..7}_<WxDxH>cm_PR_V_NVD_01.usd`

### Pallets
- `Isaac/Props/Pallet/pallet.usd` — single EUR-style wooden pallet, bbox ≈ **1.2 × 0.8 × 0.144 m**
- `Isaac/Props/Pallet/o3dyn_pallet.usd`
- `Isaac/Props/Pallet/pallet_holder.usd`, `pallet_holder_short.usd` — pallet stations
- `NVIDIA/Assets/ArchVis/Industrial/Pallets/Pallet_{A1,B1,C1}.usd`
- `NVIDIA/Assets/ArchVis/Industrial/Piles/Pallets_A{1..5}.usd` — pre-stacked pallet piles

### Totes / containers (DigitalTwin — **dimensions encoded in filename**, the gold path for bbox-derived layout)
- Totes: `NVIDIA/Assets/DigitalTwin/Assets/Warehouse/Storage/Totes/Tote_{A,B,C,D,E,F}/Tote_*_<WxDxH>cm_*.usd`
  - e.g. `Tote_B01_60x40x40cm` (the EUR 600×400 footprint), `Tote_C10_40x40x40cm`
- Containers: `.../Storage/Containers/Container_{A..J}/Container_*_<WxDxH>cm_*.usd`
  - e.g. `Container_B03_40x30x08cm` (EURO 400×300 shallow), `Container_I04_160x120x64cm` (large pallet-box)
- Bins: `.../Storage/Bins/Bin_{A,B}/Bin_*_<WxDxH>cm_*.usd` (small parts bins, 10×08×08 up to 45×71×32 cm)
- Cases: `.../Storage/Cases/Case_*_<WxDxH>cm_*.usd`

### PackingTable (work surface for pack/kit cells)
- `Isaac/Props/PackingTable/packing_table.usd`
- `Isaac/Props/PackingTable/props/SM_HeavyDutyPackingTable_C02_01/SM_HeavyDutyPackingTable_C02_01.usd` (+ `_physics.usd`)

---

## 2. Tool inventory for this category

| Tool | Purpose | Status | Evidence |
|---|---|---|---|
| `add_reference` | Drop a real container USD onto an Xform (`reference_path=<usd>`). THE asset-resolution path. | **exists** | `tool_schemas.py:83` |
| `add_usd_reference` | Same, with `ref_prim_path` / `instanceable` (point-instance N pallets/totes). | **exists** | `tool_schemas.py:8638` |
| `get_bounding_box` | Read a referenced container's fixed world bbox → drives all layout math. | **exists** | `tool_schemas.py` (grep) |
| `get_world_transform` | Container pose for placement frame. | **exists** | `tool_schemas.py` (grep) |
| `compute_stack_placement` | THE palletize/kitting layout engine. `pattern='grid_RxC'` / `'column'` / `'donut_RxC'`, `anchor='top'\|'inside_floor'`, multi-layer (n_items > rows*cols), `layer_rotation_deg=90` brick interlock, `cube_sizes` mixed-SKU. | **exists** | `tool_schemas.py:7158`, handler `scene_authoring.py:5454` |
| `create_kit_tray` | N labeled slots (`slot_layout='grid_RxC'\|'row_N'`), returns slot centers for `drop_targets`. | **exists** | `tool_schemas.py:2577`, handler `robot.py:4416` |
| `track_slot_occupancy` | Verify kit completion (slot→cube proximity map). | **exists** | `tool_schemas.py:2597` |
| `setup_pick_place_controller` | Executes the pick→place. `drop_targets` (per-item grid pos), `gripper_rotation` (brick yaw), `color_routing` (SKU→bin), `planning_obstacles` (avoid pallet/walls). | **exists** | `tool_schemas.py:3920` |
| `surface_gripper` / `create_gripper` | Suction EE for bin-pick / vacuum palletizing (UR10 has no built-in gripper). | **exists** | `tool_schemas.py` (grep) |
| `set_semantic_label` | Tag SKUs by class for `color_routing` sortation into bins. | **exists** | `tool_schemas.py` (grep) |
| `compute_palletizer_grid` | **MISSING** — does not exist. Palletizing is served by `compute_stack_placement` with `grid_RxC` + multi-layer + `layer_rotation_deg`. No separate tool needed; do NOT author templates that call it. | **missing** | `grep -niE 'palletiz' handlers/ tool_schemas.py` → only doc-strings, no tool |
| **asset-resolution behind `create_bin`** | **MISSING** — `create_bin` (`tool_schemas.py:3875`, codegen `robot.py:2013`) builds 5 thin collision Cubes from a `size` arg. There is NO name→USD lookup, NO real-container variant. To use a real KLT/crate/tote you must `add_reference` the USD yourself. **The category gap.** | **missing** | `_gen_create_bin` only emits primitive Cubes; no asset path resolved |

### The two real gaps (recommended new capability)

1. **`compute_palletizer_grid`** named in the brief is a phantom — fold into
   `compute_stack_placement`. The one thing `compute_stack_placement` lacks for
   true palletizing is **per-asset footprint nesting** (it assumes square
   `cube_size`/`cube_sizes`). For rectangular containers (600×400 totes) it
   needs `item_footprint=[w,d]` so a layer packs `floor(pallet_w/w) ×
   floor(pallet_d/d)` and alternating layers can rotate 90° for true brick
   interlock. → small additive extension to the existing tool, not a new tool.

2. **Asset-resolution behind `create_bin`** (the load-bearing missing piece):
   a `container_asset` arg (or a sibling `add_container(kind, size_hint)` tool)
   that resolves a friendly name (`"KLT"`, `"euro_tote"`, `"wooden_crate"`,
   `"cardbox"`, `"pallet"`) to the real USD path, references it, applies the
   `_physics`/`_visual_collision` variant, and returns the **measured bbox +
   interior floor** so `compute_stack_placement(anchor='inside_floor')` works
   without a hand-written `add_reference` + `get_bounding_box` dance. This is
   what turns "primitive proxy bin" into "real container template."

---

## 3. Proposed templates (real-asset, bbox-derived)

All use the **read-bbox-then-layout** pattern:
`add_reference(container.usd)` → `get_bounding_box` → `compute_stack_placement` →
`setup_pick_place_controller(drop_targets=...)`.

### CT-01 — Palletize-to-EUR-pallet (single-SKU, multi-layer brick)
- Robot: Franka (curobo). Tier B.
- Assets: `Isaac/Props/Pallet/pallet.usd` + N `Cardbox_B1.usd` cartons.
- Layout: `get_bounding_box(pallet)` → `compute_stack_placement(target=pallet, pattern='grid_3x2', n_items=12, layer_rotation_deg=90, anchor='top')` → 2 layers, brick-interlocked.
- Controller: `drop_targets` from placement, `gripper_rotation` per layer, `planning_obstacles=[pallet]`.

### CT-02 — KLT bin-fill (place loose parts INTO a real KLT)
- Robot: Franka or UR10+suction. Tier A→B.
- Assets: `Isaac/Props/KLT_Bin/small_KLT_visual_collision.usd` (interior collision matters).
- Layout: `compute_stack_placement(target=KLT, anchor='inside_floor', pattern='grid_2x3', n_items=6)` — parts rest on the bin's real interior floor.
- Tests interior-floor anchor against a real concave container (not a flat proxy).

### CT-03 — Bin-pick from a tote (suction, random-pose source)
- Robot: UR10 + `surface_gripper`. Tier B.
- Assets source: `Tote_B01_60x40x40cm` (pile of parts inside); dest: KLT or `create_kit_tray`.
- `get_bounding_box(tote)` defines the pick volume; suction picks topmost, places to tray slot.
- Pairs with `CP-NEW-bin-picking-random-pose` lineage but with a REAL tote instead of a cube proxy.

### CT-04 — Kitting tray from multi-container source
- Robot: Franka. Tier A.
- Assets: feed totes `Container_B03_40x30x08cm` (×3, different SKUs) → `create_kit_tray(slot_layout='grid_2x2')` on `packing_table.usd`.
- `color_routing`/recipe: each SKU → its kit slot; `track_slot_occupancy` verifies completion.

### CT-05 — Mixed-SKU palletize (rectangular footprint nesting)
- Robot: Franka (curobo). Tier C. **Exercises gap #1.**
- Assets: `pallet.usd` + mixed `Box_A04_40x30x40cm` / `Box_A06_60x40x17cm`.
- `compute_stack_placement(cube_sizes=[...])` today; ideal: `item_footprint` per SKU for honest nesting. Documents the additive tool extension.

### CT-06 — Crate-to-crate transfer / re-pack
- Robot: UR10. Tier A.
- Assets: `WoodenCrate_A1.usd` (source) → `SM_Crate_A08_Blue_01.usd` (dest), both real-bbox.
- Simplest real-container pick-place; baseline for the category's bbox-derived flow.

### CT-07 — Pack station: cartons onto packing table → seal
- Robot: Franka. Tier B. Extends `CP-NEW-yrkesroll-packer-box-seal`.
- Assets: `packing_table.usd` + `Cardbox_C1.usd`; `compute_stack_placement(anchor='top')` arranges, then seal/close phase.

---

## 4. Authoring rules for this category

- **Never** use `create_bin` for a "real container" — it is a primitive proxy.
  Use `add_reference` + the real USD. Reserve `create_bin` only when a quick
  throwaway collision box is genuinely wanted.
- **Prefer DigitalTwin assets** (`Tote_*`, `Container_*`, `Box_*`, `Bin_*`,
  `Case_*`) when you need dims at author time — they are encoded in the filename
  (`<WxDxH>cm`), so layout can be derived without a USD read. Still call
  `get_bounding_box` at runtime for the authoritative extent.
- **Use the `_physics` / `_visual_collision` variant** for any container that
  receives dropped objects (KLT, SM_Crate) — the render-only `_visual.usd` has
  no collision and items fall through.
- **`anchor='inside_floor'`** for bins/totes/crates (parts go INSIDE);
  **`anchor='top'`** for pallets (cartons stack ON TOP).
- **`planning_obstacles=[container_path]`** in curobo mode so the arm doesn't
  clip the pallet/crate walls during transit.
