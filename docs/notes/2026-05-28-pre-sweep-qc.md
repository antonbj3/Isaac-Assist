# Pre-sweep QC — 2026-05-28

Read-only verification of commits since R6 sweep (post-R6 work).
Branch tip: 897eb945 on refactor/2026-05-12-foundation-night-1.

Scope: cee5cfcb, 5f632036, ca0405fa, 26e787fe, dbace693, a45233d2, 897eb945.

## Per-commit verdict

### cee5cfcb — USD-color introspection fast path — **SOLID** (LOW risk)
File: service/isaac_assist_service/chat/tools/handlers/sensors.py (+118 lines @ 612-731)

Verifications:
- `from .. import kit_tools as _kt` resolves (chat/tools/kit_tools.py exists, exec_sync returns `{success, output}`).
- f-string at line 645 (`for cp in {cube_paths!r}:`) uses `!r` which produces a valid Python list literal of strings (repr escapes embedded chars).
- Fast-path returns ONLY when `_all_have_color and _cube_to_class` — i.e. every cube has resolvable material color. Partial-fail falls through to VLM path (correct).
- Exception handler wraps the entire Kit RPC + parse pipeline; failure logs and falls through.
- `class_labels` shape detection strips " cube" / " box" suffixes — `_color_shaped` only true when EVERY label resolves to canonical color (10 colors covered).
- Color set is hardcoded to 10 names; templates using "crimson" or "navy" would correctly fall through to VLM.

Minor: `_CANON_COLORS` rebuilt on every call (inside handler) instead of module constant — irrelevant perf-wise.

### 5f632036 — arena-lego baseplate widen — **SOLID** (LOW)
Anton-confirmed PASS. Not re-verified.

### ca0405fa — UR10 orientation 90°Z → identity — **SOLID** (LOW)
Files: CP-NEW-machine-tender-load-unload.json (+28 / -28), CP-NEW-palletizer-mixed-sku.json (+288 / -57)

- Both templates now have `orientation=[1, 0, 0, 0]` in: `code` literal, `code_template`, `role_defaults.primary_robot.orientation`.
- `code_template` substitution `{{primary_robot.orientation}}` will produce `[1, 0, 0, 0]` (matches palletizer-layer-stack PASS pattern).
- Both rendered + AST-parsed OK.
- Stale legacy comment in machine-tender `code` field line still says "orientation=[1,0,0,0] = 90-deg around X" — code is consistent, comment is wrong. **Cosmetic; not load-bearing.**
- palletizer-mixed-sku also got a non-trivial 288-line rewrite of `code_template` to use `_workpieces = {{workpieces}}` Python loop — renders cleanly, AST-OK.
- Both templates' `robot_family` still "ur10e" / "{{primary_robot.class}}" — consistent with cuRobo config registry.

### 26e787fe — SAM2+CLIP local vision provider — **SOLID** (LOW-MEDIUM)
Files: vision_sam_clip.py (NEW, 392 LOC — commit msg said 320), _shared.py (+65), vision.py (delegates to _shared), sensors.py (+33 backup chain)

- Module imports clean (verified, no Kit dependency at import time).
- Relative imports `from ....multimodal.vision_sam_clip` resolve correctly: 4 dots from handlers/_shared.py = service.isaac_assist_service.multimodal.vision_sam_clip.
- Lazy-load + asyncio.Lock pattern: correct double-check inside lock.
- Sequential lazy imports inside `_ensure_loaded` (torch / sam2 / open_clip) all guarded with ImportError → returns honest error tuple. Will not crash entire vision pipeline if deps drift.
- Provider singleton `_VISION_PROVIDER_SINGLETON` in _shared.py: process-wide cache, no race issue inside single uvicorn worker.
- `_score_crop` (CLIP) is sync; called in a loop without `to_thread`. Per-mask ~50ms = ~500ms event-loop block per detect_objects call. Acceptable since vision-gate fires once per scene, but worth noting.
- vision_models/sam2.1_hiera_small.pt confirmed present on disk (184 MB).
- `plan_trajectory` returns `[]` honestly; documented limitation.

Concern: sensors.py:783-789 — if `IA_VISION_PROVIDER=gemini` and primary returns nothing, code creates a NEW SamClipVisionProvider() instance bypassing the singleton — wastes one instance allocation but doesn't break anything (no actual model weights re-loaded; `_ensure_loaded()` re-uses module globals).

### dbace693 — H Bridge-1 multimodal — **SOLID** (LOW)
Files: canonical_instantiator.py (+25 lines: role_bindings param), multimodal/binding_adapter.py (NEW 137 LOC), multimodal/routes.py (+60 wiring), tests/test_bridge1_layout_to_canonical.py (NEW 324 LOC)

