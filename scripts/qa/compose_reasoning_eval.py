#!/usr/bin/env python3
"""compose_reasoning_eval.py — LLM-flow simulation protocol (task #28), compose-reasoning half.

Tests the CORE product question: given a user task + a catalog of verified canonical blocks,
can the LLM (Gemini) DECOMPOSE the task and propose a correct build_composed_scene plan (which
blocks, what topology)? This is the LLM's CHOICE — evaluated against an expected answer — so it
needs NO Kit and NO ChromaDB (the candidate catalog is fed directly, bypassing retrieval). The
production tool (L5) doesn't need to exist yet; we score the PLAN the LLM emits.

Gemini quota is tight (free-tier per-minute) -> calls are SPACED with asyncio.sleep and the task
count is small. Run: GEMINI_MODEL=gemini-2.5-flash python scripts/qa/compose_reasoning_eval.py [N]
(N = how many tasks to run, default 3; keep small to respect quota).
"""
import asyncio, json, os, sys, glob

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPL_DIR = os.path.join(REPO, "workspace", "templates")
# Vertex AI (Anton's GCP credits, high rate-limits, no free-tier 429). Set BEFORE genai.Client();
# do NOT pass api_key= and POP the env keys (else the free Developer-API key is forced); LOCATION
# must be 'global' (us-central1 -> 404 on 3.x).
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "project-09efd25b-a906-474e-af1")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
SPACING_S = float(os.environ.get("EVAL_SPACING", "0"))


def build_catalog(limit=40):
    """Compact catalog of VERIFIED_CORE delivery blocks the LLM chooses from: id + one-line goal
    + in/out kind. Derived from template goals + the composition_hints cache."""
    hints_path = os.path.join(REPO, "workspace", "composition_hints.json")
    hints = json.load(open(hints_path))["hints"] if os.path.exists(hints_path) else {}
    cat = []
    for name in sorted(hints):
        try:
            t = json.load(open(os.path.join(TPL_DIR, name + ".json")))
        except Exception:
            continue
        goal = (t.get("goal") or "").strip().replace("\n", " ")
        if len(goal) > 130:
            goal = goal[:127] + "..."
        h = hints[name]
        ins = ",".join(sorted({p["kind"] for p in h.get("input_ports", [])})) or "-"
        outs = ",".join(p["name"] for p in h.get("output_ports", [])) or "-"
        cat.append(f"{name}: {goal} [in:{ins} out:{outs} curobo:{bool(h.get('exclusive_resources'))}]")
        if len(cat) >= limit:
            break
    return cat


TASKS = [
    {"id": "T1-parallel-2station",
     "prompt": "Set up TWO identical pick-and-place work cells side by side, each with a Franka arm picking cubes off its own conveyor and dropping them into its own bin. Run them at the same time.",
     "expect_layout": "parallel", "expect_n_cells": 2,
     "expect_kind": "two independent pick-place-to-bin cells"},
    {"id": "T2-single-not-compose",
     "prompt": "Build one cell where a Franka arm picks five cubes off a conveyor and stacks them into a single 5-cube tower.",
     "expect_layout": "single", "expect_n_cells": 1,
     "expect_kind": "ONE template (a 5-cube stacker) — should NOT over-compose"},
    {"id": "T3-chain-feed",
     "prompt": "I want a line where a first cell picks cubes off a conveyor and delivers them onto a flat handoff surface, and a SECOND cell then picks those same cubes from the handoff and stacks them. The second cell consumes the first cell's output.",
     "expect_layout": "chain", "expect_n_cells": 2,
     "expect_kind": "a chain: cell A delivers -> cell B sources A's output"},
    {"id": "T4-parallel-3station",
     "prompt": "Stand up THREE identical pick-and-place cells running at the same time, each a Franka picking cubes off its own conveyor into its own bin — a small parallel line of three.",
     "expect_layout": "parallel", "expect_n_cells": 3,
     "expect_kind": "three independent pick-place cells in parallel"},
    {"id": "T5-single-sort",
     "prompt": "Build ONE cell that picks cubes off a conveyor and sorts them by color into different bins.",
     "expect_layout": "single", "expect_n_cells": 1,
     "expect_kind": "ONE color-sorting template — not a composition"},
    {"id": "T6-chain-3stage",
     "prompt": "A three-stage line: cell 1 picks off a conveyor onto a handoff, cell 2 takes from there onto a second handoff, cell 3 takes from there and stacks. Each stage feeds the next.",
     "expect_layout": "chain", "expect_n_cells": 3,
     "expect_kind": "a 3-stage chain, each stage feeding the next"},
    {"id": "T7-single-palletize",
     "prompt": "Build one cell where a Franka palletizes cubes into a 2x2 grid on a pallet.",
     "expect_layout": "single", "expect_n_cells": 1,
     "expect_kind": "ONE palletizing template"},
]

