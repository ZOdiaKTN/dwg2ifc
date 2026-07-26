#!/usr/bin/env python3
"""Generate an IFC file from a walls_with_openings JSON.

Usage::

    python src/generate_ifc.py walls_with_openings.json output.ifc --floor-height 2700

The JSON must contain keys ``walls`` (list of wall dicts with ``vertices``,
``thickness``, and optional ``openings``) and optionally ``doors``/``windows``.

A geometry-iterator sanity check runs at the end and prints a pass/fail summary.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import ifcopenshell
import ifcopenshell.geom

from src.ifc_skeleton import (
    MM_TO_M,
    create_ifc_skeleton,
    create_wall,
    create_opening_in_wall,
    create_space,
    find_room_loops,
    _wall_centerline,
    _wall_extrusion_info,
    fix_profile_winding_order,
)

OPENING_DEFAULTS = {
    "DOOR":   {"height_mm": 2100.0, "sill_mm": 0.0},
    "WINDOW": {"height_mm": 1200.0, "sill_mm": 900.0},
}

DEFAULT_THICKNESS_MM = 200.0


def _build_ifc(data: dict, floor_height_mm: float, output_path: str) -> str:
    """Core IFC generation from the parsed JSON dict."""
    walls = data.get("walls", [])
    doors = data.get("doors", [])
    windows = data.get("windows", [])

    # 1. Create skeleton.
    create_ifc_skeleton(floor_height_mm=floor_height_mm, output_path=output_path)

    # 2. Re-open, populate, and save.
    model = ifcopenshell.open(output_path)
    storey = model.by_type("IfcBuildingStorey")[0]

    # ── Walls ──────────────────────────────────────────────────────────
    wall_entities: dict[str, ifcopenshell.entity_instance] = {}
    for w in walls:
        verts = w["vertices"]
        if len(verts) < 2:
            continue
        p1 = tuple(verts[0])
        p2 = tuple(verts[-1])
        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 1e-6:
            continue
        thickness = w.get("thickness", DEFAULT_THICKNESS_MM)
        eid = w.get("id", "")
        wall_entity = create_wall(
            model, storey,
            p1_mm=p1, p2_mm=p2,
            thickness_mm=thickness, height_mm=floor_height_mm,
            wall_id=eid,
        )
        wall_entities[eid] = wall_entity

    # ── Openings already embedded in walls ─────────────────────────────
    # Some JSON formats embed openings inside each wall dict.
    for w in walls:
        eid = w.get("id", "")
        wall_entity = wall_entities.get(eid)
        if wall_entity is None:
            continue
        for op in w.get("openings", []):
            cat = op.get("category", "DOOR")
            defaults = OPENING_DEFAULTS.get(cat, OPENING_DEFAULTS["DOOR"])
            width = op.get("estimated_width_mm", 1000.0)
            height = op.get("height_mm", defaults["height_mm"])
            sill = op.get("sill_mm", defaults["sill_mm"])
            oid = op.get("id", "")

            # Compute center_along_mm from insertion_point if available.
            center_along_mm = None
            ip = op.get("insertion_point")
            if ip is not None:
                try:
                    p1_mm, p2_mm = _wall_centerline(wall_entity)
                    wl = math.hypot(p2_mm[0] - p1_mm[0], p2_mm[1] - p1_mm[1])
                    if wl >= 1e-6:
                        dx, dy = p2_mm[0] - p1_mm[0], p2_mm[1] - p1_mm[1]
                        t = ((ip[0] - p1_mm[0]) * dx + (ip[1] - p1_mm[1]) * dy) / (wl * wl)
                        center_along_mm = max(0.0, min(wl, t * wl))
                except Exception:
                    pass

            create_opening_in_wall(
                model, wall_entity,
                opening_width_mm=width, opening_height_mm=height,
                sill_height_mm=sill, center_along_mm=center_along_mm,
                opening_id=oid,
            )

    # ── Standalone openings (doors/windows not yet linked) ─────────────
    unlinked = [o for o in (doors + windows) if o.get("wall_id") is None]
    if unlinked:
        all_walls_list = list(model.by_type("IfcWall"))
        for op in unlinked:
            cat = op.get("category", "DOOR")
            defaults = OPENING_DEFAULTS.get(cat, OPENING_DEFAULTS["DOOR"])
            width = op.get("estimated_width_mm", 1000.0)
            height = op.get("height_mm", defaults["height_mm"])
            sill = op.get("sill_mm", defaults["sill_mm"])
            oid = op.get("id", "")

            ip = op.get("insertion_point")
            if ip is None or not all_walls_list:
                continue

            best_wall = None
            best_dist = float("inf")
            best_center_along = 0.0

            for we in all_walls_list:
                try:
                    p1_mm, p2_mm = _wall_centerline(we)
                    wl = math.hypot(p2_mm[0] - p1_mm[0], p2_mm[1] - p1_mm[1])
                    if wl < 1e-6:
                        continue
                    dx, dy = p2_mm[0] - p1_mm[0], p2_mm[1] - p1_mm[1]
                    t = ((ip[0] - p1_mm[0]) * dx + (ip[1] - p1_mm[1]) * dy) / (wl * wl)
                    proj_x = p1_mm[0] + t * dx
                    proj_y = p1_mm[1] + t * dy
                    d = math.hypot(ip[0] - proj_x, ip[1] - proj_y)
                    if d < best_dist:
                        best_dist = d
                        best_wall = we
                        best_center_along = max(0.0, min(wl, t * wl))
                except Exception:
                    continue

            if best_wall is not None and best_dist < 5000:
                _compute_and_create_opening(
                    model, best_wall, op, width, height, sill, oid,
                    center_along_mm=best_center_along,
                )

    # ── Room loop detection & IfcSpace generation ──────────────────────
    loops = find_room_loops(walls)
    for idx, loop in enumerate(loops):
        create_space(
            model, storey,
            polygon_mm=loop,
            floor_height_mm=floor_height_mm,
            space_name=f"Room {idx + 1}",
        )

    # ── Final storey check: verify every IfcProduct is in the storey ──
    contained = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        if rel.RelatingStructure == storey:
            for e in rel.RelatedElements:
                contained.add(e.id())

    assigned = len(contained)
    total_products = len(model.by_type("IfcWall")) + len(model.by_type("IfcDoor")) + \
                     len(model.by_type("IfcOpeningElement")) + len(model.by_type("IfcSpace"))

    # ── Fix profile winding order (IFC requires CCW for outer boundaries) ──
    fix_profile_winding_order(model)

    model.write(output_path)
    return output_path, assigned, total_products, len(loops)


def _compute_and_create_opening(model, wall_entity, op, width, height, sill, oid, center_along_mm=None):
    """Create the opening on the wall at the given center_along_mm."""
    if center_along_mm is not None:
        create_opening_in_wall(
            model, wall_entity,
            opening_width_mm=width, opening_height_mm=height,
            sill_height_mm=sill, center_along_mm=center_along_mm,
            opening_id=oid,
        )
    else:
        create_opening_in_wall(
            model, wall_entity,
            opening_width_mm=width, opening_height_mm=height,
            sill_height_mm=sill, opening_id=oid,
        )


def _sanity_check(ifc_path: str) -> dict:
    """Run ifcopenshell's geometry iterator and return a summary dict."""
    settings = ifcopenshell.geom.settings()
    model = ifcopenshell.open(ifc_path)

    walls = model.by_type("IfcWall")
    doors = model.by_type("IfcDoor")
    openings = model.by_type("IfcOpeningElement")
    spaces = model.by_type("IfcSpace")
    storeys = model.by_type("IfcBuildingStorey")

    # Check storey containment.
    storey_set = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        for e in rel.RelatedElements:
            storey_set.add((e.is_a(), e.id()))
    # IfcSpace uses aggregation, not containment.
    for rel in model.by_type("IfcRelAggregates"):
        if rel.RelatingObject.is_a("IfcBuildingStorey"):
            for e in rel.RelatedObjects:
                storey_set.add((e.is_a(), e.id()))

    all_products = walls + doors + openings + spaces
    missing = []
    for p in all_products:
        if (p.is_a(), p.id()) not in storey_set:
            missing.append(f"{p.is_a()}#{p.Name}")

    # Geometry check per entity (iterate() is unreliable with CGAL backend).
    iter_results = []
    ok_items = []
    fail_items = []
    for p in all_products:
        try:
            shape = ifcopenshell.geom.create_shape(settings, p)
            if shape is not None and shape.geometry is not None and len(shape.geometry.verts) > 0:
                ok_items.append(p)
            else:
                fail_items.append(p)
        except Exception:
            fail_items.append(p)

    # Volume sanity check on walls.
    volume_issues = []
    try:
        import numpy as np
        for w in walls:
            shape = ifcopenshell.geom.create_shape(settings, w)
            if shape is None or len(shape.geometry.verts) == 0:
                continue
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            faces = np.array(shape.geometry.faces).reshape(-1, 3)
            vol = 0.0
            for tri in faces:
                v0, v1, v2 = verts[tri[0]], verts[tri[1]], verts[tri[2]]
                vol += np.dot(v0, np.cross(v1, v2)) / 6.0
            vol = abs(vol)
            if vol < 0.01:
                volume_issues.append(f"Wall #{w.Name} volume={vol:.6f} m³ (near zero)")
    except Exception:
        pass

    total = len(all_products)
    ok_count = len(ok_items)
    fail_count = len(fail_items)

    return {
        "total_products": total,
        "walls": len(walls),
        "doors": len(doors),
        "openings": len(openings),
        "spaces": len(spaces),
        "storeys": len(storeys),
        "storey_mismatches": missing,
        "geometry_ok": ok_count,
        "geometry_fail": fail_count,
        "geometry_total": total,
        "volume_issues": volume_issues,
    }


