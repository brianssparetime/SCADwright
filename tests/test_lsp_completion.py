"""Tests for the LSP curated-namespace completion builder.

Covers each context branch (expression / type-tag / string /
comment), shape of the items (function vs constant vs class),
auto-paren snippet for callables, alphabetical sort order, and
specific items the design doc calls out.
"""

from __future__ import annotations

from scadwright.lsp.completion import (
    CompletionItem,
    build_completion_items,
)
from scadwright.lsp.context import ContextKind


# =============================================================================
# Context-branch behavior
# =============================================================================


def test_string_context_returns_no_items() -> None:
    assert build_completion_items(ContextKind.STRING) == []


def test_comment_context_returns_no_items() -> None:
    assert build_completion_items(ContextKind.COMMENT) == []


def test_type_tag_context_returns_six_class_items() -> None:
    items = build_completion_items(ContextKind.TYPE_TAG)
    labels = [it.label for it in items]
    assert set(labels) == {"bool", "int", "str", "tuple", "list", "dict"}
    assert all(it.kind == "class" for it in items)
    # No snippet inserts for type names — they're plain identifiers.
    assert all(not it.is_snippet for it in items)


def test_expression_context_includes_math_builtins_and_cardinality() -> None:
    items = build_completion_items(ContextKind.EXPRESSION)
    labels = {it.label for it in items}
    # Math callables (subset)
    for name in ("sin", "cos", "sqrt", "atan2", "log"):
        assert name in labels, f"missing math callable: {name}"
    # Builtins (subset)
    for name in ("len", "abs", "min", "max", "sum", "all", "any"):
        assert name in labels, f"missing builtin callable: {name}"
    # Cardinality helpers
    for name in (
        "exactly_one", "at_least_one", "at_most_one", "all_or_none",
    ):
        assert name in labels, f"missing cardinality helper: {name}"
    # Constants
    for name in ("pi", "e", "inf", "True", "False", "None"):
        assert name in labels, f"missing constant: {name}"
    # Predicate-only call name not in _CURATED_BUILTINS.
    assert "isinstance" in labels


def test_expression_items_are_alphabetically_sorted() -> None:
    items = build_completion_items(ContextKind.EXPRESSION)
    labels = [it.label for it in items]
    assert labels == sorted(labels)


def test_no_duplicate_labels_in_expression_items() -> None:
    items = build_completion_items(ContextKind.EXPRESSION)
    labels = [it.label for it in items]
    assert len(labels) == len(set(labels))


# =============================================================================
# Item-shape details
# =============================================================================


def test_callable_items_use_auto_paren_snippet() -> None:
    items = {it.label: it for it in build_completion_items(
        ContextKind.EXPRESSION,
    )}
    sin = items["sin"]
    assert sin.kind == "function"
    assert sin.is_snippet is True
    assert sin.insert_text == "sin($0)"


def test_constant_items_have_no_snippet() -> None:
    items = {it.label: it for it in build_completion_items(
        ContextKind.EXPRESSION,
    )}
    pi = items["pi"]
    assert pi.kind == "constant"
    assert pi.is_snippet is False
    assert pi.insert_text is None  # default: insert label as-is


def test_true_false_none_are_constants_not_functions() -> None:
    items = {it.label: it for it in build_completion_items(
        ContextKind.EXPRESSION,
    )}
    for name in ("True", "False", "None"):
        assert items[name].kind == "constant", (
            f"{name} should be classified as constant, not function"
        )
        assert items[name].is_snippet is False


def test_int_str_appear_as_callables_in_expression_context() -> None:
    # The same names appear as type-tag completions in TYPE_TAG context
    # (kind=class) but here they're constructors.
    items = {it.label: it for it in build_completion_items(
        ContextKind.EXPRESSION,
    )}
    assert items["int"].kind == "function"
    assert items["int"].insert_text == "int($0)"
    assert items["str"].kind == "function"


# =============================================================================
# Mutability
# =============================================================================


