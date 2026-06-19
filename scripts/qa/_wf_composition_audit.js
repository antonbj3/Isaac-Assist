export const meta = {
  name: 'composition-system-audit',
  description: 'Exhaustive adversarial correctness audit of the Isaac composition system (catalog verdicts, gates, chain-handoff, composer, real-asset recipes, scene_eyes detectors) — find correctness holes, then independently refute each finding',
  phases: [{ title: 'Audit', detail: 'one adversarial finder per dimension' }, { title: 'Verify', detail: 'independently refute each finding' }],
}

const REPO = '/home/anton/projects/Omniverse_Nemotron_Ext'
const CTX = [
  'Repo: ' + REPO + ' (Isaac Sim canonical-composition system).',
  'STRATEGY: the goal is runtime-LLM COMPOSITION — the LLM picks robust pre-verified "blocks" (templates) and chains/composes them. A block is GENUINE only if scene_eyes RAW per-object data proves it (NOT delivered-count).',
  'Core discipline = FALSE-SUCCESS-VAKT: a gate PASS or a GENUINE verdict is NOT proof; audit it adversarially against RAW per-object data and try to REFUTE it. A false GENUINE poisons every composition that uses the block.',
  'Precedent: CP-08 "grid" silently COLLAPSED to a pile and passed a lenient delivery-gate in 8 gold records until an adversarial RAW audit caught it.',
  'Gate-honesty rule: for pick-place-bin / color-sort / kit classes a delivery-gate (any arrangement IN the bin) is HONEST; for stack/column and palletize/grid the gate MUST check structure (z-levels + min-pair-xy spread) or a pile false-passes.',
  'scene_eyes = a MEASURE block (runs IN Kit) + _analyse (runs CLIENT-side, no stage) joined by eyes.json. Saved RAW lives at /home/anton/.isaac_qa/run/eyes/<CP-id>/eyes.json.',
  'You have read + bash (grep/python3) access. Be concrete: cite file:line and quote evidence. Try HARD to refute correctness; do NOT invent issues where the code/verdict is sound. cd ' + REPO + ' first.',
].join(' ')

