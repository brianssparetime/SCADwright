"""Resolution context (scoped $fn/$fa/$fs)."""

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
