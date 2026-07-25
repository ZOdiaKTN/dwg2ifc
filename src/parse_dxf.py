#!/usr/bin/env python3
"""Parse a DXF floor plan into walls, doors, and windows.

Usage::

    python src/parse_dxf.py input.dxf layer_config.yaml output.json

Writes a JSON file with keys ``walls``, ``doors``, and ``windows`` and
prints a one-line summary with counts plus any warnings that were logged.
"""

import json
import logging
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.inventory import extract_walls, extract_openings, load_layer_config

logger = logging.getLogger(__name__)


class _WarningCollector(logging.Handler):
    """Capture WARNING+ log records so we can report them in the summary."""

    def __init__(self):
        super().__init__()
        self.warnings: list[str] = []

    def emit(self, record):
        self.warnings.append(record.getMessage())


def _wall_direction(wall: dict) -> tuple[float, float]:
    """Return the (dx, dy) direction vector of a wall."""
    v = wall["vertices"]
    return (v[-1][0] - v[0][0], v[-1][1] - v[0][1])


def _are_parallel(w1: dict, w2: dict) -> bool:
    """True if two walls are approximately parallel (cos angle > 0.95)."""
    dx1, dy1 = _wall_direction(w1)
    dx2, dy2 = _wall_direction(w2)
    mag1 = (dx1**2 + dy1**2) ** 0.5
    mag2 = (dx2**2 + dy2**2) ** 0.5
    if mag1 == 0 or mag2 == 0:
        return True
    cos = abs(dx1 * dx2 + dy1 * dy2) / (mag1 * mag2)
    return cos > 0.95


