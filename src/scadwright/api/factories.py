"""User-facing factory functions.

All validation goes through `api._validate`. Strings and ambiguous scalar
broadcasts raise ValidationError at construction time, with a source
location pointing at the user's call.
"""

from __future__ import annotations

from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.csg import Difference, Hull, Intersection, Minkowski, Union
from scadwright.ast.extrude import LinearExtrude, RotateExtrude
from scadwright.ast.primitives import (
    Circle,
    Cube,
    Cylinder,
    Polygon,
    Polyhedron,
    ScadImport,
    Sphere,
    Square,
    Surface,
    Text,
)
from scadwright.api._validate import (
    _require_integer,
    _require_non_empty,
    _require_non_negative,
    _require_number,
    _require_positive,
    _require_resolution,
    _require_size_vec2,
    _require_size_vec3,
    _require_vec2,
    _require_vec3,
)
from scadwright.api._vectors import (
    _as_vec2,
    _as_vec3,
    _normalize_center,
    _normalize_center_2d,
)
from scadwright.api.resolution import resolve as _resolve_res
from scadwright.errors import ValidationError


def cube(size, center=False) -> Cube:
    # Cube sizes allow scalar broadcast (unambiguous) and symbolic values.
    size_vec = _as_vec3(
        size, name="cube size", default_scalar_broadcast=True, allow_symbolic=True,
    )
    from scadwright.animation import SymbolicExpr
    for i, s in enumerate(size_vec):
        if isinstance(s, SymbolicExpr):
            continue
        if s < 0:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"cube size[{i}] must be non-negative, got {s}",
                source_location=loc,
            )
    return Cube(
        size=size_vec,
        center=_normalize_center(center),
        source_location=SourceLocation.from_caller(),
    )


def _pick_radius(
    r_val, d_val, *, r_name: str, d_name: str, default: float | None, require
):
    """Resolve a radius from an r/d pair. Raises if both are given. Either
    side may be a SymbolicExpr (animation), in which case it propagates
    unchanged."""
    from scadwright.animation import SymbolicExpr
    if r_val is not None and d_val is not None:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"pass either {r_name} or {d_name}, not both",
            source_location=loc,
        )
    if r_val is not None:
        v = require(r_val, r_name)
        return v if isinstance(v, SymbolicExpr) else float(v)
    if d_val is not None:
        v = require(d_val, d_name)
        return v / 2 if isinstance(v, SymbolicExpr) else float(v) / 2.0
    return default


def sphere(
    r: float | None = None,
    *,
    d: float | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> Sphere:
    radius = _pick_radius(
        r, d,
        r_name="sphere radius (r)",
        d_name="sphere diameter (d)",
        default=1.0,  # SCAD default
        require=_require_positive,
    )
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="sphere")
    return Sphere(
        r=radius,
        fn=fn,
        fa=fa,
        fs=fs,
        source_location=SourceLocation.from_caller(),
    )


def cylinder(
    h: float = 1.0,
    r: float | None = None,
    *,
    r1: float | None = None,
    r2: float | None = None,
    d: float | None = None,
    d1: float | None = None,
    d2: float | None = None,
    center: bool = False,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> Cylinder:
    from scadwright.animation import SymbolicExpr
    h = _require_non_negative(h, "cylinder height")
    h = h if isinstance(h, SymbolicExpr) else float(h)

    base = _pick_radius(
        r, d,
        r_name="cylinder r", d_name="cylinder d",
        default=1.0, require=_require_non_negative,
    )
    rr1 = _pick_radius(
        r1, d1,
        r_name="cylinder r1", d_name="cylinder d1",
        default=base, require=_require_non_negative,
    )
    rr2 = _pick_radius(
        r2, d2,
        r_name="cylinder r2", d_name="cylinder d2",
        default=base, require=_require_non_negative,
    )
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="cylinder")
    return Cylinder(
        h=h,
        r1=rr1,
        r2=rr2,
        center=bool(center),
        fn=fn,
        fa=fa,
        fs=fs,
        source_location=SourceLocation.from_caller(),
    )


