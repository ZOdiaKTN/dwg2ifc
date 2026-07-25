"""DXF floor plan inventory module."""

import ezdxf
import logging
import yaml
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

INSUNITS_TO_MM = {
    0: 1.0,      # Unitless – treat as mm
    1: 25.4,     # Inches
    2: 304.8,    # Feet
    3: 1609344.0,# Miles
    4: 1.0,      # Millimeters
    5: 10.0,     # Centimeters
    6: 1000.0,   # Meters
    7: 25400.0,  # Kilometers  (not standard DXF but defensive)
    8: 0.0254,   # Microinches
    9: 254000.0, # Mil (thou)
    10: 914.4,   # Yards
    11: 100.0,   # Angstroms   (unlikely but defensive)
    12: 0.001,   # Nanometers
    13: 1e6,     # Microns
    14: 25400000.0,  # Decimeters
    15: 254000000.0, # Hectometers
    16: 25400000000.0, # Gigameters
    17: 25.4,    # AU (astronomical unit) – approximate
    18: 91440.0, # Light-years
    19: 149597870700000.0, # Parsecs
    20: 25.4,    # US Survey inches  (≈ same)
    21: 304.8006, # US Survey feet
    22: 914.4018, # US Survey yards
    23: 1609347.2, # US Survey miles
}

LINE_ENTITY_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE"}

VALID_CATEGORIES = {"WALL", "DOOR", "WINDOW", "IGNORE"}


def load_layer_config(yaml_path: str | Path) -> Dict[str, str]:
    """Load a YAML layer-to-category mapping and validate all categories.

    Expected format::

        layers:
          A-WALL: WALL
          A-DOOR: DOOR
          A-GLAZ: WINDOW

    Raises
    ------
    FileNotFoundError
        If *yaml_path* does not exist.
    ValueError
        If the YAML structure is invalid or any category is not one of
        WALL, DOOR, WINDOW, IGNORE.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "layers" not in data:
        raise ValueError("Config must contain a top-level 'layers' key")

    mapping = data["layers"]
    if not isinstance(mapping, dict):
        raise ValueError("'layers' must be a mapping of layer names to categories")

    bad: Dict[str, str] = {}
    for layer_name, category in mapping.items():
        if not isinstance(category, str) or category.upper() not in VALID_CATEGORIES:
            bad[layer_name] = str(category)

    if bad:
        details = ", ".join(f"{k}={v!r}" for k, v in bad.items())
        raise ValueError(
            f"Invalid category values: {details}. "
            f"Allowed categories: {sorted(VALID_CATEGORIES)}"
        )

    return {k: v.upper() for k, v in mapping.items()}


def inventory_layers(dxf_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load a DXF file and return layer inventory with entity counts and type breakdowns.
    
    Args:
        dxf_path: Path to the DXF file
        
    Returns:
        Dictionary with layer names as keys, containing:
            - 'total_count': Total number of entities on that layer
            - 'types': Dictionary of {entity_type: count}
        Also prints the $INSUNITS header value.
    """
    # Load the DXF file
    doc = ezdxf.readfile(dxf_path)
    
    # Print the INSUNITS header value
    insunits = doc.header.get('$INSUNITS', 'Not found')
    print(f"DXF Header $INSUNITS: {insunits}")
    
    # Initialize inventory
    inventory = defaultdict(lambda: {'total_count': 0, 'types': defaultdict(int)})
    
    # Iterate through all entities in the modelspace
    msp = doc.modelspace()
    
    for entity in msp:
        layer = entity.dxf.layer
        entity_type = entity.dxftype()
        
        inventory[layer]['total_count'] += 1
        inventory[layer]['types'][entity_type] += 1
    
    # Convert defaultdict to regular dict and types from defaultdict to dict
    final_inventory = {}
    for layer, data in inventory.items():
        final_inventory[layer] = {
            'total_count': data['total_count'],
            'types': dict(data['types'])
        }
    
    return final_inventory


def print_inventory(inventory: Dict[str, Dict[str, Any]]) -> None:
    """Pretty print the inventory dictionary."""
    print("\n" + "="*60)
    print("LAYER INVENTORY")
    print("="*60)
    
    for layer, data in sorted(inventory.items()):
        print(f"\nLayer: {layer}")
        print(f"  Total entities: {data['total_count']}")
        print("  Entity types:")
        for etype, count in sorted(data['types'].items()):
            print(f"    {etype}: {count}")


def _get_insunits_scale(doc) -> float:
    """Return a multiplication factor that converts DXF units to millimetres."""
    raw = doc.header.get("$INSUNITS", 0)
    try:
        units = int(raw)
    except (TypeError, ValueError):
        units = 0
    return INSUNITS_TO_MM.get(units, 1.0)


def _scale_xy(xy: Tuple[float, float], factor: float) -> Tuple[float, float]:
    return (round(xy[0] * factor, 6), round(xy[1] * factor, 6))


def _extract_line_points(entity) -> List[Tuple[float, float]]:
    """Return [(x, y), ...] for a LINE entity."""
    s = entity.dxf.start
    e = entity.dxf.end
    return [(s.x, s.y), (e.x, e.y)]


def _extract_lwpolyline_points(entity) -> List[Tuple[float, float]]:
    """Return [(x, y), ...] for an LWPOLYLINE entity."""
    return [(p[0], p[1]) for p in entity.get_points(format="xy")]


