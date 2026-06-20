"""Audit the LLM's geometric perception tools against KNOWN-geometry ground truth
(measure-with-control). Author a cube (0.1m @ [1,2,0.5], mass 2.0) + a sphere
(@ [1,2,1.5]); call each tool; compare returned values to the authored truth.
A tool that returns wrong/missing values = a false-success in the LLM's perception."""
import asyncio, json, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))

def lj(txt):
    for line in (txt or "").splitlines()[::-1]:
        s=line.strip()
        if s.startswith("{") or s.startswith("["):
            try: return json.loads(s)
            except: continue
    return None

def num_near(a, b, tol=0.02):
    try: return abs(float(a)-float(b)) <= tol
    except: return False

def vec_near(v, truth, tol=0.02):
    try: return all(num_near(v[i], truth[i], tol) for i in range(3))
    except: return False

async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.tools.tool_executor import execute_tool_call

    build = (
        "import omni.usd\n"
        "from pxr import UsdGeom, UsdPhysics, Gf, Vt\n"
        "ctx=omni.usd.get_context(); ctx.new_stage(); stage=ctx.get_stage()\n"
        "UsdGeom.Xform.Define(stage,'/World')\n"
        "c=UsdGeom.Cube.Define(stage,'/World/AuditCube')\n"
        "c.GetSizeAttr().Set(0.1)\n"
        "c.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(-0.05,-0.05,-0.05),Gf.Vec3f(0.05,0.05,0.05)]))\n"
        "UsdGeom.Xformable(c.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(1.0,2.0,0.5))\n"
        "UsdPhysics.RigidBodyAPI.Apply(c.GetPrim())\n"
        "UsdPhysics.MassAPI.Apply(c.GetPrim()).GetMassAttr().Set(2.0)\n"
        "s=UsdGeom.Sphere.Define(stage,'/World/AuditSphere')\n"
        "s.GetRadiusAttr().Set(0.15)\n"
        "UsdGeom.Xformable(s.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(1.0,2.0,1.5))\n"
        "print('AUDIT_BUILT', bool(stage.GetPrimAtPath('/World/AuditCube')))\n"
    )
    r = await kit_tools.exec_sync(build, timeout=20)
    print("BUILD:", (r.get("output") or "").strip(), "| ok:", r.get("success"))

    results = []
    async def call(name, args):
        try:
            o = await execute_tool_call(name, args)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return o

    # 1) get_world_transform -> position [1,2,0.5]
    o = await call("get_world_transform", {"prim_path": "/World/AuditCube"})
    j = o if isinstance(o, dict) and ("position" in o or "translation" in o) else lj(o.get("output") or "") if isinstance(o, dict) else None
    pos = (j or {}).get("position") or (j or {}).get("translation") or (j or {}).get("world_position")
    results.append(("get_world_transform", vec_near(pos, [1,2,0.5]) if pos else False, f"pos={pos} exp=[1,2,0.5]", json.dumps(j)[:200] if j else str(o)[:200]))

    # 2) get_mass -> 2.0
    o = await call("get_mass", {"prim_path": "/World/AuditCube"})
    j = o if isinstance(o, dict) else None
    mass = (j or {}).get("mass") if j else None
    if mass is None and isinstance(o, dict):
        jj = lj(o.get("output") or ""); mass = (jj or {}).get("mass") if jj else None
    results.append(("get_mass", num_near(mass, 2.0) if mass is not None else False, f"mass={mass} exp=2.0", str(o)[:200]))

    # 3) get_bounding_box -> center [1,2,0.5]
    o = await call("get_bounding_box", {"prim_path": "/World/AuditCube"})
    j = o if isinstance(o, dict) else None
    if j and "output" in j and "min" not in j: j = lj(j.get("output") or "") or j
    mn = (j or {}).get("min") or (j or {}).get("min_world") or (j or {}).get("aabb_min")
    mx = (j or {}).get("max") or (j or {}).get("max_world") or (j or {}).get("aabb_max")
    center = [(mn[i]+mx[i])/2 for i in range(3)] if (mn and mx) else None
    results.append(("get_bounding_box", vec_near(center, [1,2,0.5], 0.03) if center else False, f"center={center} exp=[1,2,0.5] (min={mn} max={mx})", json.dumps(j)[:160] if j else str(o)[:160]))

    # 4) measure_distance(cube,sphere) -> 1.0
    o = await call("measure_distance", {"prim_a": "/World/AuditCube", "prim_b": "/World/AuditSphere"})
    j = o if isinstance(o, dict) else None
    if j and "output" in j and "distance" not in j: j = lj(j.get("output") or "") or j
    dist = (j or {}).get("distance") or (j or {}).get("center_distance") or (j or {}).get("distance_m")
    results.append(("measure_distance", num_near(dist, 1.0, 0.05) if dist is not None else False, f"dist={dist} exp=1.0", json.dumps(j)[:200] if j else str(o)[:200]))

    print("\n=== PERCEPTION TOOL AUDIT vs ground truth ===")
    npass = 0
    for name, ok, summary, raw in results:
        npass += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name:22} {summary}")
        if not ok: print(f"         raw: {raw}")
    print(f"\n{npass}/{len(results)} perception tools accurate vs authored truth.")

asyncio.run(main())
