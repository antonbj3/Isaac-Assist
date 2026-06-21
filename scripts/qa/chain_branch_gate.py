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
    # single play window (sorter is slow @ belt 0.02; scale with cube count, allow CHAIN_TOTAL override)
    total = max(3200 * len(cubes), int(os.environ.get("CHAIN_TOTAL") or 0), 24000)
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
    branches = ([(a[1], a[2]), (a[3], a[4])] if len(a) >= 5
                else [("/World/HeavyBin", "CP-CHAIN-PALLETIZE-RECV"),
                      ("/World/LightBin", "CP-CHAIN-PALLETIZE-RECV")])
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
        print(f"  BRANCH {i} {recv} <- {tray}: delivered={rk.get('delivered')}/{len(h)}")
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
