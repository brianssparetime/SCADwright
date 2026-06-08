"""Higher-order composition helpers: multi_hull, sequential_hull, linear/rotate/mirror_copy, halve, arrange_on_bed."""

from __future__ import annotations

from typing import NamedTuple

from scadwright.api._vectors import _as_vec3
from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.csg import Hull, Union
from scadwright.ast.transforms import Mirror, Rotate, Translate
from scadwright.boolops import _flatten_csg_args
from scadwright.errors import ValidationError


class _Measured(NamedTuple):
    """A part plus the extents `arrange_on_bed` lays out by: its bbox-min
    corner, the Z lift onto the bed, and its X/Y footprint."""

    part: Node
    min_x: float
    min_y: float
    dz: float
    ext_x: float
    ext_y: float


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
    as a cutter in ``difference()``. Center the parent on the origin to
    match the grid, and call ``.through()`` on the grid so each hole
    breaks cleanly through both faces (``hole_grid`` adds no overlap of
    its own)::

        from scadwright.shapes import clearance_hole
        from scadwright.composition_helpers import hole_grid

        plate = cube([60, 60, 3], center="xy")
        cutter = hole_grid(
            rows=2, cols=2,
            row_spacing=30.5, col_spacing=30.5,
            hole=clearance_hole("M3", depth=3),
        ).through(plate, axis="z")
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


