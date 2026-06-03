"""
function_gate_sweep_2026_05_18.py — broad function-gate sweep over all
delivery-pattern templates after pre-sweep success-criteria fixes.

Scope (from workspace/qa_runs/function_gate_2026-05-18_scope.json):
  - 121 CP-NN/CP-NEW templates with pattern_hint ∈ {pick_place, sort,
    reorient, navigate} that are not is_self_consistent:false and not
    env_blocked, and have complete simulate_args.

Method per template:
  1. new_stage reset
  2. execute_template_canonical → build (BUILD-gate)
  3. settle_after_canonical
  4. simulate_traversal_check with simulate_args
  5. record verdict in JSONL

Output: workspace/qa_runs/function_gate_2026-05-18.jsonl

Usage:
    python scripts/qa/function_gate_sweep_2026_05_18.py
    python scripts/qa/function_gate_sweep_2026_05_18.py --only CP-01.json
    python scripts/qa/function_gate_sweep_2026_05_18.py --start-from CP-50.json
    python scripts/qa/function_gate_sweep_2026_05_18.py --max 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from service.isaac_assist_service.chat.canonical_instantiator import (  # noqa: E402
    execute_template_canonical, settle_after_canonical,
)
from service.isaac_assist_service.chat.tools.tool_executor import (  # noqa: E402
    execute_tool_call,
)
from service.isaac_assist_service.chat.tools import kit_tools  # noqa: E402


SCOPE_PATH = REPO_ROOT / "workspace/qa_runs/function_gate_2026-05-18_scope.json"
OUTPUT_JSONL = REPO_ROOT / "workspace/qa_runs/function_gate_2026-05-18.jsonl"
TEMPLATES_DIR = REPO_ROOT / "workspace/templates"


async def _reset_scene() -> None:
    code = (
        "import omni.usd\n"
        "ctx = omni.usd.get_context()\n"
        "ctx.new_stage()\n"
        "stage = ctx.get_stage()\n"
        "from pxr import UsdGeom\n"
        "UsdGeom.Xform.Define(stage, '/World')\n"
    )
    res = await kit_tools.exec_sync(code, timeout=30)
    if not res.get("success"):
        raise RuntimeError(f"reset failed: {(res.get('output') or '')[:200]}")


def _build_simulate_args(template: Dict[str, Any], cap_duration_s: Optional[int] = None) -> Dict[str, Any]:
    """Resolve simulate_args (preferring already-instantiated `simulate_args`
    field over the template form). Optionally cap duration_s."""
    sa = template.get("simulate_args") or template.get("simulate_args_template") or {}
    if not isinstance(sa, dict):
        return {}
    sa = dict(sa)  # copy
    # Normalize cube_paths→cube_path[0] if needed
    if not sa.get("cube_path") and sa.get("cube_paths"):
        cps = sa.get("cube_paths") or []
        if cps:
            sa["cube_path"] = cps[0]
    if cap_duration_s and sa.get("duration_s"):
        sa["duration_s"] = min(int(sa["duration_s"]), int(cap_duration_s))
    return sa


async def run_one(name: str, template: Dict[str, Any], rec_in: Dict[str, Any], cap_duration_s: Optional[int] = None) -> Dict[str, Any]:
    """Run one full function-gate cycle for a single template."""
    t0 = time.time()
    out: Dict[str, Any] = {
        "name": name,
        "pattern": rec_in.get("pattern"),
        "inferred_pattern": rec_in.get("inferred"),
        "had_function_gate_pass_pre": rec_in.get("had_function_gate_pass"),
        "verified_status_pre": rec_in.get("verified_status"),
        "build_ok": None,
        "build_n_ok": None,
        "build_n_calls": None,
        "build_errors": [],
        "settle_ok": None,
        "settle_error": None,
        "function_gate_ran": False,
        "function_gate_success": None,
        "function_gate_verdict": None,
        "in_target_xy": None,
        "above_floor": None,
        "at_rest": None,
        "cube_speed": None,
        "cube_final": None,
        "cube_initial": None,
        "exception": None,
        "time_elapsed_s": None,
    }
    try:
        await _reset_scene()
    except Exception as e:
        out["exception"] = f"reset:{e}"
        out["time_elapsed_s"] = round(time.time() - t0, 2)
        return out

    try:
        build_res = await execute_template_canonical(template)
        out["build_n_ok"] = build_res.get("n_ok")
        out["build_n_calls"] = build_res.get("n_calls")
        out["build_ok"] = bool(build_res.get("instantiated"))
        if build_res.get("errors"):
            out["build_errors"] = build_res.get("errors", [])[:5]
    except Exception as e:
        out["exception"] = f"build:{type(e).__name__}:{str(e)[:160]}"
        out["time_elapsed_s"] = round(time.time() - t0, 2)
        return out

    if not out["build_ok"]:
        out["function_gate_verdict"] = "BUILD_FAILED"
        out["time_elapsed_s"] = round(time.time() - t0, 2)
        return out

    try:
        settle_res = await settle_after_canonical(template)
        out["settle_ok"] = True
        out["settle_summary"] = {
            k: v for k, v in (settle_res or {}).items()
            if k in {"settled", "n_ticks", "stable", "warnings"}
        }
    except Exception as e:
        out["settle_ok"] = False
        out["settle_error"] = f"{type(e).__name__}:{str(e)[:160]}"

    # Simulate_traversal_check
    sim_args = _build_simulate_args(template, cap_duration_s=cap_duration_s)
    out["duration_s_used"] = sim_args.get("duration_s")
    try:
        res = await execute_tool_call("simulate_traversal_check", sim_args)
        out["function_gate_ran"] = True
        raw_out = (res.get("output") or "").strip()
        # The tool emits a JSON line at the end; capture last {...} line
        json_lines = [l for l in raw_out.splitlines() if l.strip().startswith("{")]
        parsed = None
        if json_lines:
            try:
                parsed = json.loads(json_lines[-1])
            except Exception:
                parsed = None
        if parsed is None:
            out["function_gate_verdict"] = "NO_JSON"
            out["raw_tail"] = raw_out[-400:]
        else:
            out["function_gate_success"] = bool(parsed.get("success"))
            out["function_gate_verdict"] = "PASS" if parsed.get("success") else "FAIL"
            out["in_target_xy"] = parsed.get("in_target_xy")
            out["above_floor"] = parsed.get("above_floor")
            out["at_rest"] = parsed.get("at_rest")
            out["cube_speed"] = parsed.get("cube_speed") or parsed.get("cube_speed_max")
            cf = parsed.get("cube_final")
            out["cube_final"] = [round(c, 4) for c in cf] if cf else None
            ci = parsed.get("cube_initial")
            out["cube_initial"] = [round(c, 4) for c in ci] if ci else None
            # Pass any error/reason field if present
            for k in ("error", "reason", "failure_mode", "details"):
                if k in parsed:
                    out[f"fg_{k}"] = parsed[k]
    except Exception as e:
        out["exception"] = f"function_gate:{type(e).__name__}:{str(e)[:160]}"
        out["function_gate_verdict"] = "EXC"
        out["traceback_tail"] = traceback.format_exc().splitlines()[-3:]

    out["time_elapsed_s"] = round(time.time() - t0, 2)
    return out


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", default=None, help="Run only this template (e.g. CP-01.json)")
    p.add_argument("--start-from", default=None, help="Skip until this template")
    p.add_argument("--max", type=int, default=None, help="Max templates to run")
    p.add_argument("--restart-every", type=int, default=30,
                   help="Trigger Kit restart hint every N templates (informational only)")
    p.add_argument("--cap-duration", type=int, default=None,
                   help="Cap simulate_traversal_check duration_s at this value")
    p.add_argument("--skip-already-passing", action="store_true",
                   help="Skip templates whose verified_status already shows function-gate ✓")
    p.add_argument("--grandfather-sample", type=int, default=0,
                   help="Append N random previously-passing templates to verify they still pass")
    args = p.parse_args()

    if not await kit_tools.is_kit_rpc_alive():
        print("[FAIL] Kit RPC not alive at 127.0.0.1:8001")
        return 2

    scope = json.loads(SCOPE_PATH.read_text())
    eligible: List[Dict[str, Any]] = scope["eligible"]

    if args.only:
        eligible = [e for e in eligible if e["name"] == args.only]
    elif args.start_from:
        idx = next((i for i, e in enumerate(eligible) if e["name"] == args.start_from), 0)
        eligible = eligible[idx:]

    if args.skip_already_passing:
        skipped_grandfather = [e for e in eligible if e.get("had_function_gate_pass")]
        eligible = [e for e in eligible if not e.get("had_function_gate_pass")]
        if args.grandfather_sample > 0:
            import random
            random.seed(42)
            sample = random.sample(skipped_grandfather, min(args.grandfather_sample, len(skipped_grandfather)))
            eligible = eligible + sample
            print(f"[sweep] sampling {len(sample)} grandfather templates")

    if args.max:
        eligible = eligible[: args.max]

    print(f"[sweep] {len(eligible)} templates to process")
    OUTPUT_JSONL.parent.mkdir(exist_ok=True, parents=True)
    # Append mode: do NOT clobber existing partial runs
    f_out = OUTPUT_JSONL.open("a", buffering=1)  # line-buffered

    n_total = 0
    n_build_ok = 0
    n_fg_pass = 0
    n_fg_fail = 0
    n_build_fail = 0
    n_exc = 0

    t_start = time.time()
    for i, rec in enumerate(eligible, 1):
        name = rec["name"]
        tp = TEMPLATES_DIR / name
        try:
            template = json.loads(tp.read_text())
        except Exception as e:
            row = {"name": name, "exception": f"load_fail:{e}",
                   "function_gate_verdict": "LOAD_FAILED"}
            f_out.write(json.dumps(row) + "\n")
            n_exc += 1
            continue

        print(f"  [{i}/{len(eligible)}] {name} (pattern={rec['pattern']}) ...", flush=True)
        try:
            row = await run_one(name, template, rec, cap_duration_s=args.cap_duration)
        except Exception as e:
            row = {"name": name, "exception": f"run_one_outer:{e}",
                   "function_gate_verdict": "OUTER_EXC"}

        f_out.write(json.dumps(row) + "\n")
        n_total += 1
        v = row.get("function_gate_verdict")
        if row.get("build_ok"):
            n_build_ok += 1
        else:
            if v == "BUILD_FAILED":
                n_build_fail += 1
        if v == "PASS":
            n_fg_pass += 1
        elif v == "FAIL":
            n_fg_fail += 1
        elif v in {"EXC", "OUTER_EXC", "LOAD_FAILED"}:
            n_exc += 1
        elapsed_min = (time.time() - t_start) / 60.0
        print(f"        verdict={v} build_ok={row.get('build_ok')} "
              f"fg_success={row.get('function_gate_success')} "
              f"elapsed={row.get('time_elapsed_s')}s "
              f"[totals so far build_ok={n_build_ok} fg_pass={n_fg_pass} "
              f"fg_fail={n_fg_fail} build_fail={n_build_fail} exc={n_exc} "
              f"wall={elapsed_min:.1f}min]",
              flush=True)

        # Bail if Kit dies mid-run
        if not await kit_tools.is_kit_rpc_alive():
            print(f"[WARN] Kit RPC died after {name}; bailing cleanly")
            break

    f_out.close()
    print(f"\n[done] processed {n_total} templates in {(time.time()-t_start)/60.0:.1f}min")
    print(f"  build_ok={n_build_ok}  build_fail={n_build_fail}  fg_pass={n_fg_pass}  "
          f"fg_fail={n_fg_fail}  exc={n_exc}")
    print(f"  Results: {OUTPUT_JSONL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