def match_opening_to_wall(
    opening: dict,
    walls: list[dict],
    angle_tolerance_deg: float = 10,
) -> dict | None:
    """Find the nearest wall to an opening whose direction matches.

    The opening's ``rotation_deg`` must align with the wall's direction
    within *angle_tolerance_deg*.  The angle between the opening rotation
    and the wall direction is checked modulo 180° (a door at 0° and a wall
    at 180° are considered aligned).

    Returns the matching wall dict, or ``None`` if no wall is both close
    enough and aligned.  Logs a warning when a nearby wall fails the
    alignment check.
    """
    import math

    if not walls:
        return None

    ox, oy = opening["insertion_point"]
    opening_angle = opening.get("rotation_deg", 0.0)

    def _point_to_segment_dist(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        len_sq = dx * dx + dy * dy
        if len_sq == 0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

    def _wall_angle_deg(wall):
        v = wall["vertices"]
        dx = v[-1][0] - v[0][0]
        dy = v[-1][1] - v[0][1]
        return math.degrees(math.atan2(dy, dx))

    def _angle_diff_mod180(a, b):
        d = abs(a - b) % 180
        return min(d, 180 - d)

    best_wall = None
    best_dist = float("inf")
    best_angle_diff = 0.0

    for wall in walls:
        v = wall["vertices"]
        dist = _point_to_segment_dist(ox, oy, v[0][0], v[0][1], v[-1][0], v[-1][1])
        if dist < best_dist:
            best_dist = dist
            best_wall = wall
            best_angle_diff = _angle_diff_mod180(opening_angle, _wall_angle_deg(wall))

    if best_wall is None:
        return None

    if best_angle_diff > angle_tolerance_deg:
        logger.warning(
            "Opening %s rejected: nearest wall %s is %.1f° off "
            "(diff=%.1f°, tolerance=%.1f°)",
            opening.get("id", "?"),
            best_wall.get("id", "?"),
            best_angle_diff,
            best_angle_diff,
            angle_tolerance_deg,
        )
        return None

    return best_wall


def compute_opening_position(opening: dict, wall: dict) -> dict | None:
    """Project an opening onto a wall centerline and validate placement.

    The opening's ``estimated_width_mm`` is centered at the projection of
    its ``insertion_point`` onto the wall segment.  Returns a dict with
    ``wall_id``, ``center_t`` (parameter along the wall, 0–1), and
    ``start_mm`` / ``end_mm`` (distance from wall start in mm).

    Returns ``None`` and logs a warning when the opening does not fit
    within the wall segment.
    """
    import math

    v0, v1 = wall["vertices"][0], wall["vertices"][-1]
    dx = v1[0] - v0[0]
    dy = v1[1] - v0[1]
    wall_length = math.hypot(dx, dy)
    if wall_length < 1e-6:
        logger.warning(
            "Opening %s rejected: wall %s has zero length",
            opening.get("id", "?"), wall.get("id", "?"),
        )
        return None

    ox, oy = opening["insertion_point"]
    t = ((ox - v0[0]) * dx + (oy - v0[1]) * dy) / (wall_length ** 2)
    t = max(0.0, min(1.0, t))

    width = opening.get("estimated_width_mm", 0.0)
    start_mm = t * wall_length - width / 2.0
    end_mm = t * wall_length + width / 2.0

    if start_mm < 0 or end_mm > wall_length:
        logger.warning(
            "Opening %s does not fit on wall %s: "
            "start=%.0f mm, end=%.0f mm, wall length=%.0f mm",
            opening.get("id", "?"), wall.get("id", "?"),
            start_mm, end_mm, wall_length,
        )
        return None

    cx = v0[0] + t * dx
    cy = v0[1] + t * dy
    return {
        "wall_id": wall["id"],
        "center_t": round(t, 6),
        "start_mm": round(start_mm, 6),
        "end_mm": round(end_mm, 6),
        "center_point": (round(cx, 6), round(cy, 6)),
    }


def snap_endpoints(
    walls: list[dict],
    tolerance_mm: float = 10,
    corner_tolerance_mm: float = 100,
    min_wall_length_mm: float = 1.0,
) -> list[dict]:
    """Snap near-coincident wall endpoints to shared coords.

    Two passes:
    1. Snap *all* endpoint pairs within *tolerance_mm* (float-noise cleanup).
    2. Snap *non-parallel* endpoint pairs within *corner_tolerance_mm*
       (drafting gaps at corners).  Parallel pairs (wall thickness) are
       never snapped in this pass so walls keep their thickness.

    After snapping, walls whose *original* length was already below
    *min_wall_length_mm* and that collapsed further are removed.
    Valid walls are never removed regardless of post-snap length.

    Returns a new list of wall dicts with corrected vertices.
    """
    from shapely.geometry import Point, MultiPoint

    if not walls:
        return walls

    # Record original lengths for degenerate detection.
    orig_lengths = {}
    for w in walls:
        v = w["vertices"]
        orig_lengths[w["id"]] = ((v[-1][0] - v[0][0]) ** 2
                                 + (v[-1][1] - v[0][1]) ** 2) ** 0.5

    def _apply_snap(walls_in, snap_map):
        corrected = []
        for wall in walls_in:
            new_vertices = []
            for coord in wall["vertices"]:
                pt = Point(coord)
                if pt in snap_map:
                    sp = snap_map[pt]
                    new_vertices.append([sp.x, sp.y])
                else:
                    new_vertices.append(list(coord))
            corrected.append({**wall, "vertices": new_vertices})
        return corrected

    def _snap_within(walls_in, max_dist):
        endpoint_map = []
        for wi, wall in enumerate(walls_in):
            for vi, coord in enumerate(wall["vertices"]):
                endpoint_map.append((Point(coord), wi, vi))

        snap_map = {}
        for i, (pt_i, wi_i, vi_i) in enumerate(endpoint_map):
            if pt_i in snap_map:
                continue
            candidates = [pt_i]
            for j in range(i + 1, len(endpoint_map)):
                pt_j, wi_j, vi_j = endpoint_map[j]
                if pt_j in snap_map:
                    continue
                if pt_i.distance(pt_j) <= max_dist:
                    candidates.append(pt_j)
            if len(candidates) > 1:
                centroid = MultiPoint(candidates).centroid
                snapped = Point(round(centroid.x, 6), round(centroid.y, 6))
                for c in candidates:
                    snap_map[c] = snapped
        return snap_map

    # Pass 1: all pairs within tolerance_mm
    snap_map1 = _snap_within(walls, tolerance_mm)
    corrected = _apply_snap(walls, snap_map1)

    # Pass 2: non-parallel pairs within corner_tolerance_mm
    endpoint_map2 = []
    for wi, wall in enumerate(corrected):
        for vi, coord in enumerate(wall["vertices"]):
            endpoint_map2.append((Point(coord), wi, vi))

    snap_map2 = {}
    for i, (pt_i, wi_i, vi_i) in enumerate(endpoint_map2):
        if pt_i in snap_map2:
            continue
        candidates = [pt_i]
        for j in range(i + 1, len(endpoint_map2)):
            pt_j, wi_j, vi_j = endpoint_map2[j]
            if pt_j in snap_map2:
                continue
            dist = pt_i.distance(pt_j)
            if dist <= tolerance_mm:
                continue  # already handled in pass 1
            if dist <= corner_tolerance_mm:
                if not _are_parallel(corrected[wi_i], corrected[wi_j]):
                    candidates.append(pt_j)
        if len(candidates) > 1:
            centroid = MultiPoint(candidates).centroid
            snapped = Point(round(centroid.x, 6), round(centroid.y, 6))
            for c in candidates:
                snap_map2[c] = snapped

    if snap_map2:
        corrected = _apply_snap(corrected, snap_map2)

    # Remove only walls that were already tiny and collapsed further.
    # Valid walls (original length > min_wall_length_mm) are never removed.
    corrected = [
        w for w in corrected
        if orig_lengths.get(w["id"], float("inf")) >= min_wall_length_mm
        or ((w["vertices"][-1][0] - w["vertices"][0][0]) ** 2
            + (w["vertices"][-1][1] - w["vertices"][0][1]) ** 2) ** 0.5
        >= min_wall_length_mm
    ]

    return corrected


def find_intersections(walls: list[dict]) -> list[dict]:
    """Detect wall-to-wall intersections and T-junctions after snapping.

    Returns a list of intersection records, each containing:
      - ``type``: ``"L"`` (corner), ``"T"`` (T-junction), or ``"X"`` (crossing)
      - ``point``: ``[x, y]`` of the intersection
      - ``walls``: list of wall *ids* involved
      - ``wall_indices``: list of integer indices into the input *walls* list

    Only geometric intersections of two segments are reported; coincident
    endpoints that were already snapped together are classified as ``"L"``
    corners.
    """
    from shapely.geometry import LineString, Point

    if len(walls) < 2:
        return []

    segs = []
    for w in walls:
        v = w["vertices"]
        segs.append(LineString([v[0], v[-1]]))

    seen = set()
    results = []

    for i in range(len(walls)):
        for j in range(i + 1, len(walls)):
            if segs[i].is_empty or segs[j].is_empty:
                continue
            if not segs[i].intersects(segs[j]):
                continue

            inter = segs[i].intersection(segs[j])
            geom_type = inter.geom_type

            if geom_type == "Point":
                pt = [round(inter.x, 6), round(inter.y, 6)]
            elif geom_type == "MultiPoint":
                if len(inter.geoms) > 1:
                    continue
                pt = [round(inter.geoms[0].x, 6), round(inter.geoms[0].y, 6)]
            else:
                continue

            key = (round(pt[0], 6), round(pt[1], 6))
            if key in seen:
                continue
            seen.add(key)

            # Classify the junction by checking whether the intersection
            # point lies on an endpoint of either segment.
            pi = Point(pt)
            eps = 1e-4
            on_i_end = (
                pi.distance(Point(walls[i]["vertices"][0])) < eps
                or pi.distance(Point(walls[i]["vertices"][-1])) < eps
            )
            on_j_end = (
                pi.distance(Point(walls[j]["vertices"][0])) < eps
                or pi.distance(Point(walls[j]["vertices"][-1])) < eps
            )

            if on_i_end and on_j_end:
                jtype = "L"
            elif on_i_end or on_j_end:
                jtype = "T"
            else:
                jtype = "X"

            results.append({
                "type": jtype,
                "point": pt,
                "walls": [walls[i]["id"], walls[j]["id"]],
                "wall_indices": [i, j],
            })

    return results


def build_joints(
    walls: list[dict],
    intersections: list[dict],
) -> list[dict]:
    """Generate proper butt-joint geometry at every intersection.

    DIALux EVO's IFC import requires walls accurate to the millimetre
    with butt joints — no gaps, no overlaps.  This function processes
    every intersection returned by :func:`find_intersections` and
    produces a new wall list where:

    * **T-junctions** — the *continuous* wall (the one whose span is
      hit) passes through unchanged; the *terminating* wall's endpoint
      is trimmed exactly to the intersection point.
    * **X-junctions** — both walls are split into two segments at the
      intersection point.
    * **L-junctions** — both walls already share a common endpoint
      (after :func:`snap_endpoints`), so they are left untouched.

    Walls that are not involved in any intersection are returned as-is.
    New wall dicts preserve all keys from the original.
    """
    if not intersections:
        return [dict(w) for w in walls]

    from shapely.geometry import LineString, Point

    # Build index lookup for fast wall access.
    wall_by_id = {w["id"]: w for w in walls}

    # Track walls that have been modified (endpoint trimmed).
    trimmed: dict[str, list[float]] = {}
    # Track walls that have been split (new segments to add).
    splits: list[tuple[str, list[list[float]], list[list[float]], dict]] = []

    for inter in intersections:
        i, j = inter["wall_indices"]
        pt = inter["point"]
        wi, wj = walls[i], walls[j]

        if inter["type"] == "L":
            continue

        if inter["type"] == "T":
            # Identify which wall terminates (has its endpoint at the
            # intersection) and which is continuous.
            pi = Point(pt)
            eps = 1e-4

            i_start = pi.distance(Point(wi["vertices"][0])) < eps
            i_end = pi.distance(Point(wi["vertices"][-1])) < eps
            j_start = pi.distance(Point(wj["vertices"][0])) < eps
            j_end = pi.distance(Point(wj["vertices"][-1])) < eps

            if i_start or i_end:
                term_id = wi["id"]
                term_idx = 0 if i_start else -1
                cont_id = wj["id"]
            else:
                term_id = wj["id"]
                term_idx = 0 if j_start else -1
                cont_id = wi["id"]

            trimmed[term_id] = (term_idx, pt)

        elif inter["type"] == "X":
            # Split both walls at the intersection point.
            for wid_idx in (i, j):
                w = walls[wid_idx]
                key = w["id"]
                v0, v1 = w["vertices"][0], w["vertices"][-1]
                p0 = Point(v0)
                p1 = Point(v1)
                dist_to_end = p1.distance(Point(pt))
                dist_to_start = p0.distance(Point(pt))
                if dist_to_end < 1e-4 or dist_to_start < 1e-4:
                    continue
                seg = LineString([v0, v1])
                frac = seg.project(Point(pt)) / seg.length
                new_v1 = [
                    round(v0[0] + frac * (v1[0] - v0[0]), 6),
                    round(v0[1] + frac * (v1[1] - v0[1]), 6),
                ]
                new_v0 = list(new_v1)
                splits.append((key, [list(v0), new_v1], [new_v0, list(v1)], w))

    # Build result list: start from a deep copy.
    result: list[dict] = []
    for w in walls:
        new_w = dict(w)
        new_w["vertices"] = [list(v) for v in w["vertices"]]

        # Apply endpoint trims.
        if w["id"] in trimmed:
            idx, pt_val = trimmed[w["id"]]
            new_w["vertices"][idx] = list(pt_val)

        result.append(new_w)

    # Apply splits: remove original, insert two halves.
    split_ids = {s[0] for s in splits}
    final: list[dict] = []
    for w in result:
        if w["id"] not in split_ids:
            final.append(w)
            continue
        for key, seg_a, seg_b, orig in splits:
            if key != w["id"]:
                continue
            w1 = dict(orig, vertices=seg_a, id=orig["id"] + "_a")
            w2 = dict(orig, vertices=seg_b, id=orig["id"] + "_b")
            final.append(w1)
            final.append(w2)

    return final


def offset_to_footprint(
    wall: dict,
    thickness_mm: float = None,
    default_thickness_mm: float = 200.0,
) -> "shapely.geometry.Polygon":
    """Convert a wall centerline into a double-line footprint polygon.

    Parameters
    ----------
    wall : dict
        Wall dict with at least a ``vertices`` key containing a list of
        ``(x, y)`` coordinate pairs (the centerline).
    thickness_mm : float, optional
        Wall thickness in millimetres.  If *None*, the wall's own
        ``"thickness"`` key is used; if that key is also absent,
        *default_thickness_mm* is applied.
    default_thickness_mm : float
        Fallback thickness when neither *thickness_mm* nor the wall dict
        supplies one.  Defaults to 200 mm.

    Returns
    -------
    shapely.geometry.Polygon
        A closed polygon representing the wall footprint, offset by
        ``thickness / 2`` on each side of the centreline.
    """
    from shapely.geometry import LineString, Polygon

    t = thickness_mm if thickness_mm is not None else wall.get("thickness", default_thickness_mm)
    half = t / 2.0

    verts = wall["vertices"]
    line = LineString(verts)

    left = line.offset_curve(half)
    right = line.offset_curve(-half)

    left_coords = list(left.coords)
    right_coords = list(right.coords)

    poly_coords = left_coords + list(reversed(right_coords))
    return Polygon(poly_coords)


def main() -> None:
    if len(sys.argv) != 4:
        print(
            f"Usage: python {sys.argv[0]} input.dxf layer_config.yaml output.json",
            file=sys.stderr,
        )
        sys.exit(1)

    dxf_path = Path(sys.argv[1])
    config_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    if not dxf_path.is_file():
        print(f"Error: DXF file not found: {dxf_path}", file=sys.stderr)
        sys.exit(1)
    if not config_path.is_file():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    layer_config = load_layer_config(config_path)

    # Set up warning collector
    inventory_logger = logging.getLogger("src.inventory")
    handler = _WarningCollector()
    handler.setLevel(logging.WARNING)
    inventory_logger.addHandler(handler)
    inventory_logger.setLevel(logging.WARNING)

    walls = extract_walls(dxf_path, layer_config)
    openings = extract_openings(dxf_path, layer_config)

    doors = [o for o in openings if o["category"] == "DOOR"]
    windows = [o for o in openings if o["category"] == "WINDOW"]

    result = {"walls": walls, "doors": doors, "windows": windows}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    summary_parts = [
        f"walls={len(walls)}",
        f"doors={len(doors)}",
        f"windows={len(windows)}",
    ]
    if handler.warnings:
        summary_parts.append(f"warnings={len(handler.warnings)}")
    print(", ".join(summary_parts))


if __name__ == "__main__":
    main()
