# dwg2ifc

Convert a 2D architectural DWG floor plan into a clean IFC file ready for import
into [DIALux EVO](https://www.dialux.com/) — automating the manual wall/window/door
modeling step of lighting-design projects.

> **Status: MVP / work in progress.** Single-storey, orthogonal-wall floor plans only.
> Accuracy target is 95%+ on wall length and opening placement vs. the source DWG,
> measured automatically (see [Validation](#validation)) — not yet reached on
> real-world files, see [Roadmap](#roadmap).

## Why

DIALux EVO has no scripting API, but it does have a robust IFC importer that reads
real semantic `IfcWall` / `IfcWindow` / `IfcDoor` / `IfcSpace` objects — including
automatically computed wall openings — rather than flat CAD geometry. This project
automates the DWG → IFC conversion so that floor plan modeling in DIALux becomes a
one-click import instead of hours of manual wall/window/door placement.

```
DWG → DXF → parse & classify → reconstruct walls → detect openings
    → generate IFC → validate accuracy → import into DIALux EVO
```

## Pipeline

| Module | Script | Does |
|---|---|---|
| 1. Parse | `src/parse_dxf.py` | Reads DXF, classifies entities into walls/doors/windows by layer |
| 2. Reconstruct | `src/reconstruct_walls.py` | Snaps endpoints, builds intersections/butt-joints, detects rooms |
| 3. Openings | `src/detect_openings.py` | Matches doors/windows to walls, computes opening position/size |
| 4. Generate | `src/generate_ifc.py` | Builds a valid IFC2x3 file with walls, voided openings, spaces |
| 5. Validate | `src/validate_conversion.py` | Scores conversion accuracy against the source DXF, renders a visual diff |

Each module reads/writes JSON so they can be run and tested independently.
See [`SCHEMA.md`](SCHEMA.md) for the exact data shape passed between them.

## Requirements

- Python 3.10+
- [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) (free) — to convert source `.dwg` files to `.dxf`
- DIALux EVO (for the actual lighting design import step)

```bash
pip install -r requirements.txt
```

## Quick start

```bash
# 1. Convert your DWG to DXF using ODA File Converter (outside this tool)

# 2. Set up layer mapping
cp config/layer_config.example.yaml config/layer_config.yaml
# Edit layer_config.yaml for your CAD conventions

# 3. Run the pipeline
python src/parse_dxf.py data/test1.dxf config/layer_config.yaml data/parsed.json
python src/reconstruct_walls.py data/parsed.json data/walls.json --tolerance 10
python src/detect_openings.py data/walls.json -o data/ -c config/openings_default.yaml
python src/generate_ifc.py data/output.json data/final.ifc --floor-height 2700

# 4. Check accuracy before trusting the output
python src/validate_conversion.py data/parsed.json output/model.ifc data/report.json --threshold 95
```

Import `output/model.ifc` into DIALux EVO via **File → Import → BIM (IFC)**.

## Configuration

Layer names vary by CAD office. Map yours in `config/layer_config.yaml`:

```yaml
layers:
  A-WALL: WALL
  A-DOOR: DOOR
  A-GLAZ: WINDOW
```

Opening defaults (overridable in the same config):

| Category | Height | Sill height |
|---|---|---|
| Door | 2100 mm | 0 mm |
| Window | 1200 mm | 900 mm |

## Validation

Every conversion produces a `report.json` with:
- per-wall length/thickness delta (mm) vs. source DXF
- per-opening match status (position/width within tolerance)
- an overall accuracy score
- `comparison.png` — source outline (blue) overlaid with converted outline (red)

The pipeline exits non-zero if the score falls below `--threshold` (default 95),
so it can gate a CI/automation step.

## Known limitations (MVP)

- Single storey only
- Orthogonal / near-orthogonal walls only (curved and angled walls not yet handled)
- Furniture and luminaire placement not yet included (planned — see Roadmap)
- Layer-mapping config must be set per CAD office convention; no auto-detection yet

## Roadmap

- [ ] Multi-storey support
- [ ] Angled and curved wall support
- [ ] Furniture (`IfcFurnishingElement`) and luminaire (`IfcLightFixture`) placement
- [ ] Automatic layer-name detection/suggestion instead of manual config
- [ ] CI pipeline running validation against a small regression set of real floor plans

## Project structure

```
dwg2ifc/
├── src/
│   ├── parse_dxf.py
│   ├── reconstruct_walls.py
│   ├── detect_openings.py
│   ├── generate_ifc.py
│   └── validate_conversion.py
├── tests/
├── config/
│   └── layer_config.example.yaml
├── data/            # sample/test DXF + JSON (gitignored except examples)
├── output/          # generated IFC + reports (gitignored)
├── SCHEMA.md         # data contract between modules
├── requirements.txt
└── README.md
```

## Contributing

This is an early-stage MVP built incrementally, module by module, with each
module unit-tested before the next is built on top of it. PRs should include a
passing pytest for any new behavior — geometry bugs here are usually silent
(subtly wrong coordinates, not crashes), so test coverage matters more than usual.

## License

_Add your chosen license here (MIT recommended for an open tool like this)._
