"""Graph-specific extractors: composition (project Component
instantiation anywhere in the class body) and ``@variant`` build
targets.

The neutral per-class extractors — ``extract_params``,
``extract_equations_attribute_reads``,
``extract_build_attribute_reads``,
``extract_class_attribute_reads`` plus ``ParamRef`` /
``AttributeRead`` — live in
:mod:`scadwright.project_index.extract` so the LSP layer can use
them without depending on the graph package. This module
re-exports them for graph consumers and adds graph-only
extractors on top.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from scadwright.project_index.extract import (
    AttributeRead,
    InvalidBinding,
    ParamRef,
    _iter_walked_nodes,
    _try_build_param_info,
    ancestor_classes,
    build_effective_params_by_class,
    build_params_by_class,
    extract_build_attribute_reads,
    extract_class_attribute_reads,
    extract_equations_attribute_reads,
    extract_params,
    one_hop_param_reads,
)
from scadwright.project_index.registry import (
    ClassRegistry,
    ResolvedClass,
    resolve_name_in_file,
    resolves_to_scadwright_name,
)
from scadwright.project_index.transforms import (
    extract_transform_uses,
)
from scadwright.project_index.walk import FileInfo


__all__ = [
    "AttributeRead",
    "CompositionRef",
    "InvalidBinding",
    "ParamRef",
    "VariantInfo",
    "ancestor_classes",
    "build_effective_params_by_class",
    "build_params_by_class",
    "extract_build_attribute_reads",
    "extract_build_instantiations",
    "extract_class_attr_components",
    "extract_class_attribute_reads",
    "extract_component_instantiations",
    "extract_equations_attribute_reads",
    "extract_params",
    "extract_transform_uses",
    "extract_variants",
    "one_hop_param_reads",
]


# =============================================================================
# Composition (build()-body instantiation) extraction
# =============================================================================


@dataclass(frozen=True)
class CompositionRef:
    """One ``OtherComponent(...)`` call in a class's ``build`` method
    where the callee resolves to a project Component.

    ``target`` is the :class:`ResolvedClass` for the instantiated
    Component. Reads with no resolvable target — curated factory
    calls like ``cube(...)`` and ``union(...)``, third-party calls,
    or callees that aren't bare names — aren't surfaced; they
    aren't a Component dependency from the project's perspective.

    Calls are deduplicated by target class, so a class that
    instantiates the same child Component three times produces one
    :class:`CompositionRef`.
    """
    target: ResolvedClass


def extract_build_instantiations(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> tuple[CompositionRef, ...]:
    """Find every project-Component instantiation in ``cls``.

    Walks the entire class body via ``ast.walk`` and matches
    ``Call`` nodes whose callee resolves through the file's imports
    to a project Component. The walker descends into every method
    body — ``build``, helper methods called from ``build``,
    properties, anything else on the class — and into class-scope
    expressions like ``inner = Inner()`` attribute assignments.
    Curated primitives (``cube``, ``cylinder``, boolean ops,
    transforms) resolve to ``None`` because they aren't in the
    class registry and drop silently.

    Calls are deduplicated by ``(file_path, name)``, so a class
    that instantiates the same child Component from multiple
    places produces one :class:`CompositionRef`.

    Returns ``()`` for classes with no Component instantiations.
    """
    seen: set[tuple[Path, str]] = set()
    out: list[CompositionRef] = []
    for sub in ast.walk(cls.ast_node):
        if not isinstance(sub, ast.Call):
            continue
        target = _resolve_callee(
            sub.func, file_info, registry, project_root,
        )
        if target is None or target.category != "component":
            continue
        key = (target.file_path, target.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(CompositionRef(target=target))
    return tuple(out)


def _resolve_callee(
    func: ast.AST,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> ResolvedClass | None:
    """Resolve a ``Call.func`` expression to a :class:`ResolvedClass`,
    or ``None`` for callees that don't name a project class.

    Handles bare ``Name(X)`` and dotted ``Attribute(Name(X), Y)``
    callees. ``Subscript``-wrapped or further-nested callees are
    skipped — they're rare in scadwright and not worth the
    complexity.
    """
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        name = f"{func.value.id}.{func.attr}"
    if name is None:
        return None
    return resolve_name_in_file(name, file_info, registry, project_root)


# =============================================================================
# Class-attribute Component instantiation
# =============================================================================


def extract_class_attr_components(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> dict[str, ResolvedClass]:
    """Map class-level ``name = OtherComponent(...)`` assignments
    on ``cls`` to the Component each one instantiates.

    Two callers use this:

    - Variant analysis on Designs. Designs use class-attribute
      Component instantiation as their composition pattern
      (``holder = AA6Holder()`` at class scope), rather than
      ``Param(...)``. Variant methods then read those via
      ``self.holder``.
    - Composition detection on Components. The design doc lists
      class-attribute instantiation alongside ``build()``-body
      instantiation as a source of ``contains`` edges. The pattern
      is uncommon on real Components (``Param(...)`` usually fills
      that role), but it's syntactically valid.

    Only Component callees surface; Specs, Designs, primitive
    factories, and unresolvable names drop. Returns ``{}`` for
    classes with no class-level Component instantiation.
    """
    out: dict[str, ResolvedClass] = {}
    for stmt in cls.ast_node.body:
        binding = _class_attr_binding(stmt)
        if binding is None:
            continue
        name, call = binding
        target = _resolve_callee(
            call.func, file_info, registry, project_root,
        )
        if target is None or target.category != "component":
            continue
        out[name] = target
    return out


def _class_attr_binding(
    stmt: ast.stmt,
) -> tuple[str, ast.Call] | None:
    """Return ``(name, call)`` for a ``name = SomeCall(...)`` or
    ``name: T = SomeCall(...)`` class-attribute statement, or
    ``None`` for any other shape.

    The annotated and unannotated forms behave identically here —
    both produce one bound name and one Call expression. Multi-
    target assignments and tuple unpacking are skipped; they're
    not idiomatic for class-attribute Components.
    """
    if isinstance(stmt, ast.Assign):
        if (
            len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Call)
        ):
            return stmt.targets[0].id, stmt.value
    elif isinstance(stmt, ast.AnnAssign):
        if (
            isinstance(stmt.target, ast.Name)
            and isinstance(stmt.value, ast.Call)
        ):
            return stmt.target.id, stmt.value
    return None


# =============================================================================
# Variant extraction
# =============================================================================


@dataclass(frozen=True)
class VariantInfo:
    """One ``@variant``-decorated method on a Design class.

    ``method_name`` is the bare method name (``"print"``,
    ``"display"``). ``builds`` is the sorted-unique tuple of
    Component classes the variant body produces — direct
    instantiation calls (``Inner()``) and reads of Design class-
    level Component attributes (``self.holder`` where ``holder =
    AA6Holder()``) both surface here.

    ``default`` mirrors the decorator's ``default=True`` flag for
    rendering hints; renderers may emphasize the default variant.
    """
    method_name: str
    default: bool
    builds: tuple[ResolvedClass, ...]


def extract_variants(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> tuple[VariantInfo, ...]:
    """Walk a Design class for ``@variant``-decorated methods.

    For each variant, the method body is walked for two patterns:

    - ``Call(func=Name(X) or Attribute(Name(X), Y))`` where the
      callee resolves to a project Component — that Component is
      a build target.
    - ``Attribute(value=Name("self"), attr=X)`` where ``X`` is a
      class-level attribute on the Design that resolved to a
      project Component — that Component is a build target.

    Targets are deduplicated by ``(file_path, name)`` and the
    return tuple preserves source order of the variant methods.
    Returns ``()`` for non-Designs and Designs with no variants.
    """
    if cls.category != "design":
        return ()
    class_attrs = extract_class_attr_components(
        cls, file_info, registry, project_root,
    )
    out: list[VariantInfo] = []
    for stmt in cls.ast_node.body:
        if not isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        if not _is_variant_decorated(stmt, file_info):
            continue
        builds = _variant_build_targets(
            stmt, class_attrs, file_info, registry, project_root,
        )
        out.append(VariantInfo(
            method_name=stmt.name,
            default=_variant_is_default(stmt),
            builds=builds,
        ))
    return tuple(out)


def _is_variant_decorated(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    file_info: FileInfo,
) -> bool:
    """Return ``True`` when one of the method's decorators resolves
    to ``scadwright.variant`` (or ``scadwright.design.variant``).

    The decorator is always called (``@variant(fn=64)``), so we
    walk for ``Call.func`` shapes. Resolution chases the file's
    imports — ``from scadwright import variant`` and
    ``from scadwright.design import variant`` both work. Bare
    ``@variant`` (uncalled) isn't valid scadwright but the walker
    handles it for robustness.
    """
    for deco in method.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        name = _decorator_name(target)
        if name is None:
            continue
        if resolves_to_scadwright_name(
            name, file_info, "variant",
            ("scadwright", "scadwright.design"),
        ):
            return True
    return False


def _decorator_name(node: ast.AST) -> str | None:
    """Return the dotted name spelled by a decorator expression,
    or ``None`` when the shape isn't a bare/dotted name.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _variant_is_default(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return ``True`` when ``@variant(default=True)`` is on the
    method. False otherwise (including when the keyword isn't set).

    Looks at the decorator call's keyword arguments only; positional
    arguments aren't accepted by the real ``variant`` decorator, so
    a positional value here would be a static-analysis red flag,
    not a missing default.
    """
    for deco in method.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        for kw in deco.keywords:
            if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                return bool(kw.value.value)
    return False


def _variant_build_targets(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    class_attrs: dict[str, ResolvedClass],
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> tuple[ResolvedClass, ...]:
    """Walk a variant method body for the Components it builds.

    Two surfacing rules:

    - Direct ``OtherComponent(...)`` instantiation → that Component.
    - ``self.X`` where ``X`` is a class-level Component attribute
      on the Design → that Component.

    Targets are deduplicated by ``(file_path, name)`` and returned
    sorted by ``(module_path, name)`` for deterministic graph
    output.
    """
    seen: set[tuple[Path, str]] = set()
    out: list[ResolvedClass] = []

    def add(target: ResolvedClass) -> None:
        key = (target.file_path, target.name)
        if key in seen:
            return
        seen.add(key)
        out.append(target)

    for sub in ast.walk(method):
        if isinstance(sub, ast.Call):
            target = _resolve_callee(
                sub.func, file_info, registry, project_root,
            )
            if target is not None and target.category == "component":
                add(target)
        elif (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "self"
        ):
            target = class_attrs.get(sub.attr)
            if target is not None:
                add(target)
    out.sort(key=lambda c: (c.module_path or "", c.name))
    return tuple(out)


# =============================================================================
# Generic-scope component-instantiation walker
# =============================================================================


def extract_component_instantiations(
    scope_node: ast.AST,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> tuple[ResolvedClass, ...]:
    """Walk ``scope_node`` for every project-Component instantiation
    call and return the deduplicated Components.

    The generic-scope counterpart to :func:`extract_build_instantiations`,
    used for transform function bodies and class-style transform
    bodies (anywhere a Component might be instantiated outside a
    Component's ``build`` method or class scope). Matches ``Call``
    nodes whose callee resolves through the file's imports to a
    project Component; non-Component callees, curated primitives,
    and unresolvable names drop silently.

    Returns Components sorted by ``(module_path, name)`` for
    deterministic edge ordering downstream.
    """
    seen: set[tuple[Path, str]] = set()
    out: list[ResolvedClass] = []
    for sub in ast.walk(scope_node):
        if not isinstance(sub, ast.Call):
            continue
        target = _resolve_callee(
            sub.func, file_info, registry, project_root,
        )
        if target is None or target.category != "component":
            continue
        key = (target.file_path, target.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    out.sort(key=lambda c: (c.module_path or "", c.name))
    return tuple(out)


