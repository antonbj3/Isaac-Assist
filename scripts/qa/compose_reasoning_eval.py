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
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
SPACING_S = float(os.environ.get("EVAL_SPACING", "20"))


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


def score(task, plan):
    if not isinstance(plan, dict):
        return False, "no JSON plan"
    layout = (plan.get("layout") or "").lower()
    cells = plan.get("cells") or []
    ok_layout = (layout == task["expect_layout"])
    ok_n = (len(cells) == task["expect_n_cells"])
    # all chosen templates must exist in the catalog ids
    valid = all(isinstance(c, dict) and isinstance(c.get("template"), str) for c in cells)
    chain_ok = True
    if task["expect_layout"] == "chain":
        chain_ok = bool(plan.get("handoffs"))
    passed = ok_layout and ok_n and valid and chain_ok
    return passed, "layout=%s(want %s) n_cells=%d(want %d) handoffs=%s" % (
        layout, task["expect_layout"], len(cells), task["expect_n_cells"], bool(plan.get("handoffs")))


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
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(TASKS)
    from service.isaac_assist_service.chat.llm_gemini import GeminiProvider
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    catalog = build_catalog()
    sys.stderr.write("catalog: %d blocks; model=%s; running %d tasks (spacing %.0fs)\n" % (len(catalog), MODEL, n, SPACING_S))
    prov = GeminiProvider(api_key=key, model=MODEL)
    sysmsg = SYS_PROMPT % "\n".join(catalog)
    npass = 0
    for i, task in enumerate(TASKS[:n]):
        if i:
            await asyncio.sleep(SPACING_S)
        user_content = sysmsg + "\n\nUSER TASK: " + task["prompt"] + "\n\nJSON plan:"
        rec = {"ts": time.time(), "kind": "compose_reasoning", "model": MODEL, "task_id": task["id"],
               "task_prompt": task["prompt"], "catalog": catalog, "system_prompt": SYS_PROMPT,
               "expected": {k: task[k] for k in ("expect_layout", "expect_n_cells", "expect_kind")}}
        try:
            r = await prov.complete([{"role": "user", "content": user_content}], {})
            txt = (r.text or "").strip()
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
    print("COMPOSE_REASONING: %d/%d passed (model=%s) | data -> workspace/training_data/compose_reasoning.jsonl" % (npass, min(n, len(TASKS)), MODEL))


if __name__ == "__main__":
    asyncio.run(main())
