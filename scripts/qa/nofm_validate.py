#!/usr/bin/env python3
"""nofm_validate — N-of-M re-validation harness with TS faithfulness [P0-06].

Per template: FRESH-KIT RESTART -> gate_one (delivery verdict) ->
scene_timeseries (graded time-series: per-cube STATEs + containment — the
faithfulness axis the bare gate misses). Every run is ledger-recorded with
extras: verdict_vector (TS states), kit_session_age proxy, batch position.
Combined with prior measured runs this lifts templates to the N-of-M bar
("stable" = consistent across fresh sessions, not a single lucky run).

Restart discipline is the point: today's calibration produced 6 consecutive
warm-Kit false-FAILs — restart-per-template makes that class structurally
impossible here.

Usage:
    python3 scripts/qa/nofm_validate.py CP-70 CP-01 ... [--no-restart] [--skip-ts]
Serial; owns Kit for the duration.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from service.isaac_assist_service.qa.verification_ledger import record_gate_run  # noqa: E402

LAUNCHER = "/home/anton/projects/sibling-project/launch_isaac_sim_with_assist.sh"
HEALTH = "http://127.0.0.1:8001/health"
_BAD_STATES = {"FLUNG", "ON_FLOOR", "TOPPLED", "MISROUTED", "ALOFT", "NOT_SEATED",
               "UNROUTABLE_NO_BIN", "OFF_TARGET", "IN_FLIGHT", "UNSETTLED"}
# per-item line: "  Cube_1: bin=... | err_xy=... | ... | STATE1,STATE2 | final=[...]"
_ITEM_RE = re.compile(r"^\s{2}(\w[\w/]*): bin=.*\|\s*([A-Z_,]+|OK)\s*\|\s*final=", re.M)


def _kit_pid() -> int | None:
    out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True).stdout
    m = re.search(r':8001\s.*pid=(\d+)', out)
    return int(m.group(1)) if m else None


def _health_ok() -> bool:
    try:
        out = subprocess.run(["curl", "-s", "-m", "3", HEALTH],
                             capture_output=True, text=True, timeout=6).stdout
        return '"ok": true' in out
    except Exception:
        return False


def _all_kit_pids() -> list[int]:
    """Every live Kit process. Three signals UNIONED — none alone suffices
    (wave-1b/1c/1d findings):
      * the :8001 listener (a booting Kit has not bound yet);
      * launcher cmdlines (killing the bash leaves the detached python);
      * nvidia-smi compute apps — Kit pythons report a bare 'python'
        cmdline but every Kit holds ~2 GB VRAM, so GPU ownership is the
        reliable signature (6 zombies at 4.6-10 GB RAM each starved the
        box to 42/62 GB + 11.2/12 GB VRAM before this fix)."""
    pids: set[int] = set()
    out = subprocess.run(["pgrep", "-f", r"[k]it/kit|isaac[-_]sim.*--headless"],
                         capture_output=True, text=True).stdout
    pids.update(int(p) for p in out.split())
    p = _kit_pid()
    if p:
        pids.add(p)
    try:
        smi = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name",
             "--format=csv,noheader"], capture_output=True, text=True,
            timeout=10).stdout
        for line in smi.splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) < 2 or not parts[0].isdigit() \
                    or "python" not in parts[1]:
                continue
            pid = int(parts[0])
            # Only claim GPU pythons that are PROVABLY Kit: their environ
            # carries Isaac/Omni/Carb vars. Never sweep unrelated GPU work
            # (training jobs etc) into a Kit kill.
            try:
                env = open(f"/proc/{pid}/environ", "rb").read().lower()
            except OSError:
                continue
            if b"isaac" in env or b"omni" in env or b"carb" in env:
                pids.add(pid)
    except Exception:
        pass
    return sorted(pids)


def restart_kit(timeout_s: int = 300) -> float:
    """Kill EVERY Kit process, wait for them to die, relaunch headless,
    wait for health + a real exec. Returns boot seconds."""
    pids = set(_all_kit_pids())
    lp = _kit_pid()
    if lp:
        pids.add(lp)
    for pid in pids:
        subprocess.run(["kill", str(pid)], check=False)
    t_kill = time.time()
    while time.time() - t_kill < 30:
        if not _all_kit_pids():
            break
        time.sleep(1)
    else:
        for pid in _all_kit_pids():
            subprocess.run(["kill", "-9", str(pid)], check=False)
        time.sleep(2)
    t0 = time.time()
    subprocess.Popen(["bash", LAUNCHER, "--headless"],
                     cwd=str(Path(LAUNCHER).parent),
                     stdout=open("/tmp/nofm_kit.log", "w"),
                     stderr=subprocess.STDOUT,
                     start_new_session=True)
    while time.time() - t0 < timeout_s:
        time.sleep(6)
        if _health_ok():
            # real exec confirms Kit is functional, not just the RPC shim
            r = subprocess.run(
                ["curl", "-s", "-m", "30", "-X", "POST",
                 "http://127.0.0.1:8001/exec_sync",
                 "-H", "Content-Type: application/json",
                 "-d", '{"code": "import omni.usd\\nprint(omni.usd.get_context().get_stage() is not None)"}'],
                capture_output=True, text=True, timeout=40).stdout
            if '"success": true' in r:
                return round(time.time() - t0, 1)
    raise RuntimeError(f"Kit failed to boot within {timeout_s}s (see /tmp/nofm_kit.log)")


def run_gate(name: str) -> bool | None:
    p = subprocess.run([sys.executable, str(REPO / "scripts/qa/gate_one.py"), name],
                       capture_output=True, text=True, timeout=900)
    out = p.stdout + p.stderr
    m = re.search(r"GATE success=(\w+)", out)
    if m is None:
        # an unparseable gate is a FINDING, not a shrug — show why
        print(f"  GATE UNPARSEABLE (exit={p.returncode}) tail: {out[-400:]}",
              flush=True)
    return (m.group(1) == "True") if m else None


def run_ts(name: str) -> tuple[bool | None, dict]:
    """scene_timeseries run -> (passed, verdict_vector). passed = no bad
    state on any graded item; None when unparseable."""
    p = subprocess.run([sys.executable, str(REPO / "scripts/qa/scene_timeseries.py"), name],
                       capture_output=True, text=True, timeout=900)
    out = p.stdout + p.stderr
    vec: dict = {}
    for m in _ITEM_RE.finditer(out):
        vec[m.group(1)] = m.group(2)
    if not vec:
        return None, {"_raw_tail": out[-200:]}
    bad = any(s in _BAD_STATES for states in vec.values() for s in states.split(","))
    return (not bad), vec


def main() -> int:
    args = [a for a in sys.argv[1:]]
    no_restart = "--no-restart" in args
    skip_ts = "--skip-ts" in args
    names = [a for a in args if not a.startswith("--")]
    if not names:
        print(__doc__)
        return 2
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                         capture_output=True, text=True).stdout.strip()
    for i, name in enumerate(names):
        tpl = f"workspace/templates/{name}.json"
        boot = 0.0
        if not no_restart:
            boot = restart_kit()
        print(f"[{i+1}/{len(names)}] {name} (kit boot {boot}s)", flush=True)

        g = run_gate(name)
        if g is not None:
            record_gate_run(REPO / tpl, g, sha, extras={
                "source": "nofm_gate", "batch_position": i, "fresh_kit": not no_restart})
        print(f"  gate={g}", flush=True)

        if not skip_ts:
            ts_pass, vec = run_ts(name)
            if ts_pass is not None:
                record_gate_run(REPO / tpl, ts_pass, sha, axis="faithfulness",
                                extras={
                                    "source": "nofm_scene_timeseries",
                                    "verdict_vector": vec,
                                    "batch_position": i,
                                    "kit_runs_since_boot": 1})
            print(f"  ts={ts_pass} vec={vec if ts_pass is not None else 'UNPARSEABLE'}", flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
