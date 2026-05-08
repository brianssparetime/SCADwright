"""Tests for the LSP static AST analyzer.

The analyzer must locate every ``equations = ...`` block in a
Python source file without importing it, and record enough
position info that the position helpers can map AST node
positions back to file ``(line, col)``. Tests cover the supported
RHS shapes (single string, list of strings), nesting variants
(top-level class, class inside class, class inside function),
prefix and quote variants, AnnAssign vs Assign, Param-name
discovery, and several edge / failure cases (syntax error,
non-class equations, unsupported RHS shapes).
"""

from __future__ import annotations

from scadwright.lsp.analyze import (
    EquationsBlock,
    EquationsHostString,
    ParamInfo,
    auto_declared_targets_before,
    find_equations_blocks,
)


# =============================================================================
# Single-string equations forms
# =============================================================================


def test_single_triple_quoted_equations_one_block_one_host() -> None:
    src = (
        "class A:\n"
        "    equations = \"\"\"\n"
        "    x = 1\n"
        "    \"\"\"\n"
    )
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].class_name == "A"
    assert len(blocks[0].hosts) == 1
    host = blocks[0].hosts[0]
    # Content begins immediately after the opening triple-quote.
    assert host.raw_text.startswith("\n    x = 1\n")
    # ``equations = """`` — the """ opens at col 16; content at col 19.
    assert host.content_start_col == 19
    # Same line as the """ token: line 1 (0-based).
    assert host.content_start_line == 1


def test_single_double_quoted_one_line_equations() -> None:
    src = 'class A:\n    equations = "x = 1"\n'
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    host = blocks[0].hosts[0]
    assert host.raw_text == "x = 1"
    # ``    equations = "`` — the " opens at col 16, content at col 17.
    assert host.content_start_col == 17
    assert host.content_start_line == 1


def test_single_quoted_with_apostrophe_outer() -> None:
    src = "class A:\n    equations = 'x = 1'\n"
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].hosts[0].raw_text == "x = 1"


def test_raw_string_prefix_offsets_skip_prefix() -> None:
    src = 'class A:\n    equations = r"x = 1"\n'
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    host = blocks[0].hosts[0]
    assert host.raw_text == "x = 1"
    # ``    equations = r"`` — r at col 16, " at 17, content at col 18.
    assert host.content_start_col == 18


def test_uppercase_raw_prefix_recognized() -> None:
    src = 'class A:\n    equations = R"x = 1"\n'
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].hosts[0].content_start_col == 18


def test_raw_triple_quoted_recognized() -> None:
    # ``r"""..."""`` is a common idiom — strips the ``r`` prefix and
    # the opening triple-quote.
    src = (
        'class A:\n'
        '    equations = r"""\n'
        '    x = 1\n'
        '    """\n'
    )
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    host = blocks[0].hosts[0]
    assert "x = 1" in host.raw_text
    # ``    equations = r"""`` — r at col 16, """ at 17-19, content at 20.
    assert host.content_start_col == 20
    assert host.content_start_line == 1


def test_empty_equations_string_emits_host_with_empty_raw_text() -> None:
    src = 'class A:\n    equations = ""\n'
    blocks = find_equations_blocks(src)
    # An empty string is degenerate but still a valid str literal; the
    # analyzer surfaces it. Downstream ``_split_logical_lines`` returns
    # an empty list of logical lines for empty input, so step 4 will
    # produce no diagnostics — correct behavior.
    assert len(blocks) == 1
    assert blocks[0].hosts[0].raw_text == ""


def test_bytes_literal_skipped() -> None:
    # ``rb"..."`` is a bytes literal — its Constant.value is bytes, not
    # str, so it isn't a valid equations host. The analyzer skips it
    # rather than misinterpret it as an equations string.
    src = 'class A:\n    equations = rb"x = 1"\n'
    assert find_equations_blocks(src) == []


# =============================================================================
# List-of-strings equations forms
# =============================================================================


