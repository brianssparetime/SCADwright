"""Resolution context (scoped ``$fn`` / ``$fa`` / ``$fs``).

Pipeline, following a value from user code down to emitted SCAD:

1. **User input.** Either per-call kwargs (``sphere(r=5, fn=64)``) or a
   scoped ``with resolution(fn=64): ...`` block.
2. **Merge with context.** Factories call :func:`resolve`, which fills
   ``None`` kwargs from the enclosing ``resolution(...)`` block's values.
   Explicit kwargs always win; only ``None``\\ s inherit.
3. **Validate.** Factories pass the merged tuple through
   ``_require_resolution`` in ``api/_validate.py``, which rejects
   non-positive values and surfaces a good error with the call site.
4. **Store on the node.** The validated ``(fn, fa, fs)`` lands as fields
   on the emitted AST node (``Sphere.fn`` etc.).
5. **Hoist or inline at emit time.** ``SCADEmitter`` runs a pre-pass
   (``_dominant_value_for``) that looks for uniform non-None values
   across the whole tree: if every resolution-carrying node has the same
   ``fn``, it's emitted once as a file-top ``$fn = N;`` global and
   suppressed at call sites (``_fmt_fn_kwargs``). Disagreement forces
   per-call emission.

Component subclasses participate via class-level attributes (``fn = 64``
on a Component class) and per-instance kwargs; their ``build()`` runs
inside a ``resolution(...)`` scope automatically so the primitives it
constructs pick up the right defaults.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from scadwright._logging import get_logger

_log = get_logger("scadwright.resolution")


# Value type: (fn, fa, fs). Any can be None meaning "unset at this level".
_current: ContextVar[tuple[float | None, float | None, float | None]] = ContextVar(
    "scadwright_resolution", default=(None, None, None)
)


def current() -> tuple[float | None, float | None, float | None]:
    """Return the (fn, fa, fs) tuple currently in effect."""
    return _current.get()


def resolve(
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> tuple[float | None, float | None, float | None]:
    """Merge explicit kwargs with the current context. Explicit wins; context fills the rest."""
    ctx_fn, ctx_fa, ctx_fs = current()
    return (
        fn if fn is not None else ctx_fn,
        fa if fa is not None else ctx_fa,
        fs if fs is not None else ctx_fs,
    )


@contextmanager
def resolution(
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
):
    """Scope $fn/$fa/$fs for primitives built within the block.

    Nested blocks inherit unspecified values from the enclosing context.
    Explicit kwargs on primitives always win over context.
    """
    prev_fn, prev_fa, prev_fs = current()
    new_val = (
        fn if fn is not None else prev_fn,
        fa if fa is not None else prev_fa,
        fs if fs is not None else prev_fs,
    )
    token = _current.set(new_val)
    _log.debug("enter resolution fn=%s fa=%s fs=%s", *new_val)
    try:
        yield
    finally:
        _current.reset(token)
        _log.debug("exit resolution, restored to fn=%s fa=%s fs=%s", prev_fn, prev_fa, prev_fs)
