"""Tests for detect_openings module."""

import json
import os
import tempfile
import pytest
import yaml

from src.detect_openings import load_opening_defaults, detect_openings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wall(wid: str, v0: list, v1: list) -> dict:
    return {"id": wid, "vertices": [v0, v1], "closed": False}


def _door(oid: str, insertion: tuple, rotation: float, width: float = 900.0) -> dict:
    return {
        "id": oid,
        "category": "DOOR",
        "insertion_point": insertion,
        "rotation_deg": rotation,
        "block_name": f"door_{oid}",
        "estimated_width_mm": width,
    }


def _window(oid: str, insertion: tuple, rotation: float, width: float = 1200.0) -> dict:
    return {
        "id": oid,
        "category": "WINDOW",
        "insertion_point": insertion,
        "rotation_deg": rotation,
        "block_name": f"window_{oid}",
        "estimated_width_mm": width,
    }


def _write_yaml(categories: dict, tmp_path=None) -> str:
    """Write a temporary YAML config and return its path."""
    data = {"categories": categories}
    if tmp_path is None:
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        return path
    path = tmp_path / "test_defaults.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# load_opening_defaults
# ---------------------------------------------------------------------------

class TestLoadOpeningDefaults:

    def test_loads_door_and_window(self):
        path = _write_yaml({
            "DOOR": {"height_mm": 2100, "sill_mm": 0},
            "WINDOW": {"height_mm": 1200, "sill_mm": 900},
        })
        try:
            defaults = load_opening_defaults(path)
            assert defaults["DOOR"]["height_mm"] == 2100
            assert defaults["DOOR"]["sill_mm"] == 0
            assert defaults["WINDOW"]["height_mm"] == 1200
            assert defaults["WINDOW"]["sill_mm"] == 900
        finally:
            os.unlink(path)

    def test_case_insensitive_keys(self):
        path = _write_yaml({
            "door": {"height_mm": 2000, "sill_mm": 50},
        })
        try:
            defaults = load_opening_defaults(path)
            assert "DOOR" in defaults
            assert defaults["DOOR"]["height_mm"] == 2000
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_opening_defaults("/nonexistent/path.yaml")

    def test_empty_categories(self):
        path = _write_yaml({})
        try:
            defaults = load_opening_defaults(path)
            assert defaults == {}
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# detect_openings
# ---------------------------------------------------------------------------

