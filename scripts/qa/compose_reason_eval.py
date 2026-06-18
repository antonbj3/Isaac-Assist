#!/usr/bin/env python3
"""compose_reason_eval.py — KIT-FREE + ChromaDB-FREE compose-REASONING eval (LLM-flow protocol split (b)).

Tests the END-GOAL reasoning half in isolation from retrieval: GIVEN the canonical work-cell catalog (no
ChromaDB), does the LLM DECOMPOSE a multi-station task and select the RIGHT block per sub-task (right robot
family AND right operation)? Bypasses the ChromaDB retrieval harness (which is watched-window-only) and Kit
(no scene execution) -> runs in parallel with serial Kit work.

Cases' ground_truth is grounded in workspace/composable_blocks.json canonical_blocks (robot:op -> CP-id).
The GAP-HONESTY case asks for a cell that does NOT exist in the catalog (UR10 color-sort = null) -> the
right behaviour is to FLAG the gap, not confidently pick a wrong-robot / wrong-op block (a false-success
the planner must avoid).

Usage:  python3 scripts/qa/compose_reason_eval.py [--model gemini-robotics-er-1.6-preview]
"""
import asyncio, json, os, re, sys, argparse
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

_BLOCKS = json.load(open(f"{REPO}/workspace/composable_blocks.json"))["canonical_blocks"]
_AVAIL = {cp for cp in _BLOCKS.values() if cp}
CATALOG = "\n".join(f"- {cp}: a {k.split(':',1)[0]} robot work-cell that performs {k.split(':',1)[1]}"
                    for k, cp in sorted(_BLOCKS.items()) if cp)

SYS = ("You are a factory-scene COMPOSITION PLANNER. You build scenes by selecting pre-built robot work-cells "
       "from a fixed catalog and composing them. Decompose the task into sub-tasks; pick exactly ONE catalog "
       "cell per sub-task, matching BOTH the robot family AND the operation. If NO catalog cell fits a sub-task, "
       "do NOT substitute a wrong-robot or wrong-operation cell — instead list that sub-task in \"gaps\". "
       "Also classify the composition STRUCTURE: 'sequential' if the cells form a HANDOFF CHAIN (one cell's "
       "output part becomes the next cell's input), or 'parallel' if the cells are INDEPENDENT side-by-side "
       "stations with no part handoff between them. "
       'Return ONLY JSON: {"cells":["CP-XX",...],"structure":"sequential|parallel","gaps":["..."],"reasoning":"one sentence"}.')

# ground_truth grounded in canonical_blocks; "gap" = the cell asked for is null in the catalog
CASES = [
    {"id": "het-2stn", "gt": {"CP-73", "CP-13"}, "gap": False,
     "task": "Two-station line. Station A: a UR10 robot picks parts and drops them in a bin. "
             "Station B: a Franka robot stacks parts into a vertical column."},
    {"id": "franka-2op", "gt": {"CP-01", "CP-08"}, "gap": False,
     "task": "A Franka robot picks loose parts into a bin at one station, and a second Franka robot "
             "arranges parts into a flat grid on a pallet at the next station."},
    {"id": "sort+kit", "gt": {"CP-03", "CP-50"}, "gap": False,
     "task": "Station 1: a Franka sorts parts by colour into separate bins. Station 2: a Franka assembles "
             "a kit from parts."},
    {"id": "3stn-mixed", "gt": {"CP-73", "CP-08", "CP-13"}, "gap": False,
     "task": "Three stations. (1) a UR10 picks parts into a bin; (2) a Franka palletizes parts into a grid; "
             "(3) a Franka stacks parts into a column."},
    {"id": "gap-ur10-sort", "gt": set(), "gap": True,
     "task": "A single station where a UR10 robot sorts parts by colour into coloured bins."},
    # ---- HARDER: the explicit robot+op lexical shortcut fails here ----
    {"id": "robot-ambig", "gt": set(), "any_of": [{"CP-01", "CP-73"}],
     "forbid": {"CP-03", "CP-08", "CP-13", "CP-50"},
     "task": "A single station: a robot picks loose parts and drops them into a bin. (Robot unspecified — "
             "choose any catalog cell that performs this operation.)"},
    {"id": "over-compose", "gt": {"CP-01"}, "forbid": {"CP-73", "CP-03", "CP-08", "CP-13", "CP-50"},
     "task": "One station only: a Franka robot picks loose parts and drops them into a bin."},
    {"id": "op-discrim", "gt": {"CP-08"}, "forbid": {"CP-13"},
     "task": "A Franka robot arranges parts neatly in rows and columns lying FLAT on a pallet surface."},
    {"id": "gap-ur10-kit", "gt": set(), "gap": True,
     "task": "A single station where a UR10 robot assembles a kit from loose parts."},
    # ---- STRUCTURE: sequential (handoff chain) vs parallel (independent stations) ----
    {"id": "struct-seq-handoff", "gt": {"CP-73", "CP-13"}, "exp_structure": "sequential",
     "task": "A UR10 picks each part from a feeder and HANDS IT OFF to a Franka, which stacks the received "
             "parts into a column. The Franka works ONLY on parts the UR10 passes to it."},
    {"id": "struct-seq-line", "gt": {"CP-01", "CP-08"}, "exp_structure": "sequential",
     "task": "An in-line process: a Franka picks each incoming part into a tote, and the SAME parts then move "
             "to a second Franka that palletizes them into a grid. Output of stage 1 IS the input of stage 2."},
    {"id": "struct-par-indep", "gt": {"CP-03", "CP-01"}, "exp_structure": "parallel",
     "task": "Two INDEPENDENT cells side by side with NO connection: cell 1 a Franka colour-sorts parts into "
             "bins; cell 2 a Franka picks unrelated parts into a bin. No part ever moves between them."},
    # ---- IMPLIED structure (no explicit 'handoff'/'independent' words — infer from the flow) ----
    {"id": "imp-seq-down", "gt": {"CP-01", "CP-50"}, "exp_structure": "sequential",
     "task": "A Franka picks raw parts onto a staging tray; a downstream Franka assembles those parts into a "
             "finished kit."},
    {"id": "imp-par-elsew", "gt": {"CP-03", "CP-08"}, "exp_structure": "parallel",
     "task": "A Franka colour-sorts loose widgets at the inspection bay; elsewhere on the floor another Franka "
             "palletizes finished crates into a grid."},
]