def arrange_on_bed(
    *parts,
    gap: float = 5.0,
    plate: tuple[float, float] = (256.0, 256.0),
    lift_to_bed: bool = True,
    assert_fit: bool = True,
    sort: str | None = None,
) -> Union:
    """Lay parts out on the print bed in rows and return their union.

    Parts go left-to-right from the bed's front-left corner. When the next
    part would run past the plate width, it starts a new row behind the
    parts already placed, so a set that wouldn't fit in a single line still
    fills the bed. Within a row, parts are centered front-to-back, and each
    is dropped so its lowest point sits at z=0 (pass `lift_to_bed=False` to
    keep its own Z). `gap` is the minimum spacing between parts and rows.

        layout = arrange_on_bed(cube(40), cube([60, 30, 20]), cube(50),
                                plate=(256, 256), gap=8)

    By default the parts are checked against `plate` and a too-large set
    raises when you build it, naming the row count and how far it runs
    over, rather than sliding off the bed unnoticed. Pass
    `assert_fit=False` to lay them out anyway.

    Parts are placed in the order given. Pass `sort="depth"` to place the
    deepest first, which lines rows up more evenly and usually frees bed
    space.

    The bed origin is its front-left corner, matching PrusaSlicer and
    Cura; for a center-of-bed coordinate system, translate the result by
    ``[-plate[0]/2, -plate[1]/2, 0]``. Rotate a part before passing it in
    to turn it on the bed.

    Parts are packed as rectangular footprints in rows, not nested, so an
    interlocking or triangular arrangement is out of scope. Lists in the
    arguments flatten one level, so ``arrange_on_bed([a, b], c)`` works.
    """
    loc = SourceLocation.from_caller()
    flat = _flatten_csg_args(parts, "arrange_on_bed")
    if gap < 0:
        raise ValidationError(
            f"arrange_on_bed: gap must be non-negative, got {gap}",
            source_location=loc,
        )
    if plate[0] <= 0 or plate[1] <= 0:
        raise ValidationError(
            f"arrange_on_bed: plate dimensions must be positive, got {plate}",
            source_location=loc,
        )
    if sort not in (None, "depth"):
        raise ValidationError(
            f'arrange_on_bed: sort must be None or "depth", got {sort!r}',
            source_location=loc,
        )

    from scadwright.bbox import tight_bbox as _tight_bbox

    # Resolve each part's extents up front. Use tight_bbox so the layout
    # (and especially the lift to z=0) uses the part's actual extents
    # rather than the conservative bbox. Conservative bbox lies for parts
    # whose top-level operator is Difference: the part would silently
    # float above the bed by the gap between the conservative and tight
    # z-min. Surfacing that as an explicit error here is what the user
    # actually wants.
    measured: list[_Measured] = []
    for part in flat:
        try:
            bb = _tight_bbox(part)
        except NotImplementedError as exc:
            raise ValidationError(
                f"arrange_on_bed: cannot lay out `{type(part).__name__}` "
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
        dz = -bb.min[2] if lift_to_bed else 0.0
        ext_x = bb.max[0] - bb.min[0]
        ext_y = bb.max[1] - bb.min[1]
        if ext_x <= 0 or ext_y <= 0:
            raise ValidationError(
                f"arrange_on_bed: `{type(part).__name__}` has no bed "
                f"footprint (its tight bbox measures {ext_x:g} x {ext_y:g} "
                f"mm), so it can't be placed or fit-checked. A part's extent "
                f"can be unknowable from its tree, most often with "
                f"`surface()`. Declare the real size with `with_bbox_from`, "
                f'e.g. `surface("h.png").with_bbox_from(cube([w, d, h]))`.',
                source_location=loc,
            )
        measured.append(
            _Measured(
                part=part,
                min_x=bb.min[0],
                min_y=bb.min[1],
                dz=dz,
                ext_x=ext_x,
                ext_y=ext_y,
            )
        )

    if sort == "depth":
        # Stable sort by depth descending: parts of equal depth keep
        # argument order so the layout stays predictable.
        measured.sort(key=lambda m: m.ext_y, reverse=True)

    # Pass 1: assign parts to rows, recording each part's X start. A part
    # wraps to a new row when it would cross the plate width, unless its
    # row is empty (an over-wide part stands alone and is caught by the
    # fit-check rather than looping forever).
    rows_of_parts: list[list[tuple[int, float]]] = []
    current_row: list[tuple[int, float]] = []
    x_cursor = 0.0
    for idx, m in enumerate(measured):
        if current_row and x_cursor + m.ext_x > plate[0]:
            rows_of_parts.append(current_row)
            current_row = []
            x_cursor = 0.0
        current_row.append((idx, x_cursor))
        x_cursor += m.ext_x + gap
    if current_row:
        rows_of_parts.append(current_row)

    # Pass 2: place each part. Within a row, center it across the row's
    # depth band (the deepest part sets the band); centering is the free
    # cross-axis choice and keeps shallow parts off the row's front edge.
    placed: list[Node] = []
    y_cursor = 0.0
    max_row_width = 0.0
    for row in rows_of_parts:
        row_depth = max(measured[idx].ext_y for idx, _x in row)
        last_idx, last_x = row[-1]
        row_width = last_x + measured[last_idx].ext_x
        if row_width > max_row_width:
            max_row_width = row_width
        for idx, x_start in row:
            m = measured[idx]
            dx = -m.min_x + x_start
            dy = -m.min_y + y_cursor + (row_depth - m.ext_y) / 2.0
            placed.append(
                Translate(v=(dx, dy, m.dz), child=m.part, source_location=loc)
            )
        y_cursor += row_depth + gap

    rows = len(rows_of_parts)
    total_x = max_row_width
    total_y = y_cursor - gap if rows_of_parts else 0.0  # drop trailing gap
    if assert_fit:
        if total_x > plate[0] or total_y > plate[1]:
            raise ValidationError(
                f"arrange_on_bed: parts laid out across {rows} "
                f"row{'s' if rows != 1 else ''}; layout is "
                f"{total_x:g} x {total_y:g} mm, which exceeds plate "
                f"{plate[0]:g} x {plate[1]:g} mm "
                f"(overflow X={max(0.0, total_x - plate[0]):g}, "
                f"Y={max(0.0, total_y - plate[1]):g}). Reorder or "
                f'pre-rotate parts, pass sort="depth", increase plate=, '
                f"or pass assert_fit=False to lay out anyway. This fills "
                f"the bed in rows, not optimal nesting.",
                source_location=loc,
            )

    return Union(children=tuple(placed), source_location=loc)


# Axis to the (on, using_anchor) face pair that stacks the next part on top
# of the previous one along +axis: the next part's low face mates to the
# previous part's high face.
_STACK_AXIS_FACES = {
    "z": ("top", "bottom"),
    "y": ("back", "front"),
    "x": ("rside", "lside"),
}


def _stack_place(parts, axis, on, using_anchor, name):
    """Place each part on the previous one along the axis (or the explicit
    anchor pair) with exact contact, and return the list of placed parts.
    Placement, and any rejection, is ``attach``'s (``fuse=False``).
    """
    loc = SourceLocation.from_caller()
    flat = _flatten_csg_args(parts, name)
    if not flat:
        raise ValidationError(
            f"{name}: needs at least one part.", source_location=loc,
        )
    if (on is None) != (using_anchor is None):
        raise ValidationError(
            f"{name}: pass both on= and using_anchor=, or neither and let "
            f"axis= pick the mating faces. Got on={on!r}, "
            f"using_anchor={using_anchor!r}.",
            source_location=loc,
        )
    if on is None:
        if axis not in _STACK_AXIS_FACES:
            raise ValidationError(
                f"{name}: axis must be 'x', 'y', or 'z' (got {axis!r}), or "
                f"pass on= and using_anchor= explicitly.",
                source_location=loc,
            )
        on, using_anchor = _STACK_AXIS_FACES[axis]

    placed = [flat[0]]
    prev = flat[0]
    for part in flat[1:]:
        here = part.attach(prev, on=on, using_anchor=using_anchor, fuse=False)
        placed.append(here)
        prev = here
    return placed


def stack(*parts, axis="z", on=None, using_anchor=None, eps=None) -> Node:
    """Stack parts in order along ``axis`` and fuse them into one body.

    Each part is placed so its low face on the axis sits on the previous
    part's high face (placement is ``attach``), then the abutting contacts
    are fused with a small overlap so the union stays manifold-clean for
    CGAL (the fuse is ``fuse``). Returns one solid::

        column = stack(base, spacer, cap)              # along +z
        rail = stack(a, b, c, axis="x")

    ``axis`` selects the mating faces (``"z"`` uses top/bottom, ``"y"`` uses
    back/front, ``"x"`` uses rside/lside). Pass ``on=`` / ``using_anchor=``
    to mate on custom anchors instead. ``eps`` overrides the overlap size.

    Stacking is placement, so it is exactly ``attach`` repeated: a
    consecutive pair that ``attach`` can't place (curved contact face,
    missing anchor) raises through ``attach`` unchanged. Use ``place_stack``
    for the same layout returned as separate parts (assembled view, or
    parts printed individually).
    """
    placed = _stack_place(parts, axis, on, using_anchor, "stack")
    if len(placed) == 1:
        return placed[0]
    from scadwright.boolops import fuse as _fuse
    if eps is None:
        return _fuse(*placed)
    return _fuse(*placed, eps=eps)


def place_stack(*parts, axis="z", on=None, using_anchor=None) -> tuple[Node, ...]:
    """Place parts in a stack along ``axis`` and return them as separate
    parts, with exact contact and no eps overlap.

    The placement is identical to ``stack``; only the result differs. Use
    this for an assembled view, or when the parts are printed individually
    and mated physically, where an added overlap would make the parts
    collide::

        base, spacer, cap = place_stack(base, spacer, cap)

    ``axis`` and ``on=`` / ``using_anchor=`` select the mating faces exactly
    as in ``stack``. A pair that ``attach`` can't place raises through
    ``attach``. To fuse the stack into one body instead, use ``stack``.
    """
    placed = _stack_place(parts, axis, on, using_anchor, "place_stack")
    return tuple(placed)


__all__ = [
    "arrange_on_bed",
    "halve",
    "hole_grid",
    "linear_copy",
    "mirror_copy",
    "multi_hull",
    "place_stack",
    "rotate_copy",
    "sequential_hull",
    "stack",
]
