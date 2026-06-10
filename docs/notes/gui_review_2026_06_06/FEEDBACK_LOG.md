# GUI Review — Anton's visual feedback vs. headless time-series (2026-06-06)

**Purpose:** Anton watches each scene live in the Isaac Sim GUI (DISPLAY :1) and describes what he sees; this log
pairs his **verbatim** observation with the **time-series measurement** of the same/equivalent run, and notes
whether they MATCH or DIFF. Raw data archived under `./data/` (eyes.json, gate logs, screenshots).

Convention: `[AB]` = Anton's verbatim (Swedish). `[TS]` = time-series measurement. `[DIFF]` = match/mismatch.

---

## CP-83 (2-cube, pedestals) — pick-solved / drop-fails
- **[AB]** "Den går ner för att plocka kuben, men gör det inte rakt uppifrån, utan från en vinkel. Får med sig
  kuben ändå telepatisk. Åker till bin, men lyckas inte droppa, stannar och kuben svävar bredvid gripper
  telepatiskt typ 30sek, sen ser jag nu att den droppat den utanför bin."
- **[TS]** Cup-axis points laterally (~[0.157,0,-0.014], not −Z). Grip latches at cup-cube_d=0.037 (proximity,
  "telepathic" = rigid zero-compliance suction). Cube_2 whipped to z≈1.6 in transit; grip releases at t≈47.2s at
  z≈1.48 (arm stranded at apex, S5 bin-descend fails); cube hangs ~37s then free-falls; lands [0.46,-0.22,0.775]
  OUTSIDE WallY2.
- **[DIFF]** ✅ MATCH on every point (angled pick, telepathic grip, can't drop, ~30s hover, drops outside).

## CP-84 (single-cube passer) — "passes" gate but sloppy
- **[AB]** "Plockar kuben på samma sätt igen, telepatiskt och med en tilt. Planerar om två gånger, och lägger sen
  kuben offset på andra kuben." + on the gripper mount: "med vinkeln på jointen där gripper sitter fast, är det
  verkligen en joint sådär och varför är den i 90grader åt sidan." (screenshot: `data/CP-84_gripper_mount_screenshot.png`)
- **[TS]** PICKED Cube_1 fired twice (t=0, t=46s = the 2 re-plans). Cube_1 final=[0.518,-0.387,**0.825**] = in bin
  XY (in_xy=True) but at z=0.825 = the bin RIM/edge, not the floor (0.75) -> the "offset" placement. Gate counts
  it delivered (in_xy + above + at_rest) but it's a marginal/edge landing.
- **[MOUNT]** Live probe (CP-84 scene): `FlangeMount` = PhysicsFixedJoint (bolts blue short_gripper.usd /Root to
  wrist_3_link); `suction_cup/Suction_Joint` = PhysicsJoint (compliant). suction_cup localZ→world ≈ [0,-0.94,0.34]
  = TILTED ~70° from straight-down. Cause: runtime `_fixup_asset_gripper_joint` rotates /Root about Y by
  `_sg_cup_align_deg` (default **−110°**) to TRY to point the cup down (the cup sits along /Root +X, 0.158m
  offset). The −110° is an EMPIRICAL FUDGE -> the cup ends up tilted, not flat-down -> the angled/telepathic picks
  across ALL UR10 templates. Anton's "why 90° to the side" = this hack. **Candidate root fix:** mount the cup so
  its suction axis points straight down the approach (correct rotation) OR compensate in the cuRobo goal
  orientation -> would fix tilt + telepathic seal cluster-wide. (Anton: analyze later, collecting feedback now.)
- **[DIFF]** ✅ MATCH (telepathic + tilt + 2 re-plans + offset/edge placement). Confirms the "passing" templates
  are gate-passing-but-sloppy, validating the reliability caveat.

## CP-71 (4-cube dispenser) — scene-geometry-blocked + BROKEN SCENE
- **[AB]** "scenen du har laddat nu, där finns ingen kub såvitt jag kan se" (no visible cube).
- **[TS]** Items are ~**4 mm** (0.004×0.004×0.001 m, paper-thin) resting at [-0.4,0.4,**0.806**] = tucked UNDER
  the Dispenser housing (z=1.125–1.175). Invisible AND unreachable. Headless: wrist hits the housing, cup stalls
  0.254m above, 0/4.
- **[DIFF]** ✅ MATCH — and Anton's "no cube" surfaced an EXTRA defect the headless metric missed: the items are
  MIS-SIZED (4mm) on top of being mis-presented. CP-71 is a BROKEN SCENE (template/generation bug: items should be
  ~5cm and presented clear of the hopper), not a robot/planner problem. Confirms 4b = scene fix, not a handler fix.

## CP-73 (4-cube conveyor) — robot delivers Cube_4 (gate-bug)  [pending]
- **[AB]** _(pending)_
- **[TS]** (headless) cubes ride the belt in; robot picks Cube_4 off the moving belt + delivers to bin floor
  [0.514,-0.283,0.785]; cubes 1-3 stay on the belt. Gate false-negatives without the robust-velocity fix.
- **[DIFF]** _(pending)_

---

### Running takeaways from the GUI review
1. The **gripper mount tilt (−110° cup-align hack)** is visible and is the root of the angled/telepathic picks
   cluster-wide — Anton pinpointed it from the screenshot. Strong candidate for THE fix.
2. The **"telepathic" rigid suction** (zero-compliance) is real and visible (cube held beside the cup, not sealed
   flat on top).
3. "Passing" templates (CP-84) deliver to the **bin edge/rim**, not cleanly — the gate's in_xy+above+at_rest is
   lenient; visually the deliveries are marginal. Reinforces that the headless gate over-states delivery quality.
