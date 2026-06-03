"""RL-paradigm precision tuning för CP-PRECISION-3CUBE.

Penalty signals:
  - adjacent_cube_displacement_m: sum |Cube_L XY shift| + |Cube_R XY shift| (target 0)
  - collision_events_non_middle: contact-events involving Cube_L/Cube_R (target 0)
  - drop_precision_error_m: |Cube_M final XY - bin_center XY| (target <0.005)
  - delivered: did Cube_M end up in bin (0 or 1)

Total penalty = adj_disp + col_evts * 0.05 + drop_err + (1-delivered) * 1.0

Auto-iter param-grid:
  - pre_grip_settle: [0.8, 1.5, 2.5, 4.0]
  - vel_clamp: [0.02, 0.04, 0.08, 0.15]
  - curobo_pos_tol: [0.001, 0.003, 0.005]

Per iter: edit pick_place.py → restart uvicorn (Kit single-tenant restart if crashes) →
observe_one(CP-PRECISION-3CUBE) → compute penalty → log → restore params → next iter.

Output:
  workspace/friction_tuning/rl_paradigm/run_<TS>/
    iter_<N>/
      params.json
      raw.jsonl (full observe_one record)
      metrics.json (penalty values + decomposition)
    rl_tune_results.csv (master pivot-table)
    best_params.json (running-best post-each-iter)
"""
import argparse, asyncio, csv, json, os, re, signal, subprocess, sys, time, urllib.request
from itertools import product
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

KIT_HEALTH = "http://127.0.0.1:8001/health"
UVI_HEALTH = "http://127.0.0.1:8000/health"
KIT_LAUNCH_HEADLESS = "/home/anton/.claude/diag/launch_kit_headless.sh"
UVI_CMD = ["python", "-m", "uvicorn", "service.isaac_assist_service.main:app",
           "--host", "0.0.0.0", "--port", "8000"]
PICK_PLACE_FILE = REPO/"service/isaac_assist_service/chat/tools/handlers/pick_place.py"

OUT_BASE = REPO/"workspace/friction_tuning/rl_paradigm"

# Cube initial positions (must match CP-PRECISION-3CUBE template)
CUBE_L_INIT_XY = (-0.3505, 0.30)
CUBE_R_INIT_XY = (-0.2495, 0.30)
CUBE_M_INIT_XY = (-0.30, 0.30)
BIN_CENTER_XY = (0.30, -0.30)
# Anton's reward: cube in CONTACT with bin-floor (settled on bottom, not mid-air)
# Bin corner-position z=0.75, wall_thickness=0.005 → bin-floor-top-z = 0.755
# Cube_half = 0.025 → cube-at-rest-z when sitting on bin-floor = 0.755 + 0.025 = 0.78
BIN_FLOOR_TOP_Z = 0.755
CUBE_HALF = 0.025
CUBE_AT_REST_Z = BIN_FLOOR_TOP_Z + CUBE_HALF  # 0.78m
# Inner bin half-extent (XY): outer 7cm - 2*wall(5mm) = 6cm inner → half = 3cm
BIN_INNER_HALF_XY = 0.03

PARAM_GRID = {
    "pre_grip_settle": [0.8, 1.5, 2.5, 4.0],
    "vel_clamp": [0.02, 0.04, 0.08, 0.15],
    "curobo_pos_tol": [0.001, 0.003, 0.005],
}


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
    _kill(_pids_on(8000)); time.sleep(2)
    log = Path(f"/tmp/uvi_rl_{time.strftime('%H%M%S')}.log")
    fd = log.open("ab")
    subprocess.Popen(UVI_CMD, cwd=str(REPO), stdout=fd, stderr=fd, start_new_session=True)
    for i in range(40):
        time.sleep(2)
        if _http_ok(UVI_HEALTH): return True
    return False


