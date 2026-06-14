#!/usr/bin/env python3
"""
parity_check.py — cloud-vs-local #11 parity comparator for a Modal cloud wave.

Reads a modal_<stamp>.jsonl (default: latest in workspace/qa_runs/cloud_results/),
extracts each template's gate verdict (status + delivered_count/total from the
nested gate_full), and compares it to an expected local baseline. Flags any
cloud != local as a DIVERGENCE — that is the #11 platform-divergence finding to
RCA (likely a hardcoded path / asset-resolution / CPU-physics-determinism diff,
NOT a reason to distrust ALL cloud — localize the specific template).

Cloud verdict is comparable to local because the pool runs gate_one.py UNCHANGED
on a warp-1.11 image (matches local Isaac). Use N-of-M for stochastic templates.

Usage:
  python3 scripts/cloud/parity_check.py [modal_<stamp>.jsonl]
  python3 scripts/cloud/parity_check.py --expect CP-10=ok,CP-44=fail [file]
"""
import json, sys, os, glob

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(REPO, "workspace", "qa_runs", "cloud_results")

# Local baselines measured fresh-Kit-solo (3/3) this session — the trustworthy
# controls for the 2026-06-14 parity batch. "ok" = must PASS on cloud too;
# "fail" = must FAIL on cloud too (guards against cloud false-PASS). Update per wave.
EXPECT = {
    # POSITIVE parity (known-good controls — must pass on cloud)
    "CP-NEW-yrkesroll-gripper-vacuum-pick": "ok",
    "CP-10": "ok", "CP-35": "ok", "CP-48": "ok", "CP-19": "ok", "CP-47": "ok",
    "CP-70": "ok",  # UR10 asset-closure check (verifies /qa_assets upload)
    # NEGATIVE parity (known-bad — must fail on cloud; guards cloud false-pass)
    "CP-59": "fail", "CP-38": "fail", "CP-NEW-palletizer-mixed-sku": "fail",
    "CP-43": "fail", "CP-44": "fail",  # CP-44 now 3/4 (belt-slow); sphere form-limited
}


def verdict(rec):
    """Return (status, delivered, total, boot_s, err) from a cloud result record."""
    g = rec.get("gate_full")
    st, dc, tot = None, None, None
    if isinstance(g, str):
        try:
            gj = json.loads(g)
            st = gj.get("status")
            dc = gj.get("delivered_count")
            tot = gj.get("total")
        except Exception:
            pass
    if st is None and isinstance(rec.get("gate"), bool):
        st = "pass(bool)" if rec["gate"] else "fail(bool)"
    return st, dc, tot, rec.get("boot_s"), rec.get("error")


def is_pass(status):
    return bool(status) and ("ok" in status or status == "pass(bool)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a.startswith("--expect"):
            for kv in a.split("=", 1)[1].split(","):
                k, v = kv.split("=")
                EXPECT[k] = v
    if args:
        path = args[0] if os.path.isabs(args[0]) else os.path.join(RES, args[0])
    else:
        files = sorted(glob.glob(os.path.join(RES, "modal_*.jsonl")))
        if not files:
            sys.exit("no cloud result files in " + RES)
        path = files[-1]
    print(f"# parity check: {os.path.basename(path)}\n")
    rows = [json.loads(l) for l in open(path) if l.strip()]
    hdr = "%-42s %-12s %-9s %-7s %-8s %s" % (
        "template", "cloud", "deliv", "boot_s", "expect", "PARITY")
    print(hdr); print("-" * len(hdr))
    n_div = 0
    for r in sorted(rows, key=lambda x: x.get("template", "")):
        t = r.get("template", "?")
        st, dc, tot, boot, err = verdict(r)
        exp = EXPECT.get(t)
        deliv = ("%s/%s" % (dc, tot)) if dc is not None else "-"
        cloud_pass = is_pass(st)
        if exp is None:
            par = "(no baseline)"
        elif (exp == "ok") == cloud_pass:
            par = "OK"
        else:
            par = "*** DIVERGENCE ***"; n_div += 1
        bs = ("%.0f" % boot) if isinstance(boot, (int, float)) else "-"
        line = "%-42s %-12s %-9s %-7s %-8s %s" % (
            t, (st or "None"), deliv, bs, (exp or "-"), par)
        if err:
            line += "  ERR=" + str(err)[:50]
        print(line)
    print("\n%d template(s), %d DIVERGENCE(s)." % (len(rows), n_div))
    if n_div:
        print("=> RCA each divergence (hardcoded path? asset-resolve? CPU-physics determinism?).")
    else:
        print("=> full parity — cloud verdicts trustworthy for this wave.")


if __name__ == "__main__":
    main()
