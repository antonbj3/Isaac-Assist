# UR10 → 100% Function Gate — Autonomous Working Strategy (read this EVERY wake)

Written 2026-06-08 after a session where I repeatedly **overstated, misattributed, and thrashed**. This document
frames the flow so those failures cannot recur. Follow it literally. The goal is not speed — it is **conclusions
Anton can trust without re-checking.**

---

## 0. MISSION (the one goal)
Drive the UR10 templates to **100% function gate** with the **faithful** gripper (real SurfaceGripper, no FixedJoint
cheat). Current verified baseline: **8/13** stable passers (CP-69/70/75/79/80/84/85/86). Fix #1 (cup-arm gap, flush
mount) and #2 (penetration) shipped+verified. Fix #3 (the bin swing) + the 5 fails are open. **When the 13 hit 100%,
the mission does NOT end — continue to the remaining UR10 + plate ("plattor") templates (§13).** State lives in
`docs/notes/NIGHT_MISSION_2026_06_07.md` + `docs/notes/GUI_REVIEW_FEEDBACK_2026_06_07.md` + memory.
**READ AT ORIENTATION (§8.1) — prior RCAs so you don't re-derive:** `docs/notes/UR10_SWING_RCA_2026_06_04.md` (the bin
swing = a geometrically-forced IK branch discontinuity for CP-69's far-behind x=-1.0 pick; all tuning levers rejected;
CP-70/75 at x=-0.5 are flip-free) + `docs/notes/NIGHT_MISSION_2026_06_05.md`.

