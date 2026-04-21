"""Stable AST-based hash for regression-pinning a part's geometry.

`sc.tree_hash(node)` returns a 16-char hex string that:
- Stays the same when only `source_location` changes (e.g. moving a test file).
- Stays the same when scadwright's emitter formatting changes.
- Changes when the geometry semantically changes.

For string-level emit hashes (rare; mostly emitter debugging), users can
`hashlib.sha1(sc.emit_str(node).encode()).hexdigest()` directly.
"""

from __future__ import annotations

import hashlib
from dataclasses import fields, is_dataclass


def tree_hash(node) -> str:
    """Return a 16-char hex hash of `node`'s semantic content.

    Component instances cache the result on themselves; subsequent calls
    return the cached hash until `_invalidate()` runs. Bare AST nodes are
    hashed fresh each call (no cache; they're frozen dataclasses and the
    typical use sites don't repeat them).
    """
    from scadwright.component.base import Component

    if isinstance(node, Component):
        cached = getattr(node, "_tree_hash_cache", None)
        if cached is not None:
            return cached
        h = hashlib.sha1(repr(_canonicalize(node)).encode("utf-8")).hexdigest()[:16]
        try:
            node._tree_hash_cache = h
        except AttributeError:
            # Frozen nodes reject attribute assignment; recompute on next call.
            pass
        return h

    canonical = _canonicalize(node)
    return hashlib.sha1(repr(canonical).encode("utf-8")).hexdigest()[:16]


def _canonicalize(value):
    """Recursively turn a value into a hashable, source_location-free form."""
    from scadwright.ast.base import Node, SourceLocation
    from scadwright.ast.custom import Custom
    from scadwright.component.base import Component

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, SourceLocation):
        return None  # excluded
    if isinstance(value, Component):
        # Hash by class qualname + sorted Param values + materialized tree.
        cls = type(value)
        params = getattr(cls, "__params__", {}) or {}
        param_items = []
        for name in sorted(params.keys()):
            param_items.append((name, _canonicalize(getattr(value, name, None))))
        materialized = _canonicalize(value._get_built_tree())
        return ("Component", cls.__qualname__, tuple(param_items), materialized)
    if isinstance(value, Custom):
        return (
            "Custom",
            value.name,
            tuple((k, _canonicalize(v)) for k, v in value.kwargs),
            _canonicalize(value.child),
        )
    if isinstance(value, Node) and is_dataclass(value):
        items = []
        for f in fields(value):
            if f.name == "source_location":
                continue
            items.append((f.name, _canonicalize(getattr(value, f.name))))
        return (type(value).__name__, tuple(items))
    if isinstance(value, (list, tuple)):
        return tuple(_canonicalize(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _canonicalize(v)) for k, v in value.items()))
    # Fallback: repr-based.
    return ("repr", repr(value))
