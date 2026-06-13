#!/usr/bin/env python
"""grasp_validate.py — ZERO-BOOT graspability pre-gate (geometric, no Kit, no real physics needed).

The position-only gate (and even a Kit boot) cannot tell you BEFORE a run whether a grasp can
physically hold. This reads the AUTHORED template geometry and scores each grasped object the way a
human reads a drawing — from the numbers, not pixels (the project philosophy):

  * jaw-fit       : grasped cross-section width < Franka max opening (0.08 m)? else UNGRASPABLE-by-jaw
  * pendulum risk : instability ratio = |CG-offset from the grip line| / grip-halfwidth. A pinch resists
                    a tip-over moment up to ~its contact halfwidth; CG far from the grip line (e.g. a
                    broom whose bristle mass hangs below the handle) pendulums out REGARDLESS of friction.
                    A SINGLE-part object grasped at its centroid has CG==grip -> ratio 0 (stable). Only a
                    COMPOSITE / offset-mass object can pendulum. Pure geometry (uniform-density centroid) —
                    only the QUANTITATIVE Nm force-closure verdict needs CAD2SimReady mass/mu, NOT faked here.

VALIDATED against MEASURED grip-slip (scene_eyes, commit c9094b7d): oxe-sweep broom -> PENDULUM (measured
83-149deg rotation-slip); a 5cm cube -> geom-OK (measured ~1deg). Discriminative + non-circular: same
metric, opposite verdict on the two controls.

Honest scope: catches the PENDULUM / jaw-fit class. Objects geometrically graspable but failing at the
CONTACT/torque-couple layer (faucet turn, drawer form-closure) read 'geom-OK' here — their verdict needs
the physics (CAD2SimReady) + the live grip-slip measurement (scene_eyes). Reported as such, not hidden.

Usage:  grasp_validate.py [TEMPLATE | all]        (default: the validation set)
"""
import json, os, re, sys, glob

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
TPL_DIR = os.path.join(REPO, "workspace", "templates")
MAX_JAW = 0.08          # Franka panda max finger opening (m)

# ---- token resolver: {{role.attr}} and {{role[i].attr}} against role_defaults ------------------
def _resolve(val, rd):
    if not isinstance(val, str):
        return val
    s = val.strip()
    m = re.fullmatch(r"\{\{\s*(\w+)\.(\w+)\s*\}\}", s)
    if m:
        return (rd.get(m.group(1)) or {}).get(m.group(2))
    m = re.fullmatch(r"\{\{\s*(\w+)\[(\d+)\]\.(\w+)\s*\}\}", s)
    if m:
        lst = rd.get(m.group(1))
        i = int(m.group(2))
        if isinstance(lst, list) and i < len(lst):
            return (lst[i] or {}).get(m.group(3))
    return val

def _num_list(s):
    try:
        return [float(x) for x in re.findall(r"-?\d+\.?\d*", s)]
    except Exception:
        return None

# ---- the grasped object: from the code_template controller call (source_paths=[...]) ----------
def grasped_paths(tpl, rd, src):
    # 1) the controller's source_paths list (authoritative — what the gripper actually grasps)
    m = re.search(r"source_paths\s*=\s*\[(.*?)\]", src, re.S)
    out = []
    if m:
        body = m.group(1)
        # loop-comprehension: f"/World/Cube_{i+1}" for i in range(N)  ->  generate the names
        lc = re.search(r'f"([^"]*?)\{[^}]*\}([^"]*)"\s+for\s+\w+\s+in\s+range\((\d+)\)', body)
        if lc:
            pre, post, n = lc.group(1), lc.group(2), int(lc.group(3))
            for i in range(n):
                out.append("%s%d%s" % (pre, i + 1, post))   # Cube_{i+1} -> 1..N
        else:
            for tok in re.findall(r'\{\{[^}]+\}\}|"[^"]+"', body):
                r = _resolve(tok.strip('"'), rd)
                if isinstance(r, str):
                    out.append(r)
    # 2) fall back to simulate_args
    if not out:
        sa = tpl.get("simulate_args") or {}
        for k in ("source_paths", "cube_paths", "cube_path"):
            v = sa.get(k)
            if isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
            elif isinstance(v, str):
                out.append(v)
    return list(dict.fromkeys(out))

