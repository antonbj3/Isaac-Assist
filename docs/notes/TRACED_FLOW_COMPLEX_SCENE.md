# Traced Flow — One COMPLEX Multi-Cell Warehouse Spec, End-to-End

**The point of this document:** trace the COMPLETE sequence of actions a user (and
the LLM acting for them) takes to get from a single high-level spec to a **VERIFIED
multi-cell scene** that COMPOSES MULTIPLE canonical templates into ONE stage — not a
single template. This is the sibling of `TRACED_FLOW_PALLETIZER.md` (one canonical),
scaled up to the North-Star T7 endgame (`MASTER_EXECUTION_PLAN.md:0`,
`CANONICAL_TAXONOMY.md:204`).

Each step is marked **[USER]/[LLM]/[SYSTEM]** and **[CHEAP-static]/[EXPENSIVE-physics]**,
and honestly labelled **EXISTS** (with `file:line`) vs **MUST BE BUILT**.

---

## The request

> A production engineer says: *"Build me a 3-cell warehouse: a UR10 palletizing boxes
> from an infeed conveyor, a Franka kitting line pulling 4 SKUs into trays, and a
> Carter AMR moving finished pallets between the two cells."*

Three sub-scenes that must live in **one shared stage / one Kit session / one physics
scene**, plus an inter-cell logistics link (the AMR). This is fundamentally different
from the palletizer trace: that one resolved to **ONE** canonical
(`CP-NEW-palletizer-layer-stack`). This resolves to **THREE+** canonicals that must be
*composed*.

---

## THE HEADLINE ANSWER (read this first)

**Multi-canonical composition is NOT possible today.** The entire pipeline — intake,
retrieval, ratify, instantiate, the `/build` route, the validators — is built around
the invariant **"one LayoutSpec → one matched template → one `execute_template_canonical`
call."** Every load-bearing structure is single-template:

| Layer | Single-template fact | Evidence |
|---|---|---|
| **Intent IR** | `LayoutSpec.bindings` is a *flat* `Dict[str, RoleBinding]` — one role-set, no list of cells, no inter-cell relations. `intent.pattern_hint` is **one** closed-enum value. | `multimodal/types.py:307-348`, `:318`, `:321` |
| **Retrieval** | Returns a ranked list but the orchestrator takes **the top hit** (sim > 0.85 → hard-instantiate that one). | `TRACED_FLOW_PALLETIZER.md` Stage 2; `template_retriever.py:601` |
| **Build route** | `POST /{sid}/build` takes **one** `body.template_id`, loads **one** `real_template`, runs **one** `execute_template_canonical`. | `multimodal/routes.py:394-507`, esp. `:430-440`, `:488-491` |
| **Instantiator** | `execute_template_canonical(template, role_bindings)` — singular `template`. No multi-template / offset / namespacing entry point. | `chat/canonical_instantiator.py:741-813` |
| **`sub_stages`** | The composition primitive named in every roadmap doc. **0 templates on disk carry it** (`grep -rl sub_stages workspace/templates → 0`). | `CANONICAL_TAXONOMY.md:201`, measured |
| **`compose_scene` tool** | The recommended ~200-LOC composition tool. **Does not exist** (`grep def.*compose_scene → none`). | `2026-05-11-composition-research-report.md:480`, measured |
| **Validators** | `gate_one.py` / `reach_validate.py` take template-ids as argv and loop **per template** — there is no integration/cross-cell gate. | `gate_one.py:12`, `reach_validate.py:175` |

**What DOES exist** are all the *ingredients*: the three sub-canonicals (palletizer,
kitting, AMR), the AMR drive primitives (`create_mobile_base_controller`,
`navigate_to`), a single-template spawn-collision repair, and a per-template static
reach validator. The missing piece is the **composition layer** that places N
canonicals in one frame, namespaces their prims, wires the AMR handoff, and runs a
cross-cell integration gate. The minimal version of that layer is specified at the
end of this doc (§ "The minimal composition mechanism").

---

## What "well-defined" means for a COMPOSED scene

