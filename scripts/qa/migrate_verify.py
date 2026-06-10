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
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/qa"))

from nofm_validate import restart_kit  # noqa: E402
from service.isaac_assist_service.qa.semantic_usd_diff import (  # noqa: E402
    diff_signatures, stage_signature)


async def _build_and_export(tpl: dict, out_path: str) -> None:
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical)
    from service.isaac_assist_service.chat.tools import kit_tools

    await kit_tools.exec_sync(
        "import omni.usd\nomni.usd.get_context().new_stage()\nprint('STAGE_CLEAR')",
        timeout=30)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        raise RuntimeError(f"BUILD_FAIL: {str(b.get('errors'))[:400]}")
    r = await kit_tools.exec_sync(
        "import omni.usd\n"
        f"omni.usd.get_context().get_stage().Export({out_path!r})\n"
        f"print('EXPORTED {out_path}')",
        timeout=60)
    if "EXPORTED" not in str(r):
        raise RuntimeError(f"EXPORT_FAIL: {str(r)[:300]}")


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_restart = "--no-restart" in sys.argv
    if len(args) != 2:
        print(__doc__)
        return 2
    name, cand_path = args
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
