"""Project/component/with-scope tolerance defaults for joints.

Clearances live on four named categories (sliding / press / snap / finger)
that map to the fit types the joint Components in ``shapes.joints``
produce. Each clearance flows through five override levels, highest
priority first:

1. **Per-call kwarg** — ``AlignmentPin(d=4, h=8, lead_in=1, clearance=0.3)``.
   Always wins for that one Component instance.
2. **Component class attribute** — ``class MyBracket(Component): clearances
   = Clearances(sliding=0.05)``. Pushed as an inner scope during the
   Component's ``build()`` (mirrors how ``fn`` on a Component class
   works — inner scope wins over outer ``with`` blocks).
3. **``with clearances(...)`` scope** — ContextVar-based, like
   ``resolution()``. Partial ``Clearances`` specs compose per-field via
   merging with the enclosing scope.
4. **Design class attribute** — ``class MyDesign(Design): clearances =
   ...``. Pushed as an outer scope around each variant's build.
5. **``DEFAULT_CLEARANCES``** — framework floor. All four fields are
   concrete so resolution always terminates in a real number.

``Clearances`` is a NamedTuple with ``float | None`` fields defaulting to
``None``. ``None`` means "inherit from the enclosing scope." Full specs
(``Clearances(0.1, 0.1, 0.2, 0.2)``) and partial specs
(``Clearances(sliding=0.05)``) share the same type; per-field resolution
walks the chain and takes the first non-None value.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import NamedTuple

from scadwright._logging import get_logger

_log = get_logger("scadwright.clearances")


class Clearances(NamedTuple):
    """Four named tolerance categories with optional per-field overrides.

    ``None`` in any field means "inherit from the enclosing scope." Partial
    specs (``Clearances(sliding=0.05)``) are first-class and compose with
    outer scopes per-field.
    """

    sliding: float | None = None   # Location-only fits (AlignmentPin socket)
    press:   float | None = None   # Interference fits (PressFitPeg — socket < shaft)
    snap:    float | None = None   # Through-hole fits for compliant pins (SnapPin)
    finger:  float | None = None   # Finger-joint play (TabSlot slot vs. tab)


#: Framework-level starter values. Documented as *starter values — tune for
#: your printer*. The floor of the resolution chain; all fields concrete
#: so a resolution pass always terminates with a real number.
DEFAULT_CLEARANCES = Clearances(
    sliding=0.1,
    press=0.1,
    snap=0.2,
    finger=0.2,
)


# ContextVar default is an all-None Clearances so outer scopes don't
# accidentally provide phantom values. The resolver falls back to
# DEFAULT_CLEARANCES explicitly when every scope leaves a field as None.
_current: ContextVar[Clearances] = ContextVar(
    "scadwright_clearances", default=Clearances()
)


def current_clearances() -> Clearances:
    """Return the active ``Clearances`` merged across every enclosing scope."""
    return _current.get()


@contextmanager
def clearances(spec: Clearances):
    """Scope clearances for joints constructed within the block.

    Partial specs merge with any enclosing scope per-field — each ``None``
    in ``spec`` inherits from the outer scope, each non-``None`` wins for
    that field::

        with clearances(Clearances(sliding=0.2, press=0.1, snap=0.3, finger=0.3)):
            with clearances(Clearances(sliding=0.05)):
                # Effective: sliding=0.05, press=0.1, snap=0.3, finger=0.3
                AlignmentPin(d=4, h=8, lead_in=1)
    """
    prev = _current.get()
    merged = Clearances(
        sliding=spec.sliding if spec.sliding is not None else prev.sliding,
        press=spec.press if spec.press is not None else prev.press,
        snap=spec.snap if spec.snap is not None else prev.snap,
        finger=spec.finger if spec.finger is not None else prev.finger,
    )
    token = _current.set(merged)
    _log.debug("enter clearances %s", merged)
    try:
        yield merged
    finally:
        _current.reset(token)
        _log.debug("exit clearances, restored %s", prev)


def resolve_clearance(category: str) -> float:
    """Return the concrete clearance for ``category``.

    Reads the active scope; falls through to ``DEFAULT_CLEARANCES`` when
    the scope leaves the field as ``None``. ``category`` must be one of
    ``Clearances``' field names.
    """
    ctx = _current.get()
    val = getattr(ctx, category)
    if val is not None:
        return val
    return getattr(DEFAULT_CLEARANCES, category)


__all__ = [
    "Clearances",
    "DEFAULT_CLEARANCES",
    "clearances",
    "current_clearances",
    "resolve_clearance",
]
