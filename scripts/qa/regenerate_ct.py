#!/usr/bin/env python3
"""regenerate_ct — rebuild code_template from code, roundtrip-proven [P2-11b].

Recipe: new_ct = code with role-default literals reverse-substituted to
{{role.field}} placeholders. ACCEPTED only when
``substitute_role_placeholders(new_ct, role_defaults) == code`` byte-exact —
then the role-path build IS the code-path build by construction (no Kit
verification needed).

Collision guard: literals shorter than --min-lit (default 8) stay inline —
short values ('A', small ints) hit unrelated code. KNOWN LIMIT: a role value
that appears inside an unrelated string literal (e.g. "eef_pos" inside an
embedded reward function) still collides and FAILS the roundtrip -> the
template lands in the manual list, never silently broken.

Usage:
    python3 scripts/qa/regenerate_ct.py CP-NEW-x [CP-NEW-y ...] [--apply]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from service.isaac_assist_service.chat.canonical_instantiator import (  # noqa: E402
    _format_for_code, substitute_role_placeholders)

MIN_LIT = 8


def regenerate(template: dict, min_lit: int = MIN_LIT):
    """(new_ct, roundtrip_ok) — never apply a False one."""
    code, rd = template["code"], template.get("role_defaults") or {}
    pairs = []
    for role, v in rd.items():
        items = enumerate(v) if isinstance(v, list) else [(None, v)]
        for i, item in items:
            if not isinstance(item, dict):
                continue
            for f, val in item.items():
                lit = _format_for_code(val)
                if len(lit) < min_lit:
                    continue
                ph = (f"{{{{{role}[{i}].{f}}}}}" if i is not None
                      else f"{{{{{role}.{f}}}}}")
                pairs.append((lit, ph))
    pairs.sort(key=lambda x: -len(x[0]))
    new_ct = code
    for lit, ph in pairs:
        new_ct = new_ct.replace(lit, ph)
    ok = substitute_role_placeholders(new_ct, rd) == code
    return new_ct, ok


def apply_ct(path: Path, new_ct: str) -> bool:
    raw = path.read_text(encoding="utf-8")
    t = json.loads(raw)
    for am in (False, True):
        old = json.dumps(t["code_template"], ensure_ascii=am)
        if old in raw:
            raw = raw.replace(old, json.dumps(new_ct, ensure_ascii=am), 1)
            json.loads(raw)
            path.write_text(raw, encoding="utf-8")
            return True
    return False


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_apply = "--apply" in sys.argv
    if not names:
        print(__doc__)
        return 2
    rc = 0
    for n in names:
        p = REPO / f"workspace/templates/{n}.json"
        t = json.loads(p.read_text(encoding="utf-8"))
        if not (t.get("roles") and t.get("role_defaults") and t.get("code")):
            print(f"{n}: SKIP (no role fields)")
            continue
        new_ct, ok = regenerate(t)
        if not ok:
            print(f"{n}: ROUNDTRIP_FAIL — manual rewrite needed")
            rc = 1
            continue
        if do_apply:
            print(f"{n}: {'APPLIED' if apply_ct(p, new_ct) else 'APPLY_FAIL'}")
        else:
            print(f"{n}: ROUNDTRIP_OK (dry-run; --apply to write)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
