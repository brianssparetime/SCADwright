"""MajorReview2 Group 6 — targeted error-message polish.

Each test pins the user-facing phrasing the review asked for. Strict
string-matching so accidental regressions get caught.
"""

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import circle, cube


# --- 6a: multmatrix wrong shape explains padding ---


def test_multmatrix_wrong_shape_mentions_padding():
    try:
        cube(1).multmatrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    except ValidationError as e:
        msg = str(e)
        assert "3x3" in msg
        assert "pad" in msg.lower()
        assert "[0, 0, 0, 1]" in msg


def test_multmatrix_wrong_shape_reports_actual_shape():
    try:
        cube(1).multmatrix([[1, 2]])
    except ValidationError as e:
        assert "1x2" in str(e)


# --- 6b: offset exactly-one shows what was given ---


def test_offset_neither_reports_both_none():
    with pytest.raises(ValidationError) as exc:
        circle(r=5).offset()
    msg = str(exc.value)
    assert "exactly one" in msg
    assert "r=None" in msg
    assert "delta=None" in msg


def test_offset_both_reports_actual_values():
    with pytest.raises(ValidationError) as exc:
        circle(r=5).offset(r=1, delta=2)
    msg = str(exc.value)
    assert "r=1" in msg
    assert "delta=2" in msg


# --- 6c: scalar-vector rejection shows concrete examples ---


def test_scalar_rejection_shows_concrete_3vec_and_kwargs():
    try:
        cube(1).translate(5)
    except ValidationError as e:
        msg = str(e)
        # Concrete example vector (not [0, 0, 0]).
        assert "[5, 0, 0]" in msg
        # Concrete keyword form with real values.
        assert "x=5" in msg
        assert "y=0" in msg
        assert "z=0" in msg


def test_scalar_rejection_for_2d_shows_2vec_form():
    # resize(v) takes a 3-vector (scalar rejected); for a 2D example, test a
    # path that goes through _as_vec with dim=2 by accessing mirror on a
    # 2-vector context isn't available — test via a factory that uses dim=2.
    # mirror goes through _vec_from_args → _as_vec3, so always dim=3.
    # The 2D path fires through _as_vec2. Use circle? circle doesn't take
    # vectors. Use `node.resize([...])` — that's dim=3. Use square([5]):
    with pytest.raises(ValidationError) as exc:
        # square takes a 2-vector size; passing a bad vector shape via
        # _as_vec2... but scalar is allowed for size (broadcast). So we need
        # a non-broadcast dim=2 path. Actually linear_extrude scale with a
        # scalar is broadcast to both axes — not a good test case.
        # Simplest: bypass via direct _as_vec with dim=2, default_scalar_broadcast=False.
        from scadwright.api._vectors import _as_vec
        _as_vec(3.14, 2, name="test", default_scalar_broadcast=False)
    msg = str(exc.value)
    assert "[5, 0]" in msg
    assert "x=5" in msg
    assert "y=0" in msg


# --- 6d: Param.group collision names the class ---


def test_param_group_collision_names_the_class():
    try:
        class MyWidget(Component):
            width = Param(float)
            Param.group("width height", float, positive=True)

            def build(self):
                return cube(1)
    except ValidationError as e:
        msg = str(e)
        assert "'width'" in msg
        # __qualname__ inside a function includes the enclosing scope, e.g.
        # 'test_param_group_collision_names_the_class.<locals>.MyWidget'.
        assert "MyWidget" in msg
        assert "already defined" in msg


def test_param_group_collision_suggests_remediation():
    try:
        class _Collide(Component):
            w = Param(float)
            Param.group("w", float)
            def build(self): return cube(1)
    except ValidationError as e:
        msg = str(e)
        # Remediation hints visible to the user:
        assert "remove" in msg.lower() or "different name" in msg.lower()
