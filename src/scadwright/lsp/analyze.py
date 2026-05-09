"""LSP-specific extensions on top of :mod:`scadwright.project_index.analyze`.

The neutral block-and-Param machinery (``EquationsBlock``,
``ParamInfo``, ``find_equations_blocks``, ``_block_from_classdef``,
``_build_param_info``, ``_is_param_call``, host-string helpers)
lives in :mod:`scadwright.project_index.analyze`. This module
re-exports the parts the LSP layer uses and adds LSP-only helpers
for tracking auto-declared bare-Name equation targets — names that
the runtime auto-declares as ``Param`` at class-define time, which
the LSP needs to know about for completion, hover origins, and
goto-definition on bare-Name references.
"""

from __future__ import annotations

import ast

from scadwright.project_index.analyze import (
    EquationsBlock,
    EquationsHostString,
    ParamInfo,
    _block_from_classdef,
    _build_param_info,
    _extract_hosts,
    _host_from_constant,
    _is_param_call,
    _string_prefix_length,
    find_equations_blocks,
)


__all__ = [
    "EquationsBlock",
    "EquationsHostString",
    "ParamInfo",
    "_block_from_classdef",
    "_build_param_info",
    "_extract_hosts",
    "_host_from_constant",
    "_is_param_call",
    "_string_prefix_length",
    "auto_declared_origins_before",
    "auto_declared_origins_in_block",
    "auto_declared_targets_before",
    "find_equations_blocks",
]


# =============================================================================
# Auto-declared target collection (for Param-aware completion)
# =============================================================================


def auto_declared_targets_before(
    block: EquationsBlock,
    host_index: int,
    line_index: int,
) -> frozenset[str]:
    """Names that appear as bare-Name equation targets on lines
    strictly preceding ``(host_index, line_index)`` in source order.

    The runtime auto-declares such names as ``Param(float)`` (or
    ``Param(None)`` per the numeric-only heuristic) when they aren't
    already declared as Params. For completion, treating them as
    available identifiers on later lines matches what the resolver
    would do at class-define time.

    Comma-broadcast targets (``x, y = 5``) expand to all named
    components. Subscript and attribute targets aren't bare Names
    and don't contribute. Adjustment lines (``x += 1``) modify
    existing names rather than introducing new ones, so they're
    skipped.
    """
    return frozenset(
        auto_declared_origins_before(block, host_index, line_index),
    )


def auto_declared_origins_before(
    block: EquationsBlock,
    host_index: int,
    line_index: int,
) -> dict[str, tuple[int, int]]:
    """Like :func:`auto_declared_targets_before` but each name maps to
    the ``(host_index, line_index)`` pair where it was first seen.

    Iteration is in source order, so the dict's insertion order
    reflects declaration order. Used by hover and completion to
    surface the originating line.
    """
    origins: dict[str, tuple[int, int]] = {}
    for h_idx, l_idx, cleaned in _walk_earlier_cleaned_lines(
        block, host_index, line_index,
    ):
        for name in _bare_targets_in_line(cleaned):
            if name not in origins:
                origins[name] = (h_idx, l_idx)
    return origins


def auto_declared_origins_in_block(
    block: EquationsBlock,
) -> dict[str, tuple[int, int]]:
    """Like :func:`auto_declared_origins_before` but considers every
    line in the block, not just those before a cursor.

    Goto-definition uses this: a bare-Name target's "definition" is
    its first occurrence anywhere in the block, regardless of where
    the cursor currently sits, because the runtime auto-declares
    every block-wide target as a Param at class-define time.
    """
    return auto_declared_origins_before(block, len(block.hosts), 0)


def _walk_earlier_cleaned_lines(
    block: EquationsBlock, host_index: int, line_index: int,
):
    """Yield ``(host_idx, line_idx, cleaned_line_text)`` for each
    logical line strictly preceding ``(host_index, line_index)``.

    ``cleaned_line_text`` is the post-annotation-strip form so the
    caller doesn't need to know about sigils or type tags.
    """
    from scadwright.component.equations import (
        _extract_name_annotations_with_colmap,
    )
    from scadwright.component.equations.lex import _split_logical_lines

    for h_idx, host in enumerate(block.hosts):
        if h_idx > host_index:
            break
        for l_idx, line in enumerate(_split_logical_lines(host.raw_text)):
            if h_idx == host_index and l_idx >= line_index:
                break
            cleaned, _, _, _ = _extract_name_annotations_with_colmap(
                line.cleaned,
            )
            yield h_idx, l_idx, cleaned


def _bare_targets_in_line(cleaned_line: str) -> list[str]:
    """Return bare-Name targets of a single equation line, or ``[]``
    when the line isn't an equation or can't be safely parsed.

    The line text is the post-annotation-strip form (sigils and type
    tags already removed). Adjustment lines (``+=``/``-=``/``*=``/
    ``/=``) and constraint lines (no top-level ``=``) yield ``[]``.
    Comma-broadcast LHS or RHS Tuples of bare Names expand to every
    named component.
    """
    from scadwright.component.resolver.parsing import (
        _split_top_level_equals,
    )
    from scadwright.errors import ValidationError

    try:
        split = _split_top_level_equals(cleaned_line)
    except ValidationError:
        # Chained `=` etc. — diagnostics will surface this; for
        # completion purposes there are no clean bare-Name targets.
        return []
    if split is None:
        return []
    lhs_text, rhs_text, _lhs_start, _rhs_start = split
    out: list[str] = []
    for side in (lhs_text, rhs_text):
        out.extend(_bare_names_from_text(side))
    return out


def _bare_names_from_text(text: str) -> list[str]:
    """Parse ``text`` as a Python expression and return its bare-Name
    target list: a single Name yields one entry, a Tuple of Names
    expands to every component, anything else yields ``[]``.
    """
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return []
    if isinstance(node, ast.Name):
        return [node.id]
    if (
        isinstance(node, ast.Tuple)
        and node.elts
        and all(isinstance(e, ast.Name) for e in node.elts)
    ):
        return [e.id for e in node.elts]
    return []
