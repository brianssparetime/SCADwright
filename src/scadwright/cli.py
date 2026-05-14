"""scadwright command-line entry point.

Subcommands:
    build SCRIPT [-o OUT] [--debug] [--pretty/--compact] [--variant NAME]
        Import SCRIPT, find a top-level `MODEL` Node, render it to a .scad
        file. Unknown args after the script path are forwarded to the
        script's `sc.arg()` parser.

    preview SCRIPT [--variant NAME] [--openscad PATH]
        Build SCRIPT to a stable temp .scad file and launch OpenSCAD's
        GUI on it. Re-running overwrites the same temp file so an
        already-open OpenSCAD window picks up the change via auto-reload.

    render SCRIPT [-o OUT.stl] [--variant NAME] [--openscad PATH]
        Build SCRIPT to a temp .scad, then invoke `openscad -o OUT.stl`
        to render it headless. Default OUT is SCRIPT.stl next to the script.

    lsp
        Run the SCADwright language server over stdio. Editors spawn
        this subcommand with the project venv's `scadwright`. Requires
        the `[lsp]` extra (`pip install 'scadwright[lsp]'`); without
        it the subcommand exits non-zero with an install hint.

    graph PATH [--format mermaid|json|dot] [--filter NAME] [--depth N]
        Emit a dependency graph for a scadwright project. PATH may be
        a directory (recursed) or a single Python file. Default
        ``--format mermaid`` writes Mermaid ``graph TD`` source — pipe
        into a renderer or embed in a README. ``--format json`` writes
        a structured representation for downstream tooling.
        ``--format dot`` writes Graphviz DOT source — pipe into ``dot
        -Tsvg`` for projects too large for Mermaid layout. ``--filter
        NAME`` focuses the graph on one class (with optional ``--depth
        N`` to limit the radius).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scadwright import set_verbose
from scadwright.api import args as _args
from scadwright.api.variant import variant as _variant_ctx
from scadwright.errors import SCADwrightError
from scadwright.render import render


def _parse_vec3(s: str) -> tuple:
    """Parse a comma-separated triple like '60,0,30' into a 3-tuple of floats."""
    parts = [float(x.strip()) for x in s.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"expected 3 comma-separated values, got {len(parts)}")
    return tuple(parts)


def _add_build_options(p: argparse.ArgumentParser) -> None:
    """Options shared by build/preview/render: how to build the .scad."""
    p.add_argument("--debug", action="store_true", help="Emit debug source comments")
    p.add_argument(
        "--compact",
        action="store_true",
        help="Compact (single-line) output instead of pretty",
    )
    p.add_argument(
        "--variant",
        default=None,
        help="Set sc.current_variant() for this build",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show INFO-level scadwright log output",
    )
    # Viewpoint overrides (OpenSCAD camera).
    p.add_argument("--vpr", type=_parse_vec3, default=None, metavar="X,Y,Z",
                    help="Camera rotation ($vpr), e.g. --vpr=60,0,30")
    p.add_argument("--vpt", type=_parse_vec3, default=None, metavar="X,Y,Z",
                    help="Camera target ($vpt), e.g. --vpt=0,0,10")
    p.add_argument("--vpd", type=float, default=None, metavar="D",
                    help="Camera distance ($vpd), e.g. --vpd=200")
    p.add_argument("--vpf", type=float, default=None, metavar="F",
                    help="Camera field of view ($vpf), e.g. --vpf=22.5")


def _add_openscad_option(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--openscad",
        default=None,
        help="Path to the openscad binary (default: $SCADWRIGHT_OPENSCAD or 'openscad' on PATH)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scadwright",
        description="scadwright — Python-first OpenSCAD authoring",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Render a script's MODEL to .scad")
    build.add_argument("script", help="Path to Python script defining MODEL")
    build.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output .scad path (default: SCRIPT with .scad extension)",
    )
    _add_build_options(build)

    prev = sub.add_parser(
        "preview",
        help="Build SCRIPT and open it in OpenSCAD's preview window",
    )
    prev.add_argument("script", help="Path to Python script defining MODEL")
    _add_build_options(prev)
    _add_openscad_option(prev)

    rend = sub.add_parser(
        "render",
        help="Build SCRIPT and headlessly render to STL via OpenSCAD",
    )
    rend.add_argument("script", help="Path to Python script defining MODEL")
    rend.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output STL path (default: SCRIPT with .stl extension)",
    )
    _add_openscad_option(rend)
    _add_build_options(rend)

    morph = sub.add_parser(
        "morph",
        help="Render a Design's morph variant into an animation file (.apng / .scad / .png sequence)",
    )
    morph.add_argument("script", help="Path to the Python script defining a Design with a morph")
    morph.add_argument("morph_name", help="Name of the morph class attribute (e.g. 'assemble')")
    morph.add_argument(
        "output",
        help=(
            "Output file. Extension picks format: .apng (default animated PNG), "
            ".scad (animated SCAD only, no rendering), .png (frame sequence with "
            "OUTPUT as the filename prefix)"
        ),
    )
    morph.add_argument(
        "--frames", type=int, default=60,
        help="Number of animation frames. Default: 60.",
    )
    morph.add_argument(
        "--fps", type=int, default=30,
        help="Frame rate for .apng output. Default: 30.",
    )
    morph.add_argument(
        "--imgsize", default="800x600", metavar="WxH",
        help="Image dimensions, e.g. 1920x1080. Default: 800x600.",
    )
    morph.add_argument(
        "--loop", dest="loop", action="store_true", default=True,
        help=".apng loop forever (default).",
    )
    morph.add_argument(
        "--no-loop", dest="loop", action="store_false",
        help=".apng plays once and stops.",
    )
    morph.add_argument(
        "--keep-frames", action="store_true",
        help="Don't delete intermediate PNG frames after encoding. The temp "
             "directory path is printed at the end.",
    )
    morph.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show INFO-level scadwright log output.",
    )
    _add_openscad_option(morph)

    sub.add_parser(
        "lsp",
        help=(
            "Run the SCADwright language server over stdio "
            "(requires the [lsp] extra)"
        ),
    )

    graph = sub.add_parser(
        "graph",
        help=(
            "Emit a dependency graph for a scadwright project"
        ),
    )
    graph.add_argument(
        "path",
        help=(
            "Project directory (recursed) or single .py file"
        ),
    )
    graph.add_argument(
        "--format",
        choices=["mermaid", "json", "dot"],
        default="mermaid",
        help=(
            "Output format: 'mermaid' (default) for Markdown / "
            "GitHub embedding, 'json' for downstream tooling, "
            "'dot' for Graphviz layout on larger projects."
        ),
    )
    graph.add_argument(
        "--filter",
        dest="focus",
        default=None,
        help=(
            "Focus the graph on one Component / Spec / Design / "
            "Variant. Match by class name, or by dotted id "
            "(``module.ClassName``) when the bare name is "
            "ambiguous."
        ),
    )
    graph.add_argument(
        "--depth",
        type=int,
        default=None,
        help=(
            "Limit how far from the --filter focus the subgraph "
            "extends (hop count in either direction). 0 shows "
            "only the focus node; 1 shows direct neighbours; "
            "default is unlimited. Requires --filter."
        ),
    )

    return parser


def _import_script(script_path: Path):
    spec = importlib.util.spec_from_file_location("__scadwright_script__", script_path)
    if spec is None or spec.loader is None:
        raise SCADwrightError(f"could not load script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["__scadwright_script__"] = module
    spec.loader.exec_module(module)
    return module


def _extract_model(module, script_path: Path):
    if not hasattr(module, "MODEL"):
        raise SCADwrightError(
            f"{script_path.name} must define a top-level `MODEL` (a scadwright Node) "
            f"or call `render(...)` at module level (or define a Design subclass) "
            f"for `scadwright build` to find what to render."
        )
    return module.MODEL


def _import_with_self_render_capture(script_path: Path):
    """Import a script while tracking any ``render()`` calls it makes at
    module level. Returns ``(module, last_rendered_path_or_None)``.

    For self-contained example scripts that do their own ``render(model,
    "out.scad")`` rather than exposing a top-level ``MODEL`` for the CLI
    to render, the captured path becomes the .scad we hand to OpenSCAD.
    Runs the import with ``cwd`` = script's directory so the typical
    relative ``render(model, "rocket.scad")`` lands next to the source.
    """
    # The package's ``__init__`` re-exports ``render`` as the function,
    # which shadows the same-named submodule attribute on the package.
    # ``importlib.import_module`` reaches the submodule via sys.modules
    # rather than attribute lookup.
    _render_module = importlib.import_module("scadwright.render")
    _render_module._reset_last_rendered_for_testing()
    prev_cwd = os.getcwd()
    os.chdir(script_path.parent)
    try:
        module = _import_script(script_path)
    finally:
        os.chdir(prev_cwd)
    return module, _render_module.last_rendered_path()


def _temp_scad_path(script_path: Path, variant: str | None) -> Path:
    """A stable temp .scad path keyed on the script (and variant). Stable so
    OpenSCAD's auto-reload sees overwrites instead of accumulating files."""
    key = f"{script_path}::{variant or ''}"
    h = hashlib.sha1(key.encode()).hexdigest()[:12]
    suffix = f"-{variant}" if variant else ""
    name = f"scadwright-{script_path.stem}{suffix}-{h}.scad"
    return Path(tempfile.gettempdir()) / name


