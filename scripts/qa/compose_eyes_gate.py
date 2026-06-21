#!/usr/bin/env python
"""compose_eyes_gate.py — the SCENE_EYES composition gate (structural enforcement of
"alltid alltid scene eyes" for composition).

compose_and_verify.py's position-bbox verdict is a re-implemented MEASURE that LIES
(cont.319-COMPOSE3: it false-negatived CP-50 2/4 while scene_eyes showed 4/4 upright). This
gate instead builds the composed scene and runs scene_eyes --compose ONCE PER INSTANCE
(EYES_FOCUS=instK — scene_eyes' per-cube analysis is focus-scoped, so one run verifies one
cell), then feeds each instance's scene_eyes STDOUT to eyes_gold_gate.py (which parses
scene_eyes' OWN verdict — no re-implementation). A composition is GOLD ONLY when scene_eyes
confirms EVERY cell. Slower than the proxy (N builds) but it cannot lie.

Usage:  python scripts/qa/compose_eyes_gate.py CP-36 CP-50   [EYES_DUR=200]
        (offsets 2.5m*idx, matching scene_eyes --compose's default placement)
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SE = str(REPO / "scripts/qa/scene_eyes.py")
GATE = str(REPO / "scripts/qa/eyes_gold_gate.py")


def main() -> int:
    cells = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not cells:
        print("usage: compose_eyes_gate.py CP-XX CP-YY ...")
        return 2
    dur = os.environ.get("EYES_DUR", "200")
    specs = ["%s@%g,0,0" % (c, 2.5 * i) for i, c in enumerate(cells)]
    gate_args = []
    for i, c in enumerate(cells):
        env = {**os.environ, "EYES_FOCUS": "inst%d" % i, "EYES_DUR": dur}
        print("=== scene_eyes --compose (focus inst%d = %s) ===" % (i, c))
        try:
            out = subprocess.run(["python3", SE, "--compose", *specs], env=env,
                                 capture_output=True, text=True, timeout=1300).stdout
        except subprocess.TimeoutExpired:
            print("  TIMEOUT inst%d" % i); out = ""
        f = "/tmp/cev_inst%d.txt" % i
        Path(f).write_text(out)
        # show the per-cube delivery + orientation lines so the verdict is auditable
        for ln in out.splitlines():
            if any(k in ln for k in ("plan_fails", "TOPPL", "TILT", "upright", "|Pallet",
                                     "|Bin", "Tray", "ORIENTATION FAIL", "never-gripped")):
                print("   " + ln.strip()[:110])
        gate_args.append("%s:%s" % (c, f))
    # eyes_gold_gate parses scene_eyes' OWN printed verdict per instance -> GOLD iff all genuine
    print("=== eyes_gold_gate (scene_eyes verdict per cell) ===")
    r = subprocess.run(["python3", GATE, "--append", *gate_args], capture_output=True, text=True)  # record GOLD compositions as training data
    print(r.stdout.strip())
    print("COMPOSE_EYES_GATE verdict:", "★ GOLD (scene_eyes-verified)" if r.returncode == 0
          else "NOT GOLD (scene_eyes did not confirm every cell)")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
