"""articulation_gates — gate classes for non-pick-place verbs [P5-22].

The delivery gate (simulate_traversal_check) grades cube-to-bin tasks; the
door/valve/machine-tender/tool-swap families have had NO function-gate verdict
class at all (graded structurally or not at all — the de-falsing target).

Two tools:
- ``verify_articulation`` — pre-flight (no sim): articulation root present,
  the named joint exists, drive present, limits sane. The form-gate leg.
- ``simulate_articulation_check`` — the verdict: play the timeline
  ``duration_s``, sample the joint position before/after, PASS iff the
  joint moved past ``min_delta_deg`` (or reached ``target_angle_deg``
  within ``angle_tolerance_deg``) AND is settled at stop.

Both are honest-eyes: they read joint state off the live stage, never a
controller's self-report.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


async def _handle_verify_articulation(args: Dict) -> Dict:
    """Pre-flight articulation check (no simulation)."""
    from .. import kit_tools  # noqa: PLC0415
    art = args["articulation_path"]
    joint = args.get("joint_name")
    code = f"""\
import json as _j
import omni.usd
from pxr import Usd, UsdPhysics
stage = omni.usd.get_context().get_stage()
_res = {{"articulation_path": {art!r}, "ok": False}}
_p = stage.GetPrimAtPath({art!r})
if not _p or not _p.IsValid():
    _res["error"] = "prim not found"
else:
    _root = _p.HasAPI(UsdPhysics.ArticulationRootAPI)
    if not _root:
        for _d in Usd.PrimRange(_p):
            if _d.HasAPI(UsdPhysics.ArticulationRootAPI):
                _root = True
                break
    _joints = []
    for _d in Usd.PrimRange(_p):
        _t = str(_d.GetTypeName())
        if _t in ("PhysicsRevoluteJoint", "PhysicsPrismaticJoint"):
            _has_drive = bool(_d.GetAttribute("drive:angular:physics:stiffness").HasAuthoredValue()
                              or _d.GetAttribute("drive:linear:physics:stiffness").HasAuthoredValue()
                              or _d.HasAPI(UsdPhysics.DriveAPI, "angular")
                              or _d.HasAPI(UsdPhysics.DriveAPI, "linear"))
            _lo = _d.GetAttribute("physics:lowerLimit").Get()
            _hi = _d.GetAttribute("physics:upperLimit").Get()
            _joints.append({{"name": _d.GetName(), "path": str(_d.GetPath()),
                             "type": _t, "drive": _has_drive,
                             "limits": [_lo, _hi],
                             "limits_sane": (_lo is None or _hi is None or _lo < _hi)}})
    _res["has_articulation_root"] = _root
    _res["n_joints"] = len(_joints)
    _res["joints"] = _joints[:24]
    _named = {joint!r}
    # ok = the joint EXISTS with sane limits. Passive articulated objects
    # (drawers/doors pulled by contact) legitimately have neither
    # ArticulationRoot nor a drive — those are reported as INFO flags
    # (driven/has_articulation_root), not failed (live drawer-open finding).
    if _named:
        _hit = [_x for _x in _joints if _x["name"] == _named]
        _res["named_joint_found"] = bool(_hit)
        _res["ok"] = bool(_hit and _hit[0]["limits_sane"])
        if _hit:
            _res["named_joint"] = _hit[0]
            _res["driven"] = _hit[0]["drive"]
    else:
        _res["ok"] = bool(_joints and all(_x["limits_sane"] for _x in _joints))
        _res["driven"] = any(_x["drive"] for _x in _joints)
print('ARTICULATION_VERIFY=' + _j.dumps(_res))
"""
    return await kit_tools.queue_exec_patch(code, f"verify_articulation {art}")


async def _handle_simulate_articulation_check(args: Dict) -> Dict:
    """Play physics and verdict a joint-angle change — the articulation
    function-gate. PASS = joint moved past min_delta (or reached target
    within tolerance) and is settled at stop."""
    from .. import kit_tools  # noqa: PLC0415
    joint_path = args["joint_path"]
    body_path = args.get("body_path")  # explicit moving-body override
    duration_s = float(args.get("duration_s", 30))
    min_delta = args.get("min_delta_deg")
    target = args.get("target_angle_deg")
    tol = float(args.get("angle_tolerance_deg", 5.0))
    settle_eps = float(args.get("settle_eps_deg", 0.5))
    if min_delta is None and target is None:
        return {"type": "error",
                "error": "simulate_articulation_check: pass min_delta_deg or target_angle_deg"}
    code = f"""\
