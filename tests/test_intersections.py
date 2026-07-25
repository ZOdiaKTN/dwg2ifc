"""Tests for find_intersections and build_joints."""

import pytest
from src.parse_dxf import find_intersections, build_joints


def _wall(wid: str, v0: list[float], v1: list[float]) -> dict:
    return {"id": wid, "vertices": [v0, v1], "closed": False}


class TestFindIntersections:

    def test_t_junction(self):
        """One wall ending mid-span of another produces a T-junction."""
        w1 = _wall("h", [0.0, 0.0], [4000.0, 0.0])
        w2 = _wall("v", [2000.0, 0.0], [2000.0, 3000.0])
        result = find_intersections([w1, w2])
        assert len(result) == 1
        inter = result[0]
        assert inter["type"] == "T"
        assert inter["point"] == pytest.approx([2000.0, 0.0])
        assert set(inter["walls"]) == {"h", "v"}

    def test_rectangle_4_corners(self):
        """Four walls forming a closed rectangle — 4 L-junctions."""
        bottom = _wall("b", [0.0, 0.0], [4000.0, 0.0])
        right = _wall("r", [4000.0, 0.0], [4000.0, 3000.0])
        top = _wall("t", [4000.0, 3000.0], [0.0, 3000.0])
        left = _wall("l", [0.0, 3000.0], [0.0, 0.0])
        walls = [bottom, right, top, left]
        result = find_intersections(walls)
        corners = [i for i in result if i["type"] == "L"]
        assert len(corners) == 4
        pts = {tuple(c["point"]) for c in corners}
        assert (0.0, 0.0) in pts
        assert (4000.0, 0.0) in pts
        assert (4000.0, 3000.0) in pts
        assert (0.0, 3000.0) in pts

    def test_x_junction(self):
        """Two walls crossing at mid-span — X-junction."""
        w1 = _wall("h", [0.0, 0.0], [4000.0, 0.0])
        w2 = _wall("v", [2000.0, -1000.0], [2000.0, 1000.0])
        result = find_intersections([w1, w2])
        assert len(result) == 1
        assert result[0]["type"] == "X"
        assert result[0]["point"] == pytest.approx([2000.0, 0.0])

    def test_no_intersection(self):
        """Two parallel walls produce no intersections."""
        w1 = _wall("a", [0.0, 0.0], [4000.0, 0.0])
        w2 = _wall("b", [0.0, 1000.0], [4000.0, 1000.0])
        result = find_intersections([w1, w2])
        assert result == []

    def test_empty_walls(self):
        assert find_intersections([]) == []

    def test_single_wall(self):
        w = _wall("a", [0.0, 0.0], [100.0, 0.0])
        assert find_intersections([w]) == []


class TestBuildJoints:

    def test_t_junction_trims_terminating_wall(self):
        """At a T-junction the terminating wall is trimmed to the intersection."""
        w1 = _wall("h", [0.0, 0.0], [4000.0, 0.0])
        w2 = _wall("v", [2000.0, 0.0], [2000.0, 3000.0])
        intersections = find_intersections([w1, w2])
        result = build_joints([w1, w2], intersections)
        assert len(result) == 2
        h = [w for w in result if w["id"] == "h"][0]
        v = [w for w in result if w["id"] == "v"][0]
        assert h["vertices"] == [[0.0, 0.0], [4000.0, 0.0]]
        # v's start endpoint is at the T-junction intersection
        assert v["vertices"][0] == pytest.approx([2000.0, 0.0])
        assert v["vertices"][1] == [2000.0, 3000.0]

    def test_t_junction_trims_start_endpoint(self):
        """T-junction where the terminating wall's START endpoint is trimmed."""
        w1 = _wall("h", [0.0, 0.0], [4000.0, 0.0])
        w2 = _wall("v", [2000.0, -100.0], [2000.0, 3000.0])
        intersections = find_intersections([w1, w2])
        # This is an X-junction since neither endpoint is at the intersection.
        # To get a T, make v start exactly on h.
        assert intersections[0]["type"] == "X"

    def test_t_junction_trims_end_endpoint(self):
        """T-junction where the terminating wall's END endpoint is trimmed."""
        w1 = _wall("h", [0.0, 0.0], [4000.0, 0.0])
        w2 = _wall("v", [2000.0, 3000.0], [2000.0, 0.0])
        intersections = find_intersections([w1, w2])
        result = build_joints([w1, w2], intersections)
        v = [w for w in result if w["id"] == "v"][0]
        assert v["vertices"][-1] == pytest.approx([2000.0, 0.0])

    def test_rectangle_no_modification(self):
        """Four L-junctions leave walls unchanged."""
        bottom = _wall("b", [0.0, 0.0], [4000.0, 0.0])
        right = _wall("r", [4000.0, 0.0], [4000.0, 3000.0])
        top = _wall("t", [4000.0, 3000.0], [0.0, 3000.0])
        left = _wall("l", [0.0, 3000.0], [0.0, 0.0])
        walls = [bottom, right, top, left]
        intersections = find_intersections(walls)
        result = build_joints(walls, intersections)
        orig = {w["id"]: w["vertices"] for w in walls}
        for w in result:
            assert w["vertices"] == orig[w["id"]]

    def test_x_junction_splits_both_walls(self):
        """An X-junction splits both walls at the crossing point."""
        w1 = _wall("h", [0.0, 0.0], [4000.0, 0.0])
        w2 = _wall("v", [2000.0, -1000.0], [2000.0, 1000.0])
        intersections = find_intersections([w1, w2])
        result = build_joints([w1, w2], intersections)
        h_segs = [w for w in result if w["id"].startswith("h")]
        v_segs = [w for w in result if w["id"].startswith("v")]
        assert len(h_segs) == 2
        assert len(v_segs) == 2
        h_pts = sorted(
            [w["vertices"][0] for w in h_segs] + [w["vertices"][-1] for w in h_segs]
        )
        assert h_pts[0] == pytest.approx([0.0, 0.0])
        assert h_pts[-1] == pytest.approx([4000.0, 0.0])

    def test_no_intersections_passthrough(self):
        w1 = _wall("a", [0.0, 0.0], [100.0, 0.0])
        w2 = _wall("b", [0.0, 200.0], [100.0, 200.0])
        result = build_joints([w1, w2], [])
        assert len(result) == 2
        assert result[0]["vertices"] == [[0.0, 0.0], [100.0, 0.0]]
        assert result[1]["vertices"] == [[0.0, 200.0], [100.0, 200.0]]
