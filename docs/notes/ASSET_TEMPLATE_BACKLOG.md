# Asset-Backed Template Backlog — the consolidated, gap-weighted slate

**Author:** Anton + Claude (consolidation 2026-06-09)
**Status:** Living backlog. Consolidates the 7 per-category proposal files
(`asset_templates_{robots,conveyors,containers,environments,sensors,warehouse,workpieces}.md`)
into **one deduplicated, tier-ordered, gap-marked slate**.
**Cross-references:** `CANONICAL_TAXONOMY.md` (the defensibility gate + the T1→T7 / 7-axis model).
Every row here is held to that document's §1 gate; the `defends:` one-liner is the gate-test-5 artifact.

> **How to read a row.** Each template is keyed by its **proposal id** (RG-/CV-/CT-/WP-/WH-/ENV-/CP-NEW-)
> so it stays traceable to the source audit. It is then placed on the **unified complexity tier** (T1→T7
> from `CANONICAL_TAXONOMY §2 A6`, NOT the per-category A/B/C label, which I restate as a *buildability*
> grade), tagged with the **measured gap(s) it fills** (suction · 3-finger · reorient · mobile-manip ·
> real-asset · insertion · perception · multi-robot · feed-dynamics · compose) or **SATURATED**, and given a
> **`defends:` one-liner** — the single distinct capability it proves and the contrast it is NOT a clone of.

---

## 0. The two grading scales (don't conflate them)

The source files mixed two orthogonal things into one "tier" column. This backlog separates them:

| Scale | Meaning | Values |
|---|---|---|
| **Complexity tier** (`A6`, the taxonomy axis) | *how hard the scene is* — what the spine must grade | **T1** single-obj · **T2** multi-obj/placement-math · **T3** feed-dynamics · **T4** perception-gated · **T5** multi-robot-cell · **T6** real-asset-cell · **T7** multi-cell/composed |
| **Buildability grade** (the per-category A/B/C/GO label) | *can we ship it today* — backend + tool readiness | **GO** (backend + tools exist, build now) · **SPLINE** (only the robot-agnostic lane, lower fidelity) · **BLOCKED** (named tool/controller/config missing) |

A row can be **T6 (hard scene) but GO (shippable)** — e.g. a real-mesh KLT pick. Or **T1 (trivial scene)
but BLOCKED** — e.g. an Allegro power grasp (single object, but no multi-finger controller). Keeping the
two apart is what makes the backlog actionable.

---

## 1. Deduplication ledger (what collapsed, and why)

70 proposal rows in → **66 distinct templates** out. Four merges + the cross-category overlaps:

| Kept | Absorbed / cross-linked | Rationale (taxonomy gate-test-4a: identical capability-tuple) |
|---|---|---|
| **WP-10** (Allegro × Rubik power-wrap) | **RG-C05** (Allegro power grasp, asset-only) | Same distinct capability = *first multi-finger grasp the spine grades*. WP-10 binds it to a real prop; RG-C05 is the bare-asset duplicate. Keep WP-10, cross-link RG-C05. |
| **WH-MM-05** (nova_carter + arm rack pick) | **RG-C01** (Ridgeback+Franka), **RG-C02** (Ridgeback+UR5) | All three are blocked on the **same** missing `setup_amr_with_manipulator` (bind arm to moving base as one TF tree). One BLOCKED base proves the gap; the other two are robot-skin variants of it. Keep WH-MM-05 as the canonical mobile-manip blocker; RG-C01/02 are its asset-variants once the tool lands. |
| **RG-C07** (Robotiq jaw on UR10) | — (kept, distinct) | Distinct gap = `mount_eoat/attach_gripper` weld-onto-tool0 + mimic-joint wiring. NOT the same as the AMR or multi-finger blockers. |
| **RG-C03** (Spot+arm), **RG-C04** (H1 bimanual) | — (kept, distinct) | Spot = legged-base↔arm coupling; H1 = curobo-config-locked-to-G1. Different blockers from each other and from WH-MM-05. |

Cross-category **non-merges** (kept separate — distinct graded axis each):
- **RG-A04** (UR10 short-suction *palletize*) vs **RG-A05** (UR10 long-suction *depalletize*) vs **CT-03**
  (UR10 suction *bin-pick from real tote*) vs **CV-06** (UR10 suction off a *gravity-fed belt*): all suction,
  but the **task axis (A3)** and **feed axis (A4)** differ — palletize-grid vs depalletize-layer vs
  random-pose-bin-pick vs gravity+convey. Each moves a different axis; all four survive the gate.
