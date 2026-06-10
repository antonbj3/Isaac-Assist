# Asset Templates — Conveyors + Feed Mechanisms

Category proposal for the canonical-template expansion. Scope: the 47 real
`ConveyorBelt_A0x.usd` props + rotary table / gravity-feed / sensor-gate feed
dynamics. All asset paths and tool names below are **verified on disk / in the
tool surface** (date 2026-06-09), not assumed.

---

## 1. Verified assets (on disk)

Root: `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/`

### Conveyor belt props (47 total)
`Isaac/Props/Conveyors/ConveyorBelt_A{01..34, 37..49}.usd`
- **47 files confirmed** (`A35` + `A36` are absent — numbering is not gapless).
- Binary USDC (crate). Sizes 13–31 MB. **Visual mesh geometry only** — peeked
  `ConveyorBelt_A01.usd`: `PXR-USDC` header, all-`MESH` prims, **no embedded
  conveyor OmniGraph, no PhysxSurfaceVelocityAPI, no RigidBody/Collision**.
  → They are *dress* props. To make them carry objects you must add the physics
  drive yourself (see "real-belt physics overlay" pattern below).

### Feed / rotary
- `Isaac/Sensors/NVIDIA/Example_Rotary.usda` (+ `Debug_Rotary`, `_2D`, `_BEAMS`)
  — these are **rotary LIDAR sensor** examples, **NOT** a rotary feed table.
  There is **no rotary-table prop asset** on disk → the rotary table is built
  procedurally by the `create_rotary_table` tool (disc + base + revolute joint).
- **No hopper / chute / gravity-feeder prop** on disk. The only `*dispenser*`
  hits are Hospital/Office water/soap/towel dispensers (decor, not feed).
  → Gravity feed is built procedurally by `create_gravity_dispenser`.

**Implication:** real assets buy *visual realism* for the belt itself; every feed
*behaviour* (motion, rotary, gravity, sensor-gate) is procedural via existing
tools. None of the 47 belt props is referenced by ANY current template
(`grep -rln "ConveyorBelt_A" workspace/templates` → 0 hits). This category's main
new value is **wiring the real props in**.

---

## 2. Tool surface (verified)

