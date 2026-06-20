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
# cont.319mm (adversarial-sim NL-pick build): scope-clarifying op descriptions so the LLM matches natural intents
# (the grounded misses were "moving real belt"->conveyor-pick, "NIR material"->material-sort, "stands upright +
# reaches"->humanoid-stand-reach). The op-name alone under-cued the LLM; a one-line scope cue lifts intent-matching.
_DESC = {
    "ForkliftB:forklift-lift": "a forklift raises/lowers a loaded pallet on its lift mast",
    "Franka:barcode-sort": "sorts items by BARCODE/SKU into destination LANES (barcode scanner)",
    "Franka:color-sort": "sorts items by COLOUR into colour-matched bins",
    "Franka:conveyor-pick": "picks parts off a conveyor/belt feed (belt-fed, real or generated; the belt pauses at a proximity sensor for the pick) — use for ANY 'pick off a (moving) conveyor/belt' station",
    "Franka:inspect/vision": "inspects each item (vision/defect check) and routes pass vs reject",
    "Franka:kit/assembly": "assembles or kits parts into a fixture/kit tray",
    "Franka:material-sort": "sorts items by MATERIAL using a NIR/material sensor (metal/plastic/glass) into recycling bins",
    "Franka:palletize/grid": "places parts into a grid/pallet layout (palletising)",
    "Franka:pick-place-bin": "picks loose parts and drops them into a bin (basic pick-and-place)",
    "Franka:pick-place-real-object": "picks a REAL meshed product object (YCB box/can/brick) into a bin",
    "Franka:precision-pick": "precision pick of ONE part from tightly-packed neighbours into a tight-tolerance bin without disturbing the others",
    "Franka:size-weight-sort": "sorts items by PHYSICAL size and weight (bounding-box + force-torque) into heavy/light bins",
    "Franka:stack/column": "stacks parts into a vertical column/tower",
    "G1-humanoid:humanoid-arm": "a humanoid robot's arm reaches/actuates (free/low-gravity)",
    "G1-humanoid:humanoid-bimanual-reach": "a standing humanoid reaches with BOTH arms (bimanual)",
    "G1-humanoid:humanoid-stand-reach": "a humanoid robot STANDS UPRIGHT under gravity (fixed base) and reaches/places with its arm",
    "UR10:pick-place-bin": "a UR10 robot picks parts and drops them into a bin",
}
CATALOG = "\n".join(f"- {cp}: a {k.split(':',1)[0]} robot work-cell — {_DESC.get(k) or ('performs ' + k.split(':',1)[1])}"
                    for k, cp in sorted(_BLOCKS.items()) if cp)