def polyhedron(points, faces, convexity: int | None = None) -> Polyhedron:
    try:
        points_list = list(points)
    except TypeError:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"polyhedron points must be iterable, got {type(points).__name__}",
            source_location=loc,
        ) from None
    _require_non_empty(points_list, "polyhedron points")
    pts = tuple(_require_vec3(p, f"polyhedron points[{i}]") for i, p in enumerate(points_list))

    try:
        faces_list = list(faces)
    except TypeError:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"polyhedron faces must be iterable, got {type(faces).__name__}",
            source_location=loc,
        ) from None
    _require_non_empty(faces_list, "polyhedron faces")
    fcs_list = []
    for fi, face in enumerate(faces_list):
        try:
            face_items = list(face)
        except TypeError:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"polyhedron faces[{fi}] must be iterable of indices",
                source_location=loc,
            ) from None
        if len(face_items) < 3:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"polyhedron faces[{fi}] must have at least 3 indices, got {len(face_items)}",
                source_location=loc,
            )
        indices = []
        for vi, idx in enumerate(face_items):
            ii = _require_integer(idx, f"polyhedron faces[{fi}][{vi}]")
            if ii < 0 or ii >= len(pts):
                loc = SourceLocation.from_caller()
                raise ValidationError(
                    f"polyhedron faces[{fi}][{vi}] index {ii} out of range for {len(pts)} points",
                    source_location=loc,
                )
            indices.append(ii)
        fcs_list.append(tuple(indices))
    if convexity is not None:
        convexity = _require_integer(convexity, "polyhedron convexity")
    return Polyhedron(
        points=pts,
        faces=tuple(fcs_list),
        convexity=convexity,
        source_location=SourceLocation.from_caller(),
    )


# --- 2D primitives ---


def square(size, center=False) -> Square:
    size_vec = _as_vec2(size, name="square size", default_scalar_broadcast=True)
    for i, s in enumerate(size_vec):
        if s < 0:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"square size[{i}] must be non-negative, got {s}",
                source_location=loc,
            )
    return Square(
        size=size_vec,
        center=_normalize_center_2d(center),
        source_location=SourceLocation.from_caller(),
    )


def circle(
    r: float | None = None,
    *,
    d: float | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> Circle:
    radius = _pick_radius(
        r, d,
        r_name="circle radius (r)",
        d_name="circle diameter (d)",
        default=1.0,
        require=_require_positive,
    )
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="circle")
    return Circle(
        r=radius,
        fn=fn,
        fa=fa,
        fs=fs,
        source_location=SourceLocation.from_caller(),
    )


