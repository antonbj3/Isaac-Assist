# Canonical Template Visual Review — Round 2 Startup

You are running a human-in-the-loop review of Isaac Sim canonical templates. Anton will watch Isaac Sim's viewport on his screen; you load each template, describe what should happen, and log his Yes/Partial/No reply.

This is **Round 2** — Anton already did Round 1 (244 tags, 233 unique templates). Round 2 verifies whether today's handler fixes + 38 template rewrites changed outcomes.

## Pre-flight (ONCE at session start)

1. **Kill any headless Kit + relaunch with VISIBLE viewport.**
   ```bash
   pkill -KILL -f isaac_sim_with_assist
   sleep 4
   /home/anton/projects/sibling-project/launch_isaac_sim_with_assist.sh > /tmp/kit_review.log 2>&1 &
   ```
   Wait ~60s. Verify Kit alive:
   ```bash
   curl -s http://127.0.0.1:8001/health
   ```
   Headless launch script passes `--no-window` which kills the viewport. Without `--headless` arg, viewport is visible.

2. **Annotations already regenerated** with sweep V8 data. Verify:
   ```bash
   ls /home/anton/projects/Omniverse_Nemotron_Ext/workspace/qa_runs/annotations/*.json | wc -l
   ```
   Should print 233.

3. **Build priority list** — start with templates most likely to have changed since Round 1:
   ```bash
   cd /home/anton/projects/Omniverse_Nemotron_Ext
   python3 -c "
   import json, glob
   items = []
   for fp in glob.glob('workspace/qa_runs/annotations/CP-*.json'):
       d = json.load(open(fp))
       name = d['template']
       sweep = d.get('sweep_v2_result') or {}
       rewrites = d.get('rewrite_history') or []
       honest = sweep.get('honest_pass')
       # Priority: HONEST_PASS first, then rewritten-with-sweep-data, then rewritten-no-data, then earlier-PASS no-rewrite
       if honest is True: prio = 0
       elif sweep and not honest: prio = 1
       elif rewrites: prio = 2
       else: prio = 3
       items.append((prio, name, len(rewrites), honest))
   items.sort()
   print('# Order:')
   for p, n, r, h in items[:60]:
       tag = 'PASS' if h else ('FAIL' if h is False else 'NO-DATA')
       print(f'  [{p}] {n}: rewrites={r} sweep_v8={tag}')
   " > /tmp/review_order_v2.txt
   head -20 /tmp/review_order_v2.txt
   ```

## V8 sweep + 3-run validation results (the recent fixes)

V8 sweep showed 6 PASS, but 3-run fresh-state validation revealed stochasticity:

**RELIABLE (3/3 PASS):**
- **CP-14** (Franka stacking, pall enlarged 0.075→0.20 + planner-cache fix) — confirmed real win
- **CP-77** (Franka multi-cube, explicit physics:mass=0.1 per cube) — confirmed real win

**STOCHASTIC (2/3 PASS):** failure mode = **delivered-then-dislodged** — cube placerar OK men hamnar på Ground/Table i 1/3 runs
- CP-09 (Franka stacking) — Run 1 cube on /World/Ground (-0.51, -0.60); Runs 2-3 on TowerBase
- CP-13 (Franka stacking, the canonical that proved planner-cache root cause) — Run 3 cube on /World/Ground (0.20, -0.99); Runs 1-2 on PalletBase
- CP-NEW-brick-stacking — Run 3 cube on /World/Table; Runs 1-2 on Baseplate

**FLUKE (0/3 PASS in validation):**
- CP-28 — passed only in single V8 sweep, all 3 validation runs failed

**Trajectory data captured** for CP-13/09/brick-stacking → `workspace/qa_runs/stochastic_trajectory.jsonl`. Full mechanism analysis in `docs/research/2026-05-20-dislodge-mechanism.md`.

**Failure mechanisms identified:**
- **YEET** (CP-13 Run 1): cube placed AT pall surface, friction-grip constraint energy stored, stochastic release impulse launches cube at 7 m/s.
- **DROP_OFF** (CP-13 Run 2): cuRobo plan_pose poor xy convergence, cube placed OFF pall edge, falls to Table.

**Proposed structural cure D — TESTED + REVERTED 2026-05-20 20:25**:
- Implemented: `_bin_drop_pos` (line 4746) → `mx[2] + FL + _dc_v` with `FL=0.105` for Franka
- **CP-13: 5/5 PASS** (vs 1/3 pre-fix). max_speeds 0.60-1.04 m/s. Cure D direction is CORRECT.
- **CP-14: 3/3 FAIL** (vs 3/3 pre-fix). All cube on Ground at 1.91 m/s. **REGRESSION**.
- Cause: raising drop_pos.z by 10.5cm changes cuRobo plan_pose trajectory → worse xy convergence at descent → cube placed off pall edge → falls to Ground.
- **Reverted** to baseline. Cure D needs more sophisticated implementation:
  - Better: pass measured grip_offset from pick phase to drop phase (~20-30 line refactor)
  - Or: keep current drop_pos.z but instead fix the pick/drop FL-asymmetry at line 5292 of `_build_segments` directly
  - Or: investigate why CP-14 had identical 1.91 m/s on all 3 fails (suggests deterministic failure mode, not stochastic)

