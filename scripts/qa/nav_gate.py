#!/usr/bin/env python3
"""nav_gate.py — base-goal function-gate for wheeled/mobile (Carter/AMR) templates.

The arm gate (simulate_traversal_check) is cube-centric and does not apply to
nav tasks. This is the mobile equivalent: build the template, play, step physics
(the SAME app.update() loop the arm gate uses), sample the robot BASE world pose
over time, and report whether it reached nav_goal.

Reads the template's simulate_args: robot_path, nav_goal=[x,y], (optional)
base_target_tolerance (default 0.20 m), duration_s (-> step budget).

Metrics (honest — distrusts the form-gate "✓" mirage):
  ever_reached_goal  base XY within tol of nav_goal at any sample (PRIMARY verdict)
  displacement_total straight-line base move from spawn (catches the navigate_to stub)
  min_dist_to_goal   closest XY approach
  reached_step       first sample index within tol
  stuck              base velocity ~0 and dist unchanged across the last third

Usage: nav_gate.py <TEMPLATE> [TEMPLATE2 ...]
A template with displacement_total ~0 = robot never moved (e.g. the navigate_to
drive-stub or position-locked wheels) -> GATE FAIL, no false positive.
"""
import asyncio, json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPLS = sys.argv[1:] or ["CP-64"]


async def nav_gate(tpl_name):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical
    tpl = json.load(open(f"{REPO}/workspace/templates/{tpl_name}.json"))
    sa = tpl.get("simulate_args") or tpl.get("simulate_args_template") or {}
    robot = sa.get("robot_path") or "/World/Carter"
    goal = sa.get("nav_goal") or sa.get("target_position") or [0.0, 0.0]
    tol = float(sa.get("base_target_tolerance", 0.20))
    dur = float(sa.get("duration_s", 60))
    nsteps = int(max(600, min(dur * 30, 5400)))  # ~30 app-updates/s, clamped

    await kit_tools.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    r = await execute_template_canonical(tpl)
    build_err = (r.get("errors") or [])[:2]

    code = f'''
import omni.usd, omni.timeline, omni.kit.app
from pxr import UsdGeom
stage = omni.usd.get_context().get_stage()
ROBOT = {robot!r}; GX, GY = {float(goal[0])}, {float(goal[1])}; TOL = {tol}; N = {nsteps}
def bpos():
    pr = stage.GetPrimAtPath(ROBOT)
    if not pr or not pr.IsValid(): return None
    t = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return [float(t[0]), float(t[1]), float(t[2])]
valid = bool(stage.GetPrimAtPath(ROBOT) and stage.GetPrimAtPath(ROBOT).IsValid())
tl = omni.timeline.get_timeline_interface(); tl.play()
app = omni.kit.app.get_app()
p0 = bpos(); samples = []; reached = None; mind = 1e9
for i in range(N):
    app.update()
    if i % 15 == 0:
        p = bpos()
        if p:
            d = ((p[0]-GX)**2 + (p[1]-GY)**2) ** 0.5
            if d < mind: mind = d
            if d < TOL and reached is None: reached = i
            samples.append((round(p[0],3), round(p[1],3)))
p1 = bpos()
disp = round(((p1[0]-p0[0])**2 + (p1[1]-p0[1])**2) ** 0.5, 3) if (p0 and p1) else None
# stuck: last third of samples within 2cm of each other
stuck = False
if len(samples) >= 6:
    tail = samples[-max(2, len(samples)//3):]
    sx = max(s[0] for s in tail) - min(s[0] for s in tail)
    sy = max(s[1] for s in tail) - min(s[1] for s in tail)
    stuck = (sx < 0.02 and sy < 0.02)
verdict = bool(reached is not None)
import json as _j
print("NAV_GATE_JSON " + _j.dumps({{
    "template": {tpl_name!r}, "robot_path": ROBOT, "nav_goal": [GX, GY], "tol": TOL,
    "robot_prim_valid": valid, "ever_reached_goal": verdict,
    "displacement_total": disp, "min_dist_to_goal": round(mind,3) if mind < 1e8 else None,
    "reached_step": reached, "stuck": stuck, "p0": p0, "p1": p1, "n_samples": len(samples),
    "success": verdict,
}}))
'''
    rr = await kit_tools.exec_sync(code, timeout=int(nsteps / 8) + 90)
    out = (rr.get("output") or "").strip()
    line = next((l for l in out.splitlines() if l.startswith("NAV_GATE_JSON")), None)
    if line:
        d = json.loads(line[len("NAV_GATE_JSON "):])
        print(f"{tpl_name}: NAV success={d['success']} reached_goal={d['ever_reached_goal']} "
              f"disp={d['displacement_total']} min_dist={d['min_dist_to_goal']} stuck={d['stuck']} "
              f"build_err={build_err}")
        print("NAV_GATE_FULL=" + json.dumps(d))
    else:
        print(f"{tpl_name}: NO_NAV_LINE build_err={build_err} :: {(rr.get('error') or out)[:200]}")


async def main():
    for t in TPLS:
        try:
            await nav_gate(t)
        except Exception as e:
            print(f"{t}: EXC {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    asyncio.run(main())
