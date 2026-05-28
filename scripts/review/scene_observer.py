"""scene_observer.py — high-resolution scene observation per template.

For each template:
  - Build + settle
  - Subscribe physx-step at 60Hz with rich state capture
  - Capture: cube positions, EE pos, cube velocity, ctrl phase, fj presence (with
    EE-cube distance at moment FJ first appears), contact events
  - Run sim for duration_s
  - At end: dump full pose snapshot + max-velocity per cube + FJ events list
  - Compute HONESTY GATES:
    * cube_on_target (existing)
    * no_telepathic_fj (no FJ created when EE-cube_dist > 0.15m)
    * no_blowup (max cube_speed during sim < 2 m/s)
    * cube_ever_in_target (cube reached target bbox at some point)
    * EE_never_underground (EE z always > table top - 5cm)

A run only passes if ALL gates pass.

Usage:
  scene_observer.py <CP-NAME> [<CP-NAME> ...]
"""
import asyncio, json, os, re, subprocess, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))
HEALTH = "http://127.0.0.1:8001/health"; LAUNCH = "/home/anton/.claude/diag/launch_kit_headless.sh"
OUT = REPO/"workspace/qa_runs/scene_observer.jsonl"

import urllib.request
def kit_alive():
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as r: return r.status == 200
    except: return False
def find_pids():
    try: return [int(p) for p in subprocess.check_output(["pgrep","-f","isaac_sim_with_assist"]).decode().split()]
    except: return []
