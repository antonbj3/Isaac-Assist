"""Diagnose: build template, run sim, probe what each cube REALLY rests on.

For each template:
  1. Reset + build + settle
  2. Run sim for duration
  3. For each cube_path in simulate_args:
       - Record cube_final position
       - Raycast DOWN from cube_center; record what prim is hit + distance
       - Check if hit-prim is descendant of target_path
  4. Print: cube_final, target_bbox, support_prim, support_distance, support_under_target

This tells us whether function-gate's "in_xy + at_rest + above_floor" is meaningful
or whether cubes are resting on table/floor adjacent to the target.

Usage: diagnose_target_support.py <CP-NAME> [<CP-NAME> ...]
"""
import asyncio, json, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))

PROBE_CODE = r"""
import omni.usd, omni.timeline, omni.kit.app, omni.physx
from pxr import UsdGeom, Sdf, Gf
import json, time

stage = omni.usd.get_context().get_stage()
TARGET_PATH = {target_path!r}
CUBE_PATHS = {cube_paths!r}
DURATION_S = {duration_s!r}

# Run sim
tl = omni.timeline.get_timeline_interface()
app = omni.kit.app.get_app()
tl.set_current_time(0.0)
tl.set_end_time(max(tl.get_end_time(), DURATION_S + 5))
tl.play()
t0 = time.monotonic()
while time.monotonic() - t0 < DURATION_S:
    app.update()
tl.stop()

# Helpers
def _world_pos(path):
    p = stage.GetPrimAtPath(Sdf.Path(path))
    if not p or not p.IsValid(): return None
    m = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0)
    t = m.ExtractTranslation()
    return [float(t[0]), float(t[1]), float(t[2])]

def _world_bbox(path):
    p = stage.GetPrimAtPath(Sdf.Path(path))
    if not p or not p.IsValid(): return None
    bb_cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    bb = bb_cache.ComputeWorldBound(p).ComputeAlignedRange()
    if bb.IsEmpty(): return None
    return {{'min': [float(bb.GetMin()[i]) for i in range(3)],
            'max': [float(bb.GetMax()[i]) for i in range(3)]}}

# Raycast helper via PhysX
phys = omni.physx.get_physx_scene_query_interface()
def _ray_down(origin, max_dist=2.0):
    try:
        from carb import Float3
        o = Float3(float(origin[0]), float(origin[1]), float(origin[2]))
        d = Float3(0.0, 0.0, -1.0)
    except Exception:
        o = origin; d = (0.0, 0.0, -1.0)
    try:
        hit = phys.raycast_closest(o, d, max_dist)
        if hit and hit.get('hit'):
            return (hit.get('rigidBody') or hit.get('collision'), float(hit.get('distance', 0.0)))
    except Exception as e:
        return ('EXC:' + type(e).__name__, None)
    return (None, None)

def _under_target(path):
    if not path: return False
    return str(path).startswith(TARGET_PATH + "/") or str(path) == TARGET_PATH

out = {{
    'target_path': TARGET_PATH,
    'target_bbox': _world_bbox(TARGET_PATH),
    'cubes': {{}},
}}

# Discover all top-level prims for context
top_prims = []
world = stage.GetPrimAtPath(Sdf.Path('/World'))
if world and world.IsValid():
    for child in world.GetChildren():
        n = child.GetName()
        if n.startswith('_') or 'Materials' in n: continue
        top_prims.append(str(child.GetPath()))
out['top_prims'] = top_prims[:20]

for cp in CUBE_PATHS:
    cf = _world_pos(cp)
    cbb = _world_bbox(cp)
    if cf is None:
        out['cubes'][cp] = {{'final': None, 'error': 'not_found'}}
        continue
    # Raycast from BELOW cube bottom — we want the prim the cube rests on.
    # Origin 1 cm below cube_min_z so the cube itself isn't hit.
    if cbb:
        origin = [cf[0], cf[1], cbb['min'][2] - 0.005]
    else:
        origin = [cf[0], cf[1], cf[2] - 0.05]
    support_path, support_dist = _ray_down(origin, max_dist=2.0)
    out['cubes'][cp] = {{
        'final': cf,
        'support_path': str(support_path) if support_path else None,
        'support_distance': support_dist,
        'support_under_target': _under_target(support_path),
        'cube_z_min': cbb['min'][2] if cbb else None,
        'cube_z_max': cbb['max'][2] if cbb else None,
        'bbox': cbb,
    }}

print('PROBE_BEGIN')
print(json.dumps(out, indent=2))
print('PROBE_END')
"""

async def main():
    if len(sys.argv) < 2:
        print("usage: diagnose_target_support.py <CP-NAME> [<CP-NAME> ...]"); return
    names = sys.argv[1:]
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical

    OUT = REPO/"workspace/qa_runs/diagnose_target_support.jsonl"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUT.exists(): OUT.write_text("")

    for name in names:
        tpl_path = REPO/f"workspace/templates/{name}.json"
        if not tpl_path.exists(): print(f"[{name}] NOT_FOUND"); continue
        tpl = json.loads(tpl_path.read_text())
        sa = tpl.get("simulate_args") or {}
        cube_paths = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
        target = sa.get("target_path")
        dur = float(sa.get("duration_s", 60.0))
        if not target or not cube_paths:
            print(f"[{name}] missing target_path or cube_path/s"); continue

        # Reset + build + settle
        await kit_tools.exec_sync("import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
        print(f"[{name}] building...")
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"):
            print(f"[{name}] BUILD_FAIL: {b.get('errors')}"); continue
        try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
        except: pass

        # Run probe
        print(f"[{name}] simulating {dur}s + probing supports...")
        code = PROBE_CODE.format(target_path=target, cube_paths=cube_paths, duration_s=dur)
        r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=dur + 120), timeout=dur + 130)
        out = (r.get("output") or "").strip()
        try:
            b_idx = out.index("PROBE_BEGIN")
            e_idx = out.index("PROBE_END")
            data = json.loads(out[b_idx + len("PROBE_BEGIN"):e_idx].strip())
            data["template"] = name
            with OUT.open("a") as f: f.write(json.dumps(data) + "\n")
            # Print summary
            tb = data["target_bbox"] or {}
            print(f"  target_bbox: min={tb.get('min')} max={tb.get('max')}")
            for cp, info in data["cubes"].items():
                print(f"  {cp}:")
                print(f"    final: {info.get('final')}")
                print(f"    support: {info.get('support_path')} (dist={info.get('support_distance')})")
                print(f"    support_under_target: {info.get('support_under_target')}")
        except Exception as e:
            print(f"  PARSE_FAIL: {type(e).__name__}: {e}")
            print(f"  output head: {out[:300]}")

asyncio.run(main())
