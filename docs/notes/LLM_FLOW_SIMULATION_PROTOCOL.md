# LLM-flow simulation protocol — plan (2026-06-15)

Anton's direction: test the PRODUCT flow — user task (natural language) → LLM (Gemini)
reasons → retrieves/reads templates → composes/instantiates a scene + actions →
(verifies with scene_eyes). This is the END GOAL of the canonical-library effort.
Crucially **Kit-free parts run in PARALLEL with serial Kit work** (the parallel unlock).

## CP07xCP27 — architecture answer (Anton's clarification)
Anton asked: do I pre-author named compositions ("CP07xCP27"), or does the LLM build
new scenes from user input? **Answer: runtime LLM capability, not a pre-authored O(N²)
library.** The LLM decomposes the task → retrieves a robust block per sub-task → calls a
`compose(blocks, layout)` capability that auto-handles namespacing + scene-extent-aware
spacing + handoff wiring. Validated compositions MAY be cached/named for reuse, but the
primary model is runtime composition (pre-creating all pairs doesn't scale or generalize).
(Design-review workflow wq0t4ee5i is stress-testing this; refine on its return.)

## What ALREADY EXISTS (ground here, don't rebuild)
- **scripts/qa/retrieval_eval_harness.py** — KIT-FREE. Calls the REAL orchestrator retrieval:
  produce_layout_spec_from_text (text→intent) → retrieve_with_intent_soft_filter (prod) →
  confidence gate (top_sim≥0.45 & margin≥0.20). Scratch-index isolated. == "which templates
  does the LLM read for a task + how does it score" = the retrieval half of the protocol.
- **scripts/qa/retrieval_eval_set.json** — 33 cases: {id, prompt, ground_truth[], 
  acceptable_alternatives[], hard_negatives[], difficulty, pattern_hint, category,
  complexity, intent_dimensions}. == the task-suite Anton described. Mostly ATOMIC (1 template).
- **service/isaac_assist_service/chat/llm_gemini.py** — Gemini backend, supports Gemini 3.x
  (thoughtSignature round-trip), default model "gemini-robotics-er-1.6-preview"; any v1beta
  model via the `model` param (so gemini-3.1 / flash-2.5 = a model-name switch).
- **scripts/direct_eval.py / scripts/qa/{judge_session,auto_judge,multi_turn_session,
  launch_campaign,ground_truth_judge}.py** — the eval/judge ecosystem (full LLM tool-calling
  runs; these DO need Kit for scene execution).
- **scene_eyes.py --compose** — NEW (cont.65): observes composed scenes. Should become an
  LLM-callable tool (Anton).

## GAPS to close for Anton's full vision
1. **Composition eval cases**: the 33-case set is atomic. Add MULTI-template cases
   (e.g. "two pick-place stations side by side" → ground_truth [CP-01, CP-01] composed;
   "pick from a conveyor then stack on a pallet" → chain CP-07→CP-13). Tests whether the
   LLM DECOMPOSES + composes, not just single-template retrieval.
2. **scene_eyes as an LLM tool**: expose a `observe_scene`/`scene_eyes` tool in
   chat/tools/tool_schemas.py so Gemini can call it to verify its own scene (currently only
   referenced in a diagnostics tool description, NOT a callable tool).
3. **Gemini 3.1 / flash-2.5 switch**: wire the model name through (where the provider is
   instantiated). A/B old vs new model on the eval set.
4. **Reasoning observability**: capture, per case — which templates retrieved (+scores),
   which the LLM selected, its reasoning/tool-call trace, what it logged. Retrieval harness
   gives retrieval; full reasoning needs the tool-calling run (judge_session / direct_eval).

## SAFETY / parallelization constraints
- **ChromaDB**: froze the machine 2x (parallel writes / pytest-against-dirs). Sentinel
  ~/.no_local_chroma_tests exists. The retrieval harness does a single scratch rebuild (447
  embeds) — low compute but machine-freeze downside = lose the session. RUN IT IN A CAREFUL,
  WATCHED WINDOW (hard timeout, background, single-process), NOT blindly. base `python3`
  (miniconda) has chromadb; isaac_lab_env does NOT.
- **Kit is serial**: retrieval (ChromaDB) + reasoning/composition (Gemini, if candidate
  templates are fed DIRECTLY, bypassing retrieval) are Kit-free → parallel with serial Kit.
  Only final scene execution + scene_eyes verification need Kit.
- **Split that maximizes parallel-safe testing**: (a) retrieval quality [ChromaDB, careful];
  (b) compose-reasoning [Gemini given candidate blocks, no ChromaDB, no Kit] — does it pick
  the right blocks + layout?; (c) end-to-end [needs Kit, serial].

## Sequenced plan
1. [safe, file-only] Add composition eval cases to the eval set (gap #1).
2. [safe, file-only] Expose scene_eyes as an LLM tool (gap #2) + Gemini model-switch plumbing (gap #3).
3. [careful window] Run retrieval_eval_harness baseline (current model) → retrieval quality on 33 + new composition cases.
4. [Gemini, no Kit] compose-reasoning eval: feed Gemini a task + candidate blocks, score its decomposition/layout choice (gap #4, observability).
5. [Kit, serial] end-to-end on a few cases with scene_eyes verification.
Incorporate design-review workflow (wq0t4ee5i) findings into 1-2 (interface shape).

## TRAINING DATA — save all LLM-flow data (Anton 2026-06-15)
Goal: train our OWN model later on the (task -> tool-call plan / USD-code) abstraction(s). So SAVE
ALL DATA from every LLM-flow interaction. Convention: append JSONL to `workspace/training_data/*.jsonl`
(one JSON object per interaction: full system+user prompt, catalog, raw model response, parsed plan,
score, model, ts). Any LLM-flow tool MUST write here.

KEY INSIGHT — the canonical library is ALREADY a training dataset at TWO abstraction levels:
  (1) tool-call level: each template's `code` = a (goal -> ordered tool-call sequence) example
      (create_bin/robot_wizard/setup_pick_place_controller/...). 70 verified-core = 70 clean examples.
  (2) USD-code level: the same code executed = the (goal -> USD scene mutation) example.
Composition ADDS the next level: (composite task -> build_composed_scene plan = cells+topology+handoffs
-> the composed tool-call sequence). compose_reasoning_eval.py captures (composite task -> plan) pairs.
So the dataset to assemble: per template {goal, tool_calls(from code), usd_effect}; per composition
{task, plan, composed_tool_calls}; per LLM-flow run {prompt, response, score} — all to training_data/.

## First result (2026-06-15)
compose_reasoning_eval.py T1 (gemini-2.5-flash): PASS — "two pick-place stations side by side" ->
['CP-01','CP-01'] parallel (correct). Data saved. Gemini quota is TIGHT (free-tier per-minute 429) ->
runs are spaced (asyncio.sleep) + small. Catalog = 40 verified-core blocks (goal + IO + curobo flag).

## CORPUS STATE — the TRUST LADDER (run `scripts/qa/dataset_manifest.py` for current counts)
Three tiers, scanned/generated never hand-counted (`workspace/dataset_manifest.json`):
  - `gold_verified_core`         L1  one canonical template, Kit-gate-verified to deliver (70).
  - `gold_kit_delivery_verified` L2  a COMPOSITION BUILT + measured to deliver FULL in Kit
                                     (compose_and_verify.py). Delivery-truth. 13 as of cont.94 (2-cell).
  - `candidate_heuristic`        --  a Gemini PLAN that passed structural + IO-semantic checks only
                                     (reasoning-truth, NOT delivery-verified). 65; this is the error-rate axis.
TWO error rates (Anton's framing): REASONING (does Gemini pick the right blocks+topology — measured by
compose_reasoning_eval, ~92% base / ~94% adversarial across the corpus, 8/8+8/8 at latest instructions)
vs DELIVERY (does the chosen composition actually deliver in Kit — measured by compose_and_verify; the
hard failures are contention + chain-handoff geometry, not block choice). Only Kit promotes candidate->gold.

## THE MEASURE MUST NOT LIE (cont.91-92) — applied to the pipeline itself
- ROUTING-AWARE + PER-CUBE-CORRECT-BIN: a sorter routes each cube to ITS designated bin (color in leaf
  name -> color_routing). Counting "any bin" fixed a false-NEGATIVE (2-color read 1/2) but opened a
  false-POSITIVE (both cubes in wrong bin = full); per-cube-correct closes both. CP-03 reads 2/2 under
  the STRICT measure -> genuine gold. Dedup on (ordered cells, layout) so re-runs RECONFIRM, not duplicate.

## REASONING HARNESS — boxing the error rate (cont.93)
compose_reasoning_eval has a BASE set (10 tasks, easy, 10/10) AND an ADVERSARIAL set (`EVAL_SET=adv`, 8
tasks) that probes block DISCRIMINATION (heterogeneous parallel must pick DIFFERENT block KINDS — graded
by set-cover over goal keywords), under/over-compose traps, ambiguous counts, and the bin-chain trap.
First adv run 7/8; the FAIL was a real physics-grounded error (model chained out of a deep bin =
unpickable, would deliver 0/N). A GENERAL 'physical-realizability over literal wording' rule in SYS_PROMPT
-> 8/8, no regression (CP-30 palletizer=FLAT handoff substituted, verified genuine). NOTE: this improved
instruction lives in the EVAL's SYS_PROMPT; promoting it to the PRODUCTION orchestrator SYSTEM_PROMPT is
the L5 composition-tool gap (gated on Anton's interface decisions — do NOT wire composition into prod
unilaterally).
