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
# Attribute-chain type resolution
# =============================================================================
#
# A reference like ``self.a.b.outer_d`` (or the equations form
# ``a.b.outer_d``) reads ``outer_d`` off the class that ``self.a.b``
# evaluates to. Resolving which class that is means walking the
# value chain hop by hop through declared Param types: ``a`` is a
# Param of the enclosing class whose type is some class A, ``b`` is
# a Param of A whose type is class B, so ``self.a.b`` is a B. The
# read extractors and the LSP rename both need this, so it lives
# here as one resolver over a precomputed class -> params map.

# Sentinel returned for the ``self`` expression: it isn't a class,
# but attribute access on it resolves against the enclosing class's
# Params.
_SELF = object()

# Key into the params map: a class's (file_path, name), matching the
# registry's own index so lookups are O(1) and identity-stable.
ClassKey = tuple[Path, str]


def _class_key(cls: ResolvedClass) -> ClassKey:
    return (cls.file_path, cls.name)


def build_params_by_class(
    registry: ClassRegistry,
    files_by_path: dict[Path, FileInfo],
    project_root: Path,
) -> dict[ClassKey, tuple[ParamRef, ...]]:
    """Extract every project class's Params once, keyed for chain
    resolution.

    Building this up front lets :func:`_resolve_chain_type` resolve
    an arbitrarily deep attribute chain with plain dict lookups
    instead of re-parsing a class body at each hop. Classes whose
    file isn't in ``files_by_path`` (couldn't be read) contribute
    an empty tuple.
    """
    out: dict[ClassKey, tuple[ParamRef, ...]] = {}
    for cls in registry.classes.values():
        file_info = files_by_path.get(cls.file_path)
        if file_info is None:
            out[_class_key(cls)] = ()
            continue
        out[_class_key(cls)] = extract_params(
            cls, file_info, registry, project_root,
        )
    return out


def _param_type(
    cls: ResolvedClass,
    name: str,
    params_by_class: dict[ClassKey, tuple[ParamRef, ...]],
) -> ResolvedClass | None:
    """Return the resolved class type of Param ``name`` on ``cls``,
    or ``None`` when ``cls`` has no such Param or its type isn't a
    project class."""
    for p in params_by_class.get(_class_key(cls), ()):
        if p.name == name:
            return p.type_resolves_to
    return None


def resolve_chain_type(
    node: ast.AST,
    enclosing_class: ResolvedClass,
    params_by_class: dict[ClassKey, tuple[ParamRef, ...]],
):
    """Resolve the class an expression evaluates to, or ``_SELF`` /
    ``None``.

    Handles ``self``, a bare Param name on the enclosing class, and
    chained attribute access through declared Param types to any
    depth. Recurses over the (finite) expression AST, so a Param
    whose type is its own class can't loop. Anything outside this
    shape — a local variable, a call, a subscript, a non-Param
    attribute — yields ``None``, which is the honest "can't know"
    answer.

    The return value is a :class:`ResolvedClass`, the ``_SELF``
    sentinel (the current instance), or ``None``. Callers that only
    want "is this a class" test ``isinstance(result, ResolvedClass)``,
    which excludes ``_SELF`` naturally.
    """
    if isinstance(node, ast.Name):
        if node.id == "self":
            return _SELF
        return _param_type(enclosing_class, node.id, params_by_class)
    if isinstance(node, ast.Attribute):
        base = resolve_chain_type(
            node.value, enclosing_class, params_by_class,
        )
        if base is _SELF:
            return _param_type(enclosing_class, node.attr, params_by_class)
        if isinstance(base, ResolvedClass):
            return _param_type(base, node.attr, params_by_class)
        return None
    return None


