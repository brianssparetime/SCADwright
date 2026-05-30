"""Project-level filesystem walker and per-file AST capture.

Given a path to a project root (a directory) or a single source file,
:func:`walk_project` returns one :class:`FileInfo` per Python file
discovered. Each ``FileInfo`` carries the file's source text, a flat
list of import bindings visible in the file, and one
:class:`ClassDefInfo` per class declaration (top-level *and* nested).

The walker tolerates parse errors: a file that doesn't parse is
returned as a ``FileInfo`` with empty imports/classes and a populated
``parse_error`` field. Callers (the import resolver, the per-class
extractors) skip such files. This keeps the graph build robust on
real projects where one stale file shouldn't sink the whole analysis.

Imports are captured at module scope only — a graph build doesn't
need conditional or function-local imports, and limiting the scan
keeps the binding map small. ClassDefs are captured everywhere
(``ast.walk``) so nested classes do appear in the registry.

Directories named ``__pycache__``, ``.venv``, ``node_modules``, or
anything starting with ``.`` (``.git``, ``.hg``, ``.idea``, ...) are
skipped during recursion. The user's project tree is everything else.
"""

from __future__ import annotations

import ast
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping


_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__",
    "node_modules",
})


@dataclass(frozen=True)
class ImportInfo:
    """One imported binding visible in a file's namespace.

    ``local_name`` is the name as it appears in the file's namespace
    (``X`` in ``import X``, ``Y`` in ``import X as Y``, ``Z`` in
    ``from X import Y as Z``).

    ``source_module`` is the module being imported from.
    ``source_attr`` is the imported attribute (``Y`` in
    ``from X import Y``); ``None`` for ``import X`` style imports
    where the binding refers to the module itself.

    ``is_relative`` is true for ``from . import ...`` and
    ``from .. import ...``. ``relative_level`` records the dot count
    so the resolver can map relatives to absolute modules.
    """
    local_name: str
    source_module: str
    source_attr: str | None
    is_relative: bool
    relative_level: int


@dataclass(frozen=True)
class ClassDefInfo:
    """One class declaration discovered in a source file.

    ``bases`` is the tuple of base-expression source texts — the
    output of ``ast.unparse`` for each base. The import resolver
    (next step) maps these to actual class identities.

    ``ast_node`` is the underlying :class:`ast.ClassDef` node so
    downstream extractors (Param walker, equations walker,
    ``build()`` walker) can re-walk the body without re-parsing.

    ``line``/``col`` and ``end_line``/``end_col`` are 0-based.
    """
    name: str
    bases: tuple[str, ...]
    line: int
    col: int
    end_line: int
    end_col: int
    ast_node: ast.ClassDef


@dataclass(frozen=True)
class FileInfo:
    """The output of analyzing one source file.

    ``parse_error`` is ``None`` on success and the formatted
    ``SyntaxError`` message on failure. Successful files have
    populated ``imports``, ``classes``, and ``tree``; failed files
    have empty tuples for the first two and ``None`` for ``tree``.

    ``tree`` is the parsed module AST, retained so later passes
    (transform discovery, register-call detection) can re-walk the
    module without re-parsing. The ``ast_node`` fields on
    ``ClassDefInfo`` are part of this same tree, so keeping the
    root reference adds no real memory cost.
    """
    path: Path
    source: str
    imports: tuple[ImportInfo, ...]
    classes: tuple[ClassDefInfo, ...]
    parse_error: str | None
    tree: ast.Module | None = None


def walk_project(
    path: str | Path,
    *,
    exclude: Iterable[str] = (),
    source_overrides: Mapping[Path, str] = MappingProxyType({}),
) -> list[FileInfo]:
    """Discover and analyze every Python file under ``path``.

    ``path`` may be a directory (recursed) or a single ``.py`` file.
    A non-Python single-file path returns ``[]``. Directories that
    don't exist also return ``[]`` — the caller can decide whether
    that's an error.

    ``exclude`` is a sequence of glob patterns. Patterns without a
    ``/`` match any path segment, so ``exclude=("OLD",)`` skips
    every file under a directory named ``OLD``. Patterns with a
    ``/`` match the file's relative path as a glob —
    ``exclude=("OLD/2026-*",)`` skips only the dated snapshot
    subdirs. The built-in skip set (``__pycache__``,
    ``node_modules``, dotted directories) always applies and isn't
    affected by ``exclude``.

    ``source_overrides`` maps a file path to text the walker should
    analyze in place of that file's on-disk contents. The LSP
    supplies the editor's live buffers here so that analysis runs
    against unsaved edits, not the stale disk copy. Overrides apply
    only to files the walk already discovers on disk; a buffer for
    a file that doesn't exist yet on disk isn't injected.

    Output is sorted by path so consumers (the renderer in
    particular) produce deterministic output.
    """
    p = Path(path)
    patterns = tuple(exclude)
    if p.is_file():
        if p.suffix != ".py":
            return []
        return [_analyze_one(p, source_overrides)]
    if not p.is_dir():
        return []
    return [
        _analyze_one(f, source_overrides)
        for f in _iter_py_files(p, patterns)
    ]


