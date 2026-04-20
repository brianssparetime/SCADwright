"""Verify each submodule exposes its promised surface and nothing leaks
from root that was supposed to move.
"""

import pytest

import scadwright


# (submodule_name, expected_names_set, all_attr_present)
# `all_attr_present=True` means the submodule declares `__all__` and we
# compare against it exactly; `False` means we only check that each name
# is reachable (looser — used when the surface is a curated subset that
# doesn't own `__all__`).
_SUBMODULE_CASES = [
    ("primitives",
     {"cube", "sphere", "cylinder", "polyhedron",
      "square", "circle", "polygon", "text", "surface", "scad_import"},
     True),
    ("boolops",
     {"union", "difference", "intersection", "hull", "minkowski"},
     True),
    ("extrusions",
     {"linear_extrude", "rotate_extrude"},
     True),
    ("composition_helpers",
     {"multi_hull", "sequential_hull",
      "linear_copy", "rotate_copy", "mirror_copy", "halve"},
     True),
    ("transforms",
     {"translate", "rotate", "scale", "mirror", "color", "resize",
      "offset", "multmatrix", "projection",
      "highlight", "background", "disable", "only",
      "Transform", "transform", "get_transform", "list_transforms"},
     True),
    ("debug",
     {"force_render", "echo"},
     True),
    ("shapes",
     {"Tube", "Funnel", "RoundedBox", "UShapeChannel", "FilletRing",
      "Arc", "Sector", "RoundedSlot", "RoundedEndsArc",
      "regular_polygon", "rounded_rect", "rounded_square"},
     False),
    ("errors",
     {"ValidationError", "BuildError", "EmitError", "SCADwrightError"},
     False),
    ("asserts",
     {"assert_bbox_equal", "assert_contains",
      "assert_fits_in", "assert_no_collision"},
     False),
]


@pytest.mark.parametrize("name, expected, check_all", _SUBMODULE_CASES, ids=[c[0] for c in _SUBMODULE_CASES])
def test_submodule_exposes_expected_surface(name, expected, check_all):
    mod = getattr(scadwright, name)
    if check_all:
        assert set(mod.__all__) == expected
    for n in expected:
        assert hasattr(mod, n), f"{name}.{n} missing"


def test_root_no_longer_exposes_submodule_names():
    """Names that moved to submodules must not leak back onto the root
    namespace — otherwise refactors that change their location silently
    keep working at root."""
    for name in ("cube", "sphere", "cylinder", "square", "circle", "polygon",
                 "polyhedron",
                 "union", "difference", "intersection", "hull", "minkowski",
                 "linear_extrude", "rotate_extrude",
                 "multi_hull", "sequential_hull",
                 "linear_copy", "rotate_copy", "mirror_copy",
                 "Tube", "Funnel", "RoundedBox",
                 "transform", "Transform", "get_transform"):
        assert not hasattr(scadwright, name), f"scadwright.{name} should have moved"


def test_root_keeps_component_authoring_and_top_level_tools():
    for name in ("Component", "Param", "materialize",
                 "positive", "non_negative", "minimum", "maximum", "in_range", "one_of",
                 "BBox", "bbox", "tight_bbox", "resolved_transform",
                 "tree_hash", "Matrix", "SourceLocation",
                 "emit", "emit_str", "render",
                 "resolution", "variant", "current_variant",
                 "arg", "parse_args"):
        assert hasattr(scadwright, name), f"scadwright.{name} should stay at root"
