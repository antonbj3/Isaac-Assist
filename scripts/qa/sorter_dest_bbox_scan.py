#!/usr/bin/env python3
"""sorter_dest_bbox_scan.py — static PRE-FILTER for the multi-dest-sorter false-pass signature (cont.144).

The routing-aware honest gate grades each cube against its ASSIGNED destination's BBOX. A destination that
is a real bbox (create_bin, or a sized create_prim Cube/Cylinder+scale) is graded correctly. A BBOX-LESS
Xform anchor has no bbox -> the gate silently degrades to the UNION of all destinations -> a misrouted cube
counts as "delivered" = FALSE-PASS (the CP-NEW-palletizer-mixed-sku class). This scans the whole template
corpus for that signature and flags multi-dest sorters whose routing destinations are bbox-less.

⚠️ PRE-FILTER ONLY (Anton 2026-06-15: static < Kit scene_eyes). A hit is a CANDIDATE, not a verdict — confirm
each with a Kit gate_one run (does the gate actually false-pass at runtime?). A clean result means "no
bbox-less-destination false-pass signature in the corpus" — the systematic closure of the false-pass hunt.

Run: python3 scripts/qa/sorter_dest_bbox_scan.py   (exit 0 = no candidates; 1 = candidates to Kit-verify)
"""
import json, glob, re, os, sys

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"


def _destinations(sim_targets, dest_map):
    d = set()
    for src in (sim_targets, dest_map):
        for v in (src or {}).values():
            if isinstance(v, str) and v.startswith("/World"):
                d.add(v)
    return d


def _how_created(code, path):
    """Classify how a destination prim is created: real-bbox vs bbox-less Xform vs not-found."""
    if re.search(r'create_bin\([^)]*prim_path="%s"' % re.escape(path), code):
        return "create_bin(bbox)"
    m = re.search(r'create_prim\([^)]*prim_path="%s"[^)]*\)' % re.escape(path), code)
    if m:
        seg = m.group(0)
        kind = re.search(r'prim_type="(\w+)"', seg)
        sized = ("scale=" in seg or "size=" in seg)
        if kind and kind.group(1) in ("Cube", "Cylinder", "Cone") and sized:
            return "create_prim %s+scale(bbox)" % kind.group(1)
        if (not kind) or kind.group(1) == "Xform":
            return "create_prim Xform(BBOX-LESS)"
        return "create_prim %s" % kind.group(1)
    return "NOT-FOUND-in-code"


def scan():
    candidates = []
    for f in sorted(glob.glob(os.path.join(REPO, "workspace/templates/*.json"))):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        code = d.get("code", "") or ""
        sa = d.get("simulate_args", {}) or {}
        dm = {}
        mdm = re.search(r'destination_map=\{([^}]*)\}', code)
        if mdm:
            for k, v in re.findall(r'"([^"]+)":\s*"([^"]+)"', mdm.group(1)):
                dm[k] = v
        dests = _destinations(sa.get("targets"), dm)
        if len(dests) < 2:          # multi-dest sorters only
            continue
        creations = {p: _how_created(code, p) for p in sorted(dests)}
        bboxless = [p for p, c in creations.items() if "BBOX-LESS" in c]
        name = os.path.basename(f).replace(".json", "")
        tag = "BBOX-LESS DEST -> Kit-verify" if bboxless else "ok (real bbox dests)"
        print("%-42s %-28s %d dests: %s" % (
            name, tag, len(dests),
            ", ".join("%s=%s" % (p.split("/")[-1], c) for p, c in creations.items())))
        if bboxless:
            candidates.append((name, bboxless))
    print("\n=== FALSE-PASS CANDIDATES (bbox-less destinations -> Kit gate_one to confirm) ===")
    if not candidates:
        print("NONE — no bbox-less-destination false-pass signature in the corpus.")
    else:
        for n, b in candidates:
            print("  %s: %s" % (n, b))
    return candidates


if __name__ == "__main__":
    sys.exit(1 if scan() else 0)
