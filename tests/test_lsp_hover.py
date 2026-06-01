"""Tests for the LSP curated hover-content builder.

Covers ``extract_word_at`` over many cursor positions, the
context-dispatch behavior of ``build_hover_content``, and the
specific markdown shape for curated names and type tags. Param-
aware hover lands in a separate step.
"""

from __future__ import annotations

import pytest

from scadwright.lsp.context import ContextKind
from scadwright.lsp.hover import (
    build_hover_content,
    extract_word_at,
)


# =============================================================================
# extract_word_at
# =============================================================================


def test_extract_word_in_middle_of_identifier() -> None:
    assert extract_word_at("width = 5", 2) == "width"


def test_extract_word_at_start_of_identifier() -> None:
    assert extract_word_at("width = 5", 0) == "width"


def test_extract_word_at_end_of_identifier() -> None:
    assert extract_word_at("width = 5", 5) == "width"


def test_extract_word_at_end_of_line_on_last_identifier() -> None:
    line = "x = width"
    assert extract_word_at(line, len(line)) == "width"


def test_extract_word_at_word_right_edge_returns_word() -> None:
    # Col 1 of "a + b" is just past 'a' (gap between 'a' and the
    # space). Per LSP convention, the cursor touches 'a' from the
    # right edge — extract_word_at returns "a".
    assert extract_word_at("a + b", 1) == "a"


def test_extract_word_in_whitespace_gap_returns_none() -> None:
    # Mid-whitespace, not touching any identifier on either side.
    assert extract_word_at("a   +   b", 2) is None


def test_extract_word_on_operator_returns_none() -> None:
    assert extract_word_at("a + b", 2) is None  # cursor on '+'


def test_extract_word_on_numeric_literal_returns_none() -> None:
    assert extract_word_at("x = 123", 4) is None  # starts with digit


def test_extract_word_with_underscore() -> None:
    assert extract_word_at("at_least_one()", 5) == "at_least_one"


def test_extract_word_with_digits_after_letter() -> None:
    assert extract_word_at("var2 + 1", 1) == "var2"


def test_extract_word_negative_col_returns_none() -> None:
    assert extract_word_at("abc", -1) is None


def test_extract_word_col_past_end_returns_none() -> None:
    assert extract_word_at("abc", 100) is None


def test_extract_word_empty_line_col_zero_returns_none() -> None:
    assert extract_word_at("", 0) is None


# =============================================================================
# build_hover_content — context dispatch
# =============================================================================


def test_string_context_returns_none() -> None:
    assert build_hover_content("sin", ContextKind.STRING) is None


def test_comment_context_returns_none() -> None:
    assert build_hover_content("sin", ContextKind.COMMENT) is None


def test_unknown_name_in_expression_returns_none() -> None:
    assert build_hover_content("not_a_known_thing", ContextKind.EXPRESSION) is None


def test_unknown_name_in_type_tag_returns_none() -> None:
    assert build_hover_content("not_a_type", ContextKind.TYPE_TAG) is None


# =============================================================================
# build_hover_content — curated names in expression context
# =============================================================================


def test_sin_hover_in_expression() -> None:
    h = build_hover_content("sin", ContextKind.EXPRESSION)
    assert h is not None
    assert "sin(x)" in h.markdown
    assert "degrees" in h.markdown.lower()


def test_atan2_hover_two_arg_form() -> None:
    h = build_hover_content("atan2", ContextKind.EXPRESSION)
    assert h is not None
    assert "atan2(y, x)" in h.markdown


@pytest.mark.parametrize(
    "name",
    [
        "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
        "degrees", "radians",
        "sqrt", "log", "exp", "abs", "ceil", "floor",
        "min", "max", "sum", "round", "len",
        "int", "float", "bool", "str",
        "tuple", "list", "dict", "set", "frozenset",
        "range", "zip", "enumerate", "sorted", "reversed",
        "all", "any", "isinstance",
        "exactly_one", "at_least_one", "at_most_one", "all_or_none",
        "pi", "e", "inf",
        "True", "False", "None",
    ],
)
def test_every_curated_name_has_hover(name: str) -> None:
    h = build_hover_content(name, ContextKind.EXPRESSION)
    assert h is not None, f"missing hover for {name!r}"
    assert h.markdown  # non-empty


