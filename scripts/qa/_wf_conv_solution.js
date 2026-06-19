export const meta = {
  name: 'conveyor-pickcell-solution',
  description: 'Solve the real-conveyor pick CELL (#52): independent grounded design approaches + a deep high-z proximity-sensor root cause, synthesized into one concrete buildable plan',
  phases: [{ title: 'Explore', detail: 'independent approaches + root cause' }, { title: 'Synthesize', detail: 'pick the most robust concrete plan' }],
}

const REPO = '/home/anton/projects/Omniverse_Nemotron_Ext'
const CTX = [
  'Repo: ' + REPO + ' (Isaac Sim canonical-composition system). cd there first. Read + bash (grep/python3/pxr) access.',
  'PROBLEM (#52): a real conveyor pick CELL — a Franka picks a cube presented on a real Isaac ConveyorBelt_A09 asset and drops it in a bin. PROVEN already: CP-CONV-01 (belt MOTION via the 3-API surface-velocity retrofit on /World/Belt) + CP-CONV-01b (a FEEDER: an end-stop holds the riding cube at a fixed pick-zone) are GENUINE. The PICK is what fails.',
  'ROOT CAUSE (established Kit-free, do not re-litigate): with a PEDESTAL Franka (base z=1.4) reaching the belt at its native ride-height ~1.781m, reach_validate says the pick-zone IS REACHABLE (3/3 IK), but the sensor-gated pick never fires (plan_calls=0, arm never moves). A controlled diff (CP-CONV-02-GEN, a GENERATED belt at the same high-z) fails IDENTICALLY -> the breaker is the HIGH-Z (~1.8m) sensor-gated pick mechanism, NOT the belt asset. In v6 the cube sits INSIDE the proximity-sensor box for 400/400 rows at high-z yet isaac_sensor:triggered never goes True. A POSITIVE CONTROL (CP-YCB-01C, the same sensor+belt+controller at LOW z ~0.85) PICKS fine (plan_calls=8).',
  'KEY FILES: workspace/templates/CP-CONV-01.json, CP-CONV-01b.json, CP-CONV-02.json (PARTIAL v6), CP-CONV-02-GEN.json; the pick controller service/isaac_assist_service/chat/tools/handlers/pick_place.py (sensor gate ~line 1900 reads isaac_sensor:triggered; controller IS base-aware, handles "elevated base" ~line 2679, set_robot_base_pose); the proximity sensor service/isaac_assist_service/chat/tools/handlers/sensors.py (add_proximity_sensor ~339-452: invisible Cube + PhysxTriggerAPI + an overlap_box step-callback that sets isaac_sensor:triggered when a /World/ rigid-body overlaps); the surface-velocity retrofit robot.py ~1880 (3-API: Collision + kinematic RigidBody + PhysxSurfaceVelocityAPI). All 31 ConveyorBelt_A* belts are >=0.9m WIDE (narrowest 0.9m), ride-z ~1.781m; a floor Franka (reach ~0.85m) cannot reach a belt CENTRE from beside it. Saved RAW: /home/anton/.isaac_qa/run/eyes/CP-CONV-*/eyes.json. real_asset_spawn.conveyor_recipe(usd) gives belt geometry.',
  'Produce a CONCRETE, grounded plan: cite the exact files/lines, the exact template DSL changes (create_scene_baseline/create_prim/add_reference/apply_api_schema/set_attribute/robot_wizard/create_bin/add_proximity_sensor/setup_pick_place_controller), the reach_validate plan, and the scene_eyes verification + the expected RAW signal. Do NOT hand-wave. Ground every claim by reading the actual code.',
].join('\n')