def test_returned_list_is_a_fresh_copy() -> None:
    a = build_completion_items(ContextKind.EXPRESSION)
    b = build_completion_items(ContextKind.EXPRESSION)
    assert a == b
    assert a is not b
    # Mutating the returned list doesn't affect the next call.
    a.clear()
    c = build_completion_items(ContextKind.EXPRESSION)
    assert len(c) == len(b)


def test_completion_item_is_immutable_dataclass() -> None:
    item = CompletionItem(label="x", kind="function")
    # Frozen dataclass — assignment raises FrozenInstanceError, which
    # subclasses Exception.
    try:
        item.label = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("CompletionItem should be frozen")


# =============================================================================
# Type-tag specifics
# =============================================================================


def test_type_tag_items_are_alphabetically_sorted() -> None:
    items = build_completion_items(ContextKind.TYPE_TAG)
    labels = [it.label for it in items]
    assert labels == sorted(labels)


def test_type_tag_items_match_inline_allowlist() -> None:
    # Sanity: the type-tag completion list matches the allowlist that
    # the resolver actually accepts.
    from scadwright.component.equations import _INLINE_TYPE_ALLOWLIST
    items = build_completion_items(ContextKind.TYPE_TAG)
    assert {it.label for it in items} == set(_INLINE_TYPE_ALLOWLIST)


# =============================================================================
# Param-aware completion (block + cursor info)
# =============================================================================


from scadwright.lsp.analyze import find_equations_blocks  # noqa: E402


def _block(src: str):
    [block] = find_equations_blocks(src)
    return block


def test_param_aware_includes_class_param_items() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, default=5)\n'
        '    height = Param(float)\n'
        '    equations = "x = width + height"\n'
    )
    block = _block(src)
    items = build_completion_items(
        ContextKind.EXPRESSION, block=block, host_index=0, line_index=0,
    )
    by_label = {it.label: it for it in items}
    assert "width" in by_label
    assert "height" in by_label
    assert by_label["width"].kind == "variable"
    assert "Param(float, default=5)" == by_label["width"].detail
    assert by_label["height"].detail == "Param(float)"


def test_param_aware_carries_doc_into_documentation() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, doc="The widget width")\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    items = build_completion_items(
        ContextKind.EXPRESSION, block=block, host_index=0, line_index=0,
    )
    by_label = {it.label: it for it in items}
    assert by_label["width"].documentation == "The widget width"


def test_param_aware_includes_auto_declared_targets_before_cursor() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    b = a + 2\n'
        '    c = a + b\n'
        '    """\n'
    )
    block = _block(src)
    # Cursor on line 2 (index 2): "a" and "b" are auto-declared.
    items = build_completion_items(
        ContextKind.EXPRESSION, block=block, host_index=0, line_index=2,
    )
    by_label = {it.label: it for it in items}
    assert "a" in by_label and by_label["a"].detail == "auto-declared"
    assert "b" in by_label and by_label["b"].detail == "auto-declared"
    # "c" is the cursor's own line — not yet declared.
    assert "c" not in by_label


def test_param_aware_param_takes_precedence_over_auto_declared() -> None:
    # ``width`` is both a Param AND would appear as an auto-declared
    # target via "width = something" — the Param item wins, no
    # duplicate.
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width = 5\n'
        '    height = width + 1\n'
        '    """\n'
    )
    block = _block(src)
    items = build_completion_items(
        ContextKind.EXPRESSION, block=block, host_index=0, line_index=1,
    )
    width_items = [it for it in items if it.label == "width"]
    assert len(width_items) == 1
    assert width_items[0].detail == "Param(float)"


def test_param_aware_results_alphabetically_sorted() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    apple = 1\n'
        '    zebra = 2\n'
        '    middle = apple + zebra\n'
        '    """\n'
    )
    block = _block(src)
    items = build_completion_items(
        ContextKind.EXPRESSION, block=block, host_index=0, line_index=2,
    )
    labels = [it.label for it in items]
    assert labels == sorted(labels)


