"""Project-defined transform discovery and indexing.

Given the per-file output of :mod:`scadwright.project_index.walk`
and the class registry from :mod:`scadwright.project_index.registry`,
this module discovers every transform a project registers — through
the ``@transform("name")`` decorator on a free function, through a
``class MyTransform(scadwright.transforms.Transform)`` subclass with
a ``name = "..."`` class attribute, or through a module-level
``register("name", MyT())`` call — and indexes them by their
registered name.

The registry's job is purely structural; it doesn't load the
project's code or invoke the runtime transform registry. The
graph builder uses the result to emit transform nodes and to
resolve chained calls like ``body.port_cutout(...)`` to the
project's transform definitions.

Three registration shapes:

- ``@transform("name", ...)`` on a module-scope free function. The
  decorator must resolve through the file's imports to scadwright's
  ``transform`` callable, and the first positional or ``name=``
  keyword argument must be an ``ast.Constant[str]``.

- ``class MyTransform(Transform): name = "registered_name"``. The
  class must inherit (directly or transitively) from
  scadwright's ``Transform`` — captured as category ``"transform"``
  by the inheritance chase in :mod:`scadwright.project_index.registry`
  — and must declare a ``name`` class attribute whose value is an
  ``ast.Constant[str]``.

- ``register("name", MyT())`` at module scope. The callee must
  resolve to scadwright's ``register``; the first positional
  argument must be an ``ast.Constant[str]``.

Non-literal registered names (computed strings, variable
references, f-strings) skip silently — static analysis can't
follow them. Duplicate registered names across the project produce
a warning; the first definition by sorted file path / source line
wins.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from scadwright.project_index.registry import (
    ClassRegistry,
    ResolvedClass,
    _module_path_for,
    resolves_to_scadwright_name,
)
from scadwright.project_index.walk import FileInfo


# Modules through which the framework exposes ``transform`` /
# ``register`` / ``Transform``. Canonical project-facing module is
# listed first; internal paths follow because some downstream code
# imports from them directly.
_TRANSFORM_DECORATOR_MODULES: tuple[str, ...] = (
    "scadwright.transforms",
    "scadwright._custom_transforms",
    "scadwright._custom_transforms.base",
)

_REGISTER_CALL_MODULES: tuple[str, ...] = (
    "scadwright._custom_transforms.base",
)


@dataclass(frozen=True)
class ResolvedTransform:
    """One project-defined transform with its registration site.

    ``identifier_name`` is the Python name carrying the
    registration: the function name for the decorator form, the
    class name for the subclass form, or ``""`` for the bare
    ``register("name", ...)`` call form.

    ``kind`` is one of ``"decorator"``, ``"subclass"``, or
    ``"register_call"``. ``ast_node`` is the underlying
    ``ast.FunctionDef`` / ``ast.ClassDef`` / ``ast.Call`` so
    downstream extractors can re-walk the body for outgoing edges
    without re-parsing.
    """
    file_path: Path
    module_path: str
    identifier_name: str
    registered_name: str
    line: int
    kind: str
    ast_node: ast.AST = field(compare=False, hash=False)


@dataclass(frozen=True)
class TransformRegistry:
    """All project-defined transforms indexed by registered name.

    ``by_name`` maps registered name to the one chosen
    :class:`ResolvedTransform`. When two definitions claim the same
    name, the first by ``(file_path, line)`` ordering wins;
    ``warnings`` records each conflict as ``(path, message)`` so
    callers can surface them alongside parse errors.
    """
    by_name: dict[str, ResolvedTransform]
    warnings: tuple[tuple[Path, str], ...] = field(default_factory=tuple)


def build_transform_registry(
    files: list[FileInfo],
    class_registry: ClassRegistry,
    project_root: Path,
) -> TransformRegistry:
    """Walk a project's files and class registry, returning every
    project-defined transform indexed by registered name.

    ``class_registry`` must already be built; class-style transforms
    are discovered by scanning it for classes whose resolved category
    is ``"transform"``. Decorator-form and register-call-form
    transforms are discovered by walking each file's module-scope
    AST in :attr:`FileInfo.tree`.

    Duplicate registrations emit warnings; the first definition by
    sorted ``(file_path, line)`` is the one kept in ``by_name``.
    """
    found: list[ResolvedTransform] = []

    for file_info in files:
        if file_info.tree is None:
            continue
        found.extend(_decorator_transforms(file_info, project_root))
        found.extend(_register_call_transforms(file_info, project_root))

    for cls in class_registry.classes.values():
        if cls.category != "transform":
            continue
        sub = _subclass_transform(cls)
        if sub is not None:
            found.append(sub)

    found.sort(key=lambda t: (str(t.file_path), t.line))

    by_name: dict[str, ResolvedTransform] = {}
    warnings: list[tuple[Path, str]] = []
    for t in found:
        existing = by_name.get(t.registered_name)
        if existing is None:
            by_name[t.registered_name] = t
            continue
        warnings.append((
            t.file_path,
            f"transform {t.registered_name!r} already registered at "
            f"{existing.file_path}:{existing.line + 1}; "
            f"this definition at line {t.line + 1} is shadowed",
        ))
    return TransformRegistry(
        by_name=by_name,
        warnings=tuple(warnings),
    )


# =============================================================================
# Decorator form: @transform("name", ...) on a module-scope function
# =============================================================================


def _decorator_transforms(
    file_info: FileInfo,
    project_root: Path,
) -> list[ResolvedTransform]:
    """Yield decorator-form transforms in one file."""
    out: list[ResolvedTransform] = []
    module_path = _module_path_for(file_info.path, project_root)
    for node in _module_scope_iter(file_info.tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            registered = _decorator_registered_name(deco, file_info)
            if registered is None:
                continue
            out.append(ResolvedTransform(
                file_path=file_info.path,
                module_path=module_path,
                identifier_name=node.name,
                registered_name=registered,
                line=node.lineno - 1,
                kind="decorator",
                ast_node=node,
            ))
            break  # one transform per function — first matching decorator wins
    return out


def _decorator_registered_name(
    deco: ast.AST,
    file_info: FileInfo,
) -> str | None:
    """Return the registered name when ``deco`` is a call to
    scadwright's transform decorator with a literal-string argument.
    """
    if not isinstance(deco, ast.Call):
        return None
    name = _dotted_name(deco.func)
    if name is None:
        return None
    if not resolves_to_scadwright_name(
        name, file_info, "transform", _TRANSFORM_DECORATOR_MODULES,
    ):
        return None
    return _string_literal_arg(deco, "name")


# =============================================================================
# register("name", instance) — module-scope call
# =============================================================================


def _register_call_transforms(
    file_info: FileInfo,
    project_root: Path,
) -> list[ResolvedTransform]:
    """Yield register-call-form transforms in one file."""
    out: list[ResolvedTransform] = []
    module_path = _module_path_for(file_info.path, project_root)
    for node in _module_scope_iter(file_info.tree):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        name = _dotted_name(call.func)
        if name is None:
            continue
        if not resolves_to_scadwright_name(
            name, file_info, "register", _REGISTER_CALL_MODULES,
        ):
            continue
        registered = _string_literal_arg(call, None)
        if registered is None:
            continue
        out.append(ResolvedTransform(
            file_path=file_info.path,
            module_path=module_path,
            identifier_name="",
            registered_name=registered,
            line=call.lineno - 1,
            kind="register_call",
            ast_node=call,
        ))
    return out


# =============================================================================
# Subclass form: class MyT(Transform): name = "registered_name"
# =============================================================================


def _subclass_transform(cls: ResolvedClass) -> ResolvedTransform | None:
    """Return a :class:`ResolvedTransform` for a Transform-subclass
    class that declares a string-literal ``name``, or ``None`` if
    no usable name is found.
    """
    for stmt in cls.ast_node.body:
        if isinstance(stmt, ast.Assign):
            if (
                len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "name"
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                return ResolvedTransform(
                    file_path=cls.file_path,
                    module_path=cls.module_path,
                    identifier_name=cls.name,
                    registered_name=stmt.value.value,
                    line=cls.line,
                    kind="subclass",
                    ast_node=cls.ast_node,
                )
        elif isinstance(stmt, ast.AnnAssign):
            if (
                isinstance(stmt.target, ast.Name)
                and stmt.target.id == "name"
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                return ResolvedTransform(
                    file_path=cls.file_path,
                    module_path=cls.module_path,
                    identifier_name=cls.name,
                    registered_name=stmt.value.value,
                    line=cls.line,
                    kind="subclass",
                    ast_node=cls.ast_node,
                )
    return None


# =============================================================================
# Shared AST helpers
# =============================================================================


def _module_scope_iter(tree: ast.Module | None):
    """Yield every AST node reachable from ``tree`` without entering
    a function or class body. Mirrors the import-discovery walker
    in :mod:`scadwright.project_index.walk`.
    """
    if tree is None:
        return
    yield from _walk_module_scope(tree)


def _walk_module_scope(node: ast.AST):
    """Recurse from ``node`` yielding every descendant that lives in
    module scope. ``FunctionDef``, ``AsyncFunctionDef``,
    ``ClassDef``, and ``Lambda`` nodes are yielded themselves but
    their bodies are not entered — names defined inside belong to
    their own scope, not the module's.
    """
    yield node
    if isinstance(
        node,
        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
    ):
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk_module_scope(child)


def _dotted_name(node: ast.AST) -> str | None:
    """Return ``"head.attr1.attr2"`` for a Name / chained Attribute
    expression, or ``None`` for other shapes.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _string_literal_arg(
    call: ast.Call,
    kwarg_name: str | None,
) -> str | None:
    """Return the registered name from a Call's argument list.

    First positional argument wins when it's an ``ast.Constant[str]``;
    failing that, ``kwarg_name=`` (when not ``None``) supplies the
    name. Non-literal values (variables, f-strings, computed
    expressions) return ``None`` so the caller can skip the
    registration silently.
    """
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    if kwarg_name is not None:
        for kw in call.keywords:
            if kw.arg == kwarg_name:
                val = kw.value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    return val.value
    return None


