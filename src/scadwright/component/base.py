"""Component base class.

A Component IS a Node (via inheritance) but is mutable, unlike the frozen
concrete AST dataclasses. Users subclass, set attributes in __init__, and
override build() to return an AST subtree.

Mutability is achieved by overriding __setattr__ on Component itself; this
bypasses the frozen-dataclass __setattr__ inherited from Node. Concrete AST
dataclasses (Cube, Translate, etc.) remain frozen because they declare their
own @dataclass(frozen=True) and don't override __setattr__.

Components can declare params declaratively via sc.Param descriptors.
__init_subclass__ collects Params into cls.__params__ and auto-generates a
kwargs-only __init__ if the subclass doesn't define one. Hand-written
__init__ (calling super().__init__(), then assigning self.x = ...) also
works.

The subclass-time setup machinery (parsing equations, auto-declaring
Params, walking the MRO) lives in ``_subclass_setup``; the auto-init
factory lives in ``_init_factory``; build-result diagnostics live in
``_build_diagnostics``. This file owns just the ``Component`` class and
the ``materialize`` public function.
"""

from __future__ import annotations

import inspect
import time

from scadwright.ast.base import Node, SourceLocation
from scadwright.api.resolution import resolution as _resolution
from scadwright.component._build_diagnostics import (
    _build_return_hint,
    _describe_build_result,
)
from scadwright.component._subclass_setup import (
    _apply_class_attr_overrides,
    _collect_anchor_defs,
    _collect_params_from_mro,
    _register_equations,
)
from scadwright.component.params import Param
from scadwright.errors import BuildError, SCADwrightError, ValidationError
from scadwright._logging import get_logger

_log = get_logger("scadwright.component")


