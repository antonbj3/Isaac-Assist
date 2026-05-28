# Multimodal 2D-layout flow → CP-NEW canonical templates

**Date:** 2026-05-28
**Investigator:** Opus 4.7 research agent
**Scope:** Trace whether/how a 2D layout input (sketch / photo / drag-drop / viewport-sync) reaches a CP-NEW canonical instantiation today, and what the design intends.

---

## 1. The DESIGN (what the research docs say SHOULD happen)

Source: `docs/research/2026-05-27-llm-input-format.md` §2-4,
`docs/research/2026-05-27-integration-architecture.md` §3-4,
`docs/research/2026-05-27-decisions.md` D1-D8.

Intended end-to-end pipeline:

```
sketch image bytes  ──VLM──►  produce_layout_spec_from_sketch()  ─┐
photo image bytes   ──VLM──►  produce_layout_spec_from_photo()   ─┤
canvas drag-drop    ────────► POST /api/v1/canvas/{sid}/patch    ─┤  LayoutSpec
text prompt         ────────► produce_layout_spec_from_text()    ─┤  (IR with
voice (STT)         ────────► produce_layout_spec_from_voice()   ─┤   intent
viewport(Kit stage) ────────► sync_from_stage() (Kit RPC read)   ─┘  + objects
                                                                     + bindings)
                                          │
                                          ▼
                              planner/funnel.py (DESIGN)
                              Stage 1: role pre-filter (<1ms)
                              Stage 2: soft struct-filter
                              Stage 3: confidence gate (sim+margin)
                                          │
                                          ▼
                              planner/router.py (DESIGN)
                              ─► TemplateDispatch(template_id, params)
                              ─► WorkflowDispatch
                              ─► FreeformDispatch
                              ─► HilDispatch
                                          │
                                          ▼  (when TemplateDispatch)
                              ratify(template, spec)
                                          │
                                          ▼  (when ok)
                              execute_template_canonical(template,
                                                         role_bindings=spec.bindings)
                                          │
                                          ▼
                              instantiate_role_based_code(template, role_bindings)
                                  → substitute_role_placeholders(code_template,
                                                                  bindings or
                                                                  role_defaults)
                                          │
                                          ▼
                              tool capture → tool_executor → Kit RPC
```

Key design pivot — `LayoutSpec.bindings` (modality output) flows into
`instantiate_role_based_code(template, role_bindings=...)`. Inside
`substitute_role_placeholders` those bindings replace the template's
`role_defaults`, so the same `code_template` produces a scene anchored on
the USER'S object positions instead of authored defaults. That is the
"how 2D layout parameterizes a canonical" bridge.

Field-level intent (from `llm-input-format §2`, integration §3.2-3.3):

- `LayoutSpec.intent` (pattern_hint, counts, structural_features,
  structural_tags) — drives RETRIEVAL (which canonical wins).
- `LayoutSpec.objects` (TypedObject[]: class/name/position/size) — drives
  PLACEMENT (where prims go in the scene).
- `LayoutSpec.bindings` (role_name → object_id) — drives ROLE FILLING
  (which user-placed object becomes `primary_robot`, etc.).
- `LayoutSpec.parameters` — T2 substitution targets
  (`n_cubes`, `cube_color`).

The CP-NEW template already exposes the matching plug points:
`intent{}` for retrieval, `roles{}` for ratify constraints, `role_defaults{}`
as fallback values when no bindings supplied, `code_template` with mustache
placeholders (`{{primary_robot.path}}`, `{{#each workpieces}}`, etc.).
The template is ALREADY layout-aware on paper; the wiring just isn't
connected.

---

## 2. What is actually IMPLEMENTED today (file:line evidence)

### Built and load-bearing

