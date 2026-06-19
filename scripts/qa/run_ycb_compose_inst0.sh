#!/bin/bash
# observe inst0 of the 2-cell real-object compose (full 2/2 N-of-M for parallel real-object composition)
set -u
cd /home/anton/projects/Omniverse_Nemotron_Ext
RESULT=/tmp/ycb_compose_inst0.txt
: > "$RESULT"
bash scripts/qa/kit_restart.sh >> "$RESULT" 2>&1 || { echo KIT_FAIL >> "$RESULT"; exit 1; }
EYES_DUR=55 EYES_FOCUS=inst0 timeout 420 python scripts/qa/scene_eyes.py --compose "CP-YCB-01C@0,0,0" "CP-YCB-01C@2.5,0,0" >> "$RESULT" 2>&1
echo "RC=$?" >> "$RESULT"
