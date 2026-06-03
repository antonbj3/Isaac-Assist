"""Generate side-by-side comparison: Anton's R2 free-text vs virtual_eyes detection.

NO keyword regex — that was a brittle hack. Instead emit a markdown report
where each template shows:
  - Anton's free-text comment (what he saw)
  - virtual_eyes detected patterns + evidence (what the detector saw)
  - virtual_eyes narrative

Then I (Claude) read both and judge agreement manually for each one,
refining detectors based on observed gaps.
"""
import json
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
TAGS = REPO / "workspace/qa_runs/review_logs/human_tags.jsonl"
# Prefer the post-refactor R2 sweep output if it exists
OBS_R2 = REPO / "workspace/qa_runs/scene_observer_r2.jsonl"
OBS_OLD = REPO / "workspace/qa_runs/scene_observer.jsonl"
OBS = OBS_R2 if OBS_R2.exists() and OBS_R2.stat().st_size > 0 else OBS_OLD
OUT = REPO / "workspace/qa_runs/virtual_eyes_validation.md"


def main():
    tags = [json.loads(l) for l in TAGS.read_text().splitlines() if l.strip()]
    today = [t for t in tags if t.get("timestamp", "").startswith("2026-05-20") and t.get("tag") != "skip"]

    ve_data = {}
    if OBS.exists():
        for l in OBS.read_text().splitlines():
            if not l.strip(): continue
            try:
                r = json.loads(l)
                if r.get("template"): ve_data[r["template"]] = r
            except: pass

    lines = ["# Virtual Eyes — side-by-side Anton R2 vs detector",
             "",
             "For each R2-tagged template: Anton's free-text on top, virtual_eyes detection below.",
             "Judge manually whether they describe the same scene.",
             "",
             f"Total R2 tags (non-skip): {len(today)} | with VE data: {sum(1 for t in today if t['template'] in ve_data)}",
             ""]

    for t in sorted(today, key=lambda r: r.get("template", "")):
        name = t.get("template", "?")
        comment = t.get("comment", "")
        anton_tag = t.get("tag", "?")
        ve = ve_data.get(name, {}).get("virtual_eyes")
        record = ve_data.get(name, {})

        lines.append(f"## {name} ({anton_tag})")
        lines.append("")
        lines.append(f"**Anton:** {comment}")
        lines.append("")
        if ve is None:
            lines.append("*No virtual_eyes data captured.*")
            lines.append("")
            continue

        detected = [(n, p) for n, p in ve.get("patterns", {}).items() if p.get("detected")]
        if detected:
            lines.append("**Detected patterns:**")
            for n, p in detected:
                ev = p.get("evidence")
                lines.append(f"- `{n}` — {json.dumps(ev) if ev else '(no evidence)'}")
        else:
            lines.append("**Detected:** ∅")
        lines.append("")
        lines.append(f"**Narrative:** _{ve.get('narrative','')}_")
        lines.append("")
        lines.append(f"**Gates:** {json.dumps(record.get('gates', {}))}")
        lines.append("")
        lines.append(f"**honest_pass:** {record.get('honest_pass')}")
        lines.append("")
        # raw signals
        lines.append(f"**Signals:** cube_max_speed={record.get('cube_max_speed')}; ee_max_speed_in_placement={ve.get('ee_max_speed_in_placement')}; cube_xy_drift_post_target={ve.get('cube_xy_drift_post_target')}")
        lines.append("")
        lines.append("---")
        lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT}")
    print(f"  R2 templates: {len(today)} | with VE data: {sum(1 for t in today if t['template'] in ve_data)}")


if __name__ == "__main__":
    main()
