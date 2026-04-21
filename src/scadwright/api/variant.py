"""Render variant context (display vs. print, or any user-defined string).

Components can branch on `current_variant()` during build() to produce
different geometry for different output contexts.

`current_variant()` returns a `Variant` wrapper that supports string
comparison (`current_variant() == "print"`) with typo detection. Names that
were never activated via `variant(...)` and never pre-registered via
`register_variants(...)` trigger a `UserWarning` on comparison — catches
common typos like comparing against `"pint"`.
"""

from __future__ import annotations

import difflib
import warnings
from contextlib import contextmanager
from contextvars import ContextVar

from scadwright._logging import get_logger

_log = get_logger("scadwright.variant")


class Variant:
    """Active-variant marker. Use as a value: `current_variant() == "print"`.

    A `Variant` also behaves truthy when a variant is active:

        if current_variant():
            ...  # some variant is in effect

    Access the raw name via `.name` (which is `None` when no variant is
    active).
    """

    __slots__ = ("_name",)

    def __init__(self, name: str | None):
        self._name = name

    @property
    def name(self) -> str | None:
        return self._name

    def __eq__(self, other) -> bool:
        if isinstance(other, Variant):
            return self._name == other._name
        if isinstance(other, str):
            if other not in _known_variants:
                _warn_unknown_variant(other)
            return self._name == other
        if other is None:
            return self._name is None
        return NotImplemented

    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return NotImplemented
        return not result

    def __bool__(self) -> bool:
        return self._name is not None

    def __hash__(self) -> int:
        return hash(self._name)

    def __repr__(self) -> str:
        return f"Variant({self._name!r})"

    def __str__(self) -> str:
        return self._name if self._name is not None else ""


_current: ContextVar[str | None] = ContextVar("scadwright_variant", default=None)

# Names we've seen activated or pre-registered. Comparing current_variant()
# against a string not in this set warns.
_known_variants: set[str] = set()

# Avoid warning more than once per unknown name in a single process.
_warned_unknown: set[str] = set()


def _warn_unknown_variant(name: str) -> None:
    if name in _warned_unknown:
        return
    _warned_unknown.add(name)
    suggestion = ""
    if _known_variants:
        close = difflib.get_close_matches(name, sorted(_known_variants), n=1, cutoff=0.6)
        if close:
            suggestion = f" Did you mean {close[0]!r}?"
    known = ", ".join(sorted(_known_variants)) or "(none)"
    msg = (
        f"variant {name!r} was never activated with variant(...) nor registered "
        f"via register_variants(...).{suggestion} Known variants: {known}"
    )
    warnings.warn(msg, UserWarning, stacklevel=3)
    _log.warning(msg)


def current_variant() -> Variant:
    """Return the currently-active variant as a Variant wrapper.

    Compare with strings as usual: `current_variant() == "print"`. Comparing
    to an unknown variant name emits a UserWarning to help catch typos.
    """
    return Variant(_current.get())


def register_variants(*names: str) -> None:
    """Declare variant names this project uses, enabling typo-detection for
    comparisons against names that may not have been activated yet."""
    from scadwright.errors import ValidationError
    for n in names:
        if not isinstance(n, str) or not n:
            raise ValidationError(
                f"register_variants: names must be non-empty strings, got {n!r}"
            )
        _known_variants.add(n)


@contextmanager
def variant(name: str):
    """Set the active render variant for the duration of the block.

    The name is added to the known-variants set on entry so that subsequent
    comparisons against it never warn.
    """
    _known_variants.add(name)
    prev = _current.get()
    token = _current.set(name)
    _log.debug("enter variant=%s (was=%s)", name, prev)
    try:
        yield name
    finally:
        _current.reset(token)
        _log.debug("exit variant=%s, restored=%s", name, prev)


def _reset_for_testing() -> None:
    """Clear state between tests. Internal — don't use in user code."""
    _known_variants.clear()
    _warned_unknown.clear()
