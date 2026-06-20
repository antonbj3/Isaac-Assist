#!/usr/bin/env python3
"""chain_recv_probe.py — ISOLATED verification of a chain RECEIVER stage with a SYNTHETIC clean N-cube handoff.

WHY (cont.319kk): verifying a structured receiver (CP-CHAIN-STACK-RECV / CP-CHAIN-PALLETIZE-RECV) through a real
2-stage chain CONFOUNDS the receiver with the SOURCE's reliability (CP-31 itself varies 2/3<->3/3 in the gate's
bare-play stage0), so the receiver gets a DIRTY handoff and the chain reads <N/N for a reason that has nothing
to do with the receiver. This probe removes the source entirely: it injects a canonical clean N-cube handoff and
runs ONLY run_stage_k -- isolating the receiver and making N-of-M cheap (one stage per run, not two).

★ FINDING (the reason this tool exists): the NULÄGE belief "multi-cube receivers relay 1/N / need a fix" was a
STALE FALSE-NEGATIVE. The receivers are PROVEN N/N (chain_stages.json proven_chains: CP-12->STACK-RECV 3/3+3/3,
CP-08->PALLETIZE-RECV 4/4+4/4, 3-stage 4/4/4 & 3/3/3). The probe's default-window <3/3 was a WINDOW-CUT, NOT a
grip/mechanism defect: the receiver's ctrl:* diag shows phase=executing + ~16 plan_calls at freeze for a 2/3 run
vs phase=wait_sensor + 24 plan_calls for a clean 3/3 column -- i.e. cuRobo's N structured pick-place cycles run
past chain_xkit_gate's old 1700*N-update window when planning is slow. Confirmed: a generous window -> 3/3 x3
(robust), and the proven chains side-stepped it by manually setting CHAIN_TOTAL~12000. The gate now auto-sizes
the window to 3200/cube (cont.319kk) so structured chains are robust BY DEFAULT -- no manual knob. So a <N/N here
means "window too small / source dirty", almost never "receiver broken"; raise CHAIN_TOTAL before suspecting the
receiver. (The anti-deadlock heuristic marks a window-cut cube 'delivered' + terminates, which is why a cut shows
up as a cube stranded at the pick zone with cubes_delivered already == N -- a phantom, read the ctrl:phase.)

It re-uses the gate's REAL run_stage_k (same relay re-instantiation + source_override + play/measure path the
production chain uses), so a pass here is the production receiver behaviour, not a mock.

Structural verdict (the false-success-vakt, not delivered-count):
  STACK  receiver -> expect a COLUMN: N distinct z-levels, xy-extent <= 0.06m (cubes vertically aligned).
  PALLET receiver -> expect a FLAT grid: 1 z-level, all cubes settled on the pallet (z within a band).

Usage:
  bash scripts/qa/kit_restart.sh            # the probe also restarts, but start clean
  python scripts/qa/chain_recv_probe.py CP-CHAIN-STACK-RECV [N=3] [--hx=0.0 --hy=-0.39]
  for i in 1 2 3; do python scripts/qa/chain_recv_probe.py CP-CHAIN-PALLETIZE-RECV; done   # N-of-M
"""
import asyncio, json, os, sys, subprocess

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
import scripts.qa.chain_xkit_gate as G   # reuse the production run_stage_k

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
OPTS = {a.split("=")[0][2:]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
NAME = ARGS[0] if ARGS else "CP-CHAIN-STACK-RECV"
N = int(ARGS[1]) if len(ARGS) > 1 else 3
HX = float(OPTS.get("hx", 0.0))
HY = float(OPTS.get("hy", -0.39))   # default: the proven CP-31 bin xy (off ~[0,-0.79], delivered 3/3 in run1)


SPREAD = "--spread" in sys.argv


def synth_handoff(n, hx, hy):
    """The n-cube handoff geometry the receiver consumes.

    --spread = FLAT GRID (n cubes at distinct xy, same handoff_z 0.825) — what a PALLETIZE source (CP-08/CP-12)
      delivers and what the STACK/PALLETIZE-RECV goal text specifies as the DESIGNED input. This is the geometry
      to verify with; at an adequate window (gate's 3200/cube, or CHAIN_TOTAL) it delivers a robust N/N column/grid.

    DEFAULT = STACKED (n cubes at one xy, 50mm z-apart, Cube_1 on top) — what a BIN/pile source (CP-31) delivers.
      NOTE: a <N/N here or with --spread at the OLD window was a WINDOW-CUT (cuRobo did not finish N cycles in
      time), NOT a de-stack/grip defect — see the module docstring. Order/geometry barely matter; the window does."""
    if SPREAD:
        # tight row centred on (hx,hy), 0.06m pitch, all at handoff_z 0.825 (the grid a palletize source lands)
        x0 = hx - 0.06 * (n - 1) / 2.0
        return {f"/World/Cube_{i+1}": [round(x0 + 0.06 * i, 3), round(hy, 3), 0.825] for i in range(n)}
    zs = [0.785 + 0.05 * (n - 1 - i) for i in range(n)]   # Cube_1 highest (top), Cube_n lowest (bottom)
    return {f"/World/Cube_{i+1}": [round(hx, 3), round(hy, 3), round(zs[i], 3)] for i in range(n)}


def verdict(name, poses):
    """structural check on the receiver's final cube poses (xy-extent + z-levels)."""
    pts = [p for p in poses.values() if p]
    if not pts:
        return "NO-POSES"
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; zs = sorted(p[2] for p in pts)
    ext = round(max(max(xs) - min(xs), max(ys) - min(ys)), 3)
    zl = []
    for z in zs:
        if not zl or abs(z - zl[-1]) > 0.03:
            zl.append(round(z, 3))
    minz = round(min(zs), 3)
    tag = "STACK" if "STACK" in name.upper() else ("PALLET" if "PALLET" in name.upper() else "?")
    notes = [f"n={len(pts)}", f"z-levels={len(zl)}{zl}", f"xy-extent={ext}m", f"minz={minz}"]
    ok = minz >= 0.6
    if minz < 0.6:
        notes.append("⚠ a cube fell below 0.6m (floor)")
    if tag == "STACK":
        if len(zl) < N:
            ok = False; notes.append(f"⚠ expected {N} z-levels for a column, got {len(zl)} = not fully stacked")
        if ext > 0.06:
            ok = False; notes.append(f"⚠ xy-extent {ext}>0.06 = not vertically aligned")
    elif tag == "PALLET":
        if len(zl) >= 2:
            ok = False; notes.append(f"⚠ {len(zl)} z-levels = PILE not a flat grid")
    return ("CLEAN " if ok else "FLAG  ") + " | ".join(notes)


async def run():
    ok, msg = G.kit_restart()
    print(f"[kit_restart] {msg}")
    if not ok:
        print("ABORT: kit_restart failed"); return
    handoff = synth_handoff(N, HX, HY)
    print(f"[probe] {NAME} synthetic handoff (N={N}) @ xy=({HX},{HY}): {handoff}")
    r = await G.run_stage_k(1, NAME, handoff)
    # cont.319kk DIAGNOSTIC: dump the controller's own ctrl:* state so we see WHY a cube was not delivered
    # (plan-fail vs grip-miss-marked-delivered vs never-claimed) instead of inferring from final poses.
    try:
        from service.isaac_assist_service.chat.tools import kit_tools as kt
        diag = (await kt.exec_sync(
            "import omni.usd, json\n"
            "st=omni.usd.get_context().get_stage(); out={}\n"
            "for pr in st.Traverse():\n"
            "    a=pr.GetAttribute('ctrl:cubes_delivered')\n"
            "    if a and a.IsValid() and a.HasAuthoredValue():\n"
            "        p=str(pr.GetPath()); d={}\n"
            "        for k in ('cubes_delivered','cycles_attempted','error_count','plan_calls','plan_fails','picked_path','last_error','last_fail_goal','phase'):\n"
            "            at=pr.GetAttribute('ctrl:'+k)\n"
            "            if at and at.IsValid(): d[k]=at.Get()\n"
            "        out[p]=d\n"
            "print('CTRLDIAG '+json.dumps(out, default=str))\n", timeout=40)).get("output", "")
        for ln in diag.splitlines():
            if ln.startswith("CTRLDIAG"):
                print("[probe] " + ln)
    except Exception as _e:
        print(f"[probe] (ctrl-diag unavailable: {_e})")
    d, tot = r.get("delivered", 0), r.get("total", N)
    print(f"[probe] {NAME}: delivered={d}/{tot} mode={r.get('receiver_mode')} auto_offset={r.get('auto_offset')}")
    print(f"[probe] poses={json.dumps(r.get('poses'))}")
    print(f"[probe] STRUCTURE: {verdict(NAME, r.get('poses') or {})}")
    print(f"PROBE_RESULT {NAME} {d}/{tot}")


if __name__ == "__main__":
    asyncio.run(run())
