#!/usr/bin/env python3
"""compose_orchestrate.py — the INTEGRATED runtime-LLM composition loop (the real one).

Wires the two halves that were previously run SEPARATELY and hand-stitched (the cont.255 honesty
correction: "END-GOAL loop CLOSED" was two tools manually joined for one example). This is ONE program:

    task spec  ->  Gemini compose-reasoning (pick blocks + classify structure + flag gaps)   [Kit-free]
               ->  route by structure / robot-diversity
               ->  build + verify in Kit (parallel -> compose_and_verify)                     [Kit]
               ->  honest REASONING-vs-DELIVERY report

Reports BOTH error axes (Anton's framing, LLM_FLOW_SIMULATION_PROTOCOL.md): REASONING (did the LLM pick
robust blocks + the right topology?) and DELIVERY (did the chosen composition actually deliver in Kit?).

FAIL-CLOSED (no faked greens):
  - LLM flags a gap + picks no buildable cell            -> HALT (won't build a plan the LLM says is incomplete)
  - a picked cell is NOT GENUINE/scene_eyes-verified     -> HALT (won't build on unverified blocks)
  - structure == sequential                              -> GATED: needs co-designed zero-offset CP-CHAIN-*
                                                            templates (open frontier #2/#29); reports, no fake build
  - robot-diverse parallel (UR10 + Franka same Kit)      -> GATED: UR10 process-global PhysX corruption
                                                            (feedback_ur10_corrupts_global_physx); cross-Kit not wired here
  - parallel + Franka-only                               -> EXECUTE in Kit (the path that is actually GREEN)

So the orchestrator executes ONLY what is genuinely verified to work, and transparently reports every gate
instead of pretending. Scope is explicit, not hidden.

Usage:
  compose_orchestrate.py "Station 1: a Franka picks parts into a bin. Station 2: a Franka colour-sorts."
  compose_orchestrate.py "<task>" --dry-run                 # reasoning + routing only, no Kit
  compose_orchestrate.py --cells CP-01,CP-03 --structure parallel [--gap 0]   # test router w/o Gemini
Needs ONE local Kit on :8001 for the EXECUTE path (caller restarts before).
"""
import asyncio, json, os, re, sys, argparse, subprocess
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
sys.path.insert(0, REPO + "/scripts/qa")

_BLOCKS = json.load(open(f"{REPO}/workspace/composable_blocks.json"))
_ALL = _BLOCKS["all"]
_CANON = {cp for cp in _BLOCKS["canonical_blocks"].values() if cp}


def _verdict(cp):
    return (_ALL.get(cp) or {}).get("verdict", "")


def _robust(cp):
    return _verdict(cp).startswith("GENUINE")


def _robot(cp):
    return (_ALL.get(cp) or {}).get("robot", "?")


async def plan_with_gemini(task, model):
    from compose_reason_eval import CATALOG, SYS
    from service.isaac_assist_service.chat.llm_gemini import GeminiProvider
    prov = GeminiProvider(api_key=os.environ["GEMINI_API_KEY"], model=model)
    r = await prov.complete([{"role": "user", "content": f"Available work-cells:\n{CATALOG}\n\nTask: {task}"}],
                            {"system_override": SYS})
    txt = (r.text or "").strip()
    seg = txt.split('"reasoning"')[0] if '"reasoning"' in txt else txt
    seen = set()
    cells = [c for c in re.findall(r"CP-\d+", seg) if c in _CANON and not (c in seen or seen.add(c))]
    sm = re.search(r'"structure"\s*:\s*"(sequential|parallel)"', txt)
    gap = bool(re.search(r'"gaps"\s*:\s*\[\s*"[^"]', txt))
    return {"cells": cells, "structure": (sm.group(1) if sm else None), "gap": gap, "raw": txt}


