"""Run scene_observer on all rewritten templates after the agents finish.
Targets: every template with a *_rewrite_bak file (= touched by agents).
Output: workspace/qa_runs/sweep_all_rewritten.jsonl (one row per template,
HONEST_PASS verdict + 5-gate breakdown).
"""
import asyncio, json, os, subprocess, sys, glob, math, time
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))
HEALTH = "http://127.0.0.1:8001/health"; LAUNCH = "/home/anton/.claude/diag/launch_kit_headless.sh"
OUT = REPO/"workspace/qa_runs/sweep_all_rewritten.jsonl"

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

# Same OBSERVE_CODE as scene_observer.py
OBSERVE_CODE_TPL = open(REPO/"scripts/review/scene_observer.py").read()
# Extract the OBSERVE_CODE string literal
import re
m = re.search(r'OBSERVE_CODE = r"""\n(.+?)\n"""', OBSERVE_CODE_TPL, re.DOTALL)
if not m:
    print("Could not extract OBSERVE_CODE from scene_observer.py"); sys.exit(1)
OBSERVE_CODE = m.group(1)

async def observe_one(name):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    tpl_path = REPO/f"workspace/templates/{name}.json"
    if not tpl_path.exists(): return {"exception":"NOT_FOUND"}
    try:
        tpl = json.loads(tpl_path.read_text())
    except Exception as e:
        return {"exception": f"JSON_LOAD: {e}"}
    sa = tpl.get("simulate_args") or {}
    rd = tpl.get("role_defaults") or {}
    pr = rd.get("primary_robot") or rd.get("amr") or {}
    robot_path = pr.get("path", "/World/Robot")
    rc = pr.get("class") or ""
    # 2026-05-22 audit-fix #4: cuRobo handler uses tool0 for UR family — match here
    ee_link = ("panda_hand" if "franka" in rc.lower() else "tool0")
    cube_paths = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
    target_path = sa.get("target_path", "")
    color_routing = sa.get("color_routing") or sa.get("destination_map") or {}
    duration_s = float(sa.get("duration_s", 60))
    if not target_path or not cube_paths:
        return {"exception":"missing_simulate_args"}
    await kit_tools.exec_sync("import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
    try:
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"):
            return {"exception":"BUILD_FAIL", "errors_head": "; ".join(str(e)[:160] for e in (b.get("errors") or [])[:2])}
    except asyncio.TimeoutError: return {"exception":"BUILD_TIMEOUT"}
    except Exception as e: return {"exception":f"BUILD_EXC:{type(e).__name__}"}
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except: pass
    # 2026-05-22: compute template-intent scene elements for missing_scene_element detector (#38)
    try:
        from scripts.review.scene_observer import _extract_expected_scene_elements
        expected_scene_elements = _extract_expected_scene_elements(tpl)
    except Exception:
        expected_scene_elements = []
    code = OBSERVE_CODE.format(robot_path=robot_path, ee_link=ee_link,
                                cube_paths=cube_paths, target_path=target_path,
                                color_routing=color_routing,
                                duration_s=duration_s, table_top_z=0.75,
                                require_upright=bool(sa.get("require_upright", False)),
                                upright_dot_threshold=float(sa.get("upright_dot_threshold", 0.85)),
                                expected_scene_elements=expected_scene_elements)
    try:
        # 2026-05-30: scale exec wall-timeout with cube count. Big-N multi-cube (9-10 cubes)
        # need >450s WALL to complete duration_s SIM-time (blocking plan_pose freezes sim-time
        # while wall burns + wall-paced grip dwells) — the flat duration_s+180 timed them out
        # (SIM_TIMEOUT, no verdict) before the robot finished. +60s/cube above 4 gives margin.
        _exec_to = duration_s + 300 + 60 * max(0, len(cube_paths) - 4)  # base 300 (was 180): high-motion 2-stage/multi-robot templates (machine-tender, assembly-4robot) overrun a 180 base even at n<=4
        r = await asyncio.wait_for(kit_tools.exec_sync(code, timeout=_exec_to), timeout=_exec_to + 20)
        out = (r.get("output") or "").strip()
        b_i = out.find("OBSERVE_BEGIN"); e_i = out.find("OBSERVE_END")
        if b_i < 0 or e_i < 0: return {"exception":"PARSE_FAIL"}
        data = json.loads(out[b_i + len("OBSERVE_BEGIN"):e_i].strip())
        return data
    except asyncio.TimeoutError: return {"exception":"SIM_TIMEOUT"}
    except Exception as e: return {"exception":f"SIM_EXC:{type(e).__name__}"}

async def main():
    OUT.write_text("")
    # Find all rewritten templates (have *_rewrite_bak)
    bk = glob.glob(str(REPO/"workspace/templates/*_rewrite_bak"))
    bk += glob.glob(str(REPO/"workspace/templates/*_bak"))
    targets = sorted(set([Path(b).stem.split(".json")[0] for b in bk]))
    print(f"Sweeping {len(targets)} rewritten templates", flush=True)
    if not kit_alive():
        if not await launch_kit(): return
    n_pass = 0
    for i, name in enumerate(targets, 1):
        if not kit_alive():
            if not await restart_kit(): break
        print(f"[{i}/{len(targets)}] {name}", flush=True)
        rec = await observe_one(name)
        rec["template"] = name
        with OUT.open("a") as f: f.write(json.dumps(rec, default=str)+"\n")
        if rec.get("honest_pass"): n_pass += 1
        gates = rec.get("gates", {})
        verdict = "HONEST_PASS" if rec.get("honest_pass") else "FAIL"
        exc = rec.get("exception")
        print(f"  {verdict} gates={sum(1 for v in gates.values() if v)}/{len(gates) or 5} exc={exc}", flush=True)
        if i % 4 == 0 and i < len(targets): await restart_kit()
    print(f"\nFINAL: {n_pass}/{len(targets)} HONEST_PASS")

if __name__ == "__main__":
    asyncio.run(main())
