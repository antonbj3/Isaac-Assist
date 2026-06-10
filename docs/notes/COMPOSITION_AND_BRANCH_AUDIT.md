# Composition Readiness + Branch-Split Audit

Audit date: 2026-06-09
Working tree: `refactor/2026-05-12-foundation-night-1` @ `859b8014`
Compared against: `origin/master` @ `fb823eee` (k3street)
Merge-base: `97d62982` (2026-05-08) — master is +243 commits, working HEAD is +1207 commits from there.

---

## PART A — Multi-canonical composition

### VERDICT: NO. The system cannot place 2+ canonical templates in one scene today.

The hard-instantiate path is hard-wired single-template, end to end. There is no
composer, no prim-path namespacing, and no coordinate-offset mechanism. Templates
author absolute `/World/...` paths; instantiating two templates that both author
`/World/Cube_1` (or `/World/Franka`) would silently collide / overwrite in the
shared USD stage. The *only* primitive that already exists for multi-actor scenes
is per-robot+per-phase controller isolation (built for dual-arm CP-52) and an
optional `mutex_path` — both are intra-template, hand-authored, not composer-level.

### A1 — `execute_template_canonical` assumes a single template owns /World

`service/isaac_assist_service/chat/canonical_instantiator.py:764` `execute_template_canonical(template, param_overrides, role_bindings)`:

- Takes ONE `template` dict, runs ONE `code`/`code_template` field as a tool-call
  sequence (capture phase `:937-964`, execute phase `:1050-1076`). No loop over
  multiple templates, no merge.
- **No namespacing.** Paths come verbatim from the template's `code`. The role
  substitution engine (`substitute_role_placeholders` `:602`) replaces
  `{{role.path}}` with whatever `role_defaults`/`role_bindings` say — typically
  `/World/Franka`, `/World/Cube_1` (see the documented `role_defaults` example at
  `:611-620`). Nothing rewrites or prefixes a template's paths to a per-instance
  subtree. Template B's `/World/Cube_1` WILL collide with template A's.
- **No coordinate offsets.** `grep offset|prefix|namespace|scene_offset` in the
  instantiator finds only regex path-parsing internals (`path_prefix` at `:143/150`
  is for the enumerate-loop cube-position regex, not scene placement). No template
  field carries a scene origin/offset; positions are absolute, authored in the
  template `code`.
- The only entry points are single-template:
  - `chat/orchestrator.py:1031` — `inst_result = await execute_template_canonical(top["template"])`. `top = scored[0]`, i.e. the single highest-similarity match (`:1006-1016` selects ONE template above `sim/margin` threshold).
  - `multimodal/routes.py:489` — `execute_template_canonical(real_template, role_bindings=...)` for the canvas-build path (ONE `body.template_id`).
  (The audit brief said "routes.py:488"; the live call is `multimodal/routes.py:489`, body opens at `:488`.)

### A2 — Multiple controllers / physics callbacks in one stage

Partial support already exists, but it was built for the *dual-arm-within-one-template*
case, not for composing independent templates.

- **Physics-step subscriptions ARE per-robot+per-phase scoped** (so they do NOT
  clobber each other):
  - cuRobo/RmpFlow controller: `pick_place.py:887`
    `_sub_attr = "_pick_place_controller_physx_sub_" + _ROBOT_TAG + "_" + _PHASE_ID`,
    subscribe at `:894`, stored on `builtins`. Prior sub for the same robot+phase
    is torn down first (`:888-893`).
  - builtin PPC: `pick_place.py:1029`
    `_SUB_ATTR = "_builtin_pp_sub_" + _ROBOT_TAG + "_" + _PHASE_ID` with a
    stale-sub sweep over ALL phases (`:1042-1064`). Comment at `:880-883`/`:1025-1027`
    explicitly states this scoping was added so packer-box-seal can call
    `setup_pick_place_controller` twice without one robot clobbering the other.
  - belt prestep: `pick_place.py:1329` similarly suffixed by tag+phase.
  → So in principle N robots × M phases each get an independent PhysX subscription.
    This is the one piece of multi-actor plumbing that already works.
- **Shared singletons remain a hazard.** `World.instance() or World()` is used at
  `pick_place.py:645, 1084, 1852` and `SimulationManager.initialize_physics()` at
  `:1080`. These are process-global; each controller install calls `world.reset()`
  (`:648, 1165, 1873`). Composing templates that each independently `reset()` the
  world / re-seed default joint state would race — the LAST install's reset wins and
  re-seeds every articulation. This is the same class as the documented dual-Franka
  exec-gate / mutex-starvation root (`mutex_path` plumbing at `:457, 3161, 3653-3790`),
  which is a HAND-AUTHORED per-template coordination primitive, not something a
  composer injects automatically.
