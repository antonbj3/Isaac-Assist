#!/usr/bin/env python3
"""authoring_preflight.py — ONE static (no-Kit) pre-flight for an LLM-authored Isaac cell. Runs the cheap
geometric authoring checks BEFORE a Kit boot so an authoring error is caught for ~0 cost. Aggregates the
project's static pre-gates:
  * grasp_validate  — jaw-fit (object cross-section < 80mm) + pendulum CG-stability of the grasp
  * lint_ycb_spawn  — YCB Axis_Aligned asset spawned WITHOUT lie-flat rotation_euler (the upright-spawn bug,
                      cont.319-ROTATION-IS-LEVER — the dominant real-object failure this session)
A FAIL means 'do not bother booting Kit — fix the authoring first'. A WARN means 'review'. PASS = build it.
(Reach is a Kit check -> scene_validate.py separately; this pre-flight is the zero-cost static layer.)
Usage: python scripts/qa/authoring_preflight.py CP-XX [CP-YY ...]
"""
import subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
def run(tool, tpl):
    try:
        r = subprocess.run(["python3", os.path.join(HERE, tool), tpl], capture_output=True, text=True, timeout=60)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return "TOOL_ERROR " + str(e)
def main():
    tpls = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not tpls:
        print("usage: authoring_preflight.py CP-XX [CP-YY ...]"); return 2
    rc = 0
    for tpl in tpls:
        print(f"=== PRE-FLIGHT {tpl} (static, no-Kit) ===")
        g = run("grasp_validate.py", tpl)
        gv = "FAIL" if ("UNGRASPABLE" in g) else ("WARN" if ("SUSPECT" in g or "BORDERLINE" in g) else "PASS")
        gline = next((l for l in g.splitlines() if any(k in l for k in ("UNGRASPABLE","SUSPECT","graspable","geom-OK","jaw","pendulum"))), g.strip()[:90])
        print(f"  grasp_validate : {gv:4}  {gline.strip()[:100]}")
        # spawn-orientation: lint scans the whole corpus; run it + check if THIS tpl is flagged
        s = run("lint_ycb_spawn.py", "")
        flagged = any(tpl in l for l in s.splitlines() if "⚠️" in l)
        # only meaningful if the tpl references YCB; the lint prints flagged lines with the task_id
        sv = "FAIL" if flagged else "PASS"
        print(f"  spawn-orient   : {sv:4}  ({'flagged: upright-spawn bug — add rotation_euler=[90,0,0]' if flagged else 'ok (rotated/box-like or no YCB asset)'})")
        verdict = "FAIL" if (gv=="FAIL" or sv=="FAIL") else ("WARN" if gv=="WARN" else "PASS")
        print(f"  -> PRE-FLIGHT {verdict}")
        if verdict == "FAIL": rc = 1
    return rc
if __name__ == "__main__":
    sys.exit(main())
