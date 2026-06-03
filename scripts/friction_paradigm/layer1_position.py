"""Layer 1: POSITION-tuning för friction-paradigm.

ISOLATED test: cuRobo plan to grip-pose + PD-drive convergence. NO gripper-close.
Measure: |palm_z - target_z| after settle.

Goal: find params (pre_grip_settle + PD-gains) so palm konvergerar inom 1cm
av cube_top + FL i ≥95% av runs. Ingen friction-data värdefull innan detta.

Auto-iter: parameter grid → edit pick_place.py params → restart uvicorn →
run single pickup-test → measure → log → repeat.

Output: workspace/friction_tuning/layer1_position/<TS>/iter_*/
        + layer1_position_results.csv (master pivot-table)

Usage:
    # Single iter (visible/debugging):
    python scripts/friction_paradigm/layer1_position.py --once --pre-grip-settle 1.5
    # Grid auto-iter (auto-loop):
    python scripts/friction_paradigm/layer1_position.py --grid
"""
import argparse, asyncio, csv, json, os, re, signal, subprocess, sys, time, urllib.request
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

KIT_HEALTH = "http://127.0.0.1:8001/health"
UVI_HEALTH = "http://127.0.0.1:8000/health"
KIT_LAUNCH = "/home/anton/.claude/diag/launch_kit_headless.sh"
UVI_CMD = ["python", "-m", "uvicorn", "service.isaac_assist_service.main:app",
           "--host", "0.0.0.0", "--port", "8000"]

OUT_DIR = REPO/"workspace/friction_tuning/layer1_position"
MASTER_CSV = OUT_DIR/"layer1_position_results.csv"
PICK_PLACE_FILE = REPO/"service/isaac_assist_service/chat/tools/handlers/pick_place.py"

# Param-grid (Layer 1): position-related only. NO friction, NO finger-state.
PARAM_GRID = {
    "pre_grip_settle": [0.5, 0.8, 1.2, 1.8, 2.5, 3.5],
    # PD-drive arm-clamp (joint velocity-clamp affects convergence quality)
    "vel_clamp_rad_per_tick": [0.02, 0.04, 0.08, 0.15],
    # cuRobo position-tolerance affects plan-precision-vs-feasibility tradeoff
    "curobo_pos_tol": [0.001, 0.003, 0.005, 0.010],
}

# Minimal test scenario (defined here, not loaded from CP-template)
TEST_SCENE_CODE = """
import omni.usd
from pxr import UsdGeom, Sdf
from omni.isaac.core.utils.stage import create_new_stage
import asyncio

ctx = omni.usd.get_context()
ctx.new_stage()
stage = ctx.get_stage()
UsdGeom.Xform.Define(stage, '/World')
"""


def _http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200 and len(r.read()) > 0
    except: return False


def _pids_on(port):
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{port}"], stderr=subprocess.DEVNULL)
        return [int(p) for p in out.decode().split()]
    except subprocess.CalledProcessError:
        return []


