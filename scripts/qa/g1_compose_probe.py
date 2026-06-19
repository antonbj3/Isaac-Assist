#!/usr/bin/env python3
"""Verify the composer embedded-path fix: compose a Franka cell (CP-01, inst0) +
the humanoid (CP-G1-STAND-01, inst1, offset +3x) and read the humanoid pelvis at
its NAMESPACED path /World/inst1/G1/pelvis. If it holds ~0.79 -> the root-weld
found the namespaced pelvis (fix works, humanoid composes with robot-diversity)."""
import asyncio, sys, json
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

MEASURE = r'''
import json, math
import omni.usd, omni.kit.app, omni.timeline
out = {}
stage = omni.usd.get_context().get_stage()
out["rootweld_inst1_exists"] = stage.GetPrimAtPath("/World/inst1/G1_RootWeld").IsValid()
out["pelvis_inst1_exists"] = stage.GetPrimAtPath("/World/inst1/G1/pelvis").IsValid()
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
    art = SingleArticulation("/World/inst1/G1/pelvis", name="cmp_probe")
    try: art.initialize()
    except Exception as e: out["art_init_fail"] = repr(e)
    out["dof_n"] = len(list(getattr(art, "dof_names", []) or []))
except Exception as e:
    out["art_unavail"] = repr(e)
def pz():
    try:
        p,_q = art.get_world_pose(); return [round(float(p[0]),3), round(float(p[1]),3), round(float(p[2]),4)]
    except Exception as e: return ("err", repr(e)[:50])
out["pelvis_xyz_t0"] = pz()
samp=[]
for k in range(90):
    app.update()
    if k in (29,59,89): samp.append((k, pz()))
out["pelvis_xyz_samples"]=samp
try:
    names=list(getattr(art,"dof_names",[]) or []); q=art.get_joint_positions()
    ql=[float(x) for x in list(q)] if q is not None else []
    for s in ("left_shoulder_pitch_joint","left_elbow_joint"):
        if s in names and len(ql)==len(names): out["arm_"+s]=round(math.degrees(ql[names.index(s)]),1)
except Exception as e: out["arm_err"]=repr(e)
print("CMP_PROBE "+json.dumps(out))
'''


async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import compose_canonicals
    t_franka = json.load(open(f"{REPO}/workspace/templates/CP-01.json"))
    t_g1 = json.load(open(f"{REPO}/workspace/templates/CP-G1-STAND-01.json"))
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    arg = [(t_franka, "inst0", (0.0, 0.0, 0.0)), (t_g1, "inst1", (3.0, 0.0, 0.0))]
    cb = await asyncio.wait_for(compose_canonicals(arg), timeout=400)
    print("COMPOSE_BUILT:", {k: cb.get(k) for k in ("n_instances",)})
    m = await asyncio.wait_for(kit_tools.exec_sync(MEASURE, timeout=200), timeout=220)
    print("MEASURE:", str(m.get("output") if isinstance(m, dict) else m)[:600])

asyncio.run(main())
