"""
Bridge-1 adapter: LayoutSpec role bindings → canonical-instantiator role_defaults shape.

Background
----------
``LayoutSpec.bindings`` (after ``ratify(template, spec)`` returns ``status="ok"``)
maps each template role to a :class:`RoleBinding` whose ``object_id`` points
back at the matching :class:`TypedObject` in ``spec.objects``.

The role-based code_template substitution machinery in
``canonical_instantiator.substitute_role_placeholders`` consumes a
*different* shape — the same shape as ``template["role_defaults"]``:

    {
      "primary_robot": {
        "path": "/World/Franka",
        "class": "franka_panda",
        "position": [x, y, z],
        "orientation": [w, x, y, z],
      },
      "workpieces": [
        {"path": "/World/Cube_1", "position": [...]},
        ...
      ],
      ...
    }

This adapter is the load-bearing wire from "modality emitted bindings" to
"canonical code substitution" — the single bridge the design has been
missing per ``docs/notes/2026-05-28-multimodal-canonical-flow.md`` §3D and
§5 (Bridge-1 item 2). No template edits needed; templates already consume
this shape via ``role_defaults``.

Out of scope for Bridge-1
-------------------------
- Multi-instance roles backed by EXPLICIT bindings (RoleBinding is a single
  object_id per role today; list-roles like ``workpieces`` fall back to
  multiple objects matched by ``role_hint`` in a future iteration).
- Compliance fields (compliance_mode, compliance_params) — those flow
  through ``resolve_compliance`` in :mod:`ratify`, not here.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .types import LayoutSpec, RoleBinding, TypedObject

logger = logging.getLogger(__name__)


def _typed_object_to_role_dict(obj: TypedObject) -> Dict[str, Any]:
    """Render one TypedObject into the field shape canonical templates expect.

    Maps the LayoutSpec object's 2-D drawing-space coordinates into a
    3-D position triplet with z=0 (canvas/sketch are flat layouts; the
    canonical's authored z stays useful as a fallback, but the user's xy
    is load-bearing).

    Returns dict with keys:
      - ``path``     USD prim path (``/World/{name}``)
      - ``class``    object_class (the alias for ``object_class``)
      - ``position`` [x, y, 0.0]
      - ``orientation`` [w, x, y, z] identity quaternion. LayoutSpec stores
        rotation as a single Z-axis degree value; canonical templates
        consume a full quaternion via ``{{role.orientation}}``. Identity
        is the safe default; future iterations may compute the quat from
        ``obj.rotation`` when canonicals need true yaw.
      - ``size``     [w, h] (kept separate from rotation for clarity)
      - ``rotation`` raw degrees (echoed for templates that consume it)
      - ``name``     raw name (USD-identifier safe per TypedObject validator)
      - ``id``       LayoutSpec object id (echo for downstream debugging)
    """
    return {
        "path": f"/World/{obj.name}",
        "class": obj.object_class,
        "position": [obj.position.x, obj.position.y, 0.0],
        "orientation": [1.0, 0.0, 0.0, 0.0],
        "size": [obj.size.w, obj.size.h],
        "rotation": obj.rotation,
        "name": obj.name,
        "id": obj.id,
    }


def bindings_to_role_dict(spec: LayoutSpec) -> Dict[str, Any]:
    """Convert ``LayoutSpec.bindings`` → role_defaults-shaped dict.

    For each ratified role binding, look up the bound TypedObject in
    ``spec.objects`` and emit a per-role dict matching the shape consumed
    by :func:`canonical_instantiator.substitute_role_placeholders`
    (i.e. the same shape as ``template["role_defaults"]``).

    Args:
        spec: A ratified LayoutSpec — typically the spec returned from
            ``ratify(template, spec)`` with status ``ok``.

    Returns:
        Mapping ``{role_name: {path, class, position, size, ...}, ...}``.
        Roles whose binding's ``object_id`` cannot be resolved to a
        TypedObject are silently dropped (and logged). Returns ``{}`` when
        spec has no bindings or no objects.
    """
    if not spec.bindings or not spec.objects:
        return {}

    # Build an O(1) object_id → TypedObject index once.
    by_id: Dict[str, TypedObject] = {obj.id: obj for obj in spec.objects}

    out: Dict[str, Any] = {}
    for role_name, binding in spec.bindings.items():
        if not isinstance(binding, RoleBinding):
            # Pydantic models sometimes round-trip as dicts when callers
            # construct LayoutSpec from raw JSON; tolerate that.
            try:
                binding = RoleBinding(**binding)  # type: ignore[arg-type]
            except Exception:
                logger.debug(
                    f"[binding_adapter] role={role_name}: binding is not a RoleBinding "
                    f"and cannot be coerced ({type(binding).__name__}); skipping"
                )
                continue

        obj = by_id.get(binding.object_id)
        if obj is None:
            logger.debug(
                f"[binding_adapter] role={role_name}: binding object_id="
                f"{binding.object_id!r} not present in spec.objects ({len(by_id)} known); "
                f"skipping"
            )
            continue
        out[role_name] = _typed_object_to_role_dict(obj)

    return out


__all__ = ["bindings_to_role_dict"]
