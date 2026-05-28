"""morph() factory + Design class-body registration."""

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
    spec = morph(stages=["a", "b"])
    assert isinstance(spec, _MorphSpec)
    assert spec.stages == ("a", "b")
    assert spec.order is None
    assert spec.simultaneous is False


def test_morph_marker_attribute():
    spec = morph(stages=["a", "b"])
    # The marker is what Design.__init_subclass__ keys on (alongside isinstance).
    assert getattr(spec, "_scadwright_morph", False) is True


def test_morph_three_stage_chain():
    spec = morph(stages=["a", "b", "c"])
    assert spec.stages == ("a", "b", "c")


def test_morph_with_order_and_simultaneous():
    spec = morph(stages=["a", "b"], order=["base", "lid"], simultaneous=True)
    assert spec.order == ("base", "lid")
    assert spec.simultaneous is True


def test_morph_stages_must_be_list():
    with pytest.raises(ValidationError, match="must be a list"):
        morph(stages=("a", "b"))  # type: ignore[arg-type]


def test_morph_stages_too_short_raises():
    with pytest.raises(ValidationError, match="at least 2 entries"):
        morph(stages=["only_one"])


def test_morph_empty_stage_raises():
    with pytest.raises(ValidationError, match="non-empty string"):
        morph(stages=["", "b"])


def test_morph_non_string_stage_raises():
    with pytest.raises(ValidationError, match="non-empty string"):
        morph(stages=["a", None])  # type: ignore[list-item]


def test_morph_consecutive_duplicate_stages_raises():
    with pytest.raises(ValidationError, match="consecutive duplicates"):
        morph(stages=["a", "a"])


def test_morph_consecutive_duplicate_in_chain_raises():
    with pytest.raises(ValidationError, match=r"stages\[1\] and stages\[2\]"):
        morph(stages=["a", "b", "b", "c"])


def test_morph_non_consecutive_repeat_allowed():
    """A→B→A is a deliberate go-and-return sequence; legal."""
    spec = morph(stages=["a", "b", "a"])
    assert spec.stages == ("a", "b", "a")


def test_morph_order_must_be_list_of_strings():
    with pytest.raises(ValidationError, match="list of variant-part names"):
        morph(stages=["a", "b"], order=("not", "a", "list"))  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="list of variant-part names"):
        morph(stages=["a", "b"], order=["ok", 42])  # type: ignore[list-item]


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

        assemble = morph(stages=["print", "display"])

    assert "assemble" in D.__morphs__
    spec = D.__morphs__["assemble"]
    assert spec.stages == ("print", "display")


def test_three_stage_morph_registers():
    class D(Design):
        @variant()
        def print(self):
            return cube(1)

        @variant()
        def closing(self):
            return cube(1)

        @variant(default=True)
        def display(self):
            return cube(1)

        assemble = morph(stages=["print", "closing", "display"])

    assert "assemble" in D.__morphs__
    assert D.__morphs__["assemble"].stages == ("print", "closing", "display")


def test_morph_also_synthesizes_variant_entry():
    class D(Design):
        @variant()
        def print(self):
            return cube(1)

        @variant(default=True)
        def display(self):
            return cube(1)

        assemble = morph(stages=["print", "display"])

    # The morph name appears in __variants__ alongside the real variants.
    assert "assemble" in D.__variants__
    # The synthesized meta has all-None fields — render context comes from
    # the stage variants at dispatch time, not from this placeholder.
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

        assemble = morph(stages=["print", "display"])

    selected = resolve_variants("assemble", kind="build")
    assert len(selected) == 1
    assert selected[0][1] == "assemble"


def test_morph_with_missing_first_stage_raises_at_class_definition():
    with pytest.raises(
        ValidationError,
        match=r"stages\[0\]='preint' does not reference an @variant",
    ):
        class D(Design):  # noqa: F841
            @variant(default=True)
            def display(self):
                return cube(1)

            assemble = morph(stages=["preint", "display"])


def test_morph_with_missing_last_stage_raises():
    with pytest.raises(
        ValidationError,
        match=r"stages\[1\]='dispaly' does not reference an @variant",
    ):
        class D(Design):  # noqa: F841
            @variant(default=True)
            def print(self):
                return cube(1)

            assemble = morph(stages=["print", "dispaly"])


def test_morph_with_missing_middle_stage_raises():
    """In a three-stage chain, the bad index is named in the error."""
    with pytest.raises(
        ValidationError,
        match=r"stages\[1\]='middl' does not reference an @variant",
    ):
        class D(Design):  # noqa: F841
            @variant()
            def print(self):
                return cube(1)

            @variant(default=True)
            def display(self):
                return cube(1)

            assemble = morph(stages=["print", "middl", "display"])


def test_morph_cannot_reference_another_morph():
    # Stages may not reference morphs — only @variant methods.
    with pytest.raises(ValidationError, match="does not reference an @variant"):
        class D(Design):  # noqa: F841
            @variant()
            def a(self):
                return cube(1)

            @variant(default=True)
            def b(self):
                return cube(1)

            first = morph(stages=["a", "b"])
            second = morph(stages=["first", "b"])


def test_morph_shadowing_a_variant_method_resolves_to_useful_error():
    # Python class-body reassignment overwrites the @variant method, so by
    # __init_subclass__ time only the morph remains in vars(cls). The morph
    # then can't find the shadowed variant and raises a missing-variant
    # error — which is the right thing to surface to the user.
    with pytest.raises(ValidationError, match="does not reference an @variant"):
        class D(Design):  # noqa: F841
            @variant(default=True)
            def assemble(self):
                return cube(1)

            @variant()
            def other(self):
                return cube(1)

            assemble = morph(stages=["other", "assemble"])


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

        ab = morph(stages=["a", "b"])
        abc = morph(stages=["a", "b", "c"])

    assert set(D.__morphs__) == {"ab", "abc"}
    assert {"a", "b", "c", "ab", "abc"} == set(D.__variants__)


def test_morph_alongside_multiple_designs():
    class D1(Design):
        @variant(default=True)
        def x(self):
            return cube(1)

        @variant()
        def y(self):
            return cube(1)

        xy = morph(stages=["x", "y"])

    class D2(Design):
        @variant(default=True)
        def p(self):
            return cube(1)

        @variant()
        def q(self):
            return cube(1)

        pq = morph(stages=["p", "q"])

    assert len(registered_designs()) == 2
    assert "xy" in D1.__morphs__
    assert "pq" in D2.__morphs__
