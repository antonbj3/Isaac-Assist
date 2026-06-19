#!/bin/bash
# run_ycb_compose.sh — real-object COMPOSITION test. (1) CP-YCB-01C standalone (refactor no-regression),
# (2) 2-cell compose (does add_reference + the YCB asset survive the composer namespacing?). Fresh Kit each.
set -u
cd /home/anton/projects/Omniverse_Nemotron_Ext
RESULT=/tmp/ycb_compose_result.txt
: > "$RESULT"

echo "==================== CP-YCB-01C standalone ====================" >> "$RESULT"
rm -f /home/anton/.isaac_qa/run/eyes/CP-YCB-01C/eyes.json 2>/dev/null
bash scripts/qa/kit_restart.sh >> "$RESULT" 2>&1 || { echo "KIT_FAIL" >> "$RESULT"; exit 1; }
timeout 320 python scripts/qa/scene_eyes.py CP-YCB-01C 40 >> "$RESULT" 2>&1
echo "RC=$? (standalone)" >> "$RESULT"

echo "==================== CP-YCB-01C x2 COMPOSE ====================" >> "$RESULT"
bash scripts/qa/kit_restart.sh >> "$RESULT" 2>&1 || { echo "KIT_FAIL" >> "$RESULT"; exit 1; }
EYES_DUR=55 EYES_FOCUS=inst1 timeout 420 python scripts/qa/scene_eyes.py --compose "CP-YCB-01C@0,0,0" "CP-YCB-01C@2.5,0,0" >> "$RESULT" 2>&1
echo "RC=$? (compose)" >> "$RESULT"
echo "==================== DONE ====================" >> "$RESULT"
