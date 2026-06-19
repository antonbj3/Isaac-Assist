#!/usr/bin/env python3
"""stale_partial_finder.py — surface PARTIAL/FALSE catalog blocks that are likely STALE (a measurement
artifact, not a real failure), so a cheap re-verify can re-class them to GENUINE.

WHY (cont.319jj): the catalog's PARTIAL verdicts LIE in BOTH directions. This turn, hand-checking found:
  - CP-31 PARTIAL('Cube_1 thrash-no-converge') was a PRE-FIX run (template: 're-verify pending — rest_speed
    standardised'); scene_eyes N-of-3 -> 3/3 -> re-classed GENUINE.
  - CP-34 PARTIAL('stochastic blue place') was a WINDOW-CUT: the catalog basis was @ dur=90 but the template
    runs dur=180; a late-placed cube hadn't settled. At the proper dur -> 3/3 deterministic -> GENUINE.
Deriving this by hand each time is the gap. This detector flags the two stale signatures so future sweeps
go straight to the cheap re-class wins instead of pre-judging every PARTIAL as 'genuinely hard'.

Signatures flagged (a candidate has at least one):
  (1) WINDOW-CUT: the catalog basis was measured at a dur SHORTER than the template's simulate_args dur
      (the verdict may be a not-yet-settled / not-all-placed artifact -> re-verify at the template dur).
  (2) STALE-PRE-FIX: the template verified_status contains 're-verify pending' / 'pre-fix' (a fix landed
      after the PARTIAL verdict; never re-verified).

NOT a verdict — a TRIAGE list. Each candidate still needs scene_eyes N-of-M at the proper dur (the verdict
can be stale-PESSIMISTIC, as CP-31/CP-34, or genuinely real, as CP-20/CP-43; only RAW resolves it).
"""
import json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _basis_dur(basis):
    # the dur the catalog verdict was measured at, e.g. "scene_eyes cont.316 @ dur=70: ..."
    m = re.search(r"@\s*dur\s*=\s*(\d+)", basis or "")
    return int(m.group(1)) if m else None


def main():
    cat = json.load(open(f"{REPO}/workspace/composable_blocks.json"))["all"]
    cands = []
    for cid, info in cat.items():
        verdict = str(info.get("verdict", "")).lower()
        if "genuine" in verdict:
            continue  # only re-examine PARTIAL/FALSE
        basis = info.get("basis", "")
        bdur = _basis_dur(basis)
        tpl_path = f"{REPO}/workspace/templates/{cid}.json"
        tdur = None
        status = ""
        if os.path.exists(tpl_path):
            t = json.load(open(tpl_path))
            tdur = (t.get("simulate_args") or {}).get("duration_s")
            status = str(t.get("verified_status", ""))
        sigs = []
        if bdur is not None and tdur is not None and bdur < tdur:
            sigs.append(f"WINDOW-CUT(basis@{bdur}s < template@{tdur}s)")
        if re.search(r"re-verify pending|pre-fix", status, re.I):
            sigs.append("STALE-PRE-FIX(status)")
        if sigs:
            cands.append((cid, info.get("verdict", "")[:48], sigs, tdur))
    print("=== stale-PARTIAL re-verify candidates (cont.319jj tool) ===")
    if not cands:
        print("none — all PARTIAL/FALSE blocks were verified at the template dur with no stale-fix marker.")
    for cid, vd, sigs, tdur in sorted(cands):
        print(f"  {cid:8} [{vd}]")
        print(f"           -> {', '.join(sigs)}  | re-verify: scene_eyes {cid} {tdur} --noframes (N-of-M)")
    print(f"\n{len(cands)} candidate(s). NOTE: a candidate may still be genuinely PARTIAL — RAW N-of-M decides "
          f"(CP-31/CP-34 were stale-PESSIMISTIC -> GENUINE; others stay PARTIAL).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