# ---- parse create_prim -> resolved-path map + loose (loop/var/f-string) entries ----------------
def parse_prims(src, rd):
    prims = {}; loose = []
    # map loop variables to the path-stem they iterate, e.g.  for path in [f"/World/Cube_{i+1}" ...]  -> path->cube
    varstem = {}
    for vm in re.finditer(r'for\s+(\w+)\s+in\s+\[[^\]]*?f?"/World/(\w+?)_', src):
        varstem[vm.group(1)] = vm.group(2).lower()
    for b in re.findall(r"create_prim\((.*?)\)", src, re.S):
        mt = re.search(r'prim_type\s*=\s*"(\w+)"', b)
        mp = re.search(r"prim_path\s*=\s*([^,]+?)\s*,", b)
        if not (mt and mp):
            continue
        ms = re.search(r"scale\s*=\s*(\[[^\]]+\]|\{\{[\w.\[\]]+\}\})", b)
        mpos = re.search(r"position\s*=\s*(\[[^\]]+\]|\{\{[\w.\[\]]+\}\})", b)
        msz = re.search(r"\bsize\s*=\s*([\d.]+)", b)        # USD Cube edge-length (alt to scale)
        scale = None; pos = None
        if ms:
            sv = ms.group(1); scale = _num_list(sv) if sv.startswith("[") else _num_list(str(_resolve(sv, rd)) or "")
        if mpos:
            pv = mpos.group(1); pos = _num_list(pv) if pv.startswith("[") else _num_list(str(_resolve(pv, rd)) or "")
        rec = {"type": mt.group(1), "pos": pos, "scale": scale, "size": (float(msz.group(1)) if msz else None)}
        pexpr = mp.group(1).strip()
        rp = _resolve(pexpr.strip('"'), rd)
        if isinstance(rp, str) and rp.startswith("/"):
            prims[rp] = rec
        else:
            rec["expr"] = pexpr
            rec["stem"] = varstem.get(pexpr.strip().strip('"'))   # loop var -> iterated stem (cube)
            loose.append(rec)
    return prims, loose

def full_dims(p):
    # USD: `scale` multiplies the default size-2 cube (full = 2*scale); `size` sets the edge directly
    # (full = size); both -> size*scale. Cylinder follows the same scale convention.
    sc = p.get("scale"); sz = p.get("size")
    if sc is not None:                       # pad/truncate to exactly 3 (heterogeneous authoring)
        sc = (list(sc) + [sc[-1]] * 3)[:3] if sc else None
    if sz is not None:
        return [sz * sc[0], sz * sc[1], sz * sc[2]] if sc else [sz, sz, sz]
    if sc:
        return [2 * sc[0], 2 * sc[1], 2 * sc[2]]
    return [0.05, 0.05, 0.05]

def _hasgeom(r):
    return bool(r and (r.get("scale") or r.get("size")))

def geom_for(path, prims, loose):
    if path in prims and _hasgeom(prims[path]):
        return prims[path]
    stem = re.sub(r"_?\d+$", "", path.split("/")[-1]).lower()   # Cube_1 -> cube
    for rec in loose:
        ex = (rec.get("expr") or "").lower()
        if _hasgeom(rec) and stem and (rec.get("stem") == stem or stem in ex):
            return rec
    # last resort: a lone loose entry with a scale
    cands = [r for r in loose if _hasgeom(r)]
    return cands[0] if len(cands) == 1 else None

def robot_family(tpl, rd):
    blob = (json.dumps(rd) + str(tpl.get("robot") or "")).lower()
    return "ur10" if ("ur10" in blob or "surface_grip" in blob) else "franka"