**OBJECTIVE — unambiguous, and the working stance (Anton's baseline, he is flexible):** cuRobo drives **Franka** to a
clean pick-place. The SAME planner **must be made to drive UR10** to a clean pick-place. UR10's 6-DOF continuous-wrist
branch behaviour (branch-flips / the bin swing) is a **solvable seeding / pinning / scoping problem WITHIN cuRobo** —
**NOT** evidence that "cuRobo can't do UR10". Treat **"cuRobo can work for UR10" as the assumption to prove out**, not
a question to escalate. Do **NOT** off-ramp to "this needs a planner-architecture rewrite" / "it's fundamental" — that
is the premature-conclusion anti-pattern (§4.6). Such a claim is only allowed with [MEASURED] proof that **every
in-cuRobo lever has been exhausted**: IK seeds, traj seeds, ori-tol, branch-pin / `plan_cspace`, the goal JointState /
goal config, the start seed, and the collision world. Until then the front is open and you keep working it (§7 never
halts — §14).

---

## 1. PRIME DIRECTIVE — Calibrated honesty (this is the one that broke this session)
Every factual statement I make or write MUST carry a tag. No exceptions.
- **[MEASURED]** — a number I read from a fresh, uncontaminated run THIS turn. Cite the source (file/log/gate).
- **[INFERRED]** — a logical deduction *from* [MEASURED] values. Show the step.
- **[HYPOTHESIS]** — a guess not yet tested. It is NOT allowed to appear in a conclusion or a summary as if true.

**Banned:** "definitely", "the root is", "flails", dramatic physical narratives — UNLESS backed by [MEASURED].
**A log value is not a physical fact.** (This session I read a planner log `goal=0.47`, called it "arm flails 41cm
below the floor", and was wrong — the arm released at FK-ee 1.11, never went low. A LOG records what was *requested*;
only the live prim positions / contacts record what *happened*. Always separate "the instrument shows X" from "the
robot did Y" and verify Y independently.)

If I catch myself writing a confident sentence, I stop and ask: *which tag? where's the number?* If I can't tag it
[MEASURED], it is [HYPOTHESIS] and must be tested before it becomes a conclusion.

---

## 2. THE SCIENTIFIC LOOP (every problem goes through this, in order)
1. **OBSERVE** — get raw data first (scene_eyes / grip-log / ctrl: attrs / contacts / gate verdict). Do NOT theorize
   from code-reading alone. Report the raw numbers.
2. **HYPOTHESIZE** — write ONE falsifiable hypothesis: "If X is the cause, then changing X will move metric M from A
   to B." Tag it [HYPOTHESIS].
3. **PREDICT** — state the exact number you expect BEFORE running (e.g. "descend sweep 143° → <20°"). A prediction you
   can't state means the hypothesis is too vague — sharpen it.
4. **CONTROL** — change exactly **ONE variable**, gated, default-OFF. Reset all other experimental flags first
   (sticky builtins corrupted 3 of my tests this session — see §3). A/B against the untouched baseline.
5. **MEASURE** — on a **FRESH Kit** (§3). Read the metric. Compare to the prediction.
6. **CONCLUDE** — only now, with the [MEASURED] result: confirmed / refuted / inconclusive. If inconclusive, say so;
   do not round it up to "it works". Update the mission doc with the tagged result.
7. **ADVERSARIAL CHECK** — before declaring a fix DONE, actively try to **refute** it: a second fresh run, a different
   template, the N-of-M (§3). A fix is real only if it survives an honest attempt to break it.

---

## 3. MEASUREMENT DISCIPLINE (the lab rules — most of my flip-flops came from breaking these)
- **FRESH KIT before every meaningful measurement.** Kit degrades within a session (Warp churn) → 2nd+ builds measure
  falsely LOW. This session "flush regresses reach" and "seeds break the pick" were both **degraded-Kit false
  negatives** that a fresh A/B overturned. Restart pattern: robust orphan-reaping kill (reap nvidia-smi compute
  pythons) → `rm -rf ~/.cache/warp` → relaunch via the Bash tool's `run_in_background` (NOT `nohup … &` inside a
  compound command — that fails to detach). Wait for 8001.
- **A FAIL on a stale/contaminated Kit means NOTHING.** Never revert code or conclude a regression from one stale
  fail. Re-check fresh.
- **N-of-M on edge/stochastic templates.** cuRobo IK is Halton-seeded → single runs flip. A single PASS on an edge
  template is a **flake**, not an unlock (CP-82 "unlocked" → 0/3 fresh). Require ≥2/3 fresh-each before claiming a
  reliable pass; require 0/3 before claiming a reliable fail.
- **Sticky builtins contaminate tests.** Flags set via `exec_sync` PERSIST in the Kit across template rebuilds. Before
  any A/B, EITHER restart the Kit OR explicitly reset every experimental flag to its default. (This session a leftover
  `_ur10_plan_cspace=True` made me mis-read which plans were branch-pinned.)
- **Trust the GATE as the verdict, but know it lies too.** `simulate_traversal_check` (delivery) is the production
  signal — outranks scene_eyes (whose play-loop diverges + stalls stochastically). But the gate's success criterion is
  lenient/positional and has produced false-positives historically → confirm a *behaviour* fix with the actual
  trajectory (grip-log cup positions, contacts), not just `success=True`.
- **One run never proves robustness.** "Delivered once" ≠ "reliable". State the sample size with every verdict.

---

## 4. ANTI-PATTERNS (the exact ways I failed this session — recognise and refuse them)
1. **Log-as-physics.** Treating a planner/debug log value as what the robot did. → Verify against live prim positions.
2. **Dramatic narrative.** "41cm below the floor", "flailing". → State only the measured trajectory; let it be boring.
3. **Degraded-Kit flip-flop.** Concluding regress/unlock from a stale session. → Fresh A/B only.
4. **Single-run unlock.** One stochastic PASS read as a fix. → N-of-M.
5. **Contaminated state.** Old sticky flag corrupting a new test. → Reset/restart first.
6. **Premature "root cause".** Naming THE root before the experiment that isolates it. → Hypothesis → test → then name.
7. **Give-up-too-early** (Anton flagged it) AND **thrash-forever** are both failures. The cure is the loop (§2): if a
   hypothesis is refuted, form the NEXT one — don't quit and don't keep poking randomly. Escalate to a workflow (§6)
   when ≥2 hypotheses are refuted on the same problem.
8. **Editing the same hot file blind.** Re-read the exact lines before each edit; keep edits gated + minimal.

---

## 5. FIX DISCIPLINE (so I can never break the 8 passers)
- **Gated, default-OFF, one new flag per change.** Production (flags at default) must be byte-identical until the fix
  is proven. Flush (fix #1) is the only thing that ships default-ON, and only because it's gate-verified on 8/8.
- **Preserve passers.** After any change that *could* touch the shared path, re-run the 8 passers (fresh, passes
  trustworthy) before flipping a default.
- **Do NOT hand-edit template JSONs** (layout = Anton's call). Planner / cuRobo changes ARE allowed autonomously (§0
  says pursue them) — but ONLY **gated default-OFF + traceable/revertable (§14)**, so production (flags off) stays
  byte-identical and the 8 passers are never at risk. Never flip a default that regresses a passer. No "explicit go"
  gate, no stop — the gating + traceability IS the safety, not a human checkpoint.
- **Commit only when Anton asks.** Leave the tree clean + working; note uncommitted changes in the mission doc.
- **Resolve frame-math EMPIRICALLY** (measure prims in the wrist_3 frame, etc.) — do not reason it out and trust the
  reasoning.

---

## 6. AGENTS / WORKFLOWS (encouraged on the night shift)
- **Read-only fan-out is the sweet spot:** when a problem needs breadth (map a subsystem, find a mechanism across the
  cuRobo package, generate N independent fix approaches), launch a `Workflow` of READ-ONLY agents. They must NOT touch
  Kit (single-tenant) — Kit verification stays serial and mine. The drop-swing workflow this session correctly
  surfaced the cspace branch-pin mechanism — that's the model.
- **Adversarial verification:** for a finding I'm about to act on, spawn agents to try to REFUTE it (default to
  refuted-if-uncertain). Majority-refute → drop it.
- **Synthesize, don't trust blindly:** an agent's static read can be wrong (this session one assumed the passers use
  the −90 path; data said nvidia 0°). Cross-check every agent claim against [MEASURED] before acting.
- Use the budget: token cost is not the constraint on the night shift — *correctness* is.

---

## 7. DECISION LADDER (deepen / defer / done — pick deliberately, don't drift)
- **DEEPEN** (keep working it) when: hypotheses are still generating + each is testable on Kit + the metric is moving.
- **ESCALATE to a workflow** when: ≥2 hypotheses refuted, or the problem needs breadth I can't hold in one context.
- **PARK (never halt — there are NO stops at night)** when: the only remaining fix is a layout/scene-build change
  (template JSON, which I must not hand-edit) AND every controller-side hypothesis is [MEASURED]-refuted. PARK = write
  the precise [MEASURED]-backed handoff in the mission doc, then **immediately MOVE ON to the next template/problem** —
  do NOT pause, do NOT ask, do NOT idle. (Throughout this doc "DEFER" means PARK-and-continue, never stop-and-ask.)
  Candidate parks needing Anton's later layout call: CP-81/82 (primary cube y=0.55 unreachable), CP-71 (dispenser
  scene), CP-73 (far-x). A park is REVERSIBLE: a later wake may unpark it if a new controller-side hypothesis appears.
  Note: a planner-architecture rewrite is NOT a valid park reason — per §0 it must first be earned by exhausting every
  in-cuRobo lever, and even then it stays gated default-OFF (§14), not escalated.