Data: `workspace/qa_runs/cure_d_validation.jsonl`. Full analys i `docs/research/2026-05-20-dislodge-mechanism.md`.

**Major bugs Anton flagged in Round 1, status now:**
- Telepatisk kontakt (CP-06/07/12/19/49 etc) — distance gates landed. Verify whether teleport still happens.
- UR10 horizontal start (CP-69/70/71/72/75/78/79/82/86) — robot_wizard migration + home_joints. Some still go underground (sweep showed mixed results).
- Multi-bin sorting (CP-18, CP-NEW-yrkesroll-inspector-reject-divert) — Bug 1 routing fix landed. May still fail.
- Cube spawn-under-table (CP-NEW-sorter-size-weight) — z corrected. Verify spawn.
- Cylinder→Cube (CP-05) — Agent 3 fix + FlipWall removed.
- AMR Carter missing (CP-NEW-amr-pickup-handoff, CP-64) — Carter spawns + navigates now.

## The review loop

For each template in priority list:

### Step 1: Load template into Isaac Sim
```bash
cd /home/anton/projects/Omniverse_Nemotron_Ext
/home/anton/miniconda3/envs/isaac_lab_env/bin/python scripts/review/load_for_review.py <CP-NAME>
```
This resets the stage, builds, settles, frames the camera, plays timeline. Anton sees the scene animate.

### Step 2: Read AI annotation (V2 fields)
```bash
cat workspace/qa_runs/annotations/<CP-NAME>.json | python3 -m json.tool | head -50
```
Key fields:
- `narration` (brief description)
- `scene_summary` (robot, n_cubes, destinations)
- `failure_class` + `failure_reason`
- `rewrite_history` (what agents fixed)
- `sweep_v2_result` (HONEST_PASS or FAIL — does sweep agree with Anton?)
- `key_questions` (Yes/No to ask)

### Step 3: Narrate to Anton
Write a SHORT message (3-5 lines):
- Template name + intent
- Robot + scene contents  
- **What was rewritten** (from rewrite_history)
- **What sweep V8 says** (PASS or FAIL — see if you visually agree with sweep verdict)
- Ask 1-2 key questions

Example:
> CP-13 — pick_place, Franka + conveyor + 2 cubes + pallet. Stacking-rewrite enlarged pallet to 20×20cm. Sweep V8: HONEST_PASS (5/5 gates). **Ser du kuberna staplas på pallen utan att rasa?**

### Step 4: Wait for Anton's reply
Tags:
- "Yes" / "ja" / "stämmer" → `yes`
- "Partial" / "delvis" → `partial`
- "No" / "nej" / "stämmer inte" → `no`
- "Skip" / "hoppa" → `skip`

### Step 5: Log
```bash
/home/anton/miniconda3/envs/isaac_lab_env/bin/python scripts/review/log_tag.py <CP-NAME> <yes|partial|no|skip> "<comment>"
```
Append to `workspace/qa_runs/review_logs/human_tags.jsonl`. Round 1 tags coexist — new tags timestamp-disambiguate.

### Step 6: Confirm + next
"Ok, nästa" → step 1 with next template.

## What to focus on

1. **Verify sweep V8 PASS templates are visually correct** — these are claimed "real wins". Anton's eyes confirm.
2. **Check rewritten templates that sweep says FAIL** — does Anton see the rewrite actually applied? Sometimes scene_observer's gates are too strict / too lenient.
3. **Spot-check telepati cohort** — distance gates supposedly landed. Are CP-06/07/19/49 still showing telepati?
4. **Compare to Round 1 tags** — if Anton tagged CP-X as "no" before and rewrite landed, is it visually better now?

## Resume mid-session

```bash
cat workspace/qa_runs/review_logs/human_tags.jsonl | jq -r '.template + " " + .timestamp' | sort -u -k1,1
```

## Files at a glance

- `scripts/review/load_for_review.py` — loads one template into Kit + plays
- `scripts/review/log_tag.py` — appends one human tag
- `scripts/review/generate_annotations.py` — regenerates all 233 annotations
- `workspace/qa_runs/annotations/<CP>.json` — annotation v2 per template
- `workspace/qa_runs/review_logs/human_tags.jsonl` — append-only human-tag log
- `workspace/qa_runs/sweep_all_rewritten.jsonl` — sweep V8 results (5 PASS / 31 FAIL)

## Start the session

After Kit relaunched with viewport + annotations verified, greet Anton:

> Klar för canonical review round 2. Annotations regenererade med V8-sweep-data. 5 stable HONEST_PASS att verifiera först, sen rewritten-FAIL för att se vad sweep missar. Säg "starta" så plockar jag första.