def test_param_aware_without_block_matches_curated_only() -> None:
    # Calling without ``block`` is the Step-3 behavior: just curated.
    plain = build_completion_items(ContextKind.EXPRESSION)
    src = 'class A:\n    equations = "x = 1"\n'
    block = _block(src)
    rich = build_completion_items(
        ContextKind.EXPRESSION, block=block, host_index=0, line_index=0,
    )
    # The block has no Params and no earlier lines; rich should match
    # plain in label set.
    assert {it.label for it in rich} == {it.label for it in plain}


def test_param_aware_extras_join_param_signature() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, positive=True, range=(0, 10))\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    items = build_completion_items(
        ContextKind.EXPRESSION, block=block, host_index=0, line_index=0,
    )
    by_label = {it.label: it for it in items}
    detail = by_label["width"].detail
    assert "positive=True" in detail
    assert "range=(0, 10)" in detail


def test_type_tag_context_unaffected_by_block() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "?x:int = 5"\n'
    )
    block = _block(src)
    items = build_completion_items(
        ContextKind.TYPE_TAG, block=block, host_index=0, line_index=0,
    )
    assert {it.label for it in items} == {
        "bool", "int", "str", "tuple", "list", "dict",
    }


# =============================================================================
# Attribute completion (same-file cross-Component)
# =============================================================================


def _all_blocks(src: str):
    from scadwright.lsp.analyze import find_equations_blocks
    return tuple(find_equations_blocks(src))


def test_attribute_completion_returns_target_class_params() -> None:
    src = (
        'class B:\n'
        '    width = Param(float)\n'
        '    height = Param(float)\n'
        '    equations = "x = width"\n'
        '\n'
        'class A:\n'
        '    b = Param(B)\n'
        '    equations = "y = b.width"\n'
    )
    blocks = _all_blocks(src)
    a_block = next(b for b in blocks if b.class_name == "A")
    items = build_completion_items(
        ContextKind.ATTRIBUTE,
        block=a_block,
        attribute_base="b",
        sibling_blocks=blocks,
    )
    assert {it.label for it in items} == {"width", "height"}


def test_attribute_completion_carries_param_signature() -> None:
    src = (
        'class B:\n'
        '    width = Param(float, default=5)\n'
        '    equations = "x = width"\n'
        '\n'
        'class A:\n'
        '    b = Param(B)\n'
        '    equations = "y = b.width"\n'
    )
    blocks = _all_blocks(src)
    a_block = next(b for b in blocks if b.class_name == "A")
    items = build_completion_items(
        ContextKind.ATTRIBUTE,
        block=a_block,
        attribute_base="b",
        sibling_blocks=blocks,
    )
    [width_item] = [it for it in items if it.label == "width"]
    assert width_item.detail == "Param(float, default=5)"


def test_attribute_completion_no_match_returns_empty() -> None:
    # Base name maps to a type with no matching class in the file.
    src = (
        'class A:\n'
        '    b = Param(SomeOtherType)\n'
        '    equations = "y = b.width"\n'
    )
    blocks = _all_blocks(src)
    [a_block] = blocks
    items = build_completion_items(
        ContextKind.ATTRIBUTE,
        block=a_block,
        attribute_base="b",
        sibling_blocks=blocks,
    )
    assert items == []


def test_attribute_completion_unknown_base_returns_empty() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    blocks = _all_blocks(src)
    [a_block] = blocks
    items = build_completion_items(
        ContextKind.ATTRIBUTE,
        block=a_block,
        attribute_base="completely_unknown",
        sibling_blocks=blocks,
    )
    assert items == []


def test_attribute_completion_without_attribute_base_returns_empty() -> None:
    src = 'class A:\n    equations = "x = 1"\n'
    blocks = _all_blocks(src)
    [a_block] = blocks
    items = build_completion_items(
        ContextKind.ATTRIBUTE,
        block=a_block,
        sibling_blocks=blocks,
    )
    assert items == []


def test_attribute_completion_without_block_returns_empty() -> None:
    items = build_completion_items(
        ContextKind.ATTRIBUTE, attribute_base="b",
    )
    assert items == []
