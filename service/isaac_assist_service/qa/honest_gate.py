"""Honest-delivery-gate pure logic (P0-18).

The ``simulate_traversal_check`` handler in
``chat/tools/handlers/diagnostics.py`` runs the physics-bound sim inside Kit
RPC and produces, per cube, a small bundle of measured booleans/values:
``in_xy``, ``above_floor``, ``at_rest``, ``final`` position, plus an optional
raycast-down ``support`` prim path. That measurement is necessarily
Kit-bound and stays inlined in the codegen string.

This module factors out the *pure* grading that sits on TOP of those
measurements so it is unit-testable without a running Kit:

  1. per-cube target resolution — which destination is THIS cube graded
     against (per-bin routing for 2/3-way sort templates, or the single
     global ``target_path``);
  2. misroute detection — a cube at rest inside a DIFFERENT listed target
     is NOT a success even if it "delivered" to some bbox;
  3. completeness aggregation — ``any`` (legacy), ``all``, or
     ``{"min_delivered": N}``.

The equivalent of :func:`classify_cube` + :func:`aggregate_completeness`
is also inlined verbatim into the codegen string so the live gate and the
unit tests grade identically. Keep the two copies in lock-step.

BACKWARDS COMPATIBILITY CONTRACT
--------------------------------
When no routing map is supplied and ``completeness="any"`` (the defaults),
:func:`grade` reproduces the legacy verdict byte-for-byte:

    multi-cube:  success = bool(delivered) and upright_ok
    single-cube: success = (in_xy and above_floor and at_rest and upright_ok)

New behavior (per-bin routing, misroute rejection, ``all`` /
``min_delivered`` completeness) activates ONLY through the new args.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Routing-map normalization
# ---------------------------------------------------------------------------

def normalize_routing(
    cube_paths: Sequence[str],
    global_target: str,
    targets: Optional[Mapping[str, str]] = None,
    routing: Optional[Sequence[Mapping[str, str]]] = None,
) -> Dict[str, str]:
    """Resolve each cube to the destination prim path it is graded against.

    Accepts either of two equivalent shapes (both optional):

      * ``targets`` — a flat ``{cube_path: target_path}`` map, e.g.
        ``{"/World/Cube_1": "/World/BinA", "/World/Cube_2": "/World/BinB"}``.
      * ``routing`` — a list of ``{"cube": ..., "target": ...}`` dicts
        (order-preserving, friendlier for JSON tool-calls).

    Any cube not named in the map falls back to ``global_target`` so a
    PARTIAL routing map (route Cube_1->BinA, leave the rest on the default
    bin) still works. If BOTH ``targets`` and ``routing`` are empty the
    result is every cube -> ``global_target`` (legacy single-target mode).

    Returns ``{cube_path: target_path}`` for every cube in ``cube_paths``.
    """
    resolved: Dict[str, str] = {}
    if routing:
        for entry in routing:
            if not isinstance(entry, Mapping):
                continue
            cube = entry.get("cube") or entry.get("cube_path")
            tgt = entry.get("target") or entry.get("target_path")
            if cube and tgt:
                resolved[str(cube)] = str(tgt)
    if targets:
        for cube, tgt in targets.items():
            if cube and tgt:
                resolved[str(cube)] = str(tgt)
    return {cp: resolved.get(cp, global_target) for cp in cube_paths}


def all_targets(per_cube_target: Mapping[str, str]) -> List[str]:
    """Distinct destination prim paths referenced by the routing map.

    Used to detect misroutes: a cube resting inside ANY listed target that
    is not ITS assigned target is misrouted.
    """
    seen: List[str] = []
    for t in per_cube_target.values():
        if t and t not in seen:
            seen.append(t)
    return seen


# ---------------------------------------------------------------------------
# Per-cube classification
# ---------------------------------------------------------------------------

def _under(support_path: Optional[str], target: str) -> bool:
    """Is ``support_path`` the target prim or a descendant of it?

    Mirrors the codegen ``under`` test: exact match OR ``target + "/"``
    prefix. ``None`` support (no raycast hit) -> False.
    """
    if not support_path or not target:
        return False
    sp = str(support_path)
    return sp == target or sp.startswith(target + "/")


def classify_cube(
    cube: str,
    measured: Mapping[str, Any],
    assigned_target: str,
    other_targets: Sequence[str],
) -> Dict[str, Any]:
    """Grade ONE cube from its Kit-measured bundle.

    ``measured`` is the per-cube physics bundle produced by the sim:
        - ``in_xy`` (bool): final XY inside assigned-target bbox (already
          computed against the assigned target's bbox by the caller).
        - ``above_floor`` (bool): final Z at/above target floor.
        - ``at_rest`` (bool): speed < rest threshold.
        - ``final`` (list[float] | None): final world XYZ (for reporting).
        - ``support`` (str | None): raycast-down support prim path.
        - ``upright_ok`` (bool, optional): per-cube upright gate; defaults
          True when absent (single global upright gate handled by caller).

    A cube is ``delivered`` iff it is in its assigned target bbox, above the
    floor, at rest, and upright -- the SAME conjunction the legacy single-cube
    path used.

    ``misrouted`` fires when the cube is at rest and its raycast support is a
    DIFFERENT listed target (or descendant) than its assigned one. A
    misrouted cube is never counted as delivered.
    """
    in_xy = bool(measured.get("in_xy"))
    above = bool(measured.get("above_floor"))
    at_rest = bool(measured.get("at_rest"))
    upright_ok = bool(measured.get("upright_ok", True))
    support = measured.get("support")
    final = measured.get("final")

    # Misroute: at rest on/inside some OTHER listed target.
    misrouted = False
    actual_location = assigned_target if _under(support, assigned_target) else None
    if at_rest:
        for ot in other_targets:
            if ot == assigned_target:
                continue
            if _under(support, ot):
                misrouted = True
                actual_location = ot
                break

    delivered = bool(in_xy and above and at_rest and upright_ok and not misrouted)

    return {
        "cube": cube,
        "delivered": delivered,
        "target": assigned_target,
        "actual_location": actual_location,
        "misrouted": misrouted,
        "in_xy": in_xy,
        "above_floor": above,
        "at_rest": at_rest,
        "upright_ok": upright_ok,
        "support": support,
        "final": final,
    }


# ---------------------------------------------------------------------------
# Completeness aggregation
# ---------------------------------------------------------------------------

def _parse_min_delivered(completeness: Any, total: int) -> int:
    """Map a ``completeness`` arg to the minimum delivered count required.

      * ``"any"``  (or None/empty)  -> 1  (legacy: at-least-one)
      * ``"all"``                    -> total
      * ``{"min_delivered": N}``     -> clamp(N, 1, total)
      * int N                        -> clamp(N, 1, total)
    """
    if completeness is None or completeness == "" or completeness == "any":
        return 1
    if completeness == "all":
        return total
    if isinstance(completeness, Mapping):
        n = completeness.get("min_delivered", 1)
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 1
        return max(1, min(n, total))
    if isinstance(completeness, (int, float)) and not isinstance(completeness, bool):
        return max(1, min(int(completeness), total))
    # Unknown string -> treat as legacy "any" (never tighten on garbage).
    return 1


def aggregate_completeness(
    per_cube: Sequence[Mapping[str, Any]],
    completeness: Any = "any",
) -> Dict[str, Any]:
    """Roll per-cube verdicts up to a single pass/fail under a policy.

    Returns ``{delivered_count, total, min_required, completeness_mode,
    misrouted_count, success}``.
    """
    total = len(per_cube)
    delivered_count = sum(1 for c in per_cube if c.get("delivered"))
    misrouted_count = sum(1 for c in per_cube if c.get("misrouted"))
    min_required = _parse_min_delivered(completeness, total)

    if isinstance(completeness, Mapping):
        mode = "min_delivered={}".format(min_required)
    elif completeness in (None, "", "any"):
        mode = "any"
    elif completeness == "all":
        mode = "all"
    else:
        mode = str(completeness)

    success = total > 0 and delivered_count >= min_required
    return {
        "delivered_count": delivered_count,
        "total": total,
        "min_required": min_required,
        "completeness_mode": mode,
        "misrouted_count": misrouted_count,
        "success": success,
    }


# ---------------------------------------------------------------------------
# Top-level pure grader (multi-cube)
# ---------------------------------------------------------------------------

def grade(
    cube_paths: Sequence[str],
    measured_by_cube: Mapping[str, Mapping[str, Any]],
    global_target: str,
    targets: Optional[Mapping[str, str]] = None,
    routing: Optional[Sequence[Mapping[str, str]]] = None,
    completeness: Any = "any",
) -> Dict[str, Any]:
    """End-to-end pure grade for the multi-cube path.

    BACKWARDS-COMPAT: with ``targets``/``routing`` empty and
    ``completeness="any"``, ``success`` equals the legacy
    ``bool(delivered) and upright_ok`` (because ``min_required == 1`` and no
    cube can be misrouted when every cube shares the one global target -- the
    "other targets" list is then empty).

    Returns ``{per_cube: [...], delivered_count, total, completeness_mode,
    success, ...}``.
    """
    per_cube_target = normalize_routing(cube_paths, global_target, targets, routing)
    targets_list = all_targets(per_cube_target)

    per_cube: List[Dict[str, Any]] = []
    for cp in cube_paths:
        measured = measured_by_cube.get(cp)
        if measured is None:
            continue
        assigned = per_cube_target[cp]
        per_cube.append(classify_cube(cp, measured, assigned, targets_list))

    agg = aggregate_completeness(per_cube, completeness)
    agg["per_cube"] = per_cube
    agg["routing_active"] = len(targets_list) > 1
    return agg