The single-template pipeline has 7 stages (intake → retrieve → static-check → fix →
build → gate → diagnose). A composed scene wraps that with **3 composition-level
stages around the outside**: a **decompose** front-end, a **layout/namespacing**
middle, and an **integration-verify + per-cell-isolate** back-end.

| Stage | Artifact | Cost | Exists? |
|---|---|---|---|
| **C1 Decompose** | spec → DAG of (cell → canonical + role overrides) + inter-cell relations | **CHEAP-static** (LLM plan, ms) | **MUST BUILD** |
| **C2 Layout** | per-cell `cell_origin` + `prim_prefix` (namespace) + AMR route polyline | **CHEAP-static** (arithmetic) | **MUST BUILD** |
| **C3 Static-eyes (composed)** | per-cell reach + route-clear + handoff-align verdicts | **CHEAP-static** (IK probes + geom) | partial (per-cell EXISTS; inter-cell MUST BUILD) |
| 1–7 (per cell) | the single-template pipeline, run once per cell | as in palletizer trace | **EXISTS** per cell |
| **C5 Compose+build** | all 3 canonicals instantiated into ONE stage at offsets | mixed | **MUST BUILD** (the offset/namespace wrapper) |
| **C6 Integration gate** | AMR provably carries a pallet A→B; per-cell gates green | **EXPENSIVE-physics** | **MUST BUILD** (cross-cell gate); per-cell gate EXISTS |
| **C7 Isolate+iterate** | re-fix cell B without re-running A/C | cheap | partial (per-cell EXISTS; the "don't re-run siblings" cache MUST BUILD) |

---

## The full user-action sequence (numbered narrative)

### 1. [USER] Speak the high-level spec **[CHEAP-static]**

The engineer types/says the 3-cell request into the chat or canvas SPA. Today this
enters via `produce_layout_spec_from_text(prompt)`
(`multimodal/text_modality.py:213-245`).

**What happens today (the failure mode):** the rule-based extractor
(`extract_intent_rules`, `text_modality.py:186-210`) collapses the *entire* paragraph
into ONE `intent`:
- `_detect_pattern_hint` (`:77-83`) returns a **single** enum value — "palletizing /
  pick_place" fires first; "kitting" and "AMR/navigate" are **lost** (the IR has no
  slot for a second or third pattern).
- `_detect_counts` (`:156-170`) sums "conveyor"=1 across all three cells; it cannot
  attribute the conveyor to the UR10 cell vs the Franka cell.
- `_detect_features` (`:114-125`) ORs all feature flags into one bag.

So the **first action already loses the composition**: a 3-cell spec degrades to a
single muddled `pick_place` intent → retrieval returns ONE template → the other two
cells silently vanish. **This is the entry-point that the decompose stage (step 2)
must replace.**

### 2. [LLM] Decompose the spec into a cell-DAG  **[CHEAP-static] — MUST BUILD**

**The required artifact** (does not exist — closest named form is `sub_stages`,
`CANONICAL_TAXONOMY.md:201`, and the Mode-B "composition" list,
`2026-05-27-llm-input-format.md:202-211`):

```json
{
  "composition": [
    {"cell_id": "A", "role": "palletize",  "retrieve_query": "UR10 palletize boxes from infeed conveyor"},
    {"cell_id": "B", "role": "kitting",    "retrieve_query": "Franka kit 4 SKUs into trays"},
    {"cell_id": "C", "role": "amr_logistics", "retrieve_query": "Carter AMR move pallet between cells"}
  ],
  "relations": [
    {"type": "amr_route", "from": "A.pallet_out", "to": "B.tray_in", "via": "C.carter"}
  ]
}
```

**What exists to build on:**
- The Mode-B *schema sketch* exists on paper (`2026-05-27-llm-input-format.md:202-211`)
  but is explicitly *"not yet defined"* for role I/O typing (`:235` open-question Q4:
  "needs `template.outputs` schema across CP-*").
