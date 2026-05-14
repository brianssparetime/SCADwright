"""Higher-order composition helpers: multi_hull, sequential_hull, linear/rotate/mirror_copy, halve, pack_on_bed."""

from __future__ import annotations

from scadwright.api._vectors import _as_vec3
from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.csg import Hull, Union
from scadwright.ast.transforms import Mirror, Rotate, Translate
from scadwright.boolops import _flatten_csg_args
from scadwright.errors import ValidationError


def mirror_copy(*args, normal=None) -> Union:
    """Keep all children AND a mirrored copy of the group.

    Two equivalent forms:

        mirror_copy([1, 0, 0], a, b, c)        # SCAD-style: normal first, then shapes
        mirror_copy(a, b, c, normal=[1, 0, 0]) # kwargs-style: shapes first, keyword normal

    The second form is recommended for new code — it reads "these shapes,
    mirrored across this plane" and catches typos in the kwarg name.
    """
    loc = SourceLocation.from_caller()

    # Disambiguate positional vs kwarg form:
    # - If `normal=` kwarg is given: all positional args are children.
    # - Otherwise: first positional arg is the normal vector, rest are children.
    if normal is not None:
        if not args:
            raise ValidationError(
                "mirror_copy: pass at least one shape",
                source_location=loc,
            )
        children = args
        normal_val = normal
    else:
        if len(args) < 2:
            raise ValidationError(
                "mirror_copy: expected (normal, *shapes) or (*shapes, normal=...)",
                source_location=loc,
            )
        normal_val, *children = args

    normal_vec = _as_vec3(normal_val, name="mirror_copy normal", default_scalar_broadcast=False)
    flat = _flatten_csg_args(children, "mirror_copy")
    mirrored = tuple(
        Mirror(normal=normal_vec, child=c, source_location=loc) for c in flat
    )
    return Union(children=flat + mirrored, source_location=loc)


def rotate_copy(angle: float, *children, n: int = 4, axis=(0.0, 0.0, 1.0)) -> Union:
    """Rotate the group `n` total times around `axis` by `angle` degrees per step."""
    loc = SourceLocation.from_caller()
    axis_vec = _as_vec3(axis, name="rotate_copy axis", default_scalar_broadcast=False)
    flat = _flatten_csg_args(children, "rotate_copy")
    out: list[Node] = list(flat)
    for i in range(1, int(n)):
        for c in flat:
            out.append(
                Rotate(child=c, a=float(angle) * i, v=axis_vec, source_location=loc)
            )
    return Union(children=tuple(out), source_location=loc)


def linear_copy(offset, n: int, *children) -> Union:
    """Translate the group `n` total times by `offset` per step."""
    loc = SourceLocation.from_caller()
    off = _as_vec3(offset, name="linear_copy offset", default_scalar_broadcast=False)
    flat = _flatten_csg_args(children, "linear_copy")
    out: list[Node] = list(flat)
    for i in range(1, int(n)):
        for c in flat:
            out.append(
                Translate(
                    v=(off[0] * i, off[1] * i, off[2] * i),
                    child=c,
                    source_location=loc,
                )
            )
    return Union(children=tuple(out), source_location=loc)


def hole_grid(
    *,
    rows: int,
    cols: int,
    row_spacing: float,
    col_spacing: float,
    hole: Node,
    center: bool = True,
) -> Node:
    """Replicate a hole cutter in a rows × cols rectangular grid.

    The grid spans ``(rows - 1) * row_spacing`` along the row direction
    (Y) and ``(cols - 1) * col_spacing`` along the column direction (X).
    By default the grid centers on the origin; pass ``center=False`` to
    place the bottom-left hole at the origin.

    Pass any cutter shape as ``hole`` — a clearance hole, counterbore,
    countersink, or any custom cutter. The result is intended for use
    as a cutter in ``difference()``::

        from scadwright.shapes import clearance_hole
        from scadwright.composition_helpers import hole_grid

        plate = cube([60, 60, 3])
        cutter = hole_grid(
            rows=2, cols=2,
            row_spacing=30.5, col_spacing=30.5,
            hole=clearance_hole("M3", depth=5),
        )
        result = difference(plate, cutter)

    Common patterns: flight-controller stack holes (16×16, 20×20,
    25.5×25.5, 30.5×30.5 mm), VESA monitor-mount patterns, vent
    arrays, and rectangular bolt grids.
    """
    loc = SourceLocation.from_caller()
    if not isinstance(rows, int) or rows < 1:
        raise ValidationError(
            f"hole_grid: rows must be a positive int, got {rows!r}",
            source_location=loc,
        )
    if not isinstance(cols, int) or cols < 1:
        raise ValidationError(
            f"hole_grid: cols must be a positive int, got {cols!r}",
            source_location=loc,
        )
    if row_spacing <= 0:
        raise ValidationError(
            f"hole_grid: row_spacing must be > 0, got {row_spacing!r}",
            source_location=loc,
        )
    if col_spacing <= 0:
        raise ValidationError(
            f"hole_grid: col_spacing must be > 0, got {col_spacing!r}",
            source_location=loc,
        )

    grid = linear_copy([col_spacing, 0, 0], cols, hole)
    grid = linear_copy([0, row_spacing, 0], rows, grid)
    if center:
        grid = Translate(
            v=(
                -(cols - 1) * col_spacing / 2.0,
                -(rows - 1) * row_spacing / 2.0,
                0.0,
            ),
            child=grid,
            source_location=loc,
        )
    return grid


