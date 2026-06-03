#!/bin/bash
# launch_kit_pool_mig.sh — launch one Kit per MIG slice.
#
# Reads MIG-UUIDs from /tmp/mig_uuids.txt (created by setup_mig.sh).
# Ports auto-assign starting at 8001.
#
# Per-Kit isolation (kills opus#2 hypotheses #3, #4, #7):
#   CUDA_VISIBLE_DEVICES=MIG-<UUID>      # slice pinning
#   KIT_RPC_PORT=<8001+i>                # unique RPC port
#   WARP_CACHE_PATH=/tmp/warp_kit_<port> # per-Kit Warp cache (kills PCH race)
#   XDG_CACHE_HOME=/tmp/cache_kit_<port> # per-Kit KVDB / extscache (kills lock)
#   KIT_HEADLESS_POOL=1                  # optional: skip SSE retries
#
# Override:
#   PORT_BASE=9001 ./launch_kit_pool_mig.sh   # ports 9001/9002/...
#   UUID_FILE=/somewhere/else.txt ./launch_kit_pool_mig.sh
#   ONE_SLICE_INDEX=2 ./launch_kit_pool_mig.sh   # only relaunch slice index 2

set -euo pipefail

UUID_FILE="${UUID_FILE:-/tmp/mig_uuids.txt}"
PORT_BASE="${PORT_BASE:-8001}"
LAUNCH_SCRIPT="${LAUNCH_SCRIPT:-/home/anton/projects/sibling-project/launch_isaac_sim_with_assist.sh}"
HEALTH_TIMEOUT_S=180
ONE_SLICE_INDEX="${ONE_SLICE_INDEX:-}"

if [ ! -f "$UUID_FILE" ]; then
  echo "ERROR: $UUID_FILE not found. Run setup_mig.sh first."
  exit 1
fi

mapfile -t UUIDS < "$UUID_FILE"
if [ "${#UUIDS[@]}" -eq 0 ]; then
  echo "ERROR: $UUID_FILE empty."
  exit 1
fi

if [ ! -x "$LAUNCH_SCRIPT" ] && [ ! -f "$LAUNCH_SCRIPT" ]; then
  echo "ERROR: launch script not found: $LAUNCH_SCRIPT"
  exit 1
fi

# Source ROS2 if present (used by isaacsim.ros2.bridge templates)
if [ -f /opt/ros/humble/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
fi

unset DISPLAY
unset WAYLAND_DISPLAY

launch_one() {
  local SLICE_INDEX=$1
  local UUID=$2
  local PORT=$((PORT_BASE + SLICE_INDEX))
  local WARP_DIR="/tmp/warp_kit_${PORT}"
  local CACHE_DIR="/tmp/cache_kit_${PORT}"
  local LOG="/tmp/isaac_sim_launch_port${PORT}.log"

  mkdir -p "$WARP_DIR" "$CACHE_DIR"

  echo "[pool] slice $SLICE_INDEX → port $PORT"
  echo "       MIG-UUID:        $UUID"
  echo "       WARP_CACHE_PATH: $WARP_DIR"
  echo "       XDG_CACHE_HOME:  $CACHE_DIR"
  echo "       log:             $LOG"

  CUDA_VISIBLE_DEVICES="$UUID" \
  KIT_RPC_PORT="$PORT" \
  WARP_CACHE_PATH="$WARP_DIR" \
  XDG_CACHE_HOME="$CACHE_DIR" \
  KIT_HEADLESS_POOL=1 \
    nohup bash "$LAUNCH_SCRIPT" --headless \
    > "$LOG" 2>&1 &
  local PID=$!
  echo "       PID:             $PID"

  # Stagger launches by 5 s to avoid GPU init contention even with MIG
  # (PhysX startup briefly hits driver-wide locks)
  sleep 5
}

# Either launch all slices or just one (for restart-on-failure)
if [ -n "$ONE_SLICE_INDEX" ]; then
  launch_one "$ONE_SLICE_INDEX" "${UUIDS[$ONE_SLICE_INDEX]}"
else
  for i in "${!UUIDS[@]}"; do
    launch_one "$i" "${UUIDS[$i]}"
  done
fi

# Wait for all (or one) to become healthy
echo ""
echo "[pool] Waiting up to ${HEALTH_TIMEOUT_S}s for Kit(s) to come up..."

check_ports=()
if [ -n "$ONE_SLICE_INDEX" ]; then
  check_ports=("$((PORT_BASE + ONE_SLICE_INDEX))")
else
  for i in "${!UUIDS[@]}"; do
    check_ports+=("$((PORT_BASE + i))")
  done
fi

for PORT in "${check_ports[@]}"; do
  for _ in $(seq 1 $((HEALTH_TIMEOUT_S / 5))); do
    if curl -s --max-time 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      echo "  [OK] port $PORT alive"
      break
    fi
    sleep 5
  done
done

echo ""
echo "[pool] Pool status:"
for PORT in "${check_ports[@]}"; do
  HEALTH=$(curl -s --max-time 2 "http://127.0.0.1:${PORT}/health" 2>&1 || echo "DOWN")
  echo "  port $PORT: $HEALTH"
done