- `workflow_engine.py` (`multimodal/workflow_engine.py:1-40`) is a **lifecycle state
  machine** (`PENDING/IN_PROGRESS/AWAITING_APPROVAL/...`) — it is NOT a scene-composition
  DAG runner. It tracks approve/reject transitions, not template placement. Do **not**
  mistake it for the composition engine.
- The roadmap names the decompose engine but leaves it unchecked:
  `MASTER_EXECUTION_PLAN.md:184` — *"Composition engine — decompose a high-level spec
  ('3-cell warehouse …') into a DAG of canonical instantiations + inter-cell relations
  … This is the multi-cell T7 builder."* (Phase 5, the endgame, NOT built).

**Decomposition method (what the LLM does):** for our spec it splits into the three
`retrieve_query` strings above. There is **no automated splitter today** — a human or
an LLM prompt must produce this list. The cheapest correct build is: an LLM call that
emits the `composition[]` JSON above (one Haiku/Flash call,
`2026-05-27-llm-input-format.md:234`), then the existing per-query retrieval (step 4)
runs once per cell.

### 3. [SYSTEM] Resolve cell canonicals — what the three queries hit  **[CHEAP-static]**

Each `retrieve_query` runs the **existing** single-template retriever
(`template_retriever.py:601`). The library has the needed cells (440 templates total):
- **Cell A (palletize):** `CP-NEW-palletizer-layer-stack.json` — UR10, 2×3 boxes from
  infeed conveyor onto pallet. **EXISTS, gate-pending** (the exact subject of
  `TRACED_FLOW_PALLETIZER.md`).
