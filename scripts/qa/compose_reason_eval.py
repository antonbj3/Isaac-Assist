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
       'Return ONLY JSON: {"cells":["CP-XX",...],"gaps":["..."],"reasoning":"one sentence"}.')

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
]


async def _run(model):
    prov = GeminiProvider(api_key=os.environ["GEMINI_API_KEY"], model=model)
    rows = []
    for c in CASES:
        prompt = f"Available work-cells:\n{CATALOG}\n\nTask: {c['task']}"
        try:
            resp = await prov.complete([{"role": "user", "content": prompt}], {"system_override": SYS})
            txt = (resp.text or "").strip()
        except Exception as e:
            txt = f"ERROR {e}"
        picks = set(re.findall(r"CP-\d+", txt.split('"reasoning"')[0] if '"reasoning"' in txt else txt))
        picks &= _AVAIL  # only count real catalog ids
        flagged_gap = '"gaps"' in txt and bool(re.search(r'"gaps"\s*:\s*\[\s*"[^"]', txt))
        if c["gap"]:
            # PASS = flagged the gap AND did NOT confidently pick a (necessarily wrong) cell
            ok = flagged_gap and not picks
            verdict = "PASS" if ok else ("FALSE-PICK" if picks else "NO-GAP-FLAG")
        else:
            ok = c["gt"] <= picks
            verdict = "PASS" if (ok and picks == c["gt"]) else ("RECALL-OK+EXTRA" if ok else "MISS")
        rows.append({"id": c["id"], "verdict": verdict, "picks": sorted(picks),
                     "gt": sorted(c["gt"]), "gap_flag": flagged_gap, "ok": ok})
        print(f"  {c['id']:14s} {verdict:14s} picks={sorted(picks)} gt={sorted(c['gt'])} "
              f"{'gapflag='+str(flagged_gap) if c['gap'] else ''}")
    n_ok = sum(r["ok"] for r in rows)
    print(f"\nCOMPOSE-REASON: {n_ok}/{len(rows)} cases OK (model={model})")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-robotics-er-1.6-preview")
    a = ap.parse_args()
    print(f"catalog: {sorted(_AVAIL)}")
    asyncio.run(_run(a.model))
