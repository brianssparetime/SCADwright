"""Public introspection types for adjustment provenance.

The ``Adjustment`` namedtuple is what users see when they call
``component.adjustments_for(name)`` or ``component.all_adjustments()``.
One entry per applied adjustment; skipped adjustments (None
propagation) are not recorded.

The op-to-delta conversion lives here so the resolver and any future
serializers share the same convention.

The free-function helpers ``adjustments_for_lookup`` and
``all_adjustments_lookup`` carry the introspection logic that
``Component`` and ``Spec`` would otherwise duplicate. Each takes the
provenance dict, the valid-name set, and the owner-name string for
error messages, and returns the same shapes the public methods do.
"""

from __future__ import annotations

from collections import namedtuple
from typing import Any

from scadwright.errors import ValidationError


Adjustment = namedtuple("Adjustment", "line delta comment")
Adjustment.__doc__ = (
    "One applied adjustment to a name.\n\n"
    "``line`` — 1-based source-line index inside the originating "
    "``equations`` block (matches the way the user counts lines when "
    "looking at the source).\n"
    "``delta`` — for ``+=``/``-=`` the signed value added (``-=`` "
    "stored as a negative number); for ``*=``/``/=`` the "
    "multiplicative factor (``/= rhs`` stored as ``1/rhs``).\n"
    "``comment`` — trailing or preceding comment text with the leading "
    "``#`` stripped, empty string when absent."
)


def _adjustment_delta(op: str, rhs_value: Any) -> float:
    """Convert an applied ``(op, rhs_value)`` pair to the signed delta
    or factor stored in :class:`Adjustment`.

    - ``+=`` → ``rhs_value`` (additive contribution)
    - ``-=`` → ``-rhs_value`` (additive contribution, negated)
    - ``*=`` → ``rhs_value`` (multiplicative factor as written)
    - ``/=`` → ``1.0 / rhs_value`` (multiplicative factor — the
      reciprocal of the divisor — so the chain of factors composes
      via multiplication regardless of operator)

    Caller has already verified that ``rhs_value`` is non-None and that
    a ``/=`` divisor is non-zero, so this helper is total.
    """
    if op == "+=":
        return float(rhs_value)
    if op == "-=":
        return -float(rhs_value)
    if op == "*=":
        return float(rhs_value)
    if op == "/=":
        return 1.0 / float(rhs_value)
    # _split_top_level_adjustment limits ops to the four above; an
    # unrecognized op getting here is a framework bug.
    raise ValueError(f"unknown adjustment operator: {op!r}")


def adjustments_for_lookup(
    name: str,
    provenance: dict,
    valid_names: frozenset[str] | set[str],
    owner_name: str,
) -> list:
    """Shared body for ``Component.adjustments_for`` /
    ``Spec.adjustments_for``.

    Returns a fresh list of :class:`Adjustment` records (so the caller
    can mutate without affecting stored state). Raises
    :class:`ValidationError` when ``name`` is outside ``valid_names``.
    The error message names ``owner_name`` so the same helper can
    render either the Component or Spec class name in the diagnostic.
    """
    if name not in valid_names:
        raise ValidationError(
            f"{owner_name}.adjustments_for({name!r}): unknown name. "
            f"Known names: {sorted(valid_names)}."
        )
    return list(provenance.get(name, ()))


def all_adjustments_lookup(provenance: dict) -> dict:
    """Shared body for ``Component.all_adjustments`` /
    ``Spec.all_adjustments``.

    Returns a fresh dict mapping each adjusted name to a fresh list
    of records. Names that were declared but never adjusted are not
    present.
    """
    return {name: list(adjs) for name, adjs in provenance.items()}
