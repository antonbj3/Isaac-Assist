"""Build-time GEOMETRIC_OVERLAP advisory (generation wiring, 2026-06-12).

Non-destructive extraction of scene_validate.py's check 00: pairwise AABB on
dynamic rigid bodies at AUTHORED positions + robot-base footprints vs static
colliders (kinematic conveyors count as scenery — the CP-67 belt class).
Reads authored state only: no timeline play, no controller unsubscribe, so it
is safe to run inside every canonical build. Advisory — never blocks a build
(the function gate measures delivery; this annotates the result so a
spawned-interpenetrating scene is flagged the moment it is generated instead
of three diagnose iterations later).

The full validator (settle-dependent REACH / SUPPORT / INSTABILITY checks)
stays in scripts/qa/scene_validate.py — those NEED the destructive settle.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

# Kit-side source. Mirrors scripts/qa/scene_validate.py check 00 (keep the two
# in sync when calibrating: link-FP -> robot-subtree exclusion; assembly-FP ->
# same-top-level-asset exclusion; kinematic-scenery-FN -> kinematic RBs are
# statics). Prints exactly one line: OVERLAP= {json}.
OVERLAP_CHECK_CODE = r'''
import omni.usd, json as _ovl_json
from pxr import Sdf, UsdGeom, UsdPhysics
stage = omni.usd.get_context().get_stage()

def _ovl_aabb(path):
    p = stage.GetPrimAtPath(Sdf.Path(path))
    if not (p and p.IsValid()): return None
    try:
        r = UsdGeom.Imageable(p).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
        if r.IsEmpty(): return None
        mn, mx = r.GetMin(), r.GetMax()
        out = [float(mn[0]), float(mn[1]), float(mn[2])], [float(mx[0]), float(mx[1]), float(mx[2])]
        if any(abs(v) > 1e6 for v in out[0] + out[1]): return None
        return out
    except Exception:
        return None

# robot detection (same semantics as scene_validate.py: name/articulation
# heuristic, gripper-subprim + legged exclusions, top-level de-dupe)
_GRIP_MARK = ("follower","cone","gripper","suction","_sg","sgf","finger","cup","pad","tool0","shortgripper")
_LEGGED = ("g1","h1","anymal","humanoid","pelvis","biped","quadruped","spot","go1","go2","unitree")
_ROBOTS = []
_seen_top = set()
for _p in stage.Traverse():
    _nm = _p.GetName().lower(); _ps = _p.GetPath().pathString.lower()
    _is_art = _p.HasAPI(UsdPhysics.ArticulationRootAPI)
    if _is_art or any(k in _nm for k in ("ur10","ur5","ur3","ur16","franka","panda","cobotta","kuka","iiwa","abb")):
        if not _is_art and any(g in _nm for g in _GRIP_MARK): continue
        if any(k in _ps for k in _LEGGED): continue
        _rp = _p.GetPath().pathString
        _segs = _rp.strip("/").split("/")
        _top = "/" + "/".join(_segs[:2]) if len(_segs) >= 2 else _rp
        if _top in _seen_top: continue
        _seen_top.add(_top)
        try:
            _t = UsdGeom.Xformable(_p).ComputeLocalToWorldTransform(0).ExtractTranslation()
            _ROBOTS.append({"path": _rp, "base": [float(_t[0]), float(_t[1]), float(_t[2])]})
        except Exception: pass

# authored positions of dynamic rigid bodies
_pre = {}
for _pr in stage.Traverse():
    if _pr.HasAPI(UsdPhysics.RigidBodyAPI):
        _k = _pr.GetAttribute("physics:kinematicEnabled")
        if _k and _k.Get(): continue
        try:
            _t0 = UsdGeom.Xformable(_pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
            _pre[_pr.GetPath().pathString] = [float(_t0[0]), float(_t0[1]), float(_t0[2])]
        except Exception: pass

_OVL_TOL = 0.02
_V = []
def _top2(path):
    _parts = path.split("/")
    return "/".join(_parts[:3]) if len(_parts) > 2 else path
_robot_roots = [r["path"] for r in _ROBOTS]
_dyn = {}
for _p0, _c in _pre.items():
    if any(_p0 == rr or _p0.startswith(rr + "/") for rr in _robot_roots): continue
    _bb0 = _ovl_aabb(_p0)
    if not _bb0: continue
    _ext = [(_bb0[1][i] - _bb0[0][i]) / 2.0 for i in range(3)]
    _dyn[_p0] = ([_c[i] - _ext[i] for i in range(3)], [_c[i] + _ext[i] for i in range(3)])
_items = sorted(_dyn.items())
for _i in range(len(_items)):
    for _j in range(_i + 1, len(_items)):
        (_pa, _ba), (_pb, _bb2) = _items[_i], _items[_j]
        if _pa.split("/")[-1] == _pb.split("/")[-1]: continue
        if _top2(_pa) == _top2(_pb): continue
        _pen = min(min(_ba[1][k], _bb2[1][k]) - max(_ba[0][k], _bb2[0][k]) for k in range(3))
        if _pen > _OVL_TOL:
            _V.append("%s and %s spawn interpenetrating (depth %.3f m)" % (_pa, _pb, _pen))
for _rb in _ROBOTS:
    _bx, _by, _bz = _rb["base"]
    _base_bb = ([_bx - 0.15, _by - 0.15, _bz + 0.01], [_bx + 0.15, _by + 0.15, _bz + 0.10])
    for _sp in stage.Traverse():
        if not _sp.HasAPI(UsdPhysics.CollisionAPI): continue
        if _sp.HasAPI(UsdPhysics.RigidBodyAPI):
            _k = _sp.GetAttribute("physics:kinematicEnabled")
            if not (_k and _k.Get()): continue
        _spp = _sp.GetPath().pathString
        if _spp.startswith(_rb["path"]): continue
        _sbb = _ovl_aabb(_spp)
        if not _sbb: continue
        _pen = min(min(_base_bb[1][k], _sbb[1][k]) - max(_base_bb[0][k], _sbb[0][k]) for k in range(3))
        if _pen > _OVL_TOL:
            _V.append("robot base %s intersects static %s (depth %.3f m, CP-67 class)" % (_rb["path"], _spp, _pen))
print("OVERLAP=", _ovl_json.dumps({"violations": _V, "n_dynamic": len(_dyn), "n_robots": len(_ROBOTS)}))
'''


def parse_overlap_output(output: Optional[str]) -> Optional[Dict[str, Any]]:
    """Extract the OVERLAP= JSON payload from exec output. None if absent."""
    if not isinstance(output, str):
        return None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("OVERLAP="):
            try:
                return json.loads(line[len("OVERLAP="):].strip())
            except Exception:
                return None
    return None
