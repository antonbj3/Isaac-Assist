# Canonical Template Spec ("the mall")

Field-by-field spec for `workspace/templates/*.json`, grounded in what production code ACTUALLY consumes
(`scripts/canonical_schema.py` is the linter's source of truth; `canonical_instantiator.py` executes;
`template_retriever.py` retrieves; `ratify.py` binds; `gate_one.py`/`scene_eyes.py`/`reach_validate.py` verify).

## The defensibility gate for FIELDS
A field belongs iff ALL three hold:
1. **Named consumer** — some code does `template.get("<field>")` (cite it). Else it's docs, not schema.
2. **Distinct failure on removal** — name what breaks (a gate mis-measures, retrieval misses, instantiation emits wrong paths, ratify can't bind). "Nice metadata" is not a failure.
3. **Not cheaply derivable** from another field at consume-time.
(Same 3-part test the project applies to TOOLS in EXPANSION_DIRECTION_PLAN §3, applied to fields.)

## MANDATORY fields (net-new T1 scene canonical), in authoring order

1. **`task_id`** — `<domain>.<robot>.<variant>.NNN` (new) or `CP-NN`/`CP-NEW-*` (legacy). Consumed: retriever ChromaDB id (`template_retriever.py:144`), gate filename, instantiator directive header. Primary key — collisions break the index.
   - ⚠️ **MUST-FIX before new naming ships:** linter routes T1 rules off `task_id.startswith("CP-")` (`canonical_schema.py:167`). A `sort.ur10.*` id is not `CP-` → skips ALL T1 lint. ADD an explicit `tier` field or domain-prefix allowlist first.
2. **`tier`** *(ADD)* — `"T1"`|`"T2"`. Replaces the fragile CP- prefix heuristic.
3. **`goal`** — a TASK + success criterion, NOT an impl detail. Consumed: highest-weighted line of the retrieval embedding (`template_retriever.py:134,137`). Impl-detail goals pollute the embedding → retrieval can't discriminate.
4. **`intent`** {`pattern_hint` (enum: pick_place/sort/reorient/navigate/insert/train/other), `structural_features` {n_robot_stations, destination_kind, uses_conveyor_transport, n_workpieces, gripper_type…}, `structural_tags` (`isaac:robot.ur10` etc.)}. Consumed: the structural retrieval pre-filter (`template_retriever.py:404,526,535,581`). Drives WHICH canonical wins + measures the gaps (suction-thin etc.).
5. **`roles`** {role_name: {constraints, expected_count, required}}. Consumed: `ratify.py:401` parse → LayoutSpec→role binding. The contract the multimodal intake binds user objects to. Without it, a layout can't map onto the template.
6. **`role_defaults`** — concrete path/class/position/size per role (list for multi-instance). Consumed: `canonical_instantiator.py:760,811` (substitution source when no LayoutSpec bindings). Remove → unsubstituted `{{primary_robot.path}}` literals → build crashes. Also the ground-truth geometry the reach/position auditors check.
7. **`code_template`** (+ `code` legacy) — Python tool-call sequence with mustache placeholders (`{{role.field}}`, `{{role[N]}}`, `{{#each role.list}}`). Build order: `create_scene_baseline → robot_wizard → workpieces → scene elements → controller → sensors/gates`. Consumed: `execute_template_canonical:803,813`. THE executable artifact + **training-substrate L1**. `code_template` over `code` because placeholders let the SAME canonical bind to user geometry.
8. **`tools_used`** (list) — consumed by retriever (embedded) + `template_uses_motion_planning()` lint gate.
9. **`thoughts`** — discriminating rationale tokens; 2nd line of the retrieval embedding (`template_retriever.py:135`). Separates near-identical goals in embedding space.
10. **`verify_args`** {stages:[{robot_path, pick_path, place_path}], cube_path} — FORM-GATE input (`canonical_instantiator.py:1091` reach/bridge/pipeline check BEFORE sim). Without it the CP-84/85 out-of-reach class ships undetected.
11. **`simulate_args`** {target_path, duration_s, cube_path|cube_paths, xy_tolerance, color_routing} — FUNCTION-GATE + EYES input (`gate_one.py:72-80`). Each sub-field maps to a gate decision: target_path=delivery footprint (wrong→false neg/pos), duration_s=sim window (90s under-measures slow relays), cube_paths=multi-cube tracking (omit→measures only primary). **Training-substrate L3** (the label).
12. **`diagnose_args`** {robot_path, pick_pose, drop_pose, obstacles} — seeds the WHY-classifier (the DIAGNOSE stage). Build-side half of "tools come in pairs". Caveat: primary consumer `diagnose_task_outcome` is greenlit-not-built; only `reach_validate.py` reads it today.
13. **`motion_controllers`** {verified:[], failed:{name:reason}, untested:[]} — HONESTY LEDGER. Consumed: retriever controller-compat filter (`template_retriever.py:268`). Stops the library *looking* like 15 working control paths when only 2 are real (cuRobo + direct_joint).
14. **`failure_modes`** (list) — the labeled negatives; fed to the LLM few-shot + the training corpus's negative examples.
15. **`verified_status`** (free-text) — per-template position on the verification spine, with evidence. **Training-substrate L3 metadata** (which tuples are verified). N-of-M discipline records "✓ 3/3 fresh-Kit" here.

## RECOMMENDED
16. **`settle_state`** {cubes:{path:[xyz]}, conveyors:{path:[vxyz]}} — preferred source for restoring positions/velocities after the controller mutates them (`canonical_instantiator.py:215`). Without it, fragile regex over `code`. **Exactly {cubes,conveyors}** — narrative settle data goes in `thoughts` (CP-NEW-adaptive-3finger ships inert `finger_drive_state_per_object` etc. that NOTHING reads).

## OPTIONAL (provenance): `extends`+`extension_notes` (co-occur), `_patch_history`

## OPTIONAL — forward-looking (ship with consumer)
- **`asset_ref`/bbox** on a role_default {asset_ref, bbox:[dx,dy,dz]} — Phase 2A canonical→asset bridge. `create_rigid_body_array(asset_ref=)` consumes it. Sync shape with Kimate's catalog `{usd_path,name,category,tags}`.
- **`training_capture`** {l1_tool_calls, l2_expanded_usd, l3_outcome} — §3b corpus-as-training-data. L1 already captured by the instantiator; L3 lives in verified_status; this structures + pairs them.
- **`variants.spec`** {axes, exclude, max_combinations, naming} — Phase 4 Cartesian expansion. ONLY on hand-authored bases; children carry `variant_of`/`variant_axes` (no recursive expansion). None exist today.

## FORBIDDEN (deprecated, lint errors): `benchmark_vs_alternatives`, `verified_date`, `verified_metrics`, `delivery`, top-level `cube_path`, `extends_notes`, non-{cubes,conveyors} keys in `settle_state`.

## Additions flagged (consumed behavior with no field)
- **`tier`** (highest priority — see field 2).
- **`robot_family`/`spawn_via`** — the UR10 auto-repair (`canonical_instantiator.py:966`) infers this from captured code; make it a field.
- **`color_routing`** — read by `gate_one.py:76` but undocumented in the simulate_args schema.
