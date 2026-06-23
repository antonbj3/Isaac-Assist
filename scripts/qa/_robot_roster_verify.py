"""Robot-roster readiness verify (cont.319, mandate): spawn each catalog robot via
robot_wizard codegen into the loaded Kit and confirm it loads as a VALID ARTICULATION
(>0 dofs). False-success-vakt on _ROBOT_WIZARD_REGISTRY: the registry CLAIMS 10 robots
with resolvable cloud assets, but a claim is only real if the asset actually loads.
Untested ones (allegro/anymal_c/h1/jetbot/spot/yaskawa_gp25) are the foundation for any
MEGA robot-diversity breadth. Verified-working: franka/ur10e/g1 (in cells this session)."""
import asyncio, sys
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.tools.handlers import robot as R

UNTESTED = ["allegro", "anymal_c", "h1", "jetbot", "spot", "yaskawa_gp25"]


async def main():
    # fresh stage
    await kit_tools.exec_sync(
        "import omni.usd; omni.usd.get_context().new_stage()", timeout=60)
    for i, rn in enumerate(UNTESTED):
        path = f"/World/R_{rn}"
        code = R._gen_robot_wizard({"robot_name": rn, "dest_path": path,
                                    "position": [i * 2.0, 0, 0]})
        if code.lstrip().startswith("raise"):
            print(f"ROSTER {rn}: CODEGEN-ERROR {code[:80]}")
            continue
        # build + step a few frames so the articulation initializes, then read dofs
        probe = code + (
            "\nimport omni.kit.app\n"
            "_app = omni.kit.app.get_app()\n"
            "for _ in range(30): _app.update()\n"
            "import omni.usd\n"
            "from pxr import Usd, UsdPhysics\n"
            f"_st = omni.usd.get_context().get_stage()\n"
            f"_root = _st.GetPrimAtPath({path!r})\n"
            "_art=None; _ndof=0\n"
            "for _p in Usd.PrimRange(_root):\n"
            "    if _p.HasAPI(UsdPhysics.ArticulationRootAPI): _art=_p\n"
            "_joints=sum(1 for _p in Usd.PrimRange(_root) if 'Joint' in _p.GetTypeName() and 'Fixed' not in _p.GetTypeName())\n"
            f"print('ROSTER {rn}: artic=' + str(bool(_art)) + ' moving_joints=' + str(_joints) + ' prims=' + str(sum(1 for _ in Usd.PrimRange(_root))))\n"
        )
        r = await kit_tools.exec_sync(probe, timeout=120)
        out = (r.get("output", "") if isinstance(r, dict) else str(r))
        line = next((l for l in out.splitlines() if l.startswith(f"ROSTER {rn}")), None)
        if line:
            print(line)
        else:
            tail = "\n".join(out.splitlines()[-3:])
            print(f"ROSTER {rn}: NO-VERDICT (load failed?) tail={tail[:160]}")


asyncio.run(main())
