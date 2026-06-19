# Real-asset MEGA-direction — depth triage (cont.319t, 2026-06-19)

Anton's directive: "Den ska hantera en enorm komplexitet i scen-genereringen" — conveyors, differing
dimensions, humanoids, forklift, larger scenes. All assets surveyed **Kit-free via pxr** (no Kit boot needed
for the survey half — `from pxr import Usd`; see reference_isaac_assets_downloaded memory). Triaged by build
depth so the focused Kit sessions go in value/risk order (NOT effort — per Anton's no-time-estimates rule).

## Done
- **Real objects** (YCB) — PROVEN (CP-YCB-*, box-like reliable). `compute_spawn_recipe`.
- **Real containers** (KLT tote) — PROVEN (CP-KLT-BIN, hollow-collision fix). `container_recipe`.
- **Dimension-handling** — `real_asset_spawn.py` recipes compute spawn-z / orientation / reach per asset.

## Triaged — next builds (value/risk order)

### 1. Conveyors — BELT-MOTION PROVEN (CP-CONV-01, cont.319u); pick-cell = CP-CONV-02
31 `ConveyorBelt_A*.usd`. Belt rides at **1.781 m** (vs generated ~0.8 m) → floor-Franka can't reach → pedestal.
No built-in node → retrofit surface velocity on `/World/Belt`. Full plan + `conveyor_recipe`:
**docs/notes/CONVEYOR_INTEGRATION.md**. ✅ CP-CONV-01 GENUINE: real A09 belt + 3-API surface-velocity retrofit on /World/Belt carries cubes +2.5m along the belt (RAW-verified, 0.2 m/s, end-first arrival). CP-CONV-02 (pedestal-Franka pick): reach VALIDATED but the pick-controller does NOT engage (5 grounded variants, all plan_calls=0, arm never moves). PRIME SUSPECT = pedestal base z=1.4 (every proven pick gold is FLOOR-base z=0; setup_pick_place_controller likely has a floor-base assumption). FOCUSED FOLLOW-UP (task #52): try the LOWERED-conveyor approach (floor Franka + belt translated to the proven ~0.8m pick height = proven floor-base controller path).

### 2. Forklift — MODERATE (CORRECTED cont.319aa: TRICYCLE drive, NOT Carter-differential)
`Isaac/Robots/IsaacSim/ForkliftB/forklift_b.usd`: 8 rigidbody links. ★Joint structure (Kit-free pxr):
- `lift_joint` Prismatic-Z (body->lift) = the FORK actuator (set joint position to raise/lower).
- `back_wheel_drive` Revolute-X (back_wheel) = the single DRIVE wheel (set angular velocity).
- `back_wheel_swivel` Revolute-Z (back_wheel_swivel->body) = the STEERING (set swivel angle).
- 4× `*_roller` Revolute-X = PASSIVE support rollers (front+back, not driven).
So it is a 3-wheel TRICYCLE forklift (one rear driven+steered wheel + passive front rollers) — ★my earlier
"reuses Carter nav" was WRONG: Carter is DIFFERENTIAL (two driven wheels); the forklift needs a
steer-angle + drive-velocity (tricycle/Ackermann-ish) controller, NOT differential. bbox 3.0×1.1×2.9 m.
- ★FIRST PROOF (simplest, bounded) = CP-FORK-01 FORK LIFT only: stationary forklift, set `lift_joint`
  position to raise the fork under/with a pallet, scene_eyes-verify the pallet rises with the fork. No drive.
- DRIVE (CP-FORK-02) = tricycle control (back_wheel_drive velocity + back_wheel_swivel steer); navigate to a
  pallet. More involved than Carter (steering, not differential); own focused session. nav_gate displacement applies.
- Drive: reuse the **SOLVED Carter nav** (`navigate_to` closed-loop drives Carter end-to-end — see
  project_isaac_assist_nav_stub). Open Q: is forklift_b a WheeledRobot the nav machinery initializes (like
  Carter, works) or does it fail articulation-init (like jetbot)? → 1 Kit probe answers it.
- Lift: actuate the single prismatic joint to raise/lower the fork under a pallet (Props has pallets).
- Build: CP-FORK-01 = forklift drives to a pallet + forks lift it. Distinct value: a MOBILE manipulator that
  isn't an arm. `Props/Forklift/forklift.usd` is a static PROP (scene decoration, trivial) — the ROBOT is ForkliftB/C.

### 3. Larger scenes — COMPOSITION/decoration (MODERATE, mostly assembly)
`Isaac/Environments/Simple_Warehouse/warehouse_with_forklifts.usd`, `Modular_Warehouse/*` (h10m straight/corner
tiles), `Simple_Warehouse/full_warehouse.usd`. Animated **Biped characters** (`Isaac/People/Characters`) = scene
ACTORS (animated, not physics manipulators) → populate scenes. Build: spawn an environment USD as the stage
backdrop + place work-cells in it. Mostly add_reference + layout; the cells already work. The "enorm komplexitet"
is the cell-in-environment composition + collision against real warehouse geometry.

### 4. Humanoid — DEEP (GR00T policy domain), focused session
Unitree **G1** (`Isaac/Robots/Unitree/G1`, 44 links / 43 revolute / 29-dof+hands), **H1**, classic Humanoid
(16-link mujoco RL body). Manipulation ≠ cuRobo arm planning → **whole-body / GR00T policy**. The codebase
already has a GR00T path (CP-NEW-groot-load-eval-live, groot-eval-harness, g1 GR00T asset
`Isaac/Samples/Groot/Robots/g1_*.usd`). Defer to a focused GR00T session; not blocking the moderate items above.

## Order recommendation
CP-CONV-01 (conveyor) → CP-FORK-01 (forklift, reuses nav) → warehouse-scene composition → humanoid/GR00T.
Each is a fresh-context Kit session (avoid stacking deep builds in one fatigued session — over-investment lesson).
