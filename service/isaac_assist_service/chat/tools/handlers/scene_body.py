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
- create_rigid_body_array — N workpieces in ONE call with the full verified
  physics stack (RigidBody/Collision/Mass/PhysxRigidBody + sleepThreshold=0
  + material). `asset_ref` is THE canonical→asset bridge: primitive when
  absent, add_reference to a real USD when present — same call, same
  physics, same grading surface.
"""
from __future__ import annotations

import json
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


def _gen_create_rigid_body_array(args: Dict) -> str:
    """Emit the rigid-body init loop ~170 templates hand-roll per cube:
    prim + RigidBodyAPI + CollisionAPI + MassAPI + PhysxRigidBodyAPI +
    sleepThreshold=0.0 + physics-material binding — for N positions in one
    call. With ``asset_ref`` the SAME call swaps the primitive for a
    referenced USD asset (the canonical→asset bridge, P2-03): physics APIs
    land on the body root either way, so controllers and graders see an
    identical surface.

    Args:
        positions (list[list[3]], required): world [x, y, z] per body.
        prim_type (str): "Cube" (default) or "Sphere"; ignored with asset_ref.
        size (float): Cube size attr / Sphere diameter, metres. Default 0.05
            (the corpus workpiece).
        base_path (str): parent path, default "/World".
        name_prefix (str): default "Cube" -> /World/Cube_1, Cube_2, ...
        start_index (int): default 1.
        paths (list[str]): explicit per-body paths; overrides the
            base_path/name_prefix naming when given (len must match positions).
        mass (float): uniform mass kg via MassAPI. Absent -> PhysX derives
            from collision geometry + bound-material density.
        material (str): physics-material name from the db (e.g. "rubber",
            the corpus workpiece default). Resolved at codegen time; unknown
            names emit a raise, same contract as apply_physics_material.
        sleep_threshold (float): default 0.0 (corpus setting — workpieces
            must never sleep mid-task or the grader sees frozen cubes).
        asset_ref (str): USD file path. When present each body is an Xform
            referencing the asset; CollisionAPI is applied to its Gprim
            descendants only if the asset authors none.
        asset_scale (list[3]): scale applied to each body with asset_ref.
    """
    positions = args.get("positions")
    if not isinstance(positions, list) or not positions:
        return "raise ValueError('create_rigid_body_array: positions (non-empty list of [x,y,z]) is required')\n"
    for p in positions:
        if not isinstance(p, (list, tuple)) or len(p) != 3:
            _msg = f"create_rigid_body_array: bad position {p!r} — each must be [x,y,z]"
            return f"raise ValueError({_msg!r})\n"
    pos_tuples = [(float(p[0]), float(p[1]), float(p[2])) for p in positions]

    prim_type = str(args.get("prim_type", "Cube"))
    if prim_type not in ("Cube", "Sphere"):
        _msg = f"create_rigid_body_array: prim_type must be Cube or Sphere, got {prim_type!r}"
        return f"raise ValueError({_msg!r})\n"
    size = float(args.get("size", 0.05))
    base_path = str(args.get("base_path", "/World")).rstrip("/")
    name_prefix = str(args.get("name_prefix", "Cube"))
    start_index = int(args.get("start_index", 1))
    paths = args.get("paths")
    if paths is not None:
        if not isinstance(paths, list) or len(paths) != len(pos_tuples):
            return "raise ValueError('create_rigid_body_array: paths must match positions length')\n"
        body_paths = [str(p) for p in paths]
    else:
        body_paths = [f"{base_path}/{name_prefix}_{start_index + i}"
                      for i in range(len(pos_tuples))]

    mass = args.get("mass")
    mass = float(mass) if mass is not None else None
    sleep_threshold = float(args.get("sleep_threshold", 0.0))
    asset_ref = args.get("asset_ref")
    asset_scale = args.get("asset_scale")
    if asset_scale is not None and (not isinstance(asset_scale, (list, tuple)) or len(asset_scale) != 3):
        return "raise ValueError('create_rigid_body_array: asset_scale must be [sx,sy,sz]')\n"

    # Material resolved at CODEGEN time from the same db as
    # apply_physics_material — unknown names fail loudly, identical contract.
    material_block = ""
    bind_line = ""
    material = args.get("material")
    if material:
        from .physics import _load_physics_materials, _normalize_material_name
        db = _load_physics_materials()
        mat_key = _normalize_material_name(str(material))
        mat = db["materials"].get(mat_key)
        if mat is None:
            available = ", ".join(sorted(db["materials"].keys()))
            _msg = (f"create_rigid_body_array: unknown material {material!r} "
                    f"(normalized: {mat_key!r}). Available: {available}")
            return f"raise ValueError({_msg!r})\n"
        safe_name = mat_key.replace(" ", "_")
        material_block = f"""
