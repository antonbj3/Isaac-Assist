"""measure_fixture.py — measure a referenced FIXTURE asset's horizontal SURFACES (tiers) so a cell can
derive its drop-targets from the REAL geometry instead of hardcoded z-levels (the "frictionless real-asset"
resolver, Anton 2026-06-21). This is the fixture analogue of the bbox-driven workpiece grasp: reference an
arbitrary shelf/rack/table USD, MEASURE its actual surfaces via UsdGeom world-bbox, and report each tier's
top-z + xy-footprint. A cell then places cubes on the measured tiers — any fixture, any size, no hardcode.

A "surface/tier" = a leaf gprim whose world bbox is THIN in z and WIDE in xy (a horizontal panel you can
rest objects on), not an upright/post (tall-thin) or a beam (long in one xy axis only). Reports overall
size too, so the caller can judge reach (a 2m warehouse rack's top tiers may be out of a Franka's 0.855m
reach -> scale the asset down by the reported factor, or use only the reachable tiers).

Usage:  python scripts/qa/measure_fixture.py <ASSET.usd> [scale]
  scale (optional) = uniform scale applied to the reference before measuring (to fit a big rack to a cell).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts/qa"))

from service.isaac_assist_service.chat.tools import kit_tools  # noqa: E402


def _introspect_code(asset: str, scale: float) -> str:
    return f"""
import omni.usd, json
from pxr import Usd, UsdGeom, Gf
ctx = omni.usd.get_context(); ctx.new_stage()
stage = ctx.get_stage()
UsdGeom.Xform.Define(stage, '/World')
fx = stage.DefinePrim('/World/Fixture', 'Xform')
fx.GetReferences().AddReference({asset!r})
xf = UsdGeom.Xformable(fx)
if {scale!r} != 1.0:
    xf.AddScaleOp().Set(Gf.Vec3f({scale!r}, {scale!r}, {scale!r}))
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
ob = cache.ComputeWorldBound(fx).ComputeAlignedRange()
omn, omx = ob.GetMin(), ob.GetMax()
surfaces = []
for p in Usd.PrimRange(fx):
    if not p.IsA(UsdGeom.Gprim):
        continue
    b = cache.ComputeWorldBound(p).ComputeAlignedRange()
    if b.IsEmpty():
        continue
    mn, mx = b.GetMin(), b.GetMax()
    sx, sy, sz = float(mx[0]-mn[0]), float(mx[1]-mn[1]), float(mx[2]-mn[2])
    # horizontal slab: thin in z, wide in BOTH xy, and z thinner than half the smaller xy span
    if sz <= 0.12 and sx >= 0.20 and sy >= 0.20 and sz < 0.5*min(sx, sy):
        surfaces.append({{'prim': str(p.GetPath()), 'top_z': float(mx[2]),
                          'center': [float((mn[0]+mx[0])/2.0), float((mn[1]+mx[1])/2.0)],
                          'footprint': [sx, sy], 'thickness': sz}})
surfaces.sort(key=lambda s: s['top_z'])
# group surfaces at near-equal top_z (<2cm apart) into TIERS (a shelf level may be several coplanar panels)
tiers = []
for s in surfaces:
    if tiers and abs(s['top_z'] - tiers[-1]['top_z']) < 0.02:
        tiers[-1]['panels'] += 1
        tiers[-1]['footprint'][0] = max(tiers[-1]['footprint'][0], s['footprint'][0])
        tiers[-1]['footprint'][1] = max(tiers[-1]['footprint'][1], s['footprint'][1])
    else:
        tiers.append({{'top_z': s['top_z'], 'center': s['center'], 'footprint': list(s['footprint']), 'panels': 1}})
print("FIXTURE_SURFACES " + json.dumps({{
    'asset': {asset!r}, 'scale': {scale!r},
    'overall_size': [float(omx[0]-omn[0]), float(omx[1]-omn[1]), float(omx[2]-omn[2])],
    'overall_bbox_min': [float(omn[0]), float(omn[1]), float(omn[2])],
    'overall_bbox_max': [float(omx[0]), float(omx[1]), float(omx[2])],
    'n_surface_prims': len(surfaces), 'n_tiers': len(tiers), 'tiers': tiers}}))
"""


async def main() -> int:
    if len(sys.argv) < 2:
        print("usage: measure_fixture.py <ASSET.usd> [scale]")
        return 2
    asset = sys.argv[1]
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    res = await kit_tools.exec_sync(_introspect_code(asset, scale), timeout=60)
    out = res.get("output", "") if isinstance(res, dict) else str(res)
    print(out)
    # pretty-print the tiers for the eye
    for ln in out.splitlines():
        if ln.startswith("FIXTURE_SURFACES "):
            d = json.loads(ln[len("FIXTURE_SURFACES "):])
            print("\n=== %s (scale %.3g) ===" % (asset.split("/")[-1], d["scale"]))
            print("  overall size (m): %.3f x %.3f x %.3f  (z=height)" % tuple(d["overall_size"]))
            print("  %d horizontal surface prim(s) -> %d tier(s):" % (d["n_surface_prims"], d["n_tiers"]))
            for i, t in enumerate(d["tiers"]):
                print("   tier %d: top_z=%.3f m  center_xy=[%.3f,%.3f]  footprint=%.3fx%.3f m  (%d panel)"
                      % (i, t["top_z"], t["center"][0], t["center"][1], t["footprint"][0], t["footprint"][1], t["panels"]))
            if not d["tiers"]:
                print("   (no horizontal surfaces detected — asset may be a single mesh or all-uprights; use overall bbox)")
    return 0 if res.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
