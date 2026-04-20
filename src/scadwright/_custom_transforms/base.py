"""Custom transform registry, decorator, and Transform subclass base."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.custom import Custom
from scadwright.errors import SCADwrightError, ValidationError


class Transform:
    """Base class for custom transforms registered as classes (escape hatch).

    Subclasses define `name` and `expand(self, child, **kwargs)` returning the
    AST subtree the transform produces. Most users will use `@sc.transform`
    instead — the decorator wraps a function in an auto-generated subclass.
    """

    name: str = ""
    inline: bool = False  # True → no SCAD module hoisting; expand at use site

    def expand(self, child: Node, **kwargs) -> Node:
        raise NotImplementedError(
            f"{type(self).__name__} must implement expand(child, **kwargs)"
        )


# Module-level registry: name -> Transform instance.
_registry: dict[str, Transform] = {}


def transform(name: str, *, inline: bool = False):
    """Decorator: register a function as a custom transform.

    The function must take a Node as its first positional argument and any
    additional parameters as keyword-only. Returns the AST subtree the
    transform produces.

        @sc.transform("round_edges")
        def round_edges(node, *, r):
            return sc.minkowski(node, sc.sphere(r=r))

    After registration, `node.round_edges(r=2)` works on any Node.
    """

    def decorator(fn: Callable[..., Node]) -> Callable[..., Node]:
        _validate_signature(fn, name)

        # Auto-generate a Transform subclass that delegates to the function.
        cls = type(
            _camel_case(name),
            (Transform,),
            {
                "name": name,
                "inline": inline,
                "expand": lambda self, child, **kw: fn(child, **kw),
                "_fn": staticmethod(fn),
            },
        )
        instance = cls()
        register(name, instance)
        return fn

    return decorator


def register(name: str, t: Transform) -> None:
    """Register a Transform instance. Used by both the decorator and direct subclasses."""
    if name in _registry:
        raise SCADwrightError(f"transform {name!r} is already registered")
    _registry[name] = t


def unregister(name: str) -> None:
    """Test helper: remove a transform from the registry."""
    _registry.pop(name, None)


def get_transform(name: str) -> Transform | None:
    return _registry.get(name)


def list_transforms() -> list[str]:
    return sorted(_registry.keys())


def _validate_signature(fn: Callable, name: str) -> None:
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    if not params:
        raise SCADwrightError(
            f"transform {name!r}: function must take at least one positional argument (the child node)"
        )
    first = params[0]
    if first.kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        raise SCADwrightError(
            f"transform {name!r}: first parameter must be positional (the child node)"
        )
    for p in params[1:]:
        if p.kind in (inspect.Parameter.VAR_POSITIONAL,):
            raise SCADwrightError(
                f"transform {name!r}: *args not supported; use keyword-only parameters"
            )


def _camel_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_")) or "Transform"


# --- Node integration: dispatch transform calls via __getattr__ ---


def _node_getattr(self, attr_name: str):
    """Dynamic dispatch: if a registered transform matches, return a callable
    that builds a Custom node wrapping `self`. Falls back to raising AttributeError.
    """
    # Don't intercept dunder lookups — they should fall through to default.
    # Single-underscore names (private convention) are still dispatchable so
    # tests can register names like "_test_foo" without special-casing.
    if attr_name.startswith("__") and attr_name.endswith("__"):
        raise AttributeError(attr_name)
    t = _registry.get(attr_name)
    if t is None:
        raise AttributeError(attr_name)

    def call(**kwargs):
        loc = SourceLocation.from_caller()
        # Sort kwargs by name for stable hashing/identity.
        kw_tuple = tuple(sorted(kwargs.items()))
        return Custom(
            name=attr_name,
            kwargs=kw_tuple,
            child=self,
            source_location=loc,
        )

    return call


# Patch onto Node. Late patching keeps ast/base free of transforms-package coupling.
# Module-load runs once, so this is naturally idempotent.
if "__getattr__" not in vars(Node):
    Node.__getattr__ = _node_getattr  # type: ignore[attr-defined]
