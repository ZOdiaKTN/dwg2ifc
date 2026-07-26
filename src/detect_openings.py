#!/usr/bin/env python3
"""Match openings to walls and assign default height/sill values.

Reads ``walls.json`` (output of ``reconstruct_walls.py``) which contains
``walls``, ``doors``, and ``windows`` arrays.  Each opening is matched to
its nearest wall and assigned a default height and sill height from the
YAML override file (``config/openings_default.yaml``).

Outputs
-------
* ``openings.json`` – enriched opening list with ``height_mm``, ``sill_mm``,
  ``wall_id``, and ``position`` fields.
* ``output.json`` – walls list with an ``openings`` array attached to each
  wall that contains one or more matched openings.

Prints a summary: total openings, matched, flagged for review.
"""

import argparse
import json
import logging
import math
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parse_dxf import match_opening_to_wall, compute_opening_position

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "openings_default.yaml"
DEFAULT_ANGLE_TOL = 10.0


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("detect_openings")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)-7s  %(message)s"))
        logger.addHandler(handler)
    return logger


def load_opening_defaults(yaml_path: str | Path) -> dict:
    """Return ``{category: {"height_mm": …, "sill_mm": …}}`` from YAML."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Opening defaults config not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    categories = data.get("categories", {})
    result: dict[str, dict[str, float]] = {}
    for cat, vals in categories.items():
        key = cat.upper()
        result[key] = {
            "height_mm": float(vals.get("height_mm", 0)),
            "sill_mm": float(vals.get("sill_mm", 0)),
        }
    return result


def detect_openings(
    walls: list[dict],
    doors: list[dict],
    windows: list[dict],
    defaults: dict,
    angle_tolerance_deg: float = DEFAULT_ANGLE_TOL,
    log: logging.Logger | None = None,
) -> tuple[list[dict], list[dict], int, int]:
    """Match openings to walls and enrich with height/sill.

    Returns
    -------
    enriched_openings : list[dict]
        All openings with added ``height_mm``, ``sill_mm``, ``wall_id``,
        and ``position`` keys.
    walls_out : list[dict]
        Deep copy of *walls* with an ``openings`` list attached to each wall.
    matched_count : int
        Number of openings successfully matched to a wall.
    flagged_count : int
        Number of openings that could not be matched or placed.
    """
    if log is None:
        log = logging.getLogger("detect_openings")

    all_openings = doors + windows
    enriched: list[dict] = []
    matched = 0
    flagged = 0

    # Attach an empty openings list to every wall.
    walls_out = []
    openings_by_wall: dict[str, list[dict]] = {}
    for w in walls:
        wall_copy = {**w, "vertices": [list(v) for v in w["vertices"]], "openings": []}
        walls_out.append(wall_copy)
        openings_by_wall[w["id"]] = wall_copy["openings"]

    # Per-wall tracker for overlap detection.
    placed_by_wall: dict[str, list[dict]] = {}

    for opening in all_openings:
        cat = opening["category"]
        defaults_for_cat = defaults.get(cat, {"height_mm": 0, "sill_mm": 0})

        enriched_opening = {
            **opening,
            "height_mm": defaults_for_cat["height_mm"],
            "sill_mm": defaults_for_cat["sill_mm"],
            "wall_id": None,
            "position": None,
        }

        wall = match_opening_to_wall(opening, walls, angle_tolerance_deg)
        if wall is None:
            enriched_opening["flagged_reason"] = "no_matching_wall"
            enriched.append(enriched_opening)
            flagged += 1
            log.warning(
                "Opening %s (%s) – no matching wall found, flagged for review",
                opening["id"], cat,
            )
            continue

        placed = placed_by_wall.get(wall["id"], [])
        pos = compute_opening_position(opening, wall, placed_openings=placed)
        if pos is None:
            enriched_opening["flagged_reason"] = "position_invalid"
            enriched_opening["wall_id"] = wall["id"]
            enriched.append(enriched_opening)
            flagged += 1
            log.warning(
                "Opening %s (%s) – invalid position on wall %s, flagged for review",
                opening["id"], cat, wall["id"],
            )
            continue

        enriched_opening["wall_id"] = wall["id"]
        enriched_opening["position"] = pos
        placed.append({**pos, "id": opening["id"]})
        placed_by_wall.setdefault(wall["id"], placed)

        # Attach to the wall's openings list.
        openings_by_wall[wall["id"]].append(enriched_opening)

        enriched.append(enriched_opening)
        matched += 1
        log.debug(
            "Opening %s (%s) matched to wall %s  start=%.0f end=%.0f",
            opening["id"], cat, wall["id"],
            pos["start"], pos["end"],
        )

    return enriched, walls_out, matched, flagged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match openings to walls and assign default height/sill.",
    )
    parser.add_argument(
        "walls_json",
        help="Path to walls.json (output of reconstruct_walls.py)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directory for openings.json and output.json (default: same dir as walls_json)",
    )
    parser.add_argument(
        "-c", "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to openings_default.yaml (default: config/openings_default.yaml)",
    )
    parser.add_argument(
        "--angle-tolerance",
        type=float,
        default=DEFAULT_ANGLE_TOL,
        help="Angle tolerance in degrees for wall matching (default: 10)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    log = _setup_logging(args.verbose)

    walls_path = Path(args.walls_json)
    if not walls_path.is_file():
        print(f"Error: walls JSON not found: {walls_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else walls_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load data.
    data = json.loads(walls_path.read_text(encoding="utf-8"))
    walls = data.get("walls", [])
    doors = data.get("doors", [])
    windows = data.get("windows", [])

    log.info("Loaded %d walls, %d doors, %d windows", len(walls), len(doors), len(windows))

    # Load defaults.
    defaults = load_opening_defaults(args.config)
    log.info("Opening defaults: %s", defaults)

    # Run detection.
    enriched, walls_out, matched, flagged = detect_openings(
        walls, doors, windows, defaults,
        angle_tolerance_deg=args.angle_tolerance,
        log=log,
    )

    total = len(enriched)

    # Write openings.json.
    openings_path = out_dir / "openings.json"
    openings_path.write_text(json.dumps(enriched, indent=2), encoding="utf-8")

    # Write output.json (walls with openings attached).
    output_path = out_dir / "output.json"
    output_data = {
        "walls": walls_out,
        "doors": doors,
        "windows": windows,
    }
    output_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")

    # Summary.
    print(
        f"total_openings={total}  matched={matched}  flagged_for_review={flagged}  "
        f"walls={len(walls_out)}"
    )


if __name__ == "__main__":
    main()
