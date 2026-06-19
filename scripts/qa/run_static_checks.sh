#!/usr/bin/env bash
# Kit-free static regression suite for the PLC-export + composition machinery.
#
# Runs ONLY explicit Kit-free guard scripts (NO pytest, NO directory globs -- per the no-local-pytest /
# explicit-files rule). Each script exits 0 (green) / non-0 (regression). One command to re-verify the static
# foundation built cont.297-301: PLC-export ST is grammar-valid + faithful + control-flow-correct, and the
# composition registry + handoff predictor are self-consistent. Run before trusting any of those tools.
#
# Usage:  bash scripts/qa/run_static_checks.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CHECKS=(
  "test_plc_st_parses.py"       # emitted IEC 61131-3 ST parses under blark
  "test_plc_roundtrip.py"       # consume-IR round-trip faithful + honest (position/orientation/approach)
  "test_plc_controlflow.py"     # emitted ST state-machine control flow correct (grip-retry skip arithmetic)
  "chain_registry_validate.py"  # chain_stages.json internally consistent (positions, handoff reach)
  "test_chain_compat.py"        # handoff predictor agrees with proven ground truth + neg-controls
  "test_composable_blocks.py"   # block catalog consistent + genuine/position-honest summary matches verdicts
  "test_bin_containment.py"     # scene_eyes bin-aware ORIENTATION fix: deep-bin topple suppressed, surface stays reject
)

pass=0; fail=0; failed=()
for c in "${CHECKS[@]}"; do
  echo "=== $c ==="
  if python3 "$HERE/$c"; then
    pass=$((pass+1))
  else
    fail=$((fail+1)); failed+=("$c")
  fi
  echo
done

echo "================ STATIC SUITE: $pass passed, $fail failed ================"
if [ "$fail" -ne 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "ALL STATIC CHECKS GREEN."

# dimension-handling recipe must keep matching the hand-tuned cont.319 real-asset templates
python3 scripts/qa/real_asset_spawn.py --selftest || exit 1
