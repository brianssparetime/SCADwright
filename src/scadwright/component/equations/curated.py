"""Curated namespace + cardinality helpers exposed inside equations text.

``_CURATED_BUILTINS`` and ``_CURATED_MATH`` are the names available
inside derivation and predicate expressions. Anything not in these
(or in the Component's Param/derivation set) is rejected at
class-definition time. The cardinality helpers
(``exactly_one``/``at_least_one``/``at_most_one``/``all_or_none``) are
registered into the curated namespace so users can write
``exactly_one(?fillet, ?chamfer)`` etc.
"""

from __future__ import annotations

import math
from typing import Any


# =============================================================================
# Cardinality helpers (used in `equations` strings via the curated namespace)
# =============================================================================


def _exactly_one(*args: Any) -> bool:
    """True iff exactly one argument is not None."""
    return sum(1 for x in args if x is not None) == 1


def _at_least_one(*args: Any) -> bool:
    """True iff at least one argument is not None."""
    return any(x is not None for x in args)


def _at_most_one(*args: Any) -> bool:
    """True iff zero or one argument is not None. Vacuously True for ()."""
    return sum(1 for x in args if x is not None) <= 1


def _all_or_none(*args: Any) -> bool:
    """True iff every argument is None, or every argument is not None.

    Vacuously True for ().
    """
    set_count = sum(1 for x in args if x is not None)
    return set_count == 0 or set_count == len(args)


# =============================================================================
# Curated namespace for derivation and predicate evaluation
# =============================================================================


_CURATED_BUILTINS: dict[str, Any] = {
    "range": range, "tuple": tuple, "list": list, "dict": dict,
    "set": set, "frozenset": frozenset,
    "zip": zip, "enumerate": enumerate,
    "sum": sum, "abs": abs, "round": round, "len": len,
    "min": min, "max": max,
    "int": int, "float": float, "bool": bool, "str": str,
    "all": all, "any": any,
    "sorted": sorted, "reversed": reversed,
    "True": True, "False": False, "None": None,
    # Cardinality helpers. Each checks `x is not None` on every argument;
    # pair naturally with the `?` sigil (`exactly_one(?a, ?b)` etc.).
    "exactly_one": _exactly_one,
    "at_least_one": _at_least_one,
    "at_most_one": _at_most_one,
    "all_or_none": _all_or_none,
}


_CURATED_MATH: dict[str, Any] = {
    # Trig in degrees, matching SCAD and `scadwright.math` (`scmath`).
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    # Explicit conversion helpers, available for interop with raw-radian values.
    "degrees": math.degrees, "radians": math.radians,
    "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
    "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e, "inf": math.inf,
}