const DIMENSIONS = [
  { key: 'catalog-verdicts', prompt: [CTX, '',
    'AUDIT DIMENSION: composable-block verdicts. Read workspace/composable_blocks.json (the all map: CP-id -> {robot,class,verdict,basis,n_objects}, plus canonical_blocks and summary). For blocks marked GENUINE, adversarially check the verdict is JUSTIFIED. RED FLAGS:',
    '(a) verdict GENUINE but basis text mentions topple/slip/scatter/marginal/never-gripped/pile/"2 z-levels"-for-a-grid/thrash — anything that should have FAILED it;',
    '(b) a STRUCTURE-requiring class (stack/column OR palletize/grid) whose basis is only "delivery-gate (honest for bin/sort)" with NO z-level/min-pair structure check = the CP-08 grid->pile false-success class;',
    '(c) class-misassignment that routes a structural task to the lenient bin gate (cross-check each CP goal in workspace/templates/<CP>.json vs its recorded class);',
    '(d) suction "gripped-set empty" dismissed as a display gap WITHOUT delivery-RAW backing;',
    '(e) a verdict contradicted by a later note in the same record.',
    'For any CP with a saved eyes.json, load it with python3 and re-derive the key signal (final per-object z-levels, min-pair-xy, settled tilt, never-gripped) and compare to the verdict. Severity: high = a likely false GENUINE that poisons compositions; med = lenient/under-verified but probably ok; low = cosmetic.'].join('\n') },

  { key: 'gates-correctness', prompt: [CTX, '',
    'AUDIT DIMENSION: the verdict GATES. Read scripts/qa/eyes_gold_gate.py (verdict_for_instance) + scripts/qa/eyes_gold_gate_selfcheck.py + the detector logic in scripts/qa/scene_eyes.py _analyse (SETTLED-Z floor guard, STACK STRUCTURE z-levels + min-pair-xy, ORIENTATION/topple with bin-aware suppression, the XY-CONTAINMENT bin check, EJECTION, never-gripped). For EACH reject branch, adversarially construct (1) a concrete scene that SHOULD fail but PASSES (false-success hole), and (2) a good scene wrongly REJECTED (false-negative hole = also progress-poison). Scrutinize especially: the bin/sort xy-containment branch (does it false-reject a composed bin+pallet scene, or miss an object delivered just outside the bin?); the topple bin-suppression (can a genuinely-toppled-on-a-surface cube be suppressed?); the palletize/grid min-pair 0.045m threshold (can a pile sneak under/over?); stack/column z-level>=2 (can a 2-cube stack with a pre-placed untracked base read 1 level and false-reject, task #48?). Cite file:line + a concrete fooling scenario each.'].join('\n') },

  { key: 'chain-handoff', prompt: [CTX, '',
    'AUDIT DIMENSION: cross-Kit chain + handoff correctness. Read workspace/chain_stages.json, scripts/qa/compose_handoff.py (chain_compat), scripts/qa/chain_xkit_gate.py (the relay carries POSITION ONLY and re-creates relayed objects, historically as hardcoded 0.05 cubes), scripts/qa/chain_registry_validate.py, scripts/qa/test_chain_compat.py. Adversarially check: (1) the position-only relay — for which chains would re-creating the handoff object as a plain 0.05 cube give a wrong-shape/size/color stand-in that invalidates the receiver grasp or the "delivered the SAME part" claim? (2) chain_compat height-band/capacity/surface-not-deep-bin — construct a pair it wrongly calls COMPAT (would actually fail) or wrongly INCOMPAT (would work). (3) the YCB-aware relay branch (RELAY_ASSET env) added recently — correct? (4) does delivers_z vs handoff_z usage match what the receiver actually grasps? Cite file:line + the concrete failing pair.'].join('\n') },

  { key: 'composer-machinery', prompt: [CTX, '',
    'AUDIT DIMENSION: composer machinery (namespacing + offset + position kwargs). grep across service/ and scripts/qa/ for compose_and_verify, build_composed_scene, canonical_instantiator, POSITION_KWARGS, per-instance root, move-token, and read them. Adversarially check: (1) POSITION_KWARGS is hand-maintained (task #41) — find a position-bearing kwarg NOT in the list that would silently fail to offset under composition (a cube/sensor/bin placed at the un-offset world origin across instances). (2) namespacing — find a hardcoded /World/<name> prim in any composable template that COLLIDES across instances (the UR10 ShortGripper #46 class). (3) the instantiator runs code_template OVER code when both present (reference_code_template_overrides_code) — find a CP with BOTH where editing the code field is moot. (4) the stop->play requirement for composed scenes (each cell world.reset orphans prior cells) — is it actually enforced everywhere a composed scene is played? Cite file:line + the concrete collision/mis-offset.'].join('\n') },

  { key: 'real-asset-recipes', prompt: [CTX, '',
    'AUDIT DIMENSION: real-asset recipes + templates authored very recently (freshly-written, high audit value). Read scripts/qa/real_asset_spawn.py (compute_spawn_recipe / container_recipe / conveyor_recipe + _selftest) and templates workspace/templates/CP-YCB-*.json, CP-KLT-*.json, CP-CONV-01*.json, CP-CONV-02*.json. Adversarially check: (1) the graspability logic (jaw_fits AND box-like aspect<2.0 AND z/grip<1.8) — find a real YCB object under /mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/ it would mis-classify beyond the 4 selftest cases (pxr-inspect Kit-free: python3 -c "from pxr import Usd,UsdGeom; ..."). (2) conveyor_recipe — verify belt-surface-mesh detection + ride-z + feed-axis + exceeds_floor_reach vs the actual ConveyorBelt_A* structure. (3) the CP-CONV-01/01b GENUINE claims (belt motion + feeder) — re-derive from /home/anton/.isaac_qa/run/eyes/CP-CONV-01*/eyes.json whether cubes REALLY rode the belt (per-object x-advance matching 0.2 m/s) and the feeder cube REALLY held on the belt (z stayed ~1.8, not fell to ~0.78). (4) container_recipe solid-collision detection — correct? Cite file:line + evidence.'].join('\n') },

  { key: 'scene_eyes-detectors', prompt: [CTX, '',
    'AUDIT DIMENSION: scene_eyes.py detector correctness (the measurement tool everything trusts). Read scripts/qa/scene_eyes.py _analyse: grip-slip (EE-relative de-conflation + gripped-carry-window bound), ejection (>8 m/s / z bounds), belt timeline, PICK CONVERGENCE / CONVERGED+GRIPPED, the delivery-object name-prefix tracking + the RigidBodyAPI grasp-token rule, and the module-level asyncio.run(main()) at file end (no __main__ guard — importing runs main()). Adversarially check: (1) does any detector CONFLATE signals (the grip-slip 1990mm transport+EE-rotation precedent) or emit a false signal? (2) the delivery-prefix tracking (Cube/Item/Brick/...) + RigidBodyAPI grasp-token — find an object wrongly tracked or wrongly missed (a static container mesh named ...Box, a real-asset child mesh with an odd name). (3) the no-__main__-guard import side-effect — what breaks if scene_eyes is imported (it runs a full main / connects to Kit)? does any other script import it? (4) does scene_eyes correctly handle robot=None scenes (CP-CONV-01) without corrupting cube tracking? Cite file:line + the concrete failure mode.'].join('\n') },
]

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    summary: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['issue', 'severity', 'evidence', 'location'],
        properties: {
          issue: { type: 'string', description: 'the correctness problem, concrete' },
          severity: { type: 'string', enum: ['high', 'med', 'low'] },
          evidence: { type: 'string', description: 'quoted basis/code/eyes.json signal + a concrete fooling scenario where relevant' },
          location: { type: 'string', description: 'file:line or CP-id' },
          needs_kit_to_confirm: { type: 'boolean' },
          proposed_fix: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['isReal', 'reasoning'],
  properties: {
    isReal: { type: 'boolean', description: 'true only if independently confirmed a real correctness problem' },
    reasoning: { type: 'string' },
    refutation_attempt: { type: 'string', description: 'the strongest argument that this finding is a FALSE ALARM' },
    severity_adjusted: { type: 'string', enum: ['high', 'med', 'low'] },
  },
}