def test_list_of_strings_emits_one_host_per_element() -> None:
    src = (
        'class A:\n'
        '    equations = ["x = 1", "y = 2"]\n'
    )
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    hosts = blocks[0].hosts
    assert len(hosts) == 2
    assert hosts[0].raw_text == "x = 1"
    assert hosts[1].raw_text == "y = 2"


def test_list_of_strings_position_info_per_element() -> None:
    src = 'class A:\n    equations = ["x = 1", "y = 2"]\n'
    blocks = find_equations_blocks(src)
    h0, h1 = blocks[0].hosts
    # ``    equations = ["`` — first " at col 17, content at 18.
    assert h0.content_start_col == 18
    # h1's `"` opens after `, ` — the literal "y = 2" starts at col 27;
    # content at 28. (Easier to verify by reading the source slice.)
    assert src.splitlines()[1][h1.content_start_col] == "y"


def test_tuple_of_strings_also_supported() -> None:
    # The runtime accepts list; tuple is a forgiving extension. Not
    # strictly required by the runtime, but harmless to recognize.
    src = 'class A:\n    equations = ("x = 1", "y = 2")\n'
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    assert len(blocks[0].hosts) == 2


def test_list_with_non_string_elements_skips_those() -> None:
    src = 'class A:\n    equations = ["x = 1", some_var, "y = 2"]\n'
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    assert len(blocks[0].hosts) == 2
    assert [h.raw_text for h in blocks[0].hosts] == ["x = 1", "y = 2"]


def test_multiline_list_element() -> None:
    src = (
        'class A:\n'
        '    equations = [\n'
        '        """\n'
        '        x = 1\n'
        '        """,\n'
        '        "y = 2",\n'
        '    ]\n'
    )
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    h0, h1 = blocks[0].hosts
    assert "x = 1" in h0.raw_text
    assert h1.raw_text == "y = 2"


# =============================================================================
# AnnAssign form
# =============================================================================


def test_ann_assign_equations_recognized() -> None:
    src = (
        'class A:\n'
        '    equations: str = """\n'
        '    x = 1\n'
        '    """\n'
    )
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].class_name == "A"


def test_ann_assign_no_value_skipped() -> None:
    src = "class A:\n    equations: str\n    x = 1\n"
    assert find_equations_blocks(src) == []


# =============================================================================
# Param-name discovery
# =============================================================================


def test_param_name_discovery_bare_name() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    height = Param(float)\n'
        '    equations = "x = width + 1"\n'
    )
    blocks = find_equations_blocks(src)
    assert blocks[0].param_names == frozenset({"width", "height"})


def test_param_name_discovery_attribute_call() -> None:
    src = (
        'class A:\n'
        '    width = sc.Param(float)\n'
        '    equations = "x = width + 1"\n'
    )
    blocks = find_equations_blocks(src)
    assert blocks[0].param_names == frozenset({"width"})


def test_param_name_discovery_ann_assign() -> None:
    src = (
        'class A:\n'
        '    width: float = Param(float)\n'
        '    equations = "x = width + 1"\n'
    )
    blocks = find_equations_blocks(src)
    assert blocks[0].param_names == frozenset({"width"})


def test_non_param_assignments_not_collected() -> None:
    src = (
        'class A:\n'
        '    width = 5\n'
        '    name = "thing"\n'
        '    equations = "x = 1"\n'
    )
    blocks = find_equations_blocks(src)
    assert blocks[0].param_names == frozenset()


# =============================================================================
# Multi-class and nesting
# =============================================================================


def test_multiple_classes_emit_multiple_blocks_in_source_order() -> None:
    src = (
        'class A:\n'
        '    equations = "a = 1"\n'
        '\n'
        'class B:\n'
        '    equations = "b = 2"\n'
    )
    blocks = find_equations_blocks(src)
    assert [b.class_name for b in blocks] == ["A", "B"]