- **DONE** only after §2.7 adversarial check: fix gated, A/B-proven on fresh Kit, 8 passers preserved (N-of-M),
  metric hit its predicted value, mission doc updated with tags.

---

## 8. PER-WAKE PROTOCOL (the loop I run on every cron fire — frames the flow so I can't drift)
1. **Orient (≤2 min):** read this file's §0 + the tail of `NIGHT_MISSION_2026_06_07.md` (current state + last tagged
   result). Do not re-derive what's already [MEASURED] there.
2. **State the active problem in one line** + the ONE hypothesis I'm testing this wake (tagged), drawn from the §11
   ledger. **On the first wake (or when §11 is thin / ≥2 refuted), launch the §12 hypothesis-expansion workflow
   BEFORE experimenting** and fold its survivors into §11.
3. **Ensure a clean Kit** (§3): if the running Kit has >~5 builds or unknown flag state, restart fresh.
4. **Run the controlled experiment** (§2 steps 4-6). One variable. Predicted number stated before the run.
5. **Record the tagged result** in the mission doc (one block: hypothesis / prediction / [MEASURED] result / verdict).
6. **Adversarial check** if it looks like a win (§2.7).
7. **Decide** via §7. Update memory if a durable fact emerged.
8. **Never idle, never just "hold"** — if a hypothesis is refuted, the next wake starts at step 2 with the next one.
   Do NOT pause/delete the cron. Do NOT go silent to save tokens.
