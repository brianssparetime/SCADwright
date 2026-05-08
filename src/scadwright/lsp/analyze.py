"""Static AST analysis: locate equations blocks in a Python source file
plus per-block helpers used by completion and hover.

The user's file is parsed via ``ast.parse`` — never imported, so no
user code runs. For each ``class ... :`` the analyzer scans the
class body for an ``equations = ...`` assignment whose RHS is a
string literal or a list of string literals (mirroring the runtime's
two accepted shapes). Each contributing string literal becomes an
``EquationsHostString`` carrying the literal's content text and the
file ``(line, col)`` where the content begins (immediately after
any prefix and the opening quote).

Position arithmetic uses the literal's source-segment text rather
than the post-escape ``Constant.value``: per-char offsets into
``raw_text`` map linearly to columns from
``content_start_(line, col)``. Triple-quoted equations strings (the
canonical form) have no escapes in practice; the no-escape behavior
matches what the user sees on screen. Single-line literals
containing escape sequences (``"a\\nb"``) produce raw text that
includes the backslash characters verbatim, so the LSP highlight
will correspond to source positions, not post-escape positions.

Class-level ``name = Param(...)`` assignments contribute names to
``EquationsBlock.param_names``. The helper recognizes ``Param``,
``sc.Param``, ``scadwright.Param``, and any attribute call ending
in ``Param`` — name-based, not binding-aware (the analyzer can't
see imports without executing user code).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


_STRING_PREFIX_CHARS = frozenset("rRbBuUfF")
# Maximum legal Python string-literal prefix length (e.g., ``rb``, ``Br``).
_MAX_PREFIX_LEN = 2


@dataclass(frozen=True)
class EquationsHostString:
    """A single string literal contributing to an equations block.

    ``raw_text`` is the literal's content as it appears in the source
    file, with any prefix and the opening/closing quotes stripped.
    Escape sequences are NOT processed: ``\\n`` in the source stays
    as the two chars ``\\`` and ``n``. Per-char offsets into
    ``raw_text`` map linearly to columns from
    ``content_start_(line, col)``.

    ``content_start_line`` and ``content_start_col`` are 0-based file
    positions of ``raw_text[0]`` (i.e., immediately after the opening
    quote).
    """
    raw_text: str
    content_start_line: int
    content_start_col: int


@dataclass(frozen=True)
class ParamInfo:
    """Static info extracted from a class-level ``name = Param(...)``
    assignment.

    Field values are textual representations of the source as the
    user wrote them. ``type_text`` is the ``ast.unparse`` of the
    first positional argument (the ``type`` parameter of
    :class:`scadwright.component.params.Param`); ``None`` when the
    user passed no positional argument. ``default_text`` is the
    ``ast.unparse`` of the ``default=`` keyword if present.
    ``doc_text`` is the *string content* of the ``doc=`` keyword
    when its value is a string literal — surfaces in hover without
    surrounding quotes.

    ``extras`` is a tuple of ``(kwarg_name, source_text)`` pairs for
    every other keyword argument (``positive``, ``range``,
    ``one_of``, ``validators``, ...) in source order. Used to surface
    validator hints in hover without requiring the LSP to know each
    shorthand.

    The four ``assign_*`` fields hold the 0-based file range of the
    full assignment statement (the source span the LSP would
    highlight for goto-definition). They default to ``None`` to
    keep direct constructions back-compatible; ``find_equations_blocks``
    always populates them when the Param is discovered through AST
    traversal.
    """
    name: str
    type_text: str | None
    default_text: str | None
    doc_text: str | None
    extras: tuple[tuple[str, str], ...]
    assign_start_line: int | None = None
    assign_start_col: int | None = None
    assign_end_line: int | None = None
    assign_end_col: int | None = None

    def signature(self) -> str:
        """Render a compact ``Param(type, default=..., kw=...)`` string
        suitable for completion-item details and hover bodies.

        Order: positional ``type`` first, then ``default=``, then
        every entry in ``extras`` in source order.
        """
        parts: list[str] = []
        if self.type_text is not None:
            parts.append(self.type_text)
        if self.default_text is not None:
            parts.append(f"default={self.default_text}")
        for kw_name, kw_text in self.extras:
            parts.append(f"{kw_name}={kw_text}")
        return f"Param({', '.join(parts)})"


@dataclass(frozen=True)
class EquationsBlock:
    """A class's ``equations = ...`` assignment plus discovered metadata.

    ``class_name`` is the enclosing class's name. ``hosts`` is the
    tuple of host strings contributing logical lines (one entry for
    the single-string form, one per element for the list form, in
    source order). ``params`` is per-Param metadata in source order;
    ``param_names`` is the frozenset of those names, kept as a
    convenient lookup set for callers that only need names.

    The four ``class_*`` fields hold the 0-based file range of the
    enclosing ``class ...:`` statement (from the ``class`` keyword
    through the end of the class body). ``find_equations_blocks``
    populates them; direct constructions (e.g., in tests) leave
    them ``None``.
    """
    class_name: str
    hosts: tuple[EquationsHostString, ...]
    params: tuple[ParamInfo, ...] = ()
    param_names: frozenset[str] = frozenset()
    class_start_line: int | None = None
    class_start_col: int | None = None
    class_end_line: int | None = None
    class_end_col: int | None = None


def find_equations_blocks(source_text: str) -> list[EquationsBlock]:
    """Find every ``equations = ...`` assignment in ``source_text``.

    Returns the matching blocks in source order. Walks every
    ``ClassDef`` in the file, including nested classes (inside
    other classes or functions). Returns ``[]`` when the source
    has a syntax error, when no class declares an ``equations``
    attribute, or when every declared ``equations`` value has a
    shape the runtime would not accept (non-literal, list of
    non-strings, etc.).
    """
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []
    found: list[tuple[int, EquationsBlock]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            block = _block_from_classdef(node, source_text)
            if block is not None:
                found.append((node.lineno, block))
    found.sort(key=lambda pair: pair[0])
    return [block for _, block in found]


def _block_from_classdef(
    cls: ast.ClassDef, source_text: str,
) -> EquationsBlock | None:
    """Extract an :class:`EquationsBlock` from a single ``ClassDef``.

    Returns ``None`` when the class has no ``equations`` attribute or
    its value's shape is unsupported.
    """
    equations_value: ast.AST | None = None
    params: list[ParamInfo] = []
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign):
            if (
                len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                target_name = stmt.targets[0].id
                if target_name == "equations":
                    equations_value = stmt.value
                elif _is_param_call(stmt.value):
                    params.append(
                        _build_param_info(target_name, stmt.value, stmt),
                    )
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.value is not None:
                target_name = stmt.target.id
                if target_name == "equations":
                    equations_value = stmt.value
                elif _is_param_call(stmt.value):
                    params.append(
                        _build_param_info(target_name, stmt.value, stmt),
                    )
    if equations_value is None:
        return None
    hosts = _extract_hosts(equations_value, source_text)
    if not hosts:
        return None
    cls_end_line = getattr(cls, "end_lineno", None)
    cls_end_col = getattr(cls, "end_col_offset", None)
    return EquationsBlock(
        class_name=cls.name,
        hosts=tuple(hosts),
        params=tuple(params),
        param_names=frozenset(p.name for p in params),
        class_start_line=cls.lineno - 1,
        class_start_col=cls.col_offset,
        class_end_line=(
            cls_end_line - 1 if cls_end_line is not None
            else cls.lineno - 1
        ),
        class_end_col=(
            cls_end_col if cls_end_col is not None else cls.col_offset
        ),
    )


def _build_param_info(
    name: str, call: ast.Call, stmt: ast.stmt,
) -> ParamInfo:
    """Extract a :class:`ParamInfo` from a known ``Param(...)`` call.

    The caller has already verified ``call`` is a Param call (via
    :func:`_is_param_call`). Positional arguments past the first are
    ignored — the Param signature only consumes one positional
    (``type``). Keyword unpacking (``**kwargs``) is skipped silently
    because there's nothing static to extract from a splat.

    ``stmt`` is the enclosing :class:`ast.Assign` or
    :class:`ast.AnnAssign` statement. Its position info populates
    the ``assign_*`` fields so goto-definition can highlight the
    full assignment line.
    """
    type_text: str | None = (
        ast.unparse(call.args[0]) if call.args else None
    )
    default_text: str | None = None
    doc_text: str | None = None
    extras: list[tuple[str, str]] = []
    for kw in call.keywords:
        if kw.arg is None:
            # ``**something`` splat — no static name to record.
            continue
        if kw.arg == "default":
            default_text = ast.unparse(kw.value)
        elif kw.arg == "doc":
            # Surface the string content (no quotes) so hover can
            # render it directly. Non-literal doc values aren't
            # useful for static display; leave doc_text None.
            if (
                isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                doc_text = kw.value.value
        else:
            extras.append((kw.arg, ast.unparse(kw.value)))
    # AST positions are 1-based for line, 0-based for col. Convert
    # line to 0-based for LSP. ``end_lineno`` / ``end_col_offset``
    # have been populated since Python 3.8.
    assign_start_line = stmt.lineno - 1
    assign_start_col = stmt.col_offset
    end_line = getattr(stmt, "end_lineno", None)
    end_col = getattr(stmt, "end_col_offset", None)
    assign_end_line = (
        end_line - 1 if end_line is not None else assign_start_line
    )
    assign_end_col = (
        end_col if end_col is not None else assign_start_col
    )
    return ParamInfo(
        name=name,
        type_text=type_text,
        default_text=default_text,
        doc_text=doc_text,
        extras=tuple(extras),
        assign_start_line=assign_start_line,
        assign_start_col=assign_start_col,
        assign_end_line=assign_end_line,
        assign_end_col=assign_end_col,
    )


def _is_param_call(node: ast.AST) -> bool:
    """True if ``node`` is a call whose callee name ends in ``Param``.

    Matches ``Param(...)`` (a bare name) and ``something.Param(...)``
    (an attribute access). Name-based, since the analyzer can't
    follow imports without executing user code; a third-party
    ``Param`` class shadowing scadwright's would produce a false
    positive here, but the consequence is only a spurious entry in
    ``param_names``.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Param"
    if isinstance(func, ast.Attribute):
        return func.attr == "Param"
    return False


