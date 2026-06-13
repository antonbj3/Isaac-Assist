#!/usr/bin/env python3
"""audit_arg_value_drift — code vs code_template ARGUMENT-VALUE drift.

audit_code_template_drift.py compares only tool-call NAME multisets, so a
controller call whose source_paths / destination / target differ between
`code` and `code_template` reads as IN_SYNC — strikes #5/#6/#7 were invisible
to it and each cost a live Kit round to find reactively. The build prefers
code_template+role_defaults, so an arg "fixed" only in `code` is DEAD TEXT.

This auditor extracts, by AST, the literal kwargs of the IDENTITY-BEARING
calls where arg-drift has historically bitten (controllers, joints, sensors,
moving-obstacle regs), substitutes role_defaults into code_template, matches
calls across the two fields by an identity kwarg, and reports value
disagreements. Pure static — no Kit, no sandbox exec.

FALSE-POSITIVE DISCIPLINE (Anton: every finding is a hypothesis):
- Only compares calls present with EQUAL count on both sides (count drift is
  audit_code_template_drift.py's job, not arg drift).
- Matches multi-instance calls by an identity kwarg; unmatched -> UNMATCHED,
  not drift.
- A kwarg that is a non-literal expression on EITHER side (comprehension,
  name ref) is UNCOMPARABLE -> never a drift finding.
- Cross-references each hit to the latest function-gate verdict: a FAILING
  template with controller-arg drift is a HIGH-confidence dead-text defect;
  a PASSING template is SUSPECT (inspect, NEVER auto-fix a passer).

Exit 0 always (report-only).
"""
from __future__ import annotations

import ast
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# identity-bearing calls: {tool: (identity_kwarg, [value_kwargs_to_diff])}
TARGETS = {
    "setup_pick_place_controller": ("robot_path", [
        "source_paths", "destination_path", "target_path", "task",
        "joint_path", "pick_target", "drop_target", "planning_obstacles",
        "claim_radius", "mutex_path", "sensor_path", "target_source",
        "end_effector_initial_height", "robot_family"]),
    "create_articulated_joint": ("joint_path", [
        "body0_path", "body1_path", "joint_type", "axis", "anchor",
        "limit_lower", "limit_upper", "passive_damping"]),
    "create_physics_joint": ("joint_path", [
        "body0", "body1", "joint_type", "axis", "lower_limit", "upper_limit",
        "local_pos0", "local_pos1", "anchor"]),
    "add_proximity_sensor": ("sensor_path", ["position", "size"]),
    "register_moving_obstacle": ("robot_path", ["obstacle_path"]),
}

_UNRESOLVED = object()


def _lit(node):
    """ast.literal_eval the node; _UNRESOLVED for any non-literal expr."""
    try:
        return ast.literal_eval(node)
    except Exception:
        return _UNRESOLVED


