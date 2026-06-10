"""L0 tests for the expand=True codegen contract [P2-02b]."""
import ast

import pytest

from service.isaac_assist_service.chat.tools.expand import (
    expand_sequence,
    expand_tool_call,
)

pytestmark = pytest.mark.l0


def test_expand_create_bin_returns_parseable_raw_code():
    code = expand_tool_call("create_bin", {
        "prim_path": "/World/Bin", "position": [0.5, -0.4, 0.75],
        "size": [0.3, 0.3, 0.15]})
    ast.parse(code)                      # valid python
    assert "/World/Bin" in code          # parameterized
    assert "create_bin(" not in code     # DE-abstracted: no tool-call left


def test_expand_unknown_or_data_tool_raises():
    with pytest.raises(KeyError):
        expand_tool_call("definitely_not_a_tool", {})
    with pytest.raises(KeyError):
        expand_tool_call("static_eyes", {})  # data handler, not codegen


def test_expand_sequence_pairs_l1_l2():
    rows = expand_sequence([
        {"tool": "create_bin", "args": {"prim_path": "/World/B", "position": [0, 0, 0.75],
                                        "size": [0.3, 0.3, 0.15]}},
        {"tool": "static_eyes", "args": {}},  # non-codegen -> survives w/ error
    ])
    assert rows[0]["code"] and "/World/B" in rows[0]["code"]
    assert rows[1]["code"] is None and "error" in rows[1]
