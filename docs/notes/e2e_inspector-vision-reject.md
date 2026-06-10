# E2E trace — `inspector-vision-reject` (T4, franka, inspect-reject)

**Persona:** quality inspector (ONET SOC 51-9061, Inspectors/Testers/Sorters)
**One-sentence request:** *"a camera classifies parts on the belt as good/defect and routes defects to a reject lane"*
**Matched template:** `workspace/templates/CP-NEW-inspect-reject.json` (`task_id: CP-NEW-inspect-reject`)
**Tier:** T4 (dialog/multi-stage build) — note `verified_status` = `build-spec-2026-05-10; smoke-test ✓ 1/1 (52s)` (one smoke run, not an N-of-M function-gate pass).

This document traces the COMPLETE action sequence a user + the LLM acting for them take to reach the
target scene, the static pre-filter, the expensive physics gate, the OUTCOME, and every honesty caveat.
Each step tagged `[USER]`/`[LLM]`/`[SYSTEM]` and `[CHEAP-static]`/`[EXPENSIVE-physics]`.

---

## Why this template (grep evidence)

`grep -liE "classif|good.{0,8}defect|reject"` over `workspace/templates/` surfaces 6 real candidates:

| template | why not chosen |
|---|---|
| `CP-18` | pre-tagged cubes, no runtime classify (its own goal says so) |
| `CP-48` | "TRUE runtime-vision" but `verified_status: draft; passes=3 n=27 wilson_lower=0.0385; demoted 2026-05-15` — a demoted draft |
| `CP-50` | vision *kitting* (4 cubes 2 red/2 blue), not pass/reject divert |
| `CP-59` | dual-Franka vision bin-pick, 2-arm — wrong topology |
| `CP-NEW-yrkesroll-inspector-reject-divert` | strongest persona match (SOC 51-9061) but `form-gate pending; function-gate pending` — never gated |
| **`CP-NEW-inspect-reject`** | **chosen** — quality-engineer persona, conveyor + overhead camera + good/defect + PassBin/RejectBin, the only one with a recorded smoke ✓ |

`intent.structural_tags` = `['isaac:transport.conveyor', 'isaac:robot.fixed_base.arm', 'isaac:topology.single_station', 'isaac:vision.inspect_and_reject']` — a 1:1 structural match to the request.

---

## The target scene (from `role_defaults`)

- **Franka** `franka_panda` @ `[0,0,0.75]`, quat `[0.7071,0,0,0.7071]` (reach shell ≈ **0.855 m**)
- **ConveyorBelt** `[0.0,0.4,0.78]`, size `[2.5,0.3,0.05]`, surface velocity `[0.15,0,0]` (+x)
- **InspectCamera** `[0,0.4,1.20]` looking down at `[0,0.4,0.78]`, fov 60 (overhead inspector)
- **PickSensor** proximity trigger `[0.4,0.4,0.835]`
- **PassBin** `[0.5,-0.4,0.75]` · **RejectBin** `[-0.5,-0.4,0.75]`
- **5 cubes** down the belt: green,green,**red**,green,green (the red = `Cube_3` = the defect)

---

## Numbered narrative

### 1. [USER] [CHEAP-static] — states the goal
User types the one-liner. No build yet.

### 2. [LLM] [CHEAP-static] — intent classification → template retrieval
The LLM maps the request to `pattern_hint: sort`, `routing_axis: semantic_class`, `destination_kind: n_bins_routed`, and retrieves `CP-NEW-inspect-reject`. Pure text retrieval; no Kit.

### 3. [USER] [CHEAP-static] — (T4 dialog) confirms parameters
T4 = the LLM may ask for n_cubes / defect rate / which bin is reject. `roles.workpieces` allows `min:1 max:8` via `param_name: n_cubes`; defaults to 5 (4 good + 1 defect). User confirms defaults. This is the only branch point; on "kör på" the LLM proceeds with defaults.

### 4. [SYSTEM] [CHEAP-static] — new stage
`omni.usd.get_context().new_stage()` (the gate harness does this at `gate_one.py:22`). Cheap.

