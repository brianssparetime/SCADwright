"""Centralized tolerance constants and the ``tolerances()`` scoped override.

Two flavors of tolerance live in scadwright:

**User-tunable** — values that depend on the user's units, model scale,
and precision needs. A user modeling sub-mm jewelry features wants
tighter checks than a user modeling cabinetry. Exposed via
``ContextVar``-backed reader functions and the ``tolerances()`` context
manager:

- ``default_eps()`` — the eps overlap used by ``attach(fuse=True)``,
  ``boolops.fuse(...)``, and ``Node.through(...)`` when no explicit
  ``eps=`` is passed. Default ``0.01`` mm.
- ``coincidence_tol()`` — the bbox-vs-bbox face-matching tolerance used
  by ``through()``'s coincident-face detection. Default ``1e-4`` mm.

**Internal-only** — numerical safety margins and structural degeneracy
checks. These don't depend on user units; tuning them invites surprising
behavior across paths that all assume the framework's own conventions.
Defined as module-level constants:

- ``ANCHOR_PLANE_TOL`` — anchor-on-outermost-face dot-product tolerance.
- ``NORMAL_PARALLEL_TOL`` — unit-vector dot-product (coaxial check).
- ``BBOX_DEGEN_TOL`` — "non-zero bbox extent in 2 axes" threshold.
- ``AXIS_LEN_DEGEN_TOL`` — rotation/cross-product axis length minimum.
- ``ARC_CLAMP_TOL`` — sin/cos clamping margin for meridian-arc evaluation.
- ``INSCRIPTION_MARGIN`` — extra past analytical inscription depth in the
  curved-host bridge prism.
- ``POINT_IN_BBOX_TOL`` — cutter-bbox containment tolerance for the
  Difference custom-anchor propagation check.

If a real workflow needs to tune one of the internal constants, promote
it to user-tunable here in one place.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


# --- Internal constants (not user-tunable) -----------------------------------


# Anchor-on-outermost-face check in cross-section validator.
ANCHOR_PLANE_TOL = 1e-3
# Bbox extent below this is "degenerate" (line / point).
BBOX_DEGEN_TOL = 1e-3
# Unit-vector dot-product proximity for "coaxial / anti-parallel" checks.
NORMAL_PARALLEL_TOL = 1e-3
# Rotation axis length below this is "degenerate".
AXIS_LEN_DEGEN_TOL = 1e-12
# Cross-product length below this is "vectors parallel" (orient/align).
PARALLEL_CROSS_TOL = 1e-10
# Sin/cos clamping margin for arc evaluation (meridional walls).
ARC_CLAMP_TOL = 1e-9
# Extra slab past analytical inscription depth in the bridge prism.
INSCRIPTION_MARGIN = 1e-3
# Tolerance for "point inside bbox" (cutter overlap on Difference anchor
# propagation).
POINT_IN_BBOX_TOL = 1e-6
# Tolerance for per-kind geometric self-consistency checks on Anchor
# declarations (normal perpendicular to axis, position on sphere
# surface, etc.). See ``Anchor._validate_geometry``.
ANCHOR_GEOMETRY_TOL = 1e-3


# --- User-tunable values -----------------------------------------------------


_DEFAULT_EPS = 0.01
_DEFAULT_COINCIDENCE_TOL = 1e-4

_default_eps: ContextVar[float] = ContextVar(
    "scadwright_default_eps", default=_DEFAULT_EPS,
)
_coincidence_tol: ContextVar[float] = ContextVar(
    "scadwright_coincidence_tol", default=_DEFAULT_COINCIDENCE_TOL,
)


def default_eps() -> float:
    """Current default eps for ``attach(fuse=True)``, ``fuse(...)``,
    and ``through(...)`` when no explicit ``eps=`` is passed.
    """
    return _default_eps.get()


def coincidence_tol() -> float:
    """Current coincidence tolerance for ``through()``'s face-matching."""
    return _coincidence_tol.get()


@contextmanager
def tolerances(*, eps: float | None = None, coincidence: float | None = None):
    """Override user-tunable tolerance values within a scope.

    Use this for precision builds (sub-mm features), unit-converted
    models (e.g., inches → mm where the natural eps is finer), or for
    debugging coincidence-detection failures::

        from scadwright import tolerances

        with tolerances(eps=0.001):
            return self.precision_assembly()

        with tolerances(eps=0.001, coincidence=1e-5):
            return self.tight_fit_assembly()

    Inside the block, ``attach(fuse=True)``, ``boolops.fuse(...)``, and
    ``through()`` use the override when no explicit ``eps=`` is passed.
    The standalone helpers ``default_eps()`` and ``coincidence_tol()``
    return the override.

    Nested blocks compose — the inner ``tolerances()`` overrides the
    outer's values for its scope; on exit the outer values are restored.

    The internal-only constants (``ANCHOR_PLANE_TOL``,
    ``NORMAL_PARALLEL_TOL``, etc.) are not exposed here. If a real
    workflow needs to tune one, promote it to user-tunable in the
    ``tolerances`` module.
    """
    tokens = {}
    if eps is not None:
        tokens[_default_eps] = _default_eps.set(float(eps))
    if coincidence is not None:
        tokens[_coincidence_tol] = _coincidence_tol.set(float(coincidence))
    try:
        yield
    finally:
        for var, tok in tokens.items():
            var.reset(tok)