async def launch_kit():
    subprocess.Popen(["bash", LAUNCH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    for _ in range(36):
        await asyncio.sleep(5)
        if kit_alive(): return True
    return False
async def restart_kit():
    for pid in find_pids():
        try: os.killpg(os.getpgid(pid), 9)
        except: pass
    await asyncio.sleep(4)
    return await launch_kit()

OBSERVE_CODE = r"""
import omni.usd, omni.timeline, omni.kit.app, omni.physx
from pxr import UsdGeom, Sdf, Gf, UsdPhysics
import json, time, math

stage = omni.usd.get_context().get_stage()
ROBOT_PATH = {robot_path!r}
EE_LINK = {ee_link!r}
CUBE_PATHS = {cube_paths!r}
TARGET_PATH = {target_path!r}
DURATION_S = {duration_s!r}
TABLE_TOP_Z = {table_top_z!r}
# List of {{"role", "expected_path", "builder_hint", "source"}} dicts derived from
# template `code_template` placeholder-substitutions. Empty list = no template-intent
# data was supplied (detector inactive — never triggers).
EXPECTED_SCENE_ELEMENTS = {expected_scene_elements!r}

def _wp(p):
    try:
        pr = stage.GetPrimAtPath(Sdf.Path(p))
        if not pr or not pr.IsValid(): return None
        m = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0)
        t = m.ExtractTranslation()
        return [float(t[0]), float(t[1]), float(t[2])]
    except: return None

def _ee_pos():
    return _wp(ROBOT_PATH + "/" + EE_LINK)

def _world_bbox(p):
    try:
        pr = stage.GetPrimAtPath(Sdf.Path(p))
        if not pr or not pr.IsValid(): return None
        bb = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_]).ComputeWorldBound(pr).ComputeAlignedRange()
        return {{'min':[float(bb.GetMin()[i]) for i in range(3)],'max':[float(bb.GetMax()[i]) for i in range(3)]}}
    except: return None

target_bbox = _world_bbox(TARGET_PATH) or {{}}

# Discover ALL articulation root paths in stage (not just template-arg ROBOT_PATH).
# Fixes false positives: multi-robot templates (e.g. /World/FrankaB, /World/FixtureHolder)
# get their articulation links counted as "movable" objects. Also fixes Carter detection.
def _discover_articulation_roots():
    roots = set()
    try:
        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                roots.add(str(prim.GetPath()))
    except: pass
    # Also include template-specified ROBOT_PATH
    if ROBOT_PATH: roots.add(ROBOT_PATH)
    # Heuristic name match: prims with robot-class names (Franka, UR10, Carter, etc.)
    try:
        for prim in stage.Traverse():
            n = prim.GetName().lower()
            if any(k in n for k in ('franka', 'ur10', 'ur5', 'carter', 'jetbot', 'kuka', 'panda')):
                pth = str(prim.GetPath())
                # add if it's a top-level robot prim (no parent in roots already)
                if not any(pth.startswith(r + "/") for r in roots):
                    roots.add(pth)
    except: pass
    return roots

ARTICULATION_ROOTS = _discover_articulation_roots()
print(f"[VE] articulation_roots: {{ARTICULATION_ROOTS}}", flush=True)

def _is_under_robot(path):
    for r in ARTICULATION_ROOTS:
        if path == r or path.startswith(r + "/"): return True
    return False

def _discover_movables():
    # Auto-discover all RigidBodyAPI-applied prims excluding robot articulation.
    # Returns: dict {{prim_path: {{type, dims, gravity_disabled}}}}.
    movs = {{}}
    try:
        for prim in stage.Traverse():
            pth = str(prim.GetPath())
            if _is_under_robot(pth): continue
            if not prim.HasAPI(UsdPhysics.RigidBodyAPI): continue
            try:
                bb_cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
                bb = bb_cache.ComputeWorldBound(prim).ComputeAlignedRange()
                mn, mx = bb.GetMin(), bb.GetMax()
                dims = [float(mx[i]) - float(mn[i]) for i in range(3)]
            except: dims = [0.05, 0.05, 0.05]
            # gravity disabled?
            grav_disabled = False
            try:
                _ga = prim.GetAttribute("physxRigidBody:disableGravity")
                if _ga and _ga.IsDefined() and bool(_ga.Get()): grav_disabled = True
            except: pass
            movs[pth] = {{
                'type': str(prim.GetTypeName()),
                'dims': dims,
                'gravity_disabled': grav_disabled,
            }}
    except: pass
    return movs

MOVABLE_PRIMS = _discover_movables()
# Merge in any from template CUBE_PATHS that weren't discovered (e.g. spawned later)
for cp in CUBE_PATHS:
    if cp not in MOVABLE_PRIMS:
        MOVABLE_PRIMS[cp] = {{'type': 'Cube?', 'dims': [0.05, 0.05, 0.05], 'gravity_disabled': False}}
MOVABLE_PATHS = list(MOVABLE_PRIMS.keys())

# Robot articulation joint introspection
def _get_robot_joint_names():
    # Walk descendants for revolute/prismatic joints
    try:
        rp = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH))
        if not (rp and rp.IsValid()): return []
        # walk descendants for revolute/prismatic joints
        names = []
        for c in stage.Traverse():
            pth = str(c.GetPath())
            if not pth.startswith(ROBOT_PATH + "/"): continue
            if c.IsA(UsdPhysics.RevoluteJoint) or c.IsA(UsdPhysics.PrismaticJoint):
                names.append(pth)
        return names
    except: return []
ROBOT_JOINTS = _get_robot_joint_names()

def _get_joint_positions():
    # Read joint positions via PhysxArticulationJointAPI joint pos targets (approximate).
    poses = {{}}
    try:
        for jp in ROBOT_JOINTS:
            pr = stage.GetPrimAtPath(Sdf.Path(jp))
            if not (pr and pr.IsValid()): continue
            # joint position is stored at joint state (drive::angular::position)
            # try multiple attr names
            for attr in ("state:angular:physics:position", "physics:angularPosition", "drive:angular:physics:targetPosition"):
                a = pr.GetAttribute(attr)
                if a and a.IsDefined():
                    v = a.Get()
                    if v is not None:
                        poses[jp] = float(v); break
    except: pass
    return poses

def _get_robot_base_quat():
    try:
        rp = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH))
        if not (rp and rp.IsValid()): return None
        m = UsdGeom.Xformable(rp).ComputeLocalToWorldTransform(0)
        # Extract rotation matrix → quaternion
        q = m.ExtractRotationQuat()
        return [float(q.real), float(q.imaginary[0]), float(q.imaginary[1]), float(q.imaginary[2])]
    except: return None

def _x_axis_world_z(quat):
    # For quat (w,x,y,z), local x-axis transformed to world: how much it points in +z direction.
    # UR10 lying on side has |x_z| > 0.7 (horizontal pose).
    if not quat: return 0.0
    w, x, y, z = quat
    # local x-axis [1,0,0] rotated by quat → (1-2(y²+z²), 2(xy+wz), 2(xz-wy))
    return abs(2*(x*z - w*y))

# Count cube prims at start (for cube_disappears detector)
INITIAL_CUBE_PRIM_COUNT = sum(1 for cp in CUBE_PATHS if stage.GetPrimAtPath(Sdf.Path(cp)).IsValid())

# Check object types (for wrong_object_type_present)
def _check_object_types():
    # For each CUBE_PATH, report its prim type and bbox aspect ratio.
    # Expected for cube: Cube type, dims aspect ratio close to 1:1:1 (within 30%).
    types = {{}}
    for cp in CUBE_PATHS:
        pr = stage.GetPrimAtPath(Sdf.Path(cp))
        if not (pr and pr.IsValid()):
            types[cp] = {{'prim_type': 'MISSING'}}; continue
        t = str(pr.GetTypeName())
        # bbox aspect: dx/dy, dy/dz, dx/dz — for cube, all near 1.0
        bb_info = MOVABLE_PRIMS.get(cp, {{}})
        dims = bb_info.get('dims') or [0.05, 0.05, 0.05]
        if min(dims) < 1e-4: aspect = float('inf')
        else: aspect = max(dims) / min(dims)
        types[cp] = {{'prim_type': t, 'aspect_ratio': round(aspect, 2), 'dims': [round(d, 3) for d in dims]}}
    return types

INITIAL_OBJECT_TYPES = _check_object_types()

# Conveyor bbox lookup (for cube_spawn_off_belt detector)
def _conveyor_bbox():
    # Find first prim with 'conveyor' or 'belt' in name. Return bbox.
    for prim in stage.Traverse():
        n = prim.GetName().lower()
        if 'conveyor' in n or 'belt' in n:
            bb = _world_bbox(str(prim.GetPath()))
            if bb: return bb
    return None
CONVEYOR_BBOX = _conveyor_bbox()

# FJ discovery: scan stage every sample for new FJ
def _find_new_fjs(known):
    found = []
    try:
        for prim in stage.Traverse():
            if prim.IsA(UsdPhysics.FixedJoint):
                pth = str(prim.GetPath())
                if pth in known: continue
                fj = UsdPhysics.FixedJoint(prim)
                b0 = [str(t) for t in fj.GetBody0Rel().GetTargets()]
                b1 = [str(t) for t in fj.GetBody1Rel().GetTargets()]
                found.append({{'path': pth, 'body0': b0, 'body1': b1}})
    except: pass
    return found

# Capture state
state = {{
    'fj_events': [],    # list of {{t, fj_path, ee_pos, cube_pos, dist}}
    'cube_max_speed': {{cp: 0.0 for cp in CUBE_PATHS}},
    'ee_min_z': float('inf'),
    'cube_in_target_ever': {{cp: False for cp in CUBE_PATHS}},
    'cube_t_first_in_target': {{cp: None for cp in CUBE_PATHS}},  # for placement-window detectors
    'cube_pos_at_first_in_target': {{cp: None for cp in CUBE_PATHS}},
    'prev_cube_pos': {{cp: None for cp in CUBE_PATHS}},
    'known_fjs': set(),
    'tick': 0,
    't_start': None,
    'sample_every': 6,  # ~10Hz at 60Hz physx
    'trajectory': [],   # [{{t, ee, cubes: {{cp: pos}}, fj_count, in_target: {{cp: bool}}}}]
    'trajectory_every': 30,  # ~2Hz — sparse log for post-hoc dislodge analysis
    'phase_history': [],   # [(t, ctrl:phase)] from robot prim
    'robot_base_z': [],   # [(t, z)] — for mobile robot under-floor
    'robot_base_pos': [],  # [(t, [x,y,z])] — for mobile robot vibration / not-moving
    'spawn_pos': {{cp: None for cp in CUBE_PATHS}},  # captured at first sample
    'spawn_robot_pos': None,  # robot pose at t≈0 for teleport-at-play detection
    'ee_max_speed_in_placement': 0.0,  # max EE speed during placement phase
    'cube_xy_drift_post_target': {{cp: 0.0 for cp in CUBE_PATHS}},  # cube xy displacement after reaching target
    'prev_ee_pos': None,
    # NEW capture (R2 feedback iteration):
    'movable_pos': {{m: [] for m in MOVABLE_PATHS}},  # [(t, [x,y,z])] per movable
    'movable_z_range': {{m: [float('inf'), float('-inf')] for m in MOVABLE_PATHS}},  # min, max z over run
    'movable_spawn_pos': {{m: None for m in MOVABLE_PATHS}},
    'robot_base_quat_initial': None,  # captured at first sample
    'robot_base_quat_final': None,
    'robot_joints_initial': {{}},  # joint name -> pos at t=0
    'cube_prim_count_history': [],  # (t, n_valid) for cube_disappears detector
    'cube_quat_initial': {{}},  # cube prim -> quat at first sample (for tilt detection)
    'cube_max_tilt_deg': {{cp: 0.0 for cp in CUBE_PATHS}},  # max angular deviation
    'cube_z_in_target_max': {{cp: 0.0 for cp in CUBE_PATHS}},  # for bounce detection
    # 2026-05-21 source-data: per-tick engine telemetry
    'joint_efforts_over_time': [],  # [(t, [efforts])]
    'joint_efforts_max': {{}},  # joint_name -> max absolute effort observed
    'ee_overlap_events': [],  # overlap_box around EE detected non-self prims
    'physx_step_times': [],  # (t, step_sim_time) for sim health
}}

def _quat_of(p):
    try:
        pr = stage.GetPrimAtPath(Sdf.Path(p))
        if not (pr and pr.IsValid()): return None
        m = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0)
        q = m.ExtractRotationQuat()
        return [float(q.real), float(q.imaginary[0]), float(q.imaginary[1]), float(q.imaginary[2])]
    except: return None

def _quat_angular_diff_deg(q1, q2):
    # Angular distance between two quaternions in degrees.
    if not q1 or not q2: return 0.0
    dot = q1[0]*q2[0] + q1[1]*q2[1] + q1[2]*q2[2] + q1[3]*q2[3]
    dot = max(-1.0, min(1.0, abs(dot)))
    return math.degrees(2 * math.acos(dot))

def _is_under_target(pth):
    if not pth: return False
    return pth == TARGET_PATH or pth.startswith(TARGET_PATH + "/")

def _check_in_target(cp_now):
    if cp_now is None or not target_bbox: return False
    bm = target_bbox.get('min'); bx = target_bbox.get('max')
    if not bm or not bx: return False
    return (bm[0]-0.05 <= cp_now[0] <= bx[0]+0.05
            and bm[1]-0.05 <= cp_now[1] <= bx[1]+0.05
            and cp_now[2] >= bm[2]-0.1)

def _on_step(dt):
    state['tick'] += 1
    if state['t_start'] is None:
        state['t_start'] = time.monotonic()
    if state['tick'] % state['sample_every'] != 0:
        return
    elapsed = time.monotonic() - state['t_start']
    ee = _ee_pos()
    if ee is not None and ee[2] < state['ee_min_z']:
        state['ee_min_z'] = ee[2]
    # FJ discovery
    new_fjs = _find_new_fjs(state['known_fjs'])
    for fj in new_fjs:
        state['known_fjs'].add(fj['path'])
        # find cube + ee in body0/body1
        cube_p = None
        for b in fj.get('body0', []) + fj.get('body1', []):
            if b in CUBE_PATHS or any(b.startswith(cp) for cp in CUBE_PATHS):
                # find exact cube
                for cp in CUBE_PATHS:
                    if b == cp or b.startswith(cp): cube_p = cp; break
                if cube_p: break
        cube_pos = _wp(cube_p) if cube_p else None
        dist = None
        if ee is not None and cube_pos is not None:
            dist = math.sqrt((ee[0]-cube_pos[0])**2 + (ee[1]-cube_pos[1])**2 + (ee[2]-cube_pos[2])**2)
        state['fj_events'].append({{
            't': round(elapsed,3), 'fj_path': fj['path'],
            'cube': cube_p, 'cube_pos': cube_pos, 'ee_pos': ee, 'distance': dist,
            'body0': fj['body0'][:1], 'body1': fj['body1'][:1],
        }})
    # Per-cube tracking
    for cp in CUBE_PATHS:
        now = _wp(cp)
        prev = state['prev_cube_pos'].get(cp)
        if now is not None and prev is not None:
            dt_eff = max(dt * state['sample_every'], 1e-3)
            # Filter out position-warp artifacts: large position deltas (>0.5m
            # in one sample = teleport, e.g. cuRobo reset) are NOT real
            # velocity. Treat as discontinuity and don't count toward max_speed.
            _delta = math.sqrt(sum((now[i]-prev[i])**2 for i in range(3)))
            if _delta < 0.5:
                sp = _delta / dt_eff
                if sp > state['cube_max_speed'][cp]: state['cube_max_speed'][cp] = sp
            # Also exclude speed when cube was already delivered (in_target_ever
            # before this sample) — robot may nudge already-placed cubes; we
            # don't want that to fail no_blowup gate
        if now is not None:
            in_t_now = _check_in_target(now)
            if in_t_now:
                if not state['cube_in_target_ever'][cp]:
                    state['cube_in_target_ever'][cp] = True
                    state['cube_t_first_in_target'][cp] = elapsed
                    state['cube_pos_at_first_in_target'][cp] = list(now)
                # Track max z while in target (for bounce detection)
                if now[2] > state['cube_z_in_target_max'][cp]:
                    state['cube_z_in_target_max'][cp] = now[2]
            # Track cube xy displacement after reaching target
            if state['cube_pos_at_first_in_target'].get(cp) is not None:
                _pp = state['cube_pos_at_first_in_target'][cp]
                _drift = math.sqrt((now[0]-_pp[0])**2 + (now[1]-_pp[1])**2)
                if _drift > state['cube_xy_drift_post_target'][cp]:
                    state['cube_xy_drift_post_target'][cp] = _drift
            # Spawn pos + orientation (first sample)
            if state['spawn_pos'].get(cp) is None:
                state['spawn_pos'][cp] = list(now)
                state['cube_quat_initial'][cp] = _quat_of(cp)
            # Cube tilt tracking
            _q_init = state['cube_quat_initial'].get(cp)
            if _q_init and state['tick'] % state['trajectory_every'] == 0:
                _q_now = _quat_of(cp)
                _ang = _quat_angular_diff_deg(_q_init, _q_now)
                if _ang > state['cube_max_tilt_deg'][cp]:
                    state['cube_max_tilt_deg'][cp] = _ang
        state['prev_cube_pos'][cp] = now
    # EE speed during placement window (any cube in target)
    if ee is not None and state['prev_ee_pos'] is not None and any(state['cube_in_target_ever'].values()):
        dt_eff_ee = max(dt * state['sample_every'], 1e-3)
        _ee_delta = math.sqrt(sum((ee[i]-state['prev_ee_pos'][i])**2 for i in range(3)))
        if _ee_delta < 0.5:
            _ee_sp = _ee_delta / dt_eff_ee
            if _ee_sp > state['ee_max_speed_in_placement']:
                state['ee_max_speed_in_placement'] = _ee_sp
    state['prev_ee_pos'] = ee
    # Robot base pos sampling (mobile robot detectors)
    _rbp = _wp(ROBOT_PATH)
    if _rbp is not None:
        if state['spawn_robot_pos'] is None and elapsed < 0.5:
            state['spawn_robot_pos'] = list(_rbp)
            state['robot_base_quat_initial'] = _get_robot_base_quat()
            state['robot_joints_initial'] = _get_joint_positions()
        if state['tick'] % state['trajectory_every'] == 0:
            state['robot_base_pos'].append((round(elapsed, 2), _rbp))
            state['robot_base_z'].append((round(elapsed, 2), float(_rbp[2])))
    # Movable prims sampling (all RigidBody non-robot)
    if state['tick'] % state['trajectory_every'] == 0:
        for m in MOVABLE_PATHS:
            pos = _wp(m)
            if pos is not None:
                if state['movable_spawn_pos'].get(m) is None:
                    state['movable_spawn_pos'][m] = list(pos)
                state['movable_pos'][m].append((round(elapsed, 2), pos))
                # Track z range
                if pos[2] < state['movable_z_range'][m][0]: state['movable_z_range'][m][0] = pos[2]
                if pos[2] > state['movable_z_range'][m][1]: state['movable_z_range'][m][1] = pos[2]
    # Cube prim existence history
    if state['tick'] % state['trajectory_every'] == 0:
        _n_valid = sum(1 for cp in CUBE_PATHS if stage.GetPrimAtPath(Sdf.Path(cp)).IsValid())
        state['cube_prim_count_history'].append((round(elapsed, 2), _n_valid))
    # Joint efforts over time (1 Hz to keep data small)
    if state['tick'] % 60 == 0:
        try:
            from isaacsim.core.prims import SingleArticulation as _SArt_t
            for r in list(ARTICULATION_ROOTS)[:1]:
                _at = _SArt_t(r); _at.initialize()
                _je = _at.get_measured_joint_efforts() if hasattr(_at, 'get_measured_joint_efforts') else None
                if _je is not None:
                    _ef = [float(x) for x in _je.tolist()]
                    _dn = list(_at.dof_names) if _at.dof_names else []
                    state['joint_efforts_over_time'].append((round(elapsed, 2), _ef))
                    for _n, _v in zip(_dn, _ef):
                        if abs(_v) > abs(state['joint_efforts_max'].get(_n, 0.0)):
                            state['joint_efforts_max'][_n] = _v
        except Exception: pass
    # Overlap_box around EE — detect what's overlapping geometrically (PhysX-pre-collision)
    if state['tick'] % 30 == 0 and ee is not None:
        try:
            from carb import Float3 as _F3
            _bb_half = _F3(0.06, 0.06, 0.06)  # 12cm cube around EE
            _hits = _phys_q.overlap_box(_F3(float(ee[0]), float(ee[1]), float(ee[2])), _bb_half, _F3(0,0,0,1), lambda h: True, False) if hasattr(_phys_q, 'overlap_box') else None
            # API varies; fall through if not available
        except Exception: pass
    # PhysX simulation stats per sample
    if state['tick'] % state['trajectory_every'] == 0:
        try:
            _step_t = _phys.get_step_simulation_time() if hasattr(_phys, 'get_step_simulation_time') else None
            if _step_t is not None:
                state['physx_step_times'].append((round(elapsed, 2), float(_step_t)))
        except Exception: pass
    # Phase history (ctrl:phase USD attr) — 2 Hz
    # Multi-robot templates: ctrl:phase may live on a different articulation
    # root than ROBOT_PATH (e.g. CP-70 primary_robot=/World/UR10 but Franka
    # has the ctrl:* attrs). Try ROBOT_PATH first, then fall back to scanning
    # all ARTICULATION_ROOTS so phase_history is populated for the actually-
    # active controller.
    if state['tick'] % state['trajectory_every'] == 0:
        try:
            _ph_v = None; _ph_src = None
            for _cand in [ROBOT_PATH] + [r for r in ARTICULATION_ROOTS if r != ROBOT_PATH]:
                try:
                    _rp = stage.GetPrimAtPath(Sdf.Path(_cand))
                    if not (_rp and _rp.IsValid()): continue
                    _ph_attr = _rp.GetAttribute("ctrl:phase")
                    if _ph_attr and _ph_attr.IsDefined():
                        _v = _ph_attr.Get()
                        if _v:
                            _ph_v = str(_v); _ph_src = _cand
                            break
                except Exception: continue
            if _ph_v:
                state['phase_history'].append((round(elapsed, 2), _ph_v))
        except: pass
    # Sparse trajectory log
    if state['tick'] % state['trajectory_every'] == 0:
        state['trajectory'].append({{
            't': round(elapsed, 2),
            'ee': ee,
            'cubes': {{cp: state['prev_cube_pos'].get(cp) for cp in CUBE_PATHS}},
            'fj_count': len(state['known_fjs']),
            'in_target': dict(state['cube_in_target_ever']),
        }})

_phys = omni.physx.get_physx_interface()
_sub = _phys.subscribe_physics_step_events(_on_step)

# Contact-report subscription — comprehensive capture
# Anton R2 insight: detect kollisioner from SOURCE (PhysX), not infer from positions.
# Capture EVERY contact pair: actor0, actor1, impulse, normal. Aggregate per-pair.
state['contact_events'] = []  # individual events (cap 2000)
state['contact_pair_count'] = {{}}  # (actor0_short, actor1_short) -> count
state['contact_pair_max_impulse'] = {{}}  # -> max impulse
state['contact_pair_total_impulse'] = {{}}  # -> sum impulse
def _short(p):
    # last 2 path components for readability
    parts = str(p).strip('/').split('/')
    return '/' + '/'.join(parts[-2:]) if len(parts) > 1 else str(p)
def _classify_pair(a, b):
    # Return kind: finger_vs_cube, robot_link_vs_cube, robot_link_vs_target,
    # robot_link_vs_other, cube_vs_cube, cube_vs_target, cube_vs_other
    a_lc = a.lower(); b_lc = b.lower()
    a_robot = _is_under_robot(a); b_robot = _is_under_robot(b)
    a_cube = (a in CUBE_PATHS) or any(a.startswith(cp + "/") for cp in CUBE_PATHS)
    b_cube = (b in CUBE_PATHS) or any(b.startswith(cp + "/") for cp in CUBE_PATHS)
    a_target = TARGET_PATH and (a == TARGET_PATH or a.startswith(TARGET_PATH + "/"))
    b_target = TARGET_PATH and (b == TARGET_PATH or b.startswith(TARGET_PATH + "/"))
    # finger detection: panda_leftfinger/rightfinger, robotiq_*finger*, gripper finger links
    a_finger = a_robot and ("finger" in a_lc or "fingertip" in a_lc)
    b_finger = b_robot and ("finger" in b_lc or "fingertip" in b_lc)
    if (a_finger and b_cube) or (b_finger and a_cube): return "finger_vs_cube"
    if a_robot and b_cube: return "robot_link_vs_cube"
    if a_cube and b_robot: return "robot_link_vs_cube"
    if a_robot and b_target: return "robot_link_vs_target"
    if a_target and b_robot: return "robot_link_vs_target"
    if a_robot and b_robot: return "robot_link_vs_robot_link"
    if a_robot or b_robot: return "robot_link_vs_other"
    if a_cube and b_cube: return "cube_vs_cube"
    if a_cube and b_target: return "cube_vs_target"
    if a_target and b_cube: return "cube_vs_target"
    return "other_vs_other"

# PhysicsSchemaTools.intToSdfPath() decodes uint64 actor/collider IDs into SdfPath.
# Per omni.physx pyi (line 630): "Actor0 - uint64 use PhysicsSchemaTools::intToSdfPath
# to convert to SdfPath." Old code's path_from_handle() doesn't exist → fell through
# to digit-string fallback, producing the "140545" garbage in contact_events.
try:
    from pxr import PhysicsSchemaTools as _PST
    _HAS_PST = True
except Exception:
    _PST = None
    _HAS_PST = False

def _decode_actor_id(actor_val):
    # Convert PhysX actor/collider id → prim-path string. Handles:
    #   uint64 int (most common per pyi spec)
    #   int2/tuple (alternate dict-access form)
    #   already-resolved SdfPath / str
    # Returns ("" if can't decode) so caller can fall back to handle-string.
    try:
        if actor_val is None: return ""
        # Already a path object
        if hasattr(actor_val, 'GetString'):
            return actor_val.GetString()
        if hasattr(actor_val, 'pathString'):
            return actor_val.pathString
        # Tuple / int2 form
        if isinstance(actor_val, (tuple, list)) and len(actor_val) >= 2 and _HAS_PST:
            try: return str(_PST.decodeSdfPath(int(actor_val[0]), int(actor_val[1])))
            except: pass
        # uint64 form (the documented attribute-access shape)
        if isinstance(actor_val, int) and _HAS_PST:
            try: return str(_PST.intToSdfPath(int(actor_val)))
            except: pass
        # String — could already be a path, or a digit-string handle
        s = str(actor_val)
        if s.startswith("/"): return s
        if s.isdigit() and _HAS_PST:
            try: return str(_PST.intToSdfPath(int(s)))
            except: pass
        return ""
    except Exception:
        return ""

def _on_contact(contact_headers, contact_data):
    # PhysX contact-report callback: (headers, data). Each header has actor0/actor1
    # + contact_data_offset/num_contact_data pointing into the contact_data array.
    try:
        for header in contact_headers:
            # Get raw actor IDs (uint64). Try actor0 first, fall back to collider0
            # for shape-level reporting (some Kit versions emit colliders not actors).
            _a_raw = getattr(header, 'actor0', None)
            _b_raw = getattr(header, 'actor1', None)
            _ca_raw = getattr(header, 'collider0', None)
            _cb_raw = getattr(header, 'collider1', None)
            # Decode to prim-path. Prefer actor (rigid body root). Fall back to collider.
            a_path = _decode_actor_id(_a_raw) or _decode_actor_id(_ca_raw)
            b_path = _decode_actor_id(_b_raw) or _decode_actor_id(_cb_raw)
            # Raw handle-id fallback (for legacy/honesty: keep the digit-string)
            a_id = str(_a_raw) if _a_raw is not None else ""
            b_id = str(_b_raw) if _b_raw is not None else ""
            # Use decoded path if available, else fall through to handle-id string
            a = a_path if a_path else a_id
            b = b_path if b_path else b_id
            # One-shot debug log on first contact
            if not state.get('_contact_actor_type_logged'):
                state['_contact_actor_type_logged'] = True
                _at = type(_a_raw).__name__
                print(f"[VE] First contact actor0: type={{_at}}, raw={{_a_raw!r}}, decoded={{a_path!r}}", flush=True)
            if not a or not b: continue
            # Populate _handle_to_path opportunistically (resolved-at-capture, kept for legacy paths)
            if a_path and a_id and a_id not in _handle_to_path:
                _handle_to_path[a_id] = a_path
            if b_path and b_id and b_id not in _handle_to_path:
                _handle_to_path[b_id] = b_path
            # Sum penetration over this contact's data points
            _min_sep = float('inf')
            for i in range(header.contact_data_offset, header.contact_data_offset + header.num_contact_data):
                try:
                    sep = float(contact_data[i].separation)
                    if sep < _min_sep: _min_sep = sep
                except: pass
            # Use min separation as "impulse-proxy" (more negative = more penetration = more force)
            penetration = max(0.0, -_min_sep) if _min_sep != float('inf') else 0.0
            key = (_short(a), _short(b))
            state['contact_pair_count'][key] = state['contact_pair_count'].get(key, 0) + 1
            if penetration > state['contact_pair_max_impulse'].get(key, 0.0):
                state['contact_pair_max_impulse'][key] = penetration
            state['contact_pair_total_impulse'][key] = state['contact_pair_total_impulse'].get(key, 0.0) + penetration
            # Individual events for significant penetrations
            if penetration > 0.001 and len(state['contact_events']) < 2000:
                # Capture BOTH legacy short-form (a/b) AND resolved prim paths (prim_a/prim_b).
                # prim_a/prim_b may be None if decode failed — VE-detector callers must handle that.
                state['contact_events'].append({{
                    't': round((time.monotonic() - state['t_start']) if state['t_start'] else 0, 2),
                    'a': _short(a), 'b': _short(b),
                    'prim_a': a_path if a_path else None,
                    'prim_b': b_path if b_path else None,
                    'kind': _classify_pair(a_path or a, b_path or b),
                    'penetration_m': round(penetration, 4),
                }})
    except Exception: pass

# Apply PhysxContactReportAPI to all relevant prims so they participate in reports.
# Without this, PhysX silently doesn't fire callbacks for these pairs.
def _arm_contact_reporting():
    from pxr import PhysxSchema
    armed = []
    # Arm on all articulation links (robot) — try BOTH with CollisionAPI gate and also unconditionally
    for r in ARTICULATION_ROOTS:
        try:
            rp = stage.GetPrimAtPath(Sdf.Path(r))
            if not (rp and rp.IsValid()): continue
            for desc in stage.Traverse():
                p = str(desc.GetPath())
                if not (p == r or p.startswith(r + "/")): continue
                # Apply unconditionally — PhysxContactReportAPI is no-op on non-collision prims
                try:
                    PhysxSchema.PhysxContactReportAPI.Apply(desc)
                    if desc.HasAPI(UsdPhysics.CollisionAPI) or desc.HasAPI(UsdPhysics.RigidBodyAPI):
                        armed.append(p)
                except: pass
        except: pass
    # Arm on all MOVABLE_PRIMS — apply UNCONDITIONALLY since HasAPI gate had race condition
    # with template instantiation (cubes spawned but CollisionAPI not yet visible to traverse).
    # PhysxContactReportAPI.Apply is no-op on non-collision prims so safe to broad-apply.
    for m in MOVABLE_PATHS:
        try:
            mp = stage.GetPrimAtPath(Sdf.Path(m))
            if mp and mp.IsValid():
                PhysxSchema.PhysxContactReportAPI.Apply(mp)
                armed.append(m)  # always count — actual event capture verified via contact_events
        except: pass
    # Arm on TARGET_PATH + descendants
    if TARGET_PATH:
        try:
            tp = stage.GetPrimAtPath(Sdf.Path(TARGET_PATH))
            if tp and tp.IsValid():
                for desc in stage.Traverse():
                    p = str(desc.GetPath())
                    if not (p == TARGET_PATH or p.startswith(TARGET_PATH + "/")): continue
                    if desc.HasAPI(UsdPhysics.CollisionAPI):
                        PhysxSchema.PhysxContactReportAPI.Apply(desc)
                        armed.append(p)
        except: pass
    return armed
_armed_contact_prims = _arm_contact_reporting()
print(f"[VE] Contact-report API armed on {{len(_armed_contact_prims)}} prims", flush=True)

# Pre-build path→handle map for armed prims so we can resolve contact actor IDs post-sim.
_path_to_handle = {{}}
_handle_to_path = {{}}
try:
    _physx_simi = omni.physx.get_physx_simulation_interface()
    for p in _armed_contact_prims:
        try:
            # Try multiple API names
            h = None
            if hasattr(_physx_simi, 'get_rigid_body_id_by_path'):
                h = _physx_simi.get_rigid_body_id_by_path(p)
            elif hasattr(omni.physx, 'get_physx_interface'):
                _pxi = omni.physx.get_physx_interface()
                if hasattr(_pxi, 'get_rigidbody_handle'): h = _pxi.get_rigidbody_handle(p)
            if h is not None and h != 0:
                _path_to_handle[p] = h
                _handle_to_path[str(h)] = p
        except: pass
except: pass
print(f"[VE] Resolved path->handle for {{len(_path_to_handle)}} prims", flush=True)

try:
    _sim_iface = omni.physx.get_physx_simulation_interface()
    _contact_sub = _sim_iface.subscribe_contact_report_events(_on_contact)
    print(f"[VE] Contact-report subscription active", flush=True)
except Exception as _cse:
    print(f"[VE] Contact-report subscription FAILED: {{_cse}}", flush=True)
    _contact_sub = None

# Raycast support for end-of-sim
_phys_q = omni.physx.get_physx_scene_query_interface()
def _support_of(cp):
    # 2026-05-26 FIX: previous origin was cube_bottom - 5mm = inside/below thin bin floors.
    # New: origin = cube_TOP (well above cube), raycast down, filter out cube self via path-check.
    cbb = _world_bbox(cp); cf = _wp(cp)
    if cf is None: return (None, False)
    try:
        from carb import Float3
        z = (cbb['max'][2] + 0.005) if cbb else (cf[2] + 0.05)  # start above cube top
        o = Float3(float(cf[0]), float(cf[1]), float(z))
        d = Float3(0.0, 0.0, -1.0)
    except:
        z = (cbb['max'][2] + 0.005) if cbb else (cf[2] + 0.05)
        o = (float(cf[0]), float(cf[1]), float(z))
        d = (0.0, 0.0, -1.0)
    try:
        # Cast all hits up to 2m down; pick first non-self.
        hits = []
        try:
            def _coll(h):
                hits.append(dict(h) if isinstance(h, dict) else {{'hit':True,'rigidBody':getattr(h,'rigidBody',None),'collision':getattr(h,'collision',None)}})
                return True
            _phys_q.raycast_all(o, d, 2.0, _coll)
        except Exception:
            single = _phys_q.raycast_closest(o, d, 2.0)
            if single and single.get('hit'): hits = [single]
        cp_s = str(cp)
        for h in hits:
            sp = h.get('rigidBody') or h.get('collision')
            sp_s = str(sp) if sp else ''
            # Skip self-hits (cube hitting its own prim path/descendants)
            if sp_s and (sp_s == cp_s or sp_s.startswith(cp_s + '/') or cp_s.startswith(sp_s + '/')):
                continue
            return (sp_s, _is_under_target(sp_s))
    except: pass
    return (None, False)

# Run sim
tl = omni.timeline.get_timeline_interface()
tl.set_current_time(0.0)
tl.set_end_time(max(tl.get_end_time(), DURATION_S + 10))
tl.play()
app = omni.kit.app.get_app()
t0 = time.monotonic()
_primary_cp = CUBE_PATHS[0] if CUBE_PATHS else None
_post_deliv_frames = 0
_stable_frames = 0
_last_cube_pos = None
# Cube must end INSIDE the bin (below top of walls), not on rim. Use target_bbox.max[2] as bin top.
_bin_top_z = (target_bbox.get('max', [0,0,1e9])[2]) if target_bbox else 1e9
# Cube on floor = z ≈ bin_min_z + cube_half. Allow generous slack for tilt.
_cube_inside_z_cap = _bin_top_z  # cube center must be below bin top wall
while time.monotonic() - t0 < DURATION_S:
    app.update()
    # Early-exit logic:
    # 1. cube_in_target_ever flips True when cube enters target bbox XY-region (no upper-Z bound).
    # 2. Require cube center BELOW bin top wall (z < target_bbox.max[2]) — proves cube fell INTO bin,
    #    not resting on rim/lip.
    # 3. AND stable (<0.5mm/frame for 30 frames = settled).
    # 4. Hard fallback: 1200 frames (~20s) after first in-target.
    if _primary_cp and state['cube_in_target_ever'].get(_primary_cp):
        _post_deliv_frames += 1
        _z_now = None
        try:
            _np = _wp(_primary_cp)
            if _np is not None:
                _z_now = _np[2]
                if _last_cube_pos is not None:
                    _dd = ((_np[0]-_last_cube_pos[0])**2 + (_np[1]-_last_cube_pos[1])**2 + (_np[2]-_last_cube_pos[2])**2) ** 0.5
                    if _dd < 0.0005:
                        _stable_frames += 1
                    else:
                        _stable_frames = 0
                _last_cube_pos = _np
        except Exception:
            pass
        # Exit: cube actually inside bin AND stable
        if _z_now is not None and _z_now < _cube_inside_z_cap and _stable_frames > 30:
            break
        # Hard fallback: 1200 frames (~20s post-deliv)
        if _post_deliv_frames > 1200:
            break
tl.stop()
try: _sub.unsubscribe()
except: pass
try:
    if _contact_sub is not None: _contact_sub.unsubscribe()
except: pass

# Final state
cube_supports = {{}}
for cp in CUBE_PATHS:
    sp, ut = _support_of(cp)
    cube_supports[cp] = {{'support': sp, 'under_target': ut, 'final_pos': _wp(cp)}}

# Compute honesty gates
max_speed_overall = max(state['cube_max_speed'].values()) if state['cube_max_speed'] else 0.0
# 0.20m threshold (was 0.15) — measurement granularity: scene_observer samples
# every ~0.1s. FJ created at e.g. EE-cube=0.10m is gate-valid, but observer
# may not see it until ~0.1s later when EE has moved 0.05m. To stay honest:
# anything >0.20m IS telepathy (EE was clearly far when FJ formed). 0.15-0.20m
# is gray-zone (observer-rate artifact). Only flag clearly-bad teleports.
telepathic_fjs = [e for e in state['fj_events'] if e.get('distance') is not None and e['distance'] > 0.20]
primary_cube = CUBE_PATHS[0] if CUBE_PATHS else None
primary_support_ok = cube_supports.get(primary_cube, {{}}).get('under_target', False) if primary_cube else False
primary_in_target_ever = state['cube_in_target_ever'].get(primary_cube, False) if primary_cube else False
ee_min_z = state['ee_min_z'] if state['ee_min_z'] != float('inf') else None
ee_underground = (ee_min_z is not None and ee_min_z < TABLE_TOP_Z - 0.05)

honest_pass = bool(primary_support_ok and primary_in_target_ever
                   and not telepathic_fjs and max_speed_overall < 2.0
                   and not ee_underground)
# STRICT honest_pass — kräver INGA kvalitets-VE-triggers.
# 2026-05-22 Anton: "vi måste höja kraven, robust på alla".
# CP-NEW-brick-stacking exempel: programmatic honest_pass=True men har
# unrealistic_grip + delivered_then_dislodged + cube_tilts_over + partial_delivery
# + cube_bounces_off_target + picked_then_dropped. Strict-mode fångar det.
# Beräknas POST virtual_eyes (rad ~1990+).

# ---------------- ENGINE DATA: source-level telemetry (Anton R2 paradigm) ----------------
# "Diagnose under the hood, not on the bumper"
engine_data = {{}}

# Controller-state snapshot (ALL ctrl:* attrs on robot prim)
_ctrl_state = {{}}
try:
    _rp_t = stage.GetPrimAtPath(Sdf.Path(ROBOT_PATH))
    if _rp_t and _rp_t.IsValid():
        for attr in _rp_t.GetAttributes():
            an = attr.GetName()
            if an.startswith("ctrl:"):
                try:
                    v = attr.Get()
                    if v is None: _ctrl_state[an] = None
                    elif isinstance(v, (int, float, str, bool)): _ctrl_state[an] = v
                    else: _ctrl_state[an] = str(v)
                except: pass
except: pass
# Also try other articulation roots if ROBOT_PATH doesn't have ctrl:*
if not any(k for k in _ctrl_state if k != 'ctrl:phase'):
    for r in ARTICULATION_ROOTS:
        try:
            _rp_t = stage.GetPrimAtPath(Sdf.Path(r))
            if not (_rp_t and _rp_t.IsValid()): continue
            for attr in _rp_t.GetAttributes():
                an = attr.GetName()
                if an.startswith("ctrl:"):
                    try:
                        v = attr.Get()
                        k = f"{{r}}::{{an}}"
                        if v is None: _ctrl_state[k] = None
                        elif isinstance(v, (int, float, str, bool)): _ctrl_state[k] = v
                        else: _ctrl_state[k] = str(v)
                    except: pass
        except: pass

# PhysX contact summary (per-pair aggregates)
# Resolve actor IDs to prim paths using path→handle map built at setup
def _resolve(actor):
    # actor may already be a path string ("/World/..."), or an integer-id string
    if actor.startswith("/"): return actor
    return _handle_to_path.get(actor, actor)  # leave as ID if no mapping found

# Post-process pass: backfill prim_a/prim_b on contact_events that lack them.
# (Capture-time decode should already populate these; this is a safety net for
# any event that fell through the digit-id fallback path.) Also re-classify the
# kind once we have resolved paths.
for _ev in state['contact_events']:
    if _ev.get('prim_a') is None:
        _resolved_a = _resolve(_ev.get('a', ''))
        if _resolved_a and _resolved_a.startswith('/'):
            _ev['prim_a'] = _resolved_a
    if _ev.get('prim_b') is None:
        _resolved_b = _resolve(_ev.get('b', ''))
        if _resolved_b and _resolved_b.startswith('/'):
            _ev['prim_b'] = _resolved_b
    # Re-classify if we previously had unresolved IDs (kind would have been "other_vs_other")
    if _ev.get('prim_a') and _ev.get('prim_b') and _ev.get('kind') == 'other_vs_other':
        _ev['kind'] = _classify_pair(_ev['prim_a'], _ev['prim_b'])

_contact_summary = []
for key, count in state['contact_pair_count'].items():
    a, b = key
    max_imp = state['contact_pair_max_impulse'].get(key, 0.0)
    total_imp = state['contact_pair_total_impulse'].get(key, 0.0)
    _contact_summary.append({{
        "a": _resolve(a), "b": _resolve(b), "count": count,
        "max_impulse": round(max_imp, 3),
        "total_impulse": round(total_imp, 3),
    }})
_contact_summary.sort(key=lambda x: -x["total_impulse"])  # highest-stress first

# Contact pairs grouped by kind
_contact_by_kind = {{}}
for ev in state['contact_events']:
    k = ev.get('kind', 'unknown')
    _contact_by_kind[k] = _contact_by_kind.get(k, 0) + 1

# cuRobo planner stats from ctrl:plan_calls / ctrl:plan_fails (already in _ctrl_state)
_planner_stats = {{
    "plan_calls": _ctrl_state.get('ctrl:plan_calls') or 0,
    "plan_fails": _ctrl_state.get('ctrl:plan_fails') or 0,
    "last_fail_goal": _ctrl_state.get('ctrl:last_fail_goal') or "",
}}

# Articulation joint state (final snapshot via Articulation API)
_joint_state = {{}}
try:
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.prims import SingleArticulation
    for r in list(ARTICULATION_ROOTS)[:3]:  # cap to first 3 roots
        try:
            _art = SingleArticulation(r)
            _art.initialize()
            jp = _art.get_joint_positions()
            jv = _art.get_joint_velocities()
            je = None
            try: je = _art.get_measured_joint_efforts()
            except: pass
            _joint_state[r] = {{
                "positions": [float(x) for x in jp.tolist()] if jp is not None else None,
                "velocities": [float(x) for x in jv.tolist()] if jv is not None else None,
                "efforts": [float(x) for x in je.tolist()] if je is not None else None,
                "joint_names": _art.dof_names if hasattr(_art, 'dof_names') else None,
            }}
        except Exception as _je: _joint_state[r] = {{"error": str(_je)[:200]}}
except Exception as _jse: pass

# ---------------- VISION INPUT: viewport-projected prim-bboxes ----------------
# Capture data needed for offline SAM2/CLIP analysis. The actual viewport PNG
# capture happens via Kit's HTTP /capture endpoint from sweep_*_with_vision.py
# (post-sim). Here we just compute and dump the 3D→2D projection for each
# interesting prim using the active viewport camera matrices.
_vision_input = {{}}
try:
    import omni.kit.viewport.utility as _vp_util
    from pxr import UsdGeom as _UsdGeomV, Gf as _GfV
    _vp = _vp_util.get_active_viewport()
    if _vp:
        _cam_path = str(_vp.camera_path)
        _cam_prim = stage.GetPrimAtPath(Sdf.Path(_cam_path))
        if _cam_prim and _cam_prim.IsValid():
            _cam = _UsdGeomV.Camera(_cam_prim)
            _gf_cam = _cam.GetCamera(0)  # GfCamera (time-coded)
            # Get view + projection (4x4 GfMatrix4d each)
            _view = _gf_cam.frustum.ComputeViewMatrix()
            _proj = _gf_cam.frustum.ComputeProjectionMatrix()
            # Resolution from viewport
            try:
                _w, _h = _vp.resolution
                _w, _h = int(_w), int(_h)
            except Exception:
                _w, _h = 1280, 720
            def _world_to_pixel(p_world):
                # world → view → clip → NDC → pixel
                # USD/Gf is row-major: use v * M (not M * v which is column-vector convention)
                _v = _GfV.Vec4d(p_world[0], p_world[1], p_world[2], 1.0)
                _vc = _v * _view
                _cc = _vc * _proj
                if _cc[3] == 0: return None
                _nx, _ny, _nz = _cc[0]/_cc[3], _cc[1]/_cc[3], _cc[2]/_cc[3]
                # NDC range [-1,1] → pixel [0,W] × [0,H], Y flipped
                _px = (_nx + 1) * 0.5 * _w
                _py = (1 - _ny) * 0.5 * _h
                return (float(_px), float(_py), float(_nz))
            # For each interesting prim (cubes + bin + robot links if visible)
            _bb_cache = _UsdGeomV.BBoxCache(0, [_UsdGeomV.Tokens.default_])
            # 2026-05-21: utöka prim-selection till MOVABLE_PATHS (alla auto-discovered
            # manipulables, inte bara simulate_args.cube_paths). Tidigare missade cubes
            # på templates där cube-prim var i SOURCE_PATHS men inte CUBE_PATHS.
            _interesting = list(set(list(CUBE_PATHS) + list(MOVABLE_PATHS) +
                                    ([TARGET_PATH] if TARGET_PATH else [])))
            # Also probe gripper-relevant prim (for render_decoupled detection)
            for r in list(ARTICULATION_ROOTS)[:1]:
                # add likely gripper/hand prims under each articulation
                for sub in ('panda_hand', 'panda_leftfinger', 'panda_rightfinger',
                            'tool0', 'ee_link', 'wrist_3_link', 'gripper'):
                    _gp = f"{{r}}/{{sub}}"
                    if stage.GetPrimAtPath(Sdf.Path(_gp)).IsValid():
                        _interesting.append(_gp)
            for _pp in _interesting:
                _pr = stage.GetPrimAtPath(Sdf.Path(_pp))
                if not (_pr and _pr.IsValid()): continue
                try:
                    _bb = _bb_cache.ComputeWorldBound(_pr).ComputeAlignedRange()
                    _mn, _mx = _bb.GetMin(), _bb.GetMax()
                    # 8 AABB corners → project all, take pixel min/max
                    _corners = [(_mn[0]+ (i&1)*(_mx[0]-_mn[0]),
                                  _mn[1]+ ((i>>1)&1)*(_mx[1]-_mn[1]),
                                  _mn[2]+ ((i>>2)&1)*(_mx[2]-_mn[2])) for i in range(8)]
                    _projected = [_world_to_pixel(c) for c in _corners]
                    _projected = [p for p in _projected if p is not None and p[2] < 1]  # in front of cam
                    if not _projected: continue
                    _pxs = [p[0] for p in _projected]
                    _pys = [p[1] for p in _projected]
                    _bbox2d = [round(min(_pxs), 1), round(min(_pys), 1),
                                round(max(_pxs), 1), round(max(_pys), 1)]
                    # Clamp to image bounds + skip if completely off-screen
                    _b = [max(0, _bbox2d[0]), max(0, _bbox2d[1]),
                          min(_w, _bbox2d[2]), min(_h, _bbox2d[3])]
                    if _b[2] <= _b[0] or _b[3] <= _b[1]: continue  # off-screen
                    if (_b[2]-_b[0])*(_b[3]-_b[1]) < 400: continue  # < 20×20 px
                    # Center for point-prompt fallback
                    _cx = round((_b[0]+_b[2])/2, 1); _cy = round((_b[1]+_b[3])/2, 1)
                    _vision_input[_pp] = {{
                        "bbox_2d": _b,
                        "center_px": [_cx, _cy],
                        "expected_kind": ("cube" if "cube" in _pp.lower() else
                                          "gripper" if any(k in _pp.lower() for k in ("hand","finger","tool0","gripper")) else
                                          "bin" if any(k in _pp.lower() for k in ("bin","tray","pallet","slot")) else
                                          "robot_link"),
                    }}
                except Exception: pass
            # Also save viewport size + camera identity for analyzer
            _vision_input["__viewport__"] = {{
                "width": _w, "height": _h, "camera_path": _cam_path,
            }}
except Exception as _ve_exc:
    _vision_input["__error__"] = str(_ve_exc)[:200]

engine_data = {{
    "ctrl_state": _ctrl_state,
    "planner_stats": _planner_stats,
    "vision_input": _vision_input,
    "phase_history": state['phase_history'][-50:],  # last 50 phase transitions
    "contact_pair_summary": _contact_summary[:30],  # top 30 contact pairs by total-impulse
    "contact_events_count": len(state['contact_events']),
    "contact_events_sample": state['contact_events'][:2000],  # 2026-05-22 RL-tune: 30→2000 så Cube_L/R-kollisioner ej missas
    "contact_by_kind": _contact_by_kind,
    "joint_state": _joint_state,
    "articulation_roots": list(ARTICULATION_ROOTS),
    "movable_prims": list(MOVABLE_PATHS),
    "armed_contact_prims_count": len(_armed_contact_prims),
    "armed_contact_prims_sample": _armed_contact_prims[:10],
    "joint_efforts_over_time_count": len(state['joint_efforts_over_time']),
    "joint_efforts_max": state['joint_efforts_max'],
    "physx_step_times": state['physx_step_times'][:30],  # first 30 samples
}}

# ---------------- VIRTUAL EYES: post-sim pattern detectors ----------------
ve_patterns = {{}}
# Detect mobile robot via articulation root name OR wheels in scene
_is_mobile_robot = False
for r in ARTICULATION_ROOTS:
    rn = r.lower()
    if any(k in rn for k in ("carter", "jetbot", "amr", "mobile")):
        _is_mobile_robot = True; break
# Fallback: any prim has "wheel" in name
if not _is_mobile_robot:
    try:
        for prim in stage.Traverse():
            if 'wheel' in prim.GetName().lower(): _is_mobile_robot = True; break
    except: pass
_table_top = TABLE_TOP_Z

def _ve(name, detected, evidence=None):
    ve_patterns[name] = {{"detected": bool(detected), "evidence": evidence or {{}}}}

# 1. telepathic_contact — reuse existing data
_tel = state['fj_events']
_telepathy = [e for e in _tel if e.get('distance') is not None and e['distance'] > 0.20]
_ve("telepathic_contact", bool(_telepathy),
    {{"max_distance": max((e['distance'] for e in _telepathy), default=0)}} if _telepathy else None)

# 2. never_picked — no FJ ever AND cube didn't reach target
_never_picked_cubes = [cp for cp in CUBE_PATHS
                       if not any(e.get('cube')==cp for e in state['fj_events'])
                       and not state['cube_in_target_ever'].get(cp)]
_ve("never_picked", bool(_never_picked_cubes), {{"cubes": _never_picked_cubes}} if _never_picked_cubes else None)

# 3. picked_then_dropped — cube was gripped but ended off-target with z low
_picked_dropped = []
for cp in CUBE_PATHS:
    _gripped = any(e.get('cube')==cp for e in state['fj_events'])
    _fp = cube_supports.get(cp, {{}}).get('final_pos')
    if _gripped and _fp and _fp[2] < _table_top + 0.05 and not cube_supports.get(cp, {{}}).get('under_target'):
        _picked_dropped.append(cp)
_ve("picked_then_dropped", bool(_picked_dropped), {{"cubes": _picked_dropped}} if _picked_dropped else None)

# 4. delivered_then_dislodged — reached target but ended off-target
_dislodged = []
for cp in CUBE_PATHS:
    if state['cube_in_target_ever'].get(cp) and not cube_supports.get(cp, {{}}).get('under_target'):
        _fp = cube_supports.get(cp, {{}}).get('final_pos')
        _dislodged.append({{"cube": cp, "drift_xy": state['cube_xy_drift_post_target'].get(cp, 0),
                           "final_pos": _fp, "support": cube_supports.get(cp, {{}}).get('support')}})
_ve("delivered_then_dislodged", bool(_dislodged), {{"events": _dislodged}} if _dislodged else None)

# 5. cube_shifted_at_placement — cube reached target, xy drifted > 0.03m post-target, still on target
_shifted = []
for cp in CUBE_PATHS:
    _drift = state['cube_xy_drift_post_target'].get(cp, 0)
    if state['cube_in_target_ever'].get(cp) and 0.03 < _drift < 0.20 and cube_supports.get(cp, {{}}).get('under_target'):
        _shifted.append({{"cube": cp, "drift": round(_drift, 3)}})
_ve("cube_shifted_at_placement", bool(_shifted), {{"events": _shifted}} if _shifted else None)

# 6. arm_speed_yeet — high EE speed during placement window.
# 2026-05-21: raised threshold 1.5→2.5 m/s. Anton's real YEET cases showed
# ee_max 3-7 m/s. 1.5 m/s is normal cuRobo motion, too aggressive.
_ee_max_pp = state['ee_max_speed_in_placement']
_ve("arm_speed_yeet", _ee_max_pp > 2.5, {{"ee_max_speed": round(_ee_max_pp, 2)}} if _ee_max_pp > 1.5 else None)

# 7. bin_wall_collision — proxy via EE position deep inside bin AABB
# (without contact-report we use geometric proxy: EE z below target rim while xy inside target footprint)
# Tightened: require AT LEAST ONE cube to have reached target (proves controller engaged with bin).
# Otherwise "stuck in wait_sensor" scenarios get false-positive when EE happens to be near bin.
_bw = False; _bw_evid = None
_any_in_target = any(state['cube_in_target_ever'].values())
if target_bbox and _any_in_target:
    _tbm = target_bbox.get('min'); _tbx = target_bbox.get('max')
    if _tbm and _tbx and (_tbx[2] - _tbm[2]) > 0.07:  # only bins, not pall
        for t in state['trajectory']:
            _e = t.get('ee')
            if _e and _tbm[0] < _e[0] < _tbx[0] and _tbm[1] < _e[1] < _tbx[1] and _e[2] < _tbm[2] + 0.02:
                _bw = True; _bw_evid = {{"t": t['t'], "ee_z": round(_e[2], 3), "bin_min_z": round(_tbm[2], 3)}}; break
_ve("bin_wall_collision", _bw, _bw_evid)

# 8. blowup_at_release — cube velocity > 5 m/s at any point
_max_v = max_speed_overall
_ve("blowup_at_release", _max_v > 5.0, {{"max_speed": round(_max_v, 2)}} if _max_v > 2.0 else None)

# 9. robot_through_floor — already captured via ee_underground gate.
# Distinguish: ee_z < -10m = robot explosion (numerical instability),
# -10m < ee_z < floor_z = real "through floor" bug.
_robot_explode = (ee_min_z is not None and ee_min_z < -10.0)
_robot_through = ee_underground and not _robot_explode
_ve("robot_through_floor", _robot_through, {{"ee_min_z": round(ee_min_z, 3) if ee_min_z else None}} if _robot_through else None)
_ve("robot_explodes", _robot_explode, {{"ee_min_z": round(ee_min_z, 3) if ee_min_z else None}} if _robot_explode else None)

# 10/11/12. Mobile robot patterns
if _is_mobile_robot and state['robot_base_z']:
    _zs = [z for _, z in state['robot_base_z']]
    _min_base_z = min(_zs)
    # Mobile robot base normally on world ground (z≈0). "Under floor" = z < -0.05.
    _under = _min_base_z < -0.05
    _ve("mobile_robot_under_floor", _under, {{"min_base_z": round(_min_base_z, 3)}} if _under else None)
    # under_floor_at_load: z was below floor at start, then rose. Anton's "Carter under golvet vid play, åker upp"
    _initial_base_z = state['spawn_robot_pos'][2] if state['spawn_robot_pos'] else None
    _later_max_z = max((z for t, z in state['robot_base_z'] if t > 0.5), default=None)
    _rose = (_later_max_z is not None and _initial_base_z is not None
             and _initial_base_z < -0.05 and _later_max_z - _initial_base_z > 0.3)
    _ve("mobile_robot_under_floor_at_load", _rose,
        {{"initial_z": round(_initial_base_z, 3), "later_max_z": round(_later_max_z, 3) if _later_max_z else None}} if _rose else None)
    # vibrating: std over 5s window > 0.005 but mean position change < 0.05
    if len(state['robot_base_pos']) >= 10:
        _ps = [p for _, p in state['robot_base_pos']]
        _xs = [p[0] for p in _ps]; _ys = [p[1] for p in _ps]
        _x_range = max(_xs) - min(_xs); _y_range = max(_ys) - min(_ys)
        _mean_delta = math.sqrt((_ps[-1][0]-_ps[0][0])**2 + (_ps[-1][1]-_ps[0][1])**2)
        # crude std proxy: mean abs delta from mean
        _xm = sum(_xs)/len(_xs); _ym = sum(_ys)/len(_ys)
        _xstd = sum(abs(x-_xm) for x in _xs)/len(_xs); _ystd = sum(abs(y-_ym) for y in _ys)/len(_ys)
        _vibrating = (_xstd > 0.005 or _ystd > 0.005) and _mean_delta < 0.05
        _ve("mobile_robot_vibrating", _vibrating,
            {{"xstd": round(_xstd, 4), "ystd": round(_ystd, 4), "translation": round(_mean_delta, 3)}} if _vibrating else None)
        # Mobile robot not moving: xy displacement < 1cm. For nav-only templates
        # (no cubes), this is the primary success metric. For cube-handling
        # templates, mobile robot should also navigate.
        _not_moving = (_x_range < 0.01 and _y_range < 0.01)
        _ve("mobile_robot_not_moving", _not_moving,
            {{"x_range": round(_x_range, 4), "y_range": round(_y_range, 4), "is_nav_only": len(CUBE_PATHS) == 0}} if _not_moving else None)
    else:
        _ve("mobile_robot_vibrating", False)
        _ve("mobile_robot_not_moving", False)
else:
    _ve("mobile_robot_under_floor", False)
    _ve("mobile_robot_vibrating", False)
    _ve("mobile_robot_not_moving", False)

# 13. cube_under_table — spawn position z < table_top - 0.05
_under_table = []
for cp in CUBE_PATHS:
    _sp = state['spawn_pos'].get(cp)
    if _sp and _sp[2] < _table_top - 0.05:
        _under_table.append({{"cube": cp, "spawn_z": round(_sp[2], 3)}})
_ve("cube_under_table", bool(_under_table), {{"events": _under_table}} if _under_table else None)

# 14. cube_floats_no_gravity — cube z-range < 0.01 over duration AND z > table+0.10 AND no FJ
_floating = []
for cp in CUBE_PATHS:
    _traj_z = [t['cubes'].get(cp, [0,0,0])[2] if t['cubes'].get(cp) else None for t in state['trajectory']]
    _traj_z = [z for z in _traj_z if z is not None]
    if len(_traj_z) > 5:
        _zr = max(_traj_z) - min(_traj_z)
        _z_avg = sum(_traj_z)/len(_traj_z)
        _gripped = any(e.get('cube')==cp for e in state['fj_events'])
        if _zr < 0.01 and _z_avg > _table_top + 0.10 and not _gripped:
            _floating.append({{"cube": cp, "z_avg": round(_z_avg, 3)}})

# Also detect prims with Cube-type that have NO RigidBodyAPI (won't be in MOVABLE_PRIMS)
# Anton R2 CP-76: "mitten-kub svävar (gravity ej fixat trots RigidBodyAPI-rewrite)" — middle
# cube might not have RigidBodyAPI at all, or template-rewrite didn't apply.
_norb_floats = []
try:
    for prim in stage.Traverse():
        t = str(prim.GetTypeName())
        pth = str(prim.GetPath())
        if t != 'Cube' or _is_under_robot(pth): continue
        if pth in CUBE_PATHS: continue
        # Skip target/destination — static fixtures are expected to "float"
        if TARGET_PATH and (pth == TARGET_PATH or pth.startswith(TARGET_PATH + "/")): continue
        # Skip well-known scene-fixture names (ground, table, conveyor, etc.)
        _ln = prim.GetName().lower()
        if any(k in _ln for k in ('ground', 'table', 'conveyor', 'belt', 'wall', 'floor', 'pedestal', 'pall', 'bin', 'tray', 'fixture', 'sensor', 'marker', 'guard', 'rail', 'sign')):
            continue
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            p = _wp(pth)
            # Lowered threshold: > table+0.03 catches just-above-table mid-air objects
            if p and p[2] > _table_top + 0.03:
                bb = _world_bbox(pth)
                if bb:
                    dims = [bb['max'][i] - bb['min'][i] for i in range(3)]
                    if max(dims) < 0.50:  # small cube-like prim
                        _norb_floats.append({{"prim": pth, "z": round(p[2], 3), "has_rigidbody": False}})
except: pass
if _norb_floats:
    _floating.extend(_norb_floats)
_ve("cube_floats_no_gravity", bool(_floating), {{"events": _floating}} if _floating else None)

# 15. non_workpiece_floats_no_physics — real implementation now (R2 iter)
# Find any MOVABLE prim (not a cube/workpiece per CUBE_PATHS) that:
#   - has gravity disabled OR no RigidBodyAPI (but our discovery includes only RB)
#   - sat stationary high above table
_floats_extra = []
_cube_set = set(CUBE_PATHS)
for m, info in MOVABLE_PRIMS.items():
    if m in _cube_set: continue  # cubes covered by #14
    sp = state['movable_spawn_pos'].get(m)
    zr = state['movable_z_range'].get(m, [0, 0])
    if not sp: continue
    # gravity-disabled flag OR stayed within 0.01m of spawn z AND z high above table
    z_stable = (zr[1] - zr[0]) < 0.01
    z_high = sp[2] > _table_top + 0.10
    if (info.get('gravity_disabled') or (z_stable and z_high)):
        _floats_extra.append({{"prim": m, "spawn_z": round(sp[2], 3), "gravity_disabled": info.get('gravity_disabled', False)}})
_ve("non_cube_object_floats", bool(_floats_extra), {{"events": _floats_extra}} if _floats_extra else None)

# 16. routing_failure — placeholder (needs expected_routing map)
_ve("routing_failure", False)

# 17. controller_stuck_idle — phase=wait_sensor > 30s AND cubes never delivered
_stuck = False; _stuck_evid = None
if state['phase_history']:
    _ws_times = [t for t, p in state['phase_history'] if 'wait_sensor' in p.lower() or 'idle' in p.lower()]
    if _ws_times:
        _stuck_dur = max(_ws_times) - min(_ws_times)
        _delivered_any = any(cube_supports.get(cp, {{}}).get('under_target') for cp in CUBE_PATHS)
        if _stuck_dur > 30 and not _delivered_any:
            _stuck = True; _stuck_evid = {{"duration_s": round(_stuck_dur, 1)}}
_ve("controller_stuck_idle", _stuck, _stuck_evid)

# 18. infinite_grip_oscillation — FJ create count for same cube > 3
_grip_counts = {{}}
for e in state['fj_events']:
    cp = e.get('cube')
    if cp: _grip_counts[cp] = _grip_counts.get(cp, 0) + 1
_osc_cubes = [cp for cp, n in _grip_counts.items() if n > 3]
_ve("infinite_grip_oscillation", bool(_osc_cubes), {{"cube_counts": _grip_counts}} if _osc_cubes else None)

# 19. cube_spawn_off_belt — real impl now (R2 iter)
_off_belt = []
if CONVEYOR_BBOX:
    _cb_min = CONVEYOR_BBOX['min']; _cb_max = CONVEYOR_BBOX['max']
    for cp in CUBE_PATHS:
        sp = state['spawn_pos'].get(cp)
        if not sp: continue
        # in XY range of conveyor and z near belt top? else off-belt
        on_belt = (_cb_min[0] - 0.02 <= sp[0] <= _cb_max[0] + 0.02
                   and _cb_min[1] - 0.02 <= sp[1] <= _cb_max[1] + 0.02
                   and sp[2] >= _cb_max[2] - 0.05)
        if not on_belt and sp[2] < _table_top + 0.20:
            # cube spawned NOT on belt despite being a workpiece — bug
            _off_belt.append({{"cube": cp, "spawn": [round(v, 3) for v in sp], "conveyor_xy": [_cb_min[0], _cb_min[1], _cb_max[0], _cb_max[1]]}})
_ve("cube_spawn_off_belt", bool(_off_belt), {{"events": _off_belt}} if _off_belt else None)

# 20. physics_errors_at_play — capture via Kit console scan
_phys_errs = []
try:
    import omni.kit.app as _oka
    # scan log buffer (limited, depends on Kit's log retention)
    # fallback: skip if not available
    pass
except: pass
# heuristic: physics errors often correlate with robot teleport, missing prims, or floating objects
# For now: rely on robot_teleport / scene_missing_required_asset as proxies
_ve("physics_errors_at_play", False)  # need direct console subscribe; deferred until contact-report wiring

# 25. ur10_horizontal_start (NEW from taxonomy)
# Detection: at t=end of sim, shoulder_lift joint is near 0 (arm extended sideways).
# Correct home pose has shoulder_lift ~= -1.57 rad. If joint stays near 0 → horizontal.
# (Final joint state is more reliable than initial EE pos which can be mid-trajectory.)
_ur10_horiz = False; _ur10_evid = None
_is_ur = any('ur' in r.lower() or 'ur10' in r.lower() for r in ARTICULATION_ROOTS)
if _is_ur:
    # Read shoulder_lift from joint_state captured at end
    _shoulder_lift = None
    try:
        from isaacsim.core.prims import SingleArticulation as _SArt_d
        for r in ARTICULATION_ROOTS:
            try:
                _ad = _SArt_d(r); _ad.initialize()
                _dn = list(_ad.dof_names) if _ad.dof_names else []
                _pos = _ad.get_joint_positions()
                if _pos is not None:
                    for _jn, _v in zip(_dn, _pos.tolist()):
                        if _jn == 'shoulder_lift_joint':
                            _shoulder_lift = float(_v); break
                    if _shoulder_lift is not None: break
            except: pass
    except: pass
    # Horizontal if shoulder_lift close to 0 (within ±0.3 rad); home is near -1.57
    if _shoulder_lift is not None and abs(_shoulder_lift) < 0.5:
        _ur10_horiz = True
        _ur10_evid = {{"shoulder_lift_rad": round(_shoulder_lift, 3),
                       "expected_home_rad": -1.5708}}
_ve("ur10_horizontal_start", _ur10_horiz, _ur10_evid)

# 26. scene_missing_required_asset (NEW)
# Only flag if NO articulation roots discovered (truly no robot in scene)
# OR if a specifically-named cube_path is missing.
_missing = []
if not ARTICULATION_ROOTS:
    _missing.append({{"path": ROBOT_PATH or "(unknown)", "role": "robot"}})
if TARGET_PATH:
    pr = stage.GetPrimAtPath(Sdf.Path(TARGET_PATH))
    if not (pr and pr.IsValid()):
        _missing.append({{"path": TARGET_PATH, "role": "target"}})
for cp in CUBE_PATHS:
    pr = stage.GetPrimAtPath(Sdf.Path(cp))
    if not (pr and pr.IsValid()):
        _missing.append({{"path": cp, "role": "cube"}})
_ve("scene_missing_required_asset", bool(_missing), {{"events": _missing}} if _missing else None)

# 27. wrong_object_type_present (NEW)
_wrong_types = []
for cp, info in INITIAL_OBJECT_TYPES.items():
    _t = info.get('prim_type', '')
    _aspect = info.get('aspect_ratio', 1)
    # Expected: Cube prim type OR aspect close to 1 (any RigidBody-cube-like)
    if _t and 'cube' not in _t.lower() and _aspect > 2.0:
        # not a cube and not cubic-shaped — Anton may flag as "platta"
        _wrong_types.append({{"cube_path": cp, "actual_type": _t, "aspect": _aspect, "dims": info.get('dims')}})
_ve("wrong_object_type_present", bool(_wrong_types), {{"events": _wrong_types}} if _wrong_types else None)

# arm_collides_with_bin_walls (R2 iter) — from contact_events captured during sim
_arm_bin_coll = []
for ev in state.get('contact_events', [])[:200]:
    other = ev.get('other', '')
    other_lc = other.lower()
    # Filter: other side has 'bin' or 'wall' in name (excluding cube/floor/conveyor)
    if any(k in other_lc for k in ('bin', 'wall', 'tray', 'fixture', 'slot')) \
       and not any(k in other_lc for k in ('cube', 'floor', 'ground', 'conveyor', 'belt', 'table')) \
       and ev.get('impulse', 0) > 1.0:
        # Skip gripper-finger contacts (legitimate during grasp/release)
        link = ev.get('robot_link', '')
        if 'finger' in link.lower(): continue
        _arm_bin_coll.append({{"t": ev['t'], "link": link, "other": other, "impulse": round(ev['impulse'], 2)}})
        if len(_arm_bin_coll) >= 5: break
_ve("arm_collides_with_bin_walls", bool(_arm_bin_coll), {{"events": _arm_bin_coll}} if _arm_bin_coll else None)

# cube_tilts_over (R2 iter — Anton "kub 3 flakar")
# Tightened: only flag tilt > 45° AND cube ended outside target zone (real bug, not just lid)
_tilts = []
for cp, ang in state['cube_max_tilt_deg'].items():
    if ang > 45 and not cube_supports.get(cp, {{}}).get('under_target'):
        _tilts.append({{"cube": cp, "tilt_deg": round(ang, 1)}})
_ve("cube_tilts_over", bool(_tilts), {{"events": _tilts}} if _tilts else None)

# partial_delivery (R2 iter — Anton "3/5 i bin, platta+1 utanför")
_n_total = len(CUBE_PATHS)
_n_delivered = sum(1 for cp in CUBE_PATHS if cube_supports.get(cp, {{}}).get('under_target'))
_partial = (_n_total >= 2 and 0 < _n_delivered < _n_total)
_ve("partial_delivery", _partial, {{"delivered": _n_delivered, "total": _n_total}} if _partial else None)

# cube_bounces_off_target (R2 iter — Anton CP-28 "studsar till golvet")
_bounces = []
for cp in CUBE_PATHS:
    if state['cube_in_target_ever'].get(cp):
        # Was in target, ended NOT in target with significant z drop
        fp = cube_supports.get(cp, {{}}).get('final_pos')
        max_z_in_t = state['cube_z_in_target_max'].get(cp, 0)
        if fp and max_z_in_t > 0 and max_z_in_t - fp[2] > 0.15 and not cube_supports.get(cp, {{}}).get('under_target'):
            _bounces.append({{"cube": cp, "max_z_in_target": round(max_z_in_t, 3), "final_z": round(fp[2], 3)}})
_ve("cube_bounces_off_target", bool(_bounces), {{"events": _bounces}} if _bounces else None)

# gripper_cannot_release proxy (R2 iter)
# If a cube was gripped during run AND at end_of_sim it's within 10cm of EE
# AND that EE position is NOT a destination → gripper failed to release.
_grip_fail = []
_ee_final = state['prev_ee_pos']
if _ee_final:
    for cp in CUBE_PATHS:
        was_gripped = any(e.get('cube') == cp for e in state['fj_events'])
        if not was_gripped: continue
        fp = cube_supports.get(cp, {{}}).get('final_pos')
        if not fp: continue
        d = math.sqrt(sum((fp[i] - _ee_final[i])**2 for i in range(3)))
        # Cube still near EE at end AND not on target
        if d < 0.15 and not cube_supports.get(cp, {{}}).get('under_target'):
            _grip_fail.append({{"cube": cp, "distance_to_ee_at_end": round(d, 3)}})
_ve("gripper_cannot_release", bool(_grip_fail), {{"events": _grip_fail}} if _grip_fail else None)

# robot_vibration — joint efforts oscillate (rapid sign flips) without EE making progress.
# Anton CP-24/CP-28: arm "vibrerar" — joints fight each other instead of smooth motion.
# Source: state['joint_efforts_over_time'] is sampled ~1 Hz; we cannot literally see 5 Hz
# oscillation due to Nyquist, but effort *sign-change-rate* in the sampled series captures
# the controller "fighting itself" signature (commanded torque alternates direction every
# sample). EE displacement (from state['trajectory'], ~2 Hz) confirms "no progress".
# Strategy: scan 2-second sliding windows. For each window with ≥3 effort samples, find the
# joint with the highest sign-change-rate across delta(effort) and pair with EE displacement
# over that same window. Trigger if rate > 5 Hz AND EE displacement < 0.05 m.
# If the 1 Hz effort series is too sparse for a 2-s window (<3 samples), fall back to a 4-s
# window so we still get at least 3 effort samples.
_vibration = False; _vib_evid = None
_jeot = state['joint_efforts_over_time']
if len(_jeot) >= 3:
    # Reconstruct joint name list once (use last sampled articulation)
    _vib_joint_names = []
    try:
        from isaacsim.core.prims import SingleArticulation as _SArt_v
        for _r in list(ARTICULATION_ROOTS)[:1]:
            try:
                _av = _SArt_v(_r); _av.initialize()
                _vib_joint_names = list(_av.dof_names) if _av.dof_names else []
            except Exception: pass
    except Exception: pass
    _n_dof = max((len(ef) for _, ef in _jeot), default=0)
    if not _vib_joint_names or len(_vib_joint_names) != _n_dof:
        _vib_joint_names = ["joint_{{}}".format(i) for i in range(_n_dof)]
    # Build EE trajectory lookup (sparse, ~2 Hz)
    _ee_traj = [(t.get('t'), t.get('ee')) for t in state['trajectory']
                if t.get('t') is not None and t.get('ee') is not None]
    def _ee_disp(_t0, _t1):
        _w = [p for tt, p in _ee_traj if _t0 <= tt <= _t1]
        if len(_w) < 2: return None
        return math.sqrt(sum((_w[-1][i] - _w[0][i])**2 for i in range(3)))
    # Pick window length: prefer 2.0 s, expand to 4.0 s if too few effort samples
    _window_s = 2.0
    if len(_jeot) >= 2:
        _avg_dt = (_jeot[-1][0] - _jeot[0][0]) / max(len(_jeot) - 1, 1)
        if _avg_dt > 0.7:  # >0.7 s between samples → 2 s gives <3 samples
            _window_s = 4.0
    _best = None  # (rate, joint_idx, t_start, t_end, ee_disp, n_samples)
    for _i_start in range(len(_jeot)):
        _t_start = _jeot[_i_start][0]
        _t_end = _t_start + _window_s
        _wnd = [(_t, _ef) for _t, _ef in _jeot[_i_start:] if _t <= _t_end]
        if len(_wnd) < 3: continue
        _t0_w = _wnd[0][0]; _t1_w = _wnd[-1][0]
        _dur = max(_t1_w - _t0_w, 1e-3)
        for _ji in range(_n_dof):
            # Build effort series for this joint across window
            _series = [_ef[_ji] for _, _ef in _wnd if _ji < len(_ef)]
            if len(_series) < 3: continue
            # Sign-changes of FIRST DIFFERENCE (delta_effort) — captures rapid alternation
            _diffs = [_series[k+1] - _series[k] for k in range(len(_series)-1)]
            _sc = 0; _prev_sign = 0
            for _d in _diffs:
                if abs(_d) < 1e-6: continue  # ignore noise-zero deltas
                _s = 1 if _d > 0 else -1
                if _prev_sign != 0 and _s != _prev_sign:
                    _sc += 1
                _prev_sign = _s
            _rate = _sc / _dur
            if _best is None or _rate > _best[0]:
                _ee_d = _ee_disp(_t0_w, _t1_w)
                _best = (_rate, _ji, _t0_w, _t1_w, _ee_d, len(_series))
    if _best is not None:
        _rate, _ji, _t0_w, _t1_w, _ee_d, _ns = _best
        # Trigger: sign-change rate > 5 Hz AND EE displacement < 0.05 m in same window
        # (if EE displacement is unknown — too few trajectory samples — be conservative
        # and require rate > 8 Hz to avoid false positives from sparse data)
        _trigger = False
        if _ee_d is not None:
            _trigger = (_rate > 5.0 and _ee_d < 0.05)
        else:
            _trigger = (_rate > 8.0)
        if _trigger:
            _vibration = True
            _vib_evid = {{
                "joint_name": _vib_joint_names[_ji] if _ji < len(_vib_joint_names) else "joint_{{}}".format(_ji),
                "sign_changes_per_s": round(_rate, 2),
                "ee_displacement_m": round(_ee_d, 4) if _ee_d is not None else None,
                "window_t_start": round(_t0_w, 2),
                "window_t_end": round(_t1_w, 2),
                "effort_samples_in_window": _ns,
                "effort_sample_rate_hz": round(len(_jeot) / max(_jeot[-1][0] - _jeot[0][0], 1e-3), 2),
            }}
_ve("robot_vibration", _vibration, _vib_evid)

# routing_failure (NEW - basic impl)
# Find all destinations in scene (Bin/Tray/Slot/Pallet prims with bbox)
# If ≥2 destinations AND all delivered cubes in same one → routing_failure
_destinations = []
for prim in stage.Traverse():
    n = prim.GetName().lower()
    pth = str(prim.GetPath())
    if any(k in n for k in ("bin", "tray", "slot", "destination", "pallet")) and not _is_under_robot(pth):
        bb = _world_bbox(pth)
        if bb: _destinations.append((pth, bb))
_routing_fail = False; _routing_evid = None
if len(_destinations) >= 2 and len(CUBE_PATHS) >= 2:
    # For each cube, find which destination it ended in (if any)
    cube_dests = {{}}
    for cp in CUBE_PATHS:
        fp = cube_supports.get(cp, {{}}).get('final_pos')
        if not fp: continue
        for dpth, dbb in _destinations:
            if (dbb['min'][0]-0.05 <= fp[0] <= dbb['max'][0]+0.05
                and dbb['min'][1]-0.05 <= fp[1] <= dbb['max'][1]+0.05):
                cube_dests[cp] = dpth; break
    # All delivered cubes went to same destination?
    delivered_dests = list(cube_dests.values())
    if len(delivered_dests) >= 2 and len(set(delivered_dests)) == 1:
        _routing_fail = True
        _routing_evid = {{"cube_destinations": cube_dests, "available_destinations": [p for p, _ in _destinations]}}
_ve("routing_failure", _routing_fail, _routing_evid)

# 28. cube_disappears_or_respawns (NEW)
_disappear = False; _dis_evid = None
if state['cube_prim_count_history']:
    _max_n = max(n for _, n in state['cube_prim_count_history'])
    _final_n = state['cube_prim_count_history'][-1][1]
    if _max_n > _final_n:
        _disappear = True
        _dis_evid = {{"max_count": _max_n, "final_count": _final_n}}
    else:
        # also check: any cube z < -1.0m (fell into void)
        for cp in CUBE_PATHS:
            fp = cube_supports.get(cp, {{}}).get('final_pos')
            if fp and fp[2] < -1.0:
                _disappear = True
                _dis_evid = {{"cube": cp, "fell_to_z": round(fp[2], 2)}}
                break
_ve("cube_disappears_or_respawns", _disappear, _dis_evid)

# 21. robot_teleport_at_play — spawn_robot_pos vs first sample after 0.5s
_teleport = False; _tev = None
if state['spawn_robot_pos'] and state['robot_base_pos']:
    _later = [p for t, p in state['robot_base_pos'] if t > 1.0]
    if _later:
        _d = math.sqrt(sum((_later[0][i]-state['spawn_robot_pos'][i])**2 for i in range(3)))
        if _d > 0.30:
            _teleport = True; _tev = {{"delta_m": round(_d, 2)}}
_ve("robot_teleport_at_play", _teleport, _tev)

# 22. robot_falls_over — robot base z drop > 0.10m
_falls = False; _fev = None
if state['robot_base_z'] and state['spawn_robot_pos']:
    _z_end = state['robot_base_z'][-1][1]
    _z_start = state['spawn_robot_pos'][2]
    if _z_start - _z_end > 0.10:
        _falls = True; _fev = {{"z_drop": round(_z_start - _z_end, 2)}}
_ve("robot_falls_over", _falls, _fev)

# 23. cube_lands_on_other_cube — final support = another manipulable prim
# Iterate all CUBE_PATHS; check against MOVABLE_PATHS (auto-discovered manipulables)
# to catch cubes that aren't in template's cube_paths list (e.g. CP-09 Cube_2)
_landed_on_cube = []
_other_manipulables = set(MOVABLE_PATHS) - set(CUBE_PATHS)
for cp in CUBE_PATHS:
    _sup = cube_supports.get(cp, {{}}).get('support')
    if not _sup: continue
    # Check against other CUBE_PATHS first
    matched = False
    for other in list(CUBE_PATHS) + list(_other_manipulables):
        if other == cp: continue
        if _sup == other or _sup.startswith(other + "/"):
            _landed_on_cube.append({{"cube": cp, "lands_on": _sup}})
            matched = True; break
_ve("cube_lands_on_other_cube", bool(_landed_on_cube), {{"events": _landed_on_cube}} if _landed_on_cube else None)

# 24. cubes_roll_off_belt — cube z dropped > 0.10m from spawn, ended on /World/Ground,
# AND cube never lifted above spawn+0.10m (proxy for "never gripped" since friction-grip
# doesn't create FixedJoint events).
_rolled_off = []
for cp in CUBE_PATHS:
    _sp = state['spawn_pos'].get(cp)
    _fp = cube_supports.get(cp, {{}}).get('final_pos')
    _sup = cube_supports.get(cp, {{}}).get('support') or ""
    if not (_sp and _fp): continue
    if _sp[2] - _fp[2] <= 0.10 or "ground" not in _sup.lower(): continue
    # Check if cube was ever lifted (max z over run > spawn z + 0.05 = picked up)
    _traj_z = [t['cubes'].get(cp, [0,0,0])[2] if t['cubes'].get(cp) else None for t in state['trajectory']]
    _traj_z = [z for z in _traj_z if z is not None]
    _max_z = max(_traj_z) if _traj_z else _sp[2]
    if _max_z < _sp[2] + 0.05:  # never lifted = roll off
        _rolled_off.append({{"cube": cp, "z_drop": round(_sp[2]-_fp[2], 3), "max_z": round(_max_z, 3)}})
_ve("cubes_roll_off_belt", bool(_rolled_off), {{"events": _rolled_off}} if _rolled_off else None)

# ---------------- ENGINE-DATA DETEKTORER (Anton R2 paradigm: "sensorer på motorn") ----------------
# Dessa läser source-level controller/physics-state, inte outcome-symptom.
# Tröskelvärden är konservativa v1 — tuna mot empirisk data efter första sweep.

# 29. curobo_target_unreached — cuRobo planning succeeded but final pose was off-target
# Root cause for many symptoms: "kub off-target", "trycker ner kuben", "telepatisk vid sidan"
_pos_err = _ctrl_state.get('ctrl:curobo_pos_err_last')
_ori_err = _ctrl_state.get('ctrl:curobo_ori_err_last')
_mot_time = _ctrl_state.get('ctrl:curobo_motion_time_last')
_unreached = False; _unreached_evid = None
try:
    if _pos_err is not None and float(_pos_err) > 0.03:
        _unreached = True
        _unreached_evid = {{"pos_err_m": round(float(_pos_err), 4),
                            "ori_err_rad": round(float(_ori_err or 0), 3),
                            "motion_time_s": round(float(_mot_time or 0), 2)}}
    elif _ori_err is not None and float(_ori_err) > 0.10:
        _unreached = True
        _unreached_evid = {{"pos_err_m": round(float(_pos_err or 0), 4),
                            "ori_err_rad": round(float(_ori_err), 3),
                            "motion_time_s": round(float(_mot_time or 0), 2)}}
except (TypeError, ValueError): pass
_ve("curobo_target_unreached", _unreached, _unreached_evid)

# 30. curobo_planner_high_fail_rate — cuRobo can't find paths (obstacle inflation, unreachable goals)
# Root cause for "ingen robotrörelse", "controller_stuck_idle"
_plan_calls = _ctrl_state.get('ctrl:plan_calls') or 0
_plan_fails = _ctrl_state.get('ctrl:plan_fails') or 0
_high_fail = False; _hf_evid = None
try:
    _pc = int(_plan_calls); _pf = int(_plan_fails)
    if _pc >= 5 and (_pf / _pc) > 0.30:
        _high_fail = True
        _hf_evid = {{"plan_calls": _pc, "plan_fails": _pf,
                     "fail_rate": round(_pf/_pc, 2),
                     "last_fail_goal": _ctrl_state.get('ctrl:last_fail_goal', '')}}
except (TypeError, ValueError): pass
_ve("curobo_planner_high_fail_rate", _high_fail, _hf_evid)

# 31. physx_step_time_degradation — sim-step-time spikar (physics instability, "scen laggar")
# Compares last 10 samples vs first 10. >3x = real degradation.
_step_times = [t for _, t in state['physx_step_times']]
_degraded = False; _deg_evid = None
if len(_step_times) >= 20:
    _first10 = sorted(_step_times[:10])
    _last10 = sorted(_step_times[-10:])
    _first_med = _first10[len(_first10)//2]
    _last_max = max(_last10)
    if _first_med > 0 and _last_max > 3 * _first_med:
        _degraded = True
        _deg_evid = {{"first10_median_s": round(_first_med, 4),
                      "last10_max_s": round(_last_max, 4),
                      "degradation_x": round(_last_max/_first_med, 1)}}
_ve("physx_step_time_degradation", _degraded, _deg_evid)

# ---------------- NIGHT-12H VE-DETEKTORER 2026-05-21 22:50 ----------------
# 6 nya detektorer designade av parallella agents baserat på Antons R2-tags.
# Fokus: programmatiska, generiska, datadrivna. INGA template-specifika regler.

# 32. gripper_freeze_above_cube (Anton CP-13/14/09/24/28 regression-pattern)
# EE närmar sig cube men STANNAR ovanför utan att stänga eller skapa FJ.
# Trigger: EE inom 15cm xy (eller 20cm 3D) av cube-pos i kontinuerlig duration > 2s,
# AND ingen FJ skapad under perioden, AND cubes_delivered = 0.
_freeze = False; _freeze_evid = None
_total_delivered = sum(1 for cp in CUBE_PATHS if cube_supports.get(cp, {{}}).get('under_target'))
if _total_delivered == 0 and len(state['trajectory']) >= 5 and CUBE_PATHS:
    _best_run = None
    for cp in CUBE_PATHS:
        _run_start_t = None; _samples = []; _run_fj_at_start = None
        for _i, _ts in enumerate(state['trajectory']):
            _ee = _ts.get('ee'); _cpos = (_ts.get('cubes') or {{}}).get(cp); _t = _ts.get('t')
            if _ee is None or _cpos is None:
                if _run_start_t is not None and len(_samples) >= 2:
                    _dur = _samples[-1][0] - _run_start_t
                    if _dur > 2.0 and (_best_run is None or _dur > (_best_run[2] - _best_run[1])):
                        _best_run = (cp, _run_start_t, _samples[-1][0], list(_samples))
                _run_start_t = None; _samples = []; continue
            _dxy = math.sqrt((_ee[0]-_cpos[0])**2 + (_ee[1]-_cpos[1])**2)
            _d3d = math.sqrt(sum((_ee[i]-_cpos[i])**2 for i in range(3)))
            _near = (_dxy < 0.15) or (_d3d < 0.20)
            _above = (_ee[2] - _cpos[2]) > -0.02
            if _near and _above:
                if _run_start_t is None:
                    _run_start_t = _t; _run_fj_at_start = _ts.get('fj_count', 0)
                if _ts.get('fj_count', 0) > _run_fj_at_start:
                    if len(_samples) >= 2:
                        _dur = _samples[-1][0] - _run_start_t
                        if _dur > 2.0 and (_best_run is None or _dur > (_best_run[2] - _best_run[1])):
                            _best_run = (cp, _run_start_t, _samples[-1][0], list(_samples))
                    _run_start_t = None; _samples = []; continue
                _samples.append((_t, _ee, _cpos))
            else:
                if _run_start_t is not None and len(_samples) >= 2:
                    _dur = _samples[-1][0] - _run_start_t
                    if _dur > 2.0 and (_best_run is None or _dur > (_best_run[2] - _best_run[1])):
                        _best_run = (cp, _run_start_t, _samples[-1][0], list(_samples))
                _run_start_t = None; _samples = []
        if _run_start_t is not None and len(_samples) >= 2:
            _dur = _samples[-1][0] - _run_start_t
            if _dur > 2.0 and (_best_run is None or _dur > (_best_run[2] - _best_run[1])):
                _best_run = (cp, _run_start_t, _samples[-1][0], list(_samples))
    if _best_run is not None:
        _cp_frozen, _t_s, _t_e, _smps = _best_run
        _ee_xy_avg = [sum(s[1][i] for s in _smps)/len(_smps) for i in range(2)]
        _cube_xy_avg = [sum(s[2][i] for s in _smps)/len(_smps) for i in range(2)]
        _z_above_avg = sum(s[1][2] - s[2][2] for s in _smps) / len(_smps)
        _freeze = True
        _freeze_evid = {{
            "cube_path": _cp_frozen, "freeze_duration_s": round(_t_e - _t_s, 2),
            "ee_avg_xy": [round(_ee_xy_avg[0], 3), round(_ee_xy_avg[1], 3)],
            "cube_avg_xy": [round(_cube_xy_avg[0], 3), round(_cube_xy_avg[1], 3)],
            "ee_z_above_cube_avg": round(_z_above_avg, 3), "samples_in_freeze": len(_smps),
        }}
_ve("gripper_freeze_above_cube", _freeze, _freeze_evid)

# 33. cube_passes_sensor_zone_untriggered (Anton CP-29 observation)
# Cube traverses >0.3m in X + drops >0.10m + never gripped by robot.
_passed_untriggered = []
try:
    _final_plan_calls = int(_ctrl_state.get('ctrl:plan_calls') or 0)
    for cp in CUBE_PATHS:
        _series = [(t['t'], t['cubes'].get(cp)) for t in state['trajectory']
                   if t.get('cubes', {{}}).get(cp) is not None]
        if len(_series) < 4: continue
        _t0, _p0 = _series[0]; _x0 = _p0[0]; _z0 = _p0[2]
        _t_end_idx = None; _x_max_drift = 0.0; _z_min = _z0
        for _i, (_t, _p) in enumerate(_series):
            _dx = abs(_p[0] - _x0)
            if _dx > _x_max_drift: _x_max_drift = _dx
            if _p[2] < _z_min: _z_min = _p[2]
            if _dx > 0.3 and _t_end_idx is None: _t_end_idx = _i
        if _t_end_idx is None: continue
        _z_drop = _z0 - _z_min
        if _z_drop <= 0.10: continue
        _t_start = _series[0][0]; _t_end = _series[_t_end_idx][0]
        _gripped = any(e.get('cube') == cp for e in state['fj_events'])
        if _gripped: continue
        # max_speed_during: peak cube velocity (m/s) — use this for ACTUAL speed.
        # Naive x_traversed_m/(t_end-t_start) gives 10-20 m/s ARTIFACT because
        # t_end-t_start is observation-window, not traversing time. Real speed
        # from PhysX velocity-sample stored in state['cube_max_speed'].
        _max_speed_during = float(state['cube_max_speed'].get(cp, 0.0))
        _passed_untriggered.append({{
            "cube": cp, "x_traversed_m": round(_x_max_drift, 3),
            "z_drop_m": round(_z_drop, 3),
            "t_start": round(_t_start, 2), "t_end": round(_t_end, 2),
            "max_speed_during_m_s": round(_max_speed_during, 2),
            "plan_calls_during": _final_plan_calls, "gripped_ever": _gripped,
        }})
except Exception: pass
_ve("cube_passes_sensor_zone_untriggered", bool(_passed_untriggered),
    {{"events": _passed_untriggered}} if _passed_untriggered else None)

# 34. missing_gripper_mesh (Anton CP-69/70 — "platta i änden av arm")
# Per family probe gripper-prims, check bbox empty or all extents <1mm (truly absent mesh).
_missing_grip = []; _gripper_family = None; _gripper_probes = []
for _r in ARTICULATION_ROOTS:
    _rn = _r.lower()
    if 'franka' in _rn or 'panda' in _rn:
        _gripper_family = 'franka'
        _gripper_probes = [(_r, 'panda_hand'), (_r, 'panda_leftfinger'), (_r, 'panda_rightfinger')]
        break
    if 'ur10' in _rn or 'ur5' in _rn:
        _gripper_family = 'ur10e' if 'ur10e' in _rn else 'ur10'
        _gripper_probes = [(_r, 'ee_link'), (_r, 'tool0'), (_r, 'wrist_3_link')]
        break
    if 'cobotta' in _rn:
        _gripper_family = 'cobotta_pro_900'
        _cobotta_subs = []
        try:
            for _c in stage.Traverse():
                _cp_p = str(_c.GetPath())
                if not _cp_p.startswith(_r + "/"): continue
                _cn = _c.GetName().lower()
                if any(k in _cn for k in ('gripper', 'hand', 'finger', 'tool')):
                    _cobotta_subs.append(_cp_p)
                    if len(_cobotta_subs) >= 6: break
        except: pass
        _gripper_probes = [(None, _cp_p) for _cp_p in _cobotta_subs]
        break
# 2026-05-22 (rev. 2) — root cause: previous threshold 0.0001 m³ (= 100 cm³) was
# too coarse. Live Kit verification shows panda_leftfinger geometry IS rendered
# correctly via instance proxies; the AABB volume is genuinely small (~30 mm³)
# because physical finger extent is 25×20×50 mm (= 25 cm³ = 2.5e-5 m³, below
# threshold). Verified with all 4 purpose configurations — `default/render/proxy/guide`
# all give same 33mm³ on Franka, confirming the asset is fine. UR10 ee_link gives
# vol=0.0 (true positive — no visual on bare end-effector link). Fix: trigger ONLY
# when bbox is empty OR all three axis-extents are < 1 mm (effectively zero-extent
# placeholder prim). Genuinely small but rendered geometry (Panda fingers, gripper
# tips) no longer trips false-positive.
_MIN_EXTENT_M = 0.001  # 1 mm
if _gripper_probes:
    _bbc_mg = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                     UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide])
    for _root, _sub in _gripper_probes:
        _gp = _sub if _root is None else f"{{_root}}/{{_sub}}"
        _pr = stage.GetPrimAtPath(Sdf.Path(_gp))
        if not (_pr and _pr.IsValid()): continue
        try:
            _bb = _bbc_mg.ComputeWorldBound(_pr).ComputeAlignedRange()
            if _bb.IsEmpty():
                _missing_grip.append({{"path": _gp, "bbox_volume_m3": 0.0, "reason": "empty"}}); continue
            _mn, _mx = _bb.GetMin(), _bb.GetMax()
            _ext = [float(_mx[0]-_mn[0]), float(_mx[1]-_mn[1]), float(_mx[2]-_mn[2])]
            _vol = float(_ext[0] * _ext[1] * _ext[2])
            # Trigger only if ALL three extents are essentially zero — true missing mesh.
            # A genuinely small but present mesh has at least one axis > 1mm.
            if all(_e < _MIN_EXTENT_M for _e in _ext):
                _missing_grip.append({{"path": _gp, "bbox_volume_m3": round(_vol, 9),
                                        "extent_m": [round(_e, 6) for _e in _ext],
                                        "reason": "zero_extent"}})
        except Exception:
            _missing_grip.append({{"path": _gp, "bbox_volume_m3": None, "reason": "bbox_exc"}})
_ve("missing_gripper_mesh", bool(_missing_grip),
    {{"robot_family": _gripper_family, "missing_or_tiny_prims": _missing_grip}} if _missing_grip else None)

# 35. blocker_on_conveyor_path (Anton CP-05 — "blocker stoppar cube på conveyor")
_blockers_evid = []
if CONVEYOR_BBOX:
    _bx_min = CONVEYOR_BBOX['min']; _bx_max = CONVEYOR_BBOX['max']
    _belt_top_z = _bx_max[2]
    _belt_y_mid = 0.5 * (_bx_min[1] + _bx_max[1])
    _belt_y_half = 0.5 * (_bx_max[1] - _bx_min[1])
    _cube_set_b = set(CUBE_PATHS)
    _conveyor_paths_b = set()
    for _prim in stage.Traverse():
        _nm = _prim.GetName().lower()
        if 'conveyor' in _nm or 'belt' in _nm:
            _conveyor_paths_b.add(str(_prim.GetPath()))
    _blocker_candidates = []
    try:
        for _prim in stage.Traverse():
            _pth_b = str(_prim.GetPath())
            if _pth_b in _cube_set_b: continue
            if _is_under_robot(_pth_b): continue
            if TARGET_PATH and (_pth_b == TARGET_PATH or _pth_b.startswith(TARGET_PATH + "/")): continue
            if any(_pth_b == cv or _pth_b.startswith(cv + "/") for cv in _conveyor_paths_b): continue
            _tn_b = str(_prim.GetTypeName())
            if _tn_b in ('', 'Scope', 'Xform'): continue
            _bb_b = _world_bbox(_pth_b)
            if not _bb_b: continue
            _cx = 0.5 * (_bb_b['min'][0] + _bb_b['max'][0])
            _cy = 0.5 * (_bb_b['min'][1] + _bb_b['max'][1])
            _cz = 0.5 * (_bb_b['min'][2] + _bb_b['max'][2])
            if (_bb_b['max'][0]-_bb_b['min'][0]) < 1e-4 and (_bb_b['max'][1]-_bb_b['min'][1]) < 1e-4: continue
            _on_belt_xy = (_bx_min[0] <= _cx <= _bx_max[0]) and (_bx_min[1] <= _cy <= _bx_max[1])
            _near_belt_top = abs(_cz - _belt_top_z) < 0.05
            if _on_belt_xy and _near_belt_top:
                _blocker_candidates.append({{"path": _pth_b, "xy": [round(_cx,3), round(_cy,3)], "z": round(_cz,3)}})
    except: pass
    if _blocker_candidates:
        _traj_b = state.get('trajectory', [])
        for _bc in _blocker_candidates:
            _bxy_x, _bxy_y = _bc['xy'][0], _bc['xy'][1]
            for cp in CUBE_PATHS:
                _samples_b = []
                for _snap in _traj_b:
                    _pos_b = _snap.get('cubes', {{}}).get(cp)
                    if _pos_b is not None: _samples_b.append((_snap['t'], _pos_b))
                if len(_samples_b) < 3: continue
                if cube_supports.get(cp, {{}}).get('under_target'): continue
                _stuck_at = None
                for _i in range(len(_samples_b)):
                    _t_i, _p_i = _samples_b[_i]
                    if _p_i[0] >= _bxy_x: continue
                    if abs(_p_i[1] - _bxy_y) > _belt_y_half + 0.05: continue
                    if abs(_p_i[2] - _belt_top_z) > 0.10: continue
                    # 2026-05-22 fix: tighten — cube must be CLOSE to blocker.
                    # CP-05 flagged LandingZone 23cm from stuck cube as false-positive.
                    _dist_xy_b = math.sqrt((_p_i[0]-_bxy_x)**2 + (_p_i[1]-_bxy_y)**2)
                    if _dist_xy_b > 0.15: continue
                    for _j in range(_i+1, len(_samples_b)):
                        _t_j, _p_j = _samples_b[_j]
                        if _t_j - _t_i < 0.9: continue
                        if _t_j - _t_i > 1.5: break
                        _dp = math.sqrt((_p_j[0]-_p_i[0])**2 + (_p_j[1]-_p_i[1])**2 + (_p_j[2]-_p_i[2])**2)
                        if _dp < 0.02:
                            _passed = any(_s[1][0] >= _bxy_x for _s in _samples_b[_j:])
                            if not _passed:
                                _stuck_at = [round(_p_i[0],3), round(_p_i[1],3), round(_p_i[2],3)]
                                break
                    if _stuck_at: break
                if _stuck_at:
                    _blockers_evid.append({{
                        "blocker_prim_path": _bc['path'], "blocker_xy": _bc['xy'],
                        "cube_stuck_path": cp, "cube_stuck_at_xy": _stuck_at[:2],
                    }})
                    break
_ve("blocker_on_conveyor_path", bool(_blockers_evid),
    {{"events": _blockers_evid}} if _blockers_evid else None)

# 36. side_grasp_telepathy (Anton CP-24 — "telepati från sidan")
# FJ skapad med EE-orientation som inte är top-down. Existing telepathic_contact
# fångar distance-baserad telepati; detta är orientation-baserad.
_side_grasp = []
for _e in state['fj_events']:
    _b0_list = _e.get('body0') or []
    if not _b0_list: continue
    _ee_path = _b0_list[0]
    if not _ee_path: continue
    try:
        _ee_pr = stage.GetPrimAtPath(Sdf.Path(_ee_path))
        if not (_ee_pr and _ee_pr.IsValid()): continue
        _ee_xf = UsdGeom.Xformable(_ee_pr).ComputeLocalToWorldTransform(0)
        _rot_m = _ee_xf.ExtractRotationMatrix()
        _zx = float(_rot_m[2][0]); _zy = float(_rot_m[2][1]); _zz = float(_rot_m[2][2])
        _z_dot_down = -_zz
        if _z_dot_down < 0.3:
            _quat = _ee_xf.ExtractRotationQuat()
            _qw = float(_quat.real)
            _qi = _quat.imaginary
            _qx = float(_qi[0]); _qy = float(_qi[1]); _qz = float(_qi[2])
            _side_grasp.append({{
                "fj_path": _e.get('fj_path'), "cube": _e.get('cube'),
                "ee_z_dot_down": round(_z_dot_down, 3),
                "ee_quat": [round(_qw, 3), round(_qx, 3), round(_qy, 3), round(_qz, 3)],
                "t": _e.get('t'),
            }})
    except Exception: pass
_ve("side_grasp_telepathy", bool(_side_grasp), {{"events": _side_grasp}} if _side_grasp else None)

# 37. unrealistic_grip (Anton 2026-05-22: "inte task success om den fuskar")
# FJ skapad mellan EE och cube UTAN finger-cube fysisk kontakt i ±1s-fönster.
# Telepati-detektor baserad på PhysX contact-events (inte EE↔cube-avstånd).
# Använder agent-1's prim_a/prim_b-fix på contact_events. Skippar surface-
# gripper templates där design är contact-less (UR10 raycast→FJ-workaround).
_unrealistic_fjs = []
_CONTACT_WIN_S = 1.0
_cube_set_ug = set(CUBE_PATHS)
def _is_finger_prim(p):
    if not p: return False
    pl = str(p).lower()
    return ('finger' in pl) or ('fingertip' in pl)
def _is_cube_prim(p, cube_set):
    if not p: return False
    return p in cube_set or any(p == cp or p.startswith(cp + "/") or cp in p for cp in cube_set)
def _is_surface_gripper_ee(ee_path):
    if not ee_path: return False
    el = str(ee_path).lower()
    return ('suction' in el) or ('vacuum' in el) or ('surface_gripper' in el)
for _e in state['fj_events']:
    _cube_p = _e.get('cube')
    if not _cube_p: continue
    _t_fj = _e.get('t')
    if _t_fj is None: continue
    _b0 = _e.get('body0') or []
    if _b0 and _is_surface_gripper_ee(_b0[0]): continue
    _t_lo = _t_fj - _CONTACT_WIN_S
    _t_hi = _t_fj + _CONTACT_WIN_S
    _contacts_in_window = 0
    for _c in state.get('contact_events', []):
        _ct = _c.get('t')
        if _ct is None or _ct < _t_lo or _ct > _t_hi: continue
        _pa = _c.get('prim_a') or _c.get('a')
        _pb = _c.get('prim_b') or _c.get('b')
        _hit = (
            (_is_finger_prim(_pa) and _is_cube_prim(_pb, _cube_set_ug)) or
            (_is_finger_prim(_pb) and _is_cube_prim(_pa, _cube_set_ug))
        )
        if _hit: _contacts_in_window += 1
    if _contacts_in_window == 0:
        _unrealistic_fjs.append({{
            "fj_path": _e.get('fj_path'),
            "cube": _cube_p,
            "t": _t_fj,
            "contacts_in_window": 0,
        }})
_ve("unrealistic_grip", len(_unrealistic_fjs) > 0,
    {{"events": _unrealistic_fjs}} if _unrealistic_fjs else None)

# 38. missing_scene_element (NEW 2026-05-22)
# Programmatic CP-05-style detector: for each scene element promised by the template's
# `code_template` (via {{role.path}} placeholder-substitution), check that the prim
# actually exists in the live stage after build+settle. If the concretized `code` block
# silently dropped a builder-call (CP-05 FlipWall case), the prim won't exist at runtime.
#
# Inherently filters Pass-2 false positives (const-assignment, f-string expansion,
# builder-internal creation) because at runtime the prim either exists or doesn't,
# regardless of how the code happens to spell the path-string. Detector is inactive
# (always-False) if EXPECTED_SCENE_ELEMENTS is empty (no template-intent data passed).
_missing_intent = []
for _el in EXPECTED_SCENE_ELEMENTS:
    _ep = _el.get("expected_path")
    if not _ep: continue
    try:
        _pr = stage.GetPrimAtPath(Sdf.Path(_ep))
        if not (_pr and _pr.IsValid()):
            _missing_intent.append({{
                "role": _el.get("role"),
                "expected_path": _ep,
                "builder_hint": _el.get("builder_hint"),
                "source": _el.get("source", "code_template_promise"),
            }})
    except Exception as _mie_exc:
        _missing_intent.append({{
            "role": _el.get("role"),
            "expected_path": _ep,
            "builder_hint": _el.get("builder_hint"),
            "source": _el.get("source", "code_template_promise"),
            "error": str(_mie_exc)[:120],
        }})
_ve("missing_scene_element", bool(_missing_intent),
    {{"events": _missing_intent}} if _missing_intent else None)

# Narrative — concatenated Swedish phrases
_phrase_map = {{
    "telepathic_contact": "telepatisk kontakt, gripper aldrig i kontakt",
    "never_picked": "kub åker av bandet, ingen pickup",
    "picked_then_dropped": "lyfter kub men släpper utanför target",
    "delivered_then_dislodged": "kub placeras i target men välts vid återgång",
    "cube_shifted_at_placement": "YEET vid placement, arm-snabbrörelse shiftar kub",
    "arm_speed_yeet": "snabb arm-rörelse vid placement/återgång",
    "bin_wall_collision": "arm trycker ner i bin",
    "blowup_at_release": "kub flyger vid släpp",
    "robot_through_floor": "robot faller genom golvet",
    "mobile_robot_under_floor": "robot under golvet",
    "mobile_robot_vibrating": "robot vibrerar mot bordet",
    "robot_vibration": "robot vibrerar utan att göra framsteg",
    "gripper_freeze_above_cube": "gripper närmar sig kub men stannar utan grepp",
    "cube_passes_sensor_zone_untriggered": "kub passerar pickup-zon utan att robot reagerar",
    "missing_gripper_mesh": "robot saknar synlig gripper-mesh",
    "blocker_on_conveyor_path": "blocker-objekt på conveyor stoppar kub",
    "side_grasp_telepathy": "telepatiskt grepp från sidan (ej top-down)",
    "unrealistic_grip": "orealistisk grip (FJ utan fysisk finger-cube-kontakt)",
    "mobile_robot_not_moving": "robot rör sig inte",
    "cube_under_table": "kub spawnar under bordet",
    "cube_floats_no_gravity": "kub svävar utan gravity",
    "non_cube_object_floats": "objekt sväver",
    "routing_failure": "alla kuber i samma destination",
    "controller_stuck_idle": "controller fastnar i wait_sensor",
    "infinite_grip_oscillation": "gripper oscillerar",
    "cube_spawn_off_belt": "kub spawnar utanför conveyor",
    "physics_errors_at_play": "physics errors vid play",
    "robot_teleport_at_play": "robot teleporterar vid play",
    "robot_falls_over": "robot välter",
    "cube_lands_on_other_cube": "kub hamnar på annan kub",
    "cubes_roll_off_belt": "kuber rullar av bandet till golvet",
    "ur10_horizontal_start": "UR10 horisontell vid start, åker upp vid play",
    "scene_missing_required_asset": "scen saknar required asset",
    "wrong_object_type_present": "objekt har fel typ (ej kub-form)",
    "cube_disappears_or_respawns": "kub försvinner under run",
    "non_cube_object_floats": "icke-kub objekt sväver utan gravity",
    "mobile_robot_under_floor_at_load": "mobil robot under golv vid start, åker upp vid play",
    "gripper_cannot_release": "gripper kan inte släppa kub",
    "routing_failure": "alla kuber i samma destination, ingen sortering",
    "arm_collides_with_bin_walls": "arm kolliderar med bin-väggar",
    "cube_tilts_over": "kub flakar/tiltar",
    "partial_delivery": "endast vissa kuber levererade",
    "cube_bounces_off_target": "kub studsar av target till golvet",
    "robot_explodes": "robot exploderar (PhysX instabilitet, EE z<-10m)",
    "missing_scene_element": "scen saknar element som template-intent kräver",
}}
_detected_names = [n for n, p in ve_patterns.items() if p.get("detected")]
if _detected_names:
    _narrative = ". ".join(_phrase_map.get(n, n) for n in _detected_names)
    _conf = "high"
elif honest_pass:
    _narrative = "fungerar"; _conf = "high"
else:
    _narrative = "okänd fail (gates fail men ingen pattern triggad — eskalera till Anton)"
    _conf = "low"

virtual_eyes = {{
    "patterns": ve_patterns,
    "narrative": _narrative,
    "narrative_confidence": _conf,
    "ee_max_speed_in_placement": round(state.get('ee_max_speed_in_placement', 0), 3),
    "cube_xy_drift_post_target": {{k: round(v, 3) for k, v in state['cube_xy_drift_post_target'].items()}},
}}

out = {{
    'primary_cube': primary_cube,
    'cube_supports': cube_supports,
    'cube_max_speed': state['cube_max_speed'],
    'cube_in_target_ever': state['cube_in_target_ever'],
    'spawn_pos': state['spawn_pos'],
    'fj_events': state['fj_events'],
    'telepathic_fjs': telepathic_fjs,
    'ee_min_z': ee_min_z,
    'ee_underground': ee_underground,
    'trajectory': state['trajectory'],
    'gates': {{
        'support_under_target': primary_support_ok,
        'in_target_ever': primary_in_target_ever,
        'no_telepathic_fj': not telepathic_fjs,
        'no_blowup': max_speed_overall < 2.0,
        'ee_never_underground': not ee_underground,
    }},
    'honest_pass': honest_pass,
    'virtual_eyes': virtual_eyes,
    'engine_data': engine_data,
}}

print('OBSERVE_BEGIN')
print(json.dumps(out, indent=2, default=str))
print('OBSERVE_END')
"""

# Detector #38 input — extract scene-element promises from template's code_template.
# Each promise = {"role", "expected_path", "builder_hint", "source"} for a {{role.path}}
# placeholder that appears on a line containing a builder call (create_*/robot_wizard/
# add_*/setup_*/apply_*). Resolved via role_defaults[role].path.
# Lists of dicts under role_defaults (e.g. workpieces: [...]) and indexed placeholders
# ({{workpieces[0].path}}) are also supported.
_BUILDER_RE = re.compile(r"\b(create_[a-zA-Z_]+|robot_wizard|add_[a-zA-Z_]+|setup_[a-zA-Z_]+|apply_api_schema)\s*\(")
# Match {{role.path}} or {{role[idx].path}} placeholders.
_PATH_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][\w]*)(\[(\d+)\])?\.path\s*\}\}")

