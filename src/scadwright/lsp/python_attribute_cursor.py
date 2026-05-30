"""Cursor detection for project-class references in Python code
outside any equations block.

Hover, definition, and rename handlers consult these finders when
the equations-block cursor pipeline returns ``None``. A consumer
file that reads a Spec's attributes via
``BronicaS2Bayonet.cam_barrel_od`` (the dominant pattern in real
projects) gets the same editor features the LSP already offers
inside equations blocks.

Two cursor shapes are detected:

- :func:`find_python_attribute_at_cursor` — the cursor on the
  ``attr`` token of ``SourceClass.attr``. Returns the resolved
  class plus the attribute name and span.
- :func:`find_python_class_at_cursor` — the cursor on a class
  name that resolves to a project class: a bare ``SourceClass``
  reference, the class half of ``SourceClass.attr``, a base in
  ``class Sub(SourceClass)``, an instantiation ``SourceClass()``,
  or a dotted ``pkg.SourceClass``. Returns the resolved class and
  the name span. Goto-definition uses this to jump to the class.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from scadwright.lsp.positions import (
    byte_col_to_char_col,
    split_source_lines,
)
from scadwright.project_index.registry import (
    ClassRegistry,
    ResolvedClass,
    resolve_name_in_file,
)
from scadwright.project_index.walk import FileInfo


@dataclass(frozen=True)
class PythonAttributeCursor:
    """The class and attribute the cursor is on, plus its file range.

    ``target`` is the resolved project class whose attribute the
    cursor is accessing. ``attr_name`` is the bare attribute name
    (e.g., ``"cam_barrel_od"``). The four position fields cover
    just the attr token, after the dot following the value
    expression; LSP convention is 0-based for both lines and
    columns.
    """
    target: ResolvedClass
    attr_name: str
    attr_start_line: int
    attr_start_col: int
    attr_end_line: int
    attr_end_col: int


def find_python_attribute_at_cursor(
    file_info: FileInfo,
    file_line: int,
    file_col: int,
    registry: ClassRegistry,
    project_root: Path,
) -> PythonAttributeCursor | None:
    """Return the :class:`PythonAttributeCursor` for the cursor, or
    ``None`` when the cursor isn't on a renameable class-attribute
    access.

    The cursor must fall on the attr token of an ``ast.Attribute``
    node whose value chain (a ``Name`` or chained ``Attribute``)
    reduces to a dotted name resolving through the file's imports
    to a project class. Class scope, method bodies, module scope,
    and module-level function bodies are all in range — anywhere
    Python's grammar allows attribute access.

    Chained access on the attribute (``CamSpec.outer_d.bit_length()``)
    correctly resolves only the inner ``outer_d`` reference; the
    outer ``Attribute`` (``attr=bit_length``) has a base whose
    dotted name (``CamSpec.outer_d``) doesn't resolve to a project
    class.
    """
    if file_info.tree is None:
        return None
    source_lines = split_source_lines(file_info.source)
    for sub in ast.walk(file_info.tree):
        if not isinstance(sub, ast.Attribute):
            continue
        attr_start_line = (sub.lineno or 1) - 1
        attr_end_line = (sub.end_lineno or sub.lineno) - 1
        if file_line != attr_start_line or file_line != attr_end_line:
            continue
        # ast columns are UTF-8 byte offsets; convert to character
        # indices so the cursor comparison and emitted span line up
        # with the LSP's character-based coordinates on non-ASCII lines.
        attr_start_col = byte_col_to_char_col(
            _line_at(source_lines, attr_start_line),
            (sub.value.end_col_offset or 0) + 1,
        )
        attr_end_col = byte_col_to_char_col(
            _line_at(source_lines, attr_end_line),
            sub.end_col_offset if sub.end_col_offset is not None else 0,
        )
        if file_col < attr_start_col or file_col > attr_end_col:
            continue
        dotted = _value_chain_to_dotted_name(sub.value)
        if dotted is None:
            return None
        target = resolve_name_in_file(
            dotted, file_info, registry, project_root,
        )
        if target is None:
            return None
        return PythonAttributeCursor(
            target=target,
            attr_name=sub.attr,
            attr_start_line=attr_start_line,
            attr_start_col=attr_start_col,
            attr_end_line=attr_end_line,
            attr_end_col=attr_end_col,
        )
    return None


@dataclass(frozen=True)
class PythonClassCursor:
    """The project class the cursor is on, plus the name's span.

    ``target`` is the resolved project class. The four position
    fields cover the name token under the cursor (the bare
    ``Name``, or the final ``attr`` of a dotted ``pkg.Class``
    reference); LSP convention is 0-based for both lines and
    columns.
    """
    target: ResolvedClass
    name_start_line: int
    name_start_col: int
    name_end_line: int
    name_end_col: int


def find_python_class_at_cursor(
    file_info: FileInfo,
    file_line: int,
    file_col: int,
    registry: ClassRegistry,
    project_root: Path,
) -> PythonClassCursor | None:
    """Return the :class:`PythonClassCursor` for the cursor, or
    ``None`` when the cursor isn't on a name that resolves to a
    project class.

    Two token shapes carry a class reference: a bare ``Name``
    (``SourceClass``, the class half of ``SourceClass.attr``, a
    base in ``class Sub(SourceClass)``, an instantiation
    ``SourceClass()``), and the final ``attr`` of a dotted module
    path (``pkg.SourceClass``). The cursor must land on that token
    and the token must resolve through the file's imports to a
    class in the project registry.

    Module names in a dotted path (``pkg`` in ``pkg.SourceClass``)
    resolve to nothing and yield ``None``, so a cursor there
    doesn't produce a false jump.
    """
    if file_info.tree is None:
        return None
    source_lines = split_source_lines(file_info.source)
    for sub in ast.walk(file_info.tree):
        span = _class_token_span_at(sub, file_line, file_col, source_lines)
        if span is None:
            continue
        dotted = _resolvable_dotted_name(sub)
        if dotted is None:
            continue
        target = resolve_name_in_file(
            dotted, file_info, registry, project_root,
        )
        if target is None:
            continue
        return PythonClassCursor(
            target=target,
            name_start_line=span[0],
            name_start_col=span[1],
            name_end_line=span[2],
            name_end_col=span[3],
        )
    return None


def _class_token_span_at(
    node: ast.AST,
    file_line: int,
    file_col: int,
    source_lines: list[str],
) -> tuple[int, int, int, int] | None:
    """If the cursor lands on the class-name token of ``node``,
    return that token's 0-based ``(start_line, start_col, end_line,
    end_col)`` in character coordinates; otherwise ``None``.

    For a bare ``Name`` the token is the whole node. For an
    ``Attribute`` the token is the ``attr`` part (the ``Class`` of
    ``pkg.Class``), positioned after the dot following the value
    expression. ast byte columns are converted to character indices
    so the cursor comparison and span line up with the LSP's
    character coordinates on non-ASCII lines.
    """
    if isinstance(node, ast.Name):
        start_line = (node.lineno or 1) - 1
        end_line = (node.end_lineno or node.lineno) - 1
        if file_line != start_line or file_line != end_line:
            return None
        start_col = byte_col_to_char_col(
            _line_at(source_lines, start_line), node.col_offset,
        )
        end_col = byte_col_to_char_col(
            _line_at(source_lines, end_line),
            node.end_col_offset if node.end_col_offset is not None
            else node.col_offset,
        )
    elif isinstance(node, ast.Attribute):
        start_line = (node.lineno or 1) - 1
        end_line = (node.end_lineno or node.lineno) - 1
        if file_line != start_line or file_line != end_line:
            return None
        start_col = byte_col_to_char_col(
            _line_at(source_lines, start_line),
            (node.value.end_col_offset or 0) + 1,
        )
        end_col = byte_col_to_char_col(
            _line_at(source_lines, end_line),
            node.end_col_offset if node.end_col_offset is not None
            else (node.value.end_col_offset or 0) + 1,
        )
    else:
        return None
    if file_col < start_col or file_col > end_col:
        return None
    return (start_line, start_col, end_line, end_col)


def _line_at(source_lines: list[str], index: int) -> str:
    """Return ``source_lines[index]`` or ``""`` when out of range."""
    if 0 <= index < len(source_lines):
        return source_lines[index]
    return ""


def _resolvable_dotted_name(node: ast.AST) -> str | None:
    """Dotted name to resolve for a class-name token: the bare id
    for a ``Name``, or the full chain for an ``Attribute``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _value_chain_to_dotted_name(node)
    return None


def _value_chain_to_dotted_name(node: ast.AST) -> str | None:
    """Reduce a ``Name`` or chained ``Attribute`` expression to its
    dotted string form, or return ``None`` for other shapes.

    Mirrors the helper in :mod:`scadwright.lsp.rename` — left
    duplicated rather than importing across modules to keep this
    cursor module self-contained.
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


__all__ = [
    "PythonAttributeCursor",
    "PythonClassCursor",
    "find_python_attribute_at_cursor",
    "find_python_class_at_cursor",
]
