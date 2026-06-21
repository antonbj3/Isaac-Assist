"""grid_pack_check.py — diagnostic-first measurement of a palletizer's PACKING geometry
(dense-grid gotcha #6 / the CP-08 grid-pile #40). Builds a cell, measures the RAW per-cube
final poses, and classifies the result FLAT-GRID vs PILE/STACK from the z-spread and the
minimum horizontal gap — never trusts delivered-count alone.

Usage:  python scripts/qa/grid_pack_check.py CP-08
"""
from __future__ import annotations
import asyncio
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/qa"))
from chain_xkit_gate import run_stage0  # noqa: E402


async def main() -> int:
    cell = sys.argv[1] if len(sys.argv) > 1 else "CP-08"
    print("⚠️  POSITION-PROXY (re-implemented MEASURE) — NOT a scene_eyes gold. It shows final positions only, never grip/convergence/feeding/topple/plan_fails. For the GOLD verdict run scene_eyes.py. (Anton: alltid alltid scene eyes)")
    res = await run_stage0(cell)
    poses = {k: v for k, v in (res.get("poses") or {}).items() if v}
    delivered, total = res.get("delivered", 0), res.get("total", 0)
    print(f"=== {cell}: delivered={delivered}/{total} ===")
    for k, v in poses.items():
        print(f"  {k}: x={v[0]:+.3f} y={v[1]:+.3f} z={v[2]:.3f}")

    pts = list(poses.items())
    if len(pts) >= 2:
        zs = [v[2] for _, v in pts]
        z_spread = max(zs) - min(zs)
        xy_gaps = [((a[1][0] - b[1][0]) ** 2 + (a[1][1] - b[1][1]) ** 2) ** 0.5
                   for a, b in itertools.combinations(pts, 2)]
        min_xy = min(xy_gaps)
        # PILE if cubes are stacked (z spread > ~1 cube) or horizontally clustered (gap < cube width);
        # a clean 2x2/3x3 grid keeps all cubes at ~one layer with distinct xy slots.
        is_pile = z_spread > 0.045 or min_xy < 0.05
        verdict = "PILE/STACK (grid collapsed)" if is_pile else "FLAT-GRID (clean)"
        print(f"  z_spread={z_spread:.3f}m  min_xy_gap={min_xy:.3f}m  -> {verdict}")
        print("GRID_VERDICT", json.dumps({"cell": cell, "delivered": delivered, "total": total,
                                          "z_spread": round(z_spread, 3), "min_xy_gap": round(min_xy, 3),
                                          "verdict": "PILE" if is_pile else "FLAT_GRID"}))
    else:
        print("GRID_VERDICT", json.dumps({"cell": cell, "delivered": delivered, "verdict": "TOO_FEW_POSES"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