const APPROACHES = [
  { key: 'rootcause-highz-sensor', prompt: [CTX, '',
    'YOUR TASK: deeply root-cause WHY the proximity-sensor overlap mechanism does not fire at z~1.8 with the object correctly inside the box, when it fires fine at z~0.85. Read sensors.py add_proximity_sensor in full (the overlap_box query via get_physx_scene_query_interface, PhysxTriggerAPI, the step-callback, the watched_path_pattern filter default "/World/", and how isaac_sensor:triggered is set). Then read pick_place.py around the sensor gate (~1900) AND the controller state machine / base-pose pinning (~1997-2767) to determine whether the failure is (A) the overlap_box physics query genuinely not detecting at high z, or (B) the controller never REACHING the sensor-poll phase when the base is a pedestal at z=1.4 (e.g. an init/IK/home-pose issue that stalls before polling), or (C) the sensor prim transform/box ending up somewhere other than authored at high z. Decide which, with evidence from the code. Propose the MINIMAL fix for the true cause. Also propose the cheapest DECISIVE Kit probe (one run) to confirm: e.g. a step-callback that prints isaac_sensor:triggered + the controller phase each step at high z — give the exact probe code to inject into a template.'].join('\n') },

  { key: 'lowered-conveyor', prompt: [CTX, '',
    'YOUR TASK: design the LOWERED-CONVEYOR cell concretely (put everything in the PROVEN low-z regime). Translate the real A09 conveyor down by ~0.98m so the belt surface sits at the proven ~0.8m pick height; a FLOOR Franka (base z=0, the CP-YCB-01C / CP-CHAIN-FLAT regime) picks. RESOLVE the reach-vs-sensor tension: the belt is 0.9m wide and the Franka cannot reach its centre from beside it (>0.85m). Options to evaluate concretely with reach_validate geometry: position the Franka so the END-STOP pick-zone is at the belt NEAR edge within reach; or angle/translate the conveyor so the pick-zone sits ~0.45m from the Franka base; or use a guide so the cube settles at the near edge. Account for: the lowered conveyor frame going through the floor (cosmetic — acceptable?), the A09_02 element (was at z=2.31 -> ~1.33 after lowering — is it near the pick path? pxr-inspect its xy), and the conveyor as a cuRobo obstacle (a box proxy vs the real mesh — note cont.319w v4 showed dropping the real mesh from planning_obstacles did not break anything). Output the EXACT template DSL (all-literal paths like CP-CONV-01b) + the reach_validate target + the scene_eyes expected RAW (cube rides + Franka CONVERGED+GRIPPED + delivered to bin).'].join('\n') },

  { key: 'sensorless-direct-pick', prompt: [CTX, '',
    'YOUR TASK: design a pick that AVOIDS the proximity sensor entirely (since the high-z sensor is the breaker, sidestep it and keep the conveyor at NATIVE height with a pedestal Franka). The cube is held by the end-stop at a KNOWN fixed pick-zone position. Investigate whether setup_pick_place_controller (pick_place.py) supports a NO-sensor / static / direct pick at a known target (grep for how sensor_path=None or a direct-target mode is handled; check the proven static pick CP-CHAIN-FLAT and CP-01 — do they actually use a sensor, or a direct pick?). If a sensor-less/direct pick mode exists, design CP-CONV-02 with it: pedestal Franka (base z=1.4, reach_validate-proven) + the cube at the fixed pick-zone + NO add_proximity_sensor (or sensor_path omitted) + setup_pick_place_controller targeting the cube directly. If no direct mode exists, design the minimal handler change to add one (a direct-target pick that skips the sensor gate). Output the exact DSL + the handler change if needed + the scene_eyes expected RAW.'].join('\n') },

  { key: 'alt-sensor-fix-or-trigger', prompt: [CTX, '',
    'YOUR TASK: design a fix that makes the SENSOR work at high z OR a clever trigger workaround, keeping native height + pedestal Franka. Read sensors.py add_proximity_sensor fully. Consider: (1) is the overlap_box query bounded/relative such that a different sensor size, position, or the surfaceVelocityLocalSpace kinematic belt interferes at high z? (2) the watched_path_pattern filter — the belt is a kinematic /World/ rigid-body that may overlap the sensor box and become last_triggered_path instead of the cube; does the controller require last_triggered_path to be a SOURCE path? trace it. (3) could raising the sensor box so it excludes the belt (z above 1.781) but still covers the cube, or pointing watched_path_pattern at the specific cube path, fix it? (4) a manual trigger: a tiny step-callback in the template that sets isaac_sensor:triggered=True once the cube is settled at the pick-zone (bypassing overlap_box) — is that sound? Output the most robust option as exact DSL / handler-change + scene_eyes expected RAW. Be honest if the sensor genuinely cannot work at high z.'].join('\n') },
]

const PLAN_SCHEMA = {
  type: 'object',
  required: ['approach', 'feasible', 'confidence', 'plan'],
  properties: {
    approach: { type: 'string' },
    feasible: { type: 'boolean', description: 'is this approach genuinely viable based on the actual code you read?' },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
    root_cause_finding: { type: 'string', description: 'for the rootcause approach: A/B/C and why, with code evidence' },
    plan: { type: 'string', description: 'concrete step-by-step: exact DSL changes, file:line references, handler changes if any' },
    dsl_or_diff: { type: 'string', description: 'the exact template code or handler diff to apply' },
    verification: { type: 'string', description: 'reach_validate target + scene_eyes expected RAW signal' },
    risks: { type: 'string' },
    grounded_in: { type: 'string', description: 'the specific files/lines you actually read to ground this' },
  },
}

const SYNTH_SCHEMA = {
  type: 'object',
  required: ['recommended', 'rationale', 'build_steps'],
  properties: {
    recommended: { type: 'string', description: 'which approach (or hybrid) to build first' },
    rationale: { type: 'string', description: 'why, weighing the root-cause finding + each approach confidence/risk' },
    build_steps: { type: 'string', description: 'the concrete ordered steps to build + verify the chosen solution, with exact DSL/diffs and the reach_validate + scene_eyes gates' },
    fallback: { type: 'string', description: 'the next approach if the first fails, and the decisive signal that would trigger the switch' },
    open_questions: { type: 'string' },
  },
}

log('Exploring ' + APPROACHES.length + ' independent solution approaches for the real-conveyor pick cell')

const explored = await parallel(APPROACHES.map(function (a) {
  return function () {
    return agent(a.prompt, { label: 'explore:' + a.key, phase: 'Explore', schema: PLAN_SCHEMA })
      .then(function (p) { return { key: a.key, plan: p } })
      .catch(function () { return null })
  }
}))

const valid = explored.filter(Boolean)
log('explored ' + valid.length + '/' + APPROACHES.length + ' approaches; synthesizing')

const synthesis = await agent(
  [CTX, '',
    'You are the SYNTHESIS judge. Below are independent grounded solution approaches for the real-conveyor pick cell, each with feasibility/confidence/plan. Pick the SINGLE most robust approach (or a hybrid) to BUILD FIRST, grounded in the root-cause finding. Prefer the lowest-risk path that actually completes the cell (a robot picks a cube off the real conveyor into a bin, scene_eyes-verified CONVERGED+GRIPPED + delivered). Give concrete ordered build steps with the exact DSL/diffs, the reach_validate + scene_eyes gates, and a fallback with its trigger signal.',
    'APPROACHES: ' + JSON.stringify(valid.map(function (v) { return v.plan }), null, 1)].join('\n'),
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA }
)

return { approaches: valid.map(function (v) { return v.plan }), synthesis: synthesis }