def test_nested_class_inside_class_recognized() -> None:
    src = (
        'class Outer:\n'
        '    class Inner:\n'
        '        equations = "x = 1"\n'
        '    equations = "y = 2"\n'
    )
    blocks = find_equations_blocks(src)
    names = [b.class_name for b in blocks]
    assert "Outer" in names
    assert "Inner" in names


def test_class_inside_function_recognized() -> None:
    src = (
        'def factory():\n'
        '    class A:\n'
        '        equations = "x = 1"\n'
        '    return A\n'
    )
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].class_name == "A"


# =============================================================================
# Edge / failure cases
# =============================================================================


def test_syntax_error_returns_empty() -> None:
    src = "class A:\n    equations = \n"  # unterminated rhs
    assert find_equations_blocks(src) == []


def test_no_classes_returns_empty() -> None:
    src = 'x = 1\nprint("hi")\n'
    assert find_equations_blocks(src) == []


def test_class_without_equations_returns_empty() -> None:
    src = "class A:\n    x = 1\n    y = 2\n"
    assert find_equations_blocks(src) == []


def test_equations_assigned_from_function_call_skipped() -> None:
    # The runtime would raise; the analyzer skips and returns nothing.
    src = "class A:\n    equations = make_equations()\n"
    assert find_equations_blocks(src) == []


def test_equations_assigned_from_variable_skipped() -> None:
    src = "class A:\n    equations = SHARED\n"
    assert find_equations_blocks(src) == []


def test_module_level_equations_not_collected() -> None:
    # The runtime only consumes class-level ``equations``. The analyzer
    # mirrors: a module-level assignment isn't surfaced as a block.
    src = 'equations = "x = 1"\n'
    assert find_equations_blocks(src) == []


def test_implicit_string_concatenation_skipped_as_unsafe() -> None:
    # ``"a" "b"`` folds into one Constant whose source segment has an
    # inner quote — no clean way to map per-char offsets. Skip rather
    # than risk wrong column ranges.
    src = 'class A:\n    equations = "x = 1" "y = 2"\n'
    blocks = find_equations_blocks(src)
    # Either zero blocks (if the analyzer skipped the host entirely)
    # or zero hosts on the block. Both are acceptable; assert no
    # equations are surfaced for analysis.
    assert all(len(b.hosts) == 0 for b in blocks)


# =============================================================================
# Composition with the position helpers (sanity check)
# =============================================================================


def test_full_pipeline_through_block_to_file_position() -> None:
    # Build a fixture that exercises: class detection + content-start
    # arithmetic + the splitter on the discovered raw_text. The "x" on
    # the first equation line should map back to a file (line, col)
    # that matches what we manually compute.
    src = (
        'class Bracket:\n'
        '    equations = """\n'
        '    width > 0\n'
        '    h = width + 2\n'
        '    """\n'
    )
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    host = blocks[0].hosts[0]
    # Sanity-check: the first non-whitespace char of raw_text is 'w'.
    first_w_offset = host.raw_text.index("w")
    # That offset, mapped through offset_to_line_col + content_start,
    # should land at file line 2 col 4 (the 'w' in "    width > 0").
    from scadwright.lsp.positions import map_raw_offset_to_file
    file_line, file_col = map_raw_offset_to_file(
        first_w_offset,
        host_text=host.raw_text,
        host_start_line=host.content_start_line,
        host_start_col=host.content_start_col,
    )
    assert (file_line, file_col) == (2, 4)


# =============================================================================
# Type-shape sanity
# =============================================================================


def test_returned_objects_are_immutable_dataclasses() -> None:
    src = 'class A:\n    equations = "x = 1"\n'
    blocks = find_equations_blocks(src)
    block = blocks[0]
    assert isinstance(block, EquationsBlock)
    assert isinstance(block.hosts[0], EquationsHostString)
    assert isinstance(block.hosts, tuple)
    assert isinstance(block.param_names, frozenset)
    assert isinstance(block.params, tuple)


