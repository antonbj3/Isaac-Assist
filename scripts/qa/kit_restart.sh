#!/bin/bash
# kit_restart.sh — clean single-Kit restart with STALE-process kill + BIND verification.
#
# WHY (2026-06-17, feedback_kit_degradation_and_stale_process): launch_isaac_sim_with_assist.sh
# SILENTLY fails to bind 8001 if another Kit already holds it ("OSError [Errno 98] address already
# in use" in the boot log) — and /health still passes because the STALE Kit answers. A whole session
# was lost measuring against a stale, build-degraded Kit. `pgrep "kit|isaac"` MISSES the KitApp (it
# runs as bare `python` via heredoc), so detection must be by PORT (ss), not process name.
#
# This script (a FILE, not a heredoc-in-command — heredoc `sleep` gets blocked, exit 144) guarantees:
#   1. kill the launcher + whatever holds 8001 (stale or ours)
#   2. wait for the port to actually free
#   3. launch ONE fresh Kit
#   4. wait for /health, then VERIFY the boot log has NO "address already in use" (i.e. WE bound it)
# Exit 0 = fresh healthy Kit that WE own; nonzero = failed (caller must not trust measurements).
#
# Usage: bash scripts/qa/kit_restart.sh    [then run gate_one / chain_gate / scene_eyes]
set -u
PORT=8001
LAUNCH=/home/anton/projects/sibling-project/launch_isaac_sim_with_assist.sh
LOG="/tmp/kit_boot_$(date +%s).log"

echo "[kit_restart] killing launcher + any Kit on :$PORT ..."
pkill -9 -f "launch_isaac_sim_with_assist" 2>/dev/null
KP=$(ss -lptnH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
if [ -n "${KP:-}" ]; then echo "[kit_restart] killing 8001 holder pid=$KP"; kill -9 "$KP" 2>/dev/null; fi

# wait for the port to free (zombies release it within a couple seconds)
for i in $(seq 1 20); do
  if ! ss -lptnH "sport = :$PORT" 2>/dev/null | grep -q "pid="; then break; fi
  sleep 1
done
if ss -lptnH "sport = :$PORT" 2>/dev/null | grep -q "pid="; then
  echo "[kit_restart] FAIL: port $PORT still held after kill"; exit 4
fi

echo "[kit_restart] launching fresh Kit (log=$LOG) ..."
cd /home/anton/projects/sibling-project || { echo "[kit_restart] FAIL: cd"; exit 5; }
nohup "$LAUNCH" --headless > "$LOG" 2>&1 &
LP=$!

# wait for /health (base.kit boots ~7s; allow up to ~5 min for a cold boot)
HEALTHY=0
for i in $(seq 1 100); do
  if curl -s -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then HEALTHY=1; break; fi
  sleep 3
done
if [ "$HEALTHY" -ne 1 ]; then echo "[kit_restart] FAIL: no /health after wait (launcher pid=$LP, log=$LOG)"; exit 2; fi

# CRITICAL: verify WE bound the port (no stale Kit stole it)
if grep -qi "address already in use" "$LOG"; then
  echo "[kit_restart] FAIL: 'address already in use' in boot log — a STALE Kit holds :$PORT; /health is answering the WRONG Kit. log=$LOG"
  exit 3
fi

OWNER=$(ss -lptnH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
echo "[kit_restart] OK: fresh Kit healthy on :$PORT, owner pid=$OWNER, clean bind. log=$LOG"
echo "[kit_restart] REMINDER: run kit_health.py (positive control) before trusting any NEGATIVE result."
exit 0