def _extract_polyline_points(entity) -> List[Tuple[float, float]]:
    """Return [(x, y), ...] for a 2D POLYLINE entity."""
    return [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]


def extract_openings(
    dxf_path: str | Path,
    layer_config: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Return one opening dict per INSERT on a DOOR or WINDOW layer.

    Parameters
    ----------
    dxf_path : path to a DXF file.
    layer_config : mapping ``{layer_name: category}``
        as returned by :func:`load_layer_config`.

    Returns
    -------
    list of dict
        Each dict has keys ``id`` (str, DXF handle), ``category`` (str,
        ``"DOOR"`` or ``"WINDOW"``), ``insertion_point`` (tuple ``(x, y)`` in
        **millimetres**), ``rotation_deg`` (float, rotation angle in
        degrees), ``block_name`` (str), and ``estimated_width_mm`` (float,
        block bounding-box width in mm).
    """
    doc = ezdxf.readfile(str(dxf_path))
    scale = _get_insunits_scale(doc)

    opening_layers = {
        name: cat
        for name, cat in layer_config.items()
        if cat in ("DOOR", "WINDOW")
    }

    msp = doc.modelspace()
    openings: List[Dict[str, Any]] = []

    for entity in msp:
        layer = entity.dxf.layer
        if layer not in opening_layers:
            continue
        if entity.dxftype() != "INSERT":
            logger.warning(
                "Skipping non-INSERT entity %s (handle=%s) on %s layer '%s'",
                entity.dxftype(), entity.dxf.handle, opening_layers[layer], layer,
            )
            continue

        block_name = entity.dxf.name
        insert_xy = entity.dxf.insert
        x_mm = round(insert_xy.x * scale, 6)
        y_mm = round(insert_xy.y * scale, 6)

        rotation = getattr(entity.dxf, "rotation", 0.0)

        estimated_width_mm = 0.0
        if block_name in doc.blocks:
            block_def = doc.blocks[block_name]
            xs, ys = [], []
            for e in block_def:
                etype = e.dxftype()
                if etype == "LINE":
                    xs.extend([e.dxf.start.x, e.dxf.end.x])
                    ys.extend([e.dxf.start.y, e.dxf.end.y])
                elif etype == "LWPOLYLINE":
                    for p in e.get_points(format="xy"):
                        xs.append(p[0])
                        ys.append(p[1])
                elif etype == "ARC":
                    import math
                    cx, cy = e.dxf.center.x, e.dxf.center.y
                    r = e.dxf.radius
                    start_rad = math.radians(e.dxf.start_angle)
                    end_rad = math.radians(e.dxf.end_angle)
                    xs.extend([cx + r * math.cos(a) for a in [start_rad, end_rad]])
                    ys.extend([cy + r * math.sin(a) for a in [start_rad, end_rad]])
                elif etype == "CIRCLE":
                    cx, cy = e.dxf.center.x, e.dxf.center.y
                    r = e.dxf.radius
                    xs.extend([cx - r, cx + r])
                    ys.extend([cy - r, cy + r])
            if xs and ys:
                estimated_width_mm = round((max(xs) - min(xs)) * scale, 6)

        openings.append(
            {
                "id": entity.dxf.handle,
                "category": opening_layers[layer],
                "insertion_point": (x_mm, y_mm),
                "rotation_deg": rotation,
                "block_name": block_name,
                "estimated_width_mm": estimated_width_mm,
            }
        )

    return openings


def extract_walls(
    dxf_path: str | Path,
    layer_config: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Return one wall dict per line-type entity on a WALL layer.

    Parameters
    ----------
    dxf_path : path to a DXF file.
    layer_config : mapping ``{layer_name: category}``
        as returned by :func:`load_layer_config`.

    Returns
    -------
    list of dict
        Each dict has keys ``id`` (str, DXF handle), ``vertices``
        (list of ``(x, y)`` tuples in **millimetres**), and ``closed``
        (bool).

    Entities on a WALL layer that are *not* LINE / LWPOLYLINE / POLYLINE
    are logged at warning level and silently skipped.
    """
    doc = ezdxf.readfile(str(dxf_path))
    scale = _get_insunits_scale(doc)

    # Build the set of layer names whose category is WALL.
    wall_layers = {name for name, cat in layer_config.items() if cat == "WALL"}

    msp = doc.modelspace()
    walls: List[Dict[str, Any]] = []

    for entity in msp:
        layer = entity.dxf.layer
        if layer not in wall_layers:
            continue

        etype = entity.dxftype()

        if etype not in LINE_ENTITY_TYPES:
            logger.warning(
                "Skipping unsupported entity %s (handle=%s) on WALL layer '%s'",
                etype,
                entity.dxf.handle,
                layer,
            )
            continue

        if etype == "LINE":
            pts = _extract_line_points(entity)
            closed = False
        elif etype == "LWPOLYLINE":
            pts = _extract_lwpolyline_points(entity)
            closed = entity.closed
        elif etype == "POLYLINE":
            pts = _extract_polyline_points(entity)
            closed = entity.is_closed
        else:
            # Unreachable given the filter above, but be safe.
            continue

        scaled = [_scale_xy(p, scale) for p in pts]

        walls.append(
            {
                "id": entity.dxf.handle,
                "vertices": scaled,
                "closed": closed,
            }
        )

    return walls


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <path_to_dxf>")
        sys.exit(1)

    dxf_path = sys.argv[1]
    inventory = inventory_layers(dxf_path)
    print_inventory(inventory)