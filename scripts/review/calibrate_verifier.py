"""Calibrate new verifier (cube_on_target) against Anton's yes/no ground-truth.

For each template Anton tagged yes/no (skip partial, skip skip):
  1. Reset + build + settle + simulate_traversal_check (with new shadow fields)
  2. Record: success (old), cube_on_target (new), at_rest, cube_speed
  3. Compare to Anton's tag

Output: workspace/qa_runs/verifier_calibration.jsonl
       + summary printed at end: agreement % for old vs new metric.

If new agreement >= 90%, recommend changing `success` semantics.
"""
import asyncio, json, sys, time
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext"); sys.path.insert(0, str(REPO))

OUT = REPO/"workspace/qa_runs/verifier_calibration.jsonl"

def load_ground_truth():
    """Return {name: tag} for Anton's yes/no tags (latest per template)."""
    tags = {}
    for line in (REPO/"workspace/qa_runs/review_logs/human_tags.jsonl").open():
        r = json.loads(line)
        if r["tag"] in ("yes", "no"):
            tags[r["template"]] = r["tag"]
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
    except Exception as e: rec["exception"] = f"reset_exc:{type(e).__name__}"; return rec

    try:
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"):
            rec["exception"] = "BUILD_FAIL"
            rec["errors_head"] = "; ".join(str(e)[:200] for e in (b.get("errors") or [])[:2])[:400]
            return rec
    except asyncio.TimeoutError: rec["exception"] = "BUILD_TIMEOUT"; return rec
    except Exception as e: rec["exception"] = f"BUILD_EXC:{type(e).__name__}"; return rec
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except: pass

    sa = tpl.get("simulate_args") or {}
    fg = {"target_path": sa.get("target_path"), "duration_s": sa.get("duration_s", 60)}
    if sa.get("cube_path"): fg["cube_path"] = sa["cube_path"]
    if sa.get("cube_paths"): fg["cube_paths"] = sa["cube_paths"]
    for opt in ("xy_tolerance","rest_speed_threshold","min_cubes_delivered","per_bin_expected","routed_target_paths"):
        if opt in sa: fg[opt] = sa[opt]
    try:
        r = await asyncio.wait_for(execute_tool_call("simulate_traversal_check", fg), timeout=900)
        out = (r.get("output") or "").strip()
        jl = [l for l in out.splitlines() if l.strip().startswith("{")]
        if not jl:
            rec["exception"] = "NO_RESULT"
            rec["errors_head"] = (r.get("output") or "")[:300]
            return rec
        d = json.loads(jl[-1])
        rec["success"] = bool(d.get("success"))
        rec["cube_on_target"] = bool(d.get("cube_on_target"))
        rec["cube_ever_in_target_xy"] = bool(d.get("cube_ever_in_target_xy"))
        rec["in_target_xy"] = d.get("in_target_xy")
        rec["above_floor"] = d.get("above_floor")
        rec["at_rest"] = d.get("at_rest")
        rec["cube_speed"] = d.get("cube_speed")
        rec["cube_support_path"] = d.get("cube_support_path")
        rec["cube_support_under_target"] = d.get("cube_support_under_target")
        rec["per_cube_support"] = d.get("per_cube_support")
    except asyncio.TimeoutError: rec["exception"] = "SIM_TIMEOUT"
    except Exception as e: rec["exception"] = f"SIM_EXC:{type(e).__name__}"
    return rec

async def main():
    OUT.write_text("")
    gt = load_ground_truth()
    print(f"Calibrating against {len(gt)} yes/no ground-truth tags", flush=True)
    yes_n = sum(1 for v in gt.values() if v == "yes")
    no_n = sum(1 for v in gt.values() if v == "no")
    print(f"  {yes_n} yes / {no_n} no", flush=True)

    results = []
    for i, (name, tag) in enumerate(sorted(gt.items()), 1):
        print(f"[{i}/{len(gt)}] {name} (anton: {tag})", flush=True)
        rec = await run_one(name)
        rec["anton_tag"] = tag
        results.append(rec)
        with OUT.open("a") as f: f.write(json.dumps(rec) + "\n")
        old = rec.get("success")
        new = rec.get("cube_on_target")
        agree_old = (tag == "yes") == (old is True)
        agree_new = (tag == "yes") == (new is True)
        marker = "✓" if agree_new else ("→" if agree_old and not agree_new else "✗")
        print(f"  old:success={old} new:cube_on_target={new}  support={rec.get('cube_support_path')}  {marker}", flush=True)

    # Agreement analysis
    valid = [r for r in results if r.get("anton_tag") in ("yes","no") and "exception" not in r]
    if not valid:
        print("\nNo valid results"); return
    old_agree = sum(1 for r in valid if (r["anton_tag"]=="yes") == bool(r.get("success")))
    new_agree = sum(1 for r in valid if (r["anton_tag"]=="yes") == bool(r.get("cube_on_target")))
    print(f"\nAGREEMENT (n={len(valid)})")
    print(f"  OLD success-field:        {old_agree}/{len(valid)} = {100*old_agree/len(valid):.1f}%")
    print(f"  NEW cube_on_target field: {new_agree}/{len(valid)} = {100*new_agree/len(valid):.1f}%")
    # Disagreement detail
    print("\nDISAGREEMENTS (NEW vs Anton):")
    for r in valid:
        a = r["anton_tag"]
        n = bool(r.get("cube_on_target"))
        if (a=="yes") != n:
            print(f"  {r['template']}: anton={a} cube_on_target={n} support={r.get('cube_support_path')}")

asyncio.run(main())
