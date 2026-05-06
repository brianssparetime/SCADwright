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
"""

from __future__ import annotations

import argparse
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
            f"{script_path.name} must define a top-level `MODEL` (a scadwright Node) for `scadwright build`"
        )
    return module.MODEL


def _temp_scad_path(script_path: Path, variant: str | None) -> Path:
    """A stable temp .scad path keyed on the script (and variant). Stable so
    OpenSCAD's auto-reload sees overwrites instead of accumulating files."""
    key = f"{script_path}::{variant or ''}"
    h = hashlib.sha1(key.encode()).hexdigest()[:12]
    suffix = f"-{variant}" if variant else ""
    name = f"scadwright-{script_path.stem}{suffix}-{h}.scad"
    return Path(tempfile.gettempdir()) / name


def _resolve_openscad(explicit: str | None) -> str:
    """Pick the openscad binary: --openscad flag, then $SCADWRIGHT_OPENSCAD env,
    then PATH lookup. Raise if nothing's found."""
    candidate = explicit or os.environ.get("SCADWRIGHT_OPENSCAD") or "openscad"
    found = shutil.which(candidate)
    if not found:
        raise SCADwrightError(
            f"could not find openscad binary {candidate!r} on PATH. "
            f"Install OpenSCAD, or pass --openscad PATH, or set $SCADWRIGHT_OPENSCAD."
        )
    return found


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


def _cmd_preview(args: argparse.Namespace, unknown: list[str]) -> int:
    script_path = _common_setup(args, unknown)
    openscad = _resolve_openscad(args.openscad)
    _, designs = _import_with_fresh_design_registry(script_path)
    if designs:
        scad_path = _temp_scad_path(script_path, args.variant)
        _render_design_variants(
            script_path, designs, args, kind="preview", out_override=scad_path,
        )
    else:
        scad_path = _temp_scad_path(script_path, args.variant)
        _build_to(scad_path, script_path, args)
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
    _, designs = _import_with_fresh_design_registry(script_path)
    scad_path = _temp_scad_path(script_path, args.variant)
    if designs:
        _render_design_variants(
            script_path, designs, args, kind="render", out_override=scad_path,
        )
    else:
        _build_to(scad_path, script_path, args)
    print(f"rendering {scad_path} -> {out_stl}", file=sys.stderr)
    result = subprocess.run([openscad, "-o", str(out_stl), str(scad_path)])
    if result.returncode != 0:
        raise SCADwrightError(
            f"openscad exited with code {result.returncode} while rendering {out_stl}"
        )
    print(f"wrote {out_stl}", file=sys.stderr)
    return 0


_DISPATCH = {
    "build": _cmd_build,
    "preview": _cmd_preview,
    "render": _cmd_render,
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
