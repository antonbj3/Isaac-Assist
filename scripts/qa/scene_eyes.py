#!/usr/bin/env python
"""scene_eyes.py — VIRTUAL EYES: rich, LIVE-PHYSICS motion time-series for a canonical.

The grader (scene_timeseries.py) only logs EE *position* + a settled snapshot — too coarse to
analyse *motion* (stepping, wrist rotation, suction elongation). This permanent QA-review tool
reads the LIVE physics state and quantifies exactly what the eye sees but a settled number can't.

Per 0.1 s it logs (live):
    tool pose (suction cone — USD-live, teleported each step): position + full quaternion
    every articulation JOINT ANGLE (SingleArticulation, initialised AFTER play like the handler)
    elongation = follower<->cone gap in mm (the kinematic-mount lag = the visible 'förlängning')
    every cube position

Analysis printed:
    TOOL peak speed + stop-go cycles  (= the small stepping)
    TOOL peak rotation deg/s
    per-JOINT range° + direction-reversals  (wrist reversals = the 'roterande extra rörelser')
    ELONGATION median/min/max + spike over nominal

Optional viewport frame burst -> labelled contact sheet (lower signal; off with --noframes).

Usage: scene_eyes.py <TEMPLATE> [dur_s=40] [nframes=16] [--noframes] [--attach]
  --attach   probe the CURRENTLY loaded stage instead of re-instantiating
Outputs: /home/anton/.isaac_qa/run/eyes/<TPL>/  (eyes.json, f###.png, sheet.png)
Shares the single-tenant Kit on :8001. In GUI it repoints the active viewport for capture.
"""
import asyncio, json, sys, os, math

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
OPTS = set(a for a in sys.argv[1:] if a.startswith("--"))
FRAMES = "--noframes" not in OPTS
ATTACH = "--attach" in OPTS
# COMPOSE mode (2026-06-15, living-tools): observe a COMPOSED multi-instance scene
# (built via compose_canonicals) instead of a single template — scene_eyes IS the
# truth tool, so it must see composed scenes too (Anton). Invoke:
#   scene_eyes.py --compose "CP-01@0,0,0" "CP-09@6,0,0" [--noframes]   (EYES_DUR=secs, EYES_FOCUS=inst1)
COMPOSE = "--compose" in OPTS

def _parse_compose(arg, idx):
    """'CP-01' or 'CP-01@dx,dy,dz' -> (name, (dx,dy,dz)). Default offset +2.5*idx in x."""
    if "@" in arg:
        nm, off = arg.split("@", 1)
        dx, dy, dz = (float(x) for x in off.split(","))
        return nm, (dx, dy, dz)
    return arg, (2.5 * idx, 0.0, 0.0)

if COMPOSE:
    COMPOSE_SPECS = ARGS                         # each non-flag arg = "CP-01@dx,dy,dz"
    TPL = "compose_" + "_".join(s.split("@")[0] for s in COMPOSE_SPECS)
    DUR = float(os.environ.get("EYES_DUR", "150"))
    NFRAMES = 0
else:
    TPL = ARGS[0] if ARGS else "CP-69"
    # positional DUR wins; else honor EYES_DUR (it was silently ignored for single-template before,
    # so EYES_DUR=520 ran the 40 s default -> a slow 9-cube cell only showed ~3 picks); else 40 s.
    DUR = float(ARGS[1]) if len(ARGS) > 1 else float(os.environ.get("EYES_DUR", "40"))
    NFRAMES = int(ARGS[2]) if len(ARGS) > 2 else 16
# In compose mode, focus the probe on ONE instance's robot (default inst1, the 2nd cell
# that degrades). Empty for single-template -> auto-detect (byte-identical).
# #28 v2 (cont.171): --attach (the observe_scene LLM tool) may ALSO scope a composed instance via
# EYES_FOCUS (observe inst0 then inst1 of the LLM's OWN composed scene); a bare --attach with no
# EYES_FOCUS stays FOCUS="" (auto-detect) -> byte-identical to v1 and to every non-attach run.
if COMPOSE:
    # cont.319hh footgun fix: default to inst1 (the 2nd cell that degrades) only for a MULTI-instance
    # compose; a SINGLE-instance compose has only inst0, so defaulting to inst1 silently tracks NOTHING
    # (cubes={} -> a false "delivery failed" artifact, which mis-graded a CP-CONV-02 compose probe).
    _default_focus = "inst1" if len(COMPOSE_SPECS) >= 2 else "inst0"
    FOCUS = "/World/" + os.environ.get("EYES_FOCUS", _default_focus)
elif os.environ.get("EYES_FOCUS"):
    # cont.314 (verktygen-är-levande): allow per-robot focus on a SINGLE-template MULTI-ROBOT scene
    # (e.g. EYES_FOCUS=Franka2 for CP-02's 2nd station, EYES_FOCUS=Franka1 for a CP-07 cell) — not just
    # compose/attach. Subsumes the old `ATTACH and EYES_FOCUS` case. Default (no EYES_FOCUS) -> FOCUS="" ->
    # byte-identical auto-detect, so every existing single-robot run is unchanged.
    FOCUS = "/World/" + os.environ["EYES_FOCUS"]
else:
    FOCUS = ""
OUT = f"/home/anton/.isaac_qa/run/eyes/{TPL}"
# PER-INSTANCE eyes.json (cont.149/#39.3): a composed run observes each cell with a distinct EYES_FOCUS but all
# instances wrote to the SAME compose_<cells>/eyes.json -> only the LAST instance's raw data survived, blocking
# independent raw audit of earlier cells (the audit-obstruction that hid CP-08 behind CP-13 during cont.150).
# Scope the OUT dir by the focus instance so every cell's eyes.json persists.
if COMPOSE:
    OUT = f"{OUT}/{os.environ.get('EYES_FOCUS', 'inst1')}"

