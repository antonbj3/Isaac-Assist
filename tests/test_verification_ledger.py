"""L0 tests for verification_ledger [P0-19] — Wilson math, surgical writes
(format preservation on compact + raw-unicode templates), run accumulation,
corpus summary. The format-preservation assertions are the load-bearing ones
(the P0-08 round-trip lesson)."""
import json

import pytest

from service.isaac_assist_service.qa import verification_ledger as vl

pytestmark = pytest.mark.l0


def test_wilson_known_values():
    assert vl.wilson_lower(0, 0) == 0.0
    assert abs(vl.wilson_lower(3, 3) - 0.4385) < 0.001   # 3/3 ≈ 0.438
    assert abs(vl.wilson_lower(1, 1) - 0.2065) < 0.001   # one pass proves little
    assert vl.wilson_lower(10, 10) > vl.wilson_lower(3, 3)  # more runs -> higher floor
    assert vl.wilson_lower(0, 3) == 0.0


def _mk_template(tmp_path, body: str):
    p = tmp_path / "CP-TEST.json"
    p.write_text(body, encoding="utf-8")
    return p


COMPACT = '{\n  "task_id": "CP-TEST",\n  "tags": ["a", "b"],\n  "note": "r\\u00e5"\n}\n'
RAW_UNICODE = '{\n  "task_id": "CP-TEST",\n  "note": "kub — på bordet ±1"\n}\n'


def test_surgical_insert_preserves_unrelated_bytes(tmp_path):
    for body in (COMPACT, RAW_UNICODE):
        p = _mk_template(tmp_path, body)
        vl.write_verification(p, {"function_gate": {"status": "pass", "n": 1, "m": 1,
                                                    "wilson_lower": 0.2065,
                                                    "last_run_sha": "abc", "last_run_at": "t"}})
        new = p.read_text(encoding="utf-8")
        # every original line except the final brace is byte-identical
        for line in body.strip().splitlines()[:-1]:
            assert line in new, f"original line mutated: {line!r}"
        assert json.loads(new)["verification"]["function_gate"]["status"] == "pass"


def test_update_replaces_in_place_not_duplicates(tmp_path):
    p = _mk_template(tmp_path, COMPACT)
    vl.record_gate_run(p, True, "sha1", ledger_path=tmp_path / "led.jsonl", when="t1")
    vl.record_gate_run(p, False, "sha2", ledger_path=tmp_path / "led.jsonl", when="t2")
    raw = p.read_text(encoding="utf-8")
    assert raw.count('"verification"') == 1, "field duplicated on update"
    rec = json.loads(raw)["verification"]["function_gate"]
    assert (rec["n"], rec["m"], rec["status"]) == (1, 2, "mixed")
    assert rec["last_run_sha"] == "sha2"
    # ledger has both rows
    rows = [json.loads(l) for l in (tmp_path / "led.jsonl").read_text().splitlines()]
    assert [r["passed"] for r in rows] == [True, False]


def test_status_transitions(tmp_path):
    p = _mk_template(tmp_path, COMPACT)
    led = tmp_path / "led.jsonl"
    r1 = vl.record_gate_run(p, True, "s", ledger_path=led, when="t")
    assert r1["function_gate"]["status"] == "pass"
    r2 = vl.record_gate_run(p, True, "s", ledger_path=led, when="t")
    assert r2["function_gate"]["status"] == "pass" and r2["function_gate"]["m"] == 2
    r3 = vl.record_gate_run(p, False, "s", ledger_path=led, when="t")
    assert r3["function_gate"]["status"] == "mixed"
    # all-fail template
    p2 = _mk_template(tmp_path.joinpath("d2") if False else tmp_path, COMPACT)  # reuse dir
    p2 = tmp_path / "CP-FAIL.json"; p2.write_text(COMPACT.replace("CP-TEST", "CP-FAIL"))
    rf = vl.record_gate_run(p2, False, "s", ledger_path=led, when="t")
    assert rf["function_gate"]["status"] == "fail"


def test_corpus_summary_counts(tmp_path):
    for i, body in enumerate([COMPACT, COMPACT, COMPACT]):
        (tmp_path / f"CP-{i:02d}.json").write_text(body.replace("CP-TEST", f"CP-{i:02d}"))
    led = tmp_path / "led.jsonl"
    vl.record_gate_run(tmp_path / "CP-00.json", True, "s", ledger_path=led, when="t")
    vl.record_gate_run(tmp_path / "CP-01.json", False, "s", ledger_path=led, when="t")
    summary = vl.corpus_summary(tmp_path)
    assert summary["counts"]["pass"] == 1
    assert summary["counts"]["fail"] == 1
    assert summary["counts"]["unmeasured"] == 1


def test_refuses_to_touch_broken_json(tmp_path):
    p = tmp_path / "CP-BROKEN.json"
    p.write_text('{"task_id": "x",}')  # invalid
    with pytest.raises(Exception):
        vl.write_verification(p, {"function_gate": {}})
