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
    never = len(re.findall(r"NEVER approached", text))
    gripped = len(re.findall(r"(?<!never-)CONVERGED \+ GRIPPED", text))
    real_explosion = "*** EXPLODED/EJECTED ***" in text   # offset-invariant in current scene_eyes
    zmatch = re.search(r"STACK STRUCTURE \([^)]*\): (\d+) z-level", text)
    zlevels = int(zmatch.group(1)) if zmatch else None
    if never:
        return False, f"{never} cube(s) NEVER approached (not transported/grasped)"
    if gripped == 0 and zlevels is None:
        return False, "no CONVERGED+GRIPPED and no structure data (likely no grasp / no rows)"
    if real_explosion:
        return False, "real EJECTION/EXPLOSION detected"
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
        return True, f"grid verified ({gripped} gripped, {zlevels} z-level — flat grid is correct)"
    # bin/place/sort: transport+grasp is enough, no structure requirement
    return True, f"delivery verified ({gripped} gripped)"


def main():
    pairs = [a.split(":", 1) for a in sys.argv[1:] if ":" in a]
    if not pairs:
        print("usage: eyes_gold_gate.py CP-01:inst0.txt CP-09:inst1.txt ..."); return 2
    all_ok = True
    for tpl, path in pairs:
        cls = _class(tpl)
        text = open(path).read() if os.path.exists(path) else ""
        ok, reason = verdict_for_instance(text, cls)
        all_ok = all_ok and ok
        print(f"  {tpl:12s} [{cls:16s}] {'GENUINE' if ok else 'REJECT '} — {reason}")
    print("EYES_GOLD_VERDICT:", "GOLD (all cells scene_eyes-genuine)" if all_ok else "NOT GOLD (a cell failed scene_eyes)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