### 5. [LLM→SYSTEM] [CHEAP-static] — lighting + ground + physics scene
Emits `create_prim(DomeLight)`, `set_attribute(intensity=1000)`, `create_prim(Ground, scale[20,20,1])` + `apply_api_schema(PhysicsCollisionAPI)`, then **`set_physics_scene_config({enable_gpu_dynamics:False, broadphase_type:"MBP"})`**. USD authoring only — no simulation. Handler: `handlers/physics.py` (registered), `set_physics_scene_config` confirmed in `_models.py`.

### 6. [LLM→SYSTEM] [CHEAP-static] — table + robot
`create_prim(Table)` + collision, then `robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0,0,0.75], orientation=[0.7071,0,0,0.7071])`. `robot_wizard` spawns the Franka from a clean home pose (per MEMORY: robot_wizard avoids the wound-start asset bug). Articulation authored, not stepped.

### 7. [LLM→SYSTEM] [CHEAP-static] — conveyor
`create_conveyor(prim_path="/World/ConveyorBelt", position=[0.0,0.4,0.78], size=[2.5,0.3,0.05], surface_velocity=[0.15,0,0])`. Handler in `handlers/scene_authoring.py` (registered, `_models.py` ✓). The surface-velocity drive is authored; it only moves once the timeline plays.

### 8. [LLM→SYSTEM] [CHEAP-static] — 5 cubes + materials + semantic color
Python `for` loop emits, per cube: `create_prim(Cube_i, size=0.05)`, `create_material(mat_<color>_i, diffuse_color=...)`, `assign_material`, and the 4 physics schemas (`PhysicsRigidBodyAPI`, `PhysicsCollisionAPI`, `PhysicsMassAPI`, `PhysxRigidBodyAPI`).
**HONESTY — the "color" IS the classification oracle.** The red/green diffuse color is what `color_routing` later reads back off USD Semantics (see step 12). The cube colors ARE the ground-truth labels, authored at build time.

### 9. [LLM→SYSTEM] [CHEAP-static] — the two bins
`create_bin(PassBin, [0.5,-0.4,0.75])` and `create_bin(RejectBin, [-0.5,-0.4,0.75])`. Both bins authored. Handler `handlers/scene_authoring.py`.

### 10. [LLM→SYSTEM] [CHEAP-static] — the inspection camera
`configure_camera(camera_path="/World/InspectCamera", position=[0,0.4,1.20], look_at=[0,0.4,0.78], fov=60)`.
**HONESTY — `configure_camera` is CODEGEN-ONLY.** `handlers/sensors.py:138 _gen_configure_camera` just authors a `Camera` prim (auto-creates if missing, `sensors.py:159-185`). It does NOT attach a classifier or a render product to the routing logic. The camera is scenery — it exists so the scene *looks* like an inspection station, but nothing at runtime reads its image to route.

### 11. [LLM→SYSTEM] [CHEAP-static] — the pick trigger
`add_proximity_sensor(sensor_path="/World/PickSensor", position=[0.4,0.4,0.835], size=[0.06,0.06,0.06])`. `handlers/sensors.py:333 _gen_add_proximity_sensor`. Fires when a belt-carried cube enters the pick zone → tells the controller "a part has arrived".

### 12. [LLM→SYSTEM] [CHEAP-static] — install the routing controller (the crux)
```
setup_pick_place_controller(
    robot_path="/World/Franka", target_source="curobo",
    sensor_path="/World/PickSensor", belt_path="/World/ConveyorBelt",
    source_paths=[Cube_1..Cube_5], destination_path="/World/PassBin",
    color_routing={"green": "/World/PassBin", "red": "/World/RejectBin"},
    planning_obstacles=["/World/Table","/World/ConveyorBelt","/World/PassBin","/World/RejectBin"])
```
This installs the cuRobo controller with **`color_routing`** dispatch (`handlers/pick_place.py:456,497`; codegen 3160-3340).
**HONESTY — runtime routing reads USD Semantics, NOT the camera.** `pick_place.py` (≈3324-3330) resolves each picked cube via `Semantics.SemanticsAPI.Get(p, "Semantics_color"/"Semantics_colour"/"Semantics_class")` and falls back to `destination_path` if absent. So defect→RejectBin is decided by the **authored color label**, an oracle, not by a VLM looking at the belt. The "camera classifies" framing is satisfied structurally but the discrimination modality at runtime is USD introspection.