def _print_summary(result: dict) -> None:
    """Print a human-readable pass/fail summary."""
    print("=" * 60)
    print("  IFC GENERATION & SANITY CHECK SUMMARY")
    print("=" * 60)
    print(f"  Walls:           {result['walls']}")
    print(f"  Doors:           {result['doors']}")
    print(f"  Openings:        {result['openings']}")
    print(f"  Spaces (rooms):  {result['spaces']}")
    print(f"  Storeys:         {result['storeys']}")
    print(f"  Total products:  {result['total_products']}")
    print()

    # Storey containment.
    if result["storey_mismatches"]:
        print(f"  STOREY CONTAINMENT:  FAIL ({len(result['storey_mismatches'])} mismatched)")
        for m in result["storey_mismatches"][:10]:
            print(f"    - {m}")
    else:
        print("  STOREY CONTAINMENT:  PASS")

    # Geometry iterator.
    g_ok = result["geometry_ok"]
    g_fail = result["geometry_fail"]
    g_total = result["geometry_total"]
    if g_fail == 0 and g_total > 0:
        print(f"  GEOMETRY ITERATOR:   PASS ({g_ok}/{g_total} valid)")
    elif g_total == 0:
        print("  GEOMETRY ITERATOR:   SKIP (no products with geometry)")
    else:
        print(f"  GEOMETRY ITERATOR:   FAIL ({g_fail}/{g_total} failed)")

    # Volume sanity.
    if result["volume_issues"]:
        print(f"  VOLUME CHECK:        FAIL ({len(result['volume_issues'])} issues)")
        for v in result["volume_issues"][:5]:
            print(f"    - {v}")
    else:
        print("  VOLUME CHECK:        PASS")

    # Overall.
    all_pass = (
        not result["storey_mismatches"]
        and g_fail == 0
        and g_total > 0
        and not result["volume_issues"]
    )
    print()
    if all_pass:
        print("  OVERALL:  PASS")
    else:
        print("  OVERALL:  FAIL")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an IFC file from walls_with_openings JSON.",
    )
    parser.add_argument("input", help="Path to walls_with_openings.json")
    parser.add_argument("output", help="Path to write the output .ifc file")
    parser.add_argument(
        "--floor-height", type=float, default=2700.0,
        help="Floor height in mm (default: 2700)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))

    t0 = time.time()
    path, assigned, total_products, num_loops = _build_ifc(
        data, args.floor_height, args.output,
    )
    elapsed = time.time() - t0

    print(f"IFC written to {path} ({elapsed:.1f}s)")
    print(f"  Storey containment: {assigned}/{total_products} products assigned")
    print(f"  Room loops detected: {num_loops}")

    # Run sanity check.
    print()
    result = _sanity_check(path)
    _print_summary(result)


if __name__ == "__main__":
    main()
