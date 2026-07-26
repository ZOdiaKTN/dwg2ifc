"""Tests for the minimal IFC skeleton."""
import sys
from pathlib import Path

import ifcopenshell
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ifc_skeleton import create_ifc_skeleton


@pytest.fixture()
def skeleton_path(tmp_path):
    """Create a skeleton IFC file in a temp directory."""
    path = str(tmp_path / "skeleton.ifc")
    create_ifc_skeleton(output_path=path)
    return path


def test_file_created(skeleton_path):
    import os
    assert os.path.exists(skeleton_path)
    assert os.path.getsize(skeleton_path) > 0


def test_hierarchy(skeleton_path):
    model = ifcopenshell.open(skeleton_path)

    projects = model.by_type("IfcProject")
    sites = model.by_type("IfcSite")
    buildings = model.by_type("IfcBuilding")
    storeys = model.by_type("IfcBuildingStorey")

    assert len(projects) == 1
    assert len(sites) == 1
    assert len(buildings) == 1
    assert len(storeys) == 1

    project = projects[0]
    site = sites[0]
    building = buildings[0]
    storey = storeys[0]

    # Use Decomposes (inverse on child) to verify parent links.
    assert site.Decomposes[0].RelatingObject == project
    assert building.Decomposes[0].RelatingObject == site
    assert storey.Decomposes[0].RelatingObject == building


def test_storey_elevation(skeleton_path):
    model = ifcopenshell.open(skeleton_path)
    storey = model.by_type("IfcBuildingStorey")[0]
    assert storey.Elevation == 0.0


def test_storey_name(skeleton_path):
    model = ifcopenshell.open(skeleton_path)
    storey = model.by_type("IfcBuildingStorey")[0]
    assert storey.Name == "Ground Floor"
