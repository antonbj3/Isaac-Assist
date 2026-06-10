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
TPL = ARGS[0] if ARGS else "CP-69"
DUR = float(ARGS[1]) if len(ARGS) > 1 else 40.0
NFRAMES = int(ARGS[2]) if len(ARGS) > 2 else 16
FRAMES = "--noframes" not in OPTS
ATTACH = "--attach" in OPTS
OUT = f"/home/anton/.isaac_qa/run/eyes/{TPL}"

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

ROBOT = None
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
    if _gp.endswith("_ShortGripper/suction_cup"): CUP = _gp; break
TOOL = CONE or FOLL or CUP or EE   # tool proxy: cone/cup is USD-live (tracks the suction tip)

def xform(p):
    pr = stage.GetPrimAtPath(Sdf.Path(p)) if p else None
    if not (pr and pr.IsValid()): return None
    m = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0)
    t = m.ExtractTranslation(); q = m.ExtractRotationQuat(); im = q.GetImaginary()
    return ([round(float(t[0]), 4), round(float(t[1]), 4), round(float(t[2]), 4)],
            [round(float(q.GetReal()), 4), round(float(im[0]), 4), round(float(im[1]), 4), round(float(im[2]), 4)])

CUBES = [str(pr.GetPath()) for pr in stage.Traverse() if pr.GetName().startswith("Cube") or pr.GetName().startswith("Item")]  # 2026-06-06: track dispenser Item_* (CP-71) too, not just Cube_*

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
_contacts = set()
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
            try: _contacts.add((str(PhysicsSchemaTools.intToSdfPath(_ch.actor0)).split("/")[-1], str(PhysicsSchemaTools.intToSdfPath(_ch.actor1)).split("/")[-1]))
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
        cubes = {}
        for c in CUBES:
            cx = xform(c); cubes[c.split("/")[-1]] = (cx[0] if cx else None)
        cupx = xform(CUP) if CUP else None
        _w3 = xform("/World/UR10/wrist_3_link")
        rows.append({"t": round(i / 60.0, 2),
                     "tool_p": (tool[0] if tool else None), "tool_q": (tool[1] if tool else None),
                     "w3_p": (_w3[0] if _w3 else None), "w3_q": (_w3[1] if _w3 else None),
                     "cup_p": (cupx[0] if cupx else None), "cup_q": (cupx[1] if cupx else None),
                     "foll_p": (foll[0] if foll else None), "elong_mm": elong,
                     "j": jpos(), "jv": jvel(), "gv": gstat(), "grp": gripped(), "cubes": cubes,
                     "pc": int(cattr("ctrl:plan_calls", 0)), "pf": int(cattr("ctrl:plan_fails", 0)),
                     "pick": str(cattr("ctrl:picked_path", "")), "err": str(cattr("ctrl:last_error", "")),
                     "fgoal": str(cattr("ctrl:last_fail_goal", "")),
                     "contacts": sorted(["%s|%s" % (a, c) for (a, c) in _contacts])})
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
json.dump({"template": "__TPL__", "robot": ROBOT, "ee": EE, "cone": CONE, "follower": FOLL,
           "tool": TOOL, "dof_names": DOFN, "rows": rows, "nframes": fi, "gripper_props": gprops(), "sg_path": _SGPATH,
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


def _analyse(js):
    rows = js.get("rows", [])
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
    if not ATTACH:
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
        _rp = os.environ.get("REPOINT")
        if _rp:
            await kit_tools.exec_sync("import builtins\nbuiltins._sg_descend_repoint_deg=%s\n" % _rp, timeout=10)
            print("FLAG_SET _sg_descend_repoint_deg=%s" % _rp)
        if os.environ.get("MULTIOBS") == "0":
            await kit_tools.exec_sync("import builtins\nbuiltins._ur10_multicube_obs=False\n", timeout=10)
            print("FLAG_SET _ur10_multicube_obs=False")
        for _ev,_bn in (("IKSEEDS","_ur10_ik_seeds"),("TRAJSEEDS","_ur10_trajopt_seeds"),("GRIPZOFF","_sg_nvidia_grip_z_off"),("CUPBELOW","_sg_nvidia_cup_below_ee"),("ORITOL","_ur10_ori_tol"),("ZOFF","_reach_probe_z_off"),("CHAINSEED","_ur10_chained_drop_seed"),("CSPACE","_ur10_plan_cspace"),("DROPPIN","_ur10_drop_branch_pin"),("JOINTSPACE","_ur10_jointspace_transit"),("JSIGN","_ur10_jointspace_sign"),("POSONLY","_ur10_transit_posonly")):
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
           .replace("__TPL__", TPL))
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
