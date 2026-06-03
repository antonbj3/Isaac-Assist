"""
cuRobo hyperparameter auto-tuning för Cube_Drop grip-pose.

Each iter: sample params + plan cuRobo to Cube_Drop pose + measure palm-vs-target error.
Save best params + every result.

Run headless for 12h. Anton reviews on weekly-limit-recovery.

Usage:
    python scripts/friction_paradigm/cu_tune_cube_drop.py [max_hours]
"""

import urllib.request
import json
import time
import random
from pathlib import Path
from datetime import datetime

KIT_URL = "http://127.0.0.1:8001/exec_sync"
OUT_DIR = Path("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/friction_tuning/cu_tune_results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_WORLD = [0.264, -0.3335, 0.9932]  # Cube_Drop + 0.105
TARGET_BASE = [TARGET_WORLD[0], TARGET_WORLD[1], TARGET_WORLD[2] - 0.75]  # base-relative


def kit_exec(code: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        KIT_URL,
        data=json.dumps({"code": code, "timeout": timeout}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())


def reset_scene():
    """Stop + reset template + stop+kill subs."""
    kit_exec(
        """
import omni.timeline, omni.kit.app, builtins
omni.timeline.get_timeline_interface().stop()
for _ in range(20): omni.kit.app.get_app().update()
for n in list(vars(builtins).keys()):
    if n.startswith('_'):
        try:
            o = getattr(builtins, n, None)
            if o and hasattr(o, 'unsubscribe'): o.unsubscribe(); delattr(builtins, n)
        except: pass
""",
        timeout=15,
    )
    import subprocess

    subprocess.run(
        [
            "python",
            "-c",
            """
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, '/home/anton/projects/Omniverse_Nemotron_Ext')
from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical
async def main():
    tpl = json.loads(Path('/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-PRECISION-3CUBE.json').read_text())
    r = await execute_template_canonical(tpl)
asyncio.run(main())
""",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Post-reset stop + kill
    kit_exec(
        """
import omni.timeline, omni.kit.app, builtins
omni.timeline.get_timeline_interface().stop()
for _ in range(15): omni.kit.app.get_app().update()
for n in list(vars(builtins).keys()):
    if n.startswith('_'):
        try:
            o = getattr(builtins, n, None)
            if o and hasattr(o, 'unsubscribe'): o.unsubscribe(); delattr(builtins, n)
        except: pass
""",
        timeout=15,
    )


def force_home_pose():
    """Bypass PD via set_joint_positions to clean home."""
    return kit_exec(
        """
import numpy as np
import omni.timeline, omni.kit.app
from isaacsim.core.prims import Articulation as AV
tl = omni.timeline.get_timeline_interface()
if not tl.is_playing(): tl.play()
for _ in range(15): omni.kit.app.get_app().update()
av = AV(prim_paths_expr='/World/Franka'); av.initialize()
home = np.array([[0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04]])
av.set_joint_positions(home)
try: av.set_joint_velocities(np.zeros((1, 9)))
except: pass
for _ in range(30): omni.kit.app.get_app().update()
q = av.get_joint_positions()[0, :7]
import torch
if isinstance(q, torch.Tensor): q = q.cpu().numpy()
print('Joints:', [round(float(x),3) for x in q])
""",
        timeout=30,
    )


def run_curobo(params: dict) -> dict:
    """Run cuRobo plan + apply + measure palm-vs-target error."""
    code = f"""
import numpy as np, torch
import omni.kit.app, omni.usd
from pxr import UsdGeom, Sdf
from isaacsim.core.prims import SingleArticulation
from omni.isaac.core.utils.types import ArticulationAction
from curobo.types import JointState, GoalToolPose
from curobo.motion_planner import MotionPlanner, MotionPlannerCfg

stage = omni.usd.get_context().get_stage()
ee_prim = stage.GetPrimAtPath(Sdf.Path('/World/Franka/panda_hand'))
art = SingleArticulation(prim_path='/World/Franka')
try: art.initialize()
except: pass

current_q = art.get_joint_positions()

_pcfg = MotionPlannerCfg.create(
    robot='franka.yml',
    use_cuda_graph=False,
    num_ik_seeds={params['num_ik_seeds']},
    num_trajopt_seeds={params['num_trajopt_seeds']},
    position_tolerance={params['position_tolerance']},
    orientation_tolerance={params['orientation_tolerance']},
    self_collision_check={params['self_collision_check']},
)
planner = MotionPlanner(_pcfg)

target_base = {TARGET_BASE}
quat = {params['quat']}

pos_t = torch.tensor([[[[target_base]]]], dtype=torch.float32, device='cuda')
quat_t = torch.tensor([[[[quat]]]], dtype=torch.float32, device='cuda')
goal = GoalToolPose(tool_frames=['panda_hand'], position=pos_t, quaternion=quat_t)
q_t = torch.tensor([[float(x) for x in current_q[:7]]], dtype=torch.float32, device='cuda')
start = JointState.from_position(q_t, joint_names=list(planner.joint_names))
res = planner.plan_pose(goal, start, max_attempts={params['max_attempts']})

if res is None or not bool(res.success[0,0].item()):
    print('PLAN_FAILED')
else:
    traj = res.get_interpolated_plan().position[0,0,:,:7].detach().cpu().numpy()
    app = omni.kit.app.get_app()
    for wp in traj:
        art.apply_action(ArticulationAction(joint_positions=wp, joint_indices=np.arange(7)))
        for _ in range(4): app.update()
    for _ in range(120): app.update()
    ee = UsdGeom.Xformable(ee_prim).ComputeLocalToWorldTransform(0).ExtractTranslation()
    mtx = UsdGeom.Xformable(ee_prim).ComputeLocalToWorldTransform(0)
    m = np.array(mtx, dtype=np.float64)
    z_dir = m[:3,:3][2,:3]
    ideal = np.array([0,0,-1.0])
    orient_err_deg = np.rad2deg(np.arccos(np.clip(np.dot(z_dir, ideal), -1, 1)))
    target_world = {TARGET_WORLD}
    pos_err_mm = np.linalg.norm(np.array([float(ee[0]), float(ee[1]), float(ee[2])]) - np.array(target_world)) * 1000
    print(f'RESULT pos_err_mm={{pos_err_mm:.2f}} orient_err_deg={{orient_err_deg:.2f}} palm=[{{ee[0]:.4f}},{{ee[1]:.4f}},{{ee[2]:.4f}}]')
"""
    try:
        r = kit_exec(code, timeout=180)
        out = r.get("output", "")
        if "PLAN_FAILED" in out:
            return {"success": False, "pos_err_mm": None, "orient_err_deg": None}
        if "RESULT" in out:
            line = [l for l in out.splitlines() if "RESULT" in l][0]
            pos = float(line.split("pos_err_mm=")[1].split()[0])
            orient = float(line.split("orient_err_deg=")[1].split()[0])
            return {"success": True, "pos_err_mm": pos, "orient_err_deg": orient}
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": False, "output": out}


def sample_params() -> dict:
    """Random hyperparameter sample."""
    base_quat = [0.0, 1.0, 0.0, 0.0]
    yaw = random.uniform(-3.14, 3.14)
    cos_y, sin_y = (yaw / 2).__abs__() and (__import__("math").cos(yaw / 2), __import__("math").sin(yaw / 2)) or (1, 0)
    # quat for 180° X then yaw around Z
    import math
    cos_y = math.cos(yaw / 2)
    sin_y = math.sin(yaw / 2)
    quat = [
        round(0 * cos_y - 1 * 0, 4),
        round(1 * cos_y + 0 * 0, 4),
        round(0 * cos_y - 0 * sin_y, 4),
        round(0 * cos_y + 1 * sin_y, 4),
    ]
    return {
        "num_ik_seeds": random.choice([32, 64, 128, 256]),
        "num_trajopt_seeds": random.choice([4, 8, 16, 32]),
        "position_tolerance": random.choice([0.001, 0.003, 0.005, 0.01, 0.02]),
        "orientation_tolerance": random.choice([0.05, 0.1, 0.3, 0.5, 1.0, 1.5]),
        "self_collision_check": random.choice([True, False]),
        "quat": quat,
        "max_attempts": random.choice([5, 10, 20, 30]),
        "yaw_deg": round(math.degrees(yaw), 1),
    }


def main():
    import sys
    max_hours = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    start = time.time()
    deadline = start + max_hours * 3600

    results_file = OUT_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    best_file = OUT_DIR / "BEST_SO_FAR.json"

    iter_n = 0
    best = None
    print(f"START {datetime.now().isoformat()}. Max {max_hours}h. Target world {TARGET_WORLD}")
    print(f"Logging to: {results_file}")

    while time.time() < deadline:
        iter_n += 1
        params = sample_params()
        try:
            reset_scene()
            force_home_pose()
            result = run_curobo(params)
        except Exception as e:
            result = {"success": False, "error": f"runtime: {e}"}

        record = {"iter": iter_n, "timestamp": datetime.now().isoformat(), "params": params, "result": result}
        with results_file.open("a") as f:
            f.write(json.dumps(record) + "\n")

        if result.get("success"):
            # Score: pos_err_mm + 10 * orient_err_deg (combined metric)
            score = result["pos_err_mm"] + 10 * result["orient_err_deg"]
            if best is None or score < best.get("score", 1e9):
                best = {"iter": iter_n, "params": params, "result": result, "score": score}
                best_file.write_text(json.dumps(best, indent=2))
                print(f"  NEW BEST iter {iter_n}: pos {result['pos_err_mm']:.1f}mm orient {result['orient_err_deg']:.1f}° score {score:.2f}")
        if iter_n % 10 == 0:
            elapsed_h = (time.time() - start) / 3600
            print(f"iter {iter_n} elapsed {elapsed_h:.2f}h best_score={best.get('score', None) if best else None}")

    print(f"DONE iter {iter_n}, elapsed {(time.time()-start)/3600:.2f}h")


if __name__ == "__main__":
    main()
