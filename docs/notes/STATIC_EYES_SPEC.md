# STATIC EYES — fast, no-physics geometric layout verifier

A cheap pre-check that reads a layout (object paths + positions + fixed asset bboxes
+ robot + pick/place targets) and returns a per-check verdict + overall PASS/FAIL +
machine-actionable fix suggestions, so the LLM can iterate on a layout **without paying
for Kit build + physics settle**.

It sits between the structural `form_gate` and the expensive `function_gate`:

```
form_gate (structural, instant)  →  static_eyes (geometric, no Kit)  →  function_gate (sim, ~minutes/Kit)  →  diagnose
```

This document is grounded entirely in code that already exists. The design is mostly
**assembly + a thin pure-Python facade** over validators that are already written; it is
NOT a from-scratch tool.

---

## 1. What already exists (the parts we're assembling)

| Component | File | Needs Kit? | What it gives static_eyes |
|---|---|---|---|
| Live cuRobo reach probe | `scripts/qa/reach_validate.py` | **YES** (Kit + cuRobo) | The ground-truth reachability verdict. Too expensive for the loop; used as oracle to *calibrate* the static approximation. |
| Live scene-constraint validator | `scripts/qa/scene_validate.py` | **YES** (build+settle) | The 5 checks (reach / target-reach / interpenetration / support / physics-instability) — but post-settle, in Kit. static_eyes re-implements the geometric subset on the pre-build layout. |
| Live virtual eyes (dynamic) | `scripts/qa/scene_eyes.py` | **YES** (running sim) | Dynamic-only signals (motion, grip release, contacts over time). Defines the static/dynamic boundary: anything in here is NOT static-derivable. |
| **Pure-Python reach validator** | `service/.../multimodal/spawn_validator_contact_reachability.py` | **NO** | `ContactReachabilityValidator`: within-reach (`is_within_reach` L184), min-reach dead-zone, **AABB occlusion** via slab ray-test (`ray_intersects_aabb` L195, `is_occluded` L238), joint-limit, normal-valid. Operates on synthetic tuples. **This is the static reach core.** |
| **Pure-Python blueprint validator** | `service/.../multimodal/sub_phase_72c_blueprint_validator.py` | **NO** | `BlueprintValidator`: XY-AABB overlap (`_aabbs_overlap` L78), room-bounds, asset-class validity — all from `position` + `PALETTE` footprint. **This is the static interpenetration/footprint core.** |
| Pre-flight drop-in-container check | `scripts/validators/template_geometric_sanity.py` | YES today (queries Kit AABB L43-70) | The drop-target-inside-destination logic (`inside_xy` L112, `above_top` L113). Static-izable: swap the Kit AABB query for a PALETTE-derived AABB. |
| Fixed asset dimensions | `service/.../multimodal/object_palette.py` | NO | `PALETTE[asset].footprint_xy_m` (L21) + `default_z` (L23). **The static asset-bbox source.** (Gap: no `height_m` — see §6.) |
| Reach radius per robot | `service/.../chat/tools/handlers/resolve.py` L23 `_ROBOT_REACH_M` | NO | `ur10/ur10e=1.30, franka_panda=0.855, ur5e=0.85, kinova=0.902, h1=0.58, g1=0.45, default=0.80`. Mirror of `scene_validate.py:32 ROBOT_REACH`. |
| Verifier registry / gates | `service/.../multimodal/verifier_registry.py` | NO | `form_gate` (L164) + `function_gate` (L187). The `verify:reach` form check (L336-356) is **a stub** that passes when no `reach_diagnostics` arg is supplied. static_eyes is the thing that *fills that arg*. |

**Key finding:** the two pure-Python validators (`ContactReachabilityValidator`,
`BlueprintValidator`) already cover most of the static surface. They are exercised in
unit tests with **no Kit / GPU dependency** (spawn_validator docstring L15-18). static_eyes
is largely a façade that (a) builds their inputs from a layout + PALETTE, (b) runs them,
(c) merges findings into one verdict with actionable fix strings, and (d) feeds the result
into the `verify:reach` form-gate arg.

---

## 2. Static-vs-dynamic check taxonomy