def _resolve_openscad(explicit: str | None) -> str:
    """Pick the openscad binary.

    Lookup order: ``--openscad`` flag → ``$SCADWRIGHT_OPENSCAD`` env →
    ``openscad`` on ``PATH`` → known install locations (macOS app bundle,
    Linux distro packages, Windows installer). Raise if nothing's found.
    """
    candidate = explicit or os.environ.get("SCADWRIGHT_OPENSCAD") or "openscad"
    found = shutil.which(candidate)
    if found:
        return found
    # Fall back to known install locations. macOS ships OpenSCAD as a .app
    # bundle that doesn't put `openscad` on $PATH; on Linux distro packages
    # the binary is usually on PATH already, but Snap and Flatpak aren't;
    # Windows installer drops to Program Files without modifying PATH.
    if candidate == "openscad":
        for path in _OPENSCAD_BINARY_CANDIDATES:
            if any(c in path for c in "*?["):
                hits = sorted(glob.glob(path), reverse=True)
                for hit in hits:
                    if os.path.isfile(hit) and os.access(hit, os.X_OK):
                        return hit
            elif os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    raise SCADwrightError(
        f"could not find openscad binary {candidate!r} on PATH or in any "
        f"of the standard install locations. Install OpenSCAD, or pass "
        f"--openscad PATH, or set $SCADWRIGHT_OPENSCAD."
    )


