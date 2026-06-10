"""task_outcome — the WHY-classifier behind ``diagnose_task_outcome`` [P2-06].

Productizes the validated prototype (``scripts/qa/why_classify.py``,
EXPANSION_DIRECTION_PLAN §9): reads a saved ``ts_<template>.json`` time-series
artifact (written by ``scripts/qa/scene_timeseries.py``) and derives, per
object, a task-level WHY **purely from raw data** (positions/contacts over
time) — never from the controller's self-report (the honest-eyes contract:
controllers and gates have a documented false-positive history; raw motion
does not lie).

WHY taxonomy (§9, refined on real batch data):
- ``NOT_PICKED``               robot never engaged (sensor-gate / reach)
- ``RODE_OFF_BELT``            conveyor-sync miss: crossed the belt exit unpicked
- ``DISPLACED_NOT_DELIVERED``  left its source unpicked but NOT past a belt exit
                               (knocked off a dispenser, pushed aside)
- ``FLUNG_TO_FLOOR``           picked, ended on the floor outside any dest
- ``DELIVERED_CLEAN``          picked, in dest footprint, upright (<30 deg tilt)
- ``TOPPLED_IN_DEST``          delivered but fell over (>=30 deg)
- ``DROP_IMPRECISE_OR_EJECT``  picked, ended outside every dest footprint
- ``UNCLASSIFIED``             none of the above (flag for review)

Two deliberate deltas from the prototype (driven by live CP-71 validation —
the dispenser family broke both prototype assumptions):
1. ``picked`` = z RISES >=10 cm above the RUNNING MINIMUM, not above the
   start height. Dispenser items start HIGH and fall before the pick; the
   prototype read their whole delivery as "never picked".
2. The unpicked-but-moved bucket is split: RODE_OFF_BELT only when the item
   actually crossed a belt exit; otherwise DISPLACED_NOT_DELIVERED.

MISROUTED (right bin class, wrong bin) is NOT graded here yet — it needs the
template's routing map, which the artifact does not carry; the full routing
grade lives in scene_timeseries' ``_report``. Recorded as a known gap.

No Kit imports. Pure Python over the artifact; unit-testable.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

#: scene_timeseries' artifact directory (its TS_OUTDIR default).
DEFAULT_OUTDIR = "/home/anton/.isaac_qa/run"

WHY_TAXONOMY = (
    "NOT_PICKED", "RODE_OFF_BELT", "DISPLACED_NOT_DELIVERED",
    "FLUNG_TO_FLOOR", "DELIVERED_CLEAN", "TOPPLED_IN_DEST",
    "DROP_IMPRECISE_OR_EJECT", "UNCLASSIFIED",
)

_BAD_WHYS = {"NOT_PICKED", "RODE_OFF_BELT", "DISPLACED_NOT_DELIVERED",
             "FLUNG_TO_FLOOR", "DROP_IMPRECISE_OR_EJECT", "TOPPLED_IN_DEST"}


def _xyz(v) -> List[float]:
    if isinstance(v, dict):
        v = [v.get("x", 0), v.get("y", 0), v.get("z", 0)]
    v = list(v) if v else [0, 0, 0]
    return (v + [0, 0, 0])[:3]


def _dist3(a, b) -> float:
    a, b = _xyz(a), _xyz(b)
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def classify_timeseries(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Classify every tracked object in a loaded ``ts_*.json`` dict.

    Returns ``{objects: {name: {why, evidence:{...}}}, counts, all_clean}``.
    Mirrors the validated prototype's thresholds exactly (picked = +10 cm
    lift, moved = 10 cm, floor = -15 cm vs start, dest margin 3 cm,
    topple = 30 deg).
    """
    rows = raw.get("rows") or []
    meta = raw.get("meta", {}) or {}
    init = meta.get("init", {}) or {}

    belt_x = []
    for b in (meta.get("belt_bbox") or {}).values():
        if b:
            belt_x.append((b[0][0], b[1][0]))
    belt_max = max((x1 for _, x1 in belt_x), default=None)

    dests = []
    for p, b in (meta.get("dest_bbox") or {}).items():
        if b:
            dests.append((p.split("/")[-1], b[0][0], b[0][1], b[1][0], b[1][1]))

    names = sorted({n for r in rows for n in r.get("items", {})})
    objects: Dict[str, Any] = {}
    counts: Dict[str, int] = {}
    for nm in names:
        seq = [(r["t"], r["items"][nm]["p"], r["items"][nm].get("up"))
               for r in rows
               if r["items"].get(nm) and r["items"][nm].get("p")]
        if not seq:
            continue
        ip = _xyz(init.get(nm) or seq[0][1])
        fp = _xyz(seq[-1][1])
        fup = seq[-1][2]
        z0 = ip[2]
        # picked = z rises >=10 cm above the RUNNING minimum (not the start
        # height): dispenser items fall BEFORE the pick, so start-relative
        # lift misses their whole delivery (live CP-71 lesson).
        picked = False
        run_min = z0
        max_rise = 0.0
        for _, p, _ in seq:
            z = p[2]
            run_min = min(run_min, z)
            max_rise = max(max_rise, z - run_min)
            if max_rise > 0.10:
                picked = True
        moved = _dist3(fp, ip) > 0.10
        past_exit = belt_max is not None and fp[0] > belt_max + 0.05
        tilt = (math.degrees(math.acos(max(-1.0, min(1.0, fup))))
                if fup is not None else 0.0)
        in_dest = any(b0x - 0.03 <= fp[0] <= b1x + 0.03
                      and b0y - 0.03 <= fp[1] <= b1y + 0.03
                      for _, b0x, b0y, b1x, b1y in dests)
        on_floor = fp[2] < z0 - 0.15

        # Final position in a dest footprint DOMINATES pick detection: the
        # UR10 cup-frame carries LOW (live CP-71: rises 0.084-0.130 m for
        # the same motion), so picked must never gate a delivery verdict —
        # an in-bin item is delivered no matter how it looked getting there.
        # ``picked`` stays in evidence for the reader.
        if in_dest and tilt < 30:
            why = "DELIVERED_CLEAN"
        elif in_dest:
            why = "TOPPLED_IN_DEST"
        elif not picked and not moved:
            why = "NOT_PICKED"
        elif not picked and past_exit:
            why = "RODE_OFF_BELT"
        elif not picked and moved:
            why = "DISPLACED_NOT_DELIVERED"
        elif picked and on_floor:
            why = "FLUNG_TO_FLOOR"
        elif picked:
            why = "DROP_IMPRECISE_OR_EJECT"
        else:
            why = "UNCLASSIFIED"

        objects[nm] = {
            "why": why,
            "evidence": {
                "picked": picked, "moved": moved, "in_dest": in_dest,
                "past_belt_exit": past_exit, "on_floor": on_floor,
                "tilt_deg": round(tilt, 1),
                "final": [round(v, 3) for v in fp],
                "max_rise_m": round(max_rise, 3),
                "samples": len(seq),
            },
        }
        counts[why] = counts.get(why, 0) + 1

    return {
        "objects": objects,
        "counts": counts,
        "all_clean": bool(objects) and not any(
            o["why"] in _BAD_WHYS or o["why"] == "UNCLASSIFIED"
            for o in objects.values()),
    }


