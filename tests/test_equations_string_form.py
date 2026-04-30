from __future__ import annotations

# Multi-line `equations = "..."` form. The triple-quoted string form is
# internally normalized to the same list of logical lines the parser
# already consumes. These tests pin the splitter behavior and the
# equivalence between the two input shapes.

import pytest

from scadwright import Component, Param
from scadwright.component.equations import _split_equations_text
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Splitter unit tests
# =============================================================================


def test_split_basic_lines():
    text = """
        od = id + 2*thk
        h, id, od, thk > 0
    """
    assert _split_equations_text(text) == [
        "od = id + 2*thk",
        "h, id, od, thk > 0",
    ]


def test_split_drops_blank_lines():
    text = """
        od = id + 2*thk

        h, id, od, thk > 0


        id < od
    """
    assert _split_equations_text(text) == [
        "od = id + 2*thk",
        "h, id, od, thk > 0",
        "id < od",
    ]


def test_split_drops_whole_line_comments():
    text = """
        # outer wall
        od = id + 2*thk
        # positivity
        h, id, od, thk > 0
    """
    assert _split_equations_text(text) == [
        "od = id + 2*thk",
        "h, id, od, thk > 0",
    ]


def test_split_keeps_inline_comments():
    text = """
        od = id + 2*thk   # outer = inner + walls
        h > 0
    """
    out = _split_equations_text(text)
    assert out[0] == "od = id + 2*thk   # outer = inner + walls"
    assert out[1] == "h > 0"


def test_split_bracket_continuation():
    text = """
        cradle_positions = tuple(-(count-1)*pitch/2 + i*pitch
                                 for i in range(count))
        count > 0
    """
    out = _split_equations_text(text)
    assert len(out) == 2
    assert "cradle_positions =" in out[0]
    assert "for i in range(count)" in out[0]
    assert out[1] == "count > 0"


def test_split_backslash_continuation():
    text = """
        total = a + b \\
              + c + d
        a, b, c, d > 0
    """
    out = _split_equations_text(text)
    assert len(out) == 2
    # Backslash + newline is swallowed; the continuation is glued in.
    assert "a + b" in out[0] and "+ c + d" in out[0]
    assert "\\" not in out[0]
    assert out[1] == "a, b, c, d > 0"


def test_split_backslash_inside_comment_does_not_continue():
    """A `\\` inside a `#` comment must not glue the next line —
    matches Python's tokenizer."""
    text = """
        a = 1   # trailing slash here \\
        b = 2
    """
    out = _split_equations_text(text)
    assert out == ["a = 1   # trailing slash here \\", "b = 2"]


def test_split_brackets_inside_string_do_not_continue():
    text = """
        label = "(" + "x"
        z = 1
    """
    out = _split_equations_text(text)
    assert out == ['label = "(" + "x"', "z = 1"]


def test_split_hash_inside_string_is_not_a_comment():
    text = """
        tag = "#1"
        z = 1
    """
    out = _split_equations_text(text)
    assert out == ['tag = "#1"', "z = 1"]


def test_split_empty_input():
    assert _split_equations_text("") == []
    assert _split_equations_text("\n\n   \n") == []


# =============================================================================
# End-to-end equivalence with the list form
# =============================================================================


def test_string_form_equivalent_to_list_form():
    class TubeList(Component):
        equations = [
            "od = id + 2*thk",
            "h, id, od, thk > 0",
        ]
        def build(self): return cube([1, 1, 1])

    class TubeStr(Component):
        equations = """
            od = id + 2*thk
            h, id, od, thk > 0
        """
        def build(self): return cube([1, 1, 1])

    list_eq_raws = [e.raw for e in TubeList._unified_equations]
    str_eq_raws = [e.raw for e in TubeStr._unified_equations]
    assert list_eq_raws == str_eq_raws

    list_c_raws = [c.raw for c in TubeList._unified_constraints]
    str_c_raws = [c.raw for c in TubeStr._unified_constraints]
    assert list_c_raws == str_c_raws

    # Source-line indices align.
    list_eq_idx = [e.source_line_index for e in TubeList._unified_equations]
    str_eq_idx = [e.source_line_index for e in TubeStr._unified_equations]
    assert list_eq_idx == str_eq_idx

    # Both forms produce a working Component with the same resolved values.
    a = TubeList(h=10, id=8, thk=1)
    b = TubeStr(h=10, id=8, thk=1)
    assert a.od == b.od == 10.0


