# Self-review for external feedback — UR10 cup-orientation + CP-81 (2026-06-06)

> Written by the working agent for a feedback panel. Honest account of what I did, how, results, goal.

## The overarching goal
Reach a **100% UR10 function gate** in Isaac Sim 5.1: a UR10 with a suction gripper must reliably pick cube(s)
and deliver them into a target bin, planned by **cuRobo**. ~13 canonical templates (CP-69…CP-86). Production
gate is "ANY cube delivered + primary upright". The cluster sits at ~12/13 on fresh Kits.

## Anton's PARAMOUNT rule (the standard I'm held to)
**CORRECT OBSERVATION FIRST.** A fix is worthless without a correct diagnosis from the scene. Use CONTINUOUS-PLAY
time series (joints, EE/cup pose, grip, contacts, cuRobo plan capture). NEVER chunked/stepped probes (they distort
wall-clock controllers). Gated fixes only (default-off flags, A/B), preserve the passing templates, verify on a
FRESH Kit, review the time series every measurement. Fixes must GENERALIZE (handler/build layer, not per-template
JSON edits).

## Thread A — CP-81 stochastic fling diagnosis (earlier today)
CP-81 (2-cube on pedestals) intermittently flings Cube_2 out of the bin instead of delivering. I diagnosed it,
and I **corrected my own root-cause FOUR times**:
1. "pedestal is a cuRobo obstacle blocking the path" — WRONG (Anton's GUI intuition: posts are clear of the path).
2. "raw add_reference wound-spawn" — WRONG (the auto-repair DOES convert it to robot_wizard(home); confirmed via
   log capture + executed-call inspection).
3. "cuRobo wrist multi-turn on the cross-body transit flings it" — partially right but UPSTREAM, not the direct cause.
4. ACTUAL (via scene_eyes PLAN EVENTS): the Cube_2 drop-APPROACH plan fails repeatedly at the bin; the controller
   abandons it and force-releases (`_hold_cap` 4s timeout) WHILE the arm is whipping at 3.14 rad/s → flung.
Tools used: live RPC scene queries (prim geometry), `scene_eyes.py` 180s continuous-play time series
(joints/plans/contacts/grip), replicated the auto-repair detection in standalone AST, `execute_template_canonical`
with logging capture. KEY METHOD WIN: I suspected the `[-1.688]` "out-of-reach garbage goal" finding was
contaminated by a SHARED append-log (CP-71 noise), so I CLEARED the log and re-ran CP-81 alone → confirmed it was
CP-71 noise, not CP-81. (Avoided acting on cross-run-contaminated data.)
Outcome: CP-81 majority-passes fresh (gate ~met); the deterministic fling fix touches shared place/release logic
(risky) → I held it.

## Thread B — Cup-orientation NVIDIA-match (current, the one I want feedback on)
Anton (GUI review) flagged the gripper sits ~90° to the wrist axis (cup out the SIDE), unlike NVIDIA. Goal: make
our cup match NVIDIA's (cup out the END, along the flange normal).
Methodology + steps:
1. Loaded the NVIDIA facit `ur10_bin_stacking_short_suction.usd` in the GUI. Found it's a STATIC asset scene (no
   embedded play). Extracted NVIDIA's mount: suction_cup is a clean CHILD of ee_link, local_pos [0.1585,0,0],
   cup-Z along ee_link +X.
2. Measured OUR build mount (clean static): cup-Z = ee_link +X = IDENTICAL to NVIDIA at build. So the build is
   already correct; the runtime -90° in `_fixup_asset_gripper_joint` rotates the cup out-the-side (the 90° Anton sees).
3. Tried to remeasure the RUNTIME cup orientation (after the -90) — got CONTAMINATED data (ee_link USD is a frozen
   virtual frame + the arm was mid-motion). I flagged it as contaminated and didn't trust it. (good)
4. **Part 1** (gated flag `_sg_nvidia_cup`, `_ca_deg=0` → cup stays at ee_link +X, no -90; closed-loop still on):
   CP-69/70/84/85/83 PASS exact, but CP-81/82 REGRESS to no-pick (closed-loop can't bridge the 90° cup-vs-descend
   gap on the hard back-left reach).
5. **Part 2** (repoint cuRobo's descend so the cup axis points down). I implemented it FIRST by rotating the
   global `_world_down` quat ±90 about Y → BOTH signs broke CP-70. Realized that's a WORLD-frame rotation (rotates
   the whole target frame), wrong mechanism. Reverted.
6. Got a CLEAN cup-vs-frame measurement at static home: cup = tool0 +X (tool0≈ee_link). Re-implemented Part 2 as a
   TOOL-LOCAL post-multiply `quat_base ⊗ q_Y(±90)` at the goal. -90 broke CP-70; +90 in flight.
Net so far: 4 sign/frame variants of the descend-repoint, none yet make CP-70 deliver. Production untouched (flag
default OFF, -90 side-mount, 12/13). Current hypothesis: the cup-frame CLOSED-LOOP (gated on a DIFFERENT flag,
`_ur10_cupframe_down`, still ON) is fighting the descend-repoint; next isolation = test planner-native (nvidia_cup
ON + closed-loop OFF). Stop criterion set: if that + +90-local fail, revert Part 2 and conclude the clean NVIDIA
out-the-end needs a proper cuRobo TOOL-FRAME redefinition (config layer), not handler sign-flipping.

## Honest self-assessment of weaknesses (for the panel to react to)
- I've **flip-flopped on frame reasoning repeatedly** (pedestal→wound→multi-turn→release; world-quat→local-quat;
  multiple sign guesses). My in-head quaternion/axis reasoning is unreliable.
- A lot of **trial-and-error sign-flipping** (each costing a ~3-min Kit run + context), instead of deriving/measuring
  the correct transform once.
- **Large context/time spend** on one cosmetic-ish issue (the 90° cup may be cosmetic — CP-81's fling root was NOT
  proven to be the cup lever-arm).
- Possible **over-engineering vs the gate goal**: I'm deep in a cup-orientation refactor when the gate is ~met and
  the cup may not affect function.
- Coupled flags (`_sg_nvidia_cup`, `_ur10_cupframe_down`, closed-loop) create confounded experiments.

## Questions for the panel
1. Where did my debugging methodology go wrong, and what would a more disciplined approach look like (esp. the
   frame-math: how to get the cuRobo tool-frame / cup transform RIGHT once instead of guessing signs)?
2. Was this the right thing to be working on at all (cup orientation vs the gate / CP-81 fling)? When should I have
   stopped or escalated?
3. Concrete ideas to improve: tooling, verification design, how to avoid contaminated measurements, how to decouple
   confounded flags, how to bound trial-and-error.