### 13. [LLM→SYSTEM] [CHEAP-static] — (build-time only) `vision_detect_objects`
`tools_used` lists `vision_detect_objects`; `extension_notes` says it is "called once at canonical-build time to verify class mapping; runtime dispatch uses semantic labels." The real handler `handlers/vision.py:1313 _handle_vision_detect_objects` IS a true VLM call (Gemini provider, `_get_vision_provider()`), capturing the viewport and returning `{detections,count,model}`. But in THIS template it is a one-shot sanity check of the label map — it is **not in the routing loop**. If it were wired live it would be `[EXPENSIVE]` (network VLM round-trip per cube); as used it is build-time and skippable.

---

## 14. [SYSTEM] [CHEAP-static] — STATIC-EYES PRE-FILTER (`scripts/qa/scene_validate.py`)
Runs BEFORE the physics gate. No timeline play except a ~2.5 s passive settle; checks REACH / TARGET_REACH / interpenetration / support / physics-instability using authored positions. Franka reach = **0.855 m** (`scene_validate.py:32`).

Distances from the Franka base `[0,0,0.75]`:
- PickSensor `[0.4,0.4,0.835]` → **0.572 m** ✓ reachable
- PassBin `[0.5,-0.4,0.75]` → **0.640 m** ✓ reachable (TARGET_REACH ok)
- RejectBin `[-0.5,-0.4,0.75]` → **0.640 m** ✓ reachable
- **`Cube_1` `[-1.0,0.4,0.835]` → 1.080 m → > 0.855 m, OUT OF REACH at spawn**

**Where the static pre-filter catches/forgives a problem CHEAPLY:** `Cube_1` (and `Cube_2` at 0.894 m) spawn outside the arm's shell. A naive REACH check would flag `REACH: Cube_1 ... >reach 0.855`. But `scene_validate.py:173 belt_reachable()` sees the cube sits on a conveyor moving +x at 0.15 m/s whose forward travel brings its closest approach within 0.855 m, so it FORGIVES it (no false flag). This is the cheap pre-filter doing exactly its job: it confirms the geometry is buildable and the bins are placeable **without ever running the 180 s physics gate** — turning a would-be expensive failure into a 2.5 s static pass. Both bins reachable ⇒ the reject *destination* is geometrically valid, so any failure that follows is controller/routing-side, not geometry-side.

---

## 15. [SYSTEM] [EXPENSIVE-physics] — THE FUNCTION GATE (`gate_one.py` → `simulate_traversal_check`)
`gate_one.py` builds the canonical, settles (`settle_after_canonical`), then calls `simulate_traversal_check` with the template's own `simulate_args`:
```
cube_paths = [Cube_1, Cube_2, Cube_4, Cube_5]   # the 4 GREEN cubes only
target_path = /World/PassBin
duration_s  = 180
```
This plays the timeline for **180 s of sim time** (belt runs, sensor fires, cuRobo plans/dives/grips/places per cube) — the expensive step.

### Gate success-criterion (the OUTCOME), verbatim from `diagnostics.py:4446-4449`
```
if len(cube_paths) > 1:          # multi-cube → LENIENT
    success = bool(delivered) and upright_ok
else:
    success = bool(in_xy and above_floor and at_rest and upright_ok)
```
Here `len(cube_paths)=4 > 1`, so the gate passes if **ANY ONE of the 4 green cubes** comes to rest inside the PassBin bbox (`in_xy`+`above_floor`+`at_rest`, per-cube `diagnostics.py:4431`) **AND** the primary cube is upright (`upright_dot ≥ 0.85`, `:4443-4444`). Single-run (n_runs=1) ⇒ `success` = run 0's value (`:4449`, `:4577-4578`).

