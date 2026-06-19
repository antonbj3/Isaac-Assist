#!/usr/bin/env bash
# cont.319hh: N-of-M reproducibility re-verify of CP-09 (FALSE(scatter) candidate -- saved RAW shows a
# perfect 5-column, contradicting the "don't re-audit / always topples" dismissal). 3 fresh Kit runs,
# restart before each (restart-FORE-varje-matning). PASS-per-run = a clean 5-level aligned column.
set -u
cd /home/anton/projects/Omniverse_Nemotron_Ext
LOG=/tmp/reverify_cp09.log
echo "=== CP-09 N-of-M re-verify @ $(date +%H:%M:%S) ===" > "$LOG"
for i in 1 2 3; do
  echo "" >> "$LOG"
  echo "--- RUN $i: kit_restart ---" >> "$LOG"
  bash scripts/qa/kit_restart.sh >> "$LOG" 2>&1 || { echo "RUN $i KIT_FAIL" >> "$LOG"; continue; }
  echo "--- RUN $i: scene_eyes CP-09 60 ---" >> "$LOG"
  timeout 400 python scripts/qa/scene_eyes.py CP-09 60 --noframes >> "$LOG" 2>&1
  echo "--- RUN $i done @ $(date +%H:%M:%S) ---" >> "$LOG"
done
echo "=== REVERIFY_DONE @ $(date +%H:%M:%S) ===" >> "$LOG"