9. **No dramatic summaries.** When reporting, lead with the [MEASURED] numbers; conclusions come tagged and last.

---

## 9. VERIFICATION LADDER (what counts as "proven", strongest first)
1. **Gate N-of-M, fresh-each Kit** — the verdict. (delivery)
2. **Live trajectory** (grip-log cup positions / PhysX contacts) — proves *behaviour* (e.g. no swing).
3. **cuRobo planned-trajectory capture** (scene_eyes) — proves the *plan* (execution-independent; valid even when
   scene_eyes' play-loop stalls).
4. **ctrl: attrs / debug logs** — diagnostics; a [HYPOTHESIS] source, never a conclusion on its own.
A behaviour fix needs (1)+(2). A planner-shape change needs (3)+(1).

---

## 10. CURRENT OPEN FRONT (as of 2026-06-08, all tags from this session)
- **Fix #3 (bin swing) — REFRAMED 2026-06-09 wake 1 by the §12 read-only workflow (7 agents; all 4 top hypotheses
  [MEASURED]-refuted, survivors=[]):**
  - [MEASURED] executed cup: over-bin t8.5-9 (z~1.0-1.14) → real physical excursion to [0.03,0.46,1.71] (t10) → back
    over-bin t11 → release t12.6 (late). Cube delivers (gate PASS). The swing is real.
  - [MEASURED — CORRECTION, the old [INFERRED] claim is WITHDRAWN] "branch-flip, bestd_rad=9.57 = 548°/143° sweep" was
    a **misread log value**. 9.57 is a LOGGING ARTIFACT: L1 between the `[-π,π]`-wrapped live start and the unwrapped
    IK gq (the 6.28 wrist term inflates the printed number). The cspace gq across the stepped descend differ by only
    **0.04-0.09 rad** (verified: z=0.473 vs z=0.526 max Δ=0.086) = SAME continuous branch, `cspace_ok=True`. NOT a flip.
  - [MEASURED] the z=0.473-0.632 cspace_dbg goals are a SEPARATE **DEST place-descent** (`_bin_drop_pos` bbox-top,
    drop_pos[2]~0.31), NOT the S5 release (z=1.11, single direct plan, dz<0.12 sub-step gate). So H3.2 (swing=z0.47
    descent) is structurally wrong.
  - [MEASURED] `drop_yaw` is unconditionally zeroed for suction (L6198-6204, a 2026-06-03 swing fix) → no yaw rotation
    in transit → H3.A (yaw-flip) impossible.
  - [MEASURED] the z~1.71 excursion is ABOVE every commanded waypoint (transit h1~1.03, mid~1.17, S5 release 1.11) →
    the swing does NOT match any commanded goal → **mechanism is genuinely open** (not yet [MEASURED]).
  - **NEXT EXPERIMENT (queued, fresh Kit ready):** the decisive fork — capture the cuRobo **PLANNED per-segment
    trajectory** (FK the cup) and compare to the executed grip-log. PLAN contains the up-out sweep → planning issue in
    that segment; PLAN clean but execution swings → controller/re-plan issue. This §9.3 instrument has NOT been run on
    the swing. Gated flags in code (default OFF): `_ur10_drop_branch_pin`, `_ur10_plan_cspace`, `_ur10_highpick_approach`,
    `_ur10_plan_budget_s`. Full hypothesis+refutation set: workflow `w67367qgm` output + NIGHT_MISSION ledger.
- **The 5 fails** are layout/scene/planner — §7 DEFER unless a controller-side hypothesis survives §2.

---

