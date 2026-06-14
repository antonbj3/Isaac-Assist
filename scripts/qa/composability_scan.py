#!/usr/bin/env python3
"""composability_scan.py — classify the template library as COMPOSABLE building blocks.

Strategy context (2026-06-14, Anton's COMPOSITION reframe): templates should chain
(end-state -> next start-state), each robust template a MULTIPLIER. The composer
layer (canonical_instantiator seam) will start with ROLE-BASED + cuRobo +
function-gate-verified templates ("tier-0"). This scan measures, per template:

  - role_based?   has code_template + roles + role_defaults  (composer-tractable;
                  legacy code-only templates bake absolute /World/... -> need a
                  path-rewrite pass before they can be namespaced/composed)
  - target_source first setup_pick_place_controller backend (curobo = composition-ready;
                  sensor_gated/RmpFlow = fragile-to-start-state-drift, deprecate)
  - pass_state    best-effort from verified_status + motion_controllers.verified
  - primitive     heuristic op family (pick-place / sort / stack / inspect / merge / ...)
  - world_roots   distinct /World/<Root> prim subtrees authored (collision surface
                  for namespacing)

Output: a ranked tier table + the best pick / inspect / sort candidates for the
first composed scenario (pick->inspect->sort). Read-only, no Kit, deterministic.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

TPL_DIR = Path(__file__).resolve().parents[2] / "workspace" / "templates"

PASS_TOKENS = ("function-gate ✓", "function-gate: ✓", "gate ✓", "✓ function", "N/N", "PASS")
FAIL_TOKENS = ("function-gate ✗", "gate ✗", "FAIL", "✗")

PRIMITIVE_RULES = [
    ("sort", ("sort", "lane", "color-sort", "size-weight", "by-color", "3lane")),
    ("inspect", ("inspect", "reject", "qc", "quality", "vision-check", "scan", "barcode")),
    ("merge", ("merge", "singulat", "converg")),
    ("divert", ("divert", "recirculat", "overflow", "nir", "material-divert")),
    ("stack", ("stack", "palletiz", "kitting", "pack")),
    ("assemble", ("assembl", "insert", "peg", "screw", "fasten")),
    ("machine-tend", ("machine-tend", "cnc", "door-interlock", "load-unload", "feeder", "dispenser")),
    ("handoff", ("handoff", "relay", "bimanual", "dual-arm", "roco")),
    ("pick-place", ("pick", "place", "pp", "conveyor")),
]


def first(pat: str, code: str):
    m = re.search(pat, code)
    return m.group(1) if m else None


def classify(d: dict) -> dict:
    tid = d.get("task_id") or "?"
    code_t = d.get("code_template") or ""
    code_l = d.get("code") or ""
    code = code_t + "\n" + code_l
    role_based = bool(d.get("code_template") and d.get("roles") and d.get("role_defaults"))

    # backend = first target_source in the role path (code_template) if present, else code
    src_search = code_t if d.get("code_template") else code_l
    backend = first(r'target_source\s*=\s*"([^"]+)"', src_search) or \
        first(r'target_source\s*=\s*"([^"]+)"', code) or "(none)"

    vs = str(d.get("verified_status") or "")
    mc = d.get("motion_controllers") or {}
    verified_ctrls = mc.get("verified") or []
    pass_state = "draft"
    low = vs.lower()
    if any(t.lower() in low for t in PASS_TOKENS) or verified_ctrls:
        pass_state = "verified"
    elif any(t.lower() in low for t in FAIL_TOKENS):
        pass_state = "failed"
    elif "form-gate" in low and "✓" in vs:
        pass_state = "form-gate"

    # primitive family
    hay = (tid + " " + str(d.get("goal", "")) + " " + " ".join(d.get("tags", []) or [])).lower()
    primitive = "other"
    for name, kws in PRIMITIVE_RULES:
        if any(k in hay for k in kws):
            primitive = name
            break

    # world subtree roots authored (namespacing collision surface)
    roots = set(re.findall(r'/World/([A-Za-z0-9_]+)', code))

    # tier
    if role_based and backend == "curobo" and pass_state == "verified":
        tier = 0  # atomic, composer-ready
    elif role_based and backend == "curobo":
        tier = 1  # composer-tractable, needs verification
    elif backend == "curobo":
        tier = 2  # curobo but legacy code (needs path-rewrite to compose)
    else:
        tier = 3  # non-curobo backend or no controller

    return dict(task_id=tid, role_based=role_based, backend=backend,
                pass_state=pass_state, primitive=primitive,
                n_roots=len(roots), roots=sorted(roots)[:6],
                verified_ctrls=verified_ctrls, tier=tier, vs=vs[:80])


def main():
    files = sorted(p for p in TPL_DIR.glob("*.json"))
    rows = []
    for p in files:
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            print(f"  !! parse {p.name}: {e}", file=sys.stderr)
            continue
        r = classify(d)
        r["file"] = p.name
        rows.append(r)

    # summary
    by_tier = Counter(r["tier"] for r in rows)
    by_backend = Counter(r["backend"] for r in rows)
    by_prim = Counter(r["primitive"] for r in rows)
    print(f"=== {len(rows)} templates ===")
    print("TIERS:", dict(sorted(by_tier.items())),
          "(0=role+curobo+verified, 1=role+curobo, 2=curobo-legacy, 3=other)")
    print("BACKENDS:", dict(by_backend.most_common()))
    print("PRIMITIVES:", dict(by_prim.most_common()))

    print("\n=== TIER-0 (composer-ready: role-based + curobo + verified) ===")
    t0 = [r for r in rows if r["tier"] == 0]
    for r in sorted(t0, key=lambda r: (r["primitive"], r["task_id"])):
        print(f"  {r['primitive']:13} {r['task_id']:32} roots={r['n_roots']} "
              f"ctrls={r['verified_ctrls']}  [{r['file']}]")
    print(f"  ({len(t0)} tier-0)")

    print("\n=== TIER-1 (role-based + curobo, NOT yet verified — promotion candidates) ===")
    t1 = [r for r in rows if r["tier"] == 1]
    for r in sorted(t1, key=lambda r: (r["primitive"], r["task_id"]))[:40]:
        print(f"  {r['primitive']:13} {r['task_id']:32} {r['vs']}")
    print(f"  ({len(t1)} tier-1)")

    # pick->inspect->sort candidate seeds (prefer tier-0, fall back tier-1)
    print("\n=== pick->inspect->sort FIRST-COMPOSITION candidates ===")
    for stage, prim in (("PICK", "pick-place"), ("INSPECT", "inspect"), ("SORT", "sort")):
        cands = [r for r in rows if r["primitive"] == prim and r["tier"] <= 1]
        cands.sort(key=lambda r: (r["tier"], r["task_id"]))
        names = [f"{r['task_id']}(t{r['tier']})" for r in cands[:5]]
        print(f"  {stage:8} {names}")


if __name__ == "__main__":
    main()