def _extract_expected_scene_elements(tpl):
    """Return list of dicts for detector #38. Empty if data unavailable."""
    out = []
    seen = set()  # dedupe by (role_label, expected_path)
    code_template = tpl.get("code_template") or ""
    role_defaults = tpl.get("role_defaults") or {}
    if not code_template or not role_defaults:
        return out
    for line in code_template.splitlines():
        # Skip comment-only lines (no builder substitution there).
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        builder_m = _BUILDER_RE.search(line)
        if not builder_m:
            continue
        builder_hint = builder_m.group(1)
        for m in _PATH_PLACEHOLDER_RE.finditer(line):
            role_key = m.group(1)
            idx_str = m.group(3)
            rd_entry = role_defaults.get(role_key)
            if rd_entry is None:
                continue
            # Resolve to a concrete path (role may be dict or list[dict]).
            if isinstance(rd_entry, list):
                if idx_str is None:
                    continue  # ambiguous — skip rather than guess
                try:
                    item = rd_entry[int(idx_str)]
                except (IndexError, ValueError):
                    continue
                if not isinstance(item, dict):
                    continue
                expected_path = item.get("path")
                role_label = f"{role_key}[{idx_str}]"
            elif isinstance(rd_entry, dict):
                expected_path = rd_entry.get("path")
                role_label = role_key
            else:
                continue
            if not expected_path or not isinstance(expected_path, str):
                continue
            key = (role_label, expected_path)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "role": role_label,
                "expected_path": expected_path,
                "builder_hint": builder_hint,
                "source": "code_template_promise",
            })
    return out