| Tool | Status | Evidence |
|---|---|---|
| `create_conveyor` | **exists** | `robot.py:1744` `_gen_create_conveyor`; model `_models.py:1682`. Applies the 3-API combo (CollisionAPI + kinematic RigidBodyAPI + PhysxSurfaceVelocityAPI) to a Cube strip; auto-creates the prim if missing. |
| `create_conveyor_track` | **exists** | `robot.py:1854`; model `_models.py:1704`. Multi-segment polyline track (waypoints → oriented belt segments). Used for L/S-bends and lane geometry. |
| `create_rotary_table` | **exists** | `robot.py:4685` `_handle_create_rotary_table`; model `_models.py:1049`. Composite: static base + Cylinder disc + revolute joint, optional `angular_velocity_deg` drive. |
| `create_gravity_dispenser` | **exists** | `robot.py:4858`; model `_models.py:1010`. Pre-spawns N items stacked above `target_xy`, fall under gravity. |
| `create_recirculation_loop` | **exists** | `tool_schemas.py:1862`; model `_models.py:844`. 4-segment rectangular closed loop = the **cross-belt / recirculation sorter** substrate (NVIDIA #17 Postal Cross-Belt Sorter). |
| `add_proximity_sensor` | **exists** | `tool_schemas.py:4001`. Invisible physics trigger volume; flips `isaac_sensor:triggered`. **This IS the sensor-gate / belt-pause trigger** ("Used for belt-pause triggering, gate sensors" — verbatim from its description). |
| belt-pause / resume logic | **exists (inside controller)** | `pick_place.py:1277` "Belt pause/resume" + `_belt_pause_request`. Driven by `setup_pick_place_controller(belt_path=..., sensor_path=...)`. There is **no standalone `pause_conveyor` / `set_belt_speed` tool** — pause is a controller behaviour keyed on `belt_path`. |
| sort routing | **exists** | `setup_pick_place_controller(color_routing=...)` (`_models.py:1748`) + `setup_pick_place_with_vision` (`_models.py:1125`) + `add_vision_classifier_gate`. Routes each picked item to a per-class bin. |
| **cross-belt physical diverter / pneumatic pusher / lane-merge gate** | **MISSING** | `grep -rniE 'create_diverter\|create_pusher\|lane_merge\|create_sorter\|belt_diverter\|pneumatic_pusher'` over `tool_schemas.py` + `handlers/` → **0 hits**. Sortation today is done by a *robot arm* picking off the belt + `color_routing`, OR by `create_recirculation_loop` recirculating until picked. A *passive pneumatic pusher that knocks a parcel onto a cross belt* has no tool. |

### Gaps worth a tool (call-outs, not blockers)
1. **`create_belt_diverter`** (MISSING) — a pop-up/pusher or swing-arm gate at a
   belt junction that physically deflects an item onto a perpendicular belt
   (no arm needed). Would unlock true two-belt sortation without a manipulator.
2. **`set_conveyor_velocity` / `pause_conveyor`** (PARTIAL) — pause exists only
   inside `setup_pick_place_controller`. A standalone tool would let
   sensor-gated *accumulation* templates run without a robot in the loop.
3. **`create_lane_merge`** (MISSING) — a Y-junction that merges two infeed belts
   onto one outfeed. Today approximated by two `create_conveyor` strips angled
   into a third — workable, but no single tool.

These are deliberately surfaced so the parent can decide build-vs-defer; the
templates below are authored to work with **only the existing tools**, treating
the missing ones as future enhancements.

---

## 3. The two authoring patterns

**Pattern P-PROC (procedural belt):** `create_conveyor` makes a Cube strip and
drives it. Cheap, deterministic, what every current CP template does. Use when
the *behaviour* is the test (pick timing, pause, sort).

**Pattern P-REAL (real-asset belt + physics overlay):** `add_reference` the
visual `ConveyorBelt_A0x.usd` for realism, then lay a **thin invisible collision
strip** along the belt top with `create_conveyor` (surface velocity only) so
objects actually ride. The visual prop has no physics; the strip supplies it.
This is the **new capability** this category adds — no template does it yet.

```
# P-REAL skeleton (verified tools only)
create_prim(prim_path="/World/Belt1", prim_type="Xform", position=[0,0.4,0.0])
add_reference(prim_path="/World/Belt1",
              reference_path="/mnt/.../Isaac/Props/Conveyors/ConveyorBelt_A05.usd")
# invisible driven strip sitting on the prop's transport surface
create_conveyor(prim_path="/World/Belt1/DriveStrip",
                position=[0,0.4,<belt_top_z>], size=[<L>,<W>,0.02],
                surface_velocity=[0.2,0,0])   # ~1/3 of apparent speed (stick-slip, see CP-01)
```
NOTE on `<belt_top_z>`: must be measured from the chosen `ConveyorBelt_A0x`
bbox at instantiation time (the props differ in height/length — A01 ≈ 31 MB long
belt vs A05 ≈ 13 MB short). The template ships a default and a `verify_args`
note to re-measure with `compute_bbox` on the referenced prim.

---

## 4. Proposed templates (6, across feed dynamics)

IDs use a `CV-` prefix (Conveyor) to avoid colliding with existing `CP-` numbers.
Tiers: **A** = atomic/scene-build, **B** = single-robot behaviour,
**C** = multi-station / composite.

### CV-01 — Static staging belt, fixed-station pick (real asset) · Tier B
- **Robot:** Franka Panda (alt UR5e, Kinova Gen3).
- **Task:** A *stationary* real `ConveyorBelt_A05` props the staging area; 4 cubes
  pre-placed on it within reach; Franka picks each to a bin. Belt does **not**
  move (surface_velocity=0) — isolates the real-asset-reference + collision-strip
  pattern from belt motion.
- **Assets:** `ConveyorBelt_A05.usd`.
- **Capability:** P-REAL real-asset wiring, static feed.
- **Tools:** `add_reference`, `create_conveyor` (v=0 strip), `create_bin`,
  `robot_wizard`, `add_proximity_sensor`, `set_physics_scene_config`,
  `setup_pick_place_controller(target_source=curobo)`.
- **Why first:** smallest delta from CP-01; proves the real prop loads + collides
  before adding motion.

### CV-02 — Moving-belt pick with sensor-gated belt pause (real asset) · Tier B
- **Robot:** Franka Panda.
- **Task:** Real `ConveyorBelt_A01` (long) runs at low speed +X; cubes start
  OUTSIDE reach and ride in; an `add_proximity_sensor` at the pick station
  pauses the belt (controller `belt_path` pause/resume), Franka picks, belt
  resumes. This is CP-01's *behaviour* but on the **real prop** + explicit
  sensor-gate framing.
- **Assets:** `ConveyorBelt_A01.usd`.
- **Capability:** moving-belt pick, sensor-gate/belt-pause.
- **Tools:** `add_reference`, `create_conveyor` (driven strip), `create_bin`,
  `add_proximity_sensor`, `robot_wizard`, `set_physics_scene_config`
  (`enable_gpu_dynamics=False`, `broadphase=MBP` — required for surface velocity),
  `bulk_set_attribute` (`sleepThreshold=0`), `setup_pick_place_controller(belt_path=...)`.
- **Failure modes inherited from CP-01:** GPU dynamics silently kills surface
  velocity; non-zero `sleepThreshold` freezes cubes on a paused belt; cubes
  inside reach at t0 → belt never visibly moves.

### CV-03 — Two-belt transfer / right-angle handoff · Tier C
- **Robot:** Franka Panda (single arm bridging two belts).
- **Task:** Infeed `ConveyorBelt_A05` carries cubes +X to a transfer station;
  Franka picks and places onto a perpendicular outfeed `ConveyorBelt_A37`
  running +Y which carries them away to a bin at the far end. Exercises *two
  independent belt drives* + a robot transfer (the stand-in for the MISSING
  physical diverter).
- **Assets:** `ConveyorBelt_A05.usd`, `ConveyorBelt_A37.usd`.
- **Capability:** two-belt transfer, cross-direction handoff.
- **Tools:** 2× (`add_reference` + `create_conveyor`), `add_proximity_sensor`
  (infeed gate), `create_bin`, `robot_wizard`,
  `setup_pick_place_controller(belt_path=<infeed>, color_routing=None)`.
- **Note:** documents the diverter gap — "a physical pusher would remove the arm;
  no such tool today (`create_belt_diverter` MISSING)".

### CV-04 — Lane-merge infeed (two belts → one) · Tier C
- **Robot:** none required for the merge itself; optional Franka downstream pick.
- **Task:** Two infeed belts (`create_conveyor_track` polylines angled at ±20°)
  merge onto a single outfeed belt; cubes from both lanes interleave by physics
  alone (no merge gate). Outfeed feeds a `add_proximity_sensor` count station.
- **Assets:** procedural belts via `create_conveyor_track` (real props optional
  for dressing — `ConveyorBelt_A12.usd` straight outfeed).
- **Capability:** lane-merge feed dynamics.
- **Tools:** `create_conveyor_track` ×2 (angled infeeds) + `create_conveyor`
  (outfeed strip), `add_proximity_sensor`, `create_heap_zone`/`create_prim`
  (cube sources). Optional `add_reference` outfeed prop.
- **Gap call-out:** `create_lane_merge` MISSING — this template *demonstrates*
  the need (interleaving is uncontrolled / can jam at the Y).

### CV-05 — Rotary index table feed + pick · Tier C
- **Robot:** Franka Panda (alt UR10 for larger radius).
- **Task:** `create_rotary_table` (radius 0.35 m, `angular_velocity_deg=30`)
  continuously rotates; cubes ride the disc into the pick zone; an
  `add_proximity_sensor` over the pick station gates the Franka pick as each
  cube indexes in. Rotary-feed analogue of the linear belt.
- **Assets:** procedural (rotary table is tool-built — no prop on disk).
- **Capability:** rotary-table feed, sensor-gated indexing.
- **Tools:** `create_rotary_table`, `create_prim`+`apply_api_schema` (cubes on
  disc with `sleepThreshold=0`), `add_proximity_sensor`, `create_bin`,
  `robot_wizard`, `setup_pick_place_controller`.
- **Precedent:** CP-56 / CP-67 / kitting-station already use `create_rotary_table`
  — reuse their drive settings.

### CV-06 — Gravity dispenser feeder onto belt · Tier C
- **Robot:** UR10 (alt Franka) bin-filling downstream.
- **Task:** `create_gravity_dispenser` drops N cubes onto the head of a moving
  real `ConveyorBelt_A08`; belt carries them to the pick station; robot fills a
  bin. Combines gravity feed → belt transport → pick in one cell (NVIDIA #25
  UR10BinFilling lineage, now on a real belt).
- **Assets:** `ConveyorBelt_A08.usd`.
- **Capability:** gravity-feed dispense + belt transport.
- **Tools:** `create_gravity_dispenser`, `add_reference`+`create_conveyor`
  (driven strip), `add_proximity_sensor`, `create_bin`, `robot_wizard`,
  `setup_pick_place_controller(belt_path=...)`.
- **Precedent:** CP-21 / CP-71 / gravity-dispenser-feeder use the dispenser tool.

### (Stretch) CV-07 — Cross-belt recirculation sorter · Tier C
- Built on `create_recirculation_loop` (the verified closed-loop substrate) +
  `setup_pick_place_with_vision` color routing. Items recirculate until the arm
  picks the matching class to its bin. This is the genuine NVIDIA #17 Postal
  Cross-Belt Sorter; flagged stretch because it leans on the vision-routing
  pipeline's known axis-pairing limitation (`build_color_routing_from_vision`
  v1 caveat). Include only if vision routing is in scope for this batch.

