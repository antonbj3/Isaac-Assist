"""Mass sweep: restart Kit + uvicorn fresh, then run scene_observer against
ALL rewritten templates. Outputs scene_observer_mass_<timestamp>.jsonl +
auto-runs analyze_sweep.py to produce review-ready markdown.

Use after handler-edits — guarantees fresh state for verification.
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

TS = time.strftime("%Y%m%d_%H%M%S")
OUT_JSONL = REPO/f"workspace/qa_runs/scene_observer_mass_{TS}.jsonl"
LOG = Path(f"/tmp/mass_sweep_{TS}.log")
UVI_LOG = Path(f"/tmp/uvicorn_mass_{TS}.log")
LOCK = Path("/tmp/mass_sweep_active.pid")


def _check_no_other_sweep():
    """Prevent double-launch — Kit RPC is single-tenant, parallel sweeps cause race conditions."""
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().strip())
            os.kill(pid, 0)  # signal 0 = check if alive
            sys.exit(f"ABORT: another mass-sweep is already running (PID {pid}). "
                     f"Kill it first or remove {LOCK} if stale.")
        except (ProcessLookupError, ValueError):
            pass  # stale lock, ok to overwrite
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
        except PermissionError: print(f"  cannot kill {p} (permission)")


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
    for i in range(60):  # up to 5 min
        time.sleep(5)
        if _http_ok(KIT_HEALTH):
            print(f"  Kit up at {(i+1)*5}s", flush=True); return True
    print("  Kit TIMEOUT 5min"); return False


async def main():
    # Step 0: lockfile guard (prevent Kit single-tenant race)
    _check_no_other_sweep()
    try:
        await _main_inner()
    finally:
        try: LOCK.unlink()
        except FileNotFoundError: pass


async def _main_inner():
    # Step 1: fresh state
    if not restart_uvicorn():
        sys.exit("uvicorn-restart failed; abort")
    if not restart_kit():
        sys.exit("Kit-restart failed; abort")

    # Step 2: run sweep_all_rewritten with override OUT path
    print(f"\nMass sweep starting → {OUT_JSONL.name}", flush=True)
    # Use existing sweep machinery but override OUT
    import importlib
    sweep_mod = importlib.import_module("review.sweep_all_rewritten")
    sweep_mod.OUT = OUT_JSONL
    await sweep_mod.main()

    # Step 3: analysis
    print(f"\nGenerating review markdown...", flush=True)
    subprocess.run([sys.executable, "scripts/review/analyze_sweep.py", str(OUT_JSONL)],
                   cwd=str(REPO), check=False)

    print(f"\nDONE. Review at: {OUT_JSONL.with_suffix('.review.md')}")


if __name__ == "__main__":
    asyncio.run(main())
