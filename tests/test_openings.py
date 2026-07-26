"""Tests for opening handling: IfcOpeningElement, boolean subtraction, void/fill."""
import math
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ifc_skeleton import create_ifc_skeleton, create_wall, create_opening_in_wall

MM_TO_M = 1000.0


@pytest.fixture()
def wall_with_door(tmp_path):
    """Create an IFC file with one wall and one door opening."""
    path = str(tmp_path / "wall_door.ifc")
    create_ifc_skeleton(output_path=path)

    model = ifcopenshell.open(path)
    storey = model.by_type("IfcBuildingStorey")[0]

    # Wall: 5 m long, 200 mm thick, 2700 mm tall.
    wall = create_wall(
        model, storey,
        p1_mm=(0.0, 0.0), p2_mm=(5000.0, 0.0),
        thickness_mm=200.0, height_mm=2700.0, wall_id="W1",
    )

    # Door: 1000 mm wide, 2100 mm tall, sill at 0 mm, centered on the wall.
    create_opening_in_wall(
        model, wall,
        opening_width_mm=1000.0, opening_height_mm=2100.0,
        sill_height_mm=0.0, center_along_mm=2500.0,
        opening_id="D1",
    )

    model.write(path)
    return path


def test_opening_and_door_entities_exist(wall_with_door):
    model = ifcopenshell.open(wall_with_door)
    assert len(model.by_type("IfcOpeningElement")) == 1
    assert len(model.by_type("IfcDoor")) == 1
    assert model.by_type("IfcDoor")[0].Name == "D1_Door"


def test_void_relationship_exists(wall_with_door):
    model = ifcopenshell.open(wall_with_door)
    voids = model.by_type("IfcRelVoidsElement")
    assert len(voids) == 1
    rel = voids[0]
    assert rel.RelatingBuildingElement.is_a("IfcWall")
    assert rel.RelatedOpeningElement.is_a("IfcOpeningElement")


def test_fill_relationship_exists(wall_with_door):
    model = ifcopenshell.open(wall_with_door)
    fills = model.by_type("IfcRelFillsElement")
    assert len(fills) == 1
    rel = fills[0]
    assert rel.RelatingOpeningElement.is_a("IfcOpeningElement")
    assert rel.RelatedBuildingElement.is_a("IfcDoor")


def test_wall_boolean_result(wall_with_door):
    """The wall's representation should contain an IfcBooleanResult after subtraction."""
    model = ifcopenshell.open(wall_with_door)
    wall = model.by_type("IfcWall")[0]

    has_boolean = False
    for rep in wall.Representation.Representations:
        for item in rep.Items:
            if item.is_a("IfcBooleanResult"):
                has_boolean = True
                break
    assert has_boolean, "Wall representation has no IfcBooleanResult (boolean subtraction failed)"


def test_wall_geometry_has_hole(wall_with_door):
    """Compare wall-with-door volume to a solid wall: door wall must be smaller."""
    model = ifcopenshell.open(wall_with_door)
    wall = model.by_type("IfcWall")[0]

    settings = ifcopenshell.geom.settings()
    shape = ifcopenshell.geom.create_shape(settings, wall)
    assert shape is not None
    verts = shape.geometry.verts
    faces = shape.geometry.faces
    assert len(verts) > 0, "No vertices in wall geometry"
    assert len(faces) > 0, "No faces in wall geometry"

    # Compute volume via divergence theorem (signed tetrahedron volumes).
    verts_arr = np.array(verts).reshape(-1, 3)
    faces_arr = np.array(faces).reshape(-1, 3)
    volume = 0.0
    for tri in faces_arr:
        v0, v1, v2 = verts_arr[tri[0]], verts_arr[tri[1]], verts_arr[tri[2]]
        volume += np.dot(v0, np.cross(v1, v2)) / 6.0
    volume = abs(volume)

    # Expected solid volume: wall bounding box minus door opening.
    # Wall: 5.0 x 0.2 x 2.7 = 2.7 m³
    # Door hole: 1.0 x 0.2 x 2.1 = 0.42 m³
    # Expected: 2.7 - 0.42 = 2.28 m³
    expected_solid = 5.0 * 0.2 * 2.7
    expected_with_hole = expected_solid - 1.0 * 0.2 * 2.1

    assert volume < expected_solid - 0.01, (
        f"Wall volume {volume:.4f} m³ should be less than solid wall {expected_solid:.4f} m³"
    )
    assert abs(volume - expected_with_hole) < 0.3, (
        f"Wall volume {volume:.4f} m³ differs from expected {expected_with_hole:.4f} m³"
    )


def test_opening_positioned_at_sill(wall_with_door):
    """The opening element's placement should have Z = sill (0.0 for doors)."""
    model = ifcopenshell.open(wall_with_door)
    opening = model.by_type("IfcOpeningElement")[0]

    placement = opening.ObjectPlacement
    assert placement is not None
    assert placement.is_a("IfcLocalPlacement")
    rel_placement = placement.RelativePlacement
    assert rel_placement.is_a("IfcAxis2Placement3D")
    location = rel_placement.Location
    # Sill = 0.0 for doors.
    assert abs(location.Coordinates[2]) < 0.01, (
        f"Expected opening Z ~0.0 (sill), got {location.Coordinates[2]}"
    )


def test_door_height_matches_opening(wall_with_door):
    """The door's bounding box should match the opening dimensions."""
    model = ifcopenshell.open(wall_with_door)
    opening = model.by_type("IfcOpeningElement")[0]
    door = model.by_type("IfcDoor")[0]

    settings = ifcopenshell.geom.settings()

    def _bounding_height(entity):
        shape = ifcopenshell.geom.create_shape(settings, entity)
        if shape is None or len(shape.geometry.verts) == 0:
            return None
        verts = np.array(shape.geometry.verts).reshape(-1, 3)
        return verts[:, 2].max() - verts[:, 2].min()

    open_h = _bounding_height(opening)
    door_h = _bounding_height(door)
    assert open_h is not None, "Could not compute opening bounding height"
    assert door_h is not None, "Could not compute door bounding height"
    # Door geometry (frame+panel) may exceed the opening slightly,
    # but the door height should be within the opening height range.
    assert door_h <= open_h + 0.1, (
        f"Door height {door_h:.3f} exceeds opening height {open_h:.3f}"
    )
