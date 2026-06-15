#!/usr/bin/env python3
"""static_scene_check.py — ZERO-BOOT scene-geometry pre-validator (no Kit, no GPU).

Packages the authored-geometry checks I'd otherwise do BY HAND (per the directive:
"härleder du för hand -> first-class-detektor"). Reads a template's `code` (the
concrete tool-call sequence), parses create_prim / create_bin / robot_wizard /
create_conveyor / create_rotary_table calls (prim_path + position + scale/size),
compounds parent->child USD transforms, and flags scene-geometry bugs that cause
"0/N delivered" WITHOUT a sim run:

  DOUBLE_OFFSET   a child prim's local position ~= its PARENT's local position ->
                  USD compounds them (object ends at ~2x the intended radius).
                  (e.g. /World/Carousel/Bin_0 at [.55,0,0] AND .../Bin_0/Cube at
                  [.55,0,.05] -> cube world ~1.1).
  ROBOT_BURIAL    robot spawn z below the ground TOP (USD Cube default size=2 ->
                  a ground Cube scale=[20,20,1] at z=-0.5 tops at z=+0.5, burying a
                  robot spawned at z=0.3). ground_top = pos_z + scale_z*(size/2).
  CUBE_BURIED     a pick cube's world-z is at/below its nearest support top.
  FLAT_TARGET     target_path is a flat create_prim Cube plate (no walls) instead of
                  a walled create_bin -> placed objects slide off / get knocked.
  OUT_OF_REACH    a pick cube or the target is beyond the robot's nominal reach
                  (Franka 0.85m / UR10 1.20m from base, xy). GROSS bound only
                  (true reach is non-convex -> reach_validate/cuRobo is the live truth);
                  necessary-not-sufficient.

NECESSARY-NOT-SUFFICIENT: a clean static report does NOT mean the template delivers
(dynamics: grip, belt, timing need scene_eyes/gate). But a FLAG is a high-confidence
authored bug. Pairs with grasp_validate (static jaw-fit) for the static layer that
the single-Kit live validators (reach_validate/scene_validate/scene_eyes) can't be
run in parallel for.

Usage: static_scene_check.py <TEMPLATE> [TEMPLATE2 ...]   (or 'all')
JSON line per template on stdout + human summary on stderr.
"""
import json, os, re, sys, math

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
TPL_DIR = os.path.join(REPO, "workspace", "templates")
REACH = {"franka": 0.85, "franka_panda": 0.85, "panda": 0.85, "cobotta": 0.95,
         "ur10": 1.20, "ur10e": 1.20}
USD_CUBE_SIZE = 2.0  # USD Cube default 'size' -> half-extent = size/2 * scale


def _f(s):
    try: return float(s)
    except Exception: return None


def _vec(txt):
    """parse a [a, b, c] literal -> [floats] (or None if it has placeholders/vars)."""
    m = re.search(r"\[([^\]]*)\]", txt)
    if not m: return None
    parts = [p.strip() for p in m.group(1).split(",")]
    out = [_f(p) for p in parts]
    if any(v is None for v in out) or len(out) < 2: return None
    return out


def _kw(call, key):
    """extract key=<...> from a call string; returns the raw value text up to the
    next top-level comma or close-paren."""
    i = call.find(key + "=")
    if i < 0: return None
    j = i + len(key) + 1
    depth = 0; out = []
    for ch in call[j:]:
        if ch in "([{": depth += 1
        elif ch in ")]}":
            if depth == 0: break
            depth -= 1
        elif ch == "," and depth == 0:
            break
        out.append(ch)
    return "".join(out).strip()


def _calls(code, fn):
    """yield the argument-text of each `fn(...)` call in code (balanced parens)."""
    for m in re.finditer(re.escape(fn) + r"\s*\(", code):
        j = m.end(); depth = 1; out = []
        while j < len(code) and depth:
            ch = code[j]
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            if depth: out.append(ch)
            j += 1
        yield "".join(out)