## 11. HYPOTHESIS LEDGER (live — expand it, never let it go empty while work remains)
Maintain this as the working set. Each entry: **ID — statement [tag] — predicted metric — test instrument — status.**
A hypothesis with no predictable number is too vague (§2.3) — sharpen or drop it. When one is refuted, mark it and
form the next. The §12 workflow feeds new ones in.

**Active problem: Fix #3 (bin swing / late release).**
> [MEASURED 2026-06-09 wake1] **H3.1/H3.2/H3.3 + H3.A/H3.B/H3.C all REFUTED** by the §12 workflow (survivors=[]). Key:
> bestd_rad=9.57 was a logging artifact (not a flip); z=0.47 is a separate DEST descend (not the swing); drop_yaw is
> zeroed for suction (no yaw-flip). See §10 (reframed) for the [MEASURED] corrections + the next experiment. The three
> seed hypotheses below are kept for the record but are DEAD — do not re-test them; the swing mechanism is OPEN.
- **H3.1** — The swing is a cuRobo IK **branch-flip** on a descend re-IK [INFERRED from cspace_dbg]. [MEASURED]
  `bestd_rad=9.57` at the first descend goal = an arm branch ~548° from start. **Predict:** scoped `plan_cspace`
  branch-pin seeded from the transit-end config (`_q_chained`) drops the descend per-joint sweep ~143°→<20° AND
  removes the over-bin→`[0.03,0.46,1.71]` excursion. **Test:** `DROPPIN=1` fresh Kit, grip-log cup trajectory — no
  `FLEW OUT` lines between OVER-BIN and release. **Status:** untested-cleanly (prior runs flag-contaminated, §3).
- **H3.2** — The **goal discrepancy** is the real lever [HYPOTHESIS]. [MEASURED] `s5goal.log` goal_world z=**1.11**
  (S5 release, correct) but `cspace_dbg` goal z=**0.473–0.632** = a SEPARATE place-descent call. The swing may live in
  the z~0.47 place-descent, NOT the S5 release. **Predict:** the `FLEW OUT` timestamps align with that call's
  execution window, not S5's. **Test:** tag both `_plan_to_world_point` call-sites with distinct log markers; correlate
  `FLEW OUT` t against which goal was active. **Status:** open — highest-value next experiment (isolates WHERE).
- **H3.3** — Late release is **downstream** of the swing, not independent [HYPOTHESIS]. [MEASURED] release fires
  t=12.6 after the arm re-settles over-bin (stable t=11.5–12.5). **Predict:** removing the branch-flip (H3.1) drops
  release t 12.6→<9.5. **Test:** DROPPIN grip-log release timestamp. **Status:** depends on H3.1.

**The 5 fails (controller-side refutation attempt first, then DEFER per §7):**
- **H81** — CP-81/82 primary cube y=0.55 unreachable [MEASURED: reach_validate 0/3]. Refute attempt: any reach at
  IKSEEDS=64 / wider ori-tol? If still 0/3 → confirmed **layout**, DEFER.
- **H71** — CP-71 dispenser items free-fall before grasp [HYPOTHESIS, scene]. Test: scene_eyes cube z at t≈0; if
  falling → spawn/physics **scene** bug, DEFER.
- **H73** — CP-73 far x≈-1.6 + gate timeout [HYPOTHESIS, layout/infra]. Test: reach_validate the pick AND raise gate
  duration separately. Reach 0/3 → **layout** DEFER; reach ok + timeout → infra.
- **H83** — CP-83 low/multi-cube reach [HYPOTHESIS]. Test: reach_validate EACH cube + scene_eyes grip.

---