SYS_PROMPT = """You are the scene-composition planner for a robotics system. You solve a user task by
COMPOSING verified canonical blocks (each block = a known-good robot work-cell). You do NOT write code
or coordinates — you choose WHICH blocks and WHAT topology; the system owns all spacing/wiring.

Emit ONLY a JSON object (no prose) for the tool build_composed_scene:
{
  "cells": [ {"id": "<short label>", "template": "<CP-NN block id from the catalog>"} ],
  "layout": "single" | "parallel" | "chain",
  "handoffs": [ {"from": "<cell id>", "to": "<cell id>"} ]   // only for chain; [] otherwise
}
Rules: use "single" + one cell when ONE block already does the whole task (do NOT over-compose).
Use "parallel" for independent cells running at once. Use "chain" when one cell's OUTPUT feeds the
next cell's INPUT (declare the handoff edges). Pick blocks whose goal matches each sub-task.

CATALOG (block: goal [in/out/curobo]):
%s
"""


def _hints():
    p = os.path.join(REPO, "workspace", "composition_hints.json")
    return json.load(open(p))["hints"] if os.path.exists(p) else {}


def io_semantic_check(plan):
    """For a CHAIN: does each handoff's FROM-cell output plausibly feed the TO-cell's input?
    Returns (ok, notes). Heuristic via the hints cache: gross mismatch = from delivers to a
    PALLET/TOWER (a terminal sink) while to expects a CONVEYOR feed, or object-count mismatch.
    This is a STRUCTURAL-SEMANTIC check (reasoning sanity), NOT proof — only compose_and_verify
    (Kit delivery) proves a chain CORRECT. Catches the CP-30(pallet)->CP-09(conveyor) class."""
    H = _hints()
    cells = {c.get("id"): c.get("template") for c in (plan.get("cells") or [])}
    notes = []
    ok = True
    for ho in (plan.get("handoffs") or []):
        ft, tt = cells.get(ho.get("from")), cells.get(ho.get("to"))
        fh, th = H.get(ft) or {}, H.get(tt) or {}
        fout = " ".join(p.get("name", "") for p in fh.get("output_ports", [])).lower()
        tn = (tt or "")
        # to-cell sources from a conveyor (its goal/inputs imply a belt) but from-cell delivers to a terminal sink
        terminal = any(w in fout for w in ("pallet", "tower", "bin", "tray"))
        tcode = ""
        try:
            tcode = (json.load(open(os.path.join(REPO, "workspace", "templates", tn + ".json"))).get("code") or "").lower()
        except Exception:
            pass
        to_needs_belt = ("create_conveyor" in tcode)
        n_from = (fh.get("n_objects") or 0); n_to = (th.get("n_objects") or 0)
        if terminal and to_needs_belt:
            ok = False
            notes.append("%s->%s: from delivers to a terminal sink (%s) but to expects a CONVEYOR feed" % (ft, tt, fout.strip()))
        if n_from and n_to and n_from != n_to:
            notes.append("%s->%s: object-count %d->%d mismatch" % (ft, tt, n_from, n_to))
    return ok, notes


