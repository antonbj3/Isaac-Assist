#!/usr/bin/env python3
"""Prototype WHY-classifier for diagnose_task_outcome (EXPANSION_DIRECTION_PLAN §9).
Reads a saved ts_*.json (scene_timeseries time-series) and emits, per object, the task-level WHY
purely from RAW DATA (positions/contacts) — NOT the controller's self-report (honest-eyes contract).
Usage: python why_classify.py ts_CP-50.json [ts_CP-12.json ...]
Validation only — standalone, does not modify the production handler."""
import json, sys, math

def classify(path):
    d = json.load(open(path))
    rows = d.get("rows") or []; meta = d.get("meta", {}) or {}
    init = meta.get("init", {}) or {}
    def xyz(v):
        if isinstance(v, dict): v = [v.get("x", 0), v.get("y", 0), v.get("z", 0)]
        v = list(v) if v else [0, 0, 0]
        return (v + [0, 0, 0])[:3]
    def dist3(a, b):
        a, b = xyz(a), xyz(b)
        return sum((a[i]-b[i])**2 for i in range(3)) ** 0.5
    names = sorted({n for r in rows for n in r.get("items", {})})
    # belts: x-extent of any belt (past-exit = rode off)
    belt_x = []
    for b in (meta.get("belt_bbox") or {}).values():
        if b: belt_x.append((b[0][0], b[1][0]))
    belt_max = max((x1 for _, x1 in belt_x), default=None)
    # dests: footprints
    dests = []
    for p, b in (meta.get("dest_bbox") or {}).items():
        if b: dests.append((p.split("/")[-1], b[0][0], b[0][1], b[1][0], b[1][1]))
    out = []
    for nm in names:
        seq = [(r["t"], r["items"][nm]["p"], r["items"][nm].get("up")) for r in rows
               if r["items"].get(nm) and r["items"][nm].get("p")]
        if not seq: continue
        ip = xyz(init.get(nm) or seq[0][1]); fp = xyz(seq[-1][1]); fup = seq[-1][2]
        z0 = ip[2]; zmax = max(p[2] for _, p, _ in seq)
        picked = zmax > z0 + 0.10
        moved = dist3(fp, ip) > 0.10
        past_exit = belt_max is not None and fp[0] > belt_max + 0.05
        tilt = math.degrees(math.acos(max(-1, min(1, fup)))) if fup is not None else 0.0
        in_dest = any(b0x-0.03 <= fp[0] <= b1x+0.03 and b0y-0.03 <= fp[1] <= b1y+0.03
                      for _, b0x, b0y, b1x, b1y in dests)
        on_floor = fp[2] < z0 - 0.15
        # --- WHY taxonomy (§9) ---
        if not picked and not moved:
            why = "NOT_PICKED"          # robot never engaged (sensor-gate / reach)
        elif not picked and (past_exit or (moved and not in_dest)):
            why = "RODE_OFF_BELT"       # conveyor-sync: crossed sensor while robot busy
        elif picked and on_floor and not in_dest:
            why = "FLUNG_TO_FLOOR"
        elif picked and in_dest and tilt < 30:
            why = "DELIVERED_CLEAN"
        elif picked and in_dest and tilt >= 30:
            why = "TOPPLED_IN_DEST"
        elif picked and not in_dest:
            why = "DROP_IMPRECISE_OR_EJECT"
        else:
            why = "UNCLASSIFIED"
        out.append((nm, why, f"picked={picked} in_dest={in_dest} past_exit={past_exit} tilt={tilt:.0f} final=[{fp[0]:.2f},{fp[1]:.2f},{fp[2]:.2f}]"))
    return out

for path in sys.argv[1:]:
    print(f"\n=== {path} ===  (belt-aware, dest-aware WHY)")
    try:
        for nm, why, ev in classify(path): print(f"  {nm}: {why}   [{ev}]")
    except Exception as e:
        print(f"  ERROR: {e}")
