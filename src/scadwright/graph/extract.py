"""Per-class extractors for the graph builder.

Given a :class:`scadwright.graph.registry.ResolvedClass` (the
output of :func:`scadwright.graph.registry.build_class_registry`),
these extractors pull out the structured information the graph
needs from the class's body — Param declarations, equations
references, ``build()`` attribute reads — without re-parsing the
source.

The Param extractor reuses the LSP analyzer's per-statement
classifier (``_is_param_call``) and per-Param info builder
(``_build_param_info``) so the textual fields (name, type-text,
default, doc, extras) match what the LSP surfaces for hover and
completion. The graph layer adds one new field on top:
``type_resolves_to``, the :class:`ResolvedClass` corresponding to
the Param's type-text when it names another project class.

The equations extractor reuses ``_block_from_classdef`` (also
from the LSP analyzer) plus ``parse_equations_unified`` from the
resolver. Failed parses degrade gracefully — the graph still
includes the class, just without its equation-derived edges.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from scadwright.component.equations.lex import _split_logical_lines
from scadwright.component.resolver import parse_equations_unified
from scadwright.errors import ValidationError
from scadwright.graph.registry import (
    ClassRegistry,
    ResolvedClass,
    resolve_name_in_file,
)
from scadwright.graph.walk import FileInfo
from scadwright.lsp.analyze import (
    ParamInfo,
    _block_from_classdef,
    _build_param_info,
    _is_param_call,
)


@dataclass(frozen=True)
class ParamRef:
    """One Param declaration with project-aware type resolution.

    The textual fields (``name``, ``type_text``, ``default_text``,
    ``doc_text``, ``extras``) mirror :class:`ParamInfo` so callers
    can treat the two interchangeably.

    ``type_resolves_to`` is the :class:`ResolvedClass` corresponding
    to the Param's type-text when it names a project-local class
    (e.g., ``Param(BatterySpec)`` where ``BatterySpec`` is a class
    in the same project). ``None`` for primitive types
    (``Param(float)``), unresolvable references, and Params with no
    positional argument.
    """
    name: str
    type_text: str | None
    default_text: str | None
    doc_text: str | None
    extras: tuple[tuple[str, str], ...]
    type_resolves_to: ResolvedClass | None


def extract_params(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> tuple[ParamRef, ...]:
    """Walk a class's body for ``name = Param(...)`` and
    ``name: T = Param(...)`` assignments and produce a tuple of
    :class:`ParamRef` in source order.

    For each Param, the type-text (the source of the first
    positional argument, e.g., ``"BatterySpec"``) is resolved
    against the registry so the graph builder can wire a "uses
    Param of" edge to the target class without redoing import
    chasing.
    """
    out: list[ParamRef] = []
    for stmt in cls.ast_node.body:
        info = _try_build_param_info(stmt)
        if info is None:
            continue
        type_resolves_to: ResolvedClass | None = None
        if info.type_text is not None:
            type_resolves_to = resolve_name_in_file(
                info.type_text, file_info, registry, project_root,
            )
        out.append(ParamRef(
            name=info.name,
            type_text=info.type_text,
            default_text=info.default_text,
            doc_text=info.doc_text,
            extras=info.extras,
            type_resolves_to=type_resolves_to,
        ))
    return tuple(out)


def _try_build_param_info(stmt: ast.stmt) -> ParamInfo | None:
    """Return :class:`ParamInfo` for a class-level Param assignment,
    or ``None`` for any other statement shape.

    Mirrors the per-statement classification in
    :func:`scadwright.lsp.analyze._block_from_classdef`'s loop —
    just the Param branch, since the graph extractor doesn't care
    about ``equations`` here.
    """
    if isinstance(stmt, ast.Assign):
        if (
            len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and _is_param_call(stmt.value)
        ):
            return _build_param_info(
                stmt.targets[0].id, stmt.value, stmt,
            )
    elif isinstance(stmt, ast.AnnAssign):
        if (
            isinstance(stmt.target, ast.Name)
            and stmt.value is not None
            and _is_param_call(stmt.value)
        ):
            return _build_param_info(
                stmt.target.id, stmt.value, stmt,
            )
    return None


# =============================================================================
# Equations attribute-read extraction
# =============================================================================


@dataclass(frozen=True)
class AttributeRead:
    """One ``b.attr`` access where ``b`` is a Param of the source class.

    ``base_name`` is the Param name (e.g., ``"spec"``); ``attr`` is
    the attribute being read (``"outer_d"``). ``target`` is the
    :class:`ResolvedClass` of ``b``'s type when it resolves to a
    project-local class; ``None`` when the Param's type isn't a
    project class (primitive Params like ``Param(float)``, or
    Params with no positional argument).

    Reads are deduplicated by ``(base_name, attr)`` pair, so a
    Param read in three equations contributes one ``AttributeRead``.
    """
    base_name: str
    attr: str
    target: ResolvedClass | None


def extract_equations_attribute_reads(
    cls: ResolvedClass,
    file_info: FileInfo,
    params: tuple[ParamRef, ...],
) -> tuple[AttributeRead, ...]:
    """Find every ``b.attr`` read in ``cls``'s equations where ``b``
    is a Param of ``cls``.

    Walks every equation, constraint, and adjustment AST on the
    class. Reads on non-Param bases are skipped — those are either
    typos (the LSP's undeclared-attribute warning catches them) or
    references to names the graph builder doesn't model. Reads on
    primitive-typed Params are kept with ``target=None`` so the
    builder can choose whether to surface them.

    Returns ``()`` when the class has no equations block, no
    Params, fails parser validation, or when the equations parser
    can't be loaded (sympy isn't installed). The empty result
    keeps the surrounding graph build robust on real projects
    where one bad block shouldn't drop the class from the graph,
    and on base installs without the ``[equations]`` extra where
    a graph-only workflow shouldn't crash.
    """
    if not params:
        return ()
    block = _block_from_classdef(cls.ast_node, file_info.source)
    if block is None:
        return ()
    eq_lines: list[str] = []
    for host in block.hosts:
        for line in _split_logical_lines(host.raw_text):
            eq_lines.append(line.cleaned)
    if not eq_lines:
        return ()
    try:
        equations, constraints, _, _, adjustments = parse_equations_unified(
            eq_lines, class_name=block.class_name,
        )
    except (ValidationError, ImportError):
        return ()

    param_targets: dict[str, ResolvedClass | None] = {
        p.name: p.type_resolves_to for p in params
    }
    seen: set[tuple[str, str]] = set()
    out: list[AttributeRead] = []
    for node in _iter_walked_nodes(equations, constraints, adjustments):
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Attribute):
                continue
            base = sub.value
            if not isinstance(base, ast.Name):
                continue
            if base.id not in param_targets:
                continue
            key = (base.id, sub.attr)
            if key in seen:
                continue
            seen.add(key)
            out.append(AttributeRead(
                base_name=base.id,
                attr=sub.attr,
                target=param_targets[base.id],
            ))
    return tuple(out)


def _iter_walked_nodes(equations, constraints, adjustments):
    """Yield every AST node carried by parsed equations / constraints
    / adjustments, in source order. The caller walks each via
    ``ast.walk`` for further inspection.
    """
    for eq in equations:
        yield eq.lhs
        yield eq.rhs
    for c in constraints:
        yield c.expr
    for adj in adjustments:
        yield adj.rhs


# =============================================================================
# build() body attribute-read extraction
# =============================================================================


def extract_build_attribute_reads(
    cls: ResolvedClass,
    params: tuple[ParamRef, ...],
) -> tuple[AttributeRead, ...]:
    """Find every ``self.x.y`` read in ``cls``'s ``build`` method
    where ``x`` is a Param of ``cls``.

    Walks the method body via ``ast.walk`` and matches the two-deep
    pattern ``Attribute(value=Attribute(value=Name("self"), attr=x),
    attr=y)``. Bare ``self.x`` reads (own-Param uses) aren't
    recorded — they're not cross-Component edges. Deeper chains
    like ``self.x.y.z`` record ``(x, y)`` and stop, matching the
    equations extractor's same-shape behavior.

    Returns ``()`` for classes with no ``build`` method or no
    Params.
    """
    if not params:
        return ()
    method = _find_build_method(cls.ast_node)
    if method is None:
        return ()
    param_targets: dict[str, ResolvedClass | None] = {
        p.name: p.type_resolves_to for p in params
    }
    seen: set[tuple[str, str]] = set()
    out: list[AttributeRead] = []
    for sub in ast.walk(method):
        if not isinstance(sub, ast.Attribute):
            continue
        outer_value = sub.value
        if not isinstance(outer_value, ast.Attribute):
            continue
        if not isinstance(outer_value.value, ast.Name):
            continue
        if outer_value.value.id != "self":
            continue
        x = outer_value.attr
        if x not in param_targets:
            continue
        key = (x, sub.attr)
        if key in seen:
            continue
        seen.add(key)
        out.append(AttributeRead(
            base_name=x,
            attr=sub.attr,
            target=param_targets[x],
        ))
    return tuple(out)


def _find_build_method(class_node: ast.ClassDef) -> ast.FunctionDef | None:
    """Return the class's ``build`` method (or ``None``).

    Both regular and async ``build`` methods match — though async
    Components aren't standard practice, the static walker stays
    indifferent to it.
    """
    for stmt in class_node.body:
        if (
            isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
            and stmt.name == "build"
        ):
            return stmt
    return None


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
    """Find every project-Component instantiation in ``cls`` —
    both inside the ``build`` method body and at class scope.

    Two surfacing rules:

    - Class-attribute instantiation (``inner = Inner()`` at the
      class body): one ``CompositionRef`` per resolved Component.
    - ``build()``-body instantiation (``return Inner()`` etc.):
      walks the method body via ``ast.walk`` and matches ``Call``
      nodes whose callee resolves through the file's imports to a
      project Component. Curated primitives (``cube``, ``cylinder``,
      boolean ops, transforms) resolve to ``None`` because they
      aren't in the class registry — those calls drop silently.

    The two paths share a dedupe set keyed on the target's
    ``(file_path, name)``, so a class that both class-instantiates
    and build-instantiates the same child Component produces one
    edge.

    Returns ``()`` for classes with neither shape.
    """
    seen: set[tuple[Path, str]] = set()
    out: list[CompositionRef] = []

    def add(target: ResolvedClass) -> None:
        key = (target.file_path, target.name)
        if key in seen:
            return
        seen.add(key)
        out.append(CompositionRef(target=target))

    class_attrs = extract_class_attr_components(
        cls, file_info, registry, project_root,
    )
    for target in class_attrs.values():
        add(target)

    method = _find_build_method(cls.ast_node)
    if method is not None:
        for sub in ast.walk(method):
            if not isinstance(sub, ast.Call):
                continue
            target = _resolve_callee(
                sub.func, file_info, registry, project_root,
            )
            if target is None or target.category != "component":
                continue
            add(target)
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
        if not _is_variant_decorated(
            stmt, file_info, registry, project_root,
        ):
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
    registry: ClassRegistry,
    project_root: Path,
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
        if _resolves_to_scadwright_variant(
            name, file_info, registry, project_root,
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


def _resolves_to_scadwright_variant(
    name: str,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> bool:
    """Whether ``name`` resolves through the file's imports to the
    scadwright ``variant`` decorator.

    The registry handles classes, not free functions, so this does
    a small bespoke resolution: if the local name binds to an
    import whose original spelling is ``scadwright.variant`` or
    ``scadwright.design.variant`` (or any alias of those), say
    yes. The shape is parallel to how the registry resolves
    ``Component``/``Spec``/``Design`` re-exports.
    """
    head = name.split(".", 1)[0]
    rest = name[len(head) + 1:] if "." in name else None
    for imp in file_info.imports:
        if imp.local_name != head:
            continue
        if rest is None:
            target_module = imp.source_module
            target_attr = imp.source_attr
        else:
            target_module = imp.source_module
            if imp.source_attr is not None:
                target_module = (
                    f"{imp.source_module}.{imp.source_attr}"
                    if imp.source_module else imp.source_attr
                )
            target_attr = rest
        if target_attr != "variant":
            continue
        if target_module in ("scadwright", "scadwright.design"):
            return True
    return False


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
