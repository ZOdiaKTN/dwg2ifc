"""Tests for extract_walls function."""

import ezdxf
import logging
import tempfile
import os
import pytest

from src.inventory import extract_walls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dxf(insunits=4, entities=None):
    """Create a minimal DXF and return the path to a temp file.

    *entities* is a list of dicts describing what to add.  Each dict may
    contain: ``type`` (LINE | LWPOLYLINE | POLYLINE | TEXT | INSERT …),
    ``layer``, and type-specific keys (``start``, ``end``, ``points``,
    ``closed``, ``text``, ``block_name``, ``insert``).
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()

    for ent in (entities or []):
        etype = ent["type"]
        layer = ent.get("layer", "0")
        attribs = {"layer": layer}

        if etype == "LINE":
            msp.add_line(ent["start"], ent["end"], dxfattribs=attribs)
        elif etype == "LWPOLYLINE":
            msp.add_lwpolyline(
                ent["points"],
                dxfattribs=attribs,
                close=ent.get("closed", False),
            )
        elif etype == "POLYLINE":
            poly = msp.add_polyline2d(ent["points"], dxfattribs=attribs)
            poly.close = ent.get("closed", False)
        elif etype == "TEXT":
            msp.add_text(ent.get("text", "hello"), dxfattribs=attribs)
        elif etype == "INSERT":
            doc.blocks.new(name=ent.get("block_name", "BLOCK1"))
            msp.add_blockref(
                ent.get("block_name", "BLOCK1"),
                ent.get("insert", (0, 0)),
                dxfattribs=attribs,
            )
        else:
            raise ValueError(f"Unknown entity type in test helper: {etype}")

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        doc.saveas(tmp.name)
        return tmp.name


@pytest.fixture
def wall_layer_config():
    return {"A-WALL": "WALL", "A-DOOR": "DOOR", "A-GLAZ": "WINDOW"}


@pytest.fixture
def basic_dxf(wall_layer_config, tmp_path):
    """Synthetic DXF from Step 1.1:
    - LWPOLYLINE rectangle on A-WALL (closed)
    - LINE on A-WALL (open)
    - INSERT on A-DOOR (not a wall, must be ignored)
    $INSUNITS = 4 → millimetres, so scale = 1.
    """
    path = _make_dxf(insunits=4, entities=[
        {
            "type": "LWPOLYLINE",
            "layer": "A-WALL",
            "points": [(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)],
            "closed": True,
        },
        {
            "type": "LINE",
            "layer": "A-WALL",
            "start": (0, 5),
            "end": (10, 5),
        },
        {
            "type": "INSERT",
            "layer": "A-DOOR",
            "block_name": "DOOR",
            "insert": (5, 2.5),
        },
    ])
    yield path
    os.unlink(path)


@pytest.fixture
def stray_text_dxf(wall_layer_config, tmp_path):
    """DXF where a WALL layer contains a TEXT entity that must be skipped."""
    path = _make_dxf(insunits=4, entities=[
        {
            "type": "LWPOLYLINE",
            "layer": "A-WALL",
            "points": [(0, 0), (10, 0), (10, 5), (0, 5)],
            "closed": True,
        },
        {
            "type": "TEXT",
            "layer": "A-WALL",
            "text": "stray annotation",
        },
    ])
    yield path
    os.unlink(path)


@pytest.fixture
def inches_dxf(wall_layer_config, tmp_path):
    """DXF with $INSUNITS = 1 (inches) to verify unit conversion."""
    path = _make_dxf(insunits=1, entities=[
        {
            "type": "LINE",
            "layer": "A-WALL",
            "start": (0, 0),
            "end": (10, 0),
        },
    ])
    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# Tests – basic extraction
# ---------------------------------------------------------------------------

class TestExtractWallsBasic:

    def test_returns_list_of_dicts(self, basic_dxf, wall_layer_config):
        walls = extract_walls(basic_dxf, wall_layer_config)
        assert isinstance(walls, list)
        assert all(isinstance(w, dict) for w in walls)

    def test_only_wall_layer_entities(self, basic_dxf, wall_layer_config):
        walls = extract_walls(basic_dxf, wall_layer_config)
        # Should have 2 walls: 1 LWPOLYLINE + 1 LINE on A-WALL.
        assert len(walls) == 2

    def test_dict_keys(self, basic_dxf, wall_layer_config):
        walls = extract_walls(basic_dxf, wall_layer_config)
        for w in walls:
            assert set(w.keys()) == {"id", "vertices", "closed"}

    def test_lwpolyline_closed(self, basic_dxf, wall_layer_config):
        walls = extract_walls(basic_dxf, wall_layer_config)
        poly = [w for w in walls if not w["closed"] is False and len(w["vertices"]) == 5]
        assert len(poly) == 1
        poly = poly[0]
        assert poly["closed"] is True
        assert len(poly["vertices"]) == 5
        # Vertices should match the input (scale = 1 for mm)
        assert poly["vertices"][0] == (0.0, 0.0)
        assert poly["vertices"][1] == (10.0, 0.0)

    def test_line_not_closed(self, basic_dxf, wall_layer_config):
        walls = extract_walls(basic_dxf, wall_layer_config)
        line = [w for w in walls if len(w["vertices"]) == 2]
        assert len(line) == 1
        line = line[0]
        assert line["closed"] is False
        assert line["vertices"] == [(0.0, 5.0), (10.0, 5.0)]

    def test_door_layer_ignored(self, basic_dxf, wall_layer_config):
        walls = extract_walls(basic_dxf, wall_layer_config)
        # No entity from A-DOOR should appear.
        assert all(w["id"] != "INSERT" for w in walls)


# ---------------------------------------------------------------------------
# Tests – stray TEXT on a WALL layer
# ---------------------------------------------------------------------------

class TestExtractWallsStrayText:

    def test_text_not_extracted(self, stray_text_dxf, wall_layer_config):
        walls = extract_walls(stray_text_dxf, wall_layer_config)
        assert len(walls) == 1  # only the LWPOLYLINE

    def test_text_logs_warning(self, stray_text_dxf, wall_layer_config, caplog):
        with caplog.at_level(logging.WARNING, logger="src.inventory"):
            extract_walls(stray_text_dxf, wall_layer_config)
        assert "TEXT" in caplog.text
        assert "A-WALL" in caplog.text
        assert "Skipping" in caplog.text

    def test_text_does_not_crash(self, stray_text_dxf, wall_layer_config):
        # The function should complete without raising.
        walls = extract_walls(stray_text_dxf, wall_layer_config)
        assert isinstance(walls, list)


# ---------------------------------------------------------------------------
# Tests – unit conversion ($INSUNITS)
# ---------------------------------------------------------------------------

class TestExtractWallsUnitConversion:

    def test_inches_to_mm(self, inches_dxf, wall_layer_config):
        """LINE from (0,0) to (10,0) in inches → (0,0) to (254,0) in mm."""
        walls = extract_walls(inches_dxf, wall_layer_config)
        assert len(walls) == 1
        w = walls[0]
        assert w["vertices"][0] == (0.0, 0.0)
        # 10 * 25.4 = 254.0
        assert w["vertices"][1] == (254.0, 0.0)

    def test_mm_no_conversion(self, basic_dxf, wall_layer_config):
        """$INSUNITS=4 (mm) should leave coordinates unchanged."""
        walls = extract_walls(basic_dxf, wall_layer_config)
        line = [w for w in walls if len(w["vertices"]) == 2][0]
        assert line["vertices"] == [(0.0, 5.0), (10.0, 5.0)]


# ---------------------------------------------------------------------------
# Tests – edge cases
# ---------------------------------------------------------------------------

class TestExtractWallsEdgeCases:

    def test_empty_wall_layers(self, tmp_path, wall_layer_config):
        """DXF with no entities on any WALL layer → empty list."""
        path = _make_dxf(insunits=4, entities=[
            {"type": "INSERT", "layer": "A-DOOR", "block_name": "X", "insert": (0, 0)},
        ])
        try:
            walls = extract_walls(path, wall_layer_config)
            assert walls == []
        finally:
            os.unlink(path)

    def test_empty_config(self, basic_dxf):
        """Empty layer_config → nothing extracted."""
        walls = extract_walls(basic_dxf, {})
        assert walls == []

    def test_unmapped_wall_layer_skipped(self, tmp_path):
        """A layer called A-WALL that is *not* in the config is skipped."""
        path = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (1, 1)},
        ])
        try:
            walls = extract_walls(path, {})  # empty config
            assert walls == []
        finally:
            os.unlink(path)
