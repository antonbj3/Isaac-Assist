# UR10 — Faithful-cup review state (2026-06-09)  [all claims MEASURED unless tagged]

## TL;DR — defect #3 (varv) SOLVED on the faithful straight cup for all single-cube passers; global default-flip HELD.
- The close-pick "descend flip / varv" was a **WRAP/SEED bug, NOT a geometry or kinematic limit** — exactly Anton's
  stance. Fixed inside cuRobo's own planner (RAW/unwrapped relive seed, `_ur10_relive_seed_raw`). No planner rewrite.
- All **6 deterministic single-cube passers deliver dead-center, motion-clean** on the faithful STRAIGHT cup
  (CP-69/70/75/79/80/86), via the gated master switch `_ur10_faithful_default` (FAITHFUL=1). CP-84 also passes straight.
- **The global default-flip is HELD (reverted to default-OFF, pick_place.py L5687)** — [MEASURED] it regresses
  multi-cube (CP-83 on the straight cup stays stuck in wait_sensor / picks 0 cubes; the side cup picks+delivers
  Cube_2). Re-flip only after (a) the 8-passer N-of-M passes on FAITHFUL=1 (CP-85 still 0/1, needs confirming) AND
  (b) the multi-cube wait_sensor-stuck is fixed. The straight cup is fully demoable NOW via FAITHFUL=1; production
  default stays byte-identical (no regression shipped).

## ★ ROOT CAUSE [MEASURED] — it was a seed-wrap bug (Anton was right; my earlier "geometry limit" was wrong)
The close-pick "varv till" / fling on the place descend was caused by a **seed-wrap discontinuity**, not kinematics:
- The S5 descend was re-planned live (RELIVE) from the over-bin joints, but the seed was wrapped to (-π, π].
- The arm's PHYSICAL wound-transit config sat at pan≈320°. The wrapped seed produced a descend traj at pan≈-40°
  (same physical angle, different winding). The articulation controller then drove 320° → -40° = a **360° swing**
  — violent enough to fling the cube or take an extra lap.
- **FIX**: seed the relive descend solve RAW (unwrapped, `_ur10_relive_seed_raw`) so the planned traj is continuous
  with the physical config. → descend pan-range collapses to **0°**. Clean. Same cuRobo planner, fixed seeding.

Earlier I (wrongly) read FREEIK_ok=False at one descend goal and concluded "fundamental kinematic limit". The
adversarial check refuted it: CP-69's near-identical descend goal had a clean down-IK (ik_ok=True). The down-config
EXISTS; the planner just needed the right (raw) seed to stay in-branch. Anton's "I don't buy that geometry decides
this — dig in and fix it" was correct.

## Authoritative fresh-Kit motion-clean verify — STRAIGHT cup, master switch (warp-cleared, one Kit per measurement)
Config = `_ur10_faithful_default` (= straight nvidia mount + H7 transit sign-1 + S5 RELIVE + branch-pin + RAW seed + droptip 0.21).

| template | pick | gate | cube_final (dead-center) | descend pan-swing | bin approaches |
|---|---|---|---|---|---|
| CP-69 | far behind (x=-1.0) | ✅ | [0.508, -0.386, 0.785] | 0° | 1 |
| CP-75 | close behind (was HARD FAIL) | ✅ | [0.492, -0.401, 0.785] | 0° (relive) | 1 |
| CP-79 | front (x=0.6) | ✅ | [0.610, -0.396, 0.785] | 0° | 1 |
| CP-86 | behind (x=-0.5) | ✅ | [0.492, -0.400, 0.785] | 0° | 1 |
| CP-70 | close behind, bin y=-0.3 | ✅ | [0.510, -0.289, 0.785] | 0° (relive) | 1 |
| CP-80 | conveyor (x=-0.85) | ✅ | [0.509, -0.386, 0.785] | 0° (relive) | 1 |

Three independent motion-clean proofs converge (Anton's bar: delivery ≠ success, no extra arm movement):
1. **bin_approaches = 1** (grip_log): cup reaches the bin region exactly once → no "varv till".
2. **trajsrc seg=7 relive pan-range = 0**: the executed descend has zero pan swing → no fling.
3. **cube at_rest dead-center, velocity ≈ 0**: clean landing, not a fling that happened to miss.

(CP-84/85 stochastic suction-grip on BOTH cups — separate architectural item, Anton-call. CP-71/73/81/82/83 =
layout/scene/grader gaps, Anton-call, not controller.)

## What got FIXED this session (gated, traceable in ~/.ur10_nightshift/, then DEFAULT-FLIPPED to production)
1. **The "varv till" (defect #3 bin-loop)** — `_ur10_s5_relive`: re-plan the S5 descend LIVE from the over-bin joints
   (the static descend was planned at HOME → home→bin detour).
2. **The close-pick descend FLING/lap** — `_ur10_relive_seed_raw` (the wrap-bug fix above). THE key fix; it is what
   made the close picks (CP-70/75/80) go from flinging/lapping → clean.
3. **CP-70 never-build (straight cup)** — `_ur10_plan_budget_s` default 20 (nvidia) / 8 (side): the straight-cup
   descend is slower to plan; the 8s budget bailed before building. 20s lets it build + deliver.
4. **Cup mount 90°→straight** — `_sg_nvidia_cup` → `_ca_deg=0` (native out-the-end mount, straight down at descend).
5. **All consolidated into one master switch** `_ur10_faithful_default`, now flipped to the production DEFAULT.

## Production-default flip (2026-06-09) — ATTEMPTED then HELD (reverted to default-OFF)
- pick_place.py L5687: `getattr(_bi_fd, "_ur10_faithful_default", False)` — reverted to default-OFF after the flip
  regressed multi-cube (see below). The faithful config stays fully available + verified via the gated FAITHFUL=1 flag.
- Franka no-regression CONFIRMED [MEASURED]: CP-28 fresh-each ×2 = success dead-center (the block is UR10-asset-scoped
  so Franka was byte-identical regardless; verified empirically).
- Snapshots + diff patches in ~/.ur10_nightshift/. NOT committed to Anton's branch (per mandate).

## Why the flip is held — multi-cube regression [MEASURED 2026-06-09]
- CP-83 on the faithful STRAIGHT cup: grip_log shows mode stuck in `wait_sensor` the full 180s, arm never leaves HOME
  (jdeg=[0,-90,90,-90,-90,0]), seg=0/0, no trajectory built, 0 cubes picked → gate success=False.
- CP-83 on the SIDE cup (FAITHFUL=0): the arm executes (seg 0→7), GRIPS Cube_2 at t=12s (status=Closed,
  gripped=['/World/Cube_2'], mind=0.025), delivers it → gate success=True (real, one of two cubes).
- => the faithful default makes multi-cube STRICTLY WORSE (1 cube → 0). CP-83/81/82 are not among the 8 solid passers
  (single-cube), but shipping a default that breaks their partial delivery is a regression → held per §5/§14.6.
- Re-flip gates: (a) 8-passer N-of-M on FAITHFUL=1 (CP-85 needs confirming, 0/1 so far); (b) multi-cube wait_sensor-
  stuck root fixed (read-only §12 hypothesis workflow wofnl5zwz launched for it).

## Open (Anton's call — not controller bugs)
- CP-84/85: stochastic suction-grip (the cup latches inconsistently) — architectural, present on both cups.
- CP-71/73/81/82/83: multi-cube/layout/scene/grader gaps (template JSON layout = Anton's decision). NOTE: CP-83's
  straight-cup wait_sensor-stuck is a NEW controller-side finding under investigation (may be fixable on the straight cup).
