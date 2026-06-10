# The 2D-Layout as a Shared LLM + User Reasoning Surface

**Date:** 2026-06-09
**Scope:** Design the LayoutSpec IR (the 2D floor-plan) as a *shared reasoning
surface* both the USER (canvas drag-drop) and the LLM (tool calls) author and
critique — so the LLM can PROPOSE a layout, statically CHECK it (reach /
collision / fit) in cheap IR-space, ADJUST, and ITERATE *before* a Kit build.

**Branch note (load-bearing):** the two halves of this loop currently live on
*different branches*. The working tree
(`refactor/2026-05-12-foundation-night-1`) has the **execution bridge**
(`routes.py:488` calls `execute_template_canonical`; `binding_adapter.py`
exists). `origin/master` has the **IR-space static-reasoning stack**
(`relation_reasoning.py`, `asset_resolution.py`) which is *absent* from the
working tree. Confirmed:
`git show origin/master:.../relation_reasoning.py` exists;
`ls .../relation_reasoning.py` → No such file. The design below depends on
**both** — re-converging them is the first task.

---

## 0. The core idea

`LayoutSpec` (`service/isaac_assist_service/multimodal/types.py:307`) is ONE
pydantic object, persisted per session with a monotonic `revision`
(`types.py:345`) under a compare-and-swap protocol. It is the single source of
truth. Two clients mutate it through the *same* CAS-guarded persistence:

- **The user** edits via the Konva SPA (`web/floor-plan-ui/`), which debounce-
  PATCHes the full spec (`store/sync.ts:23 schedulePatch`, 200 ms) to
  `POST /api/v1/canvas/{sid}/patch` (`routes.py:patch_canvas`).
- **The LLM** edits via 6 registered tools (`multimodal_handlers.py:612
  register_multimodal_handlers`): `read_layout_spec`, `update_layout_spec`,
  `commit_layout_spec`, `apply_layout_spec_to_scene`, `query_layout_metric`,
  `rebind_role`.

Because both write the same IR through the same CAS gate, every change one
makes is immediately visible to the other. That bidirectional visibility — not
any new datastructure — is what makes the 2D layout a *shared* surface. The
work is in (a) re-uniting the two branches, (b) routing the IR-space static
verdict back to the LLM as a tool result, and (c) feeding real asset bboxes
into the IR so the static check is trustworthy.

---

## 1. The LLM-authoring loop

> **Q:** Can the LLM emit a LayoutSpec (objects + positions) the same way the
> user does (drag-drop → patch)? Map LLM proposes → static verdict → LLM
> patches → re-check → ratify → build.

**Yes — the mutation vocabulary is already symmetric.** The LLM does not POST a
whole spec; it issues *mutations* that mirror the user's canvas gestures
one-for-one (`_apply_mutations`, `multimodal_handlers.py:559`):

| User canvas gesture | LLM mutation op | Evidence |
|---|---|---|
| drag from Palette → drop | `{"op":"add","class","position","size"}` | `multimodal_handlers.py:563`; SPA `CanvasViewport.tsx onDrop` |
| delete key | `{"op":"remove","id"}` | `:577` |
| drag an object | `{"op":"move","id","position"}` | `:582` |
| PropertiesPanel edit | `{"op":"set_attr","id","attr","value"}` (name/rotation/notes/color/layer) | `:590` |

`update_layout_spec` (`multimodal_handlers.py:110`) takes `mutations`,
`parent_revision` (CAS), and a `reason` string, validates via
`validate_layout_spec`, and persists a new revision through
`store.save_with_cas` — the *identical* persistence the user's PATCH uses
(`routes.py:patch_canvas` → same `save_with_cas`). The LLM can bootstrap from
nothing (`parent_revision=0` → `_bootstrap_spec_from_mutations`,
`multimodal_handlers.py:146`), so it can author a layout from a blank session.

### The loop, end-to-end

```
LLM: read_layout_spec(sid)                       # get objects + revision
   → update_layout_spec(sid, mutations=[add robot, add bin, add cubes],
                         parent_revision=r, reason="propose pick-place")
   → STATIC CHECK  (§3)                            # cheap, no Kit
        query_layout_metric(reachable / overlap / distance)   ← EXISTS (flat 2D)
        verify_relation_geometry(spec)                        ← EXISTS on master (3D)
   → if verdict has violations:
        update_layout_spec(... move bin closer, parent_revision=r+1 ...)
        re-check                                    # iterate purely in IR
   → apply_layout_spec_to_scene(sid, template_id)  # ratify → build
        ratify(template, spec)  → ok / needs_choice / rejected
        execute_template_canonical(template, role_bindings)   ← Kit build
```

