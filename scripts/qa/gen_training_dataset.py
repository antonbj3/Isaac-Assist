#!/usr/bin/env python3
"""gen_training_dataset.py — extract the canonical library as a training dataset (Anton 2026-06-15).

"We want to train our OWN model later on tool calls or USD code, various abstractions." The verified
canonical templates ARE already that dataset: each is a (natural-language goal -> ordered tool-call
sequence -> USD scene). This dumps them as JSONL training records at BOTH abstraction levels:

  goal              the task in natural language (the prompt/target the model maps FROM).
  code              the raw executable body = the tool-call sequence in python (USD-code abstraction).
  tool_calls        the code parsed into [{tool, args}] (the explicit tool-call abstraction).
  io / footprint    composition metadata (input/output ports, footprint) for the composition level.
  meta              task_id, motion_controller, verified_status, n_objects.

Output: workspace/training_data/canonical_templates.jsonl (one record per template). Zero-boot, no
Kit, no Gemini, no ChromaDB — pure extraction. Run: gen_training_dataset.py [--all]
(default = VERIFIED_CORE only; --all = every template).
"""
import json, os, re, sys, glob

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
TPL_DIR = os.path.join(REPO, "workspace", "templates")
OUT_DIR = os.path.join(REPO, "workspace", "training_data")
from service.isaac_assist_service.chat.composer import template_footprint

# tool names worth capturing as the tool-call sequence (the public scene-building surface)
_KNOWN_TOOLS = ("create_prim", "create_bin", "create_conveyor", "create_rotary_table", "robot_wizard",
                "setup_pick_place_controller", "setup_cortex_behavior", "setup_nav_robot",
                "add_proximity_sensor", "run_usd_script", "create_camera", "add_semantic_label",
                "create_light", "setup_physics_scene", "create_material", "vision_detect_objects",
                "create_gravity_dispenser", "create_wheeled_robot", "navigate_to")


def parse_tool_calls(code):
    """Extract top-level fn(...) calls (balanced parens) for the known scene-building tools, in order."""
    out = []
    for fn in _KNOWN_TOOLS:
        for m in re.finditer(re.escape(fn) + r"\s*\(", code):
            j = m.end(); depth = 1; buf = []
            while j < len(code) and depth:
                ch = code[j]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if depth:
                    buf.append(ch)
                j += 1
            out.append({"tool": fn, "pos": m.start(), "args": "".join(buf).strip()})
    out.sort(key=lambda d: d["pos"])
    for d in out:
        d.pop("pos", None)
    return out


def is_verified_core(t):
    vs = t.get("verified_status") or ""
    mc = (t.get("motion_controllers") or {}).get("verified")
    return bool(mc or "stable_ok" in vs or "function-gate ✓" in vs) and "stable_fail" not in vs


def record(name, t):
    code = t.get("code") or ""
    sa = t.get("simulate_args") or t.get("verify_args") or {}
    cubes = [c for c in (sa.get("cube_paths") or sa.get("source_paths")
             or ([sa.get("cube_path")] if sa.get("cube_path") else [])) if c]
    fx = template_footprint(t, "x"); fy = template_footprint(t, "y")
    return {
        "task_id": t.get("task_id") or name,
        "goal": (t.get("goal") or "").strip(),
        "code": code,
        "tool_calls": parse_tool_calls(code),
        "io": {"inputs": cubes, "output": sa.get("target_path")},
        "footprint": {"x": [round(fx[0], 2), round(fx[1], 2)], "y": [round(fy[0], 2), round(fy[1], 2)]},
        "meta": {
            "motion_controller": (t.get("motion_controllers") or {}).get("verified"),
            "verified_status": t.get("verified_status"),
            "n_objects": len(cubes),
            "n_tool_calls": len(parse_tool_calls(code)),
        },
    }


def main():
    want_all = "--all" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "canonical_templates.jsonl")
    n = n_skip = 0
    tool_hist = {}
    with open(out_path, "w") as f:
        for fp in sorted(glob.glob(os.path.join(TPL_DIR, "*.json"))):
            name = os.path.basename(fp)[:-5]
            try:
                t = json.load(open(fp))
            except Exception:
                continue
            if not want_all and not is_verified_core(t):
                n_skip += 1
                continue
            if not (t.get("code") or "").strip() or not (t.get("goal") or "").strip():
                n_skip += 1
                continue
            r = record(name, t)
            for tc in r["tool_calls"]:
                tool_hist[tc["tool"]] = tool_hist.get(tc["tool"], 0) + 1
            f.write(json.dumps(r) + "\n")
            n += 1
    sys.stderr.write("wrote %s : %d records (%s), skipped %d\n" % (
        out_path, n, "ALL templates" if want_all else "VERIFIED_CORE", n_skip))
    sys.stderr.write("tool-call frequency: %s\n" % dict(sorted(tool_hist.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