async def _run(model, only=None):
    prov = GeminiProvider(api_key=os.environ["GEMINI_API_KEY"], model=model)
    rows = []
    for c in CASES:
        if only and not c["id"].startswith(only):
            continue
        prompt = f"Available work-cells:\n{CATALOG}\n\nTask: {c['task']}"
        try:
            resp = await prov.complete([{"role": "user", "content": prompt}], {"system_override": SYS})
            txt = (resp.text or "").strip()
        except Exception as e:
            txt = f"ERROR {e}"
        picks = set(re.findall(r"CP-\d+", txt.split('"reasoning"')[0] if '"reasoning"' in txt else txt))
        picks &= _AVAIL  # only count real catalog ids
        flagged_gap = '"gaps"' in txt and bool(re.search(r'"gaps"\s*:\s*\[\s*"[^"]', txt))
        _sm = re.search(r'"structure"\s*:\s*"(sequential|parallel)"', txt)
        struct = _sm.group(1) if _sm else None
        if c.get("gap", False):
            # PASS = flagged the gap AND did NOT confidently pick a (necessarily wrong) cell
            ok = flagged_gap and not picks
            verdict = "PASS" if ok else ("FALSE-PICK" if picks else "NO-GAP-FLAG")
        else:
            forbid_hit = picks & c.get("forbid", set())
            must_ok = c["gt"] <= picks
            anyof_ok = all(bool(picks & grp) for grp in c.get("any_of", []))
            struct_ok = (c.get("exp_structure") is None) or (struct == c["exp_structure"])
            blocks_ok = must_ok and anyof_ok and not forbid_hit
            ok = blocks_ok and struct_ok
            allowed = set(c["gt"])
            for grp in c.get("any_of", []):
                allowed |= grp
            extras = picks - allowed
            verdict = (("FORBID-HIT" if forbid_hit else ("STRUCT-MISS" if (blocks_ok and not struct_ok) else "MISS"))
                       if not ok else ("PASS" if not extras else "OK+EXTRA"))
        rows.append({"id": c["id"], "verdict": verdict, "picks": sorted(picks),
                     "gt": sorted(c["gt"]), "gap_flag": flagged_gap, "structure": struct, "ok": ok})
        _exp = ("gap" if c.get("gap", False) else f"gt={sorted(c['gt'])}"
                + (f" any{[sorted(g) for g in c['any_of']]}" if c.get("any_of") else "")
                + (f" forbid={sorted(c['forbid'])}" if c.get("forbid") else "")
                + (f" struct={c['exp_structure']}(got={struct})" if c.get("exp_structure") else ""))
        print(f"  {c['id']:16s} {verdict:12s} picks={sorted(picks)}  {_exp}")
    n_ok = sum(r["ok"] for r in rows)
    print(f"\nCOMPOSE-REASON: {n_ok}/{len(rows)} cases OK (model={model})")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-robotics-er-1.6-preview")
    ap.add_argument("--only", default=None, help="run only cases whose id startswith this (e.g. 'struct-')")
    a = ap.parse_args()
    print(f"catalog: {sorted(_AVAIL)}")
    asyncio.run(_run(a.model, a.only))
