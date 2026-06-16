# L3 chain-handoff — actionable plan for the dedicated session (#29/#10)

Consolidates the cont.80-85 diagnosis into concrete handler work. cont.85 explicitly scoped this as
"focused handler work in a dedicated session, NOT tail-of-marathon probe-hacks" — so it lives here, ready.
Status going in: flat-handoff concept validated (relay 0/4 -> 2/4); the remaining blocker is a geometry coupling.

## The problem (cont.85, MEASURED — not a guess)
A sequential chain = stage-A delivers to a handoff surface, stage-B picks FROM that surface. Five coupled
constraints that manual slab-geometry cannot satisfy simultaneously:
1. inst0 (stage-A) drops at its authored destination position (fixed by the template).
2. the handoff top must be <= inst0's drop point, else cubes drop INSIDE the slab -> interpenetration -> PhysX
   explosion (measured: slab-top 0.81 vs drop 0.75 -> z~-430000).
3. -> cubes therefore rest LOW (~0.775).
4. inst1's (stage-B) grasp is tuned for the CONVEYOR pick height (~0.835) -> plan_fail on a low rest cube.
5. the handoff slab itself is a cuRobo collision OBSTACLE in inst1's planning world -> blocks the grasp approach.
So: slab low -> cube too low for the grasp (plan_fail); slab high -> cube drops inside (explosion). No single
manual slab height resolves it -> needs handoff-geometry-AWARE chain MACHINERY.

## The robust fix (3 coupled pieces — all in the composer/handler, gated/byte-identical for non-chains)
P1. HANDOFF AT GRASP HEIGHT. The chain machinery owns the handoff surface: place its TOP at stage-B's grasp
    height (~conveyor height the downstream pick expects), and place stage-A's DROP point just above the
    handoff top (so cubes settle ON it, never inside). i.e. derive both inst0.drop_z and the handoff_top from a
    single shared `handoff_z`, rather than letting inst0 keep its authored bin-drop height.
    -> code: extend `apply_source_override` (composer.py:123) to ALSO emit a destination-Z override for inst0's
       drop (not just source/dest PATH) + author the handoff prim at handoff_z. New arg e.g.
       `handoff_z=` threaded from a `compose_chain()` wrapper. Keep parallel-mode path untouched (chain opts in).
P2. DOWNSTREAM APPROACH FROM ACTUAL REST HEIGHT. inst1's pick must approach the cube's REAL rest z on the
    handoff (handoff_top + cube_half), not the template's default conveyor pick z.
    -> code: the pick_place controller resolves the pick/grasp pose from the live cube position already (it
       reads cube position after settling). VERIFY this path is honoured for chained sources; if the grasp z is
       hard-anchored to a conveyor constant anywhere, override it from the source cube's actual z. Candidate:
       the curobo variant's pick-approach z derivation (grep the controller for the conveyor/pick height const).
P3. EXCLUDE HANDOFF FROM inst1's GRASP COLLISION WORLD. The handoff slab must not be a cuRobo obstacle for the
    descent onto it (a thin collisionless or planning-excluded surface). cont.85 used a collisionless Cube as
    the bbox marker; for the GRASP, ensure the handoff prim is absent from inst1's cuRobo collision_primitives
    (or below the approach corridor). -> code: composer marks the handoff prim so the controller's cuRobo world
    build skips it for the downstream instance.

## Validation (diagnostic-first, the bar is delivered-count not gate=True)
- Probe preserved: /tmp/chain_flat_probe.py (cont.85). Reuse/rebuild as a restart-wrapper FILE.
- Per stage: scene_eyes --compose, scope per instance (EYES_FOCUS=instN). Read RAW per-object trajectory:
  inst0 cubes settle ON the handoff (z ~= handoff_top, upright, no explosion); inst1 GRIPS from the handoff
  (CONVERGED+GRIPPED, not plan_fail) and delivers to its dest. The topple gate (cont.140) now also guards the
  handoff rest (a cube toppled on the handoff = reject).
- Gold only when BOTH stages full-deliver (relay N/N). 2/4 today -> target 4/4. eyes_gold_gate handles the
  per-instance verdict; for a chain, inst1's "sources" are inst0's outputs (already wired by apply_source_override).

## Guardrails
- Chain machinery must be byte-identical for PARALLEL compositions (the 2/3/4-cell deterministic tier must not
  regress) — gate the new behaviour behind the chain opt-in, like the parallel/chain split already is.
- Do NOT touch the shared belt-pause (CP-52/65) as part of this.
- This is the SEQUENTIAL axis; the PARALLEL axis is done (2/3/4-cell deterministic-gold, cont.140-143).
