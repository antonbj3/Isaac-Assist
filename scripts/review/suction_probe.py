#!/usr/bin/env python3
"""suction_probe.py — READ-ONLY diagnostic for native IsaacSurfaceGripper suction engagement.

Verifies the design's Step 3 for UR10/vacuum templates AFTER the attachment-point fix:
  - AttachmentPoint_0 authored under the SurfaceGripper (type, body0/body1, NOT snapped to world)
  - isaac:attachmentPoints rel targets it
  - ZERO UsdPhysics.FixedJoint links EE<->cube (the FJ-compliance gate — must stay 0)
  - native engagement: SG isaac:status reaches Closed/Closing while held, grippedObjects lists the cube
  - cube is GRIPPED (lifted + held, cup-to-cube small) and DELIVERED to target (raw positions, truth source)
  - EE/wrist not flung (world-snap check)

Usage: python3 scripts/review/suction_probe.py <TEMPLATE> [duration_s]   (e.g. CP-70 80)
"""
import asyncio, json, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))
import urllib.request
def kit_alive():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3) as r: return r.status == 200
    except Exception: return False

PROBE = r"""
import omni.usd, omni.kit.app, omni.timeline, time, json
from pxr import UsdGeom, Sdf, UsdPhysics, Usd
stage = omni.usd.get_context().get_stage()
CUBES = __CUBES__; TARGET = __TARGET__; DUR = __DUR__
def _xf(p):
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not (pr and pr.IsValid()): return None
    t=UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return (round(float(t[0]),3),round(float(t[1]),3),round(float(t[2]),3))
# --- discover SurfaceGripper(s), robots, fixed joints ---
SGS=[]; ROBOTS=[]; AP_INFO={}
for p in stage.Traverse():
    pa=str(p.GetPath()); tn=p.GetTypeName()
    if tn == "IsaacSurfaceGripper" or p.GetAttribute("isaac:attachmentPoints").IsValid(): SGS.append(pa)
    if p.GetAttribute("ctrl:phase") and p.GetAttribute("ctrl:phase").IsDefined(): ROBOTS.append(pa)
def _fj_scan():
    # returns (total_fj, list of (path, body0, body1)) for ALL UsdPhysics.FixedJoint prims
    out=[]
    for p in stage.Traverse():
        if p.GetTypeName()=="PhysicsFixedJoint" or (UsdPhysics.FixedJoint(p) and p.IsA(UsdPhysics.FixedJoint)):
            try:
                b0=[str(t) for t in p.GetRelationship("physics:body0").GetTargets()] if p.GetRelationship("physics:body0") else []
                b1=[str(t) for t in p.GetRelationship("physics:body1").GetTargets()] if p.GetRelationship("physics:body1") else []
                out.append((str(p.GetPath()), b0, b1))
            except Exception: pass
    return out
def _sg_status(sg):
    pr=stage.GetPrimAtPath(Sdf.Path(sg))
    st=""; gripped=[]
    a=pr.GetAttribute("isaac:status")
    if a and a.IsDefined(): st=str(a.Get())
    r=pr.GetRelationship("isaac:grippedObjects")
    if r and r.IsValid(): gripped=[str(t) for t in r.GetTargets()]
    return st, gripped
def _ap_describe(sg):
    pr=stage.GetPrimAtPath(Sdf.Path(sg))
    r=pr.GetRelationship("isaac:attachmentPoints")
    tgts=[str(t) for t in r.GetTargets()] if (r and r.IsValid()) else []
    info=[]
    for t in tgts:
        jp=stage.GetPrimAtPath(Sdf.Path(t))
        if not (jp and jp.IsValid()): info.append({"path":t,"valid":False}); continue
        b0=[str(x) for x in jp.GetRelationship("physics:body0").GetTargets()] if jp.GetRelationship("physics:body0") else []
        b1=[str(x) for x in jp.GetRelationship("physics:body1").GetTargets()] if jp.GetRelationship("physics:body1") else []
        info.append({"path":t,"type":str(jp.GetTypeName()),"body0":b0,"body1":b1})
    return tgts, info
# pre-play snapshot
PRE={"surface_grippers":SGS,"robots":ROBOTS,"fixed_joints_preplay":_fj_scan()}
for sg in SGS:
    rel_tgts, ap = _ap_describe(sg)
    PRE.setdefault("attachment_points",{})[sg]={"rel_targets":rel_tgts,"joints":ap}
tl=omni.timeline.get_timeline_interface(); tl.play()
app=omni.kit.app.get_app()
samples=[]; t0=time.monotonic(); ee_path=("/".join(SGS[0].split("/")[:-1]) if SGS else None)
max_fj_ee_cube=0; status_seen=set()
for i in range(int(DUR*60)):
    app.update()
    if i % 40 == 0:
        t=round(time.monotonic()-t0,1)
        cubes={c.split("/")[-1]:_xf(c) for c in CUBES}
        sg_st={};
        for sg in SGS:
            st,gr=_sg_status(sg); sg_st[sg.split("/")[-1]]={"status":st,"gripped":[g.split("/")[-1] for g in gr]}; status_seen.add(st)
        # FJ linking EE<->cube?
        fj=_fj_scan(); ee_cube_fj=[]
        for (jp,b0,b1) in fj:
            bb=" ".join(b0+b1)
            if ee_path and ee_path in bb and any(c in bb for c in CUBES): ee_cube_fj.append(jp)
        max_fj_ee_cube=max(max_fj_ee_cube,len(ee_cube_fj))
        eep=_xf(ee_path) if ee_path else None
        cup_cube={}
        for c in CUBES:
            q=_xf(c)
            if q and eep: cup_cube[c.split('/')[-1]]=round(((q[0]-eep[0])**2+(q[1]-eep[1])**2+(q[2]-eep[2])**2)**0.5,3)
        samples.append({"t":t,"cubes":cubes,"sg":sg_st,"n_fj":len(fj),"ee_cube_fj":ee_cube_fj,"ee":eep,"cup_cube":cup_cube})
tgt=_xf(TARGET) if TARGET else None
res={"pre":PRE,"target":TARGET,"target_pos":tgt,"status_values_seen":sorted(status_seen),
     "max_ee_cube_fixedjoints":max_fj_ee_cube,
     "samples":samples,"final":{c.split("/")[-1]:_xf(c) for c in CUBES}}
print("SUCTIONPROBE_BEGIN"+json.dumps(res,default=str)+"SUCTIONPROBE_END",flush=True)
"""

