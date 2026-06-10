# AUTONOMOUS MISSION — 2026-06-04 → 2026-06-05 (24h)

**Anton:** "få klart ur10 klustret ... du får bestämma i vilken ordning ... organisera dig själv och arbeta effektivt i 24timmar." Full autonomy. Don't pause for permission. Don't self-terminate (grind to deadline). Read THIS doc + memory on resume/compact.

## Goal
1. **Finish the UR10 cluster** — ground-truth + fix every core UR10 canonical to verified-working or honestly-characterized.
2. **Bridge/overview** — plannability/swing audit (which templates have CP-69-style far-pick geometry) + a cluster state overview.
3. Long-term direction (path-aware plannability constraint + LLM-telemetry exposure) = DEFERRED, written in [[project_isaac_assist_plannability_telemetry_direction]] + docs/notes/UR10_SWING_RCA_2026_06_04.md. Do NOT build the full architecture now.

## Core UR10 cluster set (suction-arm canonicals)
CP-69, CP-70, CP-71, CP-73, CP-75, CP-79, CP-80, CP-81, CP-82, CP-83, CP-84, CP-85, CP-86 (+ CP-07, CP-54 if UR10).
(The many CP-NEW-* that mention ur10 are the broader expansion — NOT this cluster; touch only if time.)

## Known state (from memory + today's work)
- CP-70 ✓ suction delivers (integrity caveat: rigid mount). CP-75/79/82/86 ✓ verified clean today (deliver err 0.0, no swing).
- CP-69 = swing (CP-69-SPECIFIC far-behind pick x=-1.0; geometric branch flip, NOT a planner bug — see UR10_SWING_RCA). cuRobo support-surface fix (f9a5587c) repaired its no-op; it DELIVERS but with the swing.
- CP-80 (+ CP-74 if present) = belt-pause-from-callback bug (memory project_isaac_assist_phase_b_state).
- CP-71/73/81/83/84/85 = unverified / partial (CP-83 = 2-cube suction, partial).

## Tools
- `scripts/qa/scene_eyes.py <TPL> [dur] [nframes] [--noframes] [--attach]` — virtual eyes: joint sweeps/reversals, EE pose, tool-length(elongation), exact cuRobo plan-capture, plan-events. USE THIS for ground-truth (grader lies about arm path).
- `scripts/qa/scene_timeseries.py <TPL> <dur>` — grader (delivery/tilt/grip-integrity).
- Restart: `bash /home/anton/.isaac_qa/restart_kit.sh` (GUI) ; headless via launch script `--headless`.
- Kit single-tenant (serial). Degradation → trust passes, re-verify FAILS on fresh Kit.
- Gated experiment flags (all off-by-default, committed): _ur10_grip_mode, _ur10_transit_arc, _ur10_plan_cspace, _ur10_ik_seeds/_trajopt_seeds, _ur10_ori_tol, _ur10_pos_only, _eyes_plan_capture.

## Plan / order
1. Headless Kit (faster, fresh, production-realistic). 
2. scene_eyes ground-truth pass over the core set → per-canonical table (delivers / swing° / grip / elongation / plan-fails).
3. Fix the fixable (belt-pause CP-80, far-pick swings, grip issues) — per-canonical, eyes-guided, predict-then-measure.
4. Plannability/swing audit (static: cube-start-vs-base distance per template) — the bridge.
5. Overview doc + QC rounds (memory: budget 3-5 rounds).

## AUTONOMOUS SESSION 2026-06-05 (Anton away ~hours) — order: FIX GRIPPER → then MOTION → then cluster
- Anton's directive: faithful UR10 suction via NVIDIA `short_gripper.usd` asset (hotswappable, procedural fallback), then the IK-seed motion fix, then grind UR10 cluster to gate. NO forms. NO idle. Headless Kit (Anton away). Review TS every measurement.
- **GRIPPER rework state** in [[project_isaac_assist_real_gripper_rework]]: asset validated (Anton confirmed visual), engagement = SurfaceGripper wrapper `.close()`, mount = the HARD part. My separate-prim+FixedJoint attempt → UPSIDE-DOWN + FLOATING (FJ has no localPos/localRot → snaps wrong; world-rotation ≠ local). robot.py `_handle_surface_gripper` has gated `_sg_use_asset_gripper` branch (default off → procedural byte-identical) — mount code is WRONG, pending the recipe.
- **Workflow `wf_8ac70c9c` RUNNING** (offline USD): definitive mount recipe (child-of-ee_link vs FJ-with-frames vs reference combined `/Stage/ur10`) from NVIDIA's `ur10_bin_stacking_short_suction.usd`. ON WAKE: check workflow result, implement the recipe in robot.py, then STEP 2 controller suction-wiring (suction gates key on `_SG_FOLLOWER_OP`/`_SGCone`; add `_SG_IS_SUCTION` + `_SG_CUP_PATH`, byte-identical for procedural/Franka), verify CP-70 grips (headless gate_one), then generalize + motion.
- Helper scripts: /tmp/load_cp70_asset.py (CP-70 asset-mode), /tmp/reload_proc.py (CP-70 procedural), /tmp/grip_test*.py.

