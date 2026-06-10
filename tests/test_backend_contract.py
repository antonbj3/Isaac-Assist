"""L0 tests for the machine-readable backend contract [P2-13].

The load-bearing one is the DRIFT GUARD: every selector the live dispatcher
handles must have a contract row, and vice versa — read from the pick_place
SOURCE (regex, no import/edit: the file is UR10-track territory)."""
import re
from pathlib import Path

import pytest

from service.isaac_assist_service.chat.tools.handlers.backend_contract import (
    AUTO_PRIORITY, BACKEND_CONTRACT, contract_for, supports_family)

pytestmark = pytest.mark.l0

_PP = Path("service/isaac_assist_service/chat/tools/handlers/pick_place.py")


def _dispatch_selectors():
    src = _PP.read_text(encoding="utf-8")
    # the dispatcher body: `if mode == "X":` / `mode in ("X", ...)` branches
    # (?<![\w_]) so `_mode in (...)`/`_hn in (...)` inside EMITTED code
    # strings (callback-manager keys like "curobo_pp") never match
    sels = set(re.findall(r'(?<![\w_])mode == "(\w+)"', src))
    sels |= {m for grp in re.findall(r'(?<![\w_])mode in \(([^)]*)\)', src)
             for m in re.findall(r'"(\w+)"', grp)}
    sels.discard("auto")          # resolver, not a backend
    # the default fall-through branch:
    sels.add("cube_tracking")
    return sels


def test_contract_covers_exactly_the_dispatch():
    dispatch = _dispatch_selectors()
    contract = set(BACKEND_CONTRACT)
    assert dispatch - contract == set(), f"dispatch utan kontrakt: {dispatch - contract}"
    assert contract - dispatch == set(), f"kontrakt utan dispatch: {contract - dispatch}"


def test_every_row_is_complete():
    required = {"families", "grip", "world_model", "multi_item", "routing",
                "sim2real", "ctrl_records", "never_auto"}
    for sel, row in BACKEND_CONTRACT.items():
        assert required <= set(row), f"{sel} saknar {required - set(row)}"
        assert row["sim2real"] in ("honest", "honest-cheat-grip", "omniscient",
                                   "external", "experimental"), sel


def test_auto_priority_matches_resolver_source():
    src = _PP.read_text(encoding="utf-8")
    body = src.split("def _resolve_auto_target_source", 1)[1].split("\ndef ", 1)[0]
    returns = re.findall(r'return "(\w+)"', body)
    # resolver returns in priority order; dedupe preserving order
    seen, order = set(), []
    for r in returns:
        if r not in seen:
            seen.add(r)
            order.append(r)
    assert order == AUTO_PRIORITY, f"resolver: {order} != kontrakt: {AUTO_PRIORITY}"
    # everything the resolver can return must NOT be marked never_auto
    for sel in order:
        assert BACKEND_CONTRACT[sel]["never_auto"] is False, sel


def test_family_support_queries():
    assert supports_family("curobo", "ur10")
    assert not supports_family("native", "ur10")       # reroutes, not serves
    assert supports_family("ros2_cmd", "anything")     # wildcard
    assert not supports_family("unknown_backend", "franka")
    assert contract_for("cortex") is None              # retired stays absent
