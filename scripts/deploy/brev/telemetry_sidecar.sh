#!/bin/bash
# telemetry_sidecar.sh — background nvidia-smi + host samplers.
#
# Samples at 1 Hz. Light overhead (~10 MB RAM, ~1 % CPU of a single core).
# Run in the background:
#   bash scripts/deploy/brev/telemetry_sidecar.sh &
#   echo $! > /tmp/telemetry_sidecar.pid
#
# Files written:
#   ${PERSIST_ROOT:-/mnt/persist}/telemetry/<timestamp>_gpu.csv
#   ${PERSIST_ROOT:-/mnt/persist}/telemetry/<timestamp>_host.csv
#   ${PERSIST_ROOT:-/mnt/persist}/telemetry/<timestamp>_kits.csv
#
# Stop with: kill $(cat /tmp/telemetry_sidecar.pid)

set -uo pipefail

PERSIST_ROOT="${PERSIST_ROOT:-/mnt/persist}"
INTERVAL_S="${INTERVAL_S:-1}"
TS="$(date +%Y%m%dT%H%M%S)"
DIR="${PERSIST_ROOT}/telemetry"
mkdir -p "$DIR"

GPU_CSV="${DIR}/${TS}_gpu.csv"
HOST_CSV="${DIR}/${TS}_host.csv"
KITS_CSV="${DIR}/${TS}_kits.csv"

echo "[telemetry] writing to $DIR/${TS}_*.csv (interval=${INTERVAL_S}s)"

# Headers
echo "timestamp,index,uuid,mem_used_mib,mem_free_mib,util_gpu_pct,util_mem_pct" > "$GPU_CSV"
echo "timestamp,cpu_pct,mem_used_mib,mem_avail_mib,swap_used_mib,load_1m" > "$HOST_CSV"
echo "timestamp,pid,port,rss_mib,cpu_pct" > "$KITS_CSV"

# Background sampler loops
gpu_loop() {
  while true; do
    TS_NOW=$(date +%s.%3N)
    nvidia-smi --query-gpu=index,uuid,memory.used,memory.free,utilization.gpu,utilization.memory \
               --format=csv,noheader,nounits 2>/dev/null \
      | while IFS=',' read -r idx uuid mu mf ug um; do
          echo "${TS_NOW},${idx// /},${uuid// /},${mu// /},${mf// /},${ug// /},${um// /}" >> "$GPU_CSV"
        done
    sleep "$INTERVAL_S"
  done
}

host_loop() {
  while true; do
    TS_NOW=$(date +%s.%3N)
    # Aggregate CPU% across all CPUs (1-shot pidstat-style via /proc/stat is heavier;
    # use top's batch mode for cheap aggregate)
    CPU_PCT=$(top -bn1 | awk '/^%Cpu/{print 100 - $8; exit}')
    MEM_LINE=$(free -m | awk '/^Mem:/{print $3","$7}')
    SWAP_USED=$(free -m | awk '/^Swap:/{print $3}')
    LOAD_1M=$(awk '{print $1}' /proc/loadavg)
    echo "${TS_NOW},${CPU_PCT:-0},${MEM_LINE},${SWAP_USED},${LOAD_1M}" >> "$HOST_CSV"
    sleep "$INTERVAL_S"
  done
}

kits_loop() {
  while true; do
    TS_NOW=$(date +%s.%3N)
    # For every Kit process, emit one row. PID → port resolved from /proc/<pid>/environ.
    for PID in $(pgrep -f isaac_sim_with_assist 2>/dev/null); do
      [ -d "/proc/$PID" ] || continue
      # Read KIT_RPC_PORT from environ (NUL-separated). Default 8001.
      PORT=$(tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null | grep -E '^KIT_RPC_PORT=' | cut -d= -f2 | head -1)
      PORT="${PORT:-8001}"
      # RSS from /proc/<pid>/status (KiB) → MiB
      RSS_KIB=$(awk '/^VmRSS:/{print $2}' "/proc/$PID/status" 2>/dev/null)
      RSS_MIB=$((${RSS_KIB:-0} / 1024))
      # CPU% via ps (1-shot)
      CPU=$(ps -o %cpu= -p "$PID" 2>/dev/null | tr -d ' ')
      echo "${TS_NOW},${PID},${PORT},${RSS_MIB},${CPU:-0}" >> "$KITS_CSV"
    done
    sleep "$INTERVAL_S"
  done
}

# Trap exit so background subshells get cleaned up
cleanup() {
  echo "[telemetry] stopping samplers"
  jobs -p | xargs -r kill 2>/dev/null
  exit 0
}
trap cleanup TERM INT EXIT

gpu_loop &
host_loop &
kits_loop &

# Wait forever (until trapped)
wait
