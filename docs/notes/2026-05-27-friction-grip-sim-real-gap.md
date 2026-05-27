# Friction-grip sim2real gap — investigation backlog

Date noted: 2026-05-27 (Anton + Claude session)
Status: **deferred** — diagnosable in 1-3h, not now

## Observation

Isaac PhysX requires roughly 3× higher gripper `maxForce` than the analytical Coulomb-friction model predicts to hold the same cube during transport:

| Cube | Analytical maxForce needed | Isaac maxForce that works |
|---|---|---|
| 0.05 kg, mu=0.9 (rubber) | 1.6 N | ~7.2 N (default) |
| 0.30 kg, mu=0.5 (metal) | 17.7 N | 200 N (70 N failed) |

70 N is real Franka spec. So Isaac is more conservative than real-world.

## Hypothesis ladder (cheapest first)

1. **Finger pad mu not set** — Franka panda's USD finger pad probably has no PhysicsMaterialAPI bound (or default mu=0.5). Effective contact friction = `min(cube_mu, finger_mu)`. If finger=0.5 and cube=0.9, we only get 0.5. Quick check: read finger collider's material binding.

2. **Cube collider type** — cube primitive vs mesh affects PhysX contact patch generation. Primitive cubes get analytic contact (3 points max), mesh cubes get full SAT. Patch size affects effective friction normal force.

3. **Articulation solver iterations** — PhysX `position_iteration_count` / `velocity_iteration_count` on the Franka articulation. Too few = unstable contact = effective grip-force lower than commanded.

4. **DriveAPI target mode** — finger drive target_position vs target_velocity vs target_force. If finger commanded with velocity target instead of position, stiffness×error doesn't apply the same way.

## Quick checks (when we revisit)

```python
# Check 1: finger material binding
ee = stage.GetPrimAtPath('/World/Franka/panda_hand/panda_leftfinger')
rel = ee.GetRelationship('material:binding:physics')
print('finger bound material:', list(rel.GetTargets()) if rel else None)

# Check 3: articulation iteration counts
art = stage.GetPrimAtPath('/World/Franka')
api = PhysxSchema.PhysxArticulationAPI(art)
print('pos_iter:', api.GetSolverPositionIterationCountAttr().Get())
print('vel_iter:', api.GetSolverVelocityIterationCountAttr().Get())
```

If hypothesis 1 is right (finger material missing/wrong mu), fix is 5-min.

## Why this matters

Production handler (`pick_place.py:4462`) hard-codes `stiff=10000`, `damping=200`, but no `maxForce`. With Isaac default `maxForce=7.2 N`, any cube > ~0.15 kg won't grip reliably even with grip_style="friction".

Bandaid that landed today (2026-05-27): `compute_optimal_grip()` returns `max_force` field; templates can pass `grip_config={max_force: 200}` to override. But cleaner fix requires identifying why Isaac needs 3× the analytical force — most likely a finger-mu binding issue.

## Related

- `service/isaac_assist_service/chat/tools/handlers/grip_config.py` — compute formula
- `scripts/friction_paradigm/find_grip_threshold.py` — empirical sweep harness
- `workspace/friction_tuning/grip_threshold/run_20260527_174715/` — sweep data confirming maxForce cap (light cubes trivial, heavy cubes NEVER under default cap)
