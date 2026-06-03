#!/bin/bash
# setup_mig.sh — enable MIG mode + create slices on A100/H100.
#
# Default: 3 × 2g.20gb slices per GPU (profile ID 14 on A100-80GB).
# Override:
#   MIG_PROFILE_ID=19 ./setup_mig.sh    # 7 × 1g.10gb
#   MIG_SLICE_COUNT=2 ./setup_mig.sh    # 2 slices instead of 3
#   GPU_INDEX=0 ./setup_mig.sh          # only GPU 0
#
# Writes MIG-UUIDs to /tmp/mig_uuids.txt, one per line.
# Output also printed to stdout for piping.
#
# Requires: sudo (nvidia-smi -mig 1 needs root).
# Run ONCE per BREV instance after provisioning.

set -euo pipefail

MIG_PROFILE_ID="${MIG_PROFILE_ID:-14}"     # 2g.20gb on A100-80GB
MIG_SLICE_COUNT="${MIG_SLICE_COUNT:-3}"
GPU_INDEX_FILTER="${GPU_INDEX:-}"
UUID_FILE="/tmp/mig_uuids.txt"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: must run as root (sudo). MIG mode toggle requires it."
  exit 1
fi

command -v nvidia-smi >/dev/null || { echo "ERROR: nvidia-smi not found"; exit 1; }

# Discover GPUs
mapfile -t GPU_IDS < <(nvidia-smi --query-gpu=index --format=csv,noheader)
if [ -n "$GPU_INDEX_FILTER" ]; then
  GPU_IDS=("$GPU_INDEX_FILTER")
fi

echo "[setup_mig] Target GPUs: ${GPU_IDS[*]}"
echo "[setup_mig] Profile ID: $MIG_PROFILE_ID  Slices/GPU: $MIG_SLICE_COUNT"

# Verify GPU supports MIG (A100 / A30 / H100 / H200 / B200)
for GPU in "${GPU_IDS[@]}"; do
  NAME=$(nvidia-smi -i "$GPU" --query-gpu=name --format=csv,noheader | tr -d ' ')
  case "$NAME" in
    *A100*|*A30*|*H100*|*H200*|*B200*) ;;
    *)
      echo "ERROR: GPU $GPU ($NAME) does not support MIG. Aborting."
      exit 2
      ;;
  esac
done

# Disable any existing MIG layout (idempotent)
for GPU in "${GPU_IDS[@]}"; do
  echo "[setup_mig] GPU $GPU: disabling MIG (if enabled)"
  nvidia-smi -i "$GPU" -mig 0 >/dev/null 2>&1 || true
done

# Enable MIG mode
for GPU in "${GPU_IDS[@]}"; do
  echo "[setup_mig] GPU $GPU: enabling MIG mode"
  nvidia-smi -i "$GPU" -mig 1
done

# Create GPU instances + compute instances
> "$UUID_FILE"
for GPU in "${GPU_IDS[@]}"; do
  echo "[setup_mig] GPU $GPU: creating $MIG_SLICE_COUNT × profile-$MIG_PROFILE_ID instances"
  for ((i=0; i<MIG_SLICE_COUNT; i++)); do
    nvidia-smi -i "$GPU" mig --create-gpu-instance "$MIG_PROFILE_ID" --default-compute-instance \
      || {
        echo "ERROR: failed to create slice $i on GPU $GPU (profile $MIG_PROFILE_ID)."
        echo "       Likely: profile too large for remaining capacity, or already at slice limit."
        exit 3
      }
  done
done

# Collect MIG UUIDs
echo ""
echo "[setup_mig] MIG layout:"
nvidia-smi -L | grep -E "MIG|GPU" | tee /tmp/nvidia_smi_L.txt

echo ""
echo "[setup_mig] MIG-UUIDs (saved to $UUID_FILE):"
nvidia-smi -L | grep -oE 'MIG-[a-f0-9-]+' | tee "$UUID_FILE"

COUNT=$(wc -l < "$UUID_FILE")
echo ""
echo "[setup_mig] DONE. Created $COUNT MIG slice(s)."
echo "[setup_mig] Next: bash scripts/deploy/brev/launch_kit_pool_mig.sh"
