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
    _base_to_dotted_name,
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


# =============================================================================
# Effective parameters: MRO merge + class-attribute overrides
# =============================================================================
#
# The per-class ``extract_params`` above sees only a class's own body.
# The runtime, by contrast, collects Params across the whole MRO and
# re-binds an inherited Param that a subclass shadows with a plain class
# attribute (``_collect_params_from_mro`` + ``_apply_class_attr_overrides``
# in ``component/_subclass_setup``). The functions below are the static
# mirror of that: an effective Param map per class, and the set of
# bindings a class introduces by assigning a project Spec / Component to
# an inherited Param name.
#
# Two binding shapes carry a resolved value source:
#
# - ``spec = PentaconSixMount`` — a bare class. Only a *fixed* Spec class
#   is a usable value bag (its resolved values live on the class); a
#   Component class or a parameterized Spec class is rejected at runtime
#   (see ``_reject_class_valued_override``), so static analysis flags it
#   rather than drawing an edge that the running code would never reach.
# - ``part = Widget(...)`` — a constructor call. The instance is a value
#   source whatever the category, so any project class resolves.


@dataclass(frozen=True)
class ClassAttrBinding:
    """A class-body ``name = X`` or ``name = X(...)`` whose value resolves
    to a project class.

    ``via_call`` is ``True`` for the constructor form (``X(...)``, an
    instance) and ``False`` for the bare-class form (``X``). The
    distinction decides validity: a bare Component or parameterized-Spec
    class is not a usable value, while a constructor call of any category
    is.
    """
    name: str
    target: ResolvedClass
    via_call: bool


@dataclass(frozen=True)
class InvalidBinding:
    """A bare-class binding that resolves to a project class which cannot
    serve as a parameter value: a Component class or a parameterized Spec
    class. Carried out of :func:`build_effective_params_by_class` so the
    graph can warn rather than silently drop the dependency.

    ``source`` is the class that wrote the binding; ``name`` the Param it
    shadowed; ``target`` the bound class; ``reason`` is ``"component"`` or
    ``"param_spec"``.
    """
    source: ResolvedClass
    name: str
    target: ResolvedClass
    reason: str


