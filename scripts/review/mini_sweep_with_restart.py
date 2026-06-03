"""Mini sweep: restart Kit + uvicorn fresh, then run scene_observer against
a curated 8-template representative subset. ~20-30 min vs ~3h for full sweep.

Templates chosen för coverage:
  CP-09  — Franka multi-cube baseline (consistent HONEST_PASS)
  CP-13  — telepati-test (PD-conv-gate-impact)
  CP-24  — multi-cube telepati
  CP-31  — R1-yes regression-test
  CP-NEW-brick-stacking  — stacking (high VE-triggers)
  CP-69  — UR10 surface_gripper-test
  CP-NEW-conveyor-tracking-moving-pick — belt-drift sensor-trigger-test
  CP-05  — FlipWall reorient + missing_scene_element-detector-test

Per iter: code-state-snapshot saved via /tmp/mini_sweep_code_state_<TS>.patch
"""
import asyncio, json, os, sys, signal, subprocess, time, urllib.request
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

KIT_HEALTH = "http://127.0.0.1:8001/health"
UVI_HEALTH = "http://127.0.0.1:8000/health"
KIT_LAUNCH = "/home/anton/.claude/diag/launch_kit_headless.sh"
UVI_CMD = ["python", "-m", "uvicorn", "service.isaac_assist_service.main:app",
           "--host", "0.0.0.0", "--port", "8000"]

MINI_TEMPLATES = [
    "CP-09", "CP-13", "CP-24", "CP-31",
    "CP-NEW-brick-stacking", "CP-69",
    "CP-NEW-conveyor-tracking-moving-pick", "CP-05",
]

TS = time.strftime("%Y%m%d_%H%M%S")
OUT_JSONL = REPO/f"workspace/qa_runs/scene_observer_mini_{TS}.jsonl"
LOG = Path(f"/tmp/mini_sweep_{TS}.log")
UVI_LOG = Path(f"/tmp/uvicorn_mini_{TS}.log")
LOCK = Path("/tmp/mini_sweep_active.pid")
CODE_PATCH = REPO/f"workspace/qa_runs/code_state_mini_{TS}.patch"


def _check_no_other_sweep():
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().strip())
            os.kill(pid, 0)
            sys.exit(f"ABORT: mini-sweep already running (PID {pid}). "
                     f"Kill or remove {LOCK} if stale.")
        except (ProcessLookupError, ValueError):
            pass
    LOCK.write_text(str(os.getpid()))


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
        except ProcessLookupError: pass


def restart_uvicorn():
    print("Restarting uvicorn...", flush=True)
    _kill(_pids_on(8000))
    time.sleep(2)
    UVI_LOG.touch()
    fd = UVI_LOG.open("ab")
    subprocess.Popen(UVI_CMD, cwd=str(REPO), stdout=fd, stderr=fd, start_new_session=True)
    for i in range(40):
        time.sleep(2)
        if _http_ok(UVI_HEALTH):
            print(f"  uvicorn up at {(i+1)*2}s", flush=True); return True
    print("  uvicorn TIMEOUT 80s"); return False


def restart_kit():
    print("Restarting Kit (headless)...", flush=True)
    _kill(_pids_on(8001))
    time.sleep(3)
    subprocess.Popen(["bash", KIT_LAUNCH], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for i in range(60):
        time.sleep(5)
        if _http_ok(KIT_HEALTH):
            print(f"  Kit up at {(i+1)*5}s", flush=True); return True
    print("  Kit TIMEOUT 5min"); return False


def save_code_snapshot():
    try:
        out = subprocess.check_output(["git", "diff", "HEAD"], cwd=str(REPO))
        CODE_PATCH.write_bytes(out)
        n_lines = len(out.decode().split('\n'))
        print(f"Code-state snapshot saved: {CODE_PATCH.name} ({n_lines} lines)", flush=True)
    except Exception as e:
        print(f"snapshot failed: {e}", flush=True)


async def main():
    _check_no_other_sweep()
    try:
        await _main_inner()
    finally:
        try: LOCK.unlink()
        except FileNotFoundError: pass


async def _main_inner():
    save_code_snapshot()
    if not restart_uvicorn():
        sys.exit("uvicorn-restart failed; abort")
    if not restart_kit():
        sys.exit("Kit-restart failed; abort")

    print(f"\nMini-sweep starting → {OUT_JSONL.name} ({len(MINI_TEMPLATES)} templates)", flush=True)

    from review.sweep_all_rewritten import observe_one, kit_alive
    OUT_JSONL.write_text("")

    pass_count = 0; fail_count = 0; exc_count = 0
    detector_counts = {}

    for i, name in enumerate(MINI_TEMPLATES, 1):
        if not kit_alive():
            print(f"[{i}/{len(MINI_TEMPLATES)}] Kit down — restart", flush=True)
            if not restart_kit():
                print("  Kit restart failed; skip"); continue
        t0 = time.time()
        print(f"[{i}/{len(MINI_TEMPLATES)}] {name}", flush=True)
        try:
            rec = await observe_one(name)
        except Exception as e:
            print(f"  CRASH: {type(e).__name__}: {e}", flush=True)
            continue
        rec['template'] = name
        with OUT_JSONL.open("a") as f:
            f.write(json.dumps(rec, default=str)+"\n")
        elapsed = round(time.time() - t0, 1)
        if rec.get('exception'):
            print(f"  EXC: {rec['exception']} ({elapsed}s)", flush=True); exc_count += 1; continue
        cs = (rec.get('engine_data') or {}).get('ctrl_state') or {}
        deliv = next((v for k, v in cs.items() if k.endswith(':cubes_delivered')), 0)
        phase = next((v for k, v in cs.items() if k.endswith(':phase')), '?')
        ve = (rec.get('virtual_eyes') or {}).get('patterns') or {}
        active_dets = [n for n, p in ve.items() if p.get('detected')]
        for d in active_dets: detector_counts[d] = detector_counts.get(d, 0) + 1
        if rec.get('honest_pass'):
            print(f"  HONEST_PASS deliv={deliv} VE=[{','.join(active_dets[:3])}{'...' if len(active_dets)>3 else ''}] ({elapsed}s)", flush=True)
            pass_count += 1
        else:
            gates = rec.get('gates', {})
            failed_gates = [k for k, v in gates.items() if not v]
            print(f"  FAIL deliv={deliv} phase={phase} fails={failed_gates} VE=[{','.join(active_dets[:3])}{'...' if len(active_dets)>3 else ''}] ({elapsed}s)", flush=True)
            fail_count += 1

    print(f"\nFINAL: {pass_count}/{len(MINI_TEMPLATES)} HONEST_PASS, {fail_count} FAIL, {exc_count} EXC", flush=True)
    print("Detector counts:", flush=True)
    for d, n in sorted(detector_counts.items(), key=lambda x: -x[1]):
        print(f"  {d}: {n}", flush=True)
    print(f"\nResults: {OUT_JSONL}")
    print(f"Code-state: {CODE_PATCH}")


if __name__ == "__main__":
    asyncio.run(main())
