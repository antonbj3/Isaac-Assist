#!/usr/bin/env python3
"""Deterministic control for scene_eyes' bin-aware ORIENTATION suppression (cont.318h-i).

scene_eyes suppresses the TOPPLED reject for a cube resting INSIDE a COLLECTION container (a prim NAMED
Bin/Tote/Hopper/Bucket). cont.318i ARCHITECTURE: the scene_eyes analysis runs in a CLIENT python with NO
omni/stage, so the bin world-bboxes are recorded in the KIT (MEASURE -> eyes.json["bin_bboxes"], a list of
[x0,y0,z0,x1,y1,z1]) and the client-side _in_deep_container just tests containment against that list. Because
the Kit records ONLY *Bin-named prims, surfaces (Pallet/Shelf/Table) are NEVER in the list -> their topples
stay rejects (no false-negative). This MIRRORS the client-side list logic verbatim (pure python, no USD).

★ Why this test was rewritten: the FIRST version queried the live stage FROM the analysis scope; it raised
NameError('UsdGeom'/'stage') then ModuleNotFoundError('omni') under a bare `except: pass`, so it SILENTLY
no-opped at run-time while the old test (a scope WITH pxr) passed = FALSE CONFIDENCE. CP-52 refuted it via RAW.
Lesson: test the logic in the SAME shape it ships (here a pure list check) — and never swallow errors.
Run: python3 scripts/qa/test_bin_containment.py   (no Kit, no USD, instant)
"""


def _in_deep_container(bin_bboxes, pos):  # MIRROR of scene_eyes.py client-side _in_deep_container
    if not pos:
        return False
    for bb in bin_bboxes:
        x0, y0, z0, x1, y1, z1 = bb
        if (x0 - 0.05 <= pos[0] <= x1 + 0.05 and y0 - 0.05 <= pos[1] <= y1 + 0.05
                and z0 - 0.08 <= pos[2] <= z0 + 0.40):
            return True
    return False


def main():
    # As recorded in the Kit (ONLY *Bin-named prims): a deep DropBin + a FLOOR-ONLY GoodBin (zext 0.03).
    # Surfaces (Table/Pallet) are NOT *Bin -> never recorded -> absent from this list.
    BINS = [
        [-0.15, -0.55, 0.75, 0.15, -0.25, 0.90],   # DropBin (deep, zext 0.15)
        [0.48, -0.52, 0.765, 0.72, -0.28, 0.795],  # GoodBin (floor-only, zext 0.03 = the CP-52 create_bin case)
    ]
    cases = [
        ("cube resting in deep DropBin", [0.0, -0.40, 0.785], True),
        ("cube tipped at DropBin edge", [0.14, -0.30, 0.80], True),
        ("★ cube in FLOOR-ONLY bin (CP-52 case)", [0.6, -0.40, 0.79], True),
        ("cube stacked high in DropBin (z+0.1)", [0.0, -0.40, 0.90], True),
        ("cube on a surface (not *Bin -> absent from list)", [0.0, 0.0, 0.78], False),
        ("cube outside any bin", [2.0, 2.0, 0.785], False),
        ("cube floating far ABOVE a bin", [0.0, -0.40, 1.50], False),
        ("no position (None)", None, False),
    ]
    fails = 0
    for name, pos, exp in cases:
        got = _in_deep_container(BINS, pos)
        ok = (got == exp)
        if not ok:
            fails += 1
        print("  %-46s -> %-5s exp=%-5s %s" % (name, got, exp, "OK" if ok else "*** FAIL ***"))
    if fails:
        print("BIN-CONTAINMENT: %d FAIL(s)" % fails)
        raise SystemExit(1)
    print("BIN-CONTAINMENT: PASS (%d cases) — list-based (Kit-recorded *Bin bboxes); floor-only handled; surfaces absent" % len(cases))


if __name__ == "__main__":
    main()
