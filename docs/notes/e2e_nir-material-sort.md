# End-to-End Trace — `nir-material-sort` (T4, franka, material-sort)

**Scenario id:** `nir-material-sort`
**Persona:** recycling tech (ONET SOC 51-9199, recycling/sortation-line operator)
**One-sentence request:** *"an NIR sensor classifies material and sorts parts into three bins"*
**Matched template:** `workspace/templates/CP-NEW-nir-material-divert.json` (exact match — T4, franka, 3 bins metal/plastic/glass, `nir_material_sensor` as routing oracle)
**Sibling / near-match considered:** `CP-66.json` (4-class recycling multi-sensor: barcode + NIR, 4 bins) — rejected as match because the request says *three* bins and *NIR-only*; CP-66 is a 4-bin barcode+NIR superset.

This document traces the COMPLETE sequence of actions to reach the target scene + the OUTCOME, marking each step `[USER]` / `[LLM]` / `[SYSTEM]` and `[CHEAP-static]` / `[EXPENSIVE-physics]`. Every claim is grounded in real templates/handlers/gate code with `file:line` citations.

---

## TL;DR (the honest outcome first)

- The build **instantiates** and is **structurally clean** (form-gate: 0 ERROR / 0 WARN — `config/canonical_backlog.yaml:852`).
- The **NIR sensor is decorative scaffolding**: its handler writes `nir:last_material=""` / `nir:read_count=0` and never reads passing items at runtime (`handlers/sensors.py:1005-1043`). The actual sort is driven by the **static USD `Semantics_class` label** baked in at build time by `set_semantic_label` (`handlers/pick_place.py:4780`), NOT by any sensor read.
- The function-gate's success criterion for this multi-cube scene is **lenient**: `success = bool(delivered) and upright_ok` — **ANY one cube** at rest in `target_path` (here `/World/BinMetal`) (`handlers/diagnostics.py:4446-4447`). It does **NOT** check that each material reached its *correct* bin.
- **Measured live outcome (`docs/notes/function_gate_ledger.md:245`, `:3110`): 1/6** — gate scores a pass via Item_1→BinMetal, but **5 of 6 items are FLUNG / ride off the belt unclaimed** (CP-12 belt-serialization bug) and Item_1 has historically fallen to the catchall bin (routing miss). This is **not** a faithful three-way sort.
- **No tool exists** to (a) read the NIR sensor at runtime, (b) classify material from a sensor signal, or (c) verify per-bin sort *accuracy*. All confirmed missing by grep (see §7).

---

## 0. Actors & artifacts

| Role | Identity in this trace |
|------|------------------------|
| `[USER]` | recycling tech typing the request into the Isaac Assist chat |
| `[LLM]` | Claude acting for the user — retrieves the canonical, fills roles, emits the tool-call program |
| `[SYSTEM]` | the service: canonical instantiator, Kit RPC, handlers, static-eyes validator, function-gate |

Key files:
- Template: `workspace/templates/CP-NEW-nir-material-divert.json`
- Handlers: `service/isaac_assist_service/chat/tools/handlers/{sensors,pick_place,diagnostics,_models}.py`
- Static-eyes pre-filter: `scripts/qa/scene_validate.py`
- Function-gate: `scripts/qa/gate_one.py` → `simulate_traversal_check` (`handlers/diagnostics.py:3920`)

---

## 1. The numbered narrative (user-action steps are the numbered ones)

### Step 1 — `[USER]` `[CHEAP-static]` — submit the request
The recycling tech types: *"an NIR sensor classifies material and sorts parts into three bins."*
No scene exists yet; this is a text prompt. Cost: a chat round-trip.

### Step 2 — `[LLM]` `[CHEAP-static]` — interpret intent & retrieve the canonical
The LLM parses the request into the template's `intent` block (`CP-NEW-nir-material-divert.json` → `intent.pattern_hint="sort"`, `structural_features.destination_kind="n_bins_routed"`, `routing_axis="label"`, `n_material_classes=3`, `has_fallthrough=true`). Structural tags include `isaac:routing.nir_material_divert`, `isaac:sensor.nir_material`, `isaac:transport.conveyor`, `isaac:routing.fallthrough_catchall`.
Retrieval lands on `CP-NEW-nir-material-divert` (sensor novelty: it is the only library entry whose oracle is `nir_material_sensor` rather than `barcode_reader_sensor` or a vision classifier).