**What EXISTS:**
- LLM authoring (`update_layout_spec`) and reading (`read_layout_spec`) —
  registered, production (`multimodal_handlers.py:625-627`).
- A cheap IR-space metric probe (`query_layout_metric`,
  `multimodal_handlers.py:329`; schema `tool_schemas.py:9775`): `distance`,
  `reachable` (flat 2D radius vs `reach_m`), `overlap` (2D AABB),
  `footprint_area`.
- Ratify (`ratify.py:436`) and the execution bridge
  (`routes.py:478-499` → `execute_template_canonical`,
  `binding_adapter.py:86 bindings_to_role_dict`).

**What is MISSING / weak:**
1. **The static verdict the LLM sees is a flat-2D toy.** `query_layout_metric`
   `reachable` is `hypot(dx,dy) ≤ reach_m` — it ignores Z, the robot's mount
   height, the reach *shell* (non-convex), and scene collision. It will pass
   picks the arm physically can't reach. The real reach verdict
   (`scripts/qa/reach_validate.py`) and scene soundness
   (`scripts/qa/scene_validate.py`) require a **live Kit build + settle**, so
   they are *not* IR-space. There is no pure-Python 3D reach/collision check
   wired into a tool. (See §3.)
2. **`apply_layout_spec_to_scene` (the tool) does not itself build** on the
   working tree — the handler ratifies and returns a `next_step` string
   (`multimodal_handlers.py:247,301-318`). The build wire is on the HTTP
   `/build` route (`routes.py:488`), not the *tool*. So the LLM's "build"
   action and the canvas's "build" button take different code paths; only the
   route executes. The tool must be brought up to call the same bridge.
3. **No template auto-selection in the loop.** `/build` and the tool both take
   `template_id` from the caller; there is no funnel/router
   (`docs/notes/2026-05-28-multimodal-canonical-flow.md` §3E — `planner/router.py`
   is design-only). For the loop, the LLM picks `template_id` explicitly (fine
   for MVP).

---

## 2. User ↔ LLM symmetry via the shared IR

> **Q:** The canvas is the user's surface; the LayoutSpec is the LLM's surface
> — they're the SAME IR. How does a fix the LLM makes show up for the user, and
> vice versa? (the CAS-revision / ratify path.)

The symmetry is realized by **one persisted object + CAS + an SSE fan-out + a
review gate**. Neither side has a private copy.

### LLM → user (the agent proposes a fix the user reviews)

1. LLM calls `update_layout_spec(..., reason="Agent: moved bin into reach")`.
   Persisted as a new `revision` via `save_with_cas`
   (`multimodal_handlers.py:165`); a telemetry event is appended
   (`:177 store.append_event("update_layout_spec", {revision, reason})`).
2. The SPA's SSE listener (`store/sync.ts:79 startSSE`, channel
   `/api/v1/chat/stream/{sid}`) receives the event, the store re-fetches /
   applies the new spec, and the change lands on the undo stack tagged as an
   agent write.