async def main():
    if len(sys.argv) < 2:
        print("usage: scene_observer.py <CP-NAME> [<CP-NAME>...]"); return
    targets = sys.argv[1:]
    if not OUT.exists(): OUT.write_text("")
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    if not kit_alive():
        if not await launch_kit(): return

    for i, name in enumerate(targets, 1):
        if not kit_alive():
            if not await restart_kit(): break
        tpl_path = REPO/f"workspace/templates/{name}.json"
        if not tpl_path.exists():
            print(f"[{i}/{len(targets)}] {name}: NOT_FOUND"); continue
        tpl = json.loads(tpl_path.read_text())
        sa = tpl.get("simulate_args") or {}
        rd = tpl.get("role_defaults") or {}
        pr = rd.get("primary_robot") or {}
        robot_path = pr.get("path", "/World/Robot")
        rc = pr.get("class") or ""
        # 2026-05-22 audit-fix #4: handler:s cuRobo använder _TOOL_FRAME="tool0" för UR10
        # (pick_place.py:4139), inte ee_link. Observer:s "ee_link" gav 5-10cm distance-diff
        # → unrealistic_grip false-positive risk på UR10-batch.
        ee_link = "panda_hand" if "franka" in rc else "tool0"
        cube_paths = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
        target_path = sa.get("target_path", "")
        duration_s = float(sa.get("duration_s", 60))
        # Find table top z (approx — assume /World/Table at z=0.375 scale_z=0.375 → top=0.75)
        table_top_z = 0.75
        # Detector #38 input — derived from template's code_template + role_defaults.
        expected_scene_elements = _extract_expected_scene_elements(tpl)

        await kit_tools.exec_sync("import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
        print(f"[{i}/{len(targets)}] {name}: building...", flush=True)
        try:
            b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
            if not b.get("instantiated"):
                print(f"  BUILD_FAIL: {b.get('errors')[:2]}"); continue
        except Exception as e:
            print(f"  BUILD_EXC: {e}"); continue
        try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
        except: pass

        code = OBSERVE_CODE.format(robot_path=robot_path, ee_link=ee_link,
                                    cube_paths=cube_paths, target_path=target_path,
                                    duration_s=duration_s, table_top_z=table_top_z,
                                    expected_scene_elements=expected_scene_elements)
        try:
            r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=duration_s + 180), timeout=duration_s + 200)
            out = (r.get("output") or "").strip()
            b_i = out.find("OBSERVE_BEGIN")
            e_i = out.find("OBSERVE_END")
            if b_i < 0 or e_i < 0:
                print(f"  PARSE_FAIL: {out[:300]}"); continue
            data = json.loads(out[b_i + len("OBSERVE_BEGIN"):e_i].strip())
            data["template"] = name
            with OUT.open("a") as f: f.write(json.dumps(data, default=str) + "\n")
            gates = data.get("gates", {})
            verdict = "HONEST_PASS" if data.get("honest_pass") else "FAIL"
            print(f"  {verdict}", flush=True)
            for k,v in gates.items(): print(f"    {k}: {v}")
            if data.get("telepathic_fjs"):
                print(f"    TELEPATHIC FJs: {len(data['telepathic_fjs'])}")
                for e in data["telepathic_fjs"][:3]:
                    print(f"      t={e['t']}s dist={e['distance']}m cube={e['cube']}")
        except Exception as e:
            print(f"  EXC: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
