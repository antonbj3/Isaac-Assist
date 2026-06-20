#!/usr/bin/env python3
"""template_lint.py (cont.319uu) — OFFLINE static lint for a hand-authored template, BEFORE a Kit run.

Hand-authoring a CP-NEW draft (or surgically editing a template) and then booting Kit to discover a typo
(a dangling /World/Bin reference, a drop_targets cube that isn't in source_paths, an obstacle that's never
created) WASTES a Kit wake. This catches those internal-consistency errors with zero Kit cost.

It is a STATIC consistency check, NOT a correctness/physics check — a template can lint CLEAN and still fail in
Kit (the only real verdict is scene_eyes RAW). Use it as a cheap pre-filter so the Kit run isn't spent on a typo.

CHECKS (per template):
  - every prim PATH referenced by the controller (destination_path, drop_target(s), planning_obstacles,
    source_paths, cube_paths, sensor_path, belt_path, robot_path) is either CREATED in the code or is a sub-path
    of a created prim (e.g. /World/UR10/ee_link under /World/UR10);
  - drop_targets keys (if a dict) are a SUBSET of source_paths/cube_paths (you can't stack a cube you don't pick);
  - no reference to a prim that a recent edit removed (heuristic: a /World/<Name> referenced but never created);
  - simulate_args.target_path / verify_args place_path resolve to a created prim.

Exit 0 + "TEMPLATE_LINT: CLEAN"; exit 1 + the issue list otherwise.
"""
import sys, os, json, re, argparse

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
_BASELINE = {"/World/Table", "/World/GroundPlane", "/World/PhysicsScene", "/World/defaultGroundPlane"}


def _created_prims(code):
    # path kwargs of CREATION calls: create_*(prim_path=), robot_wizard(dest_path=), add_proximity_sensor(sensor_path=)
    created = set(re.findall(r'(?:prim_path|dest_path|sensor_path)\s*=\s*"([^"]+)"', code))
    # loop-created cubes — the path is often indirected via a variable: `path = f"/World/Cube_{i+1}"` then
    # create_prim(prim_path=path, ...). Detect the f-string ANYWHERE (not just inline in prim_path=).
    if re.search(r'f"/World/Cube_\{i\+1\}"', code):
        n = re.search(r'range\((\d+)\)', code)
        created |= {f"/World/Cube_{i+1}" for i in range(int(n.group(1)) if n else 4)}
    created |= _BASELINE
    return created


def _is_created(path, created):
    return path in created or any(path.startswith(c + "/") for c in created)


def _refs(code):
    refs = {}
    for kw in ("destination_path", "sensor_path", "belt_path", "robot_path"):
        m = re.search(rf'{kw}\s*=\s*"([^"]+)"', code)
        if m:
            refs.setdefault(kw, []).append(m.group(1))
    refs["drop_target_keys"] = re.findall(r'"(/World/[A-Za-z0-9_]+)":\s*\[', code)
    refs["source_paths"] = ([f"/World/Cube_{i+1}" for i in range(int(re.search(r'range\((\d+)\)', code).group(1)))]
                            if re.search(r'source_paths=\[f"/World/Cube_\{i\+1\}"', code)
                            else re.findall(r'source_paths=\[([^\]]*)\]', code))
    ob = re.search(r'planning_obstacles=\[([^\]]+)\]', code)
    refs["obstacles"] = re.findall(r'"([^"]+)"', ob.group(1)) if ob else []
    return refs


