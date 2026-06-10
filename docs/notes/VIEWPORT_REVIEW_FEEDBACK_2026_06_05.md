# Viewport review — Anton's live observations (2026-06-05)
Mode: GUI viewport, Anton watches each template play live; I capture TS in parallel. COLLECT ALL feedback first,
then fix everything. Anton's eyes are ground truth; my TS corroborates.

## CP-84 (UR10 stack on BaseCube) — FAIL
- **TWO GRIPPERS in the scene**: the BLUE asset gripper (short_gripper.usd) AND the longer GREY procedural cone.
  The grey cone "bara flyger runt runt axeln" (just spins/flies around the axis). ← gripper DUPLICATION bug +
  cone instability. (My auto-repair injected a gripper for CP-84; a blue asset gripper ALSO present — why? CP-73,
  which has a NATIVE surface_gripper, shows NO blue. So the blue appears specifically on the AUTO-REPAIRED build —
  investigate during fix.)
- Arm "ballar ur och fastnar i golvet" (goes haywire + gets stuck in the floor), NO pick. (My TS: Cube_1 never
  moves from [-0.5,0.4,0.97]; cone to wrong side ~[0.84,0.65,0.49] = low, in/near floor. Matches.)

## CP-73 (UR10 Cortex/curobo + moving belt, 4 cubes) — partial?
- Arm takes SMALL STEPS around, then RE-PLANS a few times, then DROPS the cube in the bin WITH ELONGATION behavior
  (the suction tool stretches = kinematic-follower lag). NO blue gripper (grey cone only — confirmed: scene has
  only /World/UR10_SGCone, no _ShortGripper).
- IMPORTANT DISCREPANCY: Anton sees it DELIVER (with ugly elongation); my gate measured FAIL (cube flung 23.7 m/s).
  → CP-73 may actually deliver (stochastic / the gate caught a different run) — the real issue is the ELONGATION,
  not a hard fail. Re-measure + read TS.

## CP-83 — "helt katastrof" (Anton, full read)
- **Can't plan** (planning failures — matches pf count + re-plans).
- **The MIDDLE AXIS/joint pushes directly onto one of the cubes** — the arm's mid-link COLLIDES with / shoves a cube
  (NOT a grip; explains Cube_2 getting nudged to [-0.49,-0.11,0.77] — the elbow pushed it). = planner routes the arm
  body THROUGH/onto a cube.
- **Drives around, then stops ABOVE the bin** (ends over the bin, EMPTY — Cube_1 graded never touched, Cube_2 not delivered).
- **The grey cone (NOT blue) just SPINS around** = cone/wrist instability (matches my joint TS: wrist_3 wound to -26.97 rad = endless spin).
- Grippers here: grey cone only, no blue (native surface_gripper → no asset gripper).

## PATTERNS EMERGING (across CP-84/73/83)
1. **GREY CONE SPINS** (CP-84 + CP-83) — recurring cone/wrist instability. Likely a CORE root.
2. **Planning failures** — can't plan / re-plans / routes the arm body INTO cubes (CP-83 mid-joint pushes a cube).
3. **BLUE-gripper duplication** — ONLY on CP-84 (auto-repaired, no native gripper). My auto-repair likely creates an
   asset gripper on top of the procedural cone. Bug, auto-repair-specific.
4. **Elongation** (CP-73) — kinematic-follower lag stretches the tool on the carry/drop.