def _extract_hosts(
    value: ast.AST, source_text: str,
) -> list[EquationsHostString]:
    """Extract host-string metadata from the RHS of ``equations = ...``."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        host = _host_from_constant(value, source_text)
        return [host] if host is not None else []
    if isinstance(value, (ast.List, ast.Tuple)):
        out: list[EquationsHostString] = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                host = _host_from_constant(elt, source_text)
                if host is not None:
                    out.append(host)
            # Other shapes (variables, expressions, non-string constants)
            # are skipped — the runtime won't support them either.
        return out
    return []


def _host_from_constant(
    node: ast.Constant, source_text: str,
) -> EquationsHostString | None:
    """Build an :class:`EquationsHostString` from a string-literal node.

    Returns ``None`` when the source segment cannot be retrieved or
    has an unrecognized shape (e.g., implicit string concatenation
    folds two literals into one Constant whose source segment is
    ``'"a" "b"'`` — there is no single content range to record).
    """
    segment = ast.get_source_segment(source_text, node)
    if segment is None:
        return None
    prefix_len = _string_prefix_length(segment)
    rest = segment[prefix_len:]
    if not rest:
        return None
    if rest.startswith('"""') or rest.startswith("'''"):
        quote = rest[:3]
    elif rest[0] in ('"', "'"):
        quote = rest[0]
    else:
        return None
    quote_len = len(quote)
    if not rest.endswith(quote) or len(rest) < 2 * quote_len:
        return None
    raw_text = rest[quote_len:-quote_len]
    # Detect implicit string concatenation: the source segment for
    # ``"a" "b"`` would have a closing quote in the middle. The cheap
    # check: confirm the content has no unescaped occurrence of the
    # quote sequence inside it. Conservative — better to skip a
    # malformed host than to mis-map columns later.
    if quote in raw_text:
        return None
    content_line = node.lineno - 1  # 0-based
    content_col = node.col_offset + prefix_len + quote_len
    return EquationsHostString(
        raw_text=raw_text,
        content_start_line=content_line,
        content_start_col=content_col,
    )


def _string_prefix_length(segment: str) -> int:
    """Return the count of prefix chars at the start of a string literal.

    Recognizes the case-insensitive prefixes ``r``, ``b``, ``u``,
    ``f``, in any 1- or 2-character combination. Stops at the first
    non-prefix character (which must be the opening quote).
    """
    i = 0
    while (
        i < _MAX_PREFIX_LEN
        and i < len(segment)
        and segment[i] in _STRING_PREFIX_CHARS
    ):
        i += 1
    return i


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
