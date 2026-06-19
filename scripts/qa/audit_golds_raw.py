#!/usr/bin/env python3
"""audit_golds_raw.py — systematic Kit-FREE adversarial RAW-audit of every GENUINE gold in the
composable catalog (cont.319hh, the false-success-vakt as a first-class detector).

WHY: a gate PASS is not proof. CP-10 was recorded GENUINE(grid n=9) from a lucky run while its
saved RAW showed 8/9 + an off-pallet outlier (2 z-levels) -- a stale-lucky FALSE GOLD the
delivered-count never sees. This sweeps EVERY genuine gold's saved eyes.json and re-derives the
structural signals the gate trusts (z-levels, xy-extent, floor-z, settle-drift), then checks each
against its class. Any mismatch = the saved RAW contradicts the GENUINE verdict = a false-success
to investigate. Re-run after any catalog/scene_eyes change as a regression gate.

It reuses the SAME thresholds as eyes_gold_gate / scene_eyes:
  - floor: a cube settled below 0.6m = fell / never placed.
  - stack/column: must be >=2 z-levels AND xy-aligned (max-extent <= 0.06m, #48 calibration).
  - palletize/grid: must be FLAT (1 z-level). Extent is NOT bounded -- a legit twin-pallet feeder
    (CP-19) spans ~0.84m, so a global extent bound false-refuses multi-pallet layouts (cont.319hh).
  - settle: a cube still drifting >30mm in the last 8 frames = not settled (being carried/dragged).

Exit 0 = all audited golds RAW-consistent; exit 1 = at least one flagged (a candidate false-success).

⚠️ LIMITATION (cont.319hh): this audits the SAVED run's structure -- it catches a structurally-bad
saved run, but CANNOT detect STOCHASTICITY. A flaky block whose saved eyes.json happens to be a LUCKY
clean run passes here even though it fails most runs. Proven: CP-09 (FALSE, top cube topples) has a
saved RAW that is a perfect 5-column; this tool would clear it. The complement is N-of-M re-verification
(re-run K times, require a clean structure every time) -- see _reverify_cp09.sh for the pattern. Use this
tool for the cheap saved-RAW pass; use N-of-M for blocks whose robustness (not just one run) is in doubt.
"""
import json, glob, sys, os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EYES_ROOT = os.path.expanduser("~/.isaac_qa/run/eyes")


def _signals(path):
    js = json.load(open(path))
    rows = js.get("rows") or []
    if not rows:
        return None
    cubes = rows[-1].get("cubes") or {}
    if not cubes:
        return {"n": 0}
    xs = [p[0] for p in cubes.values()]; ys = [p[1] for p in cubes.values()]; zs = [p[2] for p in cubes.values()]
    zl = []
    for z in sorted(zs):
        if not zl or abs(z - zl[-1]) > 0.03:
            zl.append(z)
    drift = 0.0
    if len(rows) >= 8:
        c0 = rows[-8].get("cubes") or {}
        for nm, p in cubes.items():
            p0 = c0.get(nm)
            if p0:
                drift = max(drift, sum((p[i] - p0[i]) ** 2 for i in range(3)) ** 0.5)
    return {"n": len(cubes), "zlev": len(zl),
            "ext": round(max(max(xs) - min(xs), max(ys) - min(ys)), 3),
            "minz": round(min(zs), 3), "drift_mm": round(drift * 1000),
            "zs": [round(z, 3) for z in zl]}


def _find_eyes(cid):
    for pat in (f"{EYES_ROOT}/{cid}/eyes.json",
                f"{EYES_ROOT}/*{cid}_*/eyes.json",
                f"{EYES_ROOT}/*_{cid}/eyes.json"):
        hit = glob.glob(pat)
        if hit:
            return hit[0]
    return None


def _issue(cls, s):
    if s["minz"] < 0.6:
        return f"a cube at z={s['minz']} (<0.6m = fell to floor / never placed)"
    if "stack" in cls or "column" in cls:
        if s["zlev"] < 2:
            return f"stack but {s['zlev']} z-level = FLAT SCATTER, not a column"
        if s["ext"] > 0.06:
            return f"stack but xy-extent {s['ext']}m (>0.06) = cubes not vertically aligned"
    elif "grid" in cls or "pallet" in cls:
        if s["zlev"] >= 2:
            return f"grid but {s['zlev']} z-levels = PILE/STACK, not a flat grid"
    if s["drift_mm"] > 30:
        return f"still drifting {s['drift_mm']}mm in the last 8 frames = not settled (carried/dragged)"
    return None


def main():
    cat = json.load(open(f"{REPO}/workspace/composable_blocks.json"))["all"]
    audited = cleared = 0
    flags = []
    no_raw = []
    for cid, info in cat.items():
        if "genuine" not in str(info.get("verdict", "")).lower():
            continue
        f = _find_eyes(cid)
        if not f:
            no_raw.append(cid); continue
        try:
            s = _signals(f)
        except Exception as e:
            no_raw.append(f"{cid}(read-err)"); continue
        if not s or s.get("n", 0) == 0:
            no_raw.append(f"{cid}(no-cubes)"); continue
        audited += 1
        iss = _issue(str(info.get("class", "")).lower(), s)
        if iss:
            flags.append((cid, info.get("class"), s, iss))
        else:
            cleared += 1
    print(f"=== adversarial RAW-audit of GENUINE golds (Kit-free) ===")
    print(f"audited {audited} (saved RAW) | {cleared} CLEARED | {len(flags)} FLAGGED | {len(no_raw)} no-RAW (skipped)")
    for cid, cls, s, iss in flags:
        print(f"⚠ {cid} ({cls}): {iss}\n    {s}")
    if no_raw:
        print(f"no saved RAW for: {', '.join(no_raw[:30])}" + (" ..." if len(no_raw) > 30 else ""))
    if not flags:
        print("ALL audited golds RAW-consistent with their verdict (no false-success found).")
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
