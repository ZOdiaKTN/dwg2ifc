"""Quick sanity check of extract_walls on the real DXF."""

from pathlib import Path
from typing import List, Dict, Any

from src.inventory import load_layer_config, extract_walls

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "layer_config.example.yaml"
DEFAULT_DXF = PROJECT_ROOT / "data" / "test1.dxf"


def check_walls(
    dxf_path: str | Path = DEFAULT_DXF,
    config_path: str | Path = DEFAULT_CONFIG,
) -> List[Dict[str, Any]]:
    """Extract walls and return the list (also prints a summary)."""
    cfg = load_layer_config(config_path)
    walls = extract_walls(dxf_path, cfg)

    print(f"Total walls extracted: {len(walls)}")
    print()
    for i, w in enumerate(walls):
        n = len(w["vertices"])
        xs = [v[0] for v in w["vertices"]]
        ys = [v[1] for v in w["vertices"]]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        print(
            f"Wall {i}: handle={w['id']}  closed={w['closed']}  pts={n}  "
            f"x=[{xmin:.1f}, {xmax:.1f}]  y=[{ymin:.1f}, {ymax:.1f}]"
        )
        if n <= 6:
            print(f"       vertices={w['vertices']}")

    return walls


if __name__ == "__main__":
    check_walls()
