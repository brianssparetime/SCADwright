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
    variants as methods decorated with `@variant`. Morphs (declared with
    ``name = morph(stages=[...])`` at class level) register as variants in
    their own right — they appear in ``__variants__`` so the existing
    CLI / resolver paths find them, with an extra ``__morphs__`` dict
    that the render path uses to detect and dispatch the morph case.
    """

    __variants__: dict[str, _VariantMeta] = {}
    __morphs__: dict = {}  # dict[str, _MorphSpec]; typed loosely to avoid an import cycle.

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Late import: scadwright.api.morph depends only on errors, so this
        # late-bind sidesteps any potential cycle if morph.py grows imports.
        from scadwright.api.morph import _MorphSpec

        variants: dict[str, _VariantMeta] = {}
        morphs: dict[str, _MorphSpec] = {}
        for name, value in vars(cls).items():
            meta = getattr(value, "_scadwright_variant", None)
            if meta is not None:
                variants[name] = meta
                continue
            if isinstance(value, _MorphSpec):
                morphs[name] = value
        # Synthesize a _VariantMeta for each morph so resolve_variants() finds
        # it by name. The fields are all-None: resolution / viewpoint context
        # for a morph is sourced per-end from the underlying variants at
        # render time, not from this synthesized meta. A name collision with
        # an @variant method isn't possible here — Python class-body
        # reassignment already resolved it before __init_subclass__ ran, so
        # ``vars(cls)`` shows whichever of the two appeared last; the other
        # never makes it into the namespace.
        for mname in morphs:
            variants[mname] = _VariantMeta()
        # Validate that every stage in every morph references a real
        # @variant method. Morphs may not reference other morphs — only
        # @variant-decorated methods can appear in stages.
        real_variant_names = {n for n, m in variants.items() if n not in morphs}
        for mname, spec in morphs.items():
            for i, ref in enumerate(spec.stages):
                if ref not in real_variant_names:
                    raise ValidationError(
                        f"{cls.__name__}: morph {mname!r} stages[{i}]={ref!r} "
                        f"does not reference an @variant method. Available: "
                        f"{sorted(real_variant_names)}"
                    )

        cls.__variants__ = variants
        cls.__morphs__ = morphs

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


def _primary_script_module() -> str | None:
    """Return the name of the user's primary script module if it defines
    any ``Design`` subclasses, else ``None``.

    Variant selection prefers Designs declared in the script the user
    explicitly ran over Designs pulled in transitively from imported
    sibling modules (e.g., a helper Component class that happens to
    live in another file's Design module). Two invocation paths cover
    the user-facing cases:

    - ``python foo.py`` — the script runs as ``__main__``.
    - ``scadwright build foo.py`` — the CLI loads the script as
      ``__scadwright_script__`` (see ``scadwright.cli._import_script``).

    Returns the module name (``"__main__"`` / ``"__scadwright_script__"``)
    when that module contains Designs defined in it (matched via
    ``__module__``). Returns ``None`` when no such module is found
    (pytest, REPL, embeddings) so callers fall back to global resolution.
    """
    import sys
    for name in ("__scadwright_script__", "__main__"):
        mod = sys.modules.get(name)
        if mod is None:
            continue
        for attr in vars(mod).values():
            if (isinstance(attr, type)
                    and issubclass(attr, Design)
                    and attr is not Design
                    and attr.__module__ == name):
                return name
    return None


def resolve_variants(
    variant_name: str | None,
    *,
    kind: str = "build",
) -> list[tuple[type, str, _VariantMeta]]:
    """Apply the selection rules to pick variants to run.

    Variant discovery is global (every Design registers at class-
    definition time, including those in transitively-imported modules),
    but selection prefers Designs defined in the user's primary script
    module — the file they explicitly ran via ``python foo.py`` or
    ``scadwright build foo.py``. Designs pulled in transitively (e.g.,
    a helper Component class that happens to live in a sibling Design
    module) are excluded from selection when the primary module itself
    defines any Designs.

    Rules, in order, applied to the primary module's variants when
    detected, or the global set otherwise:

        1. If exactly one variant exists:
           - If ``variant_name`` is given and doesn't match, raise.
           - Otherwise use that one variant.
        2. If ``variant_name`` is given (multiple variants exist),
           use the match; raise if not found or ambiguous.
        3. If exactly one variant is marked ``default=True``, use it.
        4. If multiple are marked ``default=True``, raise.
        5. Multiple variants, none ``default=True``: ``kind="build"``
           runs all; other kinds (preview, render) raise.
    """
    all_variants = _flatten_variants()
    if not all_variants:
        raise SCADwrightError(
            "no variants registered; define a Design subclass with "
            "@variant-decorated methods."
        )

    # Scope to the primary script module's Designs when detected; the
    # global set is a fallback for embeddings (pytest, REPL) and for
    # primary modules that don't define Designs of their own.
    primary = _primary_script_module()
    if primary is not None:
        scoped = [v for v in all_variants if v[0].__module__ == primary]
        if scoped:
            all_variants = scoped

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


def _invalidate_design_components(design_cls: type) -> None:
    """Reset cached ``_built_tree`` / bbox / tree_hash on every Component
    stored as a class-level attribute on ``design_cls`` or any of its
    base classes.

    Called before each variant render so the next render builds fresh
    under the variant's resolution / clearance / viewpoint contexts.
    Without this, two variants in the same Design class that share a
    Component (the documented class-attribute pattern) would emit the
    same baked-in resolution — whichever one happened to fill the cache
    first.
    """
    from scadwright.component.base import Component

    for klass in design_cls.__mro__:
        for val in vars(klass).values():
            if isinstance(val, Component):
                val._invalidate_full()


def _force_eager_build(node) -> None:
    """Walk ``node`` recursively, forcing eager build on every Component.

    Each Component's ``_get_built_tree()`` runs inside whatever ambient
    context (resolution / clearances / viewpoint) is active at this call
    site. Subsequent reads return the cached tree.

    Called after ``method()`` returns and before ``render()``, both
    inside the variant's context stack. This gives two guarantees:

    1. **Fail fast on build errors.** A Component that raises during
       ``build()`` surfaces the error in the variant body's wake — no
       output file is written, the traceback points at the Component,
       and the user sees the problem before any partial SCAD lands.
    2. **Cache reflects the variant's context.** Even if some future
       code path moved emit outside the context, the cache from this
       eager pass already captured the right values.

    Idempotent: a Component whose tree is already built is a cache
    read with no rebuild.
    """
    from scadwright.component.base import Component

    if isinstance(node, Component):
        built = node._get_built_tree()
        _force_eager_build(built)
        return
    children = getattr(node, "children", None)
    if children is not None:
        for c in children:
            _force_eager_build(c)
    child = getattr(node, "child", None)
    if child is not None:
        _force_eager_build(child)


def _render_one(
    design_cls: type,
    vname: str,
    meta: _VariantMeta,
    *,
    base_dir: Path | None,
    out_override: str | Path | None = None,
    cli_viewpoint: dict | None = None,
) -> Path:
    from scadwright.render import render  # avoid import cycle

    out_path = _resolve_out_path(design_cls, vname, meta, base_dir, out_override)

    # Morph dispatch: if vname names a morph, route to the morph capture
    # + build path instead of invoking a method (morphs have no method).
    if vname in getattr(design_cls, "__morphs__", {}):
        from scadwright.animation._morph_emit import build_animated_tree
        from scadwright.animation._morph_walker import walk_chain

        spec = design_cls.__morphs__[vname]
        stage_metas = [design_cls.__variants__[s] for s in spec.stages]
        instance = design_cls()

        # Capture all stages, with stages[0] captured LAST so its Component
        # cache wins. Component _built_tree reflects whichever variant
        # built it most recently; leaving stages[0]'s build last means
        # components carry stages[0]'s resolution snapshot through to the
        # final render. (The "fn inherits from the first stage" rule.)
        trees = [None] * len(spec.stages)
        for i in range(len(spec.stages) - 1, -1, -1):
            trees[i] = _capture_variant(
                design_cls, instance, spec.stages[i], stage_metas[i],
            )

        plan = walk_chain(tuple(trees), instance)
        animated = build_animated_tree(plan, spec)

        # Render inside the final stage's viewpoint context (so the
        # output SCAD's $vpr/$vpt/etc. frame the end pose, which is what
        # users typically want to look at) plus the CLI viewpoint
        # override if any. Resolution is already pinned via stages[0]'s
        # components in cache; we don't re-enter resolution context here.
        end_meta = stage_metas[-1]
        from contextlib import ExitStack
        from scadwright.animation import t as _t_var, viewpoint as _viewpoint
        with ExitStack() as stack:
            if _meta_has_viewpoint(end_meta):
                stack.enter_context(_viewpoint(
                    rotation=end_meta.rotation, target=end_meta.target,
                    distance=end_meta.distance, fov=end_meta.fov,
                ))
            if cli_viewpoint:
                stack.enter_context(_viewpoint(**cli_viewpoint))
            if spec.michael_bay:
                # 360° orbit around world z over the animation. Pitch
                # of 60° gives a looking-down-from-above 3D shot;
                # other viewpoint fields (target / distance / fov)
                # fall through from the end-stage / CLI viewpoint via
                # the nested-viewpoint merge rule.
                stack.enter_context(_viewpoint(
                    rotation=[60, 0, _t_var() * 360],
                ))
            render(animated, out_path)
        return out_path

    # Regular variant flow.
    instance = design_cls()
    method = getattr(instance, vname)

    from contextlib import ExitStack
    from scadwright.animation import viewpoint as _viewpoint
    from scadwright.api.clearances import Clearances, clearances as _clearances_ctx

    design_clearances = getattr(design_cls, "clearances", None)
    has_cli_vp = bool(cli_viewpoint)

    # Class-attribute Components (the documented Design pattern) cache
    # `_built_tree` across renders. If a prior variant render filled the
    # cache, this variant's contexts won't reach the build. Invalidate
    # before entering contexts so the next access rebuilds fresh.
    _invalidate_design_components(design_cls)

    with ExitStack() as stack:
        if _meta_has_resolution(meta):
            stack.enter_context(_resolution(fn=meta.fn, fa=meta.fa, fs=meta.fs))
        if isinstance(design_clearances, Clearances):
            stack.enter_context(_clearances_ctx(design_clearances))
        if _meta_has_viewpoint(meta):
            stack.enter_context(_viewpoint(
                rotation=meta.rotation, target=meta.target,
                distance=meta.distance, fov=meta.fov,
            ))
        if has_cli_vp:
            stack.enter_context(_viewpoint(**cli_viewpoint))
        node = method()
        # Force every Component in the tree to build now, while the
        # variant's contexts are still active. This catches build
        # errors fail-fast (no half-written output file) and pins each
        # Component's cached tree to the variant's context.
        _force_eager_build(node)
        # Render inside the context stack as well, so any emit-time
        # context reads (e.g. viewpoint) see the variant's contexts.
        render(node, out_path)

    return out_path


def _design_output_name(design_cls) -> str:
    """The stem used for output filenames: the ``name`` class attribute
    if the Design declares one, otherwise the class's ``__name__``."""
    return getattr(design_cls, "name", None) or design_cls.__name__


def _resolve_out_path(
    design_cls, vname, meta, base_dir, out_override,
) -> Path:
    if out_override is not None:
        return Path(out_override)
    out_name = meta.out or f"{_design_output_name(design_cls)}-{vname}.scad"
    out_path = Path(out_name)
    if not out_path.is_absolute() and base_dir is not None:
        out_path = base_dir / out_path
    return out_path


def _meta_has_resolution(meta) -> bool:
    return meta.fn is not None or meta.fa is not None or meta.fs is not None


def _meta_has_viewpoint(meta) -> bool:
    return (meta.rotation is not None or meta.target is not None
            or meta.distance is not None or meta.fov is not None)


def _capture_variant(design_cls, instance, vname, meta):
    """Invoke variant ``vname`` inside its full context; return the AST
    and leave Components in the design with caches reflecting this
    variant's context.

    Used by the morph dispatch to capture start and end trees with their
    proper resolution / clearance / viewpoint contexts. The variant's
    method is invoked, eager-built, and discarded as a return value of
    this helper — only the AST and Component-cache state matter.
    """
    from contextlib import ExitStack
    from scadwright.animation import viewpoint as _viewpoint
    from scadwright.api.clearances import Clearances, clearances as _clearances_ctx

    design_clearances = getattr(design_cls, "clearances", None)
    _invalidate_design_components(design_cls)
    with ExitStack() as stack:
        if _meta_has_resolution(meta):
            stack.enter_context(_resolution(fn=meta.fn, fa=meta.fa, fs=meta.fs))
        if isinstance(design_clearances, Clearances):
            stack.enter_context(_clearances_ctx(design_clearances))
        if _meta_has_viewpoint(meta):
            stack.enter_context(_viewpoint(
                rotation=meta.rotation, target=meta.target,
                distance=meta.distance, fov=meta.fov,
            ))
        method = getattr(instance, vname)
        node = method()
        _force_eager_build(node)
    return node


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