**Stated gate outcome:** *PASS iff ≥1 green "good" part is delivered, at rest, inside `/World/PassBin`, with the primary cube upright.* (`gate_one.py:88` prints `GATE success=…`.)

---

## 16. [USER] [CHEAP-static] — inspector reads the verdict
The quality inspector sees the gate JSON: `success`, `delivered_cubes`, `per_cube_status`. End of flow.

---

## The big honesty gap — the REJECT path is NEVER gated

The request's whole point is *route defects to a reject lane*. **The gate does not verify it.**

- `simulate_traversal_check` takes a **single** `target_path` (`_models.py SimulateTraversalCheckArgs:7`) = `/World/PassBin`. There is no second target.
- `simulate_args.cube_paths` deliberately **excludes `Cube_3`** (the red defect). The red cube and the RejectBin are simply not measured.
- The template's own `failure_modes[2]` admits this: *"Red cube (Cube_3) reach RejectBin: not validated by gate (gate only checks PassBin); need separate test for reject path."*

So a build that **dumps every cube — including the defect — into PassBin** would still PASS the gate (any green delivered + upright). The "defect rejection," the defining behavior of the persona's request, is structurally present but **unverified**.

---

## Tools that would be needed but DO NOT EXIST (grep-confirmed)

1. **A two-destination / per-class routing gate** — e.g. `simulate_routing_check(class_to_target_map)` that confirms green→PassBin AND red→RejectBin. `grep -rnE "verify_routing|routing_correct|per_class_route|confusion|classification_accuracy"` over `handlers/*.py` + `scripts/qa/*.py` → **no match**. The only "reject" hits in `diagnostics.py` are `ctrl:pick_reject` (IK reach-rejection, unrelated, `:3460-3486`) and "connection confusion" (`:1053`).
2. **A multi-target `simulate_traversal_check`** — current handler is single-`target_path`; routing scenarios need N targets in one run. Missing.
3. **A live vision→routing binding** — `configure_camera` is codegen-only (`sensors.py:138`); routing reads USD Semantics, not the camera. No tool wires `vision_detect_objects` output into `setup_pick_place_controller` as the per-cube class source in this template. (`setup_pick_place_with_vision` exists — `_models.py:1125` — and DOES run runtime classification, but THIS template chose `setup_pick_place_controller` + USD-color oracle instead, so the camera is decorative.)
4. **A defect-rate / classification-accuracy metric** — no tool reports false-accept (defect→PassBin) or false-reject rates, which is the actual quality-inspection KPI.

## Unverified / draft caveats
- `verified_status` = a single 52 s smoke ✓, NOT an N-of-M function-gate pass. `motion_controllers.verified = []` (curobo/rmpflow/moveit2 all **untested**).
- `failure_modes[0]`: "vision_detect_objects may return different schema than expected."
- `failure_modes[1]`: color_routing "needs class-label registry; rolls back to destination_path if classifier errors" — i.e. on any label miss, EVERY cube silently goes to PassBin (the default), defeating rejection without erroring.
- Runtime "classification" = USD-color introspection (oracle), not camera perception. Honest label: *vision-themed-routing-with-USD-color-oracle*, not faithful camera inspection.

---

## Step ledger (user-action steps)
1. User states goal · 2. (LLM retrieve) · 3. User confirms params · 4–13. (LLM/SYSTEM build) · 14. (SYSTEM static-eyes) · 15. (SYSTEM gate) · 16. User reads verdict.

**User-action steps = 3** (steps 1, 3, 16). All other steps are LLM/SYSTEM.

**Static-eyes catches cheaply:** Cube_1/Cube_2 spawn out of the 0.855 m reach shell; `belt_reachable()` forgives (belt carries them in) → 2.5 s static PASS instead of a wasted 180 s gate run; both bins confirmed reachable.

**Gate outcome:** PASS iff ≥1 green good-part rests inside `/World/PassBin` upright (multi-cube ANY-delivered, `diagnostics.py:4446-4449`). The reject lane — the persona's actual ask — is built and reachable but **not measured by any existing gate or tool.**
