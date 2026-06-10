# UR10 GUI Review — Anton live feedback 2026-06-09

Setup: Isaac Sim GUI on robot-lab display, templates cycled in one live Kit
(`~/.ur10_nightshift/open_template_live.sh <TPL>`). Anton watches the pick execute, gives feedback.

## CP-83 (2-cube, pedestals behind robot)
Layout: UR10@[0,0,0.75]; Cube_1@[-0.5,0.4,0.925] (Pedestal_1); Cube_2 source [-0.5,0.0,0.925] (Pedestal_2); Bin@[0.5,-0.4].
- Picks 1st cube (slightly OFF-CENTER), delivers OK.
- Then **drives one arm axis INTO the other cube's platform** (upper_arm sweeps through Pedestal_2). "failure planering — seen before, thought fixed."
- ROOT (confirmed in code L5113-5118): `_ur10_multicube_obs_carry_only` scopes collision obstacles to CARRY phase (seg≥3) ONLY → during the pick APPROACH (seg 0-2) the pedestals are removed from the cuRobo world → arm sweeps through Pedestal_2. Trade-off: obstacles ON during approach → 586 plan-fails/stall; OFF → collision. This is why reach_validate said Cube_1 0/3 UNREACHABLE: no collision-free cup-down approach exists past the neighbour pedestal. ROOT IS SCENE-GEOMETRY (two tall pedestals 0.4m apart behind the robot).
- NOTE: CP-83's settle_state authors Cube_2 INTO the bin (`xformOp:translate=(0.488,-0.395,0.785)`); the pick task starts it at source [-0.5,0.0]. settle_state-in-bin appears CP-83-specific (CP-81 cubes settled on pedestals).

## CP-81 (2-cube, both behind-left +y)
Layout: Cube_1@[-0.5,0.55,0.975] (Pedestal_1@0.875); Cube_2@[-0.5,0.25,0.975] (Pedestal_2@0.875); Bin@[0.5,-0.4].
1. **Off-center pick on BOTH cubes** (cup not centered on cube). [controller — cup-cube alignment]
2. **Lag/stall when releasing in bin** — sequence pauses a while before resuming. [controller — release/resume stall]
3. **Both pedestals FLOAT in the air** (no ground support). [SCENE-BUILD]
4. **One would fall to the floor if given physics** (pedestals are kinematic). [SCENE-BUILD]

## Cross-cutting themes (likely affect many UR10 templates)
- SCENE-BUILD: pedestals/platforms placed FLOATING (kinematic, no ground contact). Systemic — check the canonical builder that spawns pedestals.
- CONTROLLER: off-center pick (cup-cube xy alignment) recurring.
- CONTROLLER: release-in-bin lag / sequence resume stall.
- PLANNING: arm sweeps through neighbour pedestal on the far-cube approach (carry_only obstacle-scoping trade-off).

## CP-71 (4-item "dispenser", high + behind-left)
Layout: Item_1[-0.45,0.35,1.1] Item_2[-0.35,0.35,1.045] Item_3[-0.45,0.45,1.1] Item_4[-0.35,0.45,1.045]; OutBin[0.5,-0.3].
1. **Items FLOAT / spawn above ground, fall onto the belt/platform** — no real dispenser visible despite `/World/Dispenser/Item_*` paths. [SCENE-BUILD — the "Dispenser" is not modeled, just 4 falling cubes]
2. **~30s lag at sim start, then Isaac Sim HUNG** (full freeze, main thread blocked). [CONTROLLER/PLANNER — CP-71 hangs the Kit; likely cuRobo plan-hang on the tight 4-item grid high up]
3. Delivers 0/4 (today).
=> CP-71 must be RESTARTED (hung Kit unrecoverable via RPC). The "dispenser" is fiction — scene-build needs a real dispenser OR re-spec as a falling-cube feed.

