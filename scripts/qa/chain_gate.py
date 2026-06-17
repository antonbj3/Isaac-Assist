#!/usr/bin/env python3
"""chain_gate.py — function-gate for a SEQUENTIAL composition CHAIN.

The composition direction has two modes:
  * PARALLEL  — independent cells run concurrently in one stage (compose_gate.py).
  * SEQUENTIAL CHAIN — stage-B sources stage-A's *delivered outputs* (end-state ->
    start-state handoff). This gate measures that relay.

Mechanism (proven 2026-06-15, memory project_isaac_assist_composition_direction):
  1. Build stage 0 normally (instance_root=inst0) and run it -> it delivers the
     physical cube prims (/World/inst0/Cube_*) into inst0's target.
  2. SETTLE: stop stage 0's belt and step a while so the just-delivered cubes
     come to rest as a flat layer. This matters because the next stage's
     EE_INITIAL_HEIGHT (cuRobo approach height) is computed AT BUILD TIME from the
     source-cube z; if the cubes are still in a transient STACK the approach is
     inflated and cuRobo plan-fails. Settling first keeps the approach sane.
  3. Build stage k (k>0) with origin_offset chosen so its PickSensor lands on
     stage (k-1)'s delivery target, and source_override = the inst0 cube prim
     paths (the cubes keep their prim path across the chain; only their position
     moves). Run it -> it relays the cubes into stage k's target.
  4. Measure, per stage, how many of the chained cubes reached that stage's
     (namespaced+offset) target bin.

The cubes are physical prims owned by stage 0, so every downstream stage's
source_override is stage 0's cube paths (re-rooted to inst0).

Reports the relay count HONESTLY (delivered/total per stage). Does NOT collapse a
partial relay to "pass" — delivered-count is the bar.

HANDOFF-GEOMETRY CAVEAT (measured 2026-06-15, do not mistake a low count for a
broken gate): the chain MECHANISM is proven — a single cube relays end-to-end
(CP-01->CP-01, conveyor -> inst0/Bin -> inst1/Bin). But robust MULTI-cube relay is
limited by the handoff geometry: when stage (k-1) delivers into a DEEP bin (0.15m
walls), stage k's pick from inside it either plan-fails (cuRobo) or grip-explodes
(PhysX corrective forces as the grasp fights the bin constraint). The settle phase
fixes the EE_INITIAL_HEIGHT inflation (flattens the stacked layer) but cannot fix
the grip-vs-wall blow-up. A robust multi-cube chain needs a PICKABLE FLAT handoff
(staging tray/conveyor, no deep walls) — a per-template DESIGN concern, not a
composer-mechanism gap. This gate honestly surfaces that: CP-01->CP-01 reports a
low relay BECAUSE deep-bin relay is geometry-limited, not because the gate is wrong.

Usage:
  chain_gate.py CP-01 CP-01@-0.29,-0.8,0          # 2-stage CP-01 -> CP-01 relay
  chain_gate.py CP-01 CP-01@-0.29,-0.8,0 CP-01@-0.58,-1.6,0   # 3-stage
  # offset of stage k must align its sensor onto stage (k-1)'s bin.

One local Kit (restart-before-run). Builds + steps; read-only on scene logic.
"""
import asyncio, json, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

# tunables (env-free; edit here). Steps scaled per stage.
RUN_STEPS = 4000          # steps to run each stage's delivery
SETTLE_STEPS = 900        # steps to let a stage's output settle before next build


def _parse(arg, idx):
    """'CP-01' or 'CP-01@dx,dy,dz' -> (name, (dx,dy,dz)). Default offset 0."""
    if "@" in arg:
        name, off = arg.split("@", 1)
        dx, dy, dz = (float(x) for x in off.split(","))
        return name, (dx, dy, dz)
    return arg, (0.0, 0.0, 0.0)