def execute_parallel(cells, timeout=780):
    """Run the proven parallel executor (compose_and_verify) as a subprocess and parse its delivery."""
    res = subprocess.run(["python3", f"{REPO}/scripts/qa/compose_and_verify.py"] + cells,
                         capture_output=True, text=True, timeout=timeout)
    out = res.stdout + res.stderr
    deliv = {}
    for l in out.splitlines():
        m = re.search(r"DELIV inst=(\S+) tpl=(\S+) delivered=(\d+)/(\d+)", l)
        if m:
            deliv[m.group(1)] = {"tpl": m.group(2), "delivered": int(m.group(3)), "total": int(m.group(4))}
    verified = "COMPOSE_VERIFY_DONE verified=True" in out
    return {"verified": verified, "delivery": deliv, "raw": out}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default=None)
    ap.add_argument("--model", default="gemini-robotics-er-1.6-preview")
    ap.add_argument("--dry-run", action="store_true", help="reasoning + routing only, no Kit")
    ap.add_argument("--cells", default=None, help="comma-sep override (skip Gemini): CP-01,CP-03")
    ap.add_argument("--structure", default=None, choices=[None, "parallel", "sequential"])
    ap.add_argument("--gap", type=int, default=0, help="override gap flag (with --cells)")
    a = ap.parse_args()

    # ---- PLAN (Gemini, or override) ----
    if a.cells is not None:
        p = {"cells": [c for c in a.cells.split(",") if c], "structure": a.structure or "parallel",
             "gap": bool(a.gap), "raw": "(override)"}
        print("E2E PLAN (override) cells=%s structure=%s gap=%s" % (p["cells"], p["structure"], p["gap"]))
    else:
        if not a.task:
            print("E2E ERROR: provide a task spec or --cells"); return
        print("E2E TASK:", a.task)
        p = await plan_with_gemini(a.task, a.model)
        print("E2E PLAN cells=%s structure=%s gap_flag=%s" % (p["cells"], p["structure"], p["gap"]))

    # ---- REASONING report ----
    robots = sorted(set(_robot(c) for c in p["cells"]))
    robust = [c for c in p["cells"] if _robust(c)]
    nonrobust = [c for c in p["cells"] if not _robust(c)]
    print("E2E REASONING robots=%s robust=%s nonrobust=%s verdicts=%s" %
          (robots, robust, nonrobust, {c: _verdict(c) for c in p["cells"]}))

    # ---- FAIL-CLOSED ----
    if p["gap"] and not p["cells"]:
        print("E2E HALT(gap): LLM flagged a missing block + picked no buildable cell -> not building (honest)."); return
    if not p["cells"]:
        print("E2E HALT(empty): no catalog cells picked."); return
    if nonrobust:
        print("E2E HALT(unverified): picked non-GENUINE block(s) %s -> refusing to build on unverified blocks." % nonrobust); return

    # ---- ROUTE ----
    if p["structure"] == "sequential":
        print("E2E GATE(sequential): handoff-chain execution needs co-designed zero-offset CP-CHAIN-* templates "
              "(open frontier #2/#29 auto-handoff). Plan is valid; NOT faking a build."); return
    if len(robots) > 1:
        print("E2E GATE(robot-diversity): %s in one Kit is blocked by UR10 process-global PhysX corruption; "
              "cross-Kit composition (chain_xkit_gate) is not yet wired into this orchestrator." % robots); return
    if a.dry_run:
        print("E2E DRY-RUN: would EXECUTE parallel Franka-only %s in Kit." % p["cells"]); return

    # ---- EXECUTE (parallel, Franka-only = the genuinely GREEN path) ----
    print("E2E EXECUTE: parallel Franka-only %s -> Kit ..." % p["cells"])
    r = execute_parallel(p["cells"])
    print("E2E DELIVERY verified=%s delivery=%s" % (r["verified"], r["delivery"]))
    print("E2E RESULT:", "✅ END-TO-END GREEN (reasoning picked robust blocks + Kit delivered full)"
          if r["verified"] else "❌ delivery FAILED (reasoning ok, execution did not deliver)")


if __name__ == "__main__":
    asyncio.run(main())
