"""Append a human review tag for a template.

Usage:
  log_tag.py <CP-NAME> <yes|partial|no> [comment]
  log_tag.py CP-13 yes "cube delivered cleanly to pallet center"
  log_tag.py CP-18 no "cube launches off in +x at ~5s, never reaches bin"

Writes to workspace/qa_runs/review_logs/human_tags.jsonl (append-only).
"""
import json, sys, time
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
LOG = REPO/"workspace/qa_runs/review_logs/human_tags.jsonl"

VALID = {"yes", "partial", "no", "skip"}

def main():
    if len(sys.argv) < 3:
        print("usage: log_tag.py <CP-NAME> <yes|partial|no|skip> [comment]"); sys.exit(1)
    name = sys.argv[1]
    tag = sys.argv[2].lower()
    if tag not in VALID:
        print(f"invalid tag '{tag}', expected one of {VALID}"); sys.exit(2)
    comment = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "template": name,
        "tag": tag,
        "comment": comment,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"logged: {name} -> {tag}  {comment[:80]}")

if __name__ == "__main__":
    main()
