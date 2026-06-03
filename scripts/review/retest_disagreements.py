"""After calibration sweep: re-test only the disagreement templates with the
chain-recursion verifier (added 2026-05-20). Reads workspace/qa_runs/verifier_calibration.jsonl,
identifies (anton=yes, new=False) and (anton=no, new=True) rows, re-tests
them against the updated diagnostics.py, and reports new agreement.
"""
import asyncio, json, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))

OUT = REPO/"workspace/qa_runs/retest_disagreements.jsonl"

def find_disagreements():
    recs = [json.loads(l) for l in (REPO/"workspace/qa_runs/verifier_calibration.jsonl").open()]
    out = []
    for r in recs:
        if r.get("exception"): continue
        a = r["anton_tag"]
        n = bool(r.get("cube_on_target"))
        if (a == "yes") != n:
            out.append((r["template"], a, n, r.get("cube_support_path")))
    return out

async def run_one(name):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    from service.isaac_assist_service.chat.tools.tool_executor import execute_tool_call

    tpl = json.loads((REPO/f"workspace/templates/{name}.json").read_text())
    code = "import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\nstage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n"
    rec = {"template": name}
    try:
        r = await kit_tools.exec_sync(code, timeout=20)
        if not r.get("success"): rec["exception"] = "reset_fail"; return rec
    except: rec["exception"] = "reset_exc"; return rec
    try:
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"): rec["exception"] = "BUILD_FAIL"; return rec
    except: rec["exception"] = "BUILD_EXC"; return rec
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except: pass

    sa = tpl.get("simulate_args") or {}
    fg = {"target_path": sa.get("target_path"), "duration_s": sa.get("duration_s", 60)}
    if sa.get("cube_path"): fg["cube_path"] = sa["cube_path"]
    if sa.get("cube_paths"): fg["cube_paths"] = sa["cube_paths"]
    for opt in ("xy_tolerance","rest_speed_threshold"):
        if opt in sa: fg[opt] = sa[opt]
    try:
        r = await asyncio.wait_for(execute_tool_call("simulate_traversal_check", fg), timeout=900)
        out = (r.get("output") or "").strip()
        jl = [l for l in out.splitlines() if l.strip().startswith("{")]
        if jl:
            d = json.loads(jl[-1])
            rec["cube_on_target"] = bool(d.get("cube_on_target"))
            rec["cube_support_path"] = d.get("cube_support_path")
            rec["per_cube_support"] = d.get("per_cube_support")
    except: pass
    return rec

async def main():
    OUT.write_text("")
    disagreements = find_disagreements()
    print(f"Re-testing {len(disagreements)} disagreement templates with chain-recursion verifier", flush=True)
    for name, anton, old_new, support in disagreements:
        print(f"  {name}: anton={anton} old_new={old_new} (support={support})", flush=True)

    flipped = 0
    for i, (name, anton, old_new, _) in enumerate(disagreements, 1):
        print(f"[{i}/{len(disagreements)}] {name}", flush=True)
        rec = await run_one(name)
        rec["anton_tag"] = anton
        rec["old_new_result"] = old_new
        with OUT.open("a") as f: f.write(json.dumps(rec) + "\n")
        new_new = rec.get("cube_on_target")
        agree_old = anton == ("yes" if old_new else "no")
        agree_new = anton == ("yes" if new_new else "no")
        marker = "FLIP→OK" if agree_new and not agree_old else ("STILL_OK" if agree_new and agree_old else "STILL_BAD" if not agree_new and not agree_old else "FLIP→BAD")
        if not agree_old and agree_new: flipped += 1
        print(f"  before:cube_on_target={old_new} after:cube_on_target={new_new} support={rec.get('cube_support_path')} → {marker}", flush=True)
    print(f"\nDONE. {flipped}/{len(disagreements)} flipped from disagreement to agreement after chain-fix.", flush=True)

asyncio.run(main())