- **WP-07/08/09** (three insertion strategies: helical-screw / spiral-search / torque-gated-seat): the
  **success-signal sub-type** differs (thread-engagement vs peg-seat vs torque-curve). Taxonomy §4 treats a
  changed success-signal as a new base, so all three are bases, not variants of one.

---

## 2. THE SLATE — by complexity tier (T1 → T7)

Legend: **GAP** column = the measured hole(s) it fills (`CANONICAL_TAXONOMY §2`); **SATURATED** = at the
already-green center (keep ≤1 as REF). **Grade** = GO / SPLINE / BLOCKED (buildability today).

---

### T1 — single robot, single object (the floor)

| id | template | robot · gripper | gap filled | grade | defends: (distinct capability vs contrast) |
|---|---|---|---|---|---|
| RG-A07 | Cobotta Pro 900 tabletop pick-place | Cobotta · parallel | **robot-family** (native, no-curobo) | GO | first **native-controller non-Franka** arm graded; contrast RG-A01 (Franka native) — proves the bundled `CobottaPro900` PPC path |
| RG-B01 | Kinova Gen3 spline pick-place | Kinova Gen3 · parallel | **robot-family** (spline-only) | SPLINE | first **7-DOF spline-lane** arm with the franka-fallback footgun explicitly avoided; contrast any curobo arm |
| RG-B02 | Fanuc CRX-10iA/L tabletop pick | Fanuc CRX · parallel | robot-family | SPLINE | first **cobot cautious-waypoint** spline fit; contrast RG-B01 (industrial-DOF) — same lane, new articulation |
| RG-B04 | xArm7 + xArm gripper pick | xArm7 · parallel(override) | robot-family + **EOAT-override** | SPLINE | first `create_gripper(parallel_jaw)` with **non-panda DOF-name override**; contrast built-in-hand arms |
| RG-B05 | Lite6 compact-cell pick | Lite6 · parallel | robot-family (**fixed_poses**) | SPLINE | first **timer-driven `fixed_poses` replay** (no IK plan); contrast spline — proves the dumbest deterministic lane |
| RG-B07 | Franka FR3 tabletop pick | FR3 · parallel | robot-family (**kinematics-drift**) | SPLINE | proves **FR3 ≠ Panda kinematics** must NOT silently fall back to franka curobo; verify-before-trust canary |
| WP-01 | YCB tomato-soup-can bin pick | Franka · parallel | **real-asset** (graspable cylinder) | GO | first **real-mesh cylinder** antipodal-tangent grasp graded by PhysX contact; contrast cube-proxy picks |
| WP-02 | YCB cracker-box repack | Franka · parallel | **real-asset** (flat-faced box) | GO | first **real-mesh flat-face** top-down grasp; closest real analogue to a cube → lowest honest-eyes risk |
| RG-C05↳WP-10 | *(merged into WP-10, T1)* | Allegro · dexterous | 3-finger / dexterous | BLOCKED | see WP-10 |
| WP-10 | Allegro 4-finger Rubik envelope grasp | Allegro · dexterous-hand | **3-finger/dexterous** | BLOCKED | first **multi-finger power-wrap** the spine would grade; needs a multi-finger controller (today only `set_joint_targets` DOF-replay). Contrast every parallel-jaw pick |
| RG-C05 | Allegro power grasp (bare asset) | Allegro · dexterous | 3-finger/dexterous | BLOCKED | *(absorbed by WP-10 — same capability-tuple)* |
| RG-C07 | Robotiq 2F/Hand-E on UR10 | UR10 · Robotiq jaw | **EOAT-mount tool** | BLOCKED | first **`mount_eoat`/`attach_gripper`** weld-onto-tool0 + mimic-joint wiring; contrast built-in-hand arms |

---

### T2 — single robot, multi-object (placement math / routing)

