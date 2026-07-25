"""Tests for load_layer_config function."""

import textwrap
from pathlib import Path

import pytest

from src.inventory import load_layer_config


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "layers.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# --- valid configs ---

class TestLoadLayerConfigValid:

    def test_basic_mapping(self, tmp_path: Path):
        cfg = _write_yaml(tmp_path, """\
            layers:
              A-WALL: WALL
              A-DOOR: DOOR
              A-GLAZ: WINDOW
              X-REF: IGNORE
        """)
        result = load_layer_config(cfg)
        assert result == {
            "A-WALL": "WALL",
            "A-DOOR": "DOOR",
            "A-GLAZ": "WINDOW",
            "X-REF": "IGNORE",
        }

    def test_case_insensitive_values(self, tmp_path: Path):
        cfg = _write_yaml(tmp_path, """\
            layers:
              wall-1: wall
              door-1: Door
              win-1:  window
        """)
        result = load_layer_config(cfg)
        assert result == {"wall-1": "WALL", "door-1": "DOOR", "win-1": "WINDOW"}

    def test_empty_layers_returns_empty_dict(self, tmp_path: Path):
        cfg = _write_yaml(tmp_path, """\
            layers: {}
        """)
        assert load_layer_config(cfg) == {}


# --- invalid configs ---

class TestLoadLayerConfigInvalid:

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_layer_config(tmp_path / "missing.yaml")

    def test_missing_layers_key(self, tmp_path: Path):
        cfg = _write_yaml(tmp_path, """\
            not_layers:
              A-WALL: WALL
        """)
        with pytest.raises(ValueError, match="top-level 'layers' key"):
            load_layer_config(cfg)

    def test_invalid_category_value(self, tmp_path: Path):
        cfg = _write_yaml(tmp_path, """\
            layers:
              A-WALL: WALL
              A-DOOR: FLOOR
        """)
        with pytest.raises(ValueError, match="Invalid category values"):
            load_layer_config(cfg)

    def test_non_string_category(self, tmp_path: Path):
        cfg = _write_yaml(tmp_path, """\
            layers:
              A-WALL: 42
        """)
        with pytest.raises(ValueError, match="Invalid category values"):
            load_layer_config(cfg)

    def test_multiple_bad_categories_reported(self, tmp_path: Path):
        cfg = _write_yaml(tmp_path, """\
            layers:
              L1: WALL
              L2: ROOF
              L3: CEILING
        """)
        with pytest.raises(ValueError, match="L2.*ROOF") as exc_info:
            load_layer_config(cfg)
        msg = str(exc_info.value)
        assert "L3" in msg
        assert "CEILING" in msg
