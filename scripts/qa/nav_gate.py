#!/usr/bin/env python3
"""nav_gate.py — base-goal function-gate for wheeled/mobile (Carter/AMR) templates.

The arm gate (simulate_traversal_check) is cube-centric and does not apply to
nav tasks. This is the mobile equivalent: build the template, play, step physics
(the SAME app.update() loop the arm gate uses), sample each robot BASE world pose
over time, and report whether it reached its nav_goal.

Reads the template's simulate_args:
  * single robot:  robot_path, nav_goal=[x,y]
  * FLEET (multi-AMR):  fleet=[{"robot_path": "...", "nav_goal": [x,y]}, ...]
  (optional) base_target_tolerance (default 0.20 m), duration_s (-> step budget).

Metrics per robot (honest — distrusts the form-gate "✓" mirage):
  reached_goal       base XY within tol of nav_goal at any sample (PRIMARY verdict)
  disp               straight-line base move from spawn (catches the navigate_to stub
                     / missing-spawn — disp~0 = robot never moved or never spawned)
  min_dist           closest XY approach
  stuck              base velocity ~0 across the last third
Fleet summary: n_spawned / n_moved (disp>0.1) / n_reached out of N.

Usage: nav_gate.py <TEMPLATE> [TEMPLATE2 ...]
"""
import asyncio, json, os, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPLS = sys.argv[1:] or ["CP-64"]