3. **The review gate:** `ConfirmBar.tsx` renders *only* when the top undo entry
   is a `bulk_update` whose `description.startsWith("Agent:")`
   (`ConfirmBar.tsx:isAgentBulk`). The user sees the floating bar with
   **Accept** / **Reject**:
   - **Accept** → no-op locally (already applied) + optional
     `POST /{sid}/commit` (with `workflow_id`) → `commit_canvas`
     (`routes.py:commit_canvas`) forwards an approve to the workflow registry.
   - **Reject** → `undo()` (pops the agent's BulkUpdate, restoring prior state)
     + `POST /{sid}/reject` with the feedback string
     (`routes.py:reject_canvas` → `_forward_workflow_reject`), which the LLM can
     read to regenerate. This is the human-in-the-loop correction channel.

   So an LLM fix surfaces to the user as a *reviewable proposal*, not a silent
   overwrite — the `"Agent:"`-prefixed `reason` is the load-bearing convention
   that drives the ConfirmBar.

### User → LLM (the user edits; the LLM re-reads)

1. User drags an object; SPA debounce-PATCHes the full spec
   (`sync.ts:schedulePatch` → `api.patch(sessionId, spec, revision)` →
   `routes.py:patch_canvas`), advancing the revision.
2. On the LLM's next turn it calls `read_layout_spec(sid)`
   (`multimodal_handlers.py:74`) and sees the user's positions + the new
   revision. Any subsequent LLM `update_layout_spec` must carry the latest
   `parent_revision` or the CAS gate returns a **409-shaped conflict**
   (`multimodal_handlers.py:166` `RevisionConflictError` →
   `{conflict, expected_revision, actual_revision, current_spec}`).

### The CAS protocol IS the concurrency contract

`LayoutSpec.revision` (`types.py:345`) + `save_with_cas(parent_revision)` give
both clients optimistic concurrency on the same object. The HTTP patch returns
`409 Conflict` with the current spec attached so the SPA can run a three-way
merge (`routes.py:patch_canvas` 409 branch); the tool returns the same payload
shape so the LLM can re-read-and-retry. Conflicts are *expected* and *typed*,
not races — this is what lets user and LLM edit interleaved without a lock.

**What EXISTS:** persisted spec + CAS + revision + ConfirmBar agent-review gate
+ SSE channel + reject→feedback→workflow path. All production.

**What is MISSING:**
- **The LLM cannot yet subscribe to user edits mid-turn** — it polls via
  `read_layout_spec` at the start of each turn. (SSE is SPA→user only; there is
  no agent-side push.) Acceptable for turn-based chat; note it.
- **`commit_layout_spec` is a telemetry no-op** (`multimodal_handlers.py:190`)
  — proposed/committed lives in SPA state. If the LLM-authoring loop needs a
  durable "this revision is the accepted one" marker, that has to be added.

---

## 3. IR-space static checks (pre-build, no Kit)

> **Q:** What static checks can run on a LayoutSpec directly (positions +
> bboxes) without instantiating in Kit? Does the LayoutSpec carry enough
> (asset bboxes, relations) to run reach / collision / fit statically?

This is the heart of the design: **the iteration must be cheap (no Kit build).**
There are today *two tiers* of static check, and a clean gap above them.

### Tier A — flat-2D metric probe (EXISTS, working tree)

`query_layout_metric` (`multimodal_handlers.py:329`) — pure Python, instant:
- `distance(from_id,to_id)` — 2D `hypot`.
- `reachable(robot_id,target_id,reach_m)` — `hypot(dx,dy) ≤ reach_m`. **Flat,
  Z-blind, no shell, no collision.** Necessary-not-sufficient at best.
- `overlap(id_a,id_b)` — 2D AABB intersection from `position ± size/2`
  (`:387`).
- `footprint_area` — Σ `w·h`.

This is enough for the LLM to catch *gross* errors (two objects on the same
spot; bin obviously across the room) but it will green-light unreachable picks.

### Tier B — deterministic 3D relation geometry (EXISTS, `origin/master` only)

`relation_reasoning.py` is a full IR-space spatial reasoner — **no Kit, no
LLM** — and is the right home for the real static check:

- `predict_relation_positions(spec)` (`relation_reasoning.py`) walks the
  relation graph (`on_top_of`, `inside`, `beside`, `mounted_to`,
  `stacked_above`) and computes **3D positions with Z-offsets** from class
  heights (`CLASS_HEIGHTS_M`), support-top tables (`SUPPORT_TOP_M`), and
  interior-floor offsets (`INTERIOR_FLOOR_OFFSET_M`). E.g. cube `on_top_of`
  table → `z = table_top + cube_height/2`; cube `inside` bin → drops to the
  bin's interior floor.
- `verify_relation_geometry(spec)` returns `{status: pass|warning|fail,
  checks:[{subject,relation,object,status,error_m,expected_position,
  actual_position}], predicted_positions, diagnostics}`. It also runs
  `normalize_spatial_relations`, which emits typed diagnostics for *physically
  unsound proposals* before any build: robot `on_top_of` table →
  `relation.robot_on_support` (normalized to `mounted_to`); object `inside` a
  non-container → `relation.container_mismatch`; two parents →
  `relation.multiple_parents` (error); large object inside container →
  `relation.large_inside_container`.

The `/build` route on master already returns this verdict to the client:
`relation_verification`, `relation_diagnostics`, `asset_resolutions`
(`origin/master:routes.py build_canvas` payload) — and the master instantiator
calls `verify_relation_geometry(spec)` at codegen time
(`origin/master:instantiator.py:~720`). This is exactly the "see what's wrong"
signal the loop needs — it just isn't exposed as an LLM *tool result* yet, and
it isn't in the working tree.

### Tier C — reach / collision (the GAP: Kit-only today)

The trustworthy reach + collision + support verdicts are **live-Kit** only:
- `scripts/qa/scene_validate.py` — builds + settles in Kit, then reads actual
  prim geometry and checks REACH (3D dist vs `ROBOT_REACH` + a z-window),
  INTERPENETRATION (post-settle clump), SUPPORT (resting vs floating).
- `scripts/qa/reach_validate.py` — live cuRobo IK probe with the cup pointing
  down at the real grasp height; explicitly documents that straight-down reach
  is **non-convex and conflates kinematics with scene collision**, so "a radial
  formula mispredicts; only a probe against the real scene is correct."

That caveat is the design boundary: **a fully faithful reach/collision check
cannot be done in pure IR-space.** But a *useful, conservative* one can:

- **Reach (IR approximation):** replace Tier-A flat-2D with a 3D shell test
  using `predict_relation_positions` Z + the robot's mount height
  (`CLASS_HEIGHTS_M[robot]`) + a per-robot reach radius (mirror
  `scene_validate.ROBOT_REACH`: ur10 1.30, franka 0.855…) + a z-window. This
  catches the dominant CP-NEW failure mode documented in MEMORY
  ("ALL picks UNREACHABLE straight-down… below floor") **without a Kit build.**
  Mark verdicts `reachable_ir ∈ {ok, marginal, unreachable}`; `marginal` →
  optionally escalate to the live probe.
- **Collision/fit (IR approximation):** 3D AABB overlap using
  `predict_relation_positions` + real asset bboxes (§4), excluding
  legitimate parent/child support pairs. Catches the interpenetration class
  before settle.

**Design call:** wire a single `query_layout_metric` super-metric (or a new
`static_check` tool) that returns the Tier-B `verify_relation_geometry`
verdict **plus** the Tier-C IR approximations, all pure-Python. Keep the live
Kit validators (`scene_validate`/`reach_validate`) as the *post-build*
confirmation gate, not the iteration loop. The loop iterates on the cheap
verdict; the expensive verdict runs once at build. This is the
"`static_eyes`" plug-in point: it is `verify_relation_geometry` + a 3D-shell
reach approximation + a 3D-AABB collision approximation, fed by §4 bboxes.

**Does the LayoutSpec carry enough?** Almost:
- **Relations:** `LayoutSpec.constraints` is `Optional[List[Dict]]` with "full
  schema in v1.1" (`types.py:320`) — relations are currently passed loosely and
  read by `normalize_spatial_relations` via duck-typed `subject_id/relation/
  object_id`. **Gap:** there is no typed `Relation` model in `types.py`. Add
  one (or formalize `constraints`) so the canvas and LLM emit relations the
  same validated way they emit objects.
- **Positions:** `TypedObject.position` is 2D `(x,y)` (`types.py:234`); Z is
  *derived* by `predict_relation_positions`, not stored. That's correct for a
  floor-plan — keep 2D authoring, derive Z.
- **Sizes/bboxes:** `TypedObject.size` is 2D `(w,h)` (`types.py:240`) — the
  *drawn* footprint, which may not equal the real asset's footprint. See §4.

---

## 4. The bbox / asset-size feed

> **Q:** Assets have fixed sizes; the LayoutSpec needs the resolved asset's
> real bbox to reason about fit / collision. How does asset_resolution feed
> bboxes into the LayoutSpec for static reasoning?

Three sources of size exist; the static check must prefer the *real* one.

1. **`TypedObject.size (w,h)`** — what the user drew / the LLM proposed. Not
   authoritative; a user can draw a 0.1×0.1 box for a 0.4×0.4 Franka.
2. **`object_palette.ObjectClass.footprint_xy_m`** — the **canonical real
   footprint per class** (`object_palette.py:22`), e.g.
   `franka_panda (0.4,0.4)`, `table_large (2.0,1.0)`, `conveyor_long (3.0,0.5)`,
   `bin (0.4,0.3)`. Looked up by `get_class(name)`. This is the deterministic
   bbox source for fit/collision and is *already consumed* by
   `relation_reasoning._is_small_object` / `object_category`
   (`relation_reasoning.py` → `get_class(cls).footprint_xy_m`).
3. **The resolved USD asset's true bbox** — `asset_resolution.py`
   (`origin/master`) resolves `object_class` → a concrete `.usd` reference
   (`AssetResolution.usd_ref`, via local overrides → `asset_catalog.json` →
   palette `usd_ref`). The *catalog* can carry real bbox/height; today
   `relation_reasoning` reads height from `metadata.height_m` /
   `asset_height_m` first, then falls back to `CLASS_HEIGHTS_M`.

### The feed (design)

`resolve_layout_assets(spec.objects)` (`asset_resolution.py`) runs at build and
is *already* surfaced in the `/build` payload as `asset_resolutions`
(`origin/master:routes.py`). To make the **static check** trustworthy, run the
same resolution **before** the IR check and stamp the resolved bbox/height back
onto each object's `metadata` so `predict_relation_positions` and the
collision/reach approximations read the true sizes:

```
for obj in spec.objects:
    res = resolve_object_asset(obj)                 # asset_resolution.py
    pal = get_class(obj.object_class)               # object_palette.py
    obj.metadata["asset_footprint_xy_m"] = catalog_bbox(res) or pal.footprint_xy_m
    obj.metadata["asset_height_m"]       = catalog_height(res) or CLASS_HEIGHTS_M[class]
```

Then the static check's effective bbox per object is:
`metadata.asset_footprint_xy_m  ▸  palette.footprint_xy_m  ▸  TypedObject.size`
(first non-null wins), and height is
`metadata.asset_height_m  ▸  CLASS_HEIGHTS_M  ▸  size.z-fallback` — the exact
precedence `relation_reasoning._height_m` already uses for Z. This makes the
"drawn size" advisory and the "real asset size" load-bearing, so the LLM
reasons about fit/collision against what will actually spawn.

**Why it matters for the loop:** the LLM moves a bin "next to" the robot in 2D;
the static check must know the *real* 0.4×0.3 bin and 0.4×0.4 robot footprints
(+ their derived Z) to tell the LLM whether they collide or whether the pick
height is in-reach — `TypedObject.size` alone would lie.

**What EXISTS:** `object_palette.footprint_xy_m` (full 60-class table);
`asset_resolution.resolve_object_asset/resolve_layout_assets` and the
`asset_resolutions` payload (`origin/master`); `CLASS_HEIGHTS_M` / `_height_m`
precedence (`origin/master`).

**What is MISSING:**
- The stamp-back step (resolution → `metadata.asset_footprint_xy_m/height_m`)
  before the IR check — small, deterministic.
- A real per-asset bbox in `asset_catalog.json` (today height comes mostly from
  the `CLASS_HEIGHTS_M` fallback, footprint from the palette). Palette
  footprints are good enough to start.
- `asset_resolution.py` is **not in the working tree** — comes with the merge.

---

## 5. Build plan (what must be done)

In dependency order. Everything below is small and deterministic; no new ML.

1. **Re-converge the branches.** Bring `relation_reasoning.py`,
   `asset_resolution.py` (and the master `instantiator.py` relation/asset/
   verify body, `routes.py` relation_verification + asset_resolutions payload)
   into the working tree alongside the working tree's `binding_adapter.py` +
   `routes.py:488` execution bridge. This single merge gives you BOTH the
   IR-space static stack AND the build bridge. (Biggest, but mechanical.)

2. **Formalize relations in the IR.** Add a typed `Relation` model
   (`subject_id, relation ∈ VALID_RELATION_KINDS, object_id, confidence,
   metadata`) to `types.py` and make `LayoutSpec.constraints` (or a new
   `relations` field) carry them, so canvas + LLM emit relations through the
   same validated path objects already use. Add an `add_relation` /
   `remove_relation` mutation op in `_apply_mutations`
   (`multimodal_handlers.py:559`) and a Palette/edge affordance in the SPA.

3. **Asset-bbox stamp-back.** Before any static check, run
   `resolve_layout_assets` + palette lookup and write
   `metadata.asset_footprint_xy_m` / `metadata.asset_height_m` onto each object
   (§4). Make `_height_m` / the new collision check read that precedence.

4. **Upgrade the static check to a real `static_eyes` verdict.** Extend
   `query_layout_metric` (or add `static_check`) to return: (a)
   `verify_relation_geometry(spec)` (Tier B); (b) a 3D-shell reach
   approximation using derived Z + `ROBOT_REACH` + z-window (Tier C-reach); (c)
   3D-AABB collision using stamped bboxes (Tier C-collision). All pure-Python,
   no Kit. Return per-object `{reachable_ir, collides_with:[...],
   relation_status}` so the LLM can target its next `move`.

5. **Make the `apply_layout_spec_to_scene` *tool* build.** Point the handler
   (`multimodal_handlers.py:213`) at the same Bridge-1 path the `/build` route
   uses (`routes.py:478` → `bindings_to_role_dict` →
   `execute_template_canonical`) so the LLM's build and the canvas build are one
   code path. Keep the live `scene_validate`/`reach_validate` as the
   post-build confirmation gate.

6. **(Optional) Agent-side spec push.** If interleaved mid-turn editing is
   needed, give the agent loop a `read_layout_spec` poll between tool calls, or
   a lightweight server-side "spec changed since revision r" check. Turn-based
   polling is fine for v1.

### Net

- **Authoring symmetry:** DONE (user gestures ≡ LLM mutation ops, same CAS).
- **Review symmetry:** DONE (ConfirmBar agent-review + reject→feedback;
  SSE fan-out; CAS conflicts typed).
- **IR-space static reasoning:** EXISTS but **3D version is on `origin/master`,
  not merged**, and is **not exposed as an LLM tool result**; the working
  tree's tool-side check is flat-2D only.
- **Asset bbox feed:** the *source* exists (palette footprints + asset
  resolution); the *stamp-back into the IR before the check* must be added.
- **Build bridge:** DONE on the working tree (`routes.py:488`); the *tool* path
  must be brought to parity.

The single highest-leverage move is **#1 (merge) + #4 (real static_eyes
verdict as a tool result)** — that turns the existing flat-2D probe into a
trustworthy cheap reach/collision/fit check the LLM can iterate against before
ever paying for a Kit build.

