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
