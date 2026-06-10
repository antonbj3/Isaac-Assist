# E2E Trace — `barcode-divert` (tier T4, robot ur10, task barcode-sort)

**Persona:** logistics sorter
**One-sentence request:** *"scan a barcode on each parcel and divert it to the matching lane"*
**Matched template:** `workspace/templates/CP-NEW-barcode-scanner-divert.json` (`verified_status: "drafted-2026-05-16; form-gate ⏳; function-gate ⏳"` — **DRAFT, never gate-passed**)

Legend: **[USER]** human action · **[LLM]** model acting for the user · **[SYSTEM]** harness/gate/Kit · **[CHEAP-static]** no physics (USD/geometry/registry, ms) · **[EXPENSIVE-physics]** Kit build + PhysX sim (seconds–minutes).

---

## 1. [USER] · [CHEAP-static] — issue the request
The logistics sorter types: *"scan a barcode on each parcel and divert it to the matching lane."* This enters the chat service as a single natural-language turn. No tools run yet.

## 2. [SYSTEM] · [CHEAP-static] — retrieve the matching template
The template/role retriever (`service/isaac_assist_service/chat/tools/template_retriever.py`, `role_retriever.py`) matches the request against the library. The string "scan a barcode … divert … matching lane" lands squarely on **`CP-NEW-barcode-scanner-divert`** — its `intent.pattern_hint = "sort"`, `structural_tags` include `isaac:routing.barcode_sku_divert`, `isaac:sensor.barcode_reader`, `isaac:routing.fallthrough_catchall` (template lines 31, 42-49). This is the single best (and effectively only) barcode-routing exemplar in 504 templates.

## 3. [LLM] · [CHEAP-static] — read the goal and pick the robot
The LLM reads `goal` (template:3): a barcode-scanner SKU-based lane-divert station — items on a conveyor, a `barcode_reader_sensor` reads each SKU, a **Franka** arm diverts to LaneA / LaneB / LaneC by a routing table, unrecognised SKUs fall through to LaneC.

**Robot mismatch surfaced here.** The scenario specifies **robot = ur10**, but the template's `roles.primary_robot.constraints = ["franka_panda", "ur5e", "kinova_gen3"]` (template:53-57) — **ur10 is NOT an allowed substitution** for this template, and `role_defaults.primary_robot.class = "franka_panda"` (template:108). To honour ur10 the LLM must override the role default, which is outside the template's declared compatibility envelope and untested (`motion_controllers.verified = []`, template:349). HONEST NOTE: running this scenario as ur10 is unverified; the geometry (lane bins at ±0.35 m, y=−0.40) was reach-sized for the 0.855 m Franka envelope, not the 1.30 m UR10 envelope, and the UR10 wound-start / wrist-spin / suction-grip issues documented in MEMORY do not apply to a Franka-authored parallel-jaw scene.

## 4. [LLM] · [CHEAP-static] — emit the scene-build tool calls
The LLM walks the template `code` block (template:22) and emits, in order. Each tool below was confirmed registered in `tool_schemas.py` (schema_hits=1) and backed by a real handler:

| # | tool | handler | physics |
|---|------|---------|---------|
| a | `create_prim` ×N (DomeLight, Ground, Cell, Table, items, scanner body) | `handlers/scene_authoring.py` | [CHEAP-static] |
| b | `set_attribute` / `apply_api_schema` | scene_authoring | [CHEAP-static] |
| c | `set_physics_scene_config(enable_gpu_dynamics=False, broadphase_type="MBP")` | `handlers/physics.py` | [CHEAP-static] (config only) |
| d | `robot_wizard(robot_name="franka_panda"→ur10, dest=/World/Franka, pos=[0,0,0.75])` | `handlers/robot.py` | [CHEAP-static] (references asset) |
| e | `create_conveyor(/World/MainBelt, pos=[0,0.40,0.78], size=[3,0.35,0.05], vel=[0.15,0,0])` | `handlers/pick_place.py` | [CHEAP-static] |
| f | `create_material` ×4 (Orange/Cyan/Yellow/DarkGrey) | scene_authoring | [CHEAP-static] |
| g | 6× `create_prim` Item + `apply_api_schema` (Rigid/Collision/Mass/PhysxRigid) + `assign_material` + `set_semantic_label(class_name="sku_a/b/c", semantic_type="class")` | scene_authoring + `handlers/vision.py:_gen_set_semantic_label` (vision.py:1450) | [CHEAP-static] |
| h | `bulk_set_attribute(physics:mass=0.5)`, `bulk_set_attribute(physxRigidBody:sleepThreshold=0.0)` | scene_authoring | [CHEAP-static] |
| i | 6× `apply_physics_material("rubber")` | `handlers/resolve.py:105` (rubber preset: friction 0.9/0.8, **restitution 0.8**) | [CHEAP-static] |
| j | 3× `create_bin` (LaneA x=−0.35, LaneB x=0.0, LaneC x=+0.35, all y=−0.40) | pick_place | [CHEAP-static] |
| k | `create_prim` BarcodeScannerBody + `set_semantic_label("scanner")` | scene_authoring | [CHEAP-static] |
| l | `barcode_reader_sensor(/World/BarcodeScanner, pos=[0.10,0.40,0.92], scan_volume=[...], read_attribute="semantic_type:label")` | `handlers/sensors.py:880` | [CHEAP-static] |
| m | `add_proximity_sensor(/World/PickSensor, pos=[0.40,0.40,0.8325], size=[0.07]³)` | sensors.py | [CHEAP-static] |
| n | `setup_pick_place_controller(robot=/World/Franka, target_source="curobo", color_routing={sku_a:LaneA, sku_b:LaneB}, destination_path=/World/LaneC, drop_target=[0.35,-0.40,0.92], …)` | `handlers/pick_place.py` (color_routing branch ~3062) | [CHEAP-static] (emits controller code; physics only at sim) |

