"""Find failure → optimal stiffness threshold per (material, mass) via walk-up.

For each (material_mu, cube_mass) combo:
  1. Walk stiffness upward through STIFF_LADDER
  2. First PASS = failure_threshold (just-passing)
  3. Optimal = failure_threshold × SAFETY_FACTOR
  4. Compare to analytical formula compute_optimal_grip()

Unlike rl_tune_v2.py, this script ACTUALLY applies stiffness/mu/mass to the
scene via apply_scene_params (called between scene-build and observation).

Usage:
  python scripts/friction_paradigm/find_grip_threshold.py

Output:
  workspace/friction_tuning/grip_threshold/grip_table_<timestamp>.csv
  workspace/friction_tuning/grip_threshold/grip_table_<timestamp>.md (analytical comparison)
"""
import asyncio, json, time, sys, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.review.sweep_all_rewritten import observe_one, kit_alive, restart_kit
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.tools.handlers.grip_config import compute_optimal_grip

OUT_DIR = REPO / "workspace/friction_tuning/grip_threshold"
OUT_DIR.mkdir(parents=True, exist_ok=True)

KIT_EXEC = "http://127.0.0.1:8001/exec_sync"

# Stiffness ladder — realistic Franka range (default in handler is 10000)
# Below ~50 N/m = obviously too weak; above ~20k = approaching impulse-spike territory.
STIFF_LADDER = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]

# Material datasheet mu (cube friction coefficient)
MATERIALS = {
    "rubber":  0.9,
    "plastic": 0.4,
    "metal":   0.5,
    "glass":   0.2,
}

# Mass variants to test (kg)
MASSES = [0.05, 0.1, 0.3]

SAFETY_FACTOR = 1.5  # multiplier above failure-threshold for optimal


