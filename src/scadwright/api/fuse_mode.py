"""Scoped opt-out of fuse-mechanism eps adjustments.

When ``disable_eps_fuse()`` is active, ``attach(fuse=True)`` and
``fuse(...)`` behave as if ``fuse`` were ``False`` — exact anchor
coincidence, no parametric extension, no cross-section slab, no
legacy bilateral shift. Anchor lookup, placement, ``orient=True``,
``angle=``, ``at_z=``, and ``through()`` composition all continue
to work — only the eps geometry is suppressed.

Use cases:
- Precision builds where any geometric tweak would shift fits or
  measured-on-bed geometry by the eps amount.
- Performance debugging in complex assemblies, where many fuses
  add up to noticeable cost in OpenSCAD.

Pattern with variants::

    @variant
    def precise(self):
        with disable_eps_fuse():
            return self.assembly()

    @variant
    def normal(self):
        return self.assembly()

The same ``assembly()`` body runs in both variants; ``fuse=True``
calls inside become exact contacts in the precise variant and get
the usual eps overlap in the normal one. No per-call edits required.

Read by ``attach()`` and ``fuse()`` at call time. The flag is held
in a ``ContextVar`` so it scopes to the with-block and restores on
exit. No snapshot pattern is needed because attach/fuse are calls,
not stored AST nodes — the dispatch decision is baked into the
returned Translate/Union node immediately.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


_enabled: ContextVar[bool] = ContextVar(
    "scadwright_fuse_enabled", default=True
)


def fuse_enabled() -> bool:
    """Return whether the fuse mechanism's eps adjustments are active.

    True by default; False inside a ``disable_eps_fuse()`` block.
    """
    return _enabled.get()


@contextmanager
def disable_eps_fuse():
    """Disable fuse-mechanism eps adjustments within this scope.

    Inside the block, ``attach(fuse=True)`` and ``fuse(...)`` behave
    as if ``fuse`` were ``False``: exact anchor coincidence, no
    parametric extension, no cross-section slab, no shift.
    """
    token = _enabled.set(False)
    try:
        yield
    finally:
        _enabled.reset(token)