import json as _j
import omni.usd, omni.timeline
import omni.kit.app
stage = omni.usd.get_context().get_stage()
_jp = {joint_path!r}
_prim = stage.GetPrimAtPath(_jp)
_res = {{"joint_path": _jp, "success": False}}
from pxr import UsdGeom, Gf
_body1 = None
_explicit = {body_path!r}
if _explicit:
    _body1 = stage.GetPrimAtPath(_explicit)
# physics:body1 SHOULD be a relationship, but several templates author it
# as a string attribute via set_attribute (live drawer-open finding — USD
# pcp throws on GetRelationship over an attr-typed spec). Read both ways.
try:
    if _body1 is not None:
        raise StopIteration  # explicit body wins; skip rel reading
    _rel = _prim.GetRelationship("physics:body1")
    if _rel and _rel.IsValid():
        _tgts = _rel.GetTargets()
        if _tgts:
            _body1 = stage.GetPrimAtPath(str(_tgts[0]))
except Exception:
    pass
if _body1 is None and not _explicit:
    try:
        _at = _prim.GetAttribute("physics:body1")
        if _at and _at.HasAuthoredValue():
            _v = _at.Get()
            _pth = str(_v[0]) if isinstance(_v, (list, tuple)) and _v else str(_v)
            _body1 = stage.GetPrimAtPath(_pth)
    except Exception:
        pass
def _body1_pos():
    if not _body1 or not _body1.IsValid():
        return None
    _m = UsdGeom.Xformable(_body1).ComputeLocalToWorldTransform(0)
    _t = _m.ExtractTranslation()
    return [float(_t[0]), float(_t[1]), float(_t[2])]
_mode = "joint_state"
def _pos():
    # Primary: PhysX joint-state attr (driven articulations author it).
    # Fallback: body1's WORLD position — passive joints (contact-pulled
    # drawers/doors) never get state attrs (live drawer-open finding);
    # displacement is then the euclidean body1 movement.
    global _mode
    for _a in ("state:angular:physics:position", "state:linear:physics:position"):
        _at = _prim.GetAttribute(_a)
        if _at and _at.HasAuthoredValue():
            _mode = "joint_state"
            return float(_at.Get())
    _bp = _body1_pos()
    if _bp is not None:
        _mode = "body1_world"
        return _bp
    return None
if not _prim or not _prim.IsValid():
    _res["error"] = "joint not found"
else:
    _tl = omni.timeline.get_timeline_interface()
    _app = omni.kit.app.get_app()
    _start = _pos()
    _tl.play()
    import time as _time
    _t0 = _time.monotonic()
    _last = _start
    while _time.monotonic() - _t0 < {duration_s}:
        _app.update()
    _pre_stop = _pos()
    for _ in range(10):
        _app.update()
    _end = _pos()
    _tl.stop()
    if _start is None or _end is None:
        _res["error"] = "joint state unreadable AND no body1 to fall back on"
    else:
        _axis_i = {{"X": 0, "Y": 1, "Z": 2}}.get(str(_prim.GetAttribute("physics:axis").Get() or "X"), 0)
        def _d(a, b):
            if isinstance(a, list):
                return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
            return b - a
        if isinstance(_start, list):
            # body-world mode: PROJECT onto the joint axis — euclidean delta
            # passed a yanked-loose drawer (1.1 m with 0.36 m z-fall) before
            # the joint fix. Along-axis is the verdict; orthogonal drift is
            # flagged (loose/broken joint or body knocked sideways).
            _along = _end[_axis_i] - _start[_axis_i]
            _orth = (sum((_end[i] - _start[i]) ** 2 for i in range(3) if i != _axis_i)) ** 0.5
            _delta = _along
            _res["orthogonal_drift"] = round(_orth, 4)
            _res["orthogonal_drift_flag"] = bool(_orth > max(0.02, abs(_along) * 0.5))
        else:
            _delta = _d(_start, _end)
        _ps = _pre_stop if _pre_stop is not None else _end
        _settled = abs(_d(_ps, _end)) <= {settle_eps}
        _res["measure_mode"] = _mode
        _res.update({{"start_deg": _start, "end_deg": _end, "delta_deg": _delta,
                      "settled": _settled}})
        _min_delta = {min_delta!r}
        _target = {target!r}
        _ok = True
        if _min_delta is not None:
            _ok = _ok and abs(_delta) >= float(_min_delta)
        if _target is not None:
            _ok = _ok and abs(_end - float(_target)) <= {tol}
        _res["success"] = bool(_ok and _settled)
