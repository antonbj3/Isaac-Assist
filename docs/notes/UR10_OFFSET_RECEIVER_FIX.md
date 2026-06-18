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