For each candidate check: can it be decided from **positions + fixed asset bboxes alone**,
or does it **require physics simulation**?

| Check | Verdict | Why | Existing code |
|---|---|---|---|
| **Footprint / workspace-envelope** (object outside declared cell bounds) | **STATIC** | Pure XY compare position±footprint vs room dims. | `BlueprintValidator._check_room_bounds` (72c L247) |
| **Interpenetration / clump** (two pick objects overlap in 3D) | **STATIC** | AABB-vs-AABB overlap from positions + footprints. Settling only *worsens* a pre-existing overlap; if they overlap at spawn they're already a clump. | `_aabbs_overlap` (72c L78); 3-axis version in `scene_validate.py:312` |
| **Fit** (does workpiece fit inside the bin XY?) | **STATIC** | Compare workpiece footprint vs bin inner footprint. Pure geometry. | new (trivial AABB-containment, reuse `_aabb_xy`) |
| **Drop-target-in-container** (drop XY inside destination AABB, drop Z above its top) | **STATIC** | `inside_xy`/`above_top` are pure point-in-AABB. Today it reads Kit AABB; swap for PALETTE-derived AABB. | `template_geometric_sanity.py:112-113` |
| **Clearance** (static gap between two fixtures / between fixture and robot base swept-radius) | **STATIC** | AABB-to-AABB / point-to-AABB distance. | new (reuse slab distance) |
| **Occlusion / line-of-reach blocked** (an enclosure wall sits between base and pick) | **STATIC (approx)** | Slab ray-test base→contact vs occluder AABBs. Approximates a *straight-line* reach; the arm may route around, so this is conservative-ish (can false-flag a routable case). | `ContactReachabilityValidator.is_occluded` L238 |
| **Reachability — distance shell** (pick within radius of base) | **STATIC (necessary, not sufficient)** | Radial distance vs `_ROBOT_REACH_M`. Catches gross out-of-reach. Does NOT capture the non-convex floor (see §5). | `is_within_reach` L184; `scene_validate.py:280` |
| **Reachability — IK feasible at a specific pose** | **DYNAMIC-ish (needs cuRobo, not full physics)** | Non-convex; conflates kinematics + scene collision (reach_validate L20-23). A single-IK probe needs cuRobo but NOT a physics settle. | `reach_validate.py` (live) |
| **Support / will-it-fall-through** (does the spawn rest on a surface, not float / not buried) | **MIXED** | *Whether a support surface exists under the spawn* (gap to nearest surface top) is **STATIC** — pure AABB stacking. *Whether it stays put after release* (tips, rolls, slides) is **DYNAMIC**. | static part = `scene_validate.py:337-367` support logic, re-keyed off PALETTE |
| **Stack-stability heuristic** (will a stack topple) | **DYNAMIC** | Center-of-mass over support polygon is a *heuristic* you can compute statically, but real toppling depends on friction, contact, mass, settle dynamics. Static gives a cheap COM-over-base flag only; the real answer is physics. | static heuristic = new (COM-in-base-footprint); real = function_gate |
| **Physics-instability / spawn-overlap explosion** (parts ejected at settle) | **DYNAMIC** | This is the *consequence* of overlap under PhysX; you can predict the *cause* statically (interpenetration check) but the ejection itself is sim-only. | cause=static (interpenetration); effect=`scene_validate.py:248-255` (sim) |
| **Grip latch / release, transit swing, motion stepping, delivered-count** | **DYNAMIC** | Pure controller+physics+time signals. | `scene_eyes.py` only |

**Rule of thumb:** static_eyes answers *"is this layout geometrically coherent and grossly
feasible?"* It cannot answer *"will the controller actually execute it?"* — that is the
function_gate's job. Anything that depends on **time, contact forces, the controller, or a
specific planned trajectory** is out of scope by construction.

---

## 3. Tool interface

Pure-Python, no Kit. Lives at `service/isaac_assist_service/multimodal/static_eyes.py`
(exposed as an LLM-callable tool `static_eyes`), with a CLI mirror at
`scripts/qa/static_eyes.py` for templates.

