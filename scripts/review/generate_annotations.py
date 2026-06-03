"""Generate annotation sidecar per template — ANNOTATION V2.

For each CP-* template:
  - Read template.json (scene roles, simulate_args)
  - Read function_gate JSONLs (success/fail history per template)
  - Read *_rewrite_bak files → rewrite_history
  - Read sweep_all_rewritten.jsonl → sweep_v2_result
  - Optional: read trace_<name>.jsonl if exists (trajectory data)
  - Output workspace/qa_runs/annotations/<name>.json with:
      narration: human-readable description (V2: includes rewrite history summary)
      expected_outcome: PASS/FAIL prediction + why
      scene_summary: robot type, conveyor, bins/targets, cube count
      failure_class: A (param) / B (handler bug) / C (scene-design) / D (stochastic/env)
      latest_gate_result: most recent function_gate verdict
      key_questions: 2-3 yes/no questions for the reviewer
      rewrite_history: list of {agent, summary} dicts derived from *_rewrite_bak files
      sweep_v2_result: result from sweep_all_rewritten.jsonl (or null)
      night_handler_fixes_applied: list of handler fix tags applicable to this template

Usage:
    python scripts/review/generate_annotations.py            # all templates
    python scripts/review/generate_annotations.py CP-13      # one
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
TPL_DIR = REPO/"workspace/templates"
ANNOT_DIR = REPO/"workspace/qa_runs/annotations"
QA_DIR = REPO/"workspace/qa_runs"

ANNOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Rewrite suffix → (agent label, human summary) ──────────────────────────────
REWRITE_SUFFIX_MAP = {
    "pre_amr_rewrite_bak":       ("AMR rewrite",         "robot_wizard+nav AMR migration applied"),
    "pre_scene_rewrite_bak":     ("scene rewrite",        "missing-component fix: tables/fixtures added"),
    "pre_spawn_rewrite_bak":     ("spawn rewrite",        "spawn-position fix: cube z/x corrected"),
    "pre_phys_rewrite_bak":      ("physics rewrite",      "physics fix: RigidBodyAPI added"),
    "pre_misc_rewrite_bak":      ("misc rewrite",         "routing/misc fix: drop_target removed / Table-order / slot widened"),
    "pre_stacking_rewrite_bak":  ("stacking rewrite",     "stacking fix: pallet enlarged"),
    "pre_ur10_rewrite_bak":      ("UR10 rewrite",         "UR10 wizard migration applied"),
    "pre_residual_rewrite_bak":  ("residual rewrite",     "residual misc fix applied"),
    "pre_sdfpath_bak":           ("spawn-z fix",          "spawn z-position corrected via SdfPath patch"),
    "pre_spawn_z_fix_bak":       ("spawn-z fix",          "spawn z-position corrected"),
}

# Night-handler fixes that apply to pick_place / sort / reorient patterns
HANDLER_FIXES_PP = [
    "verifier_raycast_chain",
    "fj_distance_gate_franka",
    "fj_distance_gate_ur10",
    "fj_distance_gate_sensor_gated",
    "fj_distance_gate_curobo_franka",
    "fj_distance_gate_curobo_ur10",
    "delivered_cubes_as_obstacles",
    "bin_drop_clearance_conditional",
    "ur10_home_joints",
    "deadlock_3s_timeout",
    "kinematic_flip_at_release",
    "measurement_artifact_filter",
]
PICK_PLACE_PATTERNS = {"pick_place", "sort", "reorient"}


# ── Load all function_gate jsonl results, keyed by template name (latest wins) ─
def load_gate_results():
    by_name = {}
    files = [
        "function_gate_2026-05-18.jsonl", "function_gate_wp_strict2.jsonl",
        "function_gate_p2_rerun.jsonl", "function_gate_shadow_sweep.jsonl",
        "function_gate_no_result_rerun.jsonl", "function_gate_remaining14_rerun.jsonl",
        "function_gate_timeouts_rerun.jsonl", "function_gate_nodata_rerun.jsonl",
        "function_gate_nodata2_rerun.jsonl",
    ]
    for fn in files:
        p = QA_DIR/fn
        if not p.exists(): continue
        for line in p.open():
            try: r = json.loads(line)
            except: continue
            name = r.get("template") or (r.get("name") or "").replace(".json","")
            if not name: continue
            by_name[name] = {"src": fn, **r}
    return by_name


# ── Load sweep_all_rewritten.jsonl → dict keyed by template ────────────────────
def load_sweep_v2():
    p = QA_DIR/"sweep_all_rewritten.jsonl"
    by_name = {}
    if not p.exists():
        return by_name
    for line in p.open():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except:
            continue
        name = r.get("template")
        if not name:
            continue
        by_name[name] = r
    return by_name


def _sweep_v2_result(name, sweep_idx):
    """Extract sweep_v2_result dict from sweep index, or None if not present."""
    r = sweep_idx.get(name)
    if r is None:
        return None
    # telepathic_fjs may be a list — store count
    tfjs = r.get("telepathic_fjs")
    tfjs_count = len(tfjs) if isinstance(tfjs, list) else (int(tfjs) if isinstance(tfjs, (int, float)) else 0)
    return {
        "honest_pass": bool(r.get("honest_pass")),
        "gates": r.get("gates") or {},
        "telepathic_fjs": tfjs_count,
        "exception": r.get("exception") or None,
    }


# ── Collect rewrite_history for a template ─────────────────────────────────────
def load_rewrite_history(name):
    """Find all *_rewrite_bak files for this template, return sorted list of {agent, summary}."""
    entries = []
    for suffix, (agent_label, summary) in REWRITE_SUFFIX_MAP.items():
        bak_path = TPL_DIR/f"{name}.json.{suffix}"
        if bak_path.exists():
            mtime = bak_path.stat().st_mtime
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            entries.append((mtime, {
                "agent": agent_label,
                "summary": summary,
                "timestamp": ts,
            }))
    # Sort by modification time (chronological)
    entries.sort(key=lambda x: x[0])
    return [e[1] for e in entries]


# ── Handler fixes applicable ───────────────────────────────────────────────────
def handler_fixes_for(tpl):
    """Return list of handler fix tags applicable to this template."""
    pattern = (tpl.get("intent") or {}).get("pattern_hint", "")
    if pattern in PICK_PLACE_PATTERNS:
        return list(HANDLER_FIXES_PP)
    return []


# ── Classification heuristic ──────────────────────────────────────────────────
def classify(gate, tpl):
    """Heuristic classification of failure mode."""
    if not gate or gate.get("delivered") or gate.get("success") or gate.get("function_gate_success"):
        return ("PASS", "controller delivers cube to target as designed")
    exc = gate.get("exception") or gate.get("fg_error", "")
    if "GetPrimAtPath" in str(exc) and "C++" in str(exc):
        return ("B", "handler bug: pyusd 0.24+ removed str overload; needs Sdf.Path() wrap")
    if str(exc).startswith("BUILD_"):
        return ("E", f"build failure: {exc}")
    speed = gate.get("cube_speed") or 0
    if isinstance(speed, (int,float)) and speed > 20:
        return ("C", f"physics blowup — cube ends at {speed:.0f} m/s, controller impulse bug")
    in_xy = gate.get("in_xy") or gate.get("in_target_xy")
    at_rest = gate.get("at_rest")
    if in_xy is False and at_rest is True and (gate.get("above_floor") or False):
        return ("C", "cube settles at rest above floor but outside target xy — released in wrong position")
    if in_xy is False and at_rest is True and not gate.get("above_floor"):
        return ("C", "cube settles below floor / outside target — likely dropped or never picked up")
    if gate.get("cube_ever_in_target_xy") and not gate.get("delivered"):
        return ("F", "cube reached target during sim but moved away by sim end (multi-cube dislodge)")
    return ("D", "unknown failure mode")


def _robot_from_tags(tags):
    """Parse 'isaac:robot.<name>' from structural_tags list."""
    for t in tags or []:
        if isinstance(t, str) and t.startswith("isaac:robot.") and "fixed_base" not in t:
            return t.split(".", 2)[-1]
    return None


def _is_cube_role(role_name, role_def):
    """Detect cube-like role by name + constraints + role_def shape."""
    n = role_name.lower()
    if any(k in n for k in ("workpiece", "cube", "block", "part", "brick", "item", "good_cube", "bad_cube", "sample", "package", "box")):
        return True
    if isinstance(role_def, dict):
        constraints = role_def.get("constraints") or []
        if isinstance(constraints, list):
            for c in constraints:
                if isinstance(c, str) and any(k in c.lower() for k in ("cube", "workpiece", "brick", "package", "part")):
                    return True
    return False


def _is_dest_role(role_name, role_def):
    n = role_name.lower()
    if any(k in n for k in ("destination", "_bin", "pallet", "target", "tray", "fixture", "platform", "stack", "drop")):
        return True
    if isinstance(role_def, dict):
        constraints = role_def.get("constraints") or []
        if isinstance(constraints, list):
            for c in constraints:
                if isinstance(c, str) and any(k in c.lower() for k in ("bin", "pallet", "tray", "platform", "fixture")):
                    return True
    return False


def scene_summary(tpl):
    """Read both role_defaults schema (new) AND intent.structural_features/tags (legacy)."""
    out = {}
    rd = tpl.get("role_defaults") or {}
    roles = tpl.get("roles") or {}
    intent = tpl.get("intent") or {}
    sf = intent.get("structural_features") or {}
    tags = intent.get("structural_tags") or []
    sa = tpl.get("simulate_args") or {}

    # ── Robot ──
    pr = rd.get("primary_robot") or {}
    robot = pr.get("class") or _robot_from_tags(tags)
    if not robot:
        for k, v in rd.items():
            if "robot" in k.lower() and isinstance(v, dict) and v.get("class"):
                robot = v["class"]; break
    out["robot"] = robot or "?"

    # ── Conveyor ──
    has_conv = False
    cv = {}
    for k in ("input_conveyor", "conveyor"):
        if k in rd:
            has_conv = True; cv = rd[k] or {}; break
    if not has_conv and sf.get("uses_conveyor_transport"):
        has_conv = True
    out["has_conveyor"] = has_conv
    if cv.get("surface_velocity"):
        out["conveyor_velocity"] = cv["surface_velocity"]

    # ── Destinations ──
    dests = []
    for k, v in (rd or {}).items():
        if isinstance(v, dict) and _is_dest_role(k, roles.get(k)):
            dests.append({"role": k, "path": v.get("path"), "pos": v.get("position"), "size": v.get("size")})
    if not dests:
        tgt = sa.get("target_path")
        if tgt:
            dests.append({"role": "simulate_target", "path": tgt, "pos": None, "size": None})
    out["destinations"] = dests
    out["n_destinations"] = len(dests) or sf.get("n_destination_bins") or 0

    # ── Cubes ──
    cubes = []
    for k, v in (rd or {}).items():
        if _is_cube_role(k, roles.get(k)):
            if isinstance(v, list):
                for vv in v:
                    if isinstance(vv, dict) and vv.get("path"): cubes.append(vv["path"])
            elif isinstance(v, dict) and v.get("path"):
                cubes.append(v["path"])
    if not cubes:
        cubes = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
    n_cubes = len(cubes) or sf.get("n_workpieces") or sf.get("n_cubes") or 0
    out["n_cubes"] = n_cubes
    out["cube_paths"] = [c for c in cubes if c][:6]

    # ── Industry/pattern hints from tags ──
    industries = [t.split(".",1)[-1] for t in tags if isinstance(t,str) and t.startswith("isaac:industry.")]
    if industries: out["industry"] = industries[0]
    grippers = [t.split(".",1)[-1] for t in tags if isinstance(t,str) and t.startswith("isaac:gripper.")]
    if grippers: out["gripper"] = grippers[0]
    return out


def narrate(name, tpl, gate, klass, why, rewrite_history):
    intent = (tpl.get("intent") or {}).get("pattern_hint") or "?"
    sc = scene_summary(tpl)
    parts = []
    parts.append(f"# {name}")
    parts.append(f"Intent: {intent}.  Robot: {sc.get('robot')}.")
    n_dest = len(sc.get("destinations") or [])
    parts.append(f"Scene: {sc.get('n_cubes')} cube(s), {n_dest} destination(s){' with conveyor' if sc.get('has_conveyor') else ''}.")
    if sc.get("destinations"):
        for d in sc["destinations"][:3]:
            parts.append(f"  - {d['role']} at {d.get('pos')}")

    # V2: rewrite history block
    if rewrite_history:
        parts.append("")
        parts.append(f"Rewrite history ({len(rewrite_history)} pass{'es' if len(rewrite_history) != 1 else ''}):")
        for rw in rewrite_history:
            ts = rw.get("timestamp", "")
            parts.append(f"  [{rw['agent']}] {rw['summary']}" + (f" ({ts})" if ts else ""))

    if gate:
        parts.append("")
        parts.append(f"Latest function-gate result ({gate.get('src','?')}):")
        parts.append(f"  delivered={gate.get('delivered') or gate.get('function_gate_success')}  in_xy={gate.get('in_xy') or gate.get('in_target_xy')}  at_rest={gate.get('at_rest')}  above_floor={gate.get('above_floor')}  speed={gate.get('cube_speed')}")
        if gate.get("cube_ever_in_target_xy") is not None:
            parts.append(f"  cube_ever_in_target_xy={gate.get('cube_ever_in_target_xy')}  delivered_ever={gate.get('delivered_ever')}")
    parts.append("")
    parts.append(f"AI hypothesis: class {klass} — {why}")
    parts.append("")
    parts.append("Watch for: cube being picked up cleanly, EE motion smooth, cube delivered without bouncing off target.")
    return "\n".join(parts)


def key_questions(klass):
    base = ["Did the cube reach the intended target area?", "Did the robot move smoothly without violent motions?"]
    if klass == "C":
        base.append("Did the cube get launched/flung at high speed or fall through the floor?")
    if klass == "B":
        base.append("Did the build succeed visually before the sim ran?")
    if klass == "F":
        base.append("Was the cube delivered but later dislodged by other activity?")
    if klass == "PASS":
        base.append("Does the delivery look stable (cube settles in bin/target, doesn't bounce out)?")
    return base[:3]


def generate_one(name, gate_idx, sweep_idx):
    tpl_path = TPL_DIR/f"{name}.json"
    if not tpl_path.exists():
        return None
    tpl = json.loads(tpl_path.read_text())
    gate = gate_idx.get(name)
    klass, why = classify(gate, tpl)
    rewrite_history = load_rewrite_history(name)
    narration = narrate(name, tpl, gate, klass, why, rewrite_history)
    sa = tpl.get("simulate_args") or {}
    out = {
        "template": name,
        "narration": narration,
        "scene_summary": scene_summary(tpl),
        "simulate_args": sa,
        "expected_outcome": "PASS" if klass == "PASS" else "FAIL",
        "failure_class": klass,
        "failure_reason": why,
        "latest_gate_result": {
            "src": gate.get("src") if gate else None,
            "delivered": (gate.get("delivered") or gate.get("function_gate_success")) if gate else None,
            "in_xy": (gate.get("in_xy") or gate.get("in_target_xy")) if gate else None,
            "at_rest": gate.get("at_rest") if gate else None,
            "above_floor": gate.get("above_floor") if gate else None,
            "cube_speed": gate.get("cube_speed") if gate else None,
            "cube_ever_in_target_xy": gate.get("cube_ever_in_target_xy") if gate else None,
            "exception": (gate.get("exception") or gate.get("fg_error")) if gate else None,
        },
        "key_questions": key_questions(klass),
        # ── V2 new fields ──
        "rewrite_history": rewrite_history,
        "sweep_v2_result": _sweep_v2_result(name, sweep_idx),
        "night_handler_fixes_applied": handler_fixes_for(tpl),
    }
    return out


def main():
    gate_idx = load_gate_results()
    sweep_idx = load_sweep_v2()
    print(f"Loaded {len(gate_idx)} gate results, {len(sweep_idx)} sweep_v2 results")
    only = sys.argv[1] if len(sys.argv) > 1 else None
    names = [only] if only else sorted([p.stem for p in TPL_DIR.glob("CP-*.json")])
    n = 0
    for name in names:
        out = generate_one(name, gate_idx, sweep_idx)
        if out is None:
            print(f"  {name}: NOT_FOUND")
            continue
        (ANNOT_DIR/f"{name}.json").write_text(json.dumps(out, indent=2))
        n += 1
    print(f"Wrote {n} annotation files to {ANNOT_DIR}")


if __name__ == "__main__":
    main()
