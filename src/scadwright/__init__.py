"""scadwright — Python-first OpenSCAD authoring.

The public API is organized into submodules. Import what you need from each:

    from scadwright.primitives import cube, cylinder, sphere
    from scadwright.boolops import union, difference, intersection
    from scadwright.transforms import translate, rotate
    from scadwright.extrusions import linear_extrude, rotate_extrude
    from scadwright.composition_helpers import linear_copy, rotate_copy
    from scadwright.shapes import Tube, Funnel, RoundedBox
    from scadwright.errors import ValidationError, BuildError
    from scadwright.asserts import assert_fits_in

The root namespace keeps a small set of top-level tools and the Component
authoring surface (Component, Param, validators), plus entry points like
emit/render and global config (resolution, variant).
"""

from scadwright._logging import get_logger, set_verbose
from scadwright.anchor import Anchor
from scadwright.ast.base import SourceLocation
from scadwright.bbox import BBox, bbox, resolved_transform, tight_bbox
from scadwright.hashing import tree_hash
from scadwright.matrix import Matrix
from scadwright.component import (
    Component,
    Param,
    anchor,
    in_range,
    materialize,
    maximum,
    minimum,
    non_negative,
    one_of,
    positive,
)
from scadwright.api.args import arg, parse_args
from scadwright.api.resolution import resolution
from scadwright.api.variant import Variant, current_variant, register_variants, variant
from scadwright.emit import emit, emit_str
from scadwright.render import render

__version__ = "0.0.1"

__all__ = [
    # Version
    "__version__",
    # Anchors
    "Anchor",
    # Component authoring
    "Component",
    "Param",
    "anchor",
    "materialize",
    # Validators
    "positive",
    "non_negative",
    "minimum",
    "maximum",
    "in_range",
    "one_of",
    # Bounding boxes / geometry tools
    "BBox",
    "bbox",
    "tight_bbox",
    "resolved_transform",
    "tree_hash",
    "Matrix",
    "SourceLocation",
    # Emit / render
    "emit",
    "emit_str",
    "render",
    # Config
    "resolution",
    "variant",
    "current_variant",
    "register_variants",
    "Variant",
    # CLI
    "arg",
    "parse_args",
    # Logging
    "get_logger",
    "set_verbose",
]