## 12. HYPOTHESIS-EXPANSION WORKFLOW (launch at the START of the night, and continuously)
**At the first wake, BEFORE the first experiment**, launch a **read-only `Workflow`** that generates **N≥5 independent,
falsifiable hypotheses** for the active problem — each WITH a predicted metric AND the exact instrument that tests it
(gate / grip-log / scene_eyes / reach_validate / cspace_dbg / contacts). Agents read the codebase + the §11
[MEASURED] ledger; they **must NOT touch Kit** (single-tenant — Kit stays serial and mine). Synthesize: dedup, rank by
(testability × expected information gain), **cross-check every agent hypothesis against the [MEASURED] ledger** (an
agent's static read can be wrong — §6), append the survivors to §11.
**Re-launch the expansion whenever:** (a) ≥2 hypotheses on the active problem are refuted, or (b) the active problem
changes (fix #3 done → next template/class). The ledger must never go empty while work remains.
**Every experiment uses the FULL instrument set** (§9): gate (verdict) + grip-log cup trajectory & PhysX contacts
(behaviour) + scene_eyes cuRobo planned-trajectory (plan) + cspace_dbg/ctrl-attrs (diagnostics). A behaviour claim
with no time-series is [HYPOTHESIS], not [MEASURED].

---

## 13. AFTER 100% GATE ON THE 13 — DO NOT STOP (continuation)
When all 13 UR10 templates pass N-of-M fresh-each, **begin the SAME loop on the remaining UR10 templates and the
plate/surface ("plattor") templates** — the mission ends when the UR10 + plate library is at 100% gate or every
remaining fail is a documented [MEASURED] Anton-call, not at 13.
1. **Enumerate + baseline:** gate-sweep the remaining UR10 + plate templates fresh-each to get the pass/fail set.
2. **Root-cause each fail** via the loop: scene_eyes + reach_validate + gate; controller-side hypotheses FIRST;
   layout/scene → DEFER with a [MEASURED] handoff.
3. **Re-launch §12** per new template class to seed fresh hypotheses.
4. **Keep §5 fix discipline** — never break the now-passing set; gated, default-OFF, re-verify passers before any
   default flip.

---

---

## 14. TRACEABILITY & REVERT (the no-stop safety net — every change recoverable, nothing committed blind)
Anton's rule: **no stops at night; if something goes wrong it must be revertable and traceable.** The working tree is
already dirty with mixed in-progress work (mine + others) on branch `refactor/2026-05-12-foundation-night-1`, so a
blunt `git checkout -- <file>` would WIPE other uncommitted work. Therefore revert is **per-edit and granular**, and
traceability is a ledger + snapshots, **not** commits to Anton's branch.

**Primary safety = gating (§5).** Every change is gated default-OFF, so even an un-reverted bad edit is **inert in
production** (flags off → byte-identical). Revert is for cleanliness, not crisis. Never commit to Anton's branch
(commit only when asked).

**The protocol (follow literally):**
1. **Once, at the first wake:** `mkdir -p ~/.ur10_nightshift`; record the baseline: `git -C <repo> rev-parse HEAD`
   into the ledger (the anchor every change is traced against).
2. **At the start of every wake:** capture a full restore point of ALL uncommitted work:
   `git -C <repo> diff > ~/.ur10_nightshift/full_$(date +%Y%m%dT%H%M%S).patch`. (Reconstructs the entire delta vs
   baseline at that wake.)
3. **Before EVERY edit to a controller/hot file** (`pick_place.py` etc.): snapshot just that file —
   `cp <file> ~/.ur10_nightshift/$(basename <file>).$(date +%Y%m%dT%H%M%S).bak`. This makes the single edit
   reversible without touching any other file's changes.
4. **Revert one edit:** `cp ~/.ur10_nightshift/<basename>.<stamp>.bak <file>` (restart Kit after — handler edits need
   a fresh load, §3). Other uncommitted work is untouched.
5. **EXPERIMENT LEDGER** — append-only block in `docs/notes/NIGHT_MISSION_2026_06_07.md`, one row per change:
   `wake-time | file:line | flag introduced | before→after (one line) | [MEASURED] result | revert: <snapshot path>`.
   This is the human-readable trace; the `.bak`/`.patch` files are the machine restore points.
6. **Never flip a production default** without (a) the gated A/B proven on fresh Kit and (b) the 8 passers re-verified
   N-of-M. Flush (fix #1) is the only default-ON, already earned. Any new default-ON gets its own ledger row.

This gives Anton: every autonomous change is **traceable** (ledger + baseline sha + per-wake patch) and **revertable**
(per-file `.bak` restore), with **zero stops** and **zero commits to his branch**.

---

> The single sentence to remember: **measure first, change one thing, verify on a fresh Kit, tag every claim, and
> try to refute your own win before you call it one.**
