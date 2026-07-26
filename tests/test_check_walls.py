"""Tests for the validate_conversion script."""

import sys
from pathlib import Path

import pytest

# Make the project root importable so src.validate_conversion resolves.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.validate_conversion import check_walls, DEFAULT_DXF, DEFAULT_CONFIG

_missing_dxf = pytest.mark.skipif(not DEFAULT_DXF.exists(), reason="test1.dxf not present in data/")


@_missing_dxf
class TestCheckWallsDefaults:

    def test_runs_without_error(self, capsys):
        walls = check_walls()
        assert isinstance(walls, list)
        assert len(walls) > 0

    def test_prints_total_line(self, capsys):
        check_walls()
        captured = capsys.readouterr()
        assert "Total walls extracted:" in captured.out

    def test_stdout_has_wall_details(self, capsys):
        check_walls()
        captured = capsys.readouterr()
        assert "handle=" in captured.out
        assert "closed=" in captured.out
        assert "pts=" in captured.out

    def test_returns_wall_dicts(self):
        walls = check_walls()
        for w in walls:
            assert set(w.keys()) == {"id", "vertices", "closed"}
            assert isinstance(w["vertices"], list)
            assert all(len(v) == 2 for v in w["vertices"])


@_missing_dxf
class TestCheckWallsCustomPaths:

    def test_with_explicit_paths(self, capsys):
        walls = check_walls(dxf_path=DEFAULT_DXF, config_path=DEFAULT_CONFIG)
        assert len(walls) > 0


def test_nonexistent_dxf_raises():
    with pytest.raises(Exception):
        check_walls(dxf_path="/nonexistent/file.dxf")