def extract_calls(code: str):
    """{tool: [ {identity, kwargs:{k:val|_UNRESOLVED}} ]} or None on parse fail."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    out = {t: [] for t in TARGETS}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else None)
        if fn not in TARGETS:
            continue
        id_kw, val_kws = TARGETS[fn]
        kw = {}
        for k in node.keywords:
            if k.arg in (val_kws + [id_kw]):
                kw[k.arg] = _lit(k.value)
        ident = kw.get(id_kw)
        ident = ident if isinstance(ident, str) else None
        out[fn].append({"identity": ident, "kwargs": kw})
    return out


def diff_template(t: dict):
    """Returns list of arg-drift findings for one template (after real role
    substitution of code_template). [] if in sync; None if not applicable."""
    ct = t.get("code_template")
    c = t.get("code")
    if not (ct and t.get("role_defaults") and c):
        return None
    try:
        from service.isaac_assist_service.chat.canonical_instantiator import (
            substitute_role_placeholders)
        ct_sub = substitute_role_placeholders(ct, t.get("role_defaults"))
    except Exception:
        return None  # cannot substitute -> do not guess
    ca = extract_calls(c)
    cb = extract_calls(ct_sub)
    if ca is None or cb is None:
        return None
    findings = []
    for tool, (id_kw, val_kws) in TARGETS.items():
        a, b = ca[tool], cb[tool]
        if not a and not b:
            continue
        if len(a) != len(b):
            continue  # COUNT drift -> the other auditor's job, not arg drift
        # match by identity kwarg ONLY when identities are unique on both sides.
        # Same-identity multi-calls (one robot running load+unload phases, or
        # an N-step retry of the same arm) cannot be reliably paired — positional
        # pairing cross-matches phases (machine-tender load.dest vs unload.dest),
        # a CHECKER ARTIFACT, not drift. Flag those ambiguous so triage discounts.
        ids_a = [x["identity"] for x in a]
        ids_b = [x["identity"] for x in b]
        unique = (all(ids_a) and all(ids_b)
                  and len(set(ids_a)) == len(ids_a) and len(set(ids_b)) == len(ids_b))
        if unique:
            bmap = {x["identity"]: x for x in b}
            pairs = [(x, bmap.get(x["identity"]), False) for x in a]
        else:
            pairs = [(ax, bx, True) for ax, bx in zip(a, b)]  # ambiguous positional
        for ax, bx, ambiguous in pairs:
            if bx is None:
                findings.append({"tool": tool, "identity": ax["identity"],
                                 "kwarg": "(call)", "code": "present",
                                 "ct": "UNMATCHED", "ambiguous": ambiguous})
                continue
            for k in val_kws:
                av, bv = ax["kwargs"].get(k, _UNRESOLVED), bx["kwargs"].get(k, _UNRESOLVED)
                if av is _UNRESOLVED or bv is _UNRESOLVED:
                    continue  # uncomparable on at least one side -> not drift
                if av != bv:
                    findings.append({"tool": tool, "identity": ax["identity"],
                                     "kwarg": k, "code": av, "ct": bv,
                                     "ambiguous": ambiguous})
    return findings


def latest_verdicts():
    """{template_stem: bool passed} from the run ledger (last row wins)."""
    led = REPO / "workspace/qa_runs/verification_ledger.jsonl"
    v = {}
    if not led.exists():
        return v
    for ln in led.read_text().splitlines():
        try:
            r = json.loads(ln)
        except Exception:
            continue
        stem = (r.get("template") or "").split("/")[-1].replace(".json", "")
        if stem and "passed" in r:
            v[stem] = bool(r["passed"])
    return v


def main():
    verds = latest_verdicts()
    hits = {}
    n_applicable = 0
    for f in sorted(glob.glob(str(REPO / "workspace/templates/CP*.json"))):
        if ".bak" in f or ".pre_" in f:
            continue
        try:
            t = json.load(open(f))
        except Exception:
            continue
        d = diff_template(t)
        if d is None:
            continue
        n_applicable += 1
        if d:
            hits[Path(f).stem] = d
    # rank: failing-template drift first (dead-text defect, high confidence)
    def conf(stem):
        v = verds.get(stem)
        return 0 if v is False else (1 if v is None else 2)  # FAIL<unknown<PASS
    ranked = sorted(hits.items(), key=lambda kv: (conf(kv[0]), kv[0]))
    print(f"ARG-VALUE DRIFT AUDIT: {len(hits)} templates with drift "
          f"/ {n_applicable} dual-representation templates checked\n")
    for stem, ds in ranked:
        v = verds.get(stem)
        tag = ("FAIL->HIGH-CONFIDENCE dead-text" if v is False
               else ("PASS->SUSPECT (inspect, do NOT auto-fix)" if v is True
                     else "UNGATED"))
        n_amb = sum(1 for d in ds if d.get("ambiguous"))
        n_clean = len(ds) - n_amb
        print(f"  {stem}  [{tag}]  ({n_clean} reliable, {n_amb} ambiguous-multi)")
        for d in ds[:8]:
            amb = " ~AMBIGUOUS-MULTI~" if d.get("ambiguous") else ""
            print(f"      {d['tool']}({d['identity']}).{d['kwarg']}:{amb} "
                  f"code={str(d['code'])[:55]}  ct={str(d['ct'])[:55]}")
    if "--json" in sys.argv:
        Path("/tmp/arg_value_drift.json").write_text(
            json.dumps({"hits": hits, "verdicts": verds}, indent=1, default=str))
        print("\nJSON -> /tmp/arg_value_drift.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