- **Cell B (kitting):** closest is a Franka multi-SKU pick template (e.g. `CP-12`,
  `CP-61`, or `CP-NEW-6dof-pose-estimate-pick`). A dedicated **4-SKU-into-tray kitting**
  canonical is thin (the corpus has pick/sort but the "kit 4 distinct SKUs into one
  tray" shape is a `compose.*` GAP, `2026-05-27-expansion-roadmap.md:212`). **Partial.**
- **Cell C (AMR logistics):** `CP-NEW-yrkesroll-forklift-amr-pallet.json` exists as the
  closest AMR-pallet template. The **drive primitives** exist:
  `create_mobile_base_controller` (`tool_schemas.py:3789`, differential/ackermann/
  holonomic) and `navigate_to` (`tool_schemas.py:3816`, A*-grid → waypoints → physics-
  callback drive, codegen at `handlers/robot.py:1594-1709`). **AMR nav EXISTS; the
  pallet *carry/handoff* is the gap** (Phase-3 rung-4 is "nav only, no manip",
  `MASTER_EXECUTION_PLAN.md:138`; mobile-manipulation is "absent", rung-5).

**Verdict for step 3:** retrieval finds A cleanly, B partially, C's-nav-but-not-carry.
The corpus is the substrate; the gap is the *combination*, not the individual cells.

### 4. [SYSTEM] Retrieve + bind each cell (per-cell role_bindings)  **[CHEAP-static] — EXISTS per cell**

For each cell the **existing** ratify path runs independently:
`ratify(template, layout_spec)` (`multimodal/ratify.py:227+`) maps each cell's objects
onto that template's declared roles, producing per-cell `role_bindings`
(`ratify.py:265-281`: `role_bindings[role_name] = {"class", "object_id"}`).

Cell A binds `primary_robot=ur10`, `input_conveyor`, `primary_destination=pallet`,
`workpieces=[6 boxes]` (the palletizer roles, `CP-NEW-palletizer-layer-stack.json`
roles block). Cell B binds `primary_robot=franka`, 4 SKU classes, `tray`. Cell C binds
`mobile_base=carter`, `payload=pallet`, plus a route.

This step **works today** — but only **per cell, one at a time**. There is no object
that holds "the three cells' bindings together." The bindings are produced, then today
they would each drive a *separate* `execute_template_canonical` into a *separate* stage.
The composition layer must collect them.

### 5. [LLM/SYSTEM] Lay out the cells in one shared frame  **[CHEAP-static] — MUST BUILD**

This is the **coordinate + namespace** problem, and it is the heart of what is missing.

**The collision problem (why naive composition breaks):** every canonical authors its
prims at **`/World/...` with hard-coded names** — `CP-NEW-palletizer-layer-stack`
creates `/World/UR10`, `/World/ConveyorBelt`, `/World/Box_1..6`, `/World/Pallet`,
`/World/Table`, `/World/Ground`, `/World/DomeLight` (the build sequence in
`TRACED_FLOW_PALLETIZER.md` Stage 5). The Franka kitting cell ALSO authors
`/World/Table`, `/World/Ground`, `/World/DomeLight`, and likely `/World/Cube_1..`.
**Drop all three into one stage and:**
1. **Prim-path collisions** — two `/World/Table`, two `/World/Ground`, two
   `/World/DomeLight`; the second `create_prim` either errors or silently overwrites
   the first. The instantiator's only collision handling is the **single-template,
   UR10-specific spawn-nudge** (`canonical_instantiator.py:1000-1027`), which repairs
   a robot landing on its own pedestal — it does **not** handle two cells claiming the
   same `/World/Table`.
2. **Coordinate clash** — both cells place their robot base near `[0,0,0.75]`; the
   UR10 and the Franka would be spawned on top of each other.
3. **Singleton conflicts** — two `set_physics_scene_config(...)` calls (CPU
   determinism) and two `DomeLight`s fight over global scene state.

**The required fix (MUST BUILD): per-cell namespacing + offset.** The composition
layer assigns each cell a `cell_origin` and a `prim_prefix`:

```
Cell A (palletize):  prim_prefix=/World/CellA  cell_origin=[0.0,  0.0, 0]
Cell B (kitting):    prim_prefix=/World/CellB  cell_origin=[6.0,  0.0, 0]   # 6 m east, no overlap
Cell C (AMR route):  shared corridor between A.pallet_out and B.tray_in
```

Then every authored prim path is rewritten `/World/X → /World/CellA/X` and every
authored position is translated by `cell_origin`. **The plumbing to *find* the paths
already exists** — `_extract_prim_paths(template)` (`canonical_instantiator.py:1132-1145`)
pulls every `prim_path=`/`dest_path=`/`sensor_path=`/`robot_path=` literal from a
template's code. The composition layer would use exactly this to know what to re-namespace.
**What's missing is the rewrite step** (prefix + translate) and **collapsing the
singletons** (one shared `/World/Ground` + `/World/DomeLight` + one
`set_physics_scene_config`, NOT three).

**Layout reasoning that must run here:** where cell A ends and cell B begins (the 6 m
east offset, sized to each cell's bbox + clearance), the AMR corridor between
`A.pallet_out` and `B.tray_in` kept clear of both cells' footprints, and the handoff
**points aligned** (A's pallet-output station Z must match the AMR deck height; B's
tray-input station must be reachable by the Franka *and* by the AMR drop). The
`LAYOUT_REASONING_SURFACE.md` note is the design seed for this surface;
`compute_stack_placement` (`handlers/scene_authoring.py:5454`) is the *intra-cell*
analogue (it centers a grid on a target) — the **inter-cell** version (place a whole
cell subtree at an origin) **does not exist**.

**Does the LayoutSpec/instantiator support multi-template placement today? No.**
`LayoutSpec` has no `cell_origin` / `prim_prefix` / per-cell list (`types.py:307-348`);
`execute_template_canonical` has no offset or prefix parameter
(`canonical_instantiator.py:741-813`). Both are single-`/World`-rooted.

### 6. [SYSTEM] Static-eyes — per cell AND inter-cell  **[CHEAP-static] — partial**

This is the cheap pre-filter that catches layout problems **before** any 240 s sim
(the lesson of the palletizer trace's Stage 3).

**Per-cell reach (EXISTS):** run `reach_validate.py` once per cell — it already takes
template ids as argv and loops (`reach_validate.py:175`). For Cell A it would catch the
exact known palletizer defect: the pallet drop-column behind/below the UR10 probes
**0/3 UNREACHABLE straight-down** (`TRACED_FLOW_PALLETIZER.md` Stage 3,
`pick_place.py:6948`). For Cell B it probes the 4 SKU pick points + tray drops against
the Franka envelope. **This step works per cell today**, and because the validator is
already per-template-loopable, the composition layer gets per-cell reach **for free** —
it just runs it once per cell after applying the `cell_origin` offset (the offset
matters: a reachable pick at the cell's local origin must stay reachable after the
6 m translation — it does, because the robot moves with its cell, but the validator
must probe the *composed* coordinates to be honest).

**Inter-cell static checks (MUST BUILD) — three new cheap checks:**
1. **AMR route clear** — the corridor polyline from `A.pallet_out` to `B.tray_in` must
   not intersect either cell's footprint bbox. This is a 2D polygon-vs-polyline test
   (pure geometry, no sim). The A* grid planner inside `navigate_to`
   (`handlers/robot.py:1685` `grid_to_world`) already builds an occupancy grid — the
   static check is "does a path EXIST on that grid," runnable without driving.
2. **Handoff-point alignment** — A's pallet-output world pose vs the AMR's expected
   pickup pose (XY within tolerance, Z deck-height match); same for B's tray-input vs
   AMR drop. Pure arithmetic on the two cells' authored station coordinates.
3. **No-cell-overlap** — bbox(CellA) ∩ bbox(CellB) = ∅ after offsets. Trivial bbox test.

These three are all **CHEAP-static** (geometry, no physics) and are the inter-cell
analogue of the per-cell reach probe. None exist today; all are ≤50 LOC each.

**Where static-eyes saves the expensive gate (composed version):** if Cell A's drop
column probes UNREACHABLE, or the AMR corridor is blocked by Cell B's table, or the
handoff Z is off by 0.3 m — **all three are caught here, before any of the three cells'
240 s physics gates run.** A composed scene has 3× the sim cost, so the static catch is
3× more valuable.

### 7. [USER→LLM] Iterate the layout statically until all cells + links pass  **[CHEAP-static]**

The fix loop is pure arithmetic on `cell_origin` + per-cell `role_defaults` — **no
physics** (mirrors `TRACED_FLOW_PALLETIZER.md` Stage 4):
- Cell A unreachable drop column → move the pallet from behind the UR10 to the front
  annulus (the known CP-69/70/75 PASS region), recompute the 2×3 grid via
  `compute_stack_placement` (`scene_authoring.py:5454`).
- AMR corridor blocked → nudge `cell_origin` of B east, or route the corridor around.
- Handoff Z mismatch → raise the pallet-output station or lower the AMR deck.

Each iteration costs **one IK probe per target + a few bbox/polyline tests**, NOT a
240 s sim. Loop: `lay out → reach_validate ×3 + 3 inter-cell checks → fix → repeat`
until all green. **This is the loop that makes a composed scene affordable** — the
expensive integration gate (step 9) runs once, on a layout already proven sound.

### 8. [SYSTEM] Compose + build — instantiate all 3 canonicals into ONE stage  **[mixed] — MUST BUILD**

Today: `execute_template_canonical(template, role_bindings)` builds **one** template
into `/World` (`canonical_instantiator.py:741-813`), via sandbox-capture-then-dispatch
(`TRACED_FLOW_PALLETIZER.md` Stage 5). It is called **once** from `routes.py:488-491`.

**The required composition build (MUST BUILD)** — a `compose_and_build(composition,
layouts)` wrapper that, for each cell in DAG order:
1. Renders the cell's `code_template` with its `role_bindings` (existing
   `instantiate_role_based_code`, `canonical_instantiator.py:741`).
2. **Re-namespaces** every authored prim path `/World/X → {prim_prefix}/X` and
   **translates** every authored position by `cell_origin` (the NEW step; uses
   `_extract_prim_paths` `:1132` to find the paths).
3. **De-duplicates singletons** — only the FIRST cell authors `/World/Ground`,
   `/World/DomeLight`, and the single `set_physics_scene_config`; subsequent cells skip
   them (one shared World, one physics scene).
4. Dispatches the rewritten tool calls through the existing real `execute_tool_call`.

**What coordinates the three cells:** the shared **World** (one stage, one `PhysicsScene`)
is the substrate; the **AMR (Cell C) is the inter-cell link** — its `navigate_to`
waypoints span from A's pallet-output to B's tray-input, and its
`create_mobile_base_controller` drive callback is the only controller that *crosses*
cell boundaries. A and B's controllers each stay inside their own `prim_prefix`.

**What BREAKS when you put 3 templates in one scene (the real risks, honest):**
1. **Prim-path collisions** — covered in step 5; the namespacing rewrite is the fix.
2. **Multiple physics callbacks** — each canonical installs its own per-step physics
   callback (the pick-place controller's tick, the AMR's waypoint-drive tick at
   `handlers/robot.py:1687-1709`). Isaac Sim runs ALL registered callbacks every step;
   three controllers = three callbacks contending for the same `world.step()`. The
   project has already hit **exactly this class of bug** in the multi-arm shared-belt
   work: *"multi-arm shared-belt class shares an exec-gate/mutex-starvation root … belt-
   freeze masks it"* (memory: dual-Franka exec-gate, CP-52/51/53/65, solved via
   **per-cube mutex + belt fixes**). The 3-cell scene is a *superset* of that hazard —
   the per-callback mutex/claim discipline from CP-52 must generalize to per-cell.
3. **Controller conflicts on shared state** — if two cells' controllers both call
   `world.play()`/`world.reset()` at install time, the second resets the first's
   settled cubes. `settle_after_canonical` (`canonical_instantiator.py:193`) restores
   one cell's authored positions after its own install play — but it has no knowledge
   of sibling cells. A composed build must **install all controllers, THEN settle once**
   globally, not per-cell.
4. **Singleton fights** — two `DomeLight`s, two `set_physics_scene_config` (one wants
   `enable_gpu_dynamics=False` for determinism; if a sibling enables GPU dynamics the
   whole scene's determinism flips). The de-dup in step 3 above is mandatory, not
   cosmetic.
5. **Kit single-tenancy** — Kit RPC is single-tenant (memory:
   `feedback_isaac_assist_kit_concurrency`); the three cells must build **sequentially
   into the same session**, never in parallel.

### 9. [SYSTEM] Verify — per-cell gate + INTEGRATION gate  **[EXPENSIVE-physics] — partial**

**Per-cell function gate (EXISTS):** run `gate_one.py CELL_A_TEMPLATE` etc. — it takes
template ids as argv and loops (`gate_one.py:12`), playing the timeline for the
template's own `duration_s` (240 s for the palletizer) and grading delivery
(`diagnostics.py::_handle_simulate_traversal_check`, `TRACED_FLOW_PALLETIZER.md` Stage 6).
Each cell's *internal* success (boxes on pallet; SKUs in tray) is checkable today, but
note the gate is scoped to one template's `cube_paths`/`target_path` — in a composed
stage it must be pointed at the **namespaced** paths (`/World/CellA/Box_1`, …).

**Integration gate (MUST BUILD) — the cross-cell assertion:** *does the AMR actually
carry a pallet from A to B?* This is a new gate that:
1. Plays the **whole composed scene** for the union duration (cell A fills the pallet ~240 s,
   the AMR transits ~30 s, cell B kits ~180 s — the integration run is the longest path
   through the DAG, not the sum).
2. Asserts the **handoff invariants** the roadmap calls for (`2026-05-27-expansion-
   roadmap.md:222`: *"the runner instantiates each in sequence … asserting hand-off
   invariants between stages"*): pallet reaches `A.pallet_out` (cell-A gate) → AMR
   payload-attaches the pallet → AMR final XY within tolerance of `B.tray_in` → pallet
   Z still on the AMR deck (didn't fall off in transit) → at-rest at B.
   This is the **same primitive** as `simulate_traversal_check`'s `cp_in_xy + cp_above +
   cp_at_rest` (`diagnostics.py:4419-4434`), but applied to **the pallet as the tracked
   body across two cells' frames** instead of cubes inside one cell.
3. **Honest-eyes across the handoff** — the project's hard-won lesson is *gates lie*
   (memory: `feedback_isaac_assist_virtual_eyes_scene_data`). The AMR-carry must be
   confirmed with `scene_eyes.py` (live time-series, contacts) so the pallet is
   *carried* (contact pallet↔AMR-deck the whole transit), not teleported or
   FJ-welded — the exact `honest_pass` discipline applied to UR10 suction
   (memory: CP-70 zero-compliance caveat).

**Cost:** this is the **EXPENSIVE** step — one full multi-cell physics run. It runs
**only if step 6–7's static-eyes passed**, which is the whole reason the cheap inter-
cell checks exist.

### 10. [LLM] Diagnose + iterate — isolate cell B without re-running A/C  **[cheap] — partial**

If the integration gate fails because **cell B's kitting fails** (e.g. the Franka can't
seat SKU-3 in the tray), the diagnose leg must localize to **cell B alone** and re-fix
**without re-running cells A and C**.

**What exists:** the per-cell diagnose is fully built —
`diagnose_task_outcome`/`_handle_diagnose_pick_execution` (`diagnostics.py:3344`) reads
cell B's controller `ctrl:*` USD records (delivered/cycles/plan_fails/pick_reject) and
`scene_eyes.py` gives the live time-series for cell B's Franka. Because the gate and
diagnose are **already per-template / per-path scoped**, pointing them at
`/World/CellB/*` isolates cell B's verdict cleanly. The fix loop (move SKU-3's pick or
tray slot into the Franka envelope, re-`reach_validate` cell B) is the per-cell Stage-4
loop, run on cell B only.

**What's missing (the "don't re-run siblings" cache):** today a re-build is a fresh
`execute_template_canonical` into a fresh stage. To re-fix **only** cell B in a composed
stage you need either (a) a **checkpoint/restore** of cells A+C's settled state so cell
B can be torn down and rebuilt in place, or (b) a **scene-graph subtree rebuild** that
deletes `/World/CellB/*` and re-instantiates just that prefix. Neither exists; the
`workflow_checkpoint_store.py` / `workflow_rollback.py` modules
(`multimodal/`) are *lifecycle* checkpoints (approval state), not *physics-stage*
snapshots. **This is the one genuinely new back-end capability** — everything else in
diagnose reuses the per-cell machinery.

---

## The whole composed flow, one line per step

```
"3-cell warehouse: UR10 palletize + Franka kit-4-SKU + Carter AMR between them"
  │
  1. [USER] text → produce_layout_spec_from_text  [STATIC]              text_modality.py:213
        ⚠ TODAY collapses to ONE muddled pick_place intent — the bug composition must fix
  │
  2. [LLM] DECOMPOSE → composition[] DAG {cellA:palletize, cellB:kitting, cellC:amr}
        + relations[{amr_route: A.pallet_out → B.tray_in via C}]  [STATIC]   MUST BUILD
        (workflow_engine.py is a LIFECYCLE FSM, NOT this; sub_stages=0 on disk)
  │
  3. [SYSTEM] retrieve ×3 (one query per cell)  [STATIC]               template_retriever.py:601
        A=CP-NEW-palletizer ✓ · B=Franka multi-SKU (thin) · C=AMR-pallet + navigate_to
  │
  4. [SYSTEM] ratify ×3 → per-cell role_bindings  [STATIC]             ratify.py:227 (EXISTS per cell)
  │
  5. [LLM/SYS] LAYOUT: assign cell_origin + prim_prefix per cell; route the AMR corridor
        /World/X → /World/CellA/X ; translate by cell_origin  [STATIC]   MUST BUILD
        (paths found via _extract_prim_paths :1132; rewrite+translate+dedup-singletons new)
  │
  6. [SYSTEM] STATIC-EYES: reach_validate ×3 (per cell, EXISTS, reach_validate.py:175)
        + route-clear + handoff-align + no-overlap (3 new cheap geom checks)  [STATIC]  partial
  │
  7. [USER/LLM] iterate cell_origins + role_defaults until all green  [STATIC arithmetic]
  │
  8. [SYSTEM] COMPOSE+BUILD: instantiate all 3 into ONE stage at offsets  [mixed]   MUST BUILD
        BREAKS: prim collisions · 3 physics callbacks (CP-52 mutex root) · singleton fights ·
        install-then-settle-once · Kit single-tenant→sequential
  │
  9. [SYSTEM] VERIFY: gate_one ×3 per cell (EXISTS, gate_one.py:12) +
        INTEGRATION gate: AMR carries pallet A→B (cp_in_xy+above+at_rest on the pallet,
        honest-eyes contacts in transit)  [EXPENSIVE]   integration gate MUST BUILD
  │
 10. [LLM] DIAGNOSE: cell B fails → diagnose_pick_execution(/World/CellB/*) + scene_eyes
        (EXISTS per cell, diagnostics.py:3344) → fix cell B only → re-reach_validate(B)
        WITHOUT re-running A/C  [cheap]   per-cell EXISTS; "don't-re-run-siblings" cache MUST BUILD
```

---

## Is multi-canonical composition possible today? — NO. The minimal mechanism to make it so.

Everything per-cell exists (retrieve, ratify, instantiate, reach-validate, gate,
diagnose — all already template-id-scoped and loopable). The **minimal composition
mechanism** is five small additions, none requiring new physics, most ≤200 LOC
(matching the composition-research recommendation,
`2026-05-11-composition-research-report.md:478-487`: "Keep `compose_scene` as a new
tool — composes existing tools, not JSON primitives. ~200 LOC"):

1. **A `composition[]` IR + decompose step** (§step 2) — an LLM call that splits one
   spec into N `{cell_id, retrieve_query, role_overrides}` + `relations[]`. The schema
   sketch already exists (`2026-05-27-llm-input-format.md:202-211`); it just needs to be
   typed and wired. *Replaces the single-intent collapse at the front door.*

2. **A namespacing + offset rewrite** (§step 5/8) — given a rendered cell's code, rewrite
   `/World/X → {prefix}/X` and translate authored positions by `cell_origin`, de-dup the
   singletons (Ground/DomeLight/PhysicsScene). Reuses `_extract_prim_paths`
   (`canonical_instantiator.py:1132`). This is the single highest-leverage missing piece —
   it is what makes "3 templates in one stage" not collide.

3. **A `compose_and_build(composition, layouts)` wrapper** (§step 8) — loops the
   existing `execute_template_canonical` over cells in DAG order, applying the rewrite,
   installing all controllers, then **settling once** globally. ~150 LOC around code that
   already exists.

4. **Three inter-cell static checks** (§step 6) — route-clear, handoff-align,
   no-overlap. Pure geometry, ≤50 LOC each. The per-cell reach probe already exists.

5. **An integration gate + per-cell isolate-rebuild** (§step 9/10) — track the *pallet*
   across the A→AMR→B handoff with the existing `cp_in_xy/above/at_rest` primitive +
   `scene_eyes` honest-eyes; plus a `/World/CellB/*` subtree teardown+rebuild (or a
   physics-stage checkpoint of A+C) so a failed cell is re-fixed without re-running its
   siblings.

**The deepest non-trivial risk is NOT the plumbing — it is the multiple-physics-callback
contention** (§step 8 risk #2): three controllers ticking one `world.step()`. The
project already solved the 2-arm version (CP-52 per-cube mutex + belt fixes); composition
must generalize that claim/mutex discipline to per-cell. That is the one place where
"compose N working cells" can produce a scene that fails even though each cell passed in
isolation — and it is exactly why **step 9's integration gate (EXPENSIVE) cannot be
skipped**, even after all the cheap static-eyes pass.

**Bottom line:** the ingredients are all on disk; composition is a ~600-LOC orchestration
layer (decompose + namespace-rewrite + compose-build + 3 inter-cell checks + integration
gate) plus the one new physics capability (per-cell isolate-rebuild). It is Phase 5 of
`MASTER_EXECUTION_PLAN.md` and it is **not started** — `sub_stages`=0, `compose_scene`
absent, `/build` single-template, `LayoutSpec` single-role-set.