def analyse(name):
    path = os.path.join(TPL_DIR, name if name.endswith(".json") else name + ".json")
    if not os.path.exists(path):
        return {"tpl": name, "verdict": "NO_TEMPLATE"}
    tpl = json.load(open(path))
    rd = tpl.get("role_defaults") or {}
    src = tpl.get("code_template") or tpl.get("code") or ""
    prims, loose = parse_prims(src, rd)
    fam = robot_family(tpl, rd)
    gpaths = grasped_paths(tpl, rd, src)
    if not gpaths:
        return {"tpl": name, "fam": fam, "verdict": "NO_GRASP_TARGET"}
    g0 = gpaths[0]
    gp = geom_for(g0, prims, loose)
    if not _hasgeom(gp):
        return {"tpl": name, "fam": fam, "verdict": "UNPARSED_GEOM", "grasped": g0}
    gdim = full_dims(gp)
    jaw_w = min(gdim[0], gdim[1])
    grip_halfwidth = max(jaw_w / 2.0, 1e-4)
    # composite ONLY if the object has a dedicated Xform wrapper (parent != /World) -> sum the sibling parts.
    parent = g0.rsplit("/", 1)[0]
    parts = []
    if parent and parent != "/World" and gp.get("pos"):
        parts = [(pp, pr) for pp, pr in prims.items()
                 if pp.rsplit("/", 1)[0] == parent and pr.get("pos") and _hasgeom(pr)
                 and pr.get("type") in ("Cube", "Cylinder")]
    if len(parts) > 1:
        tot_v = 0.0; cg_z = 0.0
        for _, pr in parts:
            d = full_dims(pr); v = max(d[0] * d[1] * d[2], 1e-9); tot_v += v; cg_z += v * pr["pos"][2]
        cg_z /= tot_v
        cg_off = gp["pos"][2] - cg_z            # +ve = CG below the grip line
        composite = True
    else:
        cg_off = 0.0                            # single-part: CG == centroid == grip line
        composite = False
    ratio = abs(cg_off) / grip_halfwidth
    if jaw_w > 0.6:
        # No real manipulation target is >60cm across — this is the parser grabbing scenery
        # (a Table/Ground/oversized scale), NOT a verdict. Report honestly, don't assert UNGRASPABLE.
        verdict = "SUSPECT-GEOM(parse? %.0fmm)" % (jaw_w * 1000)
    elif jaw_w > MAX_JAW:
        verdict = "UNGRASPABLE-JAW(%.0fmm>%.0f)" % (jaw_w * 1000, MAX_JAW * 1000)
    elif ratio > 2.0:
        verdict = "PENDULUM-RISK"
    elif ratio > 0.8:
        verdict = "marginal"
    else:
        verdict = "geom-OK"
    note = "(suction robot — jaw pendulum metric N/A; face-seal TODO)" if fam == "ur10" else \
           ("(geom-OK on jaw fit+balance; contact-couple verdict needs CAD2SimReady/scene_eyes)"
            if (verdict == "geom-OK" and not composite) else "")
    # GRIPPER-CHOOSER: the end-effector the OBJECT wants, + MISMATCH = a jaw robot (Franka) assigned an
    # object it geometrically cannot pinch (too wide). UR10 has suction so a wide flat object is fine there;
    # a Franka jaw cannot -> the template must either switch to suction/UR10 or grasp a NARROWER feature than
    # the bbox (e.g. an EStop's stem, a cart's handle) -> a grasp-point refinement. Additive: verdict unchanged.
    if jaw_w > 0.6:
        recommend = "?(suspect-geom)"
    elif jaw_w > MAX_JAW:
        recommend = "suction (or narrower grasp feature)"
    elif ratio > 2.0:
        recommend = "jaw + form-closure/support (pendulum)"
    else:
        recommend = "jaw"
    mismatch = bool(fam == "franka" and MAX_JAW < jaw_w <= 0.6)
    return {"tpl": name, "fam": fam, "grasped": g0.split("/")[-1], "composite": composite,
            "jaw_w_mm": round(jaw_w * 1000, 1), "cg_off_mm": round(cg_off * 1000, 1),
            "ratio": round(ratio, 2), "verdict": verdict, "recommend": recommend,
            "mismatch": mismatch, "note": note}

VALIDATION = ["CP-NEW-oxe-sweep-into-dustpan", "CP-08", "CP-13", "CP-NEW-turn-faucet", "CP-NEW-drawer-open"]

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "all":
        names = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(TPL_DIR, "*.json")))
    elif arg:
        names = [arg]
    else:
        names = VALIDATION
        print("=== VALIDATION (broom -> PENDULUM-RISK ; cube CP-08/CP-13 -> geom-OK) ===")
    rows = [analyse(n) for n in names]
    for r in rows:
        if "jaw_w_mm" not in r:
            print("  %-42s %s %s" % (r["tpl"], r["verdict"], r.get("grasped", "")))
        else:
            print("  %-42s %-7s grasp=%-13s comp=%-5s jaw=%5.1fmm CGoff=%+6.1fmm ratio=%4.1f -> %-20s %s"
                  % (r["tpl"], r["fam"], r["grasped"], r["composite"], r["jaw_w_mm"], r["cg_off_mm"],
                     r["ratio"], r["verdict"], r["note"]))
    if arg == "all":
        from collections import Counter
        c = Counter(re.sub(r"\(.*", "", r["verdict"]) for r in rows)
        cov = sum(1 for r in rows if "jaw_w_mm" in r)
        print("\n=== corpus: %d/%d parsed ===" % (cov, len(rows)))
        for k, v in c.most_common():
            print("  %-26s %d" % (k, v))
        mm = [r for r in rows if r.get("mismatch")]
        print("\n=== GRIPPER-CHOOSER MISMATCH (Franka jaw assigned an object too wide to pinch -> switch to "
              "suction/UR10 OR grasp a narrower feature): %d ===" % len(mm))
        for r in sorted(mm, key=lambda x: -x["jaw_w_mm"]):
            print("  %-42s grasp=%-12s jaw=%5.1fmm -> %s" % (r["tpl"], r["grasped"], r["jaw_w_mm"], r["recommend"]))
    elif arg and arg != "all":
        for r in rows:
            if r.get("recommend"):
                print("  GRIPPER-CHOOSER: %s%s" % (r["recommend"], "   [MISMATCH: jaw robot can't pinch this]" if r.get("mismatch") else ""))

if __name__ == "__main__":
    main()
