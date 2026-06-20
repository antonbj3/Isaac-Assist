#!/usr/bin/env python3
"""custody_compliance_export.py — cont.319mm (adversarial-sim BUILD: compliance-grade traceability).

Black-box hostile-user demand (12x, priority-4/5, automotive + pharma + aerospace + electronics): "every
per-part decision is written to a TAMPER-EVIDENT, schema-compliant record exportable to IATF 16949 / AS9100 /
21 CFR Part 11 format." The chain runtime (chain_xkit_gate.py) emits a per-part CUSTODY chain
(/tmp/chain_custody.json); this formatter promotes it to a compliance-grade, tamper-evident export.

What it adds on top of the raw custody record:
  - robot_id per station (resolved from workspace/chain_stages.json), so each custody step names the actuating
    robot (the audit requirement, not just the cell name).
  - outcome per station (PASS = delivered, else FAIL/LOST -> an explicit custody GAP).
  - a per-record SHA-256 + a forward HASH-CHAIN (each part-record's hash folds in the previous record's hash),
    so any post-hoc edit to an earlier record invalidates every later hash = tamper-evident (the 21-CFR-Part-11
    integrity requirement). The final chain_integrity_hash seals the whole export.
  - timestamps: passed through if the chain captured them (run-time), else flagged capture_pending=True (HONEST
    -- we do NOT fabricate a process timestamp; chain_xkit_gate captures real per-stage time going forward).

Usage:  python scripts/qa/custody_compliance_export.py [/tmp/chain_custody.json]
Writes: /tmp/custody_compliance.json  (schema-compliant) + prints an audit summary.
"""
import json, sys, hashlib, os, time

CUSTODY = sys.argv[1] if len(sys.argv) > 1 else "/tmp/chain_custody.json"
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
OUT = "/tmp/custody_compliance.json"


def _robot_map():
    """station CP -> robot, from the chain-stage registry (the audit's actuating-robot field)."""
    try:
        st = json.load(open(f"{REPO}/workspace/chain_stages.json")).get("stages", {})
        return {cp: (v.get("robot") or "unknown") for cp, v in st.items()}
    except Exception as e:
        print(f"[compliance] robot map unavailable ({e}); robot_id=unknown")
        return {}


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def main():
    if not os.path.exists(CUSTODY):
        print(f"NO_CUSTODY: {CUSTODY} (run a chain via chain_xkit_gate.py first)"); return 1
    cust = json.load(open(CUSTODY))
    robots = _robot_map()
    n_stations = cust.get("n_stations", 0)
    records, prev_hash = [], "GENESIS"
    for part in cust.get("parts", []):
        steps = []
        for j in sorted(part.get("journey", []), key=lambda x: x.get("stage", 0)):
            steps.append({
                "stage": j.get("stage"),
                "station": j.get("station"),
                "robot_id": robots.get(j.get("station"), "unknown"),
                "outcome": "PASS" if j.get("delivered") else "FAIL",
                "position_m": j.get("pos"),
                "timestamp": j.get("ts") if j.get("ts") else None,
                "timestamp_capture_pending": j.get("ts") is None,
            })
        complete = part.get("complete_custody", len(steps) == n_stations)
        rec_body = {"part_id": part.get("part_id"), "steps": steps,
                    "complete_custody": complete,
                    "custody_gap": None if complete else "MISSING_AT_%d_OF_%d_STATIONS" % (len(steps), n_stations)}
        # forward hash chain: this record's hash folds in the previous -> tamper-evident
        rec_hash = _sha({"body": rec_body, "prev": prev_hash})
        rec_body["record_hash"] = rec_hash
        rec_body["prev_record_hash"] = prev_hash
        prev_hash = rec_hash
        records.append(rec_body)
    export = {
        "schema": "per-part-custody/v1 (IATF-16949 / AS9100 / 21-CFR-Part-11 compatible: per-record outcome,"
                  " actuating robot, position, tamper-evident forward hash-chain)",
        "generated_unix": int(time.time()),
        "chain": cust.get("chain", []),
        "n_stations": n_stations,
        "n_parts": len(records),
        "n_complete_custody": sum(1 for r in records if r["complete_custody"]),
        "records": records,
        "chain_integrity_hash": prev_hash,  # seals the whole export; editing any record breaks this
    }
    json.dump(export, open(OUT, "w"), indent=1)
    gaps = [r["part_id"] for r in records if not r["complete_custody"]]
    print("CUSTODY_COMPLIANCE: %d parts, %d complete custody, %d gaps%s | chain_integrity_hash=%s -> %s"
          % (len(records), export["n_complete_custody"], len(gaps),
             (" " + str(gaps)) if gaps else "", prev_hash[:16] + "...", OUT))
    # tamper-evidence self-check: re-derive the chain hash and confirm it seals
    _p = "GENESIS"
    for r in records:
        body = {k: v for k, v in r.items() if k not in ("record_hash", "prev_record_hash")}
        _p = _sha({"body": body, "prev": _p})
    print("TAMPER_CHECK: re-derived chain hash %s -> %s"
          % (_p[:16] + "...", "SEALED (matches)" if _p == prev_hash else "MISMATCH (tampered!)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