# ---- Kit-side probe (token-replaced raw string; NO f-string so dict braces stay literal) ----
_KIT = r'''
import omni.usd, omni.kit.app, omni.timeline, json, os, math
from pxr import UsdGeom, Sdf, Gf, UsdPhysics
import omni.kit.viewport.utility as vpu
stage = omni.usd.get_context().get_stage()
OUT = "__OUT__"; DUR = __DUR__; NFRAMES = __NFRAMES__; FRAMES = __FRAMES__
os.makedirs(OUT, exist_ok=True)
for _f in os.listdir(OUT):
    if _f.endswith(".png") or _f.endswith(".json"):
        try: os.remove(os.path.join(OUT, _f))
        except Exception: pass

FOCUS = "__FOCUS__"   # compose-mode: observe the robot UNDER this instance root (e.g. /World/inst1)
ROBOT = None
if FOCUS:
    for pr in stage.Traverse():
        _p = str(pr.GetPath())
        # cont.314: match the articulation AT FOCUS (single-template multi-robot, e.g. /World/Franka2 IS the
        # robot) OR UNDER FOCUS/ (composed/rerooted scene, e.g. /World/inst1/Franka). The old "under-only"
        # check silently fell back to auto-detect (first robot) for single-template focus -> live-test caught it.
        if (_p == FOCUS or _p.startswith(FOCUS + "/")) and pr.HasAPI(UsdPhysics.ArticulationRootAPI):
            ROBOT = _p; break
if ROBOT is None:
    for cand in ("/World/UR10", "/World/UR10e", "/World/Franka", "/World/ur10", "/World/Robot"):
        if stage.GetPrimAtPath(Sdf.Path(cand)).IsValid(): ROBOT = cand; break
if ROBOT is None:
    for pr in stage.Traverse():
        if pr.HasAPI(UsdPhysics.ArticulationRootAPI): ROBOT = str(pr.GetPath()); break
def _first(paths):
    for p in paths:
        if p and stage.GetPrimAtPath(Sdf.Path(p)).IsValid(): return p
    return None
EE = _first([ROBOT + "/ee_link", ROBOT + "/panda_hand", ROBOT + "/wrist_3_link"]) if ROBOT else None
CONE = ROBOT + "_SGCone" if (ROBOT and stage.GetPrimAtPath(Sdf.Path(ROBOT + "_SGCone")).IsValid()) else None
FOLL = ROBOT + "_SGFollower" if (ROBOT and stage.GetPrimAtPath(Sdf.Path(ROBOT + "_SGFollower")).IsValid()) else None
# ASSET (blue short_gripper.usd) suction cup — a *_ShortGripper/suction_cup prim (asset mode has no cone/follower).
# In asset mode the cup is the REAL suction tip; ee_link is a frozen virtual frame, so track the cup explicitly.
CUP = None
for _gpr in stage.Traverse():
    _gp = str(_gpr.GetPath())
    # #46: scope the cup to the FOCUS instance in compose mode (the cup is now namespaced under
    # /World/instN/<leaf>_ShortGripper). Single-template FOCUS="" -> `not FOCUS` -> byte-identical.
    if _gp.endswith("_ShortGripper/suction_cup") and (not FOCUS or _gp.startswith(FOCUS + "/")): CUP = _gp; break
TOOL = CONE or FOLL or CUP or EE   # tool proxy: cone/cup is USD-live (tracks the suction tip)
# 2026-06-14: belt surface-velocity per tick -> pins the belt-PAUSE/RESUME timeline (the conveyor-stall
# class: belt pauses during pick phases / while a cube is "imminent"; if it never resumes the boxes stall).
BELT = None
for _bpr in stage.Traverse():
    _bnm = _bpr.GetName()
    # #46: same focus-scoping as CUP — a global first-belt pick crosses instances in compose mode
    # (one cell's belt read for another). Single-template FOCUS="" -> byte-identical.
    if (("Conveyor" in _bnm) or _bnm.endswith("Belt")) and (not FOCUS or str(_bpr.GetPath()).startswith(FOCUS + "/")):
        BELT = str(_bpr.GetPath()); break
_belt_sv_attr = None
if BELT:
    _bp = stage.GetPrimAtPath(Sdf.Path(BELT))
    if _bp and _bp.IsValid():
        _belt_sv_attr = _bp.GetAttribute("physxSurfaceVelocity:surfaceVelocity")

def xform(p):
    pr = stage.GetPrimAtPath(Sdf.Path(p)) if p else None
    if not (pr and pr.IsValid()): return None
    m = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0)
    t = m.ExtractTranslation(); q = m.ExtractRotationQuat(); im = q.GetImaginary()
    return ([round(float(t[0]), 4), round(float(t[1]), 4), round(float(t[2]), 4)],
            [round(float(q.GetReal()), 4), round(float(im[0]), 4), round(float(im[1]), 4), round(float(im[2]), 4)])

# 2026-06-06: track dispenser Item_* (CP-71) too, not just Cube_*. 2026-06-17 (#45): also box-like DELIVERY
# objects — a "rectangular-brick palletizer" (CP-42) names its items Brick_* not Cube_*, so scene_eyes saw NO
# ROWS -> the gate false-NEGATIVE'd a working palletizer. Add unambiguous delivery-item prefixes (Brick/Carton/
# Crate/Package/Parcel); deliberately EXCLUDE "Box"/"Block" (ambiguous with Bin/container/scene-block -> would
# risk tracking a non-delivery prim into the structure verdict = a false-positive). Add those case-by-case.
# cont.319kk-l: + "Sheet" — CP-NEW-vacuum-gripper-sheet-pick names its workpieces Sheet_4/5/6; without it
# scene_eyes tracked ZERO objects (CUBES=[]) -> a false-NEGATIVE (the #45 class). Verified unambiguous: the
# only /World/Sheet* prims in the corpus are those delivery sheets (no SheetMetal-surface / Worksheet etc.).
_DELIV_PREFIX = ("Cube", "Item", "Brick", "Carton", "Crate", "Package", "Parcel", "Sheet")
CUBES = [str(pr.GetPath()) for pr in stage.Traverse() if pr.GetName().startswith(_DELIV_PREFIX)]
# 2026-06-19 (cont.319jj): DEX-HAND palm tracking for the dexterous-grasp detector. A humanoid 3-finger hand has
# NO SurfaceGripper/suction-cup, so the gripper-based grip logic (gripped-set / cup-slip) reads 'never-gripped'
# on the G1 even with real finger->cube contacts. Track the *_hand_palm_link prims so the analyser can test
# cube-FOLLOWS-palm (a dex grip = the cube moves rigidly WITH the palm), the dex analogue of cup-slip.
PALMS = [str(pr.GetPath()) for pr in stage.Traverse() if pr.GetName().endswith("_hand_palm_link")]
# 2026-06-13: also track non-cube MANIPULABLE objects (broom handle, faucet handle, drawer knob, blanks) so
# GRIP-SLIP can measure them. Additive (cubes already matched above) -> cube cases unaffected. A rigid-body
# prim whose name carries a graspable token; exclude the robot subtree and obvious scene-floor.
_GRASP_TOK = ("handle", "broom", "blank", "knob", "lever", "valve", "cap", "bottle", "brush", "peg", "gear", "bolt", "nut", "workpiece", "part", "tool",
              # 2026-06-14: geometric-primitive workpieces (CP-43/44 spheres). Without these, round
              # objects were tracked in CONTACTS but NOT positionally -> invisible to per-object
              # trajectory AND to the EJECTION detector (the exact sphere-blowup case it targets).
              # Safe: the branch below requires RigidBody/Collision API + excludes the robot subtree,
              # so render-only suction proxies (no rigid body) and scenery are not matched.
              # 2026-06-14: "box" too (CP-NEW-palletizer-mixed-sku uses Box_* workpieces — same
              # blind spot as spheres: untracked positionally -> can't SEE the actual SKU-sort).
              "sphere", "ball", "box")
try:
    for _pr in stage.Traverse():
        _pth = str(_pr.GetPath()); _lo = _pr.GetName().lower()
        if _pth in CUBES: continue
        # cont.319cc audit #9: DE-DUP a child mesh of an already-tracked delivery object. A YCB asset referenced
        # UNDER a Cube/Item Xform (e.g. /World/Item_1/_09_gelatin_box) matched a grasp-token ('box') + RB and was
        # tracked a SECOND time -> a 0mm-separation duplicate that (a) false-NEGATIVES the pick (the child leaf reads
        # 'never-gripped' since the grip contact/gripped-set key on the PARENT leaf), and (b) inflates grid/stack
        # object counts + min-pair-xy=0 -> false structure verdicts (bidirectional poison). The parent _DELIV_PREFIX
        # prim is authoritative; skip any prim that is a DESCENDANT of an already-tracked prim.
        if any(_pth.startswith(_c.rstrip("/") + "/") for _c in CUBES): continue
        if ROBOT and _pth.startswith(ROBOT): continue
        # require a DYNAMIC rigid body (a manipulable/delivery object). CollisionAPI-ONLY = static scenery or a
        # referenced CONTAINER mesh (e.g. a real KLT tote whose mesh is named *_Box) -> NOT a delivery object.
        # cont.319n: the old `or CollisionAPI` false-tracked a static KLT destination tote as a delivered item.
        if any(_t in _lo for _t in _GRASP_TOK) and _pr.HasAPI(UsdPhysics.RigidBodyAPI):
            CUBES.append(_pth)
except Exception: pass
# 2026-06-15 COMPOSE OBJECT-SCOPING FIX: in a composed multi-instance scene the SAME leaf
# names exist under every instance (/World/inst0/Cube_3 AND /World/inst1/Cube_3). The row
# dict keys cubes by leaf name (c.split('/')[-1]) -> same-named cubes across instances
# COLLIDE (last wins) -> the focused instance's object is silently overwritten by another
# instance's, producing bogus per-object trajectory + grip-slip (a ~inter-instance-distance
# phantom). Scope CUBES to the FOCUS instance so leaf names are unique. Empty FOCUS
# (single-template) -> no-op, byte-identical.
if FOCUS:
    CUBES = [c for c in CUBES if c.startswith(FOCUS + "/")]

# cuRobo PLAN EVENTS — the handler writes USD-live ctrl: counters on the ROBOT prim
# (plan_calls/plan_fails/picked_path/last_error/last_fail_goal). Reading them each sample
# lets us align planner activity to the motion: a plan_calls bump = a plan_pose at that t,
# a plan_fails bump = a failed/replan. No handler edit needed.
RP = stage.GetPrimAtPath(Sdf.Path(ROBOT)) if ROBOT else None
def cattr(nm, dflt):
    if not (RP and RP.IsValid()): return dflt
    try:
        a = RP.GetAttribute(nm)
        return a.Get() if (a and a.IsValid() and a.Get() is not None) else dflt
    except Exception:
        return dflt

# CONTACTS (PhysX contact-report) — the missing time-series signal vs scene_timeseries.
# Grip (gripper-vs-cube) + arm-vs-scene collisions. The UR10 swing collides forearm/wrist
# with the support surface (Table/Pedestal) -> arm stalls -> cube held aloft; scene_eyes was
# BLIND to this without contacts. Applied to robot links + cubes + bins/pedestals/tables.
_contacts = {}   # (actor0,actor1) -> max contact-impulse magnitude in the window (grip-force signal)
try:
    from pxr import PhysxSchema, PhysicsSchemaTools
    from omni.physx import get_physx_simulation_interface
    _crp = list(CUBES)
    _bases = [ROBOT] if ROBOT else []
    for _pr in stage.Traverse():
        _nm = _pr.GetName()
        if any(_k in _nm for _k in ("Bin", "Pedestal", "Table", "Base", "Tray", "Bridge", "Pallet", "Wall")):
            _bases.append(str(_pr.GetPath()))
    for _base in _bases:
        _bp = stage.GetPrimAtPath(Sdf.Path(_base))
        if _bp and _bp.IsValid():
            for _d in [_bp] + list(_bp.GetChildren()):
                for _dd in [_d] + list(_d.GetChildren()): _crp.append(str(_dd.GetPath()))
    for _p in set(_crp):
        _pp = stage.GetPrimAtPath(Sdf.Path(_p))
        if _pp and _pp.IsValid():
            try: PhysxSchema.PhysxContactReportAPI.Apply(_pp)
            except Exception: pass
    def _oc(h, d):
        for _ch in h:
            try:
                _key = (str(PhysicsSchemaTools.intToSdfPath(_ch.actor0)).split("/")[-1], str(PhysicsSchemaTools.intToSdfPath(_ch.actor1)).split("/")[-1])
                _imp = 0.0
                try:
                    _off = int(getattr(_ch, "contact_data_offset", 0)); _num = int(getattr(_ch, "num_contact_data", 0))
                    for _k in range(_off, _off + _num):
                        _iv = getattr(d[_k], "impulse", None)
                        if _iv is not None:
                            _m = float((_iv[0] * _iv[0] + _iv[1] * _iv[1] + _iv[2] * _iv[2]) ** 0.5)
                            if _m > _imp: _imp = _m
                except Exception: pass
                if (_key not in _contacts) or (_imp > _contacts[_key]): _contacts[_key] = _imp
            except Exception: pass
    _csub = get_physx_simulation_interface().subscribe_contact_report_events(_oc)
except Exception as _ce:
    print("CONTACT_SETUP_FAIL", repr(_ce)); _csub = None

# fixed cell camera for the (optional) frame burst
vp = None
if FRAMES:
    try:
        cam_path = "/World/_EyesCam"
        cam = UsdGeom.Camera.Define(stage, cam_path); cam.GetFocalLengthAttr().Set(18.0)
        eye = Gf.Vec3d(2.6, 2.2, 1.95); tgt = Gf.Vec3d(0.0, 0.0, 0.95); upv = Gf.Vec3d(0, 0, 1)
        mm = Gf.Matrix4d(); mm.SetLookAt(eye, tgt, upv); w = mm.GetInverse()
        xf = UsdGeom.Xformable(cam.GetPrim()); xf.ClearXformOpOrder(); xf.AddTransformOp().Set(w)
        vp = vpu.get_active_viewport(); vp.camera_path = cam_path
    except Exception as _e:
        print("CAM_FAIL", repr(_e)); vp = None

app = omni.kit.app.get_app(); tl = omni.timeline.get_timeline_interface()
# fresh episode
try: tl.stop()
except Exception: pass
for _ in range(3): app.update()
try: tl.play()
except Exception: pass
for _ in range(12): app.update()   # physics_sim_view + handler callback must be live BEFORE articulation init

# JOINTS — init AFTER play (the handler's working order; init-before-play returns 0 dofs)
ART = None; DOFN = []
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
    ART = SingleArticulation(ROBOT, name="eyes_probe")
    try: ART.initialize()
    except Exception as _ie: print("ART_INIT_FAIL", repr(_ie))
    DOFN = list(getattr(ART, "dof_names", []) or [])
except Exception as _e:
    print("JOINTS_UNAVAIL", repr(_e))
def jpos():
    if ART is None: return None
    try:
        q = ART.get_joint_positions()
        return None if q is None else [round(float(x), 4) for x in list(q)]
    except Exception: return None
def jvel():
    if ART is None: return None
    try:
        v = ART.get_joint_velocities()
        return None if v is None else [round(float(x), 3) for x in list(v)]
    except Exception: return None

# SurfaceGripper status (GripperView, Isaac 5.x) — THE grip-release signal: status int over time + gripped set.
# status: 0=Open, 1=Closing, 2=Closed (validated empirically). When it drops 2->0 mid-transit = the grip released.
_GV = None; _SGPATH = None
try:
    from isaacsim.robot.surface_gripper import GripperView as _GVcls
    _sgp = [str(pr.GetPath()) for pr in stage.Traverse() if str(pr.GetTypeName()) == "IsaacSurfaceGripper"]
    _sgp_use = [p for p in _sgp if "ShortGripper" in p] or _sgp
    if FOCUS:
        # cont.315: scope the gripper to the FOCUS robot (multi-robot scene). Else _sgp_use[0] is the FIRST
        # gripper (e.g. Franka1), so a Franka2-focused run read Franka1's grip (degenerate 0@0.0s). Match a
        # gripper UNDER FOCUS/ or FOCUS_-prefixed (e.g. /World/Franka2_ShortGripper). Completes per-robot
        # grip-attribution so multi-station scenes can be verified per robot.
        _foc = [p for p in _sgp_use if p.startswith(FOCUS + "/") or p.startswith(FOCUS + "_")]
        if _foc:
            _sgp_use = _foc
    if _sgp_use:
        _SGPATH = _sgp_use[0]; _GV = _GVcls(paths=_SGPATH)
        print("GV_OK", _SGPATH)
except Exception as _gve:
    print("GV_UNAVAIL", repr(_gve)[:120])
def gstat():
    if _GV is None: return None
    try: return [int(x) for x in list(_GV.get_surface_gripper_status())]
    except Exception: return None
def gripped():
    if _GV is None: return None
    try:
        g = _GV.get_gripped_objects()
        if not g: return []
        inner = g[0] if (isinstance(g, (list, tuple)) and len(g) and isinstance(g[0], (list, tuple))) else g
        return [str(x).split("/")[-1] for x in inner][:6]
    except Exception: return None
def gprops():
    if _GV is None: return None
    try:
        p = _GV.get_surface_gripper_properties()
        return [round(float(p[0][0]), 4), round(float(p[1][0]), 1), round(float(p[2][0]), 1)]
    except Exception: return None

N = int(DUR * 60); CAP = max(1, N // max(1, NFRAMES)); fi = 0; rows = []
for i in range(N):
    app.update()
    if i % 6 == 0:
        tool = xform(TOOL); foll = xform(FOLL)
        elong = round(math.dist(tool[0], foll[0]) * 1000, 1) if (tool and foll) else None
        cubes = {}; cubes_q = {}
        for c in CUBES:
            cx = xform(c); _cn = c.split("/")[-1]
            cubes[_cn] = (cx[0] if cx else None); cubes_q[_cn] = (cx[1] if cx else None)
        cupx = xform(CUP) if CUP else None
        _w3 = xform("/World/UR10/wrist_3_link")
        _bsv = (_belt_sv_attr.Get() if _belt_sv_attr else None)
        # AXIS-AGNOSTIC (2026-06-14): belts can feed on ANY axis (e.g. gravity-dispenser-feeder
        # surface_velocity=[0,0.15,0] is a Y-feed). Reading only vx[0] falsely reported "PAUSED"
        # for every non-X belt. bsv = full-vector MAGNITUDE (registers any-axis motion); bsvv keeps
        # the signed [vx,vy,vz] so direction/dominant-axis is still recoverable.
        _bsvv = ([round(float(_bsv[0]), 3), round(float(_bsv[1]), 3), round(float(_bsv[2]), 3)]
                 if _bsv is not None else None)
        _bsv0 = (round(float((_bsv[0] ** 2 + _bsv[1] ** 2 + _bsv[2] ** 2) ** 0.5), 3)
                 if _bsv is not None else None)
        rows.append({"t": round(i / 60.0, 2), "bsv": _bsv0, "bsvv": _bsvv,
                     "tool_p": (tool[0] if tool else None), "tool_q": (tool[1] if tool else None),
                     "w3_p": (_w3[0] if _w3 else None), "w3_q": (_w3[1] if _w3 else None),
                     "cup_p": (cupx[0] if cupx else None), "cup_q": (cupx[1] if cupx else None),
                     "foll_p": (foll[0] if foll else None), "elong_mm": elong,
                     "j": jpos(), "jv": jvel(), "gv": gstat(), "grp": gripped(), "cubes": cubes, "cubes_q": cubes_q,
                     "palm": {("left" if "left" in p else "right"): (xform(p)[0] if xform(p) else None) for p in PALMS},
                     "pc": int(cattr("ctrl:plan_calls", 0)), "pf": int(cattr("ctrl:plan_fails", 0)),
                     "pick": str(cattr("ctrl:picked_path", "")), "err": str(cattr("ctrl:last_error", "")),
                     "fgoal": str(cattr("ctrl:last_fail_goal", "")),
                     "contacts": sorted(["%s|%s" % (a, c) for (a, c) in _contacts]),
                     "cforce": {"%s|%s" % k: round(v, 3) for k, v in _contacts.items() if v > 0}})
        _contacts.clear()
        # INCREMENTAL dump every ~100 rows (~10s) so a slow/long template (CP-83 2-cube) that exceeds the
        # exec_sync timeout still leaves partial data on disk (robust observation, never a blind NO_EYES_JSON).
        if len(rows) % 100 == 0:
            try:
                import builtins as _bpd
                json.dump({"template": "__TPL__", "robot": ROBOT, "ee": EE, "cone": CONE, "follower": FOLL,
                           "tool": TOOL, "dof_names": DOFN, "rows": rows, "nframes": fi, "gripper_props": gprops(),
                           "sg_path": _SGPATH, "partial": True,
                           "plan_log": list(getattr(_bpd, "_eyes_plan_log", []) or []),
                           "plan_fields": list(getattr(_bpd, "_eyes_plan_fields", []) or [])}, open(OUT + "/eyes.json", "w"))
            except Exception: pass
    if FRAMES and vp is not None and i % CAP == 0:
        try:
            vpu.capture_viewport_to_file(vp, file_path=OUT + "/f%03d.png" % fi)
            for _ in range(6): app.update()
            fi += 1
        except Exception as _e:
            print("CAP_FAIL", repr(_e))
import builtins as _ebd
_plan_log = list(getattr(_ebd, "_eyes_plan_log", []) or [])
_plan_fields = list(getattr(_ebd, "_eyes_plan_fields", []) or [])
# cont.318i: record COLLECTION-bin world bboxes HERE (in the Kit, where stage+UsdGeom exist) so the CLIENT-side
# analysis (a clean python namespace WITHOUT omni/stage) can suppress bin-collection topples. The bin is static.
_bin_bboxes_rec = []
try:
    _bcrec = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    for _prrec in stage.Traverse():
        # cont.319-BINSCOPE: in compose/focus mode, record ONLY the FOCUS instance's bins. Without this,
        # stage.Traverse() picks up a SIBLING instance's bin (e.g. inst0 named /World/inst0/Bin) and the
        # xy-containment check then false-REJECTs the focus cell's deliveries against the wrong-instance bin
        # (caught: CP-YCB-BANANA+CP-50 compose -> CP-50's trays unrecorded, its cubes checked vs inst0's banana
        # bin 2.8m away -> false REJECT). FOCUS="" (non-compose) -> unchanged/byte-identical. Mirrors L140.
        if FOCUS and not str(_prrec.GetPath()).startswith(FOCUS + "/"):
            continue
        if any(_k in _prrec.GetName().lower() for _k in ("bin", "tote", "hopper", "bucket", "crate")):   # cont.319cc audit #4: case-INSENSITIVE (was 'Bin' only -> a 'dropbin'/lowercase container went unrecorded) + 'crate' (deep collection container). Flat surfaces (pallet/tray/shelf) deliberately EXCLUDED so their topples stay rejects.
            _rrec = _bcrec.ComputeWorldBound(_prrec).ComputeAlignedRange()
            if not _rrec.IsEmpty():
                _mnr = _rrec.GetMin(); _mxr = _rrec.GetMax()
                _bin_bboxes_rec.append([float(_mnr[0]), float(_mnr[1]), float(_mnr[2]), float(_mxr[0]), float(_mxr[1]), float(_mxr[2])])
except Exception as _bre:
    print("BIN_BBOX_REC_EXC", repr(_bre))
json.dump({"template": "__TPL__", "robot": ROBOT, "ee": EE, "cone": CONE, "follower": FOLL,
           "tool": TOOL, "dof_names": DOFN, "rows": rows, "nframes": fi, "gripper_props": gprops(), "sg_path": _SGPATH,
           "bin_bboxes": _bin_bboxes_rec,
           "plan_log": _plan_log, "plan_fields": _plan_fields}, open(OUT + "/eyes.json", "w"))
print("EYES_DONE rows=%d frames=%d robot=%s tool=%s foll=%s dofs=%d" % (len(rows), fi, ROBOT, TOOL, FOLL, len(DOFN)))
'''


