"""Sweep all 145 CP-NEW canonicals — function-gate health check.

Output per template: delivered, in_target_zone, at_rest, honest_pass, exception.
Writes JSONL incrementally so partial results survive interrupts.

Usage:
  python scripts/review/sweep_cpnew.py
  python scripts/review/sweep_cpnew.py --resume   # skip templates already in output
  python scripts/review/sweep_cpnew.py --limit 10 # smoke 10 first
"""
import asyncio, json, glob, sys, time, argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.review.sweep_all_rewritten import observe_one, kit_alive, launch_kit, restart_kit

OUT_DIR = REPO / "workspace/qa_runs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def gate_status(rec: dict) -> dict:
    """Compute function-gate metrics from observe_one record."""
    if rec.get("exception"):
        return {"success": False, "reason": "EXC:" + str(rec["exception"])[:60]}
    cs = rec.get("cube_supports", {}) or {}
    in_target_ever = rec.get("cube_in_target_ever", {}) or {}
    # Find primary cube — first in cube_supports keys
    primary = next(iter(cs.keys()), None) if cs else None
    if primary is None:
        return {"success": False, "reason": "no_cubes"}
    cm = cs.get(primary, {})
    delivered = bool(cm.get("under_target"))
    in_xy = bool(in_target_ever.get(primary))
    gates = rec.get("gates", {}) or {}
    honest_pass = bool(rec.get("honest_pass"))
    # function-gate criterion: delivered AND honest
    if delivered and honest_pass:
        return {"success": True, "reason": "ok"}
    parts = []
    if not delivered: parts.append("not_under_target")
    if not in_xy: parts.append("never_in_xy")
    for k, v in gates.items():
        if not v: parts.append(f"gate:{k}")
    if not parts: parts.append("honest_pass_false")
    return {"success": False, "reason": ",".join(parts[:3])}


DELIVERY_HINTS = {"pick_place", "sort", "insert", "reorient", "navigate"}


def filter_delivery_pattern(template_paths: list) -> list:
    """Keep templates where observe_one's delivery criterion applies."""
    keep = []
    for p in template_paths:
        try:
            t = json.loads(open(p).read())
            hint = (t.get("intent") or {}).get("pattern_hint", "")
            sa = t.get("simulate_args") or {}
            if hint in DELIVERY_HINTS and sa.get("target_path") and sa.get("cube_paths"):
                keep.append((Path(p).stem, t))
        except Exception:
            pass
    return keep


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=f"cpnew_sweep_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    parser.add_argument("--resume", action="store_true", help="Skip templates already in output file")
    parser.add_argument("--limit", type=int, default=0, help="Smoke-test N first templates (0=all)")
    parser.add_argument("--restart-every", type=int, default=4, help="Kit restart cadence")
    parser.add_argument("--timeout-margin", type=int, default=60,
                        help="Add to template duration_s for observe timeout")
    args = parser.parse_args()

    out_path = OUT_DIR / args.out
    done = set()
    if args.resume and out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                done.add(json.loads(line)["template"])
            except Exception:
                pass
        print(f"Resume mode: {len(done)} templates already done, skipping", flush=True)

    all_paths = sorted(glob.glob(str(REPO / "workspace/templates/CP-NEW-*.json")))
    pairs = filter_delivery_pattern(all_paths)  # [(name, tpl_dict), ...]
    if args.limit:
        pairs = pairs[:args.limit]
    todo = [(n, t) for (n, t) in pairs if n not in done]
    print(f"Sweeping {len(todo)} delivery-pattern CP-NEW templates "
          f"({len(all_paths)} total, {len(done)} cached, {len(all_paths) - len(pairs)} skipped non-delivery)",
          flush=True)

    if not kit_alive():
        print("Kit not alive, launching...", flush=True)
        if not await launch_kit():
            print("Kit launch failed — abort"); return

    t0 = time.time()
    pass_n = fail_n = exc_n = 0
    with out_path.open("a") as f_out:
        for i, (name, tpl) in enumerate(todo, 1):
            if not kit_alive():
                print(f"  Kit not alive, restarting...", flush=True)
                if not await restart_kit():
                    print(f"  Kit restart FAILED — skip {name}"); continue
            t_start = time.time()
            dur_s = float((tpl.get("simulate_args") or {}).get("duration_s", 60))
            timeout_s = dur_s + args.timeout_margin
            print(f"[{i}/{len(todo)}] {name} (dur={dur_s}s, t/o={timeout_s}s) ...", end=" ", flush=True)
            try:
                rec = await asyncio.wait_for(observe_one(name), timeout=timeout_s)
            except asyncio.TimeoutError:
                rec = {"exception": f"OBSERVE_TIMEOUT_{timeout_s}s"}
            except Exception as e:
                rec = {"exception": f"OUTER_EXC:{type(e).__name__}:{str(e)[:80]}"}
            elapsed = time.time() - t_start
            rec["template"] = name
            rec["_elapsed_s"] = round(elapsed, 1)
            rec["_pattern_hint"] = (tpl.get("intent") or {}).get("pattern_hint", "")
            status = gate_status(rec)
            rec["_function_gate"] = status
            f_out.write(json.dumps(rec, default=str) + "\n"); f_out.flush()
            verdict = "PASS" if status["success"] else "FAIL"
            print(f"{verdict} ({status['reason']}) [{elapsed:.1f}s]", flush=True)
            if status["success"]: pass_n += 1
            elif rec.get("exception"): exc_n += 1
            else: fail_n += 1
            # Kit restart cadence
            if i % args.restart_every == 0 and i < len(todo):
                print("  --- Kit restart ---", flush=True)
                await restart_kit()

    total_min = (time.time() - t0) / 60
    print(f"\n=== FINAL ===")
    print(f"Pass: {pass_n}/{len(todo)}  ({100*pass_n/max(len(todo),1):.1f}%)")
    print(f"Fail: {fail_n}  Exception: {exc_n}")
    print(f"Total time: {total_min:.1f} min")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
