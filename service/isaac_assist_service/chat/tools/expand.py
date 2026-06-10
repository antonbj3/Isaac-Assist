"""expand — the ``expand=True`` codegen contract [P2-02b].

Every codegen tool already emits its raw Kit/USD python as a string (the
``CODE_GEN_HANDLERS`` registry: sync ``fn(args) -> str``). This module makes
that the FORMAL contract surface:

- ``expand_tool_call(name, args)`` — resolve ONE tool call to its emitted raw
  code. This is de-abstraction: a template that needs a one-off tweak inlines
  THIS output instead of hand-rolling from scratch, and it is the **L2
  representation** (raw code) paired to the **L1** (the tool call) for the
  training substrate (X-02: never discard a level; keep the L1<->L2 pairing).
- ``expand_sequence(calls)`` — pair a whole L1 tool-call sequence with its L2
  expansions in one pass (the per-run training capture shape).

Codegen-only: data handlers (runtime queries) have no meaningful expansion
and raise KeyError — expansion is for SCENE-AUTHORING tools by design.
"""
from __future__ import annotations

from typing import Any, Dict, List


def expand_tool_call(name: str, args: Dict[str, Any]) -> str:
    """Return the raw code the codegen tool *name* emits for *args*.

    Raises KeyError for unknown/non-codegen tools (expansion is only defined
    for scene-authoring codegen tools).
    """
    from .tool_executor import CODE_GEN_HANDLERS  # late import: heavy module
    fn = CODE_GEN_HANDLERS.get(name)
    if fn is None:
        raise KeyError(
            f"{name!r} is not a codegen tool — expansion is only defined for "
            "scene-authoring codegen tools (CODE_GEN_HANDLERS)")
    code = fn(args)
    if not isinstance(code, str):
        raise TypeError(f"{name!r} codegen returned {type(code).__name__}, expected str")
    return code


def expand_sequence(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pair an L1 tool-call sequence with its L2 expansions.

    Input: ``[{"tool": name, "args": {...}}, ...]``.
    Output rows: ``{"tool", "args", "code"}`` — ``code`` is None (with
    ``"error"`` set) for non-codegen entries, so mixed sequences survive and
    the capture records exactly what could and could not be expanded.
    """
    out: List[Dict[str, Any]] = []
    for call in calls:
        row: Dict[str, Any] = {"tool": call.get("tool"), "args": call.get("args", {})}
        try:
            row["code"] = expand_tool_call(row["tool"], row["args"])
        except (KeyError, TypeError) as exc:
            row["code"] = None
            row["error"] = str(exc)
        out.append(row)
    return out
