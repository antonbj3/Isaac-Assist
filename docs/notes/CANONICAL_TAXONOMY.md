# Canonical Taxonomy — the Defensibility Spec

**Author:** Anton + Claude (synthesis 2026-06-09)
**Status:** Living spec. Defines WHICH canonicals should exist and the RULE that makes each defensible.
**Supersedes/consolidates:** `2026-05-27-canonical-taxonomy.md` (naming), `2026-05-27-expansion-roadmap.md`
(domain allocation), `2026-06-01-coverage-gap-analysis.md` + `-BACKLOG.md` (G1–G14 gaps),
`EXPANSION_DIRECTION_PLAN.md §3–4` (toolify gate + axes). Read those for derivation; this is the decision.

**The user's bar (verbatim):** *"I want to be able to defend what each canonical should contain and why it
exists."* Every canonical must earn its place by proving a **DISTINCT capability**, not by being an API-clone
of another with new coordinates. This document is the gate that enforces that.

---

## 0. The one-sentence rule

> A canonical earns its place **iff** it is the *cheapest scene that forces a capability the verification
> spine (form-gate → function-gate → honest-eyes) can measure, and which no already-green canonical forces.*
> Everything else is either a **procedural variant** (auto-generated, parametric) or **clone-spam** (rejected).

The litmus, applied to every proposed row: **"What UNIQUE thing does this prove that no existing green
canonical proves?"** If the answer is "the same thing, with a different number," it is a *variant* of an
existing base, not a new base — and it does not get hand-authored.

---

## 1. THE DEFENSIBILITY GATE

A proposed canonical is **admissible as a hand-authored base** only if it passes **all five** tests.
If it fails any, it is either downgraded to a procedural variant (§4) or rejected.

### Gate test 1 — Distinct capability (the core test)
It must move at least one **taxonomy axis** (§2) to a value **no green base already occupies**, in a way
the function-gate or honest-eyes can *distinguish*. Moving an axis the gate cannot see (e.g. cube colour,
mass within an already-tested band, a cosmetically different prop) is **not** a distinct capability.

- Admissible: `pick.ur10.suction-static.001` — first suction pick the gate grades (vs every parallel-jaw pick).
- Admissible: `assemble.franka.snap-fit-click.001` — first *click-detection* success signal (vs delivery).
- **Rejected:** "Franka picks a red cube" when "Franka picks a blue cube" is already green — colour is not
  a graded axis. → variant of the existing base, or dropped.
- **Rejected:** "UR10 picks a 60 g cube" when 50 g and 100 g siblings exist — interpolation inside a tested
  band. → procedural variant (§4), never a base.

### Gate test 2 — Gate-measurable (it must be falsifiable)
The distinct capability must produce a **signal the verification spine can read**: a delivery, a contact
event, a force/torque threshold, a routing decision, a placement-error distribution, a `why`-taxonomy verdict
(`diagnose_task_outcome`). If the only "novelty" is a structural prop with no new graded outcome, it is not a
capability — it is decoration.

- A canonical whose *only* difference from a green base is invisible to `gate_one.py` + `scene_timeseries.py`
  cannot be defended as proving anything. (This is why "no-robot" scene-only props like the broken
  `cross-belt-sorter` `stable_fail` are weak: nothing to grade.)

### Gate test 3 — Reuse-minimal (the cheapest scene that forces it)
It must be the **minimal scene** that forces the capability. If a smaller existing canonical already forces
it, prefer extending the smaller one's variant-vector over authoring a bigger near-duplicate. A 6-station
line does not earn 6 base slots if the novel thing is "back-pressure" — that is ONE capability (back-pressure)
on top of an existing handoff base.

### Gate test 4 — Not a forbidden clone (the pruning criterion)
The 121→112 prune (`EXPANSION_DIRECTION_PLAN.md §5`) archived 9 templates. The basis — now the standing
exclusion rule — was: **a template is a clone iff its `(domain, robot, gripper, task, feed, perception)`
tuple is identical to another's AND its only delta is a value inside an already-tested band.** Concretely,
prune/reject when:
- **(a) Identical capability-tuple** to a greener sibling (the greener one wins; the other is archived).
- **(b) Pure value-interpolation** inside a tested axis band (→ demote to procedural variant).
- **(c) Un-gradeable** (no robot / no measurable outcome / `stable_fail` with no path to green) AND not a
  deliberate canary.