def extract_transform_uses(
    scope_node: ast.AST,
    transforms: TransformRegistry,
) -> tuple[ResolvedTransform, ...]:
    """Walk ``scope_node`` for chained ``<expr>.<name>(...)`` calls
    whose ``<name>`` matches a project-registered transform.

    The framework registers transforms globally at import time, so
    a chained call ``body.port_cutout(...)`` works in any file that
    triggers the transform's defining module to load — even when
    the consumer file doesn't import the transform's function
    directly. Static analysis treats registry membership as truth;
    no import-binding check is applied.

    Curated framework verbs (``.translate``, ``.rotate``) and
    method calls on unrelated objects with same-spelled methods
    drop, because they aren't in the project's transform registry.

    Returns one :class:`ResolvedTransform` per (scope, target)
    pair, deduplicated by registered name. Used by both the graph
    builder (to emit ``uses_transform`` edges) and the LSP (to
    resolve chained-call positions to a transform definition).
    """
    if not transforms.by_name:
        return ()
    seen: set[str] = set()
    out: list[ResolvedTransform] = []
    for sub in ast.walk(scope_node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if not isinstance(func, ast.Attribute):
            continue
        target = transforms.by_name.get(func.attr)
        if target is None:
            continue
        if target.registered_name in seen:
            continue
        seen.add(target.registered_name)
        out.append(target)
    return tuple(out)


__all__ = [
    "ResolvedTransform",
    "TransformRegistry",
    "build_transform_registry",
    "extract_transform_uses",
]
