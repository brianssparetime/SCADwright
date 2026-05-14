"""APNG encoder tests: parse PNG, stitch APNG, round-trip back through
the parser, confirm structure."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from scadwright.animation._apng import (
    _PNG_SIGNATURE, _parse_png, _PNGImage, _write_chunk, write_apng,
)


def _make_solid_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """Build a minimal RGB8 PNG of the given dimensions, filled with the
    given (r, g, b) color. Pure stdlib."""
    # IHDR: width, height, bit_depth=8, color_type=2 (RGB), compression=0,
    # filter=0, interlace=0.
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # Raw pixel data: each scanline is [filter_byte, R, G, B, R, G, B, ...].
    r, g, b = color
    scanline = bytes([0]) + bytes([r, g, b] * width)
    raw = scanline * height
    idat_data = zlib.compress(raw)
    out = bytearray(_PNG_SIGNATURE)
    out += _write_chunk(b"IHDR", ihdr_data)
    out += _write_chunk(b"IDAT", idat_data)
    out += _write_chunk(b"IEND", b"")
    return bytes(out)


def _parse_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Extract (chunk_type, chunk_payload) for every chunk in a PNG byte
    stream. Convenience for round-trip assertions."""
    assert data[: len(_PNG_SIGNATURE)] == _PNG_SIGNATURE
    pos = len(_PNG_SIGNATURE)
    out = []
    while pos < len(data):
        length, ctype = struct.unpack(">I4s", data[pos : pos + 8])
        pos += 8
        payload = data[pos : pos + length]
        pos += length + 4  # skip CRC
        out.append((ctype, payload))
        if ctype == b"IEND":
            break
    return out


# ---------------------------------------------------------------------------
# Single-frame round-trip
# ---------------------------------------------------------------------------


def test_apng_single_frame(tmp_path: Path):
    """Encoding a single PNG into an APNG and reading the chunks back
    should produce: signature, IHDR, acTL(1, 0), fcTL, IDAT, IEND."""
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(8, 8, (255, 0, 0)))
    out = tmp_path / "out.apng"
    write_apng([src], out, fps=10)
    chunks = _parse_chunks(out.read_bytes())
    types = [c[0] for c in chunks]
    assert types == [b"IHDR", b"acTL", b"fcTL", b"IDAT", b"IEND"]


def test_apng_acTL_payload(tmp_path: Path):
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(8, 8, (0, 255, 0)))
    out = tmp_path / "out.apng"
    write_apng([src], out, fps=30, loop=5)
    chunks = dict(_parse_chunks(out.read_bytes()))
    n_frames, n_plays = struct.unpack(">II", chunks[b"acTL"])
    assert n_frames == 1
    assert n_plays == 5


def test_apng_acTL_loop_zero_is_infinite(tmp_path: Path):
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(4, 4, (0, 0, 255)))
    out = tmp_path / "out.apng"
    write_apng([src], out)  # default loop=0
    chunks = dict(_parse_chunks(out.read_bytes()))
    _, n_plays = struct.unpack(">II", chunks[b"acTL"])
    assert n_plays == 0


# ---------------------------------------------------------------------------
# Multi-frame
# ---------------------------------------------------------------------------


def test_apng_three_frames(tmp_path: Path):
    paths = []
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        p = tmp_path / f"frame{i}.png"
        p.write_bytes(_make_solid_png(8, 8, color))
        paths.append(p)
    out = tmp_path / "out.apng"
    write_apng(paths, out, fps=15)

    chunks = _parse_chunks(out.read_bytes())
    types = [c[0] for c in chunks]
    # Expected: IHDR, acTL, fcTL, IDAT, fcTL, fdAT, fcTL, fdAT, IEND.
    assert types == [
        b"IHDR", b"acTL",
        b"fcTL", b"IDAT",
        b"fcTL", b"fdAT",
        b"fcTL", b"fdAT",
        b"IEND",
    ]


