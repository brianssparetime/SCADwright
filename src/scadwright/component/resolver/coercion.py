"""Asymmetric strict type coercion for resolver-bound values.

Mirrors :meth:`scadwright.component.params.Param._coerce`: only the
lossless ``int → float`` widening is performed. A type-mismatch surfaces
``ValidationError`` immediately so a user-supplied wrong-type value is
caught with the type message rather than slipping through to a
downstream constraint failure that's harder to interpret.
"""

from __future__ import annotations

from typing import Any

from scadwright.errors import ValidationError


def _coerce_for_param(
    value: Any, param, *, name: str = "", component_name: str = "",
) -> Any:
    """Coerce ``value`` to ``param``'s declared type, asymmetrically.

    Mirrors :meth:`Param._coerce`: only the lossless ``int → float``
    widening is performed. Type mismatches raise ``ValidationError``
    immediately so a user-supplied wrong-type value surfaces with the
    type-mismatch error rather than slipping through to a downstream
    constraint-violation that's harder to interpret.
    """
    if param is None or param.type is None or value is None:
        return value
    if isinstance(value, bool) and param.type is not bool:
        prefix = f"{component_name}.{name}" if component_name and name else name or "<param>"
        raise ValidationError(
            f"{prefix}: expected {param.type.__name__}, got bool"
        )
    if isinstance(value, param.type):
        return value
    if param.type is float and isinstance(value, int):
        return float(value)
    if (
        param.type is int
        and isinstance(value, float)
        and not value.is_integer()
    ):
        prefix = f"{component_name}.{name}" if component_name and name else name or "<param>"
        raise ValidationError(
            f"{prefix}: expected int, got non-integer float {value!r} "
            f"(would silently truncate to {int(value)}; pass an int or "
            f"round explicitly if intended)."
        )
    prefix = f"{component_name}.{name}" if component_name and name else name or "<param>"
    msg = (
        f"{prefix}: expected {param.type.__name__}, got "
        f"{type(value).__name__} ({value!r})"
    )
    if getattr(param, "_auto_declared", False) and param.type is float:
        msg += (
            f"\nHint: `{name}` was auto-declared as Param(float) "
            f"from its appearance in `equations`. For a non-float value, "
            f"declare it explicitly above the equations list, e.g. "
            f"`{name} = Param(tuple)`."
        )
    raise ValidationError(msg)