- **(d) Aspirational-only** — claims a backend/capability the spine has never verified, with no plan to
  verify (the "13 declared backends, 2 real" honesty problem; `MASTER_EXECUTION_PLAN Phase 0`). De-scope to
  `declared-not-verified` rather than counting it as coverage.
- **(e) Duplicate persona dialogue** — Cohort A is capped at 220 (`dialog` saturates; adding more dilutes
  retrieval signal, roadmap §10).

### Gate test 5 — Defensible justification string (the artifact)
Every admitted base carries, in its `index_card`, a one-line **`defends:`** field stating the distinct
capability and the contrast canonical it is NOT a clone of. If you cannot write that sentence, the canonical
does not pass. Example:
`"defends": "first suction pick graded by the gate; contrast pick.franka.* (parallel-jaw, different grasp physics)"`.

**Gate summary table**

| Test | Question | Fail → |
|---|---|---|
| 1 Distinct | Moves a *graded* axis to a new value? | variant or drop |
| 2 Measurable | Spine can read the novel outcome? | drop (decoration) |
| 3 Minimal | Cheapest scene forcing it? | extend smaller base instead |
| 4 Not-clone | Capability-tuple unique + not aspirational? | prune (a–e) |
| 5 Justified | Can write the `defends:` line? | reject |

---

## 2. THE TAXONOMY AXES (the cross-product, gap-weighted)

A canonical's identity is a point in a 7-axis space. The id `<domain>.<robot>.<variant>.NNN` encodes the two
load-bearing axes (domain, robot); the rest live in `index_card` tags. **The cross-product is NOT uniform —
it is weighted toward measured gaps and away from the saturated Franka-parallel-jaw-cube-static center.**

### The 7 axes and their values

| # | Axis | Values | Saturation / gap (measured) |
|---|---|---|---|
| A1 | **robot** | franka · ur10/ur10e · multi-arm · carter/AMR · mobile-manip(AMR+arm) · g1-humanoid · anymal/quadruped · *(ros2-bridge as a cross-cut)* | franka **saturated** (~130); ur10 ~100% frontier; multi-arm partial; mobile-manip **absent**; humanoid asset-gated; quadruped 2 stubs |
| A2 | **gripper** | parallel-jaw · suction/surface · 3-finger-adaptive · tool-changer(multi) · dexterous-hand(allegro) | parallel-jaw **saturated**; suction **thin** (21 tagged, 14 pick / 3 sort / **0 reorient**); 3-finger **≈absent** (2 drafts); tool-changer 1 hand-coded; dexterous = RL-diagnostic only |
| A3 | **task** | pick · place · stack · palletize(grid) · sort(route) · convey(topology) · reorient/flip · kit · insert/assemble · inspect · machine-tend · navigate · train · bridge · safety | pick/stack/palletize/sort **deep**; **reorient thin** (4 genuine, all parallel-jaw); assemble broad-but-`drafted`; **composed multi-stage = 0 on disk** |
| A4 | **feed** | static · conveyor · gravity-dispenser · rotary-table · bin/heap-clutter | static + conveyor deep; gravity/rotary thin; clutter ~10 thin |
| A5 | **perception** | none · color · material(barcode/NIR/RFID) · vision-classifier · multi-cam-6dof · local-SAM2/CLIP-closed-loop | none/color deep; **local closed-loop perception thin** (provider exists, few templates use it); multi-cam hand-rolled |
| A6 | **complexity-tier** | T1 single-obj · T2 multi-obj · T3 feed-dynamics · T4 perception-gated · T5 multi-robot-cell · T6 real-asset-cell · T7 multi-cell-warehouse | T1–T3 deep; T4 partial; **T5 sparse** (2 with ≥3 arms); **T6 real-asset ≈absent**; **T7 absent** |
| A7 | **domain** (id segment) | pick · palletize · sort · convey · assemble · navigate · inspect · train · dialog(cap) · canary · bridge · safety · *compose* | see roadmap §2 allocation; dialog capped |

### The weighting rule (how the cross-product is biased)

