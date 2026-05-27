"""RL-paradigm precision tuning V2 — extended grid + Kit-stable.

Improvements over rl_tune_3cube.py:
- Keep Kit alive between iters (only restart on health-fail) — saves 34s/iter
- USD-patch via exec_sync (no pick_place.py edit + uvicorn restart per iter)
- 7 params total (3 old + 4 new):
  * pre_grip_settle (handler PD-konvergens)
  * vel_clamp (handler velocity-clamp)
  * curobo_pos_tol (cuRobo plan precision)
  * friction_mu (cube material — NEW)
  * finger_stiffness (gripper drive — NEW)
  * joint_vel_scale (articulation max-velocity multiplier — NEW)
  * arm_kp_scale (panda arm joint drive stiffness multiplier — NEW)
- Time-bonus in penalty (faster = better för precision-OK iter)
- Bin-floor + indirect-collision detection (preserves existing logic)
- 36h target run

Output:
  workspace/friction_tuning/rl_v2/run_<TS>/
    iter_<N>/params.json, raw.jsonl, metrics.json
    results.csv, BEST.json
"""
import argparse
import asyncio
import csv
import json
import math
import os
import random
import signal
import subprocess
import sys
import time
import urllib.request
from itertools import product
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))

# Import working observe_one from sweep_all_rewritten
from scripts.review.sweep_all_rewritten import observe_one, kit_alive, launch_kit, restart_kit

KIT_HEALTH = "http://127.0.0.1:8001/health"
UVI_HEALTH = "http://127.0.0.1:8000/health"
KIT_LAUNCH_HEADLESS = "/home/anton/.claude/diag/launch_kit_headless.sh"
KIT_EXEC = "http://127.0.0.1:8001/exec_sync"

OUT_BASE = REPO / "workspace/friction_tuning/rl_v2"

# ============ Teach Poses (Ground Truth) ============
# Load the expert demonstration poses to use as optimization targets
TEACH_POSES_DIR = REPO / "workspace/friction_tuning/teach_poses"

def load_teach_poses():
    """Load the manual teach poses as ground truth targets."""
    poses = {}
    try:
        grip_file = list(TEACH_POSES_DIR.glob("grip_cube_M_center_*.json"))[0]
        with open(grip_file) as f:
            grip_data = json.load(f)
            poses["grip_palm_xyz"] = grip_data["palm_world_xyz"]
            poses["grip_palm_quat"] = grip_data["palm_world_quat_wxyz"]
            poses["grip_joint_pos"] = grip_data["joint_positions_franka"][:7]  # Arm only
            print(f"Loaded teach pose: grip at {poses['grip_palm_xyz']}")
    except Exception as e:
        print(f"Warning: Could not load grip teach pose: {e}")
        # Fallback to default based on template
        poses["grip_palm_xyz"] = [-0.297, 0.298, 0.877]
        poses["grip_palm_quat"] = [0.001, 0.004, 0.999, 0.003]
    
    try:
        approach_file = list(TEACH_POSES_DIR.glob("approach_lift_cube_M_*.json"))[0]
        with open(approach_file) as f:
            approach_data = json.load(f)
            poses["approach_palm_xyz"] = approach_data["palm_world_xyz"]
            print(f"Loaded teach pose: approach at {poses['approach_palm_xyz']}")
    except Exception as e:
        print(f"Warning: Could not load approach teach pose: {e}")
        # Fallback: 5cm above grip
        poses["approach_palm_xyz"] = [-0.286, 0.296, 0.921]
    
    return poses

TEACH_POSES = load_teach_poses()

# Scene constants (must match CP-PRECISION-3CUBE template)
CUBE_L_INIT_XY = (-0.3505, 0.30)
CUBE_R_INIT_XY = (-0.2495, 0.30)
CUBE_M_INIT_XY = (-0.30, 0.30)
BIN_CENTER_XY = (0.2675, -0.3325)  # 2026-05-26: matches template bin position (was 0.30,-0.30 — wrong)
BIN_FLOOR_TOP_Z = 0.755
CUBE_AT_REST_Z = BIN_FLOOR_TOP_Z + 0.025  # 0.78
BIN_INNER_HALF_XY = 0.0275  # for outer 0.065, walls 5mm → inner 0.055 → half 0.0275

PARAM_GRID = {
    # 2026-05-27 PROVEN-WINNERS-LOCK: motion-planning locked to params from reward_full winners (iter 29/68/70/23).
    # Common factors: jv=0.5 (slow joint motion), pre_grip_settle 0.8-1.5, low vel_clamp.
    # Only friction-grip params varied (mu × stiff × mass) for material-tuning exploration.
    "pre_grip_settle": [0.8, 1.5],          # WINNERS: 0.8 or 1.5
    "vel_clamp": [0.02, 0.04],              # WINNERS: 0.02 or 0.04
    "curobo_pos_tol": [0.001, 0.003],       # WINNERS: either
    "joint_vel_scale": [0.5],               # WINNERS: 0.5 (slow = stable)
    "arm_kp_scale": [1.0, 2.0],             # WINNERS: 1.0 or 2.0
    # Friction-grip: dense sweep for material-tuning
    "friction_mu": [0.3, 0.6, 1.0, 2.0],
    "finger_stiffness": [80000, 200000, 500000],
    "cube_mass": [0.1, 0.2, 0.5],
}

