#!/usr/bin/env python3
"""
advanced_user_sim.py — Dynamic retrieval-pipeline simulation for the
Isaac Assist canonical harness.

Simulates advanced LLM users issuing ambitious robotics tasks and feeds each
prompt through the REAL canonical-retrieval pipeline (Kit-free). It reuses the
production entry-points without reimplementing scoring:

  - produce_layout_spec_from_text  (multimodal/text_modality.py)
        -> rule-based intent extraction (pattern_hint / counts / features;
           structural_tags always []).
  - retrieve_with_intent_soft_filter (chat/tools/template_retriever.py)
        -> prod-default "soft" mode: dense embedding of the user prompt over
           ChromaDB (all-MiniLM-L6-v2), pattern_hint 15% soft-boost, re-rank.
  - the orchestrator decision gate (orchestrator.py:1009-1014):
           confident_match = top_sim >= 0.45 AND (top1 - top2) >= 0.20.

ISOLATION: We point the retriever's module-level _PERSIST_DIR / _COLLECTION_NAME
at a fresh temp directory and call the REAL rebuild_index() so all templates on
disk are embedded with the SAME document format (goal\\n\\nthoughts\\n\\ntools)
and the SAME default embedder the production code uses. The production
collection in workspace/tool_index is never touched.

NO KIT. No service launch. No simulator. Pure retrieval + intent logic.

Run (env with chromadb + sentence-transformers):
  /home/anton/miniconda3/envs/splatview/bin/python scripts/qa/advanced_user_sim.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

# Gate constants — mirror orchestrator.py:921-922 / 1009-1014 defaults.
CANONICAL_MIN_SIM = float(os.environ.get("CANONICAL_MIN_SIM", "0.45"))
CANONICAL_MIN_MARGIN = float(os.environ.get("CANONICAL_MIN_MARGIN", "0.20"))
TOP_K = 3  # production hard-instantiate reads top-1; we record top-3.

# ---------------------------------------------------------------------------
# The advanced-user prompt set (~28). Sourced from the coverage-gap report's
# 24 simulated requests + a handful of additional ambitious shapes. Each is a
# realistic 1-3 sentence LLM-user request. `axis` tags the capability axis;
# `note` records what a genuinely-correct canonical would have to be.
# ---------------------------------------------------------------------------
PROMPTS = [
    # ----- Multi-robot cells & coordination -----
    {"id": "A01", "axis": "multi-robot line",
     "prompt": "Build a 6-station automotive sub-assembly line with 4 fixed Franka arms, one UR10 on a 7th-axis rail, and a Nova Carter AMR feeding parts, with WIP buffers between stations, station-blocking back-pressure, and a line-balancing report giving cycle time per station and the bottleneck."},
    {"id": "A02", "axis": "bimanual hold+fasten",
     "prompt": "Two Franka arms perform a true bimanual assembly: the left arm holds a bracket under continuous 5 N press force while the right arm drives four M4 screws into it in a cross pattern, keeping the hold force throughout all four screw cycles with no per-cycle release."},
    {"id": "A03", "axis": "pipelined 3-arm cell",
     "prompt": "Set up a three-arm circular cell where arm A picks, arm B inspects and regrips, and arm C inserts, running as a continuously pipelined flow with all three arms active at once, sustaining at least one part per second steady state."},
    {"id": "A04", "axis": "mobile manipulation",
     "prompt": "A Carter AMR with a UR10 mounted on its deck navigates to three shelf bays, picks an SKU from each at different heights, and returns to a packing station, coordinating its base pose so each target stays inside the arm's dexterous workspace."},
    # ----- Contact-rich manipulation & assembly -----
    {"id": "A05", "axis": "spiral-search insertion",
     "prompt": "Insert a splined shaft into a mating hub with 0.05 mm clearance using a spiral-search plus force-feedback strategy, aborting and re-approaching if axial force exceeds 15 N before seating, and report the insertion depth versus force curve."},
    {"id": "A06", "axis": "torque-controlled threading",
     "prompt": "Thread an M8 bolt six full turns into a tapped hole with a helical-screw motion and torque-controlled tightening to a 5 N·m target, detecting cross-threading from the torque-spike signature in the first half turn."},
    {"id": "A07", "axis": "snap-fit assembly",
     "prompt": "Press a plastic clip into a housing as a snap-fit, detect the click from the force-drop signature, verify full engagement, and retry up to three times with re-orientation on a failed snap."},
    {"id": "A08", "axis": "gear-mesh assembly",
     "prompt": "Place a spur gear onto a shaft and rotate it to mesh with a mating gear, using contact-torque feedback to find the tooth-engagement angle."},
    # ----- Perception under realism -----
    {"id": "A09", "axis": "clutter bin-pick (local vision)",
     "prompt": "Run closed-loop bin-picking from a cluttered tote of 20 mixed parts in random 6-DOF poses with mutual occlusion, using a local segmentation and pose pipeline with no cloud API, collision-aware grasp selection, and a re-perceive-after-each-pick loop."},
    {"id": "A10", "axis": "deformable sheet handling",
     "prompt": "Pick a limp gasket sheet from a stack with a vacuum array, detect its sag, and lay it flat into a fixture without folding, using real soft-body physics rather than a rigid proxy."},
    {"id": "A11", "axis": "trained-detector defect loop",
     "prompt": "Run defect inspection with a YOLO model trained on this scene's own SDG output, then close the loop so items the live detector flags as scratched get diverted, and report precision and recall against the ground-truth semantic labels."},
    {"id": "A12", "axis": "multi-cam hand-eye pose",
     "prompt": "Estimate 6-DOF object poses from multiple hand-eye-calibrated cameras and feed them to the grasp planner, validated end-to-end against known fiducial poses with a reprojection-error report."},
    # ----- Long-horizon sequencing & error recovery -----
    {"id": "A13", "axis": "long-horizon kit-build + rollback",
     "prompt": "Run a 12-step kit build that places a base, inserts three fasteners, mounts a cover, applies a label, boxes and seals, with per-step verification, automatic retry on failure, and a checkpoint-rollback to the last good state if a step fails twice."},
    {"id": "A14", "axis": "palletize-then-verify",
     "prompt": "Build a three-layer mixed-SKU pallet and, after each layer, run an overhead scan to confirm placement within plus or minus 5 mm, re-placing any item that drifted before starting the next layer."},
    {"id": "A15", "axis": "composed cross-domain workflow",
     "prompt": "As one runnable scenario, pick from a conveyor, vision-inspect, sort defects to a reject lane, palletize the good parts, and emit an OEE and defect-rate dashboard."},
    # ----- Tolerance / precision / metrology -----
    {"id": "A16", "axis": "precision place + Cpk",
     "prompt": "Precision-place a part into a 0.5 mm-clearance fixture pocket with vision-servo final alignment, then report the placement-error distribution over 20 cycles and a Cpk against a plus or minus 0.3 mm spec."},
    {"id": "A17", "axis": "tolerance stack-up report",
     "prompt": "Verify a five-fixture stack-up by computing the cumulative tolerance, flag whether the worst-case assembly still clears a 2 mm guard, and produce an auditable tolerance-stack report."},
    # ----- Tool-use & reconfiguration -----
    {"id": "A18", "axis": "mid-task EE changeover",
     "prompt": "Have a UR10 start with a parallel-jaw gripper and palletize four boxes, then auto-swap to a vacuum cup at a tool stand and de-palletize flat sheets, verifying tool engagement after each swap."},
    {"id": "A19", "axis": "adaptive 3-finger grasp",
     "prompt": "Use an adaptive three-finger gripper to handle five different geometries — cube, cylinder, sphere, thin plate, and irregular casting — selecting the grasp topology of parallel, tripod, or power per object."},
    # ----- Humanoid / dexterous -----
    {"id": "A20", "axis": "humanoid bimanual clear",
     "prompt": "Have a Unitree G1 humanoid do a bimanual table-clear, picking objects with both hands and placing them in a bin while maintaining whole-body balance, using a real humanoid pick controller rather than one arm at a time."},
    {"id": "A21", "axis": "in-hand reorient + handoff",
     "prompt": "Reorient a cube 180 degrees in-hand with an Allegro hand using finger-gaiting and per-fingertip contact-force observation, then hand it off to a parallel-jaw gripper for placement."},
    # ----- Industrial integration at scale & sim2real -----
    {"id": "A22", "axis": "PLC-in-the-loop + Cat-0 stop",
     "prompt": "Set up a PLC-in-the-loop cell over OPC-UA and Modbus where the robot pick trigger, conveyor run-stop, and a safety light-curtain interlock are all driven by external PLC tags, with an E-stop that brings the arm to an ISO 10218 Category-0 stop mid-trajectory and then resumes safely."},
    {"id": "A23", "axis": "rosbag sim2real autotune",
     "prompt": "Replay a real-robot rosbag of 200 joint trajectories into the sim, measure the per-joint sim-to-real deviation, auto-tune the actuator friction, armature, and damping to minimize it, and report the residual gap with a confidence bound."},
    {"id": "A24", "axis": "CNC machine-tending loop",
     "prompt": "Run a CNC machine-tending cycle where a UR10 loads a blank, closes the door interlock, runs the machine for a fixed dwell, opens the door, and unloads the finished part to an outfeed, looped for five parts with the door interlock enforced every cycle."},
    # ----- Additional ambitious shapes (mine) -----
    {"id": "A25", "axis": "cable routing (deformable)",
     "prompt": "Route a flexible cable harness through three clips on a panel and seat the connector, keeping the cable bend radius above its minimum the whole time."},
    {"id": "A26", "axis": "moving-target conveyor pick",
     "prompt": "Track and pick parts off a conveyor moving at 0.3 m/s with a single Franka, dropping each into a tote without stopping the belt."},
    {"id": "A27", "axis": "dual-arm large-object handoff",
     "prompt": "Two UR10 arms cooperatively lift a long rigid beam that is too large for one arm, keeping it level during transfer to a fixture across the cell."},
    {"id": "A28", "axis": "RL grasp policy in-the-loop",
     "prompt": "Train an RL grasp policy in IsaacLab across parallel environments, then step the trained policy in-the-loop as the controller to pick varied objects and report success rate."},
]


def _stage_clean_templates(src: Path) -> Path:
    """Stage a clean template dir: symlink every *.json EXCEPT stale backups
    (`*-old.json`, `*.pre_*`, `*_bak*`). The real _build_index globs *.json and
    embeds by task_id; on a fresh chromadb build a duplicate task_id (CP-13.json
    vs CP-13-old.json both declare task_id 'CP-13') raises DuplicateIDError.
    Excluding the backup mirrors the intended clean library on disk and is the
    set the coverage report counts (447 clean templates). Returns the staged dir.
    """
    staged = Path(tempfile.mkdtemp(prefix="adv_sim_templates_"))
    skipped = []
    for f in sorted(src.glob("*.json")):
        name = f.name
        if name.endswith("-old.json") or ".pre_" in name or "_bak" in name:
            skipped.append(name)
            continue
        (staged / name).symlink_to(f)
    if skipped:
        print(f"[sim] staged clean template dir, excluded {len(skipped)} backup(s): {skipped}")
    return staged


def _build_isolated_index():
    """Repoint the real retriever at a fresh temp persist dir + clean template
    dir + collection, and run the REAL _build_index() so the production index is
    untouched. Returns the template_retriever module + temp dirs."""
    from service.isaac_assist_service.chat.tools import template_retriever as tr

    staged = _stage_clean_templates(tr._TEMPLATES_DIR)
    tmp = Path(tempfile.mkdtemp(prefix="adv_sim_chroma_"))
    tr._TEMPLATES_DIR = staged
    tr._PERSIST_DIR = tmp
    tr._COLLECTION_NAME = "adv_sim_templates"
    tr._collection = None
    tr._client = None
    tr._template_cache = {}
    # _get_collection() create-path will _build_index() into the fresh dir.
    col = tr._get_collection()
    if col is not None and col.count() == 0:
        tr._build_index()
    return tr, tmp


def _retrieve(prompt: str, top_k: int):
    """Production-default 'soft' path: intent extraction + soft-filter retrieve."""
    from service.isaac_assist_service.multimodal.text_modality import (
        produce_layout_spec_from_text,
    )
    from service.isaac_assist_service.chat.tools.template_retriever import (
        retrieve_with_intent_soft_filter,
    )
    spec = produce_layout_spec_from_text(prompt)
    intent = spec.intent.model_dump(mode="json")
    scored = retrieve_with_intent_soft_filter(
        intent, top_k=top_k, original_query=prompt
    )
    return intent, scored


def main():
    tr, tmp = _build_isolated_index()
    col = tr._get_collection()
    n_indexed = col.count() if col else 0
    n_with_intent = sum(1 for t in tr._template_cache.values() if t.get("intent"))
    print(f"[sim] isolated index built: {n_indexed} templates "
          f"({n_with_intent} with intent) @ {tmp}")

    rows = []
    for p in PROMPTS:
        t0 = time.perf_counter()
        intent, scored = _retrieve(p["prompt"], TOP_K)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        top = []
        for s in scored[:3]:
            top.append({
                "task_id": s["task_id"],
                "similarity": round(s["similarity"], 4),
                "similarity_boosted": round(s.get("similarity_boosted", s["similarity"]), 4),
                "boost_applied": s.get("boost_applied", False),
            })
        top1_sim = scored[0]["similarity"] if scored else 0.0
        top2_sim = scored[1]["similarity"] if len(scored) > 1 else 0.0
        margin = top1_sim - top2_sim
        confident = bool(scored) and top1_sim >= CANONICAL_MIN_SIM and margin >= CANONICAL_MIN_MARGIN

        feats = intent.get("structural_features", {}) or {}
        feats_on = sorted(k for k, v in feats.items() if v is True)
        counts = intent.get("counts", {}) or {}

        rows.append({
            "id": p["id"],
            "axis": p["axis"],
            "prompt": p["prompt"],
            "pattern_hint": intent.get("pattern_hint"),
            "counts_nonzero": {k: v for k, v in counts.items() if v},
            "features_on": feats_on,
            "structural_tags": intent.get("structural_tags", []),
            "top3": top,
            "top1_sim": round(top1_sim, 4),
            "top2_sim": round(top2_sim, 4),
            "margin": round(margin, 4),
            "gate_fires": confident,
            "action": "hard_instantiate" if confident else "few_shot",
            "latency_ms": round(latency_ms, 1),
        })

    out = {
        "mode": "soft (production default)",
        "thresholds": {"min_sim": CANONICAL_MIN_SIM, "min_margin": CANONICAL_MIN_MARGIN},
        "index": {"n_indexed": n_indexed, "n_with_intent": n_with_intent},
        "n_prompts": len(rows),
        "n_gate_fires": sum(1 for r in rows if r["gate_fires"]),
        "pattern_hint_dist": _dist(r["pattern_hint"] for r in rows),
        "results": rows,
    }
    res_path = _REPO / "workspace" / "benchmarks" / "advanced_user_sim_results.json"
    res_path.parent.mkdir(parents=True, exist_ok=True)
    res_path.write_text(json.dumps(out, indent=2))

    # Console summary
    print(f"\n{'id':<5}{'pat_hint':<12}{'gate':<6}{'sim1':<7}{'mgn':<7}top-1")
    for r in rows:
        print(f"{r['id']:<5}{str(r['pattern_hint']):<12}"
              f"{'FIRE' if r['gate_fires'] else '-':<6}"
              f"{r['top1_sim']:<7}{r['margin']:<7}"
              f"{r['top3'][0]['task_id'] if r['top3'] else '(none)'}")
    print(f"\n[sim] pattern_hint distribution: {out['pattern_hint_dist']}")
    print(f"[sim] gate fired (hard-instantiate): "
          f"{out['n_gate_fires']}/{len(rows)}")
    print(f"[sim] wrote {res_path}")


def _dist(it):
    d = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    main()
