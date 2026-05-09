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

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None


CAMERA = "0,0,0,60,0,45,500"   # rx=60° inclination, rz=45° azimuth; dist overridden by --viewall
IMGSIZE = "1200,900"
COLORSCHEME = "Metallic"
FN = 96                        # override $fn globally for smooth circles
MAC_DEFAULT = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"

# Per-entry overrides for example shots — camera, imgsize, $fn, etc.
# Keyed by script stem (e.g. ``[rocket]`` matches ``examples/rocket.py``).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAMERAS_TOML = PROJECT_ROOT / "examples" / ".beauty-cameras.toml"

# Shape-library hero/gallery mosaic — fixed layout so successive regens
# stay consistent. Re-run with --hero after adding/removing shapes.
HERO_DIR = Path("docs/shapes/images")
HERO_OUTPUT = HERO_DIR / "hero.png"
HERO_TILE = "9x6"              # 54 cells; resize when the tile count changes
HERO_GEOMETRY = "300x225+3+3"  # per-tile size + 3px gap
HERO_BG = "#AAAAFF"            # matches the Metallic shots' lavender backdrop

# Per-tile size for multi-variant example composites.
COMPOSITE_TILE_GEOMETRY = "800x600+5+5"


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


def _load_camera_overrides() -> dict[str, dict]:
    """Per-entry overrides keyed by section name. Empty when the file is
    missing or tomllib isn't available."""
    if tomllib is None or not CAMERAS_TOML.is_file():
        return {}
    with open(CAMERAS_TOML, "rb") as f:
        return tomllib.load(f)


def _resolve_opts(args: argparse.Namespace, override: dict | None) -> dict:
    """Merge CLI flags > TOML overrides > built-in defaults.

    CLI flags default to ``None`` and only win when explicitly passed,
    so a TOML override (e.g. the rocket's saved camera) survives a
    bare ``render_beauty_shots.py`` invocation.
    """
    o = override or {}
    return {
        "camera": args.camera if args.camera is not None else o.get("camera", CAMERA),
        "imgsize": args.imgsize if args.imgsize is not None else o.get("imgsize", IMGSIZE),
        "colorscheme": args.colorscheme if args.colorscheme is not None else o.get("colorscheme", COLORSCHEME),
        "fn": args.fn if args.fn is not None else o.get("fn", FN),
        "viewall": o.get("viewall", True),
        "autocenter": o.get("autocenter", True),
    }


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
    ]
    if opts.get("autocenter", True):
        cmd.append("--autocenter")
    if opts.get("viewall", True):
        cmd.append("--viewall")
    cmd += ["-D", f"$fn={opts['fn']}", str(scad_path)]
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


def _render_composite(entry: dict) -> bool:
    """Assemble a side-by-side composite from already-rendered tile PNGs.

    Returns True on success, False if any tile is missing (skipped).
    Requires ImageMagick.
    """
    magick = shutil.which("magick")
    if not magick:
        raise SystemExit(
            "could not find 'magick' on PATH. Install ImageMagick (e.g. `brew install imagemagick`)."
        )
    tiles = [Path(t) for t in entry["tiles"]]
    missing = [str(t) for t in tiles if not t.exists()]
    if missing:
        print(f"  [composite] skipping {entry['out']} (missing: {', '.join(missing)})", file=sys.stderr)
        return False
    out = Path(entry["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    layout = f"{len(tiles)}x1"
    cmd = [magick, "montage", *map(str, tiles),
           "-tile", layout,
           "-geometry", COMPOSITE_TILE_GEOMETRY,
           "-background", HERO_BG,
           str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"magick montage failed for {out}:\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return True


def _render_example_entry(
    entry: dict, tmpdir: str, openscad: str,
    args: argparse.Namespace, overrides: dict[str, dict],
) -> None:
    # Run each example in a fresh interpreter so module-level state (the
    # @transform decorator's registry, the render() capture singleton)
    # doesn't leak between scripts or between variants of one script.
    script = entry["script"]
    stem = Path(script).stem
    override = overrides.get(stem)
    opts = _resolve_opts(args, override)

    variant = entry.get("variant")
    if variant is not None:
        scad_path = Path(tmpdir) / f"{stem}-{variant}.scad"
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
    else:
        # Flat script (no Design class, no MODEL): just run it. Its
        # module-level render() writes the .scad to its cwd, so we cd
        # to the script's directory first — that's also where the
        # script expects to find its sibling .scad if it reads one.
        script_path = (PROJECT_ROOT / script).resolve()
        scad_filename = (override or {}).get("scad", f"{stem}.scad")
        scad_path = script_path.parent / scad_filename
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(script_path.parent),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"running {script} failed:\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        if not scad_path.is_file():
            raise SystemExit(
                f"{script} produced no {scad_filename} at {scad_path}"
            )

    _render_png(scad_path, Path(entry["out"]), openscad, opts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render beauty-shot PNGs from the manifest.")
    parser.add_argument("--filter", help="render only entries whose output path contains this substring")
    parser.add_argument("--openscad", default=None, help="path to openscad binary")
    # Render opts default to None so a TOML per-entry override (e.g. the
    # rocket's saved camera) wins over the built-in default. Explicit CLI
    # flags still beat the TOML.
    parser.add_argument("--camera", default=None,
                        help=f"OpenSCAD --camera arg (default: {CAMERA}, or per-entry from {CAMERAS_TOML.name})")
    parser.add_argument("--imgsize", default=None,
                        help=f"WxH comma pair (default: {IMGSIZE}, or per-entry)")
    parser.add_argument("--colorscheme", default=None,
                        help=f"OpenSCAD colorscheme (default: {COLORSCHEME}, or per-entry)")
    parser.add_argument("--fn", type=int, default=None,
                        help=f"override $fn for smooth circles (default: {FN}, or per-entry)")
    parser.add_argument("--hero", action="store_true",
                        help=f"regenerate {HERO_OUTPUT} from the current shape-library PNGs and exit (no shot rendering)")
    args = parser.parse_args(argv)

    if args.hero:
        return _render_hero()

    tools_dir = Path(__file__).parent
    sys.path.insert(0, str(tools_dir))
    import beauty_shots as manifest

    openscad = _resolve_openscad(args.openscad)
    overrides = _load_camera_overrides()
    component_opts = _resolve_opts(args, None)

    def _match(path: str) -> bool:
        return args.filter is None or args.filter in path

    components = [e for e in getattr(manifest, "COMPONENTS", []) if _match(e["out"])]
    examples = [e for e in getattr(manifest, "EXAMPLES", []) if _match(e["out"])]
    composites = [e for e in getattr(manifest, "COMPOSITES", []) if _match(e["out"])]
    total = len(components) + len(examples)
    if total == 0 and not composites:
        print("no entries match the filter", file=sys.stderr)
        return 1

    print(f"rendering {total} shot(s) with openscad={openscad}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmpdir:
        for e in components:
            print(f"  [component] -> {e['out']}", file=sys.stderr)
            _render_component_entry(e, tmpdir, openscad, component_opts)
        for e in examples:
            print(f"  [example]   -> {e['out']}", file=sys.stderr)
            _render_example_entry(e, tmpdir, openscad, args, overrides)

    composite_count = 0
    for e in composites:
        if _render_composite(e):
            print(f"  [composite] -> {e['out']}", file=sys.stderr)
            composite_count += 1

    print(f"done: wrote {total + composite_count} image(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
