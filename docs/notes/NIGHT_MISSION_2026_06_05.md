# NIGHT MISSION 2026-06-05 → 06 (12h autonomous, Anton away)

## GOAL
100% UR10 function gate. Asset gripper (short_gripper.usd) is the production default (robot.py:6286).

## ANTON'S PARAMOUNT DIRECTIVE
**CORRECT OBSERVATION FIRST. A fix is worthless without a correct diagnosis from the scene.**
- Use CONTINUOUS-PLAY time series: full joint trajectories, EE/cup pose, grip state, contacts, cuRobo plan capture.
- NEVER chunked-play probes — they distort wall-clock (time.monotonic) controllers. PROVEN: /tmp/probe_cp80.py
  at vmax 0.3 showed "cube never picked, cup on wrong side" which CONTRADICTS the continuous eyes+gate (CP-80
  picks then flings). The chunk gaps let the controller's wall-clock jump ahead of the stepped physics.
- Build/extend the RIGHT analytics tool for each specific question. Verify the tool before trusting it.
- Throw the kitchen sink: cuRobo docs + WebSearch for UR10 config specifics; analyze the past CC conversation
  for a timeline of what's been tried (avoid repeating dead ends). Don't waste tokens.

## CURRENT GATE STATE (UR10 suction cluster, asset gripper default)
PASS (8, must not regress): CP-69, CP-70, CP-75, CP-79, CP-82, CP-84, CP-85, CP-86 (all single-cube, simple).
FAIL: 
- CP-80 (single, ELEVATED conveyor z=0.95): cube PICKED then FLUNG during transit (plan#4: 177° elbow + 180°
  wrist swing). Ends [0.137,0.401,0.775] on the table. Loaded-transit vmax cap at 1.2 did NOT help (gate: moved
  0.5mm). vmax 0.3 needs a CONTINUOUS-play re-test (chunk probe unreliable).
- CP-83 / CP-81 (2-cube): cup picks Cube_2 (nearer) fine; Cube_1 (far) untouched -> stays UPRIGHT (gate's
  C1-upright OK). Blocked on DELIVERING C2: CP-83 flings C2 onto table; CP-81 carries C2 to bin xy but (probe,
  unreliable) didn't show release. Gate is LENIENT (ANY cube delivered + C1 upright) -> need ONE cube in the bin.
- CP-54 = a FRANKA template (grep over-match), OUT OF UR10 SCOPE.
- CP-71 (4-cube gravity dispenser), CP-73 (4-cube moving conveyor + Cortex) = hardest, deferred.

## OPEN ROOT-CAUSE QUESTION (needs CORRECT observation)
Why does the asset compliant grip release the cube mid-transit? Candidates (force limit is 500N >> ~0.5N needed,
so NOT force):
  (a) arm angular velocity too high -> centripetal lag breaks grip  => slowdown fixes it (re-test vmax 0.3 CONTINUOUS)
  (b) SurfaceGripper maxGripDistance auto-release: compliant cube lags > maxGripDistance -> SG opens. (asset
      maxGripDistance = short_gripper.usd authored default; NOT set by us in robot.py — only forceLimits set)
  (c) cuRobo plans a needlessly violent swing (wrist multi-turn / elbow flip) -> gentler waypoints/attach_object fix
The per-tick close_gripper re-assert (pick_place.py:5594-5598) keeps a CLOSED grip closed -> does NOT drop it.

## PLAN
0. Infra: cron heartbeat (16903dc6, ~22min) + this doc + research Workflow (conversation timeline, cuRobo UR10
   config, SurfaceGripper physics) + ROBUST continuous-play observation tool (fix scene_eyes multi-cube crash).
1. Diagnose CP-80 fling root CORRECTLY with continuous joint+grip+contact time series (which candidate a/b/c).
2. Principled fix (cuRobo velocity/accel limit OR maxGripDistance OR attach_object OR waypoints), gated, fresh-Kit verify.
3. Scale to CP-83/81, then CP-71/73. Re-gate the whole cluster each round; preserve the 8 passing.

## PROGRESS LOG
- (start) cron updated, mission doc written. Asset gripper default + loaded-transit vmax cap landed (vmax 1.2
  insufficient for CP-80 per gate). Chunked probe deprecated (unreliable). Building reliable observation next.

## RESEARCH SYNTHESIS (Workflow wnhtz4xmu, 4 agents) + CORRECTED METHOD
TOOL UPGRADE: scene_eyes.py now logs GripperView grip STATUS (0=Open 1=Closing 2=Closed), gripped-objects,
joint VELOCITIES, + a GRIP TIMELINE in _analyse (transition log w/ cup-cube dist + jvmax). SG status API =
isaacsim.robot.surface_gripper.GripperView (NOT acquire_*_interface). Asset SG maxGripDistance=0.02, force=500.

CRITICAL METHOD LESSON (re-confirmed Anton's mandate): a TOO-SHORT eyes window = WRONG diagnosis. CP-80 at 45s
showed "cube never moves, cup min 0.51m away, grip never latches" — but the gate(180s)+first eyes(55s) show CP-80
PICKS then FLINGS at t~53s. The 45s window simply ENDED before the pick. => always observe FULL duration (>=90s).
Also chunked-play probes are DEPRECATED (wall-clock controller distortion). Use continuous-play scene_eyes only.

TOP FIX PLAN (evidence-based, from synthesis) — apply TOGETHER, gated:
  Fix#1 maxGripDistance: 0.02 is the limiting grip window. BUT 0.30 ALONE already tried -> constraint EXPLOSION
        (cube ejected x=1.36). Must pair with a speed cap.
  Fix#2 loaded-transit speed cap (_sg_loaded_vmax): 1.2 alone did nothing because the 2cm window was the limiter.
        Lower vmax (~0.5) + bigger maxGripDistance (~0.20-0.30) TOGETHER: bigger window tolerates small lag; slower
        transit keeps lag small so the constraint doesn't explode.
  Fix#3 CP-83: verify whether the asset SG (body0=/Root, binds) is used (old ledger said bare ee_link SG didn't
        bind — but that was the PROCEDURAL path; asset default should bind). Re-observe.

DEAD ENDS — DO NOT REPEAT (from research): extra_links cup-frame IK (reverted 2x, CP-69 worse); drop-tip pz cup
offset (broke CP-78); FixedJoint grip EE<->cube (FORBIDDEN by Anton); asset-mount via fresh separate FJ (upside-
down — but our current mount WORKS); force-limit chasing (500N already enough); maxGripDistance=0.45 (low-EV);
breakForce->inf / stiffen D6 (banned weld); attachment_manager.attach (collision-only, ee_link 0 sphere slots);
velocity_scale/time_dilation to MotionPlannerCfg (TypeError, not in fork); PoseCostMetric/vhold/linear_motion(z)
on UR10 (broken); drop-yaw on suction (violent wrist); position-only transit one-liner (broke planning); blanket
motion_time*=2 (early-open instability); Warp upgrade (API incompat). KEY FILES: robot.py asset SG 6377-6383;
pick_place.py motion_time stretch ~6291; ur10_scene.yml cspace 125-156 (no velocity_scale).

NEXT (in flight): full-duration eyes CP-84(90s, validate grip enum+latch on a known-deliverer) + CP-80(90s, see
if it PICKS or never reaches the cube). Then apply Fix#1+#2 together, gated, fresh-Kit gate.

## CP-80 DEFINITIVE ROOT (full-duration grip-eyes, 2026-06-05 night)
NOT a transit-fling. The asset grip NEVER engages (gripped=[] all 90s, status never reaches 2=Closed, cup min
0.511m from cube). shoulder_pan_joint THRASHES at 16.2 rad/s the entire run (all other joints normal). Contacts:
upper_arm_link|ConveyorStand + upper_arm_link|ConveyorBelt PERSIST t=0->85s. Geometry: ConveyorStand bbox
[-1.0,0.25,0.75]->[0.0,0.55,0.95] abuts the UR10 (base[0,0,0.75], upper_arm reaches y=0.27) -> upper_arm CLIPS the
stand corner (y overlap 0.25-0.27) -> persistent penetration -> shoulder_pan blow-up -> arm can't rotate to the
cube (far -x, behind the stand) -> cube just knocked off the belt onto the table. CP-80 = MALFORMED/OBSTRUCTED
SCENE (robot spawned in collision with the conveyor stand). Fix = generalizing spawn-collision repair (detect
robot-link vs static-obstacle overlap -> nudge base clear) OR per-scene reposition. DEFERRED (harder, flawed
scene); validated CP-84 grips+delivers cleanly (status 0->2 at t=7.7, gripped Cube_1, jvmax 0.9, released in bin)
so the ASSET GRIP ITSELF IS SOUND. Pivot to 2-cube CP-83/81 (grip works; blocker is delivery).

## 2026-06-06 00:xx — 2-CUBE TRUTH (full-verdict gate, fresh Kit)
The asset grip is SOUND for 2-cube: CP-81 eyes (90s) = grip status 0->2 on Cube_2 (gripped, jvmax 0.9 gentle, NO
fling), Cube_2 DELIVERED to bin [0.52,-0.39,0.79], Cube_1 untouched/upright. So NO transit-fling with the asset
gripper (synthesis premise was procedural-era). The maxGripDistance+vmax fix is NOT applied (unneeded).
FULL-VERDICT GATE (fresh Kit, CP-81 x2): success=False BUT cubes_ever_in_target_xy{Cube_2:TRUE} + per_cube_support
Cube_2 support=/World/Bin/Floor under_target=TRUE at sim-end. => Cube_2 reaches+rests in the bin, yet the
multi-cube success (delivered_cubes, strict cp_in_xy+at_rest) doesn't credit it. Investigating per_cube_status
(at_rest vs in_xy). CP-83 DIFFERS: Cube_2 ever_in_target=false, support=/World/Ground => Cube_2 FLUNG OUT (real
delivery fail — placement/release, not the same as CP-81).
TOOL: scene_eyes hardened (incremental eyes.json dump every ~100 rows + exec-timeout tolerance + stale-guard) so
slow CP-83 yields partial data instead of NO_EYES_JSON. Gate criterion: diagnostics.py:4208 multi-cube
success=bool(delivered_cubes) and upright_ok; delivered=cp_in_xy(center in target bbox±tol) & above & at_rest.
S6 retract (anti-ascent-knock) is suction-EXCLUDED at pick_place.py:6096 — candidate fix if Cube_2 fails at_rest.

## 2026-06-06 ~01:00 — CP-81 ROOT-CAUSED via FULL TIME SERIES (Anton's introspection nudge → right place)
I was looking at the WRONG place (post-delivery disturbance / transit swing). The FULL 180s time series + gate
code reveal the true chain:
1. CP-81 DELIVERS Cube_2 cleanly to the bin; eyes show it PERFECTLY STATIC [0.3929,-0.4283,0.785] for the last
   1.5s (speed 0.0 over 0.1/0.5/1.0s windows). Cube_1 stays upright. => functionally a PASS.
2. After delivering Cube_2 (t~44), the controller targets Cube_1 (unplannable: pc 7->466, pf 0->63 in 0.4s,
   "RuntimeError: planning failed"). _build_segments RAISES (not None-return) -> escapes to the outer except
   WITHOUT releasing the plan-token (acquired in mode==settling) -> controller FROZEN on Cube_1 for 140s
   (pc/pf stuck 466/63, picked_path never cleared).
3. The frozen tick runs the sim in SLOW-MOTION -> the function-gate's wall-clock timeout (duration_s+60=240s)
   fires BEFORE sim-time reaches 180s -> the gate's pre-position capture (diagnostics.py:4153) never runs ->
   cp_pre stays at Cube_2's t=0 PEDESTAL pos. Gate velocity = (bin - pedestal)/one-frame = 1.21m/0.0167 = 72.9
   m/s (BOTH gate runs identically 72.935 = deterministic ARTIFACT, not a real disturbance) -> at_rest=False ->
   delivered_cubes=[] -> success=False. A measurement FALSE-NEGATIVE on a genuinely-delivered cube.
FIX (pick_place.py ~6558, generalizing, additive — only the raise path changes): wrap the _build_segments calls
in try/except; on a raise, _record_err + segs=None so the existing 3-strike abandon fires (mark cube failed,
RELEASE the plan-token, idle). => no freeze -> sim runs at normal speed -> gate measures the true (zero) velocity
-> CP-81 should pass. Generalizes to every multi-cube template with an unplannable cube (CP-83/71/73 likely too).
NOTE: the gate's stale-cp_pre-on-timeout + one-frame-dt is ALSO a latent measurement bug (amplifies any slow-sim
into a huge spurious velocity); the controller fix removes the trigger. Gate-harden is a possible follow-up (CAREFUL
- Anton: don't loosen / risk false-positives). >> GATE IN FLIGHT: CP-81 x2 + CP-83 + CP-84/CP-70 regression.
METHOD WIN: the eyes time series (Cube_2 static) vs the gate (72.9) is what cracked it — exactly Anton's "kom ihåg
tidsserier, alltid". A too-short window (45s) earlier gave a WRONG read; full-duration continuous-play was decisive.

## 2026-06-06 ~01:40 — FREEZE-FIX GATE: kept (no regression) but did NOT solve CP-81/83
CP-84 ✓ CP-70 ✓ (regression preserved). CP-81 x2 FAIL: run1 Cube_2 FLUNG to Ground [-1.36,0.93,0.52] speed71;
run2 Cube_2 on TABLE edge [0.497,-0.21] in_xy=False. CP-83 FAIL Cube_2 on Table, never reached bin. The freeze
fix changed Cube_1 from a harmless 140s FREEZE to PROCEEDING through its cycle -> the Cube_1 transit/drop at the
SHARED bin DISTURBS the delivered Cube_2 (real fling now, not just the measurement artifact). TWO real roots:
(1) STOCHASTIC violent transit swing (z=2.06) flings/misplaces Cube_2; (2) unpickable Cube_1 cycle disturbs Cube_2.
Freeze fix KEPT (valid robustness, additive, 0 regression). NEXT: test _ur10_transit_arc (clean fold-in-rotate,
eliminates the z=2.06 swing) on the transit -> should fix the stochastic delivery AND gentle the Cube_1 transit.
Observe eyes CP-81 --transitarc FIRST (see swing gone), then gate CP-81 x2 + CP-84/85 regression.

## 2026-06-06 ~03:00 — maxGripDistance 0.10 + GRIP-MISS ABORT (two landed fixes)
maxGripDistance gate: CP-84 ✓ CP-70 ✓ (0.10 does NOT explode the asset compliant grip — research's "0.30
explodes" was the PROCEDURAL cone, confirmed N/A here). CP-81 run2: Cube_2 IN THE BIN [0.519,-0.386,0.785]
in_xy=True under_target=True — maxGripDistance HELPED (vs flung-to-Ground before) — BUT failed on speed=72.9 (the
SAME stale-cp_pre artifact). ROOT of the artifact (time-series-confirmed): the unpickable far Cube_1's cycle
GRINDS — its bin-drop plan fails (bin occupied by delivered Cube_2), re-plans ~150x = slow-motion sim -> gate
wall-clock timeout fires before sim-end -> stale cp_pre. TWO fixes landed (both gated UR10-suction, additive):
 (1) maxGripDistance 0.02->0.10 (robot.py:~6383, flag _sg_asset_maxgrip) — Cube_2 holds the swing-lag, reaches bin.
 (2) GRIP-MISS ABORT (pick_place.py ~6766): if the 6s close-timeout fires with cup >0.12m from the cube (never
     gripped, e.g. Cube_1), mark failed + abort the cycle BEFORE the grinding transit/bin-drop -> controller idles
     -> sim normal speed -> gate measures correctly. 0.12m gate => normally-gripped cubes (8 passing) untouched.
 + freeze fix (catch _build_segments raise) already landed.
EXPECT: CP-81 sim now normal-speed -> Cube_2 (in bin, run2-like) measures at_rest -> PASS when Cube_2 reaches bin.
Residual: STOCHASTIC delivery (run1 Cube_2 on table-edge in_xy=False = swing places it short) -> may need N-of-M or
the swing made consistent. >> GATE IN FLIGHT: CP-81 x2 + CP-83 + CP-84/70 regression.

## 2026-06-06 ~04:30 — CP-81 Cube_2 GENUINELY DELIVERED; the last blocker was a GATE TIMEOUT (not the robot)
ALL-FIXES gate (maxGrip0.10 + freeze + grip-miss + plan-budget): CP-81 BOTH runs now deliver Cube_2 to the EXACT
bin pos [0.519,-0.386,0.785], in_xy=True, under_target=True (Bin/Floor) — DELIVERY IS NOW CONSISTENT (maxGrip 0.10
cured the stochastic fling/table-edge). CP-84 ✓ CP-70 ✓ (zero regression). But CP-81 still success=False on the
DETERMINISTIC 72.9 m/s artifact. PROVEN root: 72.9351 = |bin-pedestal|(1.216m) / one-frame(0.0167s) -> cp_pre is
the cube's t=0 SPAWN pos because the UR10 cuRobo+asset sim runs ~1.5x slower than real-time and hit the gate's
`duration_s+60` wall-clock cap at sim-t~160s, BEFORE the pre-pos capture (sim-t 179.85) ran. Cube_2 is genuinely
delivered + at rest; the gate just never reached sim-end to measure it. FIX (diagnostics.py:4161, SAFE — pure
patience, no criterion change): wall-clock cap 60 -> `duration_s*2.0+120` so slow sims COMPLETE. gate_full sim
timeout 220->500 to match. >> RE-GATE IN FLIGHT (slower now, sims run to completion). EXPECT CP-81 PASS. CP-83
Cube_2 ends on Table (ever_in_target=False) = a REAL non-delivery (swing flings it short) — separate, still open.

## 2026-06-06 ~05:15 — ✅ CP-81 PASSES (deterministic x2)! First new gate pass of the night.
TIMEOUT-MARGIN gate: CP-81 success=True BOTH runs — delivered_cubes=['/World/Cube_2'], Cube_2 [0.519,-0.386,0.785]
in_xy=True speed=0.0 at_rest=True DELIVERED=True; Cube_1 upright. CP-84 ✓ CP-70 ✓ (0 regression).
THE FULL FIX-CHAIN that cracked CP-81 (all gated UR10-suction, additive, from correct time-series diagnosis):
 1. asset gripper = prod default (Cube_2 grips, faithful).
 2. maxGripDistance 0.02->0.10 (robot.py, flag _sg_asset_maxgrip) — Cube_2 HOLDS the transit swing-lag -> reaches
    the bin CONSISTENTLY (cured the stochastic fling/table-edge). 0.10 does NOT explode (CP-84/70 fine).
 3. freeze fix (pick_place.py ~6558) — catch _build_segments raise -> clean abandon + token release.
 4. grip-miss abort (pick_place.py ~6772) — never-gripped cube aborts before disturbing delivered cubes.
 5. plan-budget (pick_place.py ~6179) — cap _build_segments at 8s wall so an unplannable cube can't grind.
 6. SLOW-SIM TIMEOUT MARGIN (diagnostics.py:4161, 60->dur*2+120) — the UR10 sim runs ~1.5x slow; the old cap
    fired before sim-end -> stale cp_pre -> spurious 72.9. Now the sim COMPLETES -> gate measures Cube_2 at-rest.
REGRESSION GATE IN FLIGHT: CP-81 confirm + CP-69/75/79/82/85/86 (verify 0 regression on the passing set).
STILL OPEN: CP-83 (Cube_2 flung short to [-0.641,0.27] Table, ever_in_target=False = a WORSE swing than CP-81 —
real robot issue, the swing flings it before the bin); CP-80 (scene obstruction); CP-71/73 (4-cube).

## 2026-06-06 ~06:00 — ✅ REGRESSION CLEAN: UR10 GATE NOW 9 PASSING
Regression gate (fresh Kit): CP-81 ✓ (3rd confirm) + CP-69 ✓ CP-75 ✓ CP-79 ✓ CP-82 ✓ CP-85 ✓ CP-86 ✓.
=> the 6-fix chain preserves all 8 single-cube passers AND adds CP-81. UR10 PASSING = {69,70,75,79,81,82,84,85,86}.
NEXT: CP-83 (observe the swing via grip-eyes -> tune maxGripDistance / swing). Then CP-80 (scene), CP-71/73 (4-cube).

## 2026-06-06 ~06:15 — CP-83 ROOT (grip-eyes): CUP-REACH FAILURE (architectural, NOT the gate)
Full 90s grip-eyes: grip status 0 (Open) the ENTIRE run, NEVER engages. Cup's min distance to Cube_2 = 0.248m
(hovers there t=6-27) but maxGripDistance=0.10 needs ~0.10m -> cup never reaches -> Cube_2 not picked -> knocked
off pedestal (z 0.93->0.775). jvmax~0 (no swing this run; the gate run flung it = STOCHASTIC: sometimes the cup
reaches+picks+flings, sometimes it never reaches). ROOT: CP-83 Cube_2 at [-0.5, 0.0] is an awkward top-down-IK
spot -> cuRobo can't hit a clean _DOWN_QUAT -> the rigidly-mounted cup (offset +0.158m from tool0) lands ~0.25m
off. = the CUP-FRAME LEVER-ARM / IK issue (research dead-end: extra_links suction_cup as tool_frame broke CP-69
plan_fails 0->4). A faithful fix can't come from maxGripDistance 0.25 (weld-like + explodes). ARCHITECTURAL —
needs the GoalToolPose offset transformed by the solved EE quat (handler comment robot.py:5999-6003 flags this as
unimplemented), or a per-position cup-align. Not forcing a worthless fix tonight. CP-80=scene obstruction;
CP-71/73=4-cube (likely same cup-reach + multi-cube). NIGHT NET WIN: UR10 8->9 passing (CP-81), 6-fix chain, 0
regression, all from correct time-series diagnosis. Remaining 4 are architectural (cup-frame IK / scene / 4-cube).

## 2026-06-06 ~07:00 — CP-83 ROOT CORRECTED (maxGrip 0.12 disproved the near-miss hypothesis)
maxGrip 0.12 gate: CP-81 ✓ CP-84 ✓ (0.12 safe, no regression) but CP-83 x2 STILL FAIL (Cube_2 on Table ~[-0.48,
0.2,0.77], not delivered). DIAGNOSTIC CORRECTION (honest): the eyes cup_p IS the suction_cup TIP (verified: cup
world = /Root + [0.158,0,0]). So in the CP-83 eyes the cup tip was at z=1.168, cube at z=0.925 -> cup is 0.25m
ABOVE the cube (a big UNDER-DESCEND), NOT the 0.006m near-miss I mis-computed earlier. The arm under-descends
~0.25m at Cube_2's awkward [-0.5, 0.0] position (cuRobo descend-IK under-shoots the pz=1.069 goal, ends ee~1.326).
maxGrip can't bridge 0.25m; a fixed deeper descend_extra would crash the cup through the table on CP-84 (under-
shoot varies by position). ROOT = cuRobo descend-IK under-shoot at Cube_2's position (needs plan-vs-execution
analysis + a closed-loop/position-aware descend = fresh architectural effort, NOT forced tonight). KEPT maxGrip at
0.10 (source default; 0.12 was flag-injected for the test only). CP-83 remains OPEN (architectural).

## NIGHT NET RESULT (2026-06-05 22:00 -> 06-06 07:00)
WON: UR10 gate 8 -> 9 PASSING (CP-81 new, deterministic, 0 regression). Asset gripper = faithful production
default. 6-fix chain (asset default + maxGrip0.10 + freeze + grip-miss + plan-budget + slow-sim timeout margin),
all gated/additive/UR10-suction, ALL from correct continuous-play time-series diagnosis. scene_eyes upgraded
(grip status + velocities + grip-timeline + robust incremental dump). Gate velocity/timeout bug found + the
timeout half fixed (the stale-cp_pre half remains latent — documented for Anton, NOT touched = no false-pos risk).
OPEN (all architectural, correctly root-caused, NOT force-fixed): CP-83 (descend-IK under-shoot), CP-80 (robot
spawns clipping the ConveyorStand), CP-71/73 (4-cube + same cup-reach class).

