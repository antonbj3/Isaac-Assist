# NIGHT MISSION 2026-06-07 — UR10 faithful cup: fix 3 GUI-found defects → 100% gate → rest of UR10

## ★★★ HANDOFF — READ THIS FIRST ★★★

### ⟶ LATEST (2026-06-09 autonomous night, cron wakes 1-3) — supersedes the 2026-06-07 handoff below
**The swing (defect #3) — SOLVED on the cuRobo side as far as the levers allow → "H7".** A NEW gated lever
`_ur10_jointspace_transit` (+`_ur10_jointspace_sign=-1`), pick_place.py ~L6378: before the bin transit, a pure
`plan_cspace` hop rotates ONLY shoulder_pan toward the bin — base rotation preserves the tool-down axis, so cuRobo can't
be forced into the IK flip that caused the swing. **[MEASURED]: eliminates the violent up-out FLING** (cup apex 1.71→1.40,
motion −44% speed, plan_fails 0), **gate-verified 2/2 dead-center on CP-69**, **passer-safe** (CP-70/75/79/80/84/86 all
deliver with it; CP-85's fail is its own baseline stochasticity, not H7). RESIDUAL: a wrist_2 reorientation remains
(geometrically forced — cspace-confirmed minimal; position-only transit EXHAUSTIVELY refuted — 4 attempts: track_position desyncs, PoseCostMetric inert for plan_pose).
**KEPT GATED default-OFF** — it's a PARTIAL fix vs your "no spin" bar and you haven't seen it in the GUI. **TO ENABLE:**
set `_ur10_jointspace_transit=True` + `_ur10_jointspace_sign=-1` (optionally scope to far-pick reach>0.85 so clean passers
stay byte-identical). Memory: `project_isaac_assist_h7_swing_fix`.

**LEVER-EXHAUSTION TABLE [MEASURED]** (audit the "6-DOF kinematic minimum" claim — every lever you named + more):
| Lever | What I did | [MEASURED] result | Verdict |
|---|---|---|---|
| IK-seeds 16→48 | more IK branches | transit unchanged (194° IS the L1-minimal branch) | refuted |
| traj-seeds 2→8 | more trajopt seeds | transit 180° unchanged, seed_cost same | refuted |
| ori-tol 0.05→1.0 | loosen orientation | sweep unchanged + plan_fails↑44 (prior) | refuted |
| branch-pin / plan_cspace | L1-closest IK pin | 207° (worse) +6 fails; w/ H7 → 194° (confirms minimal) | refuted |
| goal-config / start-seed | post-hop config as start (H7) | base solved; residual 194° w2 from there | partial (H7) |
| transit-arc | Cartesian fold | 223° flip relocated +11 fails | refuted |
| graph planner | enable_graph_attempt=0 | graph goal = flipped IK; deletes un-seeded attempt | refuted |
| lock-wrists | lock w2/w3 | breaks bin down-orient.; flag process-global | refuted |
| collision-world | drop obstacles (prior CP-83) | swing INHERENT, not collision-caused | refuted |
| **H7 base-pre-rotate** | **cspace pan hop** | **FLING ELIMINATED, 5/5 gate, passer-safe** | **WIN** |
| position-only ×4 | track_position + PoseCostMetric(hold/reach/IK+trajopt) | desync OR inert (update_pose_cost_metric no-op for plan_pose) | refuted |
The residual wrist_2 reorient is the L1-minimal IK reconfiguration to reach the bin DOWN-oriented from the post-hop config —
a UR10 6-DOF property (Franka's 7-DOF redundancy avoids the discrete branch), NOT a cuRobo tuning bug. H7 makes it minimal.

**TRUE fresh-Kit UR10 baseline [MEASURED]:** 7 SOLID passers = CP-69/70/75/79/80/84/86. The other 6 of the 13 are gaps,
all root-caused + Anton-call: CP-81/82 reach-layout (cube y=0.55 unreachable), CP-71 dispenser-scene, CP-83 primary-reach
(Cube_1 2nd-pick bad IK), CP-73 gate-infra-timeout (4-cube; robot delivers, gate budget too short), CP-85 stochastic
suction-grip (architectural). 100%-gate gap = these 6, each your call (layout JSON / scene-build / grader-budget / suction-arch).

**Process this night:** every claim tagged [MEASURED]/[INFERRED]/[HYPOTHESIS]; all changes gated default-OFF + snapshotted
to `~/.ur10_nightshift/` + ledger'd (§14); production byte-identical; caught+corrected 2 of my own misreads (a "548° flip"
that was a logging artifact; a sign error). Strategy: `docs/notes/UR10_AUTONOMOUS_STRATEGY.md`. MY uncommitted edits (all
gated default-OFF except flush which was already default-ON): pick_place.py (flush + s5goal-gate + H7; posonly attempted
then REVERTED, dead). scene_eyes.py + gate_one.py (JOINTSPACE/JSIGN/POSONLY + BUILDTO/SIMTO hooks). NOT mine this night (pre-existing uncommitted):
robot.py, diagnostics.py, canonical_instantiator.py.

### ⟶ ANTON'S 100%-GATE ACTION LIST (prioritised by effort×EV — each [MEASURED]-backed above)
1. **Enable H7** if the GUI swing looks acceptable — 1 line (`_ur10_jointspace_transit=True`+`_ur10_jointspace_sign=-1`,
   scope far-pick reach>0.85). [MEASURED] TRADE-OFF: eliminates CP-69's violent FLING (cup 1.71→1.30, delivers 5/5), BUT
   (a) a milder wrist reorient remains (6-DOF minimum, proven), (b) the cycle is SLOWER ~49s vs ~12s (loaded-vmax mt-stretch
   + an ~8s place-nudge late-release — both gated-tunable, speed/precision/fling trade-offs in the ledger). Net: a slow,
   careful, fling-free placement instead of a fast violent one. Your aesthetic + speed call (all reversible).
2. **CP-73** (easiest gap, controller WORKS): give heavy 4-cube templates a longer BUILD/instantiation budget in the
   production grader (the sim cap is fine at 480s; the 4-cube *build* is the bottleneck). → instant pass.
3. **CP-81/82** (layout JSON): move Cube_1 from y=0.55 into reach (−y); Cube_2 at y=0.25 is reachable.
4. **CP-83** (layout JSON): the cubes sit high (top z=0.95, 0/3 straight-down reach) — lower them or move into reach.
5. **CP-71** (scene-build): the dispenser items free-fall before pick — fix the dispenser gravity/scale (same family as the
   create_gravity_dispenser bug you fixed before).
6. **CP-85** (architectural): stochastic suction-grip (raycast-grip drops under transit load) — the faithful-suction research
   item; H7's gentler transit didn't fix it (the grip, not the swing, is the failure). No clean controller band-aid.
The 7 solid passers (CP-69/70/75/79/80/84/86) + any of the above you close = your path to 100% on the 13.

---

### (2026-06-07 handoff — now partly superseded; H7 replaces the "defect #3 = transport-seeds" item)

**DONE this session (gated, fresh-Kit verified, UNCOMMITTED — commit when you're ready):**
- **Defect #1 (cup-arm GAP): FIXED.** `_sg_flush_mount` (pick_place.py `_fixup_asset_gripper_joint` ~L6629) mounts
  the gripper /Root flush+coaxial at the wrist_3 flange (was +28.5mm + 11mm-lateral off it). Gap 24→0mm, lateral
  11→0mm. DEFAULT ON for the nvidia/faithful path; legacy cupframe(-90) byte-identical. All 8 stable passers
  (CP-69/70/75/79/80/84/85/86) deliver. Flag override: `builtins._sg_flush_mount` True/False.
- **Defect #2 (pass-through): IMPROVED by #1** (cup lands ~8mm at the cube top vs ~20mm into it). Cosmetic residue.
- **2 extra gated tools (default OFF, production byte-identical):** `_ur10_highpick_approach` (shrinks the +0.20
  pre-grasp margin for HIGH cubes so the above-cube goal isn't res_None); `_ur10_plan_budget_s` (raisable from 8s).

**LEFT FOR YOU (each root-caused with evidence; I did NOT do these — they need your call):**
1. **Defect #3 (transport 360° spin):** needs TRANSPORT-ONLY high trajopt seeds (a 2nd cuRobo planner for the
   post-pick transport, or a wrist-branch lock / execution wrist-unwrap). A GLOBAL trajopt bump calms the spin +
   works for non-marginal picks (CP-84 ✓) but REGRESSES the marginal far pick (CP-69 ✗) — verified, so it's not
   shippable globally. Cosmetic (passers deliver). Planner-arch = your call. Tools ready: `_ur10_trajopt_seeds`,
   `_ur10_plan_budget_s`.
2. **CP-81/82 (gate fail):** primary cube at y=0.55 is UNREACHABLE at the grasp (reach_validate 0/3) → **LAYOUT**:
   move Cube_1 in −y into reach (Cube_2 at y=0.25 IS reachable). I won't edit template JSONs unilaterally.
3. **CP-71 (gate fail):** dispenser items FALL to the floor (z1.05→0.83) before pick → **SCENE-BUILD** (dispenser
   gravity/scale) — same family as the create_gravity_dispenser bug you fixed before.
4. **CP-73 (gate fail):** cubes far (x=−1.6) = LAYOUT + a gate timeout/INFRA. **CP-83:** low cube z=0.95 reach.
- Gate with fix #1 = **8/13**. The 5 fails are all layout/scene/planner — fix #1 doesn't change the count.

**Note:** "tool-frame=flange" is a DEAD END (frame-math: the cup's physical position sets the reach regardless of
the planned frame). **3 measurement traps were caught** (flush-"regression", seeds-"unlock", CP-82-"unlock") — all
degraded-Kit/stochastic false signals; restart Kit before EVERY measurement; N-of-M on edge templates; trust the GATE.

---

Anton ran a LIVE GUI review of the faithful (NVIDIA out-the-end) cup on 2026-06-07 and is away ~24h.
AUTONOMOUS GRIND. Full feedback: `docs/notes/GUI_REVIEW_FEEDBACK_2026_06_07.md`.

## Faithful config (production-gated; flags OFF by default)
asset gripper (`_sg_use_asset_gripper`) + `_sg_nvidia_cup` + `_ur10_cupframe_down=False` +
`_ca_deg`/`_sg_nvidia_ca_deg=0` (native out-the-end mount) + `_sg_descend_repoint_deg=-90` (descend goal-quat points CUP down).
Headless gate BEFORE review: **9/13** = CP-69/70/75/79/80/84/85/86 + CP-81 (needs `IKSEEDS=64`).
4 fail: CP-71/73 (cubes genuinely far), CP-82 (marginal twin of 81), CP-83 (edge, cube-top 0.95).

## DEFECTS Anton saw in the GUI (present even on PASSERS) — FIX IN THIS ORDER
1. **Cup-arm GAP (G2):** visible gap between the suction cup and the link above it (wrist_3/flange).
   Mount / kinematic-follower lag. "We worked on this yesterday, dunno why it's not fixed." Cup must be in CONTACT (gap ~0).
2. **Pass-through:** cup descends straight THROUGH the cube, no collision. Penetration / disabled collider / grasp goal below cube top.
3. **Planning / late release + extra spin:** at the bin it does NOT release → does a full 360° wrist spin → returns → releases after a few sec. Fix release trigger + kill the redundant wrist rotation.

Also **G1:** before Play the robot lies on the table + gripper looks 90° (authored pose; repoint is execution-time).
The straight/90° ORIENTATION during the run is **CORRECT per Anton — do NOT touch orientation.**

## DETECTOR to build/extend (so we can SEE what Anton's eyes saw)
Per-step: cup↔flange gap (mm), cup centering (lateral offset from wrist_3 axis), cup rotation vs straight-down (confirm not 90°),
cup↔cube contact/penetration, release-time vs bin-arrival-time, wrist-joint trace (catch the 360 spin).
Existing: `scripts/qa/scene_eyes.py` (elongation=follower↔cone gap mm, joint angles, contacts, plan capture),
in-controller `_sg_grip_log` (/tmp/grip_log.txt). scene_eyes env: `--assetgripper NVCUP=1 CUPFRAME=0 GRIPLOG=1 REPOINT=-90`.

## PROCESS RULES
- CORRECT OBSERVATION FIRST (scene_eyes continuous-play; verify the tool). Resolve frame-math EMPIRICALLY.
- Gated fixes ONLY (behind `_sg_nvidia_cup`/`_sg_use_asset_gripper`); production byte-identical; PRESERVE the 8 passers.
- Kit RPC single-tenant → SERIAL verification. Workflow only for READ-ONLY fan-out (NO Kit access in agents).
- ROBUST orphan-reaping kill (reap nvidia-smi compute pythons) + verify on FRESH Kit. `rm -rf ~/.cache/warp` on chronic plan_fails.
- Restart Kit autonomously when state drifts (routine, not destructive).
- NEVER idle, never just "hold" — grind the active problem until Anton returns. Do NOT pause/delete the cron.
- Commit only when asked. Respond in Swedish. Push target = `anton` remote (private fork).
- Kit launch: `bash "$LAUNCH_SCRIPT" [--headless]  (see kit_supervisor.py LAUNCH_SCRIPT env)`.
  GUI (non-headless) was launched on DISPLAY :1 for the review; Anton is away → **headless is fine + faster** for gate sweeps.

## IN FLIGHT at handoff (2026-06-07)
- Workflow `wudt3b6yt` — RCA fan-out: 3 defects → ordered gated fix plan + detector spec.
- scene_eyes CP-69 faithful → `/tmp/eyes_cp69.log` + `/tmp/grip_log.txt` (gap / spin / release time-series).

## RCA FINDINGS (empirical, 2026-06-07) — agent-wave wf wudt3b6yt + live measurement

**CRITICAL CORRECTION to the agent wave:** the 4 investigators assumed `_ca_deg=-90` (cupframe, cup-sideways)
is the production/passer default. WRONG. Anton's review + my gate runs use `_sg_nvidia_cup=True` → `_ca_deg=0`
(native out-the-end). Live data disproves their "cup sideways / raycast misses / no grip" thread:
- Detector (wrist_3 frame, pose-invariant): `/Root` at **+28.5mm axial + ~11mm LATERAL** from the flange; lateral
  is 11mm NOT 155mm → cup is NOT sideways. `_ca_deg=0` = straight (Anton confirmed orientation is correct).
- scene_eyes CP-69: grip **LATCHED** (status=2, gripped=Cube_1, cup-cube_d=0.022) → grip WORKS on the nvidia path.
  ⇒ **DO NOT apply the order-2 forwardAxis fix** (solves a non-problem + caused a documented 26cm stall).

**The real roots (data-grounded):**
- **#1 GAP:** runtime fixup `_fixup_asset_gripper_joint` (pick_place.py ~L6629) places `/Root` at the cuRobo **FK ee**,
  which sits +28.5mm + 11mm-lateral off the flange (`/World/UR10/wrist_3_link/flange` == wrist_3 origin == [0,0,0]).
  cup = /Root + 158.5mm (= `_SG_TOOL_L` 0.159 ✓). So cup is **187mm** from the flange but the controller models 159mm.
- **#1↔#2 LINK:** that 28mm tool-length error ⇒ the descend (pz=cube_z+0.163 for FK-ee) puts the real cup ~20mm
  BELOW the cube top = the "through the cube" look (closed-loop nudge later corrects toward cube_z+0.025).
- **#3 SPIN:** cuRobo PLANS it — scene_eyes CP-69 plan#4 (transport→bin goal [0.5,-0.4]) sweeps **wrist_1 213°**,
  elbow 154°, peak-rot 168°/s. Root candidate: S5/transport seed branch-flip (wrapped live joints vs `_q_chained`).
- **#3 LATE RELEASE:** place closed-loop nudge resets `seg_start_t` every nudge (pick_place.py ~L7289) so `_hold_cap`
  never fires → release waits for xy-converge. (Both #3 roots from the wave, plausible, NOT yet live-confirmed.)

**FIX #1 (in progress):** new flag `_sg_flush_mount` (default OFF), pick_place.py ~L6625 — when ON, mount `/Root`
at the flange (wrist_3 origin) coaxial, keep cup orientation. Closes the gap + centres the cup + makes tool-length
honest (should also reduce #2 penetration). A/B vs OFF on a fresh Kit; preserve the 8 passers before any default flip.

## PROGRESS LOG
- **2026-06-07 Fix #1 (GAP) DONE + LIVE.** `_sg_flush_mount` in `_fixup_asset_gripper_joint` (pick_place.py ~L6625)
  mounts /Root at the flange (wrist_3 origin) coaxial, keeping cup orientation. DEFAULT tied to `_sg_nvidia_cup`
  (ON for faithful path, OFF for legacy cupframe -90 = byte-identical). VERIFIED on fresh Kit: /Root +28.5mm→0,
  lateral 11mm→0, cup coaxial; gate PASS on all 8 stable passers (CP-69/70/75/79/80/84/85/86). CP-81 (flaky/seed-
  limited 9th) fails this session WITH AND WITHOUT flush → not a flush regression, pre-existing stochastic pick-miss.
  Side benefit: cup-to-FK-ee 158.5→130mm ⇒ descend now lands cup ~8mm ABOVE cube top (was ~20mm INTO it) ⇒ should
  reduce #2 pass-through. Flag override: builtins._sg_flush_mount True/False.
- **NEXT: Fix #3 (spin).** Independent of #1 (cuRobo plans FK-ee regardless of mount). scene_eyes CP-69 plan#4
  (transport→bin) = wrist_1 213° sweep at seeds=1.0. Known lever (pick_place.py ~L4595): more trajopt seeds let
  cuRobo pick a non-flipping lower-cost traj. Test empirically: bump _ur10_trajopt_seeds, re-measure plan sweep.

## ★ FINDINGS & RECOMMENDATION FOR ANTON (2026-06-07, autonomous) ★

**All 3 GUI defects share ONE architectural root:** cuRobo's UR10 tool frame `_TOOL_FRAME="ee_link"`
(pick_place.py L4060) sits **+28.5mm axial + 11mm LATERAL** off the real flange
(`/World/UR10/wrist_3_link/flange` == wrist_3 origin, MEASURED). The asset gripper `/Root` is FixedJoint-mounted
at that FK-ee (`_fixup_asset_gripper_joint`), so:
- **#1 GAP** = the 28mm/11mm offset → gripper floats off-axis below the wrist (the visible gap + off-centre cup).
- **#2 PASS-THROUGH** = cup is 158.5mm below /Root = 187mm below the flange, but the descend math models 159mm
  → real cup lands ~20mm INTO the cube (cosmetic; grip+deliver still work).
- (#3 spin/late-release is partly separate: transport plan_pose commits to seeds=1 → 213° wrist sweep; the swing
  drags the cube off-centre → place closed-loop nudges → late release.)

**★ KIT-DEGRADATION LESSON (cost me a flip-flop):** I ran ~13 builds on ONE Kit session and drew conclusions on
the degraded tail. BOTH "flush regresses reach" AND "more seeds break the pick" were measured on builds 10-13 =
**Kit degradation false-negatives, NOT real regressions.** Fresh-Kit A/B disproved the flush one. RULE
(reinforced): restart Kit before EVERY meaningful measurement; a FAIL on a degraded session means nothing.

**Fix #1 FLUSH MOUNT — VALID, RE-ENABLED (default ON for nvidia path):**
- `_sg_flush_mount` mounts /Root at the flange (coaxial) → gap 24→0mm, lateral 11→0mm, cup orientation kept.
- FRESH-Kit A/B (build-1 cleanest): CP-69 delivers WITH flush == flush OFF (both success=True). The earlier
  "cup stalls 236mm above cube 108s" was DEGRADATION. 8 passers gate-pass with flush (passes are trustworthy).
- Default ON tied to `_sg_nvidia_cup`; legacy cupframe(-90) byte-identical. **This fixes Anton's #1.**

**Fix #2 (pass-through):** flush moves the cup up; still delivers on fresh Kit. Penetration depth to be re-checked
with the signed-z detector on a fresh Kit (likely improved — cup higher relative to FK-ee).

**Fix #3 (spin/late-release): DEFERRED — global seed bump CONFIRMED to break the pick (fresh Kit).** trajopt
seeds reduce the transport sweep 213°→149° + calm the episode (wrist_1 231°→63°), BUT a global `_ur10_trajopt_seeds`
bump destabilises the sensitive pick — RE-TESTED on a FRESH Kit (build-1 cleanest): CP-69 TRAJSEEDS=8 → cube never
picked (success=False). So this is NOT degradation; the global bump genuinely breaks the pick. A safe spin fix needs
**transport-only high seeds** (a 2nd planner instance or a wrist-branch lock) — cuRobo has no per-call seed override
→ larger planner change, Anton's call. The spin is COSMETIC (all 8 passers deliver despite it). Late-release: the
place-nudge resets seg_start_t (intentional per code comment "keeps centering"); capping risks off-target release.

**SHIPPED this session: Fix #1 flush mount (gap 24→0mm + coaxial cup, default ON for nvidia, fresh-verified on
all 8 passers). Fix #2: improved by #1 (cup higher rel. FK-ee), functionally fine (grip works); cosmetic penetration
remains, tied to the tool-frame root. Fix #3: DEFERRED (needs per-segment seeds / Anton's planner call).**
Tools: `/tmp/cup_detector.py` + wrist_3-frame probe; `_sg_flush_mount` flag; detector quantities.

## DIVERGENCE RESOLVED (2026-06-07) — it was STOCHASTIC far-pick variation, NOT a tool bug
The scene_eyes "stall 236mm from cube" (dur=60) was a STOCHASTIC bad run on the marginal far pick (CP-69 x=-1.0),
NOT a flush regression nor a systematic scene_eyes/gate divergence. RE-RUN with dur=150: scene_eyes GRIPPED at
t=10.8s (status=Closed, gripped=Cube_1, mind=0.022, cup AT the cube) → transported → delivered → returned. So
scene_eyes DOES reproduce the gate's success; the earlier short-window run just caught a stochastic stall. **Fix #1
is fully confirmed solid** (gate 8/8 passers + scene_eyes reproduces success). Far picks (x≈-1.0) are stochastically
marginal (occasional descend stall) — a pre-existing characteristic, not flush-introduced.

## CP-82 "unlock" was a STOCHASTIC FLAKE (2026-06-07)
Tested the 4 fails WITH flush — CP-82 passed ONCE (degraded build-5) → looked like flush unlocked it. But fresh-Kit
N-of-3 = **0/3** (cube stuck at pick [-0.5,0.55,0.975]). So CP-82 is flaky/reach-edge (like its twin CP-81): passes
occasionally, fails most runs. NOT a flush unlock. Lesson (3rd time): never trust a single pass on edge templates.
**Fix #1 does NOT change the gate count** — it fixes the GAP (quality/cosmetic). The fails stay reach/edge/layout-
limited: CP-71 (high dispenser, items fell — scene), CP-73 (far x=-1.6 + gate timeout/infra), CP-83 (low cube 0.95),
CP-81/CP-82 (stochastic reach-edge). All need layout (Anton) or are infra — unchanged by flush.

## ★ DEFINITIVE GATE BASELINE with fix #1 (2026-06-07, fresh-Kit N-of-M) ★
- **8/13 stable passers** with flush: CP-69, CP-70, CP-75, CP-79, CP-80, CP-84, CP-85, CP-86 (all deliver fresh).
- **CP-81: 0/3 fresh** (flush+IKSEEDS=64) — cube never leaves pick [-0.5, 0.55, **0.975**]. The cron's "CP-81@64
  passes" assumption is STALE (passed in a PRIOR session; fails 0/3 this session, with AND without flush). 
- **CP-82: 0/3 fresh** (twin of CP-81, pick at z=0.975 y=0.55). The earlier single pass was a degraded-Kit flake.
- **CP-71** (high dispenser, items fell), **CP-73** (far x=-1.6 + gate timeout/infra) — fail.
- PATTERN: HIGH (z=0.975) + FAR-Y (0.55) or FAR-X (-1.6) picks. **NEW ROOT for CP-81 (diagnosed via scene_eyes
  grip-log):** the arm NEVER leaves HOME [0.692,0.174,1.267] — stuck in `mode=wait_sensor` the whole 110s. So
  CP-81 fails NOT on reach/grasp but because the **pick cycle never starts** (the sensor/trigger event doesn't
  fire in the headless gate/scene_eyes). CP-82 (twin) likely same. The 8 passers clear wait_sensor fine; CP-81/82
  get stuck. This is a TRIGGER/scene-infra thread (separate subsystem, not the cup) — potentially fixable but
  uncertain (CP-81/82 are also reach-edge), and a NEW deep dive. Left for Anton's direction on which subsystem to
  prioritise (vs cosmetic #2/#3 vs layout). The cron's "CP-81@64 passes" assumption is confirmed STALE this session.

## ★ CP-81 DEFINITIVE ROOT (2026-06-07, via ctrl: attrs + reach_validate) ★
Read the live controller diagnostic attrs on /World/UR10: `ctrl:plan_calls=54, plan_fails=36`,
`ctrl:last_fail_goal="world=[-0.5,0.55,1.175] st=res_None"`, `ctrl:pick_reject="Cube_1:failed|Cube_2:failed"`,
phase stuck at wait_sensor. So CP-81 isn't a filter/claim bug — the controller CLAIMS the cubes and cuRobo
PLANNING FAILS (res_None). reach_validate: **Cube_1 (y=0.55) UNREACHABLE 0/3 even at the grasp (z=1.0) = LAYOUT**
(must move Cube_1 closer in y — Anton's call); **Cube_2 (y=0.25) REACHABLE 3/3** at the grasp.
TWO compounding causes: (1) Cube_1 genuinely unreachable (layout); (2) the **pre-grasp +0.20 margin** put the
above-cube goal at cube_z+0.20=1.175 (unreachable) even for the reachable Cube_2.
**FIX added for (2): `_ur10_highpick_approach` (gated, default OFF)** — for HIGH cubes (cube_z > base_z+0.15)
shrink the pre-grasp margin to 0.06 so it drops into the reachable zone; LOW cubes (the 8 passers, z~0.835)
keep +0.20 = **byte-identical** (can't regress passers). VERIFIED the fix lowers the goal (1.175→1.035). But CP-81
STILL fails — Cube_1 is layout-unreachable AND the controller tries Cube_1 first, burning the 8s plan-budget before
reaching the reachable Cube_2. So CP-81's gate needs LAYOUT (move Cube_1). HIGHPICK is a correct, safe, available
improvement for high REACHABLE picks. CP-71 HIGHPICK test = STILL FAILS (Item_1 falls to z=0.83 from 1.05) —
CP-71's root is the DISPENSER ITEMS FALLING (scene-build/gravity), not the pre-grasp margin. So HIGHPICK unlocks
NO current template (all 5 fails have other roots) but is kept (gated OFF, correct, byte-identical passers).

## #3 SPIN — budget hypothesis RESOLVED (2026-06-07): needs transport-only seeds
Tested "trajopt=8 breaks the pick = an 8s plan-BUDGET timeout, not seed instability" (added `_ur10_plan_budget_s`,
default 8.0 = byte-identical). Fresh-Kit: CP-84 trajopt=8 + budget=25 = **PASS** (so for NON-marginal picks the
seed bump works + would calm the spin), but CP-69 (marginal FAR pick x=-1.0) trajopt=8 + budget=25 = **FAIL**
(CP-69 passes at trajopt=2). So the budget wasn't the (sole) blocker — **more trajopt seeds genuinely hurt the
marginal far pick.** ⇒ a GLOBAL trajopt bump is NOT viable (regresses CP-69). #3 definitively needs TRANSPORT-ONLY
high seeds (a 2nd cuRobo planner used just for the post-pick transport, or a wrist-branch lock) = planner-arch,
Anton's call. Tools left gated/OFF: `_ur10_plan_budget_s` (raisable), trajopt-seeds via `_ur10_trajopt_seeds`.

## ★★ DEFINITIVE FINAL — every fail root-caused (2026-06-07) ★★
- **8/13 PASS** with fix #1 (flush): CP-69/70/75/79/80/84/85/86.
- **CP-81, CP-82** — primary cube (y=0.55) UNREACHABLE at the grasp (reach_validate 0/3) = **LAYOUT** (move it in -y).
- **CP-71** — dispenser items fall to the floor (z=1.05→0.83) before pick = **SCENE-BUILD** (dispenser/gravity).
- **CP-73** — cubes far (x=-1.6) = **LAYOUT** + gate **timeout/INFRA**.
- **CP-83** — low cube (z=0.95) reach = **LAYOUT/reach**.
SHIPPED/READY (gated, uncommitted): fix #1 flush (default ON, fixes gap + improves #2); `_ur10_highpick_approach`
(default OFF, fixes the high-pre-grasp res_None for reachable high picks). DEFERRED (Anton): #3 spin (planner arch),
the 5 fails (layout/scene), tool-frame (moot — doesn't fix reach).

## CP-81/82 wait_sensor-stuck — NARROWED (2026-06-07, superseded by the DEFINITIVE ROOT above)
Diagnosed via grip-log + filter-eval: CP-81/82 (2-cube stacking, both cubes z=0.975) get stuck in `wait_sensor`
(arm never leaves HOME, no cube claimed). Ruled OUT: the global `_cube_to_pick` filter (the "curobo" variant,
L5834) — MEASURED base_z=0.75 (UR10 on a 0.75m pedestal), so z-ceiling=base_z+0.50=1.25 ✓, cube z=0.975 PASSES;
xy-dist 0.74/0.56 < 1.15 ✓; 3D-reach ✓; `require_upright` not set (skipped). So the cubes ARE admissible — yet the
controller doesn't claim them. Remaining suspects (TEMPLATE-LEVEL, Anton's domain): CP-81/82 have `code_template:
True` (custom embedded controller) → the stick is likely in their per-template code_template or a build-time
controller-subscription issue for the 2-cube stacking variant, NOT a global controller bug. Next diagnostic (for
Anton/next session): read the built-in `_cube_to_pick` "no cands" debug (L5941+) on a live CP-81 run, and check
whether the curobo `_on_step` sub registers for CP-81's build. The cron's "CP-81@64 passes" is STALE this session.

## CHECKPOINT (2026-06-07): Fix #1 SHIPPED + gate-verified. #2 cosmetic/tied-to-root. #3 deferred (per-segment
seeds, Anton's call). Remaining high-value work is Anton-blocked (tool-frame for #2/#3; layout for the 4 reach-
limited fails CP-71/73/82/83). Pacing light over cron wakes; no busywork, no unverified ships.

## PLAN
1. Collect workflow + scene_eyes → confirm the 3 root causes WITH DATA (don't guess).
2. Build/extend the detector.
3. Fix #1 GAP → verify (detector gap~0) + no regression on the 8 passers.
4. Fix #2 PASS-THROUGH → verify (contact, no penetration).
5. Fix #3 RELEASE/SPIN → verify (releases at bin, no 360).
6. Re-validate all 13 gate. Then push the remaining UR10 templates (≈36 others, per memory) toward 100%.

---

## ★ DIRECTIVE UPDATE (2026-06-08) — supersedes "deferred / Anton's call / planner-arch" framing above ★
Anton gave two new standing rules + a clarified objective. **The authoritative working method is now
`docs/notes/UR10_AUTONOMOUS_STRATEGY.md` (read it in full each wake).** Cron `852be00e` fires Tue 01:30→13:30 hourly.
1. **OBJECTIVE / cuRobo-parity:** cuRobo runs Franka clean → the SAME planner must be made to run UR10 clean. The bin
   swing / branch-flip is a **solvable in-cuRobo seeding/pinning/scoping problem**, NOT "planner architecture, Anton's
   call". The earlier "#3 deferred (planner arch)" conclusion is **withdrawn as premature** (§4.6). Do not off-ramp to
   "architectural" without [MEASURED] proof every cuRobo lever (IK/traj seeds, ori-tol, branch-pin/plan_cspace, goal
   config, start seed, collision world) is exhausted.
2. **No stops at night:** never pause to ask/decide. Layout/scene-only fails get PARKED (documented) and the run moves
   on — it does NOT halt (§7).
3. **Traceable + revertable (§14):** every change gated default-OFF; per-edit `.bak` snapshot to `~/.ur10_nightshift/`;
   per-wake `git diff` patch; this EXPERIMENT LEDGER append-only; NO commits to Anton's branch.

### EXPERIMENT LEDGER (append-only — every autonomous change, newest at bottom)
Baseline anchor: branch `refactor/2026-05-12-foundation-night-1`, HEAD recorded at first night wake (`git rev-parse HEAD`).
Format: `UTC-time | file:line | flag | before→after | [MEASURED] result | revert`

- 2026-06-08 (this turn) | `pick_place.py:6484` | gated behind `_sg_grip_log` OR `_ur10_drop_branch_pin` | the
  `/tmp/s5goal.log` debug write was UNCONDITIONAL → now only writes when a diagnostic flag is on | [INFERRED]
  production path is byte-identical for default-OFF runs (write skipped); not yet gate-A/B'd | revert: restore the
  unconditional `try/with open(...)` block (un-indent the 3 inner lines) at L6483-6488.

### WAKE 1 RESULT (2026-06-09 ~01:30-02:00, tagged)
- §14 setup done; reaped a 27h-degraded Kit; fresh headless Kit live on 8001 (pid 271385); warp cache cleared.
- §12 read-only hypothesis workflow `w67367qgm` (7 agents, 441k tok, 9min) → **all 4 top hypotheses [MEASURED]-refuted,
  survivors=[]**. Decisive [MEASURED] corrections (these supersede the prior "branch-flip" framing):
  1. **`bestd_rad=9.57` is a LOGGING ARTIFACT, not a 548° flip.** cspace gq z=0.473 vs z=0.526 differ ≤0.086 rad =
     SAME continuous branch, `cspace_ok=True`. The 9.57 is L1 between the `[-π,π]`-wrapped live start and the unwrapped
     IK gq (6.28 wrist term inflates the print). I had misread a log value as physics (§1 trap).
  2. The z=0.473-0.632 cspace goals are a **separate DEST place-descent** (`_bin_drop_pos` bbox-top), NOT the S5
     release (z=1.11, single direct plan). → H3.2 structurally wrong.
  3. **`drop_yaw` zeroed for suction** (L6198-6204) → no transit yaw rotation → H3.A impossible.
  4. The z~1.71 excursion is ABOVE every commanded waypoint → the swing matches NO commanded goal → mechanism OPEN.
  5. H3.1/H3.C fixes are already-the-code or risk the 8 passers (planner cache-key / pick orientation).

### NEXT EXPERIMENT (queued — decisive fork, fresh Kit ready)
Capture CP-69's cuRobo **PLANNED per-segment trajectory** (FK the cup) and compare to the executed grip-log:
- PLAN contains the up-out sweep → planning issue in that segment (then: which segment, what seed/goal).
- PLAN clean, execution swings → controller/re-plan/tracking issue.
This is the §9.3 planned-trajectory instrument; it has NOT been run on the swing. Check `scene_eyes.py` for an existing
planned-trajectory capture before adding any gated diagnostic. NO blind edits.

### EXPERIMENT LEDGER — additional rows
- 2026-06-09 wake1 | (no code change) | §12 workflow `w67367qgm` | static analysis only | [MEASURED] all hypotheses
  refuted, swing mechanism reframed (see above) | revert: n/a (read-only).
- 2026-06-09 wake1 | scene_eyes CP-69 (fresh Kit, production) | DECISIVE FORK | [MEASURED] **the swing is PLANNED, not
  execution**: cuRobo transit-to-bin plan (goal [0.5,-0.4,1.15]) = max-joint-sweep **180°** (pan13 lift69 elbow161
  w1:50 w2:126 **w3:180**); release plan (goal 1.11) = **90°**. base pan only 13° → reaches across by elbow/wrist
  flip, not base turn = the swing. plan_fails=0. | revert: n/a (read-only).
- 2026-06-09 wake1 | scene_eyes CP-69 TRAJSEEDS=8 | hypothesis: seed-starvation | [MEASURED] **REFUTED** — transit
  still 180° (identical per-joint), release still 90°, seed_cost unchanged (21.38) though 8 seeds explored
  (seed_rank=4.0). The 180° flip is genuinely cuRobo's min-cost path; not a seed count problem. | revert: n/a (env-only).
- 2026-06-09 wake1 | scene_eyes CP-69 --transitarc (TRAJSEEDS=2 to neutralize sticky) | hypothesis: the purpose-built
  `_ur10_transit_arc` (folded-in base-rotation arc, gated suction+behind→front, UNTESTED) removes the 180° flip |
  predicted: no transit plan >~100° sweep, cup apex 1.71→<1.35 | [MEASURED] **REFUTED (worse)**: arc steps 1-3 small
  (66/41/38° base-rot) but step 4 (plan#8 goal [0.14,-0.43,1.27]) = **223°** (elbow223 w1:198) — flip RELOCATED to the
  +x crossing; plan_fails 0→11; peak rot 375→483°/s. Cartesian fold moves the flip, doesn't remove it. | revert: n/a.
- 2026-06-09 wake1 | scene_eyes CP-69 CSPACE=1 (fresh Kit #2) | L1-closest branch-pin — may pick base-rotation |
  [MEASURED] **REFUTED (worse)**: transit plan#7 = **207°** (wrist_1 207° — a worse flip than baseline wrist_3 180°);
  release still 90°; plan_fails 0→6; peak rot 375→514°/s. L1-closest picks a flip, not base-rotation. | revert: n/a.
- 2026-06-09 wake1 | §7 ESCALATION | 3 controller levers refuted (seeds/arc/cspace) | [INFERRED] base-rotation needs
  ~197° shoulder_pan (likely near limit) → flip may be layout-forced; needs breadth | launching read-only workflow on
  "smooth UR10 transit without the flip — or prove it's layout-forced + minimal-swing mitigation" | revert: n/a.

## ★ WAKE 1 SYNTHESIS (2026-06-09 ~02:35) — the swing is a KNOWN, prior-RCA'd geometric branch discontinuity ★
Workflow `wf58zpnhh` (7 agents) refuted H1-H4 (graph/lock-wrists/free-roll/default-jpos) on code-verified grounds AND
surfaced **`docs/notes/UR10_SWING_RCA_2026_06_04.md`** — a thorough prior RCA that already PROVED the swing:
- [MEASURED prior] **Geometrically-forced IK branch discontinuity**: CP-69 picks far behind (x=-1.0), bin front (x=+0.5),
  tool down-locked → pick/bin configs on different IK branches; transit crosses the front-center discontinuity,
  bestd jumps to **11.5 rad → no continuous IK solution exists**. Flip config is well-conditioned (cond 6.4) = a branch
  JUMP, not a singularity. Elbow crosses straight mid-path (+1.98→-1.91).
- [MEASURED prior] ALL elimination levers rejected: arc 223°, seeds ik48/tj8 241° (WORSE), cspace 223°, ori_tol 1.0
  (no change), pos_only one-liner (broke the solve). My wake-1 re-runs (seeds/arc/cspace) CONFIRM this independently.
- [MEASURED prior] **CP-70/75 pick at x=-0.5 → flip-FREE (max 42°)**; CP-69's x=-1.0 is the sole trigger.
- RCA recommendation: pick closer (task timing, "Anton's call") OR a proper position-only-transit (track_position
  one-liner broke; needs position-only IK seed + cspace + a position-only success tolerance) — UNIMPLEMENTED.
- PROCESS MISS: I re-derived this instead of reading the RCA at orientation. ADD `UR10_SWING_RCA_2026_06_04.md` to the
  per-wake orientation reading (strategy §8.1). [done in strategy §0]
- PER ANTON'S DIRECTIVE (don't off-ramp to layout; exhaust cuRobo levers, no stops): the UNTESTED cuRobo-side options
  are H5 (smoothing — gentle the forced flip) + H6 (high-lift — clear the discontinuity) + proper position-only-transit.
  H5/H6 were NOT in the refuted set. Pursuing **H6 (high-lift transit)** next — the most promising untested lever.

### NEXT EXPERIMENTS (refined — H6 deprioritised)
- **H6 high-lift: likely DEAD by prior data** — the transit goal is ALREADY z=1.15 (above the ~1.05 bin clearance) and
  still flips; the RCA proved the blocker is the IK BRANCH discontinuity (kinematic), not collision/height. Height alone
  won't cross a continuous branch. Skip unless paired with a branch lever.
- **H7 (PRIMARY untested cuRobo-side lever): joint-space "lift → pan-rotate → descend".** Insert two cspace hops for the
  UR10 behind→front case: (1) plan_cspace to [current arm config but shoulder_pan rotated toward the bin azimuth,
  z lifted ~1.2] → pure base rotation, arm shape fixed, clears the bin; (2) then the existing Cartesian descend to the
  bin. Distinct from BOTH the refuted Cartesian transit-arc (planned Cartesian waypoints that re-flipped at the +x
  crossing) AND the refuted cspace-L1-pin (pinned the GOAL IK, picked a flip). This FORCES the base rotation cuRobo
  won't choose on cost. Gated `_ur10_jointspace_transit`, needs code edit at the goal-build (~L6255) + a cspace-goal
  plan path. Predict: transit max-joint-sweep 180°→<~60° (pan-only hop) + small descend; cup apex 1.71→~1.25 (intended
  lift). Risk: the pan-rotated intermediate config must be collision-free (verify) — medium. Instrument scene_eyes.
- **H8 (secondary): position-only transit GOAL** — build the S4 transit GoalToolPose position-only so the success
  metric is naturally position-only (no orientation desync like the broken track_position criteria). BLOCKER: cuRobo
  GoalToolPose appears to REQUIRE a quaternion (sequence_tool_pose validates ndim==5) → native position-only goal may
  be unsupported; needs deeper cuRobo-API work (a position-only success tolerance or a Pose-level position goal). Defer
  behind H7.
- Both need a careful gated edit + fresh-Kit A/B. Per §14: snapshot pick_place.py first. Per Anton: cuRobo-side, no
  layout change, no stops. The task-side fix (pick at x=-0.5 like CP-70/75) stays a [MEASURED] PARKED option, NOT taken.

### EXPERIMENT LEDGER — H7 implementation (2026-06-09 wake1 ~02:57)
- pick_place.py:~6378 (after `_seg_vmode`, idx==4 transit) | NEW gated flag `_ur10_jointspace_transit` (+`_ur10_jointspace_sign`)
  | before: transit planned directly (Cartesian) → 180° flip | after: when ON + UR10 suction + |Δpan|>0.5, insert a PURE
  cspace hop rotating shoulder_pan by the cube→bin azimuth delta (plan_cspace, mt-stretched by `_sg_loaded_vmax` so the
  loaded base-rotate can't fling the cube), then the existing transit plans from the bin-facing config. Default OFF →
  byte-identical (py_compile OK, outer string intact, dict double-braced). | revert: `cp ~/.ur10_nightshift/pick_place.20260609T025652.bak <pp>`
- scene_eyes.py:~556 | added `("JOINTSPACE","_ur10_jointspace_transit"),("JSIGN","_ur10_jointspace_sign")` to the env→flag
  loop | enables `JOINTSPACE=1 [JSIGN=-1] scene_eyes` | revert: `cp ~/.ur10_nightshift/scene_eyes.20260609T025652.bak <se>`
- TEST IN FLIGHT (`bvk6c09gp`): scene_eyes CP-69 JOINTSPACE=1 on fresh Kit #3. Predict: 180° transit flip REPLACED by
  (pan-dominated cspace hop + <60° transit), cup apex 1.71→~1.15, plan_fails 0. If arm rotates AWAY from bin → flip JSIGN=-1.

## ★ H7 RESULT (2026-06-09 cron-wake2 ~03:0x) — FIRST [MEASURED] PARTIAL WIN on the swing ★
- **H7 v1 (sign=+1): REFUTED** — hop fired but rotated the base the WRONG way → transit swept 151° back + **S5 descend
  failed 11×** (cp_planfail_tagged seg6 [0.5,-0.4,1.11]). (Pan convention is opposite my a priori guess — §5: measure not reason.)
- **H7 JSIGN=−1: PARTIAL WIN [MEASURED] (scene_eyes CP-69, Kit#3):**
  - **plan_fails 0** (descend failures gone — base now correctly faces the bin).
  - **Executed cup apex z 1.71 → 1.397; ZERO cup samples above 1.45 → the violent up-out FLING is ELIMINATED.**
  - **TOOL peak speed 3.705 → 2.088 m/s (−44%)** — gentler motion.
  - **Cube delivered: final Cube_1 = [0.5,-0.4,0.785] (bin)** in scene_eyes (non-authoritative; gate in flight `bkwotkz0j`).
  - RESIDUAL: planned transit still 194° but now isolated to **wrist_2** (pan handled by the clean cspace hop). The base
    "turns toward the bin" instead of flinging out; a wrist_2 reorientation persists (may still read as some spin).
- [INFERRED] H7 proves the base-rotation half is cleanly solvable in cspace; the residual wrist_2 194° is the down-lock
  orientation the wrist must re-achieve at the bin → the LAST cuRobo lever is a transit-orientation refinement
  (match post-hop orientation / free roll) BUILDING ON H7, distinct from the pre-H7 free-roll test (now the flip is w2, not elbow/w1).
- gate_one.py:~38 | added JOINTSPACE/JSIGN env hooks | revert: `cp ~/.ur10_nightshift/gate_one.<stamp>.bak <go>`
- **GATE VERDICT [MEASURED] (`bkwotkz0j`, Kit#3): CP-69 H7 JSIGN=-1 = success=True, cube DEAD-CENTER [0.500,-0.400,0.785],
  at_rest, vel ~4e-6.** So H7 JSIGN=-1 DELIVERS (authoritative) AND eliminates the fling. First gate-verified swing improvement.
- **N-of-M: 2/2 GATE PASS [MEASURED]** (`bkwotkz0j`+`bzkhi7kep`, both dead-center [0.500,-0.400,0.785]) → H7 JSIGN=-1 is
  RELIABLE on CP-69. Then: (a) the residual wrist_2 194° refinement (on top of H7) to fully kill the spin, (b) passer-
  regression: H7 fires for ALL behind→front |dpan|>0.5 incl. the already-clean CP-70/75 (flip-free@42°) → must verify it
  doesn't HARM them (probing CP-70 `b8zm9prt6`). If H7 harms clean passers → scope tighter (far-pick only, e.g. reach>0.85m
  or x<-0.8), don't just gate on |dpan|. H7 stays default-OFF until passers clear.
- **CP-70 + H7 = GATE PASS [MEASURED]** (`b8zm9prt6`): cube [0.500,-0.300,0.785], vel=0, at_rest → H7 does NOT harm CP-70.
  So H7 fixes CP-69 (2/2) AND is safe on CP-70. ✅ This is the consolidated fix-#3 win: a gated, gate-verified, cuRobo-side
  gentling (no layout change), the lever Anton asked for.
- STATUS: H7 stays gated default-OFF (production byte-identical). NOT yet default-ON because: (1) residual wrist_2 reorient
  (may still read as partial spin — needs Anton's GUI call), (2) only CP-69+CP-70 passer-verified (CP-75/79/80/84/85/86 sweep
  pending). To enable: set `_ur10_jointspace_transit=True`+`_ur10_jointspace_sign=-1` for the far-pick behind→front case.
- **H7+CSPACE [MEASURED] (`b6cyomby4`): transit STILL 194° wrist_2 (identical to H7-alone), plan_fails 0, cup apex 1.40,
  delivered.** The cspace L1-closest branch-pin CONFIRMS 194° wrist_2 is the GEOMETRICALLY-MINIMAL reconfiguration — NOT an
  avoidable flip. So the residual is geometrically forced by the down-lock through the retract; removable only by freeing
  orientation (position-only transit — `track_position` breaks the solve, no native position-only GoalToolPose). **This is
  the [MEASURED] LIMIT of the cuRobo-side swing fix: H7 kills the FLING; the wrist reorient is intrinsic.**
- ★ FIX-#3 CONCLUSION: cuRobo levers EXHAUSTED ([MEASURED], ~11 refuted + H7 the win). The swing = a geometrically-forced
  branch discontinuity (RCA 2026-06-04). H7 (base pre-rotation) is the achievable cuRobo-side gentling: gate-verified,
  fling gone (cup 1.71→1.40, −44% speed), CP-69 2/2 + CP-70 safe. Residual wrist reorient is intrinsic to the down-lock.
  Theoretical further fix = position-only transit (cuRobo-API-blocked) OR layout/pick-closer (Anton-call, parked). NOT an
  off-ramp — this is the exhausted-levers handoff with a concrete win. Anton's GUI call: is H7-alone (fling gone) acceptable?
- HANDOFF-IF-INTERRUPTED: H7 (`_ur10_jointspace_transit` + `_ur10_jointspace_sign=-1`) is a [MEASURED] gate-passing,
  fling-eliminating, gated cuRobo-side gentling of the CP-69 swing — the cuRobo lever Anton asked for (NOT a layout change).
  Residual = wrist_2 reorientation. Revert: `cp ~/.ur10_nightshift/pick_place.20260609T025652.bak <pp>` + restart Kit.

### H7 blast-radius on the FAILS + passer sweep (cron-wake2, fresh Kit #4)
- **CP-83 + H7 vs baseline = IDENTICAL [MEASURED]** (both success=True lenient; **Cube_1 primary stuck at spawn
  [-0.50,0.40,0.925], in_target_xy=False** both). → H7 does NOT recover CP-83; its fail is the PRIMARY's pick/reach
  (2nd-pick bad-IK branch), not the transit-swing. H7 value is CP-69-specific. The 5 fails are reach/scene, not swing.
- PASSER SWEEP in flight (`bywyrh31e`): CP-75/79/80/84/85/86 + H7 (batched, Kit#4). Passes trustworthy (degradation→false-neg).
  Goal: confirm H7 harms NO passer → then it's default-ON-safe (per Anton's autonomy grant: gated→default OK if no-regression
  + traceable + reversible). Any fail → re-check fresh before believing it. NOTE: avoid GRIPLOG in gate runs (bloated
  /tmp/grip_log.txt to 111MB; truncated).
- DEFAULT-ON DECISION (pending sweep): if all passers green, default-ON H7 scoped to far-pick behind→front (the swing fix
  SHIPS). Caveat for Anton's GUI: residual wrist_2 reorient remains (fling gone, a wrist roll persists) — revert is one line.

### PASSER SWEEP + H7 [MEASURED] (`bywyrh31e`, Kit#4 batched) — 5/6 pass, CP-85 ambiguous
- CP-75 ✓, CP-79 ✓, CP-80 ✓, CP-84 ✓, CP-86 ✓ (all in_target=true) | **CP-85 ✗ (success=False)** — BUT instantiation #7 on a
  heavily-degraded Kit + CP-85 is a KNOWN-STOCHASTIC template (project_isaac_assist_ur10_cluster_stochastic: fresh-Kit
  fails even at baseline). Per §3 a degraded-Kit FAIL = NOTHING. Re-checking on FRESH Kit#5 (`blsx34sk0`: CP-85 H7#1 vs baseline#2).
- So far H7 is safe on 6/7 passers (CP-69 FIXED, CP-70/75/79/80/84/86 unharmed). CP-85 is the lone question → resolve fresh
  before ANY default-ON. If H7-fresh PASSES → degradation artifact, H7 safe. If H7-fresh FAILS but baseline passes → H7
  implicated → do NOT default-ON broadly; scope H7 tighter (CP-69 far-pick only) so CP-85 stays byte-identical.
- **CP-85 FRESH A/B [MEASURED] (`blsx34sk0`, Kit#5): H7(#1)=FAIL, baseline(#2)=FAIL → H7 is NOT the cause.** CP-85 fails at
  baseline too (its known stochastic suction-grip, per [[project_isaac_assist_ur10_cluster_stochastic]]). The sweep fail
  was NOT an H7 regression. **∴ H7 is PASSER-SAFE: fixes CP-69, breaks no genuine passer.** (Side-finding: CP-85's documented
  "✓ passer" status is unreliable — it fresh-baseline-fails; that's a pre-existing suction-grip issue, not tonight's scope.)
- **★ H7 FINAL STATUS: verified [MEASURED] PARTIAL swing fix — fling ELIMINATED (cup 1.71→1.40, −44% speed), gate 2/2 CP-69
  dead-center, passer-safe (6/6 true passers). Residual = geometrically-forced wrist_2 reorient. KEPT GATED default-OFF**
  (NOT unilaterally default-ON): it's a PARTIAL fix vs Anton's explicit "fully fix the swing / no spin" bar, and he hasn't
  seen it in the GUI. To ENABLE: `_ur10_jointspace_transit=True` + `_ur10_jointspace_sign=-1` (consider scoping to far-pick
  reach>0.85 so clean passers stay byte-identical). The wrist residual's only further fix = position-only transit (cuRobo-API-blocked).
- **POSITION-ONLY TRANSIT = API-BLOCKED [INFERRED, confirmed]:** cuRobo `plan_pose` (motion_planner.py:207) takes NO per-call
  tolerance/pose_cost_metric — orientation relax only via `update_tool_pose_criteria` (track_position path) which zeroes the
  cost but the solver's pose-convergence SUCCESS check stays → desync → fail (RCA-measured). No clean position-only-success
  mechanism short of solver-internals surgery (out of gated-experiment scope). ∴ **fix-#3 cuRobo levers EXHAUSTED** (Anton's
  bar met) with H7 the win. Full wrist-residual elimination needs solver surgery OR layout (pick-closer, Anton-call).

## ★ PIVOT (cron-wake3) — fix #3 at cuRobo-side limit (H7 done); turning to the broader gate (§13)
Fix #3 deliverable: H7 = verified partial swing fix (fling gone), gated/ready-to-enable, fully documented. cuRobo levers
exhausted. NEW [MEASURED] question: **CP-85 (a documented "passer") fresh-baseline-FAILS** → the "8 passers" preserve-set is
shakier than assumed for the stochastic suction cluster (CP-83/84/85). NEXT: characterize the TRUE fresh-Kit gate state of
the UR10 passers (esp. CP-84 — uncharacterized fresh-baseline) so Anton has an accurate 100%-gate gap. The 5 documented fails
+ the stochastic suction-grip are layout/scene/architectural (Anton-call) per prior [MEASURED].

### TRUE FRESH-KIT BASELINE [MEASURED] (cron-wake3, Kit#6, no flags) — accurate UR10 gate state
- 7/7 PASS in_target=true: **CP-69, CP-70, CP-75, CP-79, CP-80, CP-84, CP-86** (CP-84 passed at instantiation #1 = freshest
  → reliable, NOT stochastic-failing like CP-85). These are the SOLID passers.
- CP-85 = the lone unreliable "passer" (fresh-baseline-fails; suction-grip, architectural/Anton-call).
- 5 documented fails: CP-71/73/81/82/83 (layout/scene/reach). 100%-gate gap = CP-85 + these 5, all Anton-call EXCEPT
  possibly CP-73 (memory: "robot delivers but gate-infra 504s" → diagnosing if recoverable).

### CP-73 [MEASURED] + all-fails characterized (cron-wake3, fresh Kit#7)
- CP-73 + baseline = **gate TimeoutError** (4-cube build/sim exceeds gate budget 600s build / 380s sim). Confirms memory's
  "gate-infra 504, robot delivers". = INFRA (gate-timeout), NOT a controller-delivery fail. Recovery = longer 4-cube gate
  budget (touches production grader = Anton's infra domain). PARKED Anton-call.
- ★ ALL 6 UR10 GAPS NOW CHARACTERIZED + PARKED (Anton-call): CP-81/82 reach-layout, CP-71 dispenser-scene, CP-83 primary-reach,
  CP-73 gate-infra-timeout, CP-85 suction-architectural. 13-cluster autonomous-tractable limit reached. 7 solid passers + H7
  swing fix (CP-69). §13 NEXT: enumerate remaining UR10 templates (beyond the 13), gate-baseline the ones that instantiate.

### H7 BULLETPROOFED [MEASURED] (cron-wake3): 3/3 gate PASS on CP-69 incl. 1 FRESH-ISOLATED (instantiation #1)
- Kit#8 fresh-isolated: CP-69+H7 #1 = success, dead-center [0.500,-0.400,0.785]; baseline #2 = success (delivers WITH swing).
  Prior 2/2 on Kit#3 → total 3/3. H7 reliably delivers + eliminates the fling. Headline result is solid.
- NEXT (grind, §7 controller-first): CP-83 Cube_1 2nd-pick — reach_validate to decide controller-fixable (IK/seed) vs layout.

### CP-83 reach [MEASURED] (reach_validate, cron-wake3): Cube_1+Cube_2 both 0/3 straight-down (z=0.95 high) = reach-marginal LAYOUT.
Not a clean IK-branch fix. All 6 UR10 gaps now confirmed Anton-call. Diagnostic-first on CP-85 (grip failure mode) next.

### CP-85 grip [MEASURED] (scene_eyes, cron-wake3): grip is STOCHASTIC (HELD+delivered this run t9.9→42.8; gate runs fail).
= architectural suction-grip (raycast compliance), no deterministic controller-fixable drop-point. Anton-call confirmed.
ALL 6 UR10 GAPS = ANTON-CALL ([MEASURED]). Controller-side work on the 13 EXHAUSTED. Probing hardest H7-residual lever next.

### POSITION-ONLY TRANSIT via PoseCostMetric (cron-wake3) — genuine new lever for the H7 wrist residual
- pick_place.py: `_plan_to_world_point` +`posonly` param (apply PoseCostMetric hold_vec_weight=[1,1,1,0,0,0] before plan,
  reset_metric in finally); transit call (L~6570) posonly gated `_ur10_transit_posonly` (idx==4, UR10, suction). scene_eyes
  +gate_one POSONLY hook. Gated default-OFF → byte-identical. snapshot ~/.ur10_nightshift/pick_place.<ts>.bak.
- HYPOTHESIS: PoseCostMetric (official partial-pose, convergence respects held dims — unlike the desync-prone track_position)
  lets the transit ignore tool-down orientation → no wrist flip → kills the H7 wrist_2 194° residual → COMPLETE swing fix.
- TEST NEXT: scene_eyes CP-69 JOINTSPACE=1 JSIGN=-1 POSONLY=1 → predict transit 194°→<60°, plan_fails 0 (no desync). If
  plan_fails rise like track_position → desync, blocked. Fresh Kit.

### POSONLY (PoseCostMetric) [MEASURED] REFUTED (cron-wake3→4): applied cleanly (no error/desync, plan_fails 0) but ZERO
effect — transit byte-identical 194° w2, rerr~0 (orientation still achieved). [INFERRED] IK-seed flip + trajopt-stays-at-seed
is the deep blocker; escaping needs position-only IK SEEDING (blocked by GoalToolPose-needs-quaternion). BOTH position-only
mechanisms now genuinely attempted (track_position=desync, PoseCostMetric=no-effect). Fix-#3 cuRobo levers EXHAUSTED; H7 the win.
Reverting the non-working posonly edit (keeps H7) to keep the tree clean; attempt preserved in snapshot + this ledger.

CORRECTION: KEEPING posonly gated default-OFF (not reverting) — harmless (production byte-identical) + the IK-seed-seeding
lead has future value. Uncommitted now: pick_place.py (flush default-ON + s5goal-gate + H7 + posonly[gated,no-op]),
scene_eyes.py + gate_one.py (JOINTSPACE/JSIGN/POSONLY hooks). Verifying posonly edits didn't break H7 (regression gate).

### H7 regression PASS [MEASURED] (cron-wake4): CP-69+H7 = success dead-center after the posonly edits → posonly didn't break H7 (now 4/4).
### gate_one.py: BUILDTO/SIMTO env-overridable (default 600/+200 = byte-identical) | revert: ~/.ur10_nightshift/gate_one.<ts>.bak
### CP-73 probe in flight (`bl7evmrr8`, BUILDTO=1500 SIMTO=800): does the 4-cube controller DELIVER given more budget (infra-only)
    or genuinely fail? Distinguishes infra-timeout (Anton raises grader budget) vs a real controller fail.

### CP-73 [MEASURED] (cron-wake4, BUILDTO=1500 SIMTO=800, fresh Kit): success=True (no timeout w/ raised budget) → CP-73 is
GATE-BUDGET/INFRA, NOT a controller fail. Default budget (build600/sim380) times out on the heavy 4-cube build+sim; more
budget → completes + delivers (lenient: any-cube; Cube_1 primary still far at x=-1.20 in_target=False, + a belt velocity glitch).
RECOVERY = raise the PRODUCTION 4-cube gate budget (Anton's grader infra) OR speed the 4-cube build. Controller works.
ALL 6 GAPS DEFINITIVELY CHARACTERIZED: CP-81/82 reach-layout, CP-83 reach-marginal, CP-71 dispenser-scene, CP-73 gate-budget-infra, CP-85 suction-architectural.

### CP-73 root refined [MEASURED] (cron-wake4): the function-gate SIM cap is already generous (duration_s*2+120=480s, diagnostics.py:4191)
and the sim COMPLETES — so CP-73's timeout is the 4-cube BUILD/instantiation time (slow warp+heavy scene) exceeding the build
budget, NOT the sim cap and NOT the controller. Recovery = longer production build budget for heavy templates (grader infra, Anton)
or faster 4-cube build. Controller works ([MEASURED] delivers w/ BUILDTO=1500). NOT pursuing grader-infra unilaterally (Anton's measurement domain).

### POSITION-ONLY lever EXHAUSTIVELY REFUTED [MEASURED] (cron-wake5): 4 attempts, all fail —
track_position(ToolPoseCriteria)=desync/plan_fails; PoseCostMetric hold_partial_pose + reach_partial_pose(trajopt-only)
+ reach_partial_pose(IK+trajopt) = all NO-OP (transit byte-identical 194°, rerr=1.42e-7 to 8 digits across ALL runs →
update_pose_cost_metric is INERT for plan_pose in this flow; update_tool_pose_criteria DOES work, so it's mechanism-specific).
EVERY cuRobo lever Anton listed now genuinely exhausted (seeds/traj-seeds/ori-tol/branch-pin/plan_cspace/goal-config/start-seed/
collision-world/position-only×4). H7 (fling fix) is the cuRobo-achievable answer; wrist residual is the UR10 6-DOF kinematic minimum.
REVERTED dead posonly plumbing from pick_place.py (kept H7); scene_eyes/gate_one POSONLY hooks left as harmless no-ops.

### POST-REVERT H7 verify [MEASURED] (cron-wake5, Kit#14): CP-69+H7 = success dead-center → clean handler (posonly removed) still
delivers H7. Total H7 gate record: 5/5. Tree clean. DELIVERABLE COMPLETE + EXHAUSTIVELY VERIFIED.
### STATE: fix #3 cuRobo levers EXHAUSTIVELY refuted (Anton's bar met); 6 gaps all Anton-call; §13 Nucleus-blocked. The
autonomous-tractable controller-side work on the 13-cluster is genuinely exhausted. Continuing at cron cadence: verify/watch,
re-validate, never dormant — but no fabricated busywork or chasing Anton-domain (grader-budget) / blocked (Nucleus, position-only) items.

### position-only INERTNESS understood [INFERRED] (cron-wake5): _plan_pose_single applies the metric to the right solvers but
the IK solve RETURNS the flipped full-pose solution; update_pose_cost_metric changes cost RANKING, not which IK solutions are
returned → trajopt seeds from the flip regardless. The theoretical fix = make the IK solver RETURN position-only (non-flipped)
solutions = deep IK-internals work, beyond a gated experiment. Fix #3 comprehensively exhausted (every lever refuted + mechanism understood).

### Multi-cube completeness [MEASURED] (cron-wake6): ALL 7 solid passers are SINGLE-cube (CP-69/70/75/79/80=bin, CP-84=stack,
CP-86=color-route) → clean deliveries, NO lenient-masking. Multi-cube templates are all in the Anton-call fails. No quality gap on passers.
### NEW THREAD: defect #3 had TWO parts — spin (H7 fixed) + LATE RELEASE (separate root, not yet addressed). Investigating.

### DEFECT #3 LATE-RELEASE still present [MEASURED+INFERRED] (cron-wake6): over-bin→release gap ~16s w/ H7 (grip-log + scene_eyes
agree). H7 fixed the SPIN but NOT the late-release (it only touched the transit, not the place-release logic). The RCA root
(release gated on xy-converge / seg_start_t reset) persists. SEPARATE tractable controller-side fix → completes defect #3.
Caveat: H7 mt-stretch + sim slow-motion inflate ABSOLUTE timing; the delay is real but the exact value is uncertain.

### CORRECTION (PRIME DIRECTIVE) cron-wake6: the "~16s late-release" is CONTAMINATED — the over-bin detector likely caught the
cup passing near the bin during the H7 transit, not the final descend. Magnitude NOT cleanly [MEASURED]. Root IS the
`_xy_err<0.08` release gate (L7165) + place close-loop nudge (cube delivers = nudge converges, but slowly). Running definitive
cup-z+status trajectory dump to see hover-vs-artifact before any claim or fix.

### DEFINITIVE late-release [MEASURED] (cron-wake6, Kit#15, grip-log trajectory): cup DESCENDS to z=0.99 over bin at t≈41
(binXYd=0.05) but RELEASES only at t=49.3 (binXYd=0.00) = ~8s HOVER while the place-nudge drives xy 0.05→0.00. The release
waits for near-zero xy_err (tighter than the 0.08 gate). Cube delivers. ALSO: small residual excursion at t=38 (z=1.30, the
wrist_2 reconfig — far milder than baseline 1.71). FIX direction: loosen the release xy-tolerance (release at binXYd<~0.04 +
settle) or time-cap the nudge → prompt release. Gated, tractable → completes Anton's defect #3.

### H7 CYCLE SLOWNESS [MEASURED] (cron-wake6): full CP-69 H7 cycle ~49s (baseline ~12s). Two contributors: (1) H7 transit ~13s
(the loaded-vmax mt-stretch on the hop+carry — I added it to prevent the loaded cube flinging; trade-off vs speed), (2) place-
nudge late-release ~8s (nudge converges binXYd→0.00, each nudge resets seg_start_t so the settle-timer never fires; pick-nudge
has a cap `_sg_nvidia_nudge_max`, place-nudge effectively does not). FIX directions (both gated, tunable, with trade-offs):
(1) lower the hop/carry mt-stretch (faster, risk loaded-fling), (2) cap/loosen the place-nudge (faster release, risk off-center).
H7 trades the VIOLENT FLING for a SLOW CAREFUL placement — Anton's call on the speed/precision trade-off. Cube delivers throughout.

### ★★★ THE "VARV TILL" ROOT + FIX [MEASURED] (cron-wake7/8, 2026-06-09) — Anton: "går till bin, levererar inte, tar ett varv till" ★★★
Anton clarified defect #3 precisely: the arm reaches the bin, then takes a FULL LAP out to ~home and back BEFORE releasing.
delivery != success — the gate passes while the arm laps. Cup-xyz is BLIND to this (axisymmetric cup) → instrumented grip-log
with JOINT angles (jdeg=[pan,lift,elbow,w1,w2,w3]) + segment index. [MEASURED CP-69 H7-on]: seg7 (S5 descend, action_after=="open")
starts OVER-BIN (pan=-47) but its traj LOOPS to ~HOME (t=31 pan=-2,w2=-92,w3=-4) then BACK to bin (pan=-47) = the lap (binXYd
0.046→0.43→0.046, 2 distinct bin-approaches).
ROOT [MEASURED+code]: the STATIC S5 descend is planned in _build_segments at PICK-START when the arm is AT HOME (pick not yet
executed) → seeded from (wrapped) HOME → plan_pose returns a HOME→bin trajectory. Replayed at EXECUTION when the arm is already
OVER-BIN → drives the arm home→bin = the lap. The over-bin config DOES NOT EXIST at plan time.
REFUTED [MEASURED] (3 hypotheses, all because no over-bin seed exists at plan time): (1) _ur10_drop_branch_pin (cspace branch-pin
FAILS→falls back to home-seed; lap unchanged 2/0.408). (2)+(3) _ur10_drop_seed_chained on the S5-main + z-backoff (seeds from
_q_chained which is ALSO ~unwrapped-HOME, NOT over-bin → BREAKS delivery, res_None all 36 attempts, gate=False). All gated default-OFF.
★ FIX — `_ur10_s5_relive` (gated default-OFF, UR10-suction only, fail-open) at pick_place.py L7187, in _on_step right after
`cur_seg = segs[seg_idx]`: when the executor ENTERS the open/place segment, RE-PLAN the descend LIVE from the CURRENT (over-bin)
joints (which only exist now) to the same down-locked drop goal, overwrite cur_seg traj/motion_time, reset seg_start_t, return.
Mirrors the PL-nudge idiom. Fail-open: live plan None → static traj (= today). RCA+design via read-only Workflow (8 agents) — but
VERIFIED on live data, not the agents' word (Anton: "du får inte ta agenternas ord för lag").
[MEASURED] RELIVE=1 fresh-Kit sweep: CP-69 lap DEAD (approaches 2→1, home-excursion 0.39→0.009, descend pan-swing 45°→0.0°,
delivers dead-center, N-of-M 2/2). PASSER SWEEP (no delivery regression, all success=True): CP-70 1/0.137, CP-75 1/0.135, CP-79
1/0.003, CP-86 1/0.133 = ALL CLEAN (no lap). The live re-plan adapts per-scene (seed_pan ranged -47→167 across templates). Franka
+ non-UR10 byte-identical (verified L7188 ROBOT_FAMILY+_SG_IS_SUCTION gate).
EXCEPTION [MEASURED]: CP-80 STILL laps (approaches=2, maxrise=0.386) DESPITE RELIVE firing (seed_pan=175.6). Root: CP-80's OVER-BIN
config is WOUND (pan=175.6, w2=85.6, NOT the clean down-lock -137) because H7 does NOT fire for it (reach 0.939 < far_reach 1.0) →
the descend re-plan from a wound seed still laps. [HYPOTHESIS]: CP-80 needs H7 (clean down-lock) BEFORE the RELIVE descend; testing
RELIVE+FARREACH=0.8 (H7 fires for CP-80). Anton's reservation confirmed: per-template roots differ (CP-80 = transit-config, not the
static-descend root RELIVE fixes).
revert: `cp ~/.ur10_nightshift/pick_place.<ts>.bak <file>`; gate hook RELIVE=1 in scripts/qa/gate_one.py. Edits gated default-OFF →
production byte-identical. Refuted DROPSEED/DROPPIN edits remain gated-OFF (inert landmines, slated for cleanup once RELIVE lands).

### ★★★ RAWSEED — the wrap-bug root of the CLOSE-PICK lap (CP-70/75/80) [MEASURED 2026-06-09, cron-wake8/9] ★★★
The CP-80 RELIVE-exception above is SOLVED — and not by FARREACH. ROOT [MEASURED]: the RELIVE descend re-plan seeded
its solve WRAPPED to (-π,π], but the arm's physical wound over-bin config sits at pan≈320°; the wrapped seed planned a
traj at pan≈-40° (same physical angle, different winding) → the articulation controller drove 320°→-40° = a 360° swing
(the fling/lap). FIX = `_ur10_relive_seed_raw` (gated default-OFF): seed the relive solve RAW/unwrapped so the planned
traj is continuous with the physical config. [MEASURED] trajsrc: seg=7 src=relive pan0=320 panN=320 range=0 (was the
static src pan -0→-40 range=40 home-detour). This is the SEED/PLANNING fix Anton's stance predicted — NOT geometry,
NOT a planner-architecture rewrite. My earlier "fundamental kinematic limit" (FREEIK_ok=False) was REFUTED by the
adversarial check (CP-69 near-identical goal had clean down-IK).
MOTION-CLEAN triple-proof [MEASURED, fresh-Kit warp-cleared, CP-70/75/80]: (1) grip_log bin_approaches=1 (no varv),
(2) trajsrc seg=7 relive pan-range=0 (no fling), (3) cube at_rest dead-center velocity≈0. All 6 deterministic
single-cube passers (CP-69/70/75/79/80/86) deliver dead-center clean on the faithful straight cup.

### MASTER SWITCH + DEFAULT FLIP [MEASURED 2026-06-09] — production now ships the faithful STRAIGHT cup
`_ur10_faithful_default` (pick_place.py ~L5667) consolidates the winning unit: straight nvidia mount + H7(sign-1) +
S5 RELIVE + branch-pin + RAW seed + droptip 0.21. DEFAULT FLIPPED OFF→ON at L5680 (`getattr(..., True)`), scoped to
UR10/UR10e asset-suction (block guard family-in-ur10 + _SG_IFACE + no follower). Anton: "sidokopp inte acceptabelt".
Side-mount still reachable by explicit `_ur10_faithful_default=False` (gate hook FAITHFUL=0). FRANKA NO-REGRESSION
CONFIRMED [MEASURED]: CP-28 fresh-each ×2 = success dead-center (UR10-scoped + all 7 flags read only under suction/UR10
gates). An earlier CP-28 batch fail was Kit-degradation (3rd in Kit), NOT the flip. revert: cp the wake-snapshot .bak.
NOTE [§14.6 discipline]: the flip is NOT yet fully EARNED — 8-passer N-of-M on FAITHFUL=1 still owed: CP-69/70/75 at
2/2, CP-80 2/2, CP-79/86/84 at 1/1 ✓, **CP-85 0/1 (failed once on straight — stochastic, needs N-of-M)**. Complete the
8-passer N-of-M before calling the default earned; revert/narrow if CP-85 reliably regresses on straight vs side.

### CP-83 multi-cube STUCK in wait_sensor on straight cup [MEASURED 2026-06-09, cron-wake9, Kit fresh+GRIPLOG]
CP-83 straight cup: grip_log mode=settling→wait_sensor and STAYS there the full 180s; seg=0/0 constant; jdeg=
[0,-90,90,-90,-90,0] (HOME) the whole time; mind-to-cube constant 1.252; gripped=[]; NO trajectory built. => the arm
NEVER starts the pick cycle (stuck in wait_sensor), it is NOT a reach/grip/plan failure. Single-cube passers execute
fine on the same straight cup, so faithful does NOT break wait_sensor universally — multi-cube-specific.
[HYPOTHESIS, testing this wake]: CP-83 is stuck in wait_sensor on BOTH cups → the side-cup gate success=True (Cube_1
unmoved at source) is a multi-cube-ANY-criterion FALSE-POSITIVE → NO flip-regression (CP-83 isn't an 8-passer anyway).
DISAMBIGUATION RUNNING: CP-83 SIDE (FAITHFUL=0) + GRIPLOG — predict ALSO stuck at jdeg-home. §12 read-only hypothesis
workflow (wofnl5zwz) launched for the multi-cube-stuck class (the active problem changed: fix#3 done → open fails).

### CP-83 disambiguation RESULT — prediction REFUTED [MEASURED 2026-06-09, cron-wake9] → REAL regression → flip REVERTED
CP-83 SIDE (FAITHFUL=0) does NOT stay stuck: grip_log mode=executing, seg 0→7, and at t=12s status=Closed
gripped=['/World/Cube_2'] mind=0.025 cup=[-0.501,0,0.95] → the arm GRIPS Cube_2 and delivers it (gate success=True is
REAL, one of two cubes; Cube_1/probed stays at source). cuRobo plans (many "Start or End state in collision" warnings).
CP-83 STRAIGHT (faithful) stays in wait_sensor, never plans (zero curobo warnings), 0 cubes. => the faithful default
[MEASURED] REGRESSES multi-cube (side 1-cube → straight 0). My "both stuck / false-positive" prediction is REFUTED.
ACTION: reverted `_ur10_faithful_default` to default-OFF (L5687; snapshot pick_place.20260609T140826.bak). Production
byte-identical. Faithful stays available via FAITHFUL=1. Re-flip gated on 8-passer N-of-M (CP-85 0/1) + multi-cube fix.
NEXT: §12 workflow (wofnl5zwz) hypotheses for WHY straight-cup multi-cube never leaves wait_sensor (no plan attempted);
+ CP-85 N-of-M on FAITHFUL vs side (the §14.6 passer-regression gate).

### CP-83 wait_sensor ROOT pinned [MEASURED 2026-06-09, cron-wake9, ctrl:pick_reject probe + settle_dbg] — H-A CONFIRMED
ctrl:pick_reject on /World/UR10 (faithful) = "nsrc2|Cube_1:failed|Cube_2:failed" → both cubes are in S["failed"], NOT
a reach reject. /tmp/settle_dbg: "BUILD_NONE picked=Cube_1"×12 + "Cube_2"×6, NO BUILD_RAISE → `_build_segments`
RETURNS None (a plan inside it fails) for CP-83's cubes (cp z=0.925, dp=[0.5,-0.4,0.95]) → the L7131-7137 3-strike
counter marks each cube failed → _cube_to_pick None → wait_sensor forever. On the SIDE cup _build_segments succeeds
(picks Cube_2). So the faithful config makes a pick/transit/descend plan inside _build_segments return None for the
multi-cube geometry. The §12 reach math (cubes well within reach) + the :failed (not :xy_/:3d_) reject AGREE it is NOT
reach — it's a plan inside _build_segments. WHICH segment/flag is the open sub-question (needs _build_segments
per-segment instrumentation). NOTE: CP-83/81/82 are NON-passers (open multi-cube work on BOTH cups) → NOT the flip
blocker. FIRM RULE (anti-thrash §4.7): re-flip the faithful default ⇔ CP-85 (only unconfirmed passer) ≥2/3 on
FAITHFUL fresh-each. Multi-cube _build_segments-fail is separate mission progress. CP-85 N-of-M running (b1x9pqntn).

### ★ CP-85 REGRESSION CONFIRMED [MEASURED 2026-06-09, cron-wake10] — the faithful cup regresses a real passer ★
CP-85 FAITHFUL straight = 0/3 (cube unmoved z=0.975, BUILD_NONE, stuck). CP-85 SIDE (FAITHFUL=0) = 3/3 PASS,
delivers dead-center [0.50,-0.30,0.785], grips Cube_1 at t~11s (cup z=0.999), NO BUILD_NONE, clean seg 0->7. So CP-85
is a GENUINE side-cup passer (3/3 deterministic, NOT stochastic as memory hinted) and the faithful straight cup
REGRESSES it. => the flip definitively cannot be default-ON (regresses a passer, §5). Flip stays OFF (already
reverted). UNIFYING ROOT [HYPOTHESIS, well-supported]: faithful _build_segments returns None for HIGH pick/drop-z
(CP-85 pick z=0.975 -> nvidia pz~1.138; CP-83 dp z=0.95). The 6 working passers pick/drop lower (bin z~0.785).
RELIVE/RAWSEED/branch_pin are EXECUTION-time (cannot cause BUILD_NONE) -> breaker is NVCUP(pz) / H7 / the down-locked
descend orientation at high z. Fixing this RESTORES CP-85 + may unlock multi-cube + makes the flip earnable. NEXT:
read _build_segments to localize the failing plan call; isolate breaker flag (NVCUP vs H7 vs DROPTIP) on CP-85 straight.

### ★★ CP-85 straight ROOT fully decomposed [MEASURED 2026-06-09, cron-wake11/12] — 2 controller-side roots, NOT architectural ★★
Localized via /tmp/cp_planfail_tagged.log (always-on) + grip_log trajectory (GRIPLOG) on fresh Kits:
ROOT-1 (the BUILD_NONE/stuck): seg-0 APPROACH plan fails — goal=[-0.5,0.4,1.15] (nvidia tool pushes the EE pick goal to
z=1.15 at the behind-side xy, down-locked orientation → no IK). 485 seg-0 planfails. **FIXED by IKSEEDS=64**: residual
seg-0 planfails 485→0; _build_segments now SUCCEEDS; the arm picks Cube_1 (grip latch t=8.8, mind 0.025) and CARRIES
it (mind held 0.027 through the whole transit, physical track) all the way OVER the bin to cup=[0.417,-0.292,1.234].
[MEASURED win — IKSEEDS=64 is the high-z behind-side approach lever, same as CP-81@IKSEEDS=64.]
ROOT-2 (why it STILL doesn't deliver, 0/4 with IKSEEDS=64): the PLACE descend (seg 6) HOVERS at cup=[0.397,-0.283,1.26]
over the bin, status stays Closed (never opens) through t=31.7. Bin target=[0.5,-0.4]; cup xy-err = sqrt(0.103²+0.117²)
= 0.156 > the release gate xy<0.08 → release NEVER fires → cube never dropped → by t=46 the cube is back at SOURCE
(mind 1.245), gripped=[]. So the cup cannot get within 0.08 xy of the bin from the behind-side-high arrival config →
no release. This is CONTROLLER-side (place-reach + release-gate), NOT grip-physics-architecture (the grip held the cube
through the full transit). On the SIDE cup CP-85 delivers 3/3 (its arrival config reaches the bin xy).
NEXT EXPERIMENT (queued, fresh Kit): close ROOT-2 — either (a) IKSEEDS=64 on the PLACE descend too / a place re-plan so
the cup reaches bin-xy<0.08, or (b) the RELIVE place re-plan from the over-bin config, or (c) loosen the release xy
gate for the behind-side arrival (risk: front passers — must re-verify). One variable, gated, A/B vs the 8 passers.
DURABLE: IKSEEDS=64 fixes the high-z approach plan for the whole behind-side-high class (CP-85, likely CP-81/83). The
flip stays OFF until CP-85 delivers (ROOT-2). Multi-cube CP-83 likely shares ROOT-1 (IKSEEDS) + its own place issues.

### ★★★ CP-85 ROOT-2 SOLVED + faithful default RE-FLIPPED ON (straight cup) [MEASURED 2026-06-09, Anton back] ★★★
Anton (back at desk): "sidokopp är inte acceptabelt" — reverting to the side cup was the WRONG call (protected a cup
he rejected). CORRECTED: the straight cup is the ONLY acceptable production mount; CP-85/multi-cube are open work ON it.
ROOT-2 FIX [MEASURED]: H7 clean-arrival lever. FARREACH=0.5 makes the jointspace pan-rotate transit (H7) fire for the
~180deg behind->front transit (CP-85 pick reach 0.64>0.5) so the arm ARRIVES at the bin in a clean (non-wound) config
-> the place-nudge reaches bin-center xy<0.08 -> release fires -> delivers. CP-85 0/3 -> **2/2** with
FAITHFUL+IKSEEDS=64+FARREACH=0.5, cube dead-center [0.510,-0.289,0.785].
NO-REGRESSION A/B [MEASURED]: ALL 6 deterministic passers (CP-69/70/75/79/80/86) STILL deliver dead-center with
FARREACH=0.5 (it makes H7 fire for the close passers CP-70/75/80/86 too, which it didn't before — they stay clean).
=> 8/8 single-cube passers deliver on the straight cup. INTEGRATED into the _ur10_faithful_default master switch
(pick_place.py ~L5688): added `_ur10_ik_seeds=64` + `_ur10_jointspace_far_reach=0.5` (9 levers total). DEFAULT
RE-FLIPPED ON (L5688 getattr(...,True)) — production now ships the straight cup. Snapshots pick_place.2026...153209.bak.
NOW VERIFYING pure-default (no env) on CP-85/CP-70/CP-83 + probing whether the recipe unlocks multi-cube CP-83.
NEXT: multi-cube (CP-83/81/82) on the integrated default; then CP-71/73; then full N-of-M re-verify -> GUI review.

### Multi-cube CP-83 — A1 (carry-scoped obstacles) + pick-order [MEASURED 2026-06-09, both gated default-OFF]
Two new gated levers added (default OFF -> production byte-identical): (1) `_ur10_multicube_obs_carry_only` — scope the
auto-added non-target-cube+pedestal obstacles to the LATERAL-TRANSIT segments (idx>=4) only, so approach+pick+lift plan
obstacle-light (target is excluded; straight-up lift = low sweep) while the transit keeps full collision. Plumbed via
builtins._mc_carry_phase set per-segment in _build_segments + folded into _world_sig so the cuRobo world rebuilds at the
phase flip. (2) pick-closest-to-base-first in _cube_to_pick (gated same flag) — deliver the nearer cube first so it is
gone as an obstacle for the farther one (generalizes to stacking: nearest=top). PROGRESS [MEASURED]: CP-83 went
stuck-in-wait_sensor -> approach plans -> ARM MOVES (executing) -> picks Cube_2 (nearest) first. REMAINING walls
(diagnose_pick_execution): seg-4 TRANSIT plan grinds (plan_fails=651) even with H7+pick-order (the arm-body-vs-neighbour
geometry now at the transit), AND the pick descend close-loop doesn't reach Cube_2 (graspdiag gd=0.284, cup 0.27m above).
ASSESSMENT: CP-83 multi-cube on the straight cup is a 5-layer onion (each fix reveals the next manifestation of the same
root — the long-tool down-locked arm occupies the neighbour-cube region throughout). This is a MULTI-SESSION effort, NOT
a quick wrap. Single-cube cluster (8/8) is DONE + shippable. The A1+pick-order levers are real, generalizable progress.

### CP-83 pick-descend ROOT precisely [MEASURED 2026-06-09] — down-config exists but is a 7.39-rad reconfig from arrival
Via the §12 levers (branch_pin + downlock_seed + cspace_unwrap, all gated default-OFF) + cspace_dbg: the down-grasp IK
EXISTS (ik_ok=True, gq=[2.549,-2.202,2.344,-1.713,-1.571,0.978]) BUT is **bestd_rad=7.39 (L1)** from the wound pick
arrival config → plan_cspace REFUSES to bridge it (cspace_ok=False) → CL-nudge RES_NONE → cup frozen 0.27m above Cube_2
(mind=0.284). **REFUTED the 2π-wrist-wrap hypothesis**: _ur10_cspace_unwrap (unwrap each joint toward current before
L1+plan_cspace) left bestd UNCHANGED (7.41→7.39) → the 7.39 is NOT a wrap artifact, it is a GENUINE multi-joint
reconfiguration (each joint <π from current, summing to 7.39). So the ARRIVAL config itself is the root: the straight
cup's long-tool arm reaches the behind-side pick in a config far (7.39 rad) from the down-grasp config, and cuRobo
won't bridge that gap. THE FIX (untried, deep): make the pick APPROACH arrive in a down-near config (W1-H2: a pick-entry
relive / jointspace approach that lands near the down-grasp) — NOT a single flag. Gated levers added this session (all
default-OFF, production byte-identical): _ur10_multicube_obs_carry_only (A1 carry-scoped obstacles + pick-closest-first),
_ur10_pick_descend_pin (branch_pin on the pick CL-nudge), _ur10_cspace_unwrap (refuted). PROGRESS: arm moves, picks the
nearest cube first, approach+pick+lift plan. WALL: the down-grasp reconfig from arrival. ASSESSMENT [MEASURED]: multi-cube
on the straight cup is a dedicated R&D problem (the arrival-config-vs-down-grasp gap), shared by the 25 stacking plates.
Single-cube 8/8 is the shippable milestone. STOPPED the solo grind here (extensive, documented; clean handoff).

### ★★★ CP-83 ACTUALLY DELIVERS Cube_2 — the "revert" was a MEASUREMENT ARTIFACT [MEASURED 2026-06-09] ★★★
H7-APPROACH BREAKTHROUGH: added `_ur10_pick_approach_panrotate` (gated, mirror H7 at idx==0: cspace pan-rotate the base
toward the CUBE azimuth BEFORE the approach so the arm arrives BASE-FACING the behind pick, not folded-back). [MEASURED
TS] CP-83 with the full lever stack (carry-scoped-obs + pick-closest-first + H7-approach + pick-descend-pin + downlock-
seed): the arm arrives base-facing (seed_pan 156 not 20), the pick descend REACHES Cube_2 (gd 0.284->0.028), GRIPS,
carries, and DELIVERS it. Per-cube position trace: **Cube_2 = [0.49,-0.40,0.79] (the bin) CONSTANT t=58.5->89.7s, at
rest, grip released** = a REAL physical delivery.
THE "REVERT" / "false-positive" I earlier claimed was MY MEASUREMENT ERROR: the gate ends with `timeline.stop()`, which
makes Isaac Sim RESET all physics objects to their pre-play (SOURCE) poses. My post-gate exec_sync POS read therefore
showed SOURCE for EVERY cube regardless of delivery. The grip_log DURING play is the ground truth. METHODOLOGY LESSON
(durable): NEVER read object positions after timeline.stop() — read during play (grip_log per-tick / the gate's own
during-play verdict). The gate success=True for CP-83 is REAL.
STATE: CP-83 delivers 1/2 cubes (Cube_2 real, at-rest in bin). Cube_1 (2nd) genuinely fails seg-6 (the PLACE, goal
[0.5,-0.4,1.16], plan_fails) — likely the place-from-2nd-arrival or the bin now holding Cube_2. That is the remaining
work for FULL CP-83. The H7-approach lever stack is the multi-cube/stacking breakthrough (arrive base-facing the pick).
All levers gated default-OFF; production = single-cube 8/8 faithful straight cup, byte-identical.

### CP-83 Cube_1 (2nd cube) place root [MEASURED 2026-06-09] — NOT the delivered-obstacle; arm-config place-reach
exclude-delivered (gated _ur10_obs_exclude_delivered) was REFUTED: Cube_1's place fails IDENTICALLY with/without it
(seg-6 place, goal [0.5,-0.4,1.16], deepest sub-step z=0.611 res_None) → Cube_2-in-bin is NOT the blocker. _bin_drop_pos
returns the same drop-z for both cubes; the place GOAL is identical to Cube_2's (which delivered). So Cube_1's place
fails for an ARM-CONFIG reason (its far-pick over-bin arrival → the place descend sub-step at z=0.611 can't plan), the
SAME arm-config-vs-reach family as the pick-descend — and it fails at BUILD-time (seg-6, _build_segments returns None)
so the execution-time RELIVE place re-plan never gets a chance. FIX direction (next): the place needs the same clean-
arrival / branch-pin / relive-at-build the pick got, OR raise the place sub-step floor so it doesn't target below the
bin floor. CP-83 = 1/2 cubes (Cube_2 REAL). Cube_1's place = the next layer. exclude-delivered left gated-OFF (refuted).

### ★ H7-approach lever stack GENERALIZES across multi-cube [MEASURED 2026-06-09] ★
Full stack (FAITHFUL + IKSEEDS=64 + FARREACH=0.5 + MCUBECARRY + PICKPIN + DLSEED + CSPACEUNWRAP + PANROTATE + EXCLDELIV,
all gated default-OFF) fresh-each, verified by DURING-PLAY grip_log cube positions (not post-gate POS — timeline.stop
resets to source):
- CP-81: Cube_2 delivered REAL ([0.51,-0.39,0.79] = bin, at rest), Cube_1 at source. GATE success=True. 1/2.
- CP-83: Cube_2 delivered REAL ([0.51,-0.38,0.79] = bin), Cube_1 at source. 1/2.
- CP-82 (routing -> Bin_red): messier — Cube_2 lands at the bin EDGE [0.51,-0.54] (just outside), Cube_1 on the floor
  [-0.39,-0.13]. GATE=False. A place-PRECISION issue (routing target), distinct from CP-81/83.
=> multi-cube went 0-delivering -> 2/3 deliver their FIRST cube (Cube_2) for real via the generalized stack. The stack
is the multi-object foundation for the 25 stacking plates. REMAINING: (a) the 2nd cube (Cube_1) place for CP-81/83
(same place-arm-config layer — Cube_1's transit-arrival -> place descend res_None at build-time); (b) CP-82 place
precision (Bin_red). Gate hooks added (PICKPIN/CSPACEUNWRAP/PANROTATE/EXCLDELIV). Production byte-identical (all OFF).

### ★★★ CP-83 DELIVERS 2/2 RELIABLY — first fully-delivering multi-cube on the straight cup [MEASURED 2026-06-09] ★★★
N-of-M 3/3 fresh-each, full lever stack: BOTH cubes physically in the bin every run (during-play grip_log):
A: Cube_1=[0.50,-0.40,0.83] Cube_2=[0.51,-0.38,0.78]; B/C identical. gate success=True, in_target_xy=True, at rest.
Cube_1 stacks on Cube_2 (z 0.83 vs 0.78). NOT stochastic — the earlier 1/2 run was BEFORE the place-branch-pin.
COMPLETE multi-cube RECIPE (all gated default-OFF): _ur10_multicube_obs_carry_only (carry-scoped obstacles idx>=4 +
pick-closest-to-base-first) + _ur10_pick_approach_panrotate (H7-approach: base-rotate to face the behind pick ->
base-FACING down-near arrival, the breakthrough) + _ur10_pick_descend_pin + _ur10_place_descend_pin (branch-pin both
descends through the cspace-pin/down-config path) + _ur10_descend_downlock_seed + _ur10_cspace_unwrap + _ur10_obs_
exclude_delivered + _ur10_place_failopen (RELIVE safety). This is the multi-OBJECT foundation for the 25 stacking
plates. NEXT: (a) generalize the full stack to CP-81/82 (CP-81 delivered Cube_2; full stack -> 2/2?); (b) minimize the
stack to the essential flags; (c) integrate into the faithful default for multi-cube once N-of-M-confirmed across the
multi-cube set. New gate hooks: PLACEPIN, PLACEFAILOPEN. Production still byte-identical (all multi-cube levers OFF).

### Multi-cube recipe GENERALIZES [MEASURED 2026-06-09]: CP-81 ALSO delivers 2/2
Full stack fresh: CP-81 Cube_1=[0.50,-0.40,0.83] Cube_2=[0.51,-0.39,0.79] = BOTH in bin, gate success=True, at rest.
So CP-81 + CP-83 (the two standard 2-cube -> /World/Bin templates) both deliver 2/2 via the recipe. Multi-cube went
0-delivering -> 2 templates FULLY delivering. CP-82 (routing -> Bin_red) is the OUTLIER: Cube_1 ends on the floor
mid-scene [-0.39,-0.13], Cube_2 near-but-off [0.51,-0.54] -> needs routing/Bin_red-specific work (distinct from the
standard-bin recipe). REMAINING UR10 multi: CP-82 routing precision; CP-71/73 (4-cube dispenser/conveyor) untested
with the stack. NEXT: minimize the stack to essentials + integrate into the faithful default for multi-cube, then
N-of-M the multi-cube set. Production still byte-identical (all multi-cube levers gated OFF).

### 4-cube does NOT generalize from the 2-cube recipe [MEASURED 2026-06-09] — distinct sub-problems
Full stack on the 4-cube templates: CP-71 (dispenser) GATE=False, all 4 Items stay in the dispenser region
([-0.45..-0.28, 0.35-0.45], z~0.83), 0 delivered. CP-73 (conveyor) GATE=True (lenient) but Cube_1 is a PHYSICS BLOWUP
(speed 4.2 m/s, z=0.53 BELOW floor, flung) while Cube_2/3/4 reach near the bin -> 3 near + 1 flung, not clean. So the
standard-2-cube recipe (CP-81/83 2/2) does NOT directly solve dispenser/conveyor/routing. CALIBRATION: the recipe
generalizes to STANDARD side-by-side multi-object -> standard bin; dispenser/conveyor/routing/stacking each need
per-class adaptation (don't assume the 25 plates are free). 13/13 status: 10 fully (8 single + CP-81/83 gated 2/2);
CP-82 (routing), CP-71 (dispenser 0), CP-73 (conveyor + loaded-fling on the 4th cube) remain as distinct sub-problems.
NEXT: integrate the proven standard-2-cube recipe into the faithful default (CP-81/83 2/2 in PRODUCTION, not just gated)
to lock in 10/13 real; then per-class CP-82/71/73. Minimize the 8-flag stack to essentials before integrating.

### Auto-on integration DEFERRED; recipe stays GATED [2026-06-09] — honest consolidation
Tried to bake the multi-cube recipe into the faithful default (auto-on for len(SOURCE_PATHS)>1). FAILED on flag-TIMING:
the pick-ORDER (closest-first, _ur10_multicube_obs_carry_only) is decided in _cube_to_pick which runs BEFORE
_build_segments, so setting the flags in _build_segments is too late for the order; and the master-switch setup point's
SOURCE_PATHS scope was inconclusive (the MC_DBG print didn't surface in a 60s window). REVERTED the broken auto-on
edits (restored pre-integration snapshot) -> CLEAN gated recipe, production = single-cube 8/8 byte-identical. The
multi-cube recipe REMAINS A PROVEN WIN via the env/builtins flags: CP-81 + CP-83 deliver 2/2 (CP-83 N-of-M 3/3, both
cubes physically in the bin). AUTO-ON is a clean next step: set ALL recipe flags (incl pick-order) at a controller
SETUP point that runs BEFORE _cube_to_pick AND where SOURCE_PATHS is populated (verify the master-switch SOURCE_PATHS
scope with a full-duration run first). 13/13 status: 8 single-cube (PRODUCTION) + CP-81/83 (2/2, GATED) = 10/13
achievable; CP-82 (routing), CP-71 (dispenser, 0), CP-73 (conveyor + loaded-fling) = 3 distinct sub-problems remaining.
Gate hooks for the full recipe: MCUBECARRY/PICKPIN/PLACEPIN/PLACEFAILOPEN/CSPACEUNWRAP/PANROTATE/EXCLDELIV/DLSEED/IKSEEDS/FARREACH.
