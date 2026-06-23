#!/usr/bin/env python3
"""negotiator_probe.py (cont.319bbb) — test the REAL production clarification layer (negotiator.negotiate), not the
qa orchestrator. Anton's point: the agentic harness (ChatOrchestrator + negotiator) already exists; the honest
question is how DEEP its clarification is — does it ASK for the missing variables on a demanding special-order, or
guess? This drives the production negotiate() standalone (a single LLM call, NO ChromaDB -> safe locally) on the
adversarial special-orders + reports needs_clarification + the questions it asks. Pure Gemini, no Kit.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "service"))
sys.path.insert(0, os.path.dirname(__file__))
from isaac_assist_service.chat.negotiator import negotiate
from isaac_assist_service.chat.llm_gemini import GeminiProvider
from compose_stress_scale import CASES


async def main():
    prov = GeminiProvider(api_key=os.environ["GEMINI_API_KEY"], model="gemini-2.5-flash")
    print(f"=== PRODUCTION negotiator on {len(CASES)} adversarial special-orders ===\n")
    asks = 0
    for _id, req, trap, kind in CASES:
        try:
            r = await negotiate(req, prov)
        except Exception as e:
            print(f"[ERR] {_id}: {e}"); continue
        nc = r.get("needs_clarification")
        qs = r.get("questions") or []
        if nc:
            asks += 1
        print(f"[{'ASKS' if nc else 'proceeds':8}] {_id:14} ({kind})")
        print(f"     trap: {trap}")
        for q in qs[:3]:
            print(f"     Q: {q}")
        print()
        # cont.319ddd: HEAVY pace (~3/min) for FREE-TIER RPM. On Vertex
        # (GEMINI_PROVIDER_VERTEX=1, high RPM) the 20s is unnecessary -> NEGOTIATOR_PACE_S
        # lets a Vertex run go fast (e.g. 3s). Default 20 keeps free-tier behaviour.
        await asyncio.sleep(float(os.environ.get("NEGOTIATOR_PACE_S", "20")))
    print(f"=== {asks}/{len(CASES)} requests triggered a clarifying question ===")
    print("Read which it ASKS vs PROCEEDS on: does it catch the gripper-object / Y-split / geometric / vague traps,")
    print("or proceed silently? (This is the REAL production clarification depth, vs the qa-script shallowness.)")


if __name__ == "__main__":
    asyncio.run(main())
