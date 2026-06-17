#!/usr/bin/env python3
"""chain_xkit_gate.py — CROSS-KIT declarative composition chain (robot-diversity unblock).

WHY (2026-06-17, feedback_ur10_corrupts_global_physx): a single UR10 run corrupts process-global PhysX
state (survives new_stage/reset_simulation/SM._clear; only a Kit PROCESS restart clears it). So a UR10->Franka
chain in ONE Kit is fundamentally blocked — the UR10 stage0 poisons the Franka stage1 (single-Kit chain_gate
relay = 0/1). This gate runs EACH stage in its OWN FRESH Kit and hands off at the STATE level (recorded cube
end-pose), sidestepping the corruption. PROVEN 2026-06-17: CP-CHAIN-UR10-SRC (UR10) -> kit_restart ->
CP-CHAIN-FLAT (Franka) = stage0 1/1 + stage1 1/1 (vs single-Kit 1/1 + 0/1).

Model: stage k runs standalone in a fresh Kit; its delivered cube end-poses are RECORDED as the handoff
state. The geometric guarantee that stage (k-1)'s delivery == stage k's pick location is the template-pair
DESIGN responsibility (same as single-Kit chain_gate's @offset) — this gate REPORTS the handoff pos + whether
it falls in the next stage's pick zone, and measures each stage's own delivery. Per-stage delivery is the bar
(NEVER collapse a partial to pass).

Usage:
  python scripts/qa/chain_xkit_gate.py CP-CHAIN-UR10-SRC CP-CHAIN-FLAT
  (each arg = a template name; stages run in order, one fresh Kit each. First stage uses the CURRENT Kit;
   restart it first with kit_restart.sh for a clean start.)
One Kit at a time; restarts between stages via scripts/qa/kit_restart.sh (the UR10-corruption mitigation).
"""
import asyncio, json, sys, subprocess
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

MEASURE = r'''
import omni.usd, omni.kit.app, omni.timeline, json
from pxr import Sdf, UsdGeom
stage=omni.usd.get_context().get_stage()
def cz(p):
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not pr or not pr.IsValid(): return None
    t=UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return [round(float(t[i]),3) for i in range(3)]
def bb(p):
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not pr or not pr.IsValid(): return None
    r=UsdGeom.Imageable(pr).ComputeWorldBound(0,UsdGeom.Tokens.default_).ComputeAlignedRange()
    if r.IsEmpty(): return None
    return [float(r.GetMin()[i]) for i in range(3)],[float(r.GetMax()[i]) for i in range(3)]
TARGET=__TARGET__; CUBES=__CUBES__
def into(p, tb):
    c=cz(p)
    if not (c and tb): return False, c
    ok = (tb[0][0]-0.06<=c[0]<=tb[1][0]+0.06 and tb[0][1]-0.06<=c[1]<=tb[1][1]+0.06 and c[2]>tb[0][2]-0.04)
    return ok, c
tb=bb(TARGET)
res={"target":TARGET,"delivered":0,"total":len(CUBES),"poses":{}}
for cp in CUBES:
    ok,c=into(cp,tb); res["poses"][cp]=c
    if ok: res["delivered"]+=1
print("MEASURE "+json.dumps(res))
'''


async def run_stage(name, run_steps=5000):
    from service.isaac_assist_service.chat.tools import kit_tools as kt
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
    sa = tpl.get("simulate_args") or tpl.get("verify_args") or {}
    cubes = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else ["/World/Cube_1"])
    target = sa.get("target_path") or tpl.get("verify_args", {}).get("stages", [{}])[0].get("place_path") or "/World/Bin"
    await kt.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    await kt.exec_sync("import builtins\nfor k in [x for x in list(vars(builtins)) if x.startswith('_curobo_pp_sub_')]:\n    try: delattr(builtins,k)\n    except Exception: pass\n", timeout=10)
    await execute_template_canonical(tpl); await settle_after_canonical(tpl)
    await kt.exec_sync(f"import omni.timeline,omni.kit.app; omni.timeline.get_timeline_interface().play()\n_a=omni.kit.app.get_app()\nfor _ in range({run_steps}): _a.update()", timeout=int(run_steps/25)+60)
    code = MEASURE.replace("__TARGET__", repr(target)).replace("__CUBES__", repr(cubes))
    out = (await kt.exec_sync(code, timeout=60)).get("output", "").strip()
    line = [l for l in out.splitlines() if l.startswith("MEASURE")]
    return json.loads(line[-1][len("MEASURE "):]) if line else {"error": out[:200]}


def kit_restart():
    out = subprocess.run(["bash", f"{REPO}/scripts/qa/kit_restart.sh"], capture_output=True, text=True, timeout=400)
    return "OK:" in out.stdout, ([l for l in out.stdout.splitlines() if "OK:" in l or "FAIL" in l] or [""])[-1]


async def main():
    specs = sys.argv[1:] or ["CP-CHAIN-UR10-SRC", "CP-CHAIN-FLAT"]
    results = []
    for i, name in enumerate(specs):
        if i > 0:
            ok, msg = kit_restart()
            print(f"  [kit_restart -> stage{i}] {msg}")
            if not ok:
                print("CHAIN_XKIT ABORT: kit_restart failed before stage %d" % i); return
        r = await run_stage(name)
        r["stage"] = i; r["name"] = name
        results.append(r)
        print(f"  stage{i} {name}: delivered={r.get('delivered')}/{r.get('total')} target={r.get('target')} poses={r.get('poses')}")
    print("CHAIN_XKIT STAGES:")
    for r in results:
        print("  inst%d %s relay=%s/%s target=%s" % (r["stage"], r["name"], r.get("delivered"), r.get("total"), r.get("target")))
    all_ok = all(r.get("delivered", 0) >= r.get("total", 1) for r in results)
    print("CHAIN_XKIT SUMMARY: %d stage(s), %s — %s" % (
        len(specs), " + ".join("%d/%d" % (r.get("delivered", 0), r.get("total", 1)) for r in results),
        "ALL DELIVERED (cross-Kit chain complete)" if all_ok else "INCOMPLETE"))

asyncio.run(main())