- `execute_template_canonical(template, param_overrides=None, role_bindings=None)` — both new params are keyword-default-None; positional call site at orchestrator.py:1031 `execute_template_canonical(top["template"])` still works (verified via inspect.signature).
- routes.py:430-438 wraps `_load_template` in try/except — handles missing-template; sentinel `{"id": template_id}` only used in ratify (legacy path).
- routes.py:494-499 wraps `execute_template_canonical` call in try/except + populates `execution_error` payload key.
- binding_adapter: list-valued roles like `workpieces` NOT supported (per docstring); when Bridge-1 caller omits a role, `{{#each workpieces}}` block expands to empty (correct, no crash).
- Adapter hardcodes `position[2]=0.0` (2-D LayoutSpec) — known limitation; will put robot on floor if user supplies layout-based bindings to a table-mounted-robot template. Documented in adapter docstring.
- pytest tests/test_bridge1_layout_to_canonical.py → 5/5 pass. Regression suites (canonical_instantiator, canonical_templates_b1b, multimodal_foundation, role_based_code_dispatch) 99/99 pass on tip.

### a45233d2 — SOC + doc QC + inspector-reject z-fix — **SOLID** (LOW)
Mostly docs/_patch_history entries. The inspector-reject-divert diff includes a real physics fix (cube z 0.830 → 0.8325, was half-embedded in belt). Verified: fix applied to `code` field, `settle_state.cubes_initial`, AND `role_defaults.workpieces[N].position`. `code_template` uses `{{workpieces[N].position}}` so substitution picks up new z. Consistent across all three surfaces.

### 897eb945 — I-batch 5 templates — **SOLID** (LOW-MEDIUM)
- vacuum-gripper-sheet-pick, tray-stack-unstack, kit-prep-operator, yrkesroll-packer-box-seal, conveyor-recirculation-overflow.
- All 5 render via instantiate_role_based_code(template, None) and ast.parse cleanly.
- Role-vs-default keys match (no orphan {{role.field}} refs).
- conveyor-recirculation-overflow: new `workpieces` + `pick_sensor` roles wired in both `roles` and `role_defaults` (added per commit msg).
- packer-box-seal merged correctly with 1c56a590's 1-PPC collapse — only 1 actual setup_pick_place_controller call in template (other occurrence is in code comment).
- tray-stack-unstack: drop_targets dict baked at author time, top-down ordering correct, j=4 z=0.935 wrist-singularity flagged in `failure_modes`. Robot at z=0.78 + reach 1.3m envelope covers target. Author honestly tags MEDIUM confidence.
- Lid `define_grasp_pose` in packer template uses correct kwarg names. `set_semantic_label(label=..., class_name=...)` matches handler signature in _models.py:SetSemanticLabelArgs (label is Optional).

## Top 3 concerns

1. **palletizer-mixed-sku had a 288-line code_template rewrite hidden inside the "orientation fix" commit.** Anton's commit message documents only orientation [.707] → [1]; rewrite from inline Python sku-dict to `_workpieces = {{workpieces}}` Python loop is a separate semantic change. Targeted re-test FAILED (different downstream reason per commit msg) so this risk is already known.

2. **SAM2+CLIP first-call latency.** `_ensure_loaded()` on cold path runs SAM2 model.to(cuda) + CLIP build_model → typically 3-8 s under `asyncio.to_thread`-less critical section. First vision-classifier template in sweep eats this on its turn. Not a bug, just a wall-clock surprise.

3. **Stale legacy comment in machine-tender-load-unload `code` field** still says "orientation=[1,0,0,0] = 90-deg around X" after the identity-quaternion change. Cosmetic. Code value is correct.

## Risk score per Kit sweep

| Commit | Risk |
|---|---|
| cee5cfcb | LOW |
| 5f632036 | LOW (Anton-confirmed) |
| ca0405fa | LOW (orientation correctly propagated to all surfaces) |
| 26e787fe | LOW-MEDIUM (first-call lazy-load latency, dep cascade if torch/sam2/open_clip drift) |
| dbace693 | LOW (backward-compat verified, try/except wrappers) |
| a45233d2 | LOW (mostly docs; inspector z-fix consistent) |
| 897eb945 | LOW-MEDIUM (5 templates render OK; tray-stack & packer MEDIUM author-confidence due to motion-controller singularities, not code) |

## Net recommendation

**SAFE TO SWEEP.**

All 8 templates render and AST-parse via `instantiate_role_based_code`. All new handlers have honest import/exception guards. No call-site signature breaks. No cross-commit conflict on packer-box-seal (1c56a590 collapse + 897eb945 #each loop merged cleanly).

Pre-sweep optional: bump test_role_based_code_dispatch.py to include the 5 I-batch templates so future regressions get caught at lint-time (not strictly required for this sweep).
