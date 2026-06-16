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
# Vertex per-minute quota on gemini-3.5-flash is TIGHT (saw 429 RESOURCE_EXHAUSTED at ~3 back-to-back
# calls, cont.95). Space calls out by default so a run doesn't burn into 429 (which is an INFRA failure,
# NOT a reasoning failure — see _save_record / manifest, which separate errored records from fails).
SPACING_S = float(os.environ.get("EVAL_SPACING", "12"))


_TERMINAL_SINKS = ("bin", "bowl", "tray", "crate", "bucket", "tote", "hopper")
_FLAT_SURFACES = ("pallet", "tower", "base", "plate", "pad", "pedestal", "table", "marker")


def _io_kinds(name, t, h):
    """Make the IO explicit so the LLM can MATCH chain handoffs: where objects come FROM
    (the input source) and what kind of place they go TO (terminal container vs flat pickable
    surface). A chain needs to-cell.input compatible with from-cell.output."""
    code = (t.get("code") or "")
    src = "conveyor" if "create_conveyor" in code else ("known-positions/surface" if not h.get("input_ports") else "surface")
    outs = [p["name"] for p in h.get("output_ports", [])]
    sink = "-"
    if outs:
        nm = outs[0].lower()
        if any(w in nm for w in _TERMINAL_SINKS):
            sink = "%s (TERMINAL container — hard to pick back out)" % outs[0]
        elif any(w in nm for w in _FLAT_SURFACES):
            sink = "%s (FLAT pickable surface — good chain handoff)" % outs[0]
        else:
            sink = outs[0]
    return src, sink


def build_catalog(limit=None):
    """Compact catalog of VERIFIED_CORE delivery blocks the LLM chooses from: id + one-line goal
    + EXPLICIT IO (consumes-from / delivers-to kind) so chain handoffs can be matched. CATALOG_LIMIT
    env caps it; default = ALL verified-core (realistic block-selection / discrimination difficulty)."""
    if limit is None:
        limit = int(os.environ.get("CATALOG_LIMIT", "999"))
    hints_path = os.path.join(REPO, "workspace", "composition_hints.json")
    hints = json.load(open(hints_path))["hints"] if os.path.exists(hints_path) else {}
    # TRUSTED-ONLY (2026-06-15): the reasoning LLM must compose from scene_eyes-VERIFIED blocks, not the
    # position-gate-trusted 70 (which included CP-09's scatter false-success + the partials). Filter by the
    # composable-block registry: keep only verdicts starting GENUINE/TRUSTED. Set TRUSTED_ONLY=0 to disable.
    trusted = None
    reg_path = os.path.join(REPO, "workspace", "composable_blocks.json")
    if os.environ.get("TRUSTED_ONLY", "1") == "1" and os.path.exists(reg_path):
        allb = json.load(open(reg_path)).get("all", {})
        trusted = {n for n, b in allb.items() if str(b.get("verdict", "")).startswith(("GENUINE", "TRUSTED"))}
    cat = []
    for name in sorted(hints):
        if trusted is not None and name not in trusted:
            continue   # exclude scene_eyes-false / partial / pending blocks from the LLM's choices
        try:
            t = json.load(open(os.path.join(TPL_DIR, name + ".json")))
        except Exception:
            continue
        goal = (t.get("goal") or "").strip().replace("\n", " ")
        if len(goal) > 120:
            goal = goal[:117] + "..."
        h = hints[name]
        src, sink = _io_kinds(name, t, h)
        n = h.get("n_objects", 0)
        cat.append(f"{name}: {goal} || CONSUMES: {n} objects from {src} -> DELIVERS to: {sink} | curobo={bool(h.get('exclusive_resources'))}")
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
    # ── harder / edge cases to box in the real error rate (the easy ones all pass) ──
    {"id": "T8-parallel-5station",
     "prompt": "Stand up a row of FIVE identical pick-and-place cells, all running at once, each a Franka picking cubes off its own conveyor into its own bin.",
     "expect_layout": "parallel", "expect_n_cells": 5,
     "expect_kind": "five independent pick-place cells in parallel"},
    {"id": "T9-elaborate-single",
     "prompt": "Build a cell that picks cubes off a conveyor, identifies each cube's color, and routes it into the matching colored bin — a single color-sorting station.",
     "expect_layout": "single", "expect_n_cells": 1,
     "expect_kind": "ONE color-sort station — elaborate but still a single block, do NOT over-compose"},
    {"id": "T10-deepbin-chain-trap",
     "prompt": "Make a two-stage line: the first cell delivers cubes, and a second cell then picks those delivered cubes and stacks them into a tower. The handoff between them must be physically pickable.",
     "expect_layout": "chain", "expect_n_cells": 2,
     "expect_kind": "chain whose FIRST cell delivers onto a FLAT pickable surface (NOT a deep bin) so stage 2 can pick"},
]

