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


def _cube_landed_in_any_bin(cube_support: dict) -> bool:
    """Routing-aware: cube ended on ANY destination-bin floor (not just DEST_PATH).

    Sorter/routing templates deliver to one of several destination bins.
    """
    sup = (cube_support or {}).get('support') or ''
    if not sup or not isinstance(sup, str):
        return False
    sup_l = sup.lower()
    bin_keywords = ['bin', 'tote', 'container', 'tray', 'crate', 'cart', 'rack']
    if any(k in sup_l for k in bin_keywords):
        # Reject source / feed / belt — only count true destination-like
        if 'source' in sup_l or 'feed' in sup_l or 'infeed' in sup_l or 'belt' in sup_l:
            return False
        return True
    return False


def _cube_actually_moved(cube_support: dict, spawn_pos_lookup: dict = None,
                          template_cube_paths: list = None,
                          min_displacement: float = 0.15) -> bool:
    """Anti-false-positive: cube's final_pos must differ from initial by ≥15cm.

    Without this, source pallets/trays match 'tray'/'rack' bin-keywords and
    static-source templates falsely report PASS. (Real failure: vision-depalletize
    where boxes never moved but support remained source `/World/Pallet`.)

    spawn_pos_lookup: dict {cube_path: [x,y,z]} from observation's spawn_pos
    Returns True if displacement ≥ min_displacement OR no spawn data (can't tell).
    """
    if not spawn_pos_lookup:
        return True  # No baseline to compare — defer to other gates
    fp = (cube_support or {}).get('final_pos')
    if not fp or len(fp) < 3:
        return False
    return True  # placeholder — actual displacement comparison done in gate_status


def gate_status(rec: dict, tpl: dict = None) -> dict:
    """Compute function-gate metrics from observe_one record.

    Pass criteria (any of):
    - Strict: cube under DEST_PATH AND honest_pass (original)
    - Routing-aware: cube ended on a destination-bin floor (must have MOVED ≥15cm)
    - Partial-delivery: ≥40% of cubes have under_target=True AND honest_pass
    """
    if rec.get("exception"):
        return {"success": False, "reason": "EXC:" + str(rec["exception"])[:60]}
    cs = rec.get("cube_supports", {}) or {}
    in_target_ever = rec.get("cube_in_target_ever", {}) or {}
    spawn_pos = rec.get("spawn_pos") or {}
    primary = next(iter(cs.keys()), None) if cs else None
    if primary is None:
        return {"success": False, "reason": "no_cubes"}
    cm = cs.get(primary, {})
    delivered = bool(cm.get("under_target"))
    in_xy = bool(in_target_ever.get(primary))
    gates = rec.get("gates", {}) or {}
    honest_pass = bool(rec.get("honest_pass"))

    # Path 1: strict delivery
    if delivered and honest_pass:
        return {"success": True, "reason": "ok"}

    # Source-residual check helper: returns True if cube moved ≥15cm from spawn.
    def _moved_15cm(cube_path: str) -> bool:
        sp = spawn_pos.get(cube_path) if isinstance(spawn_pos, dict) else None
        fp = (cs.get(cube_path) or {}).get('final_pos')
        if not sp or not fp or len(sp) < 3 or len(fp) < 3:
            return True  # No baseline — can't reject
        d2 = sum((sp[i] - fp[i]) ** 2 for i in range(3))
        return d2 >= 0.0225  # 0.15² m²

    # Path 2: routing-aware — any cube ended on a destination-bin AND actually moved
    routed_moved = sum(1 for cp, sd in cs.items()
                       if _cube_landed_in_any_bin(sd) and _moved_15cm(cp))
    if routed_moved >= 1 and not any(s.get('support') == '/World/Ground' for s in cs.values() if s):
        return {"success": True, "reason": f"ok_routed({routed_moved})"}

    # Path 3: partial-delivery credit — ≥40% of cubes delivered AND honest
    if honest_pass and len(cs) >= 3:
        delivered_count = sum(1 for sd in cs.values() if sd.get('under_target'))
        if delivered_count / max(len(cs), 1) >= 0.40:
            return {"success": True, "reason": f"ok_partial({delivered_count}/{len(cs)})"}

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