| Capability | File | Lines | Status |
|---|---|---|---|
| LayoutSpec IR (Intent, Counts, StructuralFeatures, TypedObject, RoleBinding, Source) | `service/isaac_assist_service/multimodal/types.py` | 1-348 | Production |
| Text-prompt → LayoutSpec.intent (rule-based + LLM) | `service/isaac_assist_service/multimodal/text_modality.py` | 213-245, 324-350 | Production, default `MULTIMODAL_TEXT_INTENT=soft` |
| Sketch → LayoutSpec (VLM extraction adapter) | `service/isaac_assist_service/multimodal/vlm_modality.py` | 167-199 | Scaffold (vlm_call callable seam; no HTTP intake) |
| Photo → LayoutSpec | `service/isaac_assist_service/multimodal/vlm_modality.py` | 185-199 | Scaffold (same as sketch) |
| Voice → text → LayoutSpec | `service/isaac_assist_service/multimodal/voice_modality.py` | n/a | Scaffold (no real STT wired) |
| Viewport (Kit stage) → LayoutSpec | `service/isaac_assist_service/multimodal/stage_to_spec.py` | 160-216 (pure), 216+ (async sync_from_stage wrapper) | Pure layer prod; HTTP route doc-claims-only |
| Drag-drop canvas SPA → LayoutSpec | `web/floor-plan-ui/src/components/CanvasViewport.tsx` | 151-170 (onDrop), `…/api/types.ts:20` (drag_drop modality) | Production-quality SPA |
| Canvas backend (CAS-guarded persist + ratify) | `service/isaac_assist_service/multimodal/routes.py` | 137-507 | Production — endpoints exist |
| Ratify waterfall (auto-binding, needs_choice, rejected) | `service/isaac_assist_service/multimodal/ratify.py` | full 705 LOC | Production |
| Soft struct-filter retrieval | `service/isaac_assist_service/chat/tools/template_retriever.py` (`retrieve_with_intent_soft_filter`) | called from orchestrator.py:974 | Production (hit@1 0.84 R17b) |
| Text-prompt → orchestrator → retrieval → hard-instantiate | `service/isaac_assist_service/chat/orchestrator.py` | 942-1071 | Production |
| Role-based code_template substitution | `service/isaac_assist_service/chat/canonical_instantiator.py` | 601-737 (`substitute_role_placeholders`), 740-760 (`instantiate_role_based_code`) | Production for role_defaults fallback |
| LayoutSpec → USD codegen (LayoutSpecCodeGenerator) | `service/isaac_assist_service/multimodal/instantiator.py` | 61-261 | Production for dry-run; live Kit RPC = scaffold (line 51) |
| 6 LLM-callable tools for layout-spec management | `service/isaac_assist_service/chat/tools/multimodal_handlers.py` | 612-628 | Production-registered |

### CP-NEW templates layout-readiness

Sample inspected: `workspace/templates/CP-NEW-bin-picking-random-pose.json`.
Templates have:

- `intent{pattern_hint, structural_features, structural_tags}` (lines 106-126) — read by retrieval.
- `roles{primary_robot, source_bin, destination_bin, workpieces}` (lines 127-164) — read by `ratify()`.
- `role_defaults{...}` (lines 165-259) — used by `instantiate_role_based_code` when no bindings supplied.
- `code_template` with mustache placeholders (lines 260-260) — supports `{{role.field}}`, `{{role[i].field}}`, `{{#each role}}`, nested + indexed forms.

**No template references** `layout_input`, `from_sketch`, `multimodal_args`,
`from_layout`, `"layout"`, `"sketch"` — confirmed by grep of all
`workspace/templates/*.json`. Templates are layout-CONSUMER-shaped via the
roles/role_defaults/code_template trio, not by any explicit "from-sketch"
field. The design path is: bindings override defaults — that's the entire
contract.

---

## 3. What is MISSING / NOT-YET-CONNECTED

### A. No HTTP entry point for sketch or photo

`produce_layout_spec_from_sketch` and `produce_layout_spec_from_photo`
exist (`vlm_modality.py:167,185`) but NO route accepts an image and calls
them. Grep result for both function names outside the module: only
`__init__.py` re-exports and the docs. `multimodal/__init__.py:85-90`
explicitly states **"VLM modalities — sketch + photo: pre-wired; 0
callers today."**

Real VLM client `vision_real_gemini.py` exists but is not bound to the
sketch/photo producers anywhere.

### B. Canvas `/build` ratifies but DOES NOT execute

`POST /api/v1/canvas/{sid}/build`
(`multimodal/routes.py:393-459`) calls `ratify(template, spec)` then
returns the result. It DOES NOT invoke `execute_template_canonical`.
Line 397 acknowledges this:

> "Actual Kit RPC execution is the existing canonical-instantiator flow
> — wired in Block 1B alongside role-based template refactor."

Block 1B has NOT wired this. Confirmed by grep:
`canonical_instantiator` / `execute_template_canonical` is NEVER imported
anywhere under `service/isaac_assist_service/multimodal/`.

### C. `apply_layout_spec_to_scene` tool handler same gap

`chat/tools/multimodal_handlers.py:213-326` ratifies and returns
`next_step: "ratified ok — caller should invoke canonical-pipeline build
via the existing hard-instantiate path; role-based substitution lands in
Block 1B"` (line 301-305). The "caller" is the LLM agent — but the agent
has no tool to do this, and the orchestrator's hard-instantiate path
(line 1031) is text-only, fed by `produce_layout_spec_from_text` only.

### D. `execute_template_canonical` ignores LayoutSpec bindings