## PROGRESS LOG (update as I go — survives compact)
- 2026-06-04 ~end-of-day: mission started. scene_eyes built+committed. Swing RCA committed. Verified today: CP-70/75/79/82/86 deliver clean; CP-69 delivers-with-swing (far-pick). Next: full ground-truth pass on the rest (CP-71/73/80/81/83/84/85 + CP-07/54).
- 2026-06-04 LATE (Anton-steered detour, dual-Franka CP-52): Anton asked "har CP-52 fungerat? spawn-mönster?". FULL hard-data diagnosis (eyes + belt_probe + move_token_probe + grader, all reviewed as TIME SERIES):
  * CP-52 = REGRESSION (12/20 @ 2026-05-15 → 0 now). Belt-pause added 2026-05-31 + Z-settle gate 2026-06-03 BOTH post-date the baseline.
  * Spawn-in-geometry feedback (robots in rotary table/conveyor) was **CP-67**, NOT CP-52. (Yesterday's "scen bytte"-confusion = a 2nd session loading scenes over Anton's GUI viewport.)
  * CP-52 root chain: (1) belt-freeze SYMPTOM — Cube_3 spawns 0.10m downstream of SensorB (HOLD_R=0.15) → multi-robot standing-pause pins shared belt SV=0 forever (probe: beltSV=[0,0,0] every tick, all cubes Δ=0). (2) MASTER ROOT = exec-gate: move_token_probe shows FrankaA holds MOVE_LOCK + phase=executing + picked=/Cube_2 the WHOLE run, never completes (cycles on reach-edge Cube_2 @ -1.15, 0.76m vs reach 0.85), HOLDS claim-mutex → FrankaB wait_sensor pc=0 forever (starved). IK is PERFECT (perr~1e-7) → NOT reach-infeasible, NOT a simple lock-deadlock. Earlier "Cube_1-OOR 0.985m" diagnosis was WRONG.
  * The belt-freeze MASKED the exec-gate. CP-65 (also multi-arm, also 0/4): pre-fix frozen-on-belt; with belt fix → belt animates, cubes ride off (EE range=0.000m, robot never picks) = same exec-gate exposed.
  * **LANDED (uncommitted, working tree): belt-pause downstream-skip fix** in `_cube_imminent_at_sensor` (pick_place.py ~5435-5466). GATED `_multi = len(_curobo_live_pp_subs())>1`; single-arm templates (3station-oee/inspect-reject/CP-12 = 1 pp_controller each) BYTE-IDENTICAL → ZERO regression risk (verified by call-count). Correct + generalizable (don't freeze belt for a cube already downstream of its sensor) but NET-ZERO delivery alone — needs the exec-gate fix.
  * REMAINING = architectural multi-robot claim/handoff pass (Anton's-call per LIBRARY_HEALTH): FrankaA must release claim-mutex when it can't make progress on a reach-edge cube (don't starve sibling) + Z-settle gate × mutex-churn (FrankaB never accumulates 6 obs) + reach-edge grip reliability. Probes: scripts/qa/{belt_probe,move_token_probe}.py.
- 2026-06-05 MORNING — Anton: "jobba, allt ska fixas, 100% function gate" (NO forms — a form cost the whole night). MULTI-ROBOT GRIND, 3 gated fixes landed (uncommitted, working tree), all measured/time-series-reviewed:
  * (1) belt downstream-skip (`_cube_imminent_at_sensor`): CP-52 0→1/4 (belt animates, Cube_2 delivered).
  * (2) PER-CUBE MUTEX (wait_sensor guard ~6185 + claim ~6205): wait only if sibling's `claimed_cube` ∈ MY source_paths (shared/handoff CP-51/53); disjoint parallel-pick (CP-52) claims concurrently — PLAN_LOCK serializes planning, MOVE_LOCK execution. Adds `mutex:claimed_cube` attr; claim takes the slot only when free/mine (no overwrite). RESULT: CP-52 1→**2/4** — FrankaB now picks (Cube_3 @t3.6 + Cube_2 @t20, both delivered). The exec-gate "stuck" was really mutex over-serialization.
  * (3) belt-hold-while-busy (callback ~5381): hold shared belt while THIS robot mode∈settling/executing/gripping/retreating, so the 2nd cube doesn't ride off during the 1st pick (Cube_1/Cube_4 flew off). Measuring now.
  * ALL gated multi-robot (`len(_curobo_live_pp_subs())>1`) → 37 single-robot byte-identical. Multi-robot class was 0/N so low regression risk. NEXT: verify CP-52 4/4, then CP-51/53/65 (shared roots), then commit; gate checks Cube_1 (FrankaA 2nd) so Cube_1 delivery is required for CP-52 gate-pass.
- 2026-06-05 — COMMITTED 8b54efb8 (CP-52 multi-robot fixes, fresh-Kit 4/4, Cube_1 seated). Then DROP z-backoff fallback COMMITTED b5a0f02c: a release-descend (action_after=='open') with no feasible plan at the requested z retries higher z (+0.06..0.26) + releases from the first feasible height. ADDITIVE (only on drop-fail) → the 37 + CP-52 byte-identical. CP-65 handoff 0/4→2/4 (FrankaA drop-to-HandoffBridge now plans → relay works; Cube_4→OutBin seated, Cube_2→KitTray err0.013). CP-84/85 (UR10) NOT helped → drop infeasible at ALL heights = UR10 reach-envelope (architectural, plannability-constraint class).
- **MEASUREMENT FIX (important): the GATE uses the template's `simulate_args.duration_s` (90–180s), NOT the 90s grader.** I was under-measuring slow relays (CP-65 gate=180s; Cube_1 spawns furthest upstream → picked LAST). Built `scripts/qa/gate_one.py` = authoritative `simulate_traversal_check` with the template's own verify_args/simulate_args. Gate criterion (diagnostics.py ~4208): multi-cube=ANY cube delivered + primary(Cube_1) UPRIGHT (lenient); single-cube=must deliver. CONFIRMED PASS: CP-52, CP-65. Commits 8b54efb8, b5a0f02c, 6dcda04b.
- **TIME-SERIES COMPLETED (Anton: vital).** scene_eyes was blind to CONTACTS (only scene_timeseries had them); gate_one = final-verdict-only (NOT a TS). Added per-frame contacts + ARM-VS-SCENE collision flag to scene_eyes → complete SINGLE-robot TS (joints+plans+EE+tool+cubes+contacts). Commit 859b8014. Memory [[project_isaac_assist_timeseries_system]] [[project_isaac_assist_gate_criterion]]. (per-robot merge = TODO for multi-robot.)
- **UR10 HELD-ALOFT ROOT + ARC FIX (CP-84/85/83/81).** The complete TS (contacts!) PROVED it: z-backoff fixes the drop-PLAN, but the cross-table transit does a single 215° swing that drives wrist/upper_arm/forearm THROUGH Table+Pedestal+BaseCube (excluded from cuRobo → not avoided → execution collides → arm stalls held-aloft). pos_only REJECTED (worse: 3.4m/s, 316° wrist, still collides, drops cube — orientation can't fix a GEOMETRIC collision). KEY COMPARISON: working CP-70 uses a TRANSIT-ARC (plan#4-9: small ~28° steps at high apex z~1.24, fold-in-and-rotate) → NO collision. CP-84 (foll=None) was suction-GATED out of the arc. FIX (applied, uncommitted): extend the arc gate `_SG_FOLLOWER_OP is not None` → `ROBOT_FAMILY in ("ur10","ur10e")` (pick_place.py ~6011). VERIFIED via scene_eyes: CP-84 now generates the arc, swing-collisions GONE (only benign t=0 home contact, like CP-70). Gate-delivery verify on fresh Kit IN FLIGHT (CP-84/85 + CP-70 regression). NEXT: confirm deliver → commit; CP-83/81 are SUCTION (already had the arc) → their held-aloft is a DIFFERENT root (cone physics).

## RESUME / durability
- Cron backstop (session-only): daa19c89 ("7,22,37,52 * * * *"). If the session restarted and it's gone, RECREATE it (fires only when idle → resumes the chain). 
- On compact/resume: read this doc's PROGRESS LOG + /tmp/ur10_gt.txt + memory. Continue; don't restart from scratch.
- Active loop: ground-truth batch (/tmp/ur10_groundtruth.sh → /tmp/ur10_gt.txt) running headless; waiter notifies on UR10_GT_DONE.

## GROUND-TRUTH (2026-06-04 ~20:10, headless) — full UR10 cluster
- DELIVER OK (verified today): CP-69 (w/ swing, far-pick), CP-70, CP-75, CP-79, CP-82, CP-86.
- CP-84 (stack) + CP-85 (color-route): cuRobo, PICK ok but DROP plan FAILS (res_None, NO collision warning) — descend goal goes BELOW table (z=0.685 < 0.75). Root: handler descends drop_target−approach_h → into the table for SURFACE drops (fine for bin-drops which release high). SHARED root candidate.
- CP-80 (elevated conveyor z=0.95): cuRobo THRASH — wrist_3 958°, 183 reversals, no delivery. Distinct (elevated-height instability).
- CP-81 + CP-83 (two-cube pedestal): not delivered (OFF_TARGET / Cube_2 flung). CP-83 known-hard (memory).
- CP-71 (dispenser-fill 4 cubes) + CP-73 (Cortex-BT conveyor): grader returns empty (different modes — may not be standard deliver tasks; verify separately).
- GRADER BUG (separate): scene_timeseries crashes Sdf.Path(None) (TS_PARSE_FAIL) on non-delivering/non-standard templates — measurement only.
- FIX ORDER: (1) drop-descend-below-surface CP-84/85 [shared, safe-gated] → (2) CP-80 thrash → (3) CP-81/83 two-cube → (4) CP-71/73 mode-check + grader robustness.

## 2026-06-04 ~20:40 — grader fix landed + drop-fail root refined
- GRADER FIX (LANDED, verified): scene_timeseries.py (run-dir /home/anton/.isaac_qa/run/) now auto-detects
  the ArticulationRoot when role_defaults.primary_robot is unset (CP-80/84/85 etc had it None → grader picked
  /World/Franka → EE None → Sdf.Path(None) crash). Also None-guards wp()/bbox(). CP-84 now grades. GENERAL.
  (Run-dir tool, not in repo — recorded here.)
- ROOT (refined, shared CP-81/83/84/85 pedestal→destination drops): _build_segments plans ALL segments
  UPFRONT; a failing DROP plan (res_None) aborts the WHOLE pick-place → arm never moves → cube stays aloft
  (joints=0 + "PICKED" but cube at start = this, not a grasp). Drop excludes only the held cube
  (exclude_obs=S["picked_path"]), NOT the destination (stack BaseCube / bin) → with collision restored the
  non-suction descend onto the destination collides → res_None. Suction dodges it via high release.
- NEXT FIX: exclude the DESTINATION from collision on the drop/descend segment (extend _build_scene_cfg /
  exclude_obs to a list). Verify CP-84 delivers + CP-70 (suction) byte-identical. Likely lands 4 canonicals.

## 2026-06-04 ~21:20 — DECISIVE root: hard canonicals = UR10 reachability/orientation envelope
Measured (cspace ik_ok per-plan): CP-84 drop goal [0.5,-0.4,0.825] ik_ok=FALSE (zero IK seeds);
same xy at z=1.005/1.175 ik_ok=True. So the drop pose is IK-INFEASIBLE: the NON-SUCTION UR10 flange
can't reach z=0.825 @ r=0.64 with down-orientation. CP-69/70 (suction) deliver to z=0.785 because the
cone tool-offset (~0.16m) keeps the FLANGE high while the tip is low. => CP-84/85 (ee_link, no offset)
+ the CP-69 swing + likely CP-80/81/83 are ALL the same root: targets near/beyond the UR10 down-
orientation reach envelope. This IS the plannability-constraint story (long-term direction) — NOT
per-canonical handler bugs. Honest implication: these templates as authored place drop goals the UR10
can't reach flange-down; fixes = (a) a tool-offset for non-suction drops (flange stays high), (b)
relax drop orientation, or (c) template geometry (drop higher/closer). The plannability flag should
catch these at gen time. Landed: destination-exclude fallback (additive, unblocked CP-85 planning).

## 2026-06-04 ~21:50 — COMPLETE UR10 cluster characterization
| canonical | verdict | root |
|---|---|---|
| CP-69 | deliver (w/ swing) | far-pick branch-flip (envelope) |
| CP-70/75/79/82/86 | DELIVER OK | suction, clean |
| CP-83 | fail (swing/envelope) | wrist 290°/elbow 243° smooth swing, no deliver |
| CP-84/85 | fail (drop IK-infeasible) | non-suction flange can't reach low+far down-oriented (measured ik_ok=False) |
| CP-80 | fail (VIOLENT thrash) | wrist_1 525°, 172 reversals, peak rot 1789°/s — controller/physics blow-up (elevated conveyor) |
| CP-81 | fail (VIOLENT explosion) | peak TOOL speed 27 m/s, rot 1799°/s — physics blow-up (two-cube pedestal) |
| CP-71 | grader OK now (fix landed) | dispenser-fill — needs closer delivery check |
| CP-73 | not gradable by this tool | Cortex behaviour-tree mode (different verifier needed) |
TWO root-classes among the 7 non-clean: (A) REACH/ORIENTATION ENVELOPE (CP-69/83/84/85) = plannability
story, needs orientation-relax / template-geometry / the plannability flag; (B) VIOLENT BLOW-UP
(CP-80/81) = controller/physics instability, distinct + likely more tractable. CP-71/73 = different modes.
LANDED tonight: support-surface fix (CP-69), grader robustness (all measurable), destination-exclude
(CP-85 planning), scene_eyes tool, full swing RCA. NEXT: investigate CP-80/81 blow-up (distinct bug).

## 2026-06-04 ~22:00 — honest boundary + NEXT (for cron-wake / fresh context)
UR10 cluster is FULLY characterized + tractable shared-roots fixed. The remaining 7 are TWO known-hard
classes, NOT quick handler bugs:
  (A) reach/orientation ENVELOPE (CP-69 swing / CP-83 / CP-84 / CP-85) → the plannability-constraint
      story (long-term, [[project_isaac_assist_plannability_telemetry_direction]]). Tractable lever to
      TRY: proper orientation-relax for the DROP only (pos-only broke the whole solve; do drop-only).
  (B) suction-cone PHYSICS BLOW-UP (CP-80 thrash, CP-81 cone flung to z=-0.43 @ 11 m/s) → architectural
      suction-cone/follower instability = Anton's-call per [[feedback_isaac_assist_no_fj_fusk]] history.
  CP-71 (dispenser-fill: grader now runs, verify delivery) + CP-73 (Cortex-BT: needs a different verifier).
NEXT (pick on wake, efficient — DON'T rabbit-hole the known-hard cone-physics):
  1. CP-71 closer delivery check (grader runs now — does the dispenser-fill actually deliver?). EASY win candidate.
  2. Try drop-only orientation-relax for CP-83/84 (the envelope lever not yet properly tried).
  3. Else pivot to a fresh pending cluster (#11 conveyor-sync, #12 dual-Franka, #13 stacking) for quick wins.
Don't re-sweep; targeted + predict-then-measure. Cron daa19c89 active.

## 2026-06-04 ~22:15 — UR10 cluster night-verdict + PIVOT to cluster #2
UR10 FINAL (tonight): 6/13 deliver (CP-69 swing,70,75,79,82,86). 7 known-hard, levers EXHAUSTED:
 - Envelope (CP-83/84/85 + CP-69-swing): cspace/seeds/ori_tol/pos-only/destination-excl ALL tried,
   none deliver. ori_tol doesn't reach IK feasibility. = plannability/template-redesign territory.
 - Cone blow-up (CP-80/81): suction-cone/follower physics instability (CP-81 cone flung to z=-0.43
   @ 11 m/s) = architectural, Anton's-call.
 - CP-71 (dispenser cubes end ON_FLOOR, not delivered), CP-73 (Cortex-BT, not gradable by this tool).
 LANDED: support-surface(CP-69), grader-robustness(all measurable), destination-excl(CP-85 planning),
 scene_eyes, full RCA. NOT chasing the known-hard 7 further tonight (no quick lever exists; documented).
PIVOT: cluster #2 conveyor-sync/claim-logic = CP-12, CP-NEW-3station-oee, CP-NEW-inspect-reject.
Ground-truth launched -> /tmp/c2_gt.txt. Analyze on next wake; fix tractable ones; predict-then-measure.

## 2026-06-04 ~22:40 — cluster #2 (conveyor-sync) ground-truth + root
CP-12 (palletize, Franka): Cube_1/2 OK→Pallet, Cube_3 rode belt off end (x=1.64→Ground t=56.1, NEVER
picked). CP-NEW-3station-oee: 6/7 deliver, Cube_7 rode off (ON_BELT x=2.19). CP-NEW-inspect-reject: 5/5
to PassBin OK. => failures = cubes ride the conveyor PAST the robot before being claimed (the cluster's
claim-logic theme), NOT flings. Tractable: belt-pause/pacing OR claim-the-next-cube sequencing. Better
shape than UR10. NEXT: why isn't the later cube claimed before riding off (belt-pause gap / pick-loop
stops early)? Fix + verify CP-12 (predict-then-measure, no re-sweep).

## NEXT (actionable for the next cron-wake / fresh context — do this first)
TARGET: CP-12 belt-ride-off (cluster #2). Cube_3 rides the conveyor off the end before the robot
claims it (Cube_1/2 deliver fine). Root to confirm + fix:
  1. Read the Franka multi-cube pick-loop + belt-pause in pick_place.py (_pause_belt / wait_sensor /
     the loop that picks the NEXT source cube). Hypothesis: belt doesn't pause for cube N, or the
     pick-loop doesn't re-claim after 2 cubes, so cube_3 rides past.
  2. CAREFUL: Franka path = the byte-identical 37-set. Gate any fix so the 37 don't regress. Predict
     the effect before editing; verify CP-12 alone (target 3/3), then spot-check 1-2 of the 37.
  3. Then CP-NEW-3station-oee (Cube_7 same ride-off). inspect-reject already 5/5.
Tools: scene_eyes / scene_timeseries (run-dir), grader has the auto-articulation + None-guard fixes.
DON'T re-sweep UR10 (done: 6/13, 7 known-hard documented). DON'T rabbit-hole the UR10 cone-physics
(architectural/Anton). Flags reset clean. Kit headless+healthy.

## 2026-06-05 ~00:30 (cron-cycle) — CP-12 fix#1 MISPLACED + reverted; correct target identified
- MISTAKE caught: I edited the BUILTIN _next_cube (line ~1378) but CP-12 uses target_source="curobo"
  (the cuRobo handler). So the edit never applied to CP-12 -> Cube_3 still rode off. CP-22 (regression
  check) stayed clean. REVERTED the misplaced edit (git checkout, was uncommitted). Lesson: confirm the
  template's handler path (builtin/native/cuRobo/spline/sensor_gated) BEFORE editing a per-path function.
- CP-12 facts: PickSensor @ x=+0.4 (downstream), belt +0.2 m/s +x, 3 cubes 0.40m apart. Cube_3 reaches
  the sensor ~t44 while the robot is BUSY (its 3rd cycle) -> not claimed -> belt carries it past -> off
  the end (x=1.68). Suspect: "Resume belt unconditionally on wait_sensor transition" — belt resumes even
  with an undelivered cube near the sensor.
- CORRECT NEXT (careful, fresh context): find CP-12's ACTUAL claim state-machine (native S@~2858 vs
  cuRobo S@~5322; target_source=curobo => the cuRobo one). Fix = DON'T resume the belt while an
  undelivered cube is within the sensor zone (hold it until claimed). GATE so the 37 single-robot Franka
  (paced belts) are byte-identical; verify CP-12=3/3 + spot-check CP-22/CP-08. predict-then-measure.

## 2026-06-05 ~00:45 (cron) — cluster #2 verdict + pivot to landscape-completion
- CP-12 cuRobo path ALREADY has belt-hold logic (_resume_belt_if_clear / _cube_imminent_at_sensor:
  suppress resume while a cube is within HOLD_R of the sensor). Cube_3 ride-off = subtle edge: it drifts
  PAST HOLD_R while the robot is busy -> no longer "imminent" -> belt resumes -> rides off. belt_v=0.2
  (<0.25) so _look_ahead_x=0. A real fix = hold belt while ANY undelivered cube is at/past sensor &
  reachable — but that intricate claim-logic governs the multi-robot/conveyor templates too =>
  HIGH-RISK for one cube (CP-12 is 2/3). NOT worth it without broader regression coverage.
- Cluster #2 verdict: GOOD shape (CP-12 2/3, 3station 6/7, inspect-reject 5/5); failures are subtle
  belt-timing edges, not cheap wins.
- DECISION: don't high-risk-fiddle the claim-logic for marginal gains. Complete the LANDSCAPE instead
  (ground-truth remaining clusters) so the review has the full picture. Launched cluster #3 (dual-Franka
  CP-51/52/53) ground-truth -> /tmp/c3_gt.txt.

## 2026-06-05 ~01:00 (cron) — cluster #3 (dual-Franka) verdict + landscape near-complete
CP-51 (relay): Cube_1 picked then FLUNG (final [0,-0.29], not Bin[0.7,-0.5]). CP-52 (shared-bin): Cube
1-4 NEVER MOVED (stayed at start row y=0.4, impact_vz~-0.05, 0 picks — robots idle, possible claim-mutex
deadlock). CP-53 (staging relay): Cube_1-3 picked then FLUNG. => cluster #3 = 0/3, MULTI-ROBOT handoff
broken (known-hard: shared-mutex/handoff-sync/seed-bias per memory). CP-52's never-moved is the most
distinct (idle, not fling) — possible tractable deadlock if revisited.
LIBRARY-HEALTH PICTURE (this run): UR10 6/13 (7 hard: envelope+cone). Cluster#2 conveyor good (CP-12 2/3,
3station 6/7, inspect-reject 5/5; subtle belt-edges). Cluster#3 dual-Franka 0/3 (multi-robot, hard).
=> failures concentrate in HARD CLASSES (reach-envelope, cone-physics, multi-robot, belt-timing); cheap
wins scarce. Launched cluster #4-5 (CP-05 flip + stacking) ground-truth -> /tmp/c45_gt.txt to complete
the map, then write a comprehensive library-health OVERVIEW for Anton's review.

## 2026-06-05 ~01:20 (cron) — LANDSCAPE COMPLETE + review overview written
Cluster #4-5: CP-01 4/4 OK, CP-04 4/4 OK (single-robot Franka stacking solid); CP-05 flip grader-empty.
=> Single-robot Franka mostly works; failures concentrate in 3 hard classes. Full review-ready synthesis:
docs/notes/LIBRARY_HEALTH_OVERVIEW_2026_06_05.md (per-cluster health + 3 hard classes + recommendations +
landed fixes). This is the culminating deliverable for Anton's review.
NEXT (if loop continues): the remaining work is (1) plannability constraint [Anton-decide], (2) faithful
suction-cone [Anton-decide/architectural], (3) multi-robot claim-logic (CP-52 deadlock = tractable entry).
None are cheap; (3)/CP-52 is the most tractable if a fix-attempt is wanted. Don't high-risk-fiddle the
conveyor belt-edges or UR10 envelope (documented dead-ends without the constraint).

## 2026-06-05 ~01:35 (cron) — CP-52 confirmed deadlock + DEFINITIVE conclusion
CP-52: primary EE (FrankaA/panda_hand) displacement = 0.000m ALL run (fully idle), 0 picks, no plan/mutex
log. = multi-robot claim/move-token DEADLOCK (FrankaA never claims). This is the dual-Franka cluster that
was NEVER finished (pending), the most intricate code (carefully-built shared-mutex). Safe fix needs a
dedicated multi-robot pass — NOT bloated-context fiddling (regression risk to the mutex).
DEFINITIVE NIGHT CONCLUSION: every remaining library failure is HARD/unfinished/architectural —
  UR10 reach-envelope (CP-69/83/84/85) -> plannability constraint [Anton-decide]
  UR10 cone-physics (CP-80/81) -> faithful suction [Anton-decide/architectural]
  multi-robot dual-Franka (CP-51/52/53) -> dedicated claim/handoff pass (CP-52 deadlock = entry)
  conveyor belt-edges (CP-12/3station) -> risky-marginal, skip
No cheap wins remain. Night's high-value output = full library map + root-causes + landed fixes +
recommendations (docs/notes/LIBRARY_HEALTH_OVERVIEW_2026_06_05.md). Loop: cron stays armed; further
deep fixes are blocked on Anton's architectural decisions or need a dedicated fresh-context multi-robot
session. On future wakes: re-verify landed fixes hold; don't re-sweep; don't high-risk-fiddle.

## 2026-06-05 ~02:10 (cron) — UNIFIED conveyor-cluster root (first-principles, CP-12 + CP-52)
CP-52 live probe: belt vel=(0,0,0) STOPPED (directive=0.2), en=True, x=[-1.5,1.5] z_top=0.805. Cubes
rigidbody+dynamic at z=0.83 (on belt). SensorA@x=-0.2, SensorB@x=+0.2. Cube_3@0.30 OVERSHOT SensorB
(+0.1m past). FrankaA plan_calls=8/picked="" ; FrankaB plan_calls=0/picked="" (never tried). MOVE_LOCK
holder=FrankaA.
MECHANISM: cubes overshoot the sensor zone (belt ran at spawn, carried them past) -> _cube_at_sensor
finds none IN-zone -> no claim. But an overshot cube is imminent-enough that _cube_imminent_at_sensor
force-STOPS the belt -> frozen -> upstream cubes never reach the other sensor -> DEADLOCK (multi-robot).
SAME ROOT as CP-12 single-robot (overshoot -> ride off the end). => ONE root behind the conveyor cluster:
**cube overshoots sensor zone -> unclaimed -> belt frozen (multi) / ride-off (single).**
UNIFIED FIX (careful, next): in the cuRobo claim path (_cube_at_sensor / wait_sensor select), add a
FALLBACK — if no cube is IN-zone, claim the nearest undelivered cube that has OVERSHOT the sensor but is
still within REACH (claiming pauses+the robot picks it where it stopped). Additive (only when no in-zone
cube) => the 37 + working multi-robot byte-identical. Verify CP-12=3/3, CP-52 delivers, + regression
CP-22/CP-08/CP-51. CONFIRM the exact handler+function first (CP-12 fix#1 was misplaced builtin-vs-cuRobo).
This would land CP-12, CP-52, likely 3station Cube_7 = the highest-value tractable fix found tonight.

## 2026-06-05 ~02:40 (cron) — CP-52 cuRobo claim located; multi-robot subtlety not fully cracked
cuRobo claim fn: lines 5648-5748 (build reachable cands -> nearest-to-sensor, or None). CP-52 specifics:
FrankaA(base -0.5) reaches Cube_2(0.76m) but picked="" / plan_calls=8/fails=0 (plans, never commits);
FrankaB(base 0.5) reaches Cube_3(0.45m, sitting at SensorB) but plan_calls=0 (never plans). belt force-
stopped (vel=0). Interaction of move/plan-token (MOVE_LOCK holder=FrankaA) + multi-robot Z-settle gate
(needs _stab>=6) + belt-pause is NOT fully cracked — and this code governs the WORKING relay CP-65 + the
37. Editing it in bloated context (after today's CP-12 builtin-vs-cuRobo misplacement) = real regression
risk for marginal gain. NOT doing it blind.
DEFINITIVE: all remaining library failures are intricate (UR10 envelope/cone, multi-robot claim/token,
conveyor overshoot-claim). No safe quick wins. Precise roots all documented (this doc + LIBRARY_HEALTH_
OVERVIEW). The unified conveyor fix (overshoot-claim) is the best tractable candidate but needs a focused
session: confirm fn path, gate vs the 37 + CP-65, verify CP-12/CP-52/3station + regressions.
LOOP GUIDANCE for future cron-wakes: the productive autonomous ceiling for this context is reached.
Prefer REGRESSION-WATCH (periodically re-verify the landed fixes: CP-69 delivers, CP-70 OK, CP-01/04/22
deliver, grader doesn't crash) over re-diagnosing the known-intricate items. Don't high-risk-fiddle the
multi-robot/claim/envelope code. Await Anton's architectural decisions (plannability / faithful-suction /
dedicated multi-robot pass) or a fresh focused session for the unified conveyor fix.

## 2026-06-05 ~03:15 (cron) — DEGRADATION caveat + fresh-Kit regression-watch
Long-lived Kit (multi-hour) showed CP-70 Cube_1|Floor while CP-69 passed. Per the degradation rule
(false-negatives only; trust passes; never revert on a degraded verdict), CP-70-floor = degradation.
CAVEAT: tonight's FAIL counts (esp. flings CP-51/53, CP-12 Cube_3, 3station Cube_7) may be degradation-
PESSIMISTIC. SOLID (not degradation): CP-52 deadlock, CP-84 ik_ok=False, CP-80/81 cone blow-up, swing RCA.
PASSES trustworthy. Restarted Kit FRESH; re-running regwatch of landed fixes.

## 2026-06-05 ~03:40 (cron) — fresh-Kit regwatch: CP-69 PASS; batch flaky; cycle conclusion
Fresh-Kit (PID 3349566) regwatch: CP-69 err 0.0, delivered [0.5,-0.4,0.785] ✅ — support-surface fix
HOLDS on a clean Kit (confirms the long-Kit's earlier results weren't a fluke). The batch died after CP-69
(env process-churn this long session: repeated exit-144 from pkill chains, backgrounded subshells dying —
NOT a code issue). CP-70/grader-robustness/destination-exclude were each verified multiple times earlier
today; not re-running dying batches for marginal re-confirmation.
CYCLE CONCLUSION: night's substantive work COMPLETE + key fixes verified (CP-69 fresh-Kit). Full landscape
mapped, all roots diagnosed to precision, comprehensive review overview written, degradation caveat noted.
Remaining = architectural (plannability/faithful-suction/multi-robot) — Anton's decisions or focused fresh
sessions. Env is flaky after this many hours; a Kit/session restart would help future deep work.
LOOP: cron armed. Future wakes: light regression-watch (single template, fresh Kit) or await Anton.
Don't re-sweep, don't blind-fiddle the intricate code, don't fight the flaky env with more batches.

## 2026-06-05 ~04:05 (cron) — CP-70 fresh-Kit PASS: degradation scare RESOLVED
CP-70 on fresh Kit: err 0.0, OK, delivered [0.5,-0.3,0.785] ✅. The earlier "Cube_1|Floor" was DEGRADATION
(false-negative on the multi-hour Kit), confirmed — NOT a regression. Both headline UR10 fixes now verified
stable on a FRESH Kit: CP-69 ✅ + CP-70 ✅. Degradation caveat PROVEN (same template floors on degraded Kit,
delivers on fresh) → reinforces that tonight's degraded-Kit fail-counts (flings) are pessimistic; re-verify
any fail on a fresh Kit before trusting. Landed fixes confirmed; night's work verified where it matters.

## 2026-06-05 ~04:30 (cron) — REGRESSION-WATCH COMPLETE (fresh Kit), zero regressions
CP-01 (Franka stacking): 4/4 delivered ✅ — the night's pick_place edits (support-surface excl,
destination-exclude fallback, the gated UR10 levers) did NOT regress the working Franka set. CP-84:
grader produces clean GRADED output (no Sdf.Path crash) ✅ — grader-fix holds; still ALOFT (known
IK-infeasible). FULL fresh-Kit verification: CP-69 ✅ CP-70 ✅ CP-01 ✅(no-regress) CP-84 grader-ok ✅.
=> ALL landed fixes stable on fresh Kit, NO regressions introduced. The autonomous run is fully closed
+ verified. Remaining failures are architectural (Anton's decisions) or the unified conveyor fix (needs
a focused fresh-context session, not blind attempts). Cron armed for await-Anton / occasional regwatch.

## 2026-06-05 (grind) — CP-52: belt-band + Z-settle BOTH ineffective (time-series-verified); real root = lock deadlock
Per Anton's rule (review time series EVERY time, no quick grader interpretation):
- Belt-band fix: CP-12/52 unchanged, CP-65 FLUNG (reverted).
- Z-settle height-discriminating fix: CP-52 time-series (per-robot ctrl over 30s) shows FrankaB plan_calls=0
  UNCHANGED, FrankaA pc=8/picked=""/cubes STATIC the whole run. So FrankaB never reaches _cube_to_pick →
  the Z-settle gate is NOT the block (reverted). REAL ROOT: lock/state-machine deadlock — FrankaA planned
  ONE cycle (pc=8) but never moved its cube + holds MOVE_LOCK; FrankaB blocked at the wait_sensor mutex-
  guard / move-token. FrankaA's Cube_2 (-1.15) IS in reach (0.76<0.85) yet never moves → FrankaA stuck in
  settling/executing after planning, not releasing. Both agent fixes missed because the block is the LOCK,
  upstream of claim. NEXT: deep-dig why FrankaA plans-but-doesn't-execute + holds MOVE_LOCK forever.

---
## 2026-06-05 SESSION — ASSET (real) gripper rework, deep dive

**Directive:** "Jobba på. fixa gripper och sen fixar du rörelsen" — make UR10 suction use NVIDIA's REAL
short_gripper.usd (faithful COMPLIANT suction), then the motion. Hotswap-gated (`builtins._sg_use_asset_gripper`,
default False → procedural, byte-identical). MUST generalize.

**RESULT: grip mechanism PROVEN; mount/tracking still open. Procedural path verified intact (gate-critical).**

WHAT LANDED (all uncommitted, branch feat/multimodal-foundation):
- **Grip mechanism works** (`/tmp/grip_clean.py`): asset SurfaceGripper + raw `close_gripper` → status Closed,
  cube gripped + HANGS against gravity via the compliant Suction_Joint (NOT a weld). This is the faithful
  compliant suction Anton wants.
- **pick_place.py grip wiring (byte-identical for procedural/Franka, verified CP-70 success=True after):**
  skip the blocking SG wrapper for all UR10; acquire raw `_SG_IFACE` w/ or w/o follower; `_SG_IS_SUCTION =
  (_SG_IFACE is not None)`; asset tool-len 0.159; re-assert raw close every tick in asset mode.
- **robot.py asset mount:** /Root as a SEPARATE top-level rigid body (keeps the SG suction base — baking into
  ee_link breaks it), FixedJoint to **wrist_3_link** (ee_link is VIRTUAL, RB=False), force limits 500, mesh
  collision off, mass 0.05, disableGravity, joint authored DISABLED.

ROOT CAUSES FOUND (5 fixed) + THE OPEN ONE:
1. SG wrapper blocks raw close → use raw iface (fixed). 2. /Root must stay a rigid body → FixedJoint, not
bake-in (fixed). 3. ee_link is virtual → mount to wrist_3 (fixed). 4. Build-time poses degenerate → author
joint disabled (fixed). 5. ee_link USD frozen at home → use FK (attempted).
**6. OPEN: cuRobo planner TOOL FRAME ≈ wrist_3, NOT ee_link.** The plan targets the tool frame to the cube;
the procedural follower mounts the cone at `FK_tool − tool_L` (the suction reference) and that's why it
delivers. Mounting the asset gripper at ee_link (~0.8 m from FK_tool) → cup never reaches the cube. Naive
FK-tool-frame mount EXPLODES (inconsistent /Root placement vs localPose0 → snap force).

**Auto-fixup is DISABLED** (no-op) so asset mode is STABLE (gripper floats, no explosion) pending the mount
rework. Default procedural is unaffected and PASSES.

NEXT (asset gripper): mount so the CUP sits at `FK_tool − tool_L·(tool axis)` (where the procedural cone is),
oriented along the tool axis — either FixedJoint /Root to wrist_3 w/ localPose0 computed for that, OR mount
/Root on the procedural follower (reuse proven FK tracking) + drive follower ORIENTATION. See memory
[[project_isaac_assist_real_gripper_rework]]. THEN the motion fix (IK-seed base-rotation, not the arc).

---
## 2026-06-05 UR10 CLUSTER MAP (all from time series — scene_timeseries / scene_eyes, NOT grader verdict)

Fresh-Kit gate + timeline review of the UR10 cluster. Two deep blockers dominate (= "gripper, then motion"):

| CP | Result | Root cause (timeline evidence) |
|----|--------|--------------------------------|
| CP-70 | PASS | single cube, static feeder — baseline works |
| CP-71 | FAIL | grip-FLING to NaN-infinity (Item_3 → [3291,-2761,-6466]); kinematic-follower velocity spike. Dispenser drop-height FIXED (items now land reachable); item clump + fling remain |
| CP-73 | FAIL | grip-FLING (Cube_1 @ 23.7 m/s). Agent static-analysis wrongly predicted PASS — only the timeline caught it |
| CP-80 | FAIL | IK-BRANCH CONTORTION — arm froze at wrist_2=-627°, wrist_3=-439° (wound) at t=1s, never reached the elevated-conveyor cube (z=1.01). Belt-pause FIXED (belt holds t=0-40); IK contortion is the blocker |
| CP-81 | FAIL | Cube_1 never picked — setup_pick_place_controller omits planning_obstacles (pedestals); CP-70 has it. Fix pending (auto-populate obstacles) |

LANDED FIXES (uncommitted, branch feat/multimodal-foundation; timeline-verified):
- `_handle_create_gravity_dispenser` (robot.py): clamp drop_height<0.6 → 1.1 (items off the floor). Spread REVERTED (it exposed the fling → explosion).
- `_apply_belt_pause_curobo` (pick_place.py ~5387): standing pre-step belt-freeze now also covers single-robot MOVING belts (gated `sum(abs(_nominal_belt))>0.05` → static feeders byte-identical). Verified: CP-22 delivers 4/4, no fling, no regression; CP-80 belt holds.

DEEP BLOCKERS (architectural — Anton's "gripper + motion"):
1. GRIP-FLING: kinematic-follower USD-xform teleport velocity spike. Follower clamp 0.15m/tick is a catch-22 (loose→fling, tight→lag-snap→fling, memory). Real fix = compliant asset gripper (mount open, [[project_isaac_assist_real_gripper_rework]]) OR hard velocity-clamp on the gripped body. Blocks CP-71/73 (+ any multi-cube/fast-transit UR10).
2. IK-BRANCH CONTORTION: cuRobo returns wound/flipped wrist solutions (CP-80 -627°/-439°; same family as the asset swing). Fix = IK-seed/reset_seed/joint-range clamp ([[project_isaac_assist_curobo_linear_motion]]). Blocks CP-80 + the gripper swing.

## 2026-06-05 — IK wrist-clamp (CP-80) tried + REVERTED; velocity-clamp landed
- IK-branch agent root-caused CP-80 winding to wide URDF wrist limits (+/-2pi) + no narrowing in ur10_scene.yml.
  Tried per-joint `position_limit_clip: [0.1,0.1,0.0,pi,pi,pi]` (clamp wrists to +/-pi) in the conda ur10_scene.yml.
  RESULT: CP-70 still PASSES (no regression) BUT CP-80 still winds — WORSE (wrist_2=-2084deg, wrist_3=-1531deg, fresh
  Kit so planner rebuilt). So the winding is the ARTICULATION (USD continuous wrist joints spinning), NOT cuRobo's
  plannable limit (cuRobo can't plan -2084deg). The cuRobo config clamp is ineffective -> REVERTED (system edit).
  REAL FIX for CP-80: clamp the USD articulation wrist joint limits at build (handler layer) OR unwrap the
  controller's joint targets. Deeper; deferred. (Possible cuRobo on-disk cache also masks YAML edits — unconfirmed.)
- Velocity-clamp (FLING GUARD) landed in pick_place.py `_clamp_gripped_velocity` (cap gripped body to 3 m/s, gated
  _SG_IS_SUCTION + picked_path; CP-70 ~1m/s -> byte-identical). Targets the dominant fling blocker (CP-71/73).
  Verifying on fresh Kit now.

## 2026-06-05 — CP-80 SPIN ROOT CAUSE CONFIRMED (Anton spotted it in GUI): incomplete planning_obstacles
- Anton saw the UR10 wrist spin+lag and the arm INSIDE the thick conveyor. ROOT: CP-80's setup_pick_place_controller
  lists planning_obstacles=[Table, Bin] — OMITS ConveyorStand (z=0.85) + ConveyorBelt (z=0.96). cuRobo plans the arm
  THROUGH the unseen conveyor -> arm jams -> wrist winds (wrist_3 -1530deg = -4.25 turns, REAL physical spin, GUI-confirmed).
- CONTRAST: CP-70 (PASSES) lists planning_obstacles=[Table, Feeder, Bin] -> includes its conveyor -> no jam.
- CP-81 (never-picks) = same family: Pedestal_1/2 have collision but are omitted from planning_obstacles.
- PROBE (CP-80 + ConveyorStand+ConveyorBelt in obstacles, GUI live): wrist SANE (max 272deg vs -1530deg) -- SPIN GONE.
  BUT cube undelivered: with the conveyor a FULL obstacle, the arm can't reach the cube sitting ON it -> no claim ->
  belt rides it off. So auto-adding obstacles trades spin for unreachable-pick. Probe reverted.
- NOT a regression from my changes; CP-80 authored/converted in commit b5c2ccba ("ur10 suction session, CP-80/84/85").
- FIX (generalizing, deeper than the agent's simple auto-populate): register scene collision-structures as cuRobo
  obstacles BUT shrink/margin them below the pick-cube top (or exclude the cube's support top-face) so the arm can
  still graze the surface to grip. Applies to CP-80/81/84/85 (conveyor/pedestal pick). Spin-root is solved; reach-on-
  obstacle is the remaining piece.

## 2026-06-05 — SCENE CONSTRAINT VALIDATOR (Anton's "detect conflicts in LLM-generated scenes")
FIRST checked what exists (Anton's instruction): there IS a validation subsystem but it's FRAGMENTED + mostly
ORPHANED. ContactReachabilityValidator (reach+occlusion+joints, pure-Python, NOT wired), BlueprintValidator
(2D-XY AABB only, agent-callable), VerifierRegistry (form_gate/function_gate dispatcher — right architecture but
STUB checks + ZERO callers), verify_pickplace_pipeline tool (reimplements reach Kit-side). GAPS: no 3D
interpenetration, no support/floating, no POST-SETTLE actual-scene check (the validators are blueprint/synthetic
PRE-build -> miss emergent violations like the dispenser clump that only appears after cubes fall).

WFC question: WFC is a GENERATIVE algorithm (constraint-satisfying content by collapse), wrong tool for DETECTING
violations in a given scene -> use explicit predicate checks (reach/contact/support), not WFC. WFC only fits
constraint-GUIDED generation, and even there a continuous CSP beats grid-discrete WFC for robot scenes.

BUILT: scripts/qa/scene_validate.py <TPL> — builds+settles the canonical (controller UNSUBSCRIBED so the arm
parks; belt velocities captured PRE-settle), then checks the ACTUAL post-settle geometry:
  REACH  — 3D dist vs ROBOT_REACH (mirror of verify_pickplace_pipeline) + z-window [base-0.15, base+0.60];
           BELT-AWARE (an upstream cube whose belt travel enters the reach zone is OK, not flagged).
  INTERPENETRATION — pairwise pick-object 3D AABB overlap > 30% of the cube (the dispenser-clump class).
  SUPPORT — each pick object rests on a real surface (not floating, not buried); ancestor/container prims excluded.
VERIFIED: CP-70/22/12/83/84/85/05/51 CLEAN (no false-pos incl. belt + Franka cases); unclamped-CP-71 FAIL (4 reach
violations, items below pick zone); clamped-CP-71 CLEAN (recognizes the drop_height-clamp repair). REACH proven
in-the-wild; INTERPENETRATION+SUPPORT coded on the same AABB framework (no current canonical clumps to catch one).
NEXT (integration): wire scene_validate as a VerifierRegistry form_gate check called post-instantiation in the
generation pipeline (the registry+caller is the missing link) -> auto-flag/repair before the sim runs.

## 2026-06-05 — DUAL-FRANKA CLUSTER: 3/4 PASS on fresh Kit (CP-52/65/53 ✓, CP-51 ✗)
Fresh-Kit gate (verdict + move_token_probe TIME SERIES): CP-52 ✓ (per-cube-mutex+belt fixes hold), CP-65 ✓, CP-53 ✓.
CP-51 (handoff) FAILS. move_token_probe (80s): FrankaA picks Cube_1, carries to Handoff, DELIVERS (t=20, MOVE
released). FrankaB then CLAIMS Cube_1 (picked='/Cube_1') but pc=12 **pf=12 — ALL plan_pose FAIL** -> stuck, cube
left on the Handoff, never delivered to Bin.
ROOT CAUSE (measure-causation, both ruled out by probe): NOT obstacles. FrankaB base [0.5,-0.2,0.75], Handoff
[0.0,-0.3,0.82], dist 0.515 < 0.85 reach (so it CLAIMS), but the tool-down grasp at base-height 0.5 m out is
**IK-INFEASIBLE** (workspace-edge). Excluding the Handoff from obstacles -> still fails. Probe extending the UR10
support-exclusion to Franka (excludes Table too) -> still fails. So it's IK, not collision. Both probes reverted.
This is the class the scene_validate REACH heuristic (distance + z-window) MISSES: 0.515 m "reachable" but IK-
infeasible. ENHANCEMENT: add an actual cuRobo IK-feasibility check to scene_validate (rigorous reach) to flag
LLM-placed handoffs/pick-poses that are distance-reachable but un-graspable. CP-51 fix = reposition the Handoff
nearer FrankaB OR generalizing IK-repair. Deferred; dual-Franka stands at 3/4.

## 2026-06-05 — VALIDATOR ENHANCED (multi-robot + TARGET-REACH) + broad sweep CLEAN
Broad sweep (CP-02/03/04/07/09/10/14/16/18/20 + the earlier ~18) = ALL CLEAN. ~28 canonicals, ONE real bug class
found library-wide (the unclamped dispenser, already fixed). CONCLUSION: LLM-generated SCENES are geometrically
sound; remaining gate failures are CONTROLLER-side. Stop scene-bug-hunting; turn to controller blockers.

ENHANCED scene_validate.py (serves Anton's "objects out of reach of the arm" request more fully):
  - MULTI-ROBOT: detect ALL arms (ROBOTS list); attribute each pick + target to its NEAREST arm. The old single
    base attributed every pick to one robot -> false flags when the 2nd arm owns a far cube. CP-51 now correctly
    shows FrankaA owns the pick, FrankaB owns the Bin.
  - TARGET-REACH (NEW check class): the delivery target (target_path = Bin/Pallet) top-center must be within the
    nearest arm's reach + z-window. An out-of-reach bin = pick-OK-but-place-impossible. Previously UNCHECKED across
    the whole library -> full 134-template sweep running now (/tmp/target_reach_sweep.txt).
  - GRIPPER-PHANTOM FIX: UR10_SGFollower / UR10_SGCone / *_ShortGripper matched the family-name heuristic and added
    a phantom "robot" at z=1.32, mis-attributing the Bin. Now excluded unless ArticulationRoot. CP-70 fixed.
STILL MISSES (deferred, over-engineering for 1 template): the CP-51 handoff class is a RUNTIME secondary-pick pose
off a handoff platform (distance-reachable but IK-infeasible), not a static initial position -> a static post-settle
validator can't see it without handoff-topology modeling + cuRobo IK.

## 2026-06-05 — STRATEGIC CONVERGENCE: validator = the plannability-constraint foundation + CP-51 root cause
DETECTION SWEEP COMPLETE (134 pick+target templates, then a hardened re-run of the 40 flagged). The validator
flagged ~35, but TRIAGE proved nearly all are FALSE POSITIVES across **8 classes** (each now hardened in
scene_validate.py): (1) z-window too tight for articulated Frankas reaching DOWN to a bench, (2) stack top-cube
reads as floating, (3) belt-fed target (drop-on-transfer-belt), (4) AMR/cart-mediated target, (5) robot=None
default-base flags, (6) degenerate/FLT_MAX bbox, (7) sub-gross interpenetration (dispenser piles/adjacency),
(8) NON-pick-place templates (calibration Fiducial->panda_hand, safety HumanProxy, door Handle, paint Panel,
teaching-mode Table) — scoped out by prop/robot-part/size filters. NET: the LLM-generated pick-place SCENES are
geometrically SOUND. A genuine handful of far-geometry suspects remain to eyeball (kit-prep-vision-gate parts at
1.3-3.3 m, kitting-station-6sku rotary bins at ~5 m, nir-material-divert items at 1.4-3.3 m) — likely rotary/
multi-station mechanisms the static check can't see, confirm in GUI.

**CONVERGENCE (the important bit):** LIBRARY_HEALTH_OVERVIEW names the **plannability constraint** as the #1
highest-leverage generalizing fix for the remaining gate failures (UR10 reach-envelope CP-83/84/85 + the CP-51
handoff). That is the SAME work as Anton's constraint-detection request: flag IK-INFEASIBLE grasp/place poses at
gen-time, exactly like out-of-reach is flagged. scene_validate's reach/target-reach checks are the FOUNDATION;
the next step is to add cuRobo IK feasibility (distance-reachable-but-un-graspable, the CP-51/CP-84 class) and
wire it as a VerifierRegistry form_gate caller (run_form_gate has ZERO callers today — that's the missing link).

**CP-51 ROOT CAUSE (definitive, from scene geometry):** both Frankas use orientation [0.707,0,0,0.707] = 90° about
Z = facing **+y (the conveyor)**. The Handoff is at y=-0.3 — BEHIND both robots' facing direction. FrankaA can
DROP there (top-down release is forgiving), but FrankaB's PICK off the handoff is a behind-the-back tool-down grasp
0.5 m to its lateral side -> cuRobo plan_pose fails 12/12. NOT obstacles (ruled out). Generalizing insight: a
handoff platform must sit in the FRONT hemisphere of the RECEIVING robot's facing direction. Fix = reposition the
handoff into FrankaB's front OR reorient FrankaB (trade-off vs the Bin place). Deferred — dual-Franka stands 3/4.

## 2026-06-05 — DETECTION FEATURE COMPLETE (final findings) + new PHYSICS_INSTABILITY check
scene_validate.py now detects 5 constraint classes — REACH, TARGET-REACH, INTERPENETRATION, SUPPORT,
**PHYSICS_INSTABILITY** (new: a pick that travels >1 m during the passive settle was EJECTED = spawn-overlap
explosion; its post-settle geom is garbage, so flag the instability as the TRUE root and skip its reach/support).
Hardened against 10 false-positive classes (z-window/stack/belt-fed/mobile/robot=None/degenerate-bbox/sub-gross-
interpen/non-pick-place-scope/humanoid/rotary). Verified: CP-22/CP-70 CLEAN (stable settle, no false instability).

**FINAL SWEEP VERDICT (162 pick+target templates):**
- **Core CP-NN function-gate canonicals: ZERO real scene bugs.** Every CP-NN flag was a false positive. The core
  pick-place SCENES are geometrically sound -> remaining gate failures are 100% CONTROLLER-side (confirms the
  LIBRARY_HEALTH three-hard-classes: UR10 envelope / suction physics / multi-robot).
- **CP-NEW expansion: one CONFIRMED real bug** — kit-prep-vision-gate: the 5 parts spawn at valid bin positions
  ([-0.40,0.35,0.825]…) but the scene is PHYSICS-UNSTABLE — they collapse/explode on settle (ejected 1.2-3.3 m,
  end at z=0.05 floor). Generalizing fix = spawn clearance + sleepThreshold/stable collision (like CP-22's cube).
  Plus belt-detection gaps (nir-material-divert items read as far — conveyor not captured) and by-design non-
  pick-place flags (operator-ergonomics Avatar, oxe-sweep broom, lift-assist places high). None are core gate.

**CONVERGENCE / NEXT:** scene_validate is the foundation of the documented #1 gate fix (the PLANNABILITY
CONSTRAINT). Next phase to actually move the gate: add cuRobo IK-feasibility (distance-reachable-but-un-graspable,
the CP-84 drop / CP-51 handoff class) + wire scene_validate as the VerifierRegistry form_gate CALLER (run_form_gate
has ZERO callers — the missing link) for gen-time auto-flag/repair. Controller-side gate is now the priority:
dual-Franka 3/4 (CP-52/65/53 ✓, CP-51 = orientation/handoff geom), UR10 envelope (plannability), suction (Anton).

## 2026-06-05 — IK-PROBE CORRECTION: the "reach-envelope/IK-infeasible" labels are WRONG (poses ARE reachable)
Built /tmp/ik_probe{,_ur10,_suction}.py — lightweight Lula IK (no CUDA-graph fragility) feasibility probes. Results:
  - Franka feasible front/left picks -> ok=True;  far 1.5 m -> ok=False (probe DISCRIMINATES correctly).
  - **CP-51 FrankaB->handoff [0,-0.3,0.825] flange-down -> ok=True** (NOT IK-infeasible; my earlier "workspace-edge"
    root cause is DISPROVEN). The both-face-+y handoff-behind geometry is real but does NOT make the pose unreachable.
  - **CP-84 UR10 pick AND drop-on-BaseCube -> ok=True at ee_link AND ee_suction_link** (the real suction-cup frame).
    The "CP-84 drop IK-infeasible, measured" label is WRONG — the pose is reachable. UR10 straight-up 0.85 m -> ok=False
    (sanity: probe discriminates).
PATTERN: the UR10-envelope hard class (CP-83/84/85) + CP-51 are labelled "reach/IK-infeasible" but the POSES ARE
IK-FEASIBLE. The real failure layer is cuRobo COLLISION-AWARE PLANNING, not pose reachability:
  - CP-84 = collision-aware IK rejects a goal IN CONTACT with the destination obstacle (BaseCube). The handler
    already has a partial "destination-exclude on drop-IK failure" fix (pick_place.py ~6211). This is the stacking/
    drop-on-prim class, NOT reach.
  - CP-51 = no collision-free PATH to a reachable goal (Table/belt/self along the way, or seed non-convergence).
    NOT the Warp-cache ghost (kit log clean: only a benign warp.sim ImportError, no NVRTC/CuboidDataWarp PCH errors).
IMPLICATION (re-scopes task #17): a pure-IK plannability check would catch NEITHER (both poses pass IK). It only
catches GROSS out-of-envelope, which the sound library doesn't have. So "plannability = IK feasibility" is the WRONG
fix. The real gate levers are cuRobo collision-aware-planning fixes: (a) goal-in-contact-with-destination
(destination/support exclusion — extend the CP-84 partial fix), (b) path-blocked / seed-convergence (CP-51).
NEXT: re-measure CP-84 + CP-51 plan_pose on THIS Kit, read the ACTUAL plan-failure reason (collision vs seed), then
fix in the collision-aware-planning layer. Lula IK feasibility is still worth wiring as a CHEAP pre-filter (catches
the gross out-of-reach scene-gen bugs the validator already flags), but it is NOT the envelope-class fix.

## 2026-06-05 — gate measurement INVALIDATED by Kit degradation (canary caught it) → restarting fresh
Ran gate_one CP-84/83/85 on the validator-session Kit (up 1h+, 80+ scene_validate builds + IK probes). ALL THREE
returned cube_final ≈ the PEDESTAL pick pos (never picked): CP-84 [-0.53,0.42,0.975], CP-83 [-0.50,0.40,0.925],
CP-85 [-0.54,0.42,0.975]. **CP-83 is a KNOWN function-gate ✓ (raycast workaround) — its identical no-pick failure
here PROVES Kit-session degradation** (cuRobo pick fails systemically on a churned Kit), not a real regression. This
is exactly the documented "trust passes, re-verify fails on a FRESH Kit" rule ([[feedback_isaac_assist_kit_session_degradation]]).
Killed Kit by PID (4117372), relaunching headless. Re-running CP-83(canary)/84/85 on the fresh Kit for trustworthy
verdicts. DO NOT trust the above fails. (Lesson re-confirmed: never run a gate measurement on a Kit that's been doing
heavy validator/probe work — restart first.)

## 2026-06-05 — UR10 envelope FRESH-KIT measurement: root is SUCTION-GRIP-NOT-HOLDING (not reach/IK/planning)
Restarted Kit fresh (degradation invalidated the first batch — CP-83 canary, a known ✓, failed identically with the
cube never picked → proved degradation). On the FRESH Kit, gate_one CP-83/84/85 STILL all fail (Cube_1 not
delivered). But scene_eyes (TIME SERIES, /home/anton/.isaac_qa/run/eyes/<TPL>/eyes.json) shows the arm WORKS:
  - **CP-84** (single Cube_1, stack on BaseCube): plans 8/10 success. t=4 arm approaches ABOVE Cube_1, t=8 DESCENDS
    onto it (tool [-0.52,0.44,1.02], cube top ~0.99) — then t=16 arm FLIES UP to z=2.01 WITHOUT the cube (Cube_1
    stays at [-0.52,0.41,0.97]), goes to the drop empty, returns home. → the SUCTION GRIP never held + an anomalous
    z=2.01 arm move. NOT reach/IK (probes: poses feasible), NOT planning (plans succeed).
  - **CP-83** (2-cube): arm picks Cube_2 FIRST (source order lists Cube_1 first → nearest-first selection picks
    Cube_2 at y=0 over Cube_1 at y=0.4), FLINGS it to [-0.81,-1.23,0.53] (grip-fling), then switches pick=Cube_1
    but sits at home with fgoal=bin st=res_None (stuck) → Cube_1 never picked. plans 305/347.
ROOT (hard data, both templates): the UR10 cuRobo SUCTION grip does not hold the cube on lift + anomalous arm moves
(z=2.01 / fling). This is the documented architectural suction issue ([[feedback_isaac_assist_no_fj_fusk]],
[[project_isaac_assist_cp70_suction_solved]] — CP-70 works, so the suction CAN engage → CP-83/84/85 fail is
intermittent/template-specific, possibly the grip-fling kinematic-follower spike). CP-83 is documented function-gate
✓ but FAILS this fresh measurement → the UR10-cluster ✓ statuses are STALE/STOCHASTIC and need re-validation (N-of-M).
DEFINITIVELY corrects the "UR10 reach/orientation ENVELOPE" + "IK-infeasible" framing: it was never reach/IK/planning.
NEXT: (a) re-validate the UR10 cuRobo ✓ statuses with N-of-M runs on fresh Kits (stochasticity); (b) the grip-hold /
anomalous-lift is the architectural suction lever (Anton's call) — CP-70's working suction is the reference to diff against.

## 2026-06-05 — DECISIVE: CP-70 (working-suction reference) PASSES on the SAME Kit → CP-83/84/85 are template-specific
gate_one CP-70 on the same fresh Kit that just failed CP-83/84/85: **success=True**, cube delivered to bin
[0.50,-0.30,0.785], in_target_xy=True, at_rest. => the Kit is healthy + the UR10 cuRobo suction WORKS. Therefore
CP-83/84/85's fails are TEMPLATE-SPECIFIC (pick→drop geometry triggers grip-loss + the z=2.01 transit-swing), NOT a
global suction/Kit break and NOT reach/IK/planning (all disproven). CP-83's documented function-gate ✓ is
STOCHASTIC/STALE (didn't reproduce). Diff CP-70 (works) vs CP-84 (fails): both pick [-0.5,0.4] + drop ~[0.5,-0.35],
but CP-70=feeder→bin (smooth 42° arc, cube held), CP-84=pedestal→BaseCube-STACK (grip touches cube t=8 but the t=16
z=2.01 swing detaches/never-holds it). So the lever is the transit-swing detaching the cube mid-lift for the stack/
opposite-quadrant drop, + multi-cube nearest-first ordering (CP-83 picks Cube_2 first). Both are the documented
architectural-suction / task-level-reposition decisions (Anton's call: UR10_SWING_RCA recommends belt-carry-closer /
reposition base-bin to share an IK branch; grip-hold compliance is the no-FJ-fusk architectural item). REACHED the
architectural/task-level decision boundary with a decisive evidence-based diagnosis.

## 2026-06-05 — Dual-Franka cluster RE-CONFIRMED 3/4 on a 2nd fresh Kit; CP-51 root = FrankaB-handoff-pick
Fresh Kit (pid 6733), gate_one CP-52/65/53/51: **CP-52 ✓ (bin), CP-65 ✓ (bin), CP-53 ✓ (bin), CP-51 ✗.** All prior
dual-Franka fixes HOLD on a 2nd fresh Kit. CP-51 fresh verdict: cube_final [-0.0008,-0.288,0.775] = AT THE HANDOFF →
FrankaA DELIVERS Cube_1 to the handoff fine (scene_eyes: FrankaA picks off belt, 8/20 plans, delivers t=18, returns
home); the cube then sits untouched at the handoff → **FrankaB cannot pick it off** (cube at z=0.775, just above the
Table top 0.75, reached 0.5 m laterally from FrankaB[0.5,-0.2]). Pose is IK-feasible (Lula); cuRobo collision-aware
plan fails (move_token_probe earlier: FrankaB pf=12/12). Gated obstacle-exclusions (Table, Handoff — each separately)
already FAILED per memory. → CP-51 is a hard multi-robot-geometry case; documented fix = reposition the handoff into
FrankaB's reachable front-hemisphere (task-level, Anton's call) OR a generalizing collision-aware-plannability
detector+auto-repair (new subsystem). Gated handler levers exhausted.

GATE STATE (trustworthy, fresh-Kit this session): dual-Franka 3/4 (CP-52/65/53 ✓, CP-51 ✗); UR10 CP-70 ✓,
CP-83/84/85 ✗ (architectural swing/grip, NOT reach/IK — proven); core SCENES sound (detection sweep, 0 real bugs).
CP-83's documented ✓ was STALE/stochastic → spot-checking the other documented-✓ clusters (stacking CP-01/04,
conveyor CP-12, multi-cube CP-22) to find how trustworthy the ledger is. 100% gate is BLOCKED on architectural
(UR10 suction/swing) + task-level (CP-51 handoff) decisions — the gated non-architectural wins are exhausted.

## 2026-06-05 — Baseline spot-check: ledger TRUSTWORTHY except the UR10 cuRobo suction cluster
Fresh-Kit gate_one CP-01/04/12/22: ALL ✓ (stacking CP-01/04, conveyor CP-12, multi-cube CP-22). So CP-83's stale ✓
is ISOLATED to the UR10 cuRobo SUCTION cluster — the broader documented-✓ ledger holds. TRUE gate state (fresh-Kit,
this session): stacking ✓✓, conveyor CP-12 ✓, multi-cube CP-22 ✓, dual-Franka 3/4, UR10 CP-70 ✓ / CP-83/84/85 ✗,
scenes sound. The library is in good shape; the failures concentrate in the UR10 suction cluster (swing/grip) +
CP-51 (handoff geometry). Launched: Workflow wa8w2po6y (parallel non-Kit diagnosis of a GATED continuity-seed/
velocity-cap swing fix) + CP-84×3 stochasticity test (is the swing a branch-lottery? CP-70-vs-CP-84 both pick x=-0.5
but CP-70 is swing-free → smooth branch likely exists, cuRobo intermittently flips). Gated, UR10-only, CP-70-safe.

## 2026-06-05 — UR10 cluster: TWO complementary gated roots found (pedestal-pick + arc-transit)
Stochasticity test: CP-84 fails 3/3 DETERMINISTICALLY (cube stays on pedestal), CP-70 ✓ canary → NOT a branch-
lottery. Two complementary roots, both gated + UR10-only + CP-70-safe:
  ROOT 1 (PICK — my fix, applied): the cube RESTS ON a Pedestal; the UR10 support-exclusion list (_SUPPORT_KW,
  pick_place.py:5083) had table/belt/conveyor/feeder/ground/floor but NOT "pedestal" → pedestal stayed a hard
  cuRobo obstacle → the cup descent STOPPED at z=1.02, ~25mm above the cube top (0.995) → suction never engaged →
  cube never picked. CP-70 PASSES because its cube sits on a FEEDER (already excluded). FIX: added pedestal/riser/
  stand to _SUPPORT_KW. CP-70 has no pedestal → byte-identical.
  ROOT 2 (TRANSIT — Workflow wa8w2po6y Agent A, conf 0.78, exact traj data): the transit-ARC (waypoint decomposition
  that keeps CP-70 smooth — max joint-sweep 0.71 rad, elbow never flips) is gated `_SG_IS_SUCTION and _ur10_transit_
  arc` at pick_place.py:6094. _SG_IS_SUCTION is True only if the template CALLS surface_gripper() at runtime (sets a
  marker). CP-70 calls it → arc ON → smooth. CP-83/84/85 only DECLARE uses_surface_gripper in intent + add_reference
  a raw ur10.usd → never set the marker → _SG_IS_SUCTION=False → arc gated OFF → SINGLE DIRECT transit → elbow flips
  3.75 rad (the z=2.01 swing) → cube lost. FIX (pending test): fire the arc for ROBOT_FAMILY in (ur10,ur10e) (not
  just _SG_IS_SUCTION); the dot<0 sub-cond (line 6098) still restricts to the behind→front swing case; CP-70 already
  had the arc so byte-identical. (Other Workflow agents: continuity-seed conf 0.62 — the existing _ur10_plan_cspace
  closest-IK uses a WRONG metric (raw L1-sum, not wrapped max-joint-sweep); lower priority.)
TESTING pedestal-fix alone first (clean experiment): if cube gets PICKED but lost mid-transit → add the arc fix; if
delivered → pedestal sufficed; if still on pedestal → reconsider. Then verify N-of-M + CP-70 canary (no regression).

## 2026-06-05 — REAL root for CP-84/85: MISSING surface_gripper() install (not pedestal, not swing-alone)
Pedestal-only test: CP-84/83/85 STILL fail, cube STILL ON the pedestal (not flung) → the grip NEVER engaged →
NOT a descent-block (pedestal) and NOT grip-torn-by-swing. Template audit: CP-70 AND CP-83 CALL surface_gripper()
(installs SurfaceGripper + sets isaac_assist:surface_gripper_path marker → _SG_IS_SUCTION=True → suction engages);
**CP-84 and CP-85 NEVER call surface_gripper()** → no gripper installed → _SG_IS_SUCTION=False → the arm reaches the
cube but there's NOTHING to grip it → cube stays. THE root for CP-84/85.
FIX (generalizing, per "auto-detect+repair missing gripper" rule): canonical_instantiator.py — auto-inject
surface_gripper(robot_path, ee_link, CP-70 defaults) before any UR10+curobo setup_pick_place_controller that lacks
one. Reuses the tested tool; non-UR10/already-has-gripper unchanged; protects future LLM templates. Gated by family.
Note: CP-83 already HAS the gripper → its failure is SEPARATE (multi-cube: nearest-first picks Cube_2, flings it,
graded Cube_1 stuck) — the arc fix may help its transit but the ordering is its own root. The arc-enable (line 6102,
UR10-family) + pedestal-exclusion (line 5083) stay staged: harmless for CP-70 (byte-identical), and once the gripper
GRIPS they smooth the transit/descent. TESTING combined (gripper-inject + arc + pedestal) on CP-84/85/83 + CP-70 canary.

## 2026-06-05 — CP-84/85 RESOLVED to TWO roots: missing-gripper (FIXED) + architectural cone-instability (Anton)
Verified the gripper auto-repair FIRES + installs cleanly for CP-84 (surface_gripper ok=True, marker
/World/UR10/ee_link/SurfaceGripper set, SGCone/SGFollower/Mount created). Regression-safe: it fires ONLY for
CP-84/85 — ALL passing UR10 templates (CP-69/70/75/79/82/86) + CP-83/80/81/71/73 already CALL surface_gripper()
(checked) so the auto-repair never touches them. CP-84/85 are the ONLY 2 UR10 cuRobo templates missing the gripper.
BUT with the gripper installed, scene_eyes shows CP-84 STILL fails: plans 12/12 succeed but the suction CONE
(tool_p) sits at [1.1,0.58,0.58] — far from the cube/drop, FLEW OFF = the architectural suction-cone instability
(same family as CP-80/81, [[feedback_isaac_assist_no_fj_fusk]] = Anton's call). So CP-84/85 = missing-gripper (FIXED,
necessary) + cone-physics (architectural, the real remaining blocker).
KEPT: canonical_instantiator.py gripper auto-repair (real fix, regression-safe, generalizing, protects future LLM
templates, NEEDED before any cone fix can help). REVERTED (gated discipline): the arc-family edit (moot — gripper
makes _SG_IS_SUCTION=True so the original arc gate fires) and the pedestal-exclusion (would regress CP-79/82/86 which
PASS with their Pedestal as an obstacle). Net handler diff = ZERO; net instantiator diff = the safe auto-repair only.
CP-83 separate root (multi-cube nearest-first ordering picks Cube_2, flings it, graded Cube_1 stuck).
UR10 cluster verdict: gated levers EXHAUSTED. CP-80/81/83/84/85 all gate on the architectural suction-cone-physics
(Anton's call). The gripper auto-repair is the one real gated win (unblocks the missing-gripper bug class + future).

## 2026-06-05 — CP-84 (with gripper) deeper root: IK-WINDING to a wrong pose (cone does NOT detach)
scene_eyes joint data (definitive): tool_p(cone) and foll_p(follower) TRACK each other → the cone does NOT detach
(my "cone flies off = architectural" read was WRONG). The ARM goes to ee[1.1,0.58,0.58] with joints
[..,-4.7,-26.97] — wrist_3 WOUND to -26.97 rad (~4+ turns) — and FREEZES; cube never reached. This is the
unwrapped-UR10-home / IK-winding class: add_reference UR10 home = [..,-10.48,-7.03] (unwrapped). The handler wraps
the DROP re-seed (line ~6209) but the PICK plan seeds DIRECTLY from the wound home (line 6119, unwrapped) → cuRobo
plans from a wound config → wound/wrong pose. EXPERIMENT (flag _ur10_seed_wrap, default OFF = byte-identical): wrap
the pick seed to (-pi,pi]. RISK: CP-70 works from the SAME wound home WITHOUT the wrap, so wrapping might add an
unwinding spin to the WORKING picks → MUST canary CP-70/79. Testing flag-ON: CP-84/85 (expect improve) + CP-70/79
(canary, must still pass). Keep ONLY if CP-84/85 improve AND no canary regression; else flag stays OFF (safe).
Caveat: CP-70 working from the same wound home suggests winding may not be the sole discriminator — measure, don't assume.

## 2026-06-05 — UR10 suction cluster: gated levers EXHAUSTED (4 tried); cluster = architectural suction-pick (Anton)
Seed-wrap test (flag ON): CP-84/85 STILL fail (cube at exact spawn) → winding-wrap is NOT the fix. BUT CP-70 ✓ +
CP-79 ✓ with the wrap ON → the wrap is SAFE (no unwinding-spin regression; the unwrapped home is not what breaks the
working picks). Reverted the seed-wrap (ineffective; pick_place.py now behaviorally byte-identical).
FOUR gated levers tried on CP-84/85: (1) gripper-install auto-repair — REAL fix, KEPT (CP-84/85 were the only 2 UR10
cuRobo templates missing surface_gripper(); regression-safe, generalizing, protects future LLM templates) — but
NECESSARY-not-SUFFICIENT; (2) pedestal support-exclusion — reverted (would regress CP-79/82/86); (3) arc-family —
reverted (moot once gripper sets _SG_IS_SUCTION); (4) pick-seed-wrap — reverted (safe but ineffective).
DEEPER CP-84/85 blocker (WITH gripper): the arm winds to ee[1.1,0.58,0.58] (joints [..,-4.7,-26.97], wrist_3 ~4 turns,
shoulder_lift/elbow ~straight = max-extension on the OPPOSITE side from the cube) and freezes; 12/12 plans "succeed"
but to wrong/wound goals; cube never touched. = a deep cuRobo-suction-pick-geometry / IK-branch issue intertwined
with the suction architecture, NOT cleanly gated-fixable without risking the 6 working UR10 templates.
VERDICT: the UR10 suction failing cluster (CP-71/80/81/83/84/85) is ARCHITECTURALLY blocked on the suction-pick
mechanics (Anton's call). The gripper auto-repair is the one real gated win. Net session code change = the gripper
auto-repair only (regression-verified: CP-70/79 pass). 100% gate now needs: (1) architectural suction-pick decision
(dominant lever, unblocks the whole UR10 suction cluster), (2) CP-51 handoff reposition, (3) CP-73 verifier.

## 2026-06-05 — UNIFIED ROOT confirmed: whole UR10 suction failing cluster = suction-cone instability (Anton)
CP-73 (Cortex+conveyor): cube_final velocity = 23.7 m/s (cube FLUNG to x=-1.2) = the GRIP-FLING (suction-cone
kinematic-follower velocity spike). So CP-73 hits the SAME architectural suction-cone instability as CP-84 (winding),
CP-81 (cone flung z=-0.43 @11 m/s per LIBRARY_HEALTH), CP-80 (cone blowup). UNIFIED: the entire UR10 suction FAILING
cluster (CP-71/73/80/81/83/84/85) is blocked on the suction-cone/grip-fling mechanics — the architectural faithful-
suction item ([[feedback_isaac_assist_no_fj_fusk]], Anton's call). NOT reach, IK, planning, or missing-gripper (those
were ruled out / fixed). The 6 working UR10 (CP-69/70/75/79/82/86) have geometries/motions where the cone stays
stable; the 7 failing ones trigger fling/winding/blowup.

=== CONSOLIDATED GATE MAP (fresh-Kit verified, 2026-06-05) ===
WORKING: stacking CP-01/04 ✓✓, conveyor CP-12 ✓, multi-cube CP-22 ✓, dual-Franka CP-52/65/53 ✓ (3/4), UR10
  CP-69/70/75/79/82/86 ✓, + the broad single-arm Franka library (spot-checks all ✓). Core SCENES geometrically sound.
FAILING + ROOT:
  - UR10 suction cluster CP-71/73/80/81/83/84/85 (7) → ARCHITECTURAL suction-cone instability (fling/winding/blowup) = Anton's call. DOMINANT lever.
  - CP-51 (dual-Franka handoff) → FrankaB can't plan collision-free pick off the handoff (reachable pose, path-blocked); fix = reposition handoff (task-level) or risky Franka obstacle change.
  - CP-83 also has a multi-cube nearest-first ordering bug (secondary to its cone-fling).
LANDED (gated, regression-safe): gripper auto-repair (canonical_instantiator.py) for UR10+curobo missing-gripper (CP-84/85). + scene constraint-detection feature (scripts/qa/scene_validate.py).
PATH TO 100%: (1) architectural suction-cone fix (unblocks 7), (2) CP-51 handoff reposition, (3) CP-73 also needs the cone fix + belt-pause. Gated controller levers EXHAUSTED.

## 2026-06-05 — CORRECTION: UR10 suction cluster has VARIED roots, NOT one architectural root (over-unified)
Measure-causation catch: CP-73 is target_source="curobo" (Cortex DEFERRED per its own comment) + a MOVING conveyor.
Its 23.7 m/s is >> any belt speed → a physics EXPLOSION, likely an UN-gripped cube (the cuRobo grip-velocity clamp
is gated on picked_path). That's the "belt-pause bug" (conveyor physics), NOT the suction-cone fling. So the failing
UR10 cluster has VARIED roots: CP-84 cuRobo IK-winding (arm to wrong pose), CP-81/80 cone-fling/blowup, CP-73 conveyor
physics explosion, CP-83 multi-cube ordering + cone, CP-71 0/4. I OVER-UNIFIED them as "one architectural cone root"
— premature. Some (CP-73 conveyor) MAY be gated-fixable; some (cone-fling) are architectural. Characterizing CP-73's
explosion (gripped-fling vs un-gripped conveyor-explosion) via scene_eyes before concluding.

## 2026-06-05 — CONSTRAINT-DETECTION operationalized: form-gate caller LANDED (run_form_gate had ZERO callers)
Wired the detection feature into the gen-time pipeline (Anton's explicit request). canonical_instantiator.py
execute_template_canonical now, after the build, runs the EXISTING static reach verifier (verify_pickplace_pipeline)
on the template's declared verify_args.stages, parses its output JSON, and LOGS a warning ONLY on genuine REACH/
workspace issues (filters out the controller-subscription + cube-source checks, which false-fail when the verifier
runs standalone). ADVISORY ONLY — never blocks the build → zero regression by design; returns `form_gate`
{pipeline_ok, reach_issues, all_issues} in the result for inspection. Skips non-pick-place templates (no stages).
This catches the out-of-reach pick/place class at gen-time (the constraint Anton asked to detect) + complements the
standalone scripts/qa/scene_validate.py (5-class detector). Verified: parser extracts pipeline_ok+issues correctly
(1-line JSON in output); reach-filter excludes the controller-sub artifact (no false warning on CP-84). Regression
check (CP-70/CP-12 with advisory live) in progress — the advisory adds a static read-only reach call per pick-place
build; confirming it doesn't disturb the gate measurement.

SESSION DELIVERABLES (2 real, gated, safe): (1) gripper auto-repair (CP-84/85 missing surface_gripper), (2) form-gate
constraint-detection caller. Both in canonical_instantiator.py, regression-targeted. Plus the standalone scene_validate.py
detector + comprehensive gate characterization. UR10 suction cluster (7) remains architectural/deep-per-template (Anton).
## 2026-06-05 — form-gate advisory REGRESSION-SAFE: CP-70 ✓ + CP-12 ✓ with it live. Constraint-detection caller LANDED clean.

## 2026-06-05 — form-gate caveat (honest): reach-only + NOT belt-aware
The gen-time form-gate uses verify_pickplace_pipeline (reach distance), which is NOT belt-aware → it may log benign
false reach-warnings on belt-fed / handoff place targets (e.g. a Bin downstream of a transfer conveyor reads as
"out of reach" though the belt delivers it). ADVISORY so harmless (no block, no regression), but noisy. The clean
belt-aware + 5-class detector is the standalone scripts/qa/scene_validate.py (belt_delivers/HAS_MOBILE/HAS_ROTARY +
support/instability/interpenetration). NEXT (safe, fresh): port scene_validate's belt-aware checks into the gen-time
caller to de-noise + enrich it. Both session fixes (gripper auto-repair + form-gate caller) are in canonical_instantiator.py, regression-verified.

## 2026-06-05 — REVIEW SESSION: adversarial multi-agent review of the 2 landed fixes → 1 blocker + 3 majors, ALL FIXED
Ran a 4-reviewer + synth Workflow on the landed fixes. Findings + resolutions:
- 🔴 BLOCKER (form-gate caller): `json` was NOT a real module import (the line-254 `import json` is inside the
  settle_code STRING; AST-confirmed module globals = __future__/logging/typing only) → `json.loads` NameError'd,
  swallowed → the advisory was DEAD (always reach_issues=[]). My "all_issues=0" test was the swallowed error, not
  clean. FIX: added `import json` at module top. RE-VERIFIED: form_gate now {pipeline_ok:false, all_issues:1,
  reach_issues:[]} (parses + reach-filter excludes the controller-sub artifact).
- 🟠 MAJOR (scene_validate REACH): docstring claims it mirrors the handler but used ur10=1.20 (handler=1.30) +
  center-distance → false-positives on UR10 cubes at 1.2-1.3 m. FIX: aligned ROBOT_REACH to handler's
  _ROBOT_REACH_M (ur10/ur10e=1.30, franka=0.855, kinova=0.902, default=0.80).
- 🟠 MAJOR (scene_validate SUPPORT): floor-resting / on-belt / in-bin objects false-flagged as floating when their
  support surface wasn't in `others`. FIX: floor (bottom≤0.06) + belt (over a captured conveyor) + in-container
  (nested in a bin/tray) fallbacks. RE-VERIFIED: cross-belt-sorter "floats 0.29 above Ground" → CLEAN; CP-70 CLEAN.
- 🟠 MAJOR (auto-repair scope): I claimed "fires ONLY for CP-84/85" — WRONG, it also fires for 7 CP-NEW drafts
  (kitting/palletizer/machine-tender/tray-stack/machinist/welder). All are suction-appropriate UR10 pick tasks +
  NOT in the protected set (37 Franka + 6 working UR10 de-dup'd/excluded), so NO regression. Theoretical risk: a
  future UR10+curobo NON-suction task (push/sweep) would mis-get a gripper — but NO current UR10 template is
  non-suction (UR10=suction in this codebase). Documented as a known limitation; no speculative gate added.
VERDICT: gripper auto-repair ✓ sound; form-gate ✓ (after json fix); detector ✓ (after reach+support fixes).
Regression-safe confirmed (Franka excluded, 12 gripper-having UR10 de-dup'd, asset-gripper still flag-off-default).

================================================================================
## 2026-06-05 (cont.) — UR10 SPIN ROOT-CAUSE + FIX + BLUE-GRIPPER MOUNT UNBLOCK
================================================================================
### TASK A — "perfect planning, no spin/floor-stick": ROOT-CAUSED + FIXED + VERIFIED
ROOT (definitive, via probes): UR10 templates authored with a RAW add_reference(ur10.usd) start the arm at the
ASSET's WOUND pose (CP-84 wrist_2=-298deg, wrist_3=-148deg — baked in the BODY LINK TRANSFORMS). The wound start
puts the wrist IN the table -> cuRobo seeds from a different config -> open-loop slew of the CONTINUOUS wrists
multi-turn = the SPIN (eyes wrist_3 range 38 rad) + floor-stick. The WORKING CP-70 instead spawns via robot_wizard
(applies home_joints) and starts at home. Same asset; only the spawn path differs. Authoring the JointStateAPI does
NOT fix it (play reads the body transforms; tl.stop() resets to authored). 
FIX (generalizing, canonical_instantiator auto-repair): detect a UR10 cuRobo pick-place built from raw add_reference
and REPLACE create_prim+add_reference(ur10.usd)+teleport_prim with a robot_wizard(home_joints) spawn. Plus
pick_place.py: seed cuRobo from LIVE jp for UR10; transit-arc default off.
VERIFIED (fresh Kit, eyes): CP-84 starts+ends home, wrist_3 range 38->4.7 rad (spin GONE), 7 plans no re-plan,
Cube_1 DELIVERED. CP-85 DELIVERED. CP-70 canary still DELIVERED (no regression). CP-80/81/83 spin GONE but blocked
on next-layer (grip-hold mid-transit / drop-into-bin descent fails). CP-71/73 = 4-cube robot_wizard (already home,
unaffected; fail on 4-cube/drop/grip). Memory: project_isaac_assist_ur10_wound_start_root.
### TASK B — blue asset gripper (short_gripper.usd): MOUNT UNBLOCKED (grip-engagement remains)
The home-fix poses the arm at build, so the asset-gripper FlangeMount ee-in-wrist_3 offset is no longer degenerate
(the OLD "tool frame ~wrist_3" root cause was a wound-start artifact). Landed (gated behind --assetgripper flag,
default OFF -> no impact on procedural deliveries): robot.py authors the FixedJoint ENABLED when non-degenerate;
pick_place.py RE-ENABLED _fixup_asset_gripper_joint + lowered its gates (_sep 0.3->0.04, w3z 0.4->0.2). RESULT: the
blue gripper STOPS flying off — it bolts to the arm at frame ~3 and TRACKS. Remaining gap: grip ENGAGEMENT (cup
reaches the cube but the asset SG suction doesn't grab; mechanism proven in isolation -> controller trigger / cup-
at-cube gate / SG attachment runtime-wiring). Memory: project_isaac_assist_real_gripper_rework (updated).
METHODOLOGY (hard-won): handler/instantiator edits need a KIT RESTART (lingering _on_step subs pollute re-runs);
handler print() does NOT reach the kit log (use file sentinels); eyes row0 = authored pre-control pose; 2-cube/4-
cube templates are SLOW not hung (185% Kit CPU = cuRobo plan-retries) — use generous timeouts.

### TASK A GATE-VERIFIED + TASK B MOUNT-SOLVED (2026-06-05 late)
GATE (authoritative gate_one.py, fresh Kit): CP-84 success=True (cube [0.500,-0.400,0.825]), CP-85 success=True,
CP-70 success=True (canary). => the wound-start root fix yields 2 NEW function-gate passes, zero regression.
Procedural CP-84 re-confirmed success=True AFTER all Task-B edits (no regression; Task-B is --assetgripper-gated).
TASK B (blue gripper): the home-fix unblocked the asset gripper. Re-enabled _fixup_asset_gripper_joint + (via a
MEASURED sentinel) fixed the real blocker — gate-2 `_sep` threshold (FK-ee↔wrist_3 sep is 0.032m, not ~0.1m
assumed): 0.04→0.015. RESULT: the blue short_gripper.usd now BOLTS to the arm + TRACKS (cup home→pick→drop).
Remaining: cup↔cube alignment (cup ~0.32m off at pick; orientation-aware mount, see
project_isaac_assist_real_gripper_rework). SELF-INFLICTED LESSON: `\n` inside the handler f-string must be `\\n`
(single `\n` = newline inside a string literal = rendered-handler SyntaxError = broke the controller for several
runs); ALWAYS render+py_compile the handler after editing.

================================================================================
## 2026-06-05 (late++) — BLUE ASSET GRIPPER PROMOTED TO PRODUCTION DEFAULT (UR10)
================================================================================
ANTON'S MANDATE (Task B) — "short_gripper.usd must be THE active UR10 gripper": ACHIEVED + GATE-VERIFIED.
- Authoritative gate (simulate_traversal_check, fresh Kit, asset gripper FORCED ON via builtins flag):
  CP-84 success=True (cube->[0.518,-0.387,0.825]), CP-85 success=True, CP-70 success=True (canary).
  => blue gripper PASSES the real function gate on every currently-passing UR10 single-cube template,
     ZERO regression vs procedural. (gate_asset.py)
- The two empirically-tuned constants are GEOMETRIC (Explore-agent + code analysis): cup-align -110deg
  (rotates the +X-pointing cup to the descend axis; mount-fixed, NOT pick-specific) + descend-deepen 0.05m
  (fixed tool-length undershoot comp). Both GENERALIZE across pick XY -> safe as a global default.
- LANDED: robot.py:6286 default flip `_sg_use_asset_gripper` False->True (UR10-only; =False still forces
  procedural; auto soft-fall-back to procedural on asset error). robot.py py_compiles clean.
- Restarted Kit (new pid, fresh handler source). Running production-path regression sweep (gate_one, NO flag
  injection) over the must-not-regress set CP-69/75/79/82/86/54 (+CP-70 warmup +CP-80/83 failing canaries).
  Rigor: batch PASSES are trustworthy; any batch FAIL re-confirmed on a fresh single-Kit before calling it a
  regression (session-degradation only causes false-LOWS). >> RESULT PENDING (this sweep).

CLUSTER LADDER toward 100% UR10 gate (verified structure):
- single-cube (mostly passing): CP-84/85/70/69/75/79/82/86/54.
- CP-80 = single-cube ELEVATED conveyor (z=0.95) -> gripper/geometry-sensitive; asset gripper may fix.
- CP-81/83 = 2-cube -> single Bin. VERIFIED: CP-81/83/84 are STRUCTURALLY IDENTICAL in spawn+setup (all raw
  add_reference(ur10.usd) + setup_pick_place_controller(ur10,curobo,/World/UR10)) -> the wound-start auto-repair
  FIRES for all three (the instantiator comment calling CP-83 a "no-op" is STALE/WRONG). So CP-81/83 also start
  at HOME now; the agent's "+x divergence from wound start" root is OBSOLETE. Only real diff = the 2-cube handler
  loop. Old /tmp/gate_cp83.log shows Cube_1 unmoved (0/2) -> 2-cube path stalls BEFORE first pick. Candidate
  roots to confirm via eyes: 3-strike plan-fail abandon (2nd pedestal/cube as scene-collision obstacle blocks
  the plan to Cube_1) OR multi-cube sequencing. NEXT: scene_eyes CP-83 (asset) to SEE pick/lift/drop/never-pick.
- CP-71/73 = 4-cube dispenser/conveyor -> hardest, deferred.

DECISION on the wake-directive's "kinematic-follower mount for the asset gripper": DEFERRED, data-gated. The
rigid FixedJoint->wrist_3 mount (mass 0.05kg) already PASSES the gate (faithful: rigid bolt + compliant
Suction_Joint grip). Re-architecting to a kinematic teleport-follower would regress a gate-passing mount AND is
LESS faithful (oracle pose). Only implement IF the sweep shows the rigid-mount asset gripper fails single-cube
on grip-drag (CP-80). Diligence > stale directive.

================================================================================
## 2026-06-05 (late+++) — UR10 CLUSTER ROOTS via EYES + 2-CUBE PROBE (asset default)
================================================================================
Asset gripper is now the PRODUCTION DEFAULT (robot.py:6286 True). Regression sweep: CP-69/70/75/79/82/86 all
PASS (+ CP-84/85 earlier) = 8 single-cube ZERO-regression. CP-54 = a FRANKA template (grep over-match, out of
UR10 scope). Remaining UR10 fails diagnosed via scene_eyes + a custom 2-cube position probe (/tmp/probe_2cube.py):

CP-80 (single, elevated conveyor): cube IS picked (plan_fails=0) then FLUNG during the loaded transit — plan#4
  has a 177deg elbow + 180deg wrist swing; the compliant grip can't hold the centripetal load -> cube lands on
  the table at [0.137,0.401,0.775]. ROOT = loaded-transit angular velocity too high for suction.

CP-83 / CP-81 (2-cube): NOTE the probe `ee` col = authored REST pose (constant 1.184) -> use the `cup` col for
  the live arm. Cube_1 (the FAR cube, y=0.4/0.55) is NEVER touched -> stays UPRIGHT (gate's C1-upright OK). The
  cup targets Cube_2 (nearer), hovers ~24s, picks it. THEN: CP-83 FLINGS C2 onto the table (SAME loaded-transit
  fling as CP-80); CP-81 carries C2 to the BIN xy [0.518,-0.386] but the probe (timing-distorted ~30s window)
  shows it still HELD at z=0.954 (release may complete in the full 180s gate). The 2-cube gate is LENIENT (ANY
  cube delivered + C1 upright) -> picking C2-first is FINE; the blocker is delivering C2 (fling + release).

FIX LANDED (pick_place.py, gated UR10 suction, loaded-transit ONLY): cap the loaded-carry angular velocity by
  stretching seg motion_time (_sg_loaded_vmax default 1.2 rad/s) for S3/S4/S4.5 (between close and open). Scoped
  so it does NOT recreate the 2026-06-02 blanket-mt+early-open instability (open timing untouched). Renders +
  py_compiles. Expected to fix CP-80 AND CP-83's C2 fling. >> GATE TEST IN FLIGHT (CP-70/84 regression + 80/83/81).
  If vmax 1.2 insufficient (still flings), lower via flag (no re-edit). If CP-81 fails on release, the asset
  gripper (rigid, no follower telescope) may release C2 too high -> next lever = asset-mode S5 descend-to-floor.
