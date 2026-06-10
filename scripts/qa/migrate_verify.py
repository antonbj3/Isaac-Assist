#!/usr/bin/env python3
"""migrate_verify — semantic-diff harness for toolify migrations [P2-07..09].

Builds a template's ORIGINAL code and a CANDIDATE (migrated) code in the same
fresh Kit session, exports both authored stages, and compares them with the
semantic USD diff (P2-01). Zero semantic delta = the migration is safe to
commit; any delta is printed prim-by-prim so the tool (or the candidate) gets
fixed BEFORE the corpus moves. Authored-scene comparison only — no settle, no
physics, so warm-Kit degradation does not apply between the two builds.

Usage:
    python3 scripts/qa/migrate_verify.py CP-01 path/to/CP-01.candidate.json
    python3 scripts/qa/migrate_verify.py CP-01 cand.json --no-restart
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# --role-path: build via code_template+roles (for CT migrations); default
# strips the role fields so `code` is what gets verified.
_USE_ROLE_PATH = "--role-path" in __import__("sys").argv
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/qa"))

from nofm_validate import restart_kit  # noqa: E402
from service.isaac_assist_service.qa.semantic_usd_diff import (  # noqa: E402
    diff_signatures, stage_signature)


def _force_code_path(tpl: dict) -> dict:
    """The executor PREFERS code_template+roles when present — which made
    every wave verdict for role-path templates VOID (proven 2026-06-10
    evening: a candidate with table_height=9.99 sabotaged into `code`
    still ZERO_DELTA'd, because both builds ran the untouched
    code_template). Migration verification MUST exercise the field being
    migrated: strip the role-path fields so the build runs `code`."""
    t = dict(tpl)
    t.pop("code_template", None)
    t.pop("roles", None)
    t.pop("role_defaults", None)
    return t


async def _build_and_export(tpl: dict, out_path: str) -> None:
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical)
    from service.isaac_assist_service.chat.tools import kit_tools

    # Deterministic start: /World's TYPE flip-flops with Kit's new_stage
    # internals (wave-1c: typed in A untyped in B on one template, the
    # REVERSE on another) — session noise, not template semantics. Typing
    # it here makes both builds start from the identical stage state.
    await kit_tools.exec_sync(
        "import omni.usd\nfrom pxr import UsdGeom\n"
        "omni.usd.get_context().new_stage()\n"
        "UsdGeom.Xform.Define(omni.usd.get_context().get_stage(), '/World')\n"
        "print('STAGE_CLEAR')",
        timeout=30)
    b = await asyncio.wait_for(execute_template_canonical(
        tpl if _USE_ROLE_PATH else _force_code_path(tpl)), timeout=600)
    if not b.get("instantiated"):
        raise RuntimeError(f"BUILD_FAIL: {str(b.get('errors'))[:400]}")
    # Deterministic export: STOP (not pause) the timeline first — stop
    # resets prims to their AUTHORED state, so multi-robot/belt templates
    # that start simulating during build (CP-52 family: 62 runtime-state
    # attrs varied build-to-build) export the scene as authored, not a
    # random mid-motion frame.
    r = await kit_tools.exec_sync(
        "import omni.usd, omni.timeline, omni.kit.app\n"
        "omni.timeline.get_timeline_interface().stop()\n"
        "for _ in range(5):\n"
        "    omni.kit.app.get_app().update()\n"
        f"omni.usd.get_context().get_stage().Export({out_path!r})\n"
        f"print('EXPORTED {out_path}')",
        timeout=60)
    if "EXPORTED" not in str(r):
        raise RuntimeError(f"EXPORT_FAIL: {str(r)[:300]}")


async def main() -> int:
    argv = sys.argv[1:]
    # strip flag-with-value pairs BEFORE positional parse
    positional, skip = [], False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a == "--orig":
            skip = True
            continue
        if not a.startswith("--"):
            positional.append(a)
    args = positional
    no_restart = "--no-restart" in argv
    if len(args) != 2:
        print(__doc__)
        return 2
    name, cand_path = args
    orig_override = None
    for i, a in enumerate(sys.argv):
        if a == "--orig" and i + 1 < len(sys.argv):
            orig_override = sys.argv[i + 1]
    if orig_override:
        orig = json.load(open(orig_override))
    else:
        orig = json.load(open(REPO / f"workspace/templates/{name}.json"))
    cand = json.load(open(cand_path))

    if not no_restart:
        print(f"kit boot {restart_kit()}s", flush=True)
    old_usd = f"/tmp/mig_{name}_old.usda"
    new_usd = f"/tmp/mig_{name}_new.usda"
    print("building ORIGINAL...", flush=True)
    await _build_and_export(orig, old_usd)
    print("building CANDIDATE...", flush=True)
    await _build_and_export(cand, new_usd)

    d = diff_signatures(stage_signature(old_usd), stage_signature(new_usd))
    print(json.dumps(d, indent=1, default=str)[:4000])
    same = bool(d["equivalent"])
    print(f"MIGRATION_VERDICT={'ZERO_DELTA' if same else 'DELTA'} "
          f"(missing={len(d['missing_in_b'])} extra={len(d['extra_in_b'])} "
          f"attr={len(d['attr_diffs'])})")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