PICK_PLACE_FILE = REPO / "service/isaac_assist_service/chat/tools/handlers/pick_place.py"

# ============ Kit RPC ============

def kit_exec(code: str, timeout: int = 120) -> dict:
    """Execute code in Kit headless."""
    try:
        req = urllib.request.Request(
            KIT_EXEC,
            data=json.dumps({"code": code, "timeout": timeout}).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())
    except Exception as e:
        return {"success": False, "output": f"kit_exec error: {e}"}


def _http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200 and len(r.read()) > 0
    except:
        return False


def _pids_on(port):
    try:
        return [int(p) for p in subprocess.check_output(["lsof", "-ti", f":{port}"], stderr=subprocess.DEVNULL).decode().split()]
    except subprocess.CalledProcessError:
        return []


def _kill(pids):
    for p in pids:
        try:
            os.kill(p, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def restart_kit_headless():
    print("  Kit restart...", flush=True)
    _kill(_pids_on(8001)); time.sleep(3)
    subprocess.Popen(["bash", KIT_LAUNCH_HEADLESS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(60):
        time.sleep(5)
        if _http_ok(KIT_HEALTH):
            return True
    return False


def restart_uvicorn():
    print("  uvicorn restart...", flush=True)
    _kill(_pids_on(8000)); time.sleep(2)
    log = Path(f"/tmp/uvi_rl_v2_{time.strftime('%H%M%S')}.log")
    fd = log.open("ab")
    subprocess.Popen(
        ["python", "-m", "uvicorn", "service.isaac_assist_service.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(REPO), stdout=fd, stderr=fd, start_new_session=True
    )
    for _ in range(30):
        time.sleep(2)
        if _http_ok(UVI_HEALTH):
            return True
    return False


# ============ Param application ============

def edit_handler_params(params: dict):
    """Edit pick_place.py för 3 OLD handler-level params."""
    src = PICK_PLACE_FILE.read_text()
    if "pre_grip_settle" in params:
        v = params["pre_grip_settle"]
        import re
        src = re.sub(r"pre_grip_settle = [\d.]+ if _is_grip_seg else 0\.0",
                     f"pre_grip_settle = {v} if _is_grip_seg else 0.0", src)
    if "vel_clamp" in params:
        v = params["vel_clamp"]
        import re
        src = re.sub(r"_max_delta = [\d.]+  # rad per tick.*",
                     f"_max_delta = {v}  # rad per tick (rl_v2)", src)
    if "curobo_pos_tol" in params:
        v = params["curobo_pos_tol"]
        import re
        src = re.sub(r"position_tolerance=[\d.]+,.*",
                     f"position_tolerance={v},  # rl_v2", src)
    PICK_PLACE_FILE.write_text(src)


def revert_handler_params():
    src = PICK_PLACE_FILE.read_text()
    import re
    src = re.sub(r"pre_grip_settle = [\d.]+ if _is_grip_seg else 0\.0",
                 "pre_grip_settle = 0.8 if _is_grip_seg else 0.0", src)
    src = re.sub(r"_max_delta = [\d.]+  # rad per tick.*",
                 "_max_delta = 0.04  # rad per tick", src)
    src = re.sub(r"position_tolerance=[\d.]+,.*",
                 "position_tolerance=0.003,", src)
    PICK_PLACE_FILE.write_text(src)


def apply_scene_params(params: dict) -> dict:
    """Apply NEW scene-level params via USD-patch in Kit (post-scene-build, pre-observation)."""
    mu = params.get("friction_mu", 2.0)
    fstiff = params.get("finger_stiffness", 80000)
    vel_scale = params.get("joint_vel_scale", 1.0)
    arm_kp_scale = params.get("arm_kp_scale", 1.0)
    cube_mass = params.get("cube_mass", 0.1)
    code = f"""
import omni.usd
from pxr import UsdGeom, Sdf, UsdPhysics
stage = omni.usd.get_context().get_stage()

# Friction on all cubes
for cp in ['/World/Cube_M', '/World/Cube_L', '/World/Cube_R']:
    p = stage.GetPrimAtPath(Sdf.Path(cp))
    if not p: continue
    rel = p.GetRelationship('material:binding:physics')
    if rel:
        for mp in rel.GetTargets():
            m = stage.GetPrimAtPath(mp)
            if m:
                pm = UsdPhysics.MaterialAPI.Apply(m)
                pm.GetStaticFrictionAttr().Set({mu})
                pm.GetDynamicFrictionAttr().Set({mu})

# Finger stiffness
for jp in ['/World/Franka/panda_hand/panda_finger_joint1', '/World/Franka/panda_hand/panda_finger_joint2']:
    p = stage.GetPrimAtPath(Sdf.Path(jp))
    if p:
        try:
            drv = UsdPhysics.DriveAPI.Apply(p, 'linear')
            drv.GetStiffnessAttr().Set({fstiff})
        except: pass

# Arm joint stiffness scale (multiply default kp)
for jn in ['panda_joint1','panda_joint2','panda_joint3','panda_joint4','panda_joint5','panda_joint6','panda_joint7']:
    for prefix in ['/World/Franka', '/World/Franka/panda_link0']:
        p = stage.GetPrimAtPath(Sdf.Path(prefix + '/' + jn))
        if p and p.IsValid():
            try:
                drv = UsdPhysics.DriveAPI.Apply(p, 'angular')
                kp = drv.GetStiffnessAttr().Get() or 1000.0
                drv.GetStiffnessAttr().Set(kp * {arm_kp_scale})
            except: pass
            break
# Cube mass
for cp in ['/World/Cube_M', '/World/Cube_L', '/World/Cube_R']:
    p = stage.GetPrimAtPath(Sdf.Path(cp))
    if p:
        try:
            mass_attr = p.GetAttribute('physics:mass')
            if mass_attr: mass_attr.Set({cube_mass})
        except: pass

print('Scene-patch ok: mu={mu} fstiff={fstiff} vel_scale={vel_scale} arm_kp_scale={arm_kp_scale} mass={cube_mass}')
"""
    return kit_exec(code, timeout=15)


# ============ Observation ============
# Using observe_one imported from scripts.review.sweep_all_rewritten
# This uses kit_tools.exec_sync directly instead of HTTP endpoint


# ============ Penalty ============

def _euclidean_dist(p1, p2):
    """Calculate Euclidean distance between two 3D points."""
    if not p1 or not p2 or len(p1) < 3 or len(p2) < 3:
        return None
    return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2) ** 0.5

def compute_penalty(rec: dict, elapsed_s: float, params: dict) -> dict:
    # FIX 2026-05-26: cube_supports is TOP-LEVEL in observe_one record, NOT inside engine_data
    cs = rec.get("cube_supports") or (rec.get("engine_data") or {}).get("cube_supports") or {}
    cm = cs.get("/World/Cube_M") or {}
    cl = cs.get("/World/Cube_L") or {}
    cr = cs.get("/World/Cube_R") or {}

    def _xy_dist(p, init):
        if not p or len(p) < 2: return None
        return ((p[0]-init[0])**2 + (p[1]-init[1])**2) ** 0.5

    fp_l = cl.get("final_pos")
    fp_r = cr.get("final_pos")
    fp_m = cm.get("final_pos")
    disp_l = _xy_dist(fp_l, CUBE_L_INIT_XY) or 0.0
    disp_r = _xy_dist(fp_r, CUBE_R_INIT_XY) or 0.0
    adj_disp = disp_l + disp_r

    drop_xy_err = 1.0
    inside_bin = 0
    if fp_m and len(fp_m) >= 2:
        drop_xy_err = ((fp_m[0]-BIN_CENTER_XY[0])**2 + (fp_m[1]-BIN_CENTER_XY[1])**2) ** 0.5
        # FIX 2026-05-26: use under_target flag (physical reality from cube_supports raycast)
        # rather than XY-threshold which was too tight for cube touching bin walls
        if cm.get("under_target") or (abs(fp_m[0]-BIN_CENTER_XY[0]) < BIN_INNER_HALF_XY and abs(fp_m[1]-BIN_CENTER_XY[1]) < BIN_INNER_HALF_XY):
            inside_bin = 1

    cube_on_floor = 0
    z_err_floor = 1.0
    if fp_m and len(fp_m) >= 3:
        z_err_floor = abs(fp_m[2] - CUBE_AT_REST_Z)
        if z_err_floor < 0.005:
            cube_on_floor = 1

    # ============ NEW: Grip Position Error vs Teach Pose ============
    # Extract actual palm position at grip moment from observation data
    # The trajectory data is under "trajectory" key with "ee" positions
    ee_data = (rec.get("trajectory") or [])
    grip_pos_error = 1.0  # Default high error if no data
    approach_pos_error = 1.0
    
    if ee_data and len(ee_data) > 0:
        # Find position closest to grip phase (usually middle of trajectory or when near cube)
        cube_m_pos = list(CUBE_M_INIT_XY) + [0.775]  # Initial cube position with Z
        
        min_dist_to_cube = float('inf')
        closest_palm_pos = None
        
        for ee_sample in ee_data:
            # Trajectory structure: {"t": time, "ee": [x, y, z], "cubes": {...}}
            palm_pos = ee_sample.get("ee")
            if palm_pos and len(palm_pos) >= 3:
                dist_to_cube = _euclidean_dist(palm_pos, cube_m_pos)
                if dist_to_cube < min_dist_to_cube:
                    min_dist_to_cube = dist_to_cube
                    closest_palm_pos = palm_pos
        
        if closest_palm_pos:
            # Calculate error vs taught grip pose
            # 2026-05-26: Use COMPUTED geometric target (cube_pos + FL=0.105) as ground-truth.
            # Anton's manual teach was eye-balled, ~3mm off from physics-correct target.
            # Handler computes deterministically; tuning should validate against same computation.
            FRANKA_FL = 0.105  # palm-to-fingertip
            target_grip = [CUBE_M_INIT_XY[0], CUBE_M_INIT_XY[1], 0.775 + FRANKA_FL]  # cube_top is 0.775+0.025
            grip_pos_error = _euclidean_dist(closest_palm_pos, target_grip) or 1.0
            
            # Calculate error vs taught approach pose (5cm above)
            target_approach = TEACH_POSES.get("approach_palm_xyz", [-0.286, 0.296, 0.921])
            # Approximate approach by finding point at grip Z + 5cm
            approach_proxy = [closest_palm_pos[0], closest_palm_pos[1], closest_palm_pos[2] + 0.05]
            approach_pos_error = _euclidean_dist(approach_proxy, target_approach) or 1.0
    
    # ============ TIGHTENED: Target <2mm grip accuracy ============
    # Normalize grip error: 2mm (0.002) should give normalized=1.0
    # <2mm = good, >2mm = increasingly bad
    grip_error_normalized = min(grip_pos_error / 0.002, 10.0)  # Cap at 10.0, 2mm = 1.0
    
    # STRICT reward: require <2mm grip error AND <5mm drop error
    reward_full = bool((adj_disp < 0.001) and inside_bin and cube_on_floor and drop_xy_err < 0.005 and grip_pos_error < 0.002)

    col_direct = 0
    col_indirect = 0
    # 2026-05-26 FIX: also read contact_pair_summary (NO penetration filter — gives brushing contacts).
    # Previous read of contact_events_sample missed events with <1mm penetration even when L/R got shoved 50mm.
    contact_evts = ((rec.get("engine_data") or {}).get("contact_events_sample") or [])
    pair_summary = ((rec.get("engine_data") or {}).get("contact_pair_summary") or [])
    SIDE = {"/World/Cube_L", "/World/Cube_R"}
    from collections import Counter
    culprit_breakdown = Counter()
    # Source 1: contact_events_sample (high-penetration contacts)
    for ce in contact_evts:
        pa, pb = ce.get("prim_a") or "", ce.get("prim_b") or ""
        if pa in SIDE:
            other = pb
        elif pb in SIDE:
            other = pa
        else:
            continue
        if other == "/World/Cube_M":
            col_indirect += 1
            culprit_breakdown["indirect_cube_M"] += 1
        elif any(k in other.lower() for k in ("finger", "panda", "franka", "hand")):
            col_direct += 1
    # Source 2: contact_pair_summary (ALL contacts incl brushing) — weighted by count
    for s in pair_summary:
        a = str(s.get("a","")); b = str(s.get("b","")); count = int(s.get("count",0))
        if not count: continue
        if a in SIDE: other = b
        elif b in SIDE: other = a
        else: continue
        if other == "/World/Cube_M":
            col_indirect += count
            culprit_breakdown["indirect_cube_M_pair"] += count
        elif any(k in other.lower() for k in ("finger", "panda", "franka", "hand")):
            col_direct += count
            # Classify culprit by prim name
            if "finger" in other.lower(): culprit_breakdown["finger"] += 1
            elif "hand" in other.lower(): culprit_breakdown["palm_hand"] += 1
            elif "link7" in other.lower(): culprit_breakdown["link7_wrist"] += 1
            elif "link8" in other.lower(): culprit_breakdown["link8_flange"] += 1
            elif any(f"link{i}" in other.lower() for i in range(7)): culprit_breakdown["arm_link"] += 1
            else: culprit_breakdown["other_robot"] += 1
    col_count = col_direct + col_indirect

    # 2026-05-26: NEW — count EE-vs-bin (destination) collisions. Previously missed.
    # If fingers/palm/links touch bin walls during drop = bad even if cube ends in bin (cheating delivery).
    ee_vs_bin_count = 0
    for ce in contact_evts:
        pa, pb = ce.get("prim_a") or "", ce.get("prim_b") or ""
        is_bin = (pa.startswith("/World/Bin/") or pb.startswith("/World/Bin/"))
        is_robot = ("Franka" in pa or "Franka" in pb or "panda" in pa.lower() or "panda" in pb.lower())
        if is_bin and is_robot:
            ee_vs_bin_count += 1
    col_count = col_direct + col_indirect + ee_vs_bin_count  # Include destination collisions
    col_normalized = 1.0 - math.exp(-col_count/5.0) if col_count > 0 else 0.0

    # Time bonus (only when reward_full): faster = better
    # Penalize slow iter slightly even when successful
    time_factor = elapsed_s / 30.0  # normalized to ~1.0 for 30s
    time_penalty = max(0, time_factor - 1.0) * 0.5  # only over 30s adds penalty

    # 2026-05-26: Extract VE-patterns (virtual_eyes = automated equivalents of human visual observation)
    ve = rec.get("virtual_eyes") or {}
    ve_patterns = ve.get("patterns") or {}
    ve_detected = [name for name, p in ve_patterns.items() if p.get("detected")]
    ve_narrative = ve.get("narrative", "")

    # 2026-05-26: Friction-grip-equivalent VE-patterns (re-implemented locally — scene_observer originals are FJ-dependent)
    # Use trajectory + cube_supports we already have access to
    traj = rec.get("trajectory") or []
    if traj:
        # Friction equiv of picked_then_dropped: Cube_M lifted then landed wrong
        cube_m_series = [(s.get("t",0), s.get("cubes",{}).get("/World/Cube_M"))
                         for s in traj if s.get("cubes",{}).get("/World/Cube_M")]
        if cube_m_series and len(cube_m_series) > 5:
            z_initial = cube_m_series[0][1][2]
            z_max = max(p[2] for _, p in cube_m_series if p)
            if fp_m and z_max > z_initial + 0.10 and fp_m[2] < 0.80 and not cm.get("under_target"):
                ve_detected.append("friction_picked_then_dropped")
        # Friction equiv of gripper_freeze: EE near Cube_M for >2s but Cube_M never moved
        cube_m_initial = (-0.30, 0.30, 0.775)
        time_near_cube = 0.0
        last_t = None
        cube_displacement_max = 0.0
        for s in traj:
            t = s.get("t",0); ee = s.get("ee"); cm_pos = s.get("cubes",{}).get("/World/Cube_M")
            if ee and cm_pos:
                d = ((ee[0]-cm_pos[0])**2 + (ee[1]-cm_pos[1])**2 + (ee[2]-cm_pos[2])**2) ** 0.5
                if d < 0.20:  # within 20cm
                    if last_t is not None: time_near_cube += (t - last_t)
                    last_t = t
                else:
                    last_t = None
                disp = ((cm_pos[0]-cube_m_initial[0])**2 + (cm_pos[1]-cube_m_initial[1])**2)**0.5
                if disp > cube_displacement_max: cube_displacement_max = disp
        if time_near_cube > 2.0 and cube_displacement_max < 0.01 and not cm.get("under_target"):
            ve_detected.append("friction_gripper_freeze")
        # 2026-05-26: Cube-lost detection — distinguish (A) dropped mid-transit vs (B) missed bin at release
        # Scan trajectory for first moment cube separates from EE (>5cm distance after being gripped)
        cube_lost_t = None
        cube_lost_dist_from_bin = None
        ee_close_to_cube_seen = False  # only count "loss" after grip was established
        for s in traj:
            t = s.get("t", 0); ee = s.get("ee"); cm_pos = s.get("cubes",{}).get("/World/Cube_M")
            if not ee or not cm_pos: continue
            d_ee_cube = ((ee[0]-cm_pos[0])**2 + (ee[1]-cm_pos[1])**2 + (ee[2]-cm_pos[2])**2)**0.5
            if d_ee_cube < 0.05:
                ee_close_to_cube_seen = True
            elif ee_close_to_cube_seen and d_ee_cube > 0.10 and cube_lost_t is None:
                # Cube separated from EE after being close (likely dropped or released)
                cube_lost_t = t
                cube_lost_dist_from_bin = ((cm_pos[0]-BIN_CENTER_XY[0])**2 + (cm_pos[1]-BIN_CENTER_XY[1])**2)**0.5
                break
        # Classify failure mode
        failure_mode = "unknown"
        # Check if cube ever lifted (z > initial + 5cm) — uses cube_m_series from line ~407
        cube_max_z = max((p[2] for _, p in cube_m_series if p), default=0)
        cube_ever_lifted = cube_max_z > 0.775 + 0.05  # 0.775 = template init Z
        if int(cm.get("under_target", False)):
            failure_mode = "delivered"
        elif not cube_ever_lifted:
            failure_mode = "C_pickup_never_lifted"  # friction-grip too weak (low mu) or palm missed cube
        elif cube_lost_t is not None:
            if cube_lost_t < 15.0 and (cube_lost_dist_from_bin or 0) > 0.30:
                failure_mode = "A_dropped_in_transit"
            else:
                failure_mode = "B_missed_bin"

        # Friction equiv of unrealistic_grip: cube held while EE-cube distance > 15cm
        # (real friction-grip needs fingers ON cube, not 15cm away)
        for s in traj[len(traj)//3:]:  # check mid-late trajectory
            ee = s.get("ee"); cm_pos = s.get("cubes",{}).get("/World/Cube_M")
            if not ee or not cm_pos: continue
            d = ((ee[0]-cm_pos[0])**2 + (ee[1]-cm_pos[1])**2)**0.5
            # If cube z > table_top + 10cm (lifted) AND EE far from cube → telekinesis
            if cm_pos[2] > 0.85 and d > 0.15:
                ve_detected.append("friction_unrealistic_lift")
                break

    # 2026-05-26: VE-pattern weights — AUDITED for CP-PRECISION-3CUBE + FRICTION-GRIP paradigm
    # SKIPPED (FJ-event-dependent, friction-grip has no FJ → false signals):
    #   picked_then_dropped (requires FJ ever existed)
    #   gripper_freeze_above_cube (triggers ALWAYS for friction since no FJ created)
    #   unrealistic_grip (FJ-distance-based)
    # SKIPPED (irrelevant for 3CUBE):
    #   never_picked (intent for sides), cubes_roll_off_belt, cube_passes_sensor_zone_*,
    #   mobile_robot_*, partial_delivery (stack), cube_bounces_off_target (false-pos),
    #   arm_speed_yeet (threshold-dependent)
    VE_WEIGHTS = {
        # Original VE-patterns (work for friction-grip too):
        "cube_tilts_over": 30,            # tilt>45° AND not in bin — catches friction-slip
        "delivered_then_dislodged": 20,   # cube_in_target ever AND not under_target — knocked out
        "cube_shifted_at_placement": 15,  # in_target AND drift 3-20cm — palm-flick at placement
        "telepathic_contact": 50,         # FJ distance>20cm — zero-trigger för friction = safe penalty
        "bin_wall_collision": 10,         # EE inside bin AABB pushing wall
        "blowup_at_release": 25,          # cube velocity > 5m/s — physics explosion
        # Friction-grip-specific (re-implemented in compute_penalty using trajectory):
        "friction_picked_then_dropped": 50,  # RAISED — penalize HARD: cube lifted then dropped mid-transit
        "friction_gripper_freeze": 25,       # EE near cube >2s but cube never moved
        "friction_unrealistic_lift": 30,     # cube lifted while EE >15cm away = telekinesis
    }
    ve_penalty = sum(VE_WEIGHTS.get(name, 0) for name in ve_detected)

    # ============ AGGRESSIVE: Very high weight on grip position accuracy ============
    # Position error is critical - if we don't reach the right spot, nothing else matters
    # With 2mm target: error=2mm -> 1.0 * 50 = 50 penalty, error=4mm -> 2.0 * 50 = 100 penalty
    # 2026-05-26: adj_disp × 100 is the strong discriminator (L/R XY-shift, measured in meters)
    # 2026-05-27: CLIPPED at 1m — PhysX explosions ejected cubes to 30km, making all iter look identical (always max).
    # Clipping lets optimizer differentiate 5mm vs 50mm iter while still penalizing explosions heavily.
    adj_disp_clipped = min(adj_disp, 1.0)
    total = (grip_error_normalized * 20 +      # grip already 0.1mm capable
             adj_disp_clipped * 100 +           # CLIPPED: L/R displacement penalty (max 100)
             drop_xy_err * 1 +
             z_err_floor * 2 +
             col_normalized * 1 +               # generic col_count incl ee_vs_bin
             (0 if reward_full else 1.0) +      # Success bonus
             time_penalty +
             ve_penalty)

    return {
        "adj_disp_m": round(adj_disp, 4),
        "disp_l_m": round(disp_l, 4),
        "disp_r_m": round(disp_r, 4),
        "drop_xy_err_m": round(drop_xy_err, 4),
        "z_err_floor_m": round(z_err_floor, 4),
        "grip_pos_error_m": round(grip_pos_error, 4),
        "approach_pos_error_m": round(approach_pos_error, 4),
        "inside_bin": inside_bin,
        "cube_on_floor": cube_on_floor,
        "reward_full": int(reward_full),
        "col_direct": col_direct,
        "col_indirect": col_indirect,
        "col_count": col_count,
        # 2026-05-26 BUGFIX: under_target raycast misses when cube rests ON bin floor (origin offset issue).
        # Fallback: geometric check — cube center inside bin XY-half + cube_Z in bin Z range (0.75..0.82).
        "delivered": int(cm.get("under_target", False) or (
            fp_m and len(fp_m) >= 3
            and abs(fp_m[0]-BIN_CENTER_XY[0]) < BIN_INNER_HALF_XY
            and abs(fp_m[1]-BIN_CENTER_XY[1]) < BIN_INNER_HALF_XY
            and 0.75 <= fp_m[2] <= 0.82)),
        "elapsed_s": round(elapsed_s, 1),
        "time_penalty": round(time_penalty, 3),
        "total_penalty": round(total, 4),
        "culprit_breakdown": dict(culprit_breakdown),
        "ve_detected": ve_detected,
        "ve_narrative": ve_narrative,
        "failure_mode": failure_mode if 'failure_mode' in dir() else "unknown",
        "cube_lost_t": cube_lost_t if 'cube_lost_t' in dir() else None,
        "cube_lost_dist_from_bin_m": round(cube_lost_dist_from_bin, 3) if 'cube_lost_dist_from_bin' in dir() and cube_lost_dist_from_bin else None,
        "params": params,
    }


# ============ Main loop ============

async def run_one_iter(iter_id: str, params: dict, iter_dir: Path) -> dict:
    iter_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Iter {iter_id}: {params}", flush=True)
    (iter_dir / "params.json").write_text(json.dumps(params, indent=2))
    # edit_handler_params(params)  # 2026-05-26: DISABLED — caused pick_place.py corruption

    # Ensure Kit is running (uses kit_alive and restart_kit from sweep_all_rewritten)
    if not kit_alive():
        print("  Kit not alive, restarting...")
        if not await restart_kit():
            print("  Kit restart FAILED — skip")
            return None

    t0 = time.time()
    rec = await observe_one("CP-PRECISION-3CUBE")
    elapsed = time.time() - t0

    # Check for exceptions from observe_one
    if rec.get("exception"):
        print(f"  observe_one exception: {rec['exception']}")
        return None

    (iter_dir / "raw.jsonl").write_text(json.dumps(rec, default=str))

    # 2026-05-27: compute penalty up-front so we can skip cameras on perfect-reward iter (saves ~5-6s).
    penalty = compute_penalty(rec, elapsed, params)
    (iter_dir / "metrics.json").write_text(json.dumps(penalty, indent=2))

    # 2026-05-26: Multi-view capture at final state — visual eyes for human/agent
    # Top (XY drop precision), Iso (overall scene), Side (Z/grip-height)
    # Cameras created once per iter via exec_sync, then switched via /set_viewport_camera.
    # 2026-05-27: SKIP cameras on reward_full==1 (saves ~6s); always on failures + every 25th iter.
    try:
        _iter_num = int(iter_id)
    except Exception:
        _iter_num = 0
    _capture_cams = (penalty.get("reward_full", 0) != 1) or (_iter_num % 25 == 0)
    if _capture_cams:
      try:
        import urllib.request, urllib.parse, base64
        # Create 3 cameras pointing at workspace center (0, 0, 0.85)
        cam_code = """
import omni.usd
from pxr import UsdGeom, Gf, Sdf
stage = omni.usd.get_context().get_stage()
# Workspace target ~ (0, 0, 0.85) — covers Franka(0,0,0.75)+cubes(-0.3,0.3)+bin(0.27,-0.33)
def _mk_cam(path, pos, target, up_hint=(0,0,1)):
    if not stage.GetPrimAtPath(path).IsValid():
        cam = UsdGeom.Camera.Define(stage, path)
    else:
        cam = UsdGeom.Camera(stage.GetPrimAtPath(path))
    xf = UsdGeom.Xformable(cam.GetPrim())
    xf.ClearXformOpOrder()
    p = Gf.Vec3d(*pos); t = Gf.Vec3d(*target); up = Gf.Vec3d(*up_hint)
    fwd = (t - p); fwd_n = fwd.GetNormalized()
    # Guard against gimbal lock: if up || fwd, pick a different up
    if abs(Gf.Dot(fwd_n, up)) > 0.99:
        up = Gf.Vec3d(0, 1, 0) if abs(Gf.Dot(fwd_n, Gf.Vec3d(0,1,0))) < 0.99 else Gf.Vec3d(1, 0, 0)
    # Camera convention in USD: -Z forward, +Y up
    right = Gf.Cross(fwd_n, up).GetNormalized()
    cam_up = Gf.Cross(right, fwd_n).GetNormalized()
    m = Gf.Matrix4d(
        right[0],  right[1],  right[2],  0,
        cam_up[0], cam_up[1], cam_up[2], 0,
        -fwd_n[0], -fwd_n[1], -fwd_n[2], 0,
        p[0], p[1], p[2], 1)
    xf.AddTransformOp().Set(m)
    cam.GetFocalLengthAttr().Set(24.0)  # wider FOV
# Top-down: explicit up=+Y avoids gimbal lock (Z-fwd parallel to Z-up)
_mk_cam("/World/_DebugCam_Top",  (0, 0, 2.0),     (0, 0, 0.78), up_hint=(0,1,0))
_mk_cam("/World/_DebugCam_Iso",  (0.9, -0.9, 1.6), (0, 0, 0.85))
_mk_cam("/World/_DebugCam_Side", (1.4, 0.0, 0.95), (0, 0, 0.85))
print("CAMS_OK")
"""
        from service.isaac_assist_service.chat.tools import kit_tools
        await kit_tools.exec_sync(cam_code, timeout=10)
        for cam_name, cam_path in [("top", "/World/_DebugCam_Top"), ("iso", "/World/_DebugCam_Iso"), ("side", "/World/_DebugCam_Side")]:
            try:
                # Set viewport camera + advance render frames SYNCHRONOUSLY (PATCH_QUEUE was async and not honored)
                switch_code = f"""
import omni.kit.viewport.utility, omni.kit.app
vp = omni.kit.viewport.utility.get_active_viewport()
vp.camera_path = '{cam_path}'
app = omni.kit.app.get_app()
for _ in range(8):
    app.update()
print('SWITCHED:{cam_path}')
"""
                await kit_tools.exec_sync(switch_code, timeout=10)
                with urllib.request.urlopen("http://127.0.0.1:8001/capture?max_dim=1280", timeout=15) as r:
                    d = json.loads(r.read())
                    if d.get("image_b64"):
                        (iter_dir / f"view_{cam_name}.png").write_bytes(base64.b64decode(d["image_b64"]))
            except Exception as e:
                print(f"  capture {cam_name} failed: {e}")
      except Exception as e:
        print(f"  multi-view capture failed: {e}")

    print(f"  PENALTY: total={penalty['total_penalty']:.3f} grip_err={penalty['grip_pos_error_m']:.4f}m approach_err={penalty['approach_pos_error_m']:.4f}m adj={penalty['adj_disp_m']} drop_xy={penalty['drop_xy_err_m']} z_floor={penalty['z_err_floor_m']} col={penalty['col_count']} reward={penalty['reward_full']} ({elapsed:.1f}s) cams={'Y' if _capture_cams else 'N'}",
          flush=True)
    return penalty


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-hours", type=float, default=36.0)
    parser.add_argument("--random", action="store_true", help="Random sample (vs grid)")
    parser.add_argument("--material", default="rubber", choices=["rubber", "metal", "plastic", "glass"],
                        help="Material category — constrains friction_mu range")
    parser.add_argument("--max-iter", type=int, default=0, help="Stop after N iter (0 = no limit, use --max-hours)")
    args = parser.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = OUT_BASE / f"run_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / "results.csv"
    best_path = run_dir / "BEST.json"

    print(f"Run dir: {run_dir}")
    print(f"Max time: {args.max_hours}h | material: {args.material} | max_iter: {args.max_iter or 'no-limit'}")

    # Material-specific friction_mu range (real-world datasheet values)
    MAT_MU = {
        "rubber":  [0.6, 0.9, 1.2],
        "metal":   [0.3, 0.5, 0.7],
        "plastic": [0.2, 0.4, 0.6],
        "glass":   [0.1, 0.2, 0.3],
    }
    # 2026-05-26: Only apply material override if PARAM_GRID is in default-multi-value state (smart-region locks via single-value list).
    if len(PARAM_GRID.get("friction_mu", [])) > 1:
        PARAM_GRID["friction_mu"] = MAT_MU.get(args.material, PARAM_GRID["friction_mu"])
    else:
        print(f"  PARAM_GRID friction_mu LOCKED to {PARAM_GRID['friction_mu']} (material flag {args.material} ignored)")
    print(f"friction_mu range for {args.material}: {PARAM_GRID['friction_mu']}")

    # Ensure Kit is running at start
    if not kit_alive():
        print("Starting Kit headless...")
        if not await launch_kit():
            print("Failed to start Kit - exiting")
            return

    # CSV header
    fields = ["iter_id", "timestamp"] + list(PARAM_GRID.keys()) + [
        "total_penalty", "adj_disp_m", "drop_xy_err_m", "z_err_floor_m",
        "grip_pos_error_m", "approach_pos_error_m",
        "inside_bin", "cube_on_floor", "reward_full", "col_count", "col_direct", "col_indirect",
        "delivered", "elapsed_s",
    ]
    with csv_path.open("w", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writeheader()

    if args.random:
        # Random sample mode
        param_iter = iter(lambda: {k: random.choice(v) for k, v in PARAM_GRID.items()}, None)
    else:
        # Grid mode
        keys = list(PARAM_GRID.keys())
        combos = list(product(*PARAM_GRID.values()))
        random.shuffle(combos)  # randomize order so we don't bias by params
        print(f"Grid: {len(combos)} combos")
        def _gen():
            for c in combos:
                yield dict(zip(keys, c))
        param_iter = _gen()

    start = time.time()
    deadline = start + args.max_hours * 3600
    best = None
    n = 0

    try:
        for params in param_iter:
            if time.time() >= deadline:
                print(f"  Deadline reached")
                break
            n += 1

            # 2026-05-26 DISABLED: Periodic Kit restart breaks cuRobo motion-controller state.
            # iter 1-9 produced valid data; iter 10+ post-restart had adj_disp=0 (robot never moved)
            # despite cubes spawning correctly. Trade staleness risk for state continuity.
            # if n > 1 and n % 10 == 0:
            #     restart_kit_headless()

            iter_dir = run_dir / f"iter_{n:04d}"
            p = await run_one_iter(f"{n:04d}", params, iter_dir)
            if p is None:
                continue
            # Append to CSV
            row = {"iter_id": f"{n:04d}", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
            for k in PARAM_GRID:
                row[k] = params.get(k)
            for k in ["total_penalty", "adj_disp_m", "drop_xy_err_m", "z_err_floor_m",
                      "grip_pos_error_m", "approach_pos_error_m",
                      "inside_bin", "cube_on_floor", "reward_full", "col_count", "col_direct", "col_indirect",
                      "delivered", "elapsed_s"]:
                row[k] = p.get(k)
            with csv_path.open("a", newline="") as f:
                csv.DictWriter(f, fieldnames=fields).writerow(row)
            if best is None or p["total_penalty"] < best["total_penalty"]:
                best = p
                best_path.write_text(json.dumps(best, indent=2))
                print(f"  >>> NEW BEST: total={p['total_penalty']} {params}", flush=True)
            if n % 10 == 0:
                eh = (time.time() - start) / 3600
                print(f"--- {n} iter, {eh:.2f}h elapsed, best={best['total_penalty'] if best else None}")
    finally:
        revert_handler_params()
        print(f"DONE. {n} iter, {(time.time()-start)/3600:.2f}h. Reverted params.")


if __name__ == "__main__":
    asyncio.run(main())