def test_string_form_solves_correctly():
    class Tube(Component):
        equations = """
            od = id + 2*thk
            h, id, od, thk > 0
        """
        def build(self): return cube([1, 1, 1])

    t = Tube(h=10, id=8, thk=1)
    assert t.od == 10.0


def test_string_form_constraint_violation():
    class Tube(Component):
        equations = """
            od = id + 2*thk
            h, id, od, thk > 0
        """
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError):
        Tube(h=10, id=8, thk=-1)


# =============================================================================
# Source-line indexing under string form
# =============================================================================


def test_string_form_error_index_matches_logical_line_position():
    """`equations[N]` in error messages is the post-cleanup logical-line
    index — same semantics as the list form. Blank/comment lines do not
    shift the count."""
    class C(Component):
        equations = """

            # leading comment
            x = 5

            y = 3

            x < y
        """
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C()
    msg = str(exc_info.value)
    # Logical lines: x = 5 (0), y = 3 (1), x < y (2).
    assert "C.equations[2]" in msg


def test_string_form_with_continuation_keeps_one_index():
    class C(Component):
        equations = """
            total = (a
                     + b
                     + c)
            a, b, c, total > 0
        """
        def build(self): return cube([1, 1, 1])

    # Two logical lines: equation (index 0), constraint (index 1).
    eqs = C._unified_equations
    cons = C._unified_constraints
    assert len(eqs) == 1
    assert eqs[0].source_line_index == 0
    assert all(c.source_line_index == 1 for c in cons)


def test_string_form_optional_sigil_works():
    class Box(Component):
        size = Param(tuple)
        equations = """
            ?fillet > 0
            ?chamfer > 0
            len(size) = 3
            exactly_one(?fillet, ?chamfer)
            edge = ?fillet if ?fillet else ?chamfer
            all(s > 2 * edge for s in size)
        """
        def build(self): return cube([1, 1, 1])

    b = Box(size=(20, 15, 10), fillet=2)
    assert b.edge == 2.0


def test_string_form_empty_no_breakage():
    class C(Component):
        equations = ""
        def build(self): return cube([1, 1, 1])

    assert C._unified_equations == []
    assert C._unified_constraints == []
    C()  # constructs cleanly


def test_string_form_whitespace_only_no_breakage():
    class C(Component):
        equations = "\n   \n\n"
        def build(self): return cube([1, 1, 1])

    assert C._unified_equations == []
    assert C._unified_constraints == []


# =============================================================================
# Mixed list: single-line entries plus a multi-line string entry
# =============================================================================


def test_mixed_list_with_multiline_string_entry():
    """A list whose entries are a mix of single-line strings and a
    multi-line string expands the multi-line entry into its logical
    lines. Source indices run sequentially across the flattened result."""
    class C(Component):
        equations = [
            "od = id + 2*thk",
            """
                h > 0
                id > 0
                od > 0
            """,
            "thk > 0",
        ]
        def build(self): return cube([1, 1, 1])

    # 1 equation + 4 constraints (3 from the multi-line entry, 1 trailing).
    assert len(C._unified_equations) == 1
    assert len(C._unified_constraints) == 4

    # Source indices are sequential post-expansion: equation at 0, then
    # the three from the multi-line block at 1/2/3, then thk > 0 at 4.
    assert C._unified_equations[0].source_line_index == 0
    cons_idx = sorted(c.source_line_index for c in C._unified_constraints)
    assert cons_idx == [1, 2, 3, 4]

    # The Component still solves correctly.
    c = C(h=10, id=8, thk=1)
    assert c.od == 10.0


def test_mixed_list_error_index_points_at_expanded_line():
    """When a constraint inside a multi-line string entry fails, the
    error message indexes the expanded position — same model as the
    pure list form."""
    class C(Component):
        equations = [
            "x = 5",
            """
                y = 3
                z = 7
            """,
            "x < y",   # index 3 after expansion; fails (5 < 3 false)
        ]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C()
    msg = str(exc_info.value)
    assert "C.equations[3]" in msg


def test_pure_list_form_unchanged_when_no_multiline_entries():
    """A list with no multi-line entries goes through the unchanged
    path — source indices match the list positions."""
    class C(Component):
        equations = [
            "od = id + 2*thk",
            "h, id, od, thk > 0",
            "id < od",
        ]
        def build(self): return cube([1, 1, 1])

    assert C._unified_equations[0].source_line_index == 0
    # The bound rule on line 1 expands across multiple constraints, but
    # all share source_line_index=1.
    bound_idxs = {c.source_line_index for c in C._unified_constraints
                  if "> 0" in c.raw}
    assert bound_idxs == {1}
