#!/usr/bin/env python3
"""Deterministic control for scene_eyes' bin-aware ORIENTATION fix (2026-06-19).

scene_eyes suppresses the TOPPLED reject only for a cube resting INSIDE a deep walled
CONTAINER (bin/tote/hopper, wall-height>0.08) — a flat surface/grid/shelf topple STAYS a
reject (no false-negative). _in_deep_container runs against the LIVE Kit stage, so it can't
be imported standalone; this MIRRORS its logic verbatim and exercises it against a constructed
in-memory USD stage (pxr is standalone-importable). Asserts the positive (in deep bin -> True)
AND the negatives (shallow 'bin' -> False via wall guard; outside xy -> False; above top -> False).
Run: python3 scripts/qa/test_bin_containment.py   (Kit-free, seconds)
"""
from pxr import Usd, UsdGeom, Gf


def _in_deep_container(stage, pos):  # MIRROR of scene_eyes.py _in_deep_container
    if not pos:
        return False
    try:
        _bc = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
        for _pr in stage.Traverse():
            if not any(_k in _pr.GetName() for _k in ("Bin", "Tote", "Hopper", "Bucket")):
                continue
            _rng = _bc.ComputeWorldBound(_pr).ComputeAlignedRange()
            if _rng.IsEmpty():
                continue
            _mn = _rng.GetMin(); _mx = _rng.GetMax()
            if float(_mx[2] - _mn[2]) < 0.08:
                continue
            if (_mn[0] - 0.03 <= pos[0] <= _mx[0] + 0.03 and _mn[1] - 0.03 <= pos[1] <= _mx[1] + 0.03
                    and pos[2] <= _mx[2] + 0.03):
                return True
    except Exception:
        pass
    return False


def _box(stage, path, center, half):
    c = UsdGeom.Cube.Define(stage, path)
    c.GetSizeAttr().Set(2.0)  # extent [-1,1] -> scale by half gives world bbox [center-half, center+half]
    xf = UsdGeom.Xformable(c)
    xf.AddTranslateOp().Set(Gf.Vec3d(*center))
    xf.AddScaleOp().Set(Gf.Vec3f(*half))
    return c


def main():
    stage = Usd.Stage.CreateInMemory()
    # Deep DropBin: world bbox x[-0.15,0.15] y[-0.55,-0.25] z[0.75,0.90] -> wall-height 0.15 (walled container).
    _box(stage, "/World/DropBin", [0.0, -0.4, 0.825], [0.15, 0.15, 0.075])
    # Shallow 'GoodBin' (matches keyword 'Bin' but z-extent 0.05 < 0.08 = flat plate, must NOT count).
    _box(stage, "/World/GoodBin", [0.5, -0.4, 0.79], [0.10, 0.10, 0.025])
    # A non-container support surface (keyword not matched at all).
    _box(stage, "/World/Table", [0.0, 0.0, 0.375], [0.6, 0.9, 0.375])

    cases = [
        ("cube resting in deep DropBin", [0.0, -0.40, 0.785], True),
        ("cube tipped at DropBin edge",  [0.14, -0.30, 0.80], True),
        ("cube in SHALLOW bin (wall<0.08 guard)", [0.5, -0.4, 0.79], False),
        ("cube on Table surface (not a container)", [0.0, 0.0, 0.78], False),
        ("cube outside any bin xy",       [2.0, 2.0, 0.785], False),
        ("cube floating ABOVE DropBin top", [0.0, -0.4, 1.50], False),
        ("no position (None)",            None, False),
    ]
    fails = 0
    for name, pos, exp in cases:
        got = _in_deep_container(stage, pos)
        ok = (got == exp)
        if not ok:
            fails += 1
        print("  %-42s -> %-5s exp=%-5s %s" % (name, got, exp, "OK" if ok else "*** FAIL ***"))
    if fails:
        print("BIN-CONTAINMENT: %d FAIL(s)" % fails)
        raise SystemExit(1)
    print("BIN-CONTAINMENT: PASS (%d cases) — deep-bin topple suppressed, surface/shallow/outside stay rejects" % len(cases))


if __name__ == "__main__":
    main()
