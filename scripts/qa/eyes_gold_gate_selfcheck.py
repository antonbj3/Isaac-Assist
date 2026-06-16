#!/usr/bin/env python3
"""eyes_gold_gate_selfcheck.py — standalone regression guard for the scene_eyes gold-gate verdict logic.

Runs the gate's `verdict_for_instance` against synthetic scene_eyes-style fixtures covering every reject
branch + the pass cases, so a future scene_eyes/gate edit cannot silently break gold-trust. NOT a pytest
file (won't be collected by a directory sweep — honours the "never pytest against dirs" rule); run it
directly: `python3 scripts/qa/eyes_gold_gate_selfcheck.py`. Exit 0 = all invariants hold.

Each fixture is the kind of text scene_eyes prints per instance; the asserted (genuine, reason-substr)
encodes a gold-trust invariant. cont.140 added the TOPPLED branch; this guards it + the prior branches.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eyes_gold_gate import verdict_for_instance

# A complete, genuine column delivery (2 cubes, 2 z-levels, both upright).
CLEAN_COLUMN = """PICK CONVERGENCE:
    Cube_1         closest= 104mm (dz= 103mm dxy=   8mm) @  4.2s  -> CONVERGED + GRIPPED
    Cube_2         closest= 103mm (dz= 103mm dxy=   5mm) @ 23.1s  -> CONVERGED + GRIPPED
STACK STRUCTURE (2 objs): 2 z-level(s) [0.825, 0.875] | xy-extent=0.00x0.00m | min-pair-xy=0.002m
    -> COLUMN / multi-tier vertical structure — consistent with a TOWER/column stacker
ORIENTATION (settled cube tilt from world-up; >60°=TOPPLED, 30-60°=TILTED; round items skipped; reject scoped to box-like):
    Cube_1         tilt=  6.6°  upright
    Cube_2         tilt=  6.4°  upright
"""

# Same column but one cube ended toppled on its side (>60°). DELIVERED by position, NOT correctly placed.
TOPPLED_COLUMN = CLEAN_COLUMN.replace(
    "    Cube_2         tilt=  6.4°  upright\n",
    "    Cube_2         tilt= 88.1°  TOPPLED\n"
    "*** ORIENTATION FAIL: 1 object(s) TOPPLED (delivered but tipped >60° from upright = not correctly placed): Cube_2 ***\n")

# A cube TILTED (30-60°) but not toppled — a soft warning, must NOT reject (no-false-negative discipline).
TILTED_COLUMN = CLEAN_COLUMN.replace(
    "    Cube_2         tilt=  6.4°  upright\n",
    "    Cube_2         tilt= 41.0°  TILTED\n")

# An elongated graspable resting flat — scene_eyes scopes the reject to box-like, so NO ORIENTATION FAIL
# line is emitted for it; the gate must still pass (this fixture has no FAIL line, mirroring that scoping).
NONBOX_FLAT = """PICK CONVERGENCE:
    Broom_handle   closest= 104mm (dz= 103mm dxy=   8mm) @  4.2s  -> CONVERGED + GRIPPED
STACK STRUCTURE (2 objs): 1 z-level(s) [0.820] | xy-extent=0.30x0.00m | min-pair-xy=0.300m
    -> FLAT 1-tier spread grid (gaps present, gripper-clearance ok). OK for a PALLETIZER; ...
ORIENTATION (settled cube tilt from world-up; >60°=TOPPLED, 30-60°=TILTED; round items skipped; reject scoped to box-like):
    Broom_handle   tilt= 89.0°  TOPPLED (non-box; not a reject)
"""

# A cube that was never grasped (transport/grasp failure).
NEVER_GRIPPED = """GRIP-ATTEMPT (per-object; gripped? else closest gripper-to-object approach):
    Cube_1         never-gripped  closest tool approach= 420mm @ 12.0s  NEVER approached (reach / not-claimed)
STACK STRUCTURE (2 objs): 2 z-level(s) [0.825, 0.875] | xy-extent=0.00x0.00m | min-pair-xy=0.002m
"""

# A cube that fell to the ground (final z below the target surface).
LOW_Z = """    Cube_1         closest= 104mm (dz= 103mm dxy=   8mm) @  4.2s  -> CONVERGED + GRIPPED
    Cube_2         closest= 103mm (dz= 103mm dxy=   5mm) @ 23.1s  -> CONVERGED + GRIPPED
STACK STRUCTURE (2 objs): 2 z-level(s) [0.530, 0.825] | xy-extent=0.00x0.00m | min-pair-xy=0.002m
"""

CASES = [
    # (name, text, class, expect_genuine, reason_substr)
    ("clean column -> GOLD",            CLEAN_COLUMN,   "stack/column",   True,  "column verified"),
    ("toppled cube -> REJECT",          TOPPLED_COLUMN, "stack/column",   False, "TOPPLED"),
    ("toppled in a BIN task -> REJECT", TOPPLED_COLUMN, "pick-place-bin", False, "TOPPLED"),   # class-independent
    ("tilted (warn) -> GOLD",           TILTED_COLUMN,  "stack/column",   True,  "column verified"),
    ("non-box flat (scoped out) -> OK", NONBOX_FLAT,    "palletize/grid", True,  "grid verified"),
    ("never-gripped -> REJECT",         NEVER_GRIPPED,  "stack/column",   False, "NEVER approached"),
    ("fell to ground -> REJECT",        LOW_Z,          "stack/column",   False, "below 0.6m"),
]


def main():
    fails = 0
    for name, text, cls, exp_ok, substr in CASES:
        ok, reason = verdict_for_instance(text, cls)
        good = (ok == exp_ok) and (substr.lower() in reason.lower())
        print("  %-34s %-7s exp=%-7s | %s%s" % (
            name, "GENUINE" if ok else "REJECT", "GENUINE" if exp_ok else "REJECT", reason,
            "" if good else "   <<< MISMATCH"))
        if not good:
            fails += 1
    print("SELFCHECK:", "PASS (all %d gold-trust invariants hold)" % len(CASES) if not fails
          else "FAIL (%d/%d mismatched)" % (fails, len(CASES)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
