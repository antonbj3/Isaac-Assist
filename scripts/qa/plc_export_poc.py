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


def ir_to_controller_args(ir):
    """CONSUME-IR (the inverse of extract_ir): reconstruct the controller's ORCHESTRATION config from the IR.
    Proves the IR is a LOSSLESS engine-agnostic orchestration spec via the controller->IR->controller round-trip
    (the hot-swap-doctrine foundation: one IR, swappable engine). Scope = the orchestration (source_paths +
    per-object drop targets), NOT the full scene/sensor/obstacle setup (those are scene-build, not orchestration)."""
    objs, drops, dest = [], {}, None
    for s in ir["steps"]:
        o, pt = s.get("object"), s.get("place_target")
        if o and o not in objs:
            objs.append(o)
        if o and pt:
            if pt.get("kind") == "explicit_pose":
                drops[o] = pt["value"]
            elif pt.get("kind") == "destination_bbox_center":
                dest = pt["value"]
    args = {"source_paths": objs, "robot_family": ir.get("robot")}
    if drops:
        args["drop_targets"] = drops
    if dest:
        args["destination_path"] = dest
    return args


def roundtrip_check(tid):
    """controller -> IR -> controller: does the reconstructed orchestration match the template's original?"""
    t = json.load(open(f"{TPL_DIR}/{tid}.json"))
    sa = t.get("simulate_args") or {}
    code = t.get("code") or ""
    orig_src = sa.get("source_paths") or sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
    orig_drops = sa.get("drop_targets") or _code_drop_targets(code)
    orig_dest = sa.get("destination_path") or sa.get("target_path") or sa.get("drop_target_path")
    recon = ir_to_controller_args(extract_ir(tid))
    src_ok = list(orig_src) == list(recon.get("source_paths", []))
    rec_drops = recon.get("drop_targets") or {}
    # normalize the original: a LIST [pos parallel to source_paths] is SEMANTICALLY {cube_i: pos_i}
    if isinstance(orig_drops, list):
        orig_norm = {orig_src[i]: orig_drops[i] for i in range(min(len(orig_src), len(orig_drops)))}
    elif isinstance(orig_drops, dict):
        orig_norm = orig_drops
    else:
        orig_norm = {}
    drops_ok = (not orig_norm and not rec_drops) or all(
        cp in rec_drops and [round(float(v), 3) for v in orig_norm[cp]] == [round(float(v), 3) for v in rec_drops[cp]]
        for cp in orig_norm)
    # destination_path is a redundant FALLBACK when drop_targets covers every source cube (orchestration captured)
    drops_cover_all = bool(orig_norm) and all(cp in orig_norm for cp in orig_src)
    dest_ok = (orig_dest == recon.get("destination_path")) or drops_cover_all or (bool(orig_drops) and not orig_dest)
    return {"template": tid, "source_paths": src_ok, "drop_targets": drops_ok, "destination": dest_ok,
            "lossless": src_ok and drops_ok and dest_ok, "recon": recon}


def _phase_of(step_name):
    """Classify an IR step by canonical phase -> (command, target_mode, z_offset_const, guard_bool).
    target_mode: 'pick' (index into recipe pick), 'place', 'relative' (EE-relative lift), 'none'."""
    n = step_name
    if "Approach" in n: return ("CMD_MOVEL", "pick", "APPROACH_H", "ee_reached")
    if "Descend" in n:  return ("CMD_MOVEL", "pick", "GRASP_H", "ee_reached")
    if "Grip" in n:     return ("CMD_GRIP", "none", None, "grip_confirmed")
    if "Lift" in n:     return ("CMD_MOVEL", "relative", "LIFT_H", "ee_reached")
    if "Transit" in n:  return ("CMD_MOVEL", "place", "DROP_H", "ee_reached AND settled")
    if "Release" in n:  return ("CMD_RELEASE", "none", None, "dwell_done")
    if "Home" in n:     return ("CMD_HOME", "none", None, "system_ready")
    return ("CMD_HOME", "none", None, None)  # S_Done


