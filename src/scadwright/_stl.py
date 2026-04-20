"""Minimal STL parser for extracting bounding boxes of imported STL files.

Supports both binary and ASCII STL. Returns None on missing/invalid input
rather than raising — bbox callers fall through to a degenerate default.
"""

from __future__ import annotations

import os
import re
import struct
from functools import lru_cache


def _read_binary_stl_bbox(path: str):
    """Return (min_xyz, max_xyz) from a binary STL, or None on error."""
    try:
        with open(path, "rb") as f:
            f.seek(80)
            count_bytes = f.read(4)
            if len(count_bytes) != 4:
                return None
            n_triangles = struct.unpack("<I", count_bytes)[0]
            min_x = min_y = min_z = float("inf")
            max_x = max_y = max_z = float("-inf")
            for _ in range(n_triangles):
                # Skip normal (3 floats, 12 bytes).
                if len(f.read(12)) != 12:
                    return None
                for _ in range(3):
                    vertex_bytes = f.read(12)
                    if len(vertex_bytes) != 12:
                        return None
                    x, y, z = struct.unpack("<fff", vertex_bytes)
                    if x < min_x: min_x = x
                    if y < min_y: min_y = y
                    if z < min_z: min_z = z
                    if x > max_x: max_x = x
                    if y > max_y: max_y = y
                    if z > max_z: max_z = z
                # Skip attribute byte count.
                if len(f.read(2)) != 2:
                    return None
            if min_x == float("inf"):
                return None
            return ((min_x, min_y, min_z), (max_x, max_y, max_z))
    except OSError:
        return None


_VERTEX_RE = re.compile(
    rb"vertex\s+([+\-0-9.eE]+)\s+([+\-0-9.eE]+)\s+([+\-0-9.eE]+)"
)


def _read_ascii_stl_bbox(path: str):
    """Return (min_xyz, max_xyz) from an ASCII STL, or None on error."""
    try:
        min_x = min_y = min_z = float("inf")
        max_x = max_y = max_z = float("-inf")
        with open(path, "rb") as f:
            for line in f:
                m = _VERTEX_RE.search(line)
                if not m:
                    continue
                try:
                    x = float(m.group(1))
                    y = float(m.group(2))
                    z = float(m.group(3))
                except ValueError:
                    continue
                if x < min_x: min_x = x
                if y < min_y: min_y = y
                if z < min_z: min_z = z
                if x > max_x: max_x = x
                if y > max_y: max_y = y
                if z > max_z: max_z = z
        if min_x == float("inf"):
            return None
        return ((min_x, min_y, min_z), (max_x, max_y, max_z))
    except OSError:
        return None


def _looks_binary(path: str) -> bool:
    """Detect a binary STL by comparing file size to the expected size
    computed from the triangle count at bytes 80..84."""
    try:
        size = os.path.getsize(path)
        if size < 84:
            return False
        with open(path, "rb") as f:
            f.seek(80)
            count_bytes = f.read(4)
        if len(count_bytes) != 4:
            return False
        n = struct.unpack("<I", count_bytes)[0]
        return size == 84 + 50 * n
    except OSError:
        return False


@lru_cache(maxsize=128)
def stl_bbox(path: str):
    """Parse an STL file and return ((min_xyz), (max_xyz)) or None.

    Cached per-path. Call `stl_bbox.cache_clear()` after regenerating a file.
    """
    if not os.path.isfile(path):
        return None
    if _looks_binary(path):
        return _read_binary_stl_bbox(path)
    return _read_ascii_stl_bbox(path)
