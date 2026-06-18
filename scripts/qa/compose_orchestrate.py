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
  - structure == sequential                              -> EXECUTE via chain_xkit_gate (cross-Kit relay;
                                                            arbitrary-offset UR10 receivers OK post cont.261).
                                                            Needs chain-ready blocks; arbitrary canonical blocks
                                                            may not chain (handoff role/height compat = open #29).
  - robot-diverse parallel (UR10 + Franka same Kit)      -> GATED: UR10 process-global PhysX corruption — robot-
                                                            diversity goes through the SEQUENTIAL cross-Kit chain.
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
_CHAIN = json.load(open(f"{REPO}/workspace/chain_stages.json"))["stages"]   # verified chain-ready stages (#29)


def _verdict(cp):
    return (_ALL.get(cp) or {}).get("verdict", "")


def _robust(cp):
    # GENUINE (scene_eyes-verified canonical) OR a verified chain-ready stage (for sequential chains)
    return _verdict(cp).startswith("GENUINE") or cp in _CHAIN


def _robot(cp):
    return (_ALL.get(cp) or {}).get("robot") or (_CHAIN.get(cp) or {}).get("robot", "?")


async def plan_with_gemini(task, model):
    from compose_reason_eval import CATALOG, SYS
    from service.isaac_assist_service.chat.llm_gemini import GeminiProvider
    # AUGMENT (cont.264): the canonical CATALOG only has PARALLEL-station blocks (they deliver into bins -> not
    # chainable). Add the chain-ready stages so the LLM can pick chainable SOURCE+RECEIVER for a SEQUENTIAL
    # handoff task. (compose_reason_eval itself is untouched -> its validated eval is unaffected.)
    _cl = []
    for cp, m in _CHAIN.items():
        h = m.get("handoff_surface") or m.get("pick_height")
        n = m.get("n_cube")
        multi = (isinstance(n, int) and n > 1) or (isinstance(n, str) and "N" in n)
        if m.get("role") == "source":
            what = (("palletizes %s parts into a %s handoff grid (a downstream cell can pick each of them)" % (n, h)) if multi
                    else ("delivers a part onto a %s handoff surface" % h))
        elif m.get("can_source"):
            # MID-stage receiver (cont.300 formal can_source, supersedes the cont.296 're-palletize' string-match):
            # it re-arranges parts onto its OWN output handoff (delivers_surface), which is itself a handoff a
            # further cell can chain FROM -> this cell can be a MID-stage source for a deeper chain.
            ds = m.get("delivers_surface") or "a handoff surface"
            what = ("picks parts (one OR several) off a %s handoff surface and RE-ARRANGES them onto a %s output, "
                    "which is ITSELF a handoff a FURTHER pick cell can chain FROM (so this cell can be a MID-stage "
                    "source; only add a 3rd downstream cell if the task explicitly asks for a final pick/sort AFTER "
                    "this re-arrange)" % (h, ds))
        else:
            what = (("picks parts (one OR several) off a %s handoff surface and deposits them into a bin" % h) if (multi or "N" in str(n))
                    else ("picks a part off a %s handoff surface and deposits it into a bin" % h))
        _cl.append("- %s: a %s chain %s that %s" % (cp, m.get("robot"), (m.get("role") or "").upper(), what))
    aug_catalog = CATALOG + "\n\n--- chain-ready stages (use ONLY for a SEQUENTIAL handoff chain) ---\n" + "\n".join(_cl)
    aug_sys = SYS + (" For a SEQUENTIAL handoff chain, do NOT use the parallel work-cells (they deliver into "
                     "bins and can't be picked from); instead pick a chain SOURCE then a chain RECEIVER from the "
                     "chain-ready stages, whose handoff heights MATCH (flat-source->flat-receiver, raised-source"
                     "->raised-receiver; UR10 delivers flat + picks raised, Franka delivers flat/raised + picks flat).")
    prov = GeminiProvider(api_key=os.environ["GEMINI_API_KEY"], model=model)
    r = await prov.complete([{"role": "user", "content": f"Available work-cells:\n{aug_catalog}\n\nTask: {task}"}],
                            {"system_override": aug_sys})
    txt = (r.text or "").strip()
    seg = txt.split('"reasoning"')[0] if '"reasoning"' in txt else txt
    seen = set()
    cells = [c for c in re.findall(r"CP-[A-Z0-9-]+", seg)
             if (c in _CANON or c in _CHAIN) and not (c in seen or seen.add(c))]
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


def execute_chain(cells, timeout=2600):
    """Run the cross-Kit SEQUENTIAL chain executor (chain_xkit_gate) as a subprocess + parse per-stage delivery.
    chain_xkit_gate restarts the Kit between stages internally. Post cont.261 it handles ARBITRARY-offset UR10
    receivers (no hand-designed zero-offset pairs). ⚠️ It still needs CHAIN-READY blocks (each stage a
    source->handoff->receiver with compatible handoff HEIGHT); arbitrary canonical blocks may not chain
    (role/height compat = open #29 auto-handoff) — in which case a stage honestly reports delivered<total."""
    res = subprocess.run(["python3", f"{REPO}/scripts/qa/chain_xkit_gate.py"] + cells,
                         capture_output=True, text=True, timeout=timeout)
    out = res.stdout + res.stderr
    stages = []
    for l in out.splitlines():
        m = re.search(r"stage(\d+) (\S+): delivered=(\d+)/(\d+)", l)
        if m:
            stages.append({"stage": int(m.group(1)), "tpl": m.group(2),
                           "delivered": int(m.group(3)), "total": int(m.group(4))})
    return {"all_ok": "ALL DELIVERED" in out, "stages": stages, "raw": out}


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
        # ROUTE sequential -> the cross-Kit chain executor (handles arbitrary-offset UR10 receivers post
        # cont.261). This is the robot-diversity path (cross-Kit sidesteps the UR10 same-Kit PhysX block).
        # #29 HANDOFF PRE-FILTER (cont.263): check each consecutive (src,recv) pair is chain-compatible
        # (deliver onto a pickable surface at a height the receiver robot can grasp) BEFORE the expensive
        # cross-Kit run. This catches the cont.262 CP-73->CP-13 failure (deep-bin handoff) for free.
        from compose_handoff import chain_compat
        for i in range(len(p["cells"]) - 1):
            cmp = chain_compat(p["cells"][i], p["cells"][i + 1])
            print("E2E HANDOFF %s->%s: %s — %s" % (p["cells"][i], p["cells"][i + 1],
                  "COMPAT" if cmp["compatible"] else "INCOMPAT", cmp["reason"]))
            if not cmp["compatible"]:
                print("E2E HALT(handoff-incompat): chain blocks not handoff-compatible -> not running an "
                      "incompatible cross-Kit chain (#29 pre-filter). Needs chain-ready surface-delivering "
                      "source + height-matched receiver."); return
        if a.dry_run:
            print("E2E DRY-RUN: would route sequential %s -> chain_xkit_gate (cross-Kit relay)." % p["cells"]); return
        print("E2E EXECUTE: sequential %s -> chain_xkit_gate (cross-Kit relay) ... [needs chain-ready blocks; "
              "arbitrary canonical blocks may not chain = open #29]" % p["cells"])
        r = execute_chain(p["cells"])
        print("E2E CHAIN stages=%s all_delivered=%s" % (r["stages"], r["all_ok"]))
        print("E2E RESULT:", "✅ SEQUENTIAL CHAIN GREEN (cross-Kit relay delivered)" if r["all_ok"]
              else "❌ chain did not fully deliver (block chain-readiness / handoff-height compat = #29)"); return
    if len(robots) > 1:
        print("E2E GATE(robot-diversity parallel): %s in ONE Kit is blocked by UR10 process-global PhysX "
              "corruption. Robot-diversity goes through the SEQUENTIAL cross-Kit chain (structure=sequential), "
              "not same-Kit parallel — re-pose the task as a handoff line." % robots); return
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
