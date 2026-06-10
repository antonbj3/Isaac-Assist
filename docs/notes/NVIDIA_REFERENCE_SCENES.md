# NVIDIA Isaac reference / sample scenes (ground-truth "facit" for later)

Root: `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/`

## Manipulation / pick-place (most relevant to the UR10 suction work)
- `Samples/Leonardo/Stage/ur10_bin_stacking_short_suction.usd` ← **the UR10 short-suction facit** (used below)
- `Samples/Leonardo/Stage/ur10_bin_stacking_short_suction_2.usd`
- `Samples/Leonardo/Stage/ur10_bin_stacking_long_conveyor.usd`
- `Samples/Leonardo/Stage/ur10_bin_filling.usd`
- `Samples/Leonardo/Stage/franka_block_stacking.usd`
- `Samples/Replicator/Stage/sdg_grasping_xarm.usd` (xArm grasping, SDG)
- `Robots/UniversalRobots/ur10/Legacy/ur10_short_suction.usd`, `ur10_long_suction.usd` (robot+gripper, no demo)
- Props: `Samples/Leonardo/Props/{conveyor,stacking_conveyor,pipe_funnel}.usd`

## Mobile (Carter / Nova Carter / forklift)
- `Samples/OmniGraph/nova_carter_drive_to_goal.usd`
- `Samples/NvBlox/Robots/{carter_nvblox_ros,Nova_Carter_ROS_nvblox_setup}.usd`
- `Samples/ROS2/Robots/{Carter_ROS,forklift_b_ROS,iw_hub_ROS,leatherback_ROS}.usd`
- `Robots/NVIDIA/Carter/{carter_v1,carter_v1_physx_lidar}.usd`, `Robots/NVIDIA/NovaCarter/nova_carter.usd`
- `Samples/Rigging/Forklift/forklift_b_rigged_cm.usd`, `Samples/Rigging/NovaCarterDevKit/nova_carter_dev_kit.usd`

## Humanoids / quadrupeds
- G1: `Samples/Groot/Robots/g1_29dof_anneal_23dof.usd`, `g1_29dof_with_hand_rev_1_0.usd`; `Robots/Unitree/G1/g1.usd`
- H1: `Samples/Rigging/H1/h1_rigged.usd`, `Samples/ROS2/Robots/h1_ROS.usd`, `Robots/Unitree/H1/h1.usd`
- Digit: `Robots/Agility/Digit/digit_v4.usd`
- Fourier GR-1: `Robots/FourierIntelligence/GR-1/GR1T1/GR1_T1.usd`, `.../GR1T2_fourier_hand_6dof/...`
- Unitree quadrupeds: A1, Go1/Go2, B2, aliengo, laikago; arm: Z1; hands: Dex3/Dex5
- IsaacSim humanoid: `Robots/IsaacSim/Humanoid/humanoid.usd`, `Humanoid28/humanoid_28.usd`; `Robots/XHumanoid/Tien Kung/tienkung.usd`

## Warehouse / SDG / misc
- `Samples/Replicator/Stage/full_warehouse_worker_and_anim_cameras.usd`, `warehouse_pallets_behavior_scripts.usd`
- `Samples/Replicator/Benchmark/full_warehouse_worker_benchmark_sdg.usd`
- `Samples/NvBlox/nvblox_sample_scene.usd`, `Samples/Rigging/{Jetbot,RubiksCube,ChargingDock}/...`

## KEY FINDING — the UR10 short-suction MOUNT (facit vs ours)
From `ur10_bin_stacking_short_suction.usd` (probed 2026-06-06):
- NVIDIA mounts the gripper **as CHILDREN of `ur10/ee_link`** — clean, inheriting the flange frame:
  `ee_link/suction_cup`, `ee_link/suction_cup/Suction_Joint` (PhysicsJoint), `ee_link/SurfaceGripper`
  (IsaacSurfaceGripper), + visual meshes `ee_link/{gripper_tip,gripper_base,tube,mount,...}`.
- The cup geometry is the SAME as our hotswap asset: `suction_cup` = `ee_link + 0.1585·(ee +X)` (cup along ee +X).
- **Difference from ours:** we mount the asset as a SEPARATE top-level prim FixedJoint'd to wrist_3 + a runtime
  −110° "cup-align" hack (the tilt root). NVIDIA just parents the gripper to ee_link (no FixedJoint, no angle hack).
  => the tilt is a MOUNT-ARCHITECTURE artifact, not the gripper geometry. The clean fix = NVIDIA-style child mount
  (gripper visuals + SurfaceGripper/Suction_Joint under ee_link) + the pick goal orienting ee +X straight down.
- (We originally used the separate FixedJoint because "PhysX rejects a rigid body under an articulation link" — but
  NVIDIA's gripper children are VISUAL meshes + the SurfaceGripper/Suction_Joint handle gripping, so no separate
  rigid body is needed under ee_link. That's the route to a hack-free mount.)
