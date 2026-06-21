# Gotcha → Flow-Composition Roadmap (2026-06-21, Anton steer)

Realistic multi-station product-flow gotchas, and how to make the system handle them
**within the composition framework** (parallel → flow → mobile-mediated → coordinated).

## The composition ladder (where each gotcha sits)

- **L1 — Parallel cells** (BUILT + verified): independent cells side-by-side, scene_eyes-gated
  (`compose_eyes_gate`). Verified to 4-cell/26-cube this session; real-fixture + real-object cells compose.
- **L2 — Sequential CHAIN, static handoff** (BUILT): `compose_orchestrate --structure sequential` →
  `chain_xkit_gate` cross-Kit relay; source delivers onto a `handoff_surface` (pick_height), receiver
  picks from there. `chain_stages.json` = verified chain-ready stages.
- **L2.5 — Branching chain** (BUILT, GOLD): 1 source → N receivers (3-way = N-of-3 GOLD, registered,
  cont.319uuu).
- **L3 — Auto-handoff geometry** (#29, OPEN): make ARBITRARY blocks chain (handoff role/height compat),
  not just pre-declared chain-ready stages.
- **L4 — MOBILE-mediated handoff + coordination** (THE GAP the gotchas demand): an AMR carries product
  between stations whose handoff locations are NOT geometrically adjacent, and the transport is
  EVENT-coordinated with the stations' timing ("drive when the cell finishes").

**Recurring gap across ALL gotchas:** today's handoff is STATIC (receiver picks where source delivered).
The gotchas need a mobile transport (AMR/forklift) as the link, plus event-synced coordination.

## The gotcha suite (realistic, graded — also the build order)

### G2 — Inbound: forklift → depalletize → size/SKU sort  *(most-ready)*
Forklift sets a mixed pallet at inbound → an arm depalletizes boxes onto a belt → a sort cell routes
each box by SIZE/SKU to one of 3 lanes.
- **Flow:** pallet → belt → sort.
- **Derivable dims:** dock = forklift footprint (measured **1.21×3.50m**) + approach; sort pitch =
  measured box footprint (the object-adaptive pitch — BUILT).
- **Have/gap:** real pallet ✅ · multi-pick depalletize ~ · multi-dest sort ✅ · object-adaptive ✅ ·
  forklift placement ~(measure ✅, mobile-forklift control ✗). Mostly L1/L2 — **buildable soon**.

### G1 — Assembly line with AMR shuttle  *(introduces L4 minimally)*
Station 1 (Franka) kits parts into a tray → Carter-AMR carries the tray to Station 2 (Franka) which
INSERTS a peg → AMR carries the finished unit to an outbound pallet at Station 3.
- **Flow:** tray kit → insert → pallet, AMR-transported.
- **Derivable dims:** aisle = AMR footprint (measured **0.67×0.63m**) + clearance; turn zone = AMR length.
- **Have/gap:** 3-cell ✅ · insertion ~ · AMR transport ~(direct-drive works, no nav-gate) ·
  **cell↔AMR event-sync ✗ (L4 core)**.

### G3 — Warehouse: receiving → storage → pick → ship  *(large scene + fleet)*
Forklifts move pallets receiving→rack array; an arm picks items rack→order totes; an AMR FLEET carries
totes→packing; a pack cell boxes orders.
- **Derivable dims:** aisle = forklift width + AMR width + 2×clearance ≈ 1.21+0.67+~1 ≈ **~2.9m** (two-way).
- **Have/gap:** large scene ~ · heterogeneous robots ~ · layout-derive ~ · **fleet coordination ✗**.

### G4 — Mixed-robot insertion on an indexing table  *(timing-sync, hardest)*
Parts on a belt → Franka picks+INSERTS into a fixture on a rotating index table → a UR arm at the next
index fastens → an AMR removes finished fixtures. Synchronize belt + index table + arms.
- **Have/gap:** insertion ~ · multi-robot-type ~(Franka+UR; UR gripper issues) · **moving-index sync ✗** ·
  belt sync ~.

## Ambiguity-handling principle (Anton, the discriminator)

Under-specification is the norm. Rule: **measurable → MEASURE it** (resolve the ambiguity via asset bbox,
e.g. forklift width 1.21m — don't guess); **unmeasurable + low-impact → explicit FLAGGED default**;
**unmeasurable + high-impact → CLARIFY**. NEVER silently assume (= the phantom/false-success risk at the
scene-spec level). Example: "3 forklifts fit across" — MEASURE gives width 1.21m, but the SEMANTIC
ambiguity *parked side-by-side (~4.6m) vs maneuvering aisle (~10m, forklift is 3.5m long)* is a 2-3× swing
→ must CLARIFY, not guess.

## Concrete next increment (L3→L4 bridge)

**Mobile-mediated handoff primitive:** a chain where the handoff is carried by an AMR, not a static
surface. Minimal: source delivers to a spot → Carter `navigate_to`s there → product attaches (constraint/
parent) → Carter drives to receiver input → detaches. Needs: navigate_to (have, direct-drive) +
attach/detach-to-AMR + a **nav-gate** (scene_eyes-equivalent: did the AMR reach the target + did the
product move + clearance). This is the keystone for G1/G3/G4 and deserves a dedicated fresh-context build.

## Measured asset dims (grounding, this session)
- forklift.usd **1.21 × 3.50 × 2.16 m** · forklift_c **1.36 × 3.73 × 2.17 m** · carter_v1 **0.67 × 0.63 × 0.66 m**
- (via `scripts/qa/measure_fixture.py` — the same measure-don't-guess primitive that derives spacing.)