`canonical_instantiator.py:763`:
```python
async def execute_template_canonical(
    template: Dict[str, Any],
    param_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
```
No `role_bindings` parameter. Line 789:
```python
raw_code = instantiate_role_based_code(template)
```
Always called with `role_bindings=None`, which forces fallback to
`template["role_defaults"]` (line 759). The substitution machinery
*can* take bindings; nothing supplies them.

### E. `planner/` directory is a different planner

`service/isaac_assist_service/planner/{generator.py,routes.py,...}` is
the validation→PatchPlan planner (analysis findings → auto-fix). It has
NO `funnel.py`, `router.py`, `index_card.py`, `hil.py`,
`workflow_registry.py` — those are pure DESIGN (integration-architecture
§3.1-3.7, action items 1-10 in decisions §5).

### F. `instantiator.LayoutSpecCodeGenerator` is parallel to canonical path

`multimodal/instantiator.py:51` — "live Kit RPC exec remains scaffold."
The generator emits per-object USD-Python (UsdGeom.Cube.Define etc.) but
its `instantiate(spec)` (line 364) goes through `queue_exec_patch`
directly — it does NOT route through any CP-NEW template. This is the
"freeform path" — useful when retrieval misses, but it BYPASSES the
canonical's verified physics/controller setup. Not the design intent for
"sketch → matched canonical → parameterized instantiation."

### G. Layout-generator (WFC+NSGA-II) fallback path doesn't exist

`llm-input-format §5` describes a `LayoutSpec → ConstraintCompiler →
MacroWFC → freeform.force_freeform` fall-through for novel topologies.
Only `freeform.force_freeform` exists (45 LOC, `freeform.py`); no
ConstraintCompiler, MacroWFC, RepairEngine. Pure design.

### H. Workflow templates exist but aren't registered (q7 t41)

`llm-input-format §1` and §6 flag this. Confirmed —
`workflow_template_{pick_place,sdg,validate_robot}.py` exist in
`multimodal/`, but no registration call sites. The ≤30-LOC
`planner/workflow_registry.py` is design only.

---

## 4. Concrete walkthrough

### "If user uploads a sketch TODAY"

1. User saves PNG of pick-place sketch.
2. **There is no HTTP endpoint** that accepts an image. The canvas
   `/api/v1/canvas/{sid}/patch` route accepts a full LayoutSpec JSON,
   not images. The orchestrator chat endpoint does multimodal text only.
3. The only way to push image bytes through the existing code today is
   to call `produce_layout_spec_from_sketch(image_bytes, vlm_call=...)`
   from a Python script — providing your own `vlm_call` callable, since
   `vision_real_gemini.py` isn't wired to it.
4. Even with that LayoutSpec in hand: posting it via
   `POST /api/v1/canvas/{sid}/patch` persists it; `POST .../build`
   ratifies; **nothing executes the template**. The response says "next
   step: caller should invoke canonical-pipeline build" — but no caller
   exists for canvas-originated specs.

**Effective result today: a 2D sketch goes nowhere. The only multimodal
input that hits canonicals today is `text` — the prompt arrives at
`POST /api/v1/chat/`, the orchestrator calls
`produce_layout_spec_from_text` (orchestrator.py:972), uses
`spec.intent` for soft-filter retrieval (line 975), and on confident
match calls `execute_template_canonical(template)` with no
bindings (line 1031) → falls back to `role_defaults`.**

### "If user drags objects onto canvas SPA TODAY"

1. SPA palette drag → `CanvasViewport.tsx:158 onDrop` creates a
   TypedObject in the local Zustand store.
2. SPA POSTs full LayoutSpec to `/api/v1/canvas/{sid}/patch`.
3. Backend validates and persists (`routes.py:156-213`).
4. `preview_render` rasterises a PNG (line 368).
5. `/build` calls `ratify(template={"id": body.template_id}, spec)` —
   note that `template={"id": ...}` is a stub dict, NOT a real template
   loaded from `workspace/templates/`. Ratify against an unloaded
   template returns "ok" trivially (legacy mode, no roles).
6. Returns `bindings` payload to SPA. **Scene is not built.**

### "What design says SHOULD happen for sketch upload"

1. `POST /api/v1/sketch/upload` (or chat-attachment) accepts image
   bytes.
2. Server calls `produce_layout_spec_from_sketch(image_bytes,
   vlm_call=gemini_vision)`.
3. `planner/router.py` runs `funnel(spec, raw_text=None)`:
   role pre-filter → soft struct-filter (using `spec.intent`) → confidence
   gate.
4. On HIGH confidence: `TemplateDispatch(template_id="CP-NEW-bin-picking-
   random-pose", params={...})`.
5. Convert `spec.bindings` (role_name → TypedObject) into the
   `role_defaults`-shaped dict (each role gets path/class/position from
   the bound TypedObject).