log('Auditing ' + DIMENSIONS.length + ' dimensions of the composition system adversarially')

const results = await pipeline(
  DIMENSIONS,
  d => agent(d.prompt, { label: 'audit:' + d.key, phase: 'Audit', schema: FINDINGS_SCHEMA }),
  (review, d) => {
    const fs = (review && review.findings) || []
    if (!fs.length) return []
    const vprompt = function (f) {
      return [CTX, '',
        'INDEPENDENTLY VERIFY this audit finding from the "' + d.key + '" dimension. Re-read the cited location yourself; do NOT trust the finder. Try HARD to REFUTE it as a false alarm (a misreading of the code, a case the existing logic already handles, a verdict that is actually sound). Default isReal=false unless the evidence clearly shows a real correctness problem that would mis-verify a scene or poison a composition.',
        'FINDING: ' + JSON.stringify(f)].join('\n')
    }
    const thunks = fs.map(function (f) {
      return async function () {
        const v = await agent(vprompt(f), { label: 'verify:' + d.key, phase: 'Verify', schema: VERDICT_SCHEMA }).catch(function () { return null })
        if (!v) return null
        return { issue: f.issue, severity: f.severity, evidence: f.evidence, location: f.location, needs_kit_to_confirm: f.needs_kit_to_confirm, proposed_fix: f.proposed_fix, dimension: d.key, verdict: v }
      }
    })
    return parallel(thunks)
  }
)

const all = results.flat().filter(Boolean)
const sevRank = { high: 0, med: 1, low: 2 }
const confirmed = all.filter(f => f.verdict && f.verdict.isReal)
confirmed.sort((a, b) => (sevRank[(a.verdict.severity_adjusted || a.severity)] ?? 3) - (sevRank[(b.verdict.severity_adjusted || b.severity)] ?? 3))
log('audit complete: ' + all.length + ' findings, ' + confirmed.length + ' confirmed real')
return {
  total_findings: all.length,
  confirmed_count: confirmed.length,
  confirmed: confirmed,
  refuted: all.filter(f => !(f.verdict && f.verdict.isReal)).map(f => ({ location: f.location, issue: f.issue, why_refuted: f.verdict && f.verdict.refutation_attempt })),
}
