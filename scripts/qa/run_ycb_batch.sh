#!/bin/bash
# run_ycb_batch.sh — run scene_eyes on each template arg, each on its OWN fresh Kit
# (restart-before-each-measurement). A FILE (not heredoc) so kit_restart sleeps don't trip exit 144.
# Usage: bash scripts/qa/run_ycb_batch.sh CP-YCB-02 CP-YCB-03   -> results in /tmp/ycb_batch_result.txt
set -u
cd /home/anton/projects/Omniverse_Nemotron_Ext
RESULT=/tmp/ycb_batch_result.txt
: > "$RESULT"
for TPL in "$@"; do
  echo "==================== $TPL ====================" >> "$RESULT"
  rm -f "/home/anton/.isaac_qa/run/eyes/$TPL/eyes.json" 2>/dev/null
  bash scripts/qa/kit_restart.sh >> "$RESULT" 2>&1 || { echo "$TPL: KIT_RESTART_FAIL" >> "$RESULT"; continue; }
  echo "---- scene_eyes stdout ($TPL) ----" >> "$RESULT"
  timeout 320 python scripts/qa/scene_eyes.py "$TPL" 40 >> "$RESULT" 2>&1
  echo "RC=$? ($TPL)" >> "$RESULT"
done
echo "==== DONE ====" >> "$RESULT"
