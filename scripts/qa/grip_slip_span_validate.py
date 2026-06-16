#!/usr/bin/env python3
"""Prototype + multi-case validator for the #39 GRIP-SLIP span fix (cont.148).

OLD scene_eyes: slip-span = [first..last finger-contact]; for a STACKER the EE re-contacts the placed base
cube when stacking the next -> span over-extends past release -> qrel drifts from EE motion vs a world-fixed
placed cube -> false SLIPPING. NEW: bound the slip window to the LIFTED carry (cube z > z_min+0.05 = off its
rest surface) so only the genuine in-air grasp is measured. Validates against saved eyes.json: stackers should
flip false-SLIPPING->RIGID; non-stackers must NOT regress (stay RIGID); a REAL carry-slip must still show.
"""
import json, math, glob, os

def rel_q(tq, cq):
    w0, x0, y0, z0 = tq; cw, cx, cy, cz = w0, -x0, -y0, -z0; w1, x1, y1, z1 = cq
    return [cw*w1-cx*x1-cy*y1-cz*z1, cw*x1+cx*w1+cy*z1-cz*y1, cw*y1-cx*z1+cy*w1+cz*x1, cw*z1+cx*y1-cy*x1+cz*w1]

def qang(a, b):
    dd = abs(sum(p*q for p, q in zip(a, b))); dd = max(-1.0, min(1.0, dd)); return math.degrees(2*math.acos(dd))

def verdict(mx):
    return "RIGID HOLD" if mx < 15 else "SLIPPING" if mx > 30 else "marginal"

def new_slip(rows, name, dthr=0.15):
    """NEW metric: max qrel-drift over the GRIPPED-CARRY window = frames where the cube is within grasp-distance
    of the tool (dist(tool_p,cube_p) < dthr ~ the ~104mm grasp offset + margin). UNIQUE carry signature for BOTH
    stacker AND bin: before pick the tool is far (cube on belt); after release the tool moves away; only during
    the genuine carry is the cube locked ~104mm from the tool. Excludes belt-transport (moving-but-not-gripped,
    which broke the 'moving' window) AND placed-in-elevated-bin (high-but-stationary, which broke the lifted-z
    window). This is the same rigidly-held signature used for the airborne-carry proof (dist locked 103.9mm)."""
    win = []
    for r in rows:
        cp = (r.get("cubes") or {}).get(name); cq = (r.get("cubes_q") or {}).get(name)
        tp = r.get("tool_p"); tq = r.get("tool_q")
        if not (cp and cq and tp and tq and cp[2] is not None): continue
        if math.dist(tp, cp) < dthr:
            win.append((tq, cq))
    if len(win) < 3: return None
    q0 = None; mx = 0.0
    for tq, cq in win:
        qr = rel_q(tq, cq)
        if q0 is None: q0 = qr; continue
        mx = max(mx, qang(qr, q0))
    return mx

def old_slip_full(rows, name):
    """OLD-ish: max qrel-drift over the FULL tracked span (proxy for the over-extended finger-contact span)."""
    q0 = None; mx = 0.0
    for r in rows:
        tq = r.get("tool_q"); cq = (r.get("cubes_q") or {}).get(name)
        if not (tq and cq): continue
        qr = rel_q(tq, cq)
        if q0 is None: q0 = qr; continue
        mx = max(mx, qang(qr, q0))
    return mx

STACKERS = ("CP-13",)

def main():
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "/home/anton/.isaac_qa/run/eyes"
    files = sorted(glob.glob(os.path.join(base, "*", "eyes.json")))
    print("GRIP-SLIP span validator — OLD(full-span) vs NEW(gripped-carry dist<0.15m) per cube")
    print("%-42s %-10s | per-cube  OLD->NEW" % ("eyes.json (last instance)", "robot"))
    regress = 0
    for f in files:
        try: d = json.load(open(f))
        except Exception: continue
        rows = d.get("rows", [])
        cubes = sorted({k for r in rows for k in (r.get("cubes_q") or {})})
        cells = []
        for c in cubes:
            o = old_slip_full(rows, c); n = new_slip(rows, c)
            if o is None or n is None: continue
            flag = ""
            if o > 30 and n < 15: flag = " FIXED"
            elif o < 15 and n > 30: flag = " <== REGRESSION!"; regress += 1
            cells.append("%s %3.0f->%2.0f°[%s]%s" % (c, o, n, verdict(n), flag))
        if cells:
            name = os.path.basename(os.path.dirname(f))
            print("%-42s %-10s | %s" % (name[:42], (d.get("robot","?").split("/")[-1])[:10], "  ".join(cells)))
    print("REGRESSIONS:", regress, "(>0 = the distance window broke a previously-RIGID cube)")
    return 1 if regress else 0

if __name__ == "__main__":
    import sys; sys.exit(main())
