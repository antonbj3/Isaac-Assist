"""static_eyes — fast, no-physics geometric layout verifier.

A pure-Python facade over :class:`ContactReachabilityValidator` + the object
``PALETTE`` (fixed asset bboxes) + a per-robot reach map. It reads a *layout*
(object paths + positions + asset bboxes + robot + pick/place targets) and
returns a per-check verdict plus machine-actionable ``fix`` suggestions, so the
LLM can iterate on a layout **without paying for a Kit build + physics settle**.

It sits between the structural ``form_gate`` and the expensive ``function_gate``::

    form_gate  ->  static_eyes (geometric, no Kit)  ->  function_gate (sim)  ->  diagnose

No Kit, no GPU, no imports of Kit-bound modules — unit-testable in isolation.
Spec: ``docs/notes/STATIC_EYES_SPEC.md``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .object_palette import PALETTE
from .spawn_validator_contact_reachability import (
    ContactPoint,
    ContactReachabilityValidator,
    OccluderBox,
    RobotReachSpec,
)

Vec3 = Tuple[float, float, float]
AABB = Tuple[Vec3, Vec3]  # ((xmin,ymin,zmin), (xmax,ymax,zmax))

# Mirror of handlers/resolve.py:_ROBOT_REACH_M and scene_validate.py ROBOT_REACH.
# Defined locally so static_eyes stays free of any Kit-bound import.
_ROBOT_REACH_M: Dict[str, float] = {
    "franka_panda": 0.855, "franka": 0.855,
    "ur5e": 0.850, "ur5": 0.850,
    "ur10": 1.300, "ur10e": 1.300, "ur16e": 1.300,
    "kinova": 0.902, "kinova_gen3": 0.902,
    "h1": 0.580, "g1": 0.450,
    "default": 0.800,
}

# PALETTE.height_m is the canonical source of truth for every known asset class.
# _CLASS_HEIGHTS_M is kept as a forward-compatibility fallback ONLY for ad-hoc /
# unknown asset names that are not in the palette (e.g. user-supplied custom assets).
# Do NOT re-populate this dict with palette entries — edit object_palette.py instead.
_CLASS_HEIGHTS_M: Dict[str, float] = {}

# Static reach-shell band: a pick within (reach - margin) is a comfortable PASS;
# within [reach - margin, reach] is UNCERTAIN (near the non-convex floor -> needs
# a live cuRobo probe, see STATIC_EYES_SPEC §5); beyond reach is a gross FAIL.
_REACH_MARGIN_M = 0.10
# A target at/below the base plane is UNCERTAIN for top-down grippers (z-window).
_BASE_Z_UNCERTAIN_M = 0.05
# Support gap tolerances: within this band of a surface top = resting (PASS).
_SUPPORT_REST_TOL_M = 0.02
# Floating up to this above a valid surface = WARN (will fall onto it), not FAIL.
_SUPPORT_FLOAT_WARN_M = 0.15

_DYNAMIC_TAGS = {"dynamic"}


# Default per-status confidence (P1-08): how sure the STATIC verdict is.
# Geometric pass/fail far from thresholds is high-confidence; warn is
# advisory; uncertain is by definition low (it exists to route to tier-2).
# Checks may override with a margin-derived value.
_STATUS_CONFIDENCE = {"pass": 0.9, "fail": 0.9, "warn": 0.6,
                      "uncertain": 0.35, "skipped": None}


@dataclass
class Check:
    """One static_eyes check result."""
    id: str
    status: str  # pass | fail | warn | uncertain | skipped
    target: str = ""
    message: str = ""
    fix: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None  # explicit override; else status default

    def effective_confidence(self) -> Optional[float]:
        return self.confidence if self.confidence is not None             else _STATUS_CONFIDENCE.get(self.status)


@dataclass
class StaticEyesReport:
    verdict: str  # PASS | FAIL | UNCERTAIN
    checks: List[Check] = field(default_factory=list)
    overall_fix_order: List[str] = field(default_factory=list)
    next_gate: str = "function_gate"
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checks": [
                {k: v for k, v in {
                    "id": c.id, "status": c.status, "target": c.target,
                    "message": c.message, "fix": c.fix,
                    "confidence": c.effective_confidence(),
                }.items() if v not in ("", None)}
                for c in self.checks
            ],
            "overall_fix_order": self.overall_fix_order,
            "next_gate": self.next_gate,
            "caveats": self.caveats,
        }


# ---------------------------------------------------------------------------
# Geometry helpers (pure)
# ---------------------------------------------------------------------------

def _dist(a: Vec3, b: Vec3) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _reach_radius(family: str) -> float:
    return _ROBOT_REACH_M.get((family or "").lower(), _ROBOT_REACH_M["default"])


def _height_of(asset_name: str) -> float:
    cls = PALETTE.get(asset_name)
    if cls is not None and getattr(cls, "height_m", 0.0):
        return float(cls.height_m)
    return _CLASS_HEIGHTS_M.get(asset_name, 0.0)


def _is_dynamic(asset_name: str) -> bool:
    cls = PALETTE.get(asset_name)
    return bool(cls and _DYNAMIC_TAGS & set(cls.tags or ()))


def _aabb_of(obj: Dict[str, Any]) -> Optional[AABB]:
    """Return ((xmin,ymin,zmin),(xmax,ymax,zmax)) for a layout object.

    Uses an explicit ``bbox`` if present, else derives one from the PALETTE
    footprint (+ height fallback) centred on ``position``. Returns None when
    neither a bbox nor a known footprint is available.
    """
    bb = obj.get("bbox")
    if bb:
        (lo, hi) = bb
        return ((float(lo[0]), float(lo[1]), float(lo[2])),
                (float(hi[0]), float(hi[1]), float(hi[2])))
    pos = obj.get("position")
    asset = obj.get("asset_name", "")
    cls = PALETTE.get(asset)
    if pos is None or cls is None:
        return None
    fx, fy = cls.footprint_xy_m
    h = _height_of(asset)
    cx, cy, cz = float(pos[0]), float(pos[1]), float(pos[2])
    # position is treated as the object centre in XY; in Z it is the base for
    # workpieces (rest on a surface) — model the box as [cz, cz+h] so the top is
    # cz+h and the bottom is cz (matches authored spawn-on-surface convention).
    return ((cx - fx / 2, cy - fy / 2, cz),
            (cx + fx / 2, cy + fy / 2, cz + h))


def _aabb_xy_overlap(a: AABB, b: AABB) -> bool:
    return (a[0][0] < b[1][0] and a[1][0] > b[0][0] and
            a[0][1] < b[1][1] and a[1][1] > b[0][1])


def _aabb_3d_overlap(a: AABB, b: AABB) -> bool:
    return (_aabb_xy_overlap(a, b) and
            a[0][2] < b[1][2] and a[1][2] > b[0][2])


def _xy_inside(pt: Vec3, box: AABB) -> bool:
    return (box[0][0] <= pt[0] <= box[1][0] and
            box[0][1] <= pt[1] <= box[1][1])


# ---------------------------------------------------------------------------
# The facade
# ---------------------------------------------------------------------------

def run(layout: Dict[str, Any]) -> StaticEyesReport:
    """Run all static checks on *layout* and return a :class:`StaticEyesReport`."""
    robots = layout.get("robots") or []
    objects = layout.get("objects") or []
    picks = layout.get("picks") or []
    places = layout.get("places") or []
    cell_bounds = layout.get("cell_bounds")

    by_path: Dict[str, Dict[str, Any]] = {o["path"]: o for o in objects if "path" in o}
    aabbs: Dict[str, AABB] = {}
    for p, o in by_path.items():
        bb = _aabb_of(o)
        if bb is not None:
            aabbs[p] = bb

    # Occluders: explicit, else only real OBSTACLES (environment category or a
    # "barrier" tag — walls/fences/enclosures/obstacle boxes). Work surfaces
    # (tables/bins/conveyors) are NOT occluders for a top-down approach.
    occ_paths = layout.get("occluders")
    if occ_paths is None:
        occ_paths = []
        for p, o in by_path.items():
            cls = PALETTE.get(o.get("asset_name", ""))
            if cls and (cls.category == "environment" or "barrier" in (cls.tags or ())):
                occ_paths.append(p)
    occluders: List[OccluderBox] = []
    for p in occ_paths:
        bb = aabbs.get(p)
        if bb is None:
            continue
        (lo, hi) = bb
        center = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
        half = ((hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2)
        occluders.append(OccluderBox(center, half))

    checks: List[Check] = []
    validator = ContactReachabilityValidator(reach_margin_m=0.0)

    def nearest_robot(pos: Vec3):
        best, bestd = None, float("inf")
        for r in robots:
            base = tuple(r.get("base", (0.0, 0.0, 0.0)))
            d = _dist(pos, base)
            if d < bestd:
                best, bestd = r, d
        return best

    # ---- reach (shell + occlusion), tiered ----
    targets: List[Tuple[str, Vec3, bool]] = []  # (label, pos, is_drop)
    for pk in picks:
        o = by_path.get(pk)
        if o and o.get("position") is not None:
            targets.append((pk, tuple(o["position"]), False))
    for pl in places:
        dt = pl.get("drop_target")
        if dt is not None:
            targets.append((pl.get("target_path", "drop"), tuple(dt), True))

    for label, pos, is_drop in targets:
        r = nearest_robot(pos) if robots else None
        if r is None:
            continue
        base = tuple(r.get("base", (0.0, 0.0, 0.0)))
        family = r.get("family", "default")
        reach = _reach_radius(family)
        d = _dist(pos, base)
        # dynamic-feed pick: spawn position is not the fixed station -> warn
        # (explicit dynamic_feed flag OR a dynamic-tagged asset; spec §6.4)
        src = by_path.get(label)
        if src and (src.get("dynamic_feed") or _is_dynamic(src.get("asset_name", ""))):
            checks.append(Check("reach:shell", "warn", label,
                                f"{label} is on a dynamic feed; reach checked at t=0 spawn — verify the fixed station position"))
            continue
        if d > reach:
            # gross out-of-reach FAIL — project onto the reach sphere
            sp = _project_to_sphere(pos, base, reach - _REACH_MARGIN_M)
            checks.append(Check(
                "reach:shell", "fail", label,
                f"{label} at {_fmt(pos)} is {d:.2f}m from {r.get('path','base')} (> reach {reach:.2f})",
                fix={
                    "action": "move_drop_target" if is_drop else "move_object",
                    "path": label,
                    "constraint": f"dist_to_base <= {reach:.2f}",
                    "suggest_position": [round(v, 3) for v in sp],
                    "human": f"{'drop' if is_drop else 'pick'} at radius {d:.2f} unreachable -> move within {reach:.2f}m of base, e.g. {[round(v,3) for v in sp]}",
                },
            ))
            continue
        # occlusion (advisory)
        cp = ContactPoint(position=pos, surface_id=label)
        rspec = RobotReachSpec(base_position=base, max_reach_m=reach + 1.0)  # don't double-flag reach here
        if validator.is_occluded(cp, rspec, occluders):
            checks.append(Check("occlusion", "warn", label,
                                f"straight line base->{label} crosses an occluder AABB; may need a non-straight approach — verify in function_gate"))
        # uncertain band: near the radius limit, or BELOW base z (the non-convex
        # straight-down floor that defeats a radial formula — see spec §5)
        if d > reach - _REACH_MARGIN_M or pos[2] < base[2] - _BASE_Z_UNCERTAIN_M:
            # deeper into the uncertain band -> lower confidence (P1-08):
            # radial overshoot into the margin scales 0.45 (just entered)
            # down to 0.25 (at the sphere); below-base-z pins to 0.25 (the
            # non-convex floor a radial formula cannot judge at all)
            if pos[2] < base[2] - _BASE_Z_UNCERTAIN_M:
                conf = 0.25
            else:
                into = (d - (reach - _REACH_MARGIN_M)) / _REACH_MARGIN_M
                conf = round(0.45 - 0.20 * max(0.0, min(1.0, into)), 3)
            checks.append(Check("reach:shell", "uncertain", label,
                                f"{label} at radius {d:.2f}/{reach:.2f}, z={pos[2]:.2f} vs base z={base[2]:.2f} — borderline; needs a live cuRobo IK probe (tier-2)",
                                confidence=conf))
        else:
            # comfortable pass: confidence grows with margin to the band
            margin = (reach - _REACH_MARGIN_M) - d
            conf = round(min(0.95, 0.75 + 0.4 * margin / max(reach, 1e-6)), 3)
            checks.append(Check("reach:shell", "pass", label, confidence=conf))

    # ---- interpenetration (3D AABB overlap among picked workpieces) ----
    pick_aabbs = [(p, aabbs[p]) for p in picks if p in aabbs]
    for i in range(len(pick_aabbs)):
        for j in range(i + 1, len(pick_aabbs)):
            (pa, ba), (pb, bb) = pick_aabbs[i], pick_aabbs[j]
            if _aabb_3d_overlap(ba, bb):
                checks.append(Check(
                    "interpenetration", "fail", f"{pa}|{pb}",
                    f"{pa} and {pb} overlap at spawn (clump -> physics ejection)",
                    fix={"action": "move_object", "path": pb,
                         "constraint": "no_aabb_overlap_with " + pa,
                         "human": f"separate {pb} from {pa} (overlapping spawn explodes under PhysX)"},
                ))
    if not any(c.id == "interpenetration" for c in checks):
        checks.append(Check("interpenetration", "pass"))

    # ---- fit + drop_in_container + support per place ----
    for pl in places:
        dest_path = pl.get("target_path", "")
        dest_bb = aabbs.get(dest_path)
        # fit: every picked workpiece footprint must fit the dest inner footprint
        if dest_bb is not None and picks:
            dfx = dest_bb[1][0] - dest_bb[0][0]
            dfy = dest_bb[1][1] - dest_bb[0][1]
            for pk in picks:
                bb = aabbs.get(pk)
                if bb is None:
                    continue
                wfx, wfy = bb[1][0] - bb[0][0], bb[1][1] - bb[0][1]
                if wfx > dfx or wfy > dfy:
                    checks.append(Check(
                        "fit", "fail", dest_path,
                        f"workpiece {pk} ({wfx:.2f}x{wfy:.2f}) does not fit {dest_path} interior ({dfx:.2f}x{dfy:.2f})",
                        fix={"action": "swap_destination", "path": dest_path,
                             "constraint": f"dest_interior >= {wfx:.2f}x{wfy:.2f}",
                             "human": f"{pk} is wider than {dest_path}; use a larger container or smaller workpiece"},
                    ))
        # drop_in_container: drop xy inside dest, z above dest top
        dt = pl.get("drop_target")
        if dt is not None and dest_bb is not None:
            dt = tuple(dt)
            inside = _xy_inside(dt, dest_bb)
            top = dest_bb[1][2]
            if not inside:
                cx = min(max(dt[0], dest_bb[0][0]), dest_bb[1][0])
                cy = min(max(dt[1], dest_bb[0][1]), dest_bb[1][1])
                checks.append(Check(
                    "drop_in_container", "fail", dest_path,
                    f"drop_target {_fmt(dt)} is outside {dest_path} footprint",
                    fix={"action": "move_drop_target", "path": dest_path,
                         "constraint": "drop_xy in dest_aabb",
                         "suggest_position": [round(cx, 3), round(cy, 3), round(top + 0.05, 3)],
                         "human": f"clamp drop XY into {dest_path}, e.g. {[round(cx,3), round(cy,3), round(top+0.05,3)]}"},
                ))
            elif dt[2] < top - 0.02:
                checks.append(Check(
                    "drop_in_container", "warn", dest_path,
                    f"drop z {dt[2]:.2f} is below {dest_path} top {top:.2f} (drop above the rim)",
                    fix={"action": "move_drop_target", "path": dest_path,
                         "constraint": f"drop_z >= {top:.2f}",
                         "suggest_position": [round(dt[0], 3), round(dt[1], 3), round(top + 0.05, 3)],
                         "human": f"raise drop z above {dest_path} top ({top:.2f})"},
                ))
            else:
                checks.append(Check("drop_in_container", "pass", dest_path))

    # ---- support: each picked workpiece rests on a surface (not floating/buried) ----
    surface_tops = _surface_tops(aabbs, by_path)
    for pk in picks:
        bb = aabbs.get(pk)
        o = by_path.get(pk)
        if bb is None or o is None:
            continue
        if _is_dynamic(o.get("asset_name", "")):
            continue  # on a belt/feed — skip support
        bottom = bb[0][2]
        cx = (bb[0][0] + bb[1][0]) / 2
        cy = (bb[0][1] + bb[1][1]) / 2
        nearest_top = _nearest_surface_top_under(cx, cy, bottom, aabbs, pk, surface_tops)
        if nearest_top is None:
            continue  # no surface info -> skip (degrade silently)
        gap = bottom - nearest_top
        if gap < -_SUPPORT_REST_TOL_M:
            checks.append(Check(
                "support", "fail", pk,
                f"{pk} bottom z={bottom:.2f} is {-gap:.2f}m BELOW the surface top {nearest_top:.2f} (buried)",
                fix={"action": "move_object", "path": pk,
                     "constraint": f"bottom_z >= {nearest_top:.2f}",
                     "suggest_position": [round(cx, 3), round(cy, 3), round(nearest_top + 0.001, 3)],
                     "human": f"raise {pk} to rest on the surface top {nearest_top:.2f}"},
            ))
        elif gap > _SUPPORT_FLOAT_WARN_M:
            checks.append(Check("support", "warn", pk,
                                f"{pk} floats {gap:.2f}m above the nearest surface — verify it is meant to fall"))
        else:
            checks.append(Check("support", "pass", pk))

    # ---- declared relations (P1-20): verify INTENT, don't guess from geometry ----
    _verify_relations(layout.get("relations") or [], aabbs, checks)

    # ---- footprint / cell bounds ----
    if cell_bounds:
        xb = cell_bounds.get("x")
        yb = cell_bounds.get("y")
        for p, bb in aabbs.items():
            if xb and (bb[0][0] < xb[0] or bb[1][0] > xb[1]) or \
               yb and (bb[0][1] < yb[0] or bb[1][1] > yb[1]):
                checks.append(Check("footprint", "fail", p,
                                    f"{p} extends outside cell bounds x={xb} y={yb}"))

    return _assemble(checks)


_REL_TOL_M = 0.03  # contact tolerance for on_top_of/supports


def _verify_relations(relations: List[Dict[str, Any]],
                      aabbs: Dict[str, AABB], checks: List[Check]) -> None:
    """P1-20 — verify DECLARED inter-object relations geometrically.

    Each relation: {type, from, to (or from_id/to_id), severity?: hard|soft,
    value?: float}. Geometric types verified statically: on_top_of/supports,
    above, inside/contains, beside. Semantic types (feeds/handoff/sequence)
    are noted as skipped — they need runtime/inter-cell context, not geometry.
    A violated ``hard`` relation fails with an actionable fix; ``soft`` warns.
    """
    for i, rel in enumerate(relations):
        rtype = rel.get("type", "")
        a_path = rel.get("from") or rel.get("from_id") or ""
        b_path = rel.get("to") or rel.get("to_id") or ""
        sev = rel.get("severity", "hard")
        cid = f"relation:{rtype}"
        a, b = aabbs.get(a_path), aabbs.get(b_path)
        if rtype in ("feeds", "handoff", "sequence"):
            checks.append(Check(cid, "skipped", f"{a_path}->{b_path}",
                                f"{rtype} is semantic — verified at runtime/inter-cell, not statically"))
            continue
        if a is None or b is None:
            checks.append(Check(cid, "fail" if sev == "hard" else "warn", f"{a_path}->{b_path}",
                                f"relation[{i}] {rtype}: unknown object "
                                f"{'(from)' if a is None else '(to)'} — no bbox derivable"))
            continue
        if rtype in ("contains",):  # contains(B holds A-args swapped) -> normalize to inside
            a_path, b_path, a, b = b_path, a_path, b, a
            rtype = "inside"
        ok, msg, suggest = True, "", None
        if rtype in ("on_top_of", "supports"):
            xy = _aabb_xy_overlap(a, b)
            gap = a[0][2] - b[1][2]  # A bottom vs B top
            ok = xy and abs(gap) <= _REL_TOL_M
            if not ok:
                msg = (f"{a_path} declared on_top_of {b_path} but "
                       + ("no XY overlap" if not xy else f"vertical gap {gap:+.3f}m"))
                bcx = (b[0][0] + b[1][0]) / 2; bcy = (b[0][1] + b[1][1]) / 2
                suggest = [round(bcx, 3), round(bcy, 3), round(b[1][2] + 0.001, 3)]
        elif rtype == "above":
            ok = _aabb_xy_overlap(a, b) and a[0][2] > b[1][2] - 1e-6
            if not ok:
                msg = f"{a_path} declared above {b_path} but is not (xy-overlap + higher z required)"
        elif rtype == "inside":
            ok = (_xy_inside(((a[0][0] + a[1][0]) / 2, (a[0][1] + a[1][1]) / 2, 0.0), b)
                  and a[0][2] >= b[0][2] - _REL_TOL_M and a[0][2] <= b[1][2])
            if not ok:
                msg = f"{a_path} declared inside {b_path} but its centre/base falls outside the container"
                bcx = (b[0][0] + b[1][0]) / 2; bcy = (b[0][1] + b[1][1]) / 2
                suggest = [round(bcx, 3), round(bcy, 3), round(b[0][2] + 0.001, 3)]
        elif rtype == "beside":
            clearance = float(rel.get("value") or 0.30)
            if _aabb_xy_overlap(a, b):
                ok, msg = False, f"{a_path} declared beside {b_path} but their footprints overlap"
            else:
                dx = max(b[0][0] - a[1][0], a[0][0] - b[1][0], 0.0)
                dy = max(b[0][1] - a[1][1], a[0][1] - b[1][1], 0.0)
                gap = max(dx, dy)
                ok = gap <= clearance
                if not ok:
                    msg = f"{a_path} declared beside {b_path} but gap {gap:.2f}m > {clearance:.2f}m"
        else:
            checks.append(Check(cid, "skipped", f"{a_path}->{b_path}",
                                f"unknown relation type {rtype!r}"))
            continue
        if ok:
            checks.append(Check(cid, "pass", f"{a_path}->{b_path}"))
        else:
            fix = None
            if suggest is not None:
                fix = {"action": "move_object", "path": a_path,
                       "constraint": f"{rtype} {b_path}",
                       "suggest_position": suggest,
                       "human": f"move {a_path} to satisfy {rtype} {b_path}, e.g. {suggest}"}
            checks.append(Check(cid, "fail" if sev == "hard" else "warn",
                                f"{a_path}->{b_path}", msg, fix=fix))


def _project_to_sphere(p: Vec3, base: Vec3, radius: float) -> Vec3:
    d = _dist(p, base)
    if d < 1e-9:
        return (base[0] + radius, base[1], base[2])
    k = radius / d
    return (base[0] + (p[0] - base[0]) * k,
            base[1] + (p[1] - base[1]) * k,
            base[2] + (p[2] - base[2]) * k)


def _surface_tops(aabbs: Dict[str, AABB], by_path: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    out = {}
    for p, bb in aabbs.items():
        o = by_path.get(p, {})
        cat = (PALETTE.get(o.get("asset_name", "")) or PALETTE.get("table_small")).category \
            if PALETTE.get(o.get("asset_name", "")) else "prop"
        if cat in ("fixture", "environment"):
            out[p] = bb[1][2]
    return out


def _nearest_surface_top_under(cx: float, cy: float, bottom: float,
                               aabbs: Dict[str, AABB], self_path: str,
                               surface_tops: Dict[str, float]) -> Optional[float]:
    best = None
    for p, top in surface_tops.items():
        if p == self_path:
            continue
        bb = aabbs[p]
        if bb[0][0] <= cx <= bb[1][0] and bb[0][1] <= cy <= bb[1][1]:
            # a support surface must be AT or BELOW the object bottom (the object
            # rests ON it) — a higher fixture is a container the object goes into,
            # not a surface it sits on. Pick the highest qualifying surface.
            if top <= bottom + _SUPPORT_REST_TOL_M and (best is None or top > best):
                best = top
    return best


def _fmt(v: Vec3) -> str:
    return "[" + ",".join(f"{x:.2f}" for x in v) + "]"


def _assemble(checks: List[Check]) -> StaticEyesReport:
    has_fail = any(c.status == "fail" for c in checks)
    has_uncertain = any(c.status == "uncertain" for c in checks)
    fix_order = [c.id for c in checks if c.status == "fail"]
    if has_fail:
        verdict, next_gate = "FAIL", "fix_and_recall_static_eyes"
    elif has_uncertain:
        verdict, next_gate = "UNCERTAIN", "tier2_reach_probe"
    else:
        verdict, next_gate = "PASS", "function_gate"
    caveats = [
        "reach:shell is a NECESSARY shell test, not IK — a PASS still needs function_gate.",
        "UNCERTAIN reach targets need a live cuRobo single-IK probe (tier-2), not a physics settle.",
        "occlusion is a straight-line advisory; the arm may route around it.",
    ]
    return StaticEyesReport(verdict=verdict, checks=checks,
                            overall_fix_order=fix_order, next_gate=next_gate,
                            caveats=caveats)


def reach_diagnostics(report: StaticEyesReport) -> Dict[str, Any]:
    """Shape the report into the ``verify:reach`` form-gate arg
    (``{all_reachable, unreachable:[...]}``) so static_eyes fills that stub."""
    unreachable = [c.target for c in report.checks
                   if c.id == "reach:shell" and c.status == "fail"]
    return {"all_reachable": not unreachable, "unreachable": unreachable}