def _callee_name(func: ast.AST) -> str | None:
    """Dotted name of a call's callee (``Name`` or ``Name.attr``), or
    ``None`` for shapes the resolver doesn't chase."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _resolve_bases(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> list[ResolvedClass]:
    """Resolve a class's direct base expressions to project classes,
    skipping framework bases and unresolvable shapes."""
    out: list[ResolvedClass] = []
    for base_node in cls.ast_node.bases:
        name = _base_to_dotted_name(base_node)
        if name is None:
            continue
        rc = resolve_name_in_file(name, file_info, registry, project_root)
        if rc is not None and rc.category != "unknown":
            out.append(rc)
    return out


def ancestor_classes(
    cls: ResolvedClass,
    registry: ClassRegistry,
    files_by_path: dict[Path, FileInfo],
    project_root: Path,
) -> list[ResolvedClass]:
    """Every transitive project base of ``cls``, nearest first, ``cls``
    itself excluded.

    Used to gather the inherited equations and ``build`` bodies that read
    a Param a subclass binds. Deduplicated by ``(file_path, name)`` and
    cycle-guarded.
    """
    seen: set[ClassKey] = set()
    out: list[ResolvedClass] = []

    def visit(c: ResolvedClass) -> None:
        file_info = files_by_path.get(c.file_path)
        if file_info is None:
            return
        for base in _resolve_bases(c, file_info, registry, project_root):
            key = _class_key(base)
            if key in seen:
                continue
            seen.add(key)
            out.append(base)
            visit(base)

    visit(cls)
    return out


def _class_attr_bindings(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> list[ClassAttrBinding]:
    """Find class-body ``name = ProjectClass`` and ``name =
    ProjectClass(...)`` assignments.

    ``name = Param(...)`` resolves its callee to ``Param`` (not a project
    class) and drops out, so explicit Param declarations don't masquerade
    as bindings. Plain scalars, tuples, and attribute reads
    (``Spec.value``) have no class-resolving value and drop too.
    """
    out: list[ClassAttrBinding] = []
    for stmt in cls.ast_node.body:
        if isinstance(stmt, ast.Assign):
            if not (
                len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                continue
            name = stmt.targets[0].id
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            if not (
                isinstance(stmt.target, ast.Name) and stmt.value is not None
            ):
                continue
            name = stmt.target.id
            value = stmt.value
        else:
            continue

        if isinstance(value, ast.Name):
            rc = resolve_name_in_file(
                value.id, file_info, registry, project_root,
            )
            if rc is not None and rc.category != "unknown":
                out.append(ClassAttrBinding(name, rc, via_call=False))
        elif isinstance(value, ast.Call):
            callee = _callee_name(value.func)
            if callee is None:
                continue
            rc = resolve_name_in_file(
                callee, file_info, registry, project_root,
            )
            if rc is not None and rc.category != "unknown":
                out.append(ClassAttrBinding(name, rc, via_call=True))
    return out


def _spec_is_parameterized(
    spec_rc: ResolvedClass,
    files_by_path: dict[Path, FileInfo],
) -> bool:
    """Whether a Spec class declares any ``?`` optional in its equations.

    A parameterized Spec's resolved values are only available on an
    instance, so binding the bare class is invalid. Mirrors the runtime's
    ``_optional_names`` test. A spec whose equations don't parse, or that
    has none, is treated as fixed.
    """
    file_info = files_by_path.get(spec_rc.file_path)
    if file_info is None:
        return False
    block = _block_from_classdef(spec_rc.ast_node, file_info.source)
    if block is None:
        return False
    eq_lines = [
        line.cleaned
        for host in block.hosts
        for line in _split_logical_lines(host.raw_text)
    ]
    if not eq_lines:
        return False
    try:
        _, _, optional_names, _, _ = parse_equations_unified(
            eq_lines, class_name=block.class_name,
        )
    except (ValidationError, ImportError):
        return False
    return bool(optional_names)


def build_effective_params_by_class(
    registry: ClassRegistry,
    files_by_path: dict[Path, FileInfo],
    project_root: Path,
) -> tuple[
    dict[ClassKey, tuple[ParamRef, ...]],
    dict[ClassKey, dict[str, ResolvedClass]],
    list[InvalidBinding],
]:
    """Compute every class's effective Param map and its locally-introduced
    project-class bindings.

    Returns three things:

    - ``effective``: per class, the MRO-merged Params with class-attribute
      overrides applied to ``type_resolves_to``. Feed this to the read
      extractors so a subclass resolves attributes off a Param its base
      declared and it rebound. The static mirror of the runtime's
      ``_collect_params_from_mro`` + ``_apply_class_attr_overrides``.
    - ``local_bindings``: per class, the Param names this class binds to a
      project Spec / Component **and thereby establishes or changes the
      resolved type** versus what it inherited. A subclass that merely
      inherits an already-typed Param contributes nothing here, so the
      binding edge attaches once, at the class that introduces it, and
      doesn't multiply down the inheritance chain.
    - ``invalid``: bare-class bindings that resolve to a Component class or
      a parameterized Spec class — values the runtime rejects, surfaced so
      the caller can warn instead of drawing an unreachable edge.
    """
    effective: dict[ClassKey, tuple[ParamRef, ...]] = {}
    local_bindings: dict[ClassKey, dict[str, ResolvedClass]] = {}
    invalid: list[InvalidBinding] = []
    memo: dict[ClassKey, dict[str, ParamRef]] = {}
    in_progress: set[ClassKey] = set()

    def resolve(cls: ResolvedClass) -> dict[str, ParamRef]:
        key = _class_key(cls)
        if key in memo:
            return memo[key]
        if key in in_progress:
            return {}  # inheritance cycle: bail to empty, like the registry
        in_progress.add(key)
        merged: dict[str, ParamRef] = {}
        file_info = files_by_path.get(cls.file_path)
        if file_info is not None:
            for base in _resolve_bases(cls, file_info, registry, project_root):
                for name, pref in resolve(base).items():
                    merged[name] = pref
            for pref in extract_params(
                cls, file_info, registry, project_root,
            ):
                merged[pref.name] = pref
            _apply_bindings(cls, file_info, merged, key)
        in_progress.discard(key)
        memo[key] = merged
        effective[key] = tuple(merged.values())
        return merged

    def _apply_bindings(
        cls: ResolvedClass,
        file_info: FileInfo,
        merged: dict[str, ParamRef],
        key: ClassKey,
    ) -> None:
        local: dict[str, ResolvedClass] = {}
        for b in _class_attr_bindings(
            cls, file_info, registry, project_root,
        ):
            if b.name not in merged:
                # Not a Param — class-level composition (``inner =
                # Inner()`` on a Design or Component) handled elsewhere.
                continue
            if not b.via_call:
                if b.target.category == "component":
                    invalid.append(
                        InvalidBinding(cls, b.name, b.target, "component"),
                    )
                    continue
                if (
                    b.target.category == "spec"
                    and _spec_is_parameterized(b.target, files_by_path)
                ):
                    invalid.append(
                        InvalidBinding(cls, b.name, b.target, "param_spec"),
                    )
                    continue
            prev = merged.get(b.name)
            prev_type = prev.type_resolves_to if prev else None
            merged[b.name] = ParamRef(
                name=b.name,
                type_text=prev.type_text if prev else None,
                default_text=None,
                doc_text=None,
                extras=(),
                type_resolves_to=b.target,
            )
            if b.target.category in ("component", "spec") and (
                prev_type is None
                or _class_key(prev_type) != _class_key(b.target)
            ):
                local[b.name] = b.target
        if local:
            local_bindings[key] = local

    for cls in registry.classes.values():
        resolve(cls)
    return effective, local_bindings, invalid


def one_hop_param_reads(
    class_node: ast.ClassDef,
    source: str,
    param_names: frozenset[str],
) -> dict[str, set[str]]:
    """Attributes read one hop off each named Param in a class body.

    Collects ``p.attr`` in the equations and ``self.p.attr`` in any
    method for every ``p`` in ``param_names``, returning ``{p: {attr,
    ...}}``. No type resolution: the caller already knows the bound
    class for each ``p`` and only needs the attribute names that flow
    into the edge label. One hop is the whole story for a value bag —
    a Spec's attributes are scalars, so ``spec.bore_dia`` never extends
    further.
    """
    out: dict[str, set[str]] = {}

    block = _block_from_classdef(class_node, source)
    if block is not None:
        eq_lines = [
            line.cleaned
            for host in block.hosts
            for line in _split_logical_lines(host.raw_text)
        ]
        if eq_lines:
            try:
                equations, constraints, _, _, adjustments = (
                    parse_equations_unified(
                        eq_lines, class_name=block.class_name,
                    )
                )
            except (ValidationError, ImportError):
                equations = constraints = adjustments = ()
            for node in _iter_walked_nodes(
                equations, constraints, adjustments,
            ):
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Attribute)
                        and isinstance(sub.value, ast.Name)
                        and sub.value.id in param_names
                    ):
                        out.setdefault(sub.value.id, set()).add(sub.attr)

    for sub in ast.walk(class_node):
        if (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Attribute)
            and isinstance(sub.value.value, ast.Name)
            and sub.value.value.id == "self"
            and sub.value.attr in param_names
        ):
            out.setdefault(sub.value.attr, set()).add(sub.attr)

    return out


