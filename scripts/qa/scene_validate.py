#!/usr/bin/env python3
"""Scene constraint validator — detect constraint violations in an LLM-generated
canonical BEFORE it wastes a sim run. Builds + settles the scene, then reads the
ACTUAL prim geometry (post-settle, in Kit) and checks the three classes that
recur in LLM-generated scenes (hand-patched one-by-one until now):

  REACH        — each pick object within the robot arm's reachable shell
                 (3D distance vs ROBOT_REACH + a vertical z-window relative to
                 the base; an arm can't reach far below its own mount).
  INTERPENETRATION — pick objects clumped / overlapping each other in 3D
                 (the dispenser-clump class: N cubes collapsed into one point).
  SUPPORT      — each pick object rests on a surface (not floating in air, not
                 buried below a surface top).

This is the POST-SETTLE / actual-scene gap: the existing validators
(ContactReachabilityValidator, BlueprintValidator) work on synthetic geometry /
blueprints PRE-build and miss emergent violations (a clump only appears after
the cubes fall). Reach math + ROBOT_REACH mirror handlers/diagnostics.py
verify_pickplace_pipeline so the verdict matches the controller's own reach gate.

Usage: scene_validate.py <TEMPLATE> [TEMPLATE2 ...]
Exit 0 if all clean; prints a per-template VIOLATIONS report. Read-only on the scene.
"""
import asyncio, json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPLS = sys.argv[1:] or ["CP-71"]

# Mirror handlers/resolve._ROBOT_REACH_M (used by verify_pickplace_pipeline) so this matches the
# controller's own reach gate. 2026-06-05 review fix: was ur10=1.20 (too tight → false-positives on
# UR10 cubes at 1.2-1.3 m) and franka=0.85; the handler uses ur10/ur10e=1.30, franka_panda=0.855.
ROBOT_REACH = {"ur10": 1.30, "ur10e": 1.30, "franka": 0.855, "franka_panda": 0.855, "cobotta": 0.95,
               "ur5": 0.85, "ur5e": 0.85, "kinova": 0.902, "ur10_long_suction": 1.30, "default": 0.80}


