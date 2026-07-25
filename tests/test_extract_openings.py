"""Tests for extract_openings function."""

import ezdxf
import os
import tempfile
import pytest

from src.inventory import extract_openings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opening_dxf(insunits=4, entities=None):
    """Create a minimal DXF with block inserts and return the temp file path.

    *entities* is a list of dicts.  Supported keys:
      ``layer``, ``block_name``, ``insert``, ``rotation``.
    Block definitions are auto-created; each block gets a LINE spanning
    (0,0)-(100,0) so the estimated width is 100 DXF-units.
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    blocks_seen = set()

    for ent in (entities or []):
        block_name = ent.get("block_name", "BLOCK1")
        if block_name not in blocks_seen:
            blk = doc.blocks.new(name=block_name)
            blk.add_line((0, 0), (100, 0))
            blocks_seen.add(block_name)

        attribs = {"layer": ent.get("layer", "0")}
        ref = msp.add_blockref(
            block_name,
            ent.get("insert", (0, 0)),
            dxfattribs=attribs,
        )
        if "rotation" in ent:
            ref.dxf.rotation = ent["rotation"]

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        doc.saveas(tmp.name)
        return tmp.name


@pytest.fixture
def opening_layer_config():
    return {"A-WALL": "WALL", "A-DOOR": "DOOR", "A-GLAZ": "WINDOW"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractOpeningsBasic:

    def test_returns_list(self, opening_layer_config):
        path = _make_opening_dxf(entities=[
            {"layer": "A-DOOR", "block_name": "D1", "insert": (10, 20)},
        ])
        try:
            result = extract_openings(path, opening_layer_config)
            assert isinstance(result, list)
            assert all(isinstance(o, dict) for o in result)
        finally:
            os.unlink(path)

    def test_only_door_window_layers(self, opening_layer_config):
        path = _make_opening_dxf(entities=[
            {"layer": "A-WALL", "block_name": "W", "insert": (0, 0)},
            {"layer": "A-DOOR", "block_name": "D", "insert": (5, 5)},
            {"layer": "A-GLAZ", "block_name": "G", "insert": (8, 8)},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert len(openings) == 2
            cats = {o["category"] for o in openings}
            assert cats == {"DOOR", "WINDOW"}
        finally:
            os.unlink(path)

    def test_dict_keys(self, opening_layer_config):
        path = _make_opening_dxf(entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (1, 2)},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert len(openings) == 1
            expected_keys = {
                "id", "category", "insertion_point", "rotation_deg",
                "block_name", "estimated_width_mm",
            }
            assert set(openings[0].keys()) == expected_keys
        finally:
            os.unlink(path)

    def test_insertion_point_scaled(self, opening_layer_config):
        path = _make_opening_dxf(insunits=1, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (10, 5)},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            # 10 inches * 25.4 = 254 mm, 5 inches * 25.4 = 127 mm
            assert openings[0]["insertion_point"] == (254.0, 127.0)
        finally:
            os.unlink(path)

    def test_estimated_width_from_bbox(self, opening_layer_config):
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0)},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert openings[0]["estimated_width_mm"] == 100.0
        finally:
            os.unlink(path)


class TestExtractOpeningsRotation:
    """Rotation must be read accurately — a silent default to 0 is a showstopper."""

    def test_rotation_0(self, opening_layer_config):
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0), "rotation": 0},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert openings[0]["rotation_deg"] == 0.0
        finally:
            os.unlink(path)

    def test_rotation_45(self, opening_layer_config):
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0), "rotation": 45},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert openings[0]["rotation_deg"] == 45.0
        finally:
            os.unlink(path)

    def test_rotation_90(self, opening_layer_config):
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0), "rotation": 90},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert openings[0]["rotation_deg"] == 90.0
        finally:
            os.unlink(path)

    def test_rotation_270(self, opening_layer_config):
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0), "rotation": 270},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert openings[0]["rotation_deg"] == 270.0
        finally:
            os.unlink(path)

    def test_rotation_37point5(self, opening_layer_config):
        """Non-standard angle — make sure floats come through, not rounded."""
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-GLAZ", "block_name": "W", "insert": (0, 0), "rotation": 37.5},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert openings[0]["rotation_deg"] == pytest.approx(37.5)
        finally:
            os.unlink(path)

    def test_default_rotation_when_not_set(self, opening_layer_config):
        """INSERT without explicit rotation should default to 0.0."""
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0)},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            assert openings[0]["rotation_deg"] == 0.0
        finally:
            os.unlink(path)

    def test_rotation_not_defaulting_to_zero(self, opening_layer_config):
        """Multiple inserts at different rotations — none should silently be 0."""
        path = _make_opening_dxf(insunits=4, entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0), "rotation": 45},
            {"layer": "A-DOOR", "block_name": "D", "insert": (5, 0), "rotation": 135},
            {"layer": "A-DOOR", "block_name": "D", "insert": (10, 0), "rotation": 225},
        ])
        try:
            openings = extract_openings(path, opening_layer_config)
            rotations = [o["rotation_deg"] for o in openings]
            assert rotations == [45.0, 135.0, 225.0]
        finally:
            os.unlink(path)


class TestExtractOpeningsEdgeCases:

    def test_empty_config(self):
        path = _make_opening_dxf(entities=[
            {"layer": "A-DOOR", "block_name": "D", "insert": (0, 0), "rotation": 45},
        ])
        try:
            assert extract_openings(path, {}) == []
        finally:
            os.unlink(path)

    def test_no_inserts_on_opening_layers(self, opening_layer_config):
        path = _make_opening_dxf(entities=[
            {"layer": "A-WALL", "block_name": "W", "insert": (0, 0)},
        ])
        try:
            assert extract_openings(path, opening_layer_config) == []
        finally:
            os.unlink(path)
