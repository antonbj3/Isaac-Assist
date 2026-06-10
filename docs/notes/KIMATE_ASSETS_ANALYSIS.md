# Kimate's Asset Package — Inventory, Catalog, Diff vs NVIDIA Mount, and Planning Fold-In

**Author:** Claude (analysis 2026-06-09) · **Source:** `/home/anton/kimate_assets/` (~14 GB, from Kimate's Google Drive)
**Status:** Analysis + recommendations. All counts/paths verified with `ls`/`find`/`python3 -c` against disk.

> **Headline:** This is a **5,000-entry, pre-cataloged, SimReady-heavy DOMESTIC/SERVICE-robot asset pack** that complements the
> industrial NVIDIA mount almost perfectly. It is the catalog Kimate referred to in Discord — **`asset_catalog.json` exists**
> (10 of them, one per top-level family), and the schema **matches the resolver's expected format exactly**
> (`{name, usd_path, relative_path, category, tags}`). The biggest unlocks: a whole **domestic/kitchen/household domain**
> (Lightwheel + ArtVIP, 243 articulated SimReady appliances + 12 interactive room scenes), a **datacenter domain** (DGX/racks/
> servers), **teleop/imitation-learning scenes** (kitchen-teleop), and **human characters for ergonomics/HRC** (incl. a `Worker`).
> These fill the exact gaps `CANONICAL_TAXONOMY.md` flags as ≈absent: **T6 real-asset-cell**, the **suction/3-finger** gripper
> frontier, **humanoid/G1**, and a brand-new **service-robot domain** the industrial-only mount could never support.

---

## 1. Inventory

**Top-level:** `/home/anton/kimate_assets/assets/` — 56 entries (28 dirs + humanoid `.stl/.part` parts + a few loose `.usd`/`.f3d`).

### 1.1 File-type counts (whole package, 4,236 files)

| Ext | Count | | Ext | Count |
|---|---|---|---|---|
| `.usd` | 2,131 | | `.png` | 1,218 |
| `.usda` | 112 | | `.jpg` | 260 |
| `.usdc` | 5 | | `.mdl` (materials) | 85 |
| `.stl` | 14 | | `.hdr`/`.exr` | 14 |
| `.part` (Onshape) | 14 | | `.obj` | 2 |
| `.f3d` (Fusion 360) | 1 | | | |

USD-native (2,248 `.usd*`), texture-heavy (1,478 images), 85 MDL materials. The `.stl/.part` are CAD source for a **humanoid
robot** (Onshape export — see §1.4). `.f3d` is one `Camera Module Assem` (Fusion).

### 1.2 Size by family (top 8)

| Family | Size | What it is |
|---|---|---|
| `Lightwheel_OpenSource` | 4.8 GB | **243 articulated SimReady kitchen appliances** (Manipulation) + 8 locomotion terrains |
| `ArtVIP` | 4.0 GB | **6 interactive household room scenes** + 1,156 furniture/appliance props |
| `Lightwheel_oz5iukPxYq_KitchenRoom` | 1.7 GB | One fully-furnished **kitchen room scene** (sink, dishwasher, microwave, cabinets, door…) |
| `Sample_Scenes_NVD` | 1.5 GB | NVIDIA sample/render scenes (EuclidVR, Astronaut, Claire lookdev, Automotive material lib) |
| `Lightwheel_kb2Hg5blQp_Apartment` | 624 MB | Full **apartment scene** (`scene_04.usd`) |
| `Collected_nova_carter` | 436 MB | **Nova Carter AMR** (collected, with Variants + Parts) |
| `Collected_table` | 285 MB | Table asset |
| Lightwheel single-appliance dirs | 4–52 MB ea | Standalone Blender/StandMixer/Stovetop/Stove SimReady assets |

### 1.3 The 10 bundled catalogs — counts by category

Each top-level family ships its own `asset_catalog.json` with `metadata.total_assets` + `assets[]`:

| Catalog (family) | total_assets | Dominant categories |
|---|---|---|
| `Warehouse_NVD` | **1,465** | equipment 260, container 153, box 146, pallet 139, shelf 105, tool 63, cabinet 35, vehicle 27 |
| `ArtVIP` | **1,156** | cabinet 182, appliance 125, table 84, decor 53, chair 43, shelf 36, box 32, tool 30 |
| `Residential_NVD` | **507** | decor 217, table 39, chair 32, food 26, utensil 26, appliance 15, lighting 15 |
| `Lightwheel_OpenSource` | **378** | appliance 175, container 28, decor 7, cabinet 5 |
| `SimReady_Containers_Shipping_01_NVD` | **334** | container 124, electronics 10, equipment 7 |
| `SimReady_Furniture_Misc_01_NVD` | **220** | utensil 23, chair 12, food 11, table 10, cabinet 4 |
| `SimReady_Containers_Shipping_02_NVD` | **212** | box 93, pallet 56, container 4 |
| `Characters_NVD` | **184** | character 184 (figures + their materials) |
| `Datacenter_NVD` | **36** | equipment 15, electronics 6 (DGX, racks, switches) |
| `Sample_Scenes_NVD` | **23** | (uncategorized — render/sample scenes) |

**Grand total across the 10 top-level catalogs: 4,515 catalog entries** (counting each `asset_catalog.json`'s `assets[]`).
Note: many entries are sub-USDs (materials, parts) of a parent, so distinct *placeable* assets is lower, but the catalog is
deliberately granular (every material is searchable by tag).

### 1.4 The humanoid CAD parts (root-level `.stl`/`.part`)

14 STL meshes + 14 Onshape `.part` descriptors at the package root form a **complete humanoid robot kinematic chain**:
`torso`, `pelvis`, `waist`, `hip_pitch_yaw`, `shoulder_pitch_yaw`, `upper/lower_humeral`, `right_forearm`, `upper/lower_femoral`,
`lower_knee`, `lower_leg`, `footpads`, `blade`. The `.part` files are Onshape document references (documentId/elementId — a live
CAD link, not just a mesh). This is **CAD source for a custom humanoid**, distinct from the G1 USD; relevant to the
"humanoid asset-gated" frontier but as *buildable parts*, not a drop-in SimReady articulation.

### 1.5 The major families, grouped

- **SimReady DOMESTIC (the new domain):** `Lightwheel_*` (243 articulated appliances: Blender, CoffeeMachine, Dishwasher,
  ElectricKettle, Microwave, Oven, RangeHood, Refrigerator, Sink, StandMixer, Stove, Stovetop, Toaster, ToasterOven) +
  `ArtVIP` (1,156 household props + 6 interactive room scenes) + `Residential_NVD` (507 home props) +
  `SimReady_Furniture_Misc_01_NVD` (kitchen/dining: utensils, plates, bowls, food).
- **Interactive room SCENES (teleop/IL-ready):** `ArtVIP/Scenes/` + `ArtVIP/Interactive_scene/` (kitchen, dining_room,
  children_room, small/large_living_room, kitchen_with_parlor — 6 each), `Lightwheel_..._KitchenRoom`, `Lightwheel_..._Apartment`,
  `Lightwheel_OpenSource/Locomotion/{Apartment,KitchenRoom,2-StoryStaircase}`.
- **TELEOP/imitation-learning:** `Collected_kitchen_scene_teleop_closed_drawer/kitchen_scene_teleop_closed_drawer.usd`
  (a teleop demo scene — drawer-manipulation start state).
- **DATACENTER (the second new domain):** `Datacenter_NVD` — DGX_A100, Rack_42U, Server_1U/2U, QM8700/SN-series switches,
  cable trays, PDUs, DataHall scenes (`DataHall_Full_01`, `DataHall_NoRacks_01`).
- **HUMAN CHARACTERS:** `Characters_NVD` — Reallusion/ActorCore figures: **`Worker`**, `uniform_m/f_0001`, `business-f-0002`,
  `party-m-0001`, `Debra`, plus an `Orc` (and all their material sub-USDs → the 184 count).
- **INDUSTRIAL (overlaps NVIDIA mount):** `Warehouse_NVD` (1,465 — boxes/pallets/shelves/containers/vehicles), the two
  `SimReady_Containers_Shipping_*` packs (shipping containers, pallets, boxes), packing tables, corrugated boxes.
- **ROBOTS / VEHICLES (overlap):** `Collected_nova_carter`, `Collected_carter_v1_physx_lidar`, `Collected_basic_vehicle_m`.
- **TERRAINS (legged-locomotion):** `Lightwheel_OpenSource/Locomotion/` — Grass, GravelGround, MudGround, SnowGround,
  SLATEGround, 2-StoryStaircase (8 ground/terrain types for quadruped/humanoid gait).
- **SAMPLE/RENDER:** `Sample_Scenes_NVD` (EuclidVR, Astronaut, Claire human-head lookdev, Automotive material library).

---

## 2. `asset_catalog.json` — YES, it exists, and the schema matches the resolver

**This is the catalog Kimate meant.** `find` returns 10 top-level `asset_catalog.json` (one per family) plus a duplicated set
nested under `Lightwheel_jYI5DYTM9W_StandMixer009/` (that one dir accidentally contains copies of 6 other families' catalogs —
a packaging artifact, ignore it).

**Schema of each catalog (verified):**
```json
{
  "metadata": {
    "total_assets": 184,
    "by_category": { "character": 184 },
    "uncategorized": 0,
    "paths_scanned": ["/home/kimate/Desktop/assets/Characters_NVD"]
  },
  "assets": [
    {
      "name": "Worker",
      "usd_path": "/home/kimate/Desktop/assets/Characters_NVD/Assets/Characters/Reallusion/Worker/Worker.usd",
      "relative_path": "Assets/Characters/Reallusion/Worker/Worker.usd",
      "category": "character",
      "tags": ["worker", "reallusion", "characters", ...]
    }
  ]
}
```

**Match against the resolver** (`service/isaac_assist_service/chat/tools/handlers/scene_blueprints.py:60-86`,
`_build_asset_index()`):

| Resolver reads | Catalog provides | Match |
|---|---|---|
| `catalog.get("assets", [])` | `assets[]` list | ✅ |
| `entry.get("name")` | `name` | ✅ |
| `entry.get("category")` → `type` | `category` | ✅ |
| `entry.get("usd_path")` → `path` | `usd_path` | ✅ |
| `entry.get("relative_path")` → `rel_path` | `relative_path` | ✅ |
| `entry.get("tags")` | `tags` | ✅ |
| `catalog["metadata"]["total_assets"]` (written on register) | `metadata.total_assets` | ✅ |

**The schema is exactly the schema-of-record.** This is the same format `download_asset` writes when it registers a new asset
(`scene_blueprints.py:1004-1019`). So Kimate's package is the *canonical producer* of the format the resolver was built to read.

**Two integration caveats (must fix before mounting):**
1. **Absolute `usd_path` is `/home/kimate/Desktop/assets/...`** — Kimate's machine, not ours. The resolver's downstream
   `_shared.py:283-285` already prefers `ASSETS_ROOT_PATH + rel_path` over `usd_path` when `rel_path` is present, so
   **`relative_path` is the portable key and it is populated** — good. But anything that reads `usd_path` directly (e.g.
   `_handle_catalog_search` returning `path = entry["usd_path"]`) will hand back a dead `/home/kimate/...` path. Fix:
   rewrite `usd_path` to the local root on import (cheap one-pass script), or make the resolver always derive `usd_path` from
   `ASSETS_ROOT_PATH + relative_path`.
2. **10 catalogs, the resolver loads ONE** (`Path(assets_root) / "asset_catalog.json"`). The package has **no single merged
   catalog at the `assets/` root.** Either (a) **merge** the 10 into one `assets/asset_catalog.json` (concatenate `assets[]`,
   sum `total_assets`, prefixing each `relative_path` with its family dir), or (b) extend the resolver to glob
   `*/asset_catalog.json`. **Option (a) is lower-risk** — it needs zero resolver change and keeps the single-file contract.
   → **Sync point with Kimate:** confirm he intends the per-family catalogs as the unit, and agree on who owns the merge.

---

## 3. Diff vs the NVIDIA mount (`/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/`)

### 3.1 NEW in Kimate's package (NVIDIA mount has nothing equivalent)

| New capability area | Kimate has | NVIDIA mount | Example path (Kimate) |
|---|---|---|---|
| **Articulated SimReady kitchen appliances** | 243 (Lightwheel Manipulation) | ❌ none | `Lightwheel_OpenSource/Manipulation/CoffeeMachine059/` |
| **Interactive household ROOM scenes** | 12 (ArtVIP) + apartment + kitchen | ❌ (only Hospital/Office/Simple_Room shells) | `ArtVIP/Interactive_scene/kitchen/` |
| **Domestic furniture/food/utensils** | ~1,200 (ArtVIP+Residential+Furniture) | ❌ industrial-only props | `Residential_NVD/...`, `SimReady_Furniture_Misc_01_NVD/...` |
| **Datacenter (DGX/racks/servers/switches)** | 36 (Datacenter_NVD) | ❌ none | `Datacenter_NVD/.../DGX_A100_01`, `DataHall_Full_01` |
| **Teleop / imitation-learning scene** | kitchen-teleop (drawer) | ❌ none | `Collected_kitchen_scene_teleop_closed_drawer/kitchen_scene_teleop_closed_drawer.usd` |
| **Pre-built `asset_catalog.json` (resolver-ready)** | 10 catalogs, 4,515 entries | ❌ (mount has no catalog — current resolver falls back to slow rglob) | `*/asset_catalog.json` |
| **Vendor SimReady packs** (Lightwheel/ArtVIP) | yes | ❌ | — |
| **Locomotion terrains** (grass/mud/snow/gravel/stairs) | 8 | ⚠️ partial (`Environments/Terrains`, `Outdoor`) | `Lightwheel_OpenSource/Locomotion/MudGround/` |
| **Custom humanoid CAD parts (Onshape)** | 14 STL+part | ❌ (mount has G1/H1 USD, not buildable CAD) | `/home/anton/kimate_assets/assets/torso_02b.{stl,part}` |

### 3.2 OVERLAP (both have it — do NOT duplicate templates)

| Asset | Kimate | NVIDIA mount |
|---|---|---|
| **Nova Carter / Carter v1 AMR** | `Collected_nova_carter/nova_carter.usd`, `Collected_carter_v1_physx_lidar/` | `Robots/NVIDIA/NovaCarter/nova_carter.usd`, `Robots/Carter` |
| **Warehouse industrial props** (boxes/pallets/shelves/containers) | `Warehouse_NVD` (1,465), `SimReady_Containers_Shipping_*` | `Props/{KLT_Bin,Pallet,Cardboard,Rack,...}` |
| **Packing table** | `Collected_SM_HeavyDutyPackingTable_C02_01` | `Props/PackingTable/packing_table.usd` |
| **Human characters** | `Characters_NVD` (Reallusion ActorCore: Worker/uniform/business + Orc/Debra) | `Isaac/People/Characters` (24 figures: construction/police/medical/business) + `NVIDIA/Assets/Characters` |

**Correction to the briefing premise:** the NVIDIA mount **does** have human characters (`Isaac/People/`, 24 rigged figures
oriented at walking-pedestrian animation; plus `NVIDIA/Assets/Characters`). So characters are an *overlap*, **not** strictly
new — BUT (a) NVIDIA's People are **not in any catalog** (invisible to `catalog_search` today), and (b) Kimate's set adds a
**`Worker`** + `uniform`/`business`/`party` ActorCore actors **already tagged and cataloged**. So the *new* thing is
"cataloged, retrievable human actors incl. a Worker," not "humans at all."

---

## 4. Map to capability gaps (`CANONICAL_TAXONOMY.md` axes + `asset_templates_environments.md`)

`CANONICAL_TAXONOMY.md §2` lists the measured gaps. Here is what Kimate's package fills:

| Taxonomy gap (verbatim from §2) | What Kimate's assets unlock |
|---|---|
| **A6 `T6 real-asset ≈absent`; `T7 absent`** — *"the asset-bridge risk"* (taxonomy §3 calls the first T6 the Phase-2A pilot) | **The biggest fill.** 243 articulated SimReady appliances + 12 interactive room scenes give a deep, real-mesh, articulated pool for the **first T6 real-asset cells** — and not just "KLT bin + crate" but full domestic cells. The catalog being resolver-ready means the asset-bridge can be exercised *immediately*. |
| **A2 `suction thin` / `3-finger ≈absent`** | Flat-top SimReady appliances + furniture + boxes (SimReady_Containers) are exactly the **flat/boxy faces a suction cup grips and a jaw can't** — substrate for the suction-pick / suction-sort frontier on real meshes (vs the nvidia_cube). |
| **A1 `g1-humanoid asset-gated`; quadruped 2 stubs** | Onshape humanoid CAD parts (buildable chain) + 8 **locomotion terrains** (grass/mud/snow/gravel/stairs) give the legged/humanoid frontier a *terrain* dimension it lacked. (G1 SimReady USD still needed from Nucleus — these are complementary, not a G1 drop-in.) |
| **A1 `mobile-manip absent`** | Nova Carter (AMR) + furnished room/apartment scenes = the **drive-then-pick in a real home** substrate for `pick.mobile.amr-*`. |
| **A3 `composed multi-stage = 0`; A6 T7** | Interactive room scenes are pre-composed multi-object environments — a natural host for the **first composed/T7 cells** once Phase-4 composition lands. |
| **NEW DOMAIN — service/domestic robotics** | **Not in the taxonomy at all today** (A7 domains are pick/palletize/sort/convey/assemble/navigate/inspect/train/dialog/canary/bridge/safety/compose — all industrial). The kitchen/household pack unlocks a **whole new A7 domain: `service`/`domestic`** (open-drawer, load-dishwasher, tend-stove, fetch-from-fridge) impossible on the industrial-only mount. |
| **NEW DOMAIN — datacenter** | DGX/rack/server/cable-tray assets unlock a **`datacenter` domain** (rack-and-stack, cable routing, server swap, robotic DC maintenance) — a second new industrial vertical. |
| **Ergonomics / human-robot-collaboration (HRC)** | The `Worker` + cataloged ActorCore actors are the **human-in-the-cell** substrate for ergonomics/HRC/safety canonicals (a person in the workspace as a dynamic obstacle / collaboration partner) — pairs with `safety.ur10.estop-*` (taxonomy §3 T6) and `ASSET_TUTORIAL_IDEAS` persona scenes. |
| **Teleop / imitation-learning** | The kitchen-teleop scene is the **first IL/teleop start-state** — a new template *family* (teleop-demo → imitation-learning) the industrial mount couldn't seed. |

### NEW template/tutorial categories these unlock (impossible with the industrial-only mount)

1. **`service` / `domestic` domain** — open-drawer, load/unload dishwasher, place-mug-in-cabinet, tend-stovetop, fetch-from-fridge.
   (Articulated Lightwheel appliances + ArtVIP kitchen scenes.) **A genuinely new A7 domain segment.**
2. **`datacenter` domain** — rack-and-stack a 1U server, route a cable in a cable tray, swap a DGX module. (Datacenter_NVD.)
3. **HRC / ergonomics tier** — a `Worker` shares the cell with the arm; the gate measures keep-out / collaboration / ergonomic
   reach. (Characters_NVD + safety spine.)
4. **Teleop → imitation-learning template family** — record/replay a kitchen-drawer teleop demo as a learnable trajectory.
5. **Legged-locomotion-over-terrain** — quadruped/humanoid gait over grass/mud/snow/gravel/stairs (the terrain axis).
6. **Real-mesh suction/3-finger picks** — the thin-gripper frontier on real SimReady geometry instead of `nvidia_cube`.

---

## 5. Fold into planning — concrete recommendations

### (a) Where to mount it for the resolver

Mount the package and point the resolver's env vars at it:
```bash
ASSETS_ROOT_PATH=/home/anton/kimate_assets/assets        # resolver root (single asset_catalog.json expected here)
# or, to keep BOTH the NVIDIA industrial mount AND Kimate's domestic pack live, add a multi-root env:
# (origin/master's asset_resolution.py uses ISAAC_ASSIST_ASSET_ROOTS — a colon/comma list)
ISAAC_ASSIST_ASSET_ROOTS=/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0:/home/anton/kimate_assets/assets
```
**Note:** the *working branch* (`refactor/2026-05-12-foundation-night-1`) resolver in `scene_blueprints.py` only reads a single
`ASSETS_ROOT_PATH/asset_catalog.json` (multi-root + `ISAAC_ASSIST_ASSET_ROOTS` live on `origin/master`'s
`multimodal/asset_resolution.py`). So on this branch you must either set `ASSETS_ROOT_PATH=/home/anton/kimate_assets/assets`
**and** produce a merged top-level catalog, or port the multi-root resolver forward. **Don't unset the NVIDIA mount** — the robot
library (`_CATALOG_ROBOTS` → `Collected_Robots/*.usd`) and all industrial templates still resolve against it.

**Required preprocessing before mount (one script):**
- **Merge** the 10 per-family `asset_catalog.json` into one `/home/anton/kimate_assets/assets/asset_catalog.json` (concat
  `assets[]`, sum `total_assets`, **prefix each `relative_path` with its family dir** so paths resolve from the new root).
- **Rewrite or drop `usd_path`** — replace the `/home/kimate/Desktop/assets/` prefix with the local root, OR strip `usd_path`
  and let the resolver derive it from `ASSETS_ROOT_PATH + relative_path` (safer; `_shared.py` already prefers `rel_path`).
- Delete/ignore the stray nested catalogs under `Lightwheel_jYI5DYTM9W_StandMixer009/` (packaging artifact).

### (b) Should the bundled `asset_catalog.json` be the schema-of-record? — **Yes.**

The bundled schema **is already** the resolver's expected schema *and* the format `download_asset` writes. Adopt it as the
schema-of-record verbatim. **Sync point with Kimate (Discord):**
1. Confirm he intends **per-family** catalogs as the distribution unit (and that *we* own the merge), vs. shipping one merged
   catalog next time.
2. Agree the **portable key is `relative_path`** (not the absolute `usd_path`), and that producers should write `usd_path`
   relative-to-root or omit it. This is the one real interop bug.
3. Confirm whether his repo's "asset catalog" referenced in Discord is *these JSON files* (almost certainly yes) or a separate
   index — so we don't maintain two.

### (c) New template categories to add to the backlog

Add to `CANONICAL_TAXONOMY.md` / the expansion backlog (each clears the §1 defensibility gate — each forces a DISTINCT,
gate-measurable capability the industrial corpus never could):
- **`service.franka.open-drawer.001`** (T6) — articulated drawer/cabinet manipulation; success = drawer-open angle. *defends:*
  first articulated-fixture interaction (vs rigid pick); contrast all rigid-body picks.
- **`service.mobile.amr-fetch-from-fridge.001`** (T6→mobile-manip) — Carter + arm in `ArtVIP/kitchen` drives-then-opens-then-picks.
  *defends:* mobile-manip in a real home (A1=mobile-manip absent + A6=T6).
- **`service.franka.load-dishwasher.001`** (T6) — place N items into an articulated dishwasher rack; grid-placement on a real mesh.
- **`datacenter.ur10.rack-and-stack-1u.001`** (T6) — insert a 1U server into a 42U rack; tight-tolerance insertion on a real mesh
  (pairs with the force-gated-insertion frontier).
- **`hrc.ur10.shared-cell-keepout.001`** (T6 + safety) — a `Worker` enters the workspace; arm must respect a keep-out / slow-down.
  *defends:* first dynamic-human obstacle the gate grades (vs static obstacles).
- **`teleop.franka.kitchen-drawer-demo.001`** — record/replay the bundled teleop scene as an IL trajectory; new success signal
  (trajectory-match), a new template *family*.
- **`navigate.anymal.terrain-gait.001`** (asset-gated quadruped) — gait over the 8 Lightwheel terrains; the terrain axis.
- **Real-mesh suction frontier:** `pick.ur10.suction-appliance-flat.001` — suction on a flat SimReady appliance face (fills
  A2=suction-thin on real geometry, not `nvidia_cube`).

Keep these **bases**; their mass/material/scene siblings are **procedural variants** (taxonomy §4).

### (d) Assets that change Phase-3 asset-bridge & Phase-5 robot ladder

- **Phase-3 asset-bridge (the T6 real-mesh risk):** This package is the **single biggest de-risker**. The asset-bridge's open
  question was "can the function-gate grade a grip on a real SimReady mesh?" — Kimate's 243 articulated appliances +
  shipping/furniture SimReady packs give a **deep, pre-cataloged, retrievable pool** to pilot against immediately. Recommend the
  **first T6 pilot use a Lightwheel appliance or a SimReady_Containers box** (real mesh, flat faces) rather than waiting on the
  KLT/crate from the NVIDIA mount — the catalog is already resolver-shaped, so `catalog_search` → `add_reference` → grip works
  end-to-end with no new plumbing. **This pulls the Phase-2A/Phase-3 pilot forward.**
- **Phase-5 robot ladder (franka→ur10→multi→AMR→g1→anymal):** 
  - **AMR/mobile-manip rung** gets real substrate now (Carter + furnished homes) — `pick.mobile.amr-*` was "absent"; it's now
    asset-unblocked (still needs the mobile-manip co-planning code, but the *scene* exists).
  - **Quadruped/legged rung** gets a terrain dimension (8 grounds) it didn't have.
  - **Humanoid rung:** the Onshape CAD parts are *buildable* humanoid source, not a G1 SimReady drop-in — they **do not** replace
    the still-needed Nucleus G1 SimReady asset, but they're useful for a custom-humanoid track if that's ever in scope. Keep the
    "G1 SimReady still gated on Nucleus" note in `2026-05-28-g1-humanoid-impl-scope.md`.
- **New domains are a planning decision, not just a backlog add:** `service`/`domestic` and `datacenter` are **new A7 domain
  segments** not in `CANONICAL_TAXONOMY.md §2 A7`. Adding them widens the corpus scope beyond industrial — worth an explicit
  decision with Kimate/Anton on whether the product targets service robotics (the assets strongly suggest *yes*, since Kimate
  curated a domestic-heavy pack).

---

## 6. Open items / sync points

1. **Merge + path-rewrite script** for the 10 catalogs (owner: us; needed before mount). `relative_path`-prefixing + `usd_path`
   localization.
2. **Confirm with Kimate** (Discord) that these JSON files *are* the "asset catalog" he added to the repo, and agree
   `relative_path` is the portable key.
3. **Resolver branch gap:** working branch reads one catalog; `origin/master` has multi-root `asset_resolution.py`. Decide
   whether to port multi-root forward or merge-to-single. (Merge-to-single is least-risk on this branch.)
4. **Domain-scope decision:** adopt `service`/`domestic` + `datacenter` as new A7 domains? (Assets say yes.)
5. **Mount location:** decide read-only bind-mount vs. symlink (the pack is 14 GB; mirror the `data/`-symlink pattern used
   elsewhere rather than copying).
