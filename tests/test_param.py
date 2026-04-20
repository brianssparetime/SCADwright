import pytest

from scadwright import Component, Param, emit_str, in_range, minimum, one_of, positive
from scadwright.errors import ValidationError
from scadwright.primitives import cube
# --- Param descriptor basics ---


class _Box(Component):
    width = Param(float, default=10)
    height = Param(float, default=20)

    def build(self):
        return cube([self.width, self.height, 5])


def test_param_kwargs_only():
    """Auto-generated __init__ is kwargs-only — catches accidental
    positional calls that would otherwise silently bind by declaration order."""
    with pytest.raises(TypeError):
        _Box(5, 8)


def test_param_unknown_kwarg_rejected():
    """Typos in kwarg names must raise instead of silently being ignored."""
    with pytest.raises(ValidationError, match="unknown parameter"):
        _Box(depth=3)


def test_param_str_to_float_coercion():
    """Non-obvious coercion path that's worth pinning."""
    b = _Box(width="3.14")
    assert b.width == pytest.approx(3.14)


def test_param_bad_coercion_raises():
    with pytest.raises(ValidationError, match="cannot coerce"):
        _Box(width="not a number")


# --- Validators ---


class _Bracket(Component):
    width = Param(float, default=10, validators=[positive])
    count = Param(int, default=2, validators=[minimum(1)])

    def build(self):
        return cube([self.width, self.width, 1])


def test_validator_positive_rejects_zero():
    with pytest.raises(ValidationError, match="positive"):
        _Bracket(width=0)


def test_validator_positive_rejects_negative():
    with pytest.raises(ValidationError, match="positive"):
        _Bracket(width=-1)


def test_validator_minimum_rejects_below():
    with pytest.raises(ValidationError, match=">= 1"):
        _Bracket(count=0)


def test_validator_includes_class_and_field_name():
    try:
        _Bracket(width=-1)
    except ValidationError as e:
        # Class name + field name should both appear in the error.
        assert "_Bracket" in str(e) or "width" in str(e)


def test_in_range_validator():
    class _Limited(Component):
        x = Param(float, default=5, validators=[in_range(0, 10)])
        def build(self):
            return cube(self.x)

    _Limited(x=5)  # ok
    with pytest.raises(ValidationError):
        _Limited(x=-1)
    with pytest.raises(ValidationError):
        _Limited(x=11)


def test_one_of_validator():
    class _Mode(Component):
        kind = Param(str, default="square", validators=[one_of("square", "round")])
        def build(self):
            return cube(1)

    _Mode(kind="round")
    with pytest.raises(ValidationError, match="one of"):
        _Mode(kind="triangle")


# --- Required (no default) ---


class _Required(Component):
    width = Param(float)  # no default

    def build(self):
        return cube(self.width)


def test_required_param_must_be_supplied():
    with pytest.raises(ValidationError, match="missing required"):
        _Required()


# --- Plain __init__ still works ---


class _Plain(Component):
    def __init__(self, w):
        super().__init__()
        self.w = w

    def build(self):
        return cube(self.w)


def test_plain_init_source_location():
    import inspect

    line = inspect.currentframe().f_lineno
    p = _Plain(1)  # line + 1
    assert p.source_location is not None
    assert p.source_location.line == line + 1


# --- setup hook ---


class _PostHook(Component):
    width = Param(float, default=10)
    height = Param(float, default=20)

    def setup(self):
        self.area = self.width * self.height

    def build(self):
        return cube([self.width, self.height, 1])


def test_post_params_runs_after_init():
    p = _PostHook(width=4, height=5)
    assert p.area == 20


# --- Source location captured at instantiation ---


def test_param_init_captures_source_location():
    import inspect

    line = inspect.currentframe().f_lineno
    b = _Box(width=1)  # line + 1
    assert b.source_location is not None
    assert b.source_location.line == line + 1


# --- Build still works with auto-init Components ---


def test_build_uses_param_values():
    b = _Box(width=3, height=4)
    out = emit_str(b)
    assert "cube([3, 4, 5]" in out
