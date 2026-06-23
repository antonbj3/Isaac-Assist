"""L0 tests for qa/task_outcome + the diagnose_task_outcome handler [P2-06].

Synthetic ts_*.json artifacts exercise every WHY class; thresholds mirror the
validated prototype (scripts/qa/why_classify.py). The handler tests prove the
LLM-callable path end-to-end without Kit.
"""
import asyncio
import json

import pytest

from service.isaac_assist_service.qa import task_outcome as to

pytestmark = pytest.mark.l0


def _artifact(items_seq, init, dests=None, belts=None, template="CP-TEST"):
    """Build a minimal ts_*.json dict. items_seq: {name: [(t, p, up), ...]}"""
    ts = sorted({t for seq in items_seq.values() for t, _, _ in seq})
    rows = []
    for t in ts:
        row = {"t": t, "ee": None, "items": {}, "contacts": []}
        for nm, seq in items_seq.items():
            for st, p, up in seq:
                if st == t:
                    row["items"][nm] = {"p": p, "up": up, "spd": 0, "vz": 0}
        rows.append(row)
    return {
        "template": template,
        "meta": {"init": init,
                 "dest_bbox": dests or {},
                 "belt_bbox": belts or {}},
        "rows": rows,
        "provenance": {"sha": "test"},
    }


_BIN = {"/World/Bin": [[0.4, -0.4, 0.75], [0.6, -0.2, 0.87]]}
_BELT = {"/World/Belt": [[-0.8, 0.3, 0.78], [0.0, 0.5, 0.83]]}


def test_delivered_clean():
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (5, [0.0, 0.0, 1.2], 1.0),
                    (10, [0.5, -0.3, 0.80], 0.99)]},
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN)
    out = to.classify_timeseries(art)
    assert out["objects"]["Cube_1"]["why"] == "DELIVERED_CLEAN"
    assert out["all_clean"] is True


def test_toppled_in_dest():
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (5, [0.0, 0.0, 1.2], 1.0),
                    (10, [0.5, -0.3, 0.80], 0.3)]},   # up=0.3 -> ~72 deg
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN)
    o = to.classify_timeseries(art)["objects"]["Cube_1"]
    assert o["why"] == "TOPPLED_IN_DEST" and o["evidence"]["tilt_deg"] > 30


def test_not_picked_never_moves():
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (10, [-0.5, 0.4, 0.84], 1.0)]},
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN)
    assert to.classify_timeseries(art)["objects"]["Cube_1"]["why"] == "NOT_PICKED"


def test_rode_off_belt():
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (10, [0.3, 0.4, 0.84], 1.0)]},
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN, belts=_BELT)
    # never lifted, ended past belt x-exit (0.0) -> conveyor-sync miss
    assert to.classify_timeseries(art)["objects"]["Cube_1"]["why"] == "RODE_OFF_BELT"


def test_flung_to_floor():
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (5, [0.0, 0.0, 1.3], 1.0),
                    (10, [0.9, 0.9, 0.03], 0.5)]},
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN)
    assert to.classify_timeseries(art)["objects"]["Cube_1"]["why"] == "FLUNG_TO_FLOOR"


def test_drop_imprecise():
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (5, [0.0, 0.0, 1.2], 1.0),
                    (10, [0.2, -0.6, 0.80], 1.0)]},   # lifted, missed the bin
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN)
    o = to.classify_timeseries(art)
    assert o["objects"]["Cube_1"]["why"] == "DROP_IMPRECISE_OR_EJECT"
    assert o["all_clean"] is False and o["counts"]["DROP_IMPRECISE_OR_EJECT"] == 1


def test_diagnose_reads_artifact_and_tags_age(tmp_path):
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (10, [0.5, -0.3, 0.80], 1.0),
                    (5, [0.0, 0.0, 1.2], 1.0)]},
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN, template="CP-77")
    (tmp_path / "ts_CP-77.json").write_text(json.dumps(art))
    res = to.diagnose(template="CP-77", outdir=str(tmp_path))
    assert res["type"] == "data" and res["template"] == "CP-77"
    assert res["objects"]["Cube_1"]["why"] == "DELIVERED_CLEAN"
    assert res["artifact_age_s"] is not None and res["artifact_age_s"] < 60
    assert res["provenance"] == {"sha": "test"}


