#!/usr/bin/env python3
"""eyes_gold_gate.py — the scene_eyes-GRADE gold gate for compositions (Anton 2026-06-15: gold must be
scene_eyes-verified, NOT position-measured; "använd scene eyes, bygg inte om det").

The CP-09 lesson: a position/bbox measure counts a scattered tower as "delivered". So a composition is
gold ONLY if scene_eyes' OWN verdict (its printed analysis, per instance) confirms, for EVERY cell:
  - every cube CONVERGED + GRIPPED (no "NEVER approached") = real transport + grasp, and
  - structure matches the template's INTENT:
       stack/column  -> STACK STRUCTURE must show >=2 z-levels (a real column, not a flat scatter)
       palletize/grid -> FLAT 1-tier grid is CORRECT (gaps for gripper clearance)
       bin/place/sort -> any arrangement in the target is fine (no structure requirement)
  - no real EJECTION/EXPLOSION.
This PARSES scene_eyes' printed output (not raw eyes.json, not a re-implemented measure). Feed it the
per-instance scene_eyes stdout captured by the orchestration wrapper.

Usage: eyes_gold_gate.py CP-01:inst0_analysis.txt CP-09:inst1_analysis.txt ...
  each arg = "<template>:<path-to-that-instance's-scene_eyes-stdout>". Exit 0 = GOLD (all cells genuine).
"""
import sys, os, re, json


def _class(template):
    try:
        t = json.load(open(f"/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/{template}.json"))
    except Exception:
        return "unknown"
    g = (t.get("goal") or "").lower()
    # cont.319cc audit #2: a PALLETIZER is a structured flat grid -> the structure gate, even if its goal also
    # says "sorted"/"sku" (e.g. CP-NEW-palletizer-mixed-sku). Check pallet/palletiz BEFORE "sort", else a sorted
    # palletizer routes to the lenient color-sort branch and a collapsed grid false-passes. A pure colour-sort
    # (into bins, no pallet) has no "pallet" token -> still color-sort. Routing a sort-onto-pallet here is only
    # STRICTER (flat-grid check), never a false-negative.
    # cont.319-STACKCOMPOSE fix: check COLUMN/STACK keywords BEFORE pallet. CP-13's goal is "2-cube column
    # stack (cube-on-cube) ... on a PALLET base" — the word "pallet" (the base) wrongly routed it to
    # palletize/grid (flat-expected), which then REJECTED its CORRECT 2-z-level column as a "pile" (a false-
    # negative). A cube-on-cube / column / tower goal is a STACK even when it mentions a pallet base. Keeps
    # pallet-before-sort (a sorted palletizer stays palletize/grid).
    if any(w in g for w in ["tower", "column", "cube-on-cube", "graduated"]): return "stack/column"
    if any(w in g for w in ["pallet", "palletiz"]): return "palletize/grid"
    if "sort" in g: return "color-sort"
    if any(w in g for w in ["grid", "2x2", "3x3"]): return "palletize/grid"
    return "pick-place-bin"


def _claimed_leaves(template):
    """Leaf names of the controller's source_paths = the CLAIMED picks. For a SELECTIVE pick (vision/LLM
    picks a SUBSET, e.g. source_paths=[one object] among many), the UN-claimed objects are left BY DESIGN
    and must NOT count as never-gripped / outside-bin failures. Returns set() when source_paths can't be
    resolved (no list, or a templated loop) -> caller falls back to the old all-objects behaviour (safe:
    never relaxes a multi-pick scene)."""
    try:
        t = json.load(open(f"/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/{template}.json"))
    except Exception:
        return set()
    code = t.get("code_template", "") or t.get("code", "")
    m = re.search(r"source_paths\s*=\s*\[(.*?)\]", code, re.S)
    if not m:
        return set()
    leaves = set()
    for p in re.findall(r'["\']([^"\']+)["\']', m.group(1)):
        if "{" in p:                       # templated loop -> unresolved -> old behaviour
            return set()
        leaves.add(p.rsplit("/", 1)[-1])
    return leaves