## CP-73 (4-cube conveyor, cubes start far, belt feeds them in)
Layout: Cube_1[-1.6,0.4] Cube_2[-1.4,0.4] Cube_3[-1.2,0.4] Cube_4[-1.0,0.4] (z=0.835); Bin[0.5,-0.3]. Cubes 1.08–1.65m (beyond reach until belt moves them).
1. **Lag after dropping the 1st cube** (release/resume stall). [CONTROLLER — recurring]
2. **Off-center pick.** [CONTROLLER — recurring]
3. **2nd cube: PIROUETTE/SPIRAL before release** (360 wrist-spin at bin = defect #3). [CONTROLLER]
4. **1st cube: a slightly unnecessary movement.** [CONTROLLER — motion quality]
5. **3rd cube: drives the arm axis DOWN INTO the conveyor and STALLS there** (= CP-83 pedestal-collision family). [PLANNING/COLLISION]

## DEFECT CATALOG (consistent across CP-81/83/73 — UR10 multi-object)
- **Arm-into-structure collision + stall** on the far/edge cube (CP-83 pedestal, CP-73 conveyor). Root: approach-phase obstacle scoping (carry_only removes supports from the approach world) OR support not in collision world.
- **Off-center pick** (cup-cube xy alignment) — EVERY template.
- **Release lag / sequence resume stall** at the bin (CP-81, CP-73).
- **360 wrist-spin / pirouette-spiral at release** (CP-73 cube 2; defect #3, thought fixed).
- **Unnecessary/extra arm movements** (motion quality).
- **SCENE-BUILD: floating supports** (pedestals/dispenser float; CP-71 dispenser is fiction, cubes spawn in air and fall).

## CP-70 (baseline single-cube passer)
Layout: Cube_1[-0.5,0.4,0.835] (SAME xy as CP-83's stuck Cube_1, but NO neighbour pedestal, z 0.835 not 0.925); Bin[0.5,-0.3].
- "Bra förutom" — delivers cleanly, NO collision (confirms [-0.5,0.4] is reachable when alone → CP-83's failure is the neighbour Pedestal_2, not the position).
- **Off-center pick** (even here). [CONTROLLER — UNIVERSAL]
- **Spins on the cube + adjusts a bit before finally releasing.** [CONTROLLER — UNIVERSAL, release-time spin/adjust = defect #3 not fully closed]
- ANTON REGRESSION CONCERN: "weren't all the extra movements gone, or re-introduced?" — recalls a cleaner state. MUST verify current motion vs documented clean (H7/cupframe/defect-#3) state. Could be faithful-master-switch turning on relive/branch_pin/jointspace re-introducing adjustments.

## CP-82 (routing → 2 colour bins; same 2-cube layout as CP-81)
Layout: Cube_1[-0.5,0.55,0.975] Cube_2[-0.5,0.25,0.975]; Bin_red[0.5,-0.3] Bin_blue[0.5,-0.55].
- 1st cube delivers well.
- **2nd cube: collides an arm axis with the OTHER bin (Bin_blue), but still delivers.** [PLANNING — the place/transit collision world omits the 2nd bin]
- **Off-center pick.** [CONTROLLER — UNIVERSAL]
- "planeringsproblem."

## CONSOLIDATED — universal vs scene-specific
UNIVERSAL controller defects (seen even on the CP-70 passer):
- (U1) Off-center pick (cup-cube xy alignment) — EVERY template.
- (U2) Release-time spin + micro-adjust before drop (defect #3) — even CP-70.
SCENE/MULTI-OBJECT planning defects:
- (P1) Arm sweeps into the SUPPORT/NEIGHBOUR structure on the far cube — Pedestal (CP-83), Conveyor (CP-73), other Bin (CP-82). Collision world omits these during approach/place (carry_only scoping + bins not added).
- (P2) Release lag / resume stall at bin (CP-81, CP-73).
- (P3) CP-71 hangs the Kit (tight 4-item high grid).
SCENE-BUILD defects:
- (S1) Floating supports — pedestals/dispenser float, would fall under physics (CP-81, CP-83, CP-71).
- (S2) CP-71 "Dispenser" is fiction — 4 cubes spawn in air + fall; no modeled dispenser.
ANTON's REGRESSION QUESTION (open): were the extra movements eliminated earlier and re-introduced? → investigate next.
