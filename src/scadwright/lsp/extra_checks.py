"""LSP-only static checks that supplement the diagnostics produced by
``parse_equations_unified``.

The runtime resolver already raises with a sharpened hint when an
unresolved name appears as the base of an attribute access (the
``b.xyz`` shape — see ``IterativeResolver._attribute_base_hints``).
That message fires at solve time, so a user editing in their editor
only sees it after running their script. This module surfaces the
same information statically: the analyzer walks every equation,
constraint, and adjustment AST after a successful parse, finds
``Attribute(value=Name(b))`` shapes whose base isn't a declared
Param of the surrounding class, and emits a warning diagnostic
naming the offending name and attribute.

This is an LSP-side check, not a runtime addition: the runtime
behavior is unchanged. The static check uses ``EquationsBlock.params``
(the explicit Param declarations the analyzer extracted from the
class body) as the "declared" set; auto-declared bare-Name targets
do not count because the runtime auto-declares them as
``Param(float)``, which can't legitimately have attributes.
"""

from __future__ import annotations

import ast

from scadwright.component.equations import (
    _extract_name_annotations_with_colmap,
)
from scadwright.lsp.analyze import EquationsBlock
from scadwright.lsp.diagnostics import (
    Diagnostic,
    DiagnosticRange,
    _LineOrigin,
)
from scadwright.lsp.positions import map_cleaned_col_to_file


def find_undeclared_attribute_bases(
    block: EquationsBlock,
    equations,
    constraints,
    adjustments,
    origins: list[_LineOrigin],
) -> list[Diagnostic]:
    """Emit warning diagnostics for ``b.xyz`` cases where ``b`` isn't
    an explicit Param of the surrounding class.

    Walks every ``ast.AST`` carried by the parsed equations,
    constraints, and adjustments. One diagnostic per offending
    attribute access — granular squiggles let the editor highlight
    each spot independently rather than collapsing the whole block
    onto one line.

    Per-line annotation colmaps are computed once up front (parallel
    to ``origins``) and reused: a single equation with five
    attribute reads costs one colmap derivation rather than five.
    """
    declared = block.param_names
    colmaps: list[tuple[int, ...]] = [
        _extract_name_annotations_with_colmap(origin.line.cleaned)[3]
        for origin in origins
    ]
    out: list[Diagnostic] = []
    for eq in equations:
        out.extend(_scan_node(
            eq.lhs, eq.source_line_index, declared, origins, colmaps, block,
        ))
        out.extend(_scan_node(
            eq.rhs, eq.source_line_index, declared, origins, colmaps, block,
        ))
    for c in constraints:
        out.extend(_scan_node(
            c.expr, c.source_line_index, declared, origins, colmaps, block,
        ))
    for adj in adjustments:
        out.extend(_scan_node(
            adj.rhs, adj.source_line_index, declared, origins, colmaps, block,
        ))
    return out


def _scan_node(
    node: ast.AST,
    source_index: int,
    declared: frozenset[str],
    origins: list[_LineOrigin],
    colmaps: list[tuple[int, ...]],
    block: EquationsBlock,
) -> list[Diagnostic]:
    """Yield diagnostics for every ``Attribute(value=Name(b))`` in
    ``node`` whose ``b`` isn't in ``declared``.
    """
    if source_index < 0 or source_index >= len(origins):
        return []
    origin = origins[source_index]
    colmap = colmaps[source_index]
    out: list[Diagnostic] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Attribute):
            continue
        base = sub.value
        if not isinstance(base, ast.Name):
            continue
        if base.id in declared:
            continue
        diag_range = _name_range(base, origin, colmap)
        if diag_range is None:
            continue
        out.append(
            Diagnostic(
                range=diag_range,
                severity="warning",
                message=_message(block.class_name, source_index, base.id, sub.attr),
            ),
        )
    return out


def _message(
    class_name: str, source_index: int, base_name: str, attr_name: str,
) -> str:
    prefix = (
        f"{class_name}.equations[{source_index}]" if class_name
        else f"equations[{source_index}]"
    )
    return (
        f"{prefix}: `{base_name}.{attr_name}` reads an attribute of "
        f"`{base_name}`, but `{base_name}` isn't declared as a Param "
        f"of this Component. Equations only see the Component's own "
        f"Params and the curated math/builtin namespace; declare "
        f"`{base_name}` as a Param, or pass `{base_name}.{attr_name}` "
        f"as a kwarg evaluated outside the equations block."
    )


def _name_range(
    name_node: ast.Name,
    origin: _LineOrigin,
    colmap: tuple[int, ...],
) -> DiagnosticRange | None:
    """File range covering the ``Name`` node. Returns ``None`` when
    position info is missing or out-of-bounds for the cleaned line.
    """
    col = getattr(name_node, "col_offset", None)
    end_col = getattr(name_node, "end_col_offset", None)
    if col is None or end_col is None:
        return None
    if col < 0 or end_col < col or end_col > len(colmap):
        return None
    try:
        start_line, start_col = map_cleaned_col_to_file(
            col,
            annotation_colmap=colmap, line=origin.line,
            host_text=origin.host.raw_text,
            host_start_line=origin.host.content_start_line,
            host_start_col=origin.host.content_start_col,
        )
        end_line, end_col_file = map_cleaned_col_to_file(
            end_col,
            annotation_colmap=colmap, line=origin.line,
            host_text=origin.host.raw_text,
            host_start_line=origin.host.content_start_line,
            host_start_col=origin.host.content_start_col,
            is_exclusive_end=True,
        )
    except (ValueError, IndexError):
        return None
    return DiagnosticRange(start_line, start_col, end_line, end_col_file)
