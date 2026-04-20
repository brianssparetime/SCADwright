"""Matrix.invert and Matrix.is_invertible must agree at matching tolerances.

Before MajorReview2 Group 4, `is_invertible(tol=1e-9)` could say False while
`invert()` still succeeded (the latter used a hardcoded 1e-12 pivot
threshold). That broke the common pattern of gating invert on is_invertible.
Now both honor the same `tol` argument and agree.
"""

import pytest

from scadwright import Matrix


# --- The formerly-broken case from the review ---


def test_default_tol_agreement_on_borderline_matrix():
    m = Matrix.scale(1e-10, 1, 1)
    assert m.is_invertible() is False
    with pytest.raises(ValueError, match="singular"):
        m.invert()


def test_same_explicit_tol_agrees_true():
    m = Matrix.scale(1e-10, 1, 1)
    assert m.is_invertible(tol=1e-12) is True
    # Same tol on invert: succeeds.
    inv = m.invert(tol=1e-12)
    assert isinstance(inv, Matrix)


def test_same_explicit_tol_agrees_false():
    m = Matrix.scale(1e-5, 1, 1)
    assert m.is_invertible(tol=1e-4) is False
    with pytest.raises(ValueError, match="singular"):
        m.invert(tol=1e-4)


# --- Parametrized sweep: agreement across scales ---


@pytest.mark.parametrize("scale", [
    1e-15, 1e-12, 1e-10, 1e-8, 1e-6, 1e-3, 1.0, 1e3, 1e6,
])
def test_is_invertible_agrees_with_invert_at_default_tol(scale):
    m = Matrix.scale(scale, 1, 1)
    expect_invertible = m.is_invertible()
    if expect_invertible:
        inv = m.invert()  # must not raise
        assert isinstance(inv, Matrix)
    else:
        with pytest.raises(ValueError, match="singular"):
            m.invert()


# --- Error message content ---


def test_error_message_includes_det_and_tol():
    m = Matrix.scale(1e-10, 1, 1)
    try:
        m.invert()
    except ValueError as e:
        msg = str(e)
        assert "|det|" in msg
        assert "tol=" in msg


# --- Normal cases still work ---


def test_identity_inverts():
    m = Matrix.identity()
    assert m.invert() == Matrix.identity()


def test_translate_inverts_to_negative():
    m = Matrix.translate(5, 10, 15)
    inv = m.invert()
    assert inv.apply_point((0, 0, 0)) == pytest.approx((-5, -10, -15))


def test_scale_inverts_to_reciprocal():
    m = Matrix.scale(2, 4, 8)
    inv = m.invert()
    assert inv.apply_point((2, 4, 8)) == pytest.approx((1, 1, 1))


def test_custom_tol_accepts_near_singular():
    # A matrix on the edge of default tol: override tol to invert it.
    m = Matrix.scale(1e-11, 1, 1)
    assert not m.is_invertible()
    with pytest.raises(ValueError):
        m.invert()
    # Loosen the tolerance and it works:
    inv = m.invert(tol=1e-20)
    assert isinstance(inv, Matrix)