| id | template | robot · gripper | gap filled | grade | defends: |
|---|---|---|---|---|---|
| RG-A02 | Franka 3-bin colour sort | Franka · parallel | SATURATED (sort REF) | GO | the **sort reference** — `drop_targets` routing to 3 bins; extends CP-13; keep as REF, variants off it |
| RG-A03 | Franka 2-cube column stack | Franka · parallel | SATURATED (stack REF) | GO | the **stack reference** — per-layer z `drop_targets`; *is* CP-13; REF only |
| RG-A04 | UR10 short-suction palletize | UR10 · short-suction | **suction × palletize** | GO | first **suction palletize-grid** (cup-frame matched); mirrors NVIDIA ur10_bin_stacking; contrast parallel-jaw palletize |
| RG-A05 | UR10 long-suction deep-bin depalletize | UR10 · long-suction | **suction × depalletize** | GO | first **long-suction layer-peel** from a deep bin; auto-selects Long_Suction variant; contrast RG-A04 (build-up vs tear-down) |
| RG-A06 | UR10e suction machine-tend load/unload | UR10e · short-suction | suction × **tend** | GO | first **suction tray→fixture→retrieve** tend loop; contrast pick-place — proves the fixture round-trip |
| WP-03 | Foam-brick + wood-block material sort | Franka · parallel | **real-asset** routed sort | GO | first **real mass/friction-difference** routed sort (`apply_physics_material` per part); contrast same-mass cube sort |
| CT-01 | Palletize-to-EUR-pallet (single-SKU brick) | Franka · parallel | **real-asset** palletize | GO | first **real EUR pallet** brick-interlock (`gripper_rotation=90`/layer, pallet as obstacle); contrast cube-grid palletize |
| CT-02 | KLT bin-fill (place INTO real KLT) | Franka · parallel | **real-asset** (interior-floor anchor) | GO | first `compute_stack_placement anchor=inside_floor` against a **real concave container**; contrast place-on-top |
| CT-04 | Kitting tray from multi-container source | Franka · parallel | **real-asset** kitting | GO | first **recipe/`track_slot_occupancy`-gated kit** routing 3 SKUs into a `create_kit_tray`; contrast undifferentiated bin-fill |
| CT-05 | Mixed-SKU palletize (rect-footprint nesting) | Franka · parallel | **real-asset** + **tool-gap** | SPLINE | exposes the `compute_stack_placement` gap — needs `item_footprint=[w,d]` per SKU for honest rectangular nesting; contrast uniform-box CT-01 |
| CT-06 | Crate-to-crate transfer / re-pack | UR10 · suction | **real-asset** (baseline) | GO | simplest **real-bbox→real-bbox** category flow; the asset-bridge baseline; contrast cube-proxy transfer |
| WP-04 | Mug grasp-by-handle | Franka · parallel | **grasp-sampler** (irregular) | BLOCKED | first **no-centroid-antipodal-pair** grasp → primary driver for a real geometry-aware grasp sampler; contrast box/cylinder grasps |
| WP-05 | Banana / curved YCB pick | Franka · parallel | grasp-sampler (curved) | BLOCKED | canonical **no-parallel-face** curved part; same sampler dependency as WP-04, different geometry class |
| WP-06 | Flip_Stack corner-bracket pick | Franka · parallel | grasp-sampler (L-shape) | BLOCKED | **grasp-a-leg-not-the-centroid** L-bracket; third irregular-geometry driver for the sampler |

---

### T3 — feed dynamics (the object moves / arrives)