def verdict_for_instance(text, cls, claimed=None):
    """Return (genuine: bool, reason: str) from one instance's scene_eyes printed analysis."""
    # ANY ungripped cube = partial = reject. scene_eyes writes "never-gripped" for BOTH the far case
    # ("NEVER approached") AND the close-but-no-grasp case ("approached but not gripped") — match the
    # common token, not just "NEVER approached" (that hole passed a 3/4 CP-08 partial as GOLD, cont.108).
    never = len(re.findall(r"never-gripped", text, re.I))
    # SELECTIVE-PICK scope (vision/LLM pick a SUBSET): un-claimed objects left by design are NOT a partial.
    # Count never-gripped only among CLAIMED picks (source_paths leaves); fall back to all if names unparsed
    # or claimed unresolved (multi-pick = all claimed -> unchanged). Conservative: a CLAIMED never-gripped
    # still rejects (no false-positive); only provably-left objects are excused.
    if claimed and never:
        _ng_names = re.findall(r"^\s{2,}(\S+)\s+never-gripped", text, re.M)
        if _ng_names:
            never = sum(1 for n in _ng_names if n in claimed)
    # cont.319cc audit #5: a per-object 'GRIP-SLIP (... object NEVER LIFTED, not held)' (scene_eyes PICK-CONVERGENCE
    # 1086/1090) = the gripper contacted the cube but it never came off the surface = NOT transported. That token is
    # neither 'never-gripped' nor 'CONVERGED + GRIPPED', so the gate was BLIND to it: a partial where one cube
    # slipped while another succeeded false-passed the bin/grid branch. Treat 'never lifted' as a reject (same class
    # as never-gripped). Matches ONLY the per-object slip verdict (not the EE-relative GRIP-SLIP section header).
    slipped = len(re.findall(r"never lifted", text, re.I))
    gripped = len(re.findall(r"(?<!never-)CONVERGED \+ GRIPPED", text))
    real_explosion = "*** EXPLODED/EJECTED ***" in text   # offset-invariant in current scene_eyes
    # FELL-TO-GROUND: a cube ending well below any target surface (<0.6m; targets sit ~0.75-0.90 on the
    # table) = fell off / never placed. Do NOT use scene_eyes' OFF-SURFACE "fell from peak" signal — it
    # false-fires on EVERY normal pick-place (lift to transit height then place lower). Use the final
    # z-LEVELS from STACK STRUCTURE instead: a level <0.6 is on the ground, not a controlled placement.
    zmatch0 = re.search(r"STACK STRUCTURE \([^)]*\): \d+ z-level\(s\) \[([^\]]*)\]", text)
    low_z = False
    if zmatch0:
        try:
            low_z = any(float(z) < 0.6 for z in zmatch0.group(1).split(","))
        except Exception:
            low_z = False
    # SETTLED-Z floor-check (2026-06-17): STACK STRUCTURE z-levels only emit for >=2 objects, so a SINGLE-cube
    # bin delivery had NO floor guard -> a grip-then-drop-to-floor false-PASSED once asset-suction grips read as
    # CONVERGED+GRIPPED. scene_eyes now emits per-box-cube SETTLED-Z for ANY count; reject if any settled <0.6m.
    szmatch = re.search(r"SETTLED-Z \([^)]*\): (.+)", text)
    if szmatch:
        try:
            for _tok in szmatch.group(1).split():
                if "=" in _tok and float(_tok.split("=")[1]) < 0.6:
                    low_z = True
                    break
        except Exception:
            pass
    zmatch = re.search(r"STACK STRUCTURE \([^)]*\): (\d+) z-level", text)
    zlevels = int(zmatch.group(1)) if zmatch else None
    # min-pair-xy (closest cube-pair in the plane) — distinguishes a SPREAD grid (gaps, gripper clearance)
    # from a CLUSTERED/PILED heap. A 2x2 grid palletizer must end FLAT (1 z-level) AND spread; a composed
    # CP-08 whose drop_targets dict didn't namespace/offset collapsed all cubes onto the pallet centre =
    # 2 z-levels + min-pair << cube-width = a PILE the lenient gate used to false-pass (cont.150).
    mpmatch = re.search(r"min-pair-xy=([\d.]+)m", text)
    minpair = float(mpmatch.group(1)) if mpmatch else None
    # xy-EXTENT (#48, cont.319hh): the bbox of all delivered cubes in the plane. A real COLUMN is xy-aligned
    # (cubes stacked on each other) -> tiny extent; a "2 z-level" set with a LARGE extent = cubes at different
    # heights but NOT vertically stacked (an UPRIGHT-but-displaced cube the tilt-topple check above misses).
    xematch = re.search(r"xy-extent=([\d.]+)x([\d.]+)m", text)
    xyext = max(float(xematch.group(1)), float(xematch.group(2))) if xematch else None
    # ORIENTATION/TOPPLE (2026-06-16, Anton false-success): a cube delivered to the right XY/Z but resting on
    # its SIDE is not correctly placed. scene_eyes now emits a settled-tilt ORIENTATION block; a >60° topple is
    # a hard reject (mirrors the Modal `vec` TOPPLED that the position gate is blind to — CP-09 lesson). TILTED
    # (30-60°) is a soft warning only — NOT a reject (avoids false-negatives per Anton's no-graze principle).
    toppled = re.search(r"\*\*\* ORIENTATION FAIL: \d+ object\(s\) TOPPLED[^:]*: ([^*]+?) \*\*\*", text)
    if never:
        return False, f"{never} cube(s) NEVER approached (not transported/grasped)"
    if slipped:
        return False, f"{slipped} cube(s) GRIP-SLIPPED (finger-contact but the object never lifted off the surface = not transported)"
    if gripped == 0 and zlevels is None:
        return False, "no CONVERGED+GRIPPED and no structure data (likely no grasp / no rows)"
    if real_explosion:
        return False, "real EJECTION/EXPLOSION detected"
    if toppled:
        _topp = toppled.group(1).strip()
        # SELECTIVE-PICK scope: only a CLAIMED pick toppling = bad PLACEMENT. An un-claimed object left in
        # place that settles tilted (e.g. a curved banana's spawn pose, a tipped cylinder) is not a delivery
        # failure — we never placed it. Keep the reject for claimed picks (and for multi-pick where claimed=all).
        if claimed:
            _claimed_topp = [n for n in re.split(r"[,\s]+", _topp) if n and n in claimed]
            _topp = ", ".join(_claimed_topp) if _claimed_topp else ""
        if _topp:
            return False, f"object(s) TOPPLED — delivered but tipped >60° from upright (not correctly placed): {_topp}"
    if low_z:
        return False, "a cube ended below 0.6m (fell to ground / never placed on the target surface)"
    if cls in ("unknown", ""):
        # FAIL-CLOSED: if we can't classify the template's intent we must NOT fall through to the
        # lenient bin/sort branch (that would pass a scattered stacker). Demand explicit re-run with
        # a known template id.
        return False, "template class UNKNOWN — fail-closed (re-run with a resolvable template id)"
    if cls == "stack/column":
        if zlevels is None or zlevels < 2:
            return False, f"stacker but {zlevels} z-level(s) = FLAT SCATTER, not a column"
        # #48 (cont.319hh): >=2 z-levels alone passes a set of cubes that are at different heights but NOT
        # vertically stacked (an upright cube displaced off the column axis -- the tilt-topple check misses an
        # untilted-but-misplaced cube). A real column is xy-ALIGNED. Calibrated on the known-good columns
        # CP-13/14/15 (max-xy-extent <=0.011m); reject >0.06m = a 5.5x margin so a valid/graduated/settle-
        # jittered column never false-refuses, while a cube displaced a full width off the axis is caught.
        if xyext is not None and xyext > 0.06:
            return False, f"stacker {zlevels} z-levels but xy-extent {xyext*1000:.0f}mm (>60mm) = cubes NOT vertically aligned (displaced off the column axis, not a real stack)"
        return True, f"column verified ({zlevels} z-levels, {gripped} gripped" + (f", xy-extent {xyext*1000:.0f}mm aligned)" if xyext is not None else ")")
    if cls == "palletize/grid":
        # A 2x2/grid palletizer must end as a FLAT (1 z-level) SPREAD grid. cont.150: a composed CP-08 whose
        # drop_targets collapsed to the pallet centre reads 2 z-levels + min-pair-xy 12-27mm (< the 50mm cube
        # width = cubes overlapping/stacked) = a PILE, which the old branch false-passed as "grid verified".
        # Reject a non-flat (>=2 z-level) OR clustered (min-pair < 0.045m) "grid". Uses the spread-vs-pile
        # signal scene_eyes already emits (STACK STRUCTURE min-pair-xy). standalone CP-08 = 1 level/131mm = PASS.
        if zlevels is not None and zlevels >= 2:
            return False, f"palletizer but {zlevels} z-levels = PILE/STACK, not a flat grid (cubes collapsed onto each other)"
        if minpair is not None and minpair < 0.045:
            return False, f"palletizer grid CLUSTERED (min-pair-xy {minpair*1000:.0f}mm < cube-width) = piled, not a spread grid"
        return True, f"grid verified ({gripped} gripped, {zlevels} z-level, min-pair {minpair*1000:.0f}mm spread)" if minpair is not None else f"grid verified ({gripped} gripped, {zlevels} z-level)"
    # bin/place/sort: transport+grasp is enough, no structure requirement — BUT (#36, 2026-06-19) the object
    # must also end INSIDE the bin's xy FOOTPRINT. scene_eyes now emits XY-CONTAINMENT lines (per box-like
    # delivery object vs the recorded collection-bin footprints) whenever a bin is present. A cube that was
    # gripped + transported but settled NEXT TO the bin (upright, at floor-z) passed never-gripped, the floor
    # guard AND the topple check — this closes that last hole. Fires ONLY when bins were recorded (a 'place on
    # a table/surface' task emits no XY-CONTAINMENT block -> no check -> unchanged). The reject lives HERE (not
    # in scene_eyes) because it is class-aware: a composed bin+pallet scene has pallet objects legitimately
    # outside the bin, and that path is graded by compose_and_verify, never this single-instance bin branch.
    outside = re.findall(r"xy-in-bin=NO", text)
    # SELECTIVE-PICK scope: only CLAIMED picks are required to land in the bin; un-claimed objects left in
    # place (on the table / source bin) are correctly outside the OUTPUT bin and must not reject.
    if claimed and outside:
        _out_names = re.findall(r"^\s{2,}(\S+)\s+xy-in-bin=NO", text, re.M)
        if _out_names:
            outside = [n for n in _out_names if n in claimed]
    if outside:
        return False, f"{len(outside)} delivery object(s) settled OUTSIDE the bin xy footprint (transported+gripped but dropped next to the bin, not IN it)"
    return True, f"delivery verified ({gripped} gripped)"