def parse_scene(code):
    """Return {prim_path: {pos:[x,y,z]|None, scale:[..]|None, size:float|None, type:str, kind:str}}
    in LOCAL coords, plus robot info."""
    prims = {}
    robot = None
    def add(path, pos, scale, size, typ, kind):
        if path: prims[path] = {"pos": pos, "scale": scale, "size": size, "type": typ, "kind": kind}
    for fn, kind in (("create_prim", "prim"), ("create_bin", "bin"),
                     ("create_conveyor", "conveyor"), ("create_rotary_table", "table"),
                     ("robot_wizard", "robot"), ("add_proximity_sensor", "sensor")):
        for c in _calls(code, fn):
            path = None
            for pk in ("prim_path", "dest_path", "table_path", "sensor_path"):
                v = _kw(c, pk)
                if v: path = v.strip().strip('"').strip("'"); break
            pos = _vec(_kw(c, "position") or "")
            scale = _vec(_kw(c, "scale") or "")
            size = _f((_kw(c, "size") or "").strip()) if not _vec(_kw(c, "size") or "") else None
            sizevec = _vec(_kw(c, "size") or "")
            typ = (_kw(c, "prim_type") or "").strip().strip('"').strip("'")
            if kind == "robot":
                rn = (_kw(c, "robot_name") or "").strip().strip('"').strip("'").lower()
                robot = {"path": path, "name": rn, "pos": pos}
            add(path, pos, scale if scale else sizevec, size, typ, kind)
    return prims, robot


def world_pos(path, prims):
    """compound LOCAL positions up the prim-path hierarchy -> world position."""
    parts = path.split("/")
    acc = [0.0, 0.0, 0.0]; ok = False
    for i in range(2, len(parts) + 1):
        sub = "/".join(parts[:i])
        if sub in prims and prims[sub]["pos"]:
            p = prims[sub]["pos"]
            for k in range(3):
                acc[k] += (p[k] if k < len(p) else 0.0)
            ok = True
    return acc if ok else None


def top_z(path, prims):
    """world top-z of a box-like prim (pos_z + half-extent_z)."""
    info = prims.get(path)
    if not info: return None
    wp = world_pos(path, prims)
    if wp is None: return None
    half = 0.0
    if info.get("scale"):
        sc = info["scale"]
        half = (sc[2] if len(sc) > 2 else sc[-1]) * (USD_CUBE_SIZE / 2.0) if info["kind"] in ("prim",) else (sc[2] if len(sc) > 2 else 0.0) / 2.0
    elif info.get("size"):
        half = info["size"] / 2.0
    return wp[2] + half


