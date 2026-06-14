#!/usr/bin/env python3
"""
extract_sequence_ir.py — PoC: lift a pick-place template's ORCHESTRATION into a
declarative Plan/Sequence-IR, then emit an IEC 61131-3 (PLC) sequence skeleton.

WHY (Anton 2026-06-14, direction memo project_isaac_assist_plc_export_direction):
The pick-first / advance-belt / pick-next sequencing in our templates is exactly
the layer a real cell runs in PLC code (sequence + I/O + interlocks), NOT motion.
Today that sequence is IMPLICIT — buried in the handler's ~4400-line generated
state machine (_gen_pick_place_curobo) — and 0 templates carry a declarative
sequence field, so there is nothing to transpile to a PLC.

This PoC PROVES the sequence CAN be captured declaratively, by EXTRACTING it from
a template's role_defaults (the declarative scene) + its setup_pick_place_controller
call + the known controller semantics (nearest-first pick, sensor-gated belt,
N items -> destination). It emits:
  1. Plan-IR        (JSON: resources + items + a PackML-flavoured step/transition graph)
  2. PLC skeleton   (IEC 61131-3 Structured Text: a SFC-style CASE state machine + I/O map)

HONEST SCOPE (do not oversell): this is post-hoc EXTRACTION for the PoC. The real
architecture makes the IR the SOURCE OF TRUTH that the sim backend CONSUMES (so sim
and PLC stay in lockstep). And the generated ST is a HAPPY-PATH SKELETON: the hard
80% of real PLC work (E-stop, interlocks, fault recovery, robot-controller
handshakes, safety) is STUBBED and flagged, not solved. An automation engineer
hardens it; validate against OpenPLC (we ship it from the industrial-expansion phase).

Usage:  python3 scripts/plc/extract_sequence_ir.py CP-44 [--out DIR]
        (writes <CP>.plan_ir.json and <CP>.st next to --out, default ./plc_out/)
"""
import json, re, sys, os, argparse

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(tpl_name):
    p = os.path.join(REPO, "workspace", "templates", f"{tpl_name}.json")
    if not os.path.exists(p):
        sys.exit(f"template not found: {p}")
    return json.load(open(p))


def _controller_call(tpl):
    """Return the raw arg-text of setup_pick_place_controller, or None."""
    src = tpl.get("code_template") or tpl.get("code") or ""
    m = re.search(r"setup_pick_place_controller\((.*?)\n\)", src, re.S)
    if not m:
        m = re.search(r"setup_pick_place_controller\((.*?)\)", src, re.S)
    return m.group(1) if m else None


def _arg(call_text, name, default=None):
    if not call_text:
        return default
    m = re.search(rf"{name}\s*=\s*([^\n,]+(?:\[[^\]]*\])?)", call_text)
    if not m:
        return default
    return m.group(1).strip().rstrip(",").strip()