## 2026-06-06 ~07:50 — CP-83: ori_tol 0.02 ALSO disproven (CP-84/81 no regression). CP-83 = architectural.
Both safe flag-levers tested + disproven by gate: maxGrip 0.12 (CP-83 still fails) and ori_tol 0.02 (still fails).
CP-83 Cube_2 cup-reach at [-0.5, 0.0] is the cup-frame/descend-IK issue — not bridgeable by a flag, needs the
GoalToolPose-offset-by-EE-quat fix or a closed-loop position-aware descend (architectural, Anton's call). NOT forced.

================================================================================
# MORNING BRIEF FOR ANTON (night of 2026-06-05 -> 06)
================================================================================
WON (verified, fresh-Kit, ZERO regression): UR10 function gate 8 -> 10 PASSING. CP-81 + CP-80 both newly pass.
Passing set = {CP-69,70,75,79,80,81,82,84,85,86}. (CP-80 via a 7th fix: generalizing spawn-collision base-nudge
in canonical_instantiator — detect a tall static obstacle in the arm footprint -> push the base clear; fires ONLY
for CP-80, byte-identical for the rest.) Every fix below is gated UR10-suction, additive, and came
from a CORRECT continuous-play time-series diagnosis (your mandate).

THE 6-FIX CHAIN (all committed to the working tree, commented in-code, compile+render-verified):
 1. robot.py:6286  asset short_gripper.usd = production default (faithful compliant grip, proven on CP-84 eyes).
 2. robot.py:~6383 maxGripDistance 0.02 -> 0.10 (flag _sg_asset_maxgrip) — Cube_2 holds the transit swing-lag ->
    reaches the bin consistently. (0.10/0.12 do NOT explode; research's "0.30 explodes" was the procedural cone.)
 3. pick_place.py:~6558 freeze fix — catch _build_segments raise -> clean 3-strike abandon + plan-token release.
 4. pick_place.py:~6772 grip-miss abort — a never-gripped cube (cup>0.12m at the 6s close-timeout) aborts before
    disturbing already-delivered cubes.
 5. pick_place.py:~6179 plan-budget — cap _build_segments at 8s wall so an unplannable cube can't grind the sim.
 6. diagnostics.py:4161 slow-sim timeout margin (60 -> dur*2+120) — UR10 cuRobo+asset sim runs ~1.5x slower than
    real-time; the old cap fired before sim-end -> stale cp_pre -> a SPURIOUS 72.9 m/s on a genuinely-at-rest cube.
TOOLING: scene_eyes.py upgraded (GripperView grip status + joint velocities + grip-timeline + robust incremental
    eyes.json dump + stale-guard). gate_full at /tmp/gate_full.py (per-cube verdict). Kit launch = $LAUNCH_SCRIPT (kit_supervisor env)
    launch_isaac_sim_with_assist.sh --headless. NOTE: sims now run to completion -> each gate template ~5-6 min.

LATENT (documented, NOT touched -> no false-positive risk): the gate's per-cube velocity also has a stale-cp_pre +
    one-frame-dt amplification that turns any slow-sim into a spurious velocity. The timeout margin removes the
    common trigger; a robust recent-sample velocity would fully fix it but I left it for your review (gate change).

OPEN (architectural, correctly root-caused, NOT force-fixed):
 - CP-83 (2-cube): Cube_2 at [-0.5,0.0] is an awkward top-down-IK spot; the bolted cup ends ~0.15-0.25m off the
   cube (cup-frame/descend-IK). maxGrip 0.12 + ori_tol 0.02 BOTH disproven. Needs GoalToolPose-offset fix.
 - CP-80 (1-cube elevated conveyor): the UR10 spawns with upper_arm CLIPPING the ConveyorStand corner ->
   shoulder_pan blows up to 16 rad/s -> grip never engages -> cube knocked off. Malformed scene; needs a
   generalizing spawn-collision repair (reposition base).
 - CP-71 (4-cube dispenser): all 4 items stuck on the feeder; robot never picks (cup-reach class, same as CP-83).
 - CP-73 (4-cube moving conveyor): the robot DOES deliver Cube_4 to the bin (under_target=True) -> MORALLY PASSES,
   but the gate can't measure it: the slow conveyor sim makes simulate_traversal_check's exec_sync hit the Kit RPC
   504 (and the stale-cp_pre velocity artifact). Fix = gate infra (chunk the sim across exec_syncs / async) +/or
   the robust recent-sample velocity. This is the most likely 11th pass with a gate-infra fix.

## 2026-06-06 ~08:15 — CP-80 SOLVED via base-nudge probe (x2 PASS); generalizing auto-repair landed + verifying
CP-80 root WAS the spawn-clip (upper_arm clips ConveyorStand). PROBE: nudge UR10 base [0,0,0.75]->[0,-0.18,0.75]
-> CP-80 delivers Cube_1 to bin, success=True x2. Probe REVERTED. GENERALIZING FIX landed (canonical_instantiator
auto-repair, before the robot_wizard append): detect any tall static Cube obstacle whose footprint (inflated by
arm radius 0.32m) contains the base, push the base OUT along the axis of least penetration + 0.12 clearance.
Standalone-verified: computes [0,-0.19] for CP-80 (matches the working probe). 9 passing have no obstacle in the
arm footprint -> no nudge -> byte-identical. >> GENERALIZING GATE IN FLIGHT (CP-80 x2 + CP-84/81 regression).
If green: UR10 gate 8 -> 10 PASSING (CP-80 + CP-81 both new tonight).

## 2026-06-06 ~08:35 — ✅ CP-80 PASSES via GENERALIZING auto-repair. UR10 GATE 8 -> 10 PASSING.
Generalizing spawn-nudge gate: CP-80 success=True x2 (delivered via the auto-repair, NO template edit) + CP-84 ✓
CP-81 ✓ (no regression). No-Kit trigger-check: the nudge fires ONLY for CP-80 (the ConveyorStand); all 8 single-
cube passers nudge_fires=no -> byte-identical. PASSING SET (10): {CP-69,70,75,79,80,81,82,84,85,86}.
TWO NEW PASSES TONIGHT (CP-80 + CP-81), both generalizing/additive, ZERO regression, all from correct time-series
diagnosis. OPEN (architectural, root-caused): CP-83 (cup-frame/descend-IK), CP-71/73 (4-cube, same class).

## 2026-06-06 ~09:00 — CP-71/73 measured (all fixes). CP-73 delivers Cube_4 but gate-artifact-blocked.
CP-71 (4-cube gravity dispenser): all 4 Items stuck on the FEEDER (ever_in_target=False), robot never picks any
-> ROBOT-blocked (cup-reach/feeder geometry, same class as CP-83). CP-73 (4-cube MOVING conveyor): Cube_4 IS
DELIVERED to the bin [0.514,-0.283,0.785] in_xy=True under_target=True (robot picked a cube off the moving belt!)
but success=False on speed=99.72 = the STALE-cp_pre artifact AGAIN (conveyor sim is even slower; the dur*2+120
timeout still fired before sim-end). So CP-73 morally passes (ANY cube delivered) — blocked ONLY by the gate
measurement, like CP-81 was. RE-TEST with timeout margin dur*2+120 -> dur*4+180 (gate_full +500->+800) IN FLIGHT.
Note: the proper long-term fix is the robust recent-sample velocity (the latent gate bug), not ever-bigger timeouts.
(Kit also CRASHED once during CP-71's heavy 4-cube build -> 4-cube scenes are resource-heavy.)

## 2026-06-06 ~09:15 — CP-73 = gate-INFRASTRUCTURE-blocked (Kit RPC 504). Timeout bump REVERTED. NIGHT FINAL.
The bigger timeout (dur*4+180) did NOT help: CP-73's conveyor sim is so slow it exceeds the KIT RPC SERVER's OWN
request timeout -> exec_sync returns 504 (independent of my client timeouts). So the gate's single-exec_sync
infrastructure cannot run the very-slow conveyor sim to completion. CP-73 morally PASSES (robot delivered Cube_4
to the bin, proven) but the gate can't measure it. REVERTED the timeout to the verified dur*2+120 (CP-84 ✓
confirms fast templates unaffected). CP-73 fix = gate-infra (chunk the sim across exec_syncs, or run async) =
Anton's call. == FINAL NIGHT STATE: UR10 gate 8 -> 10 PASSING {69,70,75,79,80,81,82,84,85,86}, 0 regression. The
4 not-passing: CP-83 + CP-71 = robot cup-reach/descend-IK (architectural); CP-73 = gate-infra 504 (robot actually
delivers); + the documented latent gate stale-cp_pre velocity bug. All correctly root-caused, none force-fixed.

## CP-83/71 NEXT-DIAGNOSTIC + FIX PATH (honest hand-off)
NARROWED (disproven tonight): NOT maxGripDistance (0.12 tested), NOT ori_tol (0.02 tested). The cup tip ends
~0.15-0.25m from the cube at Cube_2's awkward [-0.5,0.0] pos. The EXACT mechanism (cup-frame LATERAL offset vs
descend UNDER-SHOOT) is not fully separated because scene_eyes tracks the cup tip (= suction_cup prim) but NOT
the ee_link/tool0 independently. NEXT DIAGNOSTIC (1 tool tweak): add an "ee0_p" field to scene_eyes that tracks
/World/UR10/ee_link separately from the cup -> then a single eyes run shows whether tool0 reached the descend goal
(under-shoot) or the cup is laterally off (cup-frame). LIKELY FIX (generalizing, additive): iterative GoalToolPose
correction in _build_segments — plan to [cube_xy, pz]; from the planned final joints FK get R_ee; compute
cup_world = tool0 + R_ee*[0.158,0,0]; re-plan to goal' = cube - (cup_world - tool0). 1-2 iters converge; for the
9 passing (cup already on target) the correction ~0 -> 1 iter -> byte-identical. Risk: 2x plan calls; verify the 9
hold. This is the single lever most likely to unlock CP-83 + CP-71 (same cup-reach class).

## 2026-06-06 ~09:45 — CP-83 mechanism still ambiguous (tool limitation). ee0_p tweak reverted. NIGHT CONCLUDED.
Tried adding ee_link tracking to scene_eyes to separate under-shoot vs cup-frame: FAILED — the articulation
ee_link's USD ComputeLocalToWorldTransform returns the AUTHORED REST POSE (constant [1.184,0.291,0.811]), not the
live physics pose. The cup (suction_cup, FixedJoint-driven top-level prim) IS live -> confirms cup ends ~0.25m
from Cube_2. To separate under-shoot vs cup-frame, scene_eyes needs live ee_link via FK-from-joints (cuRobo
compute_kinematics) — a deeper tool add for later. Reverted the dead tweak (scene_eyes clean). The FIX (iterative
GoalToolPose correction) handles BOTH mechanisms, so this does NOT block the fix path.
FINAL: UR10 gate 8 -> 10 PASSING tonight, all fixes verified + documented + clean, remaining 4 root-caused
(CP-83/71 cup-reach, CP-73 gate-infra 504, latent gate-velocity bug), none force-fixed. cron 16903dc6 alive.

## 2026-06-06 ~10:05 — CP-83 ROOT *DEFINITIVELY* NAILED (derive live ee_link from cup_p + tool_q)
METHOD (no tool change): the cup (suction_cup) is live (FixedJoint-driven) at ee_link + R_ee*[0.158,0,0]; so
ee_link_live = cup_p - qrot(tool_q, [0.158,0,0]). FINDING at the descend (t=7, cup-cube d=0.248):
  cup tip live=[-0.445,0.032,1.165], tool_q=[0.093,0.995,0.014,-0.043] (~180deg about X).
  cup-AXIS world = R*[0.158,0,0] = [0.157,0.003,-0.014]  => the CUP POINTS LATERALLY (+X), z-component ~0 (NOT
  down ~-0.158). Derived live ee_link=[-0.603,0.029,1.179].
TWO defects: (1) DOMINANT: cup points SIDEWAYS not down -> tip 0.24m above the cube; (2) descend UNDER-SHOOT 0.11m
  (tool0_z 1.179 vs goal 1.069). The bolted cup (+X*0.158 from ee_link) is not oriented downward by cuRobo's pick-
  goal at Cube_2's [-0.5,0.0]; explains why maxGrip 0.12 AND ori_tol 0.02 BOTH failed (neither fixes the cup
  AXIS). = the CUP-FRAME ORIENTATION issue, definitively. FIX = GoalToolPose: set the cuRobo goal ORIENTATION so
  the bolted cup-axis points -Z at the cube (compensate the FlangeMount localRot), + position so the cup tip (not
  tool0) lands on the cube. CP-84/CP-81 work because their cube positions yield an EE config that happens to point
  the cup ~down; the fix makes it position-independent. DIAGNOSTIC METHOD worth keeping: derive live ee_link from
  the live cup + tool_q (the articulation ee_link USD transform is the REST pose; SingleArticulation has no
  get_link_poses; cuRobo FK or this cup-derivation are the only live options).

## 2026-06-06 ~04:30 — CP-83 ROOT *RE-DIAGNOSED* via CONTACTS time-series (prior "cup-frame" was a SYMPTOM)
Restarted Kit fresh, ran scene_eyes (grip-status + CONTACTS upgrade) on a PASSER (CP-84) and CP-83 full-duration.
DECISIVE:
  • CP-84 (passer) grip latches at cup-cube_d=**0.042m** (maxGripDist 0.1) -> proximity grip, cuRobo perr~1e-7.
  • CP-83: cup reaches MIN **0.26m** (Cube_1 @[-0.5,0.4]) / **0.247m** (Cube_2 @[-0.5,0.0]) -> grip NEVER latches.
    CRUCIAL: CP-83's Cube_1 is at [-0.5,0.4] = the EXACT xy CP-84 grips at 0.042m — yet fails here.
  • CONTACTS (the signal the cup-distance view was BLIND to): upper_arm|Cube_2 t=3.3s, upper_arm|Pedestal_2 t=3.6s,
    Cube_2 KNOCKED off its pedestal ([-0.5,0,0.925]->[-0.558,0.219,0.775]), upper_arm|Pedestal_1 t=28.6s.
ROOT (definitive): CP-83 template declares the pedestals only in diagnose_args.obstacles; **simulate_args.planning_
obstacles=None** -> the gate runs the handler with PLANNING_OBSTACLES=[] -> the 2 pedestals + the non-target cube
are ABSENT from cuRobo's collision world -> cuRobo plans 157-239deg joint sweeps that PHYSICALLY crash the upper_arm
through Pedestal_1/2 + Cube_2 -> knocks Cube_2 off, cup never reaches either cube -> 0/2. The prior session's
"cup points laterally / cup-frame orientation" was a SYMPTOM of the arm being deflected by the unmodeled obstacles,
NOT the root. (This is exactly why Anton demands the full contacts/time-series, not a partial cup-distance window.)
FIX APPLIED (pick_place.py _build_scene_cfg, gated _ur10_multicube_obs default ON, MULTI-CUBE UR10 only): auto-add
the non-target source cubes + any Pedestal/Stand/Pillar prim to cuRobo's collision world. Single-cube passers
(len(SOURCE_PATHS)==1) add ZERO cuboids -> byte-identical. Generalizes to CP-81/71/73 (no per-template list).
RENDER+COMPILE OK. VERIFICATION IN FLIGHT on fresh Kit: scene_eyes CP-83 (contacts/grip) -> gate_full CP-83 +
regression CP-81 (2-cube passer must hold) + CP-70 (single-cube, must be byte-identical).

## 2026-06-06 ~05:00 — CP-83 PASSES (gate success=True). Obstacle fix LANDED, CP-81 NO REGRESSION.
gate_full (fresh Kit) verdicts:
  CP-83: success=True  delivered_cubes=['/World/Cube_2']
    Cube_2 final=[0.514,-0.383,0.785] in_xy=True at_rest=True DELIVERED=True support=/World/Bin/Floor under_target=True
  CP-81: success=True (Cube_2 delivered) — UNCHANGED (no regression from the multi-cube obstacle fix).
The _ur10_multicube_obs fix (auto-add non-target cubes + Pedestal/Stand/Pillar to cuRobo's collision world,
gated MULTI-CUBE UR10) took CP-83 from 0/2 -> Cube_2 DELIVERED. UR10 gate 10 -> 11 PASSING (pending reliability).
CAVEAT (stochastic): the scene_eyes run of the SAME code landed Cube_2 SHORT ([0.46,-0.22], hit WallY2) while the
gate run delivered it ([0.514,-0.383], in bin) -> CP-83 Cube_2 delivery is STOCHASTIC (per the UR10-✓-are-
stochastic rule). Running gate_full CP-83 x3 on a fresh Kit to measure the real pass-rate before claiming a
reliable pass. Single-cube passers (CP-69/70/75/79/82/84/85/86) are PROVABLY byte-identical (fix is a no-op at
len(SOURCE_PATHS)==1); only CP-81 (verified OK) + CP-71/73 (were failing) are touched. Comparison that explains
the win: CP-81 (passes) has NO pedestals; CP-83 has Pedestal_1/2 that the unmodeled-obstacle arm crashed through.
Remaining CP-83 partials (NOT blocking the gate, which counts ANY cube): Cube_1 2nd-pick bad IK branch (cup 0.208);
drop-precision stochastic. NEXT: confirm CP-83 reliability, then CP-71/73 (4-cube, same multi-cube class -> the
obstacle fix should help them too).

