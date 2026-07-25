"""Tests for match_opening_to_wall."""

import pytest
import logging
from src.parse_dxf import match_opening_to_wall


def _wall(wid: str, v0: list[float], v1: list[float]) -> dict:
    return {"id": wid, "vertices": [v0, v1], "closed": False}


def _opening(oid: str, insertion: tuple[float, float], rotation: float) -> dict:
    return {
        "id": oid,
        "category": "DOOR",
        "insertion_point": insertion,
        "rotation_deg": rotation,
        "block_name": "test_door",
        "estimated_width_mm": 900.0,
    }


class TestMatchOpeningToWall:

    def test_aligned_opening_matches(self):
        """Opening at 0° near a horizontal wall (0°) matches."""
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        opening = _opening("D1", (2500.0, -100.0), 0.0)
        result = match_opening_to_wall(opening, [wall], angle_tolerance_deg=10)
        assert result is not None
        assert result["id"] == "W1"

    def test_misaligned_opening_rejected(self, caplog):
        """Opening at 15° off the wall direction is rejected and logged."""
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])  # horizontal
        opening = _opening("D2", (2500.0, -100.0), 15.0)  # 15° off
        with caplog.at_level(logging.WARNING, logger="src.parse_dxf"):
            result = match_opening_to_wall(opening, [wall], angle_tolerance_deg=10)
        assert result is None
        assert "rejected" in caplog.text
        assert "D2" in caplog.text

    def test_closest_wall_chosen(self):
        """When two walls are aligned, the nearer one wins."""
        w1 = _wall("W1", [0.0, 0.0], [5000.0, 0.0])    # y=0
        w2 = _wall("W2", [0.0, 100.0], [5000.0, 100.0])  # y=100
        opening = _opening("D1", (2500.0, 80.0), 0.0)   # 80mm from w1, 20mm from w2
        result = match_opening_to_wall(opening, [w1, w2], angle_tolerance_deg=10)
        assert result is not None
        assert result["id"] == "W2"

    def test_empty_walls_returns_none(self):
        opening = _opening("D1", (2500.0, 0.0), 0.0)
        assert match_opening_to_wall(opening, []) is None

    def test_wall_at_90_degrees_matches_opening_at_90(self):
        """Vertical wall (90°) matches opening rotated 90°."""
        wall = _wall("W1", [0.0, 0.0], [0.0, 5000.0])
        opening = _opening("D1", (-100.0, 2500.0), 90.0)
        result = match_opening_to_wall(opening, [wall], angle_tolerance_deg=10)
        assert result is not None
        assert result["id"] == "W1"

    def test_mod180_alignment(self):
        """Opening at 0° matches a wall running right-to-left (180°)."""
        wall = _wall("W1", [5000.0, 0.0], [0.0, 0.0])
        opening = _opening("D1", (2500.0, -100.0), 0.0)
        result = match_opening_to_wall(opening, [wall], angle_tolerance_deg=10)
        assert result is not None
        assert result["id"] == "W1"