SYS = ("You are a factory-scene COMPOSITION PLANNER. You build scenes by selecting pre-built robot work-cells "
       "from a fixed catalog and composing them. Decompose the task into sub-tasks; pick exactly ONE catalog "
       "cell per sub-task, matching BOTH the robot family AND the operation. If NO catalog cell fits a sub-task, "
       "do NOT substitute a wrong-robot or wrong-operation cell — instead list that sub-task in \"gaps\". "
       "Also classify the composition STRUCTURE: 'sequential' if the cells form a HANDOFF CHAIN (one cell's "
       "output part becomes the next cell's input), or 'parallel' if the cells are INDEPENDENT side-by-side "
       "stations with no part handoff between them. "
       "CRITICAL structure rule: the mere presence of 'Station 1'/'Station 2', numbering, or ordering words "
       "does NOT by itself make it sequential. Classify 'sequential' ONLY when a PHYSICAL part handled by one "
       "cell is then HANDED TO and handled by the next cell. If each cell processes its OWN separate/unrelated "
       "parts with nothing crossing between cells, it is 'parallel' even when the stations are numbered or "
       "listed in order. Ask: does a part LEAVE cell A and ENTER cell B? If no -> parallel. "
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
    # cont.319kk-s: the new attr-routed DIVERT operations (barcode-sort / material-sort) entered canonical_blocks
    # this session — discriminate them from colour-sort (forbid CP-03) so the LLM picks the RIGHT sensor/operation.
    {"id": "sortdiv-barcode", "gt": {"CP-NEW-barcode-scanner-divert"}, "forbid": {"CP-03"},
     "task": "A Franka station scans each package's BARCODE and diverts it by SKU to one of three output LANES "
             "(barcode/SKU sortation, NOT colour sorting)."},
    {"id": "sortdiv-material", "gt": {"CP-NEW-nir-material-divert"}, "forbid": {"CP-03"},
     "task": "A Franka station uses a NIR material sensor to sort items by MATERIAL — metal, plastic, glass — "
             "into recycling bins (material recycling sortation, NOT colour sorting)."},
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
    # ---- REAL-OBJECT reasoning (cont.319m): the catalog now has a real-object cell (CP-YCB-01C) distinct from
    # the generic primitive-cube pick-place (CP-01). Does the LLM pick the real-object cell when the task is
    # explicitly about real meshed product items (not primitive blocks)? ----
    {"id": "real-object", "gt": {"CP-YCB-01C"},
     "task": "A single Franka station that picks REAL meshed product items off a conveyor — actual cracker "
             "boxes, soup cans and foam bricks (scanned/meshed warehouse objects, NOT primitive cube blocks) — "
             "and drops them into a bin."},
    # ---- NEW REAL-ASSET / ROBOT-CLASS blocks (cont.319hh): does the LLM compose the new conveyor / forklift /
    # humanoid blocks that just entered canonical_blocks? (the strategy END GOAL extended to the new blocks) ----
    {"id": "real-conveyor", "any_of": [{"CP-CONV-02"}, {"CP-01"}], "gt": set(),
     "task": "A station where a Franka robot picks parts off a MOVING REAL conveyor belt (an actual Isaac "
             "ConveyorBelt asset) as they arrive at a pick-zone, and drops them into a bin."},
    {"id": "forklift-lift", "gt": {"CP-FORK-01"},
     "task": "A materials-handling station where a FORKLIFT truck raises its fork (lift mast) to lift a load."},
    {"id": "humanoid-reach", "any_of": [{"CP-G1-ARM-01"}, {"CP-G1-STAND-01"}], "gt": set(),
     "task": "A station where a HUMANOID robot actuates its arm to reach out toward an object."},
    {"id": "humanoid-stand", "gt": {"CP-G1-STAND-01"},
     "task": "A station where a HUMANOID robot STANDS UPRIGHT under gravity (fixed base) and reaches its arm "
             "toward an object on a table in front of it."},
]


def _is_overload(txt):
    """cont.319mm (instrument-lies guard): Gemini occasionally returns a 200-OK BODY that is an overload apology
    ('trouble reaching my reasoning backend ... try again'), NOT a composition. Detecting it lets the eval RETRY +
    NOT count it as a real MISS (the diagnostik-först raw-read caught 3 false-MISSes that were pure overload-errors)."""
    t = (txt or "").lower()
    return ("trouble reaching my reasoning backend" in t or "upstream service overloaded" in t
            or "try again in a moment" in t or ("overloaded" in t and "cp-" not in t))


