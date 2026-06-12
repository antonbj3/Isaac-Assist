#!/usr/bin/env python3
"""Ledger cloud measurement results (modal_*.jsonl) into the verification
ledger — same record shape as nofm_validate, with source tagged cloud_* and
the GPU/boot extras kept so cloud rows are always distinguishable from local.

Idempotent per file: a .ledgered marker is written next to each ingested
JSONL; re-runs skip marked files (so this can run after every cloud wave).

Usage:
    python3 scripts/cloud/ledger_cloud_results.py [file.jsonl ...]
(no args = all unledgered files in workspace/qa_runs/cloud_results/)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from service.isaac_assist_service.qa.verification_ledger import record_gate_run  # noqa: E402

RESULTS_DIR = REPO / "workspace" / "qa_runs" / "cloud_results"


def ingest(path: Path, sha: str) -> int:  # noqa: C901
    n = 0
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            print(f"  SKIP torn line in {path.name}")
            continue
        tpl = REPO / "workspace" / "templates" / f"{r.get('template')}.json"
        if not tpl.exists():
            print(f"  SKIP unknown template {r.get('template')}")
            continue
        # UR10 cloud rows are NON-PARITY by policy (cuRobo numerics are
        # 5070-tuned; 2026-06-11) — never ledger them, regardless of verdict.
        try:
            tpl_doc = json.loads(tpl.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"  SKIP unreadable template {r.get('template')}: {e}")
            continue
        # UR10 guard LIFTED 2026-06-12: family parity proven after the two
        # asset-portability fixes (gripper path + pinned UR10 revision —
        # CP-70/73/75/79/80/83/84 green in cloud; 69 stochastic like local
        # CP-71, 81 chronic-timeout never ledgers anyway). Cloud rows stay
        # distinguishable via the cloud_file/gpu extras.
        extras = {"source": "cloud_gate", "gpu": r.get("gpu"),
                  "boot_s": r.get("boot_s"), "cloud_file": path.name,
                  "fresh_kit": True}
        if r.get("gate") is not None:
            record_gate_run(tpl, bool(r["gate"]), r.get("sha") or sha,
                            extras=extras)
            n += 1
        # faithfulness axis stays LOCAL-only by policy (cloud TS is noisy
        # on soft-state thresholds; 2026-06-11 parity round). Opt in with
        # --with-ts for experiments.
        if "--with-ts" in sys.argv and r.get("ts") is not None:
            record_gate_run(tpl, bool(r["ts"]), sha, axis="faithfulness",
                            extras={**extras, "source": "cloud_scene_timeseries",
                                    "verdict_vector": r.get("vec") or {}})
            n += 1
    return n


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = ([Path(a) for a in args] if args
             else sorted(RESULTS_DIR.glob("modal_*.jsonl")))
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                         capture_output=True, text=True).stdout.strip()
    total = 0
    for f in files:
        marker = f.with_suffix(f.suffix + ".ledgered")
        if marker.exists():
            continue
        n = ingest(f, sha)
        marker.write_text("ok")
        print(f"{f.name}: {n} rows ledgered")
        total += n
    print(f"TOTAL {total} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
