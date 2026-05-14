"""Phase 2: morph() factory + Design class-body registration.

No rendering yet — those tests live in test_morph_render.py once the
dispatch is wired up in Phase 5. This module just confirms the
declarative surface works.
"""

from __future__ import annotations

import pytest

from scadwright import morph
from scadwright.api.morph import _MorphSpec
from scadwright.design import (
    Design, _reset_for_testing, registered_designs, resolve_variants, variant,
)
from scadwright.errors import ValidationError, SCADwrightError
from scadwright.primitives import cube


@pytest.fixture(autouse=True)
def reset_registry():
    _reset_for_testing()
    yield
    _reset_for_testing()


# ---------------------------------------------------------------------------
# morph() factory: eager validation
# ---------------------------------------------------------------------------


def test_morph_returns_spec():
    spec = morph(start="a", end="b")
    assert isinstance(spec, _MorphSpec)
    assert spec.start == "a"
    assert spec.end == "b"
    assert spec.order is None
    assert spec.simultaneous is False


def test_morph_marker_attribute():
    spec = morph(start="a", end="b")
    # The marker is what Design.__init_subclass__ keys on (alongside isinstance).
    assert getattr(spec, "_scadwright_morph", False) is True


def test_morph_with_order_and_simultaneous():
    spec = morph(start="a", end="b", order=["base", "lid"], simultaneous=True)
    assert spec.order == ("base", "lid")
    assert spec.simultaneous is True


def test_morph_start_equals_end_raises():
    with pytest.raises(ValidationError, match="must be different"):
        morph(start="x", end="x")


def test_morph_empty_start_raises():
    with pytest.raises(ValidationError, match="non-empty string"):
        morph(start="", end="b")


def test_morph_non_string_end_raises():
    with pytest.raises(ValidationError, match="non-empty string"):
        morph(start="a", end=None)  # type: ignore[arg-type]


def test_morph_order_must_be_list_of_strings():
    with pytest.raises(ValidationError, match="list of variant-part names"):
        morph(start="a", end="b", order=("not", "a", "list"))  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="list of variant-part names"):
        morph(start="a", end="b", order=["ok", 42])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Public export
# ---------------------------------------------------------------------------


def test_morph_is_importable_at_top_level():
    import scadwright
    assert hasattr(scadwright, "morph")
    assert "morph" in scadwright.__all__


# ---------------------------------------------------------------------------
# Design registration: __morphs__ and synthesized __variants__ entry
# ---------------------------------------------------------------------------


def test_class_body_morph_registers_in_morphs():
    class D(Design):
        @variant()
        def print(self):
            return cube(1)

        @variant(default=True)
        def display(self):
            return cube(1)

        assemble = morph(start="print", end="display")

    assert "assemble" in D.__morphs__
    spec = D.__morphs__["assemble"]
    assert spec.start == "print"
    assert spec.end == "display"


def test_morph_also_synthesizes_variant_entry():
    class D(Design):
        @variant()
        def print(self):
            return cube(1)

        @variant(default=True)
        def display(self):
            return cube(1)

        assemble = morph(start="print", end="display")

    # The morph name appears in __variants__ alongside the real variants.
    assert "assemble" in D.__variants__
    # The synthesized meta has all-None fields — render context comes from
    # the start/end variants at dispatch time, not from this placeholder.
    meta = D.__variants__["assemble"]
    assert meta.fn is None
    assert meta.default is False


def test_morph_findable_via_resolve_variants():
    class D(Design):
        @variant()
        def print(self):
            return cube(1)

        @variant(default=True)
        def display(self):
            return cube(1)

        assemble = morph(start="print", end="display")

    selected = resolve_variants("assemble", kind="build")
    assert len(selected) == 1
    assert selected[0][1] == "assemble"


def test_morph_with_missing_start_variant_raises_at_class_definition():
    with pytest.raises(ValidationError, match="does not reference an @variant"):
        class D(Design):  # noqa: F841
            @variant(default=True)
            def display(self):
                return cube(1)

            assemble = morph(start="preint", end="display")


def test_morph_with_missing_end_variant_raises():
    with pytest.raises(ValidationError, match="does not reference an @variant"):
        class D(Design):  # noqa: F841
            @variant(default=True)
            def print(self):
                return cube(1)

            assemble = morph(start="print", end="dispaly")


def test_morph_cannot_reference_another_morph():
    # Morphs can't chain off other morphs in v1.
    with pytest.raises(ValidationError, match="does not reference an @variant"):
        class D(Design):  # noqa: F841
            @variant()
            def a(self):
                return cube(1)

            @variant(default=True)
            def b(self):
                return cube(1)

            first = morph(start="a", end="b")
            second = morph(start="first", end="b")


def test_morph_shadowing_a_variant_method_resolves_to_useful_error():
    # Python class-body reassignment overwrites the @variant method, so by
    # __init_subclass__ time only the morph remains in vars(cls). The morph
    # then can't find its end variant (it would have been the shadowed
    # method) and raises a missing-variant error — which is the right thing
    # to surface to the user.
    with pytest.raises(ValidationError, match="does not reference an @variant"):
        class D(Design):  # noqa: F841
            @variant(default=True)
            def assemble(self):
                return cube(1)

            @variant()
            def other(self):
                return cube(1)

            assemble = morph(start="other", end="assemble")


def test_unknown_morph_name_raises_at_resolve():
    class D(Design):  # noqa: F841
        @variant(default=True)
        def display(self):
            return cube(1)

    with pytest.raises(SCADwrightError, match="no variant named"):
        resolve_variants("not-a-morph", kind="build")


def test_two_morphs_in_same_design():
    class D(Design):
        @variant()
        def a(self):
            return cube(1)

        @variant(default=True)
        def b(self):
            return cube(1)

        @variant()
        def c(self):
            return cube(1)

        ab = morph(start="a", end="b")
        bc = morph(start="b", end="c")

    assert set(D.__morphs__) == {"ab", "bc"}
    assert {"a", "b", "c", "ab", "bc"} == set(D.__variants__)


def test_morph_alongside_multiple_designs():
    class D1(Design):
        @variant(default=True)
        def x(self):
            return cube(1)

        @variant()
        def y(self):
            return cube(1)

        xy = morph(start="x", end="y")

    class D2(Design):
        @variant(default=True)
        def p(self):
            return cube(1)

        @variant()
        def q(self):
            return cube(1)

        pq = morph(start="p", end="q")

    assert len(registered_designs()) == 2
    assert "xy" in D1.__morphs__
    assert "pq" in D2.__morphs__