async def _eval_once(prov, c):
    """One LLM attempt at one case -> a result dict (id/verdict/picks/structure/ok)."""
    prompt = f"Available work-cells:\n{CATALOG}\n\nTask: {c['task']}"
    txt = ""
    for _att in range(4):   # Gemini sometimes 200-OKs an 'upstream overloaded, try again' body -> retry, don't MISS
        try:
            resp = await prov.complete([{"role": "user", "content": prompt}], {"system_override": SYS})
            txt = (resp.text or "").strip()
        except Exception as e:
            txt = f"ERROR {e}"
        if not _is_overload(txt):
            break
        await asyncio.sleep(3 * (_att + 1))
    overloaded = _is_overload(txt)
    if os.environ.get("EVAL_RAW"):
        print(f"  RAW[{c['id']}]: {txt[:400]}")
    picks = set(re.findall(r"CP-[A-Za-z0-9][A-Za-z0-9-]*", txt.split('"reasoning"')[0] if '"reasoning"' in txt else txt))
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
        # any_of = OR over acceptable answer-SETS: PASS if picks satisfy AT LEAST ONE group
        # (e.g. humanoid-reach accepts CP-G1-ARM-01 OR CP-G1-STAND-01). cont.319ii-7 BUGFIX:
        # was all(picks & grp) -> required EVERY group matched (AND), which false-MISSed a
        # correct single pick (the LLM picked CP-G1-ARM-01, scored MISS). Empty any_of -> True.
        anyof_ok = (not c.get("any_of")) or any(grp <= picks for grp in c["any_of"])
        struct_ok = (c.get("exp_structure") is None) or (struct == c["exp_structure"])
        blocks_ok = must_ok and anyof_ok and not forbid_hit
        ok = blocks_ok and struct_ok
        allowed = set(c["gt"])
        for grp in c.get("any_of", []):
            allowed |= grp
        extras = picks - allowed
        verdict = (("FORBID-HIT" if forbid_hit else ("STRUCT-MISS" if (blocks_ok and not struct_ok) else "MISS"))
                   if not ok else ("PASS" if not extras else "OK+EXTRA"))
    if overloaded:
        verdict, ok = "OVERLOAD", None   # transient Gemini overload, NOT a real miss — excluded from the pass-rate
    return {"id": c["id"], "verdict": verdict, "picks": sorted(picks),
            "gt": sorted(c["gt"]), "gap_flag": flagged_gap, "structure": struct, "ok": ok, "overloaded": overloaded}


async def _run(model, only=None, retries=0):
    prov = GeminiProvider(api_key=os.environ["GEMINI_API_KEY"], model=model)
    rows = []
    for c in CASES:
        if only and not c["id"].startswith(only):
            continue
        r = await _eval_once(prov, c)
        flaky = False
        # LLM nondeterminism: a single-shot MISS can be FLAKINESS not a real gap (op-discrim flaky-misses ~1/4,
        # cont.319y — an occasional empty/malformed pick). Retry a MISS up to `retries` times; if ANY retry passes
        # it is FLAKY-PASS. A REAL gap fails all retries. This stops a flaky-miss being misread as a regression.
        if (r["ok"] is False) and retries > 0:
            for _ in range(retries):
                r2 = await _eval_once(prov, c)
                if r2["ok"]:
                    r = r2; flaky = True; break
        r["flaky"] = flaky
        rows.append(r)
        _exp = ("gap" if c.get("gap", False) else f"gt={sorted(c['gt'])}"
                + (f" any{[sorted(g) for g in c['any_of']]}" if c.get("any_of") else "")
                + (f" forbid={sorted(c['forbid'])}" if c.get("forbid") else "")
                + (f" struct={c['exp_structure']}(got={r['structure']})" if c.get("exp_structure") else ""))
        print(f"  {c['id']:16s} {r['verdict']:12s} picks={r['picks']}  {_exp}{' (FLAKY-PASS on retry)' if flaky else ''}")
    n_ok = sum(1 for x in rows if x["ok"])
    n_scored = sum(1 for x in rows if x["ok"] is not None)   # exclude transient OVERLOAD cases from the denominator
    n_over = sum(1 for x in rows if x.get("overloaded"))
    n_flaky = sum(1 for x in rows if x.get("flaky"))
    print(f"\nCOMPOSE-REASON: {n_ok}/{n_scored} cases OK (model={model})"
          + (f"  [{n_flaky} flaky-pass]" if n_flaky else "") + (f"  [{n_over} OVERLOAD-excluded]" if n_over else ""))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-2.5-flash")  # cont.319hh: robotics-er-1.6-preview + 2.0-flash quotas EXHAUSTED; gemini-2.5-flash has its own working quota (15/15 verified). Pass --model gemini-robotics-er-1.6-preview when its quota resets.
    ap.add_argument("--only", default=None, help="run only cases whose id startswith this (e.g. 'struct-')")
    ap.add_argument("--retries", type=int, default=0, help="retry a MISSED case up to N times; any pass -> FLAKY-PASS (filters LLM nondeterminism, e.g. op-discrim ~1/4 flaky-miss)")
    a = ap.parse_args()
    print(f"catalog: {sorted(_AVAIL)}")
    asyncio.run(_run(a.model, a.only, a.retries))
