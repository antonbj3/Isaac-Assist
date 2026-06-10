#!/usr/bin/env python3
"""Generate create_scene_baseline candidates for the baseline cluster and
batch-verify them with migrate_verify [P2-07 wave driver].

Strict-match only: templates whose opening is EXACTLY the canonical
DomeLight(+Ground)+Cell+Table+physics block (89 in corpus today). Variants
stay untouched — they migrate in later waves with their own patterns.

Usage:
    python3 scripts/qa/migrate_baseline_candidates.py CP-03 CP-08 ...
    python3 scripts/qa/migrate_baseline_candidates.py --scan   # list matches
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # service.* imports in script mode (v2 substitution)

PAT = re.compile(
    r'(?:#[^\n]*\n)*'
    r'create_prim\(prim_path="/World/DomeLight", prim_type="DomeLight"\)\n'
    r'set_attribute\(prim_path="/World/DomeLight", attr_name="inputs:intensity", value=(?P<inten>[\d.]+)\)\n'
    r'(?:\n?#[^\n]*\n)*'
    r'(?P<ground>create_prim\(prim_path="/World/Ground", prim_type="Cube", position=\[0, 0, -0\.5\], scale=\[(?P<gs>[\d.]+), [\d.]+, 1\]\)\n'
    r'apply_api_schema\(prim_path="/World/Ground", schema_name="PhysicsCollisionAPI"\)\n)?'
    r'(?:\n?#[^\n]*\n)*'
    r'create_prim\(prim_path="/World/Cell", prim_type="Xform"\)\n'
    r'(?:\n?#[^\n]*\n)*'
    r'create_prim\(prim_path="/World/Table", prim_type="Cube", position=\[0, 0, 0\.375\], scale=\[(?P<tx>[\d.]+), (?P<ty>[\d.]+), 0\.375\]\)\n'
    r'apply_api_schema\(prim_path="/World/Table", schema_name="PhysicsCollisionAPI"\)\n'
    r'(?:\n?#[^\n]*\n)*'
    r'\n?set_physics_scene_config\(config=\{"enable_gpu_dynamics": False, "broadphase_type": "MBP"\}\)')


def candidate_code(code: str):
    m = PAT.search(code)
    if not m:
        return None
    parts = ["# Toolified opening [P2-07]: light"
             + ("+ground" if m.group("ground") else "")
             + "+cell+table+physics in ONE call"]
    args = []
    if float(m.group("inten")) != 1000.0:
        args.append(f"intensity={m.group('inten')}")
    if m.group("ground"):
        if float(m.group("gs")) != 20.0:
            args.append(f"ground_scale={m.group('gs')}")
    else:
        args.append("include_ground=False")
    tx, ty = float(m.group("tx")), float(m.group("ty"))
    if [tx * 2, ty * 2] != [1.5, 0.5]:
        args.append(f"table_size=[{tx * 2}, {ty * 2}]")
    parts.append(f"create_scene_baseline({', '.join(args)})")
    return code[:m.start()] + "\n".join(parts) + code[m.end():]


def main() -> int:
    args = sys.argv[1:]
    names = [a for a in args if not a.startswith("--")]
    if "--scan" in args:
        for f in sorted((REPO / "workspace/templates").glob("CP*.json")):
            if ".bak" in f.name or ".pre_" in f.name:
                continue
            try:
                code = json.loads(f.read_text(encoding="utf-8")).get("code") or ""
            except Exception:
                continue
            if PAT.search(code):
                print(f.stem)
        return 0
    if not names:
        print(__doc__)
        return 2
    ct_mode = "--ct" in args          # migrate code_template, verify via role path
    no_restart = "--no-restart" in args
    field = "code_template" if ct_mode else "code"
    results = {}
    for n in names:
        tpl = json.load(open(REPO / f"workspace/templates/{n}.json"))
        raw_field = tpl.get(field) or ""
        new_code = candidate_code(raw_field)
        if new_code is None:
            # v2: AST matcher for the variant openings; ct needs the real
            # role substitution for PARSING (raw keeps its placeholders)
            parse_text = raw_field
            if ct_mode:
                try:
                    from service.isaac_assist_service.chat.canonical_instantiator import (
                        substitute_role_placeholders)
                    parse_text = substitute_role_placeholders(
                        raw_field, tpl.get("role_defaults"))
                except Exception:
                    pass
            new_code = candidate_code_v2(raw_field, parse_text)
        if new_code is None:
            results[n] = "NO_MATCH"
            print(f"{n}: NO_MATCH (variant — later wave)", flush=True)
            continue
        tpl[field] = new_code
        cand = f"/tmp/cand_{'ct_' if ct_mode else ''}{n}.json"
        json.dump(tpl, open(cand, "w"), ensure_ascii=False)
        extra = (["--role-path"] if ct_mode else []) + (["--no-restart"] if no_restart else [])
        p = subprocess.run([sys.executable, str(REPO / "scripts/qa/migrate_verify.py"),
                            n, cand] + extra, capture_output=True, text=True, timeout=1200)
        out = p.stdout + p.stderr
        if "MIGRATION_VERDICT=ZERO_DELTA" in out:
            verdict = "ZERO_DELTA"
        elif "MIGRATION_VERDICT=DELTA" in out:
            verdict = "DELTA"
        else:
            verdict = "ERROR"  # build/export crash is NOT a diff verdict
        if verdict != "ZERO_DELTA":
            tail = [l for l in out.splitlines() if l][-12:]
            print(f"{n}: {verdict}\n  " + "\n  ".join(tail), flush=True)
        else:
            print(f"{n}: {verdict}", flush=True)
        results[n] = verdict
    print("SUMMARY " + json.dumps(results))
    return 0




# ---------------------------------------------------------------------------
# v2: AST-based opening matcher [ct-variant wave] — order-tolerant, handles
# inline intensity, multiline calls, missing Cell/Ground/Table. Works on a
# placeholder-SUBSTITUTED source; spans map back to raw lines (substitution
# preserves line structure).

import ast as _ast


def _lit(node):
    """Literal value of an ast node (Constant / List of Constants) or None."""
    if isinstance(node, _ast.Constant):
        return node.value
    if isinstance(node, (_ast.List, _ast.Tuple)):
        out = []
        for el in node.elts:
            v = _lit(el)
            if v is None and not (isinstance(el, _ast.Constant) and el.value is None):
                return None
            out.append(v)
        return out
    if isinstance(node, _ast.Dict):
        d = {}
        for k, v in zip(node.keys, node.values):
            kk, vv = _lit(k), _lit(v)
            if kk is None:
                return None
            d[kk] = vv
        return d
    if isinstance(node, _ast.UnaryOp) and isinstance(node.op, _ast.USub):
        v = _lit(node.operand)
        return -v if isinstance(v, (int, float)) else None
    return None


def _classify_stmt(stmt):
    """(kind, payload) for opening-block statements; (None, None) otherwise."""
    if not (isinstance(stmt, _ast.Expr) and isinstance(stmt.value, _ast.Call)):
        return None, None
    call = stmt.value
    if not isinstance(call.func, _ast.Name):
        return None, None
    name = call.func.id
    kw = {k.arg: _lit(k.value) for k in call.keywords if k.arg}
    if name == "create_prim":
        path = kw.get("prim_path")
        if path == "/World/DomeLight":
            return "light", {"intensity": kw.get("intensity")}
        if path == "/World/Ground" and kw.get("position") == [0, 0, -0.5]:
            sc = kw.get("scale")
            if isinstance(sc, list) and len(sc) == 3 and sc[0] == sc[1] and sc[2] == 1:
                return "ground", {"scale": float(sc[0])}
        if path == "/World/Cell" and kw.get("prim_type") == "Xform":
            return "cell", {}
        if path == "/World/Table":
            pos, sc = kw.get("position"), kw.get("scale")
            if (isinstance(pos, list) and isinstance(sc, list) and len(sc) == 3
                    and pos[:2] == [0, 0] and abs(pos[2] - sc[2]) < 1e-9):
                return "table", {"size": [sc[0] * 2, sc[1] * 2], "height": sc[2] * 2}
    elif name == "set_attribute":
        if (kw.get("prim_path") == "/World/DomeLight"
                and kw.get("attr_name") == "inputs:intensity"):
            return "light_intensity", {"intensity": kw.get("value")}
    elif name == "apply_api_schema":
        if kw.get("schema_name") == "PhysicsCollisionAPI":
            if kw.get("prim_path") == "/World/Ground":
                return "ground_col", {}
            if kw.get("prim_path") == "/World/Table":
                return "table_col", {}
    elif name == "set_physics_scene_config":
        if kw.get("config") == {"enable_gpu_dynamics": False, "broadphase_type": "MBP"}:
            return "physics", {}
    return None, None


def candidate_code_v2(raw_text: str, parse_text: str = None):
    """Replace the opening block (any canonical-family variant) with a
    create_scene_baseline call. raw_text = the text to EDIT (may contain
    placeholders); parse_text = substituted text to PARSE (defaults raw)."""
    src = parse_text if parse_text is not None else raw_text
    try:
        mod = _ast.parse(src)
    except SyntaxError:
        return None
    found, first_ln, last_ln = {}, None, None
    for stmt in mod.body:
        kind, payload = _classify_stmt(stmt)
        if kind is None:
            break
        if kind in found:        # duplicate family -> not the opening block
            break
        found[kind] = payload
        first_ln = first_ln or stmt.lineno
        last_ln = stmt.end_lineno
    if "light" not in found or "physics" not in found:
        return None
    # paired families must be complete
    if ("ground" in found) != ("ground_col" in found):
        return None
    if ("table" in found) != ("table_col" in found):
        return None
    if "table" in found and abs(found["table"]["height"] - 0.75) > 1e-9:
        return None              # non-canonical table height — out of scope
    args = []
    inten = found.get("light_intensity", {}).get("intensity",
            found["light"].get("intensity"))
    if inten is not None and float(inten) != 1000.0:
        args.append(f"intensity={inten}")
    if "ground" not in found:
        args.append("include_ground=False")
    elif found["ground"]["scale"] != 20.0:
        args.append(f"ground_scale={found['ground']['scale']}")
    if "table" not in found:
        args.append("include_table=False")
        if "cell" in found:
            args.append("include_cell=True")
    else:
        ts = found["table"]["size"]
        if ts != [1.5, 0.5]:
            args.append(f"table_size=[{ts[0]}, {ts[1]}]")
        if "cell" not in found:
            args.append("include_cell=False")
    lines = raw_text.splitlines(keepends=True)
    head = "".join(lines[: first_ln - 1])
    tail = "".join(lines[last_ln:])
    repl = ("# Toolified opening [P2-07 v2]\n"
            f"create_scene_baseline({', '.join(args)})\n")
    return head + repl + tail


if __name__ == "__main__":
    raise SystemExit(main())
