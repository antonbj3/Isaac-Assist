"""Verify cuRobo PoseCostMetric ACTUALLY changes plan_pose trajectory output.

Compare trajectory between:
- vhold OFF (default planning)
- vhold ON (hold_vec_weight=[100,100,100,100,100,0])

Both with same start joint state + same goal (vertical motion).
Measure max XY-drift in trajectory.

If max_drift_off ≈ max_drift_on → mechanism not applying.
If max_drift_off > max_drift_on → mechanism works (just maybe needs more weight).
"""
import asyncio, sys, json
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))
from service.isaac_assist_service.chat.tools import kit_tools

async def main():
    # Send code to Kit that:
    # 1. Loads the planner (must be already-built from prior run)
    # 2. Plans a vertical motion WITHOUT vhold → record trajectory
    # 3. Apply vhold → plan SAME motion → record trajectory
    # 4. Compare XY drift in both
    code = """
import builtins, torch, json
import numpy as np

# Find cached planner
_planner = None
for attr in ('_curobo_pp_planner_v21', '_curobo_pp_planner_v20'):
    if hasattr(builtins, attr):
        _planner = getattr(builtins, attr); break
if _planner is None:
    print('NO_PLANNER');
else:
    from curobo.types import JointState, GoalToolPose
    from curobo._src.cost.cost_pose_metric import PoseCostMetric

    # Start joint state: arbitrary mid-pose (use planner's default joint state)
    start_q = _planner.default_joint_state.position.clone()
    # Ensure batch dim
    if start_q.ndim == 1: start_q = start_q.unsqueeze(0)
    start_q = start_q[:, :7].to(dtype=torch.float32, device='cuda')
    start = JointState.from_position(start_q, joint_names=_planner.joint_names[:7])

    # Compute FK of start to get start EE pose
    fk_state = _planner.compute_kinematics(start)
    # tool_poses.position shape [B, H, L, 3]
    start_ee = fk_state.tool_poses.position[0, 0, 0].detach().cpu().numpy()
    print(f'START_EE: {start_ee.tolist()}')

    # Vertical goal: same XY, Z = start_ee[2] + 0.20
    goal_z = float(start_ee[2]) + 0.20
    goal_pos = torch.tensor([[[[[float(start_ee[0]), float(start_ee[1]), goal_z]]]]], dtype=torch.float32, device='cuda')
    # Identity-ish quaternion (use planner's default tool quat)
    # Approximation: gripper pointing down (w,x,y,z = 0, 1, 0, 0 for X-axis flip)
    goal_quat = torch.tensor([[[[[1.0, 0.0, 0.0, 0.0]]]]], dtype=torch.float32, device='cuda')
    tool_frame = _planner.tool_frames[0]
    goal = GoalToolPose(tool_frames=[tool_frame], position=goal_pos, quaternion=goal_quat)

    print(f'TOOL_FRAME: {tool_frame}')
    print(f'GOAL_Z: {goal_z}')

    def _measure_xy_drift(res):
        if res is None or not bool(res.success[0,0].item()):
            return None
        interp = res.get_interpolated_plan()
        # FK each timestep to get EE positions
        traj_q = interp.position[0, 0, :, :7].to(dtype=torch.float32, device='cuda')
        # Compute kinematics for each
        ee_xs, ee_ys = [], []
        for i in range(traj_q.shape[0]):
            js = JointState.from_position(traj_q[i:i+1], joint_names=_planner.joint_names[:7])
            fk = _planner.compute_kinematics(js)
            ee_xs.append(float(fk.tool_poses.position[0, 0, 0, 0]))
            ee_ys.append(float(fk.tool_poses.position[0, 0, 0, 1]))
        max_xy_drift = max(((x-start_ee[0])**2 + (y-start_ee[1])**2)**0.5 for x,y in zip(ee_xs, ee_ys))
        return max_xy_drift

    # PLAN A: WITHOUT vhold
    res_off = _planner.plan_pose(goal, start, max_attempts=3)
    drift_off = _measure_xy_drift(res_off)
    print(f'XY_DRIFT_OFF: {drift_off}')

    # Apply vhold
    _pcm = PoseCostMetric(
        hold_partial_pose=True,
        hold_vec_weight=torch.tensor([100.0,100.0,100.0,100.0,100.0,0.0], device='cuda', dtype=torch.float32),
        project_to_goal_frame=False,
    )
    _pcm_dict = {tool_frame: _pcm}
    try:
        _planner.ik_solver.update_pose_cost_metric(_pcm_dict)
        _planner.trajopt_solver.update_pose_cost_metric(_pcm_dict)
        print('VHOLD_APPLY: OK')
    except Exception as e:
        print(f'VHOLD_APPLY_FAIL: {type(e).__name__}: {e}')

    # PLAN B: WITH vhold
    res_on = _planner.plan_pose(goal, start, max_attempts=3)
    drift_on = _measure_xy_drift(res_on)
    print(f'XY_DRIFT_ON: {drift_on}')

    # Release
    try:
        _release = {tool_frame: PoseCostMetric(release_partial_pose=True)}
        _planner.ik_solver.update_pose_cost_metric(_release)
        _planner.trajopt_solver.update_pose_cost_metric(_release)
        print('VHOLD_RELEASE: OK')
    except Exception as e:
        print(f'VHOLD_RELEASE_FAIL: {e}')

    if drift_off is not None and drift_on is not None:
        ratio = drift_on / drift_off if drift_off > 0 else float('inf')
        print(f'DRIFT_REDUCTION: {drift_off*1000:.2f}mm -> {drift_on*1000:.2f}mm (ratio={ratio:.3f})')
    print('TEST_DONE')
"""
    print("Sending test to Kit...")
    r = await kit_tools.exec_sync(code, timeout=60)
    print(r.get("output", "")[:4000])
    if r.get("error"):
        print(f"ERROR: {r['error']}")

if __name__ == "__main__":
    asyncio.run(main())
