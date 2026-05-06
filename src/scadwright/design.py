"""Design class and `@variant` decorator for multi-part projects with
multiple render configurations.

See docs/organizing_a_project.md for the recommended patterns.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scadwright.api.resolution import resolution as _resolution
from scadwright.errors import SCADwrightError, ValidationError


@dataclass(frozen=True)
class _VariantMeta:
    """Metadata attached to a @variant-decorated method."""

    fn: int | None = None
    fa: float | None = None
    fs: float | None = None
    out: str | None = None
    default: bool = False
    # Viewpoint (camera) settings.
    rotation: tuple | None = None
    target: tuple | None = None
    distance: float | None = None
    fov: float | None = None


def variant(
    *,
    fn: int | None = None,
    fa: float | None = None,
    fs: float | None = None,
    out: str | None = None,
    default: bool = False,
    rotation: tuple | None = None,
    target: tuple | None = None,
    distance: float | None = None,
    fov: float | None = None,
) -> Callable[[Callable], Callable]:
    """Mark a Design method as a variant. The method's return value is the
    scene Node for that variant.

    Arguments:
        fn, fa, fs: resolution applied while building this variant.
        rotation, target, distance, fov: camera viewpoint ($vpr, $vpt,
            $vpd, $vpf) applied while building this variant.
        out: output `.scad` path. Defaults to
            `f"{DesignClass.__name__}-{method_name}.scad"` in the script's
            directory.
        default: if exactly one variant in the design is marked
            `default=True`, it's rendered when no `--variant` is given.
    """

    def deco(func: Callable) -> Callable:
        func._scadwright_variant = _VariantMeta(
            fn=fn, fa=fa, fs=fs, out=out, default=default,
            rotation=rotation, target=target, distance=distance, fov=fov,
        )
        return func

    return deco


# Registry of Design subclasses loaded in the current interpreter process.
# Populated at class-definition time; never cleared outside
# `_reset_for_testing()`. The list preserves definition order so CLI output
# is deterministic. Guarded against duplicate registration so a script that
# gets imported twice (hot-reload, re-import via `importlib.reload`) still
# ends up with one entry per class. Assumes single-threaded import (normal
# Python class-definition semantics).
_designs: list[type] = []


class Design:
    """Base class for a project-scale design with one or more variants.

    Subclasses should declare shared parts as class-body statements and
    variants as methods decorated with `@variant`.
    """

    __variants__: dict[str, _VariantMeta] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        variants: dict[str, _VariantMeta] = {}
        for name, value in vars(cls).items():
            meta = getattr(value, "_scadwright_variant", None)
            if meta is not None:
                variants[name] = meta
        cls.__variants__ = variants

        defaults = [n for n, m in variants.items() if m.default]
        if len(defaults) > 1:
            raise ValidationError(
                f"{cls.__name__}: multiple variants marked default=True: {defaults}"
            )

        if cls not in _designs:
            _designs.append(cls)


def _reset_for_testing() -> None:
    """Clear the design registry. Internal — use in tests that define
    throwaway Design subclasses."""
    _designs.clear()


def registered_designs() -> list[type]:
    """Return the list of currently-registered Design subclasses."""
    return list(_designs)


def _flatten_variants() -> list[tuple[type, str, _VariantMeta]]:
    return [
        (design, vname, meta)
        for design in _designs
        for vname, meta in design.__variants__.items()
    ]


def resolve_variants(
    variant_name: str | None,
    *,
    kind: str = "build",
) -> list[tuple[type, str, _VariantMeta]]:
    """Apply the selection rules to pick variants to run.

    Rules, in order:
        1. If exactly one variant is registered across all designs:
           - If `variant_name` is given and doesn't match, raise.
           - Otherwise run that one variant.
        2. If `variant_name` is given (multiple variants exist), run it;
           raise if the named variant doesn't exist.
        3. If exactly one variant is marked default=True, run it.
        4. If multiple are marked default=True, raise.
        5. Multiple, none default=True: `kind="build"` runs all; other
           kinds (preview, render) raise.
    """
    all_variants = _flatten_variants()
    if not all_variants:
        raise SCADwrightError(
            "no variants registered; define a Design subclass with "
            "@variant-decorated methods."
        )

    if variant_name is not None:
        matches = [v for v in all_variants if v[1] == variant_name]
        if not matches:
            available = ", ".join(sorted({v[1] for v in all_variants}))
            raise SCADwrightError(
                f"no variant named {variant_name!r}; available: {available}"
            )
        if len(matches) > 1:
            qualified = ", ".join(f"{d.__name__}.{n}" for d, n, _ in matches)
            raise SCADwrightError(
                f"variant name {variant_name!r} is ambiguous across designs; "
                f"qualify with ClassName.method (e.g. {qualified.split(', ')[0]})"
            )
        return matches

    if len(all_variants) == 1:
        return all_variants

    defaults = [v for v in all_variants if v[2].default]
    if len(defaults) == 1:
        return defaults
    if len(defaults) > 1:
        names = ", ".join(f"{d.__name__}.{n}" for d, n, _ in defaults)
        raise SCADwrightError(
            f"multiple variants marked default=True across designs: {names}"
        )

    if kind == "build":
        return all_variants

    names = ", ".join(sorted({v[1] for v in all_variants}))
    raise SCADwrightError(
        f"multiple variants available ({names}); pass --variant=NAME"
    )


def _render_one(
    design_cls: type,
    vname: str,
    meta: _VariantMeta,
    *,
    base_dir: Path | None,
    out_override: str | Path | None = None,
    cli_viewpoint: dict | None = None,
) -> Path:
    from contextlib import ExitStack

    from scadwright.animation import viewpoint as _viewpoint
    from scadwright.api.clearances import Clearances, clearances as _clearances_ctx
    from scadwright.render import render  # avoid import cycle

    instance = design_cls()
    method = getattr(instance, vname)

    # Build the node inside whatever contexts the variant / Design /
    # CLI request. Variant-level viewpoint is the outer context;
    # CLI viewpoint (if any) is the inner context so it overrides.
    has_res = meta.fn is not None or meta.fa is not None or meta.fs is not None
    has_vp = (meta.rotation is not None or meta.target is not None
              or meta.distance is not None or meta.fov is not None)
    has_cli_vp = bool(cli_viewpoint)
    design_clearances = getattr(design_cls, "clearances", None)

    with ExitStack() as stack:
        if has_res:
            stack.enter_context(_resolution(fn=meta.fn, fa=meta.fa, fs=meta.fs))
        if isinstance(design_clearances, Clearances):
            stack.enter_context(_clearances_ctx(design_clearances))
        if has_vp:
            stack.enter_context(_viewpoint(
                rotation=meta.rotation, target=meta.target,
                distance=meta.distance, fov=meta.fov,
            ))
        if has_cli_vp:
            stack.enter_context(_viewpoint(**cli_viewpoint))
        node = method()

    if out_override is not None:
        out_path = Path(out_override)
    else:
        out_name = meta.out or f"{design_cls.__name__}-{vname}.scad"
        out_path = Path(out_name)
        if not out_path.is_absolute() and base_dir is not None:
            out_path = base_dir / out_path

    render(node, out_path)
    return out_path


def run(*, variant: str | None = None, kind: str = "build") -> None:
    """Entry point for a Design script's `if __name__ == "__main__":` line.

    Parses `--variant=NAME` from `sys.argv` if `variant` isn't given,
    applies the selection rules, and renders the chosen variant(s) to
    their configured output paths.
    """
    if variant is None:
        variant = _cli_variant_from_argv()

    selected = resolve_variants(variant, kind=kind)
    base_dir = _script_dir()
    for design_cls, vname, meta in selected:
        out = _render_one(design_cls, vname, meta, base_dir=base_dir)
        print(f"wrote {out}")


def _cli_variant_from_argv() -> str | None:
    for arg in sys.argv[1:]:
        if arg.startswith("--variant="):
            return arg.split("=", 1)[1]
        if arg == "--variant" and sys.argv.index(arg) + 1 < len(sys.argv):
            return sys.argv[sys.argv.index(arg) + 1]
    return None


def _script_dir() -> Path | None:
    main_mod = sys.modules.get("__main__")
    main_file = getattr(main_mod, "__file__", None)
    if main_file:
        return Path(main_file).resolve().parent
    return None


__all__ = [
    "Design",
    "variant",
    "run",
    "resolve_variants",
    "registered_designs",
]
