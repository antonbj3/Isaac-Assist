#!/usr/bin/env python3
"""migrate_verify — semantic-diff harness for toolify migrations [P2-07..09].

Builds a template's ORIGINAL code and a CANDIDATE (migrated) code in the same
fresh Kit session, exports both authored stages, and compares them with the
semantic USD diff (P2-01). Zero semantic delta = the migration is safe to
commit; any delta is printed prim-by-prim so the tool (or the candidate) gets
fixed BEFORE the corpus moves. NOTE (QA-audit fynd 11): controllers/belts DO
run during builds (ctrl:* records prove it) — determinism comes from
timeline-stop+ticks, the belt freeze and the writeback exclusions, not from
an absence of physics. Auto-repair (UR10 spawn-triplet rewrite) runs
symmetrically on both sides and therefore MASKS candidate changes inside the
rewritten triplet — known limit, see UR10-COORD.

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


_BELT_RE = __import__("re").compile(
    r'create_conveyor\(\s*prim_path="([^"]+)"[^)]*?surface_velocity=(\[[^\]]*\])',
    __import__("re").S)


def _declared_belt_velocities(tpl: dict) -> dict:
    """{belt_path: [vx,vy,vz]} as DECLARED by create_conveyor in the
    template code. Belt pause-logic toggles the authored surfaceVelocity at
    runtime during the build (CP-51/68/conveyor-pick: rolling in one build,
    paused in the other — the last 1-attr deltas of the cluster). Re-author
    the DECLARED value before export so both sides export authored intent,
    not whichever pause-state the build happened to end in."""
    import json as _json
    import re as _re2
    # QA-audit fynd 5b: scan ONLY the field being built (the dict order
    # code->ct let an untouched ct declaration overwrite a changed code one).
    # The caller passes the ALREADY-STRIPPED build_tpl, so whichever field
    # survives is the built one.
    out = {}
    for field in ("code", "code_template"):
        src = tpl.get(field) or ""
        for m in _BELT_RE.finditer(src):
            try:
                out[m.group(1)] = _json.loads(m.group(2))
            except ValueError:
                pass
        # fynd 5a: a LATER set_attribute override on the same attr is part
        # of the declaration — freezing to create_conveyor's value would
        # erase a real candidate change.
        for m in _re2.finditer(
                r'set_attribute\(\s*prim_path="([^"]+)"\s*,\s*attr_name='
                r'"physxSurfaceVelocity:surfaceVelocity"\s*,\s*value=(\[[^\]]*\])',
                src, _re2.S):
            try:
                out[m.group(1)] = _json.loads(m.group(2))
            except ValueError:
                pass
    return out


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
    build_tpl = tpl if _USE_ROLE_PATH else _force_code_path(tpl)
    b = await asyncio.wait_for(execute_template_canonical(build_tpl), timeout=600)
    if not b.get("instantiated"):
        raise RuntimeError(f"BUILD_FAIL: {str(b.get('errors'))[:400]}")
    # BUILD QUALITY GATE (QA-audit fynd 1): instantiated=True is hardcoded in
    # the executor — symmetric per-call failures on both sides would
    # ZERO_DELTA two equally-truncated scenes. A verdict requires CLEAN
    # builds: every captured call executed ok and no capture-dropped
    # statements.
    if b.get("errors") or b.get("n_ok") != b.get("n_calls"):
        raise RuntimeError(
            f"BUILD_DIRTY: n_ok={b.get('n_ok')}/{b.get('n_calls')} "
            f"errors={str(b.get('errors'))[:300]}")
    if b.get("capture_warnings"):
        raise RuntimeError(
            f"BUILD_DIRTY: capture dropped statements: "
            f"{str(b.get('capture_warnings'))[:300]}")
    # Deterministic export: STOP (not pause) the timeline first — stop
    # resets prims to their AUTHORED state, so multi-robot/belt templates
    # that start simulating during build (CP-52 family: 62 runtime-state
    # attrs varied build-to-build) export the scene as authored, not a
    # random mid-motion frame.
    belts = _declared_belt_velocities(build_tpl)
    belt_block = ""
    if belts:
        belt_block = (
            "from pxr import Gf, PhysxSchema\n"
            "for _bp, _bv in " + repr(belts) + ".items():\n"
            "    _prim = omni.usd.get_context().get_stage().GetPrimAtPath(_bp)\n"
            "    if _prim and _prim.IsValid():\n"
            "        _api = PhysxSchema.PhysxSurfaceVelocityAPI(_prim)\n"
            "        _attr = _prim.GetAttribute('physxSurfaceVelocity:surfaceVelocity')\n"
            "        if _attr and _attr.HasAuthoredValue():\n"
            "            _attr.Set(Gf.Vec3f(*_bv))\n")
    r = await kit_tools.exec_sync(
        "import omni.usd, omni.timeline, omni.kit.app\n"
        "omni.timeline.get_timeline_interface().stop()\n"
        "for _ in range(5):\n"
        "    omni.kit.app.get_app().update()\n"
        + belt_block +
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