def main():
    argv = list(sys.argv[1:])
    expect = None
    if "--expect" in argv:
        try: expect = int(argv[argv.index("--expect") + 1])
        except Exception: expect = None
    pairs = [a.split(":", 1) for a in argv if ":" in a]
    if not pairs:
        print("usage: eyes_gold_gate.py [--append] [--expect N] CP-01:inst0.txt CP-09:inst1.txt ..."); return 2
    # 2026-06-16: GUARD against silent cell-DROP — a KIT_BOOT_FAIL / skipped instance must NOT pass as
    # "all cells genuine". If the caller declares the composition's cell count (--expect N) and fewer
    # instances were evaluated, FAIL: a partial evaluation is INVALID, not GOLD. (cont.123: a 5-cell run
    # where inst1/CP-08 boot-failed still printed GOLD over the surviving 4 cells + appended a mislabeled
    # 4-cell record. partial-as-pass is the exact false-positive that must never pass.)
    if expect is not None and len(pairs) != expect:
        print("  CELL-COUNT MISMATCH: evaluated %d of %d cells (boot-fail / skipped instance)" % (len(pairs), expect))
        print("EYES_GOLD_VERDICT: NOT GOLD (incomplete — %d/%d cells evaluated; re-run)" % (len(pairs), expect))
        return 1
    all_ok = True
    cells, verdicts = [], []
    for tpl, path in pairs:
        cls = _class(tpl)
        text = open(path).read() if os.path.exists(path) else ""
        ok, reason = verdict_for_instance(text, cls, claimed=_claimed_leaves(tpl))
        all_ok = all_ok and ok
        cells.append(tpl); verdicts.append({"template": tpl, "class": cls, "genuine": ok, "reason": reason})
        print(f"  {tpl:12s} [{cls:16s}] {'GENUINE' if ok else 'REJECT '} — {reason}")
    print("EYES_GOLD_VERDICT:", "GOLD (all cells scene_eyes-genuine)" if all_ok else "NOT GOLD (a cell failed scene_eyes)")
    # end-to-end: on a GOLD verdict, APPEND a scene_eyes-verified gold record (dedup on ordered cells).
    if all_ok and "--append" in sys.argv:
        import time
        p = "/home/anton/projects/Omniverse_Nemotron_Ext/workspace/training_data/verified_compositions.jsonl"
        key = tuple(cells)
        seen = set()
        if os.path.exists(p):
            for ln in open(p):
                try:
                    pr = json.loads(ln)
                    if pr.get("verification_tier") == "gold_scene_eyes_verified":
                        seen.add(tuple(c["template"] for c in pr["plan"]["cells"]))
                except Exception:
                    pass
        if key in seen:
            print("SCENE_EYES_GOLD already recorded (not duplicated):", "+".join(cells))
        else:
            rec = {"ts": time.time(), "level": "L2_composition",
                   "verification_tier": "gold_scene_eyes_verified",
                   "task": "compose " + " + ".join(cells),
                   "plan": {"cells": [{"id": f"inst{i}", "template": t} for i, t in enumerate(cells)], "layout": "parallel"},
                   "scene_eyes_composition_verified": True, "scene_eyes_cells": verdicts}
            with open(p, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print("SCENE_EYES_GOLD_APPENDED:", "+".join(cells), "->", p)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
