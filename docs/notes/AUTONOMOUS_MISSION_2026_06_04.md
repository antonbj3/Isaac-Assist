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

## PROGRESS LOG (update as I go — survives compact)
- 2026-06-04 ~end-of-day: mission started. scene_eyes built+committed. Swing RCA committed. Verified today: CP-70/75/79/82/86 deliver clean; CP-69 delivers-with-swing (far-pick). Next: full ground-truth pass on the rest (CP-71/73/80/81/83/84/85 + CP-07/54).

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
