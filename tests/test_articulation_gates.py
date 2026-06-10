"""L0 tests for the articulation gate classes [P5-22]."""
import ast
import asyncio

import pytest

from service.isaac_assist_service.chat.tools.handlers import articulation_gates as ag

pytestmark = pytest.mark.l0


def _capture_code(monkeypatch):
    captured = {}

    async def fake_queue(code, desc, timeout=None):
        captured["code"] = code
        captured["timeout"] = timeout
        return {"type": "code_patch", "queued": True}

    from service.isaac_assist_service.chat.tools import kit_tools
    monkeypatch.setattr(kit_tools, "queue_exec_patch", fake_queue)
    return captured


def test_verify_articulation_emits_parseable_probe(monkeypatch):
    cap = _capture_code(monkeypatch)
    res = asyncio.run(ag._handle_verify_articulation(
        {"articulation_path": "/World/Door", "joint_name": "door_hinge"}))
    assert res.get("queued") is True
    ast.parse(cap["code"])
    for marker in ("ArticulationRootAPI", "PhysicsRevoluteJoint",
                   "PhysicsPrismaticJoint", "limits_sane", "door_hinge",
                   "ARTICULATION_VERIFY="):
        assert marker in cap["code"], marker


def test_articulation_gate_min_delta_mode(monkeypatch):
    cap = _capture_code(monkeypatch)
    res = asyncio.run(ag._handle_simulate_articulation_check(
        {"joint_path": "/World/Door/hinge", "min_delta_deg": 60,
         "duration_s": 45}))
    assert res.get("queued") is True
    ast.parse(cap["code"])
    assert "state:angular:physics:position" in cap["code"]
    assert "ARTICULATION_GATE=" in cap["code"]
    assert cap["timeout"] == 45 + 120
    # settle check present — a still-swinging door must not PASS
    assert "settled" in cap["code"]


def test_articulation_gate_requires_a_criterion():
    res = asyncio.run(ag._handle_simulate_articulation_check(
        {"joint_path": "/W/j"}))
    assert res["type"] == "error"


def test_registered_in_executor():
    from service.isaac_assist_service.chat.tools.tool_executor import DATA_HANDLERS
    assert "verify_articulation" in DATA_HANDLERS
    assert "simulate_articulation_check" in DATA_HANDLERS


def test_gate_body_path_fallback_emitted(monkeypatch):
    """Passive joints (no JointStateAPI, broken body rels — the live
    drawer-open class) need the explicit body_path world-pos fallback."""
    cap = _capture_code(monkeypatch)
    asyncio.run(ag._handle_simulate_articulation_check(
        {"joint_path": "/W/J", "body_path": "/W/Drawer",
         "min_delta_deg": 0.1}))
    ast.parse(cap["code"])
    assert "'/W/Drawer'" in cap["code"]
    assert "body1_world" in cap["code"]
    assert "measure_mode" in cap["code"]