async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "CP-70"
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 80.0
    if not kit_alive(): print("Kit not alive on :8001"); return
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    tpl = json.loads((REPO / f"workspace/templates/{name}.json").read_text())
    sa = tpl.get("simulate_args") or {}
    va = tpl.get("verify_args") or {}
    cubes = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else []) \
            or ([va.get("cube_path")] if va.get("cube_path") else [])
    target = sa.get("target_path") or va.get("place_path")
    await kit_tools.exec_sync("import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"): print("BUILD_FAIL:", str(b.get("errors"))[:500]); return
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception: pass
    code = PROBE.replace("__CUBES__", repr(cubes)).replace("__TARGET__", repr(target)).replace("__DUR__", repr(dur))
    r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=dur+200), timeout=dur+220)
    out = (r.get("output") or "")
    i, j = out.find("SUCTIONPROBE_BEGIN"), out.find("SUCTIONPROBE_END")
    if i < 0 or j < 0: print("PARSE_FAIL:\n", out[-3000:]); return
    d = json.loads(out[i+len("SUCTIONPROBE_BEGIN"):j])
    pre = d["pre"]
    print("=== PRE-PLAY ===")
    print("  surface_grippers:", pre.get("surface_grippers"))
    print("  robots:", pre.get("robots"))
    print("  FixedJoints pre-play:", len(pre.get("fixed_joints_preplay", [])))
    for sg, ap in (pre.get("attachment_points") or {}).items():
        print(f"  AP[{sg}]: rel_targets={ap['rel_targets']}")
        for j2 in ap["joints"]: print(f"      joint {j2}")
    print(f"=== FJ-COMPLIANCE: max EE<->cube FixedJoints during sim = {d['max_ee_cube_fixedjoints']} (MUST be 0) ===")
    print("=== gripper isaac:status values seen:", d["status_values_seen"])
    print(f"=== TARGET {d['target']} @ {d['target_pos']} ===")
    print("=== FINAL cube positions ==="); [print(f"  {k}: {v}") for k, v in d["final"].items()]
    print("=== TIMELINE (t | sg-status/gripped | n_fj ee_cube_fj | cup_cube_dist | cube z) ===")
    for s in d["samples"]:
        sgs = " ".join(f"{k}={v['status']}/{v['gripped']}" for k, v in s["sg"].items())
        cz = " ".join(f"{k}=z{(v[2] if v else None)}" for k, v in s["cubes"].items())
        cc = " ".join(f"{k}={v}" for k, v in s["cup_cube"].items())
        print(f"  t={s['t']:>5} | {sgs} | fj={s['n_fj']} eecube={s['ee_cube_fj']} | cup-cube[{cc}] | {cz}")

if __name__ == "__main__":
    asyncio.run(main())