async def nav_gate(tpl_name):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical
    tpl = json.load(open(f"{REPO}/workspace/templates/{tpl_name}.json"))
    sa = tpl.get("simulate_args") or tpl.get("simulate_args_template") or {}
    tol = float(sa.get("base_target_tolerance", 0.20))
    dur = float(sa.get("duration_s", 60))
    nsteps = int(max(600, min(dur * 30, 5400)))  # ~30 app-updates/s, clamped
    # fleet: list of {robot_path, nav_goal}; fallback to single robot (backward-compat)
    fleet = sa.get("fleet")
    if not fleet:
        # Discover the robot path(s)+goal(s) from the template's navigate_to() calls (templates often omit
        # simulate_args.fleet/robot_path -> the old /World/Carter fallback false-negatives a robot spawned at
        # e.g. /World/AMR, cont.247). Fall back to /World/Carter only if no navigate_to is found.
        import re as _re
        _code = (tpl.get("code", "") or "") + "\n" + (tpl.get("code_template", "") or "")
        _navs = _re.findall(
            r'navigate_to\(\s*robot_path\s*=\s*["\']([^"\']+)["\'][^)]*?target_position\s*=\s*\[([^\]]+)\]',
            _code, _re.S)
        if _navs:
            fleet = []
            for _rp, _tp in _navs:
                try:
                    _xy = [float(x.strip()) for x in _tp.split(",")][:2]
                except Exception:
                    _xy = [0.0, 0.0]
                fleet.append({"robot_path": _rp, "nav_goal": _xy})
        else:
            fleet = [{"robot_path": sa.get("robot_path") or "/World/Carter",
                      "nav_goal": sa.get("nav_goal") or sa.get("target_position") or [0.0, 0.0]}]
    fleet_arg = [[f["robot_path"], float(f["nav_goal"][0]), float(f["nav_goal"][1])] for f in fleet]

    await kit_tools.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    # cont.319-L4: track a CARGO prim (the transported product) so the gate verifies it RODE with the AMR
    # (cargo_disp ~= base_disp) — makes nav_gate the unified L4 mobile-handoff transport gate. Detect from
    # simulate_args (or CARGO_PATH env). A cargo that stays put / falls => disp~0 or != base_disp => NOT transported.
    _cargo = os.environ.get("CARGO_PATH") or sa.get("cube_path") or (sa.get("source_paths") or [None])[0] \
             or (sa.get("cube_paths") or [None])[0]
    cargo_list = [_cargo] if _cargo else []

    r = await execute_template_canonical(tpl)
    build_err = (r.get("errors") or [])[:2]

    code = f'''
import omni.usd, omni.timeline, omni.kit.app, json as _j
from pxr import UsdGeom, UsdPhysics, Usd
stage = omni.usd.get_context().get_stage()
FLEET = _j.loads({json.dumps(fleet_arg)!r}); TOL = {tol}; N = {nsteps}
# physics moves the articulation ROOT LINK (/World/Carter/chassis_link), NOT the parent
# Xform — read the container and disp reads a false 0 while the robot drives metres.
def _artroot(rp):
    pr = stage.GetPrimAtPath(rp)
    if pr and pr.IsValid():
        # Prefer a prim PHYSICS actually translates (a rigid-body link) over a bare Xform that merely carries
        # ArticulationRootAPI -- some spawns put ArticulationRootAPI on BOTH the parent Xform AND the root
        # link (chassis_link); measuring the non-translating parent = false disp=0 (cont.247).
        _cands = [c for c in Usd.PrimRange(pr) if c.HasAPI(UsdPhysics.ArticulationRootAPI)]
        for c in _cands:
            if c.HasAPI(UsdPhysics.RigidBodyAPI): return c.GetPath().pathString
        if _cands: return _cands[0].GetPath().pathString
    return rp
def bpos(body):
    pr = stage.GetPrimAtPath(body)
    if not pr or not pr.IsValid(): return None
    t = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return [float(t[0]), float(t[1]), float(t[2])]
R = []
for path, gx, gy in FLEET:
    valid = bool(stage.GetPrimAtPath(path) and stage.GetPrimAtPath(path).IsValid())
    body = _artroot(path)
    R.append({{"path": path, "gx": gx, "gy": gy, "body": body, "valid": valid,
               "p0": bpos(body), "mind": 1e9, "reached": None, "last": None, "tail": []}})
CARGO = _j.loads({json.dumps(cargo_list)!r})   # cont.319-L4 cargo-transport tracking
CR = [{{"path": c, "valid": bool(stage.GetPrimAtPath(c) and stage.GetPrimAtPath(c).IsValid()),
        "p0": bpos(c), "last": None}} for c in CARGO]
tl = omni.timeline.get_timeline_interface(); tl.play()
app = omni.kit.app.get_app()
for i in range(N):
    app.update()
    if i % 15 == 0:
        for rr in R:
            p = bpos(rr["body"])
            if p:
                rr["last"] = p
                d = ((p[0]-rr["gx"])**2 + (p[1]-rr["gy"])**2) ** 0.5
                if d < rr["mind"]: rr["mind"] = d
                if d < TOL and rr["reached"] is None: rr["reached"] = i
                rr["tail"].append((round(p[0],3), round(p[1],3)))
        for cr in CR:
            cp = bpos(cr["path"])
            if cp: cr["last"] = cp
out = []
for rr in R:
    p0, p1 = rr["p0"], rr["last"]
    disp = round(((p1[0]-p0[0])**2 + (p1[1]-p0[1])**2) ** 0.5, 3) if (p0 and p1) else None
    tail = rr["tail"][-max(2, len(rr["tail"])//3):] if len(rr["tail"])>=6 else []
    stuck = False
    if tail:
        sx = max(s[0] for s in tail)-min(s[0] for s in tail); sy = max(s[1] for s in tail)-min(s[1] for s in tail)
        stuck = (sx < 0.02 and sy < 0.02)
    out.append({{"path": rr["path"], "body": rr["body"], "valid": rr["valid"],
                 "reached_goal": rr["reached"] is not None, "disp": disp,
                 "min_dist": round(rr["mind"],3) if rr["mind"]<1e8 else None,
                 "stuck": stuck, "p0": p0, "p1": p1}})
print("NAV_FLEET_JSON " + _j.dumps(out))
cargo_out = []
for cr in CR:
    c0, c1 = cr["p0"], cr["last"]
    cd = round(((c1[0]-c0[0])**2 + (c1[1]-c0[1])**2) ** 0.5, 3) if (c0 and c1) else None
    cargo_out.append({{"path": cr["path"], "valid": cr["valid"], "disp": cd, "p0": c0, "p1": c1}})
print("NAV_CARGO_JSON " + _j.dumps(cargo_out))
'''
    rr = await kit_tools.exec_sync(code, timeout=int(nsteps / 8) + 90)
    out = (rr.get("output") or "").strip()
    line = next((l for l in out.splitlines() if l.startswith("NAV_FLEET_JSON")), None)
    if not line:
        print(f"{tpl_name}: NO_NAV_LINE build_err={build_err} :: {(rr.get('error') or out)[:200]}")
        return
    robots = json.loads(line[len("NAV_FLEET_JSON "):])
    n = len(robots)
    n_spawned = sum(1 for d in robots if d["valid"])
    n_moved = sum(1 for d in robots if (d["disp"] or 0) > 0.1)
    n_reached = sum(1 for d in robots if d["reached_goal"])
    allp = (n_reached == n)
    print(f"{tpl_name}: NAV fleet={n} spawned={n_spawned} moved={n_moved} reached={n_reached}/{n} "
          f"success={allp} build_err={build_err}")
    for d in robots:
        print(f"  {d['path']}: spawned={d['valid']} disp={d['disp']} min_dist={d['min_dist']} "
              f"reached={d['reached_goal']} stuck={d['stuck']}")
    # cont.319-L4: cargo-transport verdict — a product RODE with the AMR iff its disp ~= the base disp
    # (and the base actually moved). cargo_disp~0 while base moved = product left behind (NOT transported).
    cline = next((l for l in out.splitlines() if l.startswith("NAV_CARGO_JSON")), None)
    cargo = json.loads(cline[len("NAV_CARGO_JSON "):]) if cline else []
    base_disp = max((d["disp"] or 0) for d in robots) if robots else 0.0
    cargo_verdict = []
    for c in cargo:
        rode = bool(c["disp"] is not None and base_disp > 0.3 and c["disp"] > 0.3
                    and abs(c["disp"] - base_disp) <= 0.5)
        cargo_verdict.append({**c, "base_disp": round(base_disp, 3), "rode": rode})
        print(f"  CARGO {c['path']}: disp={c['disp']} base_disp={round(base_disp,3)} -> "
              f"{'RODE with AMR (transported)' if rode else 'did NOT transport (left behind / fell)'}")
    print("NAV_GATE_FULL=" + json.dumps({"template": tpl_name, "robots": robots, "cargo": cargo_verdict,
          "n": n, "n_spawned": n_spawned, "n_moved": n_moved, "n_reached": n_reached,
          "success": allp, "build_err": build_err}))


async def main():
    for t in TPLS:
        try:
            await nav_gate(t)
        except Exception as e:
            print(f"{t}: EXC {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    asyncio.run(main())
