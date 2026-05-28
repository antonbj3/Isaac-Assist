"""
Bridge-1 smoke test — multimodal LayoutSpec → canonical instantiation.

Verifies the wire landed per docs/notes/2026-05-28-multimodal-canonical-flow.md §5:

  1. ``bindings_to_role_dict(spec)`` walks LayoutSpec.bindings and emits a
     role_defaults-shaped dict pulling positions from the user's TypedObjects.
  2. ``execute_template_canonical(template, role_bindings=...)`` accepts the
     new parameter and OVERRIDES ``template["role_defaults"]`` during
     code_template substitution.

Scope: ONE template end-to-end (CP-NEW-bin-picking-random-pose — the canonical
the design doc tracks). Other templates follow the same plumbing.

Out of scope: HTTP route integration (covered separately when canvas SPA
e2e lands), VLM modality wiring, planner/router/funnel — all post-Bridge-1.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

pytestmark = pytest.mark.l0


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def bin_picking_template() -> Dict[str, Any]:
    """The CP-NEW-bin-picking-random-pose template loaded from disk.

    This is the design-doc reference canonical (§4 walkthrough). It has all
    three role-based fields (``roles``, ``role_defaults``, ``code_template``)
    so it routes through the role-based instantiation path.
    """
    repo_root = Path(__file__).resolve().parent.parent
    p = repo_root / "workspace" / "templates" / "CP-NEW-bin-picking-random-pose.json"
    if not p.exists():
        pytest.skip(f"reference template not found at {p}")
    template = json.loads(p.read_text())
    assert template.get("code_template"), "fixture template lacks code_template"
    assert template.get("roles"), "fixture template lacks roles"
    assert template.get("role_defaults"), "fixture template lacks role_defaults"
    return template


@pytest.fixture
def layout_spec_with_bindings():
    """A LayoutSpec carrying 1 Franka + 2 bins + 1 cube and explicit
    bindings for the bin-picking template's four roles.

    Positions are intentionally OFFSET from the template's role_defaults so
    the test can verify the user's xy substitutes through. Only one cube is
    bound (workpieces falls back to defaults — that's expected; multi-instance
    list binding is out-of-scope for Bridge-1)."""
    from service.isaac_assist_service.multimodal.types import (
        Intent,
        LayoutSpec,
        Position,
        RoleBinding,
        Size,
        Source,
        TypedObject,
    )

    robot = TypedObject(
        id="obj_robot",
        name="UserFranka",
        position=Position(x=1.23, y=4.56),
        size=Size(w=0.4, h=0.4),
        **{"class": "franka_panda"},
    )
    src_bin = TypedObject(
        id="obj_src",
        name="UserSourceBin",
        position=Position(x=0.5, y=2.0),
        size=Size(w=0.35, h=0.35),
        **{"class": "bin"},
    )
    dst_bin = TypedObject(
        id="obj_dst",
        name="UserDestBin",
        position=Position(x=-0.5, y=2.0),
        size=Size(w=0.35, h=0.35),
        **{"class": "bin"},
    )

    spec = LayoutSpec(
        intent=Intent(pattern_hint="pick_place"),
        objects=[robot, src_bin, dst_bin],
        bindings={
            "primary_robot": RoleBinding(
                object_id="obj_robot", source="user_explicit", confidence=1.0,
            ),
            "source_bin": RoleBinding(
                object_id="obj_src", source="user_explicit", confidence=1.0,
            ),
            "destination_bin": RoleBinding(
                object_id="obj_dst", source="user_explicit", confidence=1.0,
            ),
        },
        source=Source(modality="drag_drop", confidence=1.0),
    )
    return spec


# ── 1. bindings_to_role_dict adapter ────────────────────────────────────────


def test_adapter_converts_bindings_to_role_defaults_shape(layout_spec_with_bindings):
    """The adapter walks spec.bindings and emits per-role dicts with path /
    class / position pulled from the bound TypedObject."""
    from service.isaac_assist_service.multimodal.binding_adapter import (
        bindings_to_role_dict,
    )

    out = bindings_to_role_dict(layout_spec_with_bindings)

    assert set(out.keys()) == {"primary_robot", "source_bin", "destination_bin"}

    robot = out["primary_robot"]
    assert robot["path"] == "/World/UserFranka"
    assert robot["class"] == "franka_panda"
    assert robot["position"] == [1.23, 4.56, 0.0]
    assert robot["name"] == "UserFranka"
    assert robot["id"] == "obj_robot"

    src = out["source_bin"]
    assert src["path"] == "/World/UserSourceBin"
    assert src["position"] == [0.5, 2.0, 0.0]


def test_adapter_returns_empty_when_no_bindings():
    """No bindings or no objects → empty dict; do not raise."""
    from service.isaac_assist_service.multimodal.binding_adapter import (
        bindings_to_role_dict,
    )
    from service.isaac_assist_service.multimodal.types import (
        Intent, LayoutSpec, Source,
    )

    spec = LayoutSpec(
        intent=Intent(pattern_hint="other"),
        source=Source(modality="text", confidence=0.5),
    )
    assert bindings_to_role_dict(spec) == {}


def test_adapter_skips_unresolvable_object_id():
    """A binding pointing at an object_id absent from spec.objects is
    silently dropped (logged); other roles still bind."""
    from service.isaac_assist_service.multimodal.binding_adapter import (
        bindings_to_role_dict,
    )
    from service.isaac_assist_service.multimodal.types import (
        Intent,
        LayoutSpec,
        Position,
        RoleBinding,
        Size,
        Source,
        TypedObject,
    )

    obj = TypedObject(
        id="obj_real",
        name="RealObj",
        position=Position(x=0, y=0),
        size=Size(w=0.1, h=0.1),
        **{"class": "cube"},
    )
    spec = LayoutSpec(
        intent=Intent(pattern_hint="pick_place"),
        objects=[obj],
        bindings={
            "real_role": RoleBinding(
                object_id="obj_real", source="user_explicit", confidence=1.0,
            ),
            "ghost_role": RoleBinding(
                object_id="obj_missing", source="user_explicit", confidence=1.0,
            ),
        },
        source=Source(modality="drag_drop", confidence=1.0),
    )

    out = bindings_to_role_dict(spec)
    assert "real_role" in out
    assert "ghost_role" not in out


# ── 2. execute_template_canonical accepts role_bindings ─────────────────────


def test_role_bindings_override_role_defaults_in_substitution(bin_picking_template):
    """instantiate_role_based_code(template, role_bindings) — when bindings
    supplied, they replace role_defaults as the substitution source.

    This is the pure-function half of the Bridge-1 wire (no async / no Kit
    needed). It proves the substitution machinery accepts the new path."""
    from service.isaac_assist_service.chat.canonical_instantiator import (
        instantiate_role_based_code,
    )

    # Default-path substitution — uses authored role_defaults (Franka at z=0.75)
    default_code = instantiate_role_based_code(bin_picking_template)
    assert "/World/Franka" in default_code
    # role_defaults.position = [0, 0, 0.75]
    assert "[0, 0, 0.75]" in default_code

    # Override path — Bridge-1 supplies role_bindings with user positions
    user_bindings = {
        "primary_robot": {
            "path": "/World/UserFranka",
            "class": "franka_panda",
            "position": [1.23, 4.56, 0.0],
            "orientation": [1, 0, 0, 0],
        },
        "source_bin": {
            "path": "/World/UserSourceBin",
            "class": "bin",
            "position": [0.5, 2.0, 0.0],
            "size": [0.35, 0.35, 0.2],
            "wall_thickness": 0.01,
        },
        "destination_bin": {
            "path": "/World/UserDestBin",
            "class": "bin",
            "position": [-0.5, 2.0, 0.0],
            "size": [0.35, 0.35, 0.2],
            "wall_thickness": 0.01,
        },
        # workpieces deliberately omitted → falls back from role_defaults
        # via Bridge-1 semantics (role_bindings = ALL OR NOTHING per the
        # current substitute_role_placeholders contract). NB: a future
        # iteration may merge per-role defaults beneath bindings.
        "workpieces": bin_picking_template["role_defaults"]["workpieces"],
    }

    overridden_code = instantiate_role_based_code(
        bin_picking_template, role_bindings=user_bindings,
    )

    # User-positioned robot present
    assert "/World/UserFranka" in overridden_code
    assert "[1.23, 4.56, 0.0]" in overridden_code

    # User bins present
    assert "/World/UserSourceBin" in overridden_code
    assert "[0.5, 2.0, 0.0]" in overridden_code
    assert "/World/UserDestBin" in overridden_code
    assert "[-0.5, 2.0, 0.0]" in overridden_code

    # And the default-path positions are GONE for the overridden roles
    assert "/World/Franka\n" not in overridden_code  # exact default robot path
    assert "[0, 0, 0.75]" not in overridden_code   # default robot position


@pytest.mark.asyncio
async def test_execute_template_canonical_passes_role_bindings_through(
    bin_picking_template, layout_spec_with_bindings, monkeypatch,
):
    """End-to-end Bridge-1: LayoutSpec → adapter → execute_template_canonical.

    Patches execute_tool_call so no Kit RPC is touched — we only verify the
    captured tool call args contain the user-supplied paths/positions, not
    the authored defaults. This is the load-bearing assertion that the wire
    is connected end-to-end."""
    from service.isaac_assist_service.chat import canonical_instantiator
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical,
    )
    from service.isaac_assist_service.multimodal.binding_adapter import (
        bindings_to_role_dict,
    )

    captured: List[Tuple[str, Dict[str, Any]]] = []

    async def _fake_execute_tool_call(tool_name: str, args: Dict[str, Any]):
        captured.append((tool_name, dict(args)))
        return {"type": "ok", "success": True, "output": "stub"}

    # Patch the tool_executor module that canonical_instantiator imports from.
    from service.isaac_assist_service.chat.tools import tool_executor as te_mod
    monkeypatch.setattr(te_mod, "execute_tool_call", _fake_execute_tool_call)

    # Bridge-1 callers merge adapter output OVER template defaults so
    # template-specific fields the adapter doesn't yet know about
    # (wall_thickness, spawn_offset, workpieces list, ...) keep their
    # authored values. Per-role merge — adapter wins per-field for the
    # roles the user bound, defaults pass through for the rest.
    adapter_bindings = bindings_to_role_dict(layout_spec_with_bindings)
    role_bindings: Dict[str, Any] = dict(bin_picking_template["role_defaults"])
    for role_name, user_fields in adapter_bindings.items():
        merged = dict(role_bindings.get(role_name) or {})
        merged.update(user_fields)
        role_bindings[role_name] = merged

    result = await execute_template_canonical(
        bin_picking_template, role_bindings=role_bindings,
    )

    assert result["instantiated"] is True, result.get("errors")
    assert result["n_calls"] > 0

    # Find the robot_wizard call and verify it received the user's path,
    # not the authored default "/World/Franka".
    robot_calls = [a for (t, a) in captured if t == "robot_wizard"]
    assert robot_calls, f"no robot_wizard in {[t for t,_ in captured]!r}"
    assert robot_calls[0].get("dest_path") == "/World/UserFranka"
    assert robot_calls[0].get("position") == [1.23, 4.56, 0.0]

    # Find a create_bin call referencing the user source bin path.
    bin_calls = [a for (t, a) in captured if t == "create_bin"]
    bin_paths = [a.get("prim_path") for a in bin_calls]
    assert "/World/UserSourceBin" in bin_paths
    assert "/World/UserDestBin" in bin_paths

    # And the authored-default bin paths should NOT have leaked through.
    assert "/World/SourceBin" not in bin_paths
    assert "/World/OutfeedBin" not in bin_paths
