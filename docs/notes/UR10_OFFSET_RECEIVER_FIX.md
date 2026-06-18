# #2 Robot-diversity multiplier: fix UR10 cuRobo under origin_offset

**Mandate (Anton 2026-06-18):** 24h deep effort. The multiplier = breadth × robot-diversity. The
unblock: make a UR10 RECEIVER work at a non-zero `origin_offset` so the cross-Kit chain
(chain_xkit_gate) handles ARBITRARY offsets → no hand-designed zero-offset CP-CHAIN-* pairs →
auto-handoff (#29) generalizes → robot-diversity chains work for any canonical block.

**Method (Anton):** diagnostik-först — reach_validate / scene_eyes / validators, NOT static guesses
(static < Kit, the 3×-wrong lesson). Develop the tools when the benefit shows. Build → adversarial
audit → fix. UR10 = restart-per-run (process-global PhysX corruption), NEVER cloud.

## Known diagnosis (prior, to RE-VERIFY on fresh Kit — phantom-rootcause lesson)
- UR10 receiver built at instance_root+origin_offset GENUINELY FAILS: arm stuck extended
  ee≈[1.683,-0.495,0.811], cube 0-jiggle, delivered=FALSE, REPRODUCES; plan_fails 617/633.
- GOAL is correct under offset (point_world tracks offset cube; _usd_pos offset-correct).
- So failure is PLAN/EXECUTION, not goal-computation. Precise cause OPEN.
- Workaround ships: zero-offset co-design (CP-CHAIN-UR10-RECV-NATIVE) — GOLD stands.

## Static code-map (Explore, cont.257) — TREAT AS HYPOTHESES ONLY
- _usd_pos/_usd_quat read from live ComputeLocalToWorldTransform (offset-correct) — both robots.
- _world_to_base, goal, obstacles all transformed to BASE frame via _usd_pos — both robots.
- cuRobo MotionPlanner built with canonical URDF (base at base-frame origin = NORMAL/correct).
- ⚠️ agent's "planner assumes origin → wrong" suspect is QUESTIONABLE: base-frame planning is
  offset-invariant; would break Franka too. Likely a misdiagnosis.
- Real candidates to test: (a) obstacle paths HARDCODED /World/Table etc. — miss rerooted
  /World/relayK/Table (but UR10 FILTERS support surfaces, so table-miss may not matter);
  (b) _ur10_multicube_obs auto-add under reroot; (c) start joints (wound) under the chain;
  (d) something receiver-specific (source_override + relayed cube).

## KEY question to resolve FIRST (empirical)
Is the BASE-frame goal identical native vs offset? In chain_xkit_gate the whole scene offsets
together, so cube-relative-to-base should be IDENTICAL → plan SHOULD be offset-invariant. If it
is and plan still fails → NOT the transform; it's obstacle/start/execution. Decisive experiment:
CP-73 (canonical UR10) built NATIVE vs at OFFSET, instrument plan goals + arm EE + planfail log.

## PROGRESS LOG
- cont.257 (2026-06-18): started. Grounded diagnosis + static map (hypotheses). Added reach_validate
  `--offset X,Y,Z` (probe reachability under composition offset).
- cont.258 (2026-06-18): ★ DECISIVE — offset does NOT break IK reach. reach_validate
  CP-CHAIN-UR10-RECV-NATIVE: NATIVE pick REACHABLE (top@1.000=3/3) AND OFFSET [0.5,-0.8,0] pick
  REACHABLE (/World/probe/Cube_1, top@1.000=3/3). Confirms base-frame invariance: the cube-relative-
  to-base is identical native vs offset, so single-IK grasp reach survives offset. REFUTES the static
  map's "planner assumes origin" suspect. => the offset failure is DEEPER: multi-segment plan (a
  specific approach/descend/lift/place segment res_None's) OR execution OR surface-grip — NOT basic IK.
  NEXT: full UR10 controller @offset via scene_eyes --compose (native control vs offset) -> read RAW
  per-tick arm trajectory + /tmp/curobo_planfail.log (WHICH segment fails) + grip.
- cont.259 (2026-06-18): ★★ THE PREMISE IS REFUTED. Fresh-Kit scene_eyes --compose
  CP-CHAIN-UR10-RECV-NATIVE @offset[0.5,-0.8,0] vs @native: the OFFSET UR10 receiver GRIPS + CARRIES
  + DELIVERS. RAW per-tick (xy-verified, not summary): grips Cube_1 @t=6.7, carries to the offset
  Tray, releases @t=32.6, FINAL Cube_1=[1.51,-1.99,0.775] = ON the offset Tray (~[1.5,-2.0,0.775],
  xy within ~1cm, z at tray top). max plan_fails=0. Native identical (faster). So the UR10 cuRobo
  controller HANDLES origin_offset CORRECTLY — the memory's "offset receiver fails, arm stuck,
  plan_fails 617/633" was a PHANTOM (degraded Kit) or a chain-specific confound, NOT the offset.
  The hand-designed zero-offset workaround was built on a FALSE premise (verify-before-dismissing /
  phantom-rootcause lesson in action). ⚠️ NOT over-claiming #2 solved: scene_eyes builds the
  template's OWN cube; the CHAIN additionally does source_override to a RELAYED cube at a sibling
  /World/relayK root. REMAINING (the real end-to-end): does chain_xkit_gate deliver a Franka->UR10
  chain with a NON-zero UR10 receiver offset (source_override to relayed cube)? If yes -> robot-
  diversity chains work for arbitrary offsets, no hand-designed pairs, #2 largely solved. NEXT: read
  chain_xkit_gate offset derivation + run the chain with a forced non-zero UR10 offset.
- cont.260 (2026-06-18): chain_xkit_gate structure mapped. run_stage_k has 3 paths: (1) off<0.05 ->
  snap to 0 -> NATIVE own-cube; (2) off>=0.05 + has_sensor -> reroot+offset + source_override to relay
  cube at sibling /World/relayK (LITERAL relay, proven GOLD for FRANKA CP-CHAIN-FLAT); (3) off>=0.05 +
  NO sensor -> reroot+offset + OWN cube, NO source_override (LOCATION-handoff). Both UR10 chain
  templates (CP-CHAIN-UR10-SRC, CP-CHAIN-UR10-RECV-NATIVE) are source_paths (no sensor) -> path 3.
  So the chain ALREADY routes large-offset UR10 receivers through path 3 (own-cube) = the mechanism
  scene_eyes PROVED delivers. The snap-to-native (139-140) + the "UR10 must be co-designed zero-offset"
  comment are STALE: they cite cont.234's path-3 failure, which was an EARLIER codebase (offset/reroot
  handling fixed since). REMAINING: airtight end-to-end -- force a LARGE offset through the real chain
  harness (run_stage_k path 3 + _play_and_measure) and confirm the UR10 receiver delivers. Adding
  CHAIN_FORCE_OFF env override to chain_xkit_gate for this (clean test hook). If it delivers -> remove
  the stale snap for source_paths receivers + correct the memory + #2 substantially solved.
