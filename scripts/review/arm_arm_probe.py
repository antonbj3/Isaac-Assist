#!/usr/bin/env python3
"""arm_arm_probe.py — READ-ONLY dual-arm proximity + contact diagnostic for CP-52/53.
Confirms/refutes "grip-slip == arm-arm collision" BEFORE any fix. Observes only.
Run: python3 scripts/review/arm_arm_probe.py CP-52
"""
import asyncio, json, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))
import urllib.request
def kit_alive():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3) as r: return r.status == 200
    except: return False

PROBE_CODE = r"""
import omni.usd, omni.physx, omni.kit.app, omni.timeline, time, json
from pxr import UsdGeom, Sdf, UsdPhysics, PhysxSchema
try:
    from pxr import PhysicsSchemaTools as _PST; _HAS_PST = True
except Exception:
    _PST = None; _HAS_PST = False
stage = omni.usd.get_context().get_stage()
ROBOT_A = "{robot_a}"; ROBOT_B = "{robot_b}"; CUBE_PATHS = {cube_paths!r}; DURATION_S = {duration_s!r}
PROX = 0.06
def _xf(p):
    pr = stage.GetPrimAtPath(Sdf.Path(p))
    if not (pr and pr.IsValid()): return None
    t = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return (float(t[0]), float(t[1]), float(t[2]))
def _links(root):
    out = []
    for d in stage.Traverse():
        pth = str(d.GetPath())
        if pth != root and not pth.startswith(root + "/"): continue
        if d.HasAPI(UsdPhysics.RigidBodyAPI) or d.HasAPI(UsdPhysics.CollisionAPI): out.append(pth)
    return out
LA = _links(ROBOT_A); LB = _links(ROBOT_B)
print("[ARMPROBE] A_links=%d B_links=%d" % (len(LA), len(LB)), flush=True)
for p in LA + LB + list(CUBE_PATHS):
    try:
        pr = stage.GetPrimAtPath(Sdf.Path(p))
        if pr and pr.IsValid(): PhysxSchema.PhysxContactReportAPI.Apply(pr)
    except Exception: pass
def _dec(v):
    try:
        if v is None: return ""
        if hasattr(v, "GetString"): return v.GetString()
        if isinstance(v, int) and _HAS_PST: return str(_PST.intToSdfPath(int(v)))
        s = str(v)
        if s.startswith("/"): return s
        if s.isdigit() and _HAS_PST: return str(_PST.intToSdfPath(int(s)))
        return ""
    except Exception: return ""
def _rob(p):
    if p == ROBOT_A or p.startswith(ROBOT_A+"/"): return "A"
    if p == ROBOT_B or p.startswith(ROBOT_B+"/"): return "B"
    return None
def _cub(p):
    for c in CUBE_PATHS:
        if p == c or p.startswith(c+"/"): return c
    return None
st = {{"t0": None, "min_aa": 1e9, "min_aa_t": None, "near": [], "aa": [], "avc": [],
       "drop_t": {{c: None for c in CUBE_PATHS}}, "zmax": {{c: -1e9 for c in CUBE_PATHS}}, "step": 0}}
def _oc(headers, data):
    try:
        for h in headers:
            a = _dec(getattr(h,"actor0",None)) or _dec(getattr(h,"collider0",None))
            b = _dec(getattr(h,"actor1",None)) or _dec(getattr(h,"collider1",None))
            if not a or not b: continue
            ra, rb = _rob(a), _rob(b); ca, cb = _cub(a), _cub(b)
            t = round((time.monotonic()-st["t0"]) if st["t0"] else 0, 2)
            sep = 1e9
            for i in range(h.contact_data_offset, h.contact_data_offset+h.num_contact_data):
                try: sep = min(sep, float(data[i].separation))
                except Exception: pass
            pen = max(0.0, -sep) if sep != 1e9 else 0.0
            if ra and rb and ra != rb:
                if len(st["aa"]) < 3000: st["aa"].append({{"t": t, "a": a, "b": b, "pen": round(pen,4)}})
            elif (ra and cb) or (rb and ca):
                link = a if ra else b; cube = cb if cb else ca
                if len(st["avc"]) < 3000: st["avc"].append({{"t": t, "link": link, "cube": cube, "pen": round(pen,4)}})
    except Exception: pass
_simi = omni.physx.get_physx_simulation_interface(); _cs = _simi.subscribe_contact_report_events(_oc)
def _os(dt):
    if st["t0"] is None: st["t0"] = time.monotonic()
    t = round(time.monotonic()-st["t0"], 2); st["step"] += 1
    pa = [(_xf(p), p) for p in LA]; pb = [(_xf(p), p) for p in LB]
    pa = [(q,p) for q,p in pa if q]; pb = [(q,p) for q,p in pb if q]
    mind = 1e9; ml = (None, None)
    for qa,na in pa:
        for qb,nb in pb:
            d = ((qa[0]-qb[0])**2+(qa[1]-qb[1])**2+(qa[2]-qb[2])**2)**0.5
            if d < mind: mind = d; ml = (na, nb)
    if mind < st["min_aa"]: st["min_aa"] = mind; st["min_aa_t"] = t
    if mind < PROX and len(st["near"]) < 3000: st["near"].append({{"t": t, "dist": round(mind,4), "lA": ml[0], "lB": ml[1]}})
    if st["step"] % 5 == 0:
        for c in CUBE_PATHS:
            q = _xf(c)
            if not q: continue
            z = q[2]
            if z > st["zmax"][c]: st["zmax"][c] = z
            if st["drop_t"][c] is None and st["zmax"][c] > 0.85 and z < st["zmax"][c]-0.08: st["drop_t"][c] = t
_ph = omni.physx.get_physx_interface(); _ps = _ph.subscribe_physics_step_events(_os)
_app = omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()
for _ in range(int(DURATION_S*60)): _app.update()
try: _ps.unsubscribe()
except: pass
try: _cs.unsubscribe()
except: pass
corr = []
for c in CUBE_PATHS:
    dt = st["drop_t"][c]
    if dt is None: continue
    near = sorted([w for w in st["near"] if abs(w["t"]-dt) <= 1.2], key=lambda w: w["dist"])
    aa = [e for e in st["aa"] if abs(e["t"]-dt) <= 1.2]
    avc = [e for e in st["avc"] if e["cube"] == c and abs(e["t"]-dt) <= 1.2]
    corr.append({{"cube": c, "drop_t": dt, "closest_arm_arm_near_drop": (near[0] if near else None),
                  "armarm_contacts_near_drop": len(aa), "arm_hit_thiscube_near_drop": len(avc), "sample_avc": avc[:3]}})
res = {{"links_A": len(LA), "links_B": len(LB), "min_arm_arm_m": round(st["min_aa"],4), "min_aa_t": st["min_aa_t"],
        "n_near_lt6cm": len(st["near"]), "first_near": st["near"][:6], "n_armarm_contacts": len(st["aa"]),
        "first_armarm": st["aa"][:6], "n_arm_vs_othercube": len(st["avc"]), "first_avc": st["avc"][:6],
        "cube_drops": {{c: st["drop_t"][c] for c in CUBE_PATHS}}, "drop_correlations": corr}}
print("ARMPROBE_BEGIN"+json.dumps(res, default=str)+"ARMPROBE_END", flush=True)
"""

async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "CP-52"
    if not kit_alive(): print("Kit not alive on :8001"); return
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    tpl = json.loads((REPO / f"workspace/templates/{name}.json").read_text())
    sa = tpl.get("simulate_args") or {}
    cube_paths = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
    duration_s = float(sa.get("duration_s", 90))
    await kit_tools.exec_sync("import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"): print("BUILD_FAIL:", str(b.get("errors"))[:400]); return
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception: pass
    code = PROBE_CODE.format(robot_a="/World/FrankaA", robot_b="/World/FrankaB", cube_paths=cube_paths, duration_s=duration_s)
    r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=duration_s+200), timeout=duration_s+220)
    out = (r.get("output") or "")
    i, j = out.find("ARMPROBE_BEGIN"), out.find("ARMPROBE_END")
    if i < 0 or j < 0: print("PARSE_FAIL:\n", out[-2000:]); return
    print(json.dumps(json.loads(out[i+len("ARMPROBE_BEGIN"):j]), indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(main())