---

## 5. Coverage matrix (feed dynamics requested)

| Feed dynamic | Template | Real asset? | New capability |
|---|---|---|---|
| static belt pick | CV-01 | yes (A05) | real-prop wiring |
| moving-belt pick | CV-02 | yes (A01) | sensor-gate pause on real prop |
| two-belt transfer | CV-03 | yes (A05+A37) | dual drive + handoff |
| lane-merge | CV-04 | optional (A12) | merge feed dynamics |
| rotary table | CV-05 | no (tool-built) | rotary index feed |
| gravity dispenser | CV-06 | yes (A08) | dispense→belt→pick |
| cross-belt sorter | CV-07 (stretch) | optional | recirculation + vision route |

Belt-prop variety: the 47 props let each template pick a *different* belt
silhouette (long A01, short A05, curved/angled variants A37/A12) so the category
visibly exercises the asset set rather than one prop 6 times.

---

## 6. Authoring guardrails (carry into every CV template)

- `set_physics_scene_config(enable_gpu_dynamics=False, broadphase_type="MBP")` —
  **mandatory**; PhysxSurfaceVelocityAPI is silently ignored under GPU broadphase.
- Apparent belt speed ≈ 3× configured `surface_velocity` (stick-slip w/ rubber).
  Set ~1/3 of desired.
- Cubes: `PhysxRigidBodyAPI` + `bulk_set_attribute(physxRigidBody:sleepThreshold=0)`
  or they sleep on a paused belt and never resume.
- Real props are visual-only → always add a `create_conveyor` collision/drive
  strip; never expect the referenced USD to carry objects by itself.
- `<belt_top_z>` differs per prop — re-measure bbox at instantiation; ship a
  default + a `verify_args` re-measure note.
- Rubber material on cubes only, never on robot fingers (triangle-mesh-on-dynamic
  PhysX warnings block the viewport on Play — CP-01/CP-02 finding).
