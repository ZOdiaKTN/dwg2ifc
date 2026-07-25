#!/usr/bin/env python3
"""Match openings to walls and assign height/sill defaults.

Usage::

    python scripts/detect_openings.py walls.json openings.json output.json
    python scripts/detect_openings.py walls.json openings.json output.json --config opening_defaults.yaml
    python scripts/detect_openings.py walls.json openings.json output.json --tolerance 90

Reads *walls.json* and *openings.json*, matches each opening to its
nearest aligned wall, assigns default height and sill per category, and
writes *output.json* with each wall's ``openings`` list populated.

Use ``--config`` to point to a YAML file that overrides the built-in
height/sill defaults (see ``data/opening_defaults.yaml``).

Use ``--tolerance`` to set the maximum allowed angle difference (degrees)
between an opening's rotation and the wall direction (default: 10).

Prints a summary: total openings, matched, flagged for review.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parse_dxf import match_opening_to_wall, compute_opening_position

logger = logging.getLogger(__name__)

DEFAULTS = {
    "DOOR": {"height_mm": 2100, "sill_mm": 0},
    "WINDOW": {"height_mm": 1200, "sill_mm": 900},
}


def load_config(config_path: str | Path | None = None) -> dict:
    """Return ``{category: {height_mm, sill_mm}, block_width_overrides: {}}``."""
    result = {
        "categories": {k: dict(v) for k, v in DEFAULTS.items()},
        "block_width_overrides": {},
    }

    if config_path is None:
        return result

    import yaml

    path = Path(config_path)
    if not path.exists():
        logger.warning("Config file not found: %s – using built-in defaults", path)
        return result

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        logger.warning("Invalid config format – using built-in defaults")
        return result

    for cat, vals in data.items():
        cat_upper = str(cat).upper()
        if cat_upper in ("BLOCK_WIDTH_OVERRIDES",):
            if isinstance(vals, dict):
                result["block_width_overrides"] = {
                    str(k): float(v) for k, v in vals.items()
                }
            continue
        if cat_upper not in result["categories"]:
            result["categories"][cat_upper] = {"height_mm": 2100, "sill_mm": 0}
        if isinstance(vals, dict):
            if "height_mm" in vals:
                result["categories"][cat_upper]["height_mm"] = float(vals["height_mm"])
            if "sill_mm" in vals:
                result["categories"][cat_upper]["sill_mm"] = float(vals["sill_mm"])

    return result


def apply_width_overrides(openings: list[dict], overrides: dict) -> list[dict]:
    """Replace ``estimated_width_mm`` for blocks listed in *overrides*."""
    if not overrides:
        return openings
    result = []
    for o in openings:
        block = o.get("block_name", "")
        if block in overrides:
            o = dict(o)
            o["estimated_width_mm"] = overrides[block]
        result.append(o)
    return result


def assign_height_sill(opening: dict, categories: dict) -> dict:
    """Return a copy of *opening* with ``height_mm`` and ``sill_mm`` set."""
    cat = opening.get("category", "DOOR")
    cat_defaults = categories.get(cat, categories.get("DOOR", {}))
    out = dict(opening)
    out.setdefault("height_mm", cat_defaults.get("height_mm", 2100))
    out.setdefault("sill_mm", cat_defaults.get("sill_mm", 0))
    return out


def _find_candidate_walls(
    opening: dict,
    walls: list[dict],
    tolerance_deg: float,
) -> list[dict]:
    """Return aligned walls sorted by distance to the opening (nearest first).

    Uses the same angle check as ``match_opening_to_wall`` but returns all
    candidates so the caller can try them in order.
    """
    import math

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

    candidates = []
    for wall in walls:
        v = wall["vertices"]
        dist = _point_to_segment_dist(ox, oy, v[0][0], v[0][1], v[-1][0], v[-1][1])
        angle_diff = _angle_diff_mod180(opening_angle, _wall_angle_deg(wall))
        if angle_diff <= tolerance_deg:
            candidates.append((dist, wall))

    candidates.sort(key=lambda x: x[0])
    return [w for _, w in candidates]


def detect(
    walls: list[dict],
    openings: list[dict],
    categories: dict,
    tolerance_deg: float = 10.0,
) -> tuple[list[dict], int, int]:
    """Match openings to walls and return the updated wall list.

    Each wall gains an ``openings`` key (list of enriched opening dicts).
    Tries aligned walls nearest-first; if the opening doesn't fit on the
    nearest wall, falls back to the next-nearest aligned wall.

    Returns ``(walls, matched_count, flagged_count)``.
    """
    wall_lookup = {w["id"]: w for w in walls}

    for w in walls:
        w.setdefault("openings", [])

    matched = 0
    flagged = 0

    for opening in openings:
        candidates = _find_candidate_walls(opening, walls, tolerance_deg)
        if not candidates:
            flagged += 1
            continue

        placed = False
        _parse_logger = logging.getLogger("src.parse_dxf")
        for wall in candidates:
            prev = _parse_logger.level
            _parse_logger.setLevel(logging.CRITICAL)
            pos = compute_opening_position(opening, wall)
            _parse_logger.setLevel(prev)
            if pos is not None:
                enriched = assign_height_sill(opening, categories)
                enriched["wall_id"] = wall["id"]
                enriched["position"] = pos
                matched += 1
                wall_lookup[wall["id"]]["openings"].append(enriched)
                placed = True
                break

        if not placed:
            flagged += 1

    return walls, matched, flagged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match openings to walls and assign height/sill defaults."
    )
    parser.add_argument("walls_json", help="Path to walls JSON file")
    parser.add_argument("openings_json", help="Path to openings JSON file")
    parser.add_argument("output_json", help="Path to output JSON file")
    parser.add_argument(
        "--config",
        default=None,
        help="YAML file with height/sill overrides and block width overrides",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=10.0,
        help="Max angle difference in degrees between opening rotation and wall (default: 10)",
    )
    args = parser.parse_args()

    walls_path = Path(args.walls_json)
    openings_path = Path(args.openings_json)
    output_path = Path(args.output_json)

    if not walls_path.is_file():
        print(f"Error: walls file not found: {walls_path}", file=sys.stderr)
        sys.exit(1)
    if not openings_path.is_file():
        print(f"Error: openings file not found: {openings_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(args.config)

    with open(walls_path, encoding="utf-8") as f:
        walls_data = json.load(f)
    with open(openings_path, encoding="utf-8") as f:
        openings_data = json.load(f)

    walls = walls_data.get("walls", walls_data) if isinstance(walls_data, dict) else walls_data
    openings = openings_data.get("openings", openings_data) if isinstance(openings_data, dict) else openings_data

    openings = apply_width_overrides(openings, config["block_width_overrides"])

    result_walls, matched, flagged = detect(
        walls, openings, config["categories"], tolerance_deg=args.tolerance
    )

    total = len(openings)
    output = {"walls": result_walls}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Total openings: {total}")
    print(f"Matched:        {matched}")
    print(f"Flagged:        {flagged}")


if __name__ == "__main__":
    main()
