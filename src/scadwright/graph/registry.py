"""Whole-project class registry with category resolution.

Given the per-file output of :mod:`scadwright.graph.walk`, this
module determines for every discovered class whether it derives
from :class:`scadwright.Component`, :class:`scadwright.Spec`, or
:class:`scadwright.Design` — directly or via project-local
intermediate base classes — and stores the result in a
:class:`ClassRegistry`.

The resolver walks each class's base expressions and chases names
through three layers:

1. The file's own imports (``Import``/``ImportFrom`` bindings
   captured by the walker).
2. Project-local class definitions in the same module.
3. Project-local re-exports across modules (``from .helpers import
   LocalBase``, where ``LocalBase`` lives in another file).

Recursion through project-local bases is cycle-guarded — a class
that recurses into its own ancestry resolves to ``unknown`` rather
than looping. Bases that don't resolve cleanly (third-party
classes, generic-subscript shapes, complex expressions) are
silently treated as unknown; the graph still gets built around
them.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from scadwright.graph.walk import ClassDefInfo, FileInfo, ImportInfo


# Base-class categories. The values are the canonical category
# strings used throughout the graph code.
_SCADWRIGHT_BASE_CATEGORY: dict[str, str] = {
    "Component": "component",
    "Spec": "spec",
    "Design": "design",
}


@dataclass(frozen=True)
class ResolvedClass:
    """A class whose category has been determined via inheritance
    chasing.

    ``category`` is one of ``"component"``, ``"spec"``, ``"design"``,
    or ``"unknown"``. ``module_path`` is the dotted Python path
    relative to the project root (e.g., ``"sub.foo"``); empty for
    files that aren't reachable from the project root.

    ``ast_node`` is preserved so downstream extractors (Param
    walker, equations walker, ``build()`` walker) can re-walk the
    body without re-parsing.
    """
    file_path: Path
    name: str
    module_path: str
    category: str
    line: int
    ast_node: ast.ClassDef


@dataclass(frozen=True)
class ClassRegistry:
    """All resolved classes from a project, indexed two ways.

    ``classes`` is the primary index by ``(file_path, class_name)``.
    ``by_module`` is a secondary index by dotted module path; both
    point at the same :class:`ResolvedClass` instances.
    """
    classes: dict[tuple[Path, str], ResolvedClass]
    by_module: dict[str, dict[str, ResolvedClass]]


def build_class_registry(
    files: list[FileInfo],
    project_root: Path,
) -> ClassRegistry:
    """Build the project-wide class registry.

    ``files`` is the output of :func:`scadwright.graph.walk.walk_project`.
    ``project_root`` is the directory rooted module paths against;
    typically the directory passed to ``walk_project`` (or, for a
    single-file run, that file's parent).

    Files with parse errors are skipped — their ``parse_error`` is
    already exposed on the ``FileInfo`` and the caller can surface
    it separately. Classes inside such files don't appear in the
    registry at all.
    """
    files_by_module: dict[str, FileInfo] = {}
    classes_by_module: dict[str, dict[str, tuple[FileInfo, ClassDefInfo]]] = {}
    for file_info in files:
        if file_info.parse_error is not None:
            continue
        module = _module_path_for(file_info.path, project_root)
        files_by_module[module] = file_info
        for cls in file_info.classes:
            classes_by_module.setdefault(module, {})[cls.name] = (
                file_info, cls,
            )

    resolved: dict[tuple[Path, str], ResolvedClass] = {}
    in_progress: set[tuple[Path, str]] = set()
    by_module: dict[str, dict[str, ResolvedClass]] = {}

    def categorize(file_info: FileInfo, cls: ClassDefInfo) -> str:
        key = (file_info.path, cls.name)
        if key in resolved:
            return resolved[key].category
        if key in in_progress:
            # Inheritance cycle — bail out; we'll resolve to unknown.
            return "unknown"
        in_progress.add(key)
        category = "unknown"
        for base_node in cls.ast_node.bases:
            base_name = _base_to_dotted_name(base_node)
            if base_name is None:
                continue
            cat = _resolve_to_category(
                base_name,
                file_info,
                files_by_module,
                classes_by_module,
                project_root,
                categorize,
            )
            if cat in _SCADWRIGHT_BASE_CATEGORY.values():
                category = cat
                break
        in_progress.discard(key)
        module_path = _module_path_for(file_info.path, project_root)
        rc = ResolvedClass(
            file_path=file_info.path,
            name=cls.name,
            module_path=module_path,
            category=category,
            line=cls.line,
            ast_node=cls.ast_node,
        )
        resolved[key] = rc
        by_module.setdefault(module_path, {})[cls.name] = rc
        return category

    for file_info in files:
        if file_info.parse_error is not None:
            continue
        for cls in file_info.classes:
            categorize(file_info, cls)

    return ClassRegistry(classes=resolved, by_module=by_module)


# =============================================================================
# Helpers
# =============================================================================


def _module_path_for(file_path: Path, project_root: Path) -> str:
    """Convert a file path to a dotted Python module name relative
    to the project root.

    A file at the root has the file stem as its module name.
    A file under a subdirectory uses dotted segments. ``__init__.py``
    files use the parent directory name as their module (matching
    Python's package-as-module convention). Files outside the project
    root return an empty string.
    """
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        return ""
    parts = list(rel.parts)
    if not parts:
        return ""
    last = parts[-1]
    if last == "__init__.py":
        parts = parts[:-1]
    elif last.endswith(".py"):
        parts[-1] = last[:-3]
    return ".".join(parts)


def _base_to_dotted_name(node: ast.AST) -> str | None:
    """Extract a ``"head.attr1.attr2"`` string from a base-class
    expression, or ``None`` for shapes the resolver can't handle.

    Handles ``Name``, chained ``Attribute`` access, and
    ``Subscript`` (descending into the subscripted value, so
    ``Generic[T]`` reduces to ``"Generic"``). Anything else
    (calls, binops, etc.) returns ``None``.
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
    if isinstance(node, ast.Subscript):
        return _base_to_dotted_name(node.value)
    return None


def _find_import_binding(
    file_info: FileInfo, name: str,
) -> ImportInfo | None:
    """Return the import that binds ``name`` in ``file_info``'s
    namespace, or ``None`` if no such binding exists.
    """
    for imp in file_info.imports:
        if imp.local_name == name:
            return imp
    return None


def _resolve_relative_module(
    imp: ImportInfo, file_info: FileInfo, project_root: Path,
) -> str | None:
    """Convert a relative-import source-module to an absolute
    project-relative dotted name.

    For ``from . import X`` in module ``pkg.sub.mod``, returns
    ``"pkg.sub"``; for ``from .helpers import X`` in the same
    module, returns ``"pkg.sub.helpers"``. Returns ``None`` when
    the relative level walks above the project root (Python would
    raise ``ImportError`` at runtime; the graph builder treats it
    as unresolvable).
    """
    if not imp.is_relative:
        return imp.source_module
    file_module = _module_path_for(file_info.path, project_root)
    parts = file_module.split(".") if file_module else []
    is_init = file_info.path.name == "__init__.py"
    package_parts = parts if is_init else parts[:-1]
    drops = imp.relative_level - 1
    if drops > len(package_parts):
        return None
    base_pkg = package_parts if drops == 0 else package_parts[:-drops]
    if imp.source_module:
        return (
            ".".join(base_pkg + [imp.source_module])
            if base_pkg
            else imp.source_module
        )
    return ".".join(base_pkg)


def _resolve_to_category(
    base_name: str,
    file_info: FileInfo,
    files_by_module: dict[str, FileInfo],
    classes_by_module: dict[str, dict[str, tuple[FileInfo, ClassDefInfo]]],
    project_root: Path,
    categorize,
    in_progress: set[tuple[str, str]] | None = None,
) -> str:
    """Walk a base name expression to a category, recursing through
    project-local bases as needed.

    ``in_progress`` is the re-export cycle guard: tracks
    ``(module, attr)`` pairs currently being resolved through
    project-internal re-exports. ``None`` at top-level callers; the
    first re-export hop creates the set.
    """
    parts = base_name.split(".")
    head, rest = parts[0], parts[1:]

    # Project-local class in the same file (no import binding involved).
    file_module = _module_path_for(file_info.path, project_root)
    locals_in_module = classes_by_module.get(file_module, {})
    if not rest and head in locals_in_module:
        target_file, target_cls = locals_in_module[head]
        return categorize(target_file, target_cls)

    # Imported binding.
    imp = _find_import_binding(file_info, head)
    if imp is None:
        return "unknown"

    resolved_module = _resolve_relative_module(imp, file_info, project_root)
    if resolved_module is None:
        return "unknown"

    if imp.source_attr is None:
        # ``import X`` / ``import X as Y`` — head binds to a module.
        return _resolve_via_module_binding(
            resolved_module, rest,
            files_by_module, classes_by_module, project_root,
            categorize, in_progress,
        )

    # ``from X import Y`` — Y can be either an attribute of X OR a
    # submodule of X (Python's ``from pkg import sub`` binds sub as
    # a module reference when ``sub`` is a submodule). Disambiguate
    # by checking whether ``X.Y`` is a known project module.
    candidate_module = (
        f"{resolved_module}.{imp.source_attr}"
        if resolved_module else imp.source_attr
    )
    if candidate_module in files_by_module:
        # Y is a submodule; head binds to that module.
        return _resolve_via_module_binding(
            candidate_module, rest,
            files_by_module, classes_by_module, project_root,
            categorize, in_progress,
        )

    # Y is an attribute of X.
    if rest:
        # Using an attribute of an imported class as a base is
        # unusual (e.g., ``class C(SomeClass.NestedClass)``); skip.
        return "unknown"
    return _categorize_module_attr(
        resolved_module, imp.source_attr,
        files_by_module, classes_by_module, project_root,
        categorize, in_progress,
    )


def _resolve_via_module_binding(
    module: str,
    rest: list[str],
    files_by_module: dict[str, FileInfo],
    classes_by_module: dict[str, dict[str, tuple[FileInfo, ClassDefInfo]]],
    project_root: Path,
    categorize,
    in_progress: set[tuple[str, str]] | None,
) -> str:
    """Resolve a base where the head name binds to a module (from
    ``import X``, ``import X as Y``, or ``from pkg import sub`` where
    sub is a submodule). ``rest`` is the dotted suffix after the
    head (e.g., ``["LocalBase"]`` for ``Y.LocalBase``).
    """
    if not rest:
        # Using the module itself as a base — unusual; skip.
        return "unknown"
    attr = rest[-1]
    if len(rest) > 1:
        extra = ".".join(rest[:-1])
        full_module = f"{module}.{extra}" if module else extra
    else:
        full_module = module
    return _categorize_module_attr(
        full_module, attr,
        files_by_module, classes_by_module, project_root,
        categorize, in_progress,
    )


def _categorize_module_attr(
    module: str,
    attr: str,
    files_by_module: dict[str, FileInfo],
    classes_by_module: dict[str, dict[str, tuple[FileInfo, ClassDefInfo]]],
    project_root: Path,
    categorize,
    in_progress: set[tuple[str, str]] | None,
) -> str:
    """Categorize a (module, attr) pair: project-local class →
    recurse; project-local re-export of a known base → recurse
    through the re-export; scadwright-rooted module + base name →
    known category; anything else → unknown.

    Re-export resolution handles the shape ``mylib/__init__.py``
    re-exporting a scadwright base under a project alias
    (``from scadwright import Component as Plate``), which a class
    elsewhere then inherits from. Without this step, the child
    class would silently categorize as ``unknown`` and drop from
    the graph. ``in_progress`` is the cycle guard for this layer:
    a (module, attr) pair already being resolved bails to
    ``unknown`` rather than recursing forever.
    """
    if module in files_by_module:
        local_classes = classes_by_module.get(module, {})
        if attr in local_classes:
            target_file, target_cls = local_classes[attr]
            return categorize(target_file, target_cls)
        # Re-export check: this module's import bindings may rebind
        # ``attr`` to something whose category we can chase.
        target_file = files_by_module[module]
        for imp in target_file.imports:
            if imp.local_name != attr:
                continue
            key = (module, attr)
            if in_progress is None:
                in_progress = set()
            if key in in_progress:
                return "unknown"
            in_progress.add(key)
            try:
                return _resolve_to_category(
                    attr, target_file,
                    files_by_module, classes_by_module,
                    project_root, categorize, in_progress,
                )
            finally:
                in_progress.discard(key)
        return "unknown"
    if _is_scadwright_module(module) and attr in _SCADWRIGHT_BASE_CATEGORY:
        return _SCADWRIGHT_BASE_CATEGORY[attr]
    return "unknown"


def _is_scadwright_module(module: str) -> bool:
    """True for ``"scadwright"`` and any of its submodule paths.

    Catches re-exports like ``from scadwright.component.base import
    Component``: any module whose dotted path begins with
    ``scadwright`` (followed by either a ``.`` or end-of-string)
    counts.
    """
    return module == "scadwright" or module.startswith("scadwright.")


def resolve_name_in_file(
    name: str,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> ResolvedClass | None:
    """Resolve a name expression visible in ``file_info`` to a
    project-local class, or ``None`` if it doesn't name one.

    Handles the same shapes :func:`_resolve_to_category` does —
    ``Name``, dotted ``Attribute`` access, and ``Subscript``-wrapped
    bases — and follows imports + relative imports + submodule
    disambiguation. Returns ``None`` for external classes (the
    scadwright bases, third-party imports) since they don't
    correspond to any :class:`ResolvedClass` in the registry.

    Used by extractors that need the actual class identity behind
    a Param's type, an attribute-base reference in an equation, or
    a ``self.x.y`` chain in a ``build()`` body.
    """
    parts = name.split(".")
    head, rest = parts[0], parts[1:]

    file_module = _module_path_for(file_info.path, project_root)
    locals_in_module = registry.by_module.get(file_module, {})
    if not rest and head in locals_in_module:
        return locals_in_module[head]

    imp = _find_import_binding(file_info, head)
    if imp is None:
        return None

    resolved_module = _resolve_relative_module(imp, file_info, project_root)
    if resolved_module is None:
        return None

    if imp.source_attr is None:
        return _lookup_via_module(resolved_module, rest, registry)

    candidate_module = (
        f"{resolved_module}.{imp.source_attr}"
        if resolved_module else imp.source_attr
    )
    if candidate_module in registry.by_module:
        return _lookup_via_module(candidate_module, rest, registry)

    if rest:
        return None
    return registry.by_module.get(resolved_module, {}).get(imp.source_attr)


def _lookup_via_module(
    module: str, rest: list[str], registry: ClassRegistry,
) -> ResolvedClass | None:
    """Resolve ``module.rest[0].rest[1]...`` as a class lookup in
    ``registry.by_module``. The last ``rest`` segment is the class
    name; earlier segments extend the module path.
    """
    if not rest:
        return None
    attr = rest[-1]
    if len(rest) > 1:
        extra = ".".join(rest[:-1])
        target_module = f"{module}.{extra}" if module else extra
    else:
        target_module = module
    return registry.by_module.get(target_module, {}).get(attr)