def extract_ir(tpl_name):
    tpl = _load(tpl_name)
    rd = tpl.get("role_defaults") or {}
    if not rd:
        sys.exit(f"{tpl_name}: no role_defaults — extractor handles role-based "
                 f"pick-place templates only (this is a PoC).")
    call = _controller_call(tpl)
    if call is None:
        sys.exit(f"{tpl_name}: no setup_pick_place_controller call — not a pick-place "
                 f"orchestration template (PoC scope).")

    robot = rd.get("primary_robot") or {}
    conv = rd.get("input_conveyor") or {}
    sensor = rd.get("pick_sensor") or {}
    dest = rd.get("primary_destination") or {}
    items = rd.get("workpieces") or []

    target_source = (_arg(call, "target_source") or '"curobo"').strip('"')
    drop_target = _arg(call, "drop_target")

    # Declarative resources — the swap boundary. sensor.signal/conveyor.motor are the
    # I/O contract a real PLC binds to (and a real sensor asset swaps in behind).
    resources = {
        "robot": {
            "path": robot.get("path"),
            "class": robot.get("class"),
            # MOTION is delegated to the robot controller (cuRobo in sim; the robot's own
            # planner/taught paths on real hw). PLC commands a program + waits a handshake.
            "motion_owner": "robot_controller",
            "sim_motion_backend": target_source,
        },
        "conveyor": {
            "path": conv.get("path"),
            "motor": "BeltMotor",            # PLC digital output
            "nominal_velocity_mps": (conv.get("surface_velocity") or [None])[0],
        },
        "pick_sensor": {
            "path": sensor.get("path"),
            "type": "proximity",             # faithful-synthetic in sim; real beam-break swaps in
            "signal": "PartAtPick",          # binary input the PLC reads (== isaac_sensor:triggered)
        },
        "gripper": {
            "type": "parallel_jaw",
            "close": "GripperClose",         # PLC output
            "feedback": "GripOK",            # PLC input (gripper-closed confirm)
        },
        "destination": {"path": dest.get("path"), "drop_target": drop_target},
    }

    n = len(items)
    # PackML-flavoured EXECUTE sub-sequence (SFC steps + guarded transitions). This mirrors
    # the curobo controller's actual semantics: belt runs, sensor gates each pick, belt
    # pauses during pick, robot picks (nearest-available) -> places at destination -> repeat.
    sequence = [
        {"step": "S0_HOME", "actions": ["BeltMotor:=OFF", "items_done:=0"],
         "transition": {"to": "S1_FEED", "guard": "CycleStart AND NOT EStop"}},
        {"step": "S1_FEED", "actions": ["BeltMotor:=ON"],
         "transition": {"to": "S2_BELT_STOP", "guard": "PartAtPick"}},
        {"step": "S2_BELT_STOP", "actions": ["BeltMotor:=OFF"],
         "transition": {"to": "S3_PICK", "guard": "TRUE"}},
        {"step": "S3_PICK",
         "actions": ["RobotProgram:=PICK", "RobotReq:=ON", "GripperClose:=ON"],
         "transition": {"to": "S4_PLACE", "guard": "RobotDone AND GripOK"}},
        {"step": "S4_PLACE",
         "actions": ["RobotReq:=OFF", "RobotProgram:=PLACE", "RobotReq:=ON"],
         "transition": {"to": "S5_RELEASE", "guard": "RobotDone"}},
        {"step": "S5_RELEASE", "actions": ["GripperClose:=OFF", "RobotReq:=OFF",
                                           "items_done:=items_done+1"],
         "transition": {"to": "S6_CHECK", "guard": "TRUE"}},
        {"step": "S6_CHECK", "actions": [],
         "transition": {"to": "S1_FEED", "guard": f"items_done < {n}",
                        "else": "S7_DONE"}},
        {"step": "S7_DONE", "actions": ["BeltMotor:=OFF"], "terminal": True},
    ]

    ir = {
        "_meta": {
            "source_template": tpl_name,
            "goal": tpl.get("goal"),
            "extractor": "extract_sequence_ir.py (PoC, post-hoc extraction)",
            "note": "Declarative Plan/Sequence-IR lifted from role_defaults + the "
                    "setup_pick_place_controller call. Target architecture: this IR is "
                    "the source of truth the sim backend CONSUMES (not extracted after).",
        },
        "task": "pick_place_conveyor",
        "resources": resources,
        "items": [it.get("path") for it in items],
        "item_count": n,
        "pick_order": "nearest_available",   # the curobo controller's _cube_to_pick policy
        "sequence": sequence,
        "unmodeled_safety": [
            "E-stop chain / safe-torque-off", "light-curtain / area scanner muting",
            "robot-cell interlocks + door switches", "belt jam / part-missing timeout + fault state",
            "gripper drop / part-present-after-place verification",
            "robot<->PLC handshake protocol (req/ack, program-complete, fault)",
        ],
    }
    return ir