def emit_sfc(ir):
    """Emit a deployable, GRAMMAR-VALID IEC 61131-3 Structured Text CASE state machine (the standard PLC
    sequence pattern). One CASE branch per SFC step: a command word (cmd / pick_idx / place_idx / offset_z) is
    written to a motion+gripper layer and PLCopen-style Done/Error feedback bits (ee_reached / grip_confirmed /
    settled / dwell_done) advance `step`. The Grip step re-descends up to 3x on a grip-miss then abandons the
    cube (faithful to pick_place.py:800-818). Geometry is engine/cell-agnostic: parts + place targets are
    RECIPE INDICES (the integrator binds index -> world pose); the concrete prim-paths/poses are in the header
    comment (slashes are legal only inside comments). VERIFIED parseable by the blark IEC 61131-3 grammar
    (scripts/qa/test_plc_st_parses.py). The motion/gripper layer + feedback are bound by a PLCopen MC_* /
    vendor library; not yet toolchain-compiled to bytecode (no IEC codegen), but it is syntactically valid ST."""
    steps = ir["steps"]
    # recipe: distinct picked objects (1-indexed) + their place targets
    recipe, idx_of = [], {}
    for s in steps:
        o = s.get("object")
        if o and o not in idx_of:
            idx_of[o] = len(recipe) + 1
            recipe.append((o, s.get("place_target")))
    L = []
    L.append(f"(* Deployable IEC 61131-3 ST (CASE state machine) -- template {ir['template']} *)")
    L.append(f"(* robot={ir['robot']}  objects={ir['n_objects']}  steps={len(steps)} *)")
    L.append(f"(* {ir['doc']} *)")
    L.append("(* RECIPE (integrator binds each index to a world pose): *)")
    for i, (o, pt) in enumerate(recipe):
        pt = pt or {}
        L.append(f"(*   [{i+1}] pick {o}  ->  place {pt.get('kind')}={pt.get('value')} *)")
    L.append("PROGRAM PickPlaceSequence")
    L.append("VAR CONSTANT")
    L.append("    CMD_NONE    : INT := 0;")
    L.append("    CMD_HOME    : INT := 1;")
    L.append("    CMD_MOVEL   : INT := 2;    (* linear move to recipe target + offset_z *)")
    L.append("    CMD_GRIP    : INT := 3;")
    L.append("    CMD_RELEASE : INT := 4;")
    L.append("    APPROACH_H  : REAL := 0.10;    (* pre-grasp approach height, m *)")
    L.append("    GRASP_H     : REAL := 0.0;     (* grasp height *)")
    L.append("    LIFT_H      : REAL := 0.15;    (* post-grip lift *)")
    L.append("    DROP_H      : REAL := 0.05;    (* pre-release drop height *)")
    L.append("END_VAR")
    L.append("VAR")
    L.append("    step       : INT  := 0;")
    L.append("    done       : BOOL := FALSE;")
    L.append("    grip_retry : INT  := 0;     (* grip-miss re-descend counter *)")
    L.append("    cmd        : INT  := 0;     (* command word -> motion/gripper layer *)")
    L.append("    pick_idx   : INT  := 0;     (* recipe index of part to pick *)")
    L.append("    place_idx  : INT  := 0;     (* recipe index of place target *)")
    L.append("    offset_z   : REAL := 0.0;   (* vertical approach/lift/drop offset *)")
    L.append("    system_ready   : BOOL := FALSE;   (* feedback <- motion/gripper layer *)")
    L.append("    ee_reached     : BOOL := FALSE;")
    L.append("    grip_confirmed : BOOL := FALSE;")
    L.append("    settled        : BOOL := FALSE;")
    L.append("    dwell_done     : BOOL := FALSE;")
    L.append("END_VAR")
    L.append("CASE step OF")
    for i, s in enumerate(steps):
        cmdc, mode, zoff, guard = _phase_of(s["step"])
        ridx = idx_of.get(s.get("object"), 0)
        L.append(f"    {i}: (* {s['step']} *)")
        asg = [f"cmd := {cmdc};"]
        if mode == "pick":
            asg.append(f"pick_idx := {ridx};")
        elif mode == "place":
            asg.append(f"place_idx := {ridx};")
        if zoff:
            asg.append(f"offset_z := {zoff};")
        L.append("        " + " ".join(asg) + ("    (* lift is EE-relative *)" if mode == "relative" else ""))
        if "Grip" in s["step"] and guard is not None:
            descend, lift = i - 1, i + 1
            skip = i + 4 if i + 4 < len(steps) else len(steps) - 1   # skip Lift/Transit/Release -> next Approach
            L.append(f"        IF {guard} THEN grip_retry := 0; step := {lift};")
            L.append(f"        ELSIF grip_retry < 3 THEN grip_retry := grip_retry + 1; step := {descend};")
            L.append(f"        ELSE grip_retry := 0; step := {skip}; END_IF;")
        elif guard is not None and i + 1 < len(steps):
            L.append(f"        IF {guard} THEN step := {i + 1}; END_IF;")
        else:
            L.append("        done := TRUE;")
    L.append("END_CASE")
    L.append("END_PROGRAM")
    return "\n".join(L)


def chain_ir(src, recv):
    """Export a 2-station CHAIN composition (station1 -> handoff -> station2) as one multi-station IR.
    Each station = its own robot/cell; the handoff is a PLC interlock (part_present_at_handoff)."""
    a, b = extract_ir(src), extract_ir(recv)
    steps = [s for s in a["steps"] if s["step"] != "S_Done"]
    steps.append({"step": "S_Handoff",
                  "action": f"(* station-1 ({a['robot']}) delivered part to handoff surface; interlock to station-2 *)",
                  "transition": "part_present_at_handoff"})
    for s in b["steps"]:
        if s["step"] == "S_Done":
            continue
        s2 = dict(s); s2["step"] = "T_" + s2["step"]  # station-2 namespace
        steps.append(s2)
    steps.append({"step": "S_Done", "action": "both stations -> home; halt", "transition": None})
    return {"template": f"{src}__{recv}", "robot": f"{a['robot']}->{b['robot']}",
            "n_objects": a["n_objects"] + b["n_objects"],
            "doc": f"2-station CHAIN (station1 {src} [{a['robot']}] -> handoff -> station2 {recv} [{b['robot']}]). "
                   f"Each station is its own robot/cell; handoff = a PLC interlock.",
            "steps": steps}


def main():
    if "--chain" in sys.argv:
        a = [x for x in sys.argv[1:] if not x.startswith("--")]
        if len(a) < 2:
            print("usage: --chain SRC RECV"); return
        os.makedirs(OUT_DIR, exist_ok=True)
        ir = chain_ir(a[0], a[1]); sfc = emit_sfc(ir)
        json.dump(ir, open(f"{OUT_DIR}/{ir['template']}.ir.json", "w"), indent=2)
        open(f"{OUT_DIR}/{ir['template']}.sfc.st", "w").write(sfc)
        print(f"  CHAIN {a[0]}->{a[1]}: {ir['robot']}, {ir['n_objects']} obj -> IR {len(ir['steps'])} steps -> "
              f"{OUT_DIR}/{ir['template']}.sfc.st")
        print("DONE"); return
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
