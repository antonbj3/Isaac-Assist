#!/usr/bin/env python3
"""real_asset_spawn.py — DIMENSION-HANDLING for real assets (Anton rescope 2026-06-19, cont.319e).

Real assets (YCB props, etc.) have arbitrary real-world dimensions vs our generated parametric primitives.
Picking a real object with the Franka jaw requires per-asset reasoning I'd been doing BY HAND 4x (measure the
USD bbox -> base-z so it rests ON the surface, orient the narrowest horizontal axis along the jaw close-axis
(world-Y, q=[0,1,0,0]), object-aware drop_height, flag tall/topple-risk, find the child Mesh for the collider).
This encapsulates that as a first-class helper so ANY real asset is auto-spawnable into a pick-place template.

compute_spawn_recipe(usd_path, surface_z=0.805) -> dict:
  extent_cm, base_offset_cm, mesh_leaf, spawn_z, rotation_euler, graspable, min_horiz_cm,
  drop_height, tall (topple-risk -> needs descend-to-place), collider_approx, note.

GROUNDED + VERIFIED against the 3 hand-tuned cont.319 templates (foam_brick native, gelatin_box native,
tomato_soup_can stood upright). Run `python real_asset_spawn.py <usd>` for a recipe, or `--selftest`.
"""
import sys, os, json

JAW_MAX = 0.075          # Franka parallel jaw usable opening (~8cm, keep margin)
TALL_THRESH = 0.09       # standing height above which a narrow object topples on a drop -> descend-to-place
ROUND_HINT = ("can", "bottle", "ball", "cylinder", "mug", "bowl", "cup", "pitcher")


def _bbox(usd_path):
    from pxr import Usd, UsdGeom
    s = Usd.Stage.Open(usd_path)
    dp = s.GetDefaultPrim()
    bb = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    rng = bb.ComputeWorldBound(dp).ComputeAlignedRange()
    mn, mx = rng.GetMin(), rng.GetMax()
    ext = [mx[i] - mn[i] for i in range(3)]
    leaf = None
    for p in s.Traverse():
        if p.GetTypeName() == "Mesh":
            leaf = p.GetName(); break
    return ext, mn[2], leaf


def compute_spawn_recipe(usd_path, surface_z=0.805, clearance=0.005):
    ext, min_z, leaf = _bbox(usd_path)
    ex, ey, ez = ext
    name = os.path.basename(usd_path)[:-4].lower()
    is_roundish = any(k in name for k in ROUND_HINT)

    rotation = None
    # A clearly-elongated round/long object (a can/bottle lying down) is NOT graspable across its length AND
    # rolls -> stand it upright (long axis -> Z) so the jaw grips the now-vertical barrel.
    longest = max(ext); li = ext.index(longest)
    others = [e for i, e in enumerate(ext) if i != li]
    elongated = longest > 1.4 * max(others)
    if li in (0, 1) and (elongated and (is_roundish or min(others) >= JAW_MAX)):
        # rotate the horizontal long axis up to Z: long on X -> rot about Y(+90); long on Y -> rot about X(+90)
        rotation = [90, 0, 0] if li == 1 else [0, 90, 0]
        # recompute extents after standing: the long axis becomes vertical
        if li == 1:   # y<->z
            ex, ey, ez = ext[0], ext[2], ext[1]
        else:         # x<->z
            ex, ey, ez = ext[2], ext[1], ext[0]

    # after orientation: ensure the NARROWER horizontal axis is along Y (the jaw close-axis). If x is narrower
    # than y, add a 90-about-Z so the narrow side faces the jaw.
    rot_z_for_jaw = ex < ey - 1e-4
    if rot_z_for_jaw:
        if rotation is None:
            rotation = [0, 0, 90]
        else:
            rotation = [rotation[0], rotation[1], rotation[2] + 90]
        ex, ey = ey, ex

    min_horiz = min(ex, ey)
    graspable = min_horiz < JAW_MAX
    height = ez
    tall = height > TALL_THRESH
    # base sits on the surface: spawn the wrapping Xform so the asset's lowest point clears the surface.
    # (min_z is the asset's base relative to its origin in the NATIVE frame; for a standing rotation the half
    # height is ez/2, origin-centered, so base offset = -ez/2.)
    base_off = (-ez / 2.0) if rotation else min_z
    spawn_z = surface_z + (-base_off) + clearance
    # object-aware drop: release just enough to clear a typical bin rim; tall objects can't be made upright by
    # drop_height alone (need descend-to-place) -> flag.
    drop_height = round(0.10 + height, 3) if not tall else round(0.10 + height, 3)
    approx = "convexDecomposition" if is_roundish and ("bowl" in name or "mug" in name) else "convexHull"

    note = []
    if not graspable:
        note.append("min horiz %.1fcm EXCEEDS jaw — scale down or different grasp" % (min_horiz * 100))
    if tall:
        note.append("TALL (%.1fcm) — topples on drop into a bin; needs DESCEND-TO-PLACE for upright" % (height * 100))
    if rotation:
        note.append("reoriented to stand/face the jaw")
    return {
        "asset": os.path.basename(usd_path),
        "mesh_leaf": leaf,
        "extent_cm": [round(e * 100, 1) for e in ext],
        "oriented_hwd_cm": [round(ex * 100, 1), round(ey * 100, 1), round(ez * 100, 1)],
        "rotation_euler": rotation,
        "spawn_z": round(spawn_z, 3),
        "graspable": graspable,
        "min_horiz_cm": round(min_horiz * 100, 1),
        "tall_needs_descend_place": tall,
        "drop_height": drop_height,
        "collider_approx": approx,
        "note": "; ".join(note) or "graspable in computed orientation",
    }


YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned"


def _selftest():
    # reproduce the 3 hand-tuned cont.319 choices
    cases = {
        "061_foam_brick":      dict(rotation_euler=None,       graspable=True,  tall=False),  # native, flat
        "009_gelatin_box":     dict(rotation_euler=None,       graspable=True,  tall=False),  # native, flat
        "005_tomato_soup_can": dict(rotation_euler=[90, 0, 0], graspable=True,  tall=True),   # stand upright, tall
    }
    ok = True
    for obj, exp in cases.items():
        r = compute_spawn_recipe(f"{YCB}/{obj}.usd")
        got = dict(rotation_euler=r["rotation_euler"], graspable=r["graspable"], tall=r["tall_needs_descend_place"])
        match = got == exp
        ok &= match
        print(("OK  " if match else "FAIL") + f" {obj:22} got={got}  exp={exp}  spawn_z={r['spawn_z']}")
    print("SELFTEST", "PASS" if ok else "FAIL — recipe diverges from hand-tuned templates")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif len(sys.argv) > 1:
        print(json.dumps(compute_spawn_recipe(sys.argv[1]), indent=2))
    else:
        print("usage: real_asset_spawn.py <usd_path> | --selftest", file=sys.stderr); sys.exit(2)
