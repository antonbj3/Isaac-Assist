#!/usr/bin/env python3
"""
retrieval_eval_harness.py — Kit-free retrieval eval harness for canonical templates.

Calls the REAL retrieval entry-points the orchestrator uses (no scoring
reimplementation):
  - produce_layout_spec_from_text   (multimodal/text_modality.py:213)
  - retrieve_with_intent_soft_filter (template_retriever.py:785)  [prod default]
  - retrieve_with_intent_filter      (template_retriever.py:601)  [hard]
  - retrieve_templates_with_scores   (template_retriever.py:295)  [off baseline]

Mirrors orchestrator.py:968-1014 exactly:
  spec = produce_layout_spec_from_text(user_message)
  intent_dump = spec.intent.model_dump(mode="json")
  soft: retrieve_with_intent_soft_filter(intent_dump, top_k, original_query=msg)
  hard: retrieve_with_intent_filter(intent_dump, top_k)          # no original_query, per orch
  off:  retrieve_templates_with_scores(msg, top_k)
  gate: confident = top_sim>=MIN_SIM(0.45) and (top_sim-top2_sim)>=MIN_MARGIN(0.20)

KIT-FREE: touches only ChromaDB + template JSON. Does NOT launch the service
or the simulator. Does NOT modify workspace/templates/*.json.

SCRATCH-INDEX ISOLATION: by default the harness rebuilds the template index
into a SEPARATE chroma collection in a temp persist dir (--scratch, on by
default), so the production index at workspace/tool_index/ is never touched
and the live 448-template corpus is measured honestly (the production load
path never re-embeds). The rebuild is DEDUP-AWARE: workspace/templates has a
duplicate task_id (CP-13 in both CP-13.json and CP-13-old.json) which crashes
chromadb 1.5.0's rebuild_index() with DuplicateIDError. The harness keeps the
first-sorted file per task_id (CP-13.json wins over CP-13-old.json) so a clean
448→447 baseline is measurable without editing the corpus.

Run (from repo root, with an env that has chromadb + sentence-transformers):
  python scripts/qa/retrieval_eval_harness.py
  EVAL_MODE=off  python scripts/qa/retrieval_eval_harness.py
  EVAL_MODE=hard python scripts/qa/retrieval_eval_harness.py
  EVAL_CORPUS=path/to/eval.json python scripts/qa/retrieval_eval_harness.py

Env:
  EVAL_CORPUS   eval set path (default scripts/qa/retrieval_eval_set.json,
                next to this script)
  EVAL_MODE     soft (default, prod) | hard | off
  EVAL_TOPK     top_k metric depth (default 10)
  EVAL_SPLIT    all (default) | dev | holdout
  EVAL_SCRATCH  1 (default) build dedup scratch index | 0 use live prod index
  EVAL_SYNTH    "" (real, default) | path to a synthetic templates dir
                (when set, indexes that dir into the scratch collection instead)
  CANONICAL_MIN_SIM     gate sim    (default 0.45)
  CANONICAL_MIN_MARGIN  gate margin (default 0.20)
  RESULTS_FILE  output JSON path
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

warnings.filterwarnings("ignore")

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

CANONICAL_MIN_SIM = float(os.environ.get("CANONICAL_MIN_SIM", "0.45"))
CANONICAL_MIN_MARGIN = float(os.environ.get("CANONICAL_MIN_MARGIN", "0.20"))
TOPK = int(os.environ.get("EVAL_TOPK", "10"))
MODE = os.environ.get("EVAL_MODE", "soft").lower().strip()
USE_SCRATCH = os.environ.get("EVAL_SCRATCH", "1").lower() in ("1", "on", "true", "yes")

_DEFAULT_CORPUS = Path(__file__).resolve().parent / "retrieval_eval_set.json"


# ---------------------------------------------------------------------------
# Scratch-index build (dedup-aware) — leaves production index untouched.
# Re-implements ONLY the doc-construction loop of _build_index (verified
# byte-for-byte against template_retriever.py:127-153) so the embedding
# fed to ChromaDB is identical to production; the SCORING functions called
# below are the real ones, unchanged.
# ---------------------------------------------------------------------------
def _make_scratch_build(tr, templates_dir: Path):
    def build_dedup() -> None:
        docs: List[str] = []
        ids: List[str] = []
        metas: List[Dict] = []
        seen = set()
        n_skipped_dup = 0
        n_skipped_empty = 0
        for tf in sorted(templates_dir.glob("*.json")):
            try:
                t = json.loads(tf.read_text())
            except Exception:
                continue
            tid = t.get("task_id", tf.stem)
            goal = t.get("goal", "")
            thoughts = t.get("thoughts", "")
            tools = " ".join(t.get("tools_used", []))
            # IDENTICAL to template_retriever.py:140
            doc = f"{goal}\n\n{thoughts}\n\n{tools}".strip()
            if not doc:
                n_skipped_empty += 1
                continue
            if tid in seen:
                n_skipped_dup += 1
                continue
            seen.add(tid)
            docs.append(doc)
            ids.append(tid)
            metas.append({"task_id": tid})
            tr._template_cache[tid] = t
        if docs:
            tr._collection.add(documents=docs, ids=ids, metadatas=metas)
        print(
            f"[scratch-index] embedded={len(docs)} "
            f"skipped_dup={n_skipped_dup} skipped_empty={n_skipped_empty} "
            f"dir={templates_dir}",
            file=sys.stderr,
        )

    return build_dedup


def _setup_index():
    """Returns (tr_module, n_indexed, n_with_intent). Builds a dedup scratch
    index unless EVAL_SCRATCH=0."""
    from service.isaac_assist_service.chat.tools import template_retriever as tr

    synth = os.environ.get("EVAL_SYNTH", "").strip()
    templates_dir = Path(synth) if synth else tr._TEMPLATES_DIR

    if USE_SCRATCH or synth:
        scratch = Path(tempfile.mkdtemp(prefix="retrieval_eval_"))
        tr._PERSIST_DIR = scratch
        tr._COLLECTION_NAME = (
            "retrieval_eval_synth" if synth else "retrieval_eval_scratch"
        )
        tr._TEMPLATES_DIR = templates_dir
        tr._client = None
        tr._collection = None
        tr._template_cache = {}
        tr._build_index = _make_scratch_build(tr, templates_dir)
        t0 = time.time()
        tr.rebuild_index()
        print(f"[scratch-index] rebuild took {time.time() - t0:.1f}s",
              file=sys.stderr)
    else:
        # Use the live production index exactly as the service loads it.
        tr._get_collection()

    col = tr._get_collection()
    n_indexed = col.count() if col else 0
    n_with_intent = sum(1 for t in tr._template_cache.values() if t.get("intent"))
    return tr, n_indexed, n_with_intent


# ---------------------------------------------------------------------------
# Retrieval — exact mirror of orchestrator.py:968-1005
# ---------------------------------------------------------------------------
def _retrieve(tr, prompt: str, top_k: int) -> List[Dict]:
    from service.isaac_assist_service.multimodal.text_modality import (
        produce_layout_spec_from_text,
    )

    if MODE == "off":
        return tr.retrieve_templates_with_scores(prompt, top_k=top_k)

    spec = produce_layout_spec_from_text(prompt)
    intent_dump = spec.intent.model_dump(mode="json")
    if MODE == "hard":
        # orchestrator.py:982 does NOT pass original_query in hard mode.
        return tr.retrieve_with_intent_filter(intent_dump, top_k=top_k)
    # soft (production default), orchestrator.py:975-979
    return tr.retrieve_with_intent_soft_filter(
        intent_dump, top_k=top_k, original_query=prompt
    )


def _spec_intent_for(prompt: str) -> Dict:
    from service.isaac_assist_service.multimodal.text_modality import (
        produce_layout_spec_from_text,
    )

    return produce_layout_spec_from_text(prompt).intent.model_dump(mode="json")


# ---------------------------------------------------------------------------
# IR metrics
# ---------------------------------------------------------------------------
def _dcg(rels: List[float]) -> float:
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


def _ndcg_at_k(ranked_ids: List[str], gt: set, alts: set, k: int) -> float:
    rels = [1.0 if t in gt else (0.5 if t in alts else 0.0) for t in ranked_ids[:k]]
    ideal = sorted([1.0] * len(gt) + [0.5] * len(alts), reverse=True)[:k]
    idcg = _dcg(ideal)
    return _dcg(rels) / idcg if idcg > 0 else 0.0


def _eval_one(tr, entry: Dict, template_intent_lookup: Dict) -> Dict:
    prompt = entry["prompt"]
    gt = {g for g in entry.get("ground_truth", []) if g is not None}
    alts = set(entry.get("acceptable_alternatives", []))
    hard_negs = set(entry.get("hard_negatives", []))
    G = gt | alts
    is_null_gt = len(gt) == 0 and not alts
    expected_action = entry.get("expected_action", "few_shot")

    t0 = time.perf_counter()
    scored = _retrieve(tr, prompt, TOPK)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    ranked = [s["task_id"] for s in scored]

    top1_sim = scored[0]["similarity"] if scored else 0.0
    top2_sim = scored[1]["similarity"] if len(scored) > 1 else 0.0
    margin = top1_sim - top2_sim
    confident = bool(scored) and top1_sim >= CANONICAL_MIN_SIM and margin >= CANONICAL_MIN_MARGIN
    actual_action = "hard_instantiate" if confident else "few_shot"

    def recall_at(k: int) -> float:
        return 1.0 if (set(ranked[:k]) & G) else 0.0

    first_rank = next((i + 1 for i, t in enumerate(ranked) if t in G), None)
    mrr = (1.0 / first_rank) if first_rank else 0.0

    disambig = None
    if entry.get("difficulty") == "near_dup" and gt:
        disambig = 1.0 if (ranked and ranked[0] in gt) else 0.0

    hn_inv = None
    if hard_negs:
        gt_best = min((i for i, t in enumerate(ranked) if t in G), default=10 ** 9)
        hn_best = min((i for i, t in enumerate(ranked) if t in hard_negs), default=10 ** 9)
        hn_inv = 1.0 if hn_best < gt_best else 0.0

    false_match = 1.0 if (is_null_gt and confident) else (0.0 if is_null_gt else None)

    # coverage: does any primary-GT canonical carry an `intent` field?
    gt_has_intent = None
    if gt:
        gt_has_intent = any(template_intent_lookup.get(g) for g in gt)

    return {
        "id": entry["id"],
        "difficulty": entry.get("difficulty", "unknown"),
        "pattern_hint": entry.get("pattern_hint", "?"),
        "category": entry.get("category", "?"),
        "complexity": entry.get("complexity", "?"),
        "gt_has_intent": gt_has_intent,
        "is_null_gt": is_null_gt,
        "recall@1": recall_at(1),
        "recall@3": recall_at(3),
        "recall@5": recall_at(5),
        "recall@10": recall_at(10),
        "mrr": round(mrr, 4),
        "ndcg@10": round(_ndcg_at_k(ranked, gt, alts, 10), 4),
        "disambig": disambig,
        "hn_inversion": hn_inv,
        "false_match": false_match,
        "margin": round(margin, 4),
        "top1_sim": round(top1_sim, 4),
        "confident": confident,
        "actual_action": actual_action,
        "expected_action": expected_action,
        "mode_correct": 1.0 if actual_action == expected_action else 0.0,
        "latency_ms": round(latency_ms, 2),
        "ranked": ranked[:TOPK],
    }


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _agg(rows: List[Dict], keys: List[str]) -> Dict:
    return {k: _mean([r.get(k) for r in rows]) for k in keys}


def _percentiles(rows):
    lat = sorted(r["latency_ms"] for r in rows)
    n = len(lat)
    if not n:
        return {"p50_ms": 0.0, "p95_ms": 0.0}
    return {
        "p50_ms": lat[n // 2],
        "p95_ms": lat[min(int(n * 0.95), n - 1)],
    }


def run():
    tr, n_indexed, n_with_intent = _setup_index()

    # template -> has-intent lookup for coverage-conditioned recall
    template_intent_lookup = {
        tid: bool(t.get("intent")) for tid, t in tr._template_cache.items()
    }

    corpus_path = Path(os.environ.get("EVAL_CORPUS", _DEFAULT_CORPUS))
    split = os.environ.get("EVAL_SPLIT", "all")
    data = json.loads(corpus_path.read_text())
    corpus = data if isinstance(data, list) else data.get("prompts", [])
    if split != "all":
        corpus = [e for e in corpus if e.get("split", "dev") == split]

    # honesty check: are all ground-truth IDs actually in the index?
    all_gt = set()
    for e in corpus:
        all_gt |= {g for g in e.get("ground_truth", []) if g}
        all_gt |= set(e.get("acceptable_alternatives", []))
        all_gt |= set(e.get("hard_negatives", []))
    missing_gt = sorted(g for g in all_gt if g not in tr._template_cache)
    if missing_gt:
        print(f"[WARN] {len(missing_gt)} referenced IDs NOT in index: {missing_gt}",
              file=sys.stderr)

    metric_keys = [
        "recall@1", "recall@3", "recall@5", "recall@10",
        "mrr", "ndcg@10", "disambig", "hn_inversion",
        "false_match", "mode_correct",
    ]
    rows = [_eval_one(tr, e, template_intent_lookup) for e in corpus]

    overall = _agg(rows, metric_keys)
    by_difficulty = {
        d: _agg([r for r in rows if r["difficulty"] == d], metric_keys)
        for d in sorted({r["difficulty"] for r in rows})
    }
    by_pattern = {
        p: _agg([r for r in rows if r["pattern_hint"] == p], metric_keys)
        for p in sorted({r["pattern_hint"] for r in rows})
    }
    cov_recall = {
        "gt_with_intent": _mean(
            [r["recall@1"] for r in rows if r.get("gt_has_intent") is True]
        ),
        "gt_without_intent": _mean(
            [r["recall@1"] for r in rows if r.get("gt_has_intent") is False]
        ),
    }
    margin_hits = [r["margin"] for r in rows if r["recall@1"] == 1.0]
    margin_miss = [r["margin"] for r in rows if r["recall@1"] == 0.0]

    out = {
        "mode": MODE,
        "split": split,
        "top_k": TOPK,
        "scratch_index": USE_SCRATCH or bool(os.environ.get("EVAL_SYNTH", "").strip()),
        "synth": os.environ.get("EVAL_SYNTH", ""),
        "corpus": str(corpus_path),
        "index": {
            "n_indexed": n_indexed,
            "n_with_intent": n_with_intent,
            "coverage_pct": round(100 * n_with_intent / n_indexed, 1) if n_indexed else 0,
        },
        "missing_referenced_ids": missing_gt,
        "thresholds": {"min_sim": CANONICAL_MIN_SIM, "min_margin": CANONICAL_MIN_MARGIN},
        "n": len(rows),
        "overall": overall,
        "by_difficulty": by_difficulty,
        "by_pattern_hint": by_pattern,
        "coverage_conditioned_recall@1": cov_recall,
        "margin_dist": {
            "hit_mean": _mean(margin_hits),
            "miss_mean": _mean(margin_miss),
        },
        "latency": _percentiles(rows),
        "per_prompt": rows,
    }

    res_path = Path(
        os.environ.get(
            "RESULTS_FILE",
            _REPO / f"workspace/benchmarks/eval_set_{MODE}_{n_indexed}_{split}.json",
        )
    )
    res_path.parent.mkdir(parents=True, exist_ok=True)
    res_path.write_text(json.dumps(out, indent=2))

    print(
        f"[{MODE}] N={len(rows)} index={n_indexed}/{n_with_intent} "
        f"({out['index']['coverage_pct']}% intent)  "
        f"R@1={overall['recall@1']} R@3={overall['recall@3']} "
        f"R@5={overall['recall@5']} MRR={overall['mrr']} "
        f"nDCG@10={overall['ndcg@10']} FMR={overall['false_match']} "
        f"mode_acc={overall['mode_correct']} "
        f"p50={out['latency']['p50_ms']}ms -> {res_path}"
    )
    return out


if __name__ == "__main__":
    run()
