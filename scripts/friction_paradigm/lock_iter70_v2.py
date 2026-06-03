"""Lock iter 70 params + run 10 iter — bypasses main() to avoid MAT_MU override."""
import asyncio, sys, json, time, csv
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
N_ITER = 10


async def main():
    out_dir = REPO/"workspace/friction_tuning/lock_iter70" / time.strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "results.csv"
    fields = ["iter_id"] + list(LOCKED.keys()) + ["adj_disp_m", "drop_xy_err_m", "grip_pos_error_m", "delivered", "reward_full"]
    with csv_path.open("w", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writeheader()

    if not rl.kit_alive():
        if not await rl.launch_kit():
            print("Kit launch FAIL"); return

    reward_count = 0
    for n in range(1, N_ITER+1):
        iter_dir = out_dir / f"iter_{n:04d}"
        iter_id = f"{n:04d}"
        p = await rl.run_one_iter(iter_id, dict(LOCKED), iter_dir)
        if p is None:
            print(f"iter {iter_id}: FAILED")
            continue
        row = {"iter_id": iter_id, **LOCKED, **{k: p.get(k) for k in ["adj_disp_m","drop_xy_err_m","grip_pos_error_m","delivered","reward_full"]}}
        with csv_path.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=fields).writerow(row)
        if p.get("reward_full"): reward_count += 1
        print(f"iter {iter_id}: deliv={p.get('delivered')} reward={p.get('reward_full')} adj={p['adj_disp_m']*1000:.1f}mm drop={p['drop_xy_err_m']*1000:.1f}mm")

    print(f"\nFINAL: {reward_count}/{N_ITER} reward_full with locked iter 70 params")
    print(f"Results: {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
