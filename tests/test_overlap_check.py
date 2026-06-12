"""l0 tests for the build-time GEOMETRIC_OVERLAP advisory (generation wiring)."""
import pytest

pytestmark = pytest.mark.l0
import ast

from service.isaac_assist_service.qa.overlap_check import OVERLAP_CHECK_CODE, parse_overlap_output


def test_kit_side_code_parses():
    ast.parse(OVERLAP_CHECK_CODE)


def test_kit_side_code_prints_single_marker():
    assert OVERLAP_CHECK_CODE.count('print("OVERLAP=') == 1


def test_kit_side_code_is_non_destructive():
    # the build-time advisory must never play the timeline or kill controller
    # subscriptions — that is scene_validate.py's destructive territory
    assert "timeline" not in OVERLAP_CHECK_CODE
    assert "unsubscribe" not in OVERLAP_CHECK_CODE
    assert "app.update" not in OVERLAP_CHECK_CODE


def test_parse_happy_path():
    out = 'noise\nOVERLAP= {"violations": ["x"], "n_dynamic": 2, "n_robots": 1}'
    assert parse_overlap_output(out) == {"violations": ["x"], "n_dynamic": 2, "n_robots": 1}


def test_parse_absent_and_garbage():
    assert parse_overlap_output("no marker here") is None
    assert parse_overlap_output(None) is None
    assert parse_overlap_output("OVERLAP= {broken") is None