### Step 3 — `[LLM]` `[CHEAP-static]` — bind roles to concrete assets
The LLM fills the template `roles` from `role_defaults`:
- `primary_robot` → `franka_panda` at `[0,0,0.75]` (constraints allow `franka_panda|ur5e|kinova_gen3`).
- `input_conveyor` → `/World/ConveyorBelt`, size `[3.0,0.35,0.05]`, surface velocity `[0.12,0,0]`.
- `nir_sensor` → `/World/NirScanner` at `[0.0,0.45,0.94]`, `scan_radius=0.12`.
- `metal_bin` / `plastic_bin` / `glass_bin` → `/World/BinMetal` (x=-0.30), `/World/BinPlastic` (x=0.0, **routing_key=null = the fall-through catchall**), `/World/BinGlass` (x=+0.30), all at y=-0.40, z=0.75.
- `workpieces` → 6 cubes (2 metal, 2 plastic, 2 glass) spaced 0.28 m on the belt (min 3 / max 12 allowed).

**Design decision the template bakes in (`thoughts` §2 + `failure_modes[1]`):** material classes are attached with `set_semantic_label(..., semantic_type="class")`, **not** `"material"`. This is load-bearing: the routing dispatch `_cube_semantic_class` only reads USD instances `Semantics_color`, `Semantics_colour`, `Semantics_class` (`handlers/pick_place.py:4780`). A `Semantics_material` instance would be silently ignored and every item would fall through to `/World/BinPlastic`. The template's `verified_status` records this exact fix: *"semantic_type-material-to-class fixed."*

### Step 4 — `[LLM]` `[CHEAP-static]` — emit the build program (tool-call sequence)
The LLM emits the ordered tool calls from the template `code` / `code_template`. All of these have registered handlers (confirmed — none missing in the *build* path):

| Tool | Handler impl | Purpose |
|------|--------------|---------|
| `create_prim` | `handlers/workflow.py` | DomeLight, Ground, Table, item cubes |
| `apply_api_schema` | `handlers/_models.py` | RigidBody/Collision/Mass on items + Ground |
| `set_physics_scene_config` | `handlers/_models.py` | **CPU dynamics** (`enable_gpu_dynamics:False`, `MBP`) for determinism |
| `robot_wizard` | `handlers/_models.py` (`code_template`) | spawn Franka un-wound at `[0,0,0.75]` |
| `create_conveyor` | `handlers/_models.py` | 3 m belt, top z=0.805, +x at 0.12 m/s |
| `create_material` ×3 | `handlers/_models.py` | metal/plastic/glass OmniPBR visual cue |
| `assign_material` | `handlers/_models.py` | per-item + per-bin colour |
| `set_semantic_label` | `handlers/_models.py` | **the real routing key** (`semantic_type="class"`) |
| `apply_physics_material` | `handlers/_models.py` | rubber (anti-slip on belt) |
| `set_attribute` | `handlers/scene_authoring.py` | `physics:mass=0.4`, `sleepThreshold=0.0` |
| `create_bin` ×3 | `handlers/_models.py` | Metal/Plastic/Glass divert bins |
| `nir_material_sensor` | `handlers/sensors.py:1005` | **scaffolding only — see Step 5** |
| `add_proximity_sensor` | `handlers/_models.py` | pick-trigger box at `[0.40,0.45,0.855]` |
| `setup_pick_place_controller` | `handlers/_models.py` → installs `pick_place.py` controller | the routing + motion engine |

The orchestrator dispatches each through `handlers/_dispatch.py`; bodies execute via `kit_tools.exec_sync` against the live Kit stage.

### Step 5 — `[SYSTEM]` `[CHEAP-static]` — the NIR sensor handler runs (and does almost nothing)
`_handle_nir_material_sensor` (`handlers/sensors.py:1005-1043`) defines a USD `Xform` at the sensor path and creates three attributes:
```python
prim.CreateAttribute("nir:scan_radius",   Float).Set(scan_radius)   # 0.12
prim.CreateAttribute("nir:last_material", String).Set("")           # never populated
prim.CreateAttribute("nir:read_count",    Int).Set(0)               # never incremented
```
There is **no proximity loop, no per-frame read, no write-back to `nir:last_material`.** The docstring even says it *"Reads cube's material:type attr … within sensor proximity,"* but the implementation does not. This is the template's own `failure_modes[0]` in CP-66's words: *"Sensors are scaffolding — no runtime read logic."* The classification the user asked for is **pre-baked**, not sensed.

