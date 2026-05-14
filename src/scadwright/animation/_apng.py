"""Pure-Python APNG encoder. Stdlib-only (struct + zlib).

OpenSCAD's ``--animate N`` produces a sequence of PNG frames. This module
stitches them into a single animated PNG by reading each input PNG's
chunks, copying the IHDR (from frame 0) and IDAT payloads, and wrapping
them in APNG-specific control chunks (``acTL``, ``fcTL``, ``fdAT``).

No pixel decoding or palette quantization happens here — the encoder
copies IDAT payloads verbatim. All input frames must share dimensions,
bit depth, and color type. APNG output renders losslessly across modern
browsers and on GitHub READMEs, Discord, Reddit, Mastodon, and other
maker-relevant targets.

References:
    - PNG spec: https://www.w3.org/TR/PNG/
    - APNG spec: https://wiki.mozilla.org/APNG_Specification
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class _PNGImage:
    """A parsed PNG: header (IHDR data) + concatenated IDAT payload."""

    ihdr: bytes  # 13-byte IHDR data
    idat: bytes  # concatenated IDAT payload across all IDAT chunks

    @property
    def width(self) -> int:
        return struct.unpack(">I", self.ihdr[0:4])[0]

    @property
    def height(self) -> int:
        return struct.unpack(">I", self.ihdr[4:8])[0]

    @property
    def bit_depth(self) -> int:
        return self.ihdr[8]

    @property
    def color_type(self) -> int:
        return self.ihdr[9]


def _parse_png(data: bytes, source: str) -> _PNGImage:
    """Read a PNG byte stream; extract IHDR data and IDAT payload.

    ``source`` is the file path or label used in error messages.
    """
    if len(data) < len(_PNG_SIGNATURE) or data[: len(_PNG_SIGNATURE)] != _PNG_SIGNATURE:
        raise ValueError(f"{source}: not a PNG (signature missing)")
    pos = len(_PNG_SIGNATURE)
    ihdr: bytes | None = None
    idat_chunks: list[bytes] = []
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError(f"{source}: truncated chunk header at {pos}")
        length, ctype = struct.unpack(">I4s", data[pos : pos + 8])
        pos += 8
        if pos + length + 4 > len(data):
            raise ValueError(f"{source}: truncated chunk {ctype!r} at {pos}")
        payload = data[pos : pos + length]
        pos += length
        # CRC: 4 bytes. We don't verify; OpenSCAD output is trusted.
        pos += 4
        if ctype == b"IHDR":
            if length != 13:
                raise ValueError(f"{source}: IHDR length {length} != 13")
            ihdr = payload
        elif ctype == b"IDAT":
            idat_chunks.append(payload)
        elif ctype == b"IEND":
            break
        # Other chunks (tEXt, pHYs, gAMA, etc.) are ignored; APNG output
        # is the minimal IHDR + IDAT structure.
    if ihdr is None:
        raise ValueError(f"{source}: no IHDR chunk")
    if not idat_chunks:
        raise ValueError(f"{source}: no IDAT chunks")
    return _PNGImage(ihdr=ihdr, idat=b"".join(idat_chunks))


def _write_chunk(ctype: bytes, payload: bytes) -> bytes:
    """Serialize one PNG chunk: length (4BE) + type (4) + payload + CRC32 (4BE)."""
    if len(ctype) != 4:
        raise ValueError(f"chunk type must be 4 bytes, got {ctype!r}")
    crc = zlib.crc32(ctype + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)


def write_apng(
    frame_paths: list[Path] | list[str],
    out_path: Path | str,
    *,
    fps: int = 30,
    loop: int = 0,
) -> None:
    """Write an animated PNG by stitching ``frame_paths`` into ``out_path``.

    Arguments:
        frame_paths: ordered list of PNG file paths. Must be non-empty.
            All frames must share width, height, bit depth, and color
            type (otherwise the output APNG would be malformed).
        out_path: output APNG path.
        fps: animation frame rate. Default 30. The delay between frames
            is encoded as a rational ``(num, den)`` of ``(1, fps)`` so
            playback runs at the requested rate.
        loop: playback count. ``0`` (default) means loop forever; any
            positive integer means play that many times then stop.

    Raises ``ValueError`` on empty input, malformed PNGs, or mismatched
    IHDR across frames.
    """
    paths = [Path(p) for p in frame_paths]
    if not paths:
        raise ValueError("write_apng: frame_paths is empty")
    if fps <= 0:
        raise ValueError(f"write_apng: fps must be positive, got {fps}")
    if loop < 0:
        raise ValueError(f"write_apng: loop must be >= 0, got {loop}")

    images: list[_PNGImage] = []
    for p in paths:
        with open(p, "rb") as f:
            data = f.read()
        images.append(_parse_png(data, str(p)))

    # Validate all frames share IHDR.
    ref = images[0]
    for img, path in zip(images[1:], paths[1:]):
        if img.ihdr != ref.ihdr:
            raise ValueError(
                f"frame {path} has IHDR {img.width}x{img.height} "
                f"bd={img.bit_depth} ct={img.color_type}, "
                f"expected {ref.width}x{ref.height} "
                f"bd={ref.bit_depth} ct={ref.color_type}. "
                f"All APNG frames must share dimensions and pixel format."
            )

    n_frames = len(images)

    # Build the output bytes.
    out = bytearray(_PNG_SIGNATURE)
    out += _write_chunk(b"IHDR", ref.ihdr)

    # acTL: animation control. num_frames (4BE) + num_plays (4BE).
    out += _write_chunk(b"acTL", struct.pack(">II", n_frames, loop))

    seq = 0
    # delay is 1/fps seconds: encoded as numerator=1, denominator=fps.
    # APNG also allows denominator=0 to mean 1/100 seconds, but explicit
    # rational is cleaner.
    delay_num, delay_den = 1, fps

    for i, img in enumerate(images):
        # fcTL: frame control. sequence_number (4BE), width (4BE),
        # height (4BE), x_offset (4BE), y_offset (4BE), delay_num (2BE),
        # delay_den (2BE), dispose_op (1), blend_op (1).
        fctl = struct.pack(
            ">IIIIIHHBB",
            seq, ref.width, ref.height, 0, 0,
            delay_num, delay_den,
            0,  # dispose_op = APNG_DISPOSE_OP_NONE (leave frame as-is)
            0,  # blend_op = APNG_BLEND_OP_SOURCE (overwrite)
        )
        out += _write_chunk(b"fcTL", fctl)
        seq += 1
        if i == 0:
            # Frame 0 uses the standard IDAT chunk as its image data.
            out += _write_chunk(b"IDAT", img.idat)
        else:
            # Subsequent frames use fdAT: sequence_number + IDAT payload.
            out += _write_chunk(b"fdAT", struct.pack(">I", seq) + img.idat)
            seq += 1

    out += _write_chunk(b"IEND", b"")

    Path(out_path).write_bytes(bytes(out))
