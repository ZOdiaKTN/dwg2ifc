"""Tests for wall creation with extruded solid geometry."""
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ifc_skeleton import create_ifc_skeleton, create_wall


@pytest.fixture()
def wall_ifc(tmp_path):
    """Create an IFC file with one wall and return its path."""
    path = str(tmp_path / "wall_test.ifc")

    # Build the skeleton (also assigns units).
    create_ifc_skeleton(output_path=path)

    # Re-open, add a wall, and re-save.
    model = ifcopenshell.open(path)
    storey = model.by_type("IfcBuildingStorey")[0]

    # A 5-metre wall, 200 mm thick, 2700 mm tall.
    create_wall(
        model,
        storey,
        p1_mm=(0.0, 0.0),
        p2_mm=(5000.0, 0.0),
        thickness_mm=200.0,
        height_mm=2700.0,
        wall_id="W001",
    )

    model.write(path)
    return path


def test_wall_entity_exists(wall_ifc):
    """An IfcWall entity must be present in the file."""
    model = ifcopenshell.open(wall_ifc)
    walls = model.by_type("IfcWall")
    assert len(walls) == 1
    assert walls[0].Name == "W001"


def test_wall_contained_in_storey(wall_ifc):
    """The wall must be contained in the Ground Floor storey."""
    model = ifcopenshell.open(wall_ifc)
    wall = model.by_type("IfcWall")[0]
    storey = model.by_type("IfcBuildingStorey")[0]

    # Check containment via the inverse relationship.
    contained = False
    for rel in storey.ContainsElements:
        if wall in rel.RelatedElements:
            contained = True
            break
    assert contained, "Wall is not contained in the storey"


def test_wall_has_representation(wall_ifc):
    """The wall must have a shape representation."""
    model = ifcopenshell.open(wall_ifc)
    wall = model.by_type("IfcWall")[0]
    rep = wall.Representation
    assert rep is not None, "Wall has no Representation"
    assert len(rep.Representations) > 0, "Representation list is empty"


def test_wall_geometry_iterator(wall_ifc):
    """Re-read the IFC with create_shape and confirm non-empty valid geometry."""
    model = ifcopenshell.open(wall_ifc)
    settings = ifcopenshell.geom.settings()

    wall = model.by_type("IfcWall")[0]
    shape = ifcopenshell.geom.create_shape(settings, wall)
    assert shape is not None, "create_shape returned None for wall"
    geom = shape.geometry
    assert geom is not None, "Geometry is None"
    assert len(geom.verts) > 0, f"Geometry has no vertices (got {len(geom.verts)})"
    assert len(geom.faces) > 0, f"Geometry has no faces (got {len(geom.faces)})"


def test_wall_extrusion_height(wall_ifc):
    """The extruded solid should span 0 to floor_height_mm (2700 mm) on Z."""
    model = ifcopenshell.open(wall_ifc)
    wall = model.by_type("IfcWall")[0]

    # Walk into the shape representation to find the IfcExtrudedAreaSolid.
    reps = wall.Representation.Representations
    found_extrusion = False
    for rep in reps:
        for item in rep.Items:
            if item.is_a("IfcExtrudedAreaSolid"):
                extrusion = item
                depth = extrusion.Depth  # in project units (mm)
                assert abs(depth - 2700.0) < 1.0, f"Expected depth ~2700 mm, got {depth}"
                found_extrusion = True
    assert found_extrusion, "No IfcExtrudedAreaSolid found in wall representation"