### Input — a `Layout`

```jsonc
{
  "robots": [
    {"path": "/World/UR10", "family": "ur10", "base": [0.0, 0.0, 1.0]}
    // reach radius looked up from _ROBOT_REACH_M by family
  ],
  "objects": [
    // each object: an explicit bbox OR an asset_name to look up in PALETTE
    {"path": "/World/Cube_1", "position": [0.4, -0.3, 0.78], "asset_name": "cube_5"},
    {"path": "/World/Bin",    "position": [0.5, -0.4, 0.40], "asset_name": "bin",
     "bbox": [[0.30,-0.55,0.0],[0.70,-0.25,0.30]]}  // explicit bbox overrides PALETTE
  ],
  "picks":   ["/World/Cube_1"],
  "places":  [{"target_path": "/World/Bin", "drop_target": [0.50, -0.40, 0.85]}],
  "occluders": ["/World/Enclosure"],   // optional; defaults to all fixture-category objects
  "cell_bounds": {"x": [-1.5, 1.5], "y": [-1.5, 1.5]}  // optional workspace envelope
}
```

Notes:
- `bbox` is `[[xmin,ymin,zmin],[xmax,ymax,zmax]]`. If absent, derived from
  `PALETTE[asset_name].footprint_xy_m` centered on `position`, with z from
  `default_z`+height (see §6 height gap).
- This is intentionally a **flattened, position-only** view — the same data the LLM already
  holds while authoring a layout. No Kit round-trip to obtain it.

### Output — a `StaticEyesReport`

```jsonc
{
  "verdict": "FAIL",
  "checks": [
    {"id": "reach:shell",        "status": "fail",
     "target": "/World/Cube_1",
     "message": "pick /World/Cube_1 at [0.40,-0.30,0.78] is 1.52m from /World/UR10 base (> reach 1.30)",
     "fix": {"action": "move_object", "path": "/World/Cube_1",
             "constraint": "dist_to_base <= 1.30",
             "suggest_position": [0.34, -0.25, 0.78],
             "human": "pick at radius 1.52 unreachable -> move within 1.30m of base, e.g. [0.34,-0.25,0.78]"}},
    {"id": "support:rest",       "status": "pass", "target": "/World/Cube_1"},
    {"id": "interpenetration",   "status": "pass"},
    {"id": "fit:bin",            "status": "pass", "target": "/World/Bin"},
    {"id": "drop_in_container",  "status": "pass", "target": "/World/Bin"},
    {"id": "occlusion",          "status": "warn",
     "message": "straight line base->/World/Cube_1 crosses /World/Enclosure AABB",
     "fix": {"action": "note", "human": "may require non-straight approach; verify in function_gate"}}
  ],
  "overall_fix_order": ["reach:shell"],     // hard errors first, ordered by cheapest-to-satisfy
  "next_gate": "function_gate",             // if PASS; else "fix_and_recall_static_eyes"
  "caveats": ["reach:shell is a NECESSARY shell test, not IK — a PASS still needs function_gate"]
}
```

Status semantics (reuse `verifier_registry.CheckStatus`): `pass` / `fail` / `skipped`,
plus `warn` for soft/advisory (occlusion, clearance) that does NOT block the overall verdict.
Overall `verdict = FAIL` iff any check is `fail`. `warn`s are surfaced but don't gate.

### Mapping to existing validators (no new geometry math where avoidable)

| Report check id | Backed by |
|---|---|
| `reach:shell`, `reach:min`, `occlusion` | `ContactReachabilityValidator.validate` (spawn_validator) — one `ContactPoint` per pick/place, one `RobotReachSpec` per robot (nearest-base), `OccluderBox` per occluder |
| `interpenetration`, `footprint`, `fit:bin` | `BlueprintValidator` AABB logic (72c) + a 3-axis variant from `scene_validate.py:312-322` |
| `drop_in_container` | `template_geometric_sanity.py:112-113`, AABB from PALETTE instead of Kit |
| `support:rest` | static port of `scene_validate.py:337-367` (gap-to-nearest-surface, PALETTE bboxes) |

---

## 4. The LLM-loop contract

