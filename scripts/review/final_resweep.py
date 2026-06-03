"""Final re-sweep with all fixes applied (Phase 4 FJ-distance + Phase 5 conveyor_track
CollisionAPI + new diagnostics chain-recursion). Targets the 37 templates that
failed in wp_strict2 plus the 9 disagreement templates — 46 total.

Records both old `success` (delivered/in_xy/at_rest/above_floor) and new
`cube_on_target` (raycast + chain) per template. Reports:
- new pass rate vs baseline
- agreement with Anton's tags for overlapping templates
- list of templates that flipped pass→fail or fail→pass after fixes

Output: workspace/qa_runs/final_resweep.jsonl
"""
import asyncio, json, os, subprocess, sys, time
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))
HEALTH = "http://127.0.0.1:8001/health"; LAUNCH = "/home/anton/.claude/diag/launch_kit_headless.sh"
OUT = REPO/"workspace/qa_runs/final_resweep.jsonl"

import urllib.request
def kit_alive():
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as r: return r.status == 200
    except: return False
def find_pids():
    try: return [int(p) for p in subprocess.check_output(["pgrep","-f","isaac_sim_with_assist"]).decode().split()]
    except: return []
async def launch_kit():
    subprocess.Popen(["bash", LAUNCH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    for _ in range(36):
        await asyncio.sleep(5)
        if kit_alive(): return True
    return False
async def restart_kit():
    for pid in find_pids():
        try: os.killpg(os.getpgid(pid), 9)
        except: pass
    await asyncio.sleep(4)
    return await launch_kit()

def collect_targets():
    """37 wp_strict2 failures + 9 calibration disagreements (dedup)."""
    seen = set()
    targets = []
    for line in (REPO/"workspace/qa_runs/function_gate_wp_strict2.jsonl").open():
        r = json.loads(line)
        if not r.get("delivered") and r["template"] not in seen:
            targets.append(r["template"]); seen.add(r["template"])
    for line in (REPO/"workspace/qa_runs/verifier_calibration.jsonl").open():
        r = json.loads(line)
        if r.get("exception"): continue
        a = r["anton_tag"]; n = bool(r.get("cube_on_target"))
        if (a == "yes") != n and r["template"] not in seen:
            targets.append(r["template"]); seen.add(r["template"])
    return targets

def load_anton_tags():
    tags = {}
    for line in (REPO/"workspace/qa_runs/review_logs/human_tags.jsonl").open():
        r = json.loads(line)
        if r["tag"] in ("yes","no","partial"): tags[r["template"]] = r["tag"]
    return tags

async def run_one(name):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    from service.isaac_assist_service.chat.tools.tool_executor import execute_tool_call

    tpl_path = REPO/f"workspace/templates/{name}.json"
    rec = {"template": name}
    if not tpl_path.exists(): rec["exception"] = "NOT_FOUND"; return rec
    tpl = json.loads(tpl_path.read_text())
    code = "import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n"
    try:
        r = await kit_tools.exec_sync(code, timeout=20)
        if not r.get("success"): rec["exception"] = "reset_fail"; return rec
    except: rec["exception"] = "reset_exc"; return rec
    try:
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"):
            rec["exception"] = "BUILD_FAIL"
            rec["errors_head"] = "; ".join(str(e)[:160] for e in (b.get("errors") or [])[:2])[:300]
            return rec
    except asyncio.TimeoutError: rec["exception"] = "BUILD_TIMEOUT"; return rec
    except Exception as e: rec["exception"] = f"BUILD_EXC:{type(e).__name__}"; return rec
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except: pass
    sa = tpl.get("simulate_args") or {}
    fg = {"target_path": sa.get("target_path"), "duration_s": sa.get("duration_s", 60)}
    if sa.get("cube_path"): fg["cube_path"] = sa["cube_path"]
    if sa.get("cube_paths"): fg["cube_paths"] = sa["cube_paths"]
    for opt in ("xy_tolerance","rest_speed_threshold","min_cubes_delivered"):
        if opt in sa: fg[opt] = sa[opt]
    try:
        r = await asyncio.wait_for(execute_tool_call("simulate_traversal_check", fg), timeout=900)
        out = (r.get("output") or "").strip()
        jl = [l for l in out.splitlines() if l.strip().startswith("{")]
        if jl:
            d = json.loads(jl[-1])
            rec["success"] = bool(d.get("success"))
            rec["cube_on_target"] = bool(d.get("cube_on_target"))
            rec["in_xy"] = d.get("in_target_xy")
            rec["at_rest"] = d.get("at_rest")
            rec["above_floor"] = d.get("above_floor")
            rec["cube_speed"] = d.get("cube_speed")
            rec["cube_support_path"] = d.get("cube_support_path")
        else: rec["exception"] = "NO_RESULT"
    except asyncio.TimeoutError: rec["exception"] = "SIM_TIMEOUT"
    except Exception as e: rec["exception"] = f"SIM_EXC:{type(e).__name__}"
    return rec

async def main():
    OUT.write_text("")
    if not kit_alive():
        if not await launch_kit(): print("Kit launch fail"); return
    targets = collect_targets()
    tags = load_anton_tags()
    print(f"Final re-sweep: {len(targets)} templates", flush=True)

    n_pass_old = 0; n_pass_new = 0; n_total = 0
    for i, name in enumerate(targets, 1):
        if not kit_alive():
            if not await restart_kit(): print("restart fail"); break
        print(f"[{i}/{len(targets)}] {name} (anton:{tags.get(name,'-')})", flush=True)
        rec = await run_one(name)
        rec["anton_tag"] = tags.get(name)
        with OUT.open("a") as f: f.write(json.dumps(rec) + "\n")
        n_total += 1
        if rec.get("success"): n_pass_old += 1
        if rec.get("cube_on_target"): n_pass_new += 1
        print(f"  OLD:success={rec.get('success')} NEW:cube_on_target={rec.get('cube_on_target')}  support={rec.get('cube_support_path')}  exc={rec.get('exception')}", flush=True)
        if i % 12 == 0 and i < len(targets):
            print(f"Kit-restart at checkpoint {i}", flush=True)
            await restart_kit()
    print(f"\nFINAL: OLD pass {n_pass_old}/{n_total} = {100*n_pass_old/max(n_total,1):.1f}%", flush=True)
    print(f"FINAL: NEW pass {n_pass_new}/{n_total} = {100*n_pass_new/max(n_total,1):.1f}%", flush=True)

asyncio.run(main())
