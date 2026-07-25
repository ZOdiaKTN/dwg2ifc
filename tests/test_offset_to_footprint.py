"""Tests for offset_to_footprint."""

import math
import pytest
from shapely.geometry import LineString, Polygon
from src.parse_dxf import offset_to_footprint


def _wall(wid: str, v0: list[float], v1: list[float], **extra) -> dict:
    d = {"id": wid, "vertices": [v0, v1], "closed": False}
    d.update(extra)
    return d


def _perpendicular_width(poly: Polygon, centerline: LineString) -> float:
    """Measure the footprint width perpendicular to the centreline.

    Casts a long ray through the centreline's midpoint, perpendicular to
    the line, and returns the length of the intersection with the polygon.
    """
    dx = centerline.coords[-1][0] - centerline.coords[0][0]
    dy = centerline.coords[-1][1] - centerline.coords[0][1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length  # unit normal

    mid_x = (centerline.coords[0][0] + centerline.coords[-1][0]) / 2
    mid_y = (centerline.coords[0][1] + centerline.coords[-1][1]) / 2

    far = length  # long enough to span the full polygon
    ray = LineString([
        (mid_x - nx * far, mid_y - ny * far),
        (mid_x + nx * far, mid_y + ny * far),
    ])
    inter = poly.intersection(ray)
    return inter.length


class TestOffsetToFootprint:

    def test_horizontal_wall(self):
        w = _wall("A", [0.0, 0.0], [1000.0, 0.0])
        poly = offset_to_footprint(w, thickness_mm=200)
        assert poly.is_valid
        assert isinstance(poly, Polygon)
        cl = LineString(w["vertices"])
        width = _perpendicular_width(poly, cl)
        assert abs(width - 200) < 1e-6

    def test_diagonal_wall(self):
        w = _wall("B", [0.0, 0.0], [300.0, 400.0])
        poly = offset_to_footprint(w, thickness_mm=100)
        cl = LineString(w["vertices"])
        width = _perpendicular_width(poly, cl)
        assert abs(width - 100) < 1e-6

    def test_default_thickness_used(self):
        w = _wall("C", [0.0, 0.0], [500.0, 0.0])
        poly = offset_to_footprint(w, default_thickness_mm=150)
        cl = LineString(w["vertices"])
        width = _perpendicular_width(poly, cl)
        assert abs(width - 150) < 1e-6

    def test_wall_dict_thickness_takes_precedence(self):
        w = _wall("D", [0.0, 0.0], [500.0, 0.0], thickness=300)
        poly = offset_to_footprint(w, default_thickness_mm=150)
        cl = LineString(w["vertices"])
        width = _perpendicular_width(poly, cl)
        assert abs(width - 300) < 1e-6

    def test_explicit_thickness_overrides_dict(self):
        w = _wall("E", [0.0, 0.0], [500.0, 0.0], thickness=300)
        poly = offset_to_footprint(w, thickness_mm=80, default_thickness_mm=150)
        cl = LineString(w["vertices"])
        width = _perpendicular_width(poly, cl)
        assert abs(width - 80) < 1e-6

    def test_multi_segment_wall(self):
        w = _wall("F", [0.0, 0.0], [100.0, 0.0])
        w["vertices"] = [[0.0, 0.0], [500.0, 0.0], [500.0, 500.0]]
        poly = offset_to_footprint(w, thickness_mm=200)
        assert poly.is_valid
        assert isinstance(poly, Polygon)
        # Straight segment width check
        cl = LineString([[0.0, 0.0], [500.0, 0.0]])
        width = _perpendicular_width(poly, cl)
        assert abs(width - 200) < 1e-6

    def test_polygon_is_closed(self):
        w = _wall("G", [0.0, 0.0], [100.0, 0.0])
        poly = offset_to_footprint(w, thickness_mm=50)
        assert poly.exterior.is_closed

    def test_footprint_contains_centreline(self):
        w = _wall("H", [0.0, 0.0], [1000.0, 0.0])
        poly = offset_to_footprint(w, thickness_mm=200)
        cl = LineString(w["vertices"])
        assert poly.contains(cl)

    def test_thin_wall(self):
        w = _wall("I", [0.0, 0.0], [200.0, 0.0])
        poly = offset_to_footprint(w, thickness_mm=10)
        cl = LineString(w["vertices"])
        width = _perpendicular_width(poly, cl)
        assert abs(width - 10) < 1e-6

    def test_no_vertices_key_raises(self):
        with pytest.raises(KeyError):
            offset_to_footprint({"id": "bad"}, thickness_mm=100)