def test_cardinality_hover_mentions_sigil() -> None:
    h = build_hover_content("exactly_one", ContextKind.EXPRESSION)
    assert h is not None
    # Surface the connection to the ``?`` sigil — that idiom is the
    # main reason the cardinality helpers exist.
    assert "?" in h.markdown or "sigil" in h.markdown.lower()


def test_constant_hover_includes_label() -> None:
    h = build_hover_content("pi", ContextKind.EXPRESSION)
    assert h is not None
    assert "pi" in h.markdown


# =============================================================================
# build_hover_content — type tags in TYPE_TAG context
# =============================================================================


@pytest.mark.parametrize(
    "name", ["bool", "int", "str", "tuple", "list", "dict"],
)
def test_every_type_tag_has_hover(name: str) -> None:
    h = build_hover_content(name, ContextKind.TYPE_TAG)
    assert h is not None
    assert "Type tag" in h.markdown
    assert name in h.markdown


def test_type_tag_hover_for_unknown_name_returns_none() -> None:
    # Even though "float" is a type-like name elsewhere, it isn't in
    # the inline-annotation allowlist, so it has no type-tag hover.
    assert build_hover_content("float", ContextKind.TYPE_TAG) is None


# =============================================================================
# Same name, different contexts
# =============================================================================


def test_bool_hover_differs_between_expression_and_type_tag() -> None:
    expr_h = build_hover_content("bool", ContextKind.EXPRESSION)
    tag_h = build_hover_content("bool", ContextKind.TYPE_TAG)
    assert expr_h is not None
    assert tag_h is not None
    # In expression: it's the constructor.
    assert "bool(x)" in expr_h.markdown
    # In type tag: it's an annotation type.
    assert "Type tag" in tag_h.markdown


# =============================================================================
# Block-aware hover (Params + auto-declared)
# =============================================================================


from scadwright.lsp.analyze import find_equations_blocks  # noqa: E402


def _block(src: str):
    [block] = find_equations_blocks(src)
    return block


def test_hover_param_shows_signature_and_doc() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, default=5, doc="The width")\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    h = build_hover_content(
        "width", ContextKind.EXPRESSION, block=block,
    )
    assert h is not None
    assert "width" in h.markdown
    assert "Param" in h.markdown
    # Signature shows non-doc fields; doc text appears separately.
    assert "Param(float, default=5)" in h.markdown
    assert "The width" in h.markdown


def test_hover_param_without_doc_omits_doc_block() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    h = build_hover_content(
        "width", ContextKind.EXPRESSION, block=block,
    )
    assert h is not None
    assert "Param(float)" in h.markdown


def test_hover_auto_declared_shows_origin_line() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    b = a + 2\n'
        '    c = a + b\n'
        '    """\n'
    )
    block = _block(src)
    # Cursor on line 2; "a" was declared on line 0.
    h = build_hover_content(
        "a", ContextKind.EXPRESSION,
        block=block, host_index=0, line_index=2,
    )
    assert h is not None
    assert "auto-declared" in h.markdown
    assert "line 0" in h.markdown


def test_hover_auto_declared_origin_is_first_occurrence() -> None:
    # If a name appears as a bare target on multiple earlier lines,
    # the first one wins.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = 1\n'
        '    x = 2\n'
        '    y = x\n'
        '    """\n'
    )
    block = _block(src)
    h = build_hover_content(
        "x", ContextKind.EXPRESSION,
        block=block, host_index=0, line_index=2,
    )
    assert h is not None
    assert "line 0" in h.markdown


def test_hover_auto_declared_for_current_line_target_returns_none() -> None:
    # ``c`` is declared on the cursor's own line, not earlier.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    c = a + 1\n'
        '    """\n'
    )
    block = _block(src)
    h = build_hover_content(
        "c", ContextKind.EXPRESSION,
        block=block, host_index=0, line_index=1,
    )
    assert h is None