def _quat_angle(qa, qb):
    """Geodesic angle (deg) between two unit quaternions [w,x,y,z]."""
    if not qa or not qb:
        return 0.0
    d = abs(sum(a * b for a, b in zip(qa, qb)))
    d = max(-1.0, min(1.0, d))
    return math.degrees(2.0 * math.acos(d))


def _qrot_inv(q, v):
    """Rotate world vector v into the frame of quaternion q=[w,x,y,z] (i.e. by q^-1).
    Used to express a grasped object's offset in the EE frame so EE rotation does not
    masquerade as grip slip — a rigidly-held object has a CONSTANT offset in this frame."""
    if not q or not v:
        return v
    w, x, y, z = q
    x, y, z = -x, -y, -z  # conjugate = inverse for a unit quat
    tx = 2.0 * (y * v[2] - z * v[1])
    ty = 2.0 * (z * v[0] - x * v[2])
    tz = 2.0 * (x * v[1] - y * v[0])
    return [v[0] + w * tx + (y * tz - z * ty),
            v[1] + w * ty + (z * tx - x * tz),
            v[2] + w * tz + (x * ty - y * tx)]


def _qmul(a, b):                        # quaternion product [w,x,y,z]
    aw, ax, ay, az = a; bw, bx, by, bz = b
    return [aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw]

def _rel_q(qee, qobj):                  # object orientation IN the EE frame = conj(qee) * qobj
    if not qee or not qobj:
        return None
    return _qmul([qee[0], -qee[1], -qee[2], -qee[3]], qobj)


