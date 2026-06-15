#!/usr/bin/env python3
"""gen_composition_hints.py — derived composition-hints cache (LAYER 2 metadata, STEP 2).

Per the design-review: composition metadata is a DERIVED, REGENERABLE cache, NOT hand-authored
fields stamped onto 439 template JSONs (avoids the em-dash-churn + stale-lying-cache failure
classes). This extracts, for every VERIFIED_CORE delivery template, the facts the composer needs:

  footprint     {x:[lo,hi], y:[lo,hi], known}  — from authored scene prims (composer.template_footprint).
                Consumed by layout_solver for collision-free spacing.
  input_ports   what the cell CONSUMES: source object paths (start positions) + their leaf 'kind'.
                A chain's downstream cell sources these.
  output_ports  what the cell PRODUCES: target/destination path + leaf name (the delivered region).
                A chain's upstream cell delivers here; apply_source_override wires output->input.
  exclusive_resources  ['curobo_planner'] when the cell uses cuRobo (process-global plan/move lock
                -> the composer must REFUSE/serialize two concurrent; precondition_check reads this).
  namespacing_safe  False if the template bakes absolute /World/ paths in a run_usd_script body
                (those escape re-rooting) -> a composability promotion gate.

Output: workspace/composition_hints.json (regenerable; a CI check can assert it matches the
authored geometry so it can't silently drift). Zero-boot, no Kit, no ChromaDB, no template mutation.

Usage: gen_composition_hints.py [--write]   (default: print summary to stderr; --write -> sidecar)
"""
import json, glob, os, sys
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
from service.isaac_assist_service.chat.composer import template_footprint, precondition_check

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
TPL_DIR = os.path.join(REPO, "workspace", "templates")
OUT = os.path.join(REPO, "workspace", "composition_hints.json")


def is_verified_core(t):
    vs = t.get("verified_status") or ""
    mc = (t.get("motion_controllers") or {}).get("verified")
    return bool(mc or "stable_ok" in vs or "function-gate ✓" in vs) and "stable_fail" not in vs


def hints_for(name, t):
    code = t.get("code") or ""
    sa = t.get("simulate_args") or t.get("verify_args") or {}
    cubes = [c for c in (sa.get("cube_paths") or sa.get("source_paths")
             or ([sa.get("cube_path")] if sa.get("cube_path") else [])) if c]
    target = sa.get("target_path")
    fx_lo, fx_hi, fx_known = template_footprint(t, "x")
    fy_lo, fy_hi, _ = template_footprint(t, "y")
    mc = (t.get("motion_controllers") or {}).get("verified") or []
    uses_curobo = ("curobo" in mc) or ("_gen_pick_place_curobo" in code) or ("setup_pick_place_controller" in code)
    ns_escape = ("run_usd_script" in code and "/World/" in code)
    return {
        "template": name,
        "footprint": {"x": [round(fx_lo, 2), round(fx_hi, 2)], "y": [round(fy_lo, 2), round(fy_hi, 2)],
                      "known": fx_known},
        "input_ports": [{"path": c, "kind": c.split("/")[-1].rstrip("0123456789_")} for c in cubes],
        "output_ports": ([{"path": target, "name": target.split("/")[-1]}] if target else []),
        "exclusive_resources": (["curobo_planner"] if uses_curobo else []),
        "namespacing_safe": (not ns_escape),
        "n_objects": len(cubes),
    }


def main():
    hints = {}
    n_core = n_deliv = 0
    for f in sorted(glob.glob(os.path.join(TPL_DIR, "*.json"))):
        name = os.path.basename(f)[:-5]
        try:
            t = json.load(open(f))
        except Exception:
            continue
        if not is_verified_core(t):
            continue
        n_core += 1
        sa = t.get("simulate_args") or t.get("verify_args") or {}
        if not (sa.get("cube_paths") or sa.get("source_paths") or sa.get("cube_path")):
            continue   # non-delivery (benchmark/plumbing) — no IO ports to compose on
        n_deliv += 1
        hints[name] = hints_for(name, t)
    payload = {"generated_for": "VERIFIED_CORE delivery templates", "n": len(hints), "hints": hints}
    if "--write" in sys.argv:
        # surgical write of a GENERATED sidecar (not a template) — plain json.dump is fine here
        json.dump(payload, open(OUT, "w"), indent=1)
        sys.stderr.write("wrote %s (%d templates)\n" % (OUT, len(hints)))
    # summary
    n_curobo = sum(1 for h in hints.values() if h["exclusive_resources"])
    n_unsafe = sum(1 for h in hints.values() if not h["namespacing_safe"])
    n_foot_unknown = sum(1 for h in hints.values() if not h["footprint"]["known"])
    sys.stderr.write("VERIFIED_CORE=%d delivery=%d hinted=%d | curobo-exclusive=%d namespacing-unsafe=%d footprint-unknown=%d\n"
                     % (n_core, n_deliv, len(hints), n_curobo, n_unsafe, n_foot_unknown))
    if not ("--write" in sys.argv):
        print(json.dumps(list(hints.values())[:2], indent=1))


if __name__ == "__main__":
    main()
