#!/bin/bash
# teardown.sh — stop Kit pool, sync logs to persistent volume.
#
# Optional flags:
#   --disable-mig    Also disable MIG mode (only when releasing the instance)
#   --keep-cache     Skip copying per-Kit warp/xdg caches to persist
#
# Logs land at /mnt/persist/logs/<timestamp>/ for post-mortem analysis.

set -uo pipefail

DISABLE_MIG=0
KEEP_CACHE=1
PERSIST_ROOT="${PERSIST_ROOT:-/mnt/persist}"

while [ $# -gt 0 ]; do
  case "$1" in
    --disable-mig) DISABLE_MIG=1 ;;
    --no-keep-cache) KEEP_CACHE=0 ;;
    *) echo "[teardown] unknown arg: $1"; exit 2 ;;
  esac
  shift
done

TS="$(date +%Y%m%dT%H%M%S)"
LOG_DIR="${PERSIST_ROOT}/logs/${TS}"
CACHE_DIR="${PERSIST_ROOT}/cache_snapshot/${TS}"

echo "[teardown] $(date -Is)"
echo "[teardown] Persist root: $PERSIST_ROOT"

# 1. Kill all Kit processes (the runner has already been pkill'd by operator)
echo "[teardown] Killing Kit processes..."
KIT_PIDS=$(pgrep -f isaac_sim_with_assist || true)
if [ -n "$KIT_PIDS" ]; then
  echo "  PIDs: $KIT_PIDS"
  # SIGTERM first, then SIGKILL after 5s
  echo "$KIT_PIDS" | xargs -r kill 2>/dev/null || true
  sleep 5
  KIT_PIDS=$(pgrep -f isaac_sim_with_assist || true)
  if [ -n "$KIT_PIDS" ]; then
    echo "  still alive, SIGKILL: $KIT_PIDS"
    echo "$KIT_PIDS" | xargs -r kill -9 2>/dev/null || true
  fi
else
  echo "  (no Kits running)"
fi

# 2. Stop telemetry sidecar if active
if [ -f /tmp/telemetry_sidecar.pid ]; then
  TPID=$(cat /tmp/telemetry_sidecar.pid)
  echo "[teardown] Stopping telemetry sidecar PID $TPID"
  kill "$TPID" 2>/dev/null || true
  rm -f /tmp/telemetry_sidecar.pid
fi

# 3. Sync Kit logs
mkdir -p "$LOG_DIR"
echo "[teardown] Copying Kit logs → $LOG_DIR"
cp -v /tmp/isaac_sim_launch_port*.log "$LOG_DIR/" 2>/dev/null || echo "  (no port logs to copy)"
cp -v /tmp/mig_uuids.txt "$LOG_DIR/" 2>/dev/null || true
cp -v /tmp/nvidia_smi_L.txt "$LOG_DIR/" 2>/dev/null || true

# 4. Optionally snapshot caches (useful as warm-cache seed for next instance)
if [ "$KEEP_CACHE" -eq 1 ]; then
  mkdir -p "$CACHE_DIR"
  echo "[teardown] Copying per-Kit caches → $CACHE_DIR (may take ~1 min)"
  for D in /tmp/warp_kit_* /tmp/cache_kit_*; do
    [ -d "$D" ] || continue
    cp -a "$D" "$CACHE_DIR/" 2>/dev/null || true
  done
fi

# 5. Optionally disable MIG
if [ "$DISABLE_MIG" -eq 1 ]; then
  echo "[teardown] Disabling MIG mode (requires sudo)..."
  if [ "$(id -u)" -ne 0 ]; then
    echo "  WARN: not root — re-running with sudo"
    sudo nvidia-smi -mig 0 || echo "  ERROR: nvidia-smi -mig 0 failed"
  else
    nvidia-smi -mig 0 || echo "  ERROR: nvidia-smi -mig 0 failed"
  fi
fi

echo "[teardown] DONE. Logs at $LOG_DIR"