# Physics material (once), bound to every body below.
_mat_path = '/World/PhysicsMaterials/{safe_name}'
_mat_prim = stage.DefinePrim(_mat_path)
_mat_api = UsdPhysics.MaterialAPI.Apply(_mat_prim)
_mat_api.CreateStaticFrictionAttr().Set({mat["static_friction"]})
_mat_api.CreateDynamicFrictionAttr().Set({mat["dynamic_friction"]})
_mat_api.CreateRestitutionAttr().Set({mat["restitution"]})
_mat_api.CreateDensityAttr().Set({mat["density_kg_m3"]})
"""
        bind_line = ("    prim.CreateRelationship('physics:materialBinding', "
                     "custom=False).SetTargets([Sdf.Path(_mat_path)])\n")

    mass_line = ""
    if mass is not None:
        mass_line = f"    _mass_api.GetMassAttr().Set({mass})\n"

    if asset_ref:
        geom_block = f"""    prim = stage.GetPrimAtPath(_path)
    if not prim or not prim.IsValid():
        prim = stage.DefinePrim(_path, 'Xform')
        prim.GetReferences().AddReference({str(asset_ref)!r})
"""
        if asset_scale is not None:
            sx, sy, sz = (float(asset_scale[0]), float(asset_scale[1]), float(asset_scale[2]))
            geom_block += f"""    _xf = UsdGeom.Xformable(prim)
    _xf.ClearXformOpOrder()
    _xf.AddTranslateOp().Set(Gf.Vec3d(*_pos))
    _xf.AddScaleOp().Set(Gf.Vec3f({sx}, {sy}, {sz}))
"""
        else:
            geom_block += """    _xf = UsdGeom.Xformable(prim)
    _xf.ClearXformOpOrder()
    _xf.AddTranslateOp().Set(Gf.Vec3d(*_pos))
"""
        # Colliders belong on the asset's Gprims; only backfill when the
        # asset authors none (most catalog assets carry their own).
        geom_block += """    if not any(d.HasAPI(UsdPhysics.CollisionAPI) for d in Usd.PrimRange(prim)):
        for _d in Usd.PrimRange(prim):
            if _d.IsA(UsdGeom.Gprim):
                UsdPhysics.CollisionAPI.Apply(_d)
"""
    else:
        define_cls = "UsdGeom.Cube" if prim_type == "Cube" else "UsdGeom.Sphere"
        attr_line = (f"    {define_cls}(prim).GetSizeAttr().Set({size})"
                     if prim_type == "Cube" else
                     f"    {define_cls}(prim).GetRadiusAttr().Set({size / 2.0})")
        geom_block = f"""    prim = stage.GetPrimAtPath(_path)
    if not prim or not prim.IsValid():
        prim = {define_cls}.Define(stage, _path).GetPrim()
{attr_line}
    _xf = UsdGeom.Xformable(prim)
    _xf.ClearXformOpOrder()
    _xf.AddTranslateOp().Set(Gf.Vec3d(*_pos))
    if not prim.HasAPI(UsdPhysics.CollisionAPI):
        UsdPhysics.CollisionAPI.Apply(prim)
"""

    return f"""\
import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf

stage = omni.usd.get_context().get_stage()
{material_block}
_bodies = {json.dumps(list(zip(body_paths, pos_tuples)))}
for _path, _pos in _bodies:
{geom_block}\
    # The verified-corpus physics stack — identical for primitive and asset.
    UsdPhysics.RigidBodyAPI.Apply(prim)
    _mass_api = UsdPhysics.MassAPI.Apply(prim)
{mass_line}\
    _px = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
    _px.CreateSleepThresholdAttr().Set({sleep_threshold})
{bind_line}\

print('rigid_body_array: ' + str(len(_bodies)) + ' bodies at ' + ', '.join(p for p, _ in _bodies))
"""


def register(
    data: Dict[str, Callable[..., Any]],
    codegen: Dict[str, Callable[..., Any]],
) -> None:
    """Register the scene-body codegen tools."""
    codegen["create_scene_baseline"] = _gen_create_scene_baseline
    codegen["create_rigid_body_array"] = _gen_create_rigid_body_array
