#!/bin/bash
# real-object cross-Kit chain: YCB-brick source -> YCB-aware relay -> Franka receiver. A FILE (kit_restart sleeps).
set -u
cd /home/anton/projects/Omniverse_Nemotron_Ext
RESULT=/tmp/ycb_chain_result.txt
: > "$RESULT"
bash scripts/qa/kit_restart.sh >> "$RESULT" 2>&1 || { echo KIT_FAIL >> "$RESULT"; exit 1; }
RELAY_ASSET="/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned/061_foam_brick.usd" RELAY_MESH="_61_foam_brick" timeout 1100 python scripts/qa/chain_xkit_gate.py CP-CHAIN-FRANKA-SRC-YCB CP-CHAIN-FLAT >> "$RESULT" 2>&1
echo "RC=$? (ycb-chain)" >> "$RESULT"