def lint(tid):
    p = os.path.join(REPO, "workspace", "templates", f"{tid}.json")
    if not os.path.exists(p):
        print(f"TEMPLATE_LINT: NOT-FOUND {tid}")
        return 2
    t = json.load(open(p))
    used_ct = not t.get("code") and bool(t.get("code_template"))
    code = t.get("code") or t.get("code_template") or ""
    created = _created_prims(code)
    refs = _refs(code)
    issues = []
    # CONFIDENCE GUARD (false-success-vakt on this tool itself): the static created-set is INCOMPLETE whenever a
    # prim path is built in a form the regex can't resolve — a bare-variable path kwarg (prim_path=some_var), a
    # non-Cube f-string loop (Bin_{j}), or a code_template with {{placeholders}}. Corpus scan: 561 variable-indirected
    # paths, 38 non-Cube loops, 213 placeholder templates. On such a template a "never created" finding can be FALSE,
    # so the lint MUST NOT claim CLEAN (or hard-fail) — it reports LOW-CONFIDENCE instead. High-confidence CLEAN is
    # reserved for the literal + Cube_{i+1}-loop idiom (the hand-authored CP-NEW/CP-CHAIN drafts this tool is FOR).
    # `path` is the cube-loop variable (`path = f"/World/Cube_{i+1}"`), which _created_prims ALREADY resolves via
    # the f-string — so exclude it. Count only GENUINELY-unresolvable bare-variable path kwargs (arbitrary names).
    unresolved = len(re.findall(r'(?:prim_path|dest_path|sensor_path)\s*=\s*(?!["\']|f["\']|path\b)[A-Za-z_]\w*', code))
    unresolved += len(re.findall(r'f"/World/(?!Cube_\{i\+1\}")[^"]*\{', code))   # non-Cube f-string loops
    low_conf = unresolved > 0 or used_ct

    for kw in ("destination_path", "sensor_path", "belt_path", "robot_path"):
        for path in refs.get(kw, []):
            if not _is_created(path, created):
                issues.append(f"{kw}={path} referenced but never created")
    for path in refs["drop_target_keys"]:
        if not _is_created(path, created):
            issues.append(f"drop_targets key {path} never created")
    for path in refs["obstacles"]:
        if not _is_created(path, created):
            issues.append(f"planning_obstacle {path} never created")

    # drop_targets keys must be a subset of the picked cubes
    src = set(refs["source_paths"]) if isinstance(refs["source_paths"], list) and refs["source_paths"] and refs["source_paths"][0].startswith("/World") else {f"/World/Cube_{i+1}" for i in range(4)}
    extra = set(refs["drop_target_keys"]) - src
    if extra:
        issues.append(f"drop_targets stack cubes not in source_paths: {sorted(extra)}")

    # simulate/verify targets resolve
    tp = (t.get("simulate_args") or {}).get("target_path")
    if tp and not _is_created(tp, created):
        issues.append(f"simulate_args.target_path={tp} never created")
    for st in (t.get("verify_args") or {}).get("stages", []):
        pp = st.get("place_path")
        if pp and not _is_created(pp, created):
            issues.append(f"verify_args place_path={pp} never created")

    print(f"TEMPLATE_LINT {tid}: created={len(created)} prims; "
          f"refs dest={refs.get('destination_path')} drop_keys={len(refs['drop_target_keys'])} obstacles={len(refs['obstacles'])}; "
          f"confidence={'LOW' if low_conf else 'high'}")
    if low_conf:
        print(f"TEMPLATE_LINT: LOW-CONFIDENCE — {unresolved} path(s) built via variable/non-Cube-loop"
              + (" + code_template placeholders" if used_ct else "")
              + "; the static created-set is INCOMPLETE, so any 'never created' below MAY BE FALSE. Verify in Kit, do not trust this lint.")
        for i in issues:
            print("   ? (cannot verify statically)", i)
        return 0   # NOT a hard fail: this tool can't reliably judge this template — refuse to assert either way
    if issues:
        print("TEMPLATE_LINT: ISSUES")
        for i in issues:
            print("   -", i)
        return 1
    print("TEMPLATE_LINT: CLEAN (high-confidence: fully-resolvable literal/Cube-loop idiom — static only; scene_eyes RAW is the real verdict)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+", help="template ids to lint")
    a = ap.parse_args()
    rc = 0
    for tid in a.ids:
        rc |= lint(tid)
        print()
    sys.exit(1 if rc else 0)
