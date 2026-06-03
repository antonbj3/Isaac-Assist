# === 2026-06-03 OVERNIGHT SESSION SUMMARY (prepended; the 2026-06-02 "vein exhausted" below is PARTLY REFUTED) ===
The autonomous vein was NOT exhausted: this session added ~6 genuinely-new passes + pruned the gate + made a strategic pivot.

NEW/RECOVERED PASSES (verified fresh, raw positions): CP-47 (eyes color-route fix 2/2), CP-19 (spawn-pack 6/6), CP-29 (drop_target
revert 1/1), CP-61 (3/3 stacked), CP-50 (mid-reach conveyor 4/4), CP-23 (2x2 grid 4/4), CP-82 (2/2), CP-NEW-sorter-color-3lane
(9-cube routed), CP-NEW-yrkesroll-inspector-reject-divert (4/4), CP-NEW-barcode-scanner-divert (6 items routed). The HIGH-LEVERAGE
lever was the EYES color-route fix (parses destination_map/*_destination -> per-cube color-bin grading) — it recovered the whole
color-sort cluster from grader false-negatives.

GATE PRUNED (Anton-approved): 9 indefensible templates archived to workspace/templates/_retired/ (CP-06/40/72/74 controller-clones,
CP-11 redundant, CP-39 api-form, CP-62 dead-scaffold, CP-78 probe, CP-NEW-multi-cam). Eligible 121 -> 112.

DOMINANT REMAINING BLOCKER = CONVEYOR-SYNC RIDE-OFF (structural, ~90% of gate is conveyor): items cross the narrow sensor zone while
the robot is busy -> ride off unclaimed (CP-12 2/3, inspect-reject 3/5, nir-material 1/6, palletizer-mixed-sku 0/6). NO reliable
per-template fix (mid-reach helped only tight layouts; static-respawn HANGS). Needs a HANDLER fix (claim-window / belt-index) =
Anton's conveyor-strategy decision. See docs/notes/EXPANSION_DIRECTION_PLAN.md (the full strategic pivot: close-the-LLM-diagnose-
loop > toolify-the-body > prune(done) > consistent-mall > ~200 expansion; lever = correct-data-reading > vision).

ANTON ACTION-LIST (unchanged clusters still need you): UR10-vacuum (GUI, SurfaceGripper-across-reset), dual-Franka (deep cuRobo),
belt CP-12/15 (values: shrink vs match-gripper), CP-NEW-conveyor-merge-vision-priority (GPU-blocked by parked side-task).
=== END SESSION SUMMARY ===

# Function-gate → 100%: what each cluster needs (for Anton's supervised/GUI time)

State as of 2026-06-02 ~02:45 (autonomous run). The **autonomous gate-win vein is exhausted** — every remaining failing
cluster needs GUI inspection, a values-decision, or deep supervised work. This doc maps each lever to the exact Anton-action
that unblocks it, ordered by leverage. robot.py is a clean baseline (grip-FJ=0, FixedJoint.Define=1, all session scaffolds reverted).

**DEFINITIVE HONEST BASELINE (fresh-confirmed, by per-cube position + honest_pass; deliv/fails IGNORED — they lie): ~39 full passes.**
- CP-NN (33): 01,02,03,04,06,08,09,13,14,16,17,18,21,22,23,24,26,31,32,33,34,37,38,39,40,41,42,45,49,53,54,62,77
- CP-NEW (4): cad-revision-drift, controller-shootout-cp, conveyor-recirculation-overflow, sorter-color-3lane · CP-PRECISION (2): 3CUBE, BIN
- ~19 re-confirmed fresh this run; borderline: CP-08 (4/4 / 3/4), CP-14 (dual-Franka 1-2/2). **Zero new autonomous passes found** beyond this.
- Each remaining template (the path to 100% below) is GUI-blocked / gaming-decision / genuine-hard. Gate moves with Anton.
- META: a fresh-Kit re-verify is the ONLY trustworthy measurement (batch sweeps degrade → false-negatives; controller deliv/fails lie).

## 1. UR10 vacuum cluster (~15 templates: CP-69/70/71/72/73/74/78–86) — BIGGEST lever
**Breakthrough this session:** the IsaacSurfaceGripper **works headless** — `~/.isaac_qa/run/minimal_sg.py` grips + LIFTS a
cube (refutes the old "engine-blocked" verdict). Reach is solved, the suction raycast hits Cube_1, forwardAxis=Z — all fine.
**The blocker is a CP-70-BUILD artifact:** the SG grips in every *bare* scene (incl. World+flatcache, conveyor, articulation,
SG-nested) but never in the full execute_template_canonical build — even with the cuRobo controller subs+state cleared and a
static free cone at the cube. Leading hypothesis: the **SurfaceGripperManager loses the SG's grip-detection registration
across the build's multiple play/stop/reset cycles** (settle + controller setup).
**ANTON / GUI ACTION (10 min):** Load CP-70 in GUI; let the arm reach the cube; manually Close the SG with the cone at the
cube; inspect whether the SurfaceGripperManager is ticking findObjectsToGrip (vs the bare `minimal_sg.py` which grips). If
it's a registration-across-reset issue → re-register the SG after the final reset (or author it after settle). 
**Then apply the proven recipe** (`docs/notes/CP70_GUI_SESSION_PLAN.md` + `~/.isaac_qa/robot.py.scaffold_freecone`): free cone
(collider+disableGravity) + kinematic follower driven to FK ee-pose each prestep + build-time SG; grip-signal = cube-follows-
cone (NOT `isaac:grippedObjects`, which is unreliable/empty even during a real grip). Unblocks ~15 templates.

## 2. Dual-Franka cluster (~9: CP-14/51/52/53/65/67/76 + assembly-4robot/triple-arm) — 2nd lever
**State (ledger):** CUDA-700 concurrency crash FIXED (gated planning-serialization lock). CP-53 passes 3/3; CP-14 1-2/2. The
remaining blocker is **FrankaB's grasp/transport on the 2nd robot** — FrankaB's hand stalls ~0.35m short of the cube
(CP-51), NOT pinnable by position probes (cuRobo IK internals / possible FrankaA interference). Shared MotionPlanner
(franka.yml+arm_scope, not per-robot-path). 6 fixes tried; firmly deferred to supervised.
**ANTON / GUI ACTION:** watch FrankaB's actual motion live, comparing **CP-51 (fails, hand stalls 1.15)** vs **CP-53 (works,
hand→0.95)** — the cause is in cuRobo's plan for FrankaB. Likely fix = per-robot-path planner instances (deep cuRobo change,
regression-gate CP-09/53).

## 3. Belt CP-12 / CP-15 — needs a VALUES DECISION from Anton (not a code fix)
**Finding (scene-data confirmed):** these spawn cubes of **5cm / 8cm / 10cm**, but the Franka parallel gripper opens ~8cm.
Cube_3 (10cm) is **physically ungraspable**; Cube_2 (8cm) is at the limit. So "1/3" is the *physical maximum* for these
templates — not a handler bug. (Verified: Cube_3 never lifts — z constant — the gripper can't close on it.)
**ANTON DECISION:** is the multi-size-cube the *point* of the task (then the robot/gripper should match), or are the sizes
incidental to a "transport 3 cubes" task (then shrinking the 10cm/8cm cubes to ≤7cm is a legit template correction)?
Shrinking-to-pass is borderline gaming per the no-fusk rule → your call. If legit → trivial template edit unlocks CP-12/15.

## 4. Other belt partials (CP-11/27/30/36) + placement-planning (CP-10/20/30/43/44/50/66)
Heterogeneous, per-template (NOT a single cluster fix): CP-30 is a cuRobo PLACE-planning fail (plan_fails=12), not ride-off;
others vary. The belt-pause was tried+reverted twice as ineffective (real cause is post-claim grip/timing, not pre-claim
ride-off). Supervised, per-template RCA. Belt-pause IS active even single-robot (cubes don't ride off in scene-data) —
so "ride-off" framing in older notes is superseded.

## 5. Genuine-hard CP-NEW drafts (dispenser/heap/sheet/grasp-hard/timeout, ~140)
Per-template deep work, low yield (synthesis). Many need NVIDIA Nucleus assets. Out of scope for the 100% baseline push.

## Floor protection
The 37+7 are Franka friction-grip / builtin, zero EE↔cube FixedJoints. A fresh re-verify of anchors (CP-01/09/14/53) + a
position-survey for CP-54-class false-negatives is running (`~/.isaac_qa/run/reverify_baseline_survey.log`). robot.py is the
exact pre-session baseline (no landed changes; all probes were runtime-only), so no regression is expected — confirming.

## Bottom line
The two GUI levers (UR10 ~15 + dual-Franka ~9 = ~24 templates) are the real path to ≫37. Both are now precisely scoped for a
fast supervised close. The autonomous contribution is maximized; the gate number moves when Anton runs the GUI sessions.
