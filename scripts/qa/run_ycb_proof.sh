#!/bin/bash
# run_ycb_proof.sh — REAL-OBJECT MANIPULATION proof.
# CP-YCB-01 (real YCB foam_brick via add_reference) = TEST; CP-01 (primitive cube) = positive CONTROL.
# Each measured on its OWN fresh Kit (restart-before-each-measurement; kit-degradation discipline).
# A FILE (not heredoc) so kit_restart's sleeps don't trip exit 144. Results -> /tmp/ycb_proof_result.txt
set -u
cd /home/anton/projects/Omniverse_Nemotron_Ext
RESULT=/tmp/ycb_proof_result.txt
: > "$RESULT"

run_one () {
  local TPL=$1
  echo "==================== $TPL ====================" >> "$RESULT"
  rm -f "/home/anton/.isaac_qa/run/eyes/$TPL/eyes.json" 2>/dev/null
  bash scripts/qa/kit_restart.sh >> "$RESULT" 2>&1
  if [ $? -ne 0 ]; then echo "$TPL: KIT_RESTART_FAIL" >> "$RESULT"; return; fi
  echo "---- scene_eyes stdout ($TPL) ----" >> "$RESULT"
  timeout 320 python scripts/qa/scene_eyes.py "$TPL" 40 >> "$RESULT" 2>&1
  echo "RC=$? (scene_eyes $TPL)" >> "$RESULT"
}

run_one CP-YCB-01
run_one CP-01
echo "==== DONE $(cat /proc/uptime | cut -d' ' -f1)s-uptime ====" >> "$RESULT"
