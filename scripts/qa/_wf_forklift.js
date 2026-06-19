export const meta = {
  name: 'forklift-fork-lift-build',
  description: 'Build CP-FORK-01: a real Isaac ForkliftB raises its fork (lift_joint prismatic) lifting a load — resolve the lift rig + actuation + a scene_eyes-verifiable proof, produce the concrete template',
  phases: [{ title: 'Analyze', detail: 'rig + actuation + verification, independent' }, { title: 'Synthesize', detail: 'one concrete buildable + verifiable template' }],
}

const REPO = '/home/anton/projects/Omniverse_Nemotron_Ext'
const FK = '/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Robots/IsaacSim/ForkliftB/forklift_b.usd'
const CTX = [
  'Repo: ' + REPO + ' (Isaac Sim canonical-composition system). cd there. Read + bash (grep/python3/pxr) access.',
  'GOAL: CP-FORK-01 = a real Isaac ForkliftB asset RAISES ITS FORK (the lift_joint) to lift a load, scene_eyes-RAW-verified. The simplest first MEGA forklift proof (drive = separate CP-FORK-02). MEGA-direction (docs/notes/MEGA_DIRECTION_TRIAGE.md).',
  'GROUNDED FACTS (Kit-free pxr): asset ' + FK + ', default prim /SMV_Forklift_B01_01 (articulation root). lift_joint = /SMV_Forklift_B01_01/lift_joint, PhysicsPrismaticJoint, physics:axis=Z, drive ALREADY configured (drive:linear:physics:stiffness=100000, damping=10000, targetPosition=0.0), limits [-0.15, 2.0]. So raising the fork = set drive:linear:physics:targetPosition to a positive value; the strong drive moves it. Other joints: back_wheel_drive/back_wheel_swivel (Revolute, the TRICYCLE drive — NOT this task) + 4 passive rollers.',
  '★RIG SURPRISE to resolve: the /SMV_Forklift_B01_01/lift LINK bbox is HUGE x[-2.15,0.89] y[-0.55,0.57] z[0,2.93] and its child meshes include SM_Forklift_Lift + OperatorCab + Glass + Pedal -> the "lift" link appears to be the WHOLE upper assembly (cab+mast+tines), not just the fork tines. Confirm: when lift_joint raises, does the WHOLE upper body rise, or just a fork carriage? WHERE do the fork tines end up + where does a pallet/box rest on them (xy + z when lowered)? Inspect sub-meshes / the S_ForkliftFork.usd prop (Isaac/Props/Forklift/S_ForkliftFork.usd) for tine geometry. The body link bbox = x[-0.99,0.89] y[-0.56,0.56] z[0.03,2.87].',
  'BUILD DSL (template "code" field = a sequence of these handler calls; all-literal /World/ paths like CP-CONV-02.json): create_prim(prim_path, prim_type, position, scale[, size]); add_reference(prim_path, reference_path); apply_api_schema(prim_path, schema_name); set_attribute(prim_path, attr_name, value); set_physics_scene_config(config); create_scene_baseline(include_ground, table_size); create_prim DomeLight+Ground (manual minimal scene like CP-CONV-02). A referenced articulated robot keeps its articulation; setting a joint drive target at build time = the joint moves to it when the sim plays.',
  'VERIFICATION: scene_eyes.py <TPL> <dur> --noframes runs the template in Kit + reports per-object RAW trajectories. It tracks delivery objects by NAME PREFIX (Cube/Item/Brick/...). It does NOT track robot links. So to PROVE the fork lifts, put a tracked box (e.g. /World/Cube_1) RESTING ON THE FORK TINES at their lowered height; when lift_joint target is raised the box should rise with the tines. RAW = the box z goes UP by ~the lift amount. Read /home/anton/.isaac_qa/run/eyes/CP-FORK-01/eyes.json for the box trajectory. If a box-on-tines is too fragile, propose an alternative verifiable proof (e.g. a small step-callback in the template printing the lift link world-z each second, captured in scene_eyes stdout).',
  'Be concrete + grounded: cite the exact prim paths/bboxes you read, the exact DSL lines, the exact target value + load-box position, and the exact scene_eyes RAW signal that confirms success. Do NOT hand-wave. The over-investment lesson: ground from the asset, do not guess the tine position.',
].join('\n')

