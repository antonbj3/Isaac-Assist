#!/usr/bin/env python3
"""untracked_finder.py — surface templates that are NOT in the composable catalog ('all' map) but look
GENUINE-quality, so a systematic scene_eyes sweep can verify + add them. The catalog is an UNDER-COUNT.

WHY (cont.319jj-18/19): the catalog 'all' map tracks ~80 of the 476 templates on disk (16%). Many untracked
templates are already self-RAW-verified GENUINE (CP-CONV-01/01b, CP-YCB-03, CP-KLT-BIN) -- never added -- and
others are gate-OK and just never scene_eyes-confirmed (CP-48 was, this turn, -> GENUINE). Hand-triaging this
each time is the gap; this ranks the untracked corpus so the next sweep goes straight to the high-value adds.

Ranking signals per untracked template (printed tier-sorted):
  TIER-1 SELF-GENUINE : verified_status starts with/contains 'GENUINE' AND a saved eyes.json exists
                        -> add Kit-FREE (carry its RAW) + run audit_golds_raw to drop any drift/false-success.
  TIER-2 GATE-OK      : status shows a passing function-gate / N/N fresh-Kit AND has delivery cubes
                        -> scene_eyes-verify (one run) then add if clean (CP-48 path).
  TIER-3 HAS-CUBES    : has delivery cubes but no clear pass marker -> diagnostik-forst (status may lie either way).
  SKIP                : 0 delivery cubes (drawer/SDG/nav/actuation -- different class), or fail/broken status,
                        or a CHAIN-*/-SRC/-RECV variant (chain-infra, tracked separately, not standalone 'all').
"""
import json, os, re, glob

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EYES = os.path.expanduser("~/.isaac_qa/run/eyes")


def main():
    cat = set(json.load(open(f"{REPO}/workspace/composable_blocks.json"))["all"].keys())
    tiers = {1: [], 2: [], 3: []}
    skipped = {"no-cubes": 0, "fail": 0, "chain-infra": 0}
    for f in glob.glob(f"{REPO}/workspace/templates/*.json"):
        cid = os.path.basename(f)[:-5]
        if cid in cat:
            continue
        try:
            t = json.load(open(f))
        except Exception:
            continue
        st = str(t.get("verified_status", ""))
        stl = st.lower()
        ncubes = len((t.get("simulate_args") or {}).get("cube_paths", []))
        has_raw = os.path.exists(f"{EYES}/{cid}/eyes.json")
        if re.search(r"-src$|-recv|chain", cid.lower()):
            skipped["chain-infra"] += 1; continue
        if re.search(r"\bfail\b|stable_fail|broken|build.*fail|likely fai", stl[:60]):
            skipped["fail"] += 1; continue
        if ncubes == 0:
            skipped["no-cubes"] += 1; continue
        if stl.strip().startswith("genuine") and has_raw:
            tiers[1].append((cid, ncubes, st[:55]))
        elif re.search(r"function-gate ok|gate ok|\d/\d.*fresh|smoke-test ✓|5/5|4/4|6/6|verified.*pass", stl):
            tiers[2].append((cid, ncubes, st[:55]))
        else:
            tiers[3].append((cid, ncubes, st[:55]))
    names = {1: "SELF-GENUINE (add Kit-free + audit-grind)", 2: "GATE-OK (scene_eyes-verify then add)",
             3: "HAS-CUBES (diagnostik-forst)"}
    print("=== untracked GENUINE-candidate templates (cont.319jj tool) ===")
    for tier in (1, 2, 3):
        print(f"\n--- TIER-{tier} {names[tier]}: {len(tiers[tier])} ---")
        for cid, n, st in sorted(tiers[tier]):
            print(f"  {cid:42} cubes={n:<2} | {st}")
    print(f"\nSKIPPED: {skipped['no-cubes']} no-cubes (non-delivery class), {skipped['fail']} fail/broken, "
          f"{skipped['chain-infra']} chain-infra (-SRC/-RECV, tracked separately).")
    print(f"TOTAL untracked-candidates worth a sweep: {sum(len(v) for v in tiers.values())}")


if __name__ == "__main__":
    main()