# =============================================================================
# Per-Param info extraction
# =============================================================================


def _params_by_name(src: str) -> dict[str, ParamInfo]:
    blocks = find_equations_blocks(src)
    assert len(blocks) == 1
    return {p.name: p for p in blocks[0].params}


def test_param_info_records_type_text() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.type_text == "float"
    assert p.default_text is None
    assert p.doc_text is None
    assert p.extras == ()


def test_param_info_records_default() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, default=5)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.type_text == "float"
    assert p.default_text == "5"


def test_param_info_default_none() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, default=None)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.default_text == "None"


def test_param_info_no_positional_no_type() -> None:
    src = (
        'class A:\n'
        '    width = Param(default=5)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.type_text is None
    assert p.default_text == "5"


def test_param_info_doc_string_literal_unquoted() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, doc="The widget width")\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.doc_text == "The widget width"


def test_param_info_doc_non_literal_dropped() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, doc=DOC)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.doc_text is None


def test_param_info_extras_record_other_kwargs() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, positive=True, range=(0, 10))\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    extras = dict(p.extras)
    assert extras == {"positive": "True", "range": "(0, 10)"}


def test_param_info_attribute_call_form() -> None:
    src = (
        'class A:\n'
        '    width = sc.Param(float, default=5)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.type_text == "float"
    assert p.default_text == "5"


def test_params_preserve_source_order() -> None:
    src = (
        'class A:\n'
        '    height = Param(float)\n'
        '    width = Param(float)\n'
        '    depth = Param(float)\n'
        '    equations = "x = width"\n'
    )
    [block] = find_equations_blocks(src)
    assert [p.name for p in block.params] == ["height", "width", "depth"]


def test_param_names_matches_params_view() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    height = Param(float)\n'
        '    equations = "x = width"\n'
    )
    [block] = find_equations_blocks(src)
    assert block.param_names == frozenset(p.name for p in block.params)