def restart_kit_headless():
    _kill(_pids_on(8001)); time.sleep(3)
    subprocess.Popen(["bash", KIT_LAUNCH_HEADLESS], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for i in range(60):
        time.sleep(5)
        if _http_ok(KIT_HEALTH): return True
    return False


def apply_param_edits(params):
    src = PICK_PLACE_FILE.read_text()
    if "pre_grip_settle" in params:
        v = params["pre_grip_settle"]
        src = re.sub(r"pre_grip_settle = [\d.]+ if _is_grip_seg else 0\.0",
                     f"pre_grip_settle = {v} if _is_grip_seg else 0.0", src)
    if "vel_clamp" in params:
        v = params["vel_clamp"]
        src = re.sub(r"_max_delta = [\d.]+  # rad per tick.*",
                     f"_max_delta = {v}  # rad per tick (rl_tune)", src)
    if "curobo_pos_tol" in params:
        v = params["curobo_pos_tol"]
        src = re.sub(r"position_tolerance=[\d.]+,.*",
                     f"position_tolerance={v},  # rl_tune", src)
    PICK_PLACE_FILE.write_text(src)


def revert_params():
    src = PICK_PLACE_FILE.read_text()
    src = re.sub(r"pre_grip_settle = [\d.]+ if _is_grip_seg else 0\.0",
                 "pre_grip_settle = 0.8 if _is_grip_seg else 0.0", src)
    src = re.sub(r"_max_delta = [\d.]+  # rad per tick.*",
                 "_max_delta = 0.04  # rad per tick", src)
    src = re.sub(r"position_tolerance=[\d.]+,.*",
                 "position_tolerance=0.003,", src)
    PICK_PLACE_FILE.write_text(src)


def compute_penalty(rec):
    """Extract 3-cube precision penalty from observe_one record.

    Antons reward (2026-05-22): cube i KONTAKT med bin-floor (settled).
    Penalty breakdown:
      - adj_disp: shift on Cube_L + Cube_R (target 0)
      - drop_xy_err: |Cube_M final XY - bin_center| (target <0.005)
      - cube_on_floor: Cube_M_final_z within +-5mm av CUBE_AT_REST_Z (settled, ej mid-air)
      - inside_bin: Cube_M_xy within bin_inner_half_xy of bin_center
      - reward_full: ALL 4 satisfied (delivered + settled + in-bin + sides-unmoved)
    """
    cs = (rec.get("engine_data") or {}).get("cube_supports") or {}
    cm = cs.get("/World/Cube_M") or {}
    cl = cs.get("/World/Cube_L") or {}
    cr = cs.get("/World/Cube_R") or {}

    def _xy_dist(p, init):
        if not p or len(p) < 2: return None
        return ((p[0]-init[0])**2 + (p[1]-init[1])**2) ** 0.5

    fp_l = cl.get("final_pos")
    fp_r = cr.get("final_pos")
    fp_m = cm.get("final_pos")

    disp_l = _xy_dist(fp_l, CUBE_L_INIT_XY) or 0.0
    disp_r = _xy_dist(fp_r, CUBE_R_INIT_XY) or 0.0
    adj_disp = disp_l + disp_r

    # Drop precision XY
    drop_xy_err = 1.0
    inside_bin = 0
    if fp_m and len(fp_m) >= 2:
        drop_xy_err = ((fp_m[0]-BIN_CENTER_XY[0])**2 + (fp_m[1]-BIN_CENTER_XY[1])**2) ** 0.5
        if abs(fp_m[0]-BIN_CENTER_XY[0]) < BIN_INNER_HALF_XY and abs(fp_m[1]-BIN_CENTER_XY[1]) < BIN_INNER_HALF_XY:
            inside_bin = 1

    # Settled on bin-floor (Antons spec: cube i kontakt med nedre änden)
    cube_on_floor = 0
    z_err_floor = 1.0
    if fp_m and len(fp_m) >= 3:
        z_err_floor = abs(fp_m[2] - CUBE_AT_REST_Z)
        if z_err_floor < 0.005:  # 5mm Z-tolerance
            cube_on_floor = 1

    # FULL reward: ALL 4 conditions
    reward_full = (adj_disp < 0.001) and inside_bin and cube_on_floor and drop_xy_err < 0.005

    # Antons spec 2026-05-22: fånga DIRECT + INDIRECT kollisioner med adjacent cubes
    # DIRECT: gripper-finger eller robot-link rör Cube_L/Cube_R
    # INDIRECT: Cube_M (held) rör Cube_L/Cube_R under transit
    # Parse contact_events från engine_data (har prim_a/prim_b efter agent-1 fix)
    col_direct = 0  # gripper/robot-link vs side-cube
    col_indirect = 0  # held cube vs side-cube
    contact_evts_raw = ((rec.get("engine_data") or {}).get("contact_events_sample") or [])
    SIDE_CUBE_PATHS = {"/World/Cube_L", "/World/Cube_R"}
    for ce in contact_evts_raw:
        pa = ce.get("prim_a") or ""
        pb = ce.get("prim_b") or ""
        # Normalize: which side is which
        if pa in SIDE_CUBE_PATHS:
            other = pb
        elif pb in SIDE_CUBE_PATHS:
            other = pa
        else:
            continue  # not a side-cube contact
        # Classify other:
        if other == "/World/Cube_M":
            col_indirect += 1
        elif ("finger" in other.lower() or "panda" in other.lower() or "franka" in other.lower()
              or "ee_link" in other.lower() or "tool0" in other.lower() or "hand" in other.lower()):
            col_direct += 1
    col_count = col_direct + col_indirect

    # Penalty: lägre = bättre. Scale-balanced så ingen komponent dominerar.
    # Each component normalized to ~0-1 range:
    #   adj_disp: 0-5cm typical → *20 = 0-1
    #   drop_xy_err: 0-30cm typical → *3 = 0-1
    #   z_err_floor: 0-15cm typical → *7 = ~0-1
    #   col_count: 0-100 cap-saturating via 1-exp(-n/5) → 0-1
    #   not reward_full: binary 0/1
    import math
    col_normalized = 1.0 - math.exp(-col_count / 5.0) if col_count > 0 else 0.0
    total = (adj_disp * 20 +       # 0-1 typical
             drop_xy_err * 3 +     # 0-1 typical
             z_err_floor * 7 +     # 0-1 typical
             col_normalized +      # 0-1 (saturating)
             (1.0 if not reward_full else 0))  # binary "all OK" bonus

    return {
        "adj_disp_m": round(adj_disp, 4),
        "disp_l_m": round(disp_l, 4),
        "disp_r_m": round(disp_r, 4),
        "drop_xy_err_m": round(drop_xy_err, 4),
        "z_err_floor_m": round(z_err_floor, 4),
        "inside_bin": inside_bin,
        "cube_on_floor": cube_on_floor,
        "reward_full": int(reward_full),
        "col_count": col_count,
        "delivered": int(cm.get("under_target", False)),  # legacy
        "total_penalty": round(total, 4),
    }


async def run_one_iter(iter_id, params, iter_dir):
    iter_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Iter {iter_id}: {params}", flush=True)
    apply_param_edits(params)

    # Save snapshot
    try:
        diff = subprocess.check_output(["git", "diff", "HEAD", str(PICK_PLACE_FILE)], cwd=str(REPO))
        (iter_dir/"code_state.patch").write_bytes(diff)
    except: pass

    if not restart_uvicorn():
        print("  uvicorn restart FAILED — skip iter"); return None

    # Kit alive check
    if not _http_ok(KIT_HEALTH):
        print("  Kit down — restart headless...")
        if not restart_kit_headless():
            print("  Kit restart FAILED — skip iter"); return None

    # Run observe_one
    t0 = time.time()
    try:
        from review.sweep_all_rewritten import observe_one
        rec = await observe_one("CP-PRECISION-3CUBE")
    except Exception as e:
        print(f"  observe CRASH: {e}"); return None
    elapsed = round(time.time() - t0, 1)

    with (iter_dir/"raw.jsonl").open("w") as f:
        f.write(json.dumps(rec, default=str)+"\n")

    penalty = compute_penalty(rec)
    penalty["iter_id"] = iter_id
    penalty["params"] = params
    penalty["elapsed_s"] = elapsed
    penalty["honest_pass"] = rec.get("honest_pass", False)
    penalty["exception"] = rec.get("exception", "")

    (iter_dir/"metrics.json").write_text(json.dumps(penalty, indent=2))
    print(f"  PENALTY: total={penalty['total_penalty']} adj={penalty['adj_disp_m']} "
          f"drop_xy={penalty['drop_xy_err_m']} z_floor={penalty['z_err_floor_m']} "
          f"col={penalty['col_count']} deliv={penalty['delivered']} reward={penalty['reward_full']} ({elapsed}s)", flush=True)
    return penalty


def append_master_csv(csv_path, penalty):
    is_new = not csv_path.exists()
    fields = ["iter_id", "timestamp", "pre_grip_settle", "vel_clamp", "curobo_pos_tol",
              "adj_disp_m", "disp_l_m", "disp_r_m", "drop_xy_err_m", "z_err_floor_m",
              "inside_bin", "cube_on_floor", "reward_full", "col_count",
              "delivered", "total_penalty", "honest_pass", "exception", "elapsed_s"]
    with csv_path.open("a") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if is_new: w.writeheader()
        row = {
            "iter_id": penalty["iter_id"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pre_grip_settle": penalty["params"].get("pre_grip_settle", ""),
            "vel_clamp": penalty["params"].get("vel_clamp", ""),
            "curobo_pos_tol": penalty["params"].get("curobo_pos_tol", ""),
            "adj_disp_m": penalty["adj_disp_m"],
            "disp_l_m": penalty["disp_l_m"],
            "disp_r_m": penalty["disp_r_m"],
            "drop_xy_err_m": penalty["drop_xy_err_m"],
            "z_err_floor_m": penalty["z_err_floor_m"],
            "inside_bin": penalty["inside_bin"],
            "cube_on_floor": penalty["cube_on_floor"],
            "reward_full": penalty["reward_full"],
            "col_count": penalty["col_count"],
            "delivered": penalty["delivered"],
            "total_penalty": penalty["total_penalty"],
            "honest_pass": penalty["honest_pass"],
            "exception": penalty["exception"],
            "elapsed_s": penalty["elapsed_s"],
        }
        w.writerow(row)


def update_best(best_path, penalty):
    """Update running-best params."""
    best = {}
    if best_path.exists():
        best = json.loads(best_path.read_text())
    if not best or penalty["total_penalty"] < best.get("total_penalty", 1e9):
        best = {**penalty}
        best_path.write_text(json.dumps(best, indent=2))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true", help="Full grid auto-iter")
    ap.add_argument("--once", action="store_true", help="Single iter (specify params)")
    ap.add_argument("--pre-grip-settle", type=float, default=None)
    ap.add_argument("--vel-clamp", type=float, default=None)
    ap.add_argument("--curobo-pos-tol", type=float, default=None)
    ap.add_argument("--max-iters", type=int, default=10000, help="Cap total iters (för 3-day budget)")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.revert:
        revert_params(); print("Params reverted"); return

    if not (args.once or args.grid):
        print("Specify --once or --grid"); sys.exit(1)

    run_dir = OUT_BASE/f"run_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir/"rl_tune_results.csv"
    best_path = run_dir/"best_params.json"

    print(f"Run dir: {run_dir}")
    print(f"Master CSV: {csv_path}")
    print(f"Best params: {best_path}")

    try:
        if args.once:
            params = {}
            if args.pre_grip_settle is not None: params["pre_grip_settle"] = args.pre_grip_settle
            if args.vel_clamp is not None: params["vel_clamp"] = args.vel_clamp
            if args.curobo_pos_tol is not None: params["curobo_pos_tol"] = args.curobo_pos_tol
            p = await run_one_iter("once", params, run_dir/"iter_once")
            if p:
                append_master_csv(csv_path, p)
                update_best(best_path, p)
        elif args.grid:
            keys = list(PARAM_GRID.keys())
            values = [PARAM_GRID[k] for k in keys]
            total = 1
            for v in values: total *= len(v)
            cap = min(total, args.max_iters)
            print(f"Grid: {total} combos (cap {cap})")
            n = 0
            for combo in product(*values):
                n += 1
                if n > cap: break
                params = dict(zip(keys, combo))
                iter_dir = run_dir/f"iter_{n:04d}"
                p = await run_one_iter(f"{n:04d}", params, iter_dir)
                if p:
                    append_master_csv(csv_path, p)
                    update_best(best_path, p)
                # Print running best every 5 iter
                if n % 5 == 0 and best_path.exists():
                    best = json.loads(best_path.read_text())
                    print(f"  >>> running best: total={best['total_penalty']} params={best['params']}", flush=True)
            print(f"\nDONE: {n} iters")
            if best_path.exists():
                best = json.loads(best_path.read_text())
                print(f"FINAL BEST: {best}")
    finally:
        revert_params()
        print("Params reverted to defaults.")


if __name__ == "__main__":
    asyncio.run(main())
