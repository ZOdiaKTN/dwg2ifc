#!/usr/bin/env python3
"""Reconstruct walls from parsed.json: snap endpoints, find intersections,
build joints, and offset to footprints.

Usage::

    python scripts/reconstruct_walls.py parsed.json output.json --tolerance 10

All corrections (snap distances, joints built, unclosable walls) are
written to ``reconstruct_walls.log`` alongside the output file.
"""

import argparse
import json
import logging
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parse_dxf import snap_endpoints, find_intersections, build_joints, offset_to_footprint


def _wall_length(verts):
    v0, v1 = verts[0], verts[-1]
    return math.hypot(v1[0] - v0[0], v1[1] - v0[1])


def _setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("reconstruct_walls")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct walls from parsed JSON with snapping, "
                    "intersection detection, joint building, and footprint "
                    "offset.")
    parser.add_argument("input", help="Path to parsed.json")
    parser.add_argument("output", help="Path to write reconstructed output.json")
    parser.add_argument("--tolerance", type=float, default=10.0,
                        help="Snap tolerance in mm (default: 10)")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.parent / "reconstruct_walls.log"

    log = _setup_logger(log_path)
    log.info("=== reconstruct_walls started ===")
    log.info("input:  %s", in_path)
    log.info("output: %s", out_path)
    log.info("tolerance: %.2f mm", args.tolerance)

    data = json.loads(in_path.read_text(encoding="utf-8"))
    walls = data.get("walls", [])
    doors = data.get("doors", [])
    windows = data.get("windows", [])

    log.info("Loaded %d walls, %d doors, %d windows", len(walls), len(doors), len(windows))

    # ── Step 1: snap endpoints ────────────────────────────────────────────
    log.info("--- Step 1: snap_endpoints (tolerance=%.2f mm) ---", args.tolerance)
    snap_counts = {"pass1_groups": 0, "pass2_groups": 0, "total_points_moved": 0}

    orig_endpoints = {}
    for w in walls:
        for v in w["vertices"]:
            key = (round(v[0], 6), round(v[1], 6))
            orig_endpoints.setdefault(w["id"], []).append(key)

    walls_snapped = snap_endpoints(walls, tolerance_mm=args.tolerance)

    for w_old, w_new in zip(walls, walls_snapped):
        for v_old, v_new in zip(w_old["vertices"], w_new["vertices"]):
            dx = v_new[0] - v_old[0]
            dy = v_new[1] - v_old[1]
            dist = math.hypot(dx, dy)
            if dist > 0.001:
                snap_counts["total_points_moved"] += 1
                log.debug("  snap wall %s endpoint (%.3f,%.3f) -> (%.3f,%.3f)  dist=%.3f mm",
                          w_old["id"], v_old[0], v_old[1], v_new[0], v_new[1], dist)

    removed = len(walls) - len(walls_snapped)
    log.info("Snap pass complete: %d endpoints moved, %d degenerate walls removed",
             snap_counts["total_points_moved"], removed)

    walls = walls_snapped

    # ── Step 2: find intersections ────────────────────────────────────────
    log.info("--- Step 2: find_intersections ---")
    intersections = find_intersections(walls)
    type_counts = {}
    for inter in intersections:
        t = inter["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        log.debug("  intersection %s at (%.3f, %.3f) walls=%s",
                  t, inter["point"][0], inter["point"][1], inter["walls"])
    log.info("Found %d intersections: %s",
             len(intersections),
             ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items())))

    # ── Step 3: build joints ──────────────────────────────────────────────
    log.info("--- Step 3: build_joints ---")
    walls_before_joints = len(walls)
    walls_jointed = build_joints(walls, intersections)
    joints_built = len(walls_jointed) - walls_before_joints
    trimmed = sum(1 for w in walls_jointed if w.get("id", "").endswith(("_a", "_b")))

    for inter in intersections:
        if inter["type"] == "T":
            log.debug("  T-junction trimmed: walls=%s at (%.3f, %.3f)",
                      inter["walls"], inter["point"][0], inter["point"][1])
        elif inter["type"] == "X":
            log.debug("  X-junction split: walls=%s at (%.3f, %.3f)",
                      inter["walls"], inter["point"][0], inter["point"][1])

    log.info("Joint building complete: %d walls -> %d (splits created: %d)",
             walls_before_joints, len(walls_jointed), trimmed)
    walls = walls_jointed

    # ── Step 4: offset to footprints ──────────────────────────────────────
    log.info("--- Step 4: offset_to_footprint ---")
    footprints = []
    unclosable = []
    for w in walls:
        try:
            poly = offset_to_footprint(w)
            if poly.is_valid and not poly.is_empty:
                footprints.append({
                    "id": w["id"],
                    "vertices": w["vertices"],
                    "footprint": [list(c) for c in poly.exterior.coords],
                })
            else:
                unclosable.append(w["id"])
                log.warning("Wall %s produced invalid/empty footprint, kept centerline only", w["id"])
                footprints.append({
                    "id": w["id"],
                    "vertices": w["vertices"],
                    "footprint": None,
                })
        except Exception as exc:
            unclosable.append(w["id"])
            log.warning("Wall %s footprint failed (%s), kept centerline only", w["id"], exc)
            footprints.append({
                "id": w["id"],
                "vertices": w["vertices"],
                "footprint": None,
            })

    log.info("Footprint offset complete: %d OK, %d unclosable",
             len(footprints) - len(unclosable), len(unclosable))
    if unclosable:
        log.warning("Unclosable wall IDs: %s", ", ".join(unclosable))

    # ── Write output ──────────────────────────────────────────────────────
    result = {
        "walls": walls,
        "doors": doors,
        "windows": windows,
        "footprints": footprints,
    }
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    log.info("=== reconstruct_walls finished ===")
    log.info("Output written to %s", out_path)
    log.info("Log written to %s", log_path)

    # Also print a one-line summary to stdout.
    print(f"walls={len(walls)} doors={len(doors)} windows={len(windows)} "
          f"intersections={len(intersections)} footprints={len(footprints) - len(unclosable)} "
          f"unclosable={len(unclosable)}")


if __name__ == "__main__":
    main()
