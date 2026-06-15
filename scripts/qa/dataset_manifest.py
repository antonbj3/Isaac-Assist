#!/usr/bin/env python3
"""dataset_manifest.py — scan workspace/training_data/ and emit a CURRENT manifest of the LLM-flow
training corpus (Anton's 'spara all data' + train-a-model goal). Generated, never hand-counted, so
it cannot go stale. Prints a human summary and writes workspace/dataset_manifest.json (gitignored).

The TRUST LADDER (verification_tier) is the spine of the corpus — train/filter by it:
  gold_verified_core        L1  a single canonical template, Kit-gate-verified to deliver
  gold_kit_delivery_verified L2 a COMPOSITION that was BUILT + measured to deliver full in Kit
  candidate_heuristic       --  a Gemini PLAN that passed structural+IO-semantic checks only
                                 (reasoning-correct, NOT Kit-delivery-verified)
Only the gold_* tiers are delivery-truth; candidate_heuristic is reasoning-truth (the error-rate axis).
"""
import json, os, collections

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
DDIR = os.path.join(REPO, "workspace", "training_data")
FILES = {
    "canonical_templates.jsonl": "L1 single verified canonical templates (gold_verified_core)",
    "verified_compositions.jsonl": "L2 Kit-delivery-verified compositions (gold_kit_delivery_verified)",
    "compose_reasoning.jsonl": "Gemini compose-reasoning plans (candidate_heuristic; reasoning error-rate)",
}


def _load(path):
    out = []
    if os.path.exists(path):
        for l in open(path):
            l = l.strip()
            if l:
                try:
                    out.append(json.loads(l))
                except Exception:
                    pass
    return out


def main():
    manifest = {"files": {}, "trust_ladder": {}}
    print("=== LLM-FLOW TRAINING CORPUS ===")
    for fn, desc in FILES.items():
        recs = _load(os.path.join(DDIR, fn))
        tiers = collections.Counter(r.get("verification_tier", "?") for r in recs)
        entry = {"records": len(recs), "desc": desc, "tiers": dict(tiers)}
        # reasoning: pass-rate per eval_set (the boxed error rate). EXCLUDE errored records (429
        # quota / network) — an infra failure is NOT a reasoning failure; conflating them would be a
        # false-negative in our OWN error-rate measure. Report errors separately.
        if "reasoning" in fn:
            by_set = collections.defaultdict(lambda: [0, 0, 0])  # [passed, scored, errored]
            for r in recs:
                s = r.get("eval_set", "?")
                if r.get("error"):
                    by_set[s][2] += 1
                    continue
                by_set[s][0] += int(bool(r.get("score_passed")))
                by_set[s][1] += 1
            entry["reasoning_pass"] = {s: f"{p}/{n}" + (f" (+{e} infra-err excluded)" if e else "") for s, (p, n, e) in by_set.items()}
            entry["models"] = dict(collections.Counter(r.get("model", "?") for r in recs))
        # compositions: complexity distribution (n_cells, n_objects)
        if "compositions" in fn:
            ncells = collections.Counter(r.get("complexity", {}).get("n_cells", "?") for r in recs)
            entry["n_cells_dist"] = dict(sorted((str(k), v) for k, v in ncells.items()))
            entry["pairs"] = ["+".join(c["template"] for c in r.get("plan", {}).get("cells", [])) for r in recs]
        manifest["files"][fn] = entry
        print(f"\n[{fn}] {len(recs)} records — {desc}")
        for t, c in tiers.items():
            print(f"    tier {t}: {c}")
        if "reasoning_pass" in entry:
            print(f"    reasoning pass-rate: {entry['reasoning_pass']} | models: {entry['models']}")
        if "n_cells_dist" in entry:
            print(f"    n_cells: {entry['n_cells_dist']}")

    out = os.path.join(REPO, "workspace", "dataset_manifest.json")
    json.dump(manifest, open(out, "w"), indent=2)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
