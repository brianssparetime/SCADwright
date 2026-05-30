"""Per-class extractors used by both the LSP and the graph package.

Given a :class:`scadwright.project_index.registry.ResolvedClass`
(the output of :func:`scadwright.project_index.registry.build_class_registry`),
these extractors pull out the structured information consumers
need from the class's body — Param declarations, equations
attribute reads, ``build()`` attribute reads — without re-parsing
the source.

The Param extractor reuses the per-statement classifier
(``_is_param_call``) and per-Param info builder
(``_build_param_info``) from :mod:`scadwright.project_index.analyze`
so the textual fields (name, type-text, default, doc, extras)
stay identical to what the LSP surfaces for hover and completion.
The cross-file extractor adds one new field on top:
``type_resolves_to``, the :class:`ResolvedClass` corresponding to
the Param's type-text when it names another project class.

The equations extractor reuses ``_block_from_classdef`` plus
``parse_equations_unified`` from the runtime resolver. Failed
parses degrade gracefully — the graph or rename pass still
includes the class, just without its equation-derived references.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from scadwright.component.equations.lex import _split_logical_lines
from scadwright.component.resolver import parse_equations_unified
from scadwright.errors import ValidationError
from scadwright.project_index.analyze import (
    ParamInfo,
    _block_from_classdef,
    _build_param_info,
    _is_param_call,
)
from scadwright.project_index.registry import (
    ClassRegistry,
    ResolvedClass,
    resolve_name_in_file,
)
from scadwright.project_index.walk import FileInfo


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
    against the registry so the caller can wire the dependency
    edge to the target class without redoing import chasing.
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
    :func:`scadwright.project_index.analyze._block_from_classdef`'s
    loop — just the Param branch, since this extractor doesn't care
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
    references to names this extractor doesn't model. Reads on
    primitive-typed Params are kept with ``target=None`` so callers
    can choose whether to surface them.

    Returns ``()`` when the class has no equations block, no
    Params, fails parser validation, or when the equations parser
    can't be loaded (sympy isn't installed). The empty result keeps
    a surrounding graph build / rename pass robust on real projects
    where one bad block shouldn't drop the class, and on base
    installs without the ``[equations]`` extra where a graph-only
    workflow shouldn't crash.
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


def extract_class_attribute_reads(
    scope_node: ast.AST,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
    exclude_names: frozenset[str] = frozenset(),
) -> tuple[AttributeRead, ...]:
    """Find every ``X.Y`` access in ``scope_node`` where ``X``
    resolves through the file's imports to a project-local class.

    The "scope node" is any AST node whose subtree should be
    walked — a class body for class-attribute reads at class
    scope, a method body for reads inside a method, or a free
    function body for reads inside a transform. ``ast.walk`` is
    used so all nested expressions surface.

    ``exclude_names`` is the set of bare names the extractor should
    not resolve. Callers pass ``{"self"}`` plus the names of any
    Params on an enclosing class so that ``self.x.y`` reads (handled
    by :func:`extract_build_attribute_reads`) and equation-style
    Param-mediated reads (handled by
    :func:`extract_equations_attribute_reads`) don't double-emit
    through this extractor too.

    Matches the same one-level shape the other read extractors use:
    ``Attribute(value=Name(X), attr=Y)``. Deeper chains
    (``X.y.z``) still emit ``(X, y)`` via the inner attribute and
    stop; ``Y.z`` doesn't produce its own edge because Spec
    attributes are scalars, not other classes.

    Reads are deduplicated by ``(base_name, attr)``. Reads whose
    base name resolves to something that isn't a project class
    (third-party imports, primitive aliases, unresolvable names)
    drop silently — those aren't a project dependency.
    """
    seen: set[tuple[str, str]] = set()
    out: list[AttributeRead] = []
    for sub in ast.walk(scope_node):
        if not isinstance(sub, ast.Attribute):
            continue
        base = sub.value
        if not isinstance(base, ast.Name):
            continue
        if base.id in exclude_names:
            continue
        key = (base.id, sub.attr)
        if key in seen:
            continue
        target = resolve_name_in_file(
            base.id, file_info, registry, project_root,
        )
        if target is None:
            continue
        seen.add(key)
        out.append(AttributeRead(
            base_name=base.id,
            attr=sub.attr,
            target=target,
        ))
    return tuple(out)


def extract_build_attribute_reads(
    cls: ResolvedClass,
    params: tuple[ParamRef, ...],
) -> tuple[AttributeRead, ...]:
    """Find every ``self.x.y`` read in ``cls``'s method bodies
    where ``x`` is a Param of ``cls``.

    Walks the entire class body via ``ast.walk`` and matches the
    two-deep pattern ``Attribute(value=Attribute(value=Name("self"),
    attr=x), attr=y)`` anywhere it appears: inside ``build``,
    inside helper methods called from ``build``, inside properties,
    or any other method on the class. The function name keeps
    ``build_`` for compatibility but the scope covers every method.

    Bare ``self.x`` reads (own-Param uses) aren't recorded — they
    aren't cross-Component references. Deeper chains like
    ``self.x.y.z`` record ``(x, y)`` and stop, matching the
    equations extractor's same-shape behavior.

    Returns ``()`` for classes with no Params.
    """
    if not params:
        return ()
    param_targets: dict[str, ResolvedClass | None] = {
        p.name: p.type_resolves_to for p in params
    }
    seen: set[tuple[str, str]] = set()
    out: list[AttributeRead] = []
    for sub in ast.walk(cls.ast_node):
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


