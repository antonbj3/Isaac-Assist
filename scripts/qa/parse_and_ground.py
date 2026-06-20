#!/usr/bin/env python3
"""parse_and_ground.py (cont.319ddd) — the FULL grounded special-order pipeline, end-to-end, locally, reliably.

Vision (Anton): a customer sold "infinite capacity" throws a demanding special-order; the system must REASON
(capture the variables) + GROUND the feasibility (not guess/assert) + be honest about what it can't do.

Pipeline: NL special-order
  -> LLM PARSE (Ollama qwen2.5-coder:14b — reliable, NO Gemini RPM; my own backend lever)  -> structured spec
  -> GROUNDED diagnose_special_order (deterministic first-principles: gripper-object, reach, payload, flow)  -> verdict

This bypasses the Gemini free-tier RPM wall that confounded the negotiator/orchestrator probes, and demonstrates the
grounded-vs-asserted reasoning the production agent should do (its resolve_* tools capture variables; this is the
grounding the slippery-cylinder/Y-split traps need).
"""
import sys, os, json, asyncio, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "service"))
sys.path.insert(0, os.path.dirname(__file__))
from isaac_assist_service.chat.llm_ollama import OllamaProvider
from grounded_feasibility import Obj, diagnose_special_order

PARSE_SYS = """You extract a STRUCTURED spec from a factory special-order. Return ONLY JSON (no prose, no fences):
{"robot":"franka|ur10|ur5|g1|unknown",
 "gripper":"vacuum_suction|parallel_jaw|magnetic|soft_compliant|unknown",
 "object":{"material":"steel|aluminum|plastic|glass|rubber|cardboard|foam|wood|ceramic|unknown",
           "shape":"box|cylinder|sphere|irregular|flat-sheet|bag","surface":"smooth-dry|smooth-wet|oily|rough|porous|textured",
           "mass_kg":<num>,"width_m":<num>,"fragile":<bool>},
 "targets":[[x,y,z]],
 "flow":[{"conditional":<bool>,"condition":"<text>"}],
 "throughput_per_min":<num or null>}
Infer sensible defaults. If a value is stated (e.g. "2 kg", "wet", "stainless steel cylinder"), capture it exactly.
"""


def _extract_json(txt):
    txt = (txt or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-z]*\n?", "", txt).rstrip("`").strip()
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else json.loads(txt)


def _norm(v, default="unknown"):
    """A weak local model often returns an enum as 'a|b' or 'a or b' — take the first concrete token."""
    if not isinstance(v, str) or not v.strip():
        return default
    return re.split(r"[|/]| or ", v.strip())[0].strip().lower()


def _augment_targets_from_nl(nl, spec):
    """Deterministic safety-net: a weak parser misses 'N metres tall' -> add a high target so the reach check fires
    regardless of the model. (The grounding is only as good as the captured variables; backstop the obvious ones.)"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(m|metre|meter|metres|meters)\b.*?\b(tall|high|column|tower)", nl, re.I)
    if m:
        h = float(m.group(1))
        if h >= 1.0:  # a real tall structure -> top of column at base_z + h
            spec.setdefault("targets", []).append((0.5, -0.3, 0.75 + h))
    return spec


async def parse_and_ground(nl, model="qwen2.5-coder:14b"):
    prov = OllamaProvider(model=model)
    r = await prov.complete([{"role": "user", "content": PARSE_SYS + "\n\nORDER: " + nl}], {})
    spec_raw = _extract_json(r.text)
    o = spec_raw.get("object") or {}
    spec = {
        "robot": _norm(spec_raw.get("robot"), "unknown"),
        "gripper": _norm(spec_raw.get("gripper"), "unknown"),
        "object": Obj(material=_norm(o.get("material"), "unknown"), shape=_norm(o.get("shape"), "box"),
                      surface=_norm(o.get("surface"), "smooth-dry"), mass_kg=float(o.get("mass_kg", 0.5) or 0.5),
                      width_m=float(o.get("width_m", 0.06) or 0.06), fragile=bool(o.get("fragile", False))),
        "targets": [tuple(t) for t in (spec_raw.get("targets") or [])],
        "flow": spec_raw.get("flow") or [],
        "throughput_per_min": spec_raw.get("throughput_per_min"),
    }
    if spec["robot"] == "unknown":   # a gripper-only order: default to the most capable arm so reach/payload still ground
        spec["robot"] = "ur10"
    _augment_targets_from_nl(nl, spec)
    return spec, diagnose_special_order(spec)


ORDERS = [
    "Place a 2 kg slippery wet stainless-steel cylinder; use a robot whose gripper can actually hold it; load it onto a conveyor that splits by weight: over 1.5kg goes to a palletizer, lighter to an inspection camera",
    "A Franka picks a dry plastic box (0.3kg, 6cm) off a belt and drops it into a bin",
    "Stack four steel blocks into a single column 1.5 metres tall using a Franka",
]


async def main():
    print("=== FULL grounded special-order pipeline (Ollama parse -> grounded diagnose) ===\n")
    for nl in ORDERS:
        print("ORDER:", nl[:90] + ("…" if len(nl) > 90 else ""))
        try:
            spec, rep = await parse_and_ground(nl)
            print(f"  parsed: robot={spec['robot']} gripper={spec['gripper']} obj={spec['object'].material}/{spec['object'].shape}/{spec['object'].surface} {spec['object'].mass_kg}kg")
            print(f"  GROUNDED feasible={rep['feasible']}")
            for f in rep["findings"]:
                tag = "BLOCK" if f.get("feasible") is False else ("?" if f.get("feasible") is None else "ok")
                print(f"    [{tag:5}] {f['check']}: {f['reason'][:110]}" + (f"  -> {f.get('suggested_gripper')}" if f.get('suggested_gripper') and not f.get('feasible') else ""))
        except Exception as e:
            print("  PARSE/GROUND ERROR:", str(e)[:160])
        print()


if __name__ == "__main__":
    asyncio.run(main())
