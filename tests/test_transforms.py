"""Transform chained-method semantics that aren't trivial Param roundtrips.

Attribute-roundtrip tests (`.translate([1,2,3]).v == (1,2,3)`) are
tautological — they fail only if Param or the dataclass itself is
broken, which every other test would catch. They're not here.
"""

from scadwright.colors import SVG_COLORS
from scadwright.primitives import cube


def test_translate_partial_kwargs_fills_zeros():
    """Only x/y/z you pass are set; the rest default to 0."""
    t = cube(1).translate(z=5)
    assert t.v == (0.0, 0.0, 5.0)


def test_scale_scalar_broadcasts_to_all_axes():
    s = cube(1).scale(2)
    assert s.factor == (2.0, 2.0, 2.0)


def test_rotate_disambiguates_axis_angle_from_euler():
    """Positional-vector vs a=/v= must produce Euler-form vs axis-angle-form."""
    euler = cube(1).rotate([0, 45, 0])
    axis_angle = cube(1).rotate(a=30, v=[0, 0, 1])
    assert euler.angles is not None and euler.a is None
    assert axis_angle.a is not None and axis_angle.angles is None


def test_shorthand_up_down_set_z_axis_correctly():
    assert cube(1).up(5).v == (0.0, 0.0, 5.0)
    assert cube(1).down(5).v == (0.0, 0.0, -5.0)


def test_shorthand_source_location_points_at_call_site():
    """Shorthand methods must capture the user's call site, not their own body."""
    import inspect

    this_line = inspect.currentframe().f_lineno
    node = cube(1).up(5)
    assert node.source_location.file.endswith("test_transforms.py")
    assert node.source_location.line == this_line + 1


def test_svg_color_shorthands_all_attached():
    """Every SVG color name must be a method on Node — if a rename breaks
    a large block, the colors list will have gaps."""
    n = cube(1)
    missing = [name for name in SVG_COLORS if not hasattr(n, name)]
    assert not missing, f"missing color methods: {missing[:5]}..."


def test_color_method_applies_alpha():
    c = cube(1).slategray(alpha=0.25)
    assert c.c == "slategray"
    assert c.alpha == 0.25


def test_flip_is_mirror_across_axis():
    m = cube(1).flip("x")
    assert m.normal == (1.0, 0.0, 0.0)