Do **not** enumerate the full Cartesian product (it is ~tens of thousands and 95% would be clone-spam at the
Franka center). Instead, **weight each candidate point by its gap-distance from the saturated center** and
build high-weight points first:

```
priority(point) =  Σ gap_weight(axis_value)   over the 7 axes
gap_weight:  saturated = 0   ·   thin = 2   ·   absent = 3   ·   safety/physics-correctness path = +1
```

- A point that is `franka × parallel-jaw × pick × static × none × T1 × pick` scores **0** → it already exists,
  build nothing (or at most one canonical reference + variants).
- A point that is `ur10 × suction × reorient × rotary × none × T3 × pick` scores high (suction=2, reorient=3,
  rotary=2) → **build the base**, it fills three gaps at once.
- A point that is `mobile-manip × suction × pick × static × multi-cam × T5 × navigate` scores very high
  (mobile-manip=3, T5=2, multi-cam=2) → high-priority frontier base.

This is the operational form of "build toward the gaps, not the saturated center" (`MASTER_EXECUTION_PLAN §4`).
**The center is represented by exactly ONE reference canonical per domain + its procedural variants — never a
hand-authored fleet of near-identical Franka-cube picks.**

---

## 3. A REPRESENTATIVE DEFENSIBLE SLICE (28 rows, T1→T7, franka→humanoid)

Each row: the `<domain>.<robot>.<variant>.NNN` id · the DISTINCT capability it proves · the one-line
defensibility justification · priority (**GAP** = high, fills a measured hole; **REF** = the single saturated-
center reference, keep one; **SKIP/variant** = do not hand-author, generate or drop). Existing-template
mapping shown where one exists.

### T1 — single-robot, single-object (the floor)

| id | distinct capability | defensibility | prio |
|---|---|---|---|
| `pick.franka.static-cube.001` | parallel-jaw pick of one static cube into a bin | THE reference for the saturated center; every variant inherits from it | **REF** (maps CP-50-class) |
| `pick.ur10.suction-static.001` | first **suction** pick the gate grades; compliant cup-frame, no kinematic-teleport oracle | contrast parallel-jaw: different grasp physics (seal vs squeeze) — proves the suction path is gradeable | **GAP** (maps CP-70 ✓) |
| `pick.franka.3finger-cube.001` | first **3-finger adaptive** grasp the gate grades | gripper axis A2=3-finger is ≈absent (2 drafts, none green); proves topology-select grasp closes | **GAP** |
| `pick.franka.static-cube.0NN` (mass/material/colour) | none — value-interpolation | NOT a base: mass/material inside a tested band | **variant** (§4) |

### T2 — single-robot, multi-object (placement math)

| id | distinct capability | defensibility | prio |
|---|---|---|---|
| `stack.franka.column-2cube.001` | vertical stack: place ON another object (z-aware) | proves cube-on-cube placement (not just into-bin) | REF (maps CP-13 ✓) |
| `palletize.ur10.layer-2x3.001` | **grid placement math** (6 drop-targets from pallet geom) | first palletize: grid arithmetic the gate verifies per-cell | **GAP** (maps CP-NEW-palletizer-layer-stack) |
| `palletize.ur10.mixed-sku.001` | heterogeneous SKU sizing in one pallet | proves mixed-size grid (not uniform boxes) — distinct from layer-2x3 | **GAP** |
| `sort.franka.color-2bin.001` | **route-by-attribute** into ≥2 destinations | first sort: a *routing decision* the gate reads (MISROUTED guard) | REF (sort reference) |
| `reorient.franka.flip-2pose.001` | **in-hand/regrip flip** to a new face | reorient axis A3 is thin (4, none suction); proves pose-change, not transport | **GAP** |

### T3 — feed dynamics (the object moves / arrives)

| id | distinct capability | defensibility | prio |
|---|---|---|---|
| `pick.franka.conveyor-sync.001` | pick a **moving** object synced to belt speed | proves moving-target timing (the dominant RODE_OFF_BELT failure mode) | REF (maps CP-12-class) |
| `pick.ur10.gravity-dispenser.001` | pick from a **gravity-fed** chute (stochastic arrival) | feed axis A4=gravity is thin; proves dispenser settling + reach | **GAP** (maps CP-71) |
| `pick.franka.rotary-table.001` | pick off an **indexing rotary** feed | distinct feed dynamics from linear belt | **GAP** |
| `pick.ur10.suction-conveyor.001` | **suction × conveyor** combined | suction(2)+moving(0 today for suction); proves seal under transit | **GAP** |