All of steps 4a–4n are **build-time / static**: they author USD prims and inject controller code. No PhysX stepping occurs.

## 5. [SYSTEM] · [CHEAP-static] — the barcode sensor is a BUILD-TIME STUB (capability gap)
`_handle_barcode_reader_sensor` (`handlers/sensors.py:880-926`) only creates an Xform prim with four USD attributes — `barcode:scan_radius`, `barcode:last_read`, `barcode:last_class`, `barcode:read_count` — all initialised empty/0. Its own docstring states: *"Runtime barcode reading would be a per-tick callback (controller-side, Sprint 3+)."* (sensors.py:889-890).

Two concrete arg gaps confirmed by grep:
- The handler signature accepts only `sensor_path`, `position`, `scan_radius`. The template passes **`scan_volume`** and **`read_attribute="semantic_type:label"`** — **neither is read** by the handler (grep for `read_attribute`/`scan_volume` in sensors.py → 0 hits). They are silently dropped kwargs.
- **No runtime consumer** of `barcode:last_class` / `barcode:last_read` / `barcode:read_count` exists anywhere — grep across `service/` and `scripts/` finds the writer (sensors.py) but **zero readers** in the pick-place controller (`pick_place.py`).

→ The "scan" in the user's request is decorative. The sensor does not actually decode a barcode at runtime.

## 6. [SYSTEM] · [CHEAP-static] — what actually does the routing (and a template self-contradiction)
The controller's routing is in `handlers/pick_place.py`:
- `_cube_semantic_class(prim_path)` (pick_place.py:3323) reads the cube's **`Semantics_class`** value directly from USD — i.e. the label written by `set_semantic_label(..., semantic_type="class")` in step 4g.
- `_destination_path_for(cube_path)` (pick_place.py:3345) maps that class through `COLOR_ROUTING` → bin, else falls through to `DEST_PATH` (=LaneC). This is the real divert mechanism. It works **without the barcode sensor at all**; the sensor's read is never consulted.

**Template-internal contradiction (latent bug, not yet gate-caught because never gated):** the template also passes `drop_target=[0.35, -0.40, 0.92]` to `setup_pick_place_controller` (template:22, near "drop_target"). In `_bin_drop_pos` (pick_place.py:3356-3371) the very first line is `if DROP_TARGET is not None: return np.array(DROP_TARGET)` — a fixed `drop_target` **short-circuits the entire `color_routing` dispatch**. With this arg present, **every** cube is dropped at the single fixed point `[0.35,−0.40,0.92]` (above LaneC), and `sku_a→LaneA / sku_b→LaneB` never happens. The divert is silently defeated. This must be removed for the sort to function; it is the single highest-impact fix and is a pure-static catch (no physics needed to see it).

## 7. [SYSTEM] · [CHEAP-static] — STATIC-EYES PRE-FILTER (the cheap gate, runs before any sim)
`scripts/qa/scene_validate.py` instantiates the template canonically, does a ~2.5 s passive settle (no controller), and runs three geometry classes — **REACH, SUPPORT, PHYSICS-INSTABILITY** — with ~10 false-positive guards. This is where a problem is caught *before* the expensive function gate:

- **REACH** (scene_validate.py:7, reach table line ~30): every pick object and the place target must sit inside the arm's reachable shell. `ROBOT_REACH = {franka_panda: 0.855, ur10: 1.30, …}`. It mirrors the controller's own `handlers/resolve._ROBOT_REACH_M` so the static verdict matches the runtime gate.
  - For **Franka** (template default): LaneA at √(0.35²+0.40²)=0.53 m and items on the belt are inside 0.855 m → REACH passes. The belt is moving, so upstream items (x=−1.5 … 0.0) are handled by `belt_reachable()` (line 173): a cube whose forward travel brings closest-approach ≤ reach is NOT flagged.
  - For **ur10** (this scenario): 1.30 m shell easily covers the same geometry → still passes, but is a *false comfort* — the scene was Franka-tuned and ur10 grasp/IK is unverified for it.
