"""chain_branch_gate.py — BRANCHING (Y-split) cross-Kit chain: 1 conditional source -> 2 downstream receivers.

Frontier #4 of the maximal-stress battery. The proven chains (chain_xkit_gate.py) are LINEAR source->receiver.
This forks: a sorter SOURCE (CP-BRANCH-SRC-SW) routes each item by weight to one of 2 HANDOFF TRAYS, then the
HeavyTray subset relays to a heavy receiver Kit and the LightTray subset to a light receiver Kit — TWO independent
cross-Kit relays off ONE source. Custody = each part delivered at BOTH its source-tray AND its branch receiver.

Reuses chain_xkit_gate's proven primitives (MEASURE/PLAY_CHUNK/run_stage_k/kit_restart) unchanged; the only new
piece is measuring the source against 2 targets after a single play (-> 2 handoffs) and running run_stage_k per branch.

Usage: python scripts/qa/chain_branch_gate.py [SOURCE] [HEAVY_TARGET HEAVY_RECV] [LIGHT_TARGET LIGHT_RECV]
Default: CP-BRANCH-SRC-SW  /World/HeavyBin CP-CHAIN-PALLETIZE-RECV  /World/LightBin CP-CHAIN-PALLETIZE-RECV
"""
import asyncio, json, os, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
sys.path.insert(0, f"{REPO}/scripts/qa")
from chain_xkit_gate import MEASURE, PLAY_CHUNK, run_stage_k, kit_restart  # proven primitives


async def run_branch_source(name, targets):
    """Build the sorter source, play once, measure delivered to EACH target tray -> {target: handoff_dict}."""
    from service.isaac_assist_service.chat.tools import kit_tools as kt
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
    sa = tpl.get("simulate_args") or {}
    cubes = sa.get("cube_paths") or []
    await kt.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    await kt.exec_sync("import builtins\nfor k in [x for x in list(vars(builtins)) if x.startswith('_curobo_pp_sub_')]:\n    try: delattr(builtins,k)\n    except Exception: pass\n", timeout=10)
    await execute_template_canonical(tpl); await settle_after_canonical(tpl)
    # single play window: scale with cube count (sorter @ belt 0.02 ~3200 updates/cube), 8000 floor; CHAIN_TOTAL
    # overrides EITHER WAY (the old unconditional max(...,24000) floor made even a 2-cube source crawl + couldn't be
    # lowered). A 2-cube MINI -> 8000 (~130s sim); a 9-cube source -> 28800.
    total = int(os.environ.get("CHAIN_TOTAL") or max(3200 * len(cubes), 8000))
    done = 0
    while done < total:
        n = min(1000, total - done)
        await kt.exec_sync(PLAY_CHUNK.replace("__N__", str(n)), timeout=200)
        done += n
    # measure each tray target separately off the SAME settled state
    handoffs = {}
    for tgt in targets:
        mcode = MEASURE.replace("__TARGET__", repr(tgt)).replace("__CUBES__", repr(cubes)).replace("__PLAY__", "False")
        out = (await kt.exec_sync(mcode, timeout=120)).get("output", "").strip()
        lines = [l for l in out.splitlines() if l.startswith("MEASURE")]
        res = json.loads(lines[-1][8:]) if lines else {"delivered_paths": [], "poses": {}}
        handoffs[tgt] = {cp: res["poses"][cp] for cp in res.get("delivered_paths", []) if res.get("poses", {}).get(cp)}
    return handoffs, cubes


async def main():
    a = sys.argv[1:]
    source = a[0] if a else "CP-BRANCH-SRC-SW"
    # N branches: SOURCE TRAY1 RECV1 TRAY2 RECV2 [TRAY3 RECV3 ...] — generalizes the 2-way Y-split to an N-way
    # fan-out (e.g. the 3-lane colour sorter -> 3 receivers); the rest of main() already loops over `branches`.
    pairs = [(a[1 + 2 * i], a[2 + 2 * i]) for i in range((len(a) - 1) // 2)]
    branches = pairs or [("/World/HeavyBin", "CP-CHAIN-PALLETIZE-RECV"),
                         ("/World/LightBin", "CP-CHAIN-PALLETIZE-RECV")]
    print(f"=== BRANCHING CHAIN: {source} -> " + " + ".join(f"{t}->{r}" for t, r in branches) + " ===")
    handoffs, cubes = await run_branch_source(source, [t for t, _ in branches])
    results = []
    for t, _ in branches:
        print(f"  source routed to {t}: {len(handoffs[t])} cubes {list(handoffs[t].keys())}")
    for i, (tray, recv) in enumerate(branches, 1):
        h = handoffs[tray]
        if not h:
            print(f"BRANCH {i} ({tray}): EMPTY handoff — source delivered 0 to this tray");
            results.append({"branch": tray, "recv": recv, "delivered": 0, "total": 0}); continue
        ok, msg = kit_restart()
        print(f"  [kit_restart -> branch {i} {recv}] {msg}")
        if not ok:
            print(f"BRANCH {i} ABORT: kit_restart failed"); break
        rk = await run_stage_k(i, recv, h)
        results.append({"branch": tray, "recv": recv, "delivered": rk.get("delivered"),
                        "total": len(h), "delivered_paths": rk.get("delivered_paths")})
        # instrument the branch (per 'instrument the failure path'): a 0-delivery branch needs the auto-offset +
        # final poses to isolate offset-too-large vs reach vs relay (the UR10-branch 0/1 diagnosis, cont.319qqq).
        _diag = f"  BRANCH {i} {recv} <- {tray}: delivered={rk.get('delivered')}/{len(h)} auto_offset={rk.get('auto_offset')} mode={rk.get('receiver_mode')} handoff_in={rk.get('handoff_in')}"
        if not rk.get("delivered"):
            _diag += f" | poses={rk.get('poses')} measure_error={str(rk.get('measure_error'))[:140]}"
        print(_diag)
    print("\n=== BRANCHING CHAIN RESULT ===")
    all_full = True
    for r in results:
        full = r["total"] > 0 and r["delivered"] == r["total"]
        all_full = all_full and full and r["total"] > 0
        print(f"  {r['branch']:18} -> {r['recv']:24} {r['delivered']}/{r['total']} {'FULL' if full else 'PARTIAL'}")
    print("VERDICT:", "BRANCHING CHAIN GOLD (both branches deliver their routed subset)" if all_full and len(results) == 2
          else "PARTIAL / needs review (honest custody)")


if __name__ == "__main__":
    asyncio.run(main())