### T4 — perception-gated (a sensor decides)

| id | distinct capability | defensibility | prio |
|---|---|---|---|
| `sort.franka.barcode-divert.001` | route by **scanned label** (material/ID axis) | perception A5=material; a *classification* gates the route | **GAP** |
| `inspect.franka.defect-divert.001` | **vision-classifier** reject to a lane | first vision-gated divert with P/R against ground truth | **GAP** (maps CP-NEW-inspect-reject) |
| `pick.franka.binpick-sam-clip-loop.001` | **local SAM2+CLIP** closed-loop, re-perceive each pick | A5=local-closed-loop is thin (provider exists, ~unused); no cloud quota; proves re-perceive loop | **GAP** (backlog #6) |
| `inspect.franka.multicam-6dof.001` | hand-eye-calibrated **multi-cam 6-DOF** pose → grasp | proves calibrated extrinsics + reprojection-error report | **GAP** (backlog #14) |

### T5 — multi-robot cell

| id | distinct capability | defensibility | prio |
|---|---|---|---|
| `pick.multi.dual-franka-handoff.001` | **shared-belt handoff** with claim-mutex | proves 2-arm coordination (mutex, not deadlock) | **GAP** (maps CP-52 ✓) |
| `assemble.multi.pipelined-3arm.001` | **continuous pipelined** flow (all arms active) + line-balance | distinct from strict-serial handoff; proves back-pressure/throughput model | **GAP** (backlog #20, L) |
| `pick.mobile.amr-ur10-navigate-pick.001` | **mobile manipulation**: drive-then-pick, base-pose-for-reach | A1=mobile-manip is **absent**; proves navigate+pick co-planning | **GAP** (backlog #8) |

### T6 — full work-cell on real assets

| id | distinct capability | defensibility | prio |
|---|---|---|---|
| `pick.ur10.asset-klt-crate.001` | first **real SimReady asset** scene (KLT bin + crate, real mesh) | A6=T6 ≈absent; proves the function gate can grade a **real-mesh** grip (the asset-bridge risk) | **GAP** (MASTER_PLAN Phase 2A pilot) |
| `machine-tend.ur10.cnc-interlock-loop.001` | **same-robot multi-phase** load→door→dwell→unload ×5 | needs `phase_id`; proves per-cycle interlock + multi-PPC without state-bleed | **GAP** (backlog #4, gated on #1) |
| `assemble.franka.peg-spiral-search-ft.001` | **force-gated insertion** (spiral search, abort >15 N) | success signal is force-curve, not delivery — a new graded outcome | **GAP** (backlog #2, build-now) |
| `assemble.franka.snap-fit-click.001` | **click-detection** via force-drop + retry | distinct success signal (contact event) from peg-in-hole | **GAP** (backlog #5, build-now) |
| `safety.ur10.estop-cat0-resume.001` | **verified mid-trajectory Cat-0 stop** + resume | proves a real stop-and-resume, not a structural `enable=false` flag | **GAP** (backlog #19, L) |

### T7 — multi-cell / composed / humanoid frontier

| id | distinct capability | defensibility | prio |
|---|---|---|---|
| `compose.franka.pick-inspect-sort-palletize.001` | **composed multi-stage** workflow (one runnable scenario) | composed (`sub_stages`) = **0 on disk**; proves cross-domain chaining + handoff invariants | **GAP** (backlog #9, roadmap §8) |
| `assemble.g1.bimanual-hold-fasten.001` | **continuous-hold** while the other arm fastens (no release) | whole bimanual-hold class is `stable_fail`; distinct from sequential | **GAP** (asset-gated G1; backlog #7) |
| `navigate.anymal.locomotion-payload.001` | **legged locomotion** + optional payload | A1=quadruped is 2 stubs; proves legged gait under load | **GAP** (asset-gated) |
| `compose.multi.3cell-warehouse-amr.001` | **multi-cell** composition + AMR logistics between cells | T7 is **absent**; the North-Star endgame scene | **GAP** (roadmap endgame, Phase 5) |

**What this slice deliberately under-builds:** more Franka-cube-static picks (REF only + variants),
more persona dialogues (capped), and any aspirational backend not on the verified spine. Eight of the
28 are REF/variant or saturated; **20 are GAP** — the slice itself is gap-weighted, matching §2.

---

## 4. BASE vs VARIANT — the split

Two tiers of canonical, with a hard boundary between them.

### Hand-authored BASE (the ≤15-per-wave tier)
A base is authored by hand and **must clear the §1 gate**. Author a base **iff** any of:
- **New tool surface** — it exercises a bridge/safety/train/insertion tool path not yet templated.
- **New robot family** — first canonical for a robot at a given gripper (franka→ur10→multi→AMR→g1→anymal).
- **Qualitatively new function-gate** — the *success signal itself* changes (delivery → force-curve →
  click-event → routing-decision → placement-Cpk → composed handoff-invariant). This is the sharpest line:
  **if the gate grades it differently, it is a base; if the gate grades it the same way with different
  numbers, it is a variant.**
- **New complexity-tier rung** — first canonical at T_n that composes T_{n-1}.

Every base re-passes the **function gate** (not just form). Budget: **≤15 hand-authored bases per wave.**

### Procedural VARIANT (the ≤500 Cartesian tier)
A variant is **generated** by `expand_variants.py` from a base's `variants.spec` block and **never
hand-authored**. It is admissible iff it is **pure parametric value-substitution inside an already-tested
axis band** — i.e. it deliberately *fails* gate-test-1 (no new graded capability) and that is fine, because
it inherits the base's verification.

```json
"variants": {
  "axes": { "cube_mass_g":[5,25,100], "n_cubes":[1,2,4], "material":["rubber","plastic","metal"] },
  "exclude": [ {"gripper":"vacuum","material":"rubber"} ],
  "max_combinations": 30,
  "naming": "pick.franka.mass-{cube_mass_g}g-{material}.NNN"
}
```

A variant passes the **form gate** + a **sampled function-gate subset** (not every child). Budget: **≤500
procedural children of ≤15 bases per wave** (roadmap §4).

### The boundary rule (one sentence)
> If a generator can emit it from a base's `variants.spec` without a freeform `python_code` arg, it is a
> **variant**. If it needs new control flow, a new tool, a new robot, or a new success signal, it is a **base**.

This is the same litmus as the toolify gate's criterion 2 (`EXPANSION_DIRECTION_PLAN §3`): parametric →
variant/tool; structural → base/raw. **Verification tiering follows the split:** T0 auto-pass (variant of a
green base) → T1 function-gate-only (new variant axis) → T2 viewport spot-check (new base/robot/EE) → T3 full
manual (contact-rich, safety, compliance) — roadmap §5.

---

## 5. GROWING DEFENSIBLY — 112 → 200 → 1000

Each growth band is tied to a **capability frontier**, not a count. The count is an *output* of filling the
frontier, never the target. A band cannot open until the prior frontier is gate-green (dependency-gated,
`MASTER_EXECUTION_PLAN`).

### Band A: ~112 → ~200 — "close the verified frontiers" (the disciplined slice)
**Frontier:** the measured G1–G14 gaps + the toolify foundation. This band is **mostly hand-authored bases +
the first procedural variants off them**, because the gaps are *capability* holes, not value holes.
- Fill the **thin-gripper** frontier: suction (pick→sort→reorient), 3-finger (the absent axis).
- Fill the **thin-task** frontier: reorient, force-gated insertion (spiral/snap/helical — build-now), the
  first **composed** workflow, the first **machine-tend multi-phase** (gated on `phase_id`).
- Fill the **thin-perception** frontier: local SAM2/CLIP closed-loop, multi-cam 6-DOF.
- Land the **asset-bridge pilot** (first T6 real-mesh canonical) — proves the gate grades real assets.
- **Every add here must clear the §1 gate.** No clone-spam: this is the band where the bar is *highest*,
  because each slot is a distinct capability the spine has never measured. Net new ≈ 88, almost all GAP.
- Discipline carry-over: **prune as you go** (extend the 121→112 prune) — archive any clone that surfaces.

### Band B: ~200 → ~600 — "ride the reuse multiplier" (variant explosion)
**Frontier:** breadth *within* now-verified capabilities. Once a base is green, its `variants.spec`
Cartesian-expands into siblings **for free** (T0/T1 verification). This is where the count grows fastest and
where clone-spam is *prevented by construction* — variants are admitted *because* they fail gate-test-1
(parametric-only) and inherit the base's verdict.
- `palletize.*` mixed-SKU × {2x3, 3x3, 2x4} × {3-SKU, 6-SKU}; `sort.*` {color/size/weight/barcode/RFID} ×
  {franka, ur10}; `convey.*` {y-merge, s-bend, cross-belt, recirc} × {1/2/3-belt}; `train.*` DR sweeps ×
  {lighting, texture, friction-mass}; mass/material/n-object sweeps off every green pick/stack base.
- **Guardrail:** a variant is only generated off a **green** base (never a `drafted` one — no auto-promoting
  children of an unverified parent, roadmap §5). The generator runs the form-gate per child; CI blocks any
  form-gate ERROR. **This band adds ~400 with ~0 new distinct capabilities — and that is correct**, because
  the capabilities were already defended in Band A; Band B is coverage *density*, not new claims.

### Band C: ~600 → ~1000 — "the hard frontiers + composition" (gated tail)
**Frontier:** the capabilities gated on infra/assets/research — bases again, but expensive ones.
- **Contact-rich at depth** (gated on PhysX-stability): peg-in-hole tolerance sweep, gear-mesh/rotate-to-mesh
  (the one truly-missing insertion strategy), bolt-tighten, wire-harness.
- **Humanoid + quadruped + mobile-manip** (gated on Nucleus SimReady assets): G1 bimanual hold, Anymal/Spot
  loco-manip, AMR+arm co-planning at cell scale.
- **Real-asset T6 cells** at breadth + **composed T7 multi-cell** workflows (≥20, the roadmap DoD), each a
  base composing ≥3 *already-stable* sub-stages (hard prereq).
- **yrkesroll fill** to ≥40 unique ONET SOC codes (currently ~12) — each new SOC role earns a base only if it
  forces a distinct capability/asset; otherwise it is a *tag* on an existing base, not a new template
  (`yrkesroll` is an A7-tag, NOT a domain — roadmap §5).

### Why this never becomes clone-spam
- **Band A & C are bases** — each clears the §1 gate (distinct, measurable, justified). The bar is the gate,
  not a quota.
- **Band B is variants** — admitted *precisely because* they are parametric (no new claim), verification
  inherited, generated not authored. They cannot be clone-spam because they are explicitly *not claiming* a
  new capability — they are coverage density on a defended base.
- The dangerous thing — a hand-authored near-duplicate base that *looks* novel but isn't — is exactly what
  gate-test-1 + gate-test-4(a) reject. The 121→112 prune is the standing proof the project already enforces
  this; this spec generalizes that prune into the admission rule.

**Definition of done (corpus):** ~1000 on disk · ≥800 function-gate green · ≥40 SOC codes · ≥20 composed
workflows · retriever ≥0.7 top-3 precision · **and every one of the ≤~120 hand-authored bases has a
defensible `defends:` line** — that last clause is this document's contribution to the DoD.

---

## 6. The `index_card.defends` field (the artifact that operationalizes this)

Add to every **base** canonical's `index_card` (variants inherit their base's, with `"variant_of": "<base-id>"`):

```json
"index_card": {
  "id": "pick.ur10.suction-static.001",
  "defends": "first suction pick graded by the function gate (seal physics); contrast pick.franka.* parallel-jaw (squeeze physics)",
  "axis_novelty": { "gripper": "suction" },          // which axis value is new vs the green corpus
  "gap_weight": 2,                                     // §2 priority score at authoring time
  "tier": "base",                                      // base | variant
  "variant_of": null                                   // base-id if tier==variant
}
```

A retrieval/audit pass over the corpus can then assert the invariant directly: **no two `tier:base`
canonicals share an `axis_novelty` value-tuple** (gate-test-4a, machine-checkable). That assertion is the
defensibility guarantee made queryable — the corpus can *prove* it contains no clone bases.
