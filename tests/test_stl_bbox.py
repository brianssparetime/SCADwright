"""Tests for the internal STL bbox parser."""

import struct

import pytest

from scadwright._stl import stl_bbox


def _make_binary_stl(path, triangles):
    """Write a minimal binary STL with the given triangle list.

    Each triangle is (normal, [v1, v2, v3]) where each vertex is (x, y, z).
    """
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(triangles)))
        for normal, (v1, v2, v3) in triangles:
            f.write(struct.pack("<fff", *normal))
            f.write(struct.pack("<fff", *v1))
            f.write(struct.pack("<fff", *v2))
            f.write(struct.pack("<fff", *v3))
            f.write(b"\x00\x00")


def _make_ascii_stl(path, triangles):
    lines = ["solid test\n"]
    for normal, (v1, v2, v3) in triangles:
        lines.append(f"  facet normal {normal[0]} {normal[1]} {normal[2]}\n")
        lines.append("    outer loop\n")
        for v in (v1, v2, v3):
            lines.append(f"      vertex {v[0]} {v[1]} {v[2]}\n")
        lines.append("    endloop\n")
        lines.append("  endfacet\n")
    lines.append("endsolid test\n")
    path.write_text("".join(lines))


def test_binary_stl_bbox(tmp_path):
    stl_bbox.cache_clear()
    path = tmp_path / "cube_corner.stl"
    # A single triangle spanning [0,10] in each axis.
    tris = [((0, 0, 1), [(0, 0, 0), (10, 0, 5), (5, 10, 10)])]
    _make_binary_stl(path, tris)
    result = stl_bbox(str(path))
    assert result == ((0.0, 0.0, 0.0), (10.0, 10.0, 10.0))


def test_ascii_stl_bbox(tmp_path):
    stl_bbox.cache_clear()
    path = tmp_path / "cube_corner_ascii.stl"
    tris = [((0.0, 0.0, 1.0), [(-5.0, 0.0, 0.0), (10.0, 0.0, 5.0), (2.5, 8.0, 12.0)])]
    _make_ascii_stl(path, tris)
    result = stl_bbox(str(path))
    assert result == ((-5.0, 0.0, 0.0), (10.0, 8.0, 12.0))


def test_missing_file_returns_none():
    stl_bbox.cache_clear()
    assert stl_bbox("/nonexistent/file.stl") is None


def test_invalid_file_returns_none(tmp_path):
    stl_bbox.cache_clear()
    path = tmp_path / "bogus.stl"
    path.write_bytes(b"not an stl at all")
    assert stl_bbox(str(path)) is None


def test_caching_same_path_returns_same_result(tmp_path):
    stl_bbox.cache_clear()
    path = tmp_path / "c.stl"
    tris = [((0, 0, 1), [(0, 0, 0), (1, 0, 0), (0, 1, 0)])]
    _make_binary_stl(path, tris)
    first = stl_bbox(str(path))
    # Overwrite contents: cached call should NOT re-read.
    _make_binary_stl(path, [((0, 0, 1), [(100, 100, 100), (200, 0, 0), (0, 200, 0)])])
    second = stl_bbox(str(path))
    assert first == second  # cache hit
    # After cache clear we see the new file.
    stl_bbox.cache_clear()
    third = stl_bbox(str(path))
    assert third != first


def test_detects_binary_vs_ascii(tmp_path):
    stl_bbox.cache_clear()
    # A binary STL whose header starts with "solid" (common in the wild).
    path = tmp_path / "evil.stl"
    with open(path, "wb") as f:
        header = b"solid this looks ascii but is binary"
        f.write(header + b"\x00" * (80 - len(header)))
        f.write(struct.pack("<I", 1))
        f.write(struct.pack("<fff", 0, 0, 1))  # normal
        f.write(struct.pack("<fff", 0, 0, 0))
        f.write(struct.pack("<fff", 5, 0, 0))
        f.write(struct.pack("<fff", 0, 5, 0))
        f.write(b"\x00\x00")
    result = stl_bbox(str(path))
    assert result == ((0.0, 0.0, 0.0), (5.0, 5.0, 0.0))
