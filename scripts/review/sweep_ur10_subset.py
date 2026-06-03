"""Run scene_observer against the 10 UR10 templates suspected fixed by
the home_joints handler patch (2026-05-21 06:45). Uses the same observe_one
from sweep_all_rewritten.py.

Output: workspace/qa_runs/scene_observer_ur10_postfix.jsonl
"""
import asyncio, json, sys, time
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

from review.sweep_all_rewritten import observe_one, kit_alive, restart_kit

OUT = REPO/"workspace/qa_runs/scene_observer_ur10_postfix.jsonl"
TARGETS = ["CP-69", "CP-70", "CP-71", "CP-72", "CP-73",
           "CP-75", "CP-78", "CP-79", "CP-82", "CP-86"]


async def main():
    OUT.write_text("")
    print(f"UR10 post-fix sweep: {len(TARGETS)} templates", flush=True)
    if not kit_alive():
        print("Kit down, restarting...", flush=True)
        if not await restart_kit():
            print("RESTART_FAILED"); return
    n_pass = 0
    t0 = time.time()
    for i, name in enumerate(TARGETS, 1):
        if not kit_alive():
            print(f"[{i}] Kit drifted, restarting before {name}...", flush=True)
            if not await restart_kit():
                print(f"[{i}] {name} SKIP (restart failed)"); continue
        ts = time.time()
        print(f"[{i}/{len(TARGETS)}] {name} starting...", flush=True)
        rec = await observe_one(name)
        rec["template"] = name
        rec["elapsed_s"] = round(time.time() - ts, 1)
        with OUT.open("a") as f:
            f.write(json.dumps(rec, default=str)+"\n")
        gates = rec.get("gates", {})
        verdict = "HONEST_PASS" if rec.get("honest_pass") else "FAIL"
        exc = rec.get("exception", "")
        ve = (rec.get("virtual_eyes") or {})
        patterns = [n for n, p in (ve.get("patterns") or {}).items() if p.get("detected")]
        # NEW: surface cuRobo errs from engine_data if present
        eng = rec.get("engine_data") or {}
        ctrl = eng.get("ctrl_state") or {}
        pos_err = ctrl.get("ctrl:curobo_pos_err_last")
        ori_err = ctrl.get("ctrl:curobo_ori_err_last")
        print(f"  → {verdict} ({rec['elapsed_s']}s)  exc={exc}  patterns={patterns}  curobo_pos_err={pos_err} ori_err={ori_err}", flush=True)
        if rec.get("honest_pass"): n_pass += 1
    print(f"\nDONE: {n_pass}/{len(TARGETS)} HONEST_PASS in {round(time.time()-t0)}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