# ── ADVERSARIAL set: designed to FIND the reasoning error boundary (the base set passes 10/10, so
# it does NOT box the error rate — Anton's 'ruta in felprocenten'). These probe block DISCRIMINATION
# (pick the right KIND per cell, not identical copies), under-/over-composition traps with misleading
# phrasing, ambiguous counts, and heterogeneous parallel. expect_goal_keywords = set-cover of block
# KINDS each plan must include (graded against the chosen blocks' goals). Run: EVAL_SET=adv.
ADV_TASKS = [
    {"id": "A1-hetero-sort+stack",
     "prompt": "I need two stations running side by side: one station sorts incoming cubes by color into colored bins, and the OTHER station stacks cubes into a tower. Two different jobs, at the same time.",
     "expect_layout": "parallel", "expect_n_cells": 2, "expect_kind": "HETEROGENEOUS parallel: one SORT cell + one STACK cell (must pick two DIFFERENT block kinds)",
     "expect_goal_keywords": [["sort", "color"], ["stack", "tower"]]},
    {"id": "A2-under-compose-line",
     "prompt": "Build a full processing line: cubes come in on a conveyor, get picked, and end up neatly placed in a bin. Just the one standard pick-and-place operation.",
     "expect_layout": "single", "expect_n_cells": 1, "expect_kind": "ONE pick-place block — 'full line' is rhetorical, do NOT over-compose"},
    {"id": "A3-three-different",
     "prompt": "Stand up three cells at once: the first sorts cubes by color, the second stacks cubes into a tower, the third palletizes cubes onto a pallet. All three run in parallel, each doing its own thing.",
     "expect_layout": "parallel", "expect_n_cells": 3, "expect_kind": "THREE heterogeneous parallel cells: sort + stack + palletize (three different kinds)",
     "expect_goal_keywords": [["sort", "color"], ["stack", "tower"], ["pallet", "palletiz"]]},
    {"id": "A4-ambiguous-count-parallel",
     "prompt": "Set up a couple of identical pick-and-place cells running together, each Franka feeding its own bin off its own conveyor.",
     "expect_layout": "parallel", "expect_n_cells": 2, "expect_kind": "'a couple' = 2 identical pick-place cells in parallel"},
    {"id": "A5-chain-sort-then-stack",
     "prompt": "A two-stage line: stage one picks cubes off a conveyor and lays them out on a flat handoff surface; stage two then picks those same cubes from the surface and stacks them into a tower. Stage two consumes stage one's output.",
     "expect_layout": "chain", "expect_n_cells": 2, "expect_kind": "chain: upstream delivers to FLAT surface, downstream STACKS from it",
     "expect_goal_keywords": [["stack", "tower", "pick", "place"]]},
    {"id": "A6-single-palletize-disguised",
     "prompt": "I want cubes arranged into a tidy 3x3 grid layer on a pallet by a single robot arm. Standard palletizing.",
     "expect_layout": "single", "expect_n_cells": 1, "expect_kind": "ONE palletizing block",
     "expect_goal_keywords": [["pallet", "palletiz", "grid"]]},
    {"id": "A7-trap-bin-chain",
     "prompt": "Two-stage line where the first cell drops cubes into a bin, and a second cell then needs to pick those cubes and stack them. Chain the second after the first.",
     "expect_layout": "chain", "expect_n_cells": 2, "expect_kind": "TRAP: chaining out of a deep BIN is not physically pickable — a correct planner must avoid bin->pick handoff (io_semantic_check should flag it)"},
    {"id": "A8-hetero-2-parallel-pickplace+sort",
     "prompt": "Run two cells together: one plain pick-and-place into a bin, and one color-sorting cell that splits cubes into colored bins. Side by side, same time.",
     "expect_layout": "parallel", "expect_n_cells": 2, "expect_kind": "heterogeneous parallel: pick-place + color-sort (two different kinds)",
     "expect_goal_keywords": [["sort", "color"], ["pick", "place", "bin"]]},
    {"id": "A9-graduated-tower-fine-discrim",
     "prompt": "Build one cell where a single arm stacks 3 cubes into a TAPERED tower — each cube smaller than the one beneath it, so the tower narrows toward the top. A graduated stack, not a uniform one.",
     "expect_layout": "single", "expect_n_cells": 1, "expect_kind": "FINE discrimination: must pick the GRADUATED/mixed-SKU tower block (CP-15), NOT a generic uniform stacker",
     "expect_goal_keywords": [["graduat", "decreas", "taper", "mixed-sku", "smaller"]]},
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
Rules:
- "single" + one cell when ONE block already does the whole task (do NOT over-compose).
- "parallel" for independent cells running at once (no handoff).
- "chain" when one cell's OUTPUT feeds the next cell's INPUT — declare the handoff edges.

COUNT FROM THE WORDING: map vague quantity words to integers and emit that many cells — "a couple"/"a pair" = 2,
"a few"/"several" = 3, "a handful" = 4-5. Cues like "each <robot> feeding its OWN <thing>", "running together",
or a plural ("cells"/"stations") mean MULTIPLE cells in parallel, not one. Do NOT collapse "a couple of cells"
to a single cell — read the count from the strongest signal (an explicit number, an "each ... its own" phrase,
or a count word).

CHAIN MATCHING (critical — this is where most plans go wrong): in a chain, the downstream cell
SOURCES the upstream cell's DELIVERED objects (its own normal input source is bypassed). So the
upstream cell's DELIVERS-to must be a place the downstream cell can physically pick FROM:
  * Deliver onto a FLAT pickable surface (pallet/table/plate) -> the next cell CAN pick from it. GOOD.
  * Deliver into a TERMINAL container (bin/bowl/tray) -> objects are walled-in, the next cell CANNOT
    cleanly pick them back out. BAD chain handoff — avoid chaining out of a terminal container.
  * The object KIND and COUNT the upstream delivers must match what the downstream consumes.
Pick each block so the chain's output->input is physically realizable, not just topologically a line.
PHYSICAL REALIZABILITY OVER LITERAL WORDING: if the user's literal phrasing would force an
unrealizable handoff (e.g. "drop cubes into a bin, then a second cell picks them from the bin"),
do NOT comply literally — the walled bin makes the pick impossible. Choose an upstream block that
delivers onto a FLAT pickable surface instead, so the downstream can actually pick. A chain whose
upstream delivers into a terminal container is never a correct plan.

CATALOG (block: goal || CONSUMES n objects from <source> -> DELIVERS to: <sink kind> | curobo):
%s
"""


def _hints():
    p = os.path.join(REPO, "workspace", "composition_hints.json")
    return json.load(open(p))["hints"] if os.path.exists(p) else {}


_DEEP_CONTAINER = ("bin", "bowl", "tray", "crate", "bucket", "tote", "hopper")


def io_semantic_check(plan):
    """For a CHAIN: is each handoff PHYSICALLY realizable? The downstream cell's own input source
    (its conveyor) is BYPASSED — source_override rewires it to the upstream's DELIVERED objects. So
    the real constraint is the HANDOFF GEOMETRY (chain_gate-proven): the upstream cell must deliver
    onto a place the downstream arm can pick FROM. FLAT surfaces (pallet/tower/table/plate) = good;
    DEEP walled containers (bin/bowl/tray) = bad (objects walled-in, grip-vs-wall blow-up). Returns
    (ok, notes). HEURISTIC reasoning-sanity, NOT proof — only Kit delivery (chain_gate / compose_and_
    verify) proves a chain CORRECT."""
    H = _hints()
    cells = {c.get("id"): c.get("template") for c in (plan.get("cells") or [])}
    notes = []
    ok = True
    for ho in (plan.get("handoffs") or []):
        ft, tt = cells.get(ho.get("from")), cells.get(ho.get("to"))
        fh, th = H.get(ft) or {}, H.get(tt) or {}
        fout = " ".join(p.get("name", "") for p in fh.get("output_ports", [])).lower()
        deep = any(w in fout for w in _DEEP_CONTAINER)
        if deep:
            ok = False
            notes.append("%s->%s: from delivers into a DEEP container (%s) — walled, next cell can't pick back out (chain_gate: needs a FLAT handoff surface)" % (ft, tt, fout.strip()))
        n_from = (fh.get("n_objects") or 0); n_to = (th.get("n_objects") or 0)
        if n_from and n_to and n_from != n_to:
            notes.append("%s->%s: object-count %d->%d (downstream consumes a different count)" % (ft, tt, n_from, n_to))
    return ok, notes


_GOAL_CACHE = {}


def _goal(template):
    """Lower-cased goal text for a chosen block (for block-SELECTION grading: did the LLM pick the
    right KIND of block per cell, not just the right count?)."""
    if template not in _GOAL_CACHE:
        try:
            t = json.load(open(os.path.join(TPL_DIR, str(template) + ".json")))
            _GOAL_CACHE[template] = ((t.get("goal") or "") + " " + (t.get("name") or "") + " " + str(template)).lower()
        except Exception:
            _GOAL_CACHE[template] = ""
    return _GOAL_CACHE[template]


def _block_selection_ok(cells, keyword_groups):
    """SET-COVER: each keyword group must be satisfied by a DISTINCT chosen cell (greedy). A group is
    a list of synonyms; a cell satisfies it if its block goal contains ANY synonym. This grades
    heterogeneous compositions — e.g. 'one SORT cell + one STACK cell' must pick two different KINDS,
    not two identical stackers. Returns (ok, unmatched_groups)."""
    used = set()
    unmatched = []
    for grp in keyword_groups:
        hit = None
        for idx, c in enumerate(cells):
            if idx in used:
                continue
            g = _goal(c.get("template") if isinstance(c, dict) else None)
            if any(kw in g for kw in grp):
                hit = idx
                break
        if hit is None:
            unmatched.append("/".join(grp))
        else:
            used.add(hit)
    return (not unmatched), unmatched


def score(task, plan, valid_ids=None):
    if not isinstance(plan, dict):
        return False, "no JSON plan"
    layout = (plan.get("layout") or "").lower()
    cells = plan.get("cells") or []
    ok_layout = (layout == task["expect_layout"])
    ok_n = (len(cells) == task["expect_n_cells"])
    valid = all(isinstance(c, dict) and isinstance(c.get("template"), str) for c in cells)
    # HALLUCINATION GUARD: every chosen block must EXIST in the catalog. A made-up CP-NN is an
    # unambiguous failure (the system could not instantiate it) — catch it on ALL tasks, not just adv.
    halluc = []
    if valid_ids is not None:
        halluc = [c.get("template") for c in cells if isinstance(c, dict) and c.get("template") not in valid_ids]
        if halluc:
            valid = False
    chain_ok = True
    sem_ok, sem_notes = True, []
    if task["expect_layout"] == "chain":
        chain_ok = bool(plan.get("handoffs"))
        sem_ok, sem_notes = io_semantic_check(plan)
    # BLOCK-SELECTION grading (adversarial set): did the LLM pick the right KIND of block per cell?
    sel_ok, sel_notes = True, []
    kw = task.get("expect_goal_keywords")
    if kw:
        sel_ok, unmatched = _block_selection_ok(cells, kw)
        if unmatched:
            sel_notes.append("block-selection MISS — no cell covers: " + ", ".join(unmatched))
    struct_passed = ok_layout and ok_n and valid and chain_ok
    # PASS requires well-formed STRUCTURE, no gross IO-semantic mismatch, AND correct block KINDS
    # (when the task specifies them). Delivery-correctness still needs compose_and_verify (Kit).
    passed = struct_passed and sem_ok and sel_ok
    if halluc:
        sel_notes.append("HALLUCINATED block id(s) not in catalog: " + ", ".join(map(str, halluc)))
    return passed, "layout=%s(want %s) n_cells=%d(want %d) handoffs=%s struct=%s sem=%s sel=%s%s" % (
        layout, task["expect_layout"], len(cells), task["expect_n_cells"], bool(plan.get("handoffs")),
        struct_passed, sem_ok, sel_ok, (" | " + "; ".join(sem_notes + sel_notes)) if (sem_notes or sel_notes) else "")


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
    eval_set = os.environ.get("EVAL_SET", "base").lower()
    pool = {"base": TASKS, "adv": ADV_TASKS, "all": TASKS + ADV_TASKS}.get(eval_set, TASKS)
    start = int(os.environ.get("EVAL_START", "0"))
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(pool)
    todo = pool[start:start + n]
    from google import genai
    client = genai.Client()   # Vertex (env set above)
    catalog = build_catalog()
    valid_ids = {c.split(":", 1)[0].strip() for c in catalog}   # for the hallucination guard in score()
    sys.stderr.write("set=%s catalog: %d blocks; model=%s (vertex); running %d tasks [%d:%d]\n" % (eval_set, len(catalog), MODEL, len(todo), start, start + n))
    sysmsg = SYS_PROMPT % "\n".join(catalog)
    npass = 0
    for i, task in enumerate(todo):
        if i:
            await asyncio.sleep(SPACING_S)
        user_content = sysmsg + "\n\nUSER TASK: " + task["prompt"] + "\n\nJSON plan:"
        rec = {"ts": time.time(), "kind": "compose_reasoning", "eval_set": eval_set,
               "verification_tier": "candidate_heuristic",  # Gemini PLAN; passed structural+IO-semantic only — NOT Kit-delivery-verified
               "model": MODEL, "task_id": task["id"],
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
        passed, detail = score(task, plan, valid_ids=valid_ids)
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