6. `execute_template_canonical(template, role_bindings=converted)` →
   `instantiate_role_based_code` substitutes user-placed positions into
   `code_template` → tool capture → Kit RPC.
7. On MED confidence: HilDispatch → HIL-2 template choice bar in SPA.
8. On LOW confidence: FreeformDispatch via WFC layout generator (also
   missing) → `freeform.force_freeform` → `instantiator.instantiate`
   (which DOES exist as the only freeform escape today).

---

## 5. Recommendations

### Minimum work to make ONE canonical actually consume a layout

This is the smallest viable bridge (let's call it "Bridge-1") to prove
the design works end-to-end with ONE template. Estimated 4 changes, no
new modules:

1. **`canonical_instantiator.execute_template_canonical` — add
   `role_bindings` parameter.** Change signature (line 763):
   ```python
   async def execute_template_canonical(
       template: Dict[str, Any],
       param_overrides: Dict[str, Any] | None = None,
       role_bindings: Dict[str, Any] | None = None,
   ) -> Dict[str, Any]:
   ```
   Pass it through to `instantiate_role_based_code(template,
   role_bindings)` (line 789).

2. **Add a `bindings_to_role_dict(layout_spec)` adapter in
   `multimodal/ratify.py` or a new `multimodal/binding_adapter.py`.**
   Walk `spec.bindings`, resolve each `object_id` to the matching
   TypedObject, emit `{role_name: {path: f"/World/{name}", class:
   object_class, position: [x,y,0], orientation: [1,0,0,0]}}`. This is
   the shape that mustache substitution already consumes — no template
   changes needed.

3. **In `multimodal/routes.py:/build` (line 393) — after
   `ratify(template, spec)` returns ok, load the real template via
   `template_retriever.get_template_by_id(body.template_id)`, call
   `bindings_to_role_dict(spec)`, then await
   `execute_template_canonical(real_template,
   role_bindings=converted)`.** Today the route uses a stub
   `{"id": body.template_id}` (line 421) — replace with a real load.

4. **One smoke test:** a unit test that creates a LayoutSpec with one
   Franka + source bin + outfeed bin + 3 cubes, calls the new
   end-to-end path, and asserts the captured tool calls match
   CP-NEW-bin-picking-random-pose with the user's positions
   substituted into `{{primary_robot.position}}`, `{{source_bin.position}}`,
   etc.

That's it for ONE template + canvas. The SPA needs no changes — it
already POSTs to `/build` and renders the response.

### What is OUT OF SCOPE for Bridge-1 (post-MVP)

- Sketch/photo entry points (need VLM client wiring + HTTP route).
- Voice intake (need STT).
- Layout-generator fallback (WFC+NSGA-II — none of it exists).
- `planner/router.py` + `planner/funnel.py` — Bridge-1 hardcodes
  template selection via the SPA's `body.template_id`. Funnel/router can
  follow once Bridge-1 proves the binding-flow works.
- Workflow registration (Mode A). Independent ≤30-LOC fix
  (`planner/workflow_registry.py`).
- Bridge-1 only proves canvas → canonical. Sketch/photo are the same
  pattern: once the image-bytes → LayoutSpec adapter is wired, the
  downstream is identical.

### Alternative framing: "integration is post-MVP"

If Bridge-1 is too large for current sprint, the honest framing is:
**the 2D-layout multimodal foundation is built but disconnected from
the canonical-execution path. Text-only retrieval works end-to-end
today; everything else is research-grade with documented seams.** The
research docs `2026-05-27-*` are forward-design — none of `planner/funnel.py`,
`planner/router.py`, `planner/index_card.py`, `planner/hil.py`,
`planner/workflow_registry.py` exists. Decisions D1-D8 are unblocked but
no D-action has landed. Acting on `decisions.md §5` action 1
("Verify workflow-registration LOC claim") is the cheapest entry point;
action 7 ("Drop `planner/funnel.py`") is the first load-bearing landing.

---

## 6. Bottom line

- **Design is coherent and ~70% scaffolded** (per integration-arch §1).
- **Real integration coverage is text-prompt-only** end-to-end.
- **Canvas + sketch + photo + voice all ratify, none execute.** The
  scaffolding ends at `ratify()`; the bridge from `RatifyResult.bindings`
  to `execute_template_canonical(template, role_bindings=...)` is the
  single most load-bearing missing wire.
- **CP-NEW templates themselves are layout-ready** — `intent`/`roles`/
  `role_defaults`/`code_template` plug directly into the design — but no
  caller passes them anything other than `role_defaults`.
- **The `planner/` directory people might assume hosts the multimodal
  router is actually a different (analysis-findings) planner.** The
  designed `planner/router.py`, `planner/funnel.py`, etc. do NOT exist
  on disk yet.