def test_apng_sequence_numbers_monotonic(tmp_path: Path):
    """fcTL.sequence_number and fdAT.sequence_number must increase
    monotonically across all animation chunks."""
    paths = []
    for i in range(3):
        p = tmp_path / f"frame{i}.png"
        p.write_bytes(_make_solid_png(4, 4, (i * 80, 0, 0)))
        paths.append(p)
    out = tmp_path / "out.apng"
    write_apng(paths, out)

    chunks = _parse_chunks(out.read_bytes())
    seqs: list[int] = []
    for ctype, payload in chunks:
        if ctype == b"fcTL":
            seqs.append(struct.unpack(">I", payload[:4])[0])
        elif ctype == b"fdAT":
            seqs.append(struct.unpack(">I", payload[:4])[0])
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)  # all unique


def test_apng_frame_count_in_acTL(tmp_path: Path):
    paths = []
    for i in range(5):
        p = tmp_path / f"frame{i}.png"
        p.write_bytes(_make_solid_png(2, 2, (i, 0, 0)))
        paths.append(p)
    out = tmp_path / "out.apng"
    write_apng(paths, out)
    chunks = dict(_parse_chunks(out.read_bytes()))
    n_frames, _ = struct.unpack(">II", chunks[b"acTL"])
    assert n_frames == 5


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_apng_mismatched_dimensions_raises(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(_make_solid_png(8, 8, (255, 0, 0)))
    b.write_bytes(_make_solid_png(16, 8, (0, 255, 0)))  # different width
    with pytest.raises(ValueError, match=r"(?s)IHDR.*All APNG frames must share"):
        write_apng([a, b], tmp_path / "out.apng")


def test_apng_empty_frames_raises(tmp_path: Path):
    with pytest.raises(ValueError, match=r"empty"):
        write_apng([], tmp_path / "out.apng")


def test_apng_invalid_fps_raises(tmp_path: Path):
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(4, 4, (0, 0, 0)))
    with pytest.raises(ValueError, match=r"fps must be positive"):
        write_apng([src], tmp_path / "out.apng", fps=0)


def test_apng_not_a_png_raises(tmp_path: Path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"this is not a PNG file")
    with pytest.raises(ValueError, match=r"(?s)signature missing"):
        write_apng([bad], tmp_path / "out.apng")


# ---------------------------------------------------------------------------
# Output is itself parseable
# ---------------------------------------------------------------------------


def test_apng_output_starts_with_png_signature(tmp_path: Path):
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(4, 4, (128, 128, 128)))
    out = tmp_path / "out.apng"
    write_apng([src], out)
    data = out.read_bytes()
    assert data[: len(_PNG_SIGNATURE)] == _PNG_SIGNATURE


def test_apng_output_roundtrip_through_parser(tmp_path: Path):
    """Encoded APNG should be re-parseable by _parse_png (which treats
    fcTL/fdAT/acTL as unknown chunks and ignores them — so the IHDR
    + IDAT should still come out correctly)."""
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(6, 4, (200, 100, 50)))
    out = tmp_path / "out.apng"
    write_apng([src], out)
    parsed = _parse_png(out.read_bytes(), str(out))
    assert parsed.width == 6
    assert parsed.height == 4


def test_apng_fctl_dimensions_match_source(tmp_path: Path):
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(12, 7, (50, 100, 200)))
    out = tmp_path / "out.apng"
    write_apng([src], out)
    chunks = dict(_parse_chunks(out.read_bytes()))
    fctl = chunks[b"fcTL"]
    seq, width, height, x_off, y_off = struct.unpack(">IIIII", fctl[:20])
    assert width == 12
    assert height == 7
    assert x_off == 0
    assert y_off == 0


def test_apng_fctl_delay_matches_fps(tmp_path: Path):
    src = tmp_path / "frame.png"
    src.write_bytes(_make_solid_png(4, 4, (255, 255, 255)))
    out = tmp_path / "out.apng"
    write_apng([src], out, fps=24)
    chunks = dict(_parse_chunks(out.read_bytes()))
    fctl = chunks[b"fcTL"]
    delay_num, delay_den = struct.unpack(">HH", fctl[20:24])
    # Delay encoded as 1/fps seconds → (1, 24).
    assert delay_num == 1
    assert delay_den == 24