def _attr_owner(
    attr_node: ast.Attribute,
    enclosing_class: ResolvedClass,
    params_by_class: dict[ClassKey, tuple[ParamRef, ...]],
) -> ResolvedClass | None:
    """Return the class that ``attr_node.attr`` is read off, or
    ``None``.

    The owner is the type the node's *value* resolves to. ``_SELF``
    (a bare ``self.x`` own-Param read) and unresolvable chains both
    yield ``None`` — neither is a cross-class reference.
    """
    owner = resolve_chain_type(
        attr_node.value, enclosing_class, params_by_class,
    )
    return owner if isinstance(owner, ResolvedClass) else None


def _immediate_base_name(value_node: ast.AST) -> str:
    """The trailing identifier of an attribute chain's base, used as
    ``AttributeRead.base_name``. ``self.spec`` -> ``"spec"``;
    ``a.b`` -> ``"b"``; a bare ``Name`` -> its id."""
    if isinstance(value_node, ast.Attribute):
        return value_node.attr
    if isinstance(value_node, ast.Name):
        return value_node.id
    return ""


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
    params_by_class: dict[ClassKey, tuple[ParamRef, ...]],
) -> tuple[AttributeRead, ...]:
    """Find every ``b.attr`` (or deeper ``a.b.attr``) read in
    ``cls``'s equations, resolving the base chain through declared
    Param types to the class the attribute is read off.

    Walks every equation, constraint, and adjustment AST. For each
    attribute access, the value chain is resolved hop by hop: a
    one-hop ``spec.outer_d`` reads ``outer_d`` off ``spec``'s type;
    a deeper ``a.b.outer_d`` reads it off ``a.b``'s type. Reads
    whose base doesn't resolve to a project class (a non-Param name,
    a primitive-typed Param, a chain that breaks) are skipped.

    Returns ``()`` when the class has no equations block, no Params,
    fails parser validation, or when the equations parser can't be
    loaded (sympy isn't installed). The empty result keeps a
    surrounding graph build / rename pass robust on real projects
    where one bad block shouldn't drop the class, and on base
    installs without the ``[equations]`` extra where a graph-only
    workflow shouldn't crash.
    """
    if not params_by_class.get(_class_key(cls)):
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

    seen: set[tuple[ClassKey, str]] = set()
    out: list[AttributeRead] = []
    for node in _iter_walked_nodes(equations, constraints, adjustments):
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Attribute):
                continue
            owner = _attr_owner(sub, cls, params_by_class)
            if owner is None:
                continue
            key = (_class_key(owner), sub.attr)
            if key in seen:
                continue
            seen.add(key)
            out.append(AttributeRead(
                base_name=_immediate_base_name(sub.value),
                attr=sub.attr,
                target=owner,
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
    params_by_class: dict[ClassKey, tuple[ParamRef, ...]],
) -> tuple[AttributeRead, ...]:
    """Find every ``self.<chain>.attr`` read in ``cls``'s method
    bodies, resolving the chain through declared Param types to the
    class the attribute is read off.

    Walks the entire class body via ``ast.walk`` (every method:
    ``build``, helpers it calls, properties, anything else). For
    each attribute access, the value chain is resolved hop by hop:
    ``self.spec.outer_d`` reads ``outer_d`` off ``spec``'s type; a
    deeper ``self.a.b.outer_d`` reads it off ``a.b``'s type. Bare
    ``self.x`` reads (own-Param uses) and chains that don't resolve
    to a project class are skipped — neither is a cross-class
    reference.

    Returns ``()`` for classes with no Params.
    """
    if not params_by_class.get(_class_key(cls)):
        return ()
    seen: set[tuple[ClassKey, str]] = set()
    out: list[AttributeRead] = []
    for sub in ast.walk(cls.ast_node):
        if not isinstance(sub, ast.Attribute):
            continue
        owner = _attr_owner(sub, cls, params_by_class)
        if owner is None:
            continue
        key = (_class_key(owner), sub.attr)
        if key in seen:
            continue
        seen.add(key)
        out.append(AttributeRead(
            base_name=_immediate_base_name(sub.value),
            attr=sub.attr,
            target=owner,
        ))
    return tuple(out)


