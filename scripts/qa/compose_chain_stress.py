#!/usr/bin/env python3
"""compose_chain_stress.py (cont.319ss) — CHAIN-WIRING-INTEGRITY-UNDER-EDIT-SEQUENCE gate.

The CHAIN analog of compose_layout_stress.py. A handoff chain wires each stage to SOURCE its immediate
predecessor's delivered parts (apply_source_override: stage B picks the cubes stage A delivered). Anton's
"build step by step, then SUDDENLY change your mind" stress, applied to the HANDOFF WIRING: if a user reorders /
removes / inserts a stage, does every stage still source its CORRECT (current) upstream, or does a stage end up
sourcing a REMOVED or WRONG-position predecessor (a stale/orphan handoff -> it picks cubes that never arrive)?

Grounded in the REAL production primitive apply_source_override (service/.../composer.py) — not a reimplementation.
Pure + offline (no Kit). Models the orchestrator's wiring rule explicitly (stage i>0 sources stage i-1's delivered
paths), runs an edit timeline, and asserts the INVARIANT after every edit.

★ NON-TAUTOLOGY GUARD (TAUTOLOG-GATE memory): a gate that only checks a function against its own construction always
passes. So this gate includes a NEGATIVE CONTROL — a deliberately STALE wiring (wired by the ORIGINAL order after a
reorder) that the invariant MUST flag as broken. If the negative control does NOT fail, the gate has no teeth and the
whole run is declared INVALID. Only a run where (real edits PASS) AND (the stale control FAILS) is trustworthy.

INVARIANT: for the wired chain in its CURRENT order, every non-source stage's effective source_paths ==
its immediate predecessor's delivered paths. No orphan (sourcing a removed stage), no stale (sourcing a
non-adjacent / original-order stage).
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "service"))
from isaac_assist_service.chat import composer as C  # PRODUCTION primitive apply_source_override


def _delivered(stage_name, pos, parts):
    """The part paths a stage at order-position `pos` delivers (namespaced to its instance)."""
    return [f"/World/inst{pos}/{stage_name}/Handoff/Cube_{k}" for k in range(parts)]


def _own_feed(pos, parts):
    return [f"/World/inst{pos}/Feed/Cube_{k}" for k in range(parts)]


def _default_calls(pos, parts):
    """A stage's captured pick-place call BEFORE chain wiring (sources its own feed)."""
    return [("setup_pick_place_controller",
             {"source_paths": _own_feed(pos, parts), "cube_paths": _own_feed(pos, parts),
              "destination_path": f"/World/inst{pos}/Drop"})]


def wire_chain(order, parts=2, src_of_pos=None):
    """Wire a chain in `order` (list of stage names) via the REAL apply_source_override.
    Returns per-stage effective source_paths. `src_of_pos(pos)` overrides WHICH order-position each stage sources
    its upstream-delivered from (default = pos-1, the correct immediate predecessor). The override exists ONLY to
    inject the stale-wiring NEGATIVE CONTROL."""
    src_of_pos = src_of_pos or (lambda pos: pos - 1)
    eff = []
    for pos, name in enumerate(order):
        calls = _default_calls(pos, parts)
        if pos == 0:
            eff.append(list(_own_feed(pos, parts)))          # source stage: its own feed
            continue
        up = src_of_pos(pos)
        up_delivered = _delivered(order[up], up, parts) if 0 <= up < len(order) else ["<ORPHAN>"]
        wired = C.apply_source_override(calls, up_delivered, dest_override=f"/World/inst{pos}/Drop")
        eff.append(wired[0][1]["source_paths"])
    return eff


def _invariant_violations(order, eff, parts=2):
    """Return list of (pos, reason) where a non-source stage does NOT source its CURRENT immediate predecessor."""
    bad = []
    for pos in range(1, len(order)):
        want = _delivered(order[pos - 1], pos - 1, parts)   # the CORRECT current predecessor's delivered paths
        if eff[pos] != want:
            reason = "ORPHAN (sources a missing stage)" if "<ORPHAN>" in eff[pos] else "STALE/WRONG predecessor"
            bad.append((pos, f"stage[{pos}]={order[pos]} {reason}: sources {eff[pos][:1]}... want {want[:1]}..."))
    return bad


def run(parts=2):
    A, B, Cc, D = "Asrc", "Bmid", "Crecv", "Dins"
    timeline = [
        ("build chain A->B->C",        [A, B, Cc]),
        ("reorder  A->C->B",           [A, Cc, B]),
        ("remove   B  (A->C)",         [A, Cc]),
        ("insert   D @1 (A->D->C)",    [A, D, Cc]),
    ]
    print("CHAIN-WIRING-STRESS timeline (each stage i>0 must source stage i-1's delivered parts)\n")
    all_ok = True
    for label, order in timeline:
        eff = wire_chain(order, parts)
        bad = _invariant_violations(order, eff, parts)
        if bad:
            all_ok = False
        print(f"  {label:28s} order={order}")
        print(f"      wiring: " + " | ".join(
            f"{order[p]}<-{'FEED' if p == 0 else order[p-1]}" for p in range(len(order))))
        for _, msg in bad:
            print(f"      ⚠️ {msg}")
    print(f"\n  REAL-EDITS INVARIANT: {'HELD every step' if all_ok else 'VIOLATED'}")

    # ── NEGATIVE CONTROL (teeth check): after a reorder A->C->B, wire each stage from its ORIGINAL-order predecessor
    # (the classic stale-cache bug) instead of the current one. The invariant MUST catch it.
    reordered = [A, Cc, B]
    orig_pred = {A: -1, B: A, Cc: B}                 # original A->B->C adjacencies (B's pred=A, C's pred=B)
    def stale_src(pos):
        name = reordered[pos]
        pred_name = orig_pred[name]
        return reordered.index(pred_name) if pred_name in reordered else -99
    eff_stale = wire_chain(reordered, parts, src_of_pos=stale_src)
    stale_bad = _invariant_violations(reordered, eff_stale, parts)
    teeth = len(stale_bad) > 0
    print(f"\n  NEGATIVE CONTROL (stale original-order wiring on {reordered}): "
          f"{'CAUGHT ' + str(len(stale_bad)) + ' violation(s) — gate has teeth' if teeth else 'NOT caught — GATE IS TOOTHLESS'}")
    for _, msg in stale_bad:
        print(f"      (control) {msg}")

    valid = all_ok and teeth
    print(f"\nCHAIN_WIRING_STRESS: {'PASS' if valid else 'FAIL'} "
          f"(real-edits {'ok' if all_ok else 'VIOLATED'}, negative-control {'has-teeth' if teeth else 'TOOTHLESS->INVALID'})")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(run())