- Net: subscription isolation = solved; world-reset / default-state arbitration and
  cross-template mutex wiring = NOT solved for arbitrary composition.

### A3 — Is there ANY multi-template / workflow composer? NO.

`grep "multi_template|sub_stages|compose_template|compose_canonical"` in `service/`
returns nothing. The candidates that exist are NOT scene composers:

- **`chat/pipeline.py` + `POST /pipeline/plan` (`chat/routes.py:418`)** — this is a
  multi-PHASE *workflow sequencer*, not a multi-template scene composer. `plan()`
  (`pipeline.py:428`) detects ONE robot (Nova Carter / Franka / etc.) and emits an
  ordered list of natural-language *prompts* (e.g. `_NOVA_CARTER_PHASES` `:27`:
  "Scene Setup" → "Robot Import" → "ROS2 Diff Drive" …). The extension sends each
  phase prompt to the normal `/message` endpoint one at a time
  (docstring `:1-12`). Each phase re-enters the LLM tool loop; it composes one
  scene over several turns, NOT several canonical templates into one scene.
- **`multimodal/workflow_engine.py` / `workflow_template_*.py`** — checkpoint/timeline/
  rollback bookkeeping for a single workflow, not scene composition.

### A — Minimal composition mechanism needed

To make 2+ canonicals co-exist in one stage, the missing layer is a thin
**composer wrapper around `execute_template_canonical`** that supplies the three
things it currently lacks:

1. **Prim-path namespacing.** Give each instance a subtree, e.g.
   `/World/inst0/...`, `/World/inst1/...`. Cleanest hook is the role-substitution
   layer already present: extend `instantiate_role_based_code` /
   `substitute_role_placeholders` (`canonical_instantiator.py:602/741`) so every
   `role.path` is rewritten under a per-instance root, OR add an
   `instance_root: str` arg to `execute_template_canonical` that prefixes all
   authored paths. (Legacy `code`-only templates that bake absolute `/World/Cube_1`
   strings would need a path-rewrite pass too — non-trivial; role-based templates
   are the tractable subset.)
2. **Coordinate offsets.** Add a per-instance translation applied to all authored
   positions (robot base, cubes, bins, conveyors). Either inject an
   `origin_offset=[dx,dy,dz]` into the role bindings, or xform the instance subtree
   root. No such field exists today.
3. **Per-template controller isolation.** Mostly already there via
   `ROBOT_TAG + PHASE_ID` subscription scoping — but the composer must (a) pass a
   distinct `phase_id`/robot path per instance, (b) arbitrate the shared
   `World.reset()` / default-state seeding (do ONE reset after all installs, or
   guard re-seeding), and (c) auto-wire `mutex_path` if two robots share a belt/bin.

Smallest viable slice: a `compose_canonicals([(tplA, offsetA), (tplB, offsetB)])`
helper that (i) namespaces each via role-binding path rewrite, (ii) offsets
positions, (iii) calls `execute_template_canonical` per instance with a unique
`phase_id`, (iv) defers a single world reset to the end. Function-gate would then
need per-instance verify_args/simulate_args (already per-template) merged.

---

## PART B — Branch split (IR-reasoning vs execution bridge)

### B1 — CONFIRMED: the static-reasoning stack is on `origin/master`, NOT the working tree

```
git show origin/master:service/isaac_assist_service/multimodal/relation_reasoning.py   → EXISTS (664 LOC)
git show origin/master:service/isaac_assist_service/multimodal/asset_resolution.py      → EXISTS (408 LOC)
ls service/isaac_assist_service/multimodal/relation_reasoning.py                        → No such file
ls service/isaac_assist_service/multimodal/asset_resolution.py                          → No such file
```