const ANALYSES = [
  { key: 'rig-and-tines', prompt: [CTX, '',
    'YOUR TASK: resolve the lift RIG + the fork-tine geometry precisely. pxr-inspect ' + FK + ': (1) does lift_joint raise the WHOLE upper assembly or a fork carriage? (look at the link hierarchy body->lift and what is rigidly attached). (2) Find the FORK TINES (the flat prongs a pallet sits on) — their world xy footprint + their TOP surface z when the joint is at targetPosition=0 (lowered). Inspect sub-meshes of /lift and the S_ForkliftFork.usd prop. (3) The forklift facing/orientation (which way do the tines point — +x or -x?). Output the EXACT load-box spawn position [x,y,z] so a 5cm box rests centred on a tine top surface, plus the lifted-height delta for a chosen target (e.g. target=0.5 -> box rises ~0.5m). Cite bboxes.'].join('\n') },

  { key: 'actuation-articulation', prompt: [CTX, '',
    'YOUR TASK: nail the ACTUATION + articulation handling. (1) Confirm setting set_attribute(/World/Forklift/lift_joint, "drive:linear:physics:targetPosition", <val>) at build time will move the joint when the sim plays (the drive is pre-configured stiffness=100000). What value lifts the fork a clean, visible amount within limits [-0.15,2.0] (e.g. 0.5)? (2) Does a referenced ForkliftB keep a LIVE PhysX articulation under add_reference + play, or does it need apply_api_schema(PhysxArticulationRootAPI)/anything extra? grep the codebase (service/.../handlers, scripts/qa) for how a referenced articulated robot (forklift / non-wizard) is loaded + how a joint drive target is set (ArticulationAction, DriveAPI, set_attribute on drive targets). (3) Does the forklift need a fixed base or will it roll/tip when the fork lifts a load (check the wheel joints / whether it is grounded)? Output the exact DSL lines for the forklift spawn + physics + the target-set, and any required articulation/base handling.'].join('\n') },

  { key: 'verification-method', prompt: [CTX, '',
    'YOUR TASK: design the most ROBUST scene_eyes-verifiable proof that the fork lifts. Primary: a tracked box (/World/Cube_1, 5cm, rigid+collider) resting on the tine top; raise the target; the box z rises ~the lift amount in eyes.json. Risks: the box slides off the smooth tine / falls between tines / the tines are angled. Mitigations: a shallow tray/lip, box size, exact placement. ALSO design a FALLBACK proof independent of the box (a step-callback injected in the template that prints the lift link world-z each ~1s, e.g. via omni.physx subscribe_physics_on_step_events, captured in scene_eyes stdout — give the exact probe code). Specify the exact scene_eyes invocation (dur), and the EXACT RAW signal that = PASS (box z delta, or lift-link-z rising) vs FAIL. Account for: scene_eyes handles robot=None / non-Franka robots; the forklift is not a Franka, so the tool/dofs lines will differ — the box trajectory is what matters.'].join('\n') },
]

const PLAN_SCHEMA = {
  type: 'object',
  required: ['key', 'findings', 'dsl_or_diff'],
  properties: {
    key: { type: 'string' },
    findings: { type: 'string', description: 'the concrete grounded answer to this analysis (with cited prim paths/bboxes/code)' },
    dsl_or_diff: { type: 'string', description: 'the exact DSL lines / probe code this analysis contributes' },
    risks: { type: 'string' },
  },
}

const SYNTH_SCHEMA = {
  type: 'object',
  required: ['code', 'verify_cmd', 'pass_signal'],
  properties: {
    code: { type: 'string', description: 'the COMPLETE CP-FORK-01 template "code" body (all-literal /World/ paths), ready to drop into a template JSON' },
    verify_cmd: { type: 'string', description: 'the exact scene_eyes invocation (template id + dur)' },
    pass_signal: { type: 'string', description: 'the exact RAW signal in eyes.json (or stdout) that = PASS' },
    rationale: { type: 'string' },
    risks_and_fallback: { type: 'string' },
  },
}

log('Analyzing the ForkliftB rig + actuation + verification for CP-FORK-01')

const analyses = await parallel(ANALYSES.map(function (a) {
  return function () {
    return agent(a.prompt, { label: 'analyze:' + a.key, phase: 'Analyze', schema: PLAN_SCHEMA })
      .then(function (r) { return r }).catch(function () { return null })
  }
}))

const valid = analyses.filter(Boolean)
log('analyzed ' + valid.length + '/' + ANALYSES.length + '; synthesizing the concrete CP-FORK-01')

const synthesis = await agent(
  [CTX, '',
    'You are the SYNTHESIS builder. Below are the grounded analyses (rig+tines, actuation+articulation, verification). Produce the COMPLETE concrete CP-FORK-01 template "code" body (all-literal /World/ paths, manual minimal scene: DomeLight + Ground + physics config + the forklift via add_reference at a chosen base position + the lift target-set + a load box on the tines + any required articulation/base handling), the exact scene_eyes verify command, and the exact RAW pass-signal. Make it self-consistent + buildable as-is.',
    'ANALYSES: ' + JSON.stringify(valid, null, 1)].join('\n'),
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA }
)

return { analyses: valid, synthesis: synthesis }
