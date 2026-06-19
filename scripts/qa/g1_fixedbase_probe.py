#!/usr/bin/env python3
"""Instrumented probe: does a VERIFIED-set physxArticulation:fixedBase=True hold
the G1 pelvis under gravity? Bypasses the instantiator (raw omni/pxr build),
reads the attribute BACK after setting it, plays physics, and reads the pelvis
pose via the articulation API (USD xformOps don't update during physics).
Decisive: if fixedBase reads True AND pelvis-z stays ~0.793 -> mechanism works
(run1's collapse was a script/apply failure, not the mechanism). If pelvis-z
drops despite fixedBase=True read-back -> the attribute genuinely does not
convert a referenced floating-base articulation."""
import asyncio, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

ASSET = ("/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/"
         "Isaac/Samples/Groot/Robots/g1_29dof_with_hand_rev_1_0.usd")

CODE = r'''
import json, math
import omni.usd, omni.kit.app, omni.timeline
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf, UsdLux
out = {}
ctx = omni.usd.get_context(); ctx.new_stage(); stage = ctx.get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

# physics scene + gravity + GPU dynamics
scene = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
scene.CreateGravityMagnitudeAttr(9.81)
psa = PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath("/World/physicsScene"))
try: psa.CreateEnableGPUDynamicsAttr(True)
except Exception as e: out["gpu_err"] = repr(e)

# dome light
UsdLux.DomeLight.Define(stage, "/World/DomeLight")

# ground (collision-only static cube)
g = UsdGeom.Cube.Define(stage, "/World/Ground")
g.GetSizeAttr().Set(1.0)
gx = UsdGeom.XformCommonAPI(g); gx.SetTranslate(Gf.Vec3d(0, 0, -0.5)); gx.SetScale(Gf.Vec3f(20, 20, 1))
UsdPhysics.CollisionAPI.Apply(g.GetPrim())

# G1 reference at pelvis-standing height
g1 = UsdGeom.Xform.Define(stage, "/World/G1")
UsdGeom.XformCommonAPI(g1).SetTranslate(Gf.Vec3d(0.0, 0.0, 0.793))
g1.GetPrim().GetReferences().AddReference("__ASSET__")
out["g1_children"] = len(list(g1.GetPrim().GetAllChildren()))

pelvis = stage.GetPrimAtPath("/World/G1/pelvis")
out["pelvis_valid"] = pelvis.IsValid()
out["pelvis_has_artroot"] = pelvis.HasAPI(UsdPhysics.ArticulationRootAPI)

# set fixedBase=True WITH read-back verification (gated by FB_ON for the A/B control)
FB_ON = __FB_ON__
if FB_ON:
    if not pelvis.HasAPI(PhysxSchema.PhysxArticulationAPI):
        PhysxSchema.PhysxArticulationAPI.Apply(pelvis)
    fb = pelvis.GetAttribute("physxArticulation:fixedBase")
    if not fb or not fb.IsDefined():
        fb = pelvis.CreateAttribute("physxArticulation:fixedBase", Sdf.ValueTypeNames.Bool)
    fb.Set(True)
    out["fixedbase_readback"] = bool(pelvis.GetAttribute("physxArticulation:fixedBase").Get())
else:
    out["fixedbase_readback"] = "FB_OFF_CONTROL"
rj = stage.GetPrimAtPath("/World/G1/rootJoint")
out["rootjoint_exists"] = rj.IsValid()
if rj.IsValid():
    stage.RemovePrim("/World/G1/rootJoint")
    out["rootjoint_deleted"] = True

# WELD ROOT: a single UsdPhysics.FixedJoint PRIM world->pelvis at the pelvis's current pose
# (the canonical "bolt the base to world" — one anchor on the ROOT, not the FixedJointAPI schema
# that exploded, not two leaf-ankle welds that over-constrained). This is the most-likely working
# load-time fixed base for a floating articulation.
WELD_ROOT = __WELD_ROOT__
if WELD_ROOT:
    mw = UsdGeom.Xformable(pelvis).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    wp = mw.ExtractTranslation(); wr = mw.ExtractRotationQuat()
    fj = UsdPhysics.FixedJoint.Define(stage, "/World/G1_RootWeld")
    fj.GetBody1Rel().SetTargets([Sdf.Path("/World/G1/pelvis")])
    fj.CreateLocalPos0Attr(Gf.Vec3f(float(wp[0]), float(wp[1]), float(wp[2])))
    fj.CreateLocalRot0Attr(Gf.Quatf(float(wr.GetReal()), Gf.Vec3f(*[float(x) for x in wr.GetImaginary()])))
    fj.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))
    fj.CreateLocalRot1Attr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    out["root_weld"] = True

# ARM DRIVE targets (degrees) -- same as CP-G1-ARM-01, set on the USD before play
for jp, tgt in (("/World/G1/torso_link/left_shoulder_pitch_joint", 50.0),
                ("/World/G1/left_shoulder_yaw_link/left_elbow_joint", 60.0)):
    jpr = stage.GetPrimAtPath(jp)
    if jpr.IsValid():
        a = jpr.GetAttribute("drive:angular:physics:targetPosition")
        if not a or not a.IsDefined():
            a = jpr.CreateAttribute("drive:angular:physics:targetPosition", Sdf.ValueTypeNames.Float)
        a.Set(float(tgt))
        out.setdefault("drives_set", []).append(jp.split("/")[-1])
    else:
        out.setdefault("drives_missing", []).append(jp)

# pelvis world-z BEFORE physics (from USD xform)
def usd_z(p):
    m = UsdGeom.Xformable(stage.GetPrimAtPath(p)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    return round(float(m.ExtractTranslation()[2]), 4)
out["pelvis_usd_z_build"] = usd_z("/World/G1/pelvis")

# play + step
app = omni.kit.app.get_app(); tl = omni.timeline.get_timeline_interface()
try: tl.stop()
except Exception: pass
for _ in range(3): app.update()
try: tl.play()
except Exception: pass
for _ in range(12): app.update()

# articulation read (after play, like scene_eyes)
art = None; pose_log = []
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
    art = SingleArticulation("/World/G1/pelvis", name="fb_probe")
    try: art.initialize()
    except Exception as e: out["art_init_fail"] = repr(e)
    out["dof_n"] = len(list(getattr(art, "dof_names", []) or []))
except Exception as e:
    out["art_unavail"] = repr(e)

def pelvis_pose_z():
    if art is None: return None
    try:
        pos, _q = art.get_world_pose()
        return round(float(pos[2]), 4)
    except Exception as e:
        return ("err", repr(e))

# step and sample pelvis-z over ~1.5s
out["pelvis_art_z_t0"] = pelvis_pose_z()
for k in range(90):
    app.update()
    if k in (29, 59, 89):
        pose_log.append((k, pelvis_pose_z()))
out["pelvis_art_z_samples"] = pose_log
out["pelvis_art_z_final"] = pelvis_pose_z()
# confirm physics is live: any joint moved?
try:
    q = art.get_joint_positions()
    out["jpos_any"] = None if q is None else round(float(max(abs(float(x)) for x in list(q))), 4)
except Exception as e:
    out["jpos_err"] = repr(e)

open("/tmp/g1_fixedbase_probe_result.json", "w").write(json.dumps(out, indent=2))
print("FB_PROBE_RESULT " + json.dumps(out))
'''.replace("__ASSET__", ASSET)

MODE = sys.argv[1] if len(sys.argv) > 1 else "fb"   # fb | off | weld
FB_ON = "True" if MODE == "fb" else "False"
WELD = "True" if MODE == "weld" else "False"
CODE = CODE.replace("__FB_ON__", FB_ON).replace("__WELD_ROOT__", WELD)


async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    r = await asyncio.wait_for(kit_tools.exec_sync(CODE, timeout=240), timeout=260)
    print("EXEC_RETURN:", str(r)[:500])

asyncio.run(main())
