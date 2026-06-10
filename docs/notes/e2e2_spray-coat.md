# E2E Trace — spray-coat (continuous-coverage, UR10)

**Scenario ID:** spray-coat
**Domain:** coating
**Robot:** UR10
**Task type:** continuous-coverage
**User request:** *"spray-coat a panel at constant standoff distance across its surface"*
**Date traced:** 2026-06-09
**Tier:** T-CONTINUOUS-PATH (coverage/trajectory family — NOT pick-place, NOT atomic CW)

---

## 0. Closest real template (grep result)

The request maps almost 1:1 to an **already-drafted** canonical:

- `workspace/templates/CP-NEW-yrkesroll-paint-sprayer-trajectory.json`
  - goal: *"A UR10 picks a rigid spray-gun proxy (Cylinder Body + Cone Nozzle joined by a FixedJoint) from a wall mount, then traces a boustrophedon raster across a target Cube panel (0.50 × 0.30 × 0.02 m) while maintaining a ~0.10 m standoff between nozzle tip and panel surface."*
  - ONET SOC 51-9123 (Painting, Coating, and Decorating Workers), `pattern_hint: "other"`.
  - structural_tags: `isaac:gesture.coverage_raster`, `isaac:trajectory.boustrophedon`, `isaac:tool_use.spray_gun`, `isaac:workpiece.panel`.
  - `verified_status: drafted-2026-05-16; form-gate-schema ⏳ pending-lint; function-gate ⏳ Kit RPC` — **never passed a gate.**