async def validate(tpl_name):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical, settle_after_canonical)
    tpl = json.load(open(f"{REPO}/workspace/templates/{tpl_name}.json"))
    sa = tpl.get("simulate_args", {}) or {}
    va = tpl.get("verify_args", {}) or {}
    # pick objects: prefer the declared source/cube paths; fall back to scanning.
    picks = (sa.get("cube_paths") or sa.get("source_paths")
             or ([sa.get("cube_path")] if sa.get("cube_path") else None)
             or ([va.get("cube_path")] if va.get("cube_path") else None) or [])
    picks = [p for p in picks if p]
    # delivery targets (place location must ALSO be reachable). target_path is the
    # bin/pallet/handoff; check it against the nearest robot's reachable shell.
    targets = (sa.get("target_paths") or ([sa.get("target_path")] if sa.get("target_path") else None)
               or ([va.get("target_path")] if va.get("target_path") else None) or [])
    targets = [t for t in targets if t]
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        print(f"{tpl_name}: BUILD_FAIL {str(b.get('errors'))[:160]}"); return
    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception:
        pass
    code = r'''
import omni.usd, math, omni.timeline, omni.kit.app, builtins
from pxr import Sdf, UsdGeom, UsdPhysics
stage = omni.usd.get_context().get_stage()
PICKS = __PICKS__
TARGETS = __TARGETS__
REACH = __REACH__
# UNSUBSCRIBE the pick controller so the arm stays at HOME while we settle (otherwise the arm moves -> the
# whole-robot bbox shifts -> wrong base; and the controller would pick/move the items before we read them).
for _k in [k for k in vars(builtins) if k.endswith("_pp_sub_") or "_pp_sub_" in k]:
    try:
        _s = getattr(builtins, _k)
        if _s is not None and hasattr(_s, "unsubscribe"): _s.unsubscribe()
        delattr(builtins, _k)
    except Exception: pass
# Capture belt surface velocities NOW (authored value) -- the controller's belt-pause callback zeros them during
# the settle play below, which would hide a real conveyor from the reach check.
_belt_cap = {}
for _p in stage.Traverse():
    _a = _p.GetAttribute("physxSurfaceVelocity:surfaceVelocity")
    if _a and _a.IsDefined():
        _v = _a.Get()
        if _v and (abs(float(_v[0]))+abs(float(_v[1]))) > 0.05:
            _belt_cap[_p.GetPath().pathString] = [float(_v[0]), float(_v[1])]
# Capture pre-settle pick positions so we can detect a PHYSICS EXPLOSION during the settle play (parts that spawn
# overlapping a bin/table get violently ejected -> they fly metres away; reading their post-settle pos as "out of
# reach" hides the TRUE root, which is the instability). Compare to post-settle below.
_pre_pos = {}
for _pp in PICKS:
    _pr = stage.GetPrimAtPath(Sdf.Path(_pp))
    if _pr and _pr.IsValid():
        try:
            _t0 = UsdGeom.Xformable(_pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
            _pre_pos[_pp] = [float(_t0[0]), float(_t0[1]), float(_t0[2])]
        except Exception: pass
# Settle PASSIVE dynamics (items fall onto their support + clumps form) with the arm parked. ~2.5 s.
try:
    omni.timeline.get_timeline_interface().play()
    _app = omni.kit.app.get_app()
    for _ in range(150): _app.update()
except Exception:
    pass

def aabb(path):
    p = stage.GetPrimAtPath(Sdf.Path(path))
    if not (p and p.IsValid()): return None
    try:
        r = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
        if r.IsEmpty(): return None  # degenerate/empty bound -> GetMin/Max return ±FLT_MAX sentinels (garbage)
        mn, mx = r.GetMin(), r.GetMax()
        out = [float(mn[0]),float(mn[1]),float(mn[2])], [float(mx[0]),float(mx[1]),float(mx[2])]
        # reject FLT_MAX-poisoned coords (an empty sub-bound that slipped through IsEmpty) — not real geometry
        if any(abs(v) > 1e6 for v in out[0]+out[1]): return None
        return out
    except Exception:
        return None

def center(bb): return [(bb[0][i]+bb[1][i])/2.0 for i in range(3)]

# Detect ALL robots (multi-arm scenes attribute each pick/target to its NEAREST arm; the old
# single-robot pick used one base for every pick -> false flags when the 2nd arm owns a far cube).
def _base_of(path):
    # base = robot prim's TRANSFORM ORIGIN (the fixed mount point), NOT bbox center (the arm inflates bbox).
    try:
        _t = UsdGeom.Xformable(stage.GetPrimAtPath(Sdf.Path(path))).ComputeLocalToWorldTransform(0).ExtractTranslation()
        return [float(_t[0]), float(_t[1]), float(_t[2])]
    except Exception:
        rb = aabb(path)
        return [(rb[0][0]+rb[1][0])/2.0, (rb[0][1]+rb[1][1])/2.0, rb[0][2]] if rb else [0.0,0.0,0.75]
ROBOTS = []  # [{path, family, base, reach}]
_seen_robot = set()
# gripper sub-prims (UR10_SGFollower / UR10_SGCone / *_ShortGripper) match the family-name heuristic but are NOT
# arms — they'd add a phantom robot at the tool height and mis-attribute targets. Exclude unless ArticulationRoot.
_GRIP_MARK = ("follower","cone","gripper","suction","_sg","sgf","finger","cup","pad","tool0","shortgripper")
for p in stage.Traverse():
    nm = p.GetName().lower(); ps = p.GetPath().pathString.lower()
    is_art = p.HasAPI(UsdPhysics.ArticulationRootAPI)
    if is_art or any(k in nm for k in ("ur10","ur5","ur3","ur16","franka","panda","cobotta","kuka","iiwa","kr","abb")):
        if not is_art and any(g in nm for g in _GRIP_MARK):
            continue
        if "/" + p.GetName().lower() in ps or ps.endswith(p.GetName().lower()):
            fam = "default"
            for f in ("ur10e","ur10","ur5e","ur5","franka","panda","cobotta"):
                if f in nm or f in ps: fam = "franka" if f=="panda" else f; break
            rpath = p.GetPath().pathString
            # de-dupe: one robot can match both ArticulationRoot and the name heuristic; key by the top-level prim
            top = "/" + rpath.strip("/").split("/")[0] + "/" + rpath.strip("/").split("/")[1] if rpath.count("/")>=2 else rpath
            if top in _seen_robot: continue
            _seen_robot.add(top)
            ROBOTS.append({"path": rpath, "family": fam, "base": _base_of(rpath),
                           "reach": REACH.get(fam, REACH["default"])})
if not ROBOTS:
    ROBOTS = [{"path": None, "family": "default", "base": [0.0,0.0,0.75], "reach": REACH["default"]}]
# humanoid / legged articulations (G1, H1, Anymal, Spot, Go1/2) reach from a SHOULDER, not the pelvis/base, and have
# a different workspace model than a fixed-base arm — the distance-from-base reach heuristic does not apply. Drop them.
_LEGGED = ("g1","h1","anymal","humanoid","pelvis","biped","quadruped","spot","go1","go2","unitree")
ROBOTS = [rb for rb in ROBOTS if not (rb["path"] and any(k in rb["path"].lower() for k in _LEGGED))] or \
         [{"path": None, "family": "default", "base": [0.0,0.0,0.75], "reach": REACH["default"]}]
# primary robot (legacy refs in belt/support code use these)
robot = ROBOTS[0]["path"]; base = ROBOTS[0]["base"]; reach = ROBOTS[0]["reach"]; family = ROBOTS[0]["family"]
HAVE_ROBOT = any(rb["path"] for rb in ROBOTS)  # no real arm detected -> can't attribute reach -> skip (no false flags)
def nearest_robot(point):
    return min(ROBOTS, key=lambda rb: (rb["base"][0]-point[0])**2 + (rb["base"][1]-point[1])**2)
for rb in ROBOTS:
    print("ROBOT %s family=%s base=[%.2f,%.2f,%.2f] reach=%.2f" % (rb["path"], rb["family"], rb["base"][0],rb["base"][1],rb["base"][2], rb["reach"]))

# moving belts (captured pre-settle): a cube upstream on a conveyor is NOT out-of-reach -- the belt carries it in.
belts = []
for bp, bv in _belt_cap.items():
    bb2 = aabb(bp)
    if bb2: belts.append((bb2, bv))

def belt_reachable(c, rbase, rreach):
    # cube on a moving belt whose forward travel brings it within reach of the base (closest approach <= reach)?
    for bb2, bv in belts:
        if bb2[0][0]-0.15 <= c[0] <= bb2[1][0]+0.15 and bb2[0][1]-0.15 <= c[1] <= bb2[1][1]+0.15:
            bn = (bv[0]**2 + bv[1]**2) ** 0.5
            if bn < 1e-6: continue
            ux, uy = bv[0]/bn, bv[1]/bn
            t = (rbase[0]-c[0])*ux + (rbase[1]-c[1])*uy
            if t < 0: t = 0.0
            clx, cly = c[0]+t*ux, c[1]+t*uy
            if ((rbase[0]-clx)**2 + (rbase[1]-cly)**2 + (c[2]-rbase[2])**2) ** 0.5 <= rreach:
                return True
    return False

def belt_delivers(tc, rbase, rreach):
    # inverse of belt_reachable for PLACE: the robot drops on a moving transfer belt within its reach, and the belt
    # carries the item DOWNSTREAM to the (far) target -> a belt-fed bin is NOT an unreachable-place bug (CP-26 class).
    for bb2, bv in belts:
        bn = (bv[0]**2 + bv[1]**2) ** 0.5
        if bn < 1e-6: continue
        # closest point of the belt footprint to the base (can the arm place onto the belt at all?)
        bx = min(max(rbase[0], bb2[0][0]), bb2[1][0]); by = min(max(rbase[1], bb2[0][1]), bb2[1][1])
        if ((rbase[0]-bx)**2 + (rbase[1]-by)**2) ** 0.5 > rreach: continue
        # does the belt flow TOWARD the target? (target downstream of the belt centre along the velocity vector)
        bcx = (bb2[0][0]+bb2[1][0])/2.0; bcy = (bb2[0][1]+bb2[1][1])/2.0
        if (tc[0]-bcx)*bv[0] + (tc[1]-bcy)*bv[1] > 0:
            return True
    return False
# mobile delivery agents (AMR / cart / forklift) carry a placed item to a far target -> don't arm-reach-check that
# target (the arm places onto the mobile base nearby, the base drives to the dropzone). cart-handoff-amr class.
HAS_MOBILE = any(any(k in p.GetName().lower() for k in ("amr","forklift","carter","jetbot","agv","_cart","cart_","trolley")) for p in stage.Traverse())
# rotary carousel / turntable presents source bins DYNAMICALLY into the pick zone; the bins' static (or settle-
# disturbed) world positions are far from the arm, but the controlled rotation brings each to an in-reach handoff.
# A passive settle play even FLINGS the unanchored bins. -> skip reach on carousel scenes (kitting-station-6sku class).
HAS_ROTARY = any(any(k in p.GetPath().pathString.lower() for k in ("carousel","rotary","turntable","indexer")) for p in stage.Traverse())

# SCOPE filter: this validator checks PICK-PLACE geometry. Many library templates declare cube_path/target_path
# that aren't pick-place semantics — calibration (Fiducial->panda_hand), safety tests (HumanProxy), door-open
# (Handle), paint (Panel/Body), teaching-mode (Table). Reach/support on those is meaningless. Drop:
#  - non-graspable scene PROPS as pick objects (human/operator/fiducial/estop/handle/door/panel/...)
#  - ROBOT-PART targets (panda_hand / *_link / the robot itself) — a place target is a bin/pallet, never the gripper.
_PROP = ("human","proxy","operator","worker","person","avatar","fiducial","marker","estop","e_stop","button","handle","door","lever","knob","dummy","pelvis","torso","spraygun","sprayer","welder","torch","nozzle","table","workbench","wall","fixture/")
_ROBOTPART = ("_hand","panda_hand","_link","gripper","finger","tcp","flange","wrist","ee_link","_ee","shortgripper","sgcone","sgfollower")
def _is_prop(path):
    pl = path.lower()
    return any(k in pl.split("/")[-1] for k in _PROP) or "/spraygun/" in pl or "/sprayer/" in pl
def _is_robot_part(path):
    if any(rb["path"] and (path == rb["path"] or path.startswith(rb["path"].rstrip("/")+"/")) for rb in ROBOTS): return True
    return any(k in path.split("/")[-1].lower() for k in _ROBOTPART)

# resolve pick objects (declared, else scan small rigid Cube prims off the robot)
picks = [p for p in PICKS if stage.GetPrimAtPath(Sdf.Path(p)).IsValid()]
if not picks:
    for p in stage.Traverse():
        if p.GetTypeName()=="Cube" and p.HasAPI(UsdPhysics.RigidBodyAPI):
            bb=aabb(p.GetPath().pathString)
            if bb and max(bb[1][i]-bb[0][i] for i in range(3))<0.15:
                picks.append(p.GetPath().pathString)
def _too_big(path):  # a declared "pick" larger than a graspable object (furniture/tool/robot) is not a real pick
    bb = aabb(path)
    return bb is not None and max(bb[1][i]-bb[0][i] for i in range(3)) > 0.5
_dropped_props = [p.split("/")[-1] for p in picks if _is_prop(p) or _is_robot_part(p) or _too_big(p)]
picks = [p for p in picks if not (_is_prop(p) or _is_robot_part(p) or _too_big(p))]
TARGETS = [t for t in TARGETS if not _is_robot_part(t)]
if _dropped_props: print("SCOPE: dropped non-pick props/robot-parts:", _dropped_props)
print("PICK OBJECTS:", [p.split("/")[-1] for p in picks])
if not picks and not TARGETS:
    print("NOT A PICK-PLACE SCENE (no graspable pick objects or place targets after scope filter) — geometry checks SKIPPED")

V = []  # violations
bbs = {p: aabb(p) for p in picks}

# 0) PHYSICS INSTABILITY — a pick that travelled >1 m during the passive settle was EJECTED (spawn-overlap
# explosion). Its post-settle pos is garbage, so flag the instability (the true root) and SKIP its reach/support.
exploded = set()
for p in picks:
    bb = bbs[p]
    if not bb or p not in _pre_pos: continue
    c = center(bb); pre = _pre_pos[p]
    disp = math.sqrt(sum((c[i]-pre[i])**2 for i in range(3)))
    if disp > 1.0:
        exploded.add(p)
        V.append("PHYSICS_INSTABILITY: %s was EJECTED %.2fm during settle (spawn-overlap explosion: %s -> %s) — physics-unstable scene, not a reach issue" % (p.split("/")[-1], disp, "[%.2f,%.2f,%.2f]"%tuple(pre), "[%.2f,%.2f,%.2f]"%tuple(c)))
picks = [p for p in picks if p not in exploded]  # exclude ejected picks from reach/support (their geom is garbage)

# 1) REACH (each pick object against its NEAREST robot arm)
DO_REACH = HAVE_ROBOT and not HAS_ROTARY
if not HAVE_ROBOT:
    print("  NO ROBOT detected — reach + target-reach checks SKIPPED (can't attribute; avoid false flags)")
elif HAS_ROTARY:
    print("  ROTARY carousel/turntable present — reach checks SKIPPED (mechanism presents items into the pick zone)")
for p in (picks if DO_REACH else []):
    bb = bbs[p]
    if not bb:
        print("  geom %s: NO BBOX" % p.split("/")[-1]); continue
    c = center(bb)
    rb = nearest_robot(c); rbase = rb["base"]; rreach = rb["reach"]
    d = math.sqrt(sum((c[i]-rbase[i])**2 for i in range(3)))
    dz = c[2]-rbase[2]
    rid = (rb["path"] or "?").split("/")[-1]
    print("  geom %s pos=[%.2f,%.2f,%.2f] dist=%.2f dz=%.2f arm=%s" % (p.split("/")[-1], c[0],c[1],c[2], d, dz, rid))
    # z-window is heuristic (the rigorous check is IK feasibility). The LOWER bound is gripper-dependent: a top-down
    # SUCTION arm (UR10) can't angle far below its mount (CP-70 ok at dz=+0.09, unclamped-CP-71 fails at dz=-0.25 ->
    # -0.15), but a 7-DOF ARTICULATED arm (Franka/cobotta parallel/finger gripper) reaches a near-full sphere and
    # routinely picks a bench 0.20-0.45 m below its pedestal -> a tight -0.15 false-flags table-mounted Frankas.
    ZLO = {"franka": -0.45, "cobotta": -0.45, "ur10": -0.15, "ur10e": -0.15, "ur5": -0.20, "ur5e": -0.20, "default": -0.25}
    zlo = ZLO.get(rb["family"], ZLO["default"])
    if d > rreach and not belt_reachable(c, rbase, rreach):
        V.append("REACH: %s at [%.2f,%.2f,%.2f] is %.2fm from %s base (>reach %.2f, and no belt carries it in)" % (p.split("/")[-1], c[0],c[1],c[2], d, rid, rreach))
    elif dz < zlo:
        V.append("REACH: %s z=%.2f is %.2fm BELOW the %s base (below %s's reachable pick zone)" % (p.split("/")[-1], c[2], -dz, rid, rb["family"]))
    elif dz > 0.60:
        V.append("REACH: %s z=%.2f is %.2fm ABOVE the %s base (out of vertical reach)" % (p.split("/")[-1], c[2], dz, rid))

# 1b) TARGET REACH (the delivery/place location must ALSO be reachable — an out-of-reach bin/pallet
# means the arm can pick but never place. Same nearest-arm + reach + z-window logic as the pick check.)
for tp in (TARGETS if (DO_REACH and picks) else []):  # no graspable pick / rotary mechanism -> target moot
    if not stage.GetPrimAtPath(Sdf.Path(tp)).IsValid():
        print("  target %s: NOT IN SCENE" % tp.split("/")[-1]); continue
    tb = aabb(tp)
    if tb:
        # place point = top-center of the target geometry (where the cube is set down)
        tc = [(tb[0][0]+tb[1][0])/2.0, (tb[0][1]+tb[1][1])/2.0, tb[1][2]]
    else:
        # marker Xform target (no mesh, e.g. PenTarget) -> the place location is its transform origin
        tc = _base_of(tp)
    rb = nearest_robot(tc); rbase = rb["base"]; rreach = rb["reach"]
    d = math.sqrt(sum((tc[i]-rbase[i])**2 for i in range(3)))
    dz = tc[2]-rbase[2]
    rid = (rb["path"] or "?").split("/")[-1]
    print("  target %s top=[%.2f,%.2f,%.2f] dist=%.2f dz=%.2f arm=%s belt_fed=%s mobile=%s" % (tp.split("/")[-1], tc[0],tc[1],tc[2], d, dz, rid, belt_delivers(tc, rbase, rreach), HAS_MOBILE))
    if d > rreach and not belt_delivers(tc, rbase, rreach) and not HAS_MOBILE:
        V.append("TARGET_REACH: place target %s top at [%.2f,%.2f,%.2f] is %.2fm from %s base (>reach %.2f) — arm can pick but never place (no transfer belt or mobile agent delivers it)" % (tp.split("/")[-1], tc[0],tc[1],tc[2], d, rid, rreach))
    elif d <= rreach and dz > 0.60:
        V.append("TARGET_REACH: place target %s top z=%.2f is %.2fm ABOVE the %s base (out of vertical reach to place)" % (tp.split("/")[-1], tc[2], dz, rid))

# 2) INTERPENETRATION (pairwise pick-object AABB overlap in all 3 axes)
for i in range(len(picks)):
    for j in range(i+1, len(picks)):
        a, b2 = bbs[picks[i]], bbs[picks[j]]
        if not (a and b2): continue
        ov = [min(a[1][k],b2[1][k]) - max(a[0][k],b2[0][k]) for k in range(3)]
        if all(o > 0 for o in ov):  # overlapping in every axis = real 3D interpenetration
            pen = min(ov)
            small = min(min(a[1][k]-a[0][k] for k in range(3)), min(b2[1][k]-b2[0][k] for k in range(3)))
            # GROSS overlap only: the target class is "N objects collapsed into one point" (~full-size overlap).
            # A sub-cm contact (dispenser pile resting together, two belt cubes adjacent) is NOT an unpickable clump
            # — physics has settled it. Require >50% of the object AND a 2 cm absolute floor to avoid those FPs.
            if pen > 0.50*small and pen > 0.02:
                V.append("INTERPENETRATION: %s & %s overlap %.3fm (>50%% of object) -> collapsed clump, not individually pickable" % (picks[i].split("/")[-1], picks[j].split("/")[-1], pen))

# 3) SUPPORT (each pick object should rest on a surface: gap to nearest surface below in [-0.02, 0.10])
others = []
for p in stage.Traverse():
    if p.HasAPI(UsdPhysics.CollisionAPI) or p.GetTypeName() in ("Cube","Mesh","Cylinder"):
        ps = p.GetPath().pathString
        if ps in picks: continue
        if robot and ps.startswith(robot): continue
        bb = aabb(ps)
        if bb: others.append((ps, bb))
# a candidate is a CONTAINER (not a support) if it is an ANCESTOR of the pick (e.g. /World/Dispenser is the items'
# PARENT — its bbox encloses them, giving a false "buried" reading) or the world root.
def _is_container(ps, pick):
    return pick.startswith(ps.rstrip("/") + "/") or ps in ("/World", "/")
for p in picks:
    bb = bbs[p]
    if not bb: continue
    cube_bottom = bb[0][2]; cx,cy = (bb[0][0]+bb[1][0])/2.0, (bb[0][1]+bb[1][1])/2.0
    best_gap = None; best = None
    # candidate supports = real surfaces (others) PLUS other pick objects (a cube can rest on a cube in a STACK;
    # without this the top cube of a stack false-reads as "floating" since picks were excluded from `others`).
    cands = list(others) + [(op, bbs[op]) for op in picks if op != p and bbs[op] and bbs[op][1][2] <= cube_bottom + 0.12]
    for ps, ob in cands:
        if _is_container(ps, p): continue
        if ob[0][0] <= cx <= ob[1][0] and ob[0][1] <= cy <= ob[1][1]:  # xy under the cube
            if ob[1][2] <= cube_bottom + 0.12:  # surface top at/below cube bottom (a support, not an overhead)
                gap = cube_bottom - ob[1][2]
                if best_gap is None or abs(gap) < abs(best_gap): best_gap = gap; best = ps
    # 2026-06-05 review fix (false-positive on floor-resting / on-belt / in-bin objects whose support surface
    # wasn't captured in `others`): fallbacks before flagging floating/floats.
    _on_floor = cube_bottom <= 0.06  # resting on/near the world ground plane (often not a CollisionAPI prim)
    _on_belt = any(bb2[0][0]-0.1 <= cx <= bb2[1][0]+0.1 and bb2[0][1]-0.1 <= cy <= bb2[1][1]+0.1
                   and bb2[1][2] <= cube_bottom + 0.12 for bb2, _bv in belts)  # over a captured conveyor
    _in_container = any((not _is_container(ps, p)) and ob[0][0] <= cx <= ob[1][0] and ob[0][1] <= cy <= ob[1][1]
                        and ob[0][2] - 0.02 <= cube_bottom <= ob[1][2] + 0.02 for ps, ob in others)  # nested inside a bin/tray
    _supported_fallback = _on_floor or _on_belt or _in_container
    print("  support %s bottom=%.2f nearest=%s gap=%s floor=%s belt=%s incontainer=%s" % (p.split("/")[-1], cube_bottom, (best.split("/")[-1] if best else None), ("%.2f"%best_gap if best_gap is not None else None), _on_floor, _on_belt, _in_container))
    if _supported_fallback:
        pass  # supported by floor / belt / container floor — not floating
    elif best_gap is None:
        V.append("SUPPORT: %s has NO surface beneath it (floating) at [%.2f,%.2f,%.2f]" % (p.split("/")[-1], cx,cy,cube_bottom))
    elif best_gap > 0.10:
        V.append("SUPPORT: %s floats %.2fm above its nearest surface (%s)" % (p.split("/")[-1], best_gap, best.split("/")[-1]))
    elif best_gap < -0.02:
        V.append("SUPPORT: %s is buried %.2fm inside %s (penetrating the support)" % (p.split("/")[-1], -best_gap, best.split("/")[-1]))

print("VIOLATIONS %d" % len(V))
for v in V: print("  !! " + v)
print("VERDICT", "CLEAN" if not V else "FAIL")
'''
    code = (code.replace("__PICKS__", json.dumps(picks))
                .replace("__TARGETS__", json.dumps(targets))
                .replace("__REACH__", json.dumps(ROBOT_REACH)))
    r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=60), timeout=80)
    out = (r.get("output") or r.get("error") or "").strip()
    print(f"=== {tpl_name} ===")
    print(out)


async def main():
    for t in TPLS:
        try:
            await validate(t)
        except Exception as e:
            print(f"{t}: ERROR {type(e).__name__}: {str(e)[:160]}")

asyncio.run(main())