### Step 6 — `[SYSTEM]` `[CHEAP-static]` — the pick-place controller is installed with NIR-keyed routing
`setup_pick_place_controller` is called with:
```
color_routing = {"metal": "/World/BinMetal", "glass": "/World/BinGlass"}
destination_path = "/World/BinPlastic"     # plastic = fall-through catchall
drop_target = [0.0, -0.40, 0.92]
planning_obstacles = [Table, ConveyorBelt, BinMetal, BinPlastic, BinGlass]
```
At runtime the controller routes each picked cube via `_destination_path_for` → `_cube_semantic_class` (`handlers/pick_place.py:4792-4800`): it reads the cube's static `Semantics_class` (`metal`/`glass`), looks it up in `COLOR_ROUTING`, and falls through to `DEST_PATH` (BinPlastic) for anything unmatched (i.e. `plastic`). **The NIR sensor prim is never consulted.** The "NIR-driven sort" is a label lookup.

### Step 7 — `[SYSTEM]` `[CHEAP-static]` — STATIC-EYES PRE-FILTER (`scripts/qa/scene_validate.py`)
**This is the cheap gate that catches geometry problems before the expensive physics gate.** It builds + settles the scene with the **arm parked** (it unsubscribes the pick controller so the arm stays at HOME — `scene_validate.py:68-75`), runs a ~2.5 s **passive** settle play (items fall onto supports / clumps form — `:96`), then reads ACTUAL post-settle prim geometry and checks three classes (no full pick-place sim, no 320 s run):

- **REACH** — each pick object + each delivery target within the arm's reachable shell. `ROBOT_REACH["franka_panda"]=0.855` (`scene_validate.py:32`, mirroring `handlers/resolve._ROBOT_REACH_M`). It is **belt-aware**: a cube upstream on a moving belt is NOT flagged out-of-reach if the belt's forward travel brings it within reach (`belt_reachable`, `:173-183`).
- **INTERPENETRATION** — pick objects clumped/overlapping in 3D (the dispenser-clump class).
- **SUPPORT** — each pick object rests on a surface (not floating, not buried).

**What it catches here (and what it lets through):**
- The 3 bins sit at distance `sqrt(0.30² + 0.40²) = 0.50 m` and `sqrt(0² + 0.40²) = 0.40 m` from the base — all **< 0.855 reach** ✓. So the PLACE targets pass. (Had the LLM pushed a bin past x≈±0.75, static-eyes would VIOLATE-REACH it here, **before** burning the 320 s sim — exactly its purpose.)
- The 6 items start on the belt at x = −1.40 … 0.00, far in front of the base, but `belt_reachable` clears them because the belt carries them in. ✓
- Items are spaced 0.28 m → no INTERPENETRATION clump. ✓
- Items rest on the belt top (z=0.855 over belt-top 0.805) → SUPPORT ok. ✓

**Verdict at this stage: static-eyes CLEAN.** The scene is geometrically sound. Note what static-eyes **cannot** see: it has no physics-of-transport model, so it cannot predict the belt-serialization fling that the expensive gate later exposes (Step 9). That is the structural boundary — reach/fit/support are checkable statically; "does the arm pick each item before it rides off the end of a moving belt" is not.

### Step 8 — `[SYSTEM]` `[CHEAP-static]` — FORM-GATE (structural validation)
`--validate-tool-calls` over the emitted program: **0 ERROR / 0 WARN** (`config/canonical_backlog.yaml:852`). Every tool name resolves to a handler, every required role is bound, schemas validate (`tool_schemas.py`, `handlers/_models.py`). The structural sort topology (`isaac:routing.nir_material_divert` + fall-through catchall) is well-formed. **Form-gate PASS.**

### Step 9 — `[SYSTEM]` `[EXPENSIVE-physics]` — FUNCTION-GATE (`scripts/qa/gate_one.py` → `simulate_traversal_check`)
This is the costly step: build + settle + **run the full pick-place sim for `duration_s=320`** (`simulate_args.duration_s`), with `cube_paths=[Item_1..Item_6]`, `target_path=/World/BinMetal`, and the 3-way `color_routing` (`gate_one.py:73-80`; `handlers/diagnostics.py:3920` `_handle_simulate_traversal_check`).