- **SUPPORT**: raycast-down; each settled item must rest on the belt, not float/penetrate. The template's spawn-height fix is baked in: `item_centre_z = 0.8325` (belt_top 0.805 + 0.025 + 0.0025), with an in-code note that the old 0.855 "caused items to spawn above belt and bounce" (template:22). So SUPPORT should pass post-fix.
- **PHYSICS-INSTABILITY**: flags any item EJECTED >Xm during settle (spawn-overlap explosion). Items are spaced 0.30 m on a 0.05 m cube → no overlap → no ejection. **Watch item:** `rubber` restitution=0.8 is bouncy; combined with any residual spawn gap this is the most likely static-settle wobble, but at 0.30 m spacing it should not eject.

**What static-eyes will NOT catch (by design — it has no controller, no SKU logic):** the step-6 `drop_target` short-circuit, the dead barcode sensor, and the missing runtime decode. Those are *behavioural*, so they survive the cheap filter and only manifest at the expensive gate (or in a careful code read). Static-eyes' value here is confirming the **geometry is sound**, narrowing any gate failure to the controller/routing side — exactly the "scenes are sound → failures are controller-side" pattern in `project_isaac_assist_scene_validator`.

## 8. [SYSTEM] · [EXPENSIVE-physics] — the FUNCTION GATE (the outcome)
Run via `scripts/qa/gate_one.py`, which reads `simulate_args` from the template and calls the Kit verifier (`verify_pickplace_pipeline`, surfaced in `handlers/diagnostics.py`). This is the expensive step: full Kit build + PhysX sim for `duration_s = 320` (template:319).

`simulate_args` (template:317-333):
- `target_path = /World/LaneA`
- `cube_paths = [Item_1 … Item_6]` (all six)
- `color_routing = {sku_a:LaneA, sku_b:LaneB, sku_c:LaneC}`

**Gate success-criterion (the OUTCOME), from `diagnostics.py:4413-4449`:**
- per-cube `delivered = (cp_in_xy AND cp_above_floor AND cp_at_rest)` inside `target_path`'s AABB;
- because `len(cube_paths) > 1` (multi-cube): **`success = bool(delivered) AND upright_ok`** — i.e. **≥1 cube comes to rest inside LaneA's bounding box AND the primary cube (Item_1) is upright** (`upright_dot ≥ upright_tol`). This is the lenient multi-cube ANY-delivered rule (`project_isaac_assist_gate_criterion`).

**Predicted outcome (honest):** with the template **as written**, the `drop_target` short-circuit (step 6) sends every cube to `[0.35,−0.40,0.92]` (over LaneC), so **nothing lands in LaneA → gate `success=False`.** Even with `drop_target` removed so `color_routing` engages, the gate only checks LaneA; it confirms the *sku_a→LaneA* leg but never verifies *sku_b→LaneB* or the *sku_c→LaneC* fall-through — so a "pass" would under-measure the actual 3-way sort. And the whole thing on **ur10** is unverified (`motion_controllers.verified=[]`, status `function-gate ⏳`). I will not claim this template passes; it is a draft.

## 9. [SYSTEM] · [EXPENSIVE-physics] — diagnose loop on failure
On `success=False`, `gate_one`/`diagnose_one.py` reads the controller telemetry attrs (`ctrl:cubes_delivered`, `ctrl:phase`, `ctrl:cycles_attempted` — diagnostics.py:3368, 3458) and emits a `root_cause` (e.g. `carried_but_not_delivered` if picked>0/delivered=0, diagnostics.py:3505). For this template the likely root_cause is "delivered to wrong bin / 0 in target_path" driven by the step-6 fixed drop_target, which a human reads from telemetry rather than re-running physics.

---

## Tools that would be needed but DO NOT exist (grep-confirmed)
1. **Runtime barcode-decode / scan-read tool** — no per-tick reader of `barcode:last_class`/`last_read`/`read_count`; no `read_barcode`/`decode_barcode`/`scan_read` handler. The sensor writes attrs nobody consumes (`sensors.py:880` is build-only; "Sprint 3+").
2. **`barcode_reader_sensor` runtime args** — `scan_volume` and `read_attribute` are accepted by the template but **not implemented** in the handler (only `scan_radius` is honoured). A volumetric / attribute-selectable scan is missing.
3. **A sensor→controller routing bridge** — nothing wires the barcode read INTO `color_routing`; routing reads `Semantics_class` directly, so true sensor-driven (vs pre-tagged) divert is unimplemented.
4. **Multi-bin / per-leg gate verifier** — the gate checks a single `target_path` (LaneA); there is no verifier that asserts sku_b→LaneB AND sku_c→LaneC simultaneously, so the 3-way sort cannot be fully scored.
5. **UR10 compatibility for this template** — no ur10 entry in `roles.primary_robot.constraints`; no ur10 barcode variant in `templates_backup_ur10/`. Running ur10 here is an unverified override.

## Template honesty assessment
- **Status:** DRAFT — `verified_status: "drafted-2026-05-16; form-gate ⏳; function-gate ⏳"`. Never passed either gate.
- **Functional core (semantic-class divert) is real** and backed by working handlers, BUT the headline feature ("scan a barcode") is a non-functional stub, and a fixed `drop_target` arg in the template defeats the divert entirely.
- **Robot:** scenario asks ur10; template is Franka-authored and ur10-incompatible as declared.
