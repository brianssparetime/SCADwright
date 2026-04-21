"""Render beauty-shot PNGs from the manifest.

Produces PNGs for shape-library Components and example scripts with a
consistent camera and colorscheme, so docs images regenerate from one command.

Usage:
    python tools/render_beauty_shots.py                   # render all
    python tools/render_beauty_shots.py --filter tube     # render matching
    python tools/render_beauty_shots.py --openscad PATH   # custom binary

Requires OpenSCAD. Binary is located via --openscad, $SCADWRIGHT_OPENSCAD,
the `openscad` name on PATH, or the default macOS .app path.

When embedding generated images in markdown docs, put captions on a new line
beneath the image to avoid sizing breakage, i.e.:

    ![alt](path/to/image.png)

    *caption here*

not:

    ![alt](path/to/image.png) *caption here*
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


CAMERA = "0,0,0,60,0,45,500"   # rx=60° inclination, rz=45° azimuth; dist overridden by --viewall
IMGSIZE = "1200,900"
COLORSCHEME = "Metallic"
FN = 96                        # override $fn globally for smooth circles
MAC_DEFAULT = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"

# Shape-library hero/gallery mosaic — fixed layout so successive regens
# stay consistent. Re-run with --hero after adding/removing shapes.
HERO_DIR = Path("docs/shapes/images")
HERO_OUTPUT = HERO_DIR / "hero.png"
HERO_TILE = "8x6"              # 48 cells; resize when the tile count changes
HERO_GEOMETRY = "300x225+3+3"  # per-tile size + 3px gap
HERO_BG = "#AAAAFF"            # matches the Metallic shots' lavender backdrop


def _resolve_openscad(explicit: str | None) -> str:
    candidate = explicit or os.environ.get("SCADWRIGHT_OPENSCAD") or "openscad"
    found = shutil.which(candidate)
    if found:
        return found
    if Path(MAC_DEFAULT).exists():
        return MAC_DEFAULT
    raise SystemExit(
        f"could not find openscad binary {candidate!r}. "
        "Install OpenSCAD, pass --openscad PATH, or set $SCADWRIGHT_OPENSCAD."
    )


def _render_png(scad_path: Path, out_png: Path, openscad: str, opts: dict) -> None:
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    # Preview (throwntogether) rather than full CGAL render: respects color()
    # directives, handles non-closed meshes (e.g. Helix), and renders faster.
    cmd = [
        openscad,
        "-o", str(out_png),
        f"--camera={opts['camera']}",
        f"--imgsize={opts['imgsize']}",
        f"--colorscheme={opts['colorscheme']}",
        "--autocenter",
        "--viewall",
        "-D", f"$fn={opts['fn']}",
        str(scad_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"openscad failed for {out_png}:\n{result.stderr.strip() or result.stdout.strip()}"
        )


def _render_component_entry(entry: dict, tmpdir: str, openscad: str, opts: dict) -> None:
    from scadwright.render import render

    # Two entry forms: Component class + kwargs, OR a build callable returning
    # a Node. The callable form is needed for 2D profiles that must be
    # extruded to be visible, and for transform-chain demos.
    if "build" in entry:
        instance = entry["build"]()
        label = entry.get("name") or Path(entry["out"]).stem
    else:
        cls = entry["component"]
        kwargs = entry.get("kwargs", {})
        label = entry.get("name", cls.__name__.lower())
        instance = cls(**kwargs)
    scad_path = Path(tmpdir) / f"{label}.scad"
    render(instance, scad_path)
    _render_png(scad_path, Path(entry["out"]), openscad, opts)


def _render_hero() -> int:
    """Assemble the shape-library hero mosaic from every PNG in HERO_DIR
    (except the hero itself) via `magick montage`.

    Sort order is alphabetical so the grid layout is stable across runs.
    Requires ImageMagick on PATH.
    """
    magick = shutil.which("magick")
    if not magick:
        raise SystemExit(
            "could not find 'magick' on PATH. Install ImageMagick (e.g. `brew install imagemagick`)."
        )
    if not HERO_DIR.is_dir():
        raise SystemExit(f"hero directory not found: {HERO_DIR}")

    tiles = sorted(p for p in HERO_DIR.glob("*.png") if p.name != HERO_OUTPUT.name)
    if not tiles:
        raise SystemExit(f"no tiles found under {HERO_DIR}")

    cmd = [magick, "montage", *map(str, tiles),
           "-tile", HERO_TILE,
           "-geometry", HERO_GEOMETRY,
           "-background", HERO_BG,
           str(HERO_OUTPUT)]
    print(f"assembling hero from {len(tiles)} tile(s) -> {HERO_OUTPUT}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"magick montage failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return 0


def _render_example_entry(entry: dict, tmpdir: str, openscad: str, opts: dict) -> None:
    # Run `scadwright build` in a subprocess so each example imports in a
    # fresh interpreter — avoids collisions on module-level state like the
    # @transform decorator's global registry when multiple variants of the
    # same script are rendered in one run.
    script = entry["script"]
    variant = entry["variant"]
    scad_path = Path(tmpdir) / f"{Path(script).stem}-{variant}.scad"
    result = subprocess.run(
        [sys.executable, "-m", "scadwright.cli",
         "build", script, "--variant", variant, "-o", str(scad_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"scadwright build failed for {script} variant {variant}:\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    _render_png(scad_path, Path(entry["out"]), openscad, opts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render beauty-shot PNGs from the manifest.")
    parser.add_argument("--filter", help="render only entries whose output path contains this substring")
    parser.add_argument("--openscad", default=None, help="path to openscad binary")
    parser.add_argument("--camera", default=CAMERA, help=f"OpenSCAD --camera arg (default: {CAMERA})")
    parser.add_argument("--imgsize", default=IMGSIZE, help=f"WxH comma pair (default: {IMGSIZE})")
    parser.add_argument("--colorscheme", default=COLORSCHEME, help=f"OpenSCAD colorscheme (default: {COLORSCHEME})")
    parser.add_argument("--fn", type=int, default=FN, help=f"override $fn for smooth circles (default: {FN})")
    parser.add_argument("--hero", action="store_true",
                        help=f"regenerate {HERO_OUTPUT} from the current shape-library PNGs and exit (no shot rendering)")
    args = parser.parse_args(argv)

    if args.hero:
        return _render_hero()

    tools_dir = Path(__file__).parent
    sys.path.insert(0, str(tools_dir))
    import beauty_shots as manifest

    openscad = _resolve_openscad(args.openscad)
    opts = {"camera": args.camera, "imgsize": args.imgsize, "colorscheme": args.colorscheme, "fn": args.fn}

    def _match(path: str) -> bool:
        return args.filter is None or args.filter in path

    components = [e for e in getattr(manifest, "COMPONENTS", []) if _match(e["out"])]
    examples = [e for e in getattr(manifest, "EXAMPLES", []) if _match(e["out"])]
    total = len(components) + len(examples)
    if total == 0:
        print("no entries match the filter", file=sys.stderr)
        return 1

    print(f"rendering {total} shot(s) with openscad={openscad}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmpdir:
        for e in components:
            print(f"  [component] -> {e['out']}", file=sys.stderr)
            _render_component_entry(e, tmpdir, openscad, opts)
        for e in examples:
            print(f"  [example]   -> {e['out']}", file=sys.stderr)
            _render_example_entry(e, tmpdir, openscad, opts)

    print(f"done: wrote {total} image(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
