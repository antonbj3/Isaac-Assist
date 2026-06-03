"""Diagnose UR10 orientation issue. Per Anton:
'UR10e horisontellt med del under bord, åker uppåt vid play, skakar sedan'

Build a CP-69-style template, probe UR10 root prim's orientation at t=0
(before play) and at t=1.0 (after physics step). Then probe each joint's
local orientation. Compare with a working Franka template (CP-13).

Hypothesis: UR10 USD asset has wrong default rotation, OR the import_robot
handler doesn't apply a base orientation.

Usage: diagnose_ur10_orientation.py
"""
import asyncio, json, sys, time
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))

PROBE_CODE = r"""
import omni.usd, omni.timeline, omni.kit.app
from pxr import UsdGeom, Sdf, Gf, UsdPhysics
import json, time

stage = omni.usd.get_context().get_stage()
ROBOT_PATH = {robot_path!r}

def _dump_xform(path, label):
    p = stage.GetPrimAtPath(Sdf.Path(path))
    if not p or not p.IsValid():
        return {{"label": label, "path": path, "error": "not_found"}}
    try:
        m = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0)
        t = m.ExtractTranslation()
        q = m.ExtractRotationQuat()
        # Compute z-axis of local frame in world (where does +Z point?)
        z_axis_world = m.Transform(Gf.Vec3d(0,0,1)) - m.Transform(Gf.Vec3d(0,0,0))
        return {{
            "label": label, "path": path,
            "pos": [float(t[0]), float(t[1]), float(t[2])],
            "quat_wxyz": [float(q.GetReal()), *[float(c) for c in q.GetImaginary()]],
            "local_z_in_world": [float(z_axis_world[0]), float(z_axis_world[1]), float(z_axis_world[2])],
        }}
    except Exception as e:
        return {{"label": label, "path": path, "error": str(e)}}

# Children of robot prim — find each link's pose
def _walk_children(root_path, depth=2):
    p = stage.GetPrimAtPath(Sdf.Path(root_path))
    if not p or not p.IsValid(): return []
    out = []
    def _w(prim, d):
        if d > depth: return
        for c in prim.GetChildren():
            out.append(str(c.GetPath()))
            _w(c, d+1)
    _w(p, 0)
    return out

out = {{
    "robot_path": ROBOT_PATH,
    "timeline_stopped": True,
}}

# t=0: before play
out["pre_play"] = _dump_xform(ROBOT_PATH, "root_pre_play")
out["children_pre_play"] = {{c: _dump_xform(c, c.split("/")[-1]) for c in _walk_children(ROBOT_PATH, 1)[:6]}}

# Play for 2 seconds
tl = omni.timeline.get_timeline_interface()
tl.set_current_time(0.0)
tl.set_end_time(10.0)
tl.play()
app = omni.kit.app.get_app()
t0 = time.monotonic()
while time.monotonic() - t0 < 2.0:
    app.update()
tl.stop()

# t=2: after physics
out["post_play"] = _dump_xform(ROBOT_PATH, "root_post_play")
out["children_post_play"] = {{c: _dump_xform(c, c.split("/")[-1]) for c in _walk_children(ROBOT_PATH, 1)[:6]}}

# Articulation root: scan for ArticulationRootAPI
art_paths = []
root_prim = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH))
if root_prim and root_prim.IsValid():
    if root_prim.HasAPI(UsdPhysics.ArticulationRootAPI):
        art_paths.append(ROBOT_PATH)
    for c in root_prim.GetChildren():
        if c.HasAPI(UsdPhysics.ArticulationRootAPI):
            art_paths.append(str(c.GetPath()))
out["articulation_root_paths"] = art_paths

print('PROBE_BEGIN')
print(json.dumps(out, indent=2))
print('PROBE_END')
"""

async def main():
    target_templates = ["CP-69", "CP-13"]  # UR10 broken + Franka working
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical

    for name in target_templates:
        tpl = json.loads((REPO/f"workspace/templates/{name}.json").read_text())
        rd = tpl.get("role_defaults", {})
        pr = rd.get("primary_robot") or {}
        robot_path = pr.get("path", "/World/Robot")

        await kit_tools.exec_sync("import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
        print(f"[{name}] building (robot at {robot_path})...")
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"):
            print(f"[{name}] BUILD_FAIL: {b.get('errors')}"); continue
        try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
        except: pass

        code = PROBE_CODE.format(robot_path=robot_path)
        r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=60), timeout=70)
        out = (r.get("output") or "").strip()
        try:
            b_idx = out.index("PROBE_BEGIN")
            e_idx = out.index("PROBE_END")
            data = json.loads(out[b_idx + len("PROBE_BEGIN"):e_idx].strip())
            print(f"\n=== {name} (robot {robot_path}) ===")
            pre = data["pre_play"]; post = data["post_play"]
            print(f"  PRE play  pos={pre.get('pos')}  quat_wxyz={pre.get('quat_wxyz')}  local_z_in_world={pre.get('local_z_in_world')}")
            print(f"  POST play pos={post.get('pos')}  quat_wxyz={post.get('quat_wxyz')}  local_z_in_world={post.get('local_z_in_world')}")
            print(f"  articulation roots: {data.get('articulation_root_paths')}")
            print(f"  first children:")
            for c, info in list(data.get("children_pre_play", {}).items())[:4]:
                print(f"    PRE  {c}: pos={info.get('pos')} z_in_world={info.get('local_z_in_world')}")
        except Exception as e:
            print(f"[{name}] PARSE_FAIL: {type(e).__name__}: {e}")
            print(f"  head: {out[:500]}")

asyncio.run(main())