def test_param_info_ann_assign_form() -> None:
    src = (
        'class A:\n'
        '    width: float = Param(float, default=5)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.type_text == "float"
    assert p.default_text == "5"


def test_param_info_kwarg_unpacking_skipped() -> None:
    # ``Param(float, **kwargs)`` — the splat has no static name to
    # record. Other kwargs (none here) still surface normally.
    src = (
        'class A:\n'
        '    width = Param(float, **OPTIONS)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.type_text == "float"
    assert p.extras == ()


# =============================================================================
# Param assignment position info (used by goto-definition)
# =============================================================================


def test_param_assignment_position_recorded() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    # Source line 1 (0-based), col 4 (after the indent).
    assert p.assign_start_line == 1
    assert p.assign_start_col == 4
    assert p.assign_end_line == 1
    # End col covers through the closing ')' of Param(float).
    src_line = src.splitlines()[1]
    assert src_line[p.assign_start_col:p.assign_end_col] == "width = Param(float)"


def test_param_assignment_position_for_ann_assign() -> None:
    src = (
        'class A:\n'
        '    width: float = Param(float, default=5)\n'
        '    equations = "x = width"\n'
    )
    p = _params_by_name(src)["width"]
    assert p.assign_start_line == 1
    src_line = src.splitlines()[1]
    span = src_line[p.assign_start_col:p.assign_end_col]
    assert span == "width: float = Param(float, default=5)"


def test_param_assignment_position_multiple_params() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    height = Param(float)\n'
        '    equations = "x = width + height"\n'
    )
    by_name = _params_by_name(src)
    assert by_name["width"].assign_start_line == 1
    assert by_name["height"].assign_start_line == 2
    # Both start at the same indent column.
    assert by_name["width"].assign_start_col == 4
    assert by_name["height"].assign_start_col == 4


def test_param_info_constructed_directly_has_none_position() -> None:
    # Direct construction (e.g., in tests) — position fields default
    # to None.
    p = ParamInfo(
        name="x",
        type_text="float",
        default_text=None,
        doc_text=None,
        extras=(),
    )
    assert p.assign_start_line is None
    assert p.assign_start_col is None


# =============================================================================
# auto_declared_targets_before
# =============================================================================


def _block_with(*lines: str) -> EquationsBlock:
    """Build a block from a list of equation lines (single host, one
    triple-quoted string).
    """
    body = "\n".join(f"    {line}" for line in lines)
    src = (
        f'class A:\n    equations = """\n{body}\n    """\n'
    )
    [block] = find_equations_blocks(src)
    return block


def test_auto_declared_no_earlier_lines_returns_empty() -> None:
    block = _block_with("x = 5", "y = x + 1")
    assert auto_declared_targets_before(block, 0, 0) == frozenset()


def test_auto_declared_single_line_target_lhs() -> None:
    block = _block_with("x = 5", "y = x + 1")
    # Targets declared before line 1: just from line 0 (x = 5).
    assert auto_declared_targets_before(block, 0, 1) == frozenset({"x"})


def test_auto_declared_two_lines_accumulates() -> None:
    block = _block_with("a = 1", "b = 2", "c = a + b")
    # Before line 2: a and b.
    assert auto_declared_targets_before(block, 0, 2) == frozenset({"a", "b"})


def test_auto_declared_comma_broadcast_expands() -> None:
    block = _block_with("x, y = 5", "z = x + y")
    assert auto_declared_targets_before(block, 0, 1) == frozenset({"x", "y"})


def test_auto_declared_both_sides_bare() -> None:
    # ``a = b`` — both sides are bare Names; both qualify.
    block = _block_with("a = b", "c = a")
    assert auto_declared_targets_before(block, 0, 1) == frozenset({"a", "b"})


def test_auto_declared_constraint_line_skipped() -> None:
    block = _block_with("x > 0", "y = 5")
    # Line 0 has no `=`; not an equation; contributes nothing.
    assert auto_declared_targets_before(block, 0, 1) == frozenset()


def test_auto_declared_adjustment_line_skipped() -> None:
    block = _block_with("x = 5", "x += 1", "y = x")
    # Line 0 contributes "x"; line 1 is an adjustment, skipped.
    assert auto_declared_targets_before(block, 0, 2) == frozenset({"x"})


def test_auto_declared_subscript_lhs_not_bare() -> None:
    block = _block_with("arr[0] = 5", "y = 1")
    assert auto_declared_targets_before(block, 0, 1) == frozenset()


def test_auto_declared_attribute_lhs_not_bare() -> None:
    block = _block_with("obj.field = 5", "y = 1")
    assert auto_declared_targets_before(block, 0, 1) == frozenset()


def test_auto_declared_strips_question_sigil() -> None:
    block = _block_with("?x = 5", "y = x")
    # ``?x`` strips to ``x``; the bare-Name target is "x".
    assert auto_declared_targets_before(block, 0, 1) == frozenset({"x"})


def test_auto_declared_strips_type_tag() -> None:
    block = _block_with("?x:int = 5", "y = x")
    assert auto_declared_targets_before(block, 0, 1) == frozenset({"x"})


def test_auto_declared_across_hosts() -> None:
    # List form with two host strings; cursor in second host has
    # access to all targets from the first host plus earlier lines
    # in the second.
    src = (
        'class A:\n'
        '    equations = [\n'
        '        "a = 1",\n'
        '        "b = 2",\n'
        '        "c = 3",\n'
        '    ]\n'
    )
    [block] = find_equations_blocks(src)
    # Cursor on host 1's first line (line 0 of that host): "a", "b" from host 0.
    assert auto_declared_targets_before(block, 1, 0) == frozenset({"a"})
    # Cursor on host 2's first line: "a", "b" from hosts 0 and 1.
    assert auto_declared_targets_before(block, 2, 0) == frozenset({"a", "b"})
