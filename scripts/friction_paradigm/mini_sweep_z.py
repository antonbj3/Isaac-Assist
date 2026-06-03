"""Mini-sweep on drop_target Z only — all other params locked.

Goal: determine empirically what drop_target Z is achievable without
fingertip-bin-wall collision. URDF says fingertip is panda_hand-116mm
but trajectory shows palm-cube_center=25mm — discrepancy, so test directly.

Locks params to best-known combo (from prior sweep):
- friction_mu=0.9, finger_stiffness=80000, cube_mass=0.2,
  vel_clamp=0.02, pre_grip_settle=1.5, joint_vel_scale=1.0, arm_kp_scale=1.0

Z values tested: 0.94, 0.92, 0.90, 0.88, 0.86, 0.84
- 0.94 = current default (cube_bottom ~80mm above bin_top)
- 0.84 = ~30mm above bin_floor (potentially in collision range)

3 runs per Z = 18 iter total.

Writes screenshots side+iso per iter for visual verification.
"""
import asyncio, json, sys, time, copy, re
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

from friction_paradigm import rl_tune_v2 as rl

LOCKED = {
    "pre_grip_settle": 1.5,
    "vel_clamp": 0.02,
    "curobo_pos_tol": 0.003,
    "friction_mu": 0.9,
    "finger_stiffness": 80000,
    "cube_mass": 0.2,
    "joint_vel_scale": 1.0,
    "arm_kp_scale": 1.0,
}

Z_VALUES = [0.94, 0.92, 0.90, 0.88, 0.86, 0.84]
RUNS_PER_Z = 3

TEMPLATE = REPO/"workspace/templates/CP-PRECISION-3CUBE.json"
ORIGINAL_TEMPLATE = TEMPLATE.read_text()


def set_drop_z(z: float):
    """Edit template drop_target Z value in place."""
    src = TEMPLATE.read_text()
    new = re.sub(r"drop_target=\[0\.2675,\s*-0\.3325,\s*[\d.]+\]",
                 f"drop_target=[0.2675, -0.3325, {z}]", src)
    TEMPLATE.write_text(new)


def restore_template():
    TEMPLATE.write_text(ORIGINAL_TEMPLATE)


async def main():
    out_dir = REPO/"workspace/friction_tuning/z_sweep" / time.strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    print(f"Z-sweep: {len(Z_VALUES)} values × {RUNS_PER_Z} runs = {len(Z_VALUES)*RUNS_PER_Z} iter")
    print(f"Out: {out_dir}")

    try:
        for z in Z_VALUES:
            set_drop_z(z)
            print(f"\n========= drop_target Z = {z} =========")
            for run in range(RUNS_PER_Z):
                iter_id = f"z{int(z*100):03d}_r{run+1}"
                iter_dir = out_dir / f"iter_{iter_id}"
                p = await rl.run_one_iter(iter_id, dict(LOCKED), iter_dir)
                if p is None:
                    print(f"  iter {iter_id}: FAILED (None returned)")
                    continue
                # Read additional details from raw
                raw = json.loads((iter_dir/"raw.jsonl").read_text())
                cube_final_z = raw["trajectory"][-1].get("cubes", {}).get("/World/Cube_M", [0,0,0])[2]
                drop_xy_mm = p["drop_xy_err_m"] * 1000
                row = {
                    "z": z, "run": run+1, "iter_id": iter_id,
                    "delivered": p.get("delivered", 0),
                    "drop_xy_mm": round(drop_xy_mm, 1),
                    "adj_disp_m": p.get("adj_disp_m", 0),
                    "col_count": p.get("col_count", 0),
                    "cube_final_z": round(cube_final_z, 3),
                    "iter_dir": str(iter_dir),
                }
                results.append(row)
                print(f"  iter {iter_id}: delivered={row['delivered']} drop_xy={row['drop_xy_mm']}mm col={row['col_count']} cube_final_z={row['cube_final_z']} adj={row['adj_disp_m']}")
        # Save summary
        (out_dir/"summary.json").write_text(json.dumps(results, indent=2))
        # Print aggregated
        print("\n========= AGGREGATE per Z =========")
        for z in Z_VALUES:
            zr = [r for r in results if r["z"] == z]
            if not zr: continue
            deliv = sum(r["delivered"] for r in zr)
            col_tot = sum(r["col_count"] for r in zr)
            drop_mean = sum(r["drop_xy_mm"] for r in zr) / len(zr)
            print(f"  Z={z}: delivered={deliv}/{len(zr)} drop_xy_mean={drop_mean:.0f}mm col_total={col_tot}")
    finally:
        restore_template()
        print("\nTemplate restored to original.")


if __name__ == "__main__":
    asyncio.run(main())
