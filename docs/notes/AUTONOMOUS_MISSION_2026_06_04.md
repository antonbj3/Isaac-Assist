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
