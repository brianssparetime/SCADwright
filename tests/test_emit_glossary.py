"""The emit-time equation glossary above each Component subtree.

Locks the format and classification (input/default/derivation), the
opt-out kwarg, and the once-per-Component-instance behavior under
nesting and replication.
"""

from __future__ import annotations

from scadwright import Component
from scadwright.emit import emit_str
from scadwright.primitives import cube


# =============================================================================
# Smoke: a 2-equation Component emits a block under each known name.
# =============================================================================


class _Tube(Component):
    equations = """
        h, id, od, thk > 0
        od = id + 2 * thk
    """

    def build(self):
        return cube([self.id, self.id, self.h])


def test_glossary_emits_for_each_resolved_name():
    out = emit_str(_Tube(h=10, id=8, thk=1))
    assert "// _Tube" in out
    # Three caller-supplied names render as inputs.
    assert "//  h   = 10  (input)" in out
    assert "//  id  = 8  (input)" in out
    assert "//  thk = 1  (input)" in out
    # The fourth resolves via the equation; line shows expr = value.
    assert "//  od  = id + 2 * thk = 10" in out


def test_glossary_omitted_when_flag_off():
    out = emit_str(_Tube(h=10, id=8, thk=1), glossary=False)
    assert "// _Tube" in out
    assert "(input)" not in out
    assert "od = id + 2 * thk" not in out


# =============================================================================
# Classification: caller-supplied vs Param-default vs override-pattern default
# vs equation-derived.
# =============================================================================


class _DefaultedTube(Component):
    """Override-pattern default: `?thk = ?thk or 1.5` resolves `thk` to 1.5
    when the caller doesn't supply it. The glossary should mark that
    `(default)`, identical to an explicit `thk=1.5`."""

    equations = """
        h, id, od > 0
        ?thk = ?thk or 1.5
        od = id + 2 * thk
    """

    def build(self):
        return cube([self.id, self.id, self.h])


def test_override_pattern_default_classified_as_default():
    out = emit_str(_DefaultedTube(h=10, id=8))
    assert "//  thk = 1.5  (default)" in out


def test_explicit_value_overrides_default_to_input():
    out = emit_str(_DefaultedTube(h=10, id=8, thk=1))
    assert "//  thk = 1  (input)" in out


def test_geometry_identical_when_default_matches_explicit():
    a = emit_str(_DefaultedTube(h=10, id=8), glossary=False)
    b = emit_str(_DefaultedTube(h=10, id=8, thk=1.5), glossary=False)
    assert a == b


# =============================================================================
# Skip rules: consistency-check lines (LHS not a bare Name) don't appear.
# =============================================================================


class _ConsistencyOnly(Component):
    spec = "spec"  # placeholder; replaced below via explicit __init__ to skip Param plumbing
    equations = """
        h > 0
        len(size:tuple) = 3
    """

    def build(self):
        return cube([self.size[0], self.size[1], self.h])


def test_consistency_check_not_in_glossary():
    out = emit_str(_ConsistencyOnly(h=10, size=(1, 2, 3)))
    # The `len(size) = 3` line is a consistency check, not a derivation,
    # so it shouldn't appear as a glossary entry.
    assert "len(size)" not in out
    # `size` is a tuple input; should still appear as `(input)`.
    assert "size = [1, 2, 3]  (input)" in out
    assert "h    = 10  (input)" in out


# =============================================================================
# Nesting: parent and child Components each get their own block.
# =============================================================================


class _Inner(Component):
    equations = """
        a > 0
        b = 2 * a
    """

    def build(self):
        return cube([self.a, self.b, 1])


class _Outer(Component):
    equations = """
        x > 0
    """

    def build(self):
        return _Inner(a=self.x).up(2)


def test_nested_components_each_emit_glossary():
    out = emit_str(_Outer(x=5))
    assert "// _Outer" in out
    assert "//  x = 5  (input)" in out
    assert "// _Inner" in out
    assert "//  a = 5  (input)" in out
    assert "//  b = 2 * a = 10" in out


# =============================================================================
# Replication: one block per Component instance, not per visit.
#
# (A `for`-style loop in `build()` builds N nodes, all from one parent
# Component instance — the parent's block fires once. If `build()`
# returns N inner Components, each is its own instance, so each gets
# its own block. The visitor-based design makes this fall out naturally;
# this test locks it.)
# =============================================================================


class _ReplicatedHolder(Component):
    equations = """
        n:int > 0
        pitch > 0
    """

    def build(self):
        from scadwright.boolops import union
        return union(*[
            cube([1, 1, 1]).right(i * self.pitch) for i in range(self.n)
        ])


def test_replication_inside_build_emits_one_block():
    out = emit_str(_ReplicatedHolder(n=4, pitch=2))
    # Exactly one `// _ReplicatedHolder` header for the outer Component.
    assert out.count("// _ReplicatedHolder") == 1
    assert "//  n     = 4  (input)" in out
    assert "//  pitch = 2  (input)" in out