Sibling continuous-path templates that share the class:
- `CP-NEW-welder-seam-track.json` (1-D seam follow, compliance-driven contact)
- `CP-NEW-yrkesroll-welder-mig-tack.json` (DISCRETE move→dwell→marker rendering; the welder template's own `extension_notes` says the *continuous* variant needs `record_waypoints + follow_trajectory_with_compliance`)
- `CP-NEW-oxe-sweep-into-dustpan.json` (debris-push gesture, no parametric coverage)

So the retrieval layer DOES have a match. The architectural question is what happens when it is instantiated and run through the gate. That is where this trace pays off.

---

## 1. Step-by-step traced flow

Legend: `[USER]` / `[LLM]` / `[SYSTEM]` and `[CHEAP-static]` (build-time USD authoring, no physics stepping) / `[EXPENSIVE-physics]` (requires Kit RPC + PhysX stepping).

| # | Actor | Cost | Action | Grounding (file:line) |
|---|-------|------|--------|-----------------------|
| 1 | `[USER]` | — | Types *"spray-coat a panel at constant standoff distance across its surface"* | — |
| 2 | `[SYSTEM]` | `[CHEAP-static]` | Retrieval embeds the prompt; `isaac:gesture.coverage_raster` + `tool_use.spray_gun` tags surface `CP-NEW-yrkesroll-paint-sprayer-trajectory` as top hit | template `intent.structural_tags` |
| 3 | `[LLM]` | `[CHEAP-static]` | Instantiates the canonical via `execute_template_canonical` → emits the `code` body | `chat/canonical_instantiator.py`; template `code` field |
| 4 | `[SYSTEM]` | `[CHEAP-static]` | `create_prim` DomeLight, Ground, PaintTable, **Panel** (0.5×0.3×0.02, top z=0.85, semanticLabel `paint_target`) | template `code` lines 1–24; `scene_authoring.py` create_prim |
| 5 | `[SYSTEM]` | `[CHEAP-static]` | `robot_wizard(robot_name="ur10", dest_path="/World/UR10", pos=[0,0,0])` — spawns UR10 at **home joints** (avoids the wound-start asset bug, see MEMORY ur10_wound_start_root) | `handlers/robot.py` robot_wizard; template `code` |
| 6 | `[SYSTEM]` | `[CHEAP-static]` | `create_prim` SprayGun/Body (Cylinder) + SprayGun/Nozzle (Cone); apply `PhysicsRigidBodyAPI/CollisionAPI/MassAPI`; `PhysicsFixedJointAPI` on Body to unify composite | template `code`; `handlers/scene_authoring.py` apply_api_schema |
| 7 | `[SYSTEM]` | `[CHEAP-static]` | `define_grasp_pose(/World/UR10, /World/SprayGun/Body, approach=[0,0,-1])` — advisory only (P7 in inventory: cuRobo never consumes it) | `handlers/pick_place.py` define_grasp_pose; TOOL_GAP_INVENTORY_V2 P7 |
| 8 | `[SYSTEM]` | `[CHEAP-static]` | `setup_pick_place_controller` to pick the gun: `pick_paths=[/World/SprayGun/Body]`, `drop_targets={Body:[0.70,0.0,1.50]}` (z=1.50 deliberately far above panel so the controller's release phase can't drop the gun on the work) | template `code`; `handlers/pick_place.py:293` |
| 9 | `[SYSTEM]` | `[EXPENSIVE-physics]` | **Pick phase executes.** Parallel-jaw UR10 grip closes on the Cylinder body. (Failure_mode: pickup race — if not settled before raster, the gun is left in the rack and the TCP sweeps empty air; mitigation = `sim_control(step,60)` before first waypoint) | template `failure_modes[last]` |
| 10 | `[SYSTEM]` | `[EXPENSIVE-physics]` | **Raster begins.** Entry waypoint `move_to_pose(target=[0.45,-0.15,1.10], rmpflow)` then 14 raster `move_to_pose` calls walking y=-0.15→+0.15 in 0.05 m steps at constant z=0.95 (= panel top 0.85 + 0.10 standoff) | template `code` raster block; `handlers/robot.py:2227` |
| 11 | `[SYSTEM]` | `[EXPENSIVE-physics]` | `record_trajectory(articulation=/World/UR10, duration=60)` samples **JOINT** pos/vel/effort at 60 Hz → `workspace/trajectories/paint_sprayer_raster.npz` | `handlers/robot.py:3779`; template `verify_args.trajectory_path` |
| 12 | `[SYSTEM]` | `[EXPENSIVE-physics]` | `sim_control` steps the world for `duration_s=60` | template `simulate_args` |
| 13 | `[SYSTEM]` | `[CHEAP-static]` | **Function-gate runs.** `verify_args` asks for: FK the recorded joints → project TCP to panel plane → check ≥ `min_coverage_fraction=0.8` of a `coverage_grid=[10,6]` is visited | template `verify_args` |
| 14 | `[SYSTEM]` | — | **Verdict** (see §3) | `multimodal/verifier_registry.py` |

---

## 2. Where it breaks — three stacked failures, root-caused

### FAIL-A (controller class) — `move_to_pose` rmpflow is a SINGLE reactive step, not a trajectory

`_gen_move_to_pose` (handlers/robot.py:2227) with `planner="rmpflow"` (the template default and the backlog's stated `motion_controller_preference: rmpflow`):

```
rmpflow.set_end_effector_target(target_pos, target_ori)   # robot.py ~2384
action = amp.get_next_articulation_action()               # robot.py ~2393  ← ONE call
art.apply_action(action)                                  # robot.py ~2396  ← applied once, no loop
```

There is **no convergence loop** — it sets the target, pulls ONE jacobian action, applies it, returns. Each of the 14 raster `move_to_pose` calls therefore advances the arm by a *single physics-substep's worth of motion* toward that waypoint, then the next call immediately retargets. The EE never reaches waypoint *k* before waypoint *k+1* is commanded. The "boustrophedon raster" collapses into a tiny jitter near the first waypoint. The recorded TCP path visits ≈1 grid cell, not ≥48 of 60. **Coverage ≈ 2%, gate threshold 80%.**

This is NOT a tuning bug. `move_to_pose` is architected as a one-shot reactive primitive for *pick-place pose hops* where the surrounding pick_place controller owns the per-step pump. Used standalone as a path-follower it cannot drive a multi-waypoint trajectory to completion. The template's own `failure_modes` admits this obliquely: *"move_to_pose has no native velocity parameter… determined by Kit RPC executor's internal dwell scaling between waypoints"* — but the deeper truth is there is no executor-side per-waypoint *settle-to-convergence* at all.

### FAIL-B (verifier class) — there is no coverage verifier in the gate

`multimodal/verifier_registry.py` registers exactly **three** function-gate checks:
- `simulate:cube_delivered` (applies_when=`True` — "cube delivery is universal for pick-place")
- `simulate:upright_at_rest`
- `simulate:human_safety_zone`

Grep across `multimodal/` for `coverage|raster|boustrophedon|standoff|visit|fk_|forward_kin` → **zero** functional hits. The template's `verify_args` carries `coverage_grid`, `min_coverage_fraction`, `trajectory_path` — **but no registered check reads them.** The live gate (`scripts/qa/gate_one.py` → `simulate_traversal_check`) computes `success` from *"did a cube reach a target bbox"*. For this scenario:
- `cube_path=/World/SprayGun/Body` never enters `target_path=/World/Panel`'s bbox (the gun stays 0.10 m ABOVE the panel by design — that IS the task).
- So `cube_delivered` returns **FALSE** even on a *perfect* raster.

The gate is **structurally incapable of passing a coating task** because its only universal success criterion is the pick-place delivery oracle. A flawless spray-coat scores identically to a robot that never moves: both deliver zero cubes.

### FAIL-C (data-shape) — `record_trajectory` records joints, coverage needs TCP

`_gen_record_trajectory` (handlers/robot.py:3779) only records Revolute/Prismatic **joint** pos/vel/effort. The template's own failure_mode states it: *"record_trajectory captures joint trajectory, not TCP — coverage verification requires forward kinematics offline… If the consumer skips FK and uses joint values directly, the coverage check is meaningless."* There is no `record_tcp_trajectory` and no FK-replay step wired into any verifier. Even if FAIL-A and FAIL-B were fixed, the coverage number would have to be computed by an offline UR10 FK pass that nothing in the gate currently runs.

---

## 3. Outcome

**Gate verdict: FAIL (`success=False`), and the failure is uninformative.**

- The arm executes a near-stationary jitter (FAIL-A), but even a *correct* raster would report `success=False` because the only criterion is cube-in-bbox (FAIL-B), and the coverage metric the template designed can't be computed anyway (FAIL-C).
- This is the worst diagnostic state: a **false-negative-by-construction**. There is no signal that distinguishes "raster worked perfectly" from "robot stood still" from "gun fell on the floor." The gate is blind to the entire task semantics.
- Honest status: the template is a well-authored *scene*, but the **execution + grading half of the continuous-coverage class does not exist.** It was drafted and parked at `function-gate ⏳ Kit RPC` for exactly this reason.

---

## 4. THE class-level finding (key deliverable)

> **Continuous-coverage / trajectory-follow is a missing CLASS — three coupled gaps, one per layer — and pick-place's primitives cannot be retrofitted into it.**

Just as the humanoid-cabinet trace showed pick-place fundamentally breaks on articulated doors (it needs a *revolute-pull* controller class), this trace shows pick-place's machinery breaks on **surface coverage**. The whole family — spray-coat, paint, powder-coat, plating, seam-weld (continuous), deburr, sand, polish, adhesive-bead, inspection-scan, plasma/laser-clad, conformal-coat — needs primitives that do not exist:

1. **Missing CONTROLLER class — `follow_cartesian_path` / `execute_trajectory`** (a multi-waypoint planner that *runs each segment to completion* at a commanded linear speed, holding tool orientation). Today's options are both wrong: `move_to_pose` rmpflow = one reactive step (FAIL-A); `move_to_pose` lula_rrt = plans a path but "no online action application; the caller must replay" — and nothing replays it. `follow_trajectory_with_compliance` (compliance.py:1077) exists but is contact/impedance-oriented, gated on the absent ros2_control bridge for live mode (P10, `dry_run=False → NotImplementedError`), and is 1-D-seam-shaped, not 2-D-coverage-shaped. **No tool drives a free-space multi-segment Cartesian path to completion.**

2. **Missing GATE/VERIFIER class — `simulate:surface_coverage`** (FK the recorded TCP path, project onto the workpiece surface, score grid-cell visitation + standoff-band adherence). The verifier_registry is hard-wired to the delivery oracle. A coverage check (`coverage_grid`, `min_coverage_fraction`, `standoff_tolerance`) is a NEW `register_function_check` that doesn't exist. Without it, every coating/welding/inspection task is a guaranteed false-negative.

3. **Missing DATA primitive — `record_tcp_trajectory`** (or an FK-replay verifier stage). `record_trajectory` is joint-space only; the coverage metric needs end-effector/tool-tip world poses per frame. This is the cheap one (S effort) but it is genuinely absent and load-bearing for the whole class.

Secondary class-implication: **surface-normal projection** for the standoff. The template hard-codes constant-Z because the panel is flat-horizontal. The moment the panel is tilted or curved (every real car door/fender), the constant-Z plane misses the surface and there is no `project_standoff_along_normal` / raycast-to-surface primitive (the template flags this as failure_mode #2, "would require per-waypoint Z-adjustment from a surface-normal lookup"). That is the curved-surface extension of the same class.

**This is NEW.** TOOL_GAP_INVENTORY_V2 is pick-place/conveyor/belt centric (M1 belt control, M12 moving-obstacle, P-series grasp tooling). It contains **no** coverage verifier, **no** path-follow controller, **no** TCP-recorder, **no** surface-normal-projection entry. The continuous-coverage class is unrepresented in the gap inventory.

---

## 5. Asset reality check (Kimate's new assets)

Searched `/home/anton/kimate_assets/assets` for spray/paint/coat/booth/nozzle/gun:
- Only **materials/textures** (`MetalPainted_White_Glossy`, `T_paint_02_BC.png`) and **residential props** (`Residential_NVD/.../PaintRoller`, `PaintTray`) — no spray-gun tool, no paint booth, no robot-mountable coating EOAT.
- The 243 articulated appliances / kitchens / datacenter / Worker actor / Allegro hand are **irrelevant** to coating.
- Verdict: the template's primitive-proxy gun (Cylinder+Cone+FixedJoint) is the only available representation; no asset substitution improves this scenario. The gap is in CONTROLLER + GATE + DATA layers, not in assets.

---

## 6. Tool-gap summary (NEW gaps only)

| Gap | Class | Effort | Blast (this family) |
|-----|-------|--------|---------------------|
| `follow_cartesian_path` / `execute_trajectory` — multi-waypoint free-space path-follow that runs each segment to completion at commanded speed | CONTROLLER | L | spray/paint/plating/deburr/sand/polish/adhesive/inspect/continuous-weld (~10+ yrkesroll) |
| `simulate:surface_coverage` verifier — FK TCP, project to surface, score grid visitation + standoff band | GATE | M | same family (every coating/inspection/continuous-weld gate is currently a false-negative) |
| `record_tcp_trajectory` (or FK-replay verifier stage) — end-effector world poses per frame, not joints | DATA | S | same family |
| `project_standoff_along_normal` / raycast-to-surface — curved/tilted-panel standoff | CONTROLLER (geometry) | M | curved-surface coating (automotive panels, all real bodywork) |

These are coupled: shipping any one alone does not pass a single coating task — the class needs the controller + the verifier + the TCP recorder together.