def find_artifact(template: str, outdir: Optional[str] = None) -> Optional[Path]:
    """Locate ``ts_<template>.json`` in the scene_timeseries output dir."""
    base = Path(outdir or os.environ.get("TS_OUTDIR", DEFAULT_OUTDIR))
    p = base / f"ts_{template}.json"
    return p if p.exists() else None


def diagnose(template: Optional[str] = None,
             artifact_path: Optional[str] = None,
             outdir: Optional[str] = None) -> Dict[str, Any]:
    """The full diagnose flow: locate artifact -> classify -> typed result.

    Honesty contract: a missing artifact is a TYPED error telling the caller
    to produce one (run scene_timeseries) — never a silent empty pass. The
    artifact's age rides the result so a stale read is visible.
    """
    if artifact_path:
        p = Path(artifact_path)
        if not p.exists():
            return {"type": "error",
                    "error": f"artifact not found: {artifact_path}"}
    elif template:
        p = find_artifact(template, outdir)
        if p is None:
            base = outdir or os.environ.get("TS_OUTDIR", DEFAULT_OUTDIR)
            return {"type": "error",
                    "error": (f"no time-series artifact for {template!r} "
                              f"(looked for ts_{template}.json in {base}). "
                              "Run scripts/qa/scene_timeseries.py "
                              f"{template} first — this tool reads recorded "
                              "raw motion, it does not re-simulate.")}
    else:
        return {"type": "error",
                "error": "diagnose_task_outcome: pass template or artifact_path"}

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"type": "error",
                "error": f"unreadable artifact {p}: {type(exc).__name__}: {exc}"}

    result = classify_timeseries(raw)
    age_s = None
    try:
        age_s = round(datetime.now(timezone.utc).timestamp() - p.stat().st_mtime, 1)
    except OSError:
        pass
    return {
        "type": "data",
        "template": raw.get("template") or template,
        "artifact": str(p),
        "artifact_age_s": age_s,
        "provenance": raw.get("provenance"),
        "taxonomy": list(WHY_TAXONOMY),
        "known_gaps": ["MISROUTED (class->required-bin) not graded here; "
                       "see scene_timeseries _report for routing grade"],
        **result,
    }
