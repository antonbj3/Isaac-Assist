"""Lock best-known rubber-params + run 50 iter deterministic.
Path: snabbaste vägen till 100% inside_bin på rubber.
"""
import asyncio, sys, time
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

# Override PARAM_GRID with single best-known config
from friction_paradigm import rl_tune_v2 as rl

BEST_RUBBER = {
    "pre_grip_settle": 0.8,
    "vel_clamp": 0.08,
    "curobo_pos_tol": 0.003,
    "friction_mu": 0.6,         # rubber-range
    "finger_stiffness": 500000,  # high stiffness
    "cube_mass": 0.2,
    "joint_vel_scale": 2.0,
    "arm_kp_scale": 1.0,
}

# Patch grid to lock single combo
rl.PARAM_GRID = {k: [v] for k, v in BEST_RUBBER.items()}

# Run 50 iter
import argparse
sys.argv = ["lock", "--max-hours", "5", "--random"]
asyncio.run(rl.main())
