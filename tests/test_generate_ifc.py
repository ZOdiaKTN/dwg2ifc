"""Tests for generate_ifc.py end-to-end pipeline."""
import json
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generate_ifc import _build_ifc, _sanity_check
from src.ifc_skeleton import find_room_loops


# ---------------------------------------------------------------------------
# Synthetic test data: a simple rectangular room made of 4 walls + 1 door.
# ---------------------------------------------------------------------------
ROOM_W = 4000.0   # mm
ROOM_H = 3000.0   # mm
WALL_THICK = 200.0
FLOOR_H = 2700.0
DOOR_W = 1000.0
DOOR_H = 2100.0


@pytest.fixture()
def simple_room_data():
    """4 walls forming a rectangle + 1 door on the south wall."""
    return {
        "walls": [
            {"id": "W_South", "vertices": [[0, 0], [ROOM_W, 0]], "thickness": WALL_THICK, "openings": []},
            {"id": "W_East",  "vertices": [[ROOM_W, 0], [ROOM_W, ROOM_H]], "thickness": WALL_THICK, "openings": []},
            {"id": "W_North", "vertices": [[ROOM_W, ROOM_H], [0, ROOM_H]], "thickness": WALL_THICK, "openings": []},
            {"id": "W_West",  "vertices": [[0, ROOM_H], [0, 0]], "thickness": WALL_THICK, "openings": []},
        ],
        "doors": [
            {
                "id": "D1",
                "category": "DOOR",
                "insertion_point": [ROOM_W / 2, 0],
                "rotation_deg": 90.0,
                "block_name": "test_door",
                "estimated_width_mm": DOOR_W,
                "height_mm": DOOR_H,
                "sill_mm": 0.0,
                "wall_id": None,
            }
        ],
        "windows": [],
    }


@pytest.fixture()
def built_ifc(simple_room_data, tmp_path):
    """Build an IFC from the synthetic data and return (path, sanity_result)."""
    path = str(tmp_path / "room.ifc")
    _build_ifc(simple_room_data, FLOOR_H, path)
    result = _sanity_check(path)
    return path, result


# ── Tests ────────────────────────────────────────────────────────────────

def test_ifc_file_created(built_ifc):
    from os.path import getsize
    path, _ = built_ifc
    assert getsize(path) > 0


def test_four_walls_created(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    assert len(model.by_type("IfcWall")) == 4


def test_door_created(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    assert len(model.by_type("IfcDoor")) == 1


def test_opening_element_created(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    assert len(model.by_type("IfcOpeningElement")) == 1


def test_void_relationship(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    voids = model.by_type("IfcRelVoidsElement")
    assert len(voids) == 1
    assert voids[0].RelatingBuildingElement.is_a("IfcWall")
    assert voids[0].RelatedOpeningElement.is_a("IfcOpeningElement")


def test_fill_relationship(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    fills = model.by_type("IfcRelFillsElement")
    assert len(fills) == 1
    assert fills[0].RelatingOpeningElement.is_a("IfcOpeningElement")
    assert fills[0].RelatedBuildingElement.is_a("IfcDoor")


def test_space_created(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    spaces = model.by_type("IfcSpace")
    assert len(spaces) >= 1, "Expected at least one IfcSpace for the room"


def test_space_contained_in_storey(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    storey = model.by_type("IfcBuildingStorey")[0]
    spaces = model.by_type("IfcSpace")
    contained_ids = set()
    # Spaces use aggregation (IfcRelAggregates), not containment.
    for rel in model.by_type("IfcRelAggregates"):
        if rel.RelatingObject == storey:
            for e in rel.RelatedObjects:
                contained_ids.add(e.id())
    for s in spaces:
        assert s.id() in contained_ids, f"Space #{s.Name} not aggregated under storey"


def test_all_walls_in_storey(built_ifc):
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    storey = model.by_type("IfcBuildingStorey")[0]
    contained_ids = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        if rel.RelatingStructure == storey:
            for e in rel.RelatedElements:
                contained_ids.add(e.id())
    walls = model.by_type("IfcWall")
    for w in walls:
        assert w.id() in contained_ids, f"Wall #{w.Name} not contained in storey"


def test_sanity_check_passes(built_ifc):
    _, result = built_ifc
    assert result["storey_mismatches"] == [], "Storey containment mismatches"
    assert result["geometry_fail"] == 0, f"{result['geometry_fail']} geometry failures"
    assert result["geometry_ok"] > 0, "No geometry produced"
    assert result["volume_issues"] == [], "Volume issues detected"


def test_wall_with_door_has_hole(built_ifc):
    """The south wall should have a boolean result from the door subtraction."""
    path, _ = built_ifc
    model = ifcopenshell.open(path)

    # Find the south wall.
    south = None
    for w in model.by_type("IfcWall"):
        if w.Name == "W_South":
            south = w
            break
    assert south is not None

    has_boolean = False
    for rep in south.Representation.Representations:
        for item in rep.Items:
            if item.is_a("IfcBooleanResult"):
                has_boolean = True
    assert has_boolean, "South wall has no boolean result after door subtraction"


def test_door_volume_less_than_solid(built_ifc):
    """South wall volume must be less than solid (door hole cut out)."""
    path, _ = built_ifc
    model = ifcopenshell.open(path)
    settings = ifcopenshell.geom.settings()

    south = None
    for w in model.by_type("IfcWall"):
        if w.Name == "W_South":
            south = w
            break
    assert south is not None

    shape = ifcopenshell.geom.create_shape(settings, south)
    assert shape is not None
    verts = np.array(shape.geometry.verts).reshape(-1, 3)
    faces = np.array(shape.geometry.faces).reshape(-1, 3)
    vol = 0.0
    for tri in faces:
        v0, v1, v2 = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        vol += np.dot(v0, np.cross(v1, v2)) / 6.0
    vol = abs(vol)

    # Solid wall: 4.0 x 0.2 x 2.7 = 2.16 m³ (approx, with corner overlaps).
    # Door hole: 1.0 x 0.2 x 2.1 = 0.42 m³.
    solid_vol = ROOM_W / 1000 * WALL_THICK / 1000 * FLOOR_H / 1000
    assert vol < solid_vol - 0.01, f"Wall vol {vol:.4f} should be < solid {solid_vol:.4f}"
    assert vol > solid_vol - 1.0, f"Wall vol {vol:.4f} is suspiciously low"


def test_find_room_loops_detects_rectangle():
    """find_room_loops should detect the 4-wall rectangle."""
    walls = [
        {"id": "W_South", "vertices": [[0, 0], [ROOM_W, 0]]},
        {"id": "W_East",  "vertices": [[ROOM_W, 0], [ROOM_W, ROOM_H]]},
        {"id": "W_North", "vertices": [[ROOM_W, ROOM_H], [0, ROOM_H]]},
        {"id": "W_West",  "vertices": [[0, ROOM_H], [0, 0]]},
    ]
    loops = find_room_loops(walls)
    assert len(loops) >= 1, "Expected at least one room loop"
    # The loop should have 4 vertices.
    assert len(loops[0]) == 4