print('ARTICULATION_GATE=' + _j.dumps(_res))
"""
    timeout = int(duration_s) + 120
    return await kit_tools.queue_exec_patch(
        code, f"simulate_articulation_check {joint_path}", timeout=timeout)


def register(data: Dict[str, Callable[..., Any]],
             codegen: Dict[str, Callable[..., Any]]) -> None:
    data["verify_articulation"] = _handle_verify_articulation
    data["simulate_articulation_check"] = _handle_simulate_articulation_check
    codegen["create_physics_joint"] = _gen_create_physics_joint


def _gen_create_physics_joint(args: Dict) -> str:
    """Author a revolute/prismatic joint CORRECTLY [P5-22 root-cause fix].

    The corpus authored ``physics:body0/body1`` as STRING ATTRIBUTES via
    set_attribute — USD requires RELATIONSHIPS, and the resulting dual-spec
    property makes pcp throw on composition AND leaves the joint
    NON-BINDING (live drawer-open finding: the drawer was yanked loose,
    z 0.95->0.59, instead of sliding -0.3..0). This codegen authors the
    joint the only correct way.

    Args:
        joint_path (str, required)
        joint_type (str): "prismatic" (default) or "revolute".
        body0 (str, required): parent body prim path.
        body1 (str, required): moving body prim path.
        axis (str): "X" (default) / "Y" / "Z".
        lower_limit / upper_limit (float, optional): limits (m or deg).
        local_pos0 / local_pos1 (list[3], optional): anchor offsets.
    """
    joint_path = args["joint_path"]
    jt = str(args.get("joint_type", "prismatic")).lower()
    if jt not in ("prismatic", "revolute"):
        _msg = f"create_physics_joint: joint_type must be prismatic/revolute, got {jt!r}"
        return f"raise ValueError({_msg!r})\n"
    cls = "PrismaticJoint" if jt == "prismatic" else "RevoluteJoint"
    body0, body1 = args["body0"], args["body1"]
    axis = str(args.get("axis", "X")).upper()
    if axis not in ("X", "Y", "Z"):
        _msg = f"create_physics_joint: axis must be X/Y/Z, got {axis!r}"
        return f"raise ValueError({_msg!r})\n"
    lo, hi = args.get("lower_limit"), args.get("upper_limit")
    lp0 = args.get("local_pos0") or [0, 0, 0]
    lp1 = args.get("local_pos1") or [0, 0, 0]
    lines = [
        "import omni.usd",
        "from pxr import UsdPhysics, Gf, Sdf",
        "stage = omni.usd.get_context().get_stage()",
        f"_j = UsdPhysics.{cls}.Define(stage, {joint_path!r})",
        f"_j.GetBody0Rel().SetTargets([Sdf.Path({body0!r})])",
        f"_j.GetBody1Rel().SetTargets([Sdf.Path({body1!r})])",
        f"_j.GetAxisAttr().Set({axis!r})",
        f"_j.GetLocalPos0Attr().Set(Gf.Vec3f({float(lp0[0])}, {float(lp0[1])}, {float(lp0[2])}))",
        f"_j.GetLocalPos1Attr().Set(Gf.Vec3f({float(lp1[0])}, {float(lp1[1])}, {float(lp1[2])}))",
    ]
    if lo is not None:
        lines.append(f"_j.GetLowerLimitAttr().Set({float(lo)})")
    if hi is not None:
        lines.append(f"_j.GetUpperLimitAttr().Set({float(hi)})")
    lines.append(f"print('physics_joint {jt}', {joint_path!r}, 'body0={body0}', 'body1={body1}')")
    return "\n".join(lines) + "\n"