**Success criterion (the OUTCOME definition) — `handlers/diagnostics.py:4446-4449`:**
```python
if len(cube_paths) > 1:
    success = bool(delivered) and upright_ok          # multi-cube: ANY cube delivered + primary upright
else:
    success = bool(in_xy and above_floor and at_rest and upright_ok)
```
`delivered` = any cube whose final position is in the `target_path` (BinMetal) XY bbox, above floor, and at rest (`:4431-4434`). **This is the lenient multi-cube gate** documented in MEMORY as `project_isaac_assist_gate_criterion`: ANY cube delivered to the *one* target bin counts — it does **not** verify metal→BinMetal AND plastic→BinPlastic AND glass→BinGlass. There is **no per-material sort-accuracy assertion anywhere** (confirmed missing, §7).

### Step 10 — `[SYSTEM]` `[EXPENSIVE-physics]` — the measured OUTCOME
From the live ledger (`docs/notes/function_gate_ledger.md:245`, corroborated `:2808`, `:3110`):

> **nir-material-divert: 1/6.** Root bug originally = `code_template` MISSING `robot_wizard` (robot was a bare `create_prim` Xform → controller couldn't install → CTRL={}). **FIXED** (robot_wizard + gate-config: 6 cube_paths + color_routing metal/glass/plastic + dur 320). After fix the controller ENGAGES (Item_1 picked). **Still 0/6 correct-sort:** `plan_fails=2` (some IK-infeasible), Item_2–6 **RIDE OFF** (final xy 1.4–3.3, the CP-12 belt-serialization bug — item crosses the narrow sensor/pick zone while the arm is busy and rides off unclaimed), and Item_1 historically routed to the **catchall** (routing miss). A later run logs *"1/6, 5 items FLUNG."*

**So the gate's lenient criterion can score a PASS (Item_1 lands at rest in BinMetal = `delivered` non-empty) while the actual task the recycling tech asked for — a faithful three-way material sort — FAILS.** This is an honesty gap between the gate verdict and the user-visible behaviour, not a controller success.

**Honest status of the template:** `verified_status` = *"patched-r-a40-fix; semantic_type-material-to-class fixed; **form-gate pending**"*; backlog `status: drafted` (`config/canonical_backlog.yaml:848`), `draft_notes` = *"first use of nir_material_sensor in library; **function-gate pending live Kit**."* It is a **draft**, function-correctness **unverified**.

---

## 2. Where static-eyes saves an expensive run (the explicit hand-off)

| Failure class | Caught by static-eyes (CHEAP, ~2.5 s settle)? | Caught only by function-gate (EXPENSIVE, 320 s sim)? |
|---|---|---|
| Bin placed out of arm reach (x past ±0.75) | **YES** — `scene_validate.py` VIOLATION-REACH, no sim burned | — |
| Item clump / interpenetration after settle | **YES** — INTERPENETRATION check | — |
| Item floating / buried (bad z) | **YES** — SUPPORT check | — |
| `semantic_type="material"` typo → all items to catchall | **NO** (static-eyes is geometry-only) | partially — shows up as mis-routing in the sim |
| Belt-serialization fling (item rides off while arm busy) | **NO** (no transport-physics model) | **YES** — Item_2–6 final xy 1.4–3.3 |
| Per-material sort *accuracy* (metal→BinMetal, etc.) | **NO** | **NO — no tool checks this at all (§7)** |

In this scenario static-eyes returns **CLEAN** (all geometry is sound), so it does not block — and the expensive gate is where the real defect (belt-serialization + lenient pass) surfaces. The value static-eyes *would* add appears the moment an LLM drifts a bin out of reach: it would reject in 2.5 s instead of 320 s.

---

## 3. Tool inventory — exists vs. MISSING

### Exists (build + gate path — all confirmed registered)
`create_prim`, `set_attribute`, `apply_api_schema`, `set_physics_scene_config`, `create_material`, `assign_material`, `apply_physics_material`, `set_semantic_label`, `create_conveyor`, `create_bin`, `nir_material_sensor` (scaffolding), `add_proximity_sensor`, `setup_pick_place_controller`, `robot_wizard`, `bulk_set_attribute`, `barcode_reader_sensor`, `simulate_traversal_check`.

### MISSING — confirmed absent by grep over `handlers/` + `tool_schemas.py` (§7)
Every tool a *faithful* NIR sort would need that does not exist:

1. **`read_nir_sensor` / `nir_sensor_read` / `get_sensor_reading`** — a runtime tool to read what the NIR sensor "sees" as items pass. Without it the sensor cannot drive routing; routing is forced to use the pre-baked `Semantics_class`. **(MISSING)**
2. **`classify_material` / `material_classify` / `nir_classify`** — turn a sensor signal into a material label at runtime (the actual "classifies material" verb in the request). **(MISSING)**
3. **`route_by_sensor`** — close the loop: sensor read → bin selection (a PLC-style divert). The current loop is label-lookup, not sensor-driven. **(MISSING)**
4. **`verify_sort_accuracy` / `sort_accuracy` / `check_routing_correct` / `per_bin_gate`** — a gate that asserts *each material reached its correct bin* (metal→BinMetal, plastic→BinPlastic, glass→BinGlass). The only gate that exists scores ANY-one-cube-in-the-one-target-bin. **This is the most consequential gap: there is no tool that can confirm the user's actual request was satisfied.** **(MISSING)**
5. **`simulate_sort_check` / `verify_routing`** — a multi-target traversal grader (per-cube → per-expected-bin). `simulate_traversal_check` is single-target. **(MISSING)**

---

## 4. Honesty notes (draft / scaffolding / unverified)

- **NIR sensor is scaffolding.** `handlers/sensors.py:1005-1043` writes empty `nir:last_material` and never reads. The user's "an NIR sensor classifies material" is realised as a **build-time semantic label**, not a sensed classification. Faithful NIR sensing is an open item — no runtime-read tool exists.
- **The gate is lenient and can lie about this task.** `success = bool(delivered) and upright_ok` (`diagnostics.py:4447`) passes on one cube reaching BinMetal; it cannot distinguish "three-way sort works" from "one metal cube landed and five items flew off." Measured truth = **1/6** with 5 flung (`function_gate_ledger.md:245`/`:3110`).
- **Belt-serialization (CP-12 class) is the live blocker**, not reach or planning: items cross the pick zone while the arm is mid-cycle and ride off (final xy 1.4–3.3). Confirmed empirically as the EXPANSION_DIRECTION "90% conveyor, fragile" structural finding (`function_gate_ledger.md:2808-2810`).
- **Template status = drafted, function-gate pending.** `verified_status: "…form-gate pending"`; backlog `status: drafted` (`canonical_backlog.yaml:848`). Treat any "✓" as un-earned until a per-material sort-accuracy gate exists and N-of-M live runs pass.

---

## 5. Cited file:line index

- Template (match): `workspace/templates/CP-NEW-nir-material-divert.json` (goal, `code`, `failure_modes`, `roles`, `simulate_args.duration_s=320`, `verified_status`)
- Sibling: `workspace/templates/CP-66.json` (`failure_modes[0]` "Sensors are scaffolding — no runtime read logic")
- NIR handler (scaffolding): `service/isaac_assist_service/chat/tools/handlers/sensors.py:1005-1043`
- Routing dispatch (label, not sensor): `service/isaac_assist_service/chat/tools/handlers/pick_place.py:4769-4800` (`_cube_semantic_class`, `_destination_path_for`), reads `Semantics_class` at `:4780`
- Gate runner: `scripts/qa/gate_one.py:64-88`
- Gate success criterion: `service/isaac_assist_service/chat/tools/handlers/diagnostics.py:3920` (`_handle_simulate_traversal_check`), `:4431-4434` (`delivered`), `:4446-4449` (multi-cube `success`)
- Static-eyes pre-filter: `scripts/qa/scene_validate.py:1-23` (REACH/INTERPENETRATION/SUPPORT), `:32` (franka reach 0.855), `:68-96` (arm-parked passive settle), `:173-183` (`belt_reachable`)
- Live measured outcome: `docs/notes/function_gate_ledger.md:245`, `:2808-2810`, `:3110-3112`
- Draft status: `config/canonical_backlog.yaml:838-852`

---

## 6. Step count

User-action steps (the numbered `[USER]`/`[LLM]`/`[SYSTEM]` flow Steps 1–10) = **10**.

## 7. Missing-tool grep evidence
```
grep -rln "def _handle_<name>|\"<name>\"|def <name>" handlers/ tool_schemas.py  → MISSING for:
  read_nir_sensor, nir_sensor_read, read_sensor, get_sensor_reading, sensor_read,
  classify_material, material_classify, route_by_sensor, sort_accuracy,
  verify_sort_accuracy, per_bin_gate, simulate_sort_check, verify_routing,
  check_routing_correct, nir_classify   (all → MISSING)
```