def _analyse(js):
    rows = js.get("rows", [])
    _BIN_BBOXES = js.get("bin_bboxes", [])   # cont.318i: COLLECTION-bin world bboxes recorded in the Kit (this
    # analysis runs in a CLIENT python WITHOUT omni/stage, so it cannot query the live stage for them).
    if not rows:
        return "no rows"
    dofn = js.get("dof_names") or []
    out = ["rows=%d  dur=%.1fs  tool=%s  dofs=%d" % (len(rows), rows[-1]["t"], js.get("tool"), len(dofn))]

    # tool linear motion -> stepping
    sp = []
    for a, b in zip(rows, rows[1:]):
        pa, pb = a.get("tool_p"), b.get("tool_p")
        dt = max(1e-3, b["t"] - a["t"])
        sp.append((b["t"], (math.dist(pa, pb) / dt) if (pa and pb) else 0.0))
    moving = [s > 0.03 for _, s in sp]
    stopgo = sum(1 for x, y in zip(moving, moving[1:]) if (not x) and y)
    out.append("TOOL peak speed=%.3f m/s   stop-go cycles=%d  (each = a fresh start out of a near-stop = a visible 'step')"
               % (max((s for _, s in sp), default=0.0), stopgo))

    # tool rotation
    rot = []
    for a, b in zip(rows, rows[1:]):
        dt = max(1e-3, b["t"] - a["t"])
        rot.append((b["t"], _quat_angle(a.get("tool_q"), b.get("tool_q")) / dt))
    pk = max(rot, key=lambda x: x[1], default=(0, 0))
    out.append("TOOL peak rotation=%.0f deg/s at t=%.1fs" % (pk[1], pk[0]))

    # joints -> the wandering
    if dofn and rows[0].get("j"):
        nj = len(rows[0]["j"])
        out.append("JOINTS (range over episode + direction reversals):")
        for ji in range(nj):
            vals = [r["j"][ji] for r in rows if r.get("j") and len(r["j"]) > ji]
            if not vals:
                continue
            rng = math.degrees(max(vals) - min(vals))
            rev = 0
            prev = 0
            for a, b in zip(vals, vals[1:]):
                d = b - a
                s = 1 if d > 1e-4 else (-1 if d < -1e-4 else 0)
                if s != 0 and prev != 0 and s != prev:
                    rev += 1
                if s != 0:
                    prev = s
            nm = dofn[ji] if ji < len(dofn) else "j%d" % ji
            out.append("    %-24s range=%6.1f°   reversals=%d" % (nm, rng, rev))
        out.append("    (high wrist reversals = the 'roterande extra rörelser i några omgångar')")
    else:
        out.append("JOINTS: none (articulation init failed)")

    # elongation
    el = [r["elong_mm"] for r in rows if r.get("elong_mm") is not None]
    if el:
        base = sorted(el)[len(el) // 2]  # median = nominal mount offset
        spikes = sorted(((r["t"], r["elong_mm"]) for r in rows if r.get("elong_mm") is not None),
                        key=lambda x: -x[1])[:4]
        out.append("ELONGATION (follower<->cone gap): median=%.1fmm  min=%.1f  max=%.1f  spike=+%.1fmm over nominal"
                   % (base, min(el), max(el), max(el) - base))
        out.append("    top gap moments (t,mm): " + ", ".join("%.1fs:%.0f" % (t, v) for t, v in sorted(spikes)))
    else:
        out.append("ELONGATION: unavailable (no follower/cone)")

    # PLAN EVENTS (from USD-live ctrl: counters) — the CAUSE behind the motion
    if any("pc" in r for r in rows):
        events = []
        prev_pc = prev_pf = 0
        prev_pick = ""
        prev_err = ""
        for r in rows:
            t = r["t"]
            pc, pf = r.get("pc", 0), r.get("pf", 0)
            if pc > prev_pc:
                events.append((t, "plan_pose ×%d (total %d)" % (pc - prev_pc, pc)))
            if pf > prev_pf:
                events.append((t, "PLAN FAIL/replan ×%d (total %d) goal=%s" % (pf - prev_pf, pf, r.get("fgoal", "")[:40])))
            pk = r.get("pick", "")
            if pk and pk != prev_pick:
                events.append((t, "PICKED %s" % pk.split("/")[-1]))
            prev_pick = pk
            er = r.get("err", "")
            if er and er != prev_err:
                events.append((t, "ERR: %s" % er[:60]))
            prev_err = er
            prev_pc, prev_pf = pc, pf
        last = rows[-1]
        out.append("PLAN EVENTS (total plan_calls=%d  plan_fails=%d):" % (last.get("pc", 0), last.get("pf", 0)))
        if events:
            for t, e in events:
                out.append("    t=%5.1fs  %s" % (t, e))
        else:
            out.append("    (no plan-event transitions captured — counters may be unexposed for this controller)")
        out.append("    → align these against the joint reversals + elongation spike above to see which plan caused the swing")

    # EXACT cuRobo PLANNING DATA (the planner's own output, not playback)
    if js.get("plan_fields"):
        out.append("cuRobo RESULT FIELDS (dir(res), this build): " + ", ".join(js["plan_fields"]))
    pl = js.get("plan_log") or []
    if pl:
        out.append("PLANNED TRAJECTORIES (exact cuRobo output — %d plan calls captured):" % len(pl))
        for k, rec in enumerate(pl):
            if not rec.get("success"):
                out.append("    plan#%d  FAIL  goal=%s  status=%s"
                           % (k, [round(x, 2) for x in rec.get("goal", [])], rec.get("status")))
                continue
            tj = rec.get("traj") or []
            jr = []
            if tj and len(tj[0]) >= 6:
                for ji in range(len(tj[0])):
                    col = [knot[ji] for knot in tj]
                    rng = math.degrees(max(col) - min(col))
                    rev = 0
                    prev = 0
                    for a, b in zip(col, col[1:]):
                        d = b - a
                        s = 1 if d > 1e-4 else (-1 if d < -1e-4 else 0)
                        if s != 0 and prev != 0 and s != prev:
                            rev += 1
                        if s != 0:
                            prev = s
                    jr.append((rng, rev))
            mx = max(jr, key=lambda x: x[0]) if jr else (0, 0)
            diag = rec.get("diag") or {}
            out.append("    plan#%d goal=%s mt=%.2fs knots=%d  max-joint-sweep=%.0f°(rev=%d)  status=%s perr=%s rerr=%s"
                       % (k, [round(x, 2) for x in rec.get("goal", [])], rec.get("motion_time", 0), rec.get("knots", 0),
                          mx[0], mx[1], diag.get("status"), diag.get("position_error"), diag.get("rotation_error")))
            if jr:
                out.append("        per-joint planned sweep°: " + " ".join("%.0f" % r for r, _ in jr))
            nm_seeds = diag.get("num_seeds")
            if nm_seeds is not None:
                out.append("        seeds=%s  seed_cost=%s  seed_rank=%s"
                           % (nm_seeds, str(diag.get("seed_cost"))[:80], str(diag.get("seed_rank"))[:60]))
            if diag.get("debug_info"):
                out.append("        debug_info: %s" % str(diag.get("debug_info"))[:200])
        out.append("    → the plan with the big sweep IS the swinging segment — cuRobo's exact intended path, before physics")
    # CONTACTS timeline (grip + arm-vs-scene collisions) — the signal scene_eyes was blind to.
    seen_c = {}; arm_scene = []
    for r in rows:
        for c in (r.get("contacts") or []):
            if "ConveyorBelt" in c: continue
            if c not in seen_c:
                seen_c[c] = r["t"]
                _lo = c.lower()
                if (any(k in _lo for k in ("table", "pedestal", "wall", "base", "bridge")) and
                        any(k in _lo for k in ("link", "forearm", "wrist", "upper_arm", "shoulder", "elbow", "hand", "finger"))):
                    arm_scene.append((r["t"], c))
    if seen_c:
        out.append("CONTACTS (first-seen t; grip + collisions, belt excluded):")
        for c, t in sorted(seen_c.items(), key=lambda kv: kv[1]):
            out.append("    t=%5.1fs  %s" % (t, c))
        if arm_scene:
            out.append("  !! ARM-VS-SCENE COLLISIONS (swing hitting the support surface -> stalls/held-aloft):")
            for t, c in arm_scene:
                out.append("      t=%5.1fs  %s" % (t, c))
    else:
        out.append("CONTACTS: none recorded (check CONTACT_SETUP_FAIL)")

    # GRIP-SLIP — did the grasped object move RELATIVE TO THE EE (true slip) or hold rigid?
    # The position-only gate is BLIND to this: it sees "delivered" but not that the part slipped/pendulumed
    # in the grip. Translation = object offset in the EE frame (rotation-robust via _qrot_inv); drift since
    # grasp-onset = mm of slip. Rotation = object spin minus EE spin since onset = ° of slip. ~0 = rigid hold.
    # Identify the held object from FINGER/CUP contacts (the exact grasp), not proximity — latching the
    # reference during the approach falsely counts the approach-to-grasp transition as slip (caught on a
    # cube control: 121mm phantom slip). Per-row grip set drives both the onset latch and the measure window.
    # SPECIFIC gripper-link tokens — NOT bare "hand": "hand" matched "Handle"/"FaucetHandle", i.e. the
    # GRASPED objects, hiding them from contact-partner detection (broke the broom + faucet grip-slip).
    _GTOK = ("finger", "_cup", "suction_cup", "gripper", "panda_hand", "_sgcone", "follower")
    def _is_grip(n):
        nl = n.lower()
        return any(t in nl for t in _GTOK) or nl in ("cup",)
    _gp = {}; _ginrow = []
    for r in rows:
        s = set()
        for c in (r.get("contacts") or []):
            a, _, b = c.partition("|")
            if _is_grip(a) and not _is_grip(b):
                s.add(b); _gp[b] = _gp.get(b, 0) + 1
            elif _is_grip(b) and not _is_grip(a):
                s.add(a); _gp[a] = _gp.get(a, 0) + 1
        _ginrow.append(s)
    # held object: PREFER the controller's declared grasp target (ctrl:picked_path) — it knows what it
    # grasped; guessing from contact-frequency picks the wrong prim (faucet: FaucetBody one-instant contact
    # beat the real FaucetHandle -> 0.0s span -> false RIGID). Fall back to contact-partner, then suction set.
    held = None
    _tracked = set()
    for r in rows:
        _tracked |= set((r.get("cubes") or {}).keys())
    _picks = [r.get("pick", "").split("/")[-1] for r in rows if r.get("pick")]
    _picks = [p for p in _picks if p and p in _tracked and p in _gp]   # contact-CONFIRMED grasp target
    if _picks:
        from collections import Counter as _Cnt
        held = _Cnt(_picks).most_common(1)[0][0]
    if held is None:
        held = max(_gp, key=_gp.get) if _gp else None   # else the actual finger/cup-contact partner
    if held is None:  # suction (no finger contacts): the SurfaceGripper gripped-set
        for r in rows:
            g = r.get("grp")
            if g and isinstance(g, list) and g:
                held = g[0]; break
    if held:
        # Window = the CONTACT SPAN [first..last finger/cup contact with this object], measured
        # CONTINUOUSLY. Bounding by per-row contact (intermittent reports) under-samples the carry
        # (false RIGID); bounding by proximity counts post-release drift (false SLIP). The span ends at
        # gripper-open (last contact) so a placed object is excluded, and covers the whole carry between.
        gidx = [ri for ri, s in enumerate(_ginrow) if held in s]
        if gidx:
            i0, i1 = gidx[0], gidx[-1]
            onset = rows[i0]["t"]; span_s = rows[i1]["t"] - onset
            p_ee0 = None; qrel0 = None; tq0 = None
            max_t = max_r = max_tt = max_rt = max_ee = 0.0
            for ri in range(i0, i1 + 1):
                r = rows[ri]
                tp, tq = r.get("tool_p"), r.get("tool_q")
                cp = (r.get("cubes") or {}).get(held); cq = (r.get("cubes_q") or {}).get(held)
                if not (tp and cp and tq):
                    continue
                # GRIPPED-CARRY gate (cont.149, multi-case-validated 89-126°->2-14° RIGID across 24+ runs, 0 regr):
                # count slip ONLY while the object is within grasp-distance of the tool (the ~104mm grasp offset +
                # margin). The finger-contact span [i0,i1] over-extends past release — a STACKER's EE re-contacts
                # the placed base cube when stacking the next, and a BIN cube sits world-fixed while the EE leaves;
                # both make qrel drift from EE motion (not slip) -> false SLIPPING. The distance gate bounds the
                # true carry (excludes pre-pick belt-transport [cube far] and post-release EE motion [tool gone]).
                if math.dist(tp, cp) > 0.15:
                    continue
                p_ee = _qrot_inv(tq, [cp[0] - tp[0], cp[1] - tp[1], cp[2] - tp[2]])
                qrel = _rel_q(tq, cq)
                if p_ee0 is None:
                    p_ee0, qrel0, tq0 = p_ee, qrel, tq; continue
                d_mm = math.dist(p_ee, p_ee0) * 1000.0
                if d_mm > max_t:
                    max_t, max_tt = d_mm, r["t"]
                # TRUE relative rotation: object orientation in the EE frame, drift since onset. Reads ~0 when
                # the object turns WITH the gripper and large only on real slip.
                if qrel and qrel0:
                    rs = _quat_angle(qrel, qrel0)
                    if rs > max_r:
                        max_r, max_rt = rs, r["t"]
                ee = _quat_angle(tq, tq0)          # EE's OWN rotation since onset — flags turn/arc tasks
                if ee > max_ee:
                    max_ee = ee
            # ROTATION-slip drives the verdict (validated pick-carry: rigid cube ~3°, slipping broom 143°).
            # EE-self-rot is an INFORMATIONAL caveat, NOT a verdict override: a turn/arc task (esp. a symmetric
            # handle on a revolute joint) rotates the object intentionally, which the slip metric conflates with
            # real slip. But high EE-rot ALSO occurs in a genuine carry+sweep with real pendulum slip (the broom),
            # so it cannot decide the verdict — it only flags "interpret with task knowledge".
            # OUT-OF-SCOPE GUARDS (no false RIGID): the rotation-slip verdict is valid only for a sustained grip
            # on a NON-symmetric object in a pick-carry. A short span = the grip barely formed (unreliable); a
            # SYMMETRIC object (sphere/ball) rolls without changing its tracked quaternion -> rotation-slip is BLIND
            # to it (a rolling sphere reads 0° = false RIGID). Report the limit instead of asserting a hold.
            _sym = any(_t in held.lower() for _t in ("sphere", "ball", "round", "cylinder"))
            # suction robot whose gripped-set is empty the WHOLE run -> the suction never engaged; any finger
            # contact is incidental (the hand near the object), so a RIGID read would be false. This IS the finding.
            _is_suction = any(r.get("gv") is not None for r in rows)
            _ever_gripped = any(r.get("grp") for r in rows)
            if _is_suction and not _ever_gripped:
                verdict = "GRIP NEVER FORMED (suction gripped-set empty all run)"
            elif span_s < 3.0:
                verdict = "inconclusive (grip-span %.1fs too short)" % span_s
            elif _sym:
                verdict = "N/A-symmetric (rotation-slip blind to %s — roll invisible)" % held
            else:
                verdict = ("RIGID HOLD" if max_r < 15 else "SLIPPING" if max_r > 30 else "marginal")
            ee_note = ("  [!] EE-self-rot %.0f° high — if this is a TURN/ARC task, rotation-slip conflates the "
                       "intended rotation with slip (not verdict-grade for turns)" % max_ee) if max_ee > 60 else ""
            out.append("GRIP-SLIP (%s, grip-span t=%.1f-%.1fs %.1fs): rotation-slip=%.0f°@%.1fs  EE-self-rot=%.0f° -> %s   [translation-slip=%.0fmm@%.1fs, incl. grasp/release edges — secondary]%s"
                       % (held, onset, rows[i1]["t"], span_s, max_r, max_rt, max_ee, verdict, max_t, max_tt, ee_note))
            out.append("    (object orientation relative to the EE over the finger/cup-contact span; >~30° = the part rotated out of a rigid couple = pinch-slip/pendulum — the signal the position-only gate cannot see)")
        else:
            _suction_held = any(held in (r.get("grp") or []) for r in rows)
            if _suction_held:
                out.append("GRIP-SLIP: '%s' held via SUCTION cup (raycast grip -> no contact-FORCE rows is EXPECTED for a suction gripper, NOT a slip; see the gripped-set / CONVERGED+GRIPPED verdict above)" % held)
            else:
                out.append("GRIP-SLIP: '%s' identified but no finger/cup-contact rows captured" % held)
    else:
        out.append("GRIP-SLIP: no grasped object identified (no finger/cup contact, no gripped-set)")
    # DEX-HAND FRICTION GRASP (cont.319jj) — the GRIP-SLIP logic above is blind to a 3-finger humanoid hand
    # (no cup/gripped-set -> 'no grasped object'). This detects an HONEST FRICTION grasp from raw signals: a cube
    # is DEX-GRIPPED iff over a sustained window >=2 OPPOSING finger groups (thumb + index/middle) of the SAME
    # hand contact it AND the cube tracks that hand's palm rigidly (cube-minus-palm ~constant) AND it does not
    # fall. Friction-only BY CONSTRUCTION: a FixedJoint cheat holds the cube WITHOUT needing finger contacts, so a
    # FJ-held cube (<2 finger contacts) never registers -> the detector ENFORCES Anton's no-FJ-grip rule.
    _FGROUPS = ("thumb", "index", "middle")
    def _finger_groups(_contacts, _cube, _side):
        _g = set()
        for _c in (_contacts or []):
            if "|" not in _c: continue
            _a, _b = _c.split("|", 1)
            if _cube not in (_a, _b): continue
            _link = (_a if _b == _cube else _b).lower()
            if (_side + "_hand_") in _link:
                for _fg in _FGROUPS:
                    if _fg in _link: _g.add(_fg)
        return _g
    import statistics as _stx
    _dex_cubes = sorted({_nm for _r in rows for _nm in (_r.get("cubes") or {})})
    _dex_any_palm = any((_r.get("palm") or {}) for _r in rows)
    if _dex_cubes and _dex_any_palm:
        for _cube in _dex_cubes:
            _best = None
            for _side in ("left", "right"):
                _caged = []
                for _r in rows:
                    _g = _finger_groups(_r.get("contacts"), _cube, _side)
                    _caged.append(("thumb" in _g) and (("index" in _g) or ("middle" in _g)))
                _bi0 = _bi1 = -1; _k = 0
                while _k < len(_caged):
                    if _caged[_k]:
                        _j = _k
                        while _j < len(_caged) and _caged[_j]: _j += 1
                        if (_j - 1 - _k) > (_bi1 - _bi0): _bi0, _bi1 = _k, _j - 1
                        _k = _j
                    else: _k += 1
                if _bi0 < 0: continue
                _span = rows[_bi1]["t"] - rows[_bi0]["t"]
                _rels = []
                for _r in rows[_bi0:_bi1 + 1]:
                    _cp = (_r.get("cubes") or {}).get(_cube); _pm = (_r.get("palm") or {}).get(_side)
                    if _cp and _pm: _rels.append([_cp[_a] - _pm[_a] for _a in range(3)])
                _follow = (round(1000 * max(_stx.pstdev([_r[_a] for _r in _rels]) for _a in range(3)), 1)
                           if len(_rels) >= 2 else None)
                _zs = [(_r.get("cubes") or {}).get(_cube)[2] for _r in rows[_bi0:_bi1 + 1] if (_r.get("cubes") or {}).get(_cube)]
                _minz = round(min(_zs), 3) if _zs else None
                _cand = {"side": _side, "span": round(_span, 1), "follow": _follow, "minz": _minz}
                if _best is None or _cand["span"] > _best["span"]: _best = _cand
            if _best is None:
                out.append("DEX-GRASP %s: no opposing-finger cage (need thumb + index/middle contact) -> NOT dex-gripped" % _cube)
                continue
            _held = (_best["span"] >= 1.0 and _best["follow"] is not None and _best["follow"] < 30
                     and (_best["minz"] is None or _best["minz"] > 0.5))
            _vd = ("DEX-GRIP (friction, rigid cube-follows-palm)" if _held else
                   ("CAGE-SLIP (caged but cube drifts %smm from palm = friction lost)" % _best["follow"]
                    if (_best["follow"] is not None and _best["follow"] >= 30) else
                    ("CAGE-BRIEF (cage-span %.1fs <1s)" % _best["span"] if _best["span"] < 1.0 else
                     "CAGE-DROP (cube fell to z=%s during cage)" % _best["minz"])))
            out.append("DEX-GRASP %s [%s hand]: cage-span=%.1fs follow=%smm minz=%s -> %s"
                       % (_cube, _best["side"], _best["span"], _best["follow"], _best["minz"], _vd))

    # GRIP FORCE (contact impulse) — a firm 2-finger/cup couple vs a grazing single touch
    _cf = {}
    for r in rows:
        for k, v in (r.get("cforce") or {}).items():
            if v > _cf.get(k, 0):
                _cf[k] = v
    _grip_cf = {k: v for k, v in _cf.items() if any(t in k.lower() for t in ("finger", "cup", "gripper", "hand"))}
    if _grip_cf:
        out.append("GRIP CONTACT FORCE (max impulse/pair, finger/cup contacts):")
        for k, v in sorted(_grip_cf.items(), key=lambda kv: -kv[1])[:6]:
            out.append("    %-42s %.3f" % (k, v))

    # EJECTION / EXPLOSION detector (2026-06-14, Anton's "addera det"): a PhysX over-close blowup (e.g. the
    # parallel jaw over-penetrating a sphere) ejects the object to huge speed/position (CP-44 sphere -> z=-39750).
    # The position-only gate only sees "not delivered"; this NAMES the blowup so grip-physics RCA is one read.
    _ej_objs = set()
    for _r in rows: _ej_objs |= set((_r.get("cubes") or {}).keys())
    _ej = []
    for _nm in sorted(_ej_objs):
        _ps = [(_r["t"], (_r.get("cubes") or {}).get(_nm)) for _r in rows if (_r.get("cubes") or {}).get(_nm)]
        if len(_ps) < 2: continue
        _vmax = 0.0; _vt = _ps[0][0]
        for _aa, _bb in zip(_ps, _ps[1:]):
            _dt = max(1e-3, _bb[0] - _aa[0]); _v = math.dist(_aa[1], _bb[1]) / _dt
            if _v > _vmax: _vmax = _v; _vt = _bb[0]
        _fp = _ps[-1][1]
        # OFFSET-INVARIANT (2026-06-15 fix): in compose mode x/y carry the instance offset (inst1~6.6m,
        # inst2~13m) so an abs-x/y>5 test FALSE-flagged every offset instance as "EXPLODED" (CP-09 inst1).
        # A real PhysX over-penetration blowup shows huge SPEED or absurd Z (CP-44 sphere -> z=-39750); z is
        # never the composition offset axis. So gate explosion on speed + z only, not on x/y world position.
        _exp = (_vmax > 8.0 or _fp[2] < -1.0 or _fp[2] > 5.0)
        if _exp or _vmax > 2.0:
            _ej.append((_nm, _vmax, _vt, _fp, _exp))
    if _ej:
        out.append("EJECTION / EXPLOSION (per-object max sample-speed + final pos; >8 m/s or z<-1/z>5 = PhysX blowup; offset-invariant):")
        for _nm, _vmax, _vt, _fp, _exp in sorted(_ej, key=lambda x: -x[1]):
            out.append("    %-14s vmax=%7.1f m/s @%.1fs  final=[%.2f,%.2f,%.2f]  %s" % (
                _nm, _vmax, _vt, _fp[0], _fp[1], _fp[2], "*** EXPLODED/EJECTED ***" if _exp else "(fast — watch)"))

    # OFF-SURFACE / KNOCK-OFF detector. A genuine knock-off ends NET-BELOW where the object STARTED (it fell
    # off a surface to a lower level / the ground) — e.g. a box knocked off an OPEN pallet (Box_5 start~0.84
    # -> final 0.54 on the Ground). FIX 2026-06-15: the old "fell >=0.10m from PEAK" false-fired on EVERY
    # normal pick-place (the arm lifts the cube to transit height ~1.07 then places it lower = a 0.25m drop
    # from peak on a perfectly good delivery). Use NET descent from START instead; a placed/stacked cube ends
    # at ~start or higher (net <=0), only a real fall ends well below start.
    def _in_any_bin(_p):
        # cont.319jj-8: a cube resting in a recorded COLLECTION bin is NOT knocked-off, even if the bin
        # floor is below the 0.70 working-height (CP-26: Bin floor=0.6 -> cubes settle at z~0.635 and were
        # FALSE-flagged 'fell to floor', while the ORIENTATION detector correctly said 'in bin — collection').
        # Mirror that in-bin logic here so OFF-SURFACE agrees and does not false-negative a low-bin delivery.
        for _bb in _BIN_BBOXES:
            if (_bb[0] - 0.03 <= _p[0] <= _bb[3] + 0.03 and _bb[1] - 0.03 <= _p[1] <= _bb[4] + 0.03
                    and _bb[2] - 0.06 <= _p[2] <= _bb[5] + 0.06):
                return True
        return False
    _off = []
    for _nm in sorted(_ej_objs):
        _zs = [(_r.get("cubes") or {}).get(_nm) for _r in rows if (_r.get("cubes") or {}).get(_nm)]
        if len(_zs) < 3: continue
        _zmax = max(p[2] for p in _zs); _fp = _zs[-1]; _z0 = _zs[0][2]
        _drop = _z0 - _fp[2]   # NET descent from start, not from transit peak
        if _in_any_bin(_fp): continue   # collected in a bin (even a low one) = not knocked-off
        # FIX 2026-06-17 (cont.232): ALSO require the cube to end BELOW working-surface height (~0.70m) to
        # flag. A genuine knock-off falls to a LOWER LEVEL / the ground (e.g. off a pallet -> 0.54, or floor
        # ~0.03). A pick-HIGH/deliver-LOW delivery (pedestal 0.975 -> tray 0.775, or de-palletize) ends DOWN
        # vs start but STILL on a working surface (>=~0.75) -> was a false-positive (CP-CHAIN-UR10-SRC,
        # cont.231: net-fell 0.20m flagged though the cube was CONVERGED+GRIPPED + delivered upright to the
        # tray). Canonical tables are 0.75; 0.70 gives a small margin. Grid->pile (cubes pile at ~table
        # height) is unaffected — that is caught by the z-levels/min-pair detector, not this one.
        if _drop > 0.15 and -1.0 < _fp[2] < 0.70:  # fell >=15cm AND ended below working height = real knock-off
            _off.append((_nm, _zmax, _fp, _drop))
    if _off:
        out.append("OFF-SURFACE / KNOCKED-OFF (fell >=0.15m from START *and* ended below working height ~0.70m = fell to a lower level/floor; intended pick-high/deliver-low drops to a surface are excluded):")
        for _nm, _zmax, _fp, _drop in sorted(_off, key=lambda x: -x[3]):
            out.append("    %-14s peak_z=%.2f -> final=[%.2f,%.2f,%.2f]  net-fell %.2fm from start" % (
                _nm, _zmax, _fp[0], _fp[1], _fp[2], _drop))
    # object-object contacts = place-time collisions that can knock neighbours off (both actors are tracked workpieces)
    _oo = sorted({k for k in _cf if "|" in k and all(p.strip() in _ej_objs for p in k.split("|"))})
    if _oo:
        out.append("OBJECT-OBJECT CONTACTS (place-time collisions — can knock neighbours off a surface): " + ", ".join(_oo[:12]))

    # STACK STRUCTURE (2026-06-15, Anton false-success): a STACKER must end with objects at DISTINCT z-levels
    # (a vertical column, ~0.05 apart per cube). Objects all sharing ONE z = a FLAT SCATTER on the base, which
    # the position-bbox gate counts identically to a built column (CP-09: 5 cubes all final z~0.82 = scatter,
    # NOT a tower; its own faithfulness gate fails 0/4). Names the column-vs-scatter the position gate is blind
    # to. Offset-invariant (z is never the composition offset axis). Read for any stack/pallet template.
    _finals = {}
    for _nm in sorted(_ej_objs):
        _ps2 = [(_r.get("cubes") or {}).get(_nm) for _r in rows if (_r.get("cubes") or {}).get(_nm)]
        if _ps2: _finals[_nm] = _ps2[-1]
    if len(_finals) >= 2:
        _levels = []
        for _z in sorted(p[2] for p in _finals.values()):
            if not _levels or abs(_z - _levels[-1]) > 0.03: _levels.append(_z)
        _fpl = list(_finals.values())
        _minpair = min((math.dist((a[0], a[1]), (b[0], b[1])) for i, a in enumerate(_fpl) for b in _fpl[i + 1:]), default=0.0)
        _xext = max(p[0] for p in _fpl) - min(p[0] for p in _fpl)
        _yext = max(p[1] for p in _fpl) - min(p[1] for p in _fpl)
        out.append("STACK STRUCTURE (%d objs): %d z-level(s) %s | xy-extent=%.2fx%.2fm | min-pair-xy=%.3fm" % (
            len(_finals), len(_levels), [round(x, 3) for x in _levels], _xext, _yext, _minpair))
        # Report observations; the PASS/FAIL verdict depends on the TEMPLATE'S INTENT (the detector can't
        # know it). >=2 z-levels = a real vertical column. 1 z-level = flat: CORRECT for a PALLETIZER grid
        # (Anton 2026-06-15: items must sit with gaps so the gripper fits between them — parallel-jaw needs
        # finger clearance, a SUCTION cup can place flush), but a SCATTER/no-stack FALSE-SUCCESS for a
        # TOWER/column stacker. min-pair-xy separates a spaced grid (gaps present) from a piled/overlapping heap.
        if len(_levels) >= 2:
            out.append("    -> COLUMN / multi-tier vertical structure — consistent with a TOWER/column stacker")
        elif len(_finals) >= 3:
            _kind = "spread grid (gaps present, gripper-clearance ok)" if _minpair > 0.045 else "clustered/piled (overlapping, no clean gaps)"
            out.append("    -> FLAT 1-tier %s. OK for a PALLETIZER; a SCATTER FALSE-SUCCESS for a TOWER/column stacker — judge by template intent." % _kind)

    # SETTLED-Z floor-guard feed (2026-06-17): the gold-gate's low_z floor-check reads STACK STRUCTURE z-levels,
    # which only emit for >=2 objects -> a SINGLE-cube bin delivery had NO floor guard. Once asset-suction grips
    # are correctly recognized (CONVERGED+GRIPPED), a grip-then-drop-to-FLOOR would FALSE-PASS the bin gate.
    # Emit each box-like cube's final settled z (ANY count) so the gate rejects a cube that ended on the ground
    # (the realistic concurrent-cuRobo place-fail -> release-midair -> fall). (predicate mirrors _boxlike below.)
    def _boxlike_z(_n):
        _l = _n.lower()
        return _l.startswith(("cube", "item", "brick")) or any(_k in _l for _k in ("box", "crate", "package", "block", "carton", "parcel", "brick"))
    _szl = [(_nm, _finals[_nm][2]) for _nm in sorted(_finals) if _boxlike_z(_nm)]
    if _szl:
        out.append("SETTLED-Z (box-like delivery cubes, final z m): " + "  ".join("%s=%.3f" % (n, z) for n, z in _szl))

    # ORIENTATION / TOPPLE (2026-06-16, Anton "vaksamma för false success"): a cube delivered to the right XY/Z
    # but resting ON ITS SIDE is NOT correctly placed — the position/bbox gate AND the CONVERGED+GRIPPED count
    # are both blind to it. scene_timeseries already flags this via settled-tilt and it surfaces in the Modal
    # `vec` (TOPPLED), but the LOCAL gold-gate parses scene_eyes' OWN text, which had no upright signal — so a
    # toppled-but-delivered cube passed the local gold-gate. Mirror scene_timeseries exactly: up_z = m22 =
    # 1-2(qx²+qy²) for q=[w,x,y,z]; tilt = acos(up_z). Measure on the SETTLED tail (per-cube speed <0.05 m/s)
    # so transit carry-swing isn't mistaken for a topple; fall back to the final frame. Round items (sphere/
    # ball) roll and have no meaningful up-axis -> skipped. >60° = TOPPLED (a real reject), 30-60° = TILTED (warn).
    def _tilt_of(_q):
        _uz = max(-1.0, min(1.0, 1.0 - 2.0 * (_q[1] ** 2 + _q[2] ** 2)))
        return math.degrees(math.acos(_uz))
    _ori = []
    for _nm in sorted(_ej_objs):
        if any(_k in _nm.lower() for _k in ("sphere", "ball", "round")):
            continue
        _seq = []; _pp = None; _pt = None
        for _r in rows:
            _cp = (_r.get("cubes") or {}).get(_nm); _cq = (_r.get("cubes_q") or {}).get(_nm)
            if not _cp or not _cq: continue
            _sp = (math.dist(_cp, _pp) / (_r["t"] - _pt)) if (_pp is not None and _r["t"] > _pt) else 0.0
            _seq.append((_cq, _sp)); _pp = _cp; _pt = _r["t"]
        if not _seq: continue
        _settled = [_tilt_of(_q) for _q, _sp in _seq if _sp < 0.05]
        _ori.append((_nm, max(_settled) if _settled else _tilt_of(_seq[-1][0])))
    if _ori:
        # The TOPPLED *reject* fires only for box-like objects with an unambiguous canonical upright (cubes/
        # items/boxes/crates/packages/blocks). Elongated graspables (broom/handle/lever/valve/bottle) that
        # scene_eyes also tracks can legitimately rest non-upright -> reporting their tilt is fine, but they
        # must NOT trigger a gold-gate reject (that would be a false-negative on a good composition). Anton's
        # no-graze / no-false-negative discipline. Compositions are cubes, so this is belt-and-suspenders.
        def _boxlike(_n):
            _l = _n.lower()
            return _l.startswith(("cube", "item", "brick")) or any(_k in _l for _k in ("box", "crate", "package", "block", "carton", "parcel", "brick"))
        # DESTINATION-AWARE (2026-06-19, Anton symmetric false-positive directive): a cube TOPPLED but resting
        # INSIDE a COLLECTION container (a prim NAMED Bin/Tote/Hopper/Bucket) is normal COLLECTION, NOT a placement
        # defect -> the reject must not fire (else a genuine bin delivery false-FAILs + the gold-gate parsing this
        # text false-rejects a real bin gold; CP-41 mixed-mass->Bin / CP-52 SharedBin were the catches). Surfaces
        # (Pallet/Shelf/Table) aren't NAMED *Bin -> never recorded -> their topples STAY rejects -> no false-negative.
        # The bin world-bboxes are recorded in the KIT (js["bin_bboxes"]) because THIS analysis runs in a CLIENT
        # python with NO omni/stage (cont.318i: a prior in-analysis stage.Traverse silently NameError'd under a bare
        # except -> the fix never fired -> CP-52 refuted it via RAW; record-in-Kit + a list check is the right shape).
        def _in_deep_container(_pos):
            if not _pos: return False
            for _bb in _BIN_BBOXES:
                _x0, _y0, _z0, _x1, _y1, _z1 = _bb
                if (_x0 - 0.05 <= _pos[0] <= _x1 + 0.05 and _y0 - 0.05 <= _pos[1] <= _y1 + 0.05
                        and _z0 - 0.08 <= _pos[2] <= _z0 + 0.40):
                    return True
            return False
        _binned = {n for n, t in _ori if t > 60 and _boxlike(n) and _in_deep_container(_finals.get(n))}
        _topp = [(n, t) for n, t in _ori if t > 60 and _boxlike(n) and n not in _binned]
        out.append("ORIENTATION (settled cube tilt from world-up; >60°=TOPPLED, 30-60°=TILTED; round items skipped; reject scoped to box-like; in-bin topple = collection, not a reject):")
        for _nm, _t in sorted(_ori, key=lambda x: -x[1]):
            _tag = "TOPPLED" if _t > 60 else "TILTED" if _t > 30 else "upright"
            _sfx = ""
            if _t > 60 and not _boxlike(_nm): _sfx = " (non-box; not a reject)"
            elif _nm in _binned: _sfx = " (in bin — collection, not a reject)"
            out.append("    %-14s tilt=%5.1f°  %s%s" % (_nm, _t, _tag, _sfx))
        if _topp:
            out.append("*** ORIENTATION FAIL: %d object(s) TOPPLED (delivered but tipped >60° from upright = not correctly placed): %s ***" % (
                len(_topp), ", ".join(n for n, _ in _topp)))
            # TILT-ONSET (cont.319-CEV3 diagnostic, Anton "varför är den fragil?"): the settled tilt alone
            # cannot say WHY a cube toppled. Report WHEN each toppled cube crossed 30/60° from world-up + how
            # long it sat SETTLED-UPRIGHT (slow <0.05 m/s AND <30° tilt) before tipping — read from the per-frame
            # pose this analysis already has (rows[*].cubes / cubes_q). The discriminator is the SETTLED-UPRIGHT
            # SPAN before the >60° crossing: a short span (<1s) = a PLACEMENT/RELEASE failure (tipped within ~1s
            # of the hand letting go — the release pose is unstable); a long span (≥1s of slow-and-upright before
            # tipping) = a DRIFT failure (sat correctly placed, then tipped later under load/disturbance). The
            # earlier wording compared to last-upright and mislabeled a release-tip as DRIFT (cont.319-CEV3 fix).
            for _nm, _t in _topp:
                _traj = []  # (t, tilt, speed)
                _pp = None; _pt = None
                for _r in rows:
                    _q = (_r.get("cubes_q") or {}).get(_nm)
                    if not _q:
                        continue
                    _cp = (_r.get("cubes") or {}).get(_nm)
                    _sp = (math.dist(_cp, _pp) / (_r["t"] - _pt)) if (_cp and _pp is not None and _r["t"] > _pt) else 0.0
                    _traj.append((_r["t"], _tilt_of(_q), _sp))
                    if _cp:
                        _pp = _cp; _pt = _r["t"]
                if not _traj:
                    continue
                _c30 = next((tt for tt, tl, _ in _traj if tl > 30), None)
                _c60 = next((tt for tt, tl, _ in _traj if tl > 60), None)
                # frames the cube was slow-AND-upright before it first crossed 60° = the time it was correctly settled
                _su = [tt for tt, tl, sp in _traj if sp < 0.05 and tl < 30 and (_c60 is None or tt < _c60)]
                _span = (max(_su) - min(_su)) if len(_su) >= 2 else 0.0
                _kind = ("PLACEMENT/RELEASE — tipped within %.1fs of settling (unstable release pose)" % _span) if _span < 1.0 \
                    else ("DRIFT — sat settled-upright %.1fs then tipped (later load/disturbance)" % _span)
                out.append("    └─ %s ONSET: first-seen %.0f°@%.1fs  cross30=%s  cross60=%s  settled-upright-span=%.1fs  end=%.1fs  -> %s" % (
                    _nm, _traj[0][1], _traj[0][0],
                    ("%.1fs" % _c30) if _c30 is not None else "never",
                    ("%.1fs" % _c60) if _c60 is not None else "never",
                    _span, _traj[-1][0], _kind))

        # XY-CONTAINMENT (#36, 2026-06-19, Anton false-success discipline): the gold-gate's bin/sort branch had
        # NO check that a delivered object actually ended INSIDE the bin's xy footprint — an object dropped NEXT
        # TO the bin (upright, at floor-z) passed BOTH the floor-guard (it's at floor-z) and the topple-check
        # (upright). Report per box-like delivery object whether its final xy is within a recorded collection-bin
        # footprint (±0.05m, the same margin _in_deep_container uses). INFORMATIONAL only (NO *** FAIL *** marker
        # that other gates auto-consume): the REJECT is CLASS-AWARE and lives in eyes_gold_gate's bin/sort branch
        # — a COMPOSED bin+pallet scene legitimately has the pallet cell's objects OUTSIDE the bin, and scene_eyes
        # tracks ALL cells' objects with no way to tell which cell owns which, so it must NOT auto-reject here.
        if _BIN_BBOXES:
            def _xy_in_bin(_pos):
                if not _pos: return False
                for _bb in _BIN_BBOXES:
                    _x0, _y0, _z0, _x1, _y1, _z1 = _bb
                    if _x0 - 0.05 <= _pos[0] <= _x1 + 0.05 and _y0 - 0.05 <= _pos[1] <= _y1 + 0.05:
                        return True
                return False
            _bl_deliv = [n for n in sorted(_finals) if _boxlike(n)]
            if _bl_deliv:
                out.append("XY-CONTAINMENT (box-like delivery objects vs %d recorded bin footprint(s); 'NO' = settled outside every bin xy):" % len(_BIN_BBOXES))
                for _nm in _bl_deliv:
                    out.append("    %-14s xy-in-bin=%s" % (_nm, "yes" if _xy_in_bin(_finals.get(_nm)) else "NO"))

    # BELT TIMELINE (2026-06-14): belt surface-velocity over the run — pins the PAUSE/RESUME behaviour
    # behind the conveyor-stall class. A belt that stays at 0 most of the run = boxes never advance to the
    # pick zone (the controller pauses the belt during pick phases / while a cube is "imminent"; if it
    # never resumes the boxes stall at spawn). Shows moving-fraction + the first 0<->nominal transitions.
    _bvals = [(_r["t"], _r.get("bsv")) for _r in rows if _r.get("bsv") is not None]
    if _bvals:
        _movf = sum(1 for _, _v in _bvals if abs(_v) > 0.001) / len(_bvals)
        _trans = []; _prev = None
        for _t, _v in _bvals:
            _st = "MOVING" if abs(_v) > 0.001 else "PAUSED"
            if _st != _prev: _trans.append((_t, _st, _v)); _prev = _st
        # dominant feed axis from the last non-zero full vector (axis-agnostic report)
        _axis = "?"
        for _r in reversed(rows):
            _vv = _r.get("bsvv")
            if _vv and any(abs(_c) > 0.001 for _c in _vv):
                _ai = max(range(3), key=lambda _k: abs(_vv[_k]))
                _axis = "%s%s" % ("+-"[_vv[_ai] < 0], "xyz"[_ai]); break
        out.append("BELT TIMELINE (surface-velocity |v|, feed-axis %s; MOVING %.0f%% of run):" % (_axis, _movf * 100))
        out.append("    " + "  ".join("%.0fs:%s(%.2f)" % (_t, _s, _v) for _t, _s, _v in _trans[:14]))
        # cont.310 FALSE-ALARM FIX (decisive test CP-38 12/12 @ dur=200): a correctly SENSOR-GATED belt is
        # mostly-paused BY DESIGN — it pauses during each slow ~15s pick and moves briefly between to advance the
        # next cube, so movf is low (8-14%) EVEN WHEN ALL N CUBES DELIVER. The old `movf<0.25` flag false-alarmed
        # "conveyor-stall" on working belts (it misled a whole breadth pass). A TRUE stall = the belt RARELY
        # RESUMES (boxes stuck at spawn). Distinguish by counting resume events (PAUSED->MOVING transitions).
        _resumes = sum(1 for _i in range(1, len(_trans)) if _trans[_i][1] == "MOVING")
        # HIGH-RESOLUTION (Anton 2026-06-18: false-POSITIVES AND false-NEGATIVES must be caught high-res — an
        # aggregate belt-velocity % lies BOTH ways). The belt's job is to get boxes to the pick zone so they get
        # PROCESSED; the ground truth is the PER-OBJECT outcome (did each box move from spawn?), not movf. A TRUE
        # stall = boxes stuck at spawn (never moved). The false-alarm (cont.310) = boxes delivered despite low movf.
        _o_first, _o_last = {}, {}
        for _r in rows:
            for _onm, _op in (_r.get("cubes") or {}).items():
                if _op:
                    _o_first.setdefault(_onm, _op); _o_last[_onm] = _op
        _moved = sum(1 for _onm in _o_first if _o_last.get(_onm) and math.dist(_o_first[_onm], _o_last[_onm]) > 0.10)
        _movedf = _moved / max(1, len(_o_first))
        if _movf < 0.25 and _resumes < 2 and _movedf < 0.30:
            out.append("    *** BELT STALLED -> rarely resumes (%d) AND %.0f%% of boxes never moved from spawn (high-res per-object): they don't reach the pick zone ***" % (_resumes, _movedf * 100))
        elif _movf < 0.25:
            out.append("    (belt mostly-paused = correct sensor-gating during slow picks [%d resumes]; per-object: %.0f%% of boxes ADVANCED/processed -> NOT a stall; longer dur completes all N)" % (_resumes, _movedf * 100))

    # GRIP-ATTEMPT (2026-06-14, Anton "högupplöst"): per-object, HIGH-RES grip outcome — was each tracked object
    # ever finger/cup-contacted (GRIPPED), and if NOT, how CLOSE did the gripper (tool) get? closest approach
    # <~60mm = NEAR-MISS (e.g. moving-pick: the cube moved during approach, the arm just missed); 60-150mm =
    # approached; >150mm = NEVER really approached (reach / sensor-not-triggered / not-claimed). Distinguishes
    # "missed by a little" from "never tried" PER OBJECT — finer than a never-gripped count.
    _grip_objs = set()
    for _k in _cf:
        if any(_t in _k.lower() for _t in ("finger", "cup")):
            for _p in _k.split("|"):
                if _p.strip() in _ej_objs:
                    _grip_objs.add(_p.strip())
    # AUTHORITATIVE engagement signal: objects the SurfaceGripper ITSELF reported holding at any tick
    # (per-tick `grp`). Asset-suction (short_gripper.usd) grips by RAYCAST -> no finger/cup CONTACT-FORCE
    # row -> the contact-based _grip_objs misses it -> a false 'never-gripped' that eyes_gold_gate then
    # HARD-REJECTS as a partial (false-negative on every genuine UR10 asset-suction delivery, 2026-06-17).
    # Defer to the SG's own gripped-list = ground truth (objects never in `grp` keep their old verdict, so
    # the partial-catching reject is preserved -> no new false-POSITIVE risk).
    _sg_held = set()
    for _r in rows:
        for _h in (_r.get("grp") or []):
            _sg_held.add(_h)
    _ga = []
    _t_end = rows[-1].get("t", 0.0) if rows else 0.0
    for _nm in sorted(_ej_objs):
        _gr = (_nm in _grip_objs) or (_nm in _sg_held)
        _md = None; _mt = None
        for _r in rows:
            _tp = _r.get("tool_p"); _op = (_r.get("cubes") or {}).get(_nm)
            if _tp and _op:
                _dd = math.dist(_tp, _op)
                if _md is None or _dd < _md:
                    _md = _dd; _mt = _r["t"]
        # cont.188: end-of-run object SPEED — distinguishes a STILL-FEEDING / in-transit cube (on a
        # conveyor, not yet at the pick = under-duration) from a genuinely UNREACHABLE one. A never-gripped
        # cube still moving at run-end is an under-duration false-NEGATIVE, NOT a reach-fail (CP-10 @100s:
        # 3 cubes mislabeled "NEVER approached (reach)" were still feeding -> 9/9 GENUINE at full 280s).
        _tail = [(_r["t"], (_r.get("cubes") or {}).get(_nm)) for _r in rows if _r.get("t", 0.0) >= _t_end - 1.0]
        _tail = [(t, p) for t, p in _tail if p]
        _endmv = (math.dist(_tail[-1][1], _tail[0][1]) / (_tail[-1][0] - _tail[0][0])) \
            if (len(_tail) >= 2 and _tail[-1][0] - _tail[0][0] > 1e-3) else 0.0
        _ga.append((_nm, _gr, _md, _mt, _endmv))
    if any(not g[1] for g in _ga):   # report when something was never gripped (the interesting case)
        out.append("GRIP-ATTEMPT (per-object; gripped? else closest gripper-to-object approach):")
        for _nm, _gr, _md, _mt, _endmv in sorted(_ga, key=lambda x: (x[1], x[2] if x[2] is not None else 9.0)):
            if _gr:
                out.append("    %-14s GRIPPED" % _nm)
            elif _md is not None:
                if _endmv > 0.03:   # still moving at run-end = feeding / in-transit, NOT unreachable
                    _tag = "STILL IN MOTION @ end (%.2f m/s -> under-duration/feeding, NOT a reach-fail)" % _endmv
                else:
                    _tag = ("NEAR-MISS (moving-pick? cube moved during approach)" if _md < 0.06
                            else "approached but not gripped" if _md < 0.15
                            else "NEVER approached (reach / sensor-not-triggered / not-claimed)")
                out.append("    %-14s never-gripped  closest tool approach=%4.0fmm @%5.1fs  %s" % (_nm, _md * 1000, _mt or 0, _tag))
            else:
                out.append("    %-14s never-gripped  (no tool/pos data)" % _nm)

    # PICK CONVERGENCE (2026-06-14, Anton "högupplöst" — new first-class detector): for objects the controller
    # CLAIMED (ctrl:picked_path), did the arm actually CONVERGE on them? Splits the closest EE-approach into
    # vertical (dz) vs horizontal (dxy) gap (height-target vs lateral-reach) and synthesises a verdict against
    # arm motion magnitude: FROZEN (barely moved — handle/gate stuck), THRASH-NO-CONVERGE (moved a lot but never
    # closed the gap — RmpFlow/IK can't settle or target unreachable), NEAR-MISS (just short — grip/target-z),
    # CONVERGED. Surfaces the hard-frontier signature "arm thrashes but never grips" that closest-mm alone hides.
    _claimed = []
    for _r in rows:
        _pp = (_r.get("pick") or "").strip()
        if _pp:
            _bn = _pp.split("/")[-1]
            if _bn and _bn not in _claimed:
                _claimed.append(_bn)
    if _claimed:
        _arm_rng = 0.0; _arm_rev = 0
        for _ji in range(nj):
            _vals = [r["j"][_ji] for r in rows if r.get("j") and len(r["j"]) > _ji]
            if not _vals:
                continue
            _nmj = (dofn[_ji] if _ji < len(dofn) else "")
            if "finger" in _nmj.lower():
                continue
            _arm_rng = max(_arm_rng, math.degrees(max(_vals) - min(_vals)))
            _pv = 0
            for _a, _b in zip(_vals, _vals[1:]):
                _s = 1 if _b - _a > 1e-4 else (-1 if _b - _a < -1e-4 else 0)
                if _s != 0 and _pv != 0 and _s != _pv:
                    _arm_rev += 1
                if _s != 0:
                    _pv = _s
        out.append("PICK CONVERGENCE (claimed-pick objects; did the arm settle on what it claimed?):")
        out.append("    arm motion: max-joint-range=%.0f°  arm-reversals=%d" % (_arm_rng, _arm_rev))
        for _bn in _claimed:
            _best = None
            for _r in rows:
                _tp = _r.get("tool_p"); _op = (_r.get("cubes") or {}).get(_bn)
                if _tp and _op:
                    _dd = math.dist(_tp, _op)
                    if _best is None or _dd < _best[0]:
                        _best = (_dd, _r["t"], abs(_tp[2] - _op[2]), math.dist(_tp[:2], _op[:2]))
            if _best is None:
                out.append("    %-14s CLAIMED but no tool/pos data" % _bn); continue
            _dd, _tt, _dz, _dxy = _best
            # _grp = engaged by EITHER a finger/cup contact-force row OR the SurfaceGripper's own gripped-list
            # (_sg_held; asset-suction raycast-grips have no contact-force row). The cont.120 LIFT guard below
            # (_held = _grp and _lifted) still gates the "GRIPPED" verdict, so a phantom SG-report that never
            # lifts the object does NOT read as held -> no false-positive (2026-06-17).
            _grp = (_bn in _grip_objs) or (_bn in _sg_held)
            # 2026-06-16: "GRIPPED" must mean the grasp actually PICKED THE OBJECT UP, not a momentary
            # finger-touch. A grasp that contacts then SLIPS never lifts the object (cont.120: a 0.3s
            # contact at the cube TOP EDGE dz=137mm read "CONVERGED + GRIPPED" while the cube never rose
            # off the belt + fell — a false-positive that masked the premature-close failure). Require the
            # object to have been LIFTED above its start height. Uses LIFT (not net-fall), so a normal
            # low-bin place (object lifted, then set DOWN low) still reads as held — no false GRIP-SLIP.
            _ozs = [p[2] for p in ((_rr.get("cubes") or {}).get(_bn) for _rr in rows) if p]
            _lifted = bool(_ozs) and (max(_ozs) - _ozs[0]) > 0.03
            _held = _grp and _lifted
            if _held or _dd < 0.03:
                if _held:
                    _verd = "CONVERGED + GRIPPED"
                elif _grp:   # finger-contact + converged but the object never came off the surface = slip
                    _verd = "CONVERGED + GRIP-SLIP (seat dz=%.0fmm — finger-contact, object NEVER LIFTED, not held)" % (_dz * 1000)
                else:
                    _verd = "CONVERGED"
            elif _grp:       # contacted but never converged-close AND never lifted = marginal-contact slip
                _verd = "GRIP-SLIP (seat dz=%.0fmm — contact, never lifted)" % (_dz * 1000)
            elif _dd < 0.10:
                _verd = "NEAR-MISS (just short — grip/target-z tuning)"
            elif _arm_rng > 60:
                _verd = "THRASH-NO-CONVERGE (arm moved a lot but never closed the gap — IK/RmpFlow can't settle / target unreachable)"
            elif _arm_rng < 15:
                _verd = "FROZEN (arm barely moved — controller/handle/gate stuck)"
            else:
                _verd = "STALL (partial motion, never reached)"
            out.append("    %-14s closest=%4.0fmm (dz=%4.0fmm dxy=%4.0fmm) @%5.1fs  -> %s" % (_bn, _dd * 1000, _dz * 1000, _dxy * 1000, _tt, _verd))

    # GRIP TIMELINE — THE grip-release signal: SurfaceGripper status (0=Open 1=Closing 2=Closed) + gripped set
    # + cup<->gripped-cube distance + max joint velocity, logged at every transition. If status falls to 0 (or the
    # gripped set empties) MID-TRANSIT while cup-cube_d just exceeded maxGripDistance -> the grip auto-RELEASED on
    # distance (candidate b). If it falls while jvmax spiked but d small -> speed/contact knocked it (candidate a/c).
    import math as _mm
    grows = [r for r in rows if r.get("gv") is not None]
    if grows:
        props = js.get("gripper_props")
        out.append("GRIP TIMELINE (status 0=Open 1=Closing 2=Closed; SG props[maxGripDist,coaxF,shearF]=%s):" % props)
        _prev = None
        for r in grows:
            gv = r.get("gv"); s = (gv[0] if gv else None)
            grp = r.get("grp") or []
            cup = r.get("cup_p"); d = None; cz = None
            if cup and grp:
                cp = (r.get("cubes") or {}).get(grp[0])
                if cp: d = round(_mm.dist(cup, cp), 3); cz = round(cp[2], 3)
            jv = r.get("jv") or []
            jvmax = round(max([abs(x) for x in jv], default=0.0), 2)
            key = (s, tuple(grp))
            if key != _prev:
                out.append("    t=%5.1fs  status=%s gripped=%s  cup-cube_d=%s cubeZ=%s  jvmax=%.2f rad/s"
                           % (r["t"], s, grp, d, cz, jvmax))
                _prev = key
        _held = [r for r in grows if r.get("grp")]
        if _held:
            out.append("    -> LAST tick with a gripped object: t=%.1fs (after this the cube is free)." % _held[-1]["t"])
        else:
            out.append("    -> NO tick ever reported a gripped object (grip never latched, or GripperView blind to this SG).")
    return "\n".join(out)


def _contact_sheet(js):
    try:
        from PIL import Image, ImageDraw
    except Exception as e:
        return "PIL unavailable: %r" % e
    frames = sorted(f for f in os.listdir(OUT) if f.startswith("f") and f.endswith(".png"))
    if not frames:
        return "no frames captured"
    rows = js.get("rows", [])
    n = len(frames)
    thumbs = []
    for k, fn in enumerate(frames):
        try:
            im = Image.open(os.path.join(OUT, fn)).convert("RGB")
        except Exception:
            continue
        im.thumbnail((420, 300))
        ridx = min(len(rows) - 1, int(k / max(1, n - 1) * (len(rows) - 1))) if rows else 0
        t = rows[ridx]["t"] if rows else 0.0
        el = rows[ridx].get("elong_mm") if rows else None
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, im.width, 16], fill=(0, 0, 0))
        d.text((3, 3), "f%d t=%.1fs gap=%smm" % (k, t, ("%.0f" % el) if el is not None else "?"), fill=(0, 255, 0))
        thumbs.append(im)
    if not thumbs:
        return "no thumbs"
    cols = 6
    rws = (len(thumbs) + cols - 1) // cols
    tw, th = thumbs[0].width, thumbs[0].height
    sheet = Image.new("RGB", (cols * tw, rws * th), (20, 20, 20))
    for k, im in enumerate(thumbs):
        sheet.paste(im, ((k % cols) * tw, (k // cols) * th))
    sp = os.path.join(OUT, "sheet.png")
    sheet.save(sp)
    return sp


async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    if not ATTACH and COMPOSE:
        # COMPOSED multi-instance scene: build via compose_canonicals, then the probe
        # (focused on EYES_FOCUS, default inst1) observes that cell's robot + objects.
        from service.isaac_assist_service.chat.canonical_instantiator import compose_canonicals
        await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
        await kit_tools.exec_sync(
            "import builtins\nbuiltins._eyes_plan_capture=True\nbuiltins._eyes_plan_log=[]\n"
            "try:\n    del builtins._eyes_plan_fields\nexcept Exception:\n    pass\n", timeout=15)
        _names = [s.split("@")[0] for s in COMPOSE_SPECS]
        _tpls = [json.load(open(f"{REPO}/workspace/templates/{n}.json")) for n in _names]
        if any("@" in s for s in COMPOSE_SPECS):
            _offs = [_parse_compose(s, i)[1] for i, s in enumerate(COMPOSE_SPECS)]   # explicit override
        else:
            # AUTO scene-extent-aware spacing (layout_solver) — must match compose_gate so the
            # eye observes the SAME geometry the gate measures; the hardcoded 2.5*idx reproduced
            # the very belt-overlap bug this tool is meant to diagnose (cont.62-63/68).
            from service.isaac_assist_service.chat.composer import compute_layout_offsets
            _lo = compute_layout_offsets(_tpls)
            _offs = [o["offset"] for o in _lo]
            print("LAYOUT_SOLVER offsets: " + ", ".join("%s@%s" % (n, o) for n, o in zip(_names, _offs)))
        compose_arg = [(_tpls[i], f"inst{i}", _offs[i]) for i in range(len(_names))]
        cb = await asyncio.wait_for(compose_canonicals(compose_arg), timeout=900)
        print("COMPOSE_BUILT instances=%d focus=%s" % (cb.get("n_instances", 0), FOCUS))
        if os.environ.get("SIMCLOCK") == "1":
            # SimClock gate-ON (compose path): the gate is checked LIVE in the controller, so injecting
            # after the build still takes effect. Trajectory playback then times by SIM-time (_clock_now).
            await kit_tools.exec_sync("import builtins\nbuiltins._use_sim_clock=True\n", timeout=10)
            print("FLAG_SET _use_sim_clock=True")
    elif not ATTACH:
        from service.isaac_assist_service.chat.canonical_instantiator import (
            execute_template_canonical, settle_after_canonical)
        tpl = json.load(open(f"{REPO}/workspace/templates/{TPL}.json"))
        await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
        # enable cuRobo plan-capture BEFORE the handler plans (during build/settle/play)
        await kit_tools.exec_sync(
            "import builtins\nbuiltins._eyes_plan_capture=True\nbuiltins._eyes_plan_log=[]\n"
            "try:\n    del builtins._eyes_plan_fields\nexcept Exception:\n    pass\n", timeout=15)
        # gated UR10 experiment flags (test a fix without editing the handler)
        for _flag in ("--posonly", "--oritol", "--cspace", "--transitarc", "--assetgripper"):
            if _flag in OPTS:
                _bn = {"--posonly": "_ur10_pos_only", "--oritol": "_ur10_ori_tol",
                       "--cspace": "_ur10_plan_cspace", "--transitarc": "_ur10_transit_arc",
                       "--assetgripper": "_sg_use_asset_gripper"}[_flag]
                await kit_tools.exec_sync("import builtins\nbuiltins.%s=True\n" % _bn, timeout=10)
                print("FLAG_SET %s" % _bn)
        # 2026-06-06: CUP_ALIGN env sets the asset-gripper cup-align mount angle (default -110) for A/B observation.
        _ca = os.environ.get("CUP_ALIGN")
        if _ca:
            await kit_tools.exec_sync("import builtins\nbuiltins._sg_cup_align_deg=%s\n" % _ca, timeout=10)
            print("FLAG_SET _sg_cup_align_deg=%s" % _ca)
        _de = os.environ.get("DESCEND_EXTRA")
        if _de:
            await kit_tools.exec_sync("import builtins\nbuiltins._sg_asset_descend_extra=%s\n" % _de, timeout=10)
            print("FLAG_SET _sg_asset_descend_extra=%s" % _de)
        if os.environ.get("CUPFRAME") == "1":
            await kit_tools.exec_sync("import builtins\nbuiltins._ur10_cupframe_down=True\n", timeout=10)
            print("FLAG_SET _ur10_cupframe_down=True")
        if os.environ.get("CUPFRAME") == "0":
            await kit_tools.exec_sync("import builtins\nbuiltins._ur10_cupframe_down=False\n", timeout=10)
            print("FLAG_SET _ur10_cupframe_down=False")
        if os.environ.get("NVCUP") == "1":
            await kit_tools.exec_sync("import builtins\nbuiltins._sg_nvidia_cup=True\n", timeout=10)
            print("FLAG_SET _sg_nvidia_cup=True")
        if os.environ.get("MCUBEOBS") == "0":
            await kit_tools.exec_sync("import builtins\nbuiltins._ur10_multicube_obs=False\n", timeout=10)
            print("FLAG_SET _ur10_multicube_obs=False")
        if os.environ.get("REACHPROBE")=="1":
            await kit_tools.exec_sync("import builtins\nbuiltins._reach_probe=True\nbuiltins._reach_probe_done=False\n", timeout=10)
            print("FLAG_SET _reach_probe=True")
        if os.environ.get("GRIPLOG")=="1":
            await kit_tools.exec_sync("import builtins\nbuiltins._sg_grip_log=True\n", timeout=10)
            print("FLAG_SET _sg_grip_log=True")
        if os.environ.get("GOALOFF"):
            await kit_tools.exec_sync("import builtins, json\nbuiltins._sg_nvidia_goal_off=json.loads('%s')\n" % os.environ["GOALOFF"], timeout=10)
            print("FLAG_SET _sg_nvidia_goal_off=%s" % os.environ["GOALOFF"])
        if os.environ.get("NUDGEMAX"):
            await kit_tools.exec_sync("import builtins\nbuiltins._sg_nvidia_nudge_max=%s\n" % os.environ["NUDGEMAX"], timeout=10)
            print("FLAG_SET _sg_nvidia_nudge_max=%s" % os.environ["NUDGEMAX"])
        if os.environ.get("TELEDESCEND") == "1":
            await kit_tools.exec_sync("import builtins\nbuiltins._ur10_telescope_descend=True\n", timeout=10)
            print("FLAG_SET _ur10_telescope_descend=True")
        if os.environ.get("SIMCLOCK") == "1":
            # SimClock gate-ON: trajectory playback times by SIM-time (_clock_now) instead of wall-clock.
            await kit_tools.exec_sync("import builtins\nbuiltins._use_sim_clock=True\n", timeout=10)
            print("FLAG_SET _use_sim_clock=True")
        _rp = os.environ.get("REPOINT")
        if _rp:
            await kit_tools.exec_sync("import builtins\nbuiltins._sg_descend_repoint_deg=%s\n" % _rp, timeout=10)
            print("FLAG_SET _sg_descend_repoint_deg=%s" % _rp)
        if os.environ.get("MULTIOBS") == "0":
            await kit_tools.exec_sync("import builtins\nbuiltins._ur10_multicube_obs=False\n", timeout=10)
            print("FLAG_SET _ur10_multicube_obs=False")
        for _ev,_bn in (("IKSEEDS","_ur10_ik_seeds"),("TRAJSEEDS","_ur10_trajopt_seeds"),("GRIPZOFF","_sg_nvidia_grip_z_off"),("CUPBELOW","_sg_nvidia_cup_below_ee"),("ORITOL","_ur10_ori_tol"),("ZOFF","_reach_probe_z_off"),("CHAINSEED","_ur10_chained_drop_seed"),("CSPACE","_ur10_plan_cspace"),("DROPPIN","_ur10_drop_branch_pin"),("JOINTSPACE","_ur10_jointspace_transit"),("JSIGN","_ur10_jointspace_sign"),("POSONLY","_ur10_transit_posonly"),("JAWDROPTIP","_jaw_drop_tip_release")):
            _vv=os.environ.get(_ev)
            if _vv:
                await kit_tools.exec_sync("import builtins\nbuiltins.%s=%s\n" % (_bn,_vv), timeout=10)
                print("FLAG_SET %s=%s" % (_bn,_vv))
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"):
            print("BUILD_FAIL", str(b.get("errors"))[:400]); return
        try:
            await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
        except Exception:
            pass
    try: os.remove(os.path.join(OUT, "eyes.json"))  # drop any stale json so a failed run can't read old data
    except Exception: pass
    raw = (_KIT.replace("__OUT__", OUT).replace("__DUR__", repr(DUR))
           .replace("__NFRAMES__", repr(NFRAMES)).replace("__FRAMES__", repr(FRAMES))
           .replace("__FOCUS__", FOCUS).replace("__TPL__", TPL))
    # Tolerate exec_sync timeout/RPC error: the loop dumps eyes.json INCREMENTALLY, so even a timed-out long
    # play leaves partial data on disk. Read whatever exists instead of a blind NO_EYES_JSON.
    try:
        r = await asyncio.wait_for(kit_tools.exec_sync(raw, timeout=int(DUR) + 200), timeout=int(DUR) + 220)
        out = r.get("output") or ""
    except Exception as _ee:
        out = ""; print("EXEC_TIMEOUT_OR_ERR", repr(_ee)[:120], "-> reading partial eyes.json")
    for l in out.splitlines():
        if any(k in l for k in ("EYES_DONE", "JOINTS_UNAVAIL", "ART_INIT_FAIL", "CAM_FAIL", "CAP_FAIL", "BUILD_FAIL")):
            print(l)
    try:
        js = json.load(open(os.path.join(OUT, "eyes.json")))
        if js.get("partial"): print("PARTIAL eyes.json (%d rows, exec did not finish cleanly)" % len(js.get("rows") or []))
    except Exception as e:
        print("NO_EYES_JSON", e); return
    print("=== MOTION ANALYSIS ===")
    print(_analyse(js))
    if FRAMES:
        print("=== CONTACT SHEET ===")
        print(_contact_sheet(js))
    print("OUT_DIR", OUT)


asyncio.run(main())
