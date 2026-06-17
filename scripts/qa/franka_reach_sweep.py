#!/usr/bin/env python
"""CONTROLLED Franka top-down reach sweep (answers: where IS the reach boundary, and does it depend on
forward distance vs orientation vs height?). Fixed Franka base [0,0,0.75]. Vary ONE thing: forward
distance d in {0.30..0.55}. Probe via the controller's own cuRobo _plan_to_world_point (faithful) at
TWO heights: grasp (cube_top+0.025) and approach (cube_top+0.295 ~= EE_INITIAL_HEIGHT 1.12). Repeat for
orientation identity vs +90deg. ONE build per (orient,height); the reach-probe fires at tick 1."""
import asyncio, sys, json
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

DISTS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55]
LOG = "/tmp/reachprobe.log"

def _mk_template(orient, front_axis):
    """front_axis: 'y' for +90deg (base+X=world+Y), 'x' for identity (base+X=world+X)."""
    lines = [
        'create_prim(prim_path="/World/DomeLight", prim_type="DomeLight")',
        'create_prim(prim_path="/World/Ground", prim_type="Cube", position=[0,0,-0.5], scale=[20,20,1])',
        'apply_api_schema(prim_path="/World/Ground", schema_name="PhysicsCollisionAPI")',
        'set_physics_scene_config(config={"enable_gpu_dynamics": False, "broadphase_type": "MBP"})',
        'create_prim(prim_path="/World/Table", prim_type="Cube", position=[0,0,0.375], scale=[0.9,0.9,0.375])',
        'apply_api_schema(prim_path="/World/Table", schema_name="PhysicsCollisionAPI")',
        f'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0,0,0.75], orientation={orient})',
    ]
    cube_paths = []
    for i, d in enumerate(DISTS):
        pos = [0.0, d, 0.80] if front_axis == 'y' else [d, 0.0, 0.80]
        p = f"/World/Cube_{i}"
        cube_paths.append(p)
        lines.append(f'create_prim(prim_path="{p}", prim_type="Cube", position={pos}, size=0.05)')
        lines.append(f'apply_api_schema(prim_path="{p}", schema_name="PhysicsCollisionAPI")')
    lines.append('create_bin(prim_path="/World/Bin", position=[0,-0.5,0.75], size=[0.3,0.3,0.12])')
    lines.append(f'setup_pick_place_controller(robot_path="/World/Franka", target_source="curobo", '
                 f'belt_path=None, source_paths={cube_paths}, destination_path="/World/Bin", '
                 f'drop_target=[0,-0.5,0.88], planning_obstacles=[])')
    return {"code": "\n".join(lines)}

async def _run(kit_tools, etc, orient, front_axis, zoff, label):
    open(LOG, "w").close()
    await kit_tools.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    tpl = _mk_template(orient, front_axis)
    await etc(tpl, instance_root="", origin_offset=(0,0,0))
    await kit_tools.exec_sync(
        f"import builtins\nbuiltins._reach_probe=True\nbuiltins._reach_probe_done=False\n"
        f"builtins._reach_probe_z_off={zoff}\n", timeout=10)
    await kit_tools.exec_sync(
        "import omni.timeline,omni.kit.app; omni.timeline.get_timeline_interface().play()\n"
        "_a=omni.kit.app.get_app()\n"
        "for _ in range(200): _a.update()", timeout=60)
    verdicts = {}
    try:
        for ln in open(LOG):
            ln = ln.strip()
            if not ln.startswith("REACH_TGT"): continue
            path = next((t[5:] for t in ln.split() if t.startswith("path=")), "?")
            idx = int(path.rsplit("_", 1)[-1]) if path.rsplit("_",1)[-1].isdigit() else -1
            nok = next((t for t in ln.split() if "/3" in t and "@" in t), "?")
            verd = ln.split("->")[-1].strip() if "->" in ln else "?"
            if 0 <= idx < len(DISTS): verdicts[DISTS[idx]] = (nok, verd)
    except Exception as e:
        print("PARSE_ERR", e)
    print(f"[{label}] (zoff={zoff}, probe_z~={0.825+zoff:.3f})")
    for d in DISTS:
        v = verdicts.get(d, ("?", "NO_DATA"))
        print(f"    d={d:.2f}m  {v[1]:<12} {v[0]}")

async def main():
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical
    Q90 = [0.7071068, 0, 0, 0.7071068]
    QID = [1, 0, 0, 0]
    # CP-01-proven orientation, grasp + approach heights
    await _run(kit_tools, execute_template_canonical, Q90, 'y', 0.025, "ORIENT +90deg, GRASP")
    await _run(kit_tools, execute_template_canonical, Q90, 'y', 0.295, "ORIENT +90deg, APPROACH")
    # identity orientation, grasp + approach
    await _run(kit_tools, execute_template_canonical, QID, 'x', 0.025, "ORIENT identity, GRASP")
    await _run(kit_tools, execute_template_canonical, QID, 'x', 0.295, "ORIENT identity, APPROACH")

asyncio.run(main())
