"""L0 tests for compute_stack_placement's explicit-bbox path [P2-04].

bbox supplied -> pure service-side math, NO Kit (planning time / asset-swap
sizing). bbox absent -> the legacy live-bbox path, byte-identical. The pure
function mirrors the Kit-exec math block exactly; the reference case below is
hand-computed from the CP-46 corpus convention (grid over a 50x50 cm pallet,
spacing 0.13, top z 0.80 -> drop z 0.825).
"""
import asyncio

import pytest

from service.isaac_assist_service.chat.tools.handlers.scene_authoring import (
    _handle_compute_stack_placement,
    _stack_positions_from_bbox,
)

pytestmark = pytest.mark.l0

# CP-46's pallet: centre [0,-0.4], 0.5x0.5 m, top z=0.80
_PALLET_BBOX = [[-0.25, -0.65, 0.75], [0.25, -0.15, 0.80]]


def _run(args):
    return asyncio.run(_handle_compute_stack_placement(args))


def test_grid_reference_case_matches_corpus_convention():
    # grid_2x3 over the CP-46 pallet = the hand-rolled drop_targets grid:
    # x in {-0.13, 0, 0.13}, y in {-0.465, -0.335}, z = 0.80 + 0.025 = 0.825
    res = _run({"target_path": "/World/Pallet", "n_items": 6,
                "pattern": "grid_2x3", "spacing": 0.13,
                "bbox": _PALLET_BBOX})
    assert res["type"] == "data" and res["bbox_source"] == "supplied"
    got = [p["position"] for p in res["positions"]]
    assert got == [
        [-0.13, -0.465, 0.825], [0.0, -0.465, 0.825], [0.13, -0.465, 0.825],
        [-0.13, -0.335, 0.825], [0.0, -0.335, 0.825], [0.13, -0.335, 0.825],
    ]
    assert res["base_z"] == 0.825 and res["target_bbox_max"] == [0.25, -0.15, 0.80]


def test_column_mixed_sku_stacks_cumulatively():
    res = _run({"target_path": "/World/Pallet", "n_items": 3,
                "pattern": "column", "cube_sizes": [0.10, 0.06, 0.04],
                "bbox": _PALLET_BBOX})
    zs = [p["position"][2] for p in res["positions"]]
    # cumulative: 0.80+0.05, 0.80+0.10+0.03, 0.80+0.16+0.02
    assert zs == [0.85, 0.93, 0.98]
    assert [p["size"] for p in res["positions"]] == [0.10, 0.06, 0.04]


def test_inside_floor_anchor_uses_bbox_bottom():
    res = _run({"target_path": "/World/Bin", "n_items": 1,
                "anchor": "inside_floor", "bbox": [[0, 0, 0.75], [0.2, 0.2, 0.87]]})
    assert res["positions"][0]["position"] == [0.1, 0.1, 0.775]


def test_donut_skips_center_and_layers_rotate():
    res = _run({"target_path": "/World/Pallet", "n_items": 16,
                "pattern": "donut_3x3", "spacing": 0.1,
                "layer_rotation_deg": 90, "bbox": _PALLET_BBOX})
    # 8 slots/layer; centre (0,-0.4) never occupied
    assert all(p["position"][:2] != [0.0, -0.4] for p in res["positions"])
    assert res["positions"][8]["rotation_deg"] == 90.0   # layer 1
    assert res["positions"][8]["position"][2] == pytest.approx(0.875)


@pytest.mark.parametrize("bad", [
    [[0, 0], [1, 1, 1]],          # min not len 3
    [[0, 0, 0]],                  # only one corner
    [[0, 0, 0], [1, 1, "x"]],     # non-numeric
    [[1, 0, 0], [0, 1, 1]],       # max < min on x
])
def test_bad_bbox_is_a_typed_error(bad):
    res = _run({"target_path": "/W/P", "n_items": 1, "bbox": bad})
    assert res["type"] == "error" and "bbox" in res["error"]


def test_no_bbox_takes_the_legacy_kit_path(monkeypatch):
    # bbox absent -> the handler must still go through kit_tools (unchanged
    # legacy behavior) and its emitted code must still query the live bbox.
    from service.isaac_assist_service.chat.tools import kit_tools
    captured = {}

    async def fake_queue(code, desc):
        captured["code"] = code
        return {"type": "code_patch", "queued": True}

    monkeypatch.setattr(kit_tools, "queue_exec_patch", fake_queue)
    res = _run({"target_path": "/World/Pallet", "n_items": 4, "pattern": "grid_2x2"})
    assert res.get("queued") is True
    assert "ComputeWorldBound" in captured["code"]


def test_pure_function_mirrors_emitted_math_formulas():
    # Drift guard: the handler's emitted Kit code must contain the SAME
    # formula lines the pure function implements (single source of truth is
    # not possible across the exec boundary; this pins them together).
    import inspect
    from service.isaac_assist_service.chat.tools.handlers import scene_authoring
    src = inspect.getsource(scene_authoring._handle_compute_stack_placement)
    pure = inspect.getsource(_stack_positions_from_bbox)
    for formula in (
        "x = cx + (col - (cols - 1) * 0.5) * spacing",
        "y = cy + (row - (rows - 1) * 0.5) * spacing",
        "z = base_z + layer * cube_size",
        "base_z = target_bot_z + first_cube_size * 0.5",
    ):
        assert formula in src, f"emitted code lost: {formula}"
        assert formula in pure, f"pure function lost: {formula}"
