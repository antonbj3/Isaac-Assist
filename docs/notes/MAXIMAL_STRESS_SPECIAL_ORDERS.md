# Maximal-stress special-orders (the gotcha battery)

Anton's directive (2026-06-21, going to bed): "tänk på hur du formulerar specialbeställningar så de stresstestar
MAXIMALT." The adversarial customer was promised "infinite capacity" and now tries to break it with demanding,
interacting, edge-probing orders. Each order below stresses one or more dimensions MAXIMALLY and the constraints
INTERACT (the system must reason about the interaction, not check each in isolation).

## What makes an order maximally stress-testing
1. **Physical feasibility** — the gripper must ACTUALLY hold the object (suction can't seal a wet/oily/porous face;
   magnetic needs ferrous; a jaw needs graspable width). Not asserted — grounded.
2. **Robot selection** — the robot must ACTUALLY lift (payload) and reach (envelope). 9 kg defeats a Franka (3 kg);
   1.6 m defeats every arm.
3. **Flow expressibility** — routing the catalog may not express (branch to distinct STATIONS = a Y-split the linear
   chains don't provide; route by an un-sensable attribute like shipping-destination).
4. **Geometric understanding** — fit, clearance, tight-pack neighbor-collision, upright vs collection placement.
5. **Vagueness → clarification** — under-specified orders must trigger ASK + variable-capture, not a silent guess.
6. **Composition complexity** — multi-stage, multi-robot, simultaneous; the real multiplier.
7. **Adversarial trickery** — looks feasible but isn't; exploits an assumption (round object "just pick it"; a height
   that reads as a normal stack).
8. **Scale / throughput** — 60/min on one arm is not feasible; the honest answer is a rate-limit or multi-cell.

The system's honest responses are three: **BUILD** (compose + scene_eyes-verify), **EXPLAIN** (grounded-infeasible +
the fix), **ASK** (capture the missing variables). A "yes" to an impossible order is the failure mode.

## The battery (each = a gotcha; → the gap it reveals / the expected honest response)

| # | Special-order (adversarial) | Stresses | Honest response | Gap it reveals |
|---|---|---|---|---|
| 1 | "Pick a 9 kg cast-iron block off a pallet and stack three of them." | payload + robot-select + stack | BUILD on **UR10** (10 kg; Franka 3 kg can't) | **UR10:stack/column** (UR10 has no stack block) |
| 2 | "Vacuum-pick a slightly oily 2 kg metal part off the belt, sort by barcode." | gripper-object (oily→suction risk) + conveyor + barcode | EXPLAIN suction-seal-risk on oily → suggest jaw; else BUILD | UR10:barcode-sort if heavy |
| 3 | "Stack steel plates into a column exactly 1.6 m tall." | reach (1.6 m ≫ UR10 1.3 m, Franka 0.855 m) | EXPLAIN infeasible — no single arm reaches 1.6 m (diagnose grounds this) | — (correctly impossible) |
| 4 | "Over 1.5 kg → heavy-duty palletizer station; else → inspection station." | branching flow (weight→2 distinct STATIONS) | EXPLAIN: sortable by weight BUT branch-to-stations = a Y-split the LINEAR chains don't provide | **branching/Y-split chain** |
| 5 | "Set up a packaging line." (deliberately vague) | vagueness | ASK: what object/packaging/robot/destinations/throughput? | clarification/variable-capture |
| 6 | "25 boxes in a tight 5×5 grid, 2 cm spacing, all perfectly upright." | tight-pack geometry | BUILD but warn marginal; or EXPLAIN tight-pack topple-risk | **dense-grid upright** (CP-20/25 PARTIAL) |
| 7 | "Place a soup can standing UPRIGHT on a shelf." | round grasp + upright place | EXPLAIN collection-OK but upright needs descend-to-place | **round-object upright** (CP-YCB-02 collection-only) |
| 8 | "Conveyor → vision-divert defects → kit good parts → palletize, 30/min." | 5-capability chain + throughput | BUILD the chain; EXPLAIN 30/min may exceed a single-arm cell → multi-cell | throughput grounding + chain |
| 9 | "UR10 hands a part to a Franka, who inserts it into a fixture." | cross-robot handoff + insertion | BUILD via **cross-Kit** chain (UR10+Franka one-process = PhysX corruption) | single-process UR10+Franka (blocked→cross-Kit) |
| 10 | "Place a 0.5 kg sphere precisely in a 6 cm cup." | round grasp + precision | EXPLAIN sphere grip-slip / roll | **round precision** (CP-43/44 PARTIAL) |
| 11 | "Lift a 600 kg pallet and move it to the loading dock." | payload (forklift) + mobile | BUILD lift (CP-FORK-01); EXPLAIN "move to dock" = mobile-nav | mobile forklift navigation |
| 12 | "Two robots work the same belt, alternating parts, no collisions." | multi-robot contention | BUILD (parallel cells verified ≤5) | — (covered, stress the limit) |
| 13 | "Route a flexible cable through three clips." | deformable + path | EXPLAIN deformable manipulation not covered | **deformable manipulation** |
| 14 | "Place a fragile glass beaker in a rack without breaking it." | fragile + force-control | EXPLAIN force-limited grasp not covered | **fragile/force-controlled grasp** |
| 15 | "Sort 100 mixed parts by material at 60/min, one robot." | material-sort + throughput + scale | BUILD material-sort; EXPLAIN 60/min single-arm infeasible | throughput limit |
| 16 | "Prove 'any cell': compose conveyor-feed → vision-inspect → 3-color-sort → palletize-good → reject-divert, all running together." | 5-stage chain, simultaneous | BUILD + scene_eyes-verify each stage delivers | the composition multiplier itself |

## Gap map → 48h work order (value-ordered: cheap promotes first, then genuine builds)
- **Robot-diversity promotes** (greppa-före-bygg, expand the composable set from already-verified blocks):
  UR10:conveyor-pick=CP-69 ✓ (done, cont.319nnn), UR10:color-sort←CP-82 (re-verifying), UR10:other←CP-86,
  UR10:stack/column (order #1 — needs a verified UR10 stacker; build if none).
- **Grounded-EXPLAIN already works** (this session's revival): reach #3, payload #1, gripper-object #2/#7,
  flow #4 — diagnose_scene_feasibility + the grounded reasoning ground these. The gotcha value here is the system
  saying the RIGHT honest "no/ask", verified.
- **Genuine BUILD gaps** (where it falls short — the real frontier): branching/Y-split chain #4, dense-grid
  upright #6, round-object upright #7, throughput-honest multi-cell #8/#15, deformable #13, fragile #14.
- **Cross-Kit composition** #9/#16 — the multiplier; chain robust blocks + scene_eyes-verify end-to-end.

Each gap, when worked: build/promote → scene_eyes RAW verify (never delivered-count alone) → commit. The order is
value: cheapest composable-breadth gains first, then the genuine "falls short" frontiers.
