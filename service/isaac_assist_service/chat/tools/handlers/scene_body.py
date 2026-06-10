"""scene_body — the toolified scene "body" codegen tools [Phase 2].

The backbone (robot_wizard, controllers) was always tool-disciplined; the
BODY (lighting/ground/table baseline, rigid-body arrays, palletizer grids)
was copy-pasted raw across ~200 templates with accidental drift. These
codegen tools make the body single-source-of-truth, while `expand=True`
(chat/tools/expand.py) lets any template de-abstract to the raw emitted
code for one-off tweaks — abstraction without losing customizability.

Tools (P2-02..05 land here):
- create_scene_baseline — the DomeLight + Ground + (Table) + PhysicsScene
  opening that ~200 templates hand-roll.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


def _gen_create_scene_baseline(args: Dict) -> str:
    """Emit the canonical scene opening: DomeLight (intensity), Ground slab
    with CollisionAPI, optional Cell Xform + work Table with CollisionAPI,
    and the PhysicsScene config (CPU dynamics + MBP broadphase by default —
    the settings the verified corpus runs on).

    Args (all optional):
        root (str): parent path, default "/World".
        intensity (float): dome light intensity, default 1000.0.
        ground_scale (float): ground half-extent metres, default 20.0.
        include_table (bool): default True.
        table_size (list[2]): table top [x, y] metres, default [1.5, 0.5].
        table_height (float): table TOP height metres, default 0.75.
        physics (dict): {"enable_gpu_dynamics": bool, "broadphase_type": str};
            defaults {False, "MBP"}.
    """
    root = args.get("root", "/World")
    intensity = float(args.get("intensity", 1000.0))
    ground_scale = float(args.get("ground_scale", 20.0))
    include_table = bool(args.get("include_table", True))
    table_size = args.get("table_size", [1.5, 0.5])
    table_height = float(args.get("table_height", 0.75))
    physics = args.get("physics") or {}
    gpu_dyn = bool(physics.get("enable_gpu_dynamics", False))
    broadphase = str(physics.get("broadphase_type", "MBP"))
    tx, ty = float(table_size[0]), float(table_size[1])
    th = table_height / 2.0  # half-extent + centre z for the table slab

    table_block = ""
    if include_table:
        table_block = f"""
# Work cell + table (top at z={table_height}). Slab modelled like the
# hand-rolled originals: Cube scaled to half-extents, centred at half height.
cell = stage.GetPrimAtPath('{root}/Cell')
if not cell or not cell.IsValid():
    stage.DefinePrim('{root}/Cell', 'Xform')
table_prim = stage.GetPrimAtPath('{root}/Table')
if not table_prim or not table_prim.IsValid():
    table_prim = UsdGeom.Cube.Define(stage, '{root}/Table').GetPrim()
_t = UsdGeom.Cube(table_prim)
_t.GetSizeAttr().Set(2.0)
_txf = UsdGeom.Xformable(table_prim)
_txf.ClearXformOpOrder()
_txf.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, {th}))
_txf.AddScaleOp().Set(Gf.Vec3f({tx / 2.0}, {ty / 2.0}, {th}))
if not table_prim.HasAPI(UsdPhysics.CollisionAPI):
    UsdPhysics.CollisionAPI.Apply(table_prim)
"""

    return f"""\
import omni.usd
from pxr import Usd, UsdGeom, UsdLux, UsdPhysics, PhysxSchema, Gf

stage = omni.usd.get_context().get_stage()

# Dome light
light_prim = stage.GetPrimAtPath('{root}/DomeLight')
if not light_prim or not light_prim.IsValid():
    light_prim = UsdLux.DomeLight.Define(stage, '{root}/DomeLight').GetPrim()
UsdLux.DomeLight(light_prim).GetIntensityAttr().Set({intensity})

# Ground slab (collision)
ground_prim = stage.GetPrimAtPath('{root}/Ground')
if not ground_prim or not ground_prim.IsValid():
    ground_prim = UsdGeom.Cube.Define(stage, '{root}/Ground').GetPrim()
_g = UsdGeom.Cube(ground_prim)
_g.GetSizeAttr().Set(2.0)
_gxf = UsdGeom.Xformable(ground_prim)
_gxf.ClearXformOpOrder()
_gxf.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.5))
_gxf.AddScaleOp().Set(Gf.Vec3f({ground_scale}, {ground_scale}, 0.5))
if not ground_prim.HasAPI(UsdPhysics.CollisionAPI):
    UsdPhysics.CollisionAPI.Apply(ground_prim)
{table_block}
# Physics scene — the verified-corpus settings unless overridden.
phys_prim = stage.GetPrimAtPath('/PhysicsScene')
if not phys_prim or not phys_prim.IsValid():
    phys_prim = UsdPhysics.Scene.Define(stage, '/PhysicsScene').GetPrim()
px_api = PhysxSchema.PhysxSceneAPI.Apply(phys_prim)
px_api.CreateEnableGPUDynamicsAttr().Set({gpu_dyn})
px_api.CreateBroadphaseTypeAttr().Set('{broadphase}')

print('scene_baseline: light+ground{"+cell+table" if include_table else ""} + PhysicsScene(gpu={gpu_dyn}, {broadphase})')
"""


def register(
    data: Dict[str, Callable[..., Any]],
    codegen: Dict[str, Callable[..., Any]],
) -> None:
    """Register the scene-body codegen tools."""
    codegen["create_scene_baseline"] = _gen_create_scene_baseline