def multi_hull(first: Node, *others) -> Union:
    """Hull connecting `first` to each of `others`. Then unioned.

    Each `hull(first, other_i)` produces a swept volume between two shapes.
    Useful for fan-shaped bridges from a hub to many endpoints.
    """
    loc = SourceLocation.from_caller()
    flat_others = _flatten_csg_args(others, "multi_hull")
    if not isinstance(first, Node):
        raise ValidationError(
            f"multi_hull first arg must be a Node, got {type(first).__name__}",
            source_location=loc,
        )
    pieces = tuple(
        Hull(children=(first, other), source_location=loc) for other in flat_others
    )
    return Union(children=pieces, source_location=loc)


def sequential_hull(*children) -> Union:
    """Chain of hulls between consecutive children: hull(c0, c1), hull(c1, c2), ..."""
    loc = SourceLocation.from_caller()
    flat = _flatten_csg_args(children, "sequential_hull")
    if len(flat) < 2:
        raise ValidationError(
            "sequential_hull requires at least 2 operands",
            source_location=loc,
        )
    pieces = tuple(
        Hull(children=(a, b), source_location=loc)
        for a, b in zip(flat, flat[1:])
    )
    return Union(children=pieces, source_location=loc)


def halve(node: Node, v=None, *, x: float = 0, y: float = 0, z: float = 0, size: float | None = None) -> Node:
    """Standalone form of `node.halve(v, ...)`. See `Node.halve` for details."""
    return node.halve(v, x=x, y=y, z=z, size=size)


def pack_on_bed(
    *parts,
    gap: float = 5.0,
    plate: tuple[float, float] = (256.0, 256.0),
    lift_to_bed: bool = True,
    assert_fit: bool = True,
) -> Union:
    """Lay parts out left-to-right on the print bed and return their union.

    Each part is translated so its bbox starts at the current X cursor on
    the bed front-left corner (origin = (0, 0)), with `lift_to_bed=True`
    additionally pulling each part down so its bbox.min[2] == 0 — printing
    requires non-negative Z. The X cursor advances by the part's X extent
    plus `gap`. Layout is along +X; total Y extent is the max bbox depth
    among all parts.

        # Replaces the usual ~15 lines of bbox→translate boilerplate
        # in print variants:
        return pack_on_bed(housing_left, housing_right, mating_disc,
                           plate=(256, 256), gap=8)

    With `assert_fit=True` (the default), raises `ValidationError` at
    construction time when the laid-out footprint would exceed `plate`,
    so a too-large variant fails during build instead of silently
    producing geometry off the bed. Pass `assert_fit=False` to lay parts
    out anyway (useful when you know it overflows and want to inspect).

    Conventions:
      - Origin at bed front-left corner (0, 0); matches typical slicer
        defaults (PrusaSlicer, Cura). For center-of-bed layouts, translate
        the result by ``[-plate[0]/2, -plate[1]/2, 0]``.
      - Layout along +X in argument order; pre-rotate parts to control
        orientation before passing them in.
      - Single row only; multi-row packing is out of scope.

    Iterables in the args flatten one level, matching the CSG-arg
    convention: ``pack_on_bed([a, b], c)`` works.
    """
    loc = SourceLocation.from_caller()
    flat = _flatten_csg_args(parts, "pack_on_bed")
    if gap < 0:
        raise ValidationError(
            f"pack_on_bed: gap must be non-negative, got {gap}",
            source_location=loc,
        )
    if plate[0] <= 0 or plate[1] <= 0:
        raise ValidationError(
            f"pack_on_bed: plate dimensions must be positive, got {plate}",
            source_location=loc,
        )

    from scadwright.bbox import tight_bbox as _tight_bbox

    placed: list[Node] = []
    x_cursor = 0.0
    max_y_extent = 0.0
    for part in flat:
        # Use tight_bbox so the layout (and especially the lift to z=0)
        # uses the part's actual extents rather than the conservative
        # bbox. Conservative bbox lies for parts whose top-level
        # operator is Difference: pack_on_bed would silently float the
        # part above the bed by the difference between the conservative
        # and tight z-min. Surfacing that as an explicit error here is
        # what the user actually wants.
        try:
            bb = _tight_bbox(part)
        except NotImplementedError as exc:
            raise ValidationError(
                f"pack_on_bed: cannot lay out `{type(part).__name__}` "
                f"because its tight bbox can't be computed. "
                f"Adjustments: (1) override `Component.tight_bbox` on "
                f"the offending Component to declare its true extents "
                f"(the equations block usually has them); "
                f"(2) refactor the build to use `halve()` instead of "
                f"`difference()` for chopping; "
                f"(3) pass `lift_to_bed=False` if the part is already "
                f"correctly placed and you only want the X/Y layout. "
                f"Underlying: {exc}",
                source_location=loc,
            ) from exc
        ext_x = bb.max[0] - bb.min[0]
        ext_y = bb.max[1] - bb.min[1]
        dx = -bb.min[0] + x_cursor
        dy = -bb.min[1]
        dz = -bb.min[2] if lift_to_bed else 0.0
        placed.append(
            Translate(v=(dx, dy, dz), child=part, source_location=loc)
        )
        x_cursor += ext_x + gap
        if ext_y > max_y_extent:
            max_y_extent = ext_y

    total_x = x_cursor - gap  # drop the trailing gap
    if assert_fit:
        if total_x > plate[0] or max_y_extent > plate[1]:
            raise ValidationError(
                f"pack_on_bed: footprint {total_x:g} x {max_y_extent:g} mm "
                f"exceeds plate {plate[0]:g} x {plate[1]:g} mm "
                f"(overflow X={max(0, total_x - plate[0]):g}, "
                f"Y={max(0, max_y_extent - plate[1]):g})",
                source_location=loc,
            )

    return Union(children=tuple(placed), source_location=loc)


__all__ = [
    "halve",
    "hole_grid",
    "linear_copy",
    "mirror_copy",
    "multi_hull",
    "pack_on_bed",
    "rotate_copy",
    "sequential_hull",
]