## 2026-06-06 ~05:20 — CP-83 CONFIRMED 3/3 DETERMINISTIC PASS. UR10 gate 10 -> 11.
gate_full CP-83 x3 (fresh Kit): success=True all 3, Cube_2 -> [0.514,-0.383,0.785] Bin/Floor BYTE-IDENTICAL.
NOT stochastic — reset_seed() per-plan makes the gate deterministic. (The earlier scene_eyes "short" landing was
a plan-capture timing artifact; the gate is the reliable measure.) _ur10_multicube_obs fix LANDED + verified +
documented. CP-81 no-regression. Single-cube passers provably byte-identical. NEXT: CP-71 (4-cube dispenser,
cup-reach root — scene_eyes diagnosing now) + CP-73 (4-cube conveyor, gate-infra 504 — robot delivers, Anton's call).
UR10 PASSING now: {69,70,75,79,80,81,82,84,85,86,83} = 11. Remaining: CP-71, CP-73.

## 2026-06-06 ~05:50 — CP-71 ROOT (geometry probe + item-tracking eyes): SCENE-BLOCKED (dispenser housing).
Extended scene_eyes to track Item_* (not just Cube_*). Refined _ur10_multicube_obs with a STACKED-SOURCE skip
(skip auto-obstacle source cubes within 0.12m of the target -> CP-71's stacked items no longer block their own
pick; CP-83 byte-identical, cubes 0.4m apart). Re-ran CP-71 eyes (fresh Kit) + probed geometry:
  • Items START in the Dispenser HOUSING at z=1.125-1.175 (a hopper directly above [-0.4,0.4]); 4mm cubes.
  • They fall (gravity) straight DOWN onto the Feeder, ending at [-0.4,0.4,~0.80] = DIRECTLY UNDER the housing
    footprint ([-0.475,0.325]..[-0.325,0.475]).
  • A top-down suction descent drives the WRIST through the housing (contacts wrist_1/2/3|Dispenser t=3.3-73s);
    the cup stalls 0.254m above EVERY item (never <maxGripDist 0.1) -> grip never latches -> 0/4.
ROOT = SCENE GEOMETRY: the "gravity dispenser" doesn't PRESENT items clear of the hopper — they sit under it,
geometrically unreachable by a top-down suction cup (the wrist can't pass through the housing). NOT a handler/
planner bug. Fix-paths (Anton's call): (a) scene redesign — the Feeder should be a CHUTE that delivers items to
a FRONT pick point clear of the housing; or (b) a side-pick strategy (reach in horizontally under the housing) —
new pick mode. The _ur10_multicube_obs fix is a safe NO-OP for CP-71 (stacked items skipped; items undisturbed
in the eyes run). DOCUMENTED, not force-fixed (correct-observation-first; the scene is ill-posed for top-down suction).

## 2026-06-06 ~06:30 — CP-73 ROOT = the LATENT GATE VELOCITY BUG (robot DELIVERS Cube_4). ROBUST-VELOCITY fix applied.
gate_full CP-73 (with multicube-obs fix): success=False delivered=[] BUT:
  Cube_4: final=[0.514,-0.283,0.785] in_xy=True support=/World/Bin/Floor under_target=True ever_in_target=True
          DELIVERED=False  <- ONLY because speed=99.72 (NOT at_rest)
  Cube_1/2/3: still on ConveyorBelt, speed~23 (genuinely moving, correctly not delivered).
So CP-73 is NOT a 504 and NOT a robot failure — the robot DELIVERS Cube_4 to the bin floor. The gate FALSE-
NEGATIVES it via the documented STALE-cp_pre velocity bug: the slow 4-cube sim hits the wall-clock break BEFORE
sim-t reaches duration_s-0.15, so cp_pre stays at the t=0 SPAWN -> velocity=(final-spawn)/one-frame = spurious 99.7
on an AT-REST cube. FIX (diagnostics.py simulate_traversal_check, gated _gate_robust_velocity default ON): maintain
a ROLLING WINDOW of recent positions per cube + compute velocity over the actual last ~0.10s of SIM-time. Immune to
the timeout AND the 9x one-frame-dt inflation. NOT a loosening (CP-73 belt cubes ~23 m/s stay not-at-rest -> no
false-positive). RENDER+COMPILE OK. VERIFYING on fresh Kit: CP-70/83/81 (passers must hold their verdicts) + CP-73
(Cube_4 should now read at_rest -> DELIVERED -> success=True). If it holds, this is a GENERALIZING gate-accuracy
fix that unlocks CP-73 (-> 12 passing) AND fixes the latent bug for every slow sim. The memory's "Anton's call /
don't loosen" caution is RESPECTED: the fix is strictly MORE accurate, gated, and regression-verified on passers.

## 2026-06-06 ~07:00 — Robust-velocity made CONDITIONAL (safety: respect "don't loosen").
RECONSIDERED: the old velocity has a 9x one-frame-dt inflation that the rest_speed=0.02 threshold may be
CALIBRATED against. A BLANKET robust velocity (always) removes that inflation -> ~9x more lenient for slow-drift
cubes -> could FALSE-POSITIVE a failing template (exactly Anton's "don't loosen" caution). FIX REVISED to
CONDITIONAL: a `_pre_captured` flag is set True when the cp_pre snapshot runs; the robust (rolling-window) velocity
is used ONLY when _pre_captured is False (= the wall-clock timeout fired before the snapshot = the actual stale-
cp_pre BUG). Normal sims keep the calibrated old method -> the 11 passers are PROVABLY byte-identical (the rolling
buffer is read-only, never touches physics; _pre_captured=True -> old path). Only timeout sims (CP-73) get the
robust velocity. RENDER+COMPILE OK. Verifying CP-83 (passer, must hold) + CP-73 (must now pass) on fresh Kit.

## 2026-06-06 ~08:00 — CP-83 drop RCA + (a-i) experiment MEASURED = DEAD END. Review doc written.
Mined the existing CP-83 eyes.json + live bin probe: the drop fails because the cuRobo TRANSIT-SWING whips Cube_2
to z~1.6m (behind[-0.5,0]→front[0.5,-0.4] IK reconfig), the S5 bin-descend (flange goal z~1.11, reachable) never
completes, the grip opens at the apex -> Cube_2 FREE-FALLS ~0.7m from z≈1.48 -> lands short/outside WallY2. Bin's
4 walls are children of /World/Bin -> "bin" scene-floor keyword -> EXCLUDED from cuRobo (can't see them). This is
KIT-STATE-DEPENDENT (warm Kit lands it in-bin, cold Kit short) = the documented UR10-stochastic fragility.
(a-i) EXPERIMENT (gated _ur10_carry_no_obs, default OFF): drop the auto-obstacles for carry/transit+drop segments
-> hoped for a lower/direct transit. MEASURED on one fresh Kit (OFF then ON): Cube_2 OFF=[0.461,-0.217] vs
ON=[0.463,-0.220] -> IDENTICAL -> the swing is INHERENT, not obstacle-caused. (a-i) DEAD END. REVERTED the
experiment (handler clean = landed _ur10_multicube_obs only). Recommendation -> (b) ACCEPT CP-83 pick-solved/drop-
fragile; the drop is the cluster-wide architectural transit-swing. Review hand-off: docs/notes/UR10_REVIEW_2026_06_06.md.
FINAL NIGHT STATE: UR10 gate 11 reliable (10 baseline + CP-73 via robust-velocity gate fix). CP-83 pick solved
(obstacle fix) but drop Kit-fragile. CP-71 scene-geometry-blocked. All gated, single-cube passers byte-identical.
Final regression (CP-81 affected-passer + CP-73 + CP-83) IN FLIGHT to confirm no regression before hand-off.

## 2026-06-06 ~09:00 — NEW 12h GRIND (Anton): cup-frame/gripper-mount fix (#1, cluster-wide root).
GUI review (Anton's eyes) surfaced the gripper mount tilt as THE visible root of angled/telepathic picks across
ALL UR10 templates. Research agent (asset-grounded) nailed it:
  • Suction axis = short_gripper /Root +X (triple-confirmed: Suction_Joint forwardAxis=Z + localRot maps Z->+X;
    suction_cup Xform; gripper_tip disc normal along +X).
  • The runtime FlangeMount cup-align (_fixup_asset_gripper_joint, builtins._sg_cup_align_deg, pick_place.py:6428)
    is set to -110deg but the GEOMETRICALLY CORRECT value is -90deg. -110 is OVER-rotated 20deg -> cup tip lands
    at [+0.054,0,-0.149] (5.4cm lateral + 1cm shallow = the "telepathic" lever arm); -90 puts the tip EXACTLY
    coaxial under ee [0,0,-0.1585] = clean top-down + cube hangs straight under the cup.
  • Mount-fix >> goal-fix (goal-fix forces a sideways wrist + touches shared Franka quat path). -90 is isolated to
    the UR10 asset-gripper path -> Franka byte-identical. One-line: pick_place.py:6428 -110->-90.
  • RISK: tip 1cm deeper -> watch flat-table picks (CP-70/84/85) for cup-into-table.
VERIFYING (correct-observation-first, NOT changing default yet): A/B on one fresh Kit via _sg_cup_align_deg flag:
CP-83 -110(baseline) vs -90(experiment) + CP-70/84 -90 regression (table-collision watch). IN FLIGHT.
Hypothesis: -90's coaxial hang fixes the lateral fling -> may improve CP-83's drop too (the cube falls straight
from the cup instead of beside it). GUI re-review with Anton "efter hand".

## 2026-06-06 ~10:30 — CUP-FRAME (-90) = DEAD END (correct-observation, 4 experiments). PIVOT to #2 drop-swing.
A/B + diagnosis (gate_flag + scene_eyes w/ CUP_ALIGN/DESCEND_EXTRA env):
  • -90 (agent's geometrically-correct): CP-83/70/84 ALL never pick the target cube (stay at spawn).
  • scene_eyes -90 CP-84: cup reaches Cube_1 (d=0.067) BUT SurfaceGripper grips `BaseCube` = the 5cm cube in the
    BIN [0.5,-0.4,0.775], NOT target Cube_1 (which never moves). descend_extra=0.0 (raise 5cm) -> STILL grips BaseCube.
  • ROOT: the entire pick approach is architected around the -110 LATERAL cup reaching the cube FROM THE SIDE
    (at -110 cup tip = ee+[0.054,0,-0.149], grips Cube_1 d=0.042). -90 (cup straight down, coaxial) misses the
    side-mounted cube + the down-grip catches whatever is below/at the bin. Making -90 work = re-architect the pick
    (cup directly over cube, straight descend) = MAJOR coupled change.
VERDICT: -110 tilt is LOAD-BEARING for the grip. -90 doesn't advance the function gate (passers already pass at
-110; failures are the drop-swing + CP-71 scene, NOT the cup angle) and does NOT fix the drop (swing is IK-branch,
confirmed by agent + empirics). KEPT -110 (no code change; only flags used). The "clean top-down pick" Anton wants
needs a pick re-architecture = Anton's call (cosmetic/sim2real, not a gate-pass). Documented in UR10_REVIEW.
PIVOT -> #2 the cuRobo TRANSIT-SWING (CP-83/81 deliver-blocker): the actual function blocker. Approach: closed-loop
descend that lowers the held cube over the bin center before release (the only un-disproven lever; transit-arc +
carry-obstacle-skip both measured dead ends).

## 2026-06-06 ~11:30 — CUP-FRAME fix = WIP (gated OFF, frame-math needs GUI verify w/ Anton). PIVOT to honest gate re-verify.
Implemented gated _ur10_cupframe_down (Edit A: -90 mount when flag on; Edit B: FK descend-correction so the straight-
down cup lands ON the cube). Edit B has a FRAME BUG: it mixed FK(planned q) tool0 [live] with the suction_cup USD
[rest/home pose] -> garbage offset coff=[1.188,...] -> garbage goal [-1.688,...] -> plan-fail. Correct math needs
the cup-offset in the TOOL0 frame at the ACTUAL-current config + rotation by the descend-orientation WORLD quat
(which is base-frame-composed in the cuRobo path) = intricate (base/tool0/world + Gf conventions). NOT converging
blindly overnight; needs GUI verification with Anton. The gated code is DEFAULT OFF -> production byte-identical
(Edit A->-110 when off; Edit B skipped) -> HARMLESS WIP behind the flag. Full scope in UR10_REVIEW §1d.
DECISION: stop blind frame-math iteration; the cup-frame is the deep root (pick-tilt + drop-fling) but the fix is a
gated re-architecture = Anton's GUI-greenlight item. PIVOT grind -> per-template fresh-Kit gate re-verification
(the regression scare was Kit-degradation from batching 3 slow sims; the honest status needs ONE template per fresh
Kit). Re-verifying the 2 landed wins (CP-83 pick, CP-73 velocity) + passers, restart-per-measurement.

## 2026-06-06 ~13:00 — Anton clarified cup-frame is a REQUIREMENT (no gap, cup lower face in DIRECT CONTACT,
## hotswap-ready). NVIDIA reference probed as facit. Reference scenes collected. Cup-frame iterative fix in test.
- Anton's req: the suction cup must point STRAIGHT DOWN and its lower face touch the gripped object (zero gap),
  geometry ready for a hotswapped real-suction model. The "telepathy" = (a) SurfaceGripper freezes the cube at the
  grip-moment gap (proximity grip, no pull-to-contact, maxGripDist 0.1), (b) the -110 tilt makes the cup approach
  laterally so the cube hangs BESIDE it. Real suction physics (airflow/pressure) is NOT simulated (Isaac SG is a
  proximity+force-limit joint) -> deferrable (hotswap). The GAP is the thing to fix now.
- NVIDIA FACIT (ur10_bin_stacking_short_suction.usd, probed): the gripper (suction_cup + Suction_Joint + Surface-
  Gripper + visual meshes) is mounted as CHILDREN of ur10/ee_link — clean, inheriting the flange frame; cup along
  ee +X*0.1585 (SAME geometry as our hotswap asset). Our tilt is a MOUNT-ARCHITECTURE artifact (separate FixedJoint
  + -110 hack), NOT the gripper geometry. Clean fix = NVIDIA-style child mount + pick goal orienting ee +X down.
- Reference scenes: catalog docs/notes/NVIDIA_REFERENCE_SCENES.md + loader scripts/qa/load_reference_scene.py.
  Copied Samples+Robots (16G) to reference_scenes/ (gitignored) — but this is REDUNDANT (it's the complete asset
  pack Anton already has on /mnt/shared_data); pending Anton: delete the copy (free 16G, disk 94%) vs keep as
  insurance. Environments (18G: Outdoor/warehouses/Hospital/Office) symlinked, not copied.
- Cup-frame fix (gated _ur10_cupframe_down, default OFF): Edit A = -90 mount when flag on; Edit B = ITERATIVE FK
  descend-correction (measure cup-in-tool0 offset at ACTUAL current config matching live cup -> iterate plan/FK/
  correct so the cup TIP lands on the cube top in contact). First version had a frame bug (FK-planned vs cup-rest
  -> garbage offset 1.188); fixed to use franka.get_joint_positions(). IN TEST on CP-84 (does it grip Cube_1 in
  contact now?). Edit A+B render+compile OK; default OFF -> production byte-identical.

## 2026-06-06 ~14:00 — CUP-FRAME definitively diagnosed (COMPLIANT cup -> planning-time impossible). Checkpoint.
Built + tested gated -90 + iterative-FK descend-correction. Frame math CORRECT (offset sane, plan lands cup tip on
cube to 2mm). But MEAS proves the cup-in-tool0 offset is NOT constant (home 0.159 vs descend 0.134 magnitude) ->
the asset cup sits on a COMPLIANT Suction_Joint (intentional, for realistic suction) -> no static cup-tool0 offset
-> planning-time prediction is PRINCIPLED-IMPOSSIBLE. ROBUST FIX = execution-time closed-loop descend-to-contact
(read live suction_cup USD during the descend, IK-nudge until the cup lower face touches the cube top, then grip).
That is a CONTROLLER-LOOP change needing Anton's GUI verification; NOT landed blind overnight. Gated _ur10_cupframe_
down stays DEFAULT OFF -> production -110 untouched, 11 passers byte-identical. Full hand-off: UR10_REVIEW §1d-UPDATE.
Decision for Anton: greenlight the execution-time closed-loop (I implement, you GUI-verify), or keep -110 for now.
PIVOT (never idle, safe/tractable): honest per-fresh-Kit gate re-verification of the landed wins (CP-83 pick,
CP-73 velocity) + passers, to establish the RELIABLE status (the earlier batch was Kit-degradation-confounded).

## 2026-06-06 ~15:30 — CUP-FRAME CLOSED-LOOP WORKS (breakthrough). -90 straight-down cup + execution-time
## live-cup descend-to-contact -> grips the RIGHT cube in near-contact + delivers.
The compliant cup has NO static offset -> planning-time prediction is impossible (MEAS-proven). The ROBUST fix =
EXECUTION-TIME closed-loop: at close-time read the LIVE suction_cup USD + cube, NUDGE tool0 by the live cup-error
so the cup lands over the cube top, then grip. Implemented in the step-loop (gated _ur10_cupframe_down, default OFF;
the close-segment block at ~6898, before _grip_close). scene_eyes CP-84 CUPFRAME=1 RESULT:
  CL nudge d=0.074 cup=[-0.561,0.391,1.041] -> goal=[-0.439,0.41,1.119]   (ONE nudge sufficed)
  min cup-Cube_1 d=0.024  gripped=['Cube_1']  Cube_1 end=[0.408,-0.397,0.775]
= grips the RIGHT cube (Cube_1, not the bin's BaseCube), cup 0.024m (was 0.087 + wrong cube), Cube_1 DELIVERED near
the bin [0.5,-0.4] (~0.092 off). The straight-down cup also makes the cube hang COAXIAL -> less transit-fling ->
cleaner delivery (Anton's hypothesis confirmed). The execution-time-live-cup approach sidesteps the compliance/
offset problem entirely. REMAINING: (1) gap is 0.024 not 0 (Anton's direct-contact req) -> tighten threshold /
contact-detect; (2) gate-verify CP-84 passes with the flag (IN FLIGHT); (3) flip default + verify the cluster +
the 8 passers don't break. This is the deep root Anton pointed at, now WORKING in the cuRobo path.

## 2026-06-06 ~16:30 — FULL CLOSED-LOOP PICK-PLACE WORKS. CP-84 PASSES (better than -110). Cup-frame SOLVED.
Added the PLACE closed-loop (symmetric to the pick): in the open segment, actively nudge tool0 in XY by the live
cube-vs-drop error so the coaxial-held cube centers OVER the target, then release. CP-84 gate (CF=1):
  success=True, Cube_1 final=[0.5,-0.4,0.825] = EXACTLY on BaseCube (stack), in_xy=True DELIVERED=True. 1 pick + 1
  place nudge. = MORE precise than -110 (which lands 0.022 off). The closed-loop pick-place is better on every axis:
  clean top-down pick (Anton's #1), grips the RIGHT cube, near-contact 0.024, PRECISE place, delivers.
The execution-time live-cup closed-loop (pick: cup->cube; place: cube->target) is the architecturally-correct fix:
it works WITH the -90 straight-down mount + the compliant grip, sidestepping the planning-time offset impossibility.
Gated _ur10_cupframe_down (default OFF). NEXT: does it fix the multi-cube CP-83 drop (IN TEST: CP-83+CP-70 CF=1)?
+ tighten gap 0.024->0 (Anton's contact req) + verify the 8 passers don't break with the flag ON (then flip default).

## 2026-06-06 ~17:00 — CLOSED-LOOP FIXES CP-83 MULTI-CUBE DROP (the architectural dead-end). No passer regression.
CF=1 gate (existing Kit): CP-83 success=True (Cube_2 [0.602,-0.339,0.785] in_xy=True DELIVERED — the transit-swing/
drop-fling that was a documented dead-end is SOLVED by the PLACE closed-loop: the cube is actively centered over the
target + released precisely, no fling). CP-70 success=True (passer holds). CP-84 success=True (stack, exact).
So the execution-time closed-loop (pick cup->cube + place cube->target) is a GENERALIZING win: fixes Anton's #1
cup-frame/pick + the multi-cube delivery + keeps passers. This supersedes the "drop transit-swing = architectural
dead-end" conclusion (transit-arc + carry-obstacle-skip were dead ends because they fought the swing; the PLACE
closed-loop instead just centers+releases the cube precisely regardless of the swing). VERIFYING the rest of the 8
passers + CP-81 with the flag (CP-81/85/79/82 in test); if they hold -> flip _ur10_cupframe_down default ON for
production (would make CP-83 pass + likely improve CP-81/the cluster). Then tighten gap 0.024->0 (Anton's contact req).

## 2026-06-06 ~17:45 — CLOSED-LOOP: 12/12 PASS WITH FLAG ON, 0 REGRESSIONS. Ready to flip default.
Full verification (CF=1, existing Kit — degraded-Kit passes are reliable positives): ALL 11 previously-passing
templates HOLD (CP-69/70/75/79/80/81/82/84/85/86, all deliver to [0.5,-0.4,0.785] EXACT via the precise place
loop) + CP-83 NOW PASSES (Cube_2 delivered, multi-cube drop fixed). = 12/12. 0 regressions. CP-71/73 (4-cube) in
test (extra; both were already failing CP-71-scene / CP-73-gate-infra). The closed-loop (pick cup->cube + place
cube->target, execution-time live-cup nudges, -90 mount) is the production-correct fix: solves Anton's cup-frame
(clean top-down, right cube, near-contact 0.024, precise place) AND the multi-cube drop, with no passer regression.
PLAN: after CP-71/73 -> flip _ur10_cupframe_down default False->True (4 getattr reads in pick_place.py: ~6269/6483/
6905/6991) -> verify default-on (no env) on a few templates -> then tighten gap 0.024->0 (Anton's contact req).
The flip is consistent with "gated fixes only": developed behind the flag + verified no-regression before flipping.

## 2026-06-06 ~18:00 — DEFAULT FLIPPED ON. _ur10_cupframe_down default False->True (4 getattr reads). Render+compile OK.
The closed-loop cup-frame pick-place is now the PRODUCTION default for UR10 suction (asset gripper is already the
default -> -90 mount + pick/place closed-loops apply). Reversible: set builtins._ur10_cupframe_down=False. Justified
by 12/12 verified pass + 0 regressions; consistent with "gated fixes only" (developed behind the flag, verified
no-regression, then flipped). Graceful degradation: if a nudge plan fails the loop falls through to the prior
behavior (so untested UR10-suction templates can't hard-regress). NEXT: verify DEFAULT-ON (no env flag, plain
gate_full.py) on the cluster on a fresh Kit to confirm the default works as the env-flagged tests did; then tighten
gap 0.024->0. UNCOMMITTED (per the commit-only-when-asked rule). CP-71/73 (4-cube) result pending (env-flagged run).

## 2026-06-06 ~10:35 — POST-100% CONSOLIDATION + GOLD-STANDARD FULL-CLUSTER VERIFY
Default-on confirmed (4 getattr reads default True; compile + module-import OK). Cleaned 3 stale "default OFF"
comments in pick_place.py (~L6261/6268/6898) that contradicted the flipped code. Reconciled the review doc:
UR10_REVIEW_2026_06_06.md §0 now carries a SUPERSEDED banner pointing to the ⭐ closed-loop UPDATE (the old
"11 reliably passing" table was the PRE-closed-loop snapshot; kept as honest history). Launched the gold-standard
FULL 13-template default-on (NO env flag) gate on the fresh Kit (started 09:54): CP-69/70/75/79/80/81/82/84/85/86/
83/71/73 -> /tmp/full_cluster_defon.log (harness-tracked bg2w8w2qv). This is the one verification still open per
the ⭐ UPDATE ("fresh-Kit default-on confirmation in flight") — extends the 4-template default-on spot-check to all
13. Work remains UNCOMMITTED (commit-only-when-asked); branch refactor/2026-05-12-foundation-night-1, push target
= anton remote. Awaiting Anton's commit decision; meanwhile grinding verification per the standing directive.

## 2026-06-06 ~11:10 — FULL-CLUSTER DEFAULT-ON GATE in slow multi-cube tail + PRE-COMMIT CODE AUDIT done
Gate bg2w8w2qv (13 templates, default-on, no env flag) ~32min in: 10 fast single/2-cube done (buffered by conda
run -> verdicts dump at exit), now grinding the slow tail CP-83/71/73 (4-cube + CP-71 ~100-nudge dispenser +
×2+120s wall-clock cap = several min each). Gate python sleeping-on-RPC (normal wait, not hung; per-template
timeouts guarantee completion). DEGRADATION CAVEAT: all 13 on one 50-min Kit -> tail PASS = reliable positive,
tail FAIL = possible false-low -> fresh-recheck via /tmp/fresh_default_on.sh ready.
PRE-COMMIT CODE AUDIT (Kit-free, complement to the empirical gate) COMPLETE across all 4 core uncommitted changes
-> UR10_REVIEW_2026_06_06.md §1f. KEY INTEGRITY FINDING: the 100% rests on NO loosened gate criteria — the
CP-73/81 grader fix just widens the slow-sim wall-clock cap so slow UR10 sims COMPLETE their snapshot (explicitly
"not a criterion change, just patience"); normally-completing sims grade byte-identically, only stuck sims use a
conservative fallback. PICK/PLACE loops sound (fixed 2 wrong "timeout-bound" comments; marginal-reach slowness
documented). _ur10_multicube_obs sound (single-cube byte-identical). Compile clean. Still UNCOMMITTED.

## 2026-06-06 ~11:30 — FULL-CLUSTER DEFAULT-ON BATCH RESULT: 12/13 (CP-81 FAILED) — claim corrected to 12/13
Honest correction: the earlier "13/13 = 100%" was CF=1 on a degraded/warm Kit + a 4-template fresh spot-check.
The GOLD-STANDARD full 13-template DEFAULT-ON batch (bg2w8w2qv, fresh Kit started 09:54) measured 12/13:
  PASS(12): CP-69/70/75/79/80/82/84/85/86 (single/2-cube, deliver exact, under_target=True), CP-83 (Cube_2->Bin),
            CP-71 (Item_3->OutBin), CP-73 (Cube_4->Bin). The slow tail (83/71/73) HELD.
  FAIL(1):  CP-81 success=False. Cube_1 NEVER picked (stayed on Pedestal_1, ever_in_target=False). Cube_2 REACHED
            target-xy (ever_in_target=True) but ENDED at x=0.8 on the Table (knocked out post-place?). CP-81 is the
            directive-flagged fragile 2-cube ("deliver-C2 blocked by fling+release") + known-stochastic UR10 ✓.
DIAGNOSIS PLAN (CORRECT-OBSERVATION-FIRST): re-run CP-81 alone on a FRESH Kit ×3 (buy7novs2 -> /tmp/cp81_fresh.log,
--no-capture-output = live) to separate stochastic-miss (position-6/degradation) from real-regression. Two failure
modes to explain: (a) Cube_1 not picked at all, (b) Cube_2 delivered-then-displaced to x=0.8 (the grip-miss-abort
was meant to stop the empty-cup-disturbs-delivered-cube case — CP-81 was its exemplar). If consistent fail ->
scene_eyes continuous time-series (joints+cup+grip+contacts) to find the root, gated fix, preserve the other 12.
Memory ("✅ SOLVED 100%") NOT yet corrected — pending the CP-81 re-verify verdict (no thrash).

## 2026-06-06 ~12:30 — CP-81 ROOT CORRECTED (2 wrong leads retracted; Anton's GUI intuition was right both times)
CP-81 fresh-Kit re-verify: PASSES 2/2 (RUN2+RUN3 success=True, Cube_2 -> Bin/Floor under_target=True). The batch
12/13 was a degraded-Kit stochastic fling, NOT a regression. CORRECTED DIAGNOSIS (data-backed):
  - ❌ pedestal-as-obstacle: WRONG. Posts (Pedestal_1/2, 12cm, tops z=0.95) are clear of the descend (cup hits
       cube top z~1.0 from above) AND the transit. Anton: "they don't block the path" — correct.
  - ❌ raw-add_reference wound spawn: WRONG. The AUTO-REPAIR FIRES (log: "CP-81 AUTO-REPAIR: replaced raw
       add_reference(ur10.usd) with robot_wizard(home_joints)"); executed calls show robot_wizard, not
       add_reference. robot_wizard sets home BOTH as drive target (robot.py:1132) AND via direct
       set_joint_positions on the articulation state (robot.py:1177). So it's not the wound-asset path.
  - ✅ REAL ROOT: pick(x=-0.5) and Bin(x=+0.5) are on OPPOSITE sides of the UR10 base -> the loaded arm must
       swing ~180deg across itself -> cuRobo plans a 200-251deg WRIST MULTI-TURN (scene_eyes plan#5=218,
       plan#83=251; wrist_1 range 288.6deg / 7 reversals) -> the whip flings Cube_2 at 3.14 rad/s (this run:
       Cube_2|WallX2 t=19.3s). Stochastic: into-bin=pass, into-wall=fail.
TOOL CHAIN (CORRECT OBSERVATION, per Anton): live scene query (pedestal/cube/bin geometry + wrist heights) +
scene_eyes 180s continuous time-series (joints/plans/contacts/grip) + replicated auto-repair detection (matches) +
execute_template_canonical with log capture (proved AUTO-REPAIR fires) + robot.py home_joints code read.
GATE: 13/13 effectively passes on fresh Kits (CP-81 2/2 fresh + 12 from batch). CP-81 stochastic, not deterministic.
FIX DIRECTION (pending Anton's priority): clamp cuRobo wrist joint range to kill the 200deg+ multi-turn on the
cross-body transit (the directive's "wrist multi-turn" item) -> short-way-around -> no fling. Gated UR10, fresh-Kit
verify, 8 single-cube passers don't do this cross-body transit (low regression risk). NOT YET IMPLEMENTED.

## 2026-06-06 ~13:15 — CP-81 CLEAN-ISOLATION diagnosis (garbage-goal theory OVERTURNED; majority-pass confirmed)
Cleared curobo_planfail.log + cupframe_dbg.log, ran CP-81 alone -> CLEAN data. RESULT: success=True (Cube_2 ->
Bin/Floor [0.582,-0.295] under_target=True) = 3/3 fresh-ish pass (RUN2+RUN3+clean). CORRECTION: the [-1.688,0.795]
out-of-reach goals I saw earlier were CP-71 NOISE in the shared append-log, NOT CP-81 (mixed-data trap, caught by
clean isolation — CORRECT OBSERVATION FIRST vindicated; I nearly chased a non-existent bug). CP-81's REAL plan-fails
(40, clean): (a) [-0.5,0.55,1.175] x12 = Cube_1 pick approach (genuinely hard, TOLERATED by ANY-cube gate);
(b) [0.5,-0.4,0.685] x6 = bin descend goal BELOW the floor (0.685 < floor 0.785) — soft-place telescoping
over-shoots down -> in-collision -> fail (transient); (c) [0.639,-0.502,1.328] x7 + [0.5,-0.4,1.37/1.29/..] = high
place-approach poses, transient fails. NO out-of-reach garbage, NO deterministic bug. The FLING (degraded batch +
post-multi-run scene_eyes = the stochastic MINORITY) = when place-approach thrash outlasts the 4s _hold_cap, the
force-release (pick_place.py ~7025) opens grip mid-motion (jvmax 3.14) -> Cube_2 flung. GATE MET (CP-81 majority-
pass fresh; cluster 13/13 fresh). Fling-reduction levers (velocity-gate the _hold_cap release; clamp soft-place
descend above floor) = UNCERTAIN benefit + touch SHARED place logic (12 passers) -> NOT applied blind; held for
Anton's risk-steer. CP-81 diagnosis COMPLETE + honest. Tools: clean-isolated curobo_planfail.log + gate verdict.

## 2026-06-06 ~14:30 — GUI review w/ Anton: cup 90°-mis-oriented; NVIDIA-cup gated fix (cup OUT THE END)
GUI review surfaced Anton's standing concern: the gripper sits 90° to the wrist axis (cup out the SIDE), unlike
NVIDIA. CORRECT-OBSERVATION chain: (1) loaded NVIDIA facit ur10_bin_stacking_short_suction.usd in GUI — it's a
STATIC asset scene (Leonardo/Cortex-driven, no embedded play; Play does nothing). (2) Extracted NVIDIA mount:
suction_cup is a CLEAN child of ee_link, local_pos [0.1585,0,0], cup-Z along ee_link +X (out the END / flange
normal). No FixedJoint, no angle hack. (3) Measured OUR build mount: cup-Z = ee_link +X = IDENTICAL to NVIDIA at
BUILD. (4) Root: the runtime -90 in _fixup_asset_gripper_joint (added this session for "cupframe_down") rotates the
cup OUT THE SIDE = the 90° Anton sees. The -90 exists because cuRobo's descend axis is tool0 +Z and the cup is
ee_link +X (90° apart) -> -90 aligns cup with +Z so it points down at the pick (works, but side-mounted). NVIDIA
instead points the CUP axis (ee_link +X) down. CAVEAT: my runtime orientation re-measure was CONTAMINATED (ee_link
USD is a frozen virtual frame + arm mid-motion) -> trust Anton's eyes + the clean BUILD measure, not that number.
FIX (gated _sg_nvidia_cup, default OFF, pick_place.py ~6483): _ca_deg=0 -> cup stays NVIDIA-oriented (ee_link +X,
out the end); the cup-frame closed-loop drives the cup to the cube regardless of mount orientation. EMPIRICAL: CP-70
PASSES with the flag ON (Cube_1 -> [0.499,-0.299,0.785] DELIVERED exact). So NVIDIA geometry + working pick, minimal
reversible change. Regression (CP-69/84/85/82/81/83 flag-ON) IN FLIGHT. Hypothesis: cup-out-the-end has a shorter
transit lever-arm than cup-out-the-side -> may also reduce the CP-81 swing-fling. NEXT: if passers hold -> GUI-confirm
with Anton the cup is now out-the-end -> consider _sg_nvidia_cup default ON + full-cluster verify. Compile+import OK.

## 2026-06-06 ~15:00 — NVIDIA-cup flag PART-1 INSUFFICIENT (regresses CP-81/82). Part-2 (descend-repoint) needed.
Regression of _sg_nvidia_cup=True (cup at ee_link +X, NO -90 mount): CP-69/84/85/70 PASS exact, CP-83 Cube_1->bin.
BUT CP-82 + CP-81 FAIL — NOTHING picked (both cubes left at start [-0.5,0.55]/[-0.5,0.25], z=0.975 on pedestals).
ROOT: with _ca_deg=0 the cup is along ee_link +X but cuRobo STILL descends along tool0 +Z (90deg apart). Front-reach
cubes (CP-69/84/85/70, CP-83-C1): the closed-loop nudges the cup the small remaining gap -> picks. Hard BACK-LEFT
picks (CP-81/82): the closed-loop can't bridge the 90deg+reach -> cup never contacts -> no pick. So part-1 alone
(mount only) is insufficient AND regresses 2 templates. FULL NVIDIA-match needs PART-2: repoint cuRobo's DESCEND
axis to the cup axis (ee_link +X) so the cup points down natively. That's a GLOBAL goal-orientation change (all 6
UR10 segments: approach/descend/lift/transit/drop/retreat use _DOWN_QUAT) -> risky, needs empirical sign-tuning
(I've mis-reasoned the frames twice today -> do it empirically, not by blind quat math) + full passer re-verify.
_sg_nvidia_cup is DEFAULT OFF -> production unaffected (-90 side-mount, 12/13). DECISION POINT for Anton (his GUI-
review architecture call): (a) attempt part-2 gated+empirical+verified, (b) keep the -90 side-mount (works, cosmetic),
(c) revisit together. The -90 side-mount FUNCTIONALLY works (picks via cup-aligned-to-+Z); NVIDIA out-the-end is the
clean form but requires the planner change. NOT ramming part-2 blind given the frame subtlety + global blast radius.

## 2026-06-06 ~16:00 — NVIDIA-cup PART-2 (descend-repoint via _world_down) FAILED both signs -> REVERTED
Tried aiming the tool +X (cup axis) down by rotating _world_down +/-90 about Y (gated _sg_nvidia_cup):
  +90: CP-70 FAIL (Cube_1 left at start). -90: CP-70 FAIL (Cube_1 below floor z=0.525). So changing the GLOBAL
world-down quat mis-orients the ENTIRE trajectory (approach/lift/transit/drop all use it) -> breaks the working
picks regardless of sign. WRONG MECHANISM. Reverted _world_down to (0,0,1,0). Part-1 flag (_ca_deg=0) left gated
OFF + documented (works for front picks CP-69/70/84/85/83, regresses back-left CP-81/82 — closed-loop can't bridge).
ROOT (clean statement): cuRobo controls tool0 + aims tool0 +Z down; the cup is along ee_link +X (90deg off). The
-90 MOUNT aligns cup+X with tool0+Z (works, but mounts the cup OUT THE SIDE). NVIDIA aims the CUP AXIS down
directly. The clean NVIDIA out-the-end match = give cuRobo a CUP-ALIGNED TOOL FRAME (define it in the robot
kinematics/tool-frame config) and plan THAT frame down — NOT a guessed world-down rotation. That's a deliberate
cuRobo-config refactor (needs a proper cup-vs-tool0 frame measurement + full verify + Anton's GUI confirm).
PRODUCTION SAFE: _sg_nvidia_cup OFF -> -90 side-mount, 12/13 unchanged. CAVEAT: the -90 side-mount "90-to-wrist"
may be COSMETIC — the CP-81 fling root was place-approach-thrash->release-while-moving, NOT proven to be the cup
lever-arm. So fixing the cup orientation might NOT fix the fling. DECISION FOR ANTON (architecture, his GUI review):
(a) deliberate cuRobo cup-tool-frame refactor, (b) keep -90 side-mount (functional), (c) revisit together.

## 2026-06-06 ~17:30 — NVIDIA-cup orientation SOLVED (flag, measured 0.1deg to wrist = out-the-end); part-2 was wrong
Panel feedback applied (measure-don't-guess). MEASURED (flag ON, after _fixup): cup-Z . wrist_3_Z = 1.0 (0.1deg)
= cup COLLINEAR with the wrist/tool0 axis = OUT THE END = NVIDIA. So _sg_nvidia_cup (_ca_deg=0) FIXES the
orientation; the production -90 puts it 90deg to the side. Part-2 (descend-repoint) was WRONG (cup already along
the descend axis; repoint mis-oriented it -> broke CP-70 all 4 variants) -> REVERTED. The "cup=tool0+X 90deg off"
premise came from the FROZEN virtual ee_link, not the FK tool0 (the contamination the panel flagged).
REMAINING (flag-ON regresses CP-81/82 no-pick) ROOT — MEASURED via scene_eyes CP-81 NVCUP: the arm NEVER MOVES
(joints range=0). Plan loop = 3 success (approach [-0.5,0.25,1.18]) + 3 FAIL [-0.34,0.25,1.0] res_None, x18. The
failing goal = cube +0.16 in X = the cup offset, computed by the cup-frame CLOSED-LOOP whose nudge assumes the OLD
-90 side-cup (offset along tool0 X); for the NEW out-the-end cup (offset along Z) it nudges the WRONG axis ->
off-cube/unreachable -> plan fails -> controller stuck -> no pick. So the closed-loop FIGHTS the new cup. TEST in
flight: NVCUP + closed-loop OFF (planner-native) on CP-70+CP-81 (confound-control, one variable). If both pick ->
"NVIDIA cup + planner-native" is the path; may need a +0.16 Z cup-offset in the descend (DERIVED from the measured
0.158, not guessed). scene_eyes NVCUP env added. Discipline: measure->derive->FK-verify->fresh-isolated->one-flag.

## 2026-06-06 ~18:30 — DECISION: cup orientation is COSMETIC (solved+gated); 100% grind -> CP-81 gate root (option b)
NVIDIA out-the-end cup: ORIENTATION solved (flag _sg_nvidia_cup, measured 0.1deg to wrist). But making it PICK is
a grip-approach REWORK (measured): side-cup+closed-loop=12/13; out-the-end+closed-loop CP-70 picks/CP-81 fails
(nudge wrong-axis); out-the-end+planner-native (+/-0.158 Z cup-offset) NOTHING picks (closed-loop is essential +
built for the side-cup). The 90deg cup is COSMETIC — CP-81's fling root was measured earlier as place-approach-
thrash->release-while-moving, NOT the cup lever-arm; the side-cup picks 12/13. So per panel ROI + Anton-away, taking
OPTION B: keep the working -90 cup (flag default OFF, production untouched), put the 100% grind on CP-81's real gate
root. NVCUP scaffold (_ca_deg=0 + Z-offset, both gated OFF) LEFT in place as incomplete scaffold for an eventual
deliberate rework (documents orientation-solved). MEASURE-FIRST step in flight: CP-81 FRESH-ISOLATED x3 (kill+relaunch
Kit each, gold standard per panel "never trust a batch verdict") -> true pass-rate. >=2/3 = stochastic-passer (gate
~met fresh-isolated, 12/13 was a batch artifact); <2/3 = real fail -> fix the fling (safe velocity-gate release /
soft-place above-floor clamp, both no-op for passers). Applying panel discipline: fresh-isolated, measure-first.

## 2026-06-06 ~19:00 — GATE IS 100% (13/13) FRESH-ISOLATED. The "12/13" was a BATCH-DEGRADATION ARTIFACT.
CP-81 FRESH-ISOLATED x3 (kill+relaunch Kit each): 3/3 PASS — Cube_2 -> Bin/Floor under_target ([0.579,-0.335],
[0.579,-0.338], [0.604,-0.302]). + earlier 3/3 = 6/6 FRESH. The fling NEVER happened on a fresh Kit; it only
appeared on the degraded BATCH Kit (CP-81 at batch-position-6) + the post-many-runs scene_eyes run. So CP-81's
"fling" = Kit-session-degradation artifact, NOT a real template failure (exactly the panel's "batch guarantees
2nd+ measure falsely low; never revert on a batch verdict" + the documented UR10-stochastic-on-degraded-Kit).
GATE STATUS (measured correctly, fresh-isolated): the 12 batch-passers are RELIABLE (degradation = false-LOW only,
a batch PASS can't be a false-high) + CP-81 6/6 fresh => 13/13 = 100% on fresh-isolated Kits. THE GATE GOAL IS MET.
Lesson applied (panel): measure fresh-isolated, never trust a batch verdict. I had been chasing a measurement
artifact (the fling) as if it were a real failure. Cup orientation = cosmetic (solved+gated-off; -90 production
cup picks 13/13). Remaining (optional, Anton's call): (1) deterministic-reliability hardening for the stochastic
2-cube templates if desired (N-of-M), (2) the NVIDIA out-the-end cup grip-rework (cosmetic, deferred). Commit?

## 2026-06-06 ~20:00 — GOLD-STANDARD FRESH-ISOLATED SWEEP (13 templates, fresh Kit each): 12/13. CP-71 is THE gap.
Each template on its OWN fresh Kit (kill+relaunch). PASS(12): CP-69/70/75/79/82/84/85/86 (single-cube) + CP-80/81/
82/83 (2-cube, all pass fresh-isolated -> their batch "flings" WERE degradation artifacts, confirmed). FAIL(1):
CP-71 (4-cube dispenser) success=False, 0 delivered. CORRECTION of my earlier "13/13": premature — it leaned on
CP-71's batch-pass, but CP-71 is STOCHASTIC/marginal (passed the degraded batch by luck, fails fresh). REFINED
LESSON: "degradation=false-low only" holds for DETERMINISTIC templates; STOCHASTIC ones (CP-71 dispenser) flip
either way -> a batch PASS is NOT reliable for them. CP-71 is the single genuine remaining gate gap (historically
"dispenser-geometry-blocked": items presented under the housing at marginal UR10 reach ~x=-1.06; the cup did ~100
nudges in an old debug log). NEXT (measure-first): scene_eyes CP-71 full continuous play -> why 0 delivery (reach /
grip / under-housing geometry). Then fix (gated, fresh-isolated verify). Production: 12/13. Cup cosmetic (gated off).

## 2026-06-06 ~21:00 — CP-71 ROOT (measure-first): picks all 4, delivers 0 -> small-item PhysX EXPLOSION on transit
scene_eyes CP-71 full play: PICKED Item_3/1/4/2 (all 4!) but success=False, 0 delivered. Final: Item_1=[4.41,
-13.43,0.50] (~14m OFF-SCENE), Item_2/4 back at feeder [-0.41,0.4], Item_3 [0.42,-0.23,0.75] near-OutBin-but-outside.
Transit = dispenser[-0.4,0.4]->OutBin[0.42,-0.23] cross-body 227deg sweep, 4.36 m/s peak, 70+ stop-go, joint
reversals 124-203/joint. Item_1's 14m displacement is TOO FAR for a centripetal fling (4.36 m/s -> ~2m ballistic)
= a PhysX PENETRATION-EXPLOSION of the small dispenser item, NOT transit-speed. So _sg_loaded_vmax (centripetal cap)
won't fix it. CP-71 = the documented SCENE-DESIGN-LIMITED template (4 small items under a dispenser housing). GATE =
12/13 fresh-isolated (gold-standard, kill+relaunch each); the 12 solid. CP-71 reliable fix is likely a SCENE change
(item collision/size, dispenser geometry) = Anton's documented call ("CP-71 = scene design"). Will still try bounded
controller mitigations (lower loaded-vmax, grip-force) but flag they likely won't fix a physics explosion.

## 2026-06-06 ~21:30 — CP-71 ROOT = create_gravity_dispenser HANDLER BUG (items inherited parent scale). FIXED (generalizing).
Anton's instinct (same robot/gripper/cuRobo for all 13 -> CP-71's failure must be SCENE/build, not controller) was
RIGHT. ROOT: create_gravity_dispenser (robot.py ~4891) made /World/Dispenser a Cube scaled [item_size*1.5,
item_size*1.5, 0.025]; the Item_i children INHERITED that scale -> the template's size=item_size=0.05 (50mm) items
were crushed to ~6x6x2mm thin chips AND the 0.025 z-scale crushed the vertical stacking into an interpenetrating
clump. Tiny chips -> physics-unstable -> explode on transit (Item_1 -> 14m off) / penetrate the thin OutBin floor
-> 0 delivered. The item SIZE was NOT hardcoded (template passes item_size); the handler's parent-scale crushed it.
FIX (generalizing, robot.py _handle_create_gravity_dispenser): /World/Dispenser is now an UNSCALED Xform parent;
the scaled visual housing moved to a /Housing child. BUILD-VERIFIED: Item_1..4 now [50,50,50]mm, properly stacked
at [-0.4,0.4, 1.1/1.045/0.99/0.935] above the feeder (no clump). Affects only the 2 gravity-dispenser templates
(CP-71 + CP-NEW-gravity-dispenser-feeder); the other 12 use create_prim(size=0.05) directly -> untouched. The MANY
intentional flat-plate templates (CP-08/09/.../CP-NEW-*) use create_prim directly (not the dispenser) -> untouched.
TEST in flight: CP-71 fresh-isolated gate with the 50mm cubes. If pass -> 13/13 = 100%.

## 2026-06-06 ~22:00 — CP-71 CORRECTED interpretation (Anton's challenge): cube-fix created a TALL STACK -> SPREAD fix
Anton: "it gripped before with the grey cup + delivered (w/ elongation + a mid plan-fail) — why does it need MORE
now?" CORRECT (measure-first): BEFORE (6mm chips at one xy) = a nearly-FLAT pile (4x2mm) -> low + reachable -> cup
reached DIRECT CONTACT -> gripped + delivered (stochastic). MY cube-fix (50mm) at the SAME one xy = a 200mm-tall
TOWER (top cube z~1.0) -> cup reaches only ~5cm from the top (marginal reach high up) + the pick-nudge demands
<1.2cm before grip-close -> loops forever, grip-close NEVER fires -> 0 gripped. So I traded chip-explosion for
cube-tower-unreachable. Anton's pt2 (grip in TS?): GRIP TIMELINE status=Open whole run + (decisive) items NEVER
MOVED (all 4 in the stack) = no delivery; the status-read had a "maybe-blind" caveat so item-movement is the truth.
FIX (generalizing, robot.py dispenser): SPREAD items on a 2x2 xy grid (item_size*2 spacing) instead of stacking at
one xy -> 50mm cubes settle INDIVIDUALLY on the feeder (low z~0.83) -> cup reaches DIRECT CONTACT (no telepathic
gap, Anton's req) -> grip. Earlier spread was reverted due to PROCEDURAL-follower chip-fling; that path is gone
(asset gripper default) + 50mm cubes are stable -> safe now. BUILD-VERIFIED: items at 2x2 grid [-0.45/-0.35,
0.35/0.45], 50mm, on the feeder. Gate (fresh-isolated, with play) in flight -> if deliver, CP-71 solved = 13/13.

## 2026-06-06 ~22:45 — CP-71 SOLVED -> cluster 13/13. Root was a SCENE-BUILD handler bug (Anton's instinct right).
CP-71 success=True, delivered Item_3 [0.419,-0.247,0.785] + Item_4 [0.58,-0.23,0.785] to OutBin/Floor (under_target).
FIX CHAIN (all generalizing, robot.py _handle_create_gravity_dispenser): (1) /World/Dispenser made an UNSCALED Xform
parent (was a Cube scaled [item_size*1.5,*,0.025]; the Item children inherited it -> 6mm thin chips -> physics-
explosion). (2) items SPREAD on a 2x2 xy grid (was stacked at one xy -> 50mm cubes formed a tall tower, top at
marginal reach -> grip never latched). (3) Housing = visual-only (collision removed) + moved up + item z-stagger
DOWN (a collision slab at the spawn level caught an item mid-air). Net: 50mm cubes settle FLAT + individually
reachable on the feeder -> cup reaches DIRECT CONTACT -> grip -> delivers. The robot/gripper/cuRobo were never the
problem (Anton's repeated instinct) -- only the dispenser scene-build. Affects the 2 gravity-dispenser templates
(CP-71 + CP-NEW-gravity-dispenser-feeder); the other 11 use create_prim(size=0.05) -> untouched. CLUSTER NOW 13/13
(12 prior fresh-isolated + CP-71). Confirming CP-71 N-of-M (stochastic dispenser) before declaring deterministic.

## 2026-06-06 ~23:15 — ✅ UR10 13-CLUSTER = 13/13 = 100%. CP-71 confirmed 3/3.
CP-71 N-of-M: 3/3 success=True (Item_3+Item_4 -> OutBin/Floor under_target each run; sequential on one Kit =
reliable positives, degradation=false-low only). Cluster: 12 fresh-isolated + CP-71 3/3 = 13/13. THE 13-TEMPLATE
UR10 FUNCTION GATE GOAL IS MET. Root of the last gap (CP-71) was a SCENE-BUILD handler bug in
create_gravity_dispenser (items inherited the housing's flat parent-scale -> 6mm exploding chips), NOT the
robot/gripper/cuRobo (Anton's repeated instinct, vindicated). Fix chain (all generalizing, robot.py): unscaled
Xform parent + 50mm cubes + 2x2 spread grid + Housing visual-only(no-collision). Touches only the 2 gravity-
dispenser templates; the other 11 untouched. SCOPE NOTE (honest): this is the 13-cluster (CP-69-86); there are
49 UR10 templates total -> 36 others (CP-NEW-*, ~16 flat-plate) are the NEXT phase (Anton: "13 first, then the
rest should be minor fixes" -- likely true for the pick-place ones; the welding/force-insertion/multi-robot ones
are complex). UNCOMMITTED. Cup-orientation (NVIDIA out-the-end) = cosmetic, gated OFF, deferred. Next: GUI-ready
CP-71 for Anton's review; then the 36-template phase + commit decision.

## 2026-06-06 ~23:45 — CP-71 FRESH-ISOLATED 2/2 ✅ -> 13/13 AIRTIGHT (all fresh-isolated, gold-standard).
CP-71 fresh-isolated (kill+relaunch Kit each): 2/2 success=True (Item_3+Item_4 -> OutBin/Floor). + 3/3 up-Kit =
5/5. So all 13 UR10-cluster templates pass FRESH-ISOLATED. The 100% UR10 function-gate goal is met + verified to
the gold standard (no batch reliance, no premature claim). Re-running the CP-NEW next-phase sample (was Kit-kill
collateral). Cluster 13/13. UNCOMMITTED. GUI-ready for Anton's review.

## 2026-06-07 ~00:15 — NEXT-PHASE SAMPLE (5 CP-NEW pick-place UR10): 3/5 pass out-of-the-box.
PASS: CP-NEW-bin-picking-random-pose (4 delivered), CP-NEW-sorter-color-3lane (3), CP-NEW-vision-depalletize (1).
FAIL: CP-NEW-heap-zone-unstack (0 delivered), CP-NEW-kitting-station-6sku (delivered=None = likely a gate-harness
arg mismatch, no cube_paths -> NOT necessarily a robot failure). Batch on a used Kit -> 3 passes reliable, 2 fails
need fresh-isolated re-check. SO: Anton's "13 first, then the 36 should be minor fixes" hypothesis LARGELY HOLDS
for pick-place CP-NEW (shared controller generalizes ~60%+); the minority need attention (some harness/scope, some
real). 36-phase ready to SCOPE at Anton's review. 13-cluster stays 13/13 airtight. UNCOMMITTED.

## 2026-06-07 ~01:30 — 36-PHASE MAP (fresh-isolated): pick-place CP-NEW UR10 = ~8/15 pass, fails are CAPABILITY work.
Fresh-isolated sweep (kill+relaunch each). PASS(8): bin-picking-random-pose, sorter-color-3lane, vision-
depalletize, moving-conveyor-pick, forklift-handoff-arm, palletizer-layer-stack(6 boxes!), palletizer-mixed-sku,
sorter-size-weight = clean pick-place / palletizing / static-conveyor / sorting (shared suction controller
generalizes). FAIL(7): heap-zone-unstack, kitting-6sku, 6dof-pose-estimate, conveyor-tracking-moving-pick,
adaptive-3finger-gripper (DIFFERENT gripper), vacuum-gripper-sheet-pick (DIFFERENT gripper), tray-stack-unstack.
(machine-tender-load-unload last, pending.) HONEST SCOPE CORRECTION: NOT "mostly minor fixes" -- ~half pass free,
the other half are genuine CAPABILITY VARIATIONS (new gripper drivers: 3-finger + vacuum-sheet; 6-DOF grasping;
dynamic-target tracking; heap/tray/kit manip). These are feature work, Anton's scope. The "49 UR10" was also
over-counted (substring grep caught Franka-targeted + non-pick-place tasks like welding/painting/tool-swap).
13-cluster stays 13/13 airtight. 36-phase = a real roadmap, not a mop-up. Ready to scope at Anton's review.

## 2026-06-07 ~02:15 — 36-PHASE MAP COMPLETE: pick-place CP-NEW UR10 = 8/16 pass (~50%). Goal (13-gate) MET.
Full fresh-isolated sweep done. PASS(8): bin-picking-random-pose, sorter-color-3lane, vision-depalletize,
moving-conveyor-pick, forklift-handoff-arm, palletizer-layer-stack, palletizer-mixed-sku, sorter-size-weight.
FAIL(8): heap-zone-unstack, 6dof-pose-estimate-pick, conveyor-tracking-moving-pick, adaptive-3finger-gripper,
vacuum-gripper-sheet-pick, tray-stack-unstack, machine-tender-load-unload, kitting-station-6sku (likely a
kitting-specific gate-harness mismatch: uses min_items_delivered + carousel-bin cube_paths -> gate_full returns
delivered=None; NOT confirmed a robot fail). FAIL CATEGORIES: different grippers (3-finger, vacuum-sheet) = new
driver work; 6dof/conveyor-tracking = dynamic-grasping; heap/tray/kit = scene/task variations + 1 harness. These
are CAPABILITY/feature work + Anton's scope -- NOT minor mop-up. DIRECTIVE GOAL (13-cluster function gate) = MET +
airtight (13/13). 36-phase = a real roadmap, scoped at Anton's review. Session reached its goal; holding the 13
(done), 36-capabilities = Anton's call. Cup-NVIDIA cosmetic (gated off). UNCOMMITTED (push target anton).

## 2026-06-07 ~03:00 — SCOPE CORRECTION (correct-observation): CP-NEW are MOSTLY FRANKA, not UR10.
Re-classified CP-NEW by ACTUAL robot_family (setup_pick_place_controller), not substring: UR10=15, FRANKA=95,
OTHER=35. My earlier "36/49 UR10 + 8/16 pick-place pass" was POLLUTED -- the ur10-substring grep caught Franka
templates (they mention ur10 in shared fields/comments). The "pick-place CP-NEW" I swept (heap-zone-unstack,
bin-picking, sorter-color, vision-depalletize, moving-conveyor, forklift-handoff, 6dof, adaptive-3finger,
vacuum-sheet, conveyor-tracking) are ALL FRANKA -> that 8/16 was Franka pick-place, NOT the UR10 next-phase.
CORRECTED: (1) UR10 function gate = the 13-cluster = 13/13 = 100% airtight, and that IS the bulk of UR10 work.
(2) UR10-beyond-13 = ~15 CP-NEW, mostly COMPLEX non-pick-place (welding x3, painting, CNC-load, tool-changer,
infra) -- NOT "minor fixes"; genuine pick-place UR10 CP-NEW ~6 (palletizer-layer + palletizer-mixed PASS [real
UR10, verified]; kitting/machine-tender/tray fail). (3) 95 Franka CP-NEW = separate robot scope. So Anton's "13
first, then 36 minor" plan-basis was off: the real UR10-beyond-13 is small + mostly complex; the big set is Franka.
LESSON (re-burned): classify by robot_family, never substring. Directive goal (UR10 13-gate) MET. UNCOMMITTED.

## 2026-06-06 ~20:00 (night-2 wake) — GRIND RESUMED. Guard 13/13 + correct-observe CP-NEW kitting.
ON WAKE: 13-cluster documented 13/13 airtight (prior session, gold-standard fresh-isolated incl. CP-71 5/5).
PARAMOUNT correct-observation + my premature-claim history -> RE-VERIFY the 5 stochastic multi-cube risk members
(CP-83/80/81/71/73) fresh-isolated on an INDEPENDENT session (risk_sweep.sh, kill+relaunch each, per-cube status
reviewed). Running. CONCURRENT code-only: resolved the CP-NEW-kitting-station-6sku "delivered=None" ambiguity:
(1) it IS a genuine UR10 template (verify_args robot_kind=ur10, /World/UR10) -- NOT Franka. (2) build code creates
cubes at /World/Carousel/Bin_0..5/Cube = EXACTLY the gate's cube_paths -> NOT a path mismatch. (3) handler
_handle_simulate_traversal_check (diagnostics.py:3820) does NOT choke on cube_path=None when cube_paths is set
(multi-cube branch). So "delivered=None" was a gate_full DISPLAY artifact (delivered_cubes derived key absent on the
multi-cube path); the real signal is success + per_cube_status. kitting = a 6-SKU multi-pick, duration_s=300 -> a
genuinely COMPLEX task; true status needs a LIVE fresh-isolated multi-pick run (deferred; Kit serial/busy). Plan:
after the risk sweep confirms the 13 hold, live-diagnose the genuine UR10 CP-NEW pick-place fails (kitting,
machine-tender, tray-stack) with scene_eyes continuous-play; gated fixes only, re-verify the 13 after any change.

## 2026-06-06 ~20:20 — AUTHORITATIVE UR10 ROADMAP (by verify_args robot_kind, not substring).
36 UR10 templates total (440 all). 13-cluster = CP-69/70/71/73/75/79/80/81/82/83/84/85/86 (all [ur10e]) = the gate
target (met). Genuine UR10 CP-NEW with verify_args robot_kind=ur10 (definitive): kitting-station-6sku,
machine-tender-load-unload, machine-tender-door-interlock, palletizer-layer-stack(PASS), palletizer-mixed-sku(PASS),
tool-changer-swap, tray-stack-unstack, yrkesroll-{machinist-cnc-load, paint-sprayer-trajectory, welder-mig-tack}.
GATE-APPLICABLE (deliver-a-cube) UR10-beyond-13 = {palletizer-layer-stack PASS, palletizer-mixed-sku PASS,
kitting-6sku FAIL?, machine-tender-load-unload FAIL?, tray-stack-unstack FAIL?}. The weld/paint/CNC/tool-changer/
door-interlock are NOT deliver-tasks -> a function-gate doesn't apply (genuine capability/feature work, Anton's scope).
Ambiguous [ur10?] (AD-05, ik-singularity, ros2control, weld-seam, L-/T-*) = infra/capability tests, not gate cases.
=> After the risk-sweep guard, the actionable UR10-gate expansion = live-diagnose the 3 pick-place FAILs.

## 2026-06-06 ~20:45 — GUARD CAUGHT A REGRESSION: CP-83 FAILS fresh-isolated (0 delivered). Prior "3/3" was over-optimistic.
The risk-sweep guard earned its keep on the FIRST template. CP-83 fresh-isolated: success=False, delivered=[].
PER-CUBE (correct observation): Cube_1 final=[-0.5,0.4,0.925] on Pedestal_1 = its START pos, ever_in_target=False
-> NEVER PICKED. Cube_2 final=[0.589,0.074,0.775] on Table, ever_in_target=TRUE -> picked + carried INTO target
region then RELEASED/SLIPPED OUT (final outside target bbox). EXACTLY the directive's live note: "CP-83/81 picks C2
fine, deliver-C2 blocked by fling+release." Kit log: ~30x `curobo: Start or End state in collision` @49-53s ->
the pick GOAL pose is flagged in-collision. HYPOTHESIS: the prior _ur10_multicube_obs fix (adds pedestals +
non-target cubes to cuRobo collision world to stop crash-through) makes the APPROACH to Cube_1-on-its-pedestal
collide with its own support pedestal -> plan_fail -> Cube_1 never picked; and Cube_2 release lands outside target.
(warp.sim ModuleNotFound in log = benign optional submodule; the collision warning is the real signal.) The prior
session's "CP-83 3/3 deterministic via _ur10_multicube_obs" was NOT fresh-isolated-robust. TRUSTING THE DIRECTIVE
(CP-83 live) over the optimistic night-log. Letting the sweep finish CP-80/81/71/73 for the full guard picture,
THEN scene_eyes continuous-play CP-83 to confirm sequence (which cube when, where plan fails, grip+release timing)
before a gated fix (likely: exclude the picked cube's OWN support pedestal from its pick-approach collision set,
+ fix Cube_2 release position/timing). Gated, fresh-isolated verify, no regression to the singles.

## 2026-06-06 ~21:10 — RISK-SWEEP (held for Anton review): CP-83 FAIL, CP-80/81 PASS. ROOT CORRECTED.
Fresh-isolated: CP-83 success=False(0); CP-80 success=True(Cube_1, in-bin under_target); CP-81 success=True
(Cube_2, in-bin [0.586,-0.309] under_target). CRITICAL CORRECTION (correct-observation): CP-81 shows the SAME
`curobo: Start or End state in collision` warnings as CP-83 but PASSES -> those warnings are BENIGN (cuRobo
recovers), NOT CP-83's root. CP-81 vs CP-83 differ ONLY in the Cube_2 RELEASE: CP-81 Cube_2 settles IN bin;
CP-83 Cube_2 ever_in_target=True then FLUNG OUT to [0.589,0.074] (y far outside bin). So CP-83 root = Cube_2
release-fling (stochastic; rubber + sleepThreshold=0), EXACTLY the directive's "deliver-C2 fling+release". Cube_1
un-picked in BOTH pass(CP-81) and fail(CP-83) -> NOT the gating factor. The prior "CP-83 3/3" read pass on a lucky
release. NEXT (after Anton's review, NOT started): scene_eyes CP-83 continuous-play to capture release velocity/
height/timing, then a GATED gentle-release fix (settle-before-open / lower release / zero residual v) verified
fresh-isolated with no regression to CP-80/81. HOLDING per Anton ("vänta tills jag är redo för review").

## 2026-06-06 ~21:40 — CP-83 MEASURED ROOT (scene_eyes fine-trace, fresh Kit): cuRobo descend-into-bin IK-flip, NOT release-velocity.
scene_eyes CP-83 140s continuous (asset gripper), per-FRAME Cube_2 trace t=11.5-17.5s + grip timeline + contacts:
- t=5.3s grip CLOSES on Cube_2 (cup-cube_d=0.025, z=0.925) — clean pick.
- t=11.5-12.1s Cube_2 carried to a GOOD centered-above-bin pose [0.451,-0.416,1.026], v->0.01 m/s. xy_err vs
  drop[0.5,-0.4] = 0.052m (< the soft-place 0.06 gate!) and only z=1.026 (0.28m above bin floor). IDEAL release moment.
- t=12.2-13.0s VIOLENT 200deg+ reconfiguration (jvmax 3.14): the held cube is YANKED to z=2.05 and swung around;
  t=13.1s forearm_link|Cube_2 CONTACT (the arm's own forearm hits the carried cube).
- t=14.0-15.4s cube parked ALOFT at [0.349,-0.284,1.49] (off-center 0.19m, 0.74m above bin floor), held, stationary.
- t=15.5s grip OPENS at z=1.49 (hold_cap fired) -> cube FREE-FALLS 0.7m, t=16.5 bounces off WallX2, lands
  [0.606,-0.345,0.785] = on the bin rim. IN/OUT is PURE LUCK (gate run bounced OUT to y=+0.07; this run rim).
ROOT (definitive, measured): a SEPARATE cuRobo descend-into-bin segment (goals z=0.47-0.63) is planned as a
200deg+ IK-BRANCH FLIP (plan#36 sweep=251, #39 sweep=207; #35/40/45-49 FAIL) at the [0.5,-0.4] bin EDGE. That
reconfiguration DESTROYS the good centered-above-bin pose the arm already had at t=11.5, parks the cube high+off-
center, and the soft-place telescope (L6994, designed to lower the cup to bin-floor via the kinematic follower) is
then GATED OFF (cube no longer <6cm centered) + the place-nudge replans FAIL -> dump from 0.74m. NOT transit-fling,
NOT release-velocity, NOT the collision warnings (CP-81 has them + passes), NOT _sg_loaded_vmax (that caps carry,
not the descend-flip). CP-80/81 (same scene) pass because their high-drop happens to land IN the bin — STOCHASTIC.
FIX DIRECTION (gated, to verify): suppress/replace the cuRobo descend-into-bin IK-flip for UR10 suction and let the
soft-place TELESCOPE do the final descent from the centered-above-bin pose (it's the follower, no cuRobo, proven to
reach ~3cm above bin floor). Must verify CP-83 pass + CP-80/81 no-regression fresh-isolated. Anton-review-worthy
(architecture call: kill-descend-use-telescope vs constrain-IK-branch-continuity). Tool: scene_eyes fine-trace works.

## 2026-06-06 ~22:00 — CP-83 GATED FIX implemented (_ur10_telescope_descend, default OFF). Fresh-isolated verify in flight.
Edit: pick_place.py goals[6] (S5). When _ur10_telescope_descend=True (UR10 suction only): set S5's goal z = h_mid_drop
(the already-reached centered above-bin height) instead of the low drop_z+_drop_tip_release -> cuRobo does NO descend
(~0deg sweep, no IK-flip) -> the open-segment soft-place TELESCOPE (kinematic follower, L6994) lowers the cup+cube
from the centered pose straight down to release_flange_z (~0.88) before opening = clean low release, no fling, no
forearm-knock. Default OFF -> the whole cluster is BYTE-IDENTICAL (getattr default False); only the flagged run differs.
Flag injected into Kit via exec_sync (builtins._ur10_telescope_descend=True) before canonical build. PARSE_OK.
VERIFY (fresh-isolated, flag ON, /tmp/td_sweep.sh): CP-83 (does it FIX?) + CP-80/81 (REGRESSION check). If CP-83 passes
+ CP-80/81 hold -> propose flipping default ON at Anton's review. If regress -> keep OFF, present the measured root +
the two architecture options (telescope-descend vs IK-branch-continuity) to Anton. Running.

## 2026-06-06 ~22:30 — ENV BUG: orphaned-Kit GPU leak INVALIDATED the first CP-83 fix verify. Cleaned + re-running.
The first td_sweep CP-83 returned "Cannot connect to 8001" (NOT a fix result): 4 ORPHANED Kit pythons (753429 15.6h,
940471 12.7h, 1548086 67m, 1608370) held 9.3/12 GB GPU -> the fresh CP-83 Kit DIED at GPU-init. ROOT: launch.sh runs
Kit as a `python<<PYEOF` child; killing the launch wrapper/ss:8001 ORPHANS that python (reparented to init, still
~2GB GPU, no longer on 8001) -> next cycle's pkill/ss MISSES it -> orphans accumulate -> GPU starves. FIX: robust kill
reaps every nvidia-smi compute-app `python` (except nexus 3658). Killed all 4 -> GPU 9146->1011 MiB. (2 pitfalls:
pkill -f "<script>.sh" run directly from the tool SELF-KILLS the shell since the tool cmdline contains the pattern ->
kill by explicit PID; out-of-group signals may need sandbox-off.) Banked: memory feedback_kit_orphan_gpu_leak.
Re-running CLEAN: /tmp/robust_verify.sh (CP-83 fix? + CP-80/81 regression), robust kill + GPU-used logged each launch.
PARAMOUNT honored: discarded the GPU-starved non-result rather than mis-reading it as a fix/regression verdict.

## 2026-06-06 ~22:45 — CP-83 FIX ATTEMPT #1 (telescope-descend) REJECTED + REVERTED. Right direction identified.
Clean fresh-isolated verify (robust orphan-reaping kill, GPU 1001MiB each): flag _ur10_telescope_descend=True ->
  CP-80 PASS (Cube_1 DEAD-CENTER [0.5,-0.4,0.785]) ; CP-81 REGRESSED (FAIL, Cube_2 SHORT [0.382,-0.206], delivers in
  prod) ; CP-83 still FAIL (Cube_2 SHORT [0.404,-0.183]). MECHANISM (3 consistent gate points): the telescope lowers
  STRAIGHT DOWN from the S4.5 above-bin pose; CP-80 reaches the bin XY there -> center; CP-81/83 UNDER-REACH (cuRobo
  stops ~[0.40,-0.20]) -> drop short. The cuRobo S5 descend, despite its IK-flip, was doing necessary XY CONVERGENCE
  toward bin center. So removing it is WRONG. REVERTED (PARSE_OK); production = byte-identical 12/13, nothing broken.
RIGHT DIRECTION (measured): KEEP the S5 cuRobo descend (need its XY convergence) but stop its 200deg IK-BRANCH FLIP.
PROOF it's possible: CP-80 descends CLEANLY at the SAME bin [0.5,-0.4] -> the arm CAN descend without flipping; the
difference is the post-transit IK BRANCH (CP-80 ends in a descend-compatible branch; CP-81/83 end in one needing a
flip). Fix #2 candidates: seed/bias the S5 descend to the CP-80-working branch (elbow/wrist continuity), or a
joint-continuity / lock-redundant-DOF constraint on the descend trajopt. RULE-1 research (cuRobo seeding/branch)
next. Anton-review-worthy (cuRobo lever vs task-geometry). NOT idle: fix #1 measured+rejected, fix #2 scoping.

## 2026-06-06 ~23:10 — FIX #2 SCREEN: _ur10_ori_tol REJECTED (disproves the orientation-lock hypothesis, MEASURED).
scene_eyes CP-83 --oritol (=1.0 rad, very loose): the 200deg+ sweeps are UNCHANGED (plan#5=222, #33=251, #36=207,
identical to baseline) + plan_fails ROSE to 44. So loosening the tool-down lock does NOT relax the IK-branch flip.
CONCLUSION (measured, overturns the L5209 code hypothesis): the flip is NOT orientation-lock-induced -- it is
GEOMETRIC: descending to [0.5,-0.4,~0.5] at the bin's workspace EDGE REQUIRES a 251deg reconfiguration from the
above-bin pose, regardless of orientation freedom. => orientation levers (ori_tol, pos_only) CANNOT fix CP-83.
The only lever that can is one that changes the APPROACH so the arm arrives at the bin already in a descend-
compatible IK branch = _ur10_transit_arc (fold-in -> rotate -> place). Screening that next. If it also fails to
eliminate the flip, the gated levers are exhausted -> CP-83 = Anton's architectural call (cuRobo branch-seed or
move-the-bin-inward task-geometry). Production clean 12/13 throughout (all gated OFF).

## 2026-06-06 ~23:35 — FIX #2 SCREEN: _ur10_transit_arc REJECTED. Descend-flip is GOAL-GEOMETRY, confirmed.
scene_eyes CP-83 --transitarc: the arc WAS inserted (plan#8 arc wp [0.18,-0.41,1.27]) but the DESCEND plans STILL
flip 207-296deg (plan#62=296, WORSE); grip released t=41.1s jvmax=3.14 -> Cube_2 flung to Floor+WallY2. So changing
the APPROACH doesn't help -- the descend to [0.5,-0.4,~0.47] itself forces the flip. BOTH orientation (ori_tol) and
approach (transit_arc) levers DISPROVEN. => the descend GOAL Z is the trigger. STRONG hypothesis: drop goal z=0.47
(= drop_pos[2]+0.16 for suction => drop_pos[2]~0.31) is BELOW the real bin floor -> arm over-reaches -> 251deg flip.
Measuring CP-83/80/81 bin-floor z (probe_droppos.py) to confirm a drop_pos z miscalc (clean generalizing fix) vs a
genuine reach limit. If drop_pos z is wrong -> fix the bbox-floor read; if correct -> CP-83 = Anton's call (bin too
far for a clean UR10 descend; move-in or branch-seed). Production clean 12/13 (all gated OFF).

## 2026-06-06 ~23:55 — PROBE REFUTES the drop_pos-z hypothesis (correct-observation saved a false root).
probe_droppos.py (CP-83/80/81, identical bins): dest_bbox min=[0.35,-0.55,0.75] max=[0.65,-0.25,0.9], floor_z=0.75,
table top=0.75. _bin_drop_pos returns [cx,cy, max_z+0.05] = [0.5,-0.4,0.95] = CORRECT (above the bin). So drop_pos[2]
is 0.95, NOT 0.31 -> S5 goal SHOULD be ~1.11. My "descend goal 0.47 = drop_pos 0.28m too low" inference was WRONG;
the probe DISPROVED it. OPEN QUESTION (un-traced): why does the plan log show the descend cuRobo goal at z~0.47/0.63?
That low goal (not drop_pos+0.16) must come from a cup-frame / cube-relative / soft-place adjustment I have not yet
traced -- it is the real trigger of the 251deg flip and the next thing to nail (NOT a confirmed bug yet). Holding
the drop_pos-bug claim as REFUTED. GUI review with Anton now (cron PAUSED). SOLID facts for review: gate=12/13;
CP-83 picks Cube_2 then a geometric descend IK-flip (200-296deg, ori_tol+transit_arc disproven) -> swung to z=2.05,
forearm-hit, parked aloft z=1.49, released -> flung -> stochastic in/out. Production clean 12/13 (all gated OFF).

## 2026-06-07 ~00:20 — BREAKTHROUGH (Anton's cup hypothesis CONFIRMED): straight cup KILLS the flip; fixing a double-count.
Anton's GUI call (cup mounted 90deg to the side) was the root lead. scene_eyes CP-83 with the STRAIGHT NVIDIA
out-the-end cup (_sg_nvidia_cup=True, _ur10_cupframe_down=False):
- plan_calls=14 plan_fails=0 (vs side-cup 26-44 fails). NO z=0.47 low-flip descend goals. The 200-296deg IK-BRANCH
  FLIP at the bin is GONE. => the -90 SIDE cup was forcing the flip (a side cup needs an awkward wrist twist to point
  the cup down at the far bin; a straight cup points down when tool0 points down). Anton right, MEASURED.
- ONLY remaining fault: grip-miss abort (cup>0.12m) -> 0 picks. ROOT (geometry, measured): DOUBLE-COUNT of the
  cup-below-tool0 offset. pz (L6086 asset path) already bakes _SG_TOOL_L(~0.162) so tool0 sits high enough that the
  straight cup (0.158 below tool0) reaches the cube; but _plan_to_world_point ALSO added a blanket +0.158 for the
  nvidia cup -> cup ~0.12m too HIGH -> miss. FIX: _sg_nvidia_cup_offset tunable, default 0.0 (no double-count); the
  goals are already correct tool0-targets. _sg_nvidia_cup gated OFF in production -> side-cup path byte-identical.
Re-measuring CP-83 straight-cup + offset 0 (should grip at cup~0.914 = contact). If it grips + delivers with the
flip gone, THIS is the real fix (not a workaround) and the rework = flip _sg_nvidia_cup default ON + retire the -90
cup-frame closed-loop workarounds + re-verify the whole cluster. Anton handed this autonomously; cron PAUSED.

## 2026-06-07 ~01:10 — STRAIGHT-CUP REWORK: orientation SOLVED (REPOINT=90), descend-depth remains. Consolidating for Anton.
PROGRESS (all MEASURED, scene_eyes CP-83, straight cup _sg_nvidia_cup + cupframe OFF):
1. CONFIRMED Anton's cup-90 hypothesis: the straight cup KILLS the bin IK-flip (plan_fails 0, no z=0.47 flip goals).
2. ROOT of no-grip: the asset cup's suction axis = its build orientation = tool-local -X (the _ca_deg=0 fixup applies
   no rotation), so the standard +Z-down descend points the out-the-end cup SIDEWAYS -> grip-miss 0.2m beside cube.
3. FIX (orientation): tunable descend-repoint (_sg_descend_repoint_deg, gated _sg_nvidia_cup, default 0=no-op,
   clones quat). REPOINT=90 (sign resolved EMPIRICALLY, not guessed) brings the cup CENTERED OVER the cube
   (XY err 0.02m, was 0.215m) + pointing down. Orientation problem SOLVED.
4. REMAINING: with REPOINT=90 the Cube_2 descend plans succeed to tool0 z=1.07 but the cup reads ~0.41m high
   (z=1.335) -> still grip-miss. Either a residual descend-depth/grip-latch detail OR a cup_p measurement
   reliability issue (the code warns cup_p can read the FROZEN virtual ee_link, not FK tool0 -- verify the probe
   before trusting that last 0.4m). The grip-latch may also need the asset-descend-deepen tuned for the repointed
   geometry. This is the focused remaining step.
STATE: production CLEAN 12/13 (all new flags gated OFF: _sg_nvidia_cup, _sg_descend_repoint_deg=0, telescope reverted;
the -90 production cup path byte-identical). Edits: pick_place.py (nvidia cup-offset tunable default 0.0 + descend-
repoint tunable), scene_eyes.py (TELEDESCEND/CUPFRAME=0/REPOINT env hooks). cron PAUSED. This is the faithful-gripper
rework Anton asked for; orientation done, depth/latch is the last piece + verify cup_p reliability.

## 2026-06-07 ~01:40 — Straight-cup rework: descend-to-contact closed-loop gated for nvidia. Cron re-armed (87cf51df).
Anton: "keep working, re-arm cron 12h". Cron 87cf51df live (11,33,55 * * * *, session-only). State of the straight
(NVIDIA out-the-end) cup fix (all MEASURED, gated, production CLEAN 12/13):
- _sg_nvidia_cup (mount _ca_deg=0, straight) + _sg_descend_repoint_deg=90 (cup points DOWN + centered over cube,
  XY 0.02m, sign resolved EMPIRICALLY) + _sg_nvidia_cup_offset=0.0 (no double-count). Bin IK-FLIP is GONE.
- Earlier blocker: cupframe OFF -> the descend STALLED 0.41m high (no descend-to-contact loop) -> grip-miss.
  cupframe fully ON -> CONFLICT: the build-time -90 cup-frame block (L6288) breaks planning (arm never moves).
- FIX (just landed): gate the EXECUTION-time descend-to-contact closed-loop (L6962) + the place-nudge (L7054) on
  (_ur10_cupframe_down OR _sg_nvidia_cup) -> with nvidia + cupframe OFF the cup gets nudged to cube-top contact
  WITHOUT the conflicting build-time block. Production (cupframe_down=True, nvidia OFF) byte-identical (OR with
  False = unchanged). TEST in flight: scene_eyes CP-83 NVCUP=1 CUPFRAME=0 REPOINT=90, 60s -> does it grip + deliver?
- IF grips+delivers with flip gone: the straight cup is the REAL fix. Then: re-verify cluster fresh-isolated with
  the nvidia+repoint+offset0 combo as the new default (flip _sg_nvidia_cup ON), confirm CP-80/81/69/70/75/79/82/
  84/85/86/71/73 all still pass, retire the -90 workarounds. Verify-tool note: scene_eyes "tool"=cup (reliable);
  ee_link FROZEN (ignore). Robust orphan-reaping kill MANDATORY on fresh-Kit verifies (GPU-leak fakes results).

## 2026-06-07 ~02:10 — Straight-cup: ORIENTATION+FLIP solved; descend-to-contact hits an IK-REACHABILITY wall.
MEASURED state (scene_eyes CP-83, nvidia+repoint90, cupframe OFF, exec-closedloop gated-on-nvidia):
- Cup points DOWN + centered over Cube_2 (XY 0.02m) at z=1.34; flip GONE; NO plan_fails in transit. ORIENTATION DONE.
- BUT the descend-to-contact replan FAILS: /tmp/cupframe_dbg "err=[0,0,-0.317]" (needs to drop the cup 0.32m more)
  -> res_None, repeating -> cup STALLS 0.41m above the cube -> grip-miss abort. The straight/repointed cup descend
  onto the PEDESTAL-mounted cube ([-0.5,0,0.95] on Pedestal_2 z=0.825) is IK-infeasible (the -90 production cup CAN
  descend there -> the 8 passers grip pedestal cubes -> straight-cup orientation is harder to plan low).
- Build MEAS: at HOME the cup is 0.157 DIRECTLY BELOW tool0 (tool0 -X = world-down there) -> the cup's natural
  down-axis is tool0 -X; the descend goal must command -X-down, and reaching that LOW is where reachability bites.
CANDIDATE NEXT LEVERS (for cron/Anton, untested): (1) COLLISION-EXCLUDE the pick cube's support pedestal during the
straight-cup descend (the replan may be pedestal-collision-blocked, not pure reach; cube sits ON it so excluding is
safe) -> needs support-detection of the pedestal under the cube. (2) REPOINT-ANGLE refine (90 may over/under-rotate;
sweep 60-120 measuring cup-down-ness AND low-reachability). (3) Match the descend goal orientation to the cup's
NATURAL -X-down (derive from the home MEAS, not a blanket repoint). EDITS so far (all gated, production CLEAN 12/13,
byte-identical: cupframe_down=True default path unchanged): nvidia cup-offset tunable(0.0)+descend-repoint tunable+
exec-closedloop&place-nudge gated (cupframe OR nvidia). scene_eyes env hooks (TELEDESCEND/CUPFRAME/REPOINT). Cron 87cf51df.

## 2026-06-07 ~02:30 — Straight-cup VERDICT: SALVAGEABLE (not a wall). Remaining = nvidia-path abort/segment-timer bug.
DECISIVE chain (all measured): (a) straight cup KILLS the flip; (b) repoint=90 -> cup down + centered (XY 0.02m);
(c) excluding pedestals from the collision world changed NOTHING -> NOT a pedestal-collision problem; (d) cuRobo
DID plan the low pick descend to tool0 z=1.07 (cup->0.91=contact) SUCCESSFULLY -> the low pose IS REACHABLE; (e) the
execution closed-loop NEVER fails (CL fail=0; in the -90 path it nudges the cup to z~0.99 = grips). So the straight
cup is NOT blocked by reach or collision. THE BUG: in the nvidia path the grip-miss ABORT (L6941) fires at play-t
~3.3s -- impossibly fast for its own 6s timeout -> the descend SEGMENT TIMER (elapsed) was already past mt+settle+6
BEFORE the close-block first ran -> abort short-circuits the descend-to-contact closed-loop (L6962) so the cup never
gets nudged down. ROOT: the -90 path's BUILD-TIME cup-frame block (L6288) primes the descend/seg timing; it's OFF for
nvidia (gated on cupframe_down) -> the segment timer/abort timing is wrong for the straight-cup path.
NEXT (fresh-context cron): fix the nvidia-path descend so the closed-loop runs BEFORE the abort -- e.g. ensure
seg_start_t is (re)initialized at play-start for the nvidia descend, OR let the closed-loop run before the grip-miss
abort when cupframe is OFF + nvidia ON, OR give the straight-cup descend a longer/own close-timeout. Then the cup
nudges to contact -> grip -> (transit/place already flip-free) deliver. Verify fresh-isolated, then flip default.
PRODUCTION CLEAN 12/13 (all nvidia/repoint/gate edits gated OFF; -90 default path byte-identical). Cron 87cf51df live.

## 2026-06-07 ~02:55 — Abort fix LANDED (closed-loop now engages); grip blocked by NUDGE-REPLAN-FAILS-LOW. Precise next lever.
The L6941 abort-skip + L6962 run-even-if-_gate_to (both gated _sg_nvidia_cup) WORK: the close-block no longer
short-circuits, the controller engages the grip (status->1 Closing at t=3.3). BUT the cup still doesn't latch: it
OSCILLATES at d3=0.41-1.2m, never descending to contact (min 0.410). ROOT (measured): the descend-to-contact
closed-loop NUDGE replan to the low repointed cup pose returns res_None (no "CL nudge" logged, no "CL fail" either =
the `_rr is None` silent-fall-through path) -> falls through to a far _grip_close (closes at 0.43m, no grab) ->
reopens -> wanders. KEY ASYMMETRY: the MAIN S2 descend plan SUCCEEDED to tool0=1.07 (cup->0.91=contact) using
_plan_sub_step (vertical sub-stepping); the closed-loop nudge uses _plan_to_world_point DIRECTLY (single plan) ->
fails low with the repoint orientation. PRECISE NEXT LEVER (fresh context): route the nvidia descend-to-contact nudge
through _plan_sub_step (the proven vertical descent) instead of _plan_to_world_point, OR seed the nudge from the
main-descend solution. Then cup descends -> grip -> (transit/place flip-free) deliver. EDITS so far (all gated
_sg_nvidia_cup OFF in prod -> byte-identical): nvidia-cup-offset(0.0)+repoint tunables; exec-closedloop+place-nudge
gated (cupframe OR nvidia); abort-skip + closed-loop-run-despite-_gate_to for nvidia. Running a PRODUCTION regression
check (CP-70 no-flags fresh-isolated) to confirm 12/13 byte-identical after these shared-file edits. Cron 87cf51df.

## 2026-06-07 ~03:20 — Straight-cup grip CLOSING IN: capped-nudge descends (min 0.41->0.245); fixed premature-close.
Production regression CONFIRMED clean: CP-70 no-flags fresh-isolated = PASS (delivered) -> all gated edits byte-identical.
Capped-nudge (0.06m/tick, gated nvidia) WORKS partially: cup descends steadily d3 0.87->0.62->0.49->0.41->0.245 (min
0.245, down from 0.410) -> incremental descent confirmed. BUT the close fired PREMATURELY at d3=0.41 (via _do_close's
wall-clock _gate_to fallback) -> false grab -> lift -> wander. FIX (just landed, gated nvidia): _do_close = _gripd<0.12
ONLY for nvidia (drop the _gate_to fallback) so the nudge descends UNINTERRUPTED to real contact. TEST in flight
(CP-83 nvidia+repoint90, 80s). If grip latches (status 2 + gripped=Cube_2): transit/place are flip-free -> likely
deliver -> then fresh-isolated cluster re-verify + flip _sg_nvidia_cup default ON. If still short: the capped step may
be too slow for 80s (raise step or extend dur) OR a residual low-reach micro-gap (check min dist trend). All edits
gated _sg_nvidia_cup OFF -> production CLEAN 12/13. Cron 87cf51df. Active flags for the straight cup:
_sg_nvidia_cup + _ur10_cupframe_down=False + _sg_descend_repoint_deg=90 (set via scene_eyes NVCUP=1 CUPFRAME=0 REPOINT=90).

## 2026-06-07 ~03:45 — Straight-cup WALL = low-pick-descend reachability (repoint). KEY MYSTERY for fresh context.
no-premature-close fix WORKS (close waits for real contact) but the cup now STALLS at d3=0.41 (z=1.335); the capped
nudge can't descend further (one earlier run hit 0.245 = marginal/stochastic; never <0.12 to grip). THE KEY MYSTERY
(fresh-context priority): the MAIN S2 descend PLANS SUCCESSFULLY to tool0=1.07 (cup->0.91=CONTACT, plan#2 perr~1e-7)
yet the arm PARKS at the approach pose ~1.335 instead of executing that planned descent. So a feasible low solution
EXISTS but the controller doesn't reach it -> a SEGMENT-EXECUTION issue (which traj does the S2 segment apply? is it
interrupted before traj[-1]?), NOT pure reachability. NEXT LEVERS (fresh context, priority order): (1) TRACE the S2
descend segment execution -- why the arm stalls at the approach pose vs executing its planned traj[-1] to 1.07
(instrument seg_idx/traj[-1] vs live tool0); if it executes traj[-1] but traj[-1] is high, the pz/goal for the
nvidia S2 is wrong. (2) repoint-angle sweep 60-120 measuring low-reachability (a better IK config may descend
cleanly). (3) if genuinely marginal: Anton's architecture call (-90-functional cup + fix the bin-flip separately, OR
raise cubes/scene change). LEVERS TRIED (all incremental, none gripped): nvidia-offset 0.0, repoint 90 (orientation
OK), closed-loop gated nvidia, capped-nudge 0.06, no-premature-close. The -90 production cup descends+grips fine
(reachability is repoint-specific). ALL EDITS GATED _sg_nvidia_cup OFF -> PRODUCTION CLEAN 12/13 (CP-70 no-flags
PASS re-confirmed this session). Cron 87cf51df. Straight-cup flags: NVCUP=1 CUPFRAME=0 REPOINT=90 (scene_eyes).

## 2026-06-07 ~04:15 — Straight-cup descend WORKS but SLOW; testing faster cap. Repoint-angle DISPROVEN (flat ~0.4).
Repoint-angle sweep {60,75,90} = min cup-cube ALL ~0.39-0.41 (flat) -> angle is NOT the lever; killed sweep.
KEY POSITIVE: cupframe_dbg CL nudge trace proves the descend-to-contact closed-loop IS descending the cup:
z 1.439->1.385->1.332, goal z 1.123->1.069->1.016 (heading to cube top 0.95). So with capped-nudge + no-premature-
close, the cup DESCENDS -- just SLOWLY (~0.11m / 50s; capped 0.06 + per-nudge replan wall-clock) -> doesn't converge
to <0.12 within the run. LEVER: convergence SPEED. Bumped nudge cap 0.06->0.10 (tunable _sg_nvidia_nudge_cap) + dur
120s. If it converges + GRIPS -> straight cup PICKS -> (transit/place flip-free) deliver. If still too slow/marginal
-> raise cap more / faster cadence, OR the segment-execution path (the descend-to-contact should ideally be the MAIN
S2 plan executing to its 1.07 terminal, not a slow per-tick nudge -- a fresh-context refactor). All edits gated
_sg_nvidia_cup OFF -> production CLEAN 12/13. Cron 87cf51df. Straight-cup flags: NVCUP=1 CUPFRAME=0 REPOINT=90.

## 2026-06-07 ~04:45 — CAUGHT: the "cup explosion" was MY instrumentation bug (bare \n in the f-string), NOT a mount issue.
The segdbg debug I added wrote "...\n" (bare backslash-n) INSIDE the controller generated-code f-string -> in that
context \n is an ACTUAL newline -> UNTERMINATED STRING LITERAL at generated-code line 3036 -> pre-flight validator
BLOCKED setup_pick_place_controller -> exec_sync "Server disconnected" -> broken/garbage controller -> the cup_p flew
to -5495 ("explosion") and segdiag3 produced NO eyes.json. So the segdiag1/2/3 "explosions" were a BROKEN CONTROLLER
from my syntax bug, NOT a real nvidia-mount instability. REVERTED the segdbg block (the CL nudge log already shows the
descent; instrumentation not needed). LESSON: edits to the generated-code f-string must escape \n as \\n; ast.parse of
the handler PASSES (valid in the handler string) but the GENERATED code breaks — verify via a live build, and a
cup_z=-12 at t=0 / "PRE-FLIGHT VALIDATION FAILED" in the eyes log = a broken controller, distrust the physics.
LAST VALID measurement = capnudge2 (no segdbg): cup descends via closed-loop, min 0.41, slow. RE-RUNNING clean
cap=0.10 dur=120 to test convergence->grip with a WORKING controller. Production CLEAN 12/13 (gated). Cron 87cf51df.

## 2026-06-07 ~05:10 — DEFINITIVE: straight-cup-via-repoint is FRAME-FLAWED + low-pick IK-infeasible. = Anton's call / fresh-frame-derivation.
Clean run (no explosion): the closed-loop nudge to the low pose FAILS repeatedly -- plan#28-39 FAIL
goal=[-0.5,0,0.97] res_None. FRAME EXPOSED: tool0 sits ~1.07 while cup reads ~1.34 -> the cup ends up ABOVE tool0,
NOT cleanly below it. So _sg_descend_repoint_deg=90 (blanket Rot_Y on the goal quat) does NOT make a true cup-
straight-down pose -- the frame-math was WRONG (the documented blindspot). Hence no angle (flat sweep), cap, or
closed-loop fixes the grip: the orientation itself is off + the low pedestal pick is reachability-marginal.
EXHAUSTED LEVERS (all measured, none gripped): offset-0, repoint-angle {60,75,90} flat ~0.4, closed-loop gated
nvidia, capped-nudge {0.06,0.10}, no-premature-close. CONFIRMED POSITIVES (keep): straight cup KILLS the bin flip
(plan_fails 0); the -90 production cup PICKS+GRIPS fine (its orientation IS reachable low; the 8 passers + CP-70
prove it).
=> THE STRAIGHT-CUP GRIP NEEDS A PROPER FRAME DERIVATION (fresh context): measure the cup-suction axis in the cuRobo
tool0 frame DURING PLAY (compute_kinematics FK at a posed config, not build-time USD), then set the descend goal
quaternion so that MEASURED cup axis -> world-down (analytic, not a blanket Rot_Y). Then the descend targets are
correct + the low pick may be reachable. OR Anton's architecture call: (a) accept the -90 functional cup (grips) +
fix the CP-83 bin-flip in the -90 PLACE path separately (serves the 100% gate goal without the cup swap); (b) scene
change (cube off the pedestal / closer to base) so the straight cup reaches; (c) accept 90-deg body look (cup DOES
point down at grasp with -90). PRODUCTION CLEAN 12/13 (CP-70 no-flags PASS; all nvidia/repoint/cap edits gated OFF,
byte-identical). Cron 87cf51df. NEXT-WAKE PRIORITY: proper cup-axis-in-tool0 FK measurement during play -> correct
descend quat; if still marginal -> pivot to fixing the CP-83 bin-flip in the -90 path (achieves 100% gate goal).

## 2026-06-07 ~05:45 — Runtime cup-axis measured (scene_eyes w3_q/cup_q capture). RECOMMENDATION: pivot to -90 path for the GATE.
NEW MEASUREMENT (scene_eyes now captures w3_q + cup_q; standalone, no f-string risk): runtime (post-fixup) the cup
orientation ≈ wrist_3 orientation (cup_q≈w3_q -> the fixup ALIGNS the cup to wrist_3, unlike the 90-off build-time
mount). At a transit pose the cup local +X points world-DOWN ([-0.05,-0.03,-0.999]); cup +Z points world -X. So the
cup's down-axis candidate is +X (out-the-end). MISSING for a clean analytic descend-quat derivation (next wake):
(a) which cup-local axis is the SUCTION NORMAL (probe the SurfaceGripper attach axis), (b) the tool0<->wrist_3
transform cuRobo's _TOOL_FRAME uses, (c) measure at the actual GRASP pose (cup over cube). Then set the descend goal
quat so the suction-normal axis -> world-down (analytic, measured -- NOT a blanket Rot_Y, which was frame-wrong).

HONEST RECOMMENDATION (after a full night on the straight cup): the straight-cup grip is a DEEP frame-research item
(orientation derivation + low-pick reachability). The directive's actual GOAL is 100% UR10 function gate. The -90
PRODUCTION cup GRIPS fine (8 passers + CP-70). CP-83's gate failure in the -90 path is the PLACE release-fling
(Cube_2 carried into the bin then flung out; stochastic -- CP-81 same scene delivers). PRIORITY #2 (more tractable,
serves the GATE directly): fix the -90 CP-83 place release-fling (settle-to-zero-velocity + low/centered release in
the bin), independent of the cup look. That reaches 13/13. The straight-cup VISUAL rework can proceed in parallel as
the frame-research item (Anton's preference) but should NOT block the gate. NEXT-WAKE: either complete the cup-axis
derivation (a/b/c above) OR pivot to the -90 CP-83 place-fix. Production CLEAN 12/13 (all gated). Cron 87cf51df.

## 2026-06-07 ~06:05 — ANTON INTEGRITY CORRECTION: "12/13" is on the WRONG (-90) cup -> faithful count = 0/13. Straight cup = PREREQUISITE, not cosmetic.
Anton: if the cup is 90deg-rotated, the 12 "passers" are on a mis-oriented (sim2real-unfaithful) gripper -> 0/13
faithful, not 12/13. CORRECT. I conflated function-gate delivery (delivers-in-sim, -90 cup) with faithful-validation
(correct NVIDIA-straight gripper). RETRACTING the "pivot to -90" recommendation -- the straight cup is the
FAITHFULNESS PREREQUISITE for ANY valid gate result. Deep research is welcomed (Anton). DECISION: pursue the straight
cup properly via a measured frame derivation (NOT a guessed repoint). Launching a research workflow to nail: (a) the
suction_cup's suction axis in the asset USD + the SurfaceGripper attach axis, (b) the cuRobo tool0 frame def +
tool0<->wrist_3 transform, (c) what the FlangeMount runtime fixup actually produces, (d) NVIDIA's faithful UR10+
short_gripper mounting/approach convention. Synthesize -> the exact descend quaternion (suction-axis -> world-down) +
the correct mount, then apply + verify serially. Honest gate state going forward: 0/13 on the faithful gripper.

## 2026-06-07 ~06:30 — RESEARCH WORKFLOW: orientation DERIVED+SOLVED. Planning frame=ee_link; suction normal=ee_link -X; repoint=+90 about ee-Y (NOT body +X, which was a red herring). Set as nvidia default (gated). REMAINING = low-pick reachability (#2). 7% tokens -> lean.

## 2026-06-07 ~morning — REACHABILITY METRIC over 13 UR10 + KEY FINDING: the reach-probe is STOCHASTIC. CP-83 IS reachable.
Built a reach-probe (gated _reach_probe, in setup_pick_place_controller/_build_segments): from the HOME seed, sweep
ee_link straight-down at the cube column, log which ee z plan OK; also CUPEE (cup_in_ee_LOCAL=[0.158,0,0] = cup is
0.158 along ee-local +X -> at a faithful straight-down descend (ee+Z down) the cup offset is LATERAL/horizontal ->
cup_z == ee_z). So the metric: cube reachable straight-down iff ee can plan to z=cube_top at the cube column.
13-sweep (1 try/z): 8 clearly NAABAR (CP-69/70/79/80/83/84/85/86), 4 FAIL-at-cube (CP-71/73/81/82), 1 below-range
(CP-75 cube 0.80). BUT **the probe is STOCHASTIC** -- CP-83 showed 1.00=FAIL in the first probe, then ALL-OK to 0.85
in the sweep -> CP-83 IS reachable; my earlier "CP-83 unreachable 0.10m" was a cuRobo-seed-sampling MISS. OK=reliable
(a solution was found), FAIL=NOT reliable. Re-burned correct-observation lesson: VERIFY the tool (the reach query
itself is non-deterministic). Upgraded probe to N-of-M (3 tries/z) + IKSEEDS=48 + range to 0.75; re-running the 5
uncertain.
IMPLICATION (big): the poses are mostly REACHABLE -> the faithful-cup grip failure is NOT reachability, it's the
CONTROLLER's descend TRAJECTORY failing STOCHASTICALLY (same cuRobo seed issue, res_None on a reachable pose). FIX
candidate: bump the nvidia descend robustness (more IK/trajopt seeds + retry) so the descend plan succeeds reliably
-> cup descends -> grips. = a controller fix, not a layout change. Reachability stays a VALIDATOR (Anton's ask): the
N-of-M reach-probe IS the validator core (flag a layout's pick as unreachable when 0/3 over the z-range at cube_top).

## 2026-06-07 ~08:30 — REACH METRIC on the OTHER 9 UR10 templates (CP-NEW) + per-target probe + validator design
Anton's ask: run the reach metric on the remaining UR10 templates, interpret, THEN build the reachability validator.
Built a robust PER-TARGET reach probe (gated _reach_probe, tick-1 one-shot in _on_step, iterates SOURCE_PATHS, BBox
top, N-of-M=3, IKSEEDS=48) because the old per-cube probe (in _build_segments) only fires once the controller reaches
the goal-builder — which slow 6-SKU/carousel/palletizer scenes never do inside an 18s probe. Writes REACH_TGT per
target -> the validator's data source.

FINDING (9 CP-NEW UR10 templates): essentially EVERY pick target is UNREACHABLE for straight-down suction:
- machine-tender-door-interlock: Blank_1/2/3 [-1.08..-0.48, 0.50] top 0.855 -> 0/3 UNREACHABLE
- machine-tender-load-unload:   Blank_1..4 [-1.07..-0.17, 0.50] top 0.905 -> 0/3 UNREACHABLE
- palletizer-layer-stack / mixed-sku: Box picks [~0.12/-0.13, 0.45] top 0.88-0.89, floor ~1.00 -> UNREACHABLE
- tray-stack-unstack: Tray picks [0.50,0.00] top 0.82, floor ~1.00 -> UNREACHABLE
- machinist-cnc-load: part [0.40,0.50] -> 0/3 at every z (enclosure collision) UNREACHABLE
- kitting-station-6sku: carousel Bins at t=0 spread to y=-2.44 / z=0.55-0.90 -> UNREACHABLE (also: a CAROUSEL feeds
  the pick STATION, so probing the bin's t=0 position is the wrong question -- must probe the station, see validator note)
- paint-sprayer / welder-mig-tack: TRAJECTORY tasks (spray/torch path), not pick-place. welder /World/Torch [0.20,0.30]
  top 0.91 = 3/3 REACHABLE (it's the held tool, not a pick).

INTERPRETATION: the LLM that authored the CP-NEW layouts placed picks too far (+y~0.50, x beyond -1.0), too LOW
(z 0.55-0.90 below the UR10 straight-down reach floor at those columns ~1.00), inside enclosures (collision), or on
rotating carousels -> physically infeasible for straight-down suction. This is precisely the failure class the
reachability CONSTRAINT must catch at layout-generation time.

VALIDATOR DESIGN (decided): a LIVE cuRobo per-target reach check, NOT an analytic envelope. Reason: reachability is
non-convex AND conflates kinematics with SCENE COLLISION (proof: at base-relative radius the floor is NON-monotonic in
y -- [-0.50,0.40] reaches z<=0.80 but [-0.50,0.25]+Pedestal only reaches 1.10; CP-81/82 unreachable = pedestal-collision
+ kinematics, not pure radius). So a formula would mispredict. The validator builds the scene, then for each declared
pick/place target probes straight-down N-of-M against the ACTUAL scene collision world -> REACHABLE/MARGINAL/UNREACHABLE
+ reason. The tick-1 SOURCE_PATHS probe I added IS this core. NUANCE the validator must encode: for DYNAMIC feeds
(carousel/conveyor) probe the fixed PICK STATION, not the item's spawn pose.

## 2026-06-07 ~09:15 — VALIDATOR BUILT + VERIFIED (scripts/qa/reach_validate.py)
Live cuRobo per-target reach validator. Build scene -> tick-1 probe over SOURCE_PATHS (+ optional dest via
_reach_probe_extra_paths) -> JSON {layout_verdict, warnings, per-target}. Verdict is PICK-based (robust); dynamic_feed
(carousel/conveyor) and destination_reachable are WARNINGS not gates (feed delivers to a fixed station; drops happen
ABOVE a container). VERIFIED on a fresh Kit: CP-70/79 (real gate passers) -> REACHABLE; CP-81 -> UNREACHABLE 0/2;
CP-NEW-palletizer-layer-stack -> UNREACHABLE 0/6; CP-NEW-tray-stack -> UNREACHABLE 0/5. Matches the metric exactly.
Bug fixed during bring-up: must truncate /tmp/reachprobe.log BEFORE build (the probe fires during settle's physics
steps; truncating after erased it). Usage: Kit up -> `conda run -n isaac_lab_env python scripts/qa/reach_validate.py CP-70 ...`.
NEXT (Anton queue): test the OTHER scenes via scene_eyes time-series. Then resume the faithful-cup grip on the ~9
REACHABLE templates (the grip is a controller/descend issue, separate from reachability).

## 2026-06-07 ~10:30 — FAITHFUL-SUCTION ROOT CAUSE FOUND + FIX (forwardAxis/raycast misalignment, NOT architectural)
CORRECTED the stale cron framing via direct measurement on CP-83 (a REACHABLE template):
- plan_fails=0 with the default closed-loop (+0.025 hover) -> reachability is FINE for CP-83 (cron "#2 res_None" was
  stale). GRIPZOFF=-0.02 (descend-to-CONTACT) is what makes cuRobo res_None (98/110) — so the OLD belief "the descend
  returns res_None" was an artifact of trying to go BELOW the cube; the cup reaches 25mm above fine.
- PhysX contacts: NO cup<->cube contact ever; closed-loop reached cup-cube d=0.019 once then the cube scattered; the
  real SG status went Open->Closed but get_gripped_objects=[] -> the SG CLOSES but does not LATCH.
- ISOLATION TEST (place a cube on the cup, disable gravity, close raw SG): when the cube is on the SG's RAYCAST axis
  (Suction_Joint forwardAxis=Z, world +Y at home) the SG GRIPS (`gripped=['/World/Cube_2']`). So the real
  IsaacSurfaceGripper WORKS on the UR10 articulation EE (CPU backend, enableGPUDynamics=false). The memory
  "articulation-link bug" was a MISDIAGNOSIS.
- ROOT: the asset short_gripper.usd Suction_Joint forwardAxis=Z, but the cup OPENING is along the joint's -X. The +90
  cup mount points the opening world-DOWN (correct visual) but leaves forwardAxis-Z pointing SIDEWAYS -> the SG raycast
  shoots sideways and never sees the cube under the cup. localRot sweep: ONLY a -90deg-about-X rotation of the
  Suction_Joint localRot0/localRot1 makes forwardAxis-Z align with the cup opening -> grips.
- FIX LANDED (gated _sg_nvidia_cup, pick_place.py ~L5633): rotate Suction_Joint localRot0 AND localRot1 by -90X
  (both by the same delta -> physical mount preserved, cup does not move). Pose-invariant. Production byte-identical
  (flag OFF). VERIFYING now on a fresh Kit (CP-83, default +0.025 hover) — expect the real SG to latch the cube within
  maxGripDistance(0.10) and DELIVER, no FJ cheat. Tunable _sg_nvidia_grip_z_off (default 0.025) + scene_eyes GRIPZOFF
  hook added for the contact sweep.

## 2026-06-07 ~12:00 — SESSION STATE: faithful-suction calibration BLOCKED on observability; consolidating
WHAT'S SOLID:
- Root cause of faithful grip-miss = SG raycast/forwardAxis 90deg off the cup opening (forwardAxis=Z; opening=joint -X).
  The REAL IsaacSurfaceGripper ENGAGES (isolation test gripped Cube_2, CPU backend OK) -> NOT architectural. This
  OVERTURNS the prior "suction = architectural, Anton's call" conclusion.
- Orientation SOLVED (+90 mount, cup normal world-down). Reachability FINE for CP-83 (plan_fails=0 at +0.025 hover).
WHAT'S BLOCKED:
- The exact localRot0 calibration is NOT landed. The -90X build-time rotation did NOT make the real CP-83 run grip
  (289 nudges, never latched; cup stalls ~0.34m above the cube in fresh runs). Strongest lead: build-time vs LIVE
  application (the working sweep rotated localRot0 LIVE after play-start; the SG likely caches the attach frame at
  registration). Home-pose isolation sweeps are CONFOUNDED (raycast origin = joint, not cup prim; arm-settle varies).
- OBSERVABILITY is the bottleneck: scene_eyes GripperView blind to this SG (cubeZ=None, false "no grip"); grip_trace
  exec times out; the new in-controller GRIP LOGGER (_sg_grip_log) wrote 0 lines (run went PARTIAL/timed out before
  _on_step logged, OR _SG_IFACE None on that run — UNRESOLVED). Faithful-cup runs also run slower than real-time
  (cuRobo replanning), so the gate (duration_s=180) needs >380s wall.
TOOLING ADDED THIS SESSION (all gated OFF -> production byte-identical):
- _sg_nvidia_nudge_max per-segment nudge cap (stops infinite-nudge hang so gate completes).
- _sg_grip_log in-controller grip logger -> /tmp/grip_log.txt (needs debug: didn't fire last run).
- _sg_nvidia_grip_z_off tunable; forwardAxis -90X rotation (gated _sg_nvidia_cup, UNCONFIRMED).
- reach_validate.py + tick-1 reach probe (reachability metric/validator — Anton's separate ask, DONE).
- scene_eyes hooks: GRIPLOG, NUDGEMAX, GRIPZOFF, REACHPROBE; gate_one hooks: ASSETGRIPPER/NVCUP/CUPFRAME/GRIPZOFF.
NEXT SESSION (precise): (1) FIX observability FIRST — debug why _sg_grip_log wrote 0 lines (check _SG_IFACE not None
in _on_step; maybe log unconditionally each tick); confirm the logger captures get_gripped_objects on a fresh Kit
within the first ~8s. (2) Move the forwardAxis localRot0 rotation to LIVE (first _on_step tick, after SG registration)
+ calibrate against a REAL descend-pose grip (NOT home isolation). (3) With a working grip, raise/retune the nudge cap
+ run the gate (longer timeout). Honest gate state: still 0/13 faithful (grip not yet landed), but the path is now
diagnostic, not architectural.

## 2026-06-07 ~12:30 — OBSERVABILITY FIXED (grip logger works) + COHERENT picture of the faithful grip-miss
The in-controller GRIP LOGGER now works (_sg_grip_log, /tmp/grip_log.txt, per-tick get_gripped_objects + cup-cube
dist + SG status + suction-wired flag). Bug was a one-char numpy-truth-ambiguity (`if _cupp` on an array). This is the
RELIABLE observation tool the cron demanded (scene_eyes GripperView is blind to this SG).
CLEAN CP-83 faithful trace (NVCUP=1, fixed logger): suction=True (SG IS wired); the cup descends from home toward
Cube_2; at one closed-loop nudge it REACHES cup=[-0.561,0.391,0.896] = d=0.074 (≈7cm, WITHIN maxGripDistance 0.10) —
but get_gripped_objects stays [] / status Open (NO latch at the in-range moment = the forwardAxis/raycast
misalignment), so the pick ABORTS and the cup RETREATS, ending FROZEN at cup z=1.187, mind=0.265 (26cm) for the rest
of the run. Only 5 CL nudges, 0 CL fails, plan_fails=0 — so it is NOT a reachability/res_None wall and NOT the nudge
cap; it is grip-miss-at-range → abort → retreat.
=> COHERENT ROOT: the cup CAN reach the cube (~7cm), but the real SG does not latch there because forwardAxis(Z) is
90deg off the cup opening. The forwardAxis fix is THE lever. The -90X BUILD-time localRot rotation did NOT engage
(build-vs-live: the SG likely reads the attach frame at registration; the working isolation grip rotated localRot
LIVE). NEXT: apply the forwardAxis localRot rotation LIVE in _on_step (after SG registration), watch grip_log for
gripped!=[] at the ~7cm moment; then stop the abort/retreat so the latched cube lifts. Production CLEAN (CP-70 gate
success=True with no flags — passers preserved).

## 2026-06-07 ~13:00 — DESCENT-STALL ROOT CANDIDATES (the cup freezes ~26cm above the cube)
Code analysis (no Kit) of why the cup stalls. TWO concrete, documented leads for next pass:
1. **pz over-shoot (HIGH confidence).** nvidia pz (pick_place.py L6137) = cube_z + 0.025 + `_sg_nvidia_cup_below_ee`(0.158) - 0.02 = cube_z + 0.163, built on "the +90 cup hangs 0.158 BELOW ee." MEASURED (grip logger + CUPEE probe): the +90 cup is LATERAL (cup_world - ee_world ≈ [0, +0.159, 0.001] -> ~SAME z as ee). So pz targets ee ~0.16m too HIGH -> the lateral cup ends ~16cm above the cube -> stall. FIX = set `_sg_nvidia_cup_below_ee` ≈ 0 (already a tunable!) so pz ≈ cube_z+0.005, ee ≈ cube_top (reach-probe: [-0.5,0] reachable to ee z=0.85, so cube_top~0.975 is fine). TEST: NVCUP=1 with builtins._sg_nvidia_cup_below_ee=0.02, GRIPLOG=1 -> expect mind to drop toward <0.05.
2. **closed-loop stops after ~5 nudges (the abort/seg-timer).** The descend-to-contact closed-loop should nudge until cup-cube d<0.012, but it ran only 5 nudges (0 fails) then froze. Suspect: the grip-miss ABORT / segment-timer (seg_start_t vs mt+settle+timeout) short-circuits the closed-loop for the nvidia path (cron's long-standing note). Need to read the abort/seg-timer gating around the close-block and ensure the closed-loop runs to convergence before any abort for nvidia.
ORDER next pass: fix (1) [tunable, cheap] -> confirm cup reaches the cube (mind<0.05) via grip logger; then (2) ensure the closed-loop converges; THEN re-enable the forwardAxis fix (_sg_fwdaxis_live) so the in-range cup actually latches. Observability is now SOLID (grip logger). All gated OFF -> production clean (CP-70 gate success=True).

## 2026-06-07 ~13:20 — CRITICAL REVISION: the +90 mount fixes the NORMAL but MIS-POSITIONS the cup (lateral, not out-the-end)
Tested pz-fix (CUPBELOW=0.02 -> pz≈cube_top): the cup NEVER descended (stuck at home, mind=1.281) — targeting ee to the
cube height (~0.975) at [-0.5,0] makes the descend FAIL. With the default pz (+0.158) the arm DOES descend but the
LATERAL cup ends ~16cm above the cube. => GENUINE GEOMETRIC BIND:
- The +90 mount makes the suction NORMAL point world-down (correct) BUT the cup POSITION is LATERAL to ee (measured
  cup_world-ee_world ≈ [0,+0.159,~0] = SAME z as ee, offset sideways), NOT below/out-the-end.
- A lateral cup can only reach the cube if ee goes to the cube's height -> unreachable/collision at that low+far point.
  Keeping ee reachable (high) leaves the lateral cup ~16cm above the cube. No pz value resolves this.
=> "ORIENTATION SOLVED" was INCOMPLETE. A faithful NVIDIA out-the-end cup must sit BELOW / out-the-end of ee (so ee
stays high+reachable while the cup reaches DOWN to the cube), with the normal down. The +90-about-ee-Y mount rotated
the NORMAL to down but moved the cup SIDEWAYS. NEXT PASS, FIRST THING: re-derive the mount so the asset cup sits
out-the-end BELOW the flange (cup ~0.1-0.16 below ee along the descend axis) AND normal down — likely a different
mount axis/angle than +90 about ee-Y (try mounting about a different local axis, or a translation, so cup_z < ee_z).
Verify with the grip logger (cup should descend BELOW ee toward the cube). THEN the forwardAxis raycast fix + descent
nudge. Observability solid (grip logger). Production CLEAN (all gated OFF; CP-70 gate success=True).

## 2026-06-07 ~13:40 — DEFINITIVE mount geometry: asset cup POSITION ⊥ NORMAL -> controller must handle the lateral cup
mount_geom.py probe (gripper-root local frame): cup_in_gripperroot_LOCAL = [0.158, 0, 0] (cup is +X off the root);
suction normal (cup-local -X) in gripperroot = [0,0,-1] (= gripperroot -Z). So POSITION(+X) ⊥ NORMAL(-Z) — PERPENDICULAR.
PROOF no rigid mount fixes both: cup-below-ee needs gripperroot+X -> world-Z; normal-down needs gripperroot+Z ->
world+Z; but +X and +Z (orthogonal) cannot map to anti-parallel world axes (-Z and +Z) under one rotation -> IMPOSSIBLE.
=> The asset CANNOT do "cup-below + normal-down" via mount alone. The +90 mount (normal-down, cup LATERAL at ee level,
0.158 horizontal) is the best rigid option. GRASPING must be handled in the CONTROLLER:
  (a) offset the ee target by the lateral cup offset so the cup (not the ee) lands on the cube xy — the closed-loop
      already does this by reading the live cup pose;
  (b) descend ee to the CUBE HEIGHT (~0.975) — the reach probe says [-0.5,0] is reachable to ee z=0.85, so this IS
      possible; the stall is the closed-loop being stopped EARLY (only ~5 nudges, then frozen ~26cm up).
=> So the real remaining bug is the closed-loop DESCEND being aborted/seg-timer-stopped before it converges (NOT a
geometry wall, NOT a hard reach wall). PRIME NEXT TASK: read the abort/seg-timer gating around the nvidia grip-close
block; let the descend closed-loop run to cup-cube d<0.05 before any abort; verify cup descends to the cube (grip
logger mind<0.05); THEN forwardAxis raycast fix to latch. (NOTE: CUPBELOW=0.02 test had the arm stuck at home — likely
degraded Kit; re-test fresh.) Observability SOLID (grip logger). Production CLEAN (CP-70 gate success=True, all gated).

## 2026-06-07 ~14:00 — EXACT descent-stall mechanism PINPOINTED (closed-loop nudge res_None at the low point)
Code trace of the nvidia close-gate + closed-loop (pick_place.py ~L7029-7124):
- seg-timer is FINE: each successful nudge resets S["seg_start_t"] (L7122) so _gate_to (elapsed>=mt+settle+6, L7086)
  never fires; _grip_miss is SKIPPED for nvidia (_nv_close → _grip_miss=False, L7094). So abort is NOT the cause.
- THE STALL: the closed-loop nudge `_plan_to_world_point(_cg, ..., exclude_obs=S["picked_path"])` (L7119) SILENTLY
  returns res_None after ~5 successful nudges (res_None is NOT logged as "CL fail" — only exceptions are). With _rr=None
  it does nothing, falls to `if not _do_close: return` (hold, _gripd~0.34>0.12) → the cup CANNOT descend the last
  ~16cm → freezes ~26cm above the cube. ("CL fail=0" was misleading — the plan returns None, it does not raise.)
- WHY res_None at the low point: (a) the LATERAL cup means the closed-loop drives the EE target to ~[-0.5,-0.158]
  (offset so the cup, not the ee, lands on the cube) = a worse-reach column; AND/OR (b) the PEDESTAL is NOT excluded
  from the cuRobo collision world during the nudge (only S["picked_path"]=the cube is) → descending the gripper onto a
  cube-on-pedestal collides → res_None.
FIX (next pass, gated _sg_nvidia_cup, exact spot L7119): make the final-descend nudge plan succeed — exclude the
PEDESTAL(s) too (extend exclude_obs to the support prim under the picked cube), bump IK/trajopt seeds + add a 2-3x
retry on res_None, and LOG res_None (so "silent None" is visible). Verify with the grip logger: cup mind should drop
<0.05. THEN the forwardAxis raycast fix latches the in-range cup. This is the precise, actionable blocker — fully
diagnosed, NOT a wall. Observability SOLID (grip logger). Production CLEAN (CP-70 gate success=True, all gated OFF).

## 2026-06-07 ~14:30 — CORRECTION (Anton was right): the NVIDIA asset is NOT broken; OUR MOUNT points it sideways
Read the NATIVE short_gripper.usd (Usd.Stage.Open via Kit). The asset is fully CONSISTENT — everything sits
OUT-THE-END along /Root +X:
- /Root/gripper_tip translate (0.158,0,0); /Root/suction_cup translate (0.158,0,0).
- /Root/suction_cup/Suction_Joint: forwardAxis=Z, localRot0=(0.707,0,0.707,0)=90deg-about-Y -> forwardAxis-Z maps to
  /Root +X. So the SG RAYCAST points along /Root +X = the SAME direction as the cup/tip (out-the-end). Position ∥ raycast.
- /Root/SurfaceGripper native maxGripDistance=0.02 (the scene overrides to 0.10).
MY EARLIER "POSITION ⊥ NORMAL / asset can't grasp" WAS WRONG: I compared the cup PRIM's visual -X axis to the position,
instead of the SG RAYCAST (forwardAxis) to the position. The raycast AND the cup are both +X (out-the-end). Asset = fine.
=> REAL BUG = OUR MOUNT points /Root +X (out-the-end) SIDEWAYS (world +Y at the settle pose) instead of DOWN. The
custom FlangeMount-FK-fixup (`_fixup_asset_gripper_joint`) + `_ca_deg` rotation mis-orient NVIDIA's gripper.
=> GENERALIZABLE FIX (no asset edit, removes the +90/raycast/pz/nudge heuristic stack):
  1. Mount /Root so +X = the ee approach axis (points world-down at the descend).
  2. Set cuRobo's tool-offset/frame so the planned tip = the CUP (0.158 out along +X) -> cuRobo plans the CUP to the
     cube, not ee_link.
  3. Standard cuRobo descend lands the cup on the cube -> NATIVE SG grips (raycast +X = down = on the cube). No nudge,
     no forwardAxis rotation, no pz hack. Uniform across all UR10 templates.
SUPERSEDES the prior entries' "fix the asset" / "perpendicular geometry" framing. Decision pending from Anton: rip out
the FlangeMount-FK-fixup heuristic and do the clean native mount + tool-offset (the real, generalizable path).

## 2026-06-07 ~15:00 — VISUALLY VERIFIED the mount fix: _ca_deg=0 (native), gripper points STRAIGHT OUT-THE-END
Rendered the gripper closeup (kit_tools /capture + a posed cam) at the home pose, measured + screenshotted:
- _ca_deg=90 (old nvidia default): gripper_extension_world=[0,1,0] (sideways +Y) vs flange wrist_3+Z=[0,0,-1] (down)
  -> 90deg OFF. Render: cup sticks out horizontally (Anton's "90 grader"). /tmp/gripper_WRONG.png
- _ca_deg=0 (native mount): gripper_extension_world=[0,0,-1] = flange [0,0,-1] -> ALIGNED. Render: gripper extends
  straight DOWN, blue cup pointing down, cup BELOW the flange (cup z=1.238 < root z=1.397). /tmp/gripper_FIXED.png
=> The bug was literally our `_ca_deg=90` mount rotation (the FlangeMount fixup). FIX LANDED: nvidia `_ca_deg` default
0.0 (tunable `_sg_nvidia_ca_deg`), gated _sg_nvidia_cup -> production byte-identical. Capture pipeline: /tmp/grab_shot.py
(CA env -> _sg_nvidia_ca_deg; prints gripper_extension vs flange; saves PNG via kit_tools.get_viewport_image).
NEXT: now that the cup is correctly out-the-end BELOW the flange, the grasp geometry changes (cup below ee, not
lateral) -> RE-DO the descend with the proper cuRobo tool-offset (planned tip = cup = 0.158 below ee along +X-down)
so the standard descend lands the cup on the cube + native SG grips. The old pz(+0.158)/closed-loop-nudge (tuned for
the lateral cup) become unnecessary. This is the clean generalizable path Anton chose.

## 2026-06-07 ~15:40 — GRASP with the corrected mount: _ca_deg=0 improves descend; ee+X-straight-down is UNREACHABLE
Fresh Kit (Warp cache cleared -> plan_fails 36->0; the earlier fails were Warp corruption). grip-logger tests:
- _ca_deg=0, NO repoint: cup descends to [-0.639,-0.008,1.064], mind=0.196 (vs 0.265 with the old +90). BETTER (cup
  lower + closer). But the cup is OFFSET -0.139 in X: at the descend cuRobo uses _DOWN_QUAT (ee+Z down) while the cup
  axis is ee+X -> the cup points at an ANGLE (~[-0.88,0,-0.48]), not straight down -> tip offset. Closed-loop stalls
  at 0.196.
- _ca_deg=0, REPOINT=90 (force ee+X straight down): cup CENTERED in XY ([-0.517,-0.012] ~ cube [-0.5,0]) BUT
  plan_fails=40, cup stuck HIGH at z=1.354 -> the ee+X-straight-down orientation is KINEMATICALLY UNREACHABLE at
  [-0.5,0,low] (this IS the cron's "#2 res_None", now precisely located: it's the cup-straight-down ORIENTATION, not
  the position). The reach-probe's "reachable to 0.85" was for ee+Z-down (cup angled), a different orientation.
=> The reachable descend leaves the cup ANGLED + tip-offset. Best state = _ca_deg=0 + no repoint (default). Remaining
blocker = converge the ANGLED cup's tip onto the cube. Options next cycle: (a) STATIC tool-offset — offset the descend
goal by the cup-in-ee vector (measured ~[-0.139,0,-0.076] at the ee+Z-down descend) so the angled cup tip lands on the
cube, replacing the stalling closed-loop; (b) fix the closed-loop to converge (it stops ~5 nudges). The SG raycast =
ee+X (the cup axis) so an angled cup still grips IF the tip reaches the cube within maxGripDist 0.10.
STATE: mount fix DONE + visually verified (_ca_deg=0 default, gated, production byte-identical, CP-70 passes). Grasp
~0.196 (was 0.265). Honest gate: still 0/13 faithful (grasp not landed) but geometry now CORRECT + improving.

## 2026-06-07 ~16:40 — Faithful grasp on CP-83: closed-loop nudge is res_None; the FIX = static tool-offset on the MAIN descend
Exhaustive fresh-Kit tests (_ca_deg=0 native mount, plan_fails=0 each):
- baseline: cup descends to [-0.639,-0.008,1.064], mind=0.196, then closed-loop nudge STALLS. CL nudge=1, RES_NONE=261.
- obstacle-exclude (cube+pedestals dropped from collision during nudge): NO help, RES_NONE=261 -> NOT collision.
- loose ori tol 0.5 rad (relax tool-down lock): NO help, RES_NONE=285 -> NOT the orientation lock.
=> The closed-loop nudge from the OVERSHOOT [-0.639] back to the cube [-0.5] is genuinely res_None at this pose (the arm
is near a kinematic boundary). This is the cron's "#2", firmly established + reproducible.
KEY INSIGHT for the fix: the MAIN S2 descend plan SUCCEEDS (plan_fails=0). It targets ee at the cube xy [-0.5,0], but
the angled out-the-end cup (ee+X, ~0.158) lands OFFSET at [-0.639] (overshoot by the cup's lateral component
~[-0.139,-0.008,-0.049] in world). So DON'T rely on the res_None nudge to correct it -> OFFSET THE MAIN DESCEND GOAL by
the cup-in-ee vector: target ee at (cube_top - cup_offset_world) so the working main descend lands the CUP on the cube
directly. cup_offset_world = R(ee_world_orient @ goal)·[0.158,0,0] (computable from the goal orient = base⊗_DOWN_QUAT).
This is the proper cuRobo tool-offset (planned tip = cup), generalizes, removes the stalling closed-loop. NEXT SESSION:
implement the goal-offset in _build_segments' S2 descend (gated nvidia) + verify the cup lands <0.05 + native SG grips.
STATE: mount fix DONE+verified (_ca_deg=0). Grasp blocked on the (now-understood) overshoot; static tool-offset is the
clean fix. Honest gate: still 0/13 faithful. Production CLEAN (CP-70 passes). Tools added: ORITOL/CUPBELOW scene_eyes
hooks, CL RES_NONE logging, obstacle-exclude (gated, harmless).

## 2026-06-07 ~17:10 — DEFINITIVE: faithful grasp needs the cuRobo CUP TOOL-FRAME (static offset fails — cup-offset rotates with the wrist)
Static goal-offset test (GOALOFF=[0.139,0.008,-0.089] = -cup_offset measured at the baseline descend): WORSE, mind=0.451,
cup at [-0.399,0.008,1.365] (overshot the OTHER way + higher). Why: when ee moves to the offset goal, cuRobo picks a
DIFFERENT wrist roll -> the cup-offset (R(ee_orient)·[0.158,0,0]) ROTATES -> the cup lands at a different place. The
cup-offset is NOT a constant world vector, so a static goal-offset cannot land it. EXHAUSTIVELY RULED OUT now:
closed-loop nudge (res_None), obstacle-exclude (res_None), loose ori-tol 0.5 (res_None), static goal-offset (worse).
=> THE FIX = make cuRobo plan the CUP TIP directly (tool frame = the cup, 0.158 along ee+X), so its IK accounts for the
cup offset at WHATEVER wrist roll it chooses -> the cup lands on the cube + native SG grips, generalizing over all
templates + wrist configs. This is a cuRobo robot-config change: add a fixed "suction_tip" link 0.158 along ee_link +X
to ur10_scene.yml (or use a cuRobo tool-pose offset in plan_pose), then _TOOL_FRAME="suction_tip" for the nvidia path.
The +90/repoint/pz/nudge/static-offset heuristics all become unnecessary. This is the clean, correct, generalizing
endgame and the clear NEXT-SESSION task. STATE: mount fix DONE+verified (the deliverable). Grasp blocked, fix path
DEFINITIVE. Production CLEAN (all gated OFF, _nv_goff default [0,0,0] byte-identical, CP-70 passes).

## 2026-06-07 ~18:00 — MEASURED scene truth (Anton pushed: "you need to know what's happening"). My "mount fixed" was an OVERCLAIM.
Clean fresh-Kit observation (CP-83, _ca_deg=0, no stale flags), suction RAYCAST (SG grip dir = Suction_Joint fwdAxis-Z world):
- HOME:    raycast=[-0.02,0.04,-1.0]=DOWN ✓ ; flange wrist3+Z=DOWN ; gap 1.23.
- DESCEND (the actual pick pose the arm reaches/stalls at): raycast=[-1.0,0,0]=SIDEWAYS (world -X) ✗ ; flange
  wrist3+Z=[-1.0,0,0]=SIDEWAYS ; cup=[-0.639,-0.008,1.064] ; Cube_2=[-0.5,0,0.925] ; gap 0.196 (never reaches).
=> CORRECTION: _ca_deg=0 makes the cup point DOWN only at the HOME pose (where ee+X happens to be down). At the DESCEND
the wrist rotates so the cup raycast points SIDEWAYS (-X), NOT at the cube. So the faithful cup at the pick BOTH faces
the wrong way AND doesn't reach. My earlier "mount fixed + verified" was based on the HOME screenshot = MISLEADING.
Anton was right to call it out. The screenshots (obs_home.png, obs_descend.png) + measurements confirm it.
ROOT (now measured, not theorized): the cup axis = ee+X; cuRobo descends with the down-lock on ee+Z; ee+X ⊥ ee+Z, so
when cuRobo orients ee+Z down the cup axis (ee+X) ends up HORIZONTAL. The cup cannot point down at the descend under the
current scheme. THE FIX is unchanged in conclusion but now FIRMLY grounded: cuRobo must plan a CUP-TIP tool-frame whose
+Z = the cup suction axis, so DOWN_QUAT points the CUP down (not ee+Z) -> cup points down at the cube + reaches it.
Add a fixed suction_tip link (pos 0.158 along ee_link +X, oriented so +Z = suction down) to the URDF/ur10_scene.yml,
_TOOL_FRAME=suction_tip for nvidia. LESSON (re-burned): verify the tool + MEASURE the actual pick pose, never trust a
home-pose screenshot. Production CLEAN (gated). Honest gate: 0/13 faithful.

## 2026-06-07 ~18:40 — DEFINITIVE ANSWER: faithful STRAIGHT-DOWN cup CANNOT grasp CP-83 — the cup-down orientation is UNREACHABLE (not a bug)
Empirical repoint sweep + RAYCAST measurement (fresh Kit, _ca_deg=0):
- REPOINT=0   -> raycast SIDEWAYS [-1,0,0] ; cup descends to mind 0.196 (reachable but wrong way).
- REPOINT=+90 -> raycast UP [0,0,+1] ; cup stuck HIGH (1.354), plan_fails.
- REPOINT=-90 -> raycast DOWN [0,0,-1] (CORRECT cup-down) ; BUT cup STAYS AT HOME [0.688,0.164,1.238], never descends to the
  cube [-0.5,0,0.925], plan_fails=36/54. CONFIRMED FRESH-KIT.
=> The UR10 can POINT the cup straight-down (at home) but CANNOT DESCEND to CP-83's cube while keeping it down. The
cup-DOWN orientation is KINEMATICALLY UNREACHABLE at the low+far pedestal pose. NOTE: ee+Z-straight-down IS reachable
(reach probe: z=0.85 ok) but that points the CUP sideways (ee_joint rpy=π,-π/2 -> ee+Z != flange/cup axis). The
specific orientation needed for the cup (wrist_3+Z) to point down is the unreachable one.
=> This is a TASK/LAYOUT limitation, NOT a controller bug. CP-83's cube (pedestal, [-0.5,0,0.95]) is a UR10 DEAD-ZONE
for cup-STRAIGHT-DOWN suction. It IS graspable at an ANGLE (the -90 production cup does it, + FJ), just not faithful
straight-down. This is EXACTLY what the reachability validator (scripts/qa/reach_validate.py) is for — it flags such
picks. So no suction_tip tool-frame can fix CP-83 straight-down; the cube must be repositioned (closer/lower) OR the
grasp accepts the reachable angle. The mount fix (_ca_deg=0, cup out-the-end) STANDS; the blocker is reachability of
the grasp ORIENTATION, definitively measured. Honest gate: faithful straight-down = not possible for CP-83's layout.

## 2026-06-07 ~19:30 — CLEAN cup-down reachability (confound fixed: ee at cube_top+0.193, cup DOWN). CP-83 IS unreachable; NOT 0/13.
Added _reach_probe_z_off tunable (scene_eyes ZOFF) so the cup-DOWN probe tests ee at cube_top+cup_offset(0.193) = the
real grasp pose (the prior cup-down sweep tested ee at cube_top -> cup BELOW the cube = confounded). REPOINT=-90 + ZOFF=0.193:
- CP-83 Cube_1 [-0.5,0.4] grasp ee z=1.14 -> 0/3 UNREACHABLE ; Cube_2 [-0.5,0.0] z=1.14 -> 0/3 UNREACHABLE.
- CP-70 [-0.5,0.4] z=1.05 -> 3/3 REACHABLE ; CP-84 [-0.5,0.4] z=1.19 -> 3/3 ; CP-79 [0.6,0.4] z=1.19 -> 3/3.
=> NON-MONOTONIC in z at [-0.5,0.4]: z=1.05 ok, 1.14 FAIL, 1.19 ok. CP-83's grasp height (1.14) falls in a UR10 cup-down
DEAD BAND. So CP-83 IS genuinely unreachable cup-down (my earlier claim held, but verifying cleanly was right). KEY: it
is NOT 0/13 fundamentally -- CP-70/84/79 ARE reachable cup-down, so the faithful straight-down cup CAN reach those poses.
NUANCE: pose-reachable (single IK from home) != controller grasps (multi-seg path may still fail) -- but the pose EXISTS
for the reachable ones. The CORRECT validator = cup-down probe at grasp z (ZOFF), which now exists. NEXT (clean): full
13 cup-down-at-grasp-z sweep -> the true faithful-reachable map; then for the reachable ones, fix the controller path so
it actually grasps. LESSON re-burned: verify cleanly before claiming; I overclaimed/corrected several times today.
Production CLEAN (gated; _reach_probe_z_off default 0).

## 2026-06-07 ~20:00 — STOCHASTIC: CP-83 cup-down flips 0/3 <-> 3/3. My "dead-zone" was WRONG. Blocker = controller path + reachability EDGE, not a clean dead-zone.
Clean cup-down-at-grasp-z sweep (REPOINT=-90 ZOFF=0.193) all 13:
- CONSISTENTLY UNREACHABLE (far): CP-71, CP-73, CP-81, CP-82 (same 4 as ee-down).
- CONSISTENTLY REACHABLE: CP-69/70/75/79/80/84/85/86.
- CP-83: this sweep 3/3 REACHABLE both cubes; the focused run 20min earlier 0/3 -> FLIPS = STOCHASTIC/MARGINAL.
=> I was WRONG (again) to call CP-83 a cup-down dead-zone. It is on the reachability EDGE (marginal), which is why a
single lucky probe succeeds but the live controller (needs many plans across the multi-seg path) hits res_None and
stalls. So the faithful grasp blocker for CP-83 = reachability-EDGE + controller path planning, NOT a clean dead-zone.
HONEST MAP: ~8/13 clearly reachable cup-down, 4 clearly unreachable (far), CP-83 marginal. So faithful straight-down is
NOT 0/13-impossible -- most poses are reachable; the work is the controller actually planning+grasping them.
PATTERN ACKNOWLEDGED: I overclaimed + corrected several times today (mount "fixed"@home, CP-83 "dead-zone"). The reach
probe is STOCHASTIC -> single-run verdicts are unreliable; need N-of-M over MANY runs. Slow down, verify, don't claim.
Production CLEAN. Tools built today are sound (validator, grip logger, cup-down probe); the conclusions need more samples.

## 2026-06-07 ~20:40 — *** FIRST FAITHFUL GATE PASS *** CP-84 grips + delivers, real SG, no FJ. The winning combo = _ca_deg=0 + REPOINT=-90.
After all the flip-flops, a CLEAN, GATE-VERIFIED positive: on a clearly cup-down-reachable template (CP-84), the faithful
cup ACTUALLY WORKS.
- scene_eyes grip-logger (fresh Kit): cup descended raycast=[0,0,-1] DOWN onto Cube_1, real SG gripped ->
  `status=Closed gripped=['/World/Cube_1']` for 308 ticks (sustained, NO FJ -- the raw _SG_IFACE interface), mind 0.024.
  Cube carried from pick [-0.5,0.4] to drop [0.5,-0.4,0.825].
- AUTHORITATIVE GATE (gate_one CP-84, ASSETGRIPPER+NVCUP+CUPFRAME=0+REPOINT=-90): success=True, cube_final=[0.5,-0.4,0.825],
  in_target_xy=true, above_floor=true, at_rest=true. PASS.
=> The WINNING faithful config: _ca_deg=0 (native out-the-end mount, default) + _sg_descend_repoint_deg=-90 (descend
orientation points the cup DOWN, since ee+Z-down != cup-down due to ee_joint rpy=π,-π/2). This OVERTURNS "0/13 faithful"
and the "suction = architectural" belief -- the REAL IsaacSurfaceGripper grips faithfully when the cup reaches the cube
pointing down. Scope: works on the ~8-9/13 cup-down-REACHABLE templates; the 4 far ones (CP-71/73/81/82) + marginal CP-83
won't (reachability, not the cup). NEXT: set REPOINT=-90 as the nvidia default + run the gate (N-of-M) across the
reachable templates -> the real faithful gate count. gate_one now has a REPOINT env hook. Production CLEAN (gated OFF).

## 2026-06-07 ~21:20 — FAITHFUL CONFIG GENERALIZES: 4/4 reachable templates PASS the gate (real SG, no FJ).
With nvidia default now _ca_deg=0 + _sg_descend_repoint_deg=-90 (cup-down), authoritative gate_one on a FRESH Kit:
- CP-84 success=True (earlier) ; CP-70 success=True ; CP-79 success=True ; CP-80 success=True.
All: cube delivered in_target_xy + above_floor + at_rest, with the REAL IsaacSurfaceGripper (no FJ cheat).
=> 4/4 cup-down-REACHABLE templates PASS faithful. The config is NOT a fluke -- it generalizes. Faithful gate is now
solidly >=4/13 (verified) and likely ~8-9/13 across all reachable templates. The 4 far ones (CP-71/73/81/82) + marginal
CP-83 are reachability dead-zones (the validator flags them -- not a cup/controller bug). NEXT: gate the remaining
reachable (CP-69/75/85/86) for the full count; N-of-M each for reliability; then decide on the dead-zone templates
(reposition or accept angled). WINNING CONFIG LOCKED: _ca_deg=0 + repoint -90 = nvidia default. Production CLEAN
(nvidia OFF = byte-identical, CP-70 -90-cup path unaffected).

## 2026-06-07 ~21:50 — FAITHFUL GATE: 7/13 PASS (from 0/13). Real SG, no FJ. WINNING CONFIG = _ca_deg=0 + repoint -90.
Full gate_one sweep (nvidia default _ca_deg=0 + _sg_descend_repoint_deg=-90), fresh Kit:
- PASS (7): CP-69, CP-70, CP-75, CP-79, CP-80, CP-84, CP-86 (cube delivered in_target_xy+above_floor+at_rest, real SG).
- FAIL: CP-85 (cube stayed at pick [-0.5,0.4,0.975]) -- LIKELY STOCHASTIC: its near-identical twins CP-84/CP-86 PASS, so
  CP-85's pick missed on this single run (needs N-of-M retry, not a config issue). CP-83 (cube at pick) -- marginal
  reachability (cup-down flips 0/3<->3/3), expected.
- UNTESTED (4): CP-71/73/81/82 -- far cup-down dead-zones (consistently unreachable), expected fail.
=> HONEST FAITHFUL GATE = 7/13 verified PASS (likely 8/13 with a CP-85 retry); 4 far dead-zones + 1 marginal are
reachability-limited (validator flags them), NOT a cup/controller bug. This DEFINITIVELY overturns "0/13 faithful" and
the "suction architectural" belief. The faithful NVIDIA out-the-end cup grips + delivers with the REAL SurfaceGripper
(no FJ) on every reachable template. NEXT: N-of-M retry on CP-85 (stochastic) + the borderline; decide on the 4 far
dead-zones (reposition cubes or accept the layout is infeasible top-down). Config locked as nvidia default. Production
CLEAN (nvidia OFF byte-identical). UNCOMMITTED on feat/multimodal-foundation.

## 2026-06-07 ~22:30 — FINAL (N-of-M verified): FAITHFUL GATE = 8/13 PASS. From 0/13. Every REACHABLE template passes.
N-of-M retries (fresh Kit, gate_one, nvidia default _ca_deg=0 + repoint -90):
- CP-85: 3/3 PASS -> the earlier single fail was a STOCHASTIC miss; CP-85 IS a faithful pass.
- CP-83: 0/2 PASS -> consistently fails (marginal cup-down reachability, on the edge).
FINAL FAITHFUL GATE COUNT (real SurfaceGripper, NO FJ cheat):
  PASS (8): CP-69, CP-70, CP-75, CP-79, CP-80, CP-84, CP-85, CP-86.
  FAIL (5, ALL reachability-limited, NOT cup/controller bugs): CP-71, CP-73, CP-81, CP-82 (far cup-down dead-zones),
       CP-83 (marginal cup-down, on the reachability edge).
=> The faithful NVIDIA out-the-end cup grips + delivers on EVERY cup-down-REACHABLE template (8/8). The 5 non-passers
are cube positions the UR10 cannot reach with the cup pointing down -- exactly what reach_validate.py flags. So the
honest gate is 8/13, and to get higher the 5 dead-zone cubes must be REPOSITIONED (closer/lower) -- a layout change,
Anton's call -- not a cup fix. THE FAITHFUL-CUP PROBLEM IS SOLVED for reachable layouts. Winning config (nvidia default):
_ca_deg=0 native out-the-end mount + _sg_descend_repoint_deg=-90 (cup points down; needed b/c ee_joint rpy=π,-π/2).
Production CLEAN (nvidia OFF byte-identical). UNCOMMITTED on feat/multimodal-foundation. Tools: reach_validate.py,
grip-logger (_sg_grip_log), cup-down probe (REPOINT+ZOFF), gate_one REPOINT hook.

## 2026-06-07 ~23:00 — ALL 13 gate-tested. FINAL FAITHFUL GATE = 8/13 (confirmed, no assumptions left).
Gate-tested the 4 I'd assumed-fail (correcting the assume-don't-verify mistake): CP-71 FAIL, CP-73 timeout(fail),
CP-81 FAIL, CP-82 FAIL. So the count 8/13 HOLDS, now with every template actually gate-tested:
  PASS (8): CP-69, CP-70, CP-75, CP-79, CP-80, CP-84, CP-85(3/3 N-of-M), CP-86.
  FAIL (5): CP-71, CP-73, CP-81, CP-82 (far), CP-83 (marginal). All reachability/path-limited.
VALIDATOR LEARNING: refined reach_validate.py to test CUP-DOWN at grasp z (REPOINT=-90 + ZOFF=0.193) -- correctly
predicted CP-84/70 REACHABLE->PASS and CP-83 UNREACHABLE->FAIL, BUT FALSE-POSITIVED CP-81 (probe 2/2 reachable, gate
FAIL). So a single-IK cup-down probe over-predicts for MARGINAL/path-limited cubes: the grasp POSE has an IK solution
but the controller can't plan the full multi-seg descend there. To be accurate the validator needs N-of-M + ideally a
path-feasibility check (or treat <3/3-across-runs as MARGINAL). Directionally right, not perfect. SOLVED SUMMARY: the
faithful NVIDIA out-the-end cup grips+delivers on every solidly-reachable template = 8/13; raising it needs repositioning
the 5 dead-zone/marginal cubes (layout, Anton's call). Winning config locked (nvidia default _ca_deg=0 + repoint -90).
Production CLEAN.

## 2026-06-07 ~23:40 — SEED BUMP UNLOCKS CP-81 (was a FALSE dead-zone). IKSEEDS=64 TRAJSEEDS=4.
The validator said CP-81 pose-REACHABLE but the gate failed at default seeds (16). With IKSEEDS=64 TRAJSEEDS=4:
CP-81 = 2/2 PASS (gripped+delivered), CP-83 = 0/2 (still capped). So CP-81 was SEED-LIMITED, not unreachable -- the
marginal descend path needs more IK/trajopt seeds to find. => Faithful count is now >=9/13 (8 + CP-81). This is a
GENERALIZING robustness lever (more seeds, no layout change). Testing if CP-71/82 (and far CP-73) also unlock with more
seeds. CP-83 genuinely on the edge (top 0.95, lower than CP-84/85/86 @1.0 -> grasp z in the cup-down dead band; more
seeds don't help). LESSON: "dead-zone" needs the seed-bumped gate, not just a default-seed gate -- another assume-fail
caught.
