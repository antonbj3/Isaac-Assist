# Real-conveyor integration — de-risk findings (cont.319t, 2026-06-19)

Anton's MEGA-direction, first call-out: real conveyors + "hur man hanterar de skiljande dimensionerna
jämfört med våra genererade". This is the static de-risk; the Kit build is the focused follow-up.

## Assets (UNBLOCKED)
- **31** `ConveyorBelt_A01..A31.usd` in `Assets/Isaac/5.0/Isaac/Props/Conveyors/`.
- A09 = clean **straight** belt (4.0 m × 0.9 m) → ideal first template. A01 = corner-ish (long −y belt).
  A15 = wide sortation (belt y-extent 4.8 m).

## Structure (per A01/A09/A15, via Kit-free pxr inspection)
- Default prim `/World` (Xform).
- `/World/SM_ConveyorBelt_*` (Mesh) — the **static frame**, has CollisionAPI. GeomSubsets: Body/Bolts/Cables/
  Caps/FixBody/Legs/Pipes/Sheets.
- `/World/Belt` (Xform, **RigidBody + Collision**) → `SM_*_Belt` Mesh — the **moving surface**.
- `/World/Rollers` (Xform, RigidBody + Collision) → SM_*_Roller01..N.

## The "skiljande dimension" (the key finding)
- The belt **surface rides at z ≈ 1.781 m** (top of the belt mesh), consistent across variants — the belt sits
  on a ~1.78 m-tall frame. Our GENERATED belts ride ~0.8 m. So:
  - An object must spawn at **belt_top + half_height + clearance** (`spawn_z_5cm_cube = 1.811`), NOT on a 0.8 m
    surface. `real_asset_spawn.conveyor_recipe()` computes this.
  - **A floor-mounted Franka (reach ~0.85 m) CANNOT reach a 1.781 m belt.** This is the real scene-complexity
    Anton means. Design options for the build:
    1. **Pedestal**: raise the arm base ~1.13 m (recipe `reach_note`). Cleanest; arm picks straight off the belt.
    2. **Lower/reposition the conveyor** (scale or translate −z) so the pick zone drops into reach — but then the
       belt no longer rides at its native height (loses dimensional fidelity).
    3. **Feeder pattern**: belt at native height feeds a *chute/ramp* to a low pick zone the floor-arm reaches —
       most realistic industrially, most build work.
  - Recommend **option 1 (pedestal)** for the first GENUINE conveyor template (least new machinery, keeps native
    belt height). The robot_wizard / template can place the Franka on a raised base.

## Belt physics (RETROFIT required)
- The assets ship **NO** ConveyorNode and no authored velocity. The `/World/Belt` is a RigidBody ready to drive.
- Retrofit options: (a) `omni.isaac.conveyor` ConveyorNode on the belt prim, or (b) the same kinematic
  surface-velocity material our generated belts (CP-38/CP-52) already use — reuse that machinery, point it at
  `/World/Belt` along the feed axis (`feed_axis` from the recipe). Reuse (b) first (proven path, no new ext).

## Tool
- `scripts/qa/real_asset_spawn.py::conveyor_recipe(usd)` → belt ride-z, feed axis + length/width, belt prim to
  drive, spawn-z, `exceeds_floor_reach` + `reach_note`. Selftest-guarded on A09.
- **Kit-free pxr inspection works** (`from pxr import Usd` in plain python3) — survey ANY Isaac asset's
  structure/dims without booting Kit. Big lever for the rest of the MEGA-direction (humanoids, forklift, large
  scenes): inspect-then-build, no Kit boot for the survey half.

## Focused build session (next)
1. CP-CONV-01: A09 belt + Franka on a ~1.13 m pedestal + 5 cm cubes spawned at 1.811 m on the belt.
2. Retrofit surface velocity on `/World/Belt` (reuse generated-belt material), feed +x.
3. Verify: cubes ride the belt to the pick zone (scene_eyes belt-timeline + per-object x-advance), Franka picks
   off the moving belt into a bin. scene_eyes already tracks belt surface-velocity + per-object trajectory.
4. Then dimension-handling generality: A01 (corner), A15 (wide) — different feed axes / multi-lane.
