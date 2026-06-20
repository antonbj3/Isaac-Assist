# Isaac Assist — Honest Capability Map (2026-06-20)

A single-page, honest map of what the system is, what it genuinely does, and where its real edges are.
Written during an infra block (Bash classifier + Gemini quota both down) — consolidates the chronological
PROGRESS LOG into a readable reference. Answers Anton's "what is this / how does it handle X".

## What it IS
A system where a user **describes a robot factory cell in plain language (any language — Gemini bridges it)**
and it **builds + runs + verifies** that cell in NVIDIA Isaac Sim. Not an LLM I'm training — a SYSTEM that
USES an off-the-shelf LLM as the language/reasoning brain, on top of a verified robot-simulation block library.

## Architecture (two parts)
1. **Composition core** (deterministic, Kit-grounded):
   - `workspace/templates/` — ~478 templates; `composable_blocks.json` canonical_blocks = the verified work-cells.
   - `service/.../chat/composer.py` — namespaces + offsets cells so they don't collide (compute_layout_offsets,
     template_footprint, precondition_check), chain handoff wiring (apply_source_override).
   - `scripts/qa/` gates — scene_eyes (RAW per-object measurement), chain_xkit_gate, compose_and_verify,
     compose_gate, the robustness gates. **These are TEST gates, not the product.**
2. **Agentic harness** (the product's reasoning layer) — `service/isaac_assist_service/chat/`:
   - `ChatOrchestrator.handle_message` — a multi-turn **tool-calling LLM loop** (intent → distill → tool-call →
     honesty rewrite). LLM-agnostic (Gemini / Anthropic / OpenAI / Ollama).
   - **~400 LLM-callable tools** incl. grounded reasoning: `diagnose_scene_feasibility`, `check_singularity`,
     `check_collisions`, `solve_ik`, `plan_trajectory`, `grasp_object`, `define_grasp_pose`,
     `resolve_constraint_phrase`/`resolve_size_adjective`/`resolve_count_vagueness` (variable capture),
     `vision_analyze_scene`/`observe_scene`/`static_eyes` (perception).
   - `negotiator.py` — clarification gate (asks the user when a complex request is under-specified).
   - retrieval (tool_retriever/template_retriever/role_retriever), `tool_honesty`, `vision_gemini`.

## Capability boundary (honest)
- **GOLD (verified-working):** Franka full op-set (pick/place, grid/palletize, stack/column, color/barcode/NIR/
  size-weight sort, inspect, kit/assembly, conveyor-pick, real-object pick); parallel multi-cell compositions;
  sequential handoff CHAINS incl. robot-diversity (Franka↔UR10 both directions) + real-asset conveyor sources
  (FLAT / STACK / 3-stage), all re-confirmed with the fixed delivered_paths gate; honest end-to-end custody.
- **WALLED (controller/RL-deep, deferred as non-essential):** UR10 **multi-target STRUCTURED** placement (grid AND
  same-xy stack — baseline placement-precision ~0.1m); G1 humanoid **dex-grasp** (open-loop knocks the object →
  needs a learned policy); complex-mesh grasp (banana refuted). Honest negatives, documented.
- **GATED (infra, NOT a capability gap):** the agentic harness's reasoning-ORCHESTRATION quality (does the agent
  actually CALL diagnose_scene_feasibility on a slippery-cylinder request?) — untestable in THIS local env (only
  free-tier Gemini, quota-exhausted + 429-flaky; Ollama embed-only; no Anthropic/OpenAI key; full agent risks a
  ChromaDB freeze). A clean assessment needs the Modal container / a reliable backend.

## How it handles different scenarios (the constraint Anton flagged)
- New combination of EXISTING blocks → composes (the multiplier: N verified blocks → many verified factories).
- A scenario needing a NEW block → flags a GAP honestly (does NOT hallucinate a broken scene). Deliberate
  tradeoff: GROUNDED RELIABILITY over the generality of free-form (hallucination-prone) code generation.
- A vague request → the negotiator ASKS for clarification (when the LLM backend is up).
- The frontier that would relax the closed-catalog constraint: a SELF-EXTENDING catalog (LLM generates a candidate
  block → the system VERIFIES it in Kit → adds it if it works) — keeps the grounding, reduces the constraint.

## This session's value-add
- **6 audit fixes** (real edge-case gotchas found by an adversarial audit GROUNDED in production code, not reasoning):
  orchestrator HALT on lowercase block-ids; humanoid self-target gold-poisoning (+ compose_gate twin); start_pose/
  target_pose not offset under composition; ground-slab footprint over-spacing; stack-collapse structural check
  (+ twin); chain_xkit_gate handoff/custody now use ACTUAL delivery (delivered_paths). Dominant gap-class:
  "fixed in one file, never ported to its twin" (5/6).
- **3 robustness gates** (layout-stress, chain-wiring-stress, template_lint) + a regression suite.
- **Chain-audit closed:** all real-asset conveyor chains re-confirmed with the fixed gate; the N=1 source's
  stochasticity honestly reclassified.
- **Gold re-verifications** (false-success-vakt): CP-08/12/13 hold (grid/grid/column).
- **End-to-end demonstrated:** NL (any language) → Gemini picks blocks → composer builds → scene_eyes verifies=True.

## Honest meta-finding
The adversarial-customer-stress idea WORKS — but only when **grounded in production code/RAW** (it found 4 real
gotchas there). Reasoning-only gotcha waves yielded INSTRUMENT artifacts (my own Gemini-throttle / regex / wrong-
layer errors), not product failures. The biggest recurring error this session was MY OWN: over-concluding from
simplified qa test scripts instead of the production agent — corrected 3× by Anton's domain knowledge.