class Component(Node):
    """Base for user-defined parametric parts.

    Subclass and override `build()` to return an AST subtree.

    Two ways to declare attributes:

    1. **Plain `__init__`** — write your own `__init__`, call
       `super().__init__()`, set `self.x = ...`.

    2. **`sc.Param` descriptors** — declare params at class scope. An
       auto-generated kwargs-only `__init__` validates inputs, solves
       `equations`, evaluates derivations, and validates predicates.

    Class attributes `fn`/`fa`/`fs` act as default resolution for primitives
    built inside `build()`. Instance attributes of the same names override.
    """

    # Class-level resolution defaults. Subclasses override as plain class vars.
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None

    # Class-level centering default. Accepts True, "xy", "xz", etc.
    center = None

    # Populated by __init_subclass__ for subclasses with Param descriptors.
    __params__: dict[str, Param] = {}

    def __setattr__(self, name, value):
        # Frozen Components refuse writes to any Param. Params cover both
        # user-supplied inputs and resolver-filled values; under the
        # unified spec those are the same category. Reassigning any of
        # them after __init__ would desync the instance from the
        # equations that produced it.
        if getattr(self, "_frozen", False):
            cls = type(self)
            if name in cls.__params__:
                raise ValidationError(
                    f"{cls.__name__} is frozen after construction; cannot "
                    f"reassign {name!r}. Create a new instance instead."
                )
        # Bypass the frozen __setattr__ inherited from Node, making Component
        # and its subclasses behave like normal Python classes.
        object.__setattr__(self, name, value)

    def __init__(self, *, _source_location: SourceLocation | None = None):
        # _source_location is an internal kwarg used by auto-generated __init__
        # methods that have already captured the caller. Plain user __init__
        # methods call super().__init__() with no args; from_instantiation_site
        # walks past scadwright frames AND the user's __init__ chain.
        if _source_location is None:
            _source_location = SourceLocation.from_instantiation_site()
        self.source_location = _source_location
        self._built_tree = None
        # Bbox cache, populated by sc.bbox() on first call. Cleared by _invalidate.
        self._bbox_cache = None
        # tree_hash cache, populated by sc.tree_hash() on first call.
        self._tree_hash_cache = None
        # Custom anchors: populated from class-scope anchor() defs during
        # __init__. Also mutable at runtime via self.anchor(...) as a final
        # escape hatch for Components that can't express an anchor declaratively.
        self._anchors: dict = {}
        # Freeze flag: set to True after __init__ for equation-using Components.
        self._frozen = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        params = _collect_params_from_mro(cls)
        _apply_class_attr_overrides(cls, params)
        _register_equations(cls, params)
        cls.__params__ = params
        cls.__anchor_defs__ = _collect_anchor_defs(cls)
        # Generate __init__ only if the subclass didn't define one, and
        # it has either Params or anchor defs that need wiring. The
        # factory is imported lazily here because _init_factory itself
        # imports Component at top — by the time this hook fires for a
        # real subclass, base.py is fully loaded and the import succeeds.
        if (params or cls.__anchor_defs__) and "__init__" not in cls.__dict__:
            from scadwright.component._init_factory import _make_param_init
            cls.__init__ = _make_param_init(cls, params)

    def build(self) -> Node:
        raise NotImplementedError(
            f"{type(self).__name__} must override build()"
        )

    def center_origin(self):
        """Return the point (x, y, z) that ``center=`` shifts to the origin.

        Default: bbox center of the built tree. Override in subclasses to
        use a different reference point (e.g. a mounting face or a hole
        center rather than the geometric center of the bounding box).
        """
        from scadwright.bbox import bbox as _bbox

        bb = _bbox(self._built_tree)
        return bb.center

    def anchor(
        self,
        name: str,
        position: tuple,
        normal: tuple,
        *,
        kind: str = "planar",
        surface_params=None,
    ) -> None:
        """Declare a named anchor on this Component at runtime.

        Prefer the class-scope ``anchor()`` descriptor — both ``at=`` and
        ``normal=`` accept string expressions, which cover conditional
        positions and conditional normals. This method is the imperative
        escape hatch for Components that genuinely can't express an anchor
        declaratively.

        ``kind`` and ``surface_params`` carry surface-type metadata for
        decoration transforms (see ``docs/add_text.md``). The default
        ``"planar"`` covers every flat face.
        """
        from scadwright.anchor import Anchor, _normalize_surface_params

        self._anchors[name] = Anchor(
            position=(float(position[0]), float(position[1]), float(position[2])),
            normal=(float(normal[0]), float(normal[1]), float(normal[2])),
            kind=kind,
            surface_params=_normalize_surface_params(surface_params),
        )

    def get_anchors(self) -> dict:
        """Return this Component's anchors: bbox-derived defaults merged with custom.

        Class-scope ``anchor()`` declarations and any runtime
        ``self.anchor(...)`` calls override the bbox-derived defaults when
        they share a name.
        """
        from scadwright.anchor import anchors_from_bbox
        from scadwright.bbox import bbox as _bbox

        bb = _bbox(self)
        result = anchors_from_bbox(bb)
        result.update(self._anchors)
        return result

    def _apply_centering(self, center_spec):
        """Wrap ``_built_tree`` in a Translate that centers the requested axes."""
        from scadwright.api._vectors import _normalize_center
        from scadwright.ast.transforms import Translate

        cx, cy, cz = self.center_origin()
        axes = _normalize_center(center_spec)
        dx = -cx if axes[0] else 0
        dy = -cy if axes[1] else 0
        dz = -cz if axes[2] else 0
        if dx or dy or dz:
            return Translate(
                v=(dx, dy, dz),
                child=self._built_tree,
                source_location=self.source_location,
            )
        return self._built_tree

    def _invoke_build(self) -> Node:
        """Call `self.build()` and coerce the result.

        `build()` may either return a Node or be a generator yielding Nodes.
        Generator form is the preferred style for composite Components: the
        framework auto-unions the yielded parts so callers don't have to
        write `parts = []; ...; return union(*parts)` boilerplate.
        """
        from scadwright.boolops import union as _union  # local: avoid import cycle

        result = self.build()
        if isinstance(result, Node):
            return result
        if inspect.isgenerator(result):
            parts = list(result)
            if not parts:
                raise BuildError(
                    f"{type(self).__name__}.build() generator yielded no parts",
                    source_location=self.source_location,
                )
            for i, p in enumerate(parts):
                if not isinstance(p, Node):
                    raise BuildError(
                        f"{type(self).__name__}.build() yielded non-Node at "
                        f"index {i}: {type(p).__name__}",
                        source_location=self.source_location,
                    )
            return parts[0] if len(parts) == 1 else _union(*parts)

        # Non-Node, non-generator return values. The base error message stays
        # the same across every shape so existing tests matching on
        # "must return a Node or yield Nodes" continue to pass; we append a
        # focused hint for the most common new-author mistakes.
        cls_name = type(self).__name__
        base = (
            f"{cls_name}.build() must return a Node or yield Nodes; "
            f"got {_describe_build_result(result)}"
        )
        hint = _build_return_hint(result)
        msg = f"{base}\nHint: {hint}" if hint else base
        raise BuildError(msg, source_location=self.source_location)

    def _get_built_tree(self) -> Node:
        """Return the materialized subtree, building and caching on first call.

        If any of fn/fa/fs are set (instance attrs win over class attrs),
        build() runs inside an implicit resolution() context so primitives
        created inside inherit those values. Same treatment for a
        ``clearances`` class attribute — inner scope wins over any outer
        ``with clearances(...)`` block, matching ``fn`` semantics.
        """
        from contextlib import ExitStack

        from scadwright.api.clearances import Clearances, clearances as _clearances_ctx

        if self._built_tree is None:
            cls_name = type(self).__name__
            fn = getattr(self, "fn", None)
            fa = getattr(self, "fa", None)
            fs = getattr(self, "fs", None)
            cls_clearances = getattr(type(self), "clearances", None)
            t0 = time.perf_counter()
            try:
                with ExitStack() as stack:
                    if fn is not None or fa is not None or fs is not None:
                        stack.enter_context(_resolution(fn=fn, fa=fa, fs=fs))
                    if isinstance(cls_clearances, Clearances):
                        stack.enter_context(_clearances_ctx(cls_clearances))
                    self._built_tree = self._invoke_build()
            except SCADwrightError as exc:
                # Add a note showing which parent Component was being built,
                # so nested failures produce a readable chain.
                loc = self.source_location
                exc.add_note(
                    f"while building {cls_name}"
                    + (f" (at {loc})" if loc else "")
                )
                raise
            except Exception as exc:
                raise BuildError(
                    f"while building {cls_name}: {exc}",
                    source_location=self.source_location,
                ) from exc
            # Apply centering after build, before caching.
            center = getattr(self, "center", None)
            if center is not None:
                self._built_tree = self._apply_centering(center)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            loc = self.source_location
            _log.info(
                "built %s in %.2fms%s",
                cls_name,
                elapsed_ms,
                f" (src: {loc})" if loc else "",
            )
        return self._built_tree

    def _invalidate(self) -> None:
        """Force rebuild + bbox + tree_hash recompute on next access."""
        self._built_tree = None
        self._bbox_cache = None
        self._tree_hash_cache = None


def materialize(component: Component) -> Node:
    """Return the (cached) built subtree of a Component."""
    return component._get_built_tree()
