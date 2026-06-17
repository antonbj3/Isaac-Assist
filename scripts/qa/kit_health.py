#!/usr/bin/env python3
"""kit_health.py — POSITIVE-CONTROL pre-flight: is the Kit instrument TRUSTWORTHY right now?

WHY (2026-06-17, feedback_kit_degradation_and_stale_process): a Kit answers /health fine even when it is
build-degraded (cuRobo plan_pose fails, rigid bodies explode to z=-26000) or when /health is being answered
by a STALE Kit that stole :8001. A degraded instrument manufactures false NEGATIVES — it makes WORKING
templates look broken. The false-success guard cuts BOTH ways. So: before trusting ANY negative Kit result,
run a KNOWN-GOLD positive control and confirm it still delivers. If the control fails, the instrument is
degraded — restart (bash scripts/qa/kit_restart.sh) and re-measure; do NOT believe the negative.

Runs a fast known-gold single-cube template through the AUTHORITATIVE gate (simulate_traversal_check) and
asserts delivered_count > 0. Also reports who holds :8001 and the most-recent boot log's bind status.

Usage: python scripts/qa/kit_health.py [CONTROL_TEMPLATE]   (default CP-CHAIN-FLAT — fast, gate-clean, gold)
Exit 0 = TRUSTWORTHY (control delivered). Exit 1 = DEGRADED (control failed → restart). Exit 2 = setup error.
"""
import asyncio, sys, os, json, glob, subprocess
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)

CONTROL = sys.argv[1] if len(sys.argv) > 1 else "CP-CHAIN-FLAT"


def _port_owner(port=8001):
    try:
        out = subprocess.run(["ss", "-lptnH", f"sport = :{port}"], capture_output=True, text=True, timeout=5).stdout
        import re
        m = re.search(r"pid=(\d+)", out)
        if not m:
            return None
        pid = m.group(1)
        et = subprocess.run(["ps", "-o", "etimes=", "-p", pid], capture_output=True, text=True, timeout=5).stdout.strip()
        return {"pid": pid, "etimes_s": et}
    except Exception as e:
        return {"err": str(e)[:80]}


def _recent_boot_bind():
    logs = sorted(glob.glob("/tmp/kit_boot_*.log") + ["/tmp/kit_boot.log"], key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
    logs = [p for p in logs if os.path.exists(p)]
    if not logs:
        return {"log": None, "bind_conflict": "unknown"}
    log = logs[-1]
    try:
        with open(log, errors="ignore") as f:
            txt = f.read()
        return {"log": log, "bind_conflict": ("address already in use" in txt.lower())}
    except Exception as e:
        return {"log": log, "err": str(e)[:80]}


def _parse_gate(res):
    out = res.get("output") if isinstance(res, dict) and isinstance(res.get("output"), str) else json.dumps(res)
    for ln in (out.splitlines() if isinstance(out, str) else []):
        s = ln.strip()
        if s.startswith("{"):
            try:
                return json.loads(s)
            except Exception:
                pass
    return res if (isinstance(res, dict) and "delivered_count" in res) else None


async def main():
    print(f"[kit_health] port-8001 owner: {json.dumps(_port_owner())}")
    print(f"[kit_health] recent boot-log bind: {json.dumps(_recent_boot_bind())}")
    from service.isaac_assist_service.chat.tools import kit_tools as kt
    # liveness
    try:
        r = await kt.exec_sync("import omni.usd; print('OK')", timeout=20)
        if "OK" not in (r.get("output") or ""):
            print("[kit_health] FAIL: Kit RPC not responding"); sys.exit(2)
    except Exception as e:
        print(f"[kit_health] FAIL: Kit RPC error: {e}"); sys.exit(2)

    from service.isaac_assist_service.chat.tools.tool_executor import execute_tool_call
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    try:
        tpl = json.load(open(f"{REPO}/workspace/templates/{CONTROL}.json"))
    except Exception as e:
        print(f"[kit_health] FAIL: cannot load control template {CONTROL}: {e}"); sys.exit(2)

    await kt.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    # clear stale builtins subs (cross-build leakage)
    await kt.exec_sync("import builtins\nfor k in [x for x in list(vars(builtins)) if x.startswith('_curobo_pp_sub_')]:\n    try: delattr(builtins,k)\n    except Exception: pass\n", timeout=10)
    await execute_template_canonical(tpl); await settle_after_canonical(tpl)
    sa = tpl.get("simulate_args") or tpl.get("verify_args") or {}
    args = {k: sa[k] for k in ("cube_path", "cube_paths", "target_path", "duration_s", "xy_tolerance", "completeness") if k in sa}
    if "duration_s" not in args:
        args["duration_s"] = 120
    res = await execute_tool_call("simulate_traversal_check", args)
    data = _parse_gate(res)
    if data is None:
        print(f"[kit_health] FAIL: gate returned no parseable result: {str(res)[:200]}"); sys.exit(2)
    dc = data.get("delivered_count"); tot = data.get("total"); status = data.get("status")
    print(f"[kit_health] CONTROL {CONTROL}: delivered={dc}/{tot} status={status} success={data.get('success')}")
    if dc and dc > 0:
        print("[kit_health] ✅ INSTRUMENT TRUSTWORTHY — control delivered. Negative results can be believed.")
        sys.exit(0)
    else:
        print("[kit_health] ❌ INSTRUMENT DEGRADED — known-gold control FAILED to deliver. "
              "Do NOT trust negative results. Run: bash scripts/qa/kit_restart.sh")
        sys.exit(1)

asyncio.run(main())
