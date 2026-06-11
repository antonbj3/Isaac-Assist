"""Introspection gate — session-assertion verdicts [P5-22 breadth].

Grades BUILD-introspection checks against the canonical execution's
per-call trace: families like grasp-pose-sampler (CP-63) and
ik-singularity-avoidance declare expectations about WHAT THE SESSION DID
(call counts, call args, per-call outputs, produced artifacts), not about
physics outcomes — the traversal gate can never measure them.

Pure function over the build result; no Kit, no sim time. Runtime-
introspection checks (ROS2 topics etc.) are declared with bridge-gated
kinds and short-circuit to BLOCKED — never False — so the ledger separates
"can't measure yet" from "measured and failed".

Check kinds (design: docs/notes/INTROSPECTION_GATE_DESIGN.md):
  call_count   {"tool", "expect"}                exact number of calls
  call_arg     {"tool", "arg", "expect", [which]} arg value on the call
  output_min   {"tool", "field", "min", [which]}  numeric floor on output
  artifact_len {"artifact", "min"}                produced-list length
  attr_equals  {"prim", "attr", "expect", [tol]}   live USD attr after the
               gate's stimulus sequence ran (values prefetched by gate_one
               into build["attrs"] as "<prim>.<attr>" -> value)
  ros2_topic   {...}                              BLOCKED (bridge-gated)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

BLOCKED_KINDS = {"ros2_topic", "ros2_action", "plc_register", "mqtt_topic",
                 "opcua_node"}


def _calls_for(trace: List[Dict], tool: str) -> List[Dict]:
    exact = [c for c in trace if (c.get("tool") or c.get("name")) == tool]
    if exact:
        return exact
    # expected_* names may shorten the real tool (interpolate ->
    # interpolate_trajectory); accept a UNIQUE prefix match only
    pref = {(c.get("tool") or c.get("name") or "") for c in trace
            if (c.get("tool") or c.get("name") or "").startswith(tool)}
    if len(pref) == 1:
        t2 = pref.pop()
        return [c for c in trace if (c.get("tool") or c.get("name")) == t2]
    return []


def _call_output(call: Dict) -> Any:
    out = call.get("output") if call.get("output") is not None else call.get("result")
    if isinstance(out, str):
        try:
            return json.loads(out)
        except (json.JSONDecodeError, ValueError):
            return out
    return out


def _field_from_output(out: Any, field: str) -> Any:
    if isinstance(out, dict):
        return out.get(field)
    if isinstance(out, str):
        # tolerate printed "field=value" / "field: value" text outputs
        m = re.search(rf"{re.escape(field)}\s*[=:]\s*(-?\d+(?:\.\d+)?)", out)
        if m:
            return float(m.group(1))
    return None


def evaluate_checks(checks: List[Dict], build: Dict) -> Dict:
    """checks x build-result -> verdict dict.

    build: the execute_template_canonical result; uses build["calls"] (or
    "call_results") with per-call tool/args/output, and build["artifacts"]
    (dict of produced lists) when present.
    """
    # the canonical instantiator returns the trace under "executed" —
    # accept the design-doc aliases too (l0 fixture bug 2026-06-11: tests
    # passed against "calls" while the real build said "executed")
    trace = (build.get("executed") or build.get("calls")
             or build.get("call_results") or [])
    artifacts = build.get("artifacts") or {}
    results = []
    n_pass = n_fail = n_blocked = 0
    for ck in checks:
        kind = ck.get("kind")
        r: Dict[str, Any] = {"kind": kind}
        if kind in BLOCKED_KINDS:
            r.update(status="BLOCKED", blocked_on="bridge")
            n_blocked += 1
            results.append(r)
            continue
        if kind == "call_count":
            got = len(_calls_for(trace, ck["tool"]))
            ok = got == int(ck["expect"])
            r.update(tool=ck["tool"], expect=ck["expect"], got=got)
        elif kind == "call_arg":
            calls = _calls_for(trace, ck["tool"])
            which = int(ck.get("which", 0))
            if which < len(calls):
                got = (calls[which].get("args") or {}).get(ck["arg"])
            else:
                got = None
            ok = got == ck["expect"]
            r.update(tool=ck["tool"], arg=ck["arg"], expect=ck["expect"],
                     got=got)
        elif kind == "output_min":
            calls = _calls_for(trace, ck["tool"])
            which = int(ck.get("which", 0))
            got = None
            if which < len(calls):
                got = _field_from_output(_call_output(calls[which]),
                                         ck["field"])
                if got is None:  # handlers often return verdict fields
                    got = (calls[which].get("result_meta") or {}).get(ck["field"])
            ok = got is not None and float(got) >= float(ck["min"])
            r.update(tool=ck["tool"], field=ck["field"], min=ck["min"],
                     got=got)
        elif kind == "output_max":
            calls = _calls_for(trace, ck["tool"])
            which = int(ck.get("which", 0))
            got = None
            if which < len(calls):
                got = _field_from_output(_call_output(calls[which]),
                                         ck["field"])
                if got is None:
                    got = (calls[which].get("result_meta") or {}).get(ck["field"])
            ok = got is not None and float(got) <= float(ck["max"])
            r.update(tool=ck["tool"], field=ck["field"], max=ck["max"],
                     got=got)
        elif kind == "attr_equals":
            key = f"{ck['prim']}.{ck['attr']}"
            got = (build.get("attrs") or {}).get(key)
            tol = ck.get("tol")
            if tol is not None and got is not None:
                try:
                    ok = abs(float(got) - float(ck["expect"])) <= float(tol)
                except (TypeError, ValueError):
                    ok = False
            else:
                ok = got == ck["expect"]
            r.update(prim=ck["prim"], attr=ck["attr"], expect=ck["expect"],
                     got=got)
        elif kind == "artifact_len":
            art = artifacts.get(ck["artifact"])
            got = len(art) if isinstance(art, (list, tuple)) else None
            ok = got is not None and got >= int(ck["min"])
            r.update(artifact=ck["artifact"], min=ck["min"], got=got)
        else:
            ok = False
            r.update(error=f"unknown check kind: {kind}")
        r["status"] = "PASS" if ok else "FAIL"
        n_pass += ok
        n_fail += not ok
        results.append(r)

    if n_blocked and not n_fail:
        status = "BLOCKED"          # nothing failed, but not fully measurable
    elif n_fail:
        status = "FAIL"
    else:
        status = "PASS"
    return {"success": status == "PASS", "status": status,
            "n_pass": n_pass, "n_fail": n_fail, "n_blocked": n_blocked,
            "checks": results}


def checks_from_expected_args(va: Dict) -> List[Dict]:
    """Mechanical expected_* -> checks mapping for legacy verify_args.

    Covers the measured families' conventions:
      expected_<tool>_calls: N            -> call_count
      expected_<tool>_<arg>: value        -> call_arg (first call)
      wpK_expected_<field>_min: x         -> output_min on check K-1
      expected_n_samples / sampling_mode  -> sampler artifact conventions
    Unmappable keys are returned as {"kind": "unmapped", ...} so the gate
    surfaces them instead of silently dropping an expectation.
    """
    checks: List[Dict] = []
    for k, v in va.items():
        if not k.startswith(("expected_", "wp")) or k in ("expected_random_pose",):
            continue
        m = re.match(r"expected_(\w+)_calls$", k)
        if m:
            checks.append({"kind": "call_count", "tool": m.group(1),
                           "expect": int(v)})
            continue
        m = re.match(r"wp(\d+)_expected_(\w+)_min$", k)
        if m:
            checks.append({"kind": "output_min", "tool": "check_singularity",
                           "field": m.group(2), "min": float(v),
                           "which": int(m.group(1)) - 1})
            continue
        if k == "expected_n_samples":
            # sampler count lives in the sampler call's OUTPUT, not in a
            # build-level artifacts dict
            checks.append({"kind": "output_min",
                           "tool": "setup_grasp_pose_sampler",
                           "field": "n_samples", "min": int(v)})
            continue
        if k == "expected_sampling_mode":
            checks.append({"kind": "call_arg", "tool": "setup_grasp_pose_sampler",
                           "arg": "sampling_mode", "expect": v})
            continue
        # GREEDY first group = split at the LAST underscore: the convention
        # is expected_<tool>_<arg> where tool itself may contain underscores
        # (expected_plan_trajectory_planner -> plan_trajectory / planner).
        m = re.match(r"expected_(\w+)_(\w+)$", k)
        if m and not k.endswith(("_topic",)):
            checks.append({"kind": "call_arg", "tool": m.group(1),
                           "arg": m.group(2), "expect": v})
            continue
        if k.endswith("_topic"):
            checks.append({"kind": "ros2_topic", "key": k, "expect": v})
            continue
        checks.append({"kind": "unmapped", "key": k, "value": v})
    return checks
