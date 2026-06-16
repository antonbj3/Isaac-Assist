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
    if "sort" in g: return "color-sort"
    if any(w in g for w in ["tower", "column", "cube-on-cube", "graduated"]): return "stack/column"
    if any(w in g for w in ["pallet", "palletiz", "grid", "2x2", "3x3"]): return "palletize/grid"
    return "pick-place-bin"


def verdict_for_instance(text, cls):
    """Return (genuine: bool, reason: str) from one instance's scene_eyes printed analysis."""
    # ANY ungripped cube = partial = reject. scene_eyes writes "never-gripped" for BOTH the far case
    # ("NEVER approached") AND the close-but-no-grasp case ("approached but not gripped") — match the
    # common token, not just "NEVER approached" (that hole passed a 3/4 CP-08 partial as GOLD, cont.108).
    never = len(re.findall(r"never-gripped", text, re.I))
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
    zmatch = re.search(r"STACK STRUCTURE \([^)]*\): (\d+) z-level", text)
    zlevels = int(zmatch.group(1)) if zmatch else None
    # min-pair-xy (closest cube-pair in the plane) — distinguishes a SPREAD grid (gaps, gripper clearance)
    # from a CLUSTERED/PILED heap. A 2x2 grid palletizer must end FLAT (1 z-level) AND spread; a composed
    # CP-08 whose drop_targets dict didn't namespace/offset collapsed all cubes onto the pallet centre =
    # 2 z-levels + min-pair << cube-width = a PILE the lenient gate used to false-pass (cont.150).
    mpmatch = re.search(r"min-pair-xy=([\d.]+)m", text)
    minpair = float(mpmatch.group(1)) if mpmatch else None
    # ORIENTATION/TOPPLE (2026-06-16, Anton false-success): a cube delivered to the right XY/Z but resting on
    # its SIDE is not correctly placed. scene_eyes now emits a settled-tilt ORIENTATION block; a >60° topple is
    # a hard reject (mirrors the Modal `vec` TOPPLED that the position gate is blind to — CP-09 lesson). TILTED
    # (30-60°) is a soft warning only — NOT a reject (avoids false-negatives per Anton's no-graze principle).
    toppled = re.search(r"\*\*\* ORIENTATION FAIL: \d+ object\(s\) TOPPLED[^:]*: ([^*]+?) \*\*\*", text)
    if never:
        return False, f"{never} cube(s) NEVER approached (not transported/grasped)"
    if gripped == 0 and zlevels is None:
        return False, "no CONVERGED+GRIPPED and no structure data (likely no grasp / no rows)"
    if real_explosion:
        return False, "real EJECTION/EXPLOSION detected"
    if toppled:
        return False, f"object(s) TOPPLED — delivered but tipped >60° from upright (not correctly placed): {toppled.group(1).strip()}"
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
        return True, f"column verified ({zlevels} z-levels, {gripped} gripped)"
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
    # bin/place/sort: transport+grasp is enough, no structure requirement
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
        ok, reason = verdict_for_instance(text, cls)
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
