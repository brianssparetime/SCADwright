"""Cursor detection for direct ``ClassName.attr`` access in Python
code outside any equations block.

Hover, definition, and rename handlers consult this when the
equations-block cursor pipeline returns ``None``. A consumer file
that reads a Spec's attributes via ``BronicaS2Bayonet.cam_barrel_od``
(the dominant pattern in real projects) gets the same editor
features the LSP already offers inside equations blocks.

The returned :class:`PythonAttributeCursor` carries the resolved
source class, the attribute name, and the file range of the attr
token so handlers can rewrite or jump to the right span.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

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
    for sub in ast.walk(file_info.tree):
        if not isinstance(sub, ast.Attribute):
            continue
        attr_start_line = (sub.lineno or 1) - 1
        attr_start_col = (sub.value.end_col_offset or 0) + 1
        attr_end_line = (sub.end_lineno or sub.lineno) - 1
        attr_end_col = sub.end_col_offset or attr_start_col
        if file_line != attr_start_line or file_line != attr_end_line:
            continue
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
    "find_python_attribute_at_cursor",
]
