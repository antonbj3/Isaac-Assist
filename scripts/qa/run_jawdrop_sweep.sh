#!/bin/bash
# descend-place lever sweep: CP-01 cube (no-regression at lower release) + CP-YCB-02 can (upright?). Each fresh Kit.
set -u
cd /home/anton/projects/Omniverse_Nemotron_Ext
RESULT=/tmp/jawdrop_result.txt
: > "$RESULT"
for TPL in CP-26; do
  echo "==================== $TPL JAWDROPTIP=0.08 ====================" >> "$RESULT"
  rm -f "/home/anton/.isaac_qa/run/eyes/$TPL/eyes.json" 2>/dev/null
  bash scripts/qa/kit_restart.sh >> "$RESULT" 2>&1 || { echo "$TPL KIT_FAIL" >> "$RESULT"; continue; }
  JAWDROPTIP=0.08 timeout 320 python scripts/qa/scene_eyes.py "$TPL" 90 >> "$RESULT" 2>&1
  echo "RC=$? ($TPL)" >> "$RESULT"
done
echo "==== DONE ====" >> "$RESULT"
