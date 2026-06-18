#!/usr/bin/env python3
"""PLC-export PoC (DIRECTION: project_isaac_assist_plc_export_direction, Anton 2026-06-14).

FIRST STEP (zero-boot, touches no running code): lift a pick-place template's orchestration into a
declarative Plan/Sequence-IR, then emit an IEC 61131-3 Sequential Function Chart (SFC) skeleton + ST
(Structured Text) action bodies. Proves the sim-validated sequence CAN be captured declaratively +
exported toward a real PLC, BEFORE any consume-the-IR refactor.

The IR is engine-agnostic (hot-swap doctrine): it names WHAT happens (pick cube_i -> place at target_i)
and the TRANSITION CONDITION between steps, not the cuRobo/Isaac specifics. A pick-place cycle per cube =
the controller's real phase chain (approach -> descend -> grip -> lift -> transit -> release), which is
exactly an SFC step chain with guarded transitions.

Usage:  python3 scripts/qa/plc_export_poc.py CP-CHAIN-FLAT [CP-01 CP-08 ...]
        python3 scripts/qa/plc_export_poc.py --all-chain   # all chain_stages sources/receivers
Emits, per template: the Sequence-IR (JSON) + an SFC skeleton (IEC 61131-3 text). Writes to
workspace/plc_export/<id>.ir.json + <id>.sfc.st (gitignored workspace) and prints a summary.
"""
import ast, json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL_DIR = f"{REPO}/workspace/templates"
OUT_DIR = f"{REPO}/workspace/plc_export"

# The 6 canonical pick-place phases (mirrors the cube_tracking controller in pick_place.py:_advance)
# as engine-agnostic SFC steps, each with its guard transition to the next.
_CYCLE = [
    ("ApproachAbove", "MoveLinear(target=PickXY + [0,0,APPROACH_H]); GripperOpen()",  "EE_reached(tol=0.05)"),
    ("Descend",       "MoveLinear(target=PickXY + [0,0,GRASP_H])",                     "EE_reached(tol=0.04)"),
    ("Grip",          "GripperClose()",                                                "grip_confirmed(dwell=0.4s)"),
    ("Lift",          "MoveLinear(target=EE + [0,0,LIFT_H])",                          "EE_reached(tol=0.05)"),
    ("Transit",       "MoveLinear(target=PlaceXY + [0,0,DROP_H])",                     "EE_reached(tol=0.015) AND settled(0.5s)"),
    ("Release",       "GripperOpen(); detach()",                                       "dt > 0.5s"),
]


def _code_drop_targets(code):
    """drop_targets often live in the template CODE (setup_pick_place_controller call), not simulate_args.
    AST-parse the call's drop_targets kwarg if it's a literal dict/list (faithful palletizer grid poses)."""
    try:
        tree = ast.parse(code)
    except Exception:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup_pick_place_controller":
            for kw in node.keywords:
                if kw.arg == "drop_targets" and isinstance(kw.value, (ast.Dict, ast.List)):
                    try:
                        return ast.literal_eval(kw.value)
                    except Exception:
                        return None
    return None


def _code_robot_family(code):
    """Authoritative robot from the controller call's robot_family kwarg (beats a 'UR10' comment match)."""
    try:
        tree = ast.parse(code)
    except Exception:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup_pick_place_controller":
            for kw in node.keywords:
                if kw.arg == "robot_family" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return None


def _cubes_and_targets(sa, code=""):
    """Return [(cube_path, place_target_repr), ...] from a template's simulate_args (+ code-level drop_targets)."""
    cubes = sa.get("source_paths") or sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
    cubes = [c for c in cubes if c]
    dest = sa.get("destination_path") or sa.get("target_path") or sa.get("drop_target_path")
    drops = sa.get("drop_targets") or _code_drop_targets(code)
    out = []
    for c in cubes:
        if isinstance(drops, dict) and c in drops:
            tgt = {"kind": "explicit_pose", "value": drops[c]}
        elif isinstance(drops, list) and c in cubes and cubes.index(c) < len(drops):
            tgt = {"kind": "explicit_pose", "value": drops[cubes.index(c)]}
        elif dest:
            tgt = {"kind": "destination_bbox_center", "value": dest}
        else:
            tgt = {"kind": "unknown", "value": None}
        out.append((c, tgt))
    return out