The whole point: **iterate without Kit**. The loop is:

```
1. LLM authors / edits a Layout (positions it already controls).
2. LLM calls static_eyes(layout)  -> StaticEyesReport   [milliseconds, no Kit]
3. If verdict == PASS: proceed to function_gate (the expensive step).
   If verdict == FAIL:
     for each fix in report.overall_fix_order:
        apply fix.suggest_position / honor fix.constraint
     goto 2   (re-call static_eyes on the edited layout)
4. Bounded: cap at N (e.g. 4) static iterations; if still FAIL, surface to diagnose
   with the residual findings (don't burn a function_gate run on a layout static_eyes
   already says is broken).
```

### What makes the fix suggestions machine-actionable

Each `fail` carries a structured `fix` object, not just prose:

- **`action`** — an enum the LLM dispatches on: `move_object`, `move_drop_target`,
  `resize_gap`, `swap_destination`, `note`.
- **`path`** — exactly which object to move (no ambiguity).
- **`constraint`** — the satisfiable inequality (`dist_to_base <= 1.30`,
  `drop_xy in dest_aabb`, `gap_to_surface in [-0.02, 0.10]`). This is the **contract**: the
  LLM can re-derive a valid position itself, or trust `suggest_position`.
- **`suggest_position`** — a concrete coordinate that *satisfies the constraint*, computed
  for free since static_eyes already knows the base, the reach radius, and the bbox. For
  reach-shell, project the offending point onto the reach sphere toward the base:
  `p' = base + (p - base) * (reach - margin) / |p - base|`. For drop-in-container, clamp
  XY into the destination AABB and set Z to `dest_top + clearance`.
- **`human`** — the natural-language version (the prompt's example:
  *"pick at y=0.55 unreachable → move to y<=0.40"*), for logs / transcripts.

Because every fix is *self-consistent with the same geometry the check used*, applying
`suggest_position` is **guaranteed to clear that specific check** on the next call (modulo a
new check it might trip — hence the loop). This is what makes the loop converge instead of
oscillate.

### Wiring into the gate that already exists

`verifier_registry`'s `verify:reach` form check (L336) already accepts a
`reach_diagnostics` arg with `{all_reachable: bool, unreachable: [...]}` and returns
`pass`/`fail` accordingly (L347-353). static_eyes produces exactly that shape, so the
integration is: **static_eyes is the producer of the form-gate's `reach_diagnostics` arg**
(and analogous args for `footprint_overshoot`, `orphan_cubes`). Today those checks stub-pass
(L356 "no detail provided") — static_eyes is what makes them actually decide. No registry
change needed; just supply the args.

---

## 5. Reachability cost analysis (the honest part)

The prompt asks: can the heavy reach check be made truly static, or does it need a live
probe? **Answer: a two-tier check — cheap static shell that is NECESSARY-not-sufficient, and
a live cuRobo probe reserved for the borderline band.**

### Why a pure analytic envelope mispredicts (don't pretend otherwise)

`reach_validate.py:20-23` documents the measured failure of a radial formula:

> straight-down reachability is non-convex AND conflates kinematics with scene collision …
> at base-relative radius the reach floor is non-monotonic in y; `[-0.50,0.40]` reaches
> z<=0.80 but `[-0.50,0.25]+Pedestal` only reaches 1.10. A radial formula mispredicts; only
> a probe against the real scene is correct.

