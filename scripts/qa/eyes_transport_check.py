#!/usr/bin/env python3
"""eyes_transport_check.py — the GOLD GATE the position-measure should have been (Anton 2026-06-15:
"var vaksam på false success" / "har du glömt scene eyes och validator igen?").

A composition's delivered-count via end-position-in-bbox LIES: a cube can read "delivered" if it
SPAWNED in the zone (zero transport), got SWEPT/knocked in (no grasp), or EXPLODED and settled in-bbox.
This reads the RAW per-cube trajectory from scene_eyes eyes.json (rows[i]["cubes"] = {path:[x,y,z]}),
NOT a summary metric, and classifies each cube's motion:

  GENUINE            lifted clear of start (max_lift > LIFT) AND moved far (displacement > DISP) -> a
                     real pick-place/stack arc.
  SPAWN_IN_ZONE      displacement < STILL -> never transported (false-success if counted delivered).
  SLID_INCIDENTAL    moved far but never lifted (max_lift < FLAT) -> swept/pushed, not grasped (suspect).
  EXPLODED           any z < -1 (sub-floor) -> PhysX blow-up; a settled fragment in-bbox is false-success.

Usage: eyes_transport_check.py <eyes.json> [<eyes.json> ...]   (one per instance/focus)
Verdict GENUINE for ALL tracked cubes => the position measure was honest for that instance.
"""
import json, sys, math

LIFT = float(__import__("os").environ.get("LIFT_MIN", "0.06"))   # m above start to count as a real lift
DISP = float(__import__("os").environ.get("DISP_MIN", "0.20"))   # m start->end to count as transported
STILL = 0.05                                                       # m: below this = didn't move (spawn-in-zone)
FLAT = 0.03                                                        # m: below this lift = never picked up


def _series(rows, name):
    return [r["cubes"][name] for r in rows if (r.get("cubes") or {}).get(name)]


def classify(pts):
    if not pts:
        return "NO_DATA", {}
    p0, pN = pts[0], pts[-1]
    disp = math.dist(p0, pN)
    z0 = p0[2]
    max_z = max(p[2] for p in pts)
    min_z = min(p[2] for p in pts)
    lift = max_z - z0
    path = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    m = {"start": [round(x, 3) for x in p0], "end": [round(x, 3) for x in pN],
         "disp": round(disp, 3), "max_lift": round(lift, 3), "path_len": round(path, 3),
         "min_z": round(min_z, 3), "n_obs": len(pts)}
    if min_z < -1.0 or pN[2] < -1.0:
        return "EXPLODED", m
    if disp < STILL:
        return "SPAWN_IN_ZONE", m
    if lift < FLAT:
        return "SLID_INCIDENTAL", m
    if lift >= LIFT and disp >= DISP:
        return "GENUINE", m
    return "WEAK", m   # moved + small lift but below GENUINE thresholds — inspect


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    overall = True
    for path in paths:
        try:
            data = json.load(open(path))
        except Exception as e:
            print(f"[{path}] LOAD_FAIL {e}"); overall = False; continue
        rows = data.get("rows") or []
        names = sorted({n for r in rows for n in (r.get("cubes") or {}).keys()})
        print(f"\n[{path}] robot={data.get('robot')} nrows={len(rows)} cubes={len(names)}")
        if not names:
            print("   NO CUBES TRACKED (focus scoping? wrong instance root?)"); overall = False; continue
        verdicts = {}
        for nm in names:
            v, m = classify(_series(rows, nm))
            verdicts[v] = verdicts.get(v, 0) + 1
            leaf = nm.split("/")[-1]
            flag = "" if v == "GENUINE" else "  <-- SUSPECT" if v in ("SPAWN_IN_ZONE", "SLID_INCIDENTAL", "EXPLODED") else "  <- check"
            print(f"   {leaf:14s} {v:15s} disp={m.get('disp')} lift={m.get('max_lift')} path={m.get('path_len')} start={m.get('start')} end={m.get('end')}{flag}")
        genuine = verdicts.get("GENUINE", 0)
        print(f"   => {genuine}/{len(names)} GENUINE | {dict(verdicts)}")
        if genuine != len(names):
            overall = False
    print("\nTRANSPORT_VERDICT:", "ALL_GENUINE" if overall else "FALSE_SUCCESS_SUSPECT")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
