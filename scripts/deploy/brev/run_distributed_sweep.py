"""run_distributed_sweep.py — distribute function-gate templates across N Kit slices.

Each worker is a single Python coroutine that targets one Kit RPC port via
the KIT_RPC_PORT env var (read by service.isaac_assist_service.chat.tools.kit_tools).

Reads templates from a text file (one CP-* name per line), splits them across
ports round-robin, runs each through the same function_gate pipeline used in
workspace/qa_runs/function_gate_runner.py, and merges results into one JSONL.

Worker-died semantics: if a Kit becomes unresponsive (3 consecutive health
failures), its remaining queue is redistributed to the surviving workers.

Usage:
    python scripts/deploy/brev/run_distributed_sweep.py \\
        --templates /tmp/all_templates.txt \\
        --ports 8001,8002,8003 \\
        --output /mnt/persist/sweeps/$(date +%Y%m%dT%H%M%S)_full.jsonl

Optional:
    --build-timeout 600
    --sim-timeout 300
    --max-templates 50          # smoke-test mode
    --resume                    # skip templates already in --output
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

REPO_ROOT = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO_ROOT))

TPL_DIR = REPO_ROOT / "workspace" / "templates"


def log(msg: str, port: Optional[int] = None) -> None:
    prefix = f"[port {port}]" if port else "[main]"
    print(f"[{time.strftime('%H:%M:%S')}] {prefix} {msg}", flush=True)


# ───────────────────────────────────────────────────────────────────────────────
# Per-port HTTP helpers (cannot reuse kit_tools KIT_RPC_BASE because it's
# captured at import-time; we set os.environ per worker before any imports
# that touch kit_tools).
# ───────────────────────────────────────────────────────────────────────────────

def kit_health(port: int, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


# ───────────────────────────────────────────────────────────────────────────────
# Per-template function-gate (mirrors workspace/qa_runs/function_gate_runner.py)
# ───────────────────────────────────────────────────────────────────────────────

async def reset_scene_on_port(port: int) -> bool:
    # Force re-import of kit_tools with the right KIT_RPC_PORT
    os.environ["KIT_RPC_PORT"] = str(port)
    # Re-evaluate the module-level KIT_RPC_BASE if already imported
    from service.isaac_assist_service.chat.tools import kit_tools as kt
    kt.KIT_RPC_BASE = f"http://127.0.0.1:{port}"

    code = (
        "import omni.usd\n"
        "ctx = omni.usd.get_context()\n"
        "ctx.new_stage()\n"
        "stage = ctx.get_stage()\n"
        "from pxr import UsdGeom\n"
        "UsdGeom.Xform.Define(stage, '/World')\n"
    )
    try:
        res = await kt.exec_sync(code, timeout=20)
        return bool(res.get("success"))
    except Exception:
        return False


async def function_gate_one(template_name: str, port: int, build_timeout_s: int, sim_timeout_s: int) -> Dict[str, Any]:
    os.environ["KIT_RPC_PORT"] = str(port)
    from service.isaac_assist_service.chat.tools import kit_tools as kt
    kt.KIT_RPC_BASE = f"http://127.0.0.1:{port}"
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical,
        settle_after_canonical,
    )
    from service.isaac_assist_service.chat.tools.tool_executor import execute_tool_call

    p = TPL_DIR / f"{template_name}.json"
    t0 = time.time()
    rec: Dict[str, Any] = {
        "template": template_name,
        "phase": "function_gate",
        "port": port,
        "build_ok": False,
        "delivered": False,
        "in_xy": None,
        "above_floor": None,
        "at_rest": None,
        "cube_speed": None,
        "duration_s": 0.0,
        "exception": None,
        "errors_head": None,
    }
    if not p.exists():
        rec["exception"] = "NOT_FOUND"
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec
    try:
        tpl = json.loads(p.read_text())
    except Exception as e:
        rec["exception"] = f"json: {type(e).__name__}"
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec

    if not await reset_scene_on_port(port):
        rec["exception"] = "reset_fail"
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec

    try:
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=build_timeout_s)
        rec["build_ok"] = bool(b.get("instantiated"))
        if not rec["build_ok"]:
            rec["exception"] = "BUILD_FAIL"
            errs = b.get("errors") or []
            rec["errors_head"] = "; ".join(str(e)[:200] for e in errs[:2])[:400]
            rec["duration_s"] = round(time.time() - t0, 2)
            return rec
    except asyncio.TimeoutError:
        rec["exception"] = "BUILD_TIMEOUT"
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec
    except Exception as e:
        rec["exception"] = f"BUILD_EXC:{type(e).__name__}:{str(e)[:200]}"
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec

    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception:
        pass

    sa = tpl.get("simulate_args") or {}
    fg: Dict[str, Any] = {"target_path": sa.get("target_path"), "duration_s": sa.get("duration_s", 45)}
    if sa.get("cube_path"):
        fg["cube_path"] = sa["cube_path"]
    if sa.get("cube_paths"):
        fg["cube_paths"] = sa["cube_paths"]
    for opt in ("xy_tolerance", "rest_speed_threshold", "min_cubes_delivered",
                "per_bin_expected", "routed_target_paths"):
        if opt in sa:
            fg[opt] = sa[opt]

    try:
        r = await asyncio.wait_for(
            execute_tool_call("simulate_traversal_check", fg),
            timeout=sim_timeout_s,
        )
        out = (r.get("output") or "").strip()
        js = [l for l in out.splitlines() if l.strip().startswith("{")]
        if js:
            d = json.loads(js[-1])
            rec["delivered"] = bool(d.get("success"))
            rec["in_xy"] = d.get("in_target_xy")
            rec["above_floor"] = d.get("above_floor")
            rec["at_rest"] = d.get("at_rest")
            cs = d.get("cube_speed")
            rec["cube_speed"] = round(cs, 3) if isinstance(cs, (int, float)) else None
        else:
            rec["exception"] = "NO_RESULT"
            rec["errors_head"] = (r.get("output") or "")[:300]
    except asyncio.TimeoutError:
        rec["exception"] = "SIM_TIMEOUT"
    except Exception as e:
        rec["exception"] = f"SIM_EXC:{type(e).__name__}:{str(e)[:200]}"

    rec["duration_s"] = round(time.time() - t0, 2)
    return rec


# ───────────────────────────────────────────────────────────────────────────────
# Worker + dispatch
# ───────────────────────────────────────────────────────────────────────────────

class Dispatcher:
    """Shared queue with worker-died re-queueing.

    Each worker pulls one template at a time. If a worker reports unhealthy,
    its in-flight template is re-enqueued for another worker to claim.
    """
    def __init__(self, templates: List[str]):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        for t in templates:
            self._queue.put_nowait(t)
        self.total = len(templates)
        self.completed = 0
        self.lock = asyncio.Lock()

    async def pop(self) -> Optional[str]:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def requeue(self, name: str) -> None:
        await self._queue.put(name)

    async def mark_done(self) -> None:
        async with self.lock:
            self.completed += 1


async def worker(port: int, dispatcher: Dispatcher, out_path: Path, args, worker_log: Path) -> Dict[str, Any]:
    stats = {"port": port, "n_done": 0, "n_delivered": 0, "n_fail": 0, "died": False}
    consecutive_health_fail = 0

    with worker_log.open("a") as wlog:
        wlog.write(f"[{time.strftime('%H:%M:%S')}] worker start port={port}\n")
        wlog.flush()

        while True:
            name = await dispatcher.pop()
            if name is None:
                break

            # Health-check before claiming
            if not kit_health(port):
                consecutive_health_fail += 1
                wlog.write(f"[{time.strftime('%H:%M:%S')}] port {port} unhealthy ({consecutive_health_fail}/3) — re-queue {name}\n")
                wlog.flush()
                await dispatcher.requeue(name)
                if consecutive_health_fail >= 3:
                    log(f"DIED after 3 consecutive health failures — worker exiting", port=port)
                    stats["died"] = True
                    break
                await asyncio.sleep(10)
                continue
            consecutive_health_fail = 0

            log(f"start {name}", port=port)
            t0 = time.time()
            try:
                rec = await function_gate_one(name, port, args.build_timeout, args.sim_timeout)
            except Exception as e:
                rec = {"template": name, "port": port, "exception": f"WORKER_EXC:{type(e).__name__}:{str(e)[:200]}",
                       "duration_s": round(time.time() - t0, 2), "delivered": False, "build_ok": False}

            with out_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            await dispatcher.mark_done()
            stats["n_done"] += 1
            if rec.get("delivered"):
                stats["n_delivered"] += 1
                tag = "DELIVERED"
            else:
                stats["n_fail"] += 1
                tag = f"FAIL({rec.get('exception') or 'sim'})"
            log(f"{tag} {name} t={rec.get('duration_s')}s "
                f"[{dispatcher.completed}/{dispatcher.total}]", port=port)
            wlog.write(f"[{time.strftime('%H:%M:%S')}] {tag} {name} t={rec.get('duration_s')}s\n")
            wlog.flush()

        wlog.write(f"[{time.strftime('%H:%M:%S')}] worker exit port={port} "
                   f"done={stats['n_done']} delivered={stats['n_delivered']} died={stats['died']}\n")

    return stats


async def main_async(args) -> int:
    # Read template list
    tpl_path = Path(args.templates)
    if not tpl_path.exists():
        log(f"ERROR: template list not found: {tpl_path}")
        return 2
    templates = [t.strip() for t in tpl_path.read_text().splitlines() if t.strip()]
    if args.max_templates:
        templates = templates[:args.max_templates]

    # Resume: skip already-done templates
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.resume and out_path.exists():
        done: Set[str] = set()
        for line in out_path.read_text().splitlines():
            try:
                done.add(json.loads(line).get("template"))
            except Exception:
                continue
        before = len(templates)
        templates = [t for t in templates if t not in done]
        log(f"Resume: {before - len(templates)} already done, {len(templates)} remaining")
    else:
        out_path.write_text("")

    # Parse ports
    ports = [int(p.strip()) for p in args.ports.split(",") if p.strip()]
    if not ports:
        log("ERROR: --ports list is empty")
        return 2

    # Pre-flight: every port must be healthy
    for p in ports:
        if not kit_health(p):
            log(f"ERROR: Kit on port {p} not responding to /health. Launch the pool first.")
            return 3

    log(f"Templates: {len(templates)}   Workers: {len(ports)} on ports {ports}")
    log(f"Output: {out_path}")

    dispatcher = Dispatcher(templates)
    t_start = time.time()

    workers = []
    for p in ports:
        wlog = out_path.with_suffix(f".worker_{p}.log")
        workers.append(asyncio.create_task(worker(p, dispatcher, out_path, args, wlog)))

    results = await asyncio.gather(*workers)

    elapsed = time.time() - t_start
    total_done = sum(r["n_done"] for r in results)
    total_delivered = sum(r["n_delivered"] for r in results)
    total_fail = sum(r["n_fail"] for r in results)
    died = [r["port"] for r in results if r["died"]]

    log(f"DONE  elapsed={elapsed:.1f}s  "
        f"total={total_done}  delivered={total_delivered}  fail={total_fail}  "
        f"died_workers={died}  pass_rate={100*total_delivered/max(total_done,1):.1f}%")

    for r in results:
        log(f"  port {r['port']}: done={r['n_done']} delivered={r['n_delivered']} died={r['died']}")

    # Throughput summary
    per_worker_thru = total_done / max(elapsed, 1) / max(len(ports), 1) * 60
    log(f"Throughput: {total_done/max(elapsed,1)*60:.1f} templates/min total, "
        f"{per_worker_thru:.1f} templates/min per worker")

    return 0 if not died else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates", required=True,
                    help="Path to text file with one template name per line (e.g. 'CP-12')")
    ap.add_argument("--ports", required=True,
                    help="Comma-separated Kit RPC ports, e.g. '8001,8002,8003'")
    ap.add_argument("--output", required=True,
                    help="Output JSONL path. Resumable if --resume given.")
    ap.add_argument("--build-timeout", type=int, default=600)
    ap.add_argument("--sim-timeout", type=int, default=300)
    ap.add_argument("--max-templates", type=int, default=0,
                    help="If > 0, only run first N templates (smoke-test mode)")
    ap.add_argument("--resume", action="store_true",
                    help="Skip templates already present in --output")
    args = ap.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
