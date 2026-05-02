"""Resolver-facing wrapper around the canonical type-coercion helper.

The actual asymmetric strict type check lives in
:func:`scadwright.component.params._coerce_value` so that
``Param.__set__`` and the resolver share one implementation. This
module supplies the call-site-friendly signature used by
:class:`IterativeResolver`: pass a ``Param`` object plus its name and
the owning component name, and the wrapper unpacks them into the
canonical helper.
"""

from __future__ import annotations

from typing import Any

from scadwright.component.params import _coerce_value


def _coerce_for_param(
    value: Any, param, *, name: str = "", component_name: str = "",
) -> Any:
    """Coerce ``value`` to ``param``'s declared type, asymmetrically.

    Thin wrapper over :func:`scadwright.component.params._coerce_value`
    that takes a ``Param`` (or ``None``) and unpacks its declared type
    plus the auto-declared flag. ``param=None`` and ``param.type=None``
    both short-circuit at the helper to a no-op pass-through.
    """
    if param is None:
        return value
    return _coerce_value(
        value,
        type_=param.type,
        auto_declared=getattr(param, "_auto_declared", False),
        name=name,
        component_name=component_name,
    )