And the execution call lives on the working tree: `multimodal/routes.py:489`
calls `execute_template_canonical` (the audit's "routes.py:488"). So the IR
static-reasoning modules and the execution call are in DIFFERENT trees.

Crucial nuance: these files were **never deleted from the working branch** — they
were **added on master AFTER the split**. At merge-base `97d62982` (2026-05-08),
`relation_reasoning.py`, `asset_resolution.py`, and `mcp_floorplan_tools.py` all
ABSENT (`git cat-file -e 97d62982:...` → not a valid object). The two branches
diverged and built the floor-plan / spatial-reasoning subsystem in PARALLEL,
incompatible directions. This is divergent development, not a revert.

### B2 — Exact master-vs-working map for the multimodal / IR / asset / execution stack

| File | origin/master | working tree | Capability |
|---|---|---|---|
| `multimodal/relation_reasoning.py` | **PRESENT** (664 LOC) | ABSENT | Deterministic spatial-relation reasoning: `normalize_spatial_relations`, `predict_relation_positions`, `verify_relation_geometry`; on_top_of/inside/stacked_above support+containment checks |
| `multimodal/asset_resolution.py` | **PRESENT** (408 LOC) | ABSENT | Reviewed `object_class` → USD ref: `resolve_object_asset`, `resolve_layout_assets`, `list_local_asset_options`, catalog scoring |
| `multimodal/cosmos3_adapter.py` | **PRESENT** (416 LOC) | ABSENT | Cosmos-3 Reasoner photo/screenshot → LayoutSpec proposal adapter |
| `multimodal/cosmos3_runtime.py` | **PRESENT** (467 LOC) | ABSENT | Cosmos-3 runtime client |
| `multimodal/scenario_campaign.py` | **PRESENT** (248 LOC) | ABSENT | Scenario-variant campaign planning over LayoutSpecs |
| `mcp_floorplan_tools.py` | **PRESENT** (2898 LOC) | ABSENT | Whole floor-plan MCP tool surface (wires the above into MCP) |
| `multimodal/instantiator.py` | MODIFIED (imports relation_reasoning + asset_resolution; reasoning-driven LayoutSpec→USD at `:524/591/1023`) | MODIFIED — **different impl**: `LayoutSpecCodeGenerator` / `apply_layout_spec_to_scene` / `_build_canonical_code` (`:61/293`), Kit-RPC codegen, NO reasoning/asset imports | Both implement LayoutSpec→scene, incompatibly |
| `chat/tools/multimodal_handlers.py` | MODIFIED (imports `resolve_layout_assets`, emits `asset_resolutions`) | MODIFIED — no asset import; uses `ratify` + `resolve_compliance` only | Both modified since MB → 3-way conflict |
| `multimodal/binding_adapter.py` | ABSENT | **PRESENT** (working-only) | LayoutSpec bindings → role_dict for `execute_template_canonical` |
| `multimodal/vision_sam_clip.py` | ABSENT | **PRESENT** (working-only) | SAM/CLIP vision provider |
| `chat/canonical_instantiator.py` | MODIFIED | MODIFIED (both since MB; small, +23/−2 net) | Execution: hard-instantiate (both have it) |
| `chat/tools/handlers/pick_place.py` | 6645 LOC | **9101 LOC** (+1708/−368 vs master) | Execution bridge — far more mature on working (UR10 cup-frame, cuRobo, suction, dual-arm mutex) |
| `chat/tools/kit_tools.py` | present | present | **IDENTICAL both sides** — the actual Kit exec transport is NOT in conflict |

Master callers of the IR/asset stack (all on master only):
`mcp_floorplan_tools.py:19-20, 490, 556, 1183, 1217, 2862`,
`multimodal/routes.py:38-53, 299, 625`,
`multimodal/instantiator.py:21-22, 524, 591, 1023`,
`chat/tools/multimodal_handlers.py:46, 261-286`.

**Summary of the split:**
- **`origin/master`** = the *static spatial-reasoning + asset-resolution + Cosmos3
  vision* floor-plan stack (relation reasoning → asset resolution → LayoutSpec →
  reasoning-driven instantiation), exposed through `mcp_floorplan_tools.py`.
  Execution / QA (pick_place) is ~1 month behind.
- **working tree** = the *execution + QA* stack (mature pick_place with UR10
  cuRobo/suction/dual-arm, gate measurement, role-binding hard-instantiate via
  `binding_adapter` + `vision_sam_clip`), but its `instantiator.py` is a
  reasoning-LESS codegen path; it lost the deterministic relation/asset reasoning.

### B3 — Re-convergence task + conflict-surface estimate

**Goal:** one tree containing (1) master's IR static-reasoning + asset-resolution +
Cosmos3, and (2) the working tree's mature execution bridge + role-binding
hard-instantiate.

**Whole-tree divergence (context, do NOT attempt as a blind 3-way merge):**
- 313 files present on master but not on working HEAD
- 95 files present on working HEAD but not on master
- 225 files modified on both sides
- working HEAD is +1207 commits from merge-base; master +243.
A blind `git merge origin/master` is not advisable — most of those 538 differing
files are unrelated (QA scripts, sub-phase scaffolding, docs).

**The TARGETED re-convergence (the part that matters) is small and mostly clean:**

1. **Cherry-port 5 clean-add modules** master→working (no working-tree
   counterpart → zero conflict, just copy + add the `__init__.py` exports):
   - `relation_reasoning.py` (664), `asset_resolution.py` (408),
     `cosmos3_adapter.py` (416), `cosmos3_runtime.py` (467),
     `scenario_campaign.py` (248). **≈2203 LOC, conflict-free.**
   Update `multimodal/__init__.py` (master adds no new exports there for these — they
   import directly — but verify).

2. **Decide on `mcp_floorplan_tools.py` (2898 LOC, master-only).** Bring it over if
   the MCP floor-plan tool surface is wanted; it imports the 5 modules above. Clean
   add (absent on working) → no merge conflict, but it must be reconciled with the
   working tree's MCP tool registration.

3. **Reconcile the 2 genuinely-conflicting files** (modified on BOTH sides since
   merge-base — real 3-way conflicts):
   - `multimodal/instantiator.py` — two incompatible LayoutSpec→scene impls
     (master's reasoning-driven vs working's `LayoutSpecCodeGenerator` codegen).
     This is the **core merge decision**: either (a) re-insert the
     `normalize_spatial_relations` + `resolve_object_asset` calls into the working
     tree's `LayoutSpecCodeGenerator` pipeline (reason → resolve → codegen → Kit
     RPC), or (b) keep both and route by mode. Hand-merge required; this is the one
     real design conflict.
   - `chat/tools/multimodal_handlers.py` — re-add the `resolve_layout_assets`
     import + `asset_resolutions` payload (master `:46, 261-286`) on top of the
     working tree's `ratify`/`resolve_compliance` version. Mechanical-ish.