def _analyze_one(
    path: Path, source_overrides: Mapping[Path, str],
) -> FileInfo:
    """Analyze ``path`` from its override text when present, else
    from disk."""
    override = source_overrides.get(path)
    if override is not None:
        return analyze_source(path, override)
    return _analyze_file(path)


def _iter_py_files(root: Path, exclude: tuple[str, ...]) -> Iterator[Path]:
    """Yield every ``.py`` path under ``root`` in sorted order, skipping
    ``__pycache__``, ``node_modules``, any directory whose name
    starts with ``.``, and any path matched by ``exclude``.
    """
    candidates: list[Path] = []
    for candidate in root.rglob("*.py"):
        if any(_should_skip_dir(part) for part in candidate.parts):
            continue
        if exclude and _matches_exclude(candidate, root, exclude):
            continue
        candidates.append(candidate)
    candidates.sort()
    yield from candidates


def _should_skip_dir(part: str) -> bool:
    if part in _SKIP_DIRS:
        return True
    # Hidden dirs (``.venv``, ``.git``, ``.idea``, ``.tox``, ...).
    return len(part) > 1 and part.startswith(".")


def _matches_exclude(
    path: Path, root: Path, patterns: tuple[str, ...],
) -> bool:
    """Whether ``path`` matches any of the user-supplied exclude
    patterns.

    Pattern semantics:

    - A pattern containing ``/`` matches the file's path relative
      to ``root`` (POSIX-style) as a single glob via
      :func:`fnmatch.fnmatch`. Example: ``OLD/2026-*`` matches
      ``OLD/2026-05-13/foo.py`` but not ``OLD/foo.py``.
    - A pattern without ``/`` matches if any single path segment
      matches it. Example: ``OLD`` matches any path containing a
      segment named ``OLD``; ``*.test.py`` matches any file segment
      ending in ``.test.py``.
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    rel_str = rel.as_posix()
    for pattern in patterns:
        # fnmatchcase (case-sensitive) over fnmatch so behavior is
        # consistent across platforms: fnmatch case-normalizes on
        # case-insensitive filesystems, which would make `--exclude
        # OLD` match `Old/` on macOS or Windows but not on Linux.
        if "/" in pattern:
            if fnmatch.fnmatchcase(rel_str, pattern):
                return True
        else:
            if any(fnmatch.fnmatchcase(part, pattern) for part in rel.parts):
                return True
    return False


# Disk-read memoization. The LSP rebuilds the project index on every
# hover / definition / rename that falls outside an equations block;
# without this, each request re-reads and re-parses every project
# file. Entries are keyed by file identity plus a version stamp
# ``(mtime_ns, size)``, so a file edited on disk invalidates its own
# entry the next time it's read. Editor buffers never enter this
# cache: ``_analyze_one`` routes open files through ``analyze_source``
# instead, so the cache only ever holds on-disk content.
#
# The cache is process-global. It's pure memoization — the same
# ``(path, mtime_ns, size)`` always maps to the same parse result —
# so it changes nothing observable except speed, with one exception
# handled by the version stamp: a file rewritten between reads. A
# generous cap bounds memory; eviction is FIFO and effectively never
# fires for a single project, whose file count is far below it.
_CACHE_MAX = 4096
_FILE_CACHE: dict[Path, tuple[int, int, FileInfo]] = {}


def clear_walk_cache() -> None:
    """Drop every memoized disk-read result.

    Mostly for tests; production code relies on the ``(mtime_ns,
    size)`` version stamp to invalidate stale entries automatically.
    """
    _FILE_CACHE.clear()


def _analyze_file(path: Path) -> FileInfo:
    """Read and parse one file from disk, capturing imports and
    class declarations. Returns a ``FileInfo`` with ``parse_error``
    set when the file can't be read or parsed.

    Memoized on ``(mtime_ns, size)``: an unchanged file is parsed
    once and served from cache on later reads; a file changed on
    disk is re-read because its version stamp no longer matches.
    """
    try:
        stat = path.stat()
    except OSError as exc:
        return FileInfo(
            path=path, source="",
            imports=(), classes=(),
            parse_error=f"could not read file: {exc}",
        )
    stamp = (stat.st_mtime_ns, stat.st_size)
    cached = _FILE_CACHE.get(path)
    if cached is not None and cached[0] == stamp[0] and cached[1] == stamp[1]:
        return cached[2]

    try:
        source = path.read_text()
    except OSError as exc:
        return FileInfo(
            path=path, source="",
            imports=(), classes=(),
            parse_error=f"could not read file: {exc}",
        )
    info = analyze_source(path, source)
    if len(_FILE_CACHE) >= _CACHE_MAX:
        # FIFO eviction: drop the oldest inserted entry.
        _FILE_CACHE.pop(next(iter(_FILE_CACHE)), None)
    _FILE_CACHE[path] = (stamp[0], stamp[1], info)
    return info


def analyze_source(path: Path, source: str) -> FileInfo:
    """Parse ``source`` as the contents of ``path``, capturing
    imports and class declarations.

    This is the in-memory counterpart to the disk-reading
    :func:`_analyze_file`. The LSP uses it to analyze the editor's
    current (possibly unsaved) document text rather than the stale
    on-disk copy, so cursor positions and the parsed AST stay in
    sync. Returns a ``FileInfo`` with ``parse_error`` set when the
    source doesn't parse.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return FileInfo(
            path=path, source=source,
            imports=(), classes=(),
            parse_error=f"{exc.msg} (line {exc.lineno})",
        )
    imports = tuple(_extract_imports(tree))
    classes = tuple(_extract_classes(tree))
    return FileInfo(
        path=path, source=source,
        imports=imports, classes=classes,
        parse_error=None,
        tree=tree,
    )