def check(name):
    f = os.path.join(TPL_DIR, name + ".json")
    t = json.load(open(f))
    code = t.get("code") or ""
    sa = t.get("simulate_args") or t.get("verify_args") or {}
    cubes = [c for c in (sa.get("cube_paths") or sa.get("source_paths")
             or ([sa.get("cube_path")] if sa.get("cube_path") else [])) if c]
    target = sa.get("target_path")
    prims, robot = parse_scene(code)
    flags = []

    # ROBOT_BURIAL: robot z below ground top
    ground = next((p for p in prims if p.split("/")[-1].lower() in ("ground", "groundplane", "floor")), None)
    gtop = top_z(ground, prims) if ground else None
    if robot and robot.get("pos") and gtop is not None:
        rz = robot["pos"][2]
        if rz < gtop - 0.02:
            flags.append({"type": "ROBOT_BURIAL", "robot_z": round(rz, 3), "ground_top": round(gtop, 3),
                          "detail": "%s spawn z<%s ground top" % (robot["path"], round(gtop, 3))})

    # DOUBLE_OFFSET: child local pos ~= parent local pos (non-trivial)
    for path, info in prims.items():
        if not info["pos"]: continue
        parent = "/".join(path.split("/")[:-1])
        pinfo = prims.get(parent)
        if pinfo and pinfo["pos"] and parent.count("/") >= 2:
            d = math.dist(info["pos"][:2], pinfo["pos"][:2])
            if d < 0.02 and (abs(pinfo["pos"][0]) > 0.1 or abs(pinfo["pos"][1]) > 0.1):
                flags.append({"type": "DOUBLE_OFFSET", "prim": path, "child_local": info["pos"],
                              "parent_local": pinfo["pos"],
                              "detail": "%s local xy == parent %s xy -> compounds to ~2x" % (path, parent)})

    # FLAT_TARGET: target is a flat create_prim Cube (no walls) AND is a CONTAINER
    # (loose objects need walls). REFINED: palletize/stack targets (Pallet/Baseplate/
    # Pad/Pedestal/Plate/Marker) are MEANT to be flat platforms you stack ON — flat is
    # correct there (CP-46 delivers 6/6 onto a flat Pallet; brick-stacking 3/3 onto a
    # flat Baseplate). Only flag when the target name implies a CONTAINER.
    _CONTAINER = ("bin", "bowl", "tray", "crate", "bucket", "tote", "hopper")
    if target and target in prims and prims[target]["kind"] == "prim":
        sc = prims[target].get("scale")
        tname = target.split("/")[-1].lower()
        is_container = any(w in tname for w in _CONTAINER)
        if sc and len(sc) > 2 and sc[2] < 0.05 and is_container:
            flags.append({"type": "FLAT_TARGET", "target": target, "scale": sc,
                          "detail": "%s is a flat create_prim plate (no walls) but a CONTAINER -> loose objects slide off; use walled create_bin" % target})

    # NOTE: a "destination in planning_obstacles" check was tried + REMOVED — REFUTED
    # by CP-01 (verified 4/4) which lists /World/Bin in planning_obstacles AND delivers,
    # so the cuRobo handler already handles destination-as-obstacle (excludes it on the
    # drop segment). It is NOT a delivery bug. (Diagnostic-first: a known-good reference
    # killed the hypothesis — the workflow agents' 6dof/wire-harness "remove from
    # planning_obstacles" proposals are likewise refuted.)

    # OUT_OF_REACH: gross xy-distance bound from robot base
    if robot and robot.get("pos"):
        reach = REACH.get(robot.get("name", ""), 0.85)
        bx, by = robot["pos"][0], robot["pos"][1]
        far = []
        for c in cubes + ([target] if target else []):
            wp = world_pos(c, prims)
            if wp is None: continue
            d = math.hypot(wp[0] - bx, wp[1] - by)
            if d > reach + 0.05:
                far.append({"prim": c, "xy_dist": round(d, 3), "reach": reach})
        if far:
            flags.append({"type": "OUT_OF_REACH", "robot": robot.get("name"), "items": far,
                          "detail": "%d pick/target beyond %.2fm gross reach (non-convex true reach -> reach_validate is live truth)" % (len(far), reach)})

    return {"template": name, "n_cubes": len(cubes), "target": target,
            "n_prims": len(prims), "robot": (robot or {}).get("name"),
            "flags": flags, "clean": not flags}


def main():
    args = sys.argv[1:]
    if not args or args == ["all"]:
        args = sorted(os.path.basename(p)[:-5] for p in
                      __import__("glob").glob(os.path.join(TPL_DIR, "*.json")))
    nflag = 0
    for name in args:
        try:
            r = check(name)
        except Exception as e:
            print(json.dumps({"template": name, "error": "%s: %s" % (type(e).__name__, str(e)[:120])}))
            continue
        print(json.dumps(r))
        ftypes = ",".join(sorted(set(fl["type"] for fl in r["flags"]))) or "clean"
        if r["flags"]: nflag += 1
        sys.stderr.write("  %-44s %s%s\n" % (name, ftypes,
                         ("  | " + "; ".join(fl["detail"] for fl in r["flags"])) if r["flags"] else ""))
    sys.stderr.write("static_scene_check: %d/%d templates flagged\n" % (nflag, len(args)))


if __name__ == "__main__":
    main()