def test_missing_artifact_is_honest_error(tmp_path):
    res = to.diagnose(template="CP-NOPE", outdir=str(tmp_path))
    assert res["type"] == "error" and "scene_timeseries" in res["error"]
    assert to.diagnose() ["type"] == "error"          # neither arg
    assert to.diagnose(artifact_path=str(tmp_path / "x.json"))["type"] == "error"


def test_handler_registered_and_callable(tmp_path):
    from service.isaac_assist_service.chat.tools.handlers import diagnostics
    data, codegen = {}, {}
    diagnostics.register(data, codegen)
    assert "diagnose_task_outcome" in data
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (10, [-0.5, 0.4, 0.84], 1.0)]},
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN)
    p = tmp_path / "ts_X.json"
    p.write_text(json.dumps(art))
    res = asyncio.run(data["diagnose_task_outcome"]({"artifact_path": str(p)}))
    assert res["type"] == "data"
    assert res["objects"]["Cube_1"]["why"] == "NOT_PICKED"


def test_dispenser_fall_then_pick_grades_as_delivered():
    # CP-71 family (live finding): item starts HIGH in the dispenser, FALLS
    # to the feeder, then is picked + carried BELOW its start height.
    # Start-relative lift reads this as never-picked; running-min rise must not.
    art = _artifact(
        {"Item_1": [(0, [-0.45, 0.35, 1.08], 1.0),   # in dispenser
                    (2, [-0.45, 0.35, 0.78], 1.0),   # fell to feeder
                    (5, [0.0, 0.0, 1.00], 1.0),      # carried (below start z!)
                    (10, [0.49, -0.41, 0.79], 1.0)]},  # in bin
        init={"Item_1": [-0.45, 0.35, 1.08]}, dests=_BIN)
    o = to.classify_timeseries(art)["objects"]["Item_1"]
    assert o["why"] == "DELIVERED_CLEAN"
    assert o["evidence"]["picked"] is True
    assert o["evidence"]["max_rise_m"] >= 0.2


def test_no_objects_tracked_is_flagged_not_silent_fail():
    # A zero-object artifact is a MEASUREMENT GAP, not "the cell failed":
    # all_clean is False (no clean objects) but no_objects_tracked makes the
    # reason explicit, and diagnose() surfaces a caution (honest-eyes).
    art = _artifact({}, init={}, dests=_BIN, template="CP-EMPTY")
    out = to.classify_timeseries(art)
    assert out["no_objects_tracked"] is True
    assert out["all_clean"] is False        # unchanged: no clean delivery
    assert out["objects"] == {}


def test_diagnose_flags_stale_and_empty_cautions(tmp_path):
    art = _artifact({}, init={}, dests=_BIN, template="CP-EMPTY2")
    p = tmp_path / "ts_CP-EMPTY2.json"
    p.write_text(json.dumps(art))
    # backdate the file well past the stale threshold
    import os
    old = to.STALE_ARTIFACT_S + 7200.0
    st = p.stat()
    os.utime(p, (st.st_atime - old, st.st_mtime - old))
    res = to.diagnose(template="CP-EMPTY2", outdir=str(tmp_path))
    assert res["type"] == "data"
    assert res["stale"] is True
    assert any("STALE" in c for c in res["cautions"])
    assert any("NO tracked objects" in c for c in res["cautions"])


def test_diagnose_fresh_artifact_not_stale(tmp_path):
    art = _artifact(
        {"Cube_1": [(0, [-0.5, 0.4, 0.84], 1.0), (10, [0.5, -0.3, 0.80], 1.0),
                    (5, [0.0, 0.0, 1.2], 1.0)]},
        init={"Cube_1": [-0.5, 0.4, 0.84]}, dests=_BIN, template="CP-FRESH")
    (tmp_path / "ts_CP-FRESH.json").write_text(json.dumps(art))
    res = to.diagnose(template="CP-FRESH", outdir=str(tmp_path))
    assert res["stale"] is False and res["cautions"] == []


def test_displaced_not_delivered_without_belt_exit():
    # Knocked off the dispenser sideways, never picked, no belt crossed:
    # must NOT read as the conveyor-sync class.
    art = _artifact(
        {"Item_3": [(0, [-0.45, 0.45, 1.08], 1.0),
                    (5, [-0.55, 0.30, 0.85], 1.0),
                    (10, [-0.69, 0.09, 0.91], 0.9)]},
        init={"Item_3": [-0.45, 0.45, 1.08]}, dests=_BIN)
    assert (to.classify_timeseries(art)["objects"]["Item_3"]["why"]
            == "DISPLACED_NOT_DELIVERED")