def _extract_imports(tree: ast.Module) -> Iterator[ImportInfo]:
    """Yield one :class:`ImportInfo` per import binding visible at
    module scope.

    Module scope spans the module body plus the bodies of any
    ``try``/``except``/``finally``, ``if``, ``with``, and ``for``/
    ``while`` blocks at the module top level — common shapes for
    conditional imports (``if TYPE_CHECKING:``, fallback ``try:
    import x; except ImportError: ...``). Function and class
    bodies are NOT entered: imports there bind in their own
    scope, not the module's, and aren't reachable from a class
    base expression.
    """
    for node in _walk_module_scope(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield ImportInfo(
                    local_name=alias.asname or alias.name.split(".")[0],
                    source_module=alias.name,
                    source_attr=None,
                    is_relative=False,
                    relative_level=0,
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            for alias in node.names:
                yield ImportInfo(
                    local_name=alias.asname or alias.name,
                    source_module=module,
                    source_attr=alias.name,
                    is_relative=level > 0,
                    relative_level=level,
                )


def _walk_module_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Yield every descendant of ``node`` reachable without crossing
    a function or class boundary.

    Suitable for collecting module-scope imports: a ``try``/``if``/
    ``with`` block at module level is traversed, but a ``def f():
    import x`` inside is not — the inner ``import`` doesn't bind in
    the module's namespace.
    """
    if isinstance(
        node,
        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
    ):
        # Skip — these introduce their own scope.
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_module_scope(child)


def _extract_classes(tree: ast.Module) -> Iterator[ClassDefInfo]:
    """Walk the AST for every :class:`ast.ClassDef`, including nested
    classes. Source order is preserved by ``ast.walk``'s breadth-first
    traversal but only loosely; classes inside the same scope appear
    in source order, while a deeply-nested class appears in
    breadth-first position. Consumers that care about source order
    re-sort by ``line``.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield _class_info(node)


def _class_info(node: ast.ClassDef) -> ClassDefInfo:
    bases = tuple(ast.unparse(b) for b in node.bases)
    end_line = (node.end_lineno - 1) if node.end_lineno else (node.lineno - 1)
    end_col = (
        node.end_col_offset
        if node.end_col_offset is not None
        else node.col_offset
    )
    return ClassDefInfo(
        name=node.name,
        bases=bases,
        line=node.lineno - 1,
        col=node.col_offset,
        end_line=end_line,
        end_col=end_col,
        ast_node=node,
    )
