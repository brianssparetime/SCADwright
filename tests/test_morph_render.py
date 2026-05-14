"""End-to-end render: a Design with a morph, exercising the dispatch in
_render_one. Confirms the animated SCAD lands and is well-formed.

The OpenSCAD parse-check (mcp__openscad__validate_scad equivalent) lives
in the integration suite gated on SCADWRIGHT_TEST_OPENSCAD. The tests
here verify the SCAD text contains the expected animation tokens.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scadwright import Component, Param, positive, morph
from scadwright.boolops import union, difference
from scadwright.design import (
    Design, _render_one, _reset_for_testing, variant,
)
from scadwright.primitives import cube


class _Box(Component):
    size: float = Param(default=10.0, validators=(positive,))

    def build(self):
        return cube(self.size)


class _Lid(Component):
    size: float = Param(default=12.0, validators=(positive,))

    def build(self):
        return cube([self.size, self.size, 2.0])


@pytest.fixture(autouse=True)
def reset_registry():
    _reset_for_testing()
    yield
    _reset_for_testing()


def test_morph_render_writes_scad_file():
    """End-to-end: register a morph, call _render_one for the morph name,
    confirm a SCAD file lands at the expected path."""
    class BoxAndLid(Design):
        box = _Box()
        lid = _Lid()

        @variant()
        def print(self):
            return union(self.box, self.lid.up(20).right(40))

        @variant(default=True)
        def display(self):
            return union(self.box, self.lid.up(15))

        assemble = morph(start="print", end="display")

    with tempfile.TemporaryDirectory() as tmp:
        base_dir = Path(tmp)
        out_path = _render_one(
            BoxAndLid, "assemble", BoxAndLid.__variants__["assemble"],
            base_dir=base_dir,
        )
        assert out_path.exists()
        text = out_path.read_text()
        # The animated chain emits $t expressions in transform args.
        assert "$t" in text


def test_morph_render_with_rotation_emits_axis_angle_rotate():
    """A morph with a rotation difference should emit `rotate(a=..., v=...)`
    in the SCAD — that's the screw motion's α·θ rotation."""
    class D(Design):
        lid = _Lid()

        @variant()
        def upright(self):
            return self.lid

        @variant(default=True)
        def flipped(self):
            return self.lid.rotate([180, 0, 0]).up(30)

        swing = morph(start="upright", end="flipped")

    with tempfile.TemporaryDirectory() as tmp:
        out_path = _render_one(
            D, "swing", D.__variants__["swing"],
            base_dir=Path(tmp),
        )
        text = out_path.read_text()
        # The screw rotation emits as rotate(a=..., v=[...]) form.
        assert "rotate(a=" in text or "rotate(a =" in text


def test_morph_render_preserves_difference_structure():
    """`difference(self.body, self.hole.up(5))` morphed against `.up(10)`
    should emit a top-level difference, not a flat union."""
    class D(Design):
        body = _Box()
        hole = _Box()

        @variant()
        def hole_low(self):
            return difference(self.body, self.hole.up(5))

        @variant(default=True)
        def hole_high(self):
            return difference(self.body, self.hole.up(15))

        slide = morph(start="hole_low", end="hole_high")

    with tempfile.TemporaryDirectory() as tmp:
        out_path = _render_one(
            D, "slide", D.__variants__["slide"],
            base_dir=Path(tmp),
        )
        text = out_path.read_text()
        # The first thing in the SCAD geometry should be `difference()`.
        # Strip comments and find the first non-comment statement.
        lines = [
            line for line in text.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        body_text = "\n".join(lines)
        assert "difference()" in body_text
        # And $t-driven transforms should appear on the cutter.
        assert "$t" in body_text


def test_morph_render_output_path_defaults_to_classname_dash_morphname():
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(10)

        animate_it = morph(start="a", end="b")

    with tempfile.TemporaryDirectory() as tmp:
        out_path = _render_one(
            D, "animate_it", D.__variants__["animate_it"],
            base_dir=Path(tmp),
        )
        assert out_path.name == "D-animate_it.scad"


def test_morph_render_with_out_override():
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(10)

        anim = morph(start="a", end="b")

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "custom-name.scad"
        out_path = _render_one(
            D, "anim", D.__variants__["anim"],
            base_dir=Path(tmp), out_override=target,
        )
        assert out_path == target
        assert out_path.exists()


def test_morph_render_then_regular_variant_works():
    """Regression test: rendering a morph shouldn't corrupt the design
    registry or component caches such that a subsequent regular-variant
    render fails."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(10)

        anim = morph(start="a", end="b")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _render_one(D, "anim", D.__variants__["anim"], base_dir=base)
        # Now render the 'a' variant normally.
        out_a = _render_one(D, "a", D.__variants__["a"], base_dir=base)
        assert out_a.exists()
        # And 'b'.
        out_b = _render_one(D, "b", D.__variants__["b"], base_dir=base)
        assert out_b.exists()


def test_morph_render_via_cli_resolve_variants():
    """The morph should be resolvable through resolve_variants — the same
    code path that the CLI uses for `scadwright build --variant=...`."""
    from scadwright.design import resolve_variants

    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(10)

        anim = morph(start="a", end="b")

    selected = resolve_variants("anim", kind="build")
    assert len(selected) == 1
    design_cls, vname, meta = selected[0]
    assert design_cls is D
    assert vname == "anim"
    with tempfile.TemporaryDirectory() as tmp:
        out_path = _render_one(design_cls, vname, meta, base_dir=Path(tmp))
        assert out_path.exists()
