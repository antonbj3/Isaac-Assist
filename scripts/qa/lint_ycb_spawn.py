#!/usr/bin/env python3
"""lint_ycb_spawn.py — flag templates that reference a YCB Axis_Aligned asset but spawn it WITHOUT a
lie-flat rotation. cont.319-ROTATION-IS-LEVER proved the dominant real-object failure is SPAWN ORIENTATION:
a YCB Axis_Aligned asset (authored upright) spawned without rotation_euler=[90,0,0] is unstable on a belt
-> tips/rolls -> bad grasp + explosion (REFUTED-GRASP/REFUTED-EXPLODE were all this confound). Fix: spawn
with rotation_euler=[90,0,0] so it settles on a stable face. This lint catches the upright-spawn bug at
authoring time (static, no Kit). Box objects (foam_brick, gelatin) authored flat may be fine without it ->
this is a WARN (review), not a hard fail. Usage: python scripts/qa/lint_ycb_spawn.py
"""
import json, re, glob, os
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/qa/X.py -> repo root
flagged = []; ok = []
for f in sorted(glob.glob(f"{REPO}/workspace/templates/*.json")):
    try: d = json.load(open(f))
    except Exception: continue
    code = (d.get("code") or "") + "\n" + (d.get("code_template") or "")
    if "YCB/Axis_Aligned" not in code: continue
    # find each Item/workpiece prim that references a YCB Axis_Aligned asset + its create_prim line
    refs = re.findall(r'add_reference\(prim_path=["\']([^"\']+)["\'][^)]*YCB/Axis_Aligned/0?(\d+)_([a-z_]+)\.usd', code)
    for prim, num, name in refs:
        # does the create_prim for this prim have rotation_euler?
        cp = re.search(r'create_prim\(prim_path=["\']' + re.escape(prim) + r'["\'][^)]*\)', code)
        has_rot = bool(cp and "rotation_euler" in cp.group(0))
        box_like = name in ("foam_brick", "gelatin_box", "sugar_box", "pudding_box", "cracker_box", "wood_block")
        rec = (d["task_id"], prim, name, has_rot, box_like, (d.get("verified_status","")[:18]))
        if has_rot or box_like: ok.append(rec)
        else: flagged.append(rec)
print("=== YCB Axis_Aligned spawn lint ===")
print("FLAGGED (non-box YCB asset spawned WITHOUT lie-flat rotation_euler -> upright-spawn-bug risk):")
for t,p,n,_,_,st in flagged: print("  ⚠️ %-22s %s = %s  [%s]" % (t, p, n, st))
if not flagged: print("  (none)")
print("OK (%d: has rotation_euler or box-like-authored-flat)" % len(ok))