async def run(specs):
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    from service.isaac_assist_service.chat.composer import reroot_prim_path

    # fresh stage
    await kit_tools.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)

    # stage 0 owns the chained cubes
    name0, off0 = specs[0]
    tpl0 = json.load(open(f"{REPO}/workspace/templates/{name0}.json"))
    sa0 = tpl0.get("simulate_args") or tpl0.get("verify_args") or {}
    cubes0 = (sa0.get("cube_paths") or sa0.get("source_paths")
              or ([sa0.get("cube_path")] if sa0.get("cube_path") else []))
    chained = [reroot_prim_path(c, "inst0") for c in cubes0 if c]

    await execute_template_canonical(tpl0, instance_root="inst0", origin_offset=off0)
    # cont.180: re-arm after build (tl.stop + _pp_reset_epoch) so the controller re-validates its
    # articulation handle. Without it the UR10 controller plans (plan_calls++) but the arm never moves
    # (cont.179: stale handle after play -> apply_action no-op; Franka tolerates it, UR10 doesn't). The
    # cube-restore no-ops for namespaced instances; the GLOBAL epoch re-arm re-validates the handle.
    # Verified: UR10 gd 1.289 -> 0.025 (cone reaches cube) + cube carried after this call.
    await settle_after_canonical(tpl0)
    await _run_steps(kit_tools, RUN_STEPS)

    results = []
    # stage 0 delivery (its own cubes into its own target)
    tgt0 = sa0.get("target_path")
    results.append(await _measure(kit_tools, "inst0", name0,
                                  chained, reroot_prim_path(tgt0, "inst0") if tgt0 else None))

    for i in range(1, len(specs)):
        name, off = specs[i]
        root = f"inst{i}"
        tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
        sa = tpl.get("simulate_args") or tpl.get("verify_args") or {}
        tgt = sa.get("target_path")
        # settle the prior stage's output (flat layer -> sane approach height)
        await _settle(kit_tools, f"inst{i-1}", SETTLE_STEPS)
        # build stage i sourcing the chained cubes; run; measure relay into its target
        await execute_template_canonical(tpl, instance_root=root, origin_offset=off,
                                         source_override=chained)
        await settle_after_canonical(tpl)   # cont.180: re-arm stage k's controller (re-validate articulation handle)
        await _run_steps(kit_tools, RUN_STEPS + 1000)
        results.append(await _measure(kit_tools, root, name, chained,
                                      reroot_prim_path(tgt, root) if tgt else None))

    print("CHAIN_GATE STAGES:")
    for r in results:
        print("  %s" % r)
    relayed = [r for r in results[1:]]
    print("CHAIN_GATE SUMMARY: %d stage(s); final-stage relay = %s"
          % (len(specs), results[-1].split("relay=")[-1] if results else "n/a"))


async def _run_steps(kit_tools, n):
    # cont.175 NOTE: tried mirroring scene_eyes' _KIT-probe arming (warm-up + SimulationManager.
    # initialize_physics + World) here to fix UR10-as-stage0 not moving — MEASURED ineffective
    # (physics_sim_view went True + timeline playing, but the UR10 cube stayed UNTOUCHED). So the
    # physics_sim_view was NOT the blocker; reverted to keep the proven CP-01 chain path byte-identical.
    # The UR10 controller-execution-under-chain_gate blocker is deeper (focused-session debug).
    await kit_tools.exec_sync(
        "import omni.timeline,omni.kit.app; omni.timeline.get_timeline_interface().play()\n"
        "_a=omni.kit.app.get_app()\n"
        f"for _ in range({n}): _a.update()", timeout=int(n/25)+60)


async def _settle(kit_tools, root, n):
    code = f'''
import omni.usd, omni.kit.app
stage=omni.usd.get_context().get_stage()
bp=stage.GetPrimAtPath("/World/{root}/ConveyorBelt")
if bp and bp.IsValid():
    a=bp.GetAttribute("physxSurfaceVelocity:surfaceVelocity")
    if a and a.IsDefined(): a.Set((0,0,0))
_a=omni.kit.app.get_app()
for _ in range({n}): _a.update()
'''
    await kit_tools.exec_sync(code, timeout=int(n/25)+60)


async def _measure(kit_tools, root, name, cubes, target):
    spec = json.dumps({"root": root, "name": name, "cubes": cubes, "target": target})
    code = f'''
import omni.usd, json as _j
from pxr import UsdGeom
stage=omni.usd.get_context().get_stage()
D=_j.loads({spec!r})
def bbox(p):
    pr=stage.GetPrimAtPath(p)
    if not pr or not pr.IsValid(): return None
    r=UsdGeom.Imageable(pr).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    if r.IsEmpty(): return None
    mn,mx=r.GetMin(),r.GetMax()
    return [float(mn[0]),float(mn[1]),float(mn[2])],[float(mx[0]),float(mx[1]),float(mx[2])]
def cpos(p):
    b=bbox(p)
    return [(b[0][i]+b[1][i])/2.0 for i in range(3)] if b else None
tb=bbox(D["target"]) if D["target"] else None
n=0
for c in D["cubes"]:
    cp=cpos(c)
    if tb and cp and tb[0][0]-0.05<=cp[0]<=tb[1][0]+0.05 and tb[0][1]-0.05<=cp[1]<=tb[1][1]+0.05 and cp[2]>tb[0][2]-0.05:
        n+=1
print("MEASURE %s %s relay=%d/%d target=%s" % (D["root"], D["name"], n, len(D["cubes"]), D["target"]))
'''
    rr = await kit_tools.exec_sync(code, timeout=60)
    out = (rr.get("output") or rr.get("error") or "").strip()
    line = [l for l in out.splitlines() if l.startswith("MEASURE")]
    return line[-1].replace("MEASURE ", "") if line else f"{root} {name} relay=ERR"


async def main():
    args = sys.argv[1:] or ["CP-01", "CP-01@-0.29,-0.8,0"]
    specs = [_parse(a, i) for i, a in enumerate(args)]
    await run(specs)

if __name__ == "__main__":
    asyncio.run(main())