def extract_ir(tid):
    """Read a pick-place template -> declarative Sequence-IR."""
    t = json.load(open(f"{TPL_DIR}/{tid}.json"))
    sa = t.get("simulate_args") or {}
    _code = t.get("code") or ""
    robot = sa.get("robot_family") or _code_robot_family(_code) or ("ur10" if "/World/UR10" in _code else "franka")
    pairs = _cubes_and_targets(sa, t.get("code") or "")
    steps = [{"step": "S0_Home", "action": "MoveJoint(home_pose); GripperOpen()", "transition": "system_ready"}]
    sid = 1
    for i, (cube, tgt) in enumerate(pairs):
        for name, action, guard in _CYCLE:
            steps.append({
                "step": f"S{sid}_{name}_{i+1}",
                "action": action.replace("PickXY", f"pose({cube})").replace(
                    "PlaceXY", (f"{tgt['value']}" if tgt["kind"] == "explicit_pose"
                                else f"bbox_center({tgt['value']})")),
                "transition": guard,
                "object": cube,
                "place_target": tgt,
            })
            sid += 1
    steps.append({"step": "S_Done", "action": "MoveJoint(home_pose); halt", "transition": None})
    return {
        "template": tid, "robot": robot, "n_objects": len(pairs),
        "doc": "Engine-agnostic pick-place sequence IR (IEC 61131-3 SFC-shaped). One guarded step chain per object.",
        "steps": steps,
    }


def emit_sfc(ir):
    """Emit an IEC 61131-3 SFC skeleton + ST action bodies (text)."""
    L = []
    L.append(f"(* SFC export — template {ir['template']} ({ir['robot']}, {ir['n_objects']} objects) *)")
    L.append(f"(* {ir['doc']} *)")
    L.append("PROGRAM PickPlaceSequence")
    L.append("VAR  step : INT := 0;  done : BOOL := FALSE;  END_VAR")
    L.append("")
    steps = ir["steps"]
    for i, s in enumerate(steps):
        nxt = steps[i + 1]["step"] if i + 1 < len(steps) else None
        L.append(f"STEP {s['step']}:")
        L.append(f"    (* action *) {s['action']};")
        if s["transition"] is not None and nxt:
            L.append(f"    (* transition *) IF {s['transition']} THEN GOTO {nxt}; END_IF")
        else:
            L.append(f"    done := TRUE;")
        L.append("END_STEP")
    L.append("END_PROGRAM")
    return "\n".join(L)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all-chain" in sys.argv:
        cs = json.load(open(f"{REPO}/workspace/chain_stages.json"))["stages"]
        args = list(cs.keys())
    if not args:
        print("usage: plc_export_poc.py <TEMPLATE_ID> [...] | --all-chain"); return
    os.makedirs(OUT_DIR, exist_ok=True)
    for tid in args:
        if not os.path.exists(f"{TPL_DIR}/{tid}.json"):
            print(f"  {tid}: NOT FOUND"); continue
        ir = extract_ir(tid)
        sfc = emit_sfc(ir)
        json.dump(ir, open(f"{OUT_DIR}/{tid}.ir.json", "w"), indent=2)
        open(f"{OUT_DIR}/{tid}.sfc.st", "w").write(sfc)
        n_steps = len(ir["steps"])
        print(f"  {tid}: {ir['robot']}, {ir['n_objects']} obj -> IR {n_steps} steps -> SFC {OUT_DIR}/{tid}.sfc.st")
    print("DONE")


if __name__ == "__main__":
    main()