# ───────────────────────── IEC 61131-3 Structured Text emitter ─────────────────────────
def emit_st(ir):
    n = ir["item_count"]
    r = ir["resources"]
    L = []
    L.append("(* ===================================================================== *)")
    L.append(f"(*  AUTO-GENERATED PLC SKELETON (IEC 61131-3 Structured Text)            *)")
    L.append(f"(*  source template : {ir['_meta']['source_template']:<48s}*)")
    L.append(f"(*  task            : {ir['task']:<48s}*)")
    L.append(f"(*  item count      : {str(n):<48s}*)")
    L.append("(*  GENERATED BY    : extract_sequence_ir.py (PoC)                       *)")
    L.append("(*                                                                       *)")
    L.append("(*  !! HAPPY-PATH SKELETON. The safety/interlock layer is STUBBED.       *)")
    L.append("(*  !! An automation engineer MUST add: E-stop, light curtains, jam/     *)")
    L.append("(*  !! timeout faults, door interlocks, robot handshake. Validate on     *)")
    L.append("(*  !! OpenPLC before any real I/O. See unmodeled_safety in the IR.       *)")
    L.append("(* ===================================================================== *)")
    L.append("")
    L.append("PROGRAM PickPlaceCell")
    L.append("VAR")
    L.append("    (* --- I/O map (bind to real channels in the PLC project) --- *)")
    L.append("    (* INPUTS *)")
    L.append(f"    PartAtPick   : BOOL;   (* proximity sensor {r['pick_sensor']['path']} *)")
    L.append("    RobotDone    : BOOL;   (* handshake: robot program complete          *)")
    L.append("    GripOK       : BOOL;   (* gripper-closed confirmation                *)")
    L.append("    CycleStart   : BOOL;   (* operator start pushbutton                  *)")
    L.append("    EStop        : BOOL;   (* TRUE = emergency stop active (STUB)        *)")
    L.append("    (* OUTPUTS *)")
    L.append(f"    BeltMotor    : BOOL;   (* conveyor motor {r['conveyor']['path']} *)")
    L.append("    RobotReq     : BOOL;   (* request robot to run selected program      *)")
    L.append("    RobotProgram : INT;    (* 1=PICK 2=PLACE                             *)")
    L.append("    GripperClose : BOOL;   (* close the parallel jaw                     *)")
    L.append("    (* INTERNAL *)")
    L.append("    STATE        : INT := 0;")
    L.append("    items_done   : INT := 0;")
    L.append(f"    N_ITEMS      : INT := {n};")
    L.append("END_VAR")
    L.append("")
    L.append("(* Global safety override — placeholder; real cell routes E-stop in hardware too *)")
    L.append("IF EStop THEN")
    L.append("    BeltMotor := FALSE; RobotReq := FALSE; GripperClose := FALSE;")
    L.append("    STATE := 0; items_done := 0;")
    L.append("    RETURN;")
    L.append("END_IF;")
    L.append("")
    L.append("CASE STATE OF")
    # map IR steps -> ST case arms
    code = {
        "S0_HOME": (0, "BeltMotor := FALSE; items_done := 0;",
                    "IF CycleStart THEN STATE := 1; END_IF;"),
        "S1_FEED": (1, "BeltMotor := TRUE;",
                    "IF PartAtPick THEN STATE := 2; END_IF;"),
        "S2_BELT_STOP": (2, "BeltMotor := FALSE;", "STATE := 3;"),
        "S3_PICK": (3, "RobotProgram := 1; RobotReq := TRUE; GripperClose := TRUE;",
                    "IF RobotDone AND GripOK THEN STATE := 4; END_IF;"),
        "S4_PLACE": (4, "RobotReq := FALSE; RobotProgram := 2; RobotReq := TRUE;",
                     "IF RobotDone THEN STATE := 5; END_IF;"),
        "S5_RELEASE": (5, "GripperClose := FALSE; RobotReq := FALSE; "
                          "items_done := items_done + 1;", "STATE := 6;"),
        "S6_CHECK": (6, "",
                     "IF items_done < N_ITEMS THEN STATE := 1; ELSE STATE := 7; END_IF;"),
        "S7_DONE": (7, "BeltMotor := FALSE;", "(* cycle complete; await reset *)"),
    }
    for st in ir["sequence"]:
        nm = st["step"]
        idx, act, trans = code[nm]
        L.append(f"    {idx}: (* {nm} *)")
        if act:
            L.append(f"        {act}")
        L.append(f"        {trans}")
    L.append("END_CASE;")
    L.append("END_PROGRAM")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("--out", default=os.path.join(REPO, "plc_out"))
    a = ap.parse_args()
    ir = extract_ir(a.template)
    os.makedirs(a.out, exist_ok=True)
    irp = os.path.join(a.out, f"{a.template}.plan_ir.json")
    stp = os.path.join(a.out, f"{a.template}.st")
    json.dump(ir, open(irp, "w"), indent=2)
    open(stp, "w").write(emit_st(ir) + "\n")

    print(f"=== {a.template}: extracted pick_place_conveyor sequence ===")
    print(f"  items={ir['item_count']}  pick_order={ir['pick_order']}  "
          f"belt={ir['resources']['conveyor']['nominal_velocity_mps']} m/s")
    print("  SFC steps: " + " -> ".join(s["step"] for s in ir["sequence"]))
    print(f"  Plan-IR : {irp}")
    print(f"  PLC ST  : {stp}")
    print(f"  unmodeled safety (engineer must add): {len(ir['unmodeled_safety'])} items")
    for s in ir["unmodeled_safety"]:
        print(f"     - {s}")


if __name__ == "__main__":
    main()
