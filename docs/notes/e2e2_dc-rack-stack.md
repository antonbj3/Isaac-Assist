# E2E Trace — `dc-rack-stack`: "insert a 1U server into a datacenter rack bay"

**Scenario id:** dc-rack-stack
**Domain:** datacenter · **Robot:** UR10 · **Task:** insert-into-slot
**Request (verbatim):** *"insert a 1U server into a datacenter rack bay"*
**Date traced:** 2026-06-09
**Verdict:** **BLOCKED — reveals a NEW class-level architectural gap** (horizontal slide-in / rail-engage insertion controller). The closest existing capability (`setup_insertion_controller`) is a *vertical* peg-in-hole family and does not model this task at all; and the asset payload is missing from disk.

---

## 0. Ground-truth inventory (what actually exists)

### Assets — Kimate's Datacenter pack
`/home/anton/kimate_assets/assets/Datacenter_NVD/asset_catalog.json` lists 36 assets, INCLUDING exactly the right pieces:
- `Rack_42U_A_01` → `Assets/DigitalTwin/Assets/Datacenter/Racks/Rack_42U_A/Rack_42U_A_01.usd`
- `Server_1U_A_01` → `.../Server_Nodes/Servers/Server_1U_A_01.usd`  ← the 1U server payload
- `Blank_1U_White/Black/...`, `Fiber_Patch_Panel_1U_A_01`, `RackScrews_Silver_A_01`, `DGX_A100_01`, `Server_2U_*`