def _normalize_bbox_hint(bbox, *, context: str, loc) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Normalize a user-supplied ((min_x,min_y,min_z),(max_x,max_y,max_z)) hint."""
    try:
        mn, mx = bbox
        mn = tuple(float(x) for x in mn)
        mx = tuple(float(x) for x in mx)
        if len(mn) != 3 or len(mx) != 3:
            raise ValueError("each corner must have 3 elements")
        for i in range(3):
            if mn[i] > mx[i]:
                raise ValueError(f"bbox min[{i}] ({mn[i]}) > max[{i}] ({mx[i]})")
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{context} bbox must be ((min_x, min_y, min_z), (max_x, max_y, max_z)): {exc}",
            source_location=loc,
        ) from None
    return (mn, mx)


_scad_import_hint_warned: set[tuple[str, int]] = set()


def _warn_if_stl_hint_too_small(
    file: str,
    hint_min: tuple[float, float, float],
    hint_max: tuple[float, float, float],
) -> None:
    """If `file` is an STL that auto-parses, warn when the hint excludes
    any of the file's actual extent. Doesn't raise — the user may
    deliberately crop or override.
    """
    if not file.lower().endswith(".stl"):
        return
    from scadwright._stl import stl_bbox

    parsed = stl_bbox(file)
    if parsed is None:
        return  # file missing or unparseable; nothing to compare against
    parsed_min, parsed_max = parsed
    import warnings

    axes = ("x", "y", "z")
    for i, axis in enumerate(axes):
        too_small = hint_min[i] > parsed_min[i] or hint_max[i] < parsed_max[i]
        if not too_small:
            continue
        key = (file, i)
        if key in _scad_import_hint_warned:
            continue
        _scad_import_hint_warned.add(key)
        warnings.warn(
            f"scad_import: bbox hint for {file!r} is smaller than the file's "
            f"actual extent on axis {axis} (hint {hint_min[i]}..{hint_max[i]}, "
            f"file {parsed_min[i]}..{parsed_max[i]}). Assembly checks based on "
            f"this bbox may report incorrect fits.",
            UserWarning,
            stacklevel=3,
        )


def scad_import(
    file: str,
    *,
    bbox: tuple | None = None,
    convexity: int | None = None,
    layer: str | None = None,
    origin: tuple[float, float] | None = None,
    scale: float | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> ScadImport:
    """Import external geometry (STL, SVG, DXF, 3MF, OFF, AMF).

    `bbox` is an optional ((min_x, min_y, min_z), (max_x, max_y, max_z))
    hint. Required for non-STL formats if you want bbox checks to work;
    STL files are auto-parsed. Never emitted to SCAD — it's scadwright
    metadata for assembly introspection.
    """
    loc = SourceLocation.from_caller()
    if not isinstance(file, str) or not file:
        raise ValidationError(
            f"scad_import: file must be a non-empty string, got {type(file).__name__}: {file!r}",
            source_location=loc,
        )
    bbox_hint_normalized = None
    if bbox is not None:
        bbox_hint_normalized = _normalize_bbox_hint(bbox, context="scad_import", loc=loc)
        _warn_if_stl_hint_too_small(file, *bbox_hint_normalized)
    if convexity is not None:
        convexity = _require_integer(convexity, "scad_import convexity")
    if origin is not None:
        origin = _require_vec2(origin, "scad_import origin")
    if scale is not None:
        scale = _require_positive(scale, "scad_import scale")
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="scad_import")
    return ScadImport(
        file=file,
        bbox_hint=bbox_hint_normalized,
        convexity=convexity,
        layer=layer,
        origin=origin,
        scale=scale,
        fn=fn, fa=fa, fs=fs,
        source_location=loc,
    )


def surface(
    file: str,
    *,
    center: bool = False,
    invert: bool = False,
    convexity: int | None = None,
) -> Surface:
    loc = SourceLocation.from_caller()
    if not isinstance(file, str) or not file:
        raise ValidationError(
            f"surface: file must be a non-empty string, got {type(file).__name__}: {file!r}",
            source_location=loc,
        )
    if convexity is not None:
        convexity = _require_integer(convexity, "surface convexity")
    return Surface(
        file=file,
        center=bool(center),
        invert=bool(invert),
        convexity=convexity,
        source_location=loc,
    )


_TEXT_HALIGN = ("left", "center", "right")
_TEXT_VALIGN = ("top", "center", "baseline", "bottom")
_TEXT_DIRECTION = ("ltr", "rtl", "ttb", "btt")


def text(
    text: str,
    *,
    size: float = 10.0,
    font: str | None = None,
    halign: str = "left",
    valign: str = "baseline",
    spacing: float = 1.0,
    direction: str = "ltr",
    language: str = "en",
    script: str = "latin",
    bbox: tuple | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> Text:
    """Create a 2D text shape.

    `bbox=((min_x, min_y, 0), (max_x, max_y, 0))` overrides the built-in
    heuristic (`0.6 * size * spacing` per character) when you need precise
    assembly checks for a specific font. The hint is scadwright-side metadata
    and is never emitted to SCAD.
    """
    loc = SourceLocation.from_caller()
    if not isinstance(text, str):
        raise ValidationError(
            f"text: first argument must be a string, got {type(text).__name__}",
            source_location=loc,
        )
    size = _require_positive(size, "text size")
    spacing = _require_positive(spacing, "text spacing")
    bbox_hint = None
    if bbox is not None:
        bbox_hint = _normalize_bbox_hint(bbox, context="text", loc=loc)
    if halign not in _TEXT_HALIGN:
        raise ValidationError(
            f"text halign must be one of {_TEXT_HALIGN}, got {halign!r}",
            source_location=loc,
        )
    if valign not in _TEXT_VALIGN:
        raise ValidationError(
            f"text valign must be one of {_TEXT_VALIGN}, got {valign!r}",
            source_location=loc,
        )
    if direction not in _TEXT_DIRECTION:
        raise ValidationError(
            f"text direction must be one of {_TEXT_DIRECTION}, got {direction!r}",
            source_location=loc,
        )
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="text")
    return Text(
        text=text,
        size=float(size),
        font=font,
        halign=halign,
        valign=valign,
        spacing=float(spacing),
        direction=direction,
        language=language,
        script=script,
        bbox_hint=bbox_hint,
        fn=fn, fa=fa, fs=fs,
        source_location=loc,
    )


def polygon(points, paths=None, convexity: int | None = None) -> Polygon:
    try:
        points_list = list(points)
    except TypeError:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"polygon points must be iterable, got {type(points).__name__}",
            source_location=loc,
        ) from None
    _require_non_empty(points_list, "polygon points")
    pts = tuple(_require_vec2(p, f"polygon points[{i}]") for i, p in enumerate(points_list))

    pth = None
    if paths is not None:
        try:
            paths_list = list(paths)
        except TypeError:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"polygon paths must be iterable, got {type(paths).__name__}",
                source_location=loc,
            ) from None
        pth_tuples = []
        for pi, path in enumerate(paths_list):
            try:
                path_items = list(path)
            except TypeError:
                loc = SourceLocation.from_caller()
                raise ValidationError(
                    f"polygon paths[{pi}] must be iterable of indices",
                    source_location=loc,
                ) from None
            idxs = []
            for vi, idx in enumerate(path_items):
                ii = _require_integer(idx, f"polygon paths[{pi}][{vi}]")
                if ii < 0 or ii >= len(pts):
                    loc = SourceLocation.from_caller()
                    raise ValidationError(
                        f"polygon paths[{pi}][{vi}] index {ii} out of range for {len(pts)} points",
                        source_location=loc,
                    )
                idxs.append(ii)
            pth_tuples.append(tuple(idxs))
        pth = tuple(pth_tuples)

    if convexity is not None:
        convexity = _require_integer(convexity, "polygon convexity")
    return Polygon(
        points=pts,
        paths=pth,
        convexity=convexity,
        source_location=SourceLocation.from_caller(),
    )


# --- extrudes ---


def linear_extrude(
    child: Node,
    height: float,
    *,
    center: bool = False,
    twist: float = 0.0,
    slices: int | None = None,
    scale=1.0,
    convexity: int | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> LinearExtrude:
    if not isinstance(child, Node):
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"linear_extrude child must be a Node, got {type(child).__name__}",
            source_location=loc,
        )
    height = _require_positive(height, "linear_extrude height")
    twist = _require_number(twist, "linear_extrude twist")
    if slices is not None:
        slices = _require_integer(slices, "linear_extrude slices")
    if convexity is not None:
        convexity = _require_integer(convexity, "linear_extrude convexity")
    from numbers import Real

    if isinstance(scale, Real) and not isinstance(scale, bool):
        scale_val = _require_positive(scale, "linear_extrude scale")
    else:
        scale_val = _require_size_vec2(scale, "linear_extrude scale")
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="linear_extrude")
    return LinearExtrude(
        child=child,
        height=height,
        center=bool(center),
        twist=twist,
        slices=slices,
        scale=scale_val,
        convexity=convexity,
        fn=fn,
        fa=fa,
        fs=fs,
        source_location=SourceLocation.from_caller(),
    )


def rotate_extrude(
    child: Node,
    *,
    angle: float = 360.0,
    convexity: int | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> RotateExtrude:
    if not isinstance(child, Node):
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"rotate_extrude child must be a Node, got {type(child).__name__}",
            source_location=loc,
        )
    angle = _require_number(angle, "rotate_extrude angle")
    if convexity is not None:
        convexity = _require_integer(convexity, "rotate_extrude convexity")
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="rotate_extrude")
    return RotateExtrude(
        child=child,
        angle=angle,
        convexity=convexity,
        fn=fn,
        fa=fa,
        fs=fs,
        source_location=SourceLocation.from_caller(),
    )


# --- CSG ---


def _flatten_csg_args(args, op_name: str) -> tuple[Node, ...]:
    out: list[Node] = []
    for a in args:
        if isinstance(a, Node):
            out.append(a)
        else:
            try:
                items = list(a)
            except TypeError:
                loc = SourceLocation.from_caller()
                raise ValidationError(
                    f"{op_name} argument must be a Node or iterable of Nodes, got {type(a).__name__}",
                    source_location=loc,
                ) from None
            for item in items:
                if not isinstance(item, Node):
                    loc = SourceLocation.from_caller()
                    raise ValidationError(
                        f"{op_name}: iterables are flattened one level only; "
                        f"found nested {type(item).__name__} inside the outer sequence. "
                        f"Pass nodes directly or as a single flat iterable.",
                        source_location=loc,
                    )
                out.append(item)
    if not out:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"{op_name} requires at least one operand",
            source_location=loc,
        )
    return tuple(out)


def union(*args) -> Union:
    return Union(
        children=_flatten_csg_args(args, "union"),
        source_location=SourceLocation.from_caller(),
    )


def difference(*args) -> Difference:
    return Difference(
        children=_flatten_csg_args(args, "difference"),
        source_location=SourceLocation.from_caller(),
    )


def intersection(*args) -> Intersection:
    return Intersection(
        children=_flatten_csg_args(args, "intersection"),
        source_location=SourceLocation.from_caller(),
    )


def mirror_copy(*args, normal=None) -> Union:
    """Keep all children AND a mirrored copy of the group.

    Two equivalent forms:

        mirror_copy([1, 0, 0], a, b, c)        # SCAD-style: normal first, then shapes
        mirror_copy(a, b, c, normal=[1, 0, 0]) # kwargs-style: shapes first, keyword normal

    The second form is recommended for new code — it reads "these shapes,
    mirrored across this plane" and catches typos in the kwarg name.
    """
    from scadwright.ast.transforms import Mirror
    from scadwright.api._vectors import _as_vec3

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
    from scadwright.ast.transforms import Rotate
    from scadwright.api._vectors import _as_vec3

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
    from scadwright.ast.transforms import Translate
    from scadwright.api._vectors import _as_vec3

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


def hull(*args) -> Hull:
    return Hull(
        children=_flatten_csg_args(args, "hull"),
        source_location=SourceLocation.from_caller(),
    )


def minkowski(*args) -> Minkowski:
    return Minkowski(
        children=_flatten_csg_args(args, "minkowski"),
        source_location=SourceLocation.from_caller(),
    )


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


def halve(node: Node, v=None, *, x: float = 0, y: float = 0, z: float = 0, size: float = 1e4) -> Node:
    """Standalone form of `node.halve(v, ...)`. See `Node.halve` for details."""
    return node.halve(v, x=x, y=y, z=z, size=size)
