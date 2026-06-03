"""Lock iter 70 (best reward_full) params + run 10 iter to verify reproducibility.

iter 70: mu=1.2 stiff=500000 mass=0.1 vel=0.04 settle=0.8 jv=0.5 arm_kp=1.0 tol=0.003
→ adj=0.1mm drop=0.2mm reward_full=1 (best ever)

If 5+/10 hit reward_full: iter 70's params are reproducible.
If <3/10: was stochastic luck — drop and try iter 68 (mu=0.9) instead.
"""
import asyncio, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))
from friction_paradigm import rl_tune_v2 as rl

LOCKED = {
    "pre_grip_settle": 0.8,
    "vel_clamp": 0.04,
    "curobo_pos_tol": 0.003,
    "friction_mu": 1.2,
    "finger_stiffness": 500000,
    "cube_mass": 0.1,
    "joint_vel_scale": 0.5,
    "arm_kp_scale": 1.0,
}
rl.PARAM_GRID = {k: [v] for k, v in LOCKED.items()}
sys.argv = ["lock_iter70", "--max-hours", "1", "--random", "--material", "rubber"]
asyncio.run(rl.main())