def test_hover_param_takes_precedence_over_curated() -> None:
    # Even though ``min`` collides with a curated builtin (the
    # runtime would reject this; we still resolve to the Param), the
    # Param hover wins.
    src = (
        'class A:\n'
        '    min = Param(float)\n'
        '    equations = "x = min"\n'
    )
    block = _block(src)
    h = build_hover_content(
        "min", ContextKind.EXPRESSION, block=block,
    )
    assert h is not None
    assert "Param" in h.markdown


def test_hover_auto_declared_takes_precedence_over_curated() -> None:
    # Same shape with an auto-declared name.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    pi = 3.14\n'
        '    x = pi * 2\n'
        '    """\n'
    )
    block = _block(src)
    h = build_hover_content(
        "pi", ContextKind.EXPRESSION,
        block=block, host_index=0, line_index=1,
    )
    assert h is not None
    assert "auto-declared" in h.markdown


def test_hover_unknown_name_with_block_returns_none() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    h = build_hover_content(
        "completely_unknown", ContextKind.EXPRESSION, block=block,
    )
    assert h is None


def test_hover_curated_still_works_with_block() -> None:
    # When the cursor's name isn't a Param or auto-declared, fall
    # through to the curated table.
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = sin(width)"\n'
    )
    block = _block(src)
    h = build_hover_content(
        "sin", ContextKind.EXPRESSION,
        block=block, host_index=0, line_index=0,
    )
    assert h is not None
    assert "sin(x)" in h.markdown


def test_hover_auto_declared_flat_index_across_hosts() -> None:
    # First host has 2 logical lines; second host's first line is
    # flat index 2.
    src = (
        'class A:\n'
        '    equations = [\n'
        '        "a = 1",\n'
        '        "b = 2",\n'
        '        "c = a + b",\n'
        '    ]\n'
    )
    block = _block(src)
    # Cursor on host 2, line 0 (flat index 2). "a" was first declared
    # on host 0, line 0 (flat index 0). "b" on host 1, line 0 (flat 1).
    h_a = build_hover_content(
        "a", ContextKind.EXPRESSION,
        block=block, host_index=2, line_index=0,
    )
    h_b = build_hover_content(
        "b", ContextKind.EXPRESSION,
        block=block, host_index=2, line_index=0,
    )
    assert h_a is not None and "line 0" in h_a.markdown
    assert h_b is not None and "line 1" in h_b.markdown


def test_hover_param_in_type_tag_context_is_not_param_hover() -> None:
    # In TYPE_TAG context, Param names don't apply — only the type-tag
    # allowlist does.
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    h = build_hover_content(
        "width", ContextKind.TYPE_TAG, block=block,
    )
    assert h is None


def test_hover_string_context_with_block_returns_none() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    assert build_hover_content(
        "width", ContextKind.STRING, block=block,
    ) is None


def test_hover_attribute_chain_resolves_param() -> None:
    src = (
        'class C:\n'
        '    radial = Param(float, doc="Radial clearance")\n'
        '    equations = "x = radial"\n'
        '\n'
        'class B:\n'
        '    clearances = Param(C)\n'
        '    equations = "x = clearances.radial"\n'
        '\n'
        'class A:\n'
        '    spec = Param(B)\n'
        '    equations = "y = spec.clearances.radial"\n'
    )
    blocks = tuple(find_equations_blocks(src))
    a_block = next(b for b in blocks if b.class_name == "A")
    h = build_hover_content(
        "radial",
        ContextKind.ATTRIBUTE,
        block=a_block,
        attribute_chain=["spec", "clearances"],
        sibling_blocks=blocks,
    )
    assert h is not None
    assert "Param(float)" in h.markdown
    assert "Radial clearance" in h.markdown


def test_hover_attribute_chain_broken_returns_none() -> None:
    src = (
        'class B:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
        '\n'
        'class A:\n'
        '    spec = Param(B)\n'
        '    equations = "y = spec.nonexistent.whatever"\n'
    )
    blocks = tuple(find_equations_blocks(src))
    a_block = next(b for b in blocks if b.class_name == "A")
    h = build_hover_content(
        "whatever",
        ContextKind.ATTRIBUTE,
        block=a_block,
        attribute_chain=["spec", "nonexistent"],
        sibling_blocks=blocks,
    )
    assert h is None
