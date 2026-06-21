"""cell_throughput.py — MEASURED throughput grounding for a manufacturing cell (gotcha #8/#15).

Builds a cell, plays it with per-chunk delivery tracking (CHAIN_TRAJ), and reports the cell's
realized SIM throughput: the steady-state parts/min (deliveries / span between the FIRST and LAST
delivery — excludes startup ramp + idle tail) plus the window-average and the mean pick-place
cycle. This GROUNDS the honest "can this cell do 30/min?" answer with a MEASURED rate instead of
a guess or a typed-in cycle (which would break "as good as scene_eyes").

⚠️ This is SIM throughput (the cell's realized rate IN SIMULATION) — a proxy for the real world:
sim pick-place motion (cuRobo planning + careful approach) may run slower or faster than a real
arm. Use it DIRECTIONALLY (a cell measuring ~3/min cannot do 30/min) and state the sim caveat.
⚠️ Chunk resolution ~ chunk_steps/60 s (default 1000 steps -> ~16.7 s); the cycle estimate is
coarse for a single delivery but averages out across several. Single-arm cells only.

Usage:  python scripts/qa/cell_throughput.py CP-37
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/qa"))
os.environ["CHAIN_TRAJ"] = "1"  # enable the per-chunk delivery trajectory in _play_and_measure

from chain_xkit_gate import run_stage0  # noqa: E402

PHYSICS_DT = 1.0 / 60.0  # 60 Hz (pick_place _PHYSICS_DT_DEFAULT_S)


def _per_min(n: int, span_steps: int) -> float:
    if span_steps <= 0:
        return 0.0
    return n * 60.0 / (span_steps * PHYSICS_DT)


async def main() -> int:
    if len(sys.argv) < 2:
        print("usage: cell_throughput.py <CANONICAL>")
        return 2
    cell = sys.argv[1]
    print("⚠️  POSITION-PROXY (re-implemented MEASURE) — NOT a scene_eyes gold. It shows final positions only, never grip/convergence/feeding/topple/plan_fails. For the GOLD verdict run scene_eyes.py. (Anton: alltid alltid scene eyes)")
    chunk = int(os.environ.get("CELL_TP_CHUNK") or 300)  # finer than the 1000-step default -> ~5s resolution
    res = await run_stage0(cell, chunk=chunk)
    traj = res.get("traj") or []
    delivered = res.get("delivered", 0)
    total = res.get("total", 0)
    chunk_res_s = chunk * PHYSICS_DT

    if not traj:
        print("THROUGHPUT " + json.dumps({"cell": cell, "error": "no trajectory", "delivered": delivered}))
        return 1

    total_steps = traj[-1]["t"]
    avg = _per_min(delivered, total_steps)

    # Step-stamp each delivery: the chunk at which the cumulative delivered count first reached each
    # level. `seen` only increases (monotonic), so a cube that BOUNCES OUT after delivery (count drops)
    # is detected as peak_delivered > delivered -> the cell is unstable, flagged (adversarial audit #4).
    deliv_at: list[int] = []
    seen = 0
    for e in traj:
        d = int(e.get("delivered", 0))
        while seen < d:
            deliv_at.append(int(e["t"]))
            seen += 1
    peak_delivered = len(deliv_at)
    bounced_out = peak_delivered - delivered  # >0 means cubes left the target after first delivery

    if len(deliv_at) >= 2:
        span = deliv_at[-1] - deliv_at[0]
        sustained = _per_min(len(deliv_at) - 1, span)  # intervals BETWEEN first & last first-delivery
        cycles_s = [(deliv_at[i] - deliv_at[i - 1]) * PHYSICS_DT for i in range(1, len(deliv_at))]
        mean_cycle = sum(cycles_s) / len(cycles_s)
        # the cycle cannot be resolved finer than one chunk; if it pins at the floor, say so honestly
        cycle_at_floor = mean_cycle <= chunk_res_s * 1.01
    else:
        sustained = avg
        mean_cycle = None
        cycle_at_floor = False

    out = {
        "cell": cell,
        "delivered": delivered,
        "total_cubes": total,
        "peak_delivered": peak_delivered,
        "bounced_out": bounced_out,
        "window_s": round(total_steps * PHYSICS_DT, 1),
        "avg_per_min": round(avg, 2),
        "sustained_per_min": round(sustained, 2),
        "mean_cycle_s": round(mean_cycle, 1) if mean_cycle is not None else None,
        "chunk_resolution_s": round(chunk_res_s, 1),
        "cycle_at_resolution_floor": cycle_at_floor,
        "first_delivery_step": deliv_at[0] if deliv_at else None,
        "note": ("SIM throughput (proxy for real). sustained = first-deliveries / span; single-arm cell. "
                 + ("⚠️ mean_cycle is PINNED at the chunk-resolution floor — the true cycle is <= this; "
                    "rerun with smaller CELL_TP_CHUNK for a tighter number. " if cycle_at_floor else "")
                 + (f"⚠️ {bounced_out} cube(s) BOUNCED OUT after delivery (unstable cell). " if bounced_out > 0 else "")),
    }
    print("THROUGHPUT " + json.dumps(out))
    # honest feasibility grounding for common gotcha targets — quantify the multi-cell scale-up
    # (the gotcha #8/#15 expected answer is "single arm can't -> multi-cell"; ground HOW MANY cells).
    import math
    for tgt in (15, 30, 60):
        if sustained <= 0:
            verdict = "UNKNOWN (cell delivered nothing — fix the cell first)"
        elif sustained >= tgt:
            verdict = "FEASIBLE on this single cell"
        else:
            n_cells = math.ceil(tgt / sustained)
            verdict = f"INFEASIBLE single-cell -> ~{n_cells} parallel cells needed at this rate"
        print(f"  target {tgt}/min: {verdict} (measured sustained {sustained:.1f}/min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
