"""L0 tests for the static_eyes LLM-callable tool registration (P1-10).

Covers: handler verdict on a good/bad layout, the error contract on a missing
layout, DATA_HANDLERS registration, and the tool_schemas entry.
"""
import pytest

from service.isaac_assist_service.chat.tools.multimodal_handlers import (
    _handle_static_eyes,
    register_multimodal_handlers,
)

pytestmark = pytest.mark.l0


def _good_layout():
    return {
        "robots": [{"path": "/World/UR10", "family": "ur10", "base": [0.0, 0.0, 1.0]}],
        "objects": [
            {"path": "/World/Cube_1", "position": [0.4, -0.3, 1.05], "asset_name": "cube_medium"},
            {"path": "/World/Bin", "position": [0.5, -0.4, 0.95], "asset_name": "bin"},
            {"path": "/World/Table", "position": [0.4, -0.3, 0.5], "asset_name": "table_medium",
             "bbox": [[-0.2, -0.7, 0.0], [1.0, 0.1, 1.0]]},
        ],
        "picks": ["/World/Cube_1"],
        "places": [{"target_path": "/World/Bin", "drop_target": [0.5, -0.4, 1.15]}],
    }


async def test_handler_pass_verdict():
    out = await _handle_static_eyes({"layout": _good_layout()})
    assert "error" not in out
    assert out["verdict"] == "PASS"
    assert out["next_gate"] == "function_gate"
    assert out["reach_diagnostics"] == {"all_reachable": True, "unreachable": []}


async def test_handler_fail_carries_actionable_fix():
    layout = _good_layout()
    layout["objects"][0]["position"] = [0.4, -1.6, 1.05]  # out of UR10 reach
    out = await _handle_static_eyes({"layout": layout})
    assert out["verdict"] == "FAIL"
    fails = [c for c in out["checks"] if c["status"] == "fail"]
    assert fails and fails[0]["fix"]["suggest_position"]
    assert out["reach_diagnostics"]["all_reachable"] is False


async def test_handler_requires_layout():
    out = await _handle_static_eyes({})
    assert "error" in out and "layout" in out["error"]


def test_registration_includes_static_eyes():
    handlers = {}
    register_multimodal_handlers(handlers)
    assert "static_eyes" in handlers
    assert handlers["static_eyes"] is _handle_static_eyes
    assert len(handlers) == 7


def test_schema_entry_exists():
    from service.isaac_assist_service.chat.tools.tool_schemas import ISAAC_SIM_TOOLS
    names = [t["function"]["name"] for t in ISAAC_SIM_TOOLS if t.get("type") == "function"]
    assert "static_eyes" in names
    entry = next(t for t in ISAAC_SIM_TOOLS if t.get("function", {}).get("name") == "static_eyes")
    assert entry["function"]["parameters"]["required"] == ["layout"]
