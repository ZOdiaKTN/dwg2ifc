"""Tests for the parse_dxf CLI script."""

import ezdxf
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "src" / "parse_dxf.py"
DEFAULT_DXF = PROJECT_ROOT / "data" / "test1.dxf"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "layer_config.yaml"


def _run_parse_dxf(dxf_path, config_path, output_path):
    """Run parse_dxf.py as a subprocess and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(dxf_path), str(config_path), str(output_path)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _make_dxf(insunits=4, entities=None):
    """Create a minimal DXF and return the path to a temp file."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()

    for ent in (entities or []):
        etype = ent["type"]
        layer = ent.get("layer", "0")
        attribs = {"layer": layer}

        if etype == "LINE":
            msp.add_line(ent["start"], ent["end"], dxfattribs=attribs)
        elif etype == "LWPOLYLINE":
            msp.add_lwpolyline(
                ent["points"], dxfattribs=attribs, close=ent.get("closed", False)
            )
        elif etype == "INSERT":
            block_name = ent.get("block_name", "BLOCK1")
            if block_name not in [b.name for b in doc.blocks]:
                blk = doc.blocks.new(name=block_name)
                blk.add_line((0, 0), (100, 0))
            ref = msp.add_blockref(block_name, ent.get("insert", (0, 0)), dxfattribs=attribs)
            if "rotation" in ent:
                ref.dxf.rotation = ent["rotation"]

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        doc.saveas(tmp.name)
        return tmp.name


def _make_layer_config(layers, tmp_path):
    """Write a layer_config.yaml and return its path."""
    path = tmp_path / "layer_config.yaml"
    content = "layers:\n"
    for name, cat in layers.items():
        content += f"  {name}: {cat}\n"
    path.write_text(content, encoding="utf-8")
    return path


class TestParseDxfOutputFile:

    def test_creates_output_json(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (10, 0)},
            {"type": "INSERT", "layer": "A-DOOR", "block_name": "D", "insert": (5, 0)},
        ])
        cfg = _make_layer_config({"A-WALL": "WALL", "A-DOOR": "DOOR"}, tmp_path)
        out = tmp_path / "out.json"
        try:
            stdout, stderr, rc = _run_parse_dxf(dxf, cfg, out)
            assert rc == 0
            assert out.is_file()
            data = json.loads(out.read_text(encoding="utf-8"))
            assert "walls" in data
            assert "doors" in data
            assert "windows" in data
        finally:
            os.unlink(dxf)

    def test_walls_keys(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (10, 0)},
        ])
        cfg = _make_layer_config({"A-WALL": "WALL"}, tmp_path)
        out = tmp_path / "out.json"
        try:
            _run_parse_dxf(dxf, cfg, out)
            data = json.loads(out.read_text(encoding="utf-8"))
            assert len(data["walls"]) == 1
            assert set(data["walls"][0].keys()) == {"id", "vertices", "closed"}
        finally:
            os.unlink(dxf)

    def test_doors_windows_split(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "INSERT", "layer": "A-DOOR", "block_name": "D1", "insert": (0, 0)},
            {"type": "INSERT", "layer": "A-GLAZ", "block_name": "W1", "insert": (5, 0)},
        ])
        cfg = _make_layer_config(
            {"A-DOOR": "DOOR", "A-GLAZ": "WINDOW"}, tmp_path
        )
        out = tmp_path / "out.json"
        try:
            _run_parse_dxf(dxf, cfg, out)
            data = json.loads(out.read_text(encoding="utf-8"))
            assert len(data["doors"]) == 1
            assert data["doors"][0]["category"] == "DOOR"
            assert len(data["windows"]) == 1
            assert data["windows"][0]["category"] == "WINDOW"
        finally:
            os.unlink(dxf)

    def test_empty_dxf(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[])
        cfg = _make_layer_config({"A-WALL": "WALL"}, tmp_path)
        out = tmp_path / "out.json"
        try:
            _run_parse_dxf(dxf, cfg, out)
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data == {"walls": [], "doors": [], "windows": []}
        finally:
            os.unlink(dxf)

    def test_json_indented(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (1, 0)},
        ])
        cfg = _make_layer_config({"A-WALL": "WALL"}, tmp_path)
        out = tmp_path / "out.json"
        try:
            _run_parse_dxf(dxf, cfg, out)
            raw = out.read_text(encoding="utf-8")
            assert "\n" in raw
            assert "  " in raw
        finally:
            os.unlink(dxf)