| id | template | robot · gripper | gap filled | grade | defends: |
|---|---|---|---|---|---|
| RG-A01 | Franka conveyor pick-and-place | Franka · parallel | SATURATED (conveyor REF) | GO | the **conveyor + proximity-gate reference** (proven CP-* pattern); REF, variants off it |
| CV-01 | Static staging belt, fixed-station pick | Franka · parallel | **real-asset** (belt wiring) | GO | first **real ConveyorBelt prop** as a static prop — isolates real-asset reference + collision-strip wiring from belt motion; contrast primitive-ground baseline |
| CV-02 | Moving-belt pick, sensor-gated belt pause | Franka · parallel | **real-asset** + feed-dynamics | GO | CP-01 behaviour on the **real belt prop** with `add_proximity_sensor` pausing via `belt_path`; contrast static CV-01 |
| RG-B03 | Yaskawa NEX10 sensor-gated machine tend | Yaskawa · parallel | **PLC-mimic** feed | SPLINE | first **`sensor_gated` PLC-mimic** (photoelectric belt-pause + pre-taught poses); contrast curobo-planned tend |
| RG-B06 | Techman TM12 vision-guided sort | Techman · parallel | robot-family + perception | SPLINE | first **spline + SDG-camera-over-belt** sort on a new arm; contrast colour-attr sort (adds a camera source) |
| CV-06 | Gravity dispenser onto moving belt | UR10 · suction | **feed-dynamics** (gravity→belt) | GO | first **gravity-dispense → belt-transport → pick** chain (NVIDIA #25 lineage on a real belt); contrast direct-belt pick |
| CV-05 | Rotary index-table feed + pick | Franka · parallel | **feed-dynamics** (rotary) | SPLINE | first **continuous rotary-index** feed (`create_rotary_table`, proximity-gated); contrast linear-belt feed |
| CV-03 | Two-belt right-angle handoff | Franka · parallel | **feed-dynamics** (multi-belt) | SPLINE | first **two independent belt drives** + arm cross-transfer (diverter stand-in); contrast single-belt |
| CV-04 | Lane-merge infeed (two belts → one) | none / opt. Franka | feed-dynamics + **tool-gap** | SPLINE | exposes the missing **merge-gate tool**; lane-interleave by physics alone → proximity count; weak-gate (no robot) per §gate-test-2 — keep as feed-dynamics canary |

---

### T4 — perception-gated (a sensor decides the route)

| id | template | robot · gripper | gap filled | grade | defends: |
|---|---|---|---|---|---|
| CP-NEW-vision-sort-samclip-local | Local SAM2+CLIP colour sort | Franka · parallel | **perception** (local closed-loop) | GO | first template proving the **on-disk SAM2+CLIP** routing oracle end-to-end (Gemini-quota-free); contrast cloud/colour-attr sort |
| CP-NEW-barcode-recirc-divert | Barcode divert + recirc no-read | Franka · parallel | **perception** (material/ID) + feed | GO | first **closed-loop no-read handling** — unread SKUs recirculate via `create_recirculation_loop` instead of falling through; contrast straight-belt fallthrough |
| CP-NEW-multicam-inspect-stereo | Multi-camera consensus inspect | Franka · parallel | **perception** (multi-cam AND-gate) | GO | first **two-viewport logical-AND** inspection (good AND good before PassBin); contrast single-cam inspect (cuts single-view false-accept) |
| CP-NEW-nir-barcode-dual-oracle | NIR-material × barcode-SKU sort | Franka · parallel | **perception** (dual-oracle fuse) | SPLINE | first **two non-vision oracles fused** into one routing key (material × SKU cross-product, NVIDIA #18 Recycling); contrast single-oracle divert |
| CP-NEW-ft-insertion-noisy-compliant | F/T peg insert + noise + admittance | Franka · parallel | **perception** (F/T) + **insertion** | BLOCKED-ish | first to exercise `add_force_torque_sensor` **noise_std/publish_topic** branches + **admittance** (not impedance) law; needs live insertion bridge; contrast plan-only insertion |

---

### T5 — multi-robot cell

| id | template | robot · gripper | gap filled | grade | defends: |
|---|---|---|---|---|---|
| RG-A09 | Dual UR10e shared-belt two-arm sort | 2× UR10e · parallel | **multi-robot** (mutex) | GO | first **per-cube-mutex shared-belt** 2-arm sort (CP-52 lesson); proves coordination not deadlock; contrast single-arm sort |
| RG-A08 | Unitree G1 bimanual pick-place | G1 humanoid · 2× hand | **robot-family** (bimanual) | GO | first **two-per-arm-curobo sequential bimanual** (`setup_bimanual_pick_place_controller`); contrast single-arm — G1-only tool |
| RG-C04 | Unitree H1 + hands bimanual | H1 humanoid · 2× hand | bimanual + **config-gap** | BLOCKED | first **H1** bimanual — BLOCKED: controller hard-locked to `unitree_g1.yml`, no H1 curobo branch; contrast RG-A08 (G1 has the config) |
| RG-C03 | Spot-with-arm mobile fetch | Spot quadruped + arm | **mobile-manip** (legged) | BLOCKED | first **legged-base↔arm coupling** — BLOCKED: no controller couples gait to arm; contrast wheeled mobile-manip |

---

### T6 — full work-cell on real assets

| id | template | robot · gripper | gap filled | grade | defends: |
|---|---|---|---|---|---|
| CT-03 | Bin-pick from real tote (suction) | UR10 · suction | **real-asset** + suction | GO | first **suction random-pose pick from a real tote** pick-volume (`get_bounding_box`); contrast cube-proxy bin-pick |
| CT-07 | Pack-station cartons + seal | Franka · parallel | **real-asset** + seal-phase | GO | first **arrange-then-seal/close** multi-phase on a real packing table; contrast place-only |
| WP-07 | M8 bolt → M8 nut threading | Franka · parallel | **insertion** (helical-screw) | BLOCKED | first **matched-thread helical-screw** insertion; success = thread-engagement curve; primary driver to make `setup_insertion_controller` live; contrast delivery-graded picks |
| WP-08 | Bearing-pin into bracket bore | Franka · parallel | **insertion** (spiral-search) | BLOCKED | first **peg-in-hole spiral-search** insertion; success = seat-depth; distinct success-signal from WP-07 |
| WP-09 | M16 loose→tight bolt seat | Franka · parallel | **insertion** (torque-gate) | BLOCKED | first **torque-gated seat** (helical descent + torque-gate contract); third distinct insertion success-signal |
| WP-12 | Flip a real part on a flip fixture | Franka · parallel | **reorient** (fixture) | BLOCKED | first **real flip-station asset** reorient (fixture interaction, not a wrist roll); drives `setup_reorient_controller`; contrast wrist-flip reorient |
| WP-11 | In-hand reorient (regrasp) Rubik | Allegro · dexterous | **reorient** + 3-finger | BLOCKED | first **finger-gaiting in-hand regrasp** — needs BOTH multi-finger controller AND a reorient tool; north-star, dual-blocked |
| RG-B08 | UR16e/UR20 heavy palletize | UR16e/20 · parallel | **robot-family** (no-config) | SPLINE | first **heavy-payload arm with no curobo config** — must spline with correct articulation, not auto-route to ur10; contrast ur10 palletize |
| WH-SHELF-01 | Shelf pick/place at a rack bay | fixed arm · parallel | **real-asset** (rack) | GO | first **rack-bay placement** via `compute_stack_placement` + `track_slot_occupancy` idle→filled gate (no native shelf tool); contrast bin placement |
| WH-RACK-02 | Rack replenish to fill-level | fixed arm · parallel | **real-asset** + occupancy-gate | GO | first **replenish-until-N** with `track_slot_occupancy` AS the gate; contrast fixed-count placement |
| WH-DOCK-03 | Dock depalletize (de-stack pile) | fixed arm · parallel | **real-asset** depalletize | GO | first **top-down layer-by-layer depalletize** via `get_bounding_box` layer-detect; RampLong_A1 as the dock; contrast palletize build-up |
| ENV-T6-01 | UR10 palletize cell in full_warehouse | UR10 · suction | **real-asset cell** (env-anchor) | GO | first **load-environment → derive-anchor → `activate_area` isolate-cell**; proves a cell drops into a real warehouse footprint |
| ENV-T6-02 | Franka kitting cell in multi-shelf warehouse | Franka · parallel | real-asset cell + **obstacle-reach** | GO | first **anchor-in-aisle with shelves as `diagnose_args.obstacles`**; proves obstacle-aware reach probe in a real env |
| ENV-T6-04 | Sim-to-real pick in Digital-Twin warehouse | Franka · parallel | real-asset cell + **HDRI-match** | GO | first **scanned-facility digital-twin + `set_environment_background` HDRI-match** anchor; the sim-to-real template |
| ENV-T6-06 | Office desk-side assist cell | Franka (small) · parallel | real-asset cell (non-industrial) | GO | first **non-warehouse env** anchor + `activate_area` isolate; proves the env-anchor flow generalizes off the factory floor |
| ENV-T6-07 | Simple-Room realistic tabletop | Franka · parallel | real-asset (backdrop swap) | GO | cheapest **env-as-backdrop swap** for the default grid (real walls/lighting); contrast primitive ground plane |

> **Wheeled-base & AMR-nav at T6** (graded as navigate, no arm): **WH-DOCK-03b** (forklift_b drive+fork-DOF),
> **WH-AMR-04** (nova_carter tote ferry, occupancy-map nav), **ENV-T6-03** (Carter aisle nav past forklift
> props), **ENV-T6-05** (Carter hospital corridor delivery). Each proves a distinct nav-graded capability
> (manual prismatic fork DOF · multi-cycle ferry · obstacle-aisle · corridor-navmesh) and is GO via existing
> `setup_nav_robot`/`navigate_to`/`generate_occupancy_map`.

---

### T7 — multi-cell / composed / mobile-manipulation frontier

| id | template | robot · gripper | gap filled | grade | defends: |
|---|---|---|---|---|---|
| ENV-T7-01 | North-Star 3-cell warehouse | UR10 + Franka + Carter | **compose** (multi-cell) | BLOCKED | first **3 canonicals → one physics scene** + AMR handoff + cross-cell integration gate (Phase-4 acceptance); the endgame |
| ENV-T7-02 | Scene-Blox tile-composed warehouse | Franka · parallel | **compose** (tile-build) | BLOCKED | first **bespoke env from a tile kit** (`add_usd_reference instanceable`) + per-tile cell-anchor; contrast load-prebuilt-env |
| ENV-T7-03 | Dual-aisle multi-AMR logistics | 2× Franka + 2× Carter | **compose** + **multi-robot-mutex** | BLOCKED | first **multi-robot mutex/handoff at env scale** (the CP-51/52/53/65 root, Phase 4.4); contrast single-cell mutex (RG-A09) |
| ENV-T7-04 | Replicated pick stations down an aisle | N× Franka/UR10 | **compose** (GridCloner) | SPLINE | first **`clone_envs` cell-replication + collision-filter** — lowest-new-infra bridge T6→T7; per-cell variation is the build gap |
| WH-MM-05 | Mobile-manipulator rack pick (AMR+arm) | Carter base + arm | **mobile-manip** | BLOCKED | first **arm bound to a moving base as one TF tree** — BLOCKED on `setup_amr_with_manipulator`; the absent A1 axis |
| RG-C01 | Ridgeback+Franka drive-to-station pick | Ridgeback+Franka | mobile-manip | BLOCKED | *(absorbed by WH-MM-05 — same `setup_amr_with_manipulator` blocker; becomes a base-skin variant once the tool lands)* |
| RG-C02 | Ridgeback+UR5 mobile sort | Ridgeback+UR5 | mobile-manip + **no-UR5-config** | BLOCKED | *(absorbed by WH-MM-05; additionally UR5 has no curobo config → spline arm)* |

---

## 3. Gap-fill scorecard (which frontiers this slate moves)

Mapped to `CANONICAL_TAXONOMY §2`'s measured-gap axes. **Count = distinct templates after dedup.**

| Frontier (measured gap) | GO-now (shippable) | SPLINE (lower-fidelity) | BLOCKED (needs tool/config/asset) | highest-value filler |
|---|---|---|---|---|
| **Suction** (A2, thin: 0 reorient) | RG-A04, RG-A05, RG-A06, CV-06, CT-03, CT-06, ENV-T6-01 (7) | — | — | **RG-A05** long-suction depalletize — first layer-peel, no suction sibling |
| **3-finger / dexterous** (A2, ≈absent) | — | — | WP-10, WP-11 (RG-C05 merged) | **WP-10** — the only thing forcing a multi-finger controller |
| **Reorient** (A3, thin: 0 suction/fixture) | — | — | WP-12, WP-11 | **WP-12** — first real flip-fixture, drives `setup_reorient_controller` |
| **Real-mesh asset** (A6 T6, ≈absent) | WP-01, WP-02, WP-03, CV-01, CV-02, CT-01/02/03/04/06/07, WH-SHELF-01, WH-RACK-02, WH-DOCK-03, ENV-T6-01/02/04/06/07 (19) | CT-05 | — | **WP-02** cracker-box — lowest honest-eyes risk real-mesh pilot (closest to a cube) |
| **Insertion / contact-rich** (A3, plan-only today) | — | — | WP-07, WP-08, WP-09, CP-NEW-ft-insertion (4) | **WP-08** spiral-search peg-in-hole — makes `setup_insertion_controller` live |
| **Perception closed-loop** (A5, thin) | CP-NEW-samclip, CP-NEW-barcode-recirc, CP-NEW-multicam (3) | CP-NEW-nir-barcode, RG-B06 | — | **CP-NEW-samclip** — first end-to-end on-disk SAM2+CLIP oracle, quota-free |
| **Mobile-manipulation** (A1, **absent**) | — | — | WH-MM-05 (RG-C01/02 merged), RG-C03 | **WH-MM-05** — the absent axis; one tool (`setup_amr_with_manipulator`) unblocks ≥3 |
| **Multi-robot cell** (A6 T5, sparse) | RG-A09 | — | ENV-T7-03 | **RG-A09** dual-UR10e — GO-now mutex base feeding the T7 multi-AMR scene |
| **Feed dynamics** (A4, gravity/rotary thin) | CV-06 | CV-03, CV-04, CV-05 | — | **CV-05** rotary-table — the non-linear-belt feed |
| **Compose / multi-cell** (A6 T7, **absent**) | — | ENV-T7-04 | ENV-T7-01, ENV-T7-02, ENV-T7-03 | **ENV-T7-01** North-Star — the corpus DoD endgame |
| **New robot-family** (A1) | RG-A07 (native) | RG-B01/02/04/05/07, RG-B08, RG-B03, RG-B06 | RG-A08 (G1, GO), RG-C04 (H1) | **RG-A07** Cobotta — only GO-now non-Franka native |
| **EOAT-mount** (A2 tool-gap) | — | — | RG-C07 | RG-C07 — `mount_eoat` weld-on path |
| **SATURATED** (keep ≤1 REF each) | RG-A01 (conveyor REF), RG-A02 (sort REF), RG-A03 (stack REF) | — | — | REF only — do NOT hand-author siblings; generate variants per §4 |

### What is SATURATED (do not expand by hand)
Three rows sit at the green Franka-parallel-jaw-cube center and are kept **only as the single reference**
per domain (`CANONICAL_TAXONOMY §2`, "ONE reference canonical per domain + procedural variants"):
**RG-A01** (conveyor), **RG-A02** (3-bin sort), **RG-A03** (2-cube stack). Their breadth (mass/colour/
n-object/bin-count) comes from `expand_variants.py`, never new hand-authored bases.

---

## 4. Build-order recommendation (gap-weight × readiness)

Ordered by `priority = gap_weight (§2) × buildability` — GO gap-fillers first, BLOCKED tool-drivers grouped
so one tool unblocks many.

1. **GO real-asset pilots (lowest risk, highest coverage):** WP-02 → WP-01 → CT-06 → CT-02 → CV-01.
   Proves the function gate grades a **real mesh** (the asset-bridge risk) before scaling the 19-strong real-asset wave.
2. **GO suction wave:** RG-A04 → RG-A05 → CT-03 → RG-A06 → CV-06. Fills the thin suction axis across palletize/depalletize/bin-pick/tend/gravity.
3. **GO perception wave:** CP-NEW-samclip → CP-NEW-multicam → CP-NEW-barcode-recirc. Lands the local closed-loop oracle.
4. **GO multi-robot + env-anchor:** RG-A09, then ENV-T6-01/02/04 (real-asset cells).
5. **Tool-driver cluster — `setup_insertion_controller` live:** WP-08 (spiral) + WP-07 (helical) + WP-09 (torque) + CP-NEW-ft-insertion. One bridge unblocks four.
6. **Tool-driver — grasp sampler:** WP-04/05/06 (handle/curved/L-bracket). One sampler unblocks three irregular-geometry picks.
7. **Tool-driver — `setup_reorient_controller`:** WP-12 (fixture flip), feeds WP-11.
8. **Tool-driver — multi-finger controller:** WP-10, feeds WP-11 (in-hand regrasp).
9. **Tool-driver — `setup_amr_with_manipulator`:** WH-MM-05, retroactively promotes RG-C01/C02.
10. **Compose endgame (gated on stable sub-stages):** ENV-T7-04 (clone bridge) → ENV-T7-01 (North-Star) → ENV-T7-03 (multi-AMR mutex) → ENV-T7-02 (tile-build).

---

## 5. Defensibility audit hook

Every row above carries its `defends:` line (gate-test-5). Before any base is committed to disk, assert the
machine-checkable invariant from `CANONICAL_TAXONOMY §6`: **no two `tier:base` templates share an
`axis_novelty` value-tuple.** The SATURATED trio (RG-A01/02/03) are the only `axis_novelty: {}` rows; every
other admitted row names a distinct axis value (suction · 3-finger · reorient · real-mesh · insertion-signal ·
perception-oracle · mobile-manip · compose). The four merges in §1 are exactly the gate-test-4a collisions
this audit would otherwise flag — resolved here, ahead of authoring.
