#!/usr/bin/env python3
"""compose_robustness_suite.py (cont.319xx) — one-command OFFLINE regression gate for composition robustness.

Consolidates the session's offline composition-integrity checks so a single run verifies the whole surface after
ANY composer / template / chain change (CI-style). Pure + offline (no Kit, no Gemini) — the cheap pre-filter that
runs in seconds; the real verdict for a SCENE is always scene_eyes RAW in Kit, this guards the STRUCTURE around it.

Bundles:
  1. compose_layout_stress  — parallel-cell layout stays collision-free + append-stable across an edit timeline.
  2. compose_chain_stress   — chain handoff wiring sources the correct predecessor across reorder/remove/insert
                              (with a negative control that must FAIL = the gate has teeth).
  3. chain-integrity        — every CP-id referenced in chain_stages.json has a template file on disk (no orphans).
  4. template_lint          — each given template (default: the hand-authored CP-NEW/CP-CHAIN drafts) is internally
                              consistent (referenced prims created, drop_targets subset of source_paths).

Exit 0 + "ROBUSTNESS_SUITE: PASS" only if every sub-check passes; non-zero + the failing list otherwise.
"""
import sys, os, json, glob, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "..")
PY = sys.executable


def _run(label, argv):
    """Run a sub-check script; return (label, ok, tail)."""
    try:
        p = subprocess.run([PY] + argv, cwd=REPO, capture_output=True, text=True, timeout=120)
        ok = p.returncode == 0
        tail = (p.stdout.strip().splitlines() or ["<no output>"])[-1]
        return (label, ok, tail)
    except Exception as e:
        return (label, False, f"ERROR {e}")


def _chain_integrity():
    """Inline: every CP-id referenced in chain_stages.json has a template on disk."""
    cs = json.load(open(os.path.join(REPO, "workspace", "chain_stages.json")))
    on_disk = {os.path.splitext(os.path.basename(p))[0]
               for p in glob.glob(os.path.join(REPO, "workspace", "templates", "*.json"))}
    refs = set()

    def walk(o):
        if isinstance(o, str):
            if o.startswith("CP-"):
                refs.add(o)
        elif isinstance(o, dict):
            [walk(v) for v in o.values()]
        elif isinstance(o, list):
            [walk(v) for v in o]
    walk(cs)
    orphans = sorted(r for r in refs if r not in on_disk)
    return ("chain-integrity", not orphans,
            "all %d refs on disk" % len(refs) if not orphans else "ORPHANS: %s" % orphans)


def main(lint_ids):
    results = []
    results.append(_run("layout-stress", [os.path.join(HERE, "compose_layout_stress.py")]))
    results.append(_run("chain-stress", [os.path.join(HERE, "compose_chain_stress.py")]))
    results.append(_chain_integrity())
    # template_lint: high-confidence templates only count as a hard check; LOW-CONFIDENCE templates lint=0 (skipped)
    if lint_ids:
        results.append(_run("template_lint", [os.path.join(HERE, "template_lint.py")] + lint_ids))

    print("=== COMPOSITION ROBUSTNESS SUITE ===")
    for label, ok, tail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:16} {tail[:90]}")
    failed = [l for l, ok, _ in results if not ok]
    print(f"\nROBUSTNESS_SUITE: {'PASS' if not failed else 'FAIL — ' + ','.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    # default lint targets: the hand-authored drafts most prone to a dangling-ref typo (literal/Cube-loop idiom)
    ids = sys.argv[1:] or ["CP-CHAIN-FLAT", "CP-73", "CP-13"]
    sys.exit(main(ids))
