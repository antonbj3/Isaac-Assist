#!/usr/bin/env python3
"""composable_registry.py — the TRUSTED composable-block registry (Anton 2026-06-15: "få grund-
templates 100% innan kompositioner" + "vi har rensat dubbletter").

The composition strategy chains ROBUST templates. A block is trustworthy only if its delivery is
GENUINE, and (this session's lesson) the position/delivery gate LIES for STRUCTURE (a tower stacker
that scatters reads delivered). So trust is earned two ways:
  - POSITION-HONEST classes (bin / place / sort): "in the bin" cannot be faked without real transport
    + grasp -> the delivery gate is honest; trust it.
  - STRUCTURE classes (stack/column, palletize/grid): the position gate is blind to scatter-vs-column,
    so require a scene_eyes STACK-STRUCTURE verdict (parsed from the sweep) — COLUMN/GRID = genuine,
    SCATTER/PILE = false (excluded), PARTIAL = needs work.

Dedup insight: the 70 verified-core has large VARIATION matrices (e.g. 17 Franka pick-place-bin differing
by one factor each — belt speed, gripper, obstacle...). Those are TEST coverage, not distinct blocks. For
composition we pick ONE canonical representative per (robot x function-class); the rest stay as coverage.

Reads composition_hints.json (the 70) + /tmp/stacker_sweep.txt (scene_eyes structure verdicts). Emits
workspace/composable_blocks.json + a human summary. Re-run after the sweep completes for the full picture.
"""
import json, os, re, collections

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
SWEEP = "/tmp/stacker_sweep.txt"
# scene_eyes verdicts already established this session (gold re-verification, cont.96-98):
KNOWN = {"CP-01": "GENUINE", "CP-03": "GENUINE", "CP-13": "GENUINE(column)",
         "CP-28": "GENUINE", "CP-29": "GENUINE", "CP-09": "FALSE(scatter)",
         # RAW-verified 2026-06-17 (cont.193-202; scene_eyes/routing_validate per-object) — pinned here so a
         # registry regen reproduces them instead of reverting to TRUSTED(position-honest)/sweep defaults:
         "CP-08": "GENUINE(grid)", "CP-42": "GENUINE(grid)",          # grid spread RAW-verified (CP-42 was UNCLEAR pre-#45)
         "CP-16": "GENUINE(routed)", "CP-50": "GENUINE(kit-routed)",  # color-sort + kit tray-routing xy-containment
         "CP-70": "GENUINE(grip+deliver)", "CP-73": "GENUINE(grip+deliver)",  # UR10 anchors: grip+carry+deliver, 0 slip
         "CP-34": "PARTIAL(stochastic blue place)"}                   # blue stochastic to far bin (in-bin 1/floor 2)
# canonical representative per (robot, class) — the most vanilla/robust block to compose FROM:
CANON = {("Franka", "pick-place-bin"): "CP-01", ("Franka", "color-sort"): "CP-03",
         ("Franka", "stack/column"): "CP-13", ("Franka", "palletize/grid"): "CP-08",
         ("Franka", "kit/assembly"): "CP-50", ("UR10", "pick-place-bin"): "CP-73"}


def fclass(g):
    g = g.lower()
    if "sort" in g: return "color-sort"
    if any(w in g for w in ["tower", "column", "cube-on-cube", "graduated"]): return "stack/column"
    if any(w in g for w in ["pallet", "palletiz", "grid", "2x2", "3x3"]): return "palletize/grid"
    if any(w in g for w in ["kit", "assembl"]): return "kit/assembly"
    if any(w in g for w in ["inspect", "reject", "divert", "vision"]): return "inspect/vision"
    if any(w in g for w in ["pick", "place", "bin", "drop"]): return "pick-place-bin"
    return "other"


def sweep_verdicts():
    """Parse scene_eyes STACK-STRUCTURE verdicts from the sweep log."""
    if not os.path.exists(SWEEP):
        return {}
    txt = open(SWEEP).read()
    out = {}
    for name, body in re.findall(r"===== SWEEP (\S+) =====(.*?)(?=\n===== SWEEP|\Z)", txt, re.S):
        # PARTIAL wins over structure: a result can show a column AND have un-picked cubes (CP-20: 8/13
        # gripped, 5 NEVER approached). Partial delivery is NOT a trusted block, so check it FIRST.
        if "NEVER approached" in body or "never-gripped" in body:
            v = "PARTIAL(some never gripped/approached)"
        elif "no rows" in body or "NO CUBES" in body:
            v = "NO-DATA"
        elif "COLUMN / multi-tier" in body:
            v = "GENUINE(column)"
        elif "FLAT 1-tier spread grid" in body:
            v = "GENUINE(grid)"
        elif "FLAT 1-tier" in body and "clustered" in body:
            v = "FALSE(scatter/pile)"
        else:
            v = "UNCLEAR"
        out[name] = v
    return out