And `reach_validate.py:12-18`: even the live single-IK probe is **necessary, not
sufficient** (CP-81 probed REACHABLE yet the gate FAILED) and **stochastic** (Halton seeds
flip single runs; use N-of-M). `scene_validate.py:274-278` says the same: the z-window is
heuristic, "the rigorous check is IK feasibility," and the lower bound is gripper-dependent
(top-down suction can't angle below its mount; a 7-DOF Franka reaches a near-full sphere).

So an analytic envelope has **two known failure modes**:
1. **False PASS** — radial distance OK but the specific straight-down grasp pose has no IK
   solution (the non-convex floor). Static shell says reachable; cuRobo says no.
2. **False FAIL** — radial says too-far for a point a 7-DOF arm could actually reach by
   tilting; or a point an articulated arm reaches below its mount that the suction z-window
   rejects.

We do **not** claim to solve this statically. Instead:

### The tiered design

- **Tier 1 — static shell (always, free):** distance vs `_ROBOT_REACH_M` + a
  gripper-specific z-window (mirror `scene_validate.py:278 ZLO`) + occlusion slab-test.
  - Confidently **rejects** grossly out-of-reach picks (the prompt's `y=0.55 → y<=0.40`
    class). These are real, common, LLM-authored errors and the static check kills them for
    free before any Kit cost.
  - Confidently **passes** picks comfortably inside the shell AND far from the non-convex
    floor (well above base z, well inside radius). Calibrate the "comfortable" margin against
    `reach_validate.py`'s 8/13 PASS set: those all probe REACHABLE and sit inside the shell.
  - Returns **`uncertain`** for the borderline band (near radius limit, near/below base z,
    near an occluder) — explicitly NOT a PASS.

- **Tier 2 — live cuRobo probe (only for `uncertain`, and only once static otherwise
  passes):** call `reach_validate.py`'s single-IK probe. This needs **Kit + cuRobo but NOT a
  physics settle / controller run** — it is far cheaper than the function_gate (one IK solve
  per target, ~10-15s, vs a full sim). Use N-of-M (reach_validate L17) for the stochastic
  flip. This is the "cheaper-than-function-gate sufficient probe."

- **Precomputed reach map (optimization, not required for v1):** for each robot family +
  base-z, sample the cuRobo IK feasibility on a grid offline (radius × y × z, with and
  without a pedestal under the base) and cache it. Then Tier 1's "uncertain" band shrinks to
  a table lookup, and Tier 2 fires only on genuine cache misses (novel occluder geometry).
  This is the only way to make the *non-convex* reach truly static — by precomputing the
  non-convexity rather than approximating it with a formula. Honest caveat: the map is keyed
  on base-z + pedestal-present; arbitrary scene-collision geometry (an enclosure the LLM
  placed) still falls back to the live occlusion slab-test + Tier-2 probe.

### Cost ladder summary

| Tier | Cost | Decides |
|---|---|---|
| Static shell + occlusion | µs, no Kit | gross reject / comfortable pass / **uncertain** |
| Precomputed reach map | µs lookup, no Kit (offline-built) | shrinks the uncertain band for known base/pedestal configs |
| Live single-IK cuRobo probe (`reach_validate`) | ~10-15s, Kit+cuRobo, **no settle** | the uncertain band only; N-of-M |
| **function_gate** | minutes, Kit + physics + controller | execution truth (still the only sufficient verdict) |

---

## 6. Known gaps / honesty notes

1. **PALETTE has no `height_m`.** `ObjectClass` (object_palette L17-24) carries
   `footprint_xy_m` + `default_z` but no z-extent. Static support/fit/drop-Z checks need a
   height. Fix: add `height_m` to `ObjectClass` (or pass explicit `bbox` per object in the
   Layout, which already overrides). Until then, support/drop-Z degrade to `warn` when only a
   footprint is known.
2. **Static AABB ≠ post-settle AABB.** `scene_validate.py` reads geometry *after* a 2.5s
   settle (L96-102); static_eyes reads the *authored* spawn. For overlap this is fine
   (overlap at spawn ⇒ overlap or explosion after). For support it can differ if the author
   floats an object expecting it to fall — static_eyes flags "floats 0.30m" which may be the
   intended pre-drop. Mitigate by treating a small positive support gap (<~0.15m) above a
   valid surface as `warn`, not `fail` (the object will fall onto it).
3. **Occlusion is a straight-line test.** `is_occluded` (spawn_validator L238) tests the
   base→contact segment; a real arm routes around obstacles. So occlusion is `warn`
   (advisory), never a hard `fail` — it tells the LLM "this may need a non-trivial approach,
   confirm in function_gate," it does not reject the layout.
4. **Dynamic feeds.** For carousel/conveyor scenes the pick item sits at its t=0 spawn, not
   the fixed pick station (reach_validate L30-33, scene_validate L207 HAS_ROTARY skip).
   static_eyes must inherit the same skip: if the layout flags a dynamic feed, reach checks
   on the spawn position emit `warn` ("verify the fixed station position"), not `fail`.
5. **Stack-stability is only a heuristic statically.** COM-over-support-polygon is the most
   static_eyes can offer; real toppling is physics → function_gate.

---

## 7. How this reduces function_gate load

- **Kills geometric-error layouts for free.** The recurring LLM-authored bugs that
  `scene_validate.py` was built to catch — clump (interpenetration), float (support),
  out-of-reach pick/place, drop-target-misses-bin — are now caught **before** a Kit build,
  by the same math, on the authored positions. Every such layout that static_eyes FAILs is
  one fewer wasted function_gate run (each costing a full build+settle+controller execution
  on the single-tenant Kit, which also degrades within a session — see MEMORY: Kit-session
  degradation).
- **Reserves cuRobo for the borderline band.** Reach is the single most expensive static-ish
  check; the tiered design only fires the live IK probe on the `uncertain` band, and only
  after the free checks pass — not on every target of every layout.
- **Converges the LLM loop cheaply.** Machine-actionable `suggest_position` fixes let the LLM
  iterate a layout to geometric-PASS in milliseconds-per-iteration, so when it finally hits
  the function_gate the layout is already coherent and the gate is measuring the *controller*,
  not catching a typo'd coordinate.
- **Fills the form_gate stubs.** `verifier_registry` `verify:reach` /
  `verify:footprint_within_bounds` / `verify:cube_source_bridged` currently stub-pass with no
  data (L356, L404, L392). static_eyes is the producer of their `*_diagnostics` args, turning
  three pass-through stubs into real decisions — at no Kit cost.

---

## 8. Implementation checklist (assembly, not greenfield)

1. `service/isaac_assist_service/multimodal/static_eyes.py` — the façade:
   - `layout_to_inputs(layout, PALETTE, _ROBOT_REACH_M)` → builds `ContactPoint[]`,
     `RobotReachSpec[]`, `OccluderBox[]`, and AABB dicts.
   - `run(layout) -> StaticEyesReport` — calls `ContactReachabilityValidator.validate_batch`
     + `BlueprintValidator` + the ported support / fit / drop-in-container checks, merges
     findings, attaches `fix` objects, orders `overall_fix_order` (hard errors first).
2. Add `height_m` to `ObjectClass` (object_palette) — unblocks support/fit/drop-Z (§6.1).
3. Port the support gap-to-surface logic from `scene_validate.py:337-367` to operate on
   PALETTE bboxes instead of live Kit AABBs (drop the settle-play; it's authored geometry).
4. Reuse `template_geometric_sanity.py`'s `inside_xy`/`above_top` for `drop_in_container`,
   swapping `aabb_of_prim` (Kit, L43) for a PALETTE-derived AABB.
5. Tier-2 reach: thin wrapper that shells out to `reach_validate.py` only for `uncertain`
   targets, N-of-M.
6. Register an LLM tool `static_eyes` (chat tools) returning the report JSON; and a CLI
   mirror `scripts/qa/static_eyes.py <TEMPLATE>` that derives the Layout from a template's
   `simulate_args` (cube_paths / target_path) for batch validation.
7. Feed `StaticEyesReport` into `verifier_registry.run_form_gate(..., args={...})` as the
   `reach_diagnostics` / `footprint_overshoot` / `orphan_cubes` producer.

---

### One-line summary
static_eyes = a pure-Python façade over the **already-written** `ContactReachabilityValidator`
+ `BlueprintValidator` (+ PALETTE asset bboxes + `_ROBOT_REACH_M`), giving the LLM a
millisecond geometric PASS/FAIL with machine-actionable `suggest_position` fixes; reach is
tiered (free shell → optional precomputed map → cuRobo IK probe only for the uncertain band,
no physics settle) because the non-convex reach floor provably defeats a pure analytic
envelope (`reach_validate.py:20-23`). It sits between form_gate and function_gate and exists
to stop wasting expensive single-tenant Kit runs on layouts that are geometrically broken on
paper.