---

## Appendix — file:line index

| Concern | File:line |
|---|---|
| LayoutSpec IR (objects 2D pos/size, revision, source) | `multimodal/types.py:234,240,246,307,345` |
| Ratify waterfall (auto-bind, needs_choice, rejected) | `multimodal/ratify.py:436` |
| Canvas routes: patch (CAS), build (bridge), commit, reject | `multimodal/routes.py:patch_canvas, build_canvas (488 exec bridge)` |
| Bindings → role_defaults adapter | `multimodal/binding_adapter.py:86` |
| Instantiator (working tree, stripped) | `multimodal/instantiator.py:293 _build_canonical_code` |
| Instantiator (master, relation Z-offset + verify + asset) | `origin/master:multimodal/instantiator.py:457,524,591,720` |
| Relation reasoning (predict pos, verify geometry, diagnostics) | `origin/master:multimodal/relation_reasoning.py` (`predict_relation_positions`, `verify_relation_geometry`, `normalize_spatial_relations`) |
| Asset resolution (class → usd_ref, catalog, overrides) | `origin/master:multimodal/asset_resolution.py:resolve_object_asset,resolve_layout_assets` |
| Object palette (footprint_xy_m bbox per class) | `multimodal/object_palette.py:22,27` |
| LLM tools: read/update/commit/apply/query_metric/rebind | `chat/tools/multimodal_handlers.py:74,110,190,213,329,408,612` |
| Tool schemas (LLM-facing) | `chat/tools/tool_schemas.py:9676,9699,9730,9748,9775,10048` |
| LLM mutation ops (add/remove/move/set_attr) | `chat/tools/multimodal_handlers.py:559` |
| Canvas SPA: drag-drop, debounced PATCH, SSE, ConfirmBar review | `web/floor-plan-ui/src/{store/sync.ts:23,79; components/ConfirmBar.tsx}` |
| Live (Kit) reach/collision validators (post-build gate, NOT IR) | `scripts/qa/scene_validate.py`, `scripts/qa/reach_validate.py` |
| Designed flow + gap analysis | `docs/notes/2026-05-28-multimodal-canonical-flow.md` §3-5 |
