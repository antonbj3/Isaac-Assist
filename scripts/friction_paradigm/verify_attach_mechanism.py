"""Verify cuRobo attachment_manager ACTUALLY changes plan_pose trajectory output.

Compare trajectory between:
- attach OFF (clean planner)
- attach ON (cube attached to TOOL_FRAME)

Same start joint state + same goal (vertical motion). Measure max XY-drift.
"""
import asyncio, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))
from service.isaac_assist_service.chat.tools import kit_tools

async def main():
    code = """
import builtins, torch
import numpy as np

_planner = None
for attr in ('_curobo_pp_planner_v21',):
    if hasattr(builtins, attr):
        _planner = getattr(builtins, attr); break
if _planner is None:
    print('NO_PLANNER')
else:
    from curobo.types import JointState, GoalToolPose
    from curobo._src.geom.types import Cuboid

    # Start joint state at default pose
    start_q = _planner.default_joint_state.position.clone()
    if start_q.ndim == 1: start_q = start_q.unsqueeze(0)
    start_q = start_q[:, :7].to(dtype=torch.float32, device='cuda')
    start = JointState.from_position(start_q, joint_names=_planner.joint_names[:7])

    fk_state = _planner.compute_kinematics(start)
    start_ee = fk_state.tool_poses.position[0, 0, 0].detach().cpu().numpy()
    print(f'START_EE: {start_ee.tolist()}')

    goal_z = float(start_ee[2]) + 0.20
    goal_pos = torch.tensor([[[[[float(start_ee[0]), float(start_ee[1]), goal_z]]]]], dtype=torch.float32, device='cuda')
    goal_quat = torch.tensor([[[[[1.0, 0.0, 0.0, 0.0]]]]], dtype=torch.float32, device='cuda')
    tool_frame = _planner.tool_frames[0]
    goal = GoalToolPose(tool_frames=[tool_frame], position=goal_pos, quaternion=goal_quat)

    def _measure_xy_drift(res):
        if res is None or not bool(res.success[0,0].item()): return None
        interp = res.get_interpolated_plan()
        traj_q = interp.position[0, 0, :, :7].to(dtype=torch.float32, device='cuda')
        max_d = 0
        for i in range(traj_q.shape[0]):
            js = JointState.from_position(traj_q[i:i+1], joint_names=_planner.joint_names[:7])
            fk = _planner.compute_kinematics(js)
            x = float(fk.tool_poses.position[0, 0, 0, 0])
            y = float(fk.tool_poses.position[0, 0, 0, 1])
            d = ((x-start_ee[0])**2 + (y-start_ee[1])**2)**0.5
            if d > max_d: max_d = d
        return max_d

    # PLAN A: WITHOUT attach
    res_off = _planner.plan_pose(goal, start, max_attempts=3)
    drift_off = _measure_xy_drift(res_off)
    print(f'XY_DRIFT_OFF: {drift_off}')

    # Attach cube
    cube_obs = Cuboid(name='picked_cube', pose=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0], dims=[0.05, 0.05, 0.05])
    try:
        _planner.trajopt_solver.core.attachment_manager.attach(joint_states=start, obstacles=[cube_obs], link_name=tool_frame)
        print('ATTACH OK')
    except Exception as e:
        print(f'ATTACH FAIL: {type(e).__name__}: {e}')

    # PLAN B: WITH attach
    res_on = _planner.plan_pose(goal, start, max_attempts=3)
    drift_on = _measure_xy_drift(res_on)
    print(f'XY_DRIFT_ON: {drift_on}')

    # Detach
    try:
        _planner.trajopt_solver.core.attachment_manager.detach(link_name=tool_frame)
        print('DETACH OK')
    except Exception as e:
        print(f'DETACH FAIL: {e}')

    if drift_off is not None and drift_on is not None:
        ratio = drift_on / drift_off if drift_off > 0 else float('inf')
        print(f'DRIFT: {drift_off*1000:.1f}mm OFF -> {drift_on*1000:.1f}mm ON (ratio={ratio:.3f})')
    print('TEST_DONE')
"""
    r = await kit_tools.exec_sync(code, timeout=60)
    print(r.get("output", "")[:3000])

if __name__ == "__main__":
    asyncio.run(main())