def main():
    hints = json.load(open(os.path.join(REPO, "workspace", "composition_hints.json")))["hints"]
    sw = sweep_verdicts()
    blocks = {}
    for n in sorted(hints):
        try:
            t = json.load(open(os.path.join(REPO, "workspace", "templates", n + ".json")))
        except Exception:
            continue
        code = (t.get("code") or t.get("code_template") or "").lower()
        g = t.get("goal") or ""
        robot = "UR10" if ("ur10" in (code + g.lower()) or "ur5" in (code + g.lower())) else ("Franka" if ("franka" in (code + g.lower()) or "panda" in (code + g.lower())) else "?")
        cls = fclass(g)
        structure = cls in ("stack/column", "palletize/grid")
        # trust verdict. A verified_status that LEADS with a refutation verdict
        # overrides the position-honest default: the 2026-06-23 false-success
        # audit proved bin/sort cells CAN fail orientation (a cube toppled
        # OUTSIDE its bin — CP-NEW-y-merge-singulation, CP-NEW-sorter-size-weight),
        # so "in-the-bin = trusted" is UNSAFE once scene_eyes has refuted the cell.
        _vs = (t.get("verified_status") or "").strip().upper()
        _refuted = _vs.startswith(("REFUTED", "ORIENTATION-REFUTED", "FALSE", "NOT A GOLD"))
        if n in KNOWN:
            verdict, basis = KNOWN[n], "scene_eyes (this session)"
        elif _refuted:
            verdict, basis = "PARTIAL(scene_eyes-refuted; see verified_status)", "verified_status refutation"
        elif structure:
            verdict, basis = sw.get(n, "PENDING(sweep)"), "scene_eyes STACK-STRUCTURE"
        else:
            verdict, basis = "TRUSTED(position-honest)", "delivery-gate (honest for bin/sort)"
        blocks[n] = {"robot": robot, "class": cls, "verdict": verdict, "basis": basis,
                     "n_objects": hints[n].get("n_objects", 0)}

    def trusted(v): return v.startswith("GENUINE") or v.startswith("TRUSTED")
    # group + canonical reps
    by_cls = collections.defaultdict(list)
    for n, b in blocks.items():
        by_cls[(b["robot"], b["class"])].append(n)
    registry = {"canonical_blocks": {}, "all": blocks, "summary": {}}
    print("=== TRUSTED COMPOSABLE-BLOCK REGISTRY ===")
    tcount = collections.Counter()
    for (robot, cls), names in sorted(by_cls.items()):
        gen = [n for n in names if trusted(blocks[n]["verdict"])]
        bad = [n for n in names if blocks[n]["verdict"].startswith("FALSE")]
        part = [n for n in names if blocks[n]["verdict"].startswith("PARTIAL")]
        pend = [n for n in names if blocks[n]["verdict"].startswith(("PENDING", "UNCLEAR", "NO-DATA"))]
        canon = CANON.get((robot, cls))
        if canon and canon not in gen:
            canon = gen[0] if gen else None
        registry["canonical_blocks"][f"{robot}:{cls}"] = canon
        tcount["trusted"] += len(gen); tcount["false"] += len(bad); tcount["partial"] += len(part); tcount["pending"] += len(pend)
        print(f"\n[{robot} / {cls}]  canonical={canon}")
        print(f"   trusted({len(gen)}): {' '.join(gen) if gen else '-'}")
        if bad: print(f"   FALSE({len(bad)}): {' '.join(bad)}")
        if part: print(f"   PARTIAL({len(part)}): {' '.join(part)}")
        if pend: print(f"   pending({len(pend)}): {' '.join(pend)}")
    registry["summary"] = {"trusted": tcount["trusted"], "false": tcount["false"], "partial": tcount["partial"], "pending": tcount["pending"], "total": len(blocks)}
    print(f"\nSUMMARY: trusted={tcount['trusted']} false={tcount['false']} partial={tcount['partial']} pending={tcount['pending']} total={len(blocks)}")
    out = os.path.join(REPO, "workspace", "composable_blocks.json")
    json.dump(registry, open(out, "w"), indent=2)
    print("->", out)


if __name__ == "__main__":
    main()