def apply_scene_params(mu: float, fstiff: float, cube_mass: float,
                        max_force: float = 70.0) -> dict:
    """Apply mu / finger-stiffness / finger-maxForce / cube-mass via USD-patch.

    Isaac panda default has maxForce=7.2N on finger drives — caps grip regardless
    of stiffness. Must explicitly raise maxForce to allow heavier grips.
    """
    code = f"""
import omni.usd
from pxr import Sdf, UsdPhysics
stage = omni.usd.get_context().get_stage()

# Friction on cubes
applied_mu = 0
for cp in ['/World/Cube_M', '/World/Cube_L', '/World/Cube_R']:
    p = stage.GetPrimAtPath(Sdf.Path(cp))
    if not p: continue
    rel = p.GetRelationship('material:binding:physics')
    if rel:
        for mp in rel.GetTargets():
            m = stage.GetPrimAtPath(mp)
            if m:
                pm = UsdPhysics.MaterialAPI.Apply(m)
                pm.GetStaticFrictionAttr().Set({mu})
                pm.GetDynamicFrictionAttr().Set({mu})
                applied_mu += 1

# Finger drive: stiffness + maxForce
applied_drive = 0
for jp in ['/World/Franka/panda_hand/panda_finger_joint1', '/World/Franka/panda_hand/panda_finger_joint2']:
    p = stage.GetPrimAtPath(Sdf.Path(jp))
    if p and p.IsValid():
        try:
            drv = UsdPhysics.DriveAPI.Apply(p, 'linear')
            drv.GetStiffnessAttr().Set({fstiff})
            mfa = drv.GetMaxForceAttr() or drv.CreateMaxForceAttr()
            mfa.Set({max_force})
            applied_drive += 1
        except Exception as e:
            print(f'drive-set fail {{jp}}: {{e}}')

# Cube mass
applied_mass = 0
for cp in ['/World/Cube_M', '/World/Cube_L', '/World/Cube_R']:
    p = stage.GetPrimAtPath(Sdf.Path(cp))
    if p and p.IsValid():
        try:
            ma = p.GetAttribute('physics:mass')
            if ma:
                ma.Set({cube_mass})
                applied_mass += 1
        except Exception as e:
            print(f'mass-set fail {{cp}}: {{e}}')

print(f'APPLIED mu={mu} (n={{applied_mu}})  stiff={fstiff} maxF={max_force} (n={{applied_drive}})  mass={cube_mass} (n={{applied_mass}})')
"""
    req = urllib.request.Request(
        KIT_EXEC,
        data=json.dumps({"code": code, "timeout": 20}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def iter_passes(rec: dict) -> bool:
    """Pass = cube delivered AND on bin floor AND adjacent cubes not nudged."""
    if rec.get("exception"):
        return False
    cs = rec.get("cube_supports", {})
    main = cs.get("/World/Cube_M", {})
    if not main.get("under_target"):
        return False
    # Adjacent shift < 1mm (precision criterion)
    fl = cs.get("/World/Cube_L", {}).get("final_pos")
    fr = cs.get("/World/Cube_R", {}).get("final_pos")
    if fl and fl[0] < -0.3504 - 0.001:  # Cube_L moved left
        return False
    if fr and fr[0] > -0.2494 + 0.001:  # Cube_R moved right
        return False
    return True


def kit_exec_http(code: str, timeout: int = 60) -> dict:
    """Direct HTTP exec_sync — avoids kit_tools.exec_sync event-loop conflicts."""
    req = urllib.request.Request(
        KIT_EXEC,
        data=json.dumps({"code": code, "timeout": timeout}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())


async def run_one(mu: float, stiff: float, mass: float, iter_id: str, run_dir: Path) -> dict:
    """Build scene via execute_template_canonical, apply params, run OBSERVE_CODE.

    Uses kit_tools.exec_sync now that scene_observer.py is guarded with
    if __name__ == "__main__" (no module-load asyncio.run nesting).
    """
    iter_dir = run_dir / f"iter_{iter_id}"
    iter_dir.mkdir(exist_ok=True)
    print(f"  [{iter_id}] mu={mu} stiff={stiff} mass={mass} ...", end=" ", flush=True)

    if not kit_alive():
        if not await restart_kit():
            return {"exception": "KIT_RESTART_FAIL"}

    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical, settle_after_canonical)
    tpl_path = REPO / "workspace/templates/CP-PRECISION-3CUBE.json"
    tpl = json.loads(tpl_path.read_text())
    sa = tpl["simulate_args"]

    # 1. Fresh stage
    await kit_tools.exec_sync(
        "import omni.usd\nctx=omni.usd.get_context()\nctx.new_stage()\n"
        "stage=ctx.get_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(stage,'/World')\n",
        timeout=20,
    )

    # 2. Build scene via template canonical (full tool-call dispatch)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        print(f"BUILD_FAIL: {b.get('errors', [])[:1]}")
        return {"exception": "BUILD_FAIL"}

    # 3. Apply OUR params (override template defaults)
    apply_result = apply_scene_params(mu=mu, fstiff=stiff, cube_mass=mass)
    if not (apply_result.get("output") or "").strip().startswith("APPLIED"):
        print(f"APPLY_FAIL: {apply_result}")
        return {"exception": "APPLY_FAIL"}

    # 4. Settle then observe
    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception:
        pass

    from scripts.review.scene_observer import OBSERVE_CODE
    rd = tpl.get("role_defaults") or {}
    pr = rd.get("primary_robot") or {}
    robot_path = pr.get("path", "/World/Franka")
    ee_link = "panda_hand"
    cube_paths = sa.get("cube_paths") or [sa.get("cube_path")]
    target_path = sa.get("target_path", "")
    duration_s = float(sa.get("duration_s", 30))
    obs_code = OBSERVE_CODE.format(
        robot_path=robot_path, ee_link=ee_link,
        cube_paths=cube_paths, target_path=target_path,
        duration_s=duration_s, table_top_z=0.75,
        require_upright=False, upright_dot_threshold=0.85,
        expected_scene_elements=[],
    )
    r = await asyncio.wait_for(kit_tools.exec_sync(obs_code, timeout=duration_s + 60),
                                timeout=duration_s + 80)
    out = (r.get("output") or "").strip()
    b_i = out.find("OBSERVE_BEGIN")
    e_i = out.find("OBSERVE_END")
    if b_i < 0 or e_i < 0:
        print(f"PARSE_FAIL out_head={out[:200]!r}")
        return {"exception": "PARSE_FAIL"}
    rec = json.loads(out[b_i + len("OBSERVE_BEGIN"):e_i].strip())
    (iter_dir / "raw.jsonl").write_text(json.dumps(rec, default=str))
    passed = iter_passes(rec)
    print(f"{'PASS' if passed else 'FAIL'}")
    return {"passed": passed, "rec": rec}


async def walk_up_one_cell(material: str, mu: float, mass: float, run_dir: Path) -> dict:
    """For (material, mass): walk stiffness up, find first PASS."""
    print(f"\n=== {material} (mu={mu}) × mass={mass} ===", flush=True)
    history = []
    first_pass = None
    for stiff in STIFF_LADDER:
        iter_id = f"{material}_{mass:.2f}_{stiff}"
        r = await run_one(mu, stiff, mass, iter_id, run_dir)
        history.append({"stiff": stiff, "passed": r.get("passed", False), "exception": r.get("exception")})
        if r.get("passed"):
            first_pass = stiff
            break
    optimal = round(first_pass * SAFETY_FACTOR) if first_pass else None
    analytical = compute_optimal_grip(mass, mu)
    result = {
        "material": material, "mu": mu, "mass": mass,
        "first_pass_stiff": first_pass,
        "optimal_stiff": optimal,
        "analytical": analytical,
        "history": history,
    }
    print(f"  → first_pass={first_pass}  optimal={optimal}  analytical_stiff={analytical['stiffness']}")
    return result


async def main():
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = OUT_DIR / f"run_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run dir: {run_dir}")
    print(f"STIFF_LADDER: {STIFF_LADDER}")
    print(f"MATERIALS: {MATERIALS}")
    print(f"MASSES: {MASSES}")
    print(f"Total cells: {len(MATERIALS) * len(MASSES)} (max {len(MATERIALS)*len(MASSES)*len(STIFF_LADDER)} iter)\n")

    if not kit_alive():
        print("Kit not alive — abort. Start Kit RPC first.")
        return

    results = []
    for material, mu in MATERIALS.items():
        for mass in MASSES:
            r = await walk_up_one_cell(material, mu, mass, run_dir)
            results.append(r)
            (run_dir / "results.json").write_text(json.dumps(results, indent=2, default=str))

    # Write summary CSV + markdown
    csv_lines = ["material,mu,mass,first_pass_stiff,optimal_stiff,analytical_stiff,analytical_force,analytical_damping"]
    for r in results:
        a = r["analytical"]
        csv_lines.append(f"{r['material']},{r['mu']},{r['mass']},"
                         f"{r['first_pass_stiff'] or ''},{r['optimal_stiff'] or ''},"
                         f"{a['stiffness']},{a['grip_force_N']},{a['damping']}")
    (run_dir / "grip_table.csv").write_text("\n".join(csv_lines))

    md = ["# Grip threshold table\n", f"Date: {ts}\n",
          "| Material | mu  | mass (kg) | first_pass_stiff | optimal | analytical | ratio |",
          "|----------|-----|-----------|------------------|---------|------------|-------|"]
    for r in results:
        emp = r["optimal_stiff"]
        ana = r["analytical"]["stiffness"]
        ratio = f"{emp/ana:.2f}" if (emp and ana) else "—"
        md.append(f"| {r['material']} | {r['mu']} | {r['mass']} | {r['first_pass_stiff'] or 'NEVER'} | "
                  f"{emp or '—'} | {ana} | {ratio} |")
    (run_dir / "grip_table.md").write_text("\n".join(md) + "\n")

    print(f"\nDONE — see {run_dir}/grip_table.md")


if __name__ == "__main__":
    asyncio.run(main())
