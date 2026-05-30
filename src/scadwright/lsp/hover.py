"""Hover-content generators for cursor positions in equations text.

Maps a name + context to a markdown body describing what the name
is. The handler in ``server.py`` adapts the internal
:class:`HoverContent` shape into ``lsprotocol.types.Hover`` at the
LSP boundary.

Resolution order in expression context:

1. The surrounding class's Params, when an
   :class:`scadwright.lsp.analyze.EquationsBlock` is supplied.
   Renders the compact ``Param(...)`` signature plus the literal
   ``doc=`` text if present.
2. Bare-Name targets declared on equation lines preceding the
   cursor (auto-declared by the resolver). Renders an
   "auto-declared" note plus the originating equations-line index.
3. Curated namespace (math, builtins, cardinality helpers,
   ``isinstance``, constants, language values). Renders signature
   + brief description.

Type-tag context (after ``:``) resolves only in the inline-tag
allowlist; anything else returns ``None``. String and comment
contexts always return ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.component.equations.lex import _split_logical_lines
from scadwright.lsp.analyze import (
    EquationsBlock,
    ParamInfo,
    auto_declared_origins_before,
    auto_declared_origins_in_block,
)
from scadwright.lsp.context import ContextKind
from scadwright.lsp.resolve import resolve_chain_to_block


@dataclass(frozen=True)
class HoverContent:
    """LSP-shaped hover body.

    ``markdown`` is rendered as ``MarkupContent(kind=markdown)`` at
    the LSP boundary. The content is short — one or two sentences
    plus a code-formatted signature when applicable.
    """
    markdown: str


def build_hover_content(
    name: str,
    context: ContextKind,
    *,
    block: EquationsBlock | None = None,
    host_index: int = 0,
    line_index: int = 0,
    attribute_chain: list[str] | None = None,
    sibling_blocks: tuple[EquationsBlock, ...] = (),
) -> HoverContent | None:
    """Return hover content for ``name`` in ``context``, or ``None``
    when no static info is available.

    String and comment contexts always return ``None``. Type-tag
    context looks up the name in the type-tag docs.

    Expression context resolves Params first (from ``block.params``
    when ``block`` is provided), then auto-declared targets (names
    appearing as bare-Name equation targets on lines strictly
    before ``(host_index, line_index)``), then the curated
    namespace. The first match wins.

    Attribute context (``spec.clearances.|``) resolves the dotted
    chain through Param type_text lookups and returns the hover
    info for ``name`` in the resolved block's Params.
    """
    if context in (ContextKind.STRING, ContextKind.COMMENT):
        return None
    if context == ContextKind.TYPE_TAG:
        body = _TYPE_TAG_DOCS.get(name)
        return HoverContent(markdown=body) if body is not None else None
    if context == ContextKind.ATTRIBUTE:
        if block is not None and attribute_chain is not None:
            resolved = resolve_chain_to_block(
                attribute_chain, block, sibling_blocks,
            )
            if resolved is not None:
                md = _param_hover_markdown(name, resolved)
                if md is not None:
                    return HoverContent(markdown=md)
        return None
    if context == ContextKind.EXPRESSION:
        if block is not None:
            md = _param_hover_markdown(name, block)
            if md is not None:
                return HoverContent(markdown=md)
            md = _auto_declared_hover_markdown(
                name, block, host_index, line_index,
            )
            if md is not None:
                return HoverContent(markdown=md)
        body = _CURATED_DOCS.get(name)
        return HoverContent(markdown=body) if body is not None else None
    return None


def build_python_attribute_hover(
    attr_name: str,
    source_block: EquationsBlock,
) -> HoverContent | None:
    """Hover content for ``attr_name`` accessed externally as
    ``SourceClass.attr_name`` from Python code outside an equations
    block. Returns ``None`` when the source class doesn't declare
    ``attr_name``.

    Resolves Params first, then auto-declared targets anywhere in
    the source block. The cursor-relative auto-declared constraint
    used by ``build_hover_content``'s expression branch doesn't
    apply here — the access is external, so visibility is the
    whole block.
    """
    md = _param_hover_markdown(attr_name, source_block)
    if md is not None:
        return HoverContent(markdown=md)
    origins = auto_declared_origins_in_block(source_block)
    if attr_name in origins:
        origin_host_index, origin_line_index = origins[attr_name]
        flat_index = _flat_logical_line_index(
            source_block, origin_host_index, origin_line_index,
        )
        return HoverContent(markdown=(
            f"**`{attr_name}`** *(auto-declared)*\n\n"
            f"Introduced as an equation target on equations line "
            f"{flat_index} of `{source_block.class_name}`."
        ))
    return None


def extract_word_at(line: str, col: int) -> str | None:
    """Return the Python identifier touching column ``col`` in
    ``line``, or ``None`` if the cursor isn't on an identifier.

    A cursor "touches" an identifier when an identifier character
    sits at ``col`` or at ``col - 1``. Walk left and right from the
    cursor over alphanumerics and underscores; if the resulting
    span is non-empty and starts with a letter or underscore, it's
    an identifier. Spans starting with a digit (e.g., the user is
    hovering on a numeric literal) yield ``None``.
    """
    if col < 0:
        return None
    n = len(line)
    if col > n:
        return None
    start = col
    while start > 0 and _is_ident_char(line[start - 1]):
        start -= 1
    end = col
    while end < n and _is_ident_char(line[end]):
        end += 1
    if start == end:
        return None
    word = line[start:end]
    if word[0].isdigit():
        return None
    return word


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


# =============================================================================
# Static doc tables
# =============================================================================
#
# Each entry is a complete markdown body. Format convention:
#
#     **`signature`** — one-sentence description.
#
#     Optional second sentence with extra detail.
#
# Kept terse so the hover popup stays scannable.


_CURATED_DOCS: dict[str, str] = {
    # Trig in degrees, matching SCAD and ``scadwright.math``.
    "sin": "**`sin(x)`** — sine of `x` in degrees.",
    "cos": "**`cos(x)`** — cosine of `x` in degrees.",
    "tan": "**`tan(x)`** — tangent of `x` in degrees.",
    "asin": "**`asin(x)`** — inverse sine of `x`. Returns degrees.",
    "acos": "**`acos(x)`** — inverse cosine of `x`. Returns degrees.",
    "atan": "**`atan(x)`** — inverse tangent of `x`. Returns degrees.",
    "atan2": (
        "**`atan2(y, x)`** — two-argument inverse tangent of `y / x`. "
        "Returns degrees."
    ),
    "degrees": "**`degrees(x)`** — convert radians to degrees.",
    "radians": "**`radians(x)`** — convert degrees to radians.",
    # Other math.
    "sqrt": "**`sqrt(x)`** — non-negative square root of `x`.",
    "log": "**`log(x)`** — natural logarithm of `x`.",
    "exp": "**`exp(x)`** — exponential of `x` (`e**x`).",
    "abs": "**`abs(x)`** — absolute value of `x`.",
    "ceil": "**`ceil(x)`** — smallest integer not less than `x`.",
    "floor": "**`floor(x)`** — largest integer not greater than `x`.",
    # Numeric reductions / queries.
    "min": "**`min(*args)`** — smallest of the arguments.",
    "max": "**`max(*args)`** — largest of the arguments.",
    "sum": "**`sum(iterable)`** — sum of the elements.",
    "round": "**`round(x[, ndigits])`** — round `x` to the nearest integer or to `ndigits` decimal places.",
    "len": "**`len(x)`** — number of elements in `x`.",
    # Type constructors / coercion (also valid as type-tag names).
    "int": "**`int(x)`** — convert `x` to an integer.",
    "float": "**`float(x)`** — convert `x` to a float.",
    "bool": "**`bool(x)`** — convert `x` to a boolean.",
    "str": "**`str(x)`** — convert `x` to a string.",
    # Iterable constructors.
    "tuple": "**`tuple(iterable)`** — build a tuple from an iterable.",
    "list": "**`list(iterable)`** — build a list from an iterable.",
    "dict": "**`dict(...)`** — build a dictionary.",
    "set": "**`set(iterable)`** — build a set from an iterable.",
    "frozenset": "**`frozenset(iterable)`** — build an immutable set from an iterable.",
    "range": "**`range(stop)`** / **`range(start, stop[, step])`** — sequence of integers.",
    # Iterator helpers.
    "zip": "**`zip(*iterables)`** — pairwise iteration over multiple iterables.",
    "enumerate": "**`enumerate(iterable)`** — iterator of `(index, value)` pairs.",
    "sorted": "**`sorted(iterable)`** — return a sorted list of the items.",
    "reversed": "**`reversed(iterable)`** — iterator over the items in reverse.",
    # Boolean reductions.
    "all": "**`all(iterable)`** — `True` when every element is truthy. Vacuously `True` for `[]`.",
    "any": "**`any(iterable)`** — `True` when any element is truthy. Vacuously `False` for `[]`.",
    # Predicate calls (in expression context).
    "isinstance": "**`isinstance(obj, cls)`** — `True` if `obj` is an instance of `cls`.",
    # Cardinality helpers — combine with the `?` sigil.
    "exactly_one": (
        "**`exactly_one(*args)`** — `True` iff exactly one argument is "
        "not `None`. Use with `?` sigils to require one of a set of "
        "alternative parameters."
    ),
    "at_least_one": (
        "**`at_least_one(*args)`** — `True` iff at least one argument "
        "is not `None`."
    ),
    "at_most_one": (
        "**`at_most_one(*args)`** — `True` iff zero or one argument "
        "is not `None`. Vacuously `True` for an empty argument list."
    ),
    "all_or_none": (
        "**`all_or_none(*args)`** — `True` iff every argument is "
        "`None`, or every argument is not `None`. Vacuously `True` "
        "for an empty argument list."
    ),
    # Constants.
    "pi": "**`pi`** — `math.pi` (≈ 3.14159).",
    "e": "**`e`** — `math.e` (Euler's number, ≈ 2.71828).",
    "inf": "**`inf`** — `math.inf` (positive infinity).",
    # Language values.
    "True": "**`True`** — boolean true.",
    "False": "**`False`** — boolean false.",
    "None": "**`None`** — the absence of a value.",
}


_TYPE_TAG_DOCS: dict[str, str] = {
    "bool": (
        "Type tag **`bool`** — boolean value. Allowed in inline "
        "annotations: `?flag:bool = True`."
    ),
    "int": (
        "Type tag **`int`** — integer value. Allowed in inline "
        "annotations: `?count:int`."
    ),
    "str": (
        "Type tag **`str`** — string value. Allowed in inline "
        "annotations: `?label:str = 'a'`."
    ),
    "tuple": (
        "Type tag **`tuple`** — tuple value. Allowed in inline "
        "annotations: `?size:tuple = (1, 2)`."
    ),
    "list": (
        "Type tag **`list`** — list value. Allowed in inline "
        "annotations: `?items:list = [1, 2, 3]`."
    ),
    "dict": (
        "Type tag **`dict`** — dict value. Allowed in inline "
        "annotations: `?spec:dict = {}`."
    ),
}


# =============================================================================
# Block-aware hover (Params + auto-declared)
# =============================================================================


def _param_hover_markdown(
    name: str, block: EquationsBlock,
) -> str | None:
    """Markdown body for a class-declared Param, or ``None`` if
    ``name`` isn't one of the block's Params."""
    for p in block.params:
        if p.name == name:
            return _render_param(p)
    return None


def _render_param(p: ParamInfo) -> str:
    parts = [f"**`{p.name}`** *(Param)*", "", f"`{p.signature()}`"]
    if p.doc_text:
        parts.extend(["", p.doc_text])
    return "\n".join(parts)


def _auto_declared_hover_markdown(
    name: str,
    block: EquationsBlock,
    host_index: int,
    line_index: int,
) -> str | None:
    """Markdown body for an auto-declared bare-Name target, or
    ``None`` if ``name`` isn't declared on any line strictly
    preceding the cursor.
    """
    origins = auto_declared_origins_before(block, host_index, line_index)
    origin = origins.get(name)
    if origin is None:
        return None
    origin_host_index, origin_line_index = origin
    flat_index = _flat_logical_line_index(
        block, origin_host_index, origin_line_index,
    )
    return (
        f"**`{name}`** *(auto-declared)*\n\n"
        f"Introduced as an equation target on equations line "
        f"{flat_index}."
    )


def _flat_logical_line_index(
    block: EquationsBlock, host_index: int, line_index_in_host: int,
) -> int:
    """Convert a per-host ``(host_index, line_index)`` into a flat
    0-based logical-line index across the whole block.

    Mirrors how the runtime numbers equation lines: the
    ``equations`` attribute is flattened across hosts at class-define
    time, so an error message of ``equations[3]`` refers to the
    flattened position. Hover surfaces the same numbering.
    """
    flat = 0
    for h_idx, host in enumerate(block.hosts):
        if h_idx == host_index:
            return flat + line_index_in_host
        flat += sum(1 for _ in _split_logical_lines(host.raw_text))
    return flat