def _kill(pids):
    for p in pids:
        try: os.kill(p, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass


def restart_uvicorn():
    _kill(_pids_on(8000))
    time.sleep(2)
    log = Path(f"/tmp/uvicorn_layer1_{time.strftime('%H%M%S')}.log")
    fd = log.open("ab")
    subprocess.Popen(UVI_CMD, cwd=str(REPO), stdout=fd, stderr=fd, start_new_session=True)
    for i in range(40):
        time.sleep(2)
        if _http_ok(UVI_HEALTH): return True
    return False


def restart_kit():
    _kill(_pids_on(8001))
    time.sleep(3)
    subprocess.Popen(["bash", KIT_LAUNCH], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for i in range(60):
        time.sleep(5)
        if _http_ok(KIT_HEALTH): return True
    return False


def apply_param_edits(params):
    """Edit pick_place.py to set Layer-1 params. Returns dict of (old, new) per param."""
    src = PICK_PLACE_FILE.read_text()
    deltas = {}

    # pre_grip_settle (0.8 → param value)
    if "pre_grip_settle" in params:
        new_val = params["pre_grip_settle"]
        old = re.search(r"pre_grip_settle = 0\.8 if _is_grip_seg else 0\.0", src)
        if old:
            new = f"pre_grip_settle = {new_val} if _is_grip_seg else 0.0"
            src = src.replace(old.group(0), new)
            deltas["pre_grip_settle"] = (0.8, new_val)

    # vel_clamp_rad_per_tick (0.04 default)
    if "vel_clamp_rad_per_tick" in params:
        new_val = params["vel_clamp_rad_per_tick"]
        old = re.search(r"_max_delta = 0\.04  # rad per tick", src)
        if old:
            new = f"_max_delta = {new_val}  # rad per tick (layer1 tuned)"
            src = src.replace(old.group(0), new)
            deltas["vel_clamp"] = (0.04, new_val)

    # curobo_pos_tol (default 0.003 in MotionPlannerCfg)
    if "curobo_pos_tol" in params:
        new_val = params["curobo_pos_tol"]
        old = re.search(r"position_tolerance=0\.003,", src)
        if old:
            new = f"position_tolerance={new_val},  # layer1 tuned"
            src = src.replace(old.group(0), new)
            deltas["curobo_pos_tol"] = (0.003, new_val)

    PICK_PLACE_FILE.write_text(src)
    return deltas


def revert_param_edits():
    """Revert Layer-1 param edits back to defaults."""
    src = PICK_PLACE_FILE.read_text()
    src = re.sub(r"pre_grip_settle = [\d.]+ if _is_grip_seg else 0\.0",
                 "pre_grip_settle = 0.8 if _is_grip_seg else 0.0", src)
    src = re.sub(r"_max_delta = [\d.]+  # rad per tick.*",
                 "_max_delta = 0.04  # rad per tick", src)
    src = re.sub(r"position_tolerance=[\d.]+,.*",
                 "position_tolerance=0.003,", src)
    PICK_PLACE_FILE.write_text(src)


def build_minimal_scene_and_test():
    """Use CP-13 (single-cube, simple Franka pickup) as Layer-1 test-scene.
    Run normal observe_one, but ONLY measure palm-position metrics — ignore
    grip success, gates, etc. We want position-convergence-distribution.
    """
    import importlib
    swp = importlib.import_module("review.sweep_all_rewritten")
    return asyncio.run(swp.observe_one("CP-13"))


def extract_position_metrics(rec):
    """Per-tick ee/cube positions are in trajectory; compute palm-cube-distance
    over the GRIP-WINDOW (when controller is in 'executing' phase + grip-seg).
    Returns: {n_grips_observed, min_dist, mean_dist, max_dist, success (dist<1cm)}.
    """
    metrics = {
        "n_ticks_sampled": 0,
        "palm_cube_dist_min": None,
        "palm_cube_dist_mean": None,
        "palm_cube_dist_max": None,
        "palm_cube_dist_at_min": None,
        "grip_segs_reached": 0,
        "below_1cm_ratio": 0.0,
        "below_2cm_ratio": 0.0,
    }
    if rec.get("exception"):
        metrics["exception"] = rec["exception"]
        return metrics
    ed = rec.get("engine_data") or {}
    traj = ed.get("trajectory") or []
    if not traj: return metrics
    dists = []
    primary_cube = ed.get("primary_cube")
    for tick in traj:
        ee = tick.get("ee")
        cubes = tick.get("cubes") or {}
        if not ee or not primary_cube: continue
        cp = cubes.get(primary_cube)
        if not cp: continue
        # Distance from EE-z to cube_z + FL (palm-to-cube-top target)
        # Plus xy alignment
        FL = 0.105
        target_z = cp[2] + FL
        dz = abs(ee[2] - target_z)
        dxy = ((ee[0]-cp[0])**2 + (ee[1]-cp[1])**2) ** 0.5
        d3 = (dz**2 + dxy**2) ** 0.5
        dists.append((d3, dxy, dz))
    if not dists: return metrics
    d3_vals = [d[0] for d in dists]
    metrics["n_ticks_sampled"] = len(d3_vals)
    metrics["palm_cube_dist_min"] = round(min(d3_vals), 4)
    metrics["palm_cube_dist_mean"] = round(sum(d3_vals)/len(d3_vals), 4)
    metrics["palm_cube_dist_max"] = round(max(d3_vals), 4)
    metrics["below_1cm_ratio"] = round(sum(1 for d in d3_vals if d < 0.01) / len(d3_vals), 3)
    metrics["below_2cm_ratio"] = round(sum(1 for d in d3_vals if d < 0.02) / len(d3_vals), 3)
    return metrics


def run_single_iter(iter_id, params, iter_dir):
    """One iter: edit params, restart uvicorn, run test, capture metrics, save."""
    iter_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Iter {iter_id} : params={params} ===", flush=True)
    deltas = apply_param_edits(params)
    print(f"  deltas: {deltas}", flush=True)

    # Snapshot code-state
    try:
        diff = subprocess.check_output(["git", "diff", "HEAD", str(PICK_PLACE_FILE)], cwd=str(REPO))
        (iter_dir/"code_state.patch").write_bytes(diff)
    except Exception as e:
        print(f"  snapshot fail: {e}")

    # Restart uvicorn (Kit stays — single-tenant)
    if not restart_uvicorn():
        print("  uvicorn restart FAILED — skip iter")
        return None

    # Run minimal test
    t0 = time.time()
    try:
        rec = build_minimal_scene_and_test()
    except Exception as e:
        print(f"  test CRASH: {e}")
        return None
    elapsed = round(time.time() - t0, 1)

    # Save raw result
    with (iter_dir/"raw.jsonl").open("w") as f:
        f.write(json.dumps(rec, default=str)+"\n")

    # Extract Layer-1 position-metrics
    metrics = extract_position_metrics(rec)
    metrics["iter_id"] = iter_id
    metrics["params"] = params
    metrics["elapsed_s"] = elapsed
    metrics["honest_pass"] = rec.get("honest_pass")

    (iter_dir/"metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"  metrics: min={metrics['palm_cube_dist_min']}m, "
          f"mean={metrics['palm_cube_dist_mean']}m, "
          f"max={metrics['palm_cube_dist_max']}m, "
          f"below_1cm={metrics['below_1cm_ratio']}, "
          f"below_2cm={metrics['below_2cm_ratio']} ({elapsed}s)", flush=True)
    return metrics


def append_master_csv(metrics):
    """Append row to master CSV for pivoting."""
    is_new = not MASTER_CSV.exists()
    fields = ["iter_id", "timestamp", "pre_grip_settle", "vel_clamp", "curobo_pos_tol",
              "n_ticks_sampled", "palm_cube_dist_min", "palm_cube_dist_mean",
              "palm_cube_dist_max", "below_1cm_ratio", "below_2cm_ratio",
              "honest_pass", "exception", "elapsed_s"]
    with MASTER_CSV.open("a") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if is_new: w.writeheader()
        row = {
            "iter_id": metrics["iter_id"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pre_grip_settle": metrics["params"].get("pre_grip_settle", ""),
            "vel_clamp": metrics["params"].get("vel_clamp_rad_per_tick", ""),
            "curobo_pos_tol": metrics["params"].get("curobo_pos_tol", ""),
            "n_ticks_sampled": metrics.get("n_ticks_sampled", 0),
            "palm_cube_dist_min": metrics.get("palm_cube_dist_min"),
            "palm_cube_dist_mean": metrics.get("palm_cube_dist_mean"),
            "palm_cube_dist_max": metrics.get("palm_cube_dist_max"),
            "below_1cm_ratio": metrics.get("below_1cm_ratio"),
            "below_2cm_ratio": metrics.get("below_2cm_ratio"),
            "honest_pass": metrics.get("honest_pass"),
            "exception": metrics.get("exception", ""),
            "elapsed_s": metrics.get("elapsed_s"),
        }
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Single iter with specified params")
    ap.add_argument("--grid", action="store_true", help="Auto-iter over full grid")
    ap.add_argument("--pre-grip-settle", type=float, default=None)
    ap.add_argument("--vel-clamp", type=float, default=None)
    ap.add_argument("--curobo-pos-tol", type=float, default=None)
    ap.add_argument("--revert", action="store_true", help="Revert all Layer-1 edits to defaults")
    args = ap.parse_args()

    if args.revert:
        revert_param_edits()
        print("Layer-1 edits reverted to defaults.")
        return

    if not (args.once or args.grid):
        print("Specify --once or --grid"); sys.exit(1)

    # Ensure Kit alive (single-tenant, don't restart if running)
    if not _http_ok(KIT_HEALTH):
        print("Kit not alive — restarting...")
        if not restart_kit():
            sys.exit("Kit restart failed; abort")

    run_dir = OUT_DIR/f"run_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run dir: {run_dir}")

    try:
        if args.once:
            params = {}
            if args.pre_grip_settle is not None: params["pre_grip_settle"] = args.pre_grip_settle
            if args.vel_clamp is not None: params["vel_clamp_rad_per_tick"] = args.vel_clamp
            if args.curobo_pos_tol is not None: params["curobo_pos_tol"] = args.curobo_pos_tol
            metrics = run_single_iter("once", params, run_dir/"iter_once")
            if metrics: append_master_csv(metrics)
        elif args.grid:
            # Full grid: cartesian product
            from itertools import product
            keys = list(PARAM_GRID.keys())
            values = [PARAM_GRID[k] for k in keys]
            total = 1
            for v in values: total *= len(v)
            print(f"Full grid: {total} iter total")
            n = 0
            for combo in product(*values):
                n += 1
                params = dict(zip(keys, combo))
                iter_dir = run_dir/f"iter_{n:04d}"
                metrics = run_single_iter(f"{n:04d}", params, iter_dir)
                if metrics: append_master_csv(metrics)
            print(f"\nDONE: {n} iters complete")
    finally:
        revert_param_edits()
        print("Layer-1 params reverted to defaults at end.")


if __name__ == "__main__":
    main()