- cont.261 (2026-06-18): ★★ ROOT CAUSE NAILED + FIXED. The chain harness `_play_and_measure` did a BARE
  play (no STOP->PLAY) — a THIRD harness with the freeze-class bug (after compose_and_verify + compose_gate,
  cont.256). For an OFFSET UR10 receiver the bare play left the controller un-re-acquired -> it targeted a
  WRONG goal (~[-0.257,-1.058], NOT the cube at [0.5,-1.2]) -> 3950 res_None plan-fails. The build was
  IDENTICAL to scene_eyes (dump: Cube_1=[0.5,-1.2,0.975], UR10=[1.0,-1.6], Tray=[1.5,-2.0]); the ONLY
  difference was the play-start (scene_eyes STOP->PLAYs + delivered). FIX: STOP->PLAY re-acquire at the top
  of _play_and_measure. VERIFIED: run_stage_k path-3 @forced off=[0.5,-0.8] -> delivered=1/1, Cube_1=
  [1.51,-1.99,0.775] (on the offset Tray), 0 planfails. So the "UR10 mishandles offset" belief was a
  MEASUREMENT ARTIFACT of the bare-play; the snap-to-zero + co-designed-zero-offset requirement compensated
  for THAT, not a UR10 limitation. => robot-diversity chains generalize to ARBITRARY-offset UR10 receivers
  via path-3, NO hand-designed zero-offset pairs needed. Commit pending no-regression on native GOLD chain.