class TestParseDxfSummaryLine:

    def test_summary_printed(self, tmp_path, capsys):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (10, 0)},
            {"type": "INSERT", "layer": "A-DOOR", "block_name": "D", "insert": (5, 0)},
        ])
        cfg = _make_layer_config({"A-WALL": "WALL", "A-DOOR": "DOOR"}, tmp_path)
        out = tmp_path / "out.json"
        try:
            stdout, _, rc = _run_parse_dxf(dxf, cfg, out)
            assert rc == 0
            assert "walls=" in stdout
            assert "doors=" in stdout
            assert "windows=" in stdout
        finally:
            os.unlink(dxf)

    def test_summary_counts_match_output(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (10, 0)},
            {"type": "LINE", "layer": "A-WALL", "start": (0, 1), "end": (10, 1)},
            {"type": "INSERT", "layer": "A-DOOR", "block_name": "D", "insert": (5, 0)},
            {"type": "INSERT", "layer": "A-GLAZ", "block_name": "W", "insert": (5, 1)},
        ])
        cfg = _make_layer_config(
            {"A-WALL": "WALL", "A-DOOR": "DOOR", "A-GLAZ": "WINDOW"}, tmp_path
        )
        out = tmp_path / "out.json"
        try:
            stdout, _, rc = _run_parse_dxf(dxf, cfg, out)
            data = json.loads(out.read_text(encoding="utf-8"))
            assert stdout == f"walls=2, doors=1, windows=1"
            assert len(data["walls"]) == 2
            assert len(data["doors"]) == 1
            assert len(data["windows"]) == 1
        finally:
            os.unlink(dxf)


class TestParseDxfWarnings:

    def test_warnings_count_in_summary(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (10, 0)},
            {"type": "INSERT", "layer": "A-WALL", "block_name": "X", "insert": (0, 0)},
        ])
        cfg = _make_layer_config({"A-WALL": "WALL"}, tmp_path)
        out = tmp_path / "out.json"
        try:
            stdout, _, rc = _run_parse_dxf(dxf, cfg, out)
            assert rc == 0
            assert "warnings=" in stdout
        finally:
            os.unlink(dxf)

    def test_no_warnings_when_clean(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (10, 0)},
        ])
        cfg = _make_layer_config({"A-WALL": "WALL"}, tmp_path)
        out = tmp_path / "out.json"
        try:
            stdout, _, rc = _run_parse_dxf(dxf, cfg, out)
            assert rc == 0
            assert "warnings=" not in stdout
        finally:
            os.unlink(dxf)


class TestParseDxfErrorHandling:

    def test_missing_args(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 1
        assert "Usage:" in result.stderr

    def test_too_few_args(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "foo.dxf"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 1
        assert "Usage:" in result.stderr

    def test_nonexistent_dxf(self, tmp_path):
        cfg = _make_layer_config({"A-WALL": "WALL"}, tmp_path)
        out = tmp_path / "out.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "nonexistent.dxf", str(cfg), str(out)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 1
        assert "DXF file not found" in result.stderr

    def test_nonexistent_config(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[])
        out = tmp_path / "out.json"
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(dxf), "nonexistent.yaml", str(out)],
                capture_output=True,
                text=True,
                cwd=str(PROJECT_ROOT),
            )
            assert result.returncode == 1
            assert "config file not found" in result.stderr
        finally:
            os.unlink(dxf)

    def test_creates_parent_dirs_for_output(self, tmp_path):
        dxf = _make_dxf(insunits=4, entities=[
            {"type": "LINE", "layer": "A-WALL", "start": (0, 0), "end": (5, 0)},
        ])
        cfg = _make_layer_config({"A-WALL": "WALL"}, tmp_path)
        out = tmp_path / "subdir" / "nested" / "out.json"
        try:
            stdout, stderr, rc = _run_parse_dxf(dxf, cfg, out)
            assert rc == 0
            assert out.is_file()
        finally:
            os.unlink(dxf)


class TestParseDxfRealFile:

    def test_runs_on_test_dxf(self, tmp_path):
        out = tmp_path / "out.json"
        stdout, stderr, rc = _run_parse_dxf(DEFAULT_DXF, DEFAULT_CONFIG, out)
        assert rc == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data["walls"], list)
        assert isinstance(data["doors"], list)
        assert isinstance(data["windows"], list)
        assert len(data["walls"]) > 0
