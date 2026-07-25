"""Tests for snap_endpoints."""

import pytest
from src.parse_dxf import snap_endpoints


def _wall(wid: str, v0: list[float], v1: list[float]) -> dict:
    return {"id": wid, "vertices": [v0, v1], "closed": False}


class TestSnapEndpoints:

    def test_merge_within_tolerance(self):
        w1 = _wall("A", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("B", [101.0, 2.0], [200.0, 2.0])  # endpoint 3mm away from w1 end
        result = snap_endpoints([w1, w2], tolerance_mm=10)
        assert len(result) == 2
        # The shared endpoint should be the midpoint of (100,0) and (101,2).
        assert result[0]["vertices"][1] == result[1]["vertices"][0]

    def test_no_merge_outside_tolerance(self):
        w1 = _wall("A", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("B", [150.0, 0.0], [250.0, 0.0])  # 50mm gap
        result = snap_endpoints([w1, w2], tolerance_mm=10)
        assert result[0]["vertices"][1] == [100.0, 0.0]
        assert result[1]["vertices"][0] == [150.0, 0.0]

    def test_empty_walls(self):
        assert snap_endpoints([]) == []

    def test_single_wall_unchanged(self):
        w = _wall("A", [0.0, 0.0], [100.0, 0.0])
        result = snap_endpoints([w], tolerance_mm=10)
        assert result[0]["vertices"] == [[0.0, 0.0], [100.0, 0.0]]

    def test_three_walls_chain(self):
        """Three walls where end1≈end2 and end2≈end3 — all snap together."""
        w1 = _wall("A", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("B", [102.0, 1.0], [200.0, 0.0])
        w3 = _wall("C", [201.0, 0.0], [300.0, 0.0])
        result = snap_endpoints([w1, w2, w3], tolerance_mm=10)
        assert result[0]["vertices"][1] == result[1]["vertices"][0]
        assert result[1]["vertices"][1] == result[2]["vertices"][0]

    def test_preserves_wall_keys(self):
        w = _wall("X", [0.0, 0.0], [100.0, 0.0])
        result = snap_endpoints([w], tolerance_mm=10)
        assert result[0]["id"] == "X"
        assert result[0]["closed"] is False

    def test_degenerate_wall_removed(self):
        """A sub-1mm wall whose both endpoints snap to the same point is removed."""
        w1 = _wall("A", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("B", [101.0, 0.0], [200.0, 0.0])
        # w3 is a 0.5mm wall that will collapse to zero
        w3 = _wall("micro", [100.2, -0.1], [100.2, 0.4])
        result = snap_endpoints([w1, w2, w3], tolerance_mm=10, corner_tolerance_mm=10)
        assert len(result) == 2
        assert result[0]["id"] == "A"
        assert result[1]["id"] == "B"

    def test_valid_small_wall_kept(self):
        """A valid 2mm wall stays even if both endpoints snap to nearby points."""
        w1 = _wall("A", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("B", [101.0, 0.0], [200.0, 0.0])
        w3 = _wall("small", [100.5, -1.0], [100.5, 1.0])
        result = snap_endpoints([w1, w2, w3], tolerance_mm=10, corner_tolerance_mm=10)
        assert len(result) == 3
        assert result[2]["id"] == "small"

    def test_corner_merge_non_parallel(self):
        """Two perpendicular walls with a 60mm gap merge at corner_tolerance=75."""
        w1 = _wall("A", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("B", [160.0, 0.0], [160.0, 100.0])  # 60mm gap from A end
        result = snap_endpoints([w1, w2], tolerance_mm=10, corner_tolerance_mm=75)
        assert len(result) == 2
        assert result[0]["vertices"][1] == result[1]["vertices"][0]

    def test_parallel_walls_not_merged(self):
        """Two parallel walls 30mm apart stay separate (wall thickness)."""
        w1 = _wall("A", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("B", [0.0, 30.0], [100.0, 30.0])
        result = snap_endpoints([w1, w2], tolerance_mm=10, corner_tolerance_mm=75)
        assert len(result) == 2
        assert result[0]["vertices"][0] == [0.0, 0.0]
        assert result[1]["vertices"][0] == [0.0, 30.0]
