# SUPERVISED ACTION PLAYBOOK — path to 100% function gate (2026-06-03)

The autonomous session extracted all SAFE gate progress. What remains needs Anton's go/no-go because each either risks the 37
verified passes, needs supervised GPU-iteration (Warp), or needs assets. Each item below is pre-diagnosed + pre-designed so a
supervised session just decides + watches the verify. Tools: `~/.isaac_qa/run/scene_timeseries.py` (single-robot eyes),
`cp51_faithful.py` (dual/multi-robot observer: build+play+read ctrl + both-hands XYZ), `grade_play.py` (general item-vs-destination
grader for conveyor-only/multi-robot). VERIFY RULE: fresh-Kit-per-template (Kit degrades within a session), trust raw positions +
grip_audit (fj_ee_item/kinematic must be False), 3-run for stochastic (conveyor) ones, grip-FJ count stays 0.

## ✅ SOLVED THIS SESSION (no action needed)
- **Faithful SUCTION** (was the #1 ask): robot.py `_handle_surface_gripper` now uses NVIDIA's gantry RING of 4 D6 attachment points
  (was 1 over-stiffened = weld) + near-free rotation (stiffness 2000/±0.30rad, was 1e5/±0.02) + real Cylinder cup + hidden follower.
  CP-70 VERIFIED: grip_audit fj_ee_item=False/kinematic=False (real compliant grip), lifts+delivers err 1mm, compliant transit wobble,
  breakable@100N. Gated to suction → 37 Franka byte-identical. **The faithful-suction GRIP is done.** (Multi-cube DELIVERY is item C/D.)
- **10 templates moved to passing**: FIXED — CP-36 (staircase: shelf_top y=-0.6), CP-PRECISION-BIN (bin 0.18→0.07), CP-NEW-inspect-
  reject (sleepThreshold=0 on conveyor cubes). RECOVERED from stale-2026-05-18-scope — CP-15, CP-22, CP-28, CP-37, CP-NEW-controller-
  shootout-cp, CP-NEW-barcode-scanner-divert, CP-NEW-kit-prep-operator. (The "failing 46" scope is heavily STALE — re-verify before
  assuming fail.)

## A. CONVEYOR-SYNC (CP-12 2/3, CP-NEW-3station-oee 8/9, CP-71, inspect-reject reject-lane) — HIGH leverage
ROOT (verified, Anton GUI + code): the robot never CLAIMS the in-reach cube; the most-downstream cube rides past the pick zone while
the robot is busy and exits reach unpicked (which cube is STOCHASTIC). NOT belt-timing — a belt-hold-only patch was built+reverted
today (regression-safe CP-01/08/16 4/4 but ZERO benefit). EFFECTIVE FIX = `_cube_to_pick` (pick_place.py ~5489-5532) must prefer the
downstream in-reach cube that is about to EXIT reach, not strict closest-to-sensor + extend the per-tick belt-hold to single-robot.
RISK: rewrites the candidate-sort + reach-gate ALL 37 belt passes use for cadence → HIGH regression risk; single-robot hold also risks
deadlock (CP-01). VERIFY: CP-12→3/3, 3station→9/9; regression CP-01/04/08/16/19/50 + sorter/inspector/barcode each fresh-Kit, 3-run.
DECISION: Anton (claim-logic change to the shared belt path).

## B. DUAL-FRANKA HANDOFF (CP-51/52/53 + assembly/triple-arm relay) — deep shared-planner
ROOT (verified via cp51_faithful trajectory): FrankaA works; the targeting Z-bug is FIXED (handoff-sync gate — FrankaB reads the
settled cube). FrankaB then approaches DIAGONALLY (the shared MotionPlanner gives it a blended path: at mid-height the hand is at
y=-0.06 not over the cube y=-0.29) → the lateral sweep PUSHES the free cube before the grip closes → grips air. The `_plan_sub_step`
mitigation was tried + FAILED (the shared planner can't plan FrankaB's pinned-XY vertical column → sub-goals plan-fail). FIX = per-robot
MotionPlanner (key `_PLANNER_ATTR` by robot_path) so FrankaB gets its own refined plan → hits the Warp module-reuse CUDA-700 crash
(identical robot_cfg = same kernel hash) unless module='unique'/distinct-cfg + cuda_graph=False. RISK: touches shared cuRobo codegen
the 37 depend on + the Warp crash + GPU-iterative. VERIFY: cp51_faithful CP-51 → FrankaB hand stays over cube XY through descent +
delivers; regression a Franka single-robot pass. DECISION: Anton (Warp per-robot-planner, supervised GPU-iteration). Independent-station
multi-robot (3station) WORKS — only the HANDOFF needs this.

## C. UR10 ARM-DELIVERY (CP-69/71/75/79/81/85/86 ~the suction cluster minus CP-70) — deep reach
ROOT (verified ts + planfail): the suction GRIP is faithful (done). The ARM never completes pick→transit→drop — EE frozen at home;
cuRobo `_build_segments` returns None at seg 5/6 (drop-side goal y≈-0.5/z≈1.2 at the UR10 reach EDGE). CP-70 delivers (drop y=-0.3 in
reach); CP-69/75 (y=-0.4) just past. The high suction drop-lift (_drop_tip=0.45) is itself a bin-wall-collision fix → lowering re-breaks
it (genuine tension). LEVERS (supervised): (a) clear ~/.cache/warp PCH + restart Kit, re-confirm seg5/6 are real reach not stale-kernel
(memory: warp_cache_planfail masquerades); (b) move UR10 mount or bin-drop pose into the reachable manifold; (c) switch the UR10 suction
cluster to the builtin NVIDIA PickPlaceController (Warp-immune reach envelope). DECISION: Anton.

## D. SUCTION MULTI-CUBE (CP-83 2-cube) — cuRobo seed
ROOT: faithful grip done; rot2000 killed the catastrophic explosion (37000→1.5). Remaining = the documented seed-snap/S5-drop-from-
unwrapped-home plan-fail (seed-wrap+chained-fallback at pick_place.py:5830-5851 partially addresses). DECISION: Anton (cuRobo seed).

## E. CP-05 FLIP-STATION — delicate passive physics
ROOT: cube on its side must tip 90° upright on a passive FlipWall. Wall 0.5cm→rides over (no tip); 3cm→barriers (stops, no tip). The
tip window is narrow (~1-2.5cm + the right belt speed). Needs careful supervised flip-tuning (iterate wall height × belt speed);
likely stochastic. DECISION: Anton (or accept as a known-hard passive-flip).

## F. STACKING (CP-46 5/6, CP-NEW-brick-stacking 2/3, tray/heap/palletizer) — parallel-jaw precision
ROOT: cubes topple/fling during stacking (parallel-jaw grip precision on a stack). Same jaw-root family as the suction was. CP-15
(graduated tower) recovered, so some stacks work; the harder ones topple. DECISION: Anton (jaw-grip precision / stack-place tuning).

## G. ASSET-DEPENDENT (~12: isaaclab-arena-lego, robohive, maniskill, adaptive-3finger, label-applicator, dr-curriculum, roco-bimanual,
yrkesroll-*) — need Nucleus / RL-benchmark assets not present locally. Blocked on assets, not code.

## CURRENT GATE ESTIMATE
~75/112 passing (66 scope + ~9 net this session; scope is stale-low). Remaining ~37 = A–G above. A (conveyor-sync) + B (dual-Franka)
+ C (UR10 reach) are the biggest single levers but all risk-the-37/Warp/supervised. The autonomous-safe ceiling is reached.