_OPENSCAD_BINARY_CANDIDATES: tuple[str, ...] = (
    # macOS — DMG/installer app bundle
    "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    # macOS — Homebrew Cellar (Apple Silicon and Intel)
    "/opt/homebrew/Cellar/openscad/*/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    "/usr/local/Cellar/openscad/*/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    # macOS — Homebrew bottle exposing a CLI binary
    "/opt/homebrew/bin/openscad",
    "/usr/local/bin/openscad",
    # Linux — Flatpak / Snap (the bare `openscad` command isn't on PATH)
    "/var/lib/flatpak/exports/bin/org.openscad.OpenSCAD",
    "/snap/bin/openscad",
    # Windows — installer default
    r"C:\Program Files\OpenSCAD\openscad.exe",
    r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
)


def _cli_viewpoint(args: argparse.Namespace) -> dict | None:
    """Extract CLI viewpoint overrides from parsed args. Returns a dict
    suitable for passing to viewpoint(), or None if no overrides."""
    vp = {}
    if getattr(args, "vpr", None) is not None:
        vp["rotation"] = args.vpr
    if getattr(args, "vpt", None) is not None:
        vp["target"] = args.vpt
    if getattr(args, "vpd", None) is not None:
        vp["distance"] = args.vpd
    if getattr(args, "vpf", None) is not None:
        vp["fov"] = args.vpf
    return vp or None


def _build_to(out_path: Path, script_path: Path, args: argparse.Namespace) -> None:
    """Import the script and render its MODEL to out_path, honoring --variant.

    Legacy (MODEL-based) path — used only when the script doesn't define any
    Design subclasses. Design-based scripts are handled via _build_design()."""
    from scadwright.animation import viewpoint as _viewpoint

    cli_vp = _cli_viewpoint(args)

    def _do_build():
        if args.variant is not None:
            with _variant_ctx(args.variant):
                module = _import_script(script_path)
                model = _extract_model(module, script_path)
                render(model, out_path, pretty=not args.compact, debug=args.debug)
        else:
            module = _import_script(script_path)
            model = _extract_model(module, script_path)
            render(model, out_path, pretty=not args.compact, debug=args.debug)

    if cli_vp:
        with _viewpoint(**cli_vp):
            _do_build()
    else:
        _do_build()


def _import_with_fresh_design_registry(script_path: Path):
    """Import the script and return (module, list_of_registered_designs).
    Resets the Design registry first so we only see what the script defines."""
    from scadwright.design import _reset_for_testing, registered_designs
    _reset_for_testing()
    module = _import_script(script_path)
    return module, registered_designs()


class _ScriptNotFound(SCADwrightError):
    """Raised when the user passes a script path that doesn't exist. Mapped
    to exit code 2 by `main` to distinguish it from internal build failures."""


def _common_setup(args: argparse.Namespace, unknown: list[str]) -> Path:
    """Verbose flag + arg forwarding + script path resolution. Returns the
    resolved script path."""
    if args.verbose:
        set_verbose(logging.INFO)
    script_path = Path(args.script).resolve()
    if not script_path.exists():
        raise _ScriptNotFound(f"script not found: {script_path}")
    _args.set_argv(unknown)
    return script_path


def _render_design_variants(
    script_path: Path,
    designs: list,
    args: argparse.Namespace,
    *,
    kind: str,
    out_override: Path | None = None,
) -> list[Path]:
    """Resolve and render variants from a Design-based script. Returns the
    list of written .scad paths."""
    from scadwright.design import resolve_variants, _render_one

    selected = resolve_variants(args.variant, kind=kind)
    if out_override is not None and len(selected) > 1:
        raise SCADwrightError(
            f"--output specified but {len(selected)} variants would be built; "
            "pass --variant=NAME to pick one."
        )
    written: list[Path] = []
    base_dir = script_path.parent
    cli_vp = _cli_viewpoint(args)
    for design_cls, vname, meta in selected:
        out = _render_one(
            design_cls, vname, meta,
            base_dir=base_dir,
            out_override=out_override,
            cli_viewpoint=cli_vp,
        )
        written.append(out)
    return written


def _cmd_build(args: argparse.Namespace, unknown: list[str]) -> int:
    script_path = _common_setup(args, unknown)
    _, designs = _import_with_fresh_design_registry(script_path)
    if designs:
        out_override = Path(args.output) if args.output else None
        written = _render_design_variants(
            script_path, designs, args, kind="build", out_override=out_override,
        )
        for p in written:
            print(f"wrote {p}", file=sys.stderr)
        return 0
    # Legacy MODEL-based path.
    out_path = Path(args.output) if args.output else script_path.with_suffix(".scad")
    _build_to(out_path, script_path, args)
    return 0


def _resolve_scad_output(
    script_path: Path, args: argparse.Namespace, *, kind: str,
) -> Path:
    """Return the .scad path to feed OpenSCAD, building it as needed.

    Three production paths, in priority order:

    1. **Design subclass.** Reset registry, import, run the resolver.
       Output goes to a stable temp path keyed on (script, variant).
    2. **Top-level ``MODEL``.** Import, render ``MODEL`` to a temp path.
    3. **Self-rendering script.** Import; if the script called
       ``render(...)`` at module level, use the path it wrote. Lets
       example scripts that already do their own rendering work with
       ``scadwright preview`` / ``render`` without rewriting them to
       expose ``MODEL``.
    """
    _, designs = _import_with_fresh_design_registry(script_path)
    if designs:
        scad_path = _temp_scad_path(script_path, args.variant)
        _render_design_variants(
            script_path, designs, args, kind=kind, out_override=scad_path,
        )
        return scad_path

    # No Design subclass — try MODEL, then fall back to capture.
    module, captured_path = _import_with_self_render_capture(script_path)
    if hasattr(module, "MODEL"):
        scad_path = _temp_scad_path(script_path, args.variant)
        _build_to(scad_path, script_path, args)
        return scad_path
    if captured_path is not None and captured_path.is_file():
        return captured_path
    raise SCADwrightError(
        f"{script_path.name} must define a top-level `MODEL`, call "
        f"`render(...)` at module level, or define a `Design` subclass "
        f"for `scadwright {kind}` to find what to render."
    )


def _cmd_preview(args: argparse.Namespace, unknown: list[str]) -> int:
    script_path = _common_setup(args, unknown)
    openscad = _resolve_openscad(args.openscad)
    scad_path = _resolve_scad_output(script_path, args, kind="preview")
    print(f"preview: wrote {scad_path}", file=sys.stderr)
    subprocess.Popen(
        [openscad, str(scad_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return 0


def _cmd_render(args: argparse.Namespace, unknown: list[str]) -> int:
    script_path = _common_setup(args, unknown)
    openscad = _resolve_openscad(args.openscad)
    out_stl = Path(args.output) if args.output else script_path.with_suffix(".stl")
    scad_path = _resolve_scad_output(script_path, args, kind="render")
    print(f"rendering {scad_path} -> {out_stl}", file=sys.stderr)
    result = subprocess.run([openscad, "-o", str(out_stl), str(scad_path)])
    if result.returncode != 0:
        raise SCADwrightError(
            f"openscad exited with code {result.returncode} while rendering {out_stl}"
        )
    print(f"wrote {out_stl}", file=sys.stderr)
    return 0


def _cmd_lsp(args: argparse.Namespace, unknown: list[str]) -> int:
    """Run the SCADwright language server over stdio.

    Requires the ``[lsp]`` extra. When pygls is missing the
    subcommand prints an install hint and exits non-zero so editor
    configs that spawn ``scadwright lsp`` get an actionable error
    rather than a Python traceback.
    """
    try:
        import pygls  # noqa: F401
    except ImportError:
        print(
            "error: scadwright lsp requires the 'lsp' extra. "
            "Install with: pip install 'scadwright[lsp]'",
            file=sys.stderr,
        )
        return 1
    from scadwright.lsp.server import main as server_main
    return server_main()


def _cmd_graph(args: argparse.Namespace, unknown: list[str]) -> int:
    """Emit a dependency graph for the project rooted at
    ``args.path``.

    Single-file inputs are treated as one-module projects (the
    file's parent acts as the implicit project root for module-path
    computation).
    """
    from scadwright.graph.build import build_graph

    target = Path(args.path)
    if not target.exists():
        print(f"error: path not found: {target}", file=sys.stderr)
        return 2
    if args.depth is not None and args.focus is None:
        print(
            "error: --depth requires --filter",
            file=sys.stderr,
        )
        return 2
    graph = build_graph(target)
    for err_path, err_msg in graph.parse_errors:
        print(
            f"warning: skipped {err_path}: {err_msg}",
            file=sys.stderr,
        )
    if args.focus is not None:
        from scadwright.graph.filter import FocusNotFound, filter_graph
        try:
            graph = filter_graph(graph, args.focus, args.depth)
        except FocusNotFound as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.format == "json":
        from scadwright.graph.render_json import render_json
        sys.stdout.write(render_json(graph))
    elif args.format == "dot":
        from scadwright.graph.render_dot import render_dot
        sys.stdout.write(render_dot(graph))
    else:
        from scadwright.graph.render_mermaid import render_mermaid
        sys.stdout.write(render_mermaid(graph))
    return 0


def _parse_imgsize(s: str) -> tuple[int, int]:
    """Parse 'WxH' (or 'W,H') into (width, height)."""
    sep = "x" if "x" in s else ","
    parts = s.split(sep)
    if len(parts) != 2:
        raise SCADwrightError(
            f"--imgsize must be 'WxH' (e.g. 1920x1080), got {s!r}"
        )
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise SCADwrightError(
            f"--imgsize dimensions must be integers, got {s!r}"
        )
    if w <= 0 or h <= 0:
        raise SCADwrightError(
            f"--imgsize dimensions must be positive, got {w}x{h}"
        )
    return w, h


_MORPH_OUTPUT_EXTS = {".apng", ".scad", ".png"}

# Common extensions users might reach for that we deliberately don't support.
# The CLI gives format-specific guidance for these rather than a bare
# "unknown extension" message — the design choice to avoid ffmpeg / Pillow
# isn't obvious to someone typing `out.mp4`.
_MORPH_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
_MORPH_GIF_EXTS = {".gif"}


def _morph_extension_error(ext: str) -> SCADwrightError:
    """Build a format-specific error for unsupported output extensions.

    Video and .gif outputs all need a heavyweight encoder (ffmpeg or Pillow);
    SCADwright stays dependency-free by exporting APNG for the in-the-box
    path and PNG sequence for the external-encoder path.
    """
    if ext in _MORPH_VIDEO_EXTS:
        return SCADwrightError(
            f"morph doesn't support {ext} output directly. SCADwright "
            f"avoids the ffmpeg dependency to keep installation simple. "
            f"Two options:\n"
            f"  - Use APNG (renders on GitHub READMEs, Discord, every "
            f"modern browser):\n"
            f"      scadwright morph SCRIPT NAME out.apng\n"
            f"  - Output a PNG sequence and encode with ffmpeg yourself:\n"
            f"      scadwright morph SCRIPT NAME frame.png --frames=N\n"
            f"      ffmpeg -framerate 30 -i frame_%04d.png "
            f"-c:v libx264 -pix_fmt yuv420p out{ext}"
        )
    if ext in _MORPH_GIF_EXTS:
        return SCADwrightError(
            f"morph doesn't support .gif output directly. APNG is the "
            f"in-the-box alternative: same coverage on modern browsers and "
            f"GitHub READMEs, without .gif's lossy 256-colour quantization "
            f"(which dithers metallic / anti-aliased 3D renders into noise).\n"
            f"  scadwright morph SCRIPT NAME out.apng\n"
            f"If you need .gif specifically for a legacy target, output a "
            f"PNG sequence and convert with ImageMagick:\n"
            f"  scadwright morph SCRIPT NAME frame.png --frames=N\n"
            f"  convert -delay 3 -loop 0 frame_*.png out.gif"
        )
    available = ", ".join(sorted(_MORPH_OUTPUT_EXTS))
    return SCADwrightError(
        f"unknown output extension {ext!r}; supported: {available}"
    )


def _cmd_morph(args: argparse.Namespace, unknown: list[str]) -> int:
    """Build a Design's morph and write it to an animation file.

    The OUTPUT extension picks the encoding path:
        - .scad → stop after building the animated SCAD.
        - .apng → render frames via OpenSCAD, encode as animated PNG.
        - .png  → render frames via OpenSCAD, rename into a sequence.
    """
    script_path = _common_setup(args, unknown)
    output_path = Path(args.output)
    ext = output_path.suffix.lower()
    if ext not in _MORPH_OUTPUT_EXTS:
        raise _morph_extension_error(ext)
    width, height = _parse_imgsize(args.imgsize)
    if args.frames < 1:
        raise SCADwrightError(f"--frames must be >= 1, got {args.frames}")

    # Resolve the morph name to a Design class.
    from scadwright.design import registered_designs

    _, designs = _import_with_fresh_design_registry(script_path)
    if not designs:
        raise SCADwrightError(
            f"{script_path.name} defines no Design subclass; cannot render morph."
        )
    morph_owner = None
    for design_cls in designs:
        if args.morph_name in getattr(design_cls, "__morphs__", {}):
            morph_owner = design_cls
            break
    if morph_owner is None:
        available = sorted({
            n
            for d in designs
            for n in getattr(d, "__morphs__", {}).keys()
        })
        if available:
            raise SCADwrightError(
                f"no morph named {args.morph_name!r}; available: {', '.join(available)}"
            )
        raise SCADwrightError(
            f"no morph named {args.morph_name!r}; {script_path.name} has no "
            f"morph declarations. Add `name = morph(start='a', end='b')` to "
            f"a Design subclass."
        )

    # Build the animated SCAD. For .scad output, write directly to OUTPUT
    # and stop. Otherwise write to a temp file.
    from scadwright.design import _render_one

    if ext == ".scad":
        scad_path = output_path
        scad_temp_dir = None
    else:
        scad_temp_dir = Path(tempfile.mkdtemp(prefix="scadwright-morph-"))
        scad_path = scad_temp_dir / "morph.scad"

    try:
        meta = morph_owner.__variants__[args.morph_name]
        _render_one(
            morph_owner, args.morph_name, meta,
            base_dir=script_path.parent,
            out_override=scad_path,
        )
        print(f"wrote {scad_path}", file=sys.stderr)

        if ext == ".scad":
            return 0

        # Render frames via OpenSCAD --animate.
        openscad = _resolve_openscad(args.openscad)
        frames_dir = Path(tempfile.mkdtemp(prefix="scadwright-morph-frames-"))
        try:
            frame_prefix = frames_dir / "frame.png"
            print(
                f"rendering {args.frames} frames at {width}x{height} via OpenSCAD...",
                file=sys.stderr,
            )
            result = subprocess.run(
                [
                    openscad,
                    "--animate", str(args.frames),
                    "--imgsize", f"{width},{height}",
                    "-o", str(frame_prefix),
                    str(scad_path),
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")
                raise SCADwrightError(
                    f"OpenSCAD exited with code {result.returncode} during "
                    f"animation render:\n{stderr}"
                )
            # Glob and sort. OpenSCAD --animate produces 5-digit zero-padded
            # filenames (frame00000.png .. frameNNNNN.png), so lex sort
            # matches numeric order.
            frames = sorted(frames_dir.glob("frame*.png"))
            if len(frames) != args.frames:
                raise SCADwrightError(
                    f"OpenSCAD wrote {len(frames)} frames; expected {args.frames}. "
                    f"Files: {[p.name for p in frames]}"
                )

            if ext == ".apng":
                from scadwright.animation._apng import write_apng
                write_apng(
                    frames, output_path,
                    fps=args.fps,
                    loop=0 if args.loop else 1,
                )
                print(f"wrote {output_path}", file=sys.stderr)
            elif ext == ".png":
                # Sequence output: OUTPUT acts as a prefix.
                stem = output_path.with_suffix("").name
                parent = output_path.parent
                parent.mkdir(parents=True, exist_ok=True)
                pad_width = max(4, len(str(len(frames))))
                for i, src in enumerate(frames):
                    dst = parent / f"{stem}_{i:0{pad_width}d}.png"
                    shutil.copy2(src, dst)
                print(
                    f"wrote {len(frames)} frames to {parent}/{stem}_*.png",
                    file=sys.stderr,
                )
        finally:
            if args.keep_frames:
                print(
                    f"--keep-frames: intermediate PNGs preserved at {frames_dir}",
                    file=sys.stderr,
                )
            else:
                shutil.rmtree(frames_dir, ignore_errors=True)
    finally:
        if scad_temp_dir is not None and not args.keep_frames:
            shutil.rmtree(scad_temp_dir, ignore_errors=True)

    return 0


_DISPATCH = {
    "build": _cmd_build,
    "preview": _cmd_preview,
    "render": _cmd_render,
    "morph": _cmd_morph,
    "lsp": _cmd_lsp,
    "graph": _cmd_graph,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args, unknown = parser.parse_known_args(argv)

    handler = _DISPATCH.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")

    try:
        return handler(args, unknown)
    except _ScriptNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except SCADwrightError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        _args.set_argv(None)


if __name__ == "__main__":
    sys.exit(main())
