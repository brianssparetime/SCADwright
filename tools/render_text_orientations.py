"""Render the 8 text-orientation reference images and compose them into a
labeled 2x4 grid for embedding in docs/add_text.md.

Each cell shows one combination of ``add_text``'s ``text_dir`` /
``rotate_glyphs`` / ``flip`` kwargs applied to "TEXT" on a curved host;
alternating hosts (cylinder / tapered cone / barrel) prove the same
combinations work uniformly across surface kinds.

Pipeline:

1. For each of the 8 combos, build a one-host SCAD and write it to a
   tempdir.
2. Render each via OpenSCAD CLI (Liberation Sans, Metallic colorscheme,
   #AAAAFF background — same conventions as ``render_beauty_shots.py``).
3. Use PIL to compose into a 2x4 grid with the kwargs printed under each
   cell, plus a header strip describing the row.
4. Write the final PNG to ``docs/images/add_text_orientations.png``.

Run: ``python tools/render_text_orientations.py``
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scadwright import render as scad_render, resolution           # noqa: E402
from scadwright.primitives import cylinder                         # noqa: E402
from scadwright.shapes import Barrel                               # noqa: E402


# (text_dir, rotate_glyphs, flip, host kind)
COMBOS = [
    ("circumferential", False, False, "cyl"),
    ("circumferential", False, True,  "cone"),
    ("circumferential", True,  False, "barrel"),
    ("circumferential", True,  True,  "cyl"),
    ("axial",           False, False, "cone"),
    ("axial",           False, True,  "barrel"),
    ("axial",           True,  False, "cyl"),
    ("axial",           True,  True,  "cone"),
]

CELL_W, CELL_H = 360, 360
LABEL_H = 48
HOST_H = 28
OUT_DIR = REPO_ROOT / "docs" / "images"
OUT_FILE = OUT_DIR / "add_text_orientations.png"
OPENSCAD = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"


def _make_host(kind):
    if kind == "cyl":
        return cylinder(h=HOST_H, r=8)
    if kind == "cone":
        return cylinder(h=HOST_H, r1=10, r2=5)
    if kind == "barrel":
        return Barrel(h=HOST_H, end_r=8, bulge=2)
    raise ValueError(kind)


def _emit_combo_scad(td, rg, fl, kind, out_path: Path) -> None:
    host = _make_host(kind)
    with resolution(fn=96):
        labeled = host.add_text(
            label="TEXT", on="outer_wall", meridian=0,
            font_size=5, relief=-0.6,
            text_dir=td, rotate_glyphs=rg, flip=fl,
        )
    scad_render(labeled, out_path)


def _openscad_render(scad_path: Path, png_path: Path) -> None:
    # Camera: eye at +X, target at origin, looking back along -X to see
    # the text engraved on the +X meridian. Vector form is `eye, center`.
    # Camera: eye on +X at fixed distance, target at the host's mid-height.
    # Fixed distance (no --viewall) keeps the host the same size across all
    # 8 cells so the engraving sizes match.
    cmd = [
        OPENSCAD,
        "--imgsize", f"{CELL_W},{CELL_H}",
        "--colorscheme", "Metallic",
        "--camera", f"60,0,{HOST_H/2},0,0,{HOST_H/2}",
        "--projection", "perspective",
        "-o", str(png_path),
        str(scad_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout.decode() + "\n" + result.stderr.decode())
        raise RuntimeError(f"openscad failed rendering {scad_path}")


def _label_for(td, rg, fl) -> str:
    td_short = "circ" if td == "circumferential" else "axial"
    parts = [f"text_dir={td_short!r}"]
    if rg:
        parts.append("rotate_glyphs=T")
    if fl:
        parts.append("flip=T")
    return ", ".join(parts)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        str(REPO_ROOT / "tests" / "fixtures" / "fonts" / "LiberationSans-Regular.ttf"),
        size,
    )


def _compose_grid(cell_pngs: list[Path]) -> Image.Image:
    cols, rows = 4, 2
    canvas_w = cols * CELL_W
    canvas_h = rows * (CELL_H + LABEL_H)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (170, 170, 255))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(20)
    for i, (td, rg, fl, _kind) in enumerate(COMBOS):
        col, row = i % cols, i // cols
        x0 = col * CELL_W
        y0 = row * (CELL_H + LABEL_H)
        cell_img = Image.open(cell_pngs[i]).convert("RGB")
        canvas.paste(cell_img, (x0, y0))
        # Label centred horizontally under the cell.
        text = _label_for(td, rg, fl)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x0 + (CELL_W - tw) // 2
        ty = y0 + CELL_H + (LABEL_H - th) // 2 - bbox[1]
        draw.text((tx, ty), text, fill=(40, 40, 40), font=font)
    return canvas


def main() -> int:
    if shutil.which(OPENSCAD) is None and not Path(OPENSCAD).exists():
        print(f"OpenSCAD not found at {OPENSCAD}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        cell_pngs: list[Path] = []
        for i, (text_dir, rg, fl, kind) in enumerate(COMBOS):
            scad_path = td_path / f"combo_{i}.scad"
            png_path = td_path / f"combo_{i}.png"
            _emit_combo_scad(text_dir, rg, fl, kind, scad_path)
            _openscad_render(scad_path, png_path)
            cell_pngs.append(png_path)
        grid = _compose_grid(cell_pngs)
        grid.save(OUT_FILE, optimize=True)
        print(f"wrote {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
