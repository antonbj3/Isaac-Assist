#!/usr/bin/env python3
"""Reconcile probe-vs-scene_eyes: build CP-G1-STAND-01 via the INSTANTIATOR
(execute_template_canonical, the same path scene_eyes uses), then play and read
the pelvis world-z via the articulation API. Tells us if the root-weld holds in
the instantiator path or only in a raw build."""
import asyncio, sys, json
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

MEASURE = r'''
import json, math
import omni.usd, omni.kit.app, omni.timeline
out = {}
stage = omni.usd.get_context().get_stage()
# is the root-weld FixedJoint present?
fjp = stage.GetPrimAtPath("/World/G1_RootWeld")
out["rootweld_prim_exists"] = fjp.IsValid()
app = omni.kit.app.get_app(); tl = omni.timeline.get_timeline_interface()
try: tl.stop()
except Exception: pass
for _ in range(3): app.update()
try: tl.play()
except Exception: pass
for _ in range(12): app.update()
art = None
try:
    from isaacsim.core.api import World
    try: from isaacsim.core.simulation_manager import SimulationManager
    except Exception: from isaacsim.core.api.simulation_manager import SimulationManager
    try:
        if SimulationManager.get_physics_sim_view() is None: SimulationManager.initialize_physics()
    except Exception: pass
    try: _w = World.instance() or World()
    except Exception: _w = None
    from isaacsim.core.prims import SingleArticulation
    art = SingleArticulation("/World/G1/pelvis", name="inst_probe")
    try: art.initialize()
    except Exception as e: out["art_init_fail"] = repr(e)
except Exception as e:
    out["art_unavail"] = repr(e)
def pz():
    try:
        p,_q = art.get_world_pose(); return round(float(p[2]),4)
    except Exception as e: return ("err",repr(e))
out["pelvis_z_t0"] = pz()
samp=[]
for k in range(90):
    app.update()
    if k in (29,59,89): samp.append((k, pz()))
out["pelvis_z_samples"]=samp
out["pelvis_z_final"]=pz()
try:
    names=list(getattr(art,"dof_names",[]) or []); q=art.get_joint_positions()
    ql=[float(x) for x in list(q)] if q is not None else []
    for s in ("left_shoulder_pitch_joint","left_elbow_joint","right_shoulder_pitch_joint","right_elbow_joint"):
        if s in names and len(ql)==len(names): out["arm_"+s]=round(math.degrees(ql[names.index(s)]),1)
except Exception as e: out["arm_err"]=repr(e)
# POSTURE: read key link world-z to confirm standing vs face-plant (false-success guard)
try:
    from isaacsim.core.prims import RigidPrim
    for link in ("head_link","torso_link","pelvis","left_knee_link","left_ankle_roll_link"):
        try:
            rp=RigidPrim("/World/G1/"+link, name="rp_"+link)
            try: rp.initialize()
            except Exception: pass
            p,_=rp.get_world_poses()
            out["z_"+link]=round(float(p[0][2]),3)
        except Exception as e:
            out["z_"+link]=("err",repr(e)[:40])
except Exception as e:
    out["rigidprim_err"]=repr(e)[:60]
print("INST_PROBE "+json.dumps(out))
'''


async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical
    tname = sys.argv[1] if len(sys.argv) > 1 else "CP-G1-STAND-01"
    tpl = json.load(open(f"{REPO}/workspace/templates/{tname}.json"))
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    r = await asyncio.wait_for(execute_template_canonical(tpl), timeout=300)
    print("INSTANTIATED:", {k: r.get(k) for k in ("n_calls", "instantiated", "errors")})
    m = await asyncio.wait_for(kit_tools.exec_sync(MEASURE, timeout=200), timeout=220)
    print("MEASURE:", str(m.get("output") if isinstance(m, dict) else m)[:600])

asyncio.run(main())