4. **No execution-bridge conflict to worry about.** `kit_tools.py` is byte-identical;
   `pick_place.py` and `canonical_instantiator.py` are STRICTLY more advanced on the
   working tree — keep working's versions verbatim, do not take master's.

**Conflict surface estimate for the targeted convergence:**
- Conflict-free additions: ~5100 LOC (2203 IR/asset/cosmos + 2898 floorplan MCP,
  if wanted) — pure copy.
- Genuine hand-merge: 2 files (`instantiator.py`, `multimodal_handlers.py`); only
  `instantiator.py` carries a real architectural decision.
- Direction: port master→working (working has the irreplaceable execution maturity;
  master has the irreplaceable reasoning modules that are clean adds).

**Recommended sequence:** copy the 5 reasoning/asset/cosmos modules (+ floorplan MCP
if desired) into the working tree as plain adds; wire the reasoning calls into the
working tree's `instantiator.LayoutSpecCodeGenerator` (the one design merge);
re-add the `asset_resolutions` payload to `multimodal_handlers.py`; keep
working-tree `pick_place.py` / `kit_tools.py` / `canonical_instantiator.py`
untouched. This converges IR static-reasoning + asset-resolution + execution bridge
in ONE tree without the 538-file blind merge.

---

### Citations (file:line / git refs)
- `git merge-base origin/master HEAD` → `97d62982` (2026-05-08); master +243, HEAD +1207
- `execute_template_canonical` — `chat/canonical_instantiator.py:764`; callers `chat/orchestrator.py:1031`, `multimodal/routes.py:489`
- per-robot+phase PhysX subs — `chat/tools/handlers/pick_place.py:887, 894, 1029, 1329`; shared `World.instance()` `:645, 1084, 1852`; `mutex_path` `:3161, 3653-3790`
- pipeline planner — `chat/pipeline.py:1-12, 27, 428`; route `chat/routes.py:418`
- master IR stack — `git show origin/master:.../multimodal/relation_reasoning.py` (664), `asset_resolution.py` (408), `cosmos3_adapter.py` (416), `cosmos3_runtime.py` (467), `scenario_campaign.py` (248), `mcp_floorplan_tools.py` (2898)
- master callers — `mcp_floorplan_tools.py:19-20,490,556,1217,2862`; `multimodal/routes.py:38-53,299,625`; `multimodal/instantiator.py:21-22,524,591,1023`; `multimodal_handlers.py:46,261-286`
- working-only — `multimodal/binding_adapter.py`, `multimodal/vision_sam_clip.py`
- both-side conflicts — `instantiator.py`, `multimodal_handlers.py` (changed vs `97d62982` on both master and HEAD)
- `kit_tools.py` identical both sides; `pick_place.py` working 9101 LOC vs master 6645 (+1708/−368)