def score(task, plan):
    if not isinstance(plan, dict):
        return False, "no JSON plan"
    layout = (plan.get("layout") or "").lower()
    cells = plan.get("cells") or []
    ok_layout = (layout == task["expect_layout"])
    ok_n = (len(cells) == task["expect_n_cells"])
    valid = all(isinstance(c, dict) and isinstance(c.get("template"), str) for c in cells)
    chain_ok = True
    sem_ok, sem_notes = True, []
    if task["expect_layout"] == "chain":
        chain_ok = bool(plan.get("handoffs"))
        sem_ok, sem_notes = io_semantic_check(plan)
    struct_passed = ok_layout and ok_n and valid and chain_ok
    # PASS now requires BOTH well-formed STRUCTURE and no gross IO-semantic mismatch (reasoning
    # sanity). Delivery-correctness still needs compose_and_verify (Kit).
    passed = struct_passed and sem_ok
    return passed, "layout=%s(want %s) n_cells=%d(want %d) handoffs=%s struct=%s sem=%s%s" % (
        layout, task["expect_layout"], len(cells), task["expect_n_cells"], bool(plan.get("handoffs")),
        struct_passed, sem_ok, (" | " + "; ".join(sem_notes)) if sem_notes else "")


def _save_record(rec):
    """SAVE ALL DATA (Anton 2026-06-15): every LLM-flow interaction -> a training-ready JSONL store,
    for later training a custom model on the (task -> tool-call plan / USD-code) abstraction. Append-
    only; one JSON object per line."""
    ddir = os.path.join(REPO, "workspace", "training_data")
    os.makedirs(ddir, exist_ok=True)
    with open(os.path.join(ddir, "compose_reasoning.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")


async def main():
    import time
    start = int(os.environ.get("EVAL_START", "0"))
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(TASKS)
    todo = TASKS[start:start + n]
    from google import genai
    client = genai.Client()   # Vertex (env set above)
    catalog = build_catalog()
    sys.stderr.write("catalog: %d blocks; model=%s (vertex); running %d tasks [%d:%d]\n" % (len(catalog), MODEL, len(todo), start, start + n))
    sysmsg = SYS_PROMPT % "\n".join(catalog)
    npass = 0
    for i, task in enumerate(todo):
        if i:
            await asyncio.sleep(SPACING_S)
        user_content = sysmsg + "\n\nUSER TASK: " + task["prompt"] + "\n\nJSON plan:"
        rec = {"ts": time.time(), "kind": "compose_reasoning", "model": MODEL, "task_id": task["id"],
               "task_prompt": task["prompt"], "catalog": catalog, "system_prompt": SYS_PROMPT,
               "expected": {k: task[k] for k in ("expect_layout", "expect_n_cells", "expect_kind")}}
        try:
            resp = client.models.generate_content(model=MODEL, contents=user_content)
            txt = (resp.text or "").strip()
            rec["raw_response"] = txt
            j0, j1 = txt.find("{"), txt.rfind("}")
            plan = json.loads(txt[j0:j1 + 1]) if j0 >= 0 and j1 > j0 else None
        except Exception as e:
            rec["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
            _save_record(rec)
            print("EVAL %s: ERR %s" % (task["id"], rec["error"][:120]))
            continue
        passed, detail = score(task, plan)
        npass += int(passed)
        rec["parsed_plan"] = plan
        rec["score_passed"] = passed
        rec["score_detail"] = detail
        _save_record(rec)
        chosen = [c.get("template") for c in (plan.get("cells") or [])] if isinstance(plan, dict) else None
        print("EVAL %s: %s | %s | chose=%s | expect=%s" % (
            task["id"], "PASS" if passed else "FAIL", detail, chosen, task["expect_kind"]))
    print("COMPOSE_REASONING: %d/%d passed (model=%s) | data -> workspace/training_data/compose_reasoning.jsonl" % (npass, len(todo), MODEL))


if __name__ == "__main__":
    asyncio.run(main())
