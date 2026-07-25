"""Tests for compute_opening_position."""

import logging
import pytest
from src.parse_dxf import compute_opening_position


def _wall(wid: str, v0: list[float], v1: list[float]) -> dict:
    return {"id": wid, "vertices": [v0, v1], "closed": False}


def _opening(oid: str, insertion: tuple[float, float], width_mm: float) -> dict:
    return {
        "id": oid,
        "category": "DOOR",
        "insertion_point": insertion,
        "rotation_deg": 0.0,
        "block_name": "test_door",
        "estimated_width_mm": width_mm,
    }


class TestComputeOpeningPosition:

    def test_opening_fits_on_wall(self):
        """An opening whose width is smaller than the wall fits correctly."""
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        opening = _opening("D1", (2500.0, 0.0), 900.0)
        result = compute_opening_position(opening, wall)

        assert result is not None
        assert result["wall_id"] == "W1"
        assert result["center_t"] == pytest.approx(0.5)
        assert result["start_mm"] == pytest.approx(2050.0)
        assert result["end_mm"] == pytest.approx(2950.0)
        assert result["center_point"] == pytest.approx((2500.0, 0.0))

    def test_opening_wider_than_wall_flagged(self, caplog):
        """An opening wider than its wall segment is rejected and logged."""
        wall = _wall("W2", [0.0, 0.0], [1000.0, 0.0])
        opening = _opening("D2", (500.0, 0.0), 1200.0)
        with caplog.at_level(logging.WARNING, logger="src.parse_dxf"):
            result = compute_opening_position(opening, wall)
        assert result is None
        assert "D2" in caplog.text
        assert "does not fit" in caplog.text

    def test_opening_at_wall_start_fits(self):
        """Opening near the start of a long wall fits."""
        wall = _wall("W3", [0.0, 0.0], [5000.0, 0.0])
        opening = _opening("D3", (500.0, 0.0), 900.0)
        result = compute_opening_position(opening, wall)

        assert result is not None
        assert result["start_mm"] == pytest.approx(50.0)
        assert result["end_mm"] == pytest.approx(950.0)

    def test_opening_at_wall_end_fits(self):
        """Opening near the end of a long wall fits."""
        wall = _wall("W4", [0.0, 0.0], [5000.0, 0.0])
        opening = _opening("D4", (4500.0, 0.0), 900.0)
        result = compute_opening_position(opening, wall)

        assert result is not None
        assert result["start_mm"] == pytest.approx(4050.0)
        assert result["end_mm"] == pytest.approx(4950.0)

    def test_opening_overlaps_start_of_wall_flagged(self, caplog):
        """Opening that bleeds past the start of the wall is rejected."""
        wall = _wall("W5", [0.0, 0.0], [5000.0, 0.0])
        opening = _opening("D5", (100.0, 0.0), 900.0)
        with caplog.at_level(logging.WARNING, logger="src.parse_dxf"):
            result = compute_opening_position(opening, wall)
        assert result is None
        assert "does not fit" in caplog.text

    def test_zero_length_wall_flagged(self, caplog):
        """A zero-length wall is rejected and logged."""
        wall = _wall("W6", [100.0, 200.0], [100.0, 200.0])
        opening = _opening("D6", (100.0, 200.0), 900.0)
        with caplog.at_level(logging.WARNING, logger="src.parse_dxf"):
            result = compute_opening_position(opening, wall)
        assert result is None
        assert "zero length" in caplog.text
