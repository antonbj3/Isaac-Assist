"""Pre-flight geometric sanity check for canonical templates.

Checks: does drop_target XY land INSIDE destination's world AABB?
Catches the class of bug where template author assumes create_bin position=corner
but it's actually center, leaving drop_target offset from destination.

Generic — reads template's simulate_args.target_path + extracts drop_target
from code string. Works for pick_place, stacking, conveyor patterns.

Usage:
    python scripts/validators/template_geometric_sanity.py CP-PRECISION-3CUBE
    python scripts/validators/template_geometric_sanity.py --all
"""
import argparse, asyncio, json, re, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

from review.sweep_all_rewritten import kit_alive, launch_kit, restart_kit
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical

TEMPLATES = REPO/"workspace/templates"


def extract_drop_target(code: str):
    """Find drop_target=[x, y, z] in code string."""
    m = re.search(r'drop_target\s*=\s*\[\s*([\d.\-]+)\s*,\s*([\d.\-]+)\s*,\s*([\d.\-]+)\s*\]', code)
    if not m:
        return None
    return [float(m.group(1)), float(m.group(2)), float(m.group(3))]


def extract_destination_path(code: str, simulate_args: dict):
    """Prefer simulate_args.target_path; fallback to destination_path in code."""
    if simulate_args.get("target_path"):
        return simulate_args["target_path"]
    m = re.search(r'destination_path\s*=\s*["\']([^"\']+)["\']', code)
    return m.group(1) if m else None


async def aabb_of_prim(path: str):
    """Query Kit for world-space AABB of prim. Returns ((xmin,ymin,zmin),(xmax,ymax,zmax)) or None."""
    code = f"""
import omni.usd
from pxr import UsdGeom, Usd
stage = omni.usd.get_context().get_stage()
prim = stage.GetPrimAtPath('{path}')
if not prim or not prim.IsValid():
    print('AABB_BEGIN'); print('null'); print('AABB_END')
else:
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default','render','proxy'], useExtentsHint=False)
    bb = cache.ComputeWorldBound(prim).ComputeAlignedBox()
    mn = bb.GetMin(); mx = bb.GetMax()
    import json
    print('AABB_BEGIN'); print(json.dumps([[mn[0],mn[1],mn[2]],[mx[0],mx[1],mx[2]]])); print('AABB_END')
"""
    r = await kit_tools.exec_sync(code, timeout=10)
    out = (r.get("output") or "").strip()
    b_i = out.find("AABB_BEGIN"); e_i = out.find("AABB_END")
    if b_i < 0 or e_i < 0:
        return None
    body = out[b_i + len("AABB_BEGIN"):e_i].strip()
    if body == "null":
        return None
    try:
        return json.loads(body)
    except Exception:
        return None


async def validate_template(name: str) -> dict:
    """Returns dict with status + details. Loads scene, queries AABB, compares to drop_target."""
    tpl_path = TEMPLATES/f"{name}.json"
    if not tpl_path.exists():
        return {"name": name, "status": "NOT_FOUND"}
    tpl = json.loads(tpl_path.read_text())
    code = tpl.get("code", "")
    simulate_args = tpl.get("simulate_args") or {}

    drop_target = extract_drop_target(code)
    dest_path = extract_destination_path(code, simulate_args)
    if drop_target is None:
        return {"name": name, "status": "SKIP_NO_DROP_TARGET",
                "note": "Template has no drop_target — likely not a pick_place pattern"}
    if not dest_path:
        return {"name": name, "status": "WARN_NO_DESTINATION",
                "drop_target": drop_target,
                "note": "drop_target defined but no destination_path/target_path"}

    # Reset scene + instantiate template so AABB query reflects actual world geometry
    await kit_tools.exec_sync(
        "import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\n"
        "from pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
    b = await execute_template_canonical(tpl)
    if not b.get("instantiated"):
        return {"name": name, "status": "BUILD_FAIL", "errors": b.get("errors", [])[:2]}
    try:
        await settle_after_canonical(tpl)
    except Exception:
        pass

    aabb = await aabb_of_prim(dest_path)
    if aabb is None:
        return {"name": name, "status": "AABB_FAIL",
                "drop_target": drop_target, "destination_path": dest_path,
                "note": "Could not compute destination AABB"}

    (mn, mx) = aabb
    dx, dy, dz = drop_target
    inside_xy = (mn[0] <= dx <= mx[0]) and (mn[1] <= dy <= mx[1])
    above_top = dz >= mx[2]  # drop_target should be ABOVE container top (cube falls in)
    # Compute offset from destination center
    cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
    offset_x_mm = (dx - cx) * 1000
    offset_y_mm = (dy - cy) * 1000
    offset_xy_mm = (offset_x_mm**2 + offset_y_mm**2)**0.5

    status = "PASS" if (inside_xy and above_top) else "FAIL"
    return {
        "name": name, "status": status,
        "drop_target": drop_target,
        "destination_path": dest_path,
        "destination_aabb": [[round(v,4) for v in mn], [round(v,4) for v in mx]],
        "destination_center_xy": [round(cx,4), round(cy,4)],
        "drop_target_inside_xy": inside_xy,
        "drop_target_above_top": above_top,
        "offset_from_center_mm": [round(offset_x_mm,1), round(offset_y_mm,1)],
        "offset_xy_mm": round(offset_xy_mm,1),
    }


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", nargs="?", help="Template name (no .json)")
    p.add_argument("--all", action="store_true", help="Validate all *.json templates")
    args = p.parse_args()

    if not kit_alive():
        if not await launch_kit():
            print("Kit launch failed"); return

    if args.all:
        names = sorted(p.stem for p in TEMPLATES.glob("*.json"))
    elif args.name:
        names = [args.name]
    else:
        print("Specify name or --all"); return

    results = []
    for name in names:
        try:
            r = await validate_template(name)
        except Exception as e:
            r = {"name": name, "status": "EXC", "error": str(e)[:200]}
        results.append(r)
        # Compact line
        st = r["status"]
        tag = "✓" if st == "PASS" else "·" if st.startswith("SKIP") else "⚠"
        extra = ""
        if st == "FAIL":
            extra = f" offset={r.get('offset_xy_mm',0):.0f}mm inside_xy={r.get('drop_target_inside_xy')} above_top={r.get('drop_target_above_top')}"
        elif st == "PASS":
            extra = f" offset={r.get('offset_xy_mm',0):.0f}mm"
        print(f"  {tag} {name}: {st}{extra}")

    # Summary
    pass_n = sum(1 for r in results if r["status"] == "PASS")
    fail_n = sum(1 for r in results if r["status"] == "FAIL")
    skip_n = sum(1 for r in results if r["status"].startswith("SKIP"))
    other_n = len(results) - pass_n - fail_n - skip_n
    print(f"\nSUMMARY: {pass_n} pass, {fail_n} fail, {skip_n} skip (no drop_target), {other_n} other")
    out_path = REPO/"workspace/qa_runs/geometric_sanity.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Full results: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
