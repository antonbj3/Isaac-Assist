#!/usr/bin/env python3
"""audit_code_template_drift — code vs code_template content drift [P2-07 follow-up].

The executor PREFERS code_template+roles when present, so drift between the
two fields means THE SCENE THAT BUILDS is not the scene `code` declares.
Found live 2026-06-10: CP-NEW-kit-prep-vision-gate's code_template lacks ALL
set_semantic_label calls -> the built scene never gets labels -> the vision
gate cannot work, while `code` reads as a complete template.

Method: capture-replica of the canonical sandbox (same _SAFE_BUILTINS, same
tool registry, kwargs-capture stubs) on BOTH fields; compare tool-call
multisets. {{role.placeholders}} in code_template are substituted with
dummies pre-parse.

Classification per template:
  BASELINE_ONLY   drift is exactly the create_scene_baseline migration vs the
                  old hand-rolled opening (equivalent content, ct not yet
                  migrated) — expected, queued for ct-migration
  CONTENT_DRIFT   calls beyond the baseline class differ — the built scene
                  diverges from `code` (the kit-prep class; REAL defects)
  PARSE_FAIL      a field does not parse even after placeholder substitution
  IN_SYNC         multisets equal

Exit 0 always (report-only); pipe to CI later once CONTENT_DRIFT is drained.
"""
from __future__ import annotations

import ast
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from service.isaac_assist_service.chat.tools.tool_executor import (  # noqa: E402
    CODE_GEN_HANDLERS, DATA_HANDLERS)

_SAFE = {"enumerate": enumerate, "range": range, "len": len, "list": list,
         "dict": dict, "tuple": tuple, "set": set, "frozenset": frozenset,
         "str": str, "int": int, "float": float, "bool": bool, "bytes": bytes,
         "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
         "sorted": sorted, "reversed": reversed, "zip": zip, "map": map,
         "filter": filter, "True": True, "False": False, "None": None,
         "print": lambda *a, **k: None}
TOOLS = set(DATA_HANDLERS) | set(CODE_GEN_HANDLERS) | {"run_usd_script"}

# The opening-block tool families: a diff composed ONLY of these (plus the
# baseline call itself) is the expected code-side migration, not content drift.
_BASELINE_TOOLS = {"create_scene_baseline", "create_prim", "set_attribute",
                   "apply_api_schema", "set_physics_scene_config"}


def capture(code: str):
    captured: list = []

    class _R:
        def __getattr__(self, n):
            return _R()

        def __iter__(self):
            return iter(())

    def mk(name):
        def f(**kw):
            captured.append(name)
            return _R()
        return f

    sb = {"__builtins__": dict(_SAFE)}
    for n in TOOLS:
        sb[n] = mk(n)
    try:
        mod = ast.parse(code)
    except SyntaxError as e:
        return None, [f"SyntaxError: {e}"]
    errs = []
    for stmt in mod.body:
        try:
            exec(compile(ast.Module(body=[stmt], type_ignores=[]), "<t>", "exec"), sb)
        except Exception as e:  # statement-permissive, like the real sandbox
            errs.append(f"line {stmt.lineno}: {type(e).__name__}: {e}")
    return captured, errs


def classify(template: dict):
    ct = template.get("code_template")
    c = template.get("code")
    if not (ct and template.get("roles") and template.get("role_defaults") and c):
        return None  # no role path -> code is what builds; nothing to drift
    # Use the REAL role substitution (dummy '"X"' substitution broke f-string
    # and numeric contexts -> false PARSE_FAILs); fall back to dummy on error.
    try:
        from service.isaac_assist_service.chat.canonical_instantiator import (
            substitute_role_placeholders)
        ct_sub = substitute_role_placeholders(ct, template.get("role_defaults"))
    except Exception:
        ct_sub = re.sub(r"\{\{[^}]+\}\}", '"X"', ct)
    a, ea = capture(c)
    b, eb = capture(ct_sub)
    if a is None or b is None:
        return {"class": "PARSE_FAIL", "detail": (ea or eb)[:2]}
    ca, cb = Counter(a), Counter(b)
    if ca == cb:
        return {"class": "IN_SYNC"}
    diff_tools = set((ca - cb) | (cb - ca))
    cls = "BASELINE_ONLY" if diff_tools <= _BASELINE_TOOLS else "CONTENT_DRIFT"
    return {"class": cls,
            "missing_in_ct": dict(ca - cb), "extra_in_ct": dict(cb - ca),
            "sandbox_errs": {"code": len(ea), "ct": len(eb)}}


def main() -> int:
    out = {}
    for f in sorted(glob.glob(str(REPO / "workspace/templates/CP*.json"))):
        if ".bak" in f or ".pre_" in f:
            continue
        try:
            t = json.load(open(f))
        except Exception:
            continue
        r = classify(t)
        if r is not None:
            out[Path(f).stem] = r
    counts = Counter(v["class"] for v in out.values())
    print("DRIFT AUDIT:", dict(counts))
    for cls in ("CONTENT_DRIFT", "PARSE_FAIL"):
        for name, v in sorted(out.items()):
            if v["class"] == cls:
                detail = v.get("missing_in_ct") or v.get("detail")
                print(f"  {cls} {name}: {str(detail)[:140]}")
    if "--json" in sys.argv:
        Path("/tmp/ct_drift_audit.json").write_text(json.dumps(out, indent=1))
        print("JSON -> /tmp/ct_drift_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