**CRITICAL — the geometry is NOT on disk.** A full file walk of the package finds **zero** `.usd/.usda/.usdc` files:
```
find .../Datacenter_NVD -type f ! -name '*.mdl' ! -name '*.png' ! -name '*.jpg'
  → PACKAGE-INFO.yaml, asset_catalog.json, *-license.txt   (only these)
```
The directory tree (`Racks/Rack_42U_A/`, `Server_Nodes/Servers/`) exists but is **empty** — only the `Materials/*.mdl` shaders shipped. The catalog `usd_path` values point at `/home/kimate/Desktop/assets/...` (Kimate's machine), not this host.

### Handler that would "do" insertion
`service/isaac_assist_service/chat/tools/handlers/insertion.py` (514 lines) — `setup_insertion_controller(robot_path, target_path, strategy, ...)`. Four strategies, all in `_STRATEGY_DEFAULTS` (insertion.py:50-108):
| strategy | geometry it models |
|---|---|
| `spiral_search` | **vertical** peg-in-hole, XY soft / Z stiff, descent + spiral re-center |
| `helical_screw` | **vertical** screw-driving, coupled Δz+Δrz |
| `snap_fit` | **vertical** press-and-click |
| `impedance_descent` | **vertical** cap/bottle seat |

Every waypoint generator (`_gen_spiral_search` insertion.py:115, etc.) emits `orientation: [1,0,0,0]` (identity quat = tool pointing straight **down**) and interpolates a monotone **Z descent** from `start_xyz` to `target_xyz`. A grep for `slide|horizontal|rail|approach_axis|insert_axis` over the whole handler returns nothing — **there is no insertion-axis concept**. The whole family is "drop something down into a hole on a table."

### Closest templates (grep `rack|slot|insert|server|1u|bay`)
- `CP-NEW-narrow-clearance-insertion.json` — **Franka**, 9.5mm peg into 9.8mm hole, `cartesian_impedance`, `verify_args.expected_peg_z_max_m=0.758`, target `/World/HoleProxy`.
- `CP-NEW-maniskill-peg-insertion.json`, `CP-NEW-tactile-insertion.json`, `CP-NEW-yrkesroll-assembler-peg-bushing.json` — all **Franka**, all vertical peg-in-hole, all use a `HoleProxy` (a primitive proxy, not a real fixture).
- **No UR10 insertion template exists. No rack template exists. No "slot" template exists** (CP-NEW-tray-stack-unstack is open-shelf stacking, not rail insertion).

### Gate
`scripts/qa/gate_one.py` runs `simulate_traversal_check`; its `success` verdict is a **pick-place delivered-to-target / under_target** check (gate_one.py:93-94). It has **no "seated below flush plane" / "rails engaged" / "mesh-pose-vs-target" criterion**. The insertion templates therefore carry *bespoke* `verify_args` (`expected_peg_z_max_m`, `narrow_clearance_success`) graded inside `insertion.py`, NOT by the function-gate. Confirmed by `TOOL_GAP_INVENTORY_V2` P11 ("position-only AABB gate chronically false-positives" for irregular parts) and P10 (`setup_insertion_controller` `dry_run=False` → `NotImplementedError`, live mode blocked on absent ros2_control bridge).

---

## 1. Traced user-action → outcome sequence

Legend: **[USER]** human · **[LLM]** model planner · **[SYSTEM]** service/Kit · **[CHEAP-static]** USD/catalog/IK-feasibility, no physics step · **[EXPENSIVE-physics]** PhysX-stepped sim.

| # | Actor | Cost | Step | Result |
|---|---|---|---|---|
| 1 | **[USER]** | — | Types *"insert a 1U server into a datacenter rack bay"* into Isaac Assist chat. | request received |
| 2 | **[LLM]** | [CHEAP-static] | Intent classify → insertion-into-slot. Searches asset index (`scene_blueprints._build_asset_index`, scene_blueprints.py:60) which loads `asset_catalog.json`. Finds `Server_1U_A_01`, `Rack_42U_A_01`. **Looks right.** | catalog hit |
| 3 | **[LLM]** | [CHEAP-static] | No matching UR10/rack template → must compose from scratch. Picks `build_scene_from_blueprint` with objects = {Rack_42U_A_01 @ floor, Server_1U_A_01 @ staging table, UR10 @ base}. | blueprint authored |
| 4 | **[SYSTEM]** | [CHEAP-static] | `build_scene_from_blueprint` codegen (scene_blueprints.py:360 `_place`) runs in Kit. For each asset: **scene_blueprints.py:364** `if not os.path.exists(asset_path): _missing_assets.append(name); print('skipping … asset not found'); return`. | **Rack + Server SILENTLY SKIPPED** — their `.usd` files are absent on this host |
| 5 | **[SYSTEM]** | [CHEAP-static] | Stage now has only the UR10 (a real Collected_Robots asset) + maybe a ground plane. `_missing_assets=['Rack_42U_A_01','Server_1U_A_01']` printed to Kit log; no hard error raised. | **scene is empty of the task objects** |
| 6 | **[LLM]** | [CHEAP-static] | (If the LLM does not parse the skip-log) proceeds to author the insertion. Calls `setup_insertion_controller(robot_path=/World/UR10, target_path=/World/RackBay, strategy=spiral_search)`. | controller requested |
| 7 | **[SYSTEM]** | [CHEAP-static] | `_handle_setup_insertion_controller` (insertion.py:276). `target_path` resolves to nothing (rack skipped). `dry_run` default → returns a trajectory plan; **`dry_run=False` raises `NotImplementedError`** (TOOL_GAP P10, insertion.py:353 "live mode requires Kit RPC + …"). | live insertion **NotImplementedError** |
| 8 | **[SYSTEM]** | — | Even in dry-run, the generated trajectory is a **vertical Z-descent with tool-down quat** (insertion.py `_gen_spiral_search`). For a rack bay the server must travel **horizontally** along the rack depth axis, body held flat. The plan is geometrically wrong for the task. | wrong-axis plan |
| 9 | **[LLM]** | [CHEAP-static] | Grip step: UR10 has only `surface_gripper` (suction; robot.py:6153) — a 1U server (flat top, perforated/finned) is a poor single-cup suction target, and the task needs the server held **cantilevered & level** to feed two rails. No parallel-jaw or fork EOAT on UR10. | grip strategy infeasible/fragile |
| 10 | **[SYSTEM]** | [EXPENSIVE-physics] | *If* one force-substitutes a primitive cube for the server and a cube-with-gap for the bay and runs the gate: `gate_one.py` → `simulate_traversal_check` grades **under_target / delivered**, NOT "rails engaged + seated to backstop." A cube parked roughly in the gap → **false PASS**. | physics step burned; verdict is a lie |
| 11 | **[SYSTEM]** | — | **Honest outcome:** no rack, no server, no horizontal insertion controller, no two-rail constraint model, no insertion-depth/seat grader for this geometry. | **TASK NOT ACHIEVABLE as specified** |

**OUTCOME:** The scenario cannot be built or executed faithfully today. It fails at *three independent layers*: (a) **asset payload missing** (catalog-without-geometry → silent skip at scene_blueprints.py:364), (b) **wrong controller class** (all insertion strategies are vertical peg-in-hole; no horizontal slide), (c) **no gate** that can score a slot-insertion. Even patching (a) by sourcing the USDs, (b) and (c) remain class-level holes.

---

## 2. NEW class-level architectural gap (the key deliverable)

### G-RACK-1 — Horizontal slide-in / rail-engage insertion controller (`slide_insert` / `rack_insert`)
This is the **datacenter analogue of the humanoid-cabinet finding**: just as pick-place fundamentally broke on an articulated *door* (revolute hinge) and needed a whole new revolute-pull controller class, **insertion fundamentally breaks on a rack bay** because the entire `setup_insertion_controller` family assumes a **single-axis vertical descent into an unconstrained-on-the-sides hole**. A rack bay is a different *kinematic class*:

- **Insertion axis is horizontal** (along rack depth), tool held level — not the hardcoded tool-down `[1,0,0,0]` + monotone-Z of every generator in insertion.py.
- **Two-sided rail constraint** — the 1U server engages **left AND right rails simultaneously**; misalignment on either rail jams it. Peg-in-hole is a *single* circular constraint with a centering funnel; a rail pair is two parallel prismatic constraints that must be co-satisfied (yaw + roll must be ~0, not just XY-center). The `spiral_search` XY-shimmy is the *wrong* search primitive — you need a **pitch/yaw/roll micro-align + push-along-axis** (admittance in 5 DoF, compliant only across the rails).
- **Long travel under sustained low force** along the axis, then a **hard backstop** (the server bottoms out / latches), not a soft "below flush plane" Z threshold.
- **Carried-body kinematics** — the server is a long rigid body held at one end and cantilevered into the bay; the controller must keep the *far edge* aligned, a control point that is NOT the gripper frame. No current controller tracks a tool-offset control point like this.

**Why it's a CLASS, not a one-off:** the same controller would serve a whole family — slide a drawer/tray into a slotted cabinet, a PCB card into an edge connector, a magazine into a feeder, a book onto a tight shelf, a pallet into drive-in racking, a cassette into a load-lock. All are "feed a long body along a horizontal axis into a multi-rail/two-sided constraint to a backstop." None of the four vertical strategies covers it. This is a **missing controller class**, an effort-**L** new subsystem (akin to M10 articulated-door, but for prismatic two-rail engage).

### G-RACK-2 — Slot/rail-aware target + seat/engagement gate (`rack_bay` form-gate)
Pairs with G-RACK-1. There is **no gate primitive** that scores "server seated in bay N: both rails engaged, body level (roll≈yaw≈0), pushed to backstop, no protrusion." `simulate_traversal_check` only knows delivered/under_target (gate_one.py:93). This is the insertion-depth/mesh-pose grader that P11 flags as missing, **specialized to the two-rail rack case** — a new **gate class** (`verify_slot_engagement`), not just the existing AABB check. Without it every rack/slot task false-passes on a roughly-parked primitive (step 10 above).

### G-RACK-3 (supporting, not the headline) — "catalog-without-payload" guard
`build_scene_from_blueprint` silently `return`s on a missing asset (scene_blueprints.py:364-367) and the LLM has no first-class signal that the *task-critical* object was dropped. A whole asset pack (Datacenter_NVD) is catalog-only on this host → every datacenter scenario inherits an empty stage that *looks* authored. Needs a **fail-loud "required asset missing" surfaced to the planner**, plus the actual USD payload sync. (This is infra/S, distinct from the controller class.)

---

## 3. Tool-gap list (NEW — not in TOOL_GAP_INVENTORY_V2)

1. **`slide_insert` / `rack_insert` horizontal slide-in + rail-engage insertion controller** — class-level missing controller. Horizontal-axis, level-tool, two-rail (prismatic) co-constraint, tool-offset control point (far edge of carried body), push-to-backstop with force cap. The 4 existing strategies are all vertical peg-in-hole; none applies. (Distinct from inventory P10/P54 which is the *vertical* insertion family blocked on ros2_control.) **Effort: L.**
2. **`verify_slot_engagement` / `rack_bay` form-gate** — score "both rails engaged + body level + at backstop + no protrusion." No current gate scores slot insertion (gate is delivered/under_target only). Distinct from inventory M14 (`place_on_shelf`, which is open-shelf *placement*, not rail engagement) and P11 (generic mesh grader). **Effort: M.**
3. **UR10 level-carry EOAT for long flat bodies (fork/shelf-fork or dual-cup bar)** — single suction cup cannot hold a 1U chassis level & cantilevered to feed rails; no parallel-jaw/fork on UR10. Distinct from inventory P6/M8 (dexterous hands). **Effort: M.**
4. **Catalog-vs-payload integrity preflight (`assert_assets_present`) surfaced to the planner** — `build_scene_from_blueprint` silently skips missing-on-disk assets (scene_blueprints.py:364); planner gets no required-asset-missing signal. Distinct from the inventory's LLM-callable `scene_validate` (which validates a *built* scene, not catalog-payload presence). **Effort: S.**
5. **Multi-rail / two-sided constraint primitive in the verifier** (`check_dual_rail_alignment`) — yaw+roll+lateral co-alignment check, a sub-primitive G-RACK-1/2 both need; nothing today checks a two-parallel-prismatic engagement. **Effort: S–M.**

---

## 4. Honest summary

- **Assets:** named in catalog (`Server_1U_A_01`, `Rack_42U_A_01`) but **USD payload absent on this host** → scene silently empty. (G-RACK-3)
- **Controller:** the entire `setup_insertion_controller` family is **vertical peg-in-hole**; a rack bay needs a **horizontal slide-in, two-rail-engage, push-to-backstop** controller that **does not exist** — the headline class-level gap. (G-RACK-1)
- **Gate:** no slot-engagement scorer; the function-gate would **false-pass** a roughly-parked primitive. (G-RACK-2)
- **Robot/EOAT:** UR10 suction is the wrong end-effector to hold a 1U chassis level into rails. (tool-gap 3)

This scenario is the datacenter twin of the humanoid-cabinet trace: the *task verb* ("insert") collides with a *kinematic class* (two-rail horizontal engage) the architecture was never built for. **Not achievable today**; the load-bearing fix is the new `slide_insert` controller class + its `verify_slot_engagement` gate, on top of sourcing the missing USDs.