class TestDetectOpenings:

    def test_matched_opening_gets_height_sill(self):
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        door = _door("D1", (2500.0, -100.0), 0.0, 900.0)
        defaults = {"DOOR": {"height_mm": 2100, "sill_mm": 0}}

        enriched, walls_out, matched, flagged = detect_openings(
            [wall], [door], [], defaults,
        )

        assert matched == 1
        assert flagged == 0
        assert enriched[0]["height_mm"] == 2100
        assert enriched[0]["sill_mm"] == 0
        assert enriched[0]["wall_id"] == "W1"
        assert enriched[0]["position"] is not None

    def test_wall_gets_openings_list(self):
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        door = _door("D1", (2500.0, -100.0), 0.0, 900.0)
        defaults = {"DOOR": {"height_mm": 2100, "sill_mm": 0}}

        _, walls_out, _, _ = detect_openings(
            [wall], [door], [], defaults,
        )

        assert len(walls_out) == 1
        assert len(walls_out[0]["openings"]) == 1
        assert walls_out[0]["openings"][0]["id"] == "D1"

    def test_unmatched_opening_flagged(self):
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        door = _door("D1", (2500.0, 0.0), 45.0, 900.0)  # 45° off horizontal wall
        defaults = {"DOOR": {"height_mm": 2100, "sill_mm": 0}}

        enriched, _, matched, flagged = detect_openings(
            [wall], [door], [], defaults,
        )

        assert matched == 0
        assert flagged == 1
        assert enriched[0]["flagged_reason"] == "no_matching_wall"
        assert enriched[0]["wall_id"] is None

    def test_window_gets_window_defaults(self):
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        win = _window("W1", (2500.0, -100.0), 0.0, 1200.0)
        defaults = {"WINDOW": {"height_mm": 1200, "sill_mm": 900}}

        enriched, _, matched, _ = detect_openings(
            [wall], [], [win], defaults,
        )

        assert matched == 1
        assert enriched[0]["height_mm"] == 1200
        assert enriched[0]["sill_mm"] == 900

    def test_empty_openings(self):
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        defaults = {"DOOR": {"height_mm": 2100, "sill_mm": 0}}

        enriched, walls_out, matched, flagged = detect_openings(
            [wall], [], [], defaults,
        )

        assert enriched == []
        assert matched == 0
        assert flagged == 0
        assert walls_out[0]["openings"] == []

    def test_multiple_openings_on_same_wall(self):
        wall = _wall("W1", [0.0, 0.0], [10000.0, 0.0])
        d1 = _door("D1", (2000.0, -100.0), 0.0, 900.0)
        d2 = _door("D2", (7000.0, -100.0), 0.0, 900.0)
        defaults = {"DOOR": {"height_mm": 2100, "sill_mm": 0}}

        enriched, walls_out, matched, flagged = detect_openings(
            [wall], [d1, d2], [], defaults,
        )

        assert matched == 2
        assert flagged == 0
        assert len(walls_out[0]["openings"]) == 2

    def test_opening_too_wide_flagged(self):
        wall = _wall("W1", [0.0, 0.0], [500.0, 0.0])
        door = _door("D1", (250.0, -100.0), 0.0, 900.0)  # 900 > 500
        defaults = {"DOOR": {"height_mm": 2100, "sill_mm": 0}}

        enriched, _, matched, flagged = detect_openings(
            [wall], [door], [], defaults,
        )

        assert matched == 0
        assert flagged == 1
        assert enriched[0]["flagged_reason"] == "position_invalid"
        assert enriched[0]["wall_id"] == "W1"

    def test_default_height_sill_when_no_category_config(self):
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        door = _door("D1", (2500.0, -100.0), 0.0, 900.0)
        defaults = {}  # no DOOR config

        enriched, _, matched, _ = detect_openings(
            [wall], [door], [], defaults,
        )

        assert matched == 1
        assert enriched[0]["height_mm"] == 0
        assert enriched[0]["sill_mm"] == 0

    def test_walls_deep_copied(self):
        wall = _wall("W1", [0.0, 0.0], [5000.0, 0.0])
        defaults = {}

        _, walls_out, _, _ = detect_openings(
            [wall], [], [], defaults,
        )

        # Original wall should not have "openings" key.
        assert "openings" not in wall
        assert "openings" in walls_out[0]


# ---------------------------------------------------------------------------
# CLI integration (smoke test with real output.json)
# ---------------------------------------------------------------------------

class TestDetectOpeningsCLI:

    def test_main_runs(self, tmp_path):
        """Smoke test: CLI runs without error on a minimal JSON."""
        walls_json = tmp_path / "walls.json"
        walls_json.write_text(json.dumps({
            "walls": [_wall("W1", [0.0, 0.0], [5000.0, 0.0])],
            "doors": [_door("D1", (2500.0, -100.0), 0.0, 900.0)],
            "windows": [],
        }), encoding="utf-8")

        config_yaml = tmp_path / "defaults.yaml"
        config_yaml.write_text(yaml.dump({"categories": {
            "DOOR": {"height_mm": 2100, "sill_mm": 0},
        }}), encoding="utf-8")

        from src.detect_openings import main
        import sys

        old_argv = sys.argv
        try:
            sys.argv = [
                "detect_openings.py",
                str(walls_json),
                "-o", str(tmp_path),
                "-c", str(config_yaml),
            ]
            main()
        finally:
            sys.argv = old_argv

        assert (tmp_path / "openings.json").exists()
        assert (tmp_path / "output.json").exists()

        data = json.loads((tmp_path / "openings.json").read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["height_mm"] == 2100
