"""Live progress monitor för rl_tune_3cube auto-grid.

Usage:
    python scripts/friction_paradigm/rl_progress.py [--watch]

Shows:
- Iter count (X/48)
- Best total_penalty so far + best params
- Recent iter trend
- Detector aggregates
"""
import argparse, csv, json, time
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
RUN_BASE = REPO/"workspace/friction_tuning/rl_paradigm"


def find_latest_run():
    runs = sorted(RUN_BASE.glob("run_*"))
    return runs[-1] if runs else None


def show_progress():
    run = find_latest_run()
    if not run:
        print("No runs found yet")
        return
    print(f"\n=== Run: {run.name} ===")
    csv_path = run/"rl_tune_results.csv"
    best_path = run/"best_params.json"
    if not csv_path.exists():
        print("No iter completed yet")
        return
    rows = list(csv.DictReader(csv_path.open()))
    n = len(rows)
    print(f"Iter: {n}/48 ({100*n/48:.0f}%)")
    if best_path.exists():
        best = json.loads(best_path.read_text())
        print(f"\nBEST so far (iter {best['iter_id']}):")
        print(f"  Total penalty: {best['total_penalty']}")
        print(f"  Params: {best['params']}")
        print(f"  Components: adj_disp={best['adj_disp_m']}m, drop_xy_err={best['drop_xy_err_m']}m, "
              f"z_err_floor={best['z_err_floor_m']}m")
        print(f"  Delivered: {best['delivered']}, In bin: {best['inside_bin']}, "
              f"On floor: {best['cube_on_floor']}, Reward_full: {best['reward_full']}")
    print(f"\nRecent 5 iters:")
    for row in rows[-5:]:
        print(f"  {row['iter_id']}: total={row['total_penalty']} "
              f"pre_grip={row['pre_grip_settle']} vel={row['vel_clamp']} pos_tol={row['curobo_pos_tol']} "
              f"deliv={row['delivered']} ({row['elapsed_s']}s)")
    print(f"\nAggregates:")
    delivered_count = sum(1 for r in rows if r['delivered'] == '1')
    reward_full_count = sum(1 for r in rows if r.get('reward_full') == '1')
    in_bin_count = sum(1 for r in rows if r.get('inside_bin') == '1')
    on_floor_count = sum(1 for r in rows if r.get('cube_on_floor') == '1')
    print(f"  Delivered: {delivered_count}/{n}")
    print(f"  Inside bin: {in_bin_count}/{n}")
    print(f"  On floor: {on_floor_count}/{n}")
    print(f"  Reward_full: {reward_full_count}/{n}")
    if rows:
        penalties = sorted([float(r['total_penalty']) for r in rows if r.get('total_penalty')])
        print(f"  Penalty range: {penalties[0]} (best) - {penalties[-1]} (worst)")
        if len(penalties) > 5:
            print(f"  Median penalty: {penalties[len(penalties)//2]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="Refresh every 30s")
    args = ap.parse_args()

    if args.watch:
        try:
            while True:
                import os
                os.system("clear")
                show_progress()
                time.sleep(30)
        except KeyboardInterrupt:
            print("\nStopped")
    else:
        show_progress()


if __name__ == "__main__":
    main()
