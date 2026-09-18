"""Design class and `@variant` decorator for multi-part projects with
multiple render configurations.

See docs/organizing_a_project.md for the recommended patterns.
"""

from __future__ import annotations

import copy
import functools
import sys
from contextlib import contextmanager
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
    func: Callable | None = None,
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
):
    """Mark a Design method as a variant. The method's return value is the
    scene Node for that variant.

    Write `@variant` when there's nothing to configure and
    `@variant(default=True)` when there is; both spellings do the same
    thing.

    Arguments:
        fn, fa, fs: resolution applied while building this variant.
        rotation, target, distance, fov: camera viewpoint ($vpr, $vpt,
            $vpd, $vpf) applied while building this variant.
        out: output `.scad` path. Defaults to
            `f"{DesignClass.__name__}-{method_name}.scad"` in the script's
            directory.
        default: if exactly one variant in the design is marked
            `default=True`, it's rendered when no `--variant` is given.

    Calling the decorated method applies everything it declares, so
    `design.display()` in a test script and `scadwright build` produce
    the same geometry. See `_invoke_variant` for what that involves.
    """

    def deco(f: Callable) -> Callable:
        meta = _VariantMeta(
            fn=fn, fa=fa, fs=fs, out=out, default=default,
            rotation=rotation, target=target, distance=distance, fov=fov,
        )

        @functools.wraps(f)
        def call(self):
            return _invoke_variant(self, f, meta)

        call._scadwright_variant = meta
        # The undecorated body, kept reachable for tooling that wants to
        # read the source the user actually wrote.
        call._scadwright_variant_body = f
        return call

    if func is None:
        return deco
    if not callable(func):
        raise ValidationError(
            f"variant: expected a method to decorate, got {func!r}. Every "
            f"setting on `@variant` is passed by name, so write "
            f"`@variant(default=True)` rather than `@variant(True)`."
        )
    return deco(func)


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

    Two optional class attributes control where output lands:
    ``name`` sets the filename stem (default: the class name), and
    ``out_dir`` sets the directory relative paths resolve against
    (default: next to the script).
    """

    #: Filename stem for this Design's output. Defaults to the class name.
    name: str | None = None
    #: Directory that relative output paths resolve against, itself
    #: relative to the script unless absolute. Defaults to the script's
    #: own directory.
    out_dir: str | Path | None = None

    __variants__: dict[str, _VariantMeta] = {}
    __morphs__: dict = {}  # dict[str, _MorphSpec]; typed loosely to avoid an import cycle.

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Late import: scadwright.api.morph depends only on errors, so this
        # late-bind sidesteps any potential cycle if morph.py grows imports.
        from scadwright.api.morph import _MorphSpec
        from scadwright.component.base import Component

        variants: dict[str, _VariantMeta] = {}
        morphs: dict[str, _MorphSpec] = {}
        for name, value in vars(cls).items():
            meta = getattr(value, "_scadwright_variant", None)
            if meta is not None:
                variants[name] = meta
                continue
            if isinstance(value, _MorphSpec):
                morphs[name] = value
                continue
            if isinstance(value, Component):
                # Tell the part the name it was declared under. Every
                # copy a variant call makes inherits it, and that shared
                # name is what pairs the copies as one part across a
                # morph's stages.
                value._design_attr = name
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


def _declared_parts(design_instance) -> dict[str, Any]:
    """Every piece of geometry the design declares, keyed by its name.

    Any Node counts, not only Components. A design may write a whole
    composed shape down at class scope (``lid_with_holes =
    difference(lid, holes)``), and the parts inside it need copying for
    the same reason a bare part does.

    Walks the class hierarchy base-first so a subclass redeclaring a part
    shadows its base, then lets anything set on the instance itself win.
    """
    from scadwright.ast.base import Node

    parts: dict[str, Any] = {}
    for klass in reversed(type(design_instance).__mro__):
        for name, value in vars(klass).items():
            if isinstance(value, Node):
                parts[name] = value
    for name, value in vars(design_instance).items():
        if isinstance(value, Node):
            parts[name] = value
    return parts


def _each_component(node):
    """Yield every Component in ``node``, including ``node`` itself.

    Walks the tree as declared. A Component's built subtree is not
    followed: whatever is in there came out of its ``build()`` and is
    rebuilt from scratch whenever that runs again.
    """
    from scadwright.component.base import Component

    stack = [node]
    seen: set[int] = set()
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if isinstance(n, Component):
            yield n
            continue
        for slot in ("child", "children"):
            c = getattr(n, slot, None)
            if isinstance(c, (list, tuple)):
                stack.extend(c)
            elif c is not None:
                stack.append(c)


@contextmanager
def _own_parts(design_instance):
    """Lend ``design_instance`` its own copies of the design's parts for
    the duration of the block, then put it back as it was.

    A design declares its parts once, as class attributes, and every
    variant reads the same objects. A Component is more than a
    declaration though: it caches the tree it builds and the resolution
    context it was last wrapped in. Shared, that cache lets the last
    variant to run rewrite the geometry of every tree already handed
    out, so two variants can't be held side by side and a variant's
    tree stops being stable as soon as another variant runs.

    Giving each call its own copies makes a variant's return value an
    ordinary value: built once, from its own parts, and unaffected by
    whatever runs next. The copies are taken in a single pass, so parts
    that reference each other reach their own copies rather than back
    into the shared originals. Specs are classes and stay shared, which
    is what keeps them one source of truth.

    The copies go onto the design itself rather than onto a stand-in, so
    ``self`` inside the variant body is the object the caller called,
    and anything the body sets on it behaves normally. Restoring
    afterwards is what keeps a part read straight off the design
    (``design.box``) the part as declared.
    """
    try:
        parts = copy.deepcopy(_declared_parts(design_instance))
    except Exception as exc:
        raise SCADwrightError(
            f"{type(design_instance).__name__}: could not copy this "
            f"design's parts for a variant run. Each variant builds from "
            f"its own copies so the variants can't disturb each other, "
            f"which means every part has to be copyable. Something a part "
            f"holds is not: {exc}"
        ) from exc

    previous = {
        name: design_instance.__dict__[name]
        for name in parts
        if name in design_instance.__dict__
    }
    from scadwright.component.base import Component

    for name, part in parts.items():
        # A part may carry a build from an earlier direct use
        # (`assert_fits_in(Demo.box, ...)`); drop it so the copy captures
        # this call's context instead of replaying that one's. Parts
        # reachable only through a composed declaration need this too.
        for component in _each_component(part):
            component._invalidate_full()
        if isinstance(part, Component):
            # A composed declaration holds the very same copies as the
            # bare ones, since the copy was taken in a single pass, so
            # naming the bare ones names every reference to them.
            part._design_attr = name
        setattr(design_instance, name, part)
    try:
        yield design_instance
    finally:
        for name in parts:
            if name in previous:
                setattr(design_instance, name, previous[name])
            else:
                design_instance.__dict__.pop(name, None)


def _invoke_variant(design_instance, body: Callable, meta: _VariantMeta):
    """Run one variant body and return its scene.

    Everything the ``@variant`` line declares is applied here rather than
    by the CLI, so a plain ``design.display()`` call, ``run()``, and
    ``scadwright build`` all produce the same geometry:

    - the design's parts are copied for this call (see ``_own_parts``),
    - the variant's ``fn`` / ``fa`` / ``fs`` and the design's
      ``clearances`` are in effect while the body runs,
    - every part is built before those contexts close, which pins the
      geometry to them and surfaces a failing ``build()`` at the call
      site rather than part-way through writing a file,
    - a declared camera rides home on the returned tree, since ``$vpr``
      and friends are written at emit time, long after the contexts
      here have closed.
    """
    from contextlib import ExitStack
    from scadwright.api.clearances import Clearances, clearances as _clearances_ctx

    design_clearances = getattr(type(design_instance), "clearances", None)

    with ExitStack() as stack:
        if _meta_has_resolution(meta):
            stack.enter_context(_resolution(fn=meta.fn, fa=meta.fa, fs=meta.fs))
        if isinstance(design_clearances, Clearances):
            stack.enter_context(_clearances_ctx(design_clearances))
        stack.enter_context(_own_parts(design_instance))
        node = body(design_instance)
        _force_eager_build(node)

    if _meta_has_viewpoint(meta):
        from scadwright.animation import Viewpoint
        from scadwright.ast.transforms import WithViewpoint

        node = WithViewpoint(
            child=node,
            viewpoint=Viewpoint(
                rotation=meta.rotation, target=meta.target,
                distance=meta.distance, fov=meta.fov,
            ),
        )
    return node


def _split_viewpoint(node):
    """Separate a variant's scene from the camera riding on it.

    Returns ``(tree, viewpoint_or_None)``. The morph path wants the bare
    trees: it compares the stages structurally, and takes one camera for
    the whole animation rather than one per stage.
    """
    from scadwright.ast.transforms import WithViewpoint

    if isinstance(node, WithViewpoint):
        return node.child, node.viewpoint
    return node, None


def _force_eager_build(node) -> None:
    """Walk ``node`` recursively, forcing eager build on every Component.

    Each Component's ``_get_built_tree()`` runs inside whatever ambient
    context (resolution, clearances) is active at this call site.
    Subsequent reads return the cached tree.

    Called by ``_invoke_variant`` once the body has returned and while
    the variant's contexts are still open. This gives two guarantees:

    1. **Fail fast on build errors.** A Component that raises during
       ``build()`` surfaces the error at the variant call, so the
       traceback points at the Component and nothing has been written.
    2. **The geometry is pinned to the variant's settings** before the
       tree is handed back, rather than depending on whatever context
       happens to be live whenever the tree is finally emitted.

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
        instance = design_cls()

        # Each stage call builds from its own copies of the design's
        # parts, so the stages are independent and capture order carries
        # no meaning. stages[0]'s tree is the one emit substitutes into,
        # which is where the "fn comes from the first stage" rule falls
        # out of. The per-stage cameras come off the trees here; a morph
        # has one camera for the whole animation, taken from the end.
        captured = [
            _split_viewpoint(getattr(instance, s)()) for s in spec.stages
        ]
        trees = [t for t, _ in captured]
        end_viewpoint = captured[-1][1]

        plan = walk_chain(tuple(trees))
        animated = build_animated_tree(plan, spec)

        # The end stage's camera frames the pose the animation settles
        # on, which is the one worth looking at. The CLI's flags override
        # it, and michael_bay overrides the rotation on top of both.
        from contextlib import ExitStack
        from scadwright.animation import t as _t_var, viewpoint as _viewpoint
        with ExitStack() as stack:
            if end_viewpoint is not None:
                stack.enter_context(_viewpoint(
                    rotation=end_viewpoint.rotation,
                    target=end_viewpoint.target,
                    distance=end_viewpoint.distance,
                    fov=end_viewpoint.fov,
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

    # Regular variant flow. The variant method applies its own
    # resolution, clearances and camera, so all that's left here is the
    # CLI's viewpoint override and the write itself.
    from contextlib import ExitStack
    from scadwright.animation import viewpoint as _viewpoint

    node = getattr(design_cls(), vname)()

    with ExitStack() as stack:
        if cli_viewpoint:
            stack.enter_context(_viewpoint(**cli_viewpoint))
        render(node, out_path)

    return out_path


def _design_output_name(design_cls) -> str:
    """The stem used for output filenames: the ``name`` class attribute
    if the Design declares one, otherwise the class's ``__name__``."""
    return getattr(design_cls, "name", None) or design_cls.__name__


def _resolve_out_path(
    design_cls, vname, meta, base_dir, out_override,
) -> Path:
    """Where this variant's ``.scad`` goes.

    Precedence, most specific first: the CLI's ``-o``, then the
    variant's own ``out=``, then the Design's ``name`` and ``out_dir``,
    then the defaults (the class name, next to the script). Anything
    absolute stops the search, so ``out_dir`` only ever redirects a
    relative path.
    """
    if out_override is not None:
        return Path(out_override)
    out_name = meta.out or f"{_design_output_name(design_cls)}-{vname}.scad"
    out_path = Path(out_name)
    if out_path.is_absolute():
        return out_path

    out_dir = getattr(design_cls, "out_dir", None)
    if out_dir is not None:
        out_path = Path(out_dir) / out_path
        if out_path.is_absolute():
            return out_path
    if base_dir is not None:
        out_path = base_dir / out_path
    return out_path


def _meta_has_resolution(meta) -> bool:
    return meta.fn is not None or meta.fa is not None or meta.fs is not None


def _meta_has_viewpoint(meta) -> bool:
    return (meta.rotation is not None or meta.target is not None
            or meta.distance is not None or meta.fov is not None)


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
