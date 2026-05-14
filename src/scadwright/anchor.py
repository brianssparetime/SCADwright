"""Anchor dataclass and face-name utilities for the attach system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from scadwright.errors import ValidationError

if TYPE_CHECKING:
    from scadwright.bbox import BBox


# Closed set of anchor surface kinds. Adding a new kind requires updating
# this tuple, ``_REQUIRED_FIELDS_BY_KIND``, and any consumer that branches
# on kind.
ANCHOR_KINDS = ("planar", "cylindrical", "conical", "spherical", "meridional")

# Per-kind required fields. Validated in ``Anchor.__post_init__`` — an
# anchor declared with a curved kind must carry the geometry its consumers
# (``add_text``, fuse bridge, attach angle/at_z/polar) rely on.
#
# Planar anchors don't have required fields by default. Cap anchors
# (cylinder/cone/barrel top/bottom) are kind="planar" with rim_radius +
# axis + meridian_zero, but those are only required for ``add_text`` and
# ``attach(angle=, radius=)`` on the cap; bare planar faces (cube top
# etc.) don't carry them.
_REQUIRED_FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "planar": (),
    "cylindrical": ("axis", "radius", "length"),
    "conical": ("axis", "r1", "r2", "length"),
    "spherical": ("axis", "axis_origin", "meridian_zero", "radius"),
    "meridional": (
        "axis", "axis_origin", "meridian_zero",
        "meridian_r", "mid_r", "meridian_s", "length",
    ),
}


@dataclass(frozen=True, slots=True)
class Anchor:
    """A named attachment point: position in local space plus outward normal.

    ``kind`` describes the surface geometry the anchor lives on (one of
    ``ANCHOR_KINDS``). Curved kinds carry their geometric parameters as
    first-class fields (``axis``, ``radius``, etc.); ``__post_init__``
    validates that the required fields for a given kind are present.

    Planar bbox-face anchors (cube top, etc.) only need ``position`` and
    ``normal``. Planar cap anchors of cylinders / cones / barrels also
    carry ``axis`` + ``meridian_zero`` + ``rim_radius`` so ``add_text``
    can wrap arc text on them and ``attach(angle=, radius=)`` can place
    on the cap.
    """

    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    kind: str = "planar"

    # Curved-surface metadata. Populated per-kind; defaults are None /
    # False so planar anchors don't have to specify any of them.
    axis: tuple[float, float, float] | None = None
    axis_origin: tuple[float, float, float] | None = None
    meridian_zero: tuple[float, float, float] | None = None
    radius: float | None = None
    r1: float | None = None
    r2: float | None = None
    length: float | None = None
    rim_radius: float | None = None
    inner: bool = False

    # Meridional (curved-meridian wall, e.g. Barrel) specifics.
    meridian_r: float | None = None
    mid_r: float | None = None
    meridian_s: int | None = None     # +1 convex / -1 concave
    end_r: float | None = None

    def __post_init__(self):
        if self.kind not in ANCHOR_KINDS:
            from scadwright.errors import ValidationError
            raise ValidationError(
                f"Anchor: kind={self.kind!r} is not one of {list(ANCHOR_KINDS)}."
            )
        required = _REQUIRED_FIELDS_BY_KIND.get(self.kind, ())
        missing = [name for name in required if getattr(self, name) is None]
        if missing:
            from scadwright.errors import ValidationError
            raise ValidationError(
                f"Anchor(kind={self.kind!r}): missing required field(s) "
                f"{missing}. Curved-kind anchors must carry these for "
                f"add_text / attach(angle=, at_z=, polar=) / fuse bridge "
                f"to work."
            )

    def _validate_geometry(self) -> None:
        """Per-kind geometric self-consistency check.

        Catches obvious declaration errors at user-input boundaries —
        Component class-scope ``anchor()`` declarations, runtime
        ``Component.anchor(...)``, and ``Node.with_anchor(...)``.
        Specifically:

        - **Cylindrical / conical**: normal must be a unit vector
          perpendicular to ``axis`` (radial direction); ``radius`` /
          ``r1`` / ``r2`` / ``length`` must be positive (with
          ``r1 == r2 == 0`` rejected on cones).
        - **Spherical**: ``position`` must lie at distance ``radius``
          from ``axis_origin``; ``normal`` must be the radial direction
          (or its negation for ``inner=True``); ``radius`` positive.

        **Not** called from internal Anchor constructors that may
        intentionally produce inconsistent values — most importantly,
        ``transform_anchors`` after a non-uniform scale on a sphere
        produces "radius" that doesn't match the position-to-axis_origin
        distance (we don't model the resulting ellipsoid; the radial
        scale is approximated). The check is for *author* errors at
        declaration time, not for runtime transform artifacts.

        **Not** validated:

        - **Meridional**: arc-evaluation math is more complex and
          rarely declared by hand. Only the required-fields presence
          check (in ``__post_init__``) applies.
        - **Whether the declared anchor lies on the actual rendered
          geometry of a Component's ``build()`` output**. That's part
          of the trust contract; see ``docs/anchors.md``.

        Raises ``ValidationError`` on failure.
        """
        import math as _math
        from scadwright.api.tolerances import ANCHOR_GEOMETRY_TOL
        from scadwright.errors import ValidationError

        def _len(v):
            return _math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

        def _dot(a, b):
            return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

        if self.kind == "planar":
            return  # bare planar faces have nothing curved to verify

        # Normal must be a unit vector for any non-planar kind.
        if abs(_len(self.normal) - 1.0) > ANCHOR_GEOMETRY_TOL:
            raise ValidationError(
                f"Anchor(kind={self.kind!r}): normal {self.normal} is not a "
                f"unit vector (length={_len(self.normal):.4f})."
            )

        if self.kind in ("cylindrical", "conical"):
            if abs(_len(self.axis) - 1.0) > ANCHOR_GEOMETRY_TOL:
                raise ValidationError(
                    f"Anchor(kind={self.kind!r}): axis {self.axis} is not a "
                    f"unit vector (length={_len(self.axis):.4f})."
                )
            if abs(_dot(self.normal, self.axis)) > ANCHOR_GEOMETRY_TOL:
                raise ValidationError(
                    f"Anchor(kind={self.kind!r}): normal {self.normal} is "
                    f"not perpendicular to axis {self.axis} (dot product = "
                    f"{_dot(self.normal, self.axis):.4f}). The wall normal "
                    f"is the radial direction — perpendicular to the "
                    f"central axis."
                )
            if self.length <= 0:
                raise ValidationError(
                    f"Anchor(kind={self.kind!r}): length must be positive, "
                    f"got {self.length}."
                )
            if self.kind == "cylindrical":
                if self.radius <= 0:
                    raise ValidationError(
                        f"Anchor(kind='cylindrical'): radius must be "
                        f"positive, got {self.radius}."
                    )
            else:
                if self.r1 < 0 or self.r2 < 0:
                    raise ValidationError(
                        f"Anchor(kind='conical'): r1={self.r1}, r2="
                        f"{self.r2} — both must be non-negative."
                    )
                if self.r1 == 0 and self.r2 == 0:
                    raise ValidationError(
                        "Anchor(kind='conical'): r1 and r2 are both zero "
                        "(degenerate point cone)."
                    )

        elif self.kind == "spherical":
            if self.radius <= 0:
                raise ValidationError(
                    f"Anchor(kind='spherical'): radius must be positive, "
                    f"got {self.radius}."
                )
            if abs(_len(self.axis) - 1.0) > ANCHOR_GEOMETRY_TOL:
                raise ValidationError(
                    f"Anchor(kind='spherical'): axis {self.axis} is not a "
                    f"unit vector (length={_len(self.axis):.4f})."
                )
            offset = (
                self.position[0] - self.axis_origin[0],
                self.position[1] - self.axis_origin[1],
                self.position[2] - self.axis_origin[2],
            )
            offset_len = _len(offset)
            if abs(offset_len - self.radius) > ANCHOR_GEOMETRY_TOL:
                raise ValidationError(
                    f"Anchor(kind='spherical'): distance from axis_origin "
                    f"{self.axis_origin} to position {self.position} is "
                    f"{offset_len:.4f}, doesn't match declared radius="
                    f"{self.radius}. The position must lie on the sphere's "
                    f"surface."
                )
            expected = (
                offset[0] / offset_len,
                offset[1] / offset_len,
                offset[2] / offset_len,
            )
            if self.inner:
                expected = (-expected[0], -expected[1], -expected[2])
            d = _dot(self.normal, expected)
            if d < 1.0 - ANCHOR_GEOMETRY_TOL:
                raise ValidationError(
                    f"Anchor(kind='spherical', inner={self.inner}): normal "
                    f"{self.normal} doesn't match the expected "
                    f"{'inward' if self.inner else 'outward'} radial "
                    f"direction {expected} from axis_origin to position. "
                    f"The normal at a point on a sphere is the radial "
                    f"direction (or its negation for inner walls)."
                )

        # meridional: only required-fields check applies (in __post_init__);
        # arc-evaluation math is deferred.


def _point_in_bbox(p, bb, tol: float | None = None) -> bool:
    """Whether ``p`` lies inside (or on, within ``tol``) the bbox ``bb``.

    Used by ``visit_Difference`` to decide whether a propagated
    custom anchor might have been invalidated by a cutter — a cutter
    whose bbox covers the anchor's position may have removed material
    at the anchor's face. ``tol`` defaults to ``POINT_IN_BBOX_TOL``
    from ``scadwright.api.tolerances``.
    """
    if tol is None:
        from scadwright.api.tolerances import POINT_IN_BBOX_TOL
        tol = POINT_IN_BBOX_TOL
    return all(bb.min[i] - tol <= p[i] <= bb.max[i] + tol for i in range(3))


# Mapping from friendly face names to (axis_index, sign).
#   top/bottom  -> Z axis
#   front/back  -> Y axis  (front = -Y, back = +Y, matching scadwright convention)
#   lside/rside -> X axis  (lside = -X = left, rside = +X = right)
_FRIENDLY_TO_AXIS: dict[str, tuple[int, int]] = {
    "top": (2, 1),
    "bottom": (2, -1),
    "front": (1, -1),
    "back": (1, 1),
    "lside": (0, -1),
    "rside": (0, 1),
}

_AXIS_SIGN_TO_AXIS: dict[str, tuple[int, int]] = {
    "+x": (0, 1),
    "-x": (0, -1),
    "+y": (1, 1),
    "-y": (1, -1),
    "+z": (2, 1),
    "-z": (2, -1),
}

# All accepted face names.
FACE_NAMES: dict[str, tuple[int, int]] = {**_FRIENDLY_TO_AXIS, **_AXIS_SIGN_TO_AXIS}

# The six normals, indexed by (axis_index, sign).
_NORMALS: dict[tuple[int, int], tuple[float, float, float]] = {
    (0, 1): (1.0, 0.0, 0.0),
    (0, -1): (-1.0, 0.0, 0.0),
    (1, 1): (0.0, 1.0, 0.0),
    (1, -1): (0.0, -1.0, 0.0),
    (2, 1): (0.0, 0.0, 1.0),
    (2, -1): (0.0, 0.0, -1.0),
}


def resolve_face_name(name: str) -> tuple[int, int]:
    """Return ``(axis_index, sign)`` for a face name, or raise ``ValidationError``."""
    try:
        return FACE_NAMES[name]
    except KeyError:
        friendly = sorted(_FRIENDLY_TO_AXIS)
        axis_sign = sorted(_AXIS_SIGN_TO_AXIS)
        raise ValidationError(
            f"Unknown face name {name!r}. "
            f"Use one of {friendly} or {axis_sign}."
        )


# Friendly-string angles around a cylinder, measured CCW from +X (the
# canonical reference meridian). Used by ``add_text(angle=...)`` and
# ``Node.attach(angle=...)`` for parametric angular position on cylindrical
# / conical / rim anchors.
_ANGLE_ALIASES: dict[str, float] = {
    "+x": 0.0,
    "rside": 0.0,
    "+y": 90.0,
    "back": 90.0,
    "-x": 180.0,
    "lside": 180.0,
    "-y": 270.0,
    "front": 270.0,
}


def resolve_angle_to_radians(
    value,
    *,
    context_name: str,
    param_name: str = "angle",
) -> float:
    """Convert a numeric angle (degrees CCW) or a face-name string alias
    to radians.

    Used by every API that takes a parametric angle around a cylindrical
    or rim surface — keeps the alias vocabulary identical across
    ``attach(angle=...)``, ``add_text(angle=...)``, and any future
    callers.

    ``context_name`` ("attach", "add_text", etc.) and ``param_name``
    ("angle", "polar", etc.) are interpolated into the error message
    so the user knows which call rejected the input and which keyword
    they used. ``param_name`` defaults to ``"angle"``; pass it
    explicitly for related concepts like ``polar`` (sphere co-latitude).
    """
    import math as _math

    if isinstance(value, str):
        key = value.lower()
        if key not in _ANGLE_ALIASES:
            raise ValidationError(
                f"{context_name}: {param_name} must be one of "
                f"{sorted(_ANGLE_ALIASES)} or a numeric angle in degrees "
                f"CCW from +X; got {value!r}."
            )
        return _math.radians(_ANGLE_ALIASES[key])
    if isinstance(value, bool):
        raise ValidationError(
            f"{context_name}: {param_name} must be a string or numeric, got bool."
        )
    if isinstance(value, (int, float)):
        return _math.radians(float(value))
    raise ValidationError(
        f"{context_name}: {param_name} must be a string or numeric, got "
        f"{type(value).__name__}."
    )


def anchors_from_bbox(bb: "BBox") -> dict[str, Anchor]:
    """Derive the six standard face anchors from an axis-aligned bounding box.

    Returns a dict with 12 keys (6 friendly names + 6 axis-sign names).
    Friendly and axis-sign keys for the same face share the same Anchor object.
    """
    cx, cy, cz = bb.center

    anchors: dict[str, Anchor] = {}
    for name, (axis, sign) in FACE_NAMES.items():
        # Position: center of the face (bbox center, with the face-axis
        # coordinate replaced by the min or max of the bbox on that axis).
        pos = [cx, cy, cz]
        pos[axis] = bb.max[axis] if sign > 0 else bb.min[axis]
        anchor = Anchor(
            position=(pos[0], pos[1], pos[2]),
            normal=_NORMALS[(axis, sign)],
        )
        anchors[name] = anchor

    return anchors


def transform_anchors(
    anchors: dict[str, "Anchor"],
    matrix: "Matrix",
) -> dict[str, "Anchor"]:
    """Apply a transform matrix to every anchor's position, normal, and
    curved-surface metadata.

    Returns a new dict. Normals and direction fields (``axis``,
    ``meridian_zero``) are rotated and re-normalized; ``axis_origin``
    gets the full affine transform; radial scalars (``radius``,
    ``r1``, ``r2``, ``rim_radius``, ``mid_r``, ``end_r``,
    ``meridian_r``) scale by the matrix's effect on a unit vector
    perpendicular to the axis; ``length`` scales by the matrix's
    effect along the axis. Non-uniform scaling perpendicular to the
    axis turns a cylinder into an ellipse — not modeled; the radius
    scales by the magnitude of a single perpendicular reference.
    """
    import math as _math

    result: dict[str, Anchor] = {}
    for name, a in anchors.items():
        pos = matrix.apply_point(a.position)
        norm = matrix.apply_vector(a.normal)
        nlen = _math.sqrt(sum(c * c for c in norm))
        if nlen > 0:
            norm = (norm[0] / nlen, norm[1] / nlen, norm[2] / nlen)

        # Curved-surface metadata transformation. Anchors without an
        # ``axis`` carry no orientable curved geometry — pass radial /
        # length / boolean fields through unchanged.
        new_axis = a.axis
        new_meridian_zero = a.meridian_zero
        new_axis_origin = a.axis_origin
        new_radius = a.radius
        new_r1 = a.r1
        new_r2 = a.r2
        new_rim_radius = a.rim_radius
        new_meridian_r = a.meridian_r
        new_mid_r = a.mid_r
        new_end_r = a.end_r
        new_length = a.length

        if a.axis is not None:
            from scadwright.api.tolerances import AXIS_LEN_DEGEN_TOL
            new_axis_raw = matrix.apply_vector(a.axis)
            axis_len = _math.sqrt(sum(c * c for c in new_axis_raw))
            if axis_len >= AXIS_LEN_DEGEN_TOL:
                new_axis = tuple(c / axis_len for c in new_axis_raw)

                if a.meridian_zero is not None:
                    mz_raw = matrix.apply_vector(a.meridian_zero)
                    mz_len = _math.sqrt(sum(c * c for c in mz_raw))
                    if mz_len > AXIS_LEN_DEGEN_TOL:
                        new_meridian_zero = tuple(c / mz_len for c in mz_raw)

                if a.axis_origin is not None:
                    new_axis_origin = matrix.apply_point(a.axis_origin)

                # Radial scaling — perpendicular reference vector.
                ax, ay, az = a.axis
                ref = (0.0, 0.0, 1.0) if abs(az) < 0.99 else (1.0, 0.0, 0.0)
                perp = (
                    ref[1] * az - ref[2] * ay,
                    ref[2] * ax - ref[0] * az,
                    ref[0] * ay - ref[1] * ax,
                )
                perp_len = _math.sqrt(sum(c * c for c in perp))
                if perp_len > AXIS_LEN_DEGEN_TOL:
                    perp_unit = tuple(c / perp_len for c in perp)
                    new_perp = matrix.apply_vector(perp_unit)
                    radial_scale = _math.sqrt(sum(c * c for c in new_perp))
                else:
                    radial_scale = 1.0

                if a.radius is not None:
                    new_radius = a.radius * radial_scale
                if a.r1 is not None:
                    new_r1 = a.r1 * radial_scale
                if a.r2 is not None:
                    new_r2 = a.r2 * radial_scale
                if a.rim_radius is not None:
                    new_rim_radius = a.rim_radius * radial_scale
                if a.meridian_r is not None:
                    new_meridian_r = a.meridian_r * radial_scale
                if a.mid_r is not None:
                    new_mid_r = a.mid_r * radial_scale
                if a.end_r is not None:
                    new_end_r = a.end_r * radial_scale

                if a.length is not None:
                    new_axis_full = matrix.apply_vector(a.axis)
                    axial_scale = _math.sqrt(sum(c * c for c in new_axis_full))
                    new_length = a.length * axial_scale

        result[name] = Anchor(
            position=pos,
            normal=norm,
            kind=a.kind,
            axis=new_axis,
            axis_origin=new_axis_origin,
            meridian_zero=new_meridian_zero,
            radius=new_radius,
            r1=new_r1,
            r2=new_r2,
            length=new_length,
            rim_radius=new_rim_radius,
            inner=a.inner,
            meridian_r=new_meridian_r,
            mid_r=new_mid_r,
            meridian_s=a.meridian_s,
            end_r=new_end_r,
        )
    return result


def get_node_anchors(node) -> dict[str, "Anchor"]:
    """Return anchors for a node, propagating custom anchors through transforms.

    - Components: returns bbox-derived anchors merged with custom anchors.
    - Transform nodes wrapping a Component: recursively gets the child's
      anchors and applies the transform to positions and normals.
    - Decoration custom transforms (``@transform(decoration=True)``): pass
      through to the child so labels/decals don't strip the host's
      anchors. See ``docs/add_text.md``.
    - CSG nodes or primitives: returns only bbox-derived anchors (custom
      anchors are dropped by boolean operations).
    """
    return _AnchorVisitor().visit(node)


# =============================================================================
# AnchorVisitor — Visitor subclass walking the AST to compute named anchors
# =============================================================================


from scadwright.emit.visitor import Visitor as _Visitor  # noqa: E402


class _AnchorVisitor(_Visitor):
    """Compute a node's named anchors by walking the AST.

    Returns ``dict[str, Anchor]``. Stateless: spatial transforms apply
    on the way back up — each transform's ``visit_X`` recurses on the
    child, then transforms the returned anchor positions and normals.
    Components return their own ``get_anchors()`` dict (bbox-derived
    plus custom anchors merged). Decoration custom transforms pass
    through to the child so chained labels and post-decoration
    ``attach()`` calls keep working.
    """

    # --- Component: own anchor collection. ---

    def visit_component(self, n):
        return n.get_anchors()

    # --- Spatial transforms: recurse, then apply matrix to result. ---

    def _visit_spatial(self, n):
        from scadwright.matrix import to_matrix
        return transform_anchors(self.visit(n.child), to_matrix(n))

    def visit_Translate(self, n): return self._visit_spatial(n)
    def visit_Rotate(self, n): return self._visit_spatial(n)
    def visit_Scale(self, n): return self._visit_spatial(n)
    def visit_Mirror(self, n): return self._visit_spatial(n)
    def visit_MultMatrix(self, n): return self._visit_spatial(n)

    # --- Pass-through wrappers. ---

    def visit_Color(self, n): return self.visit(n.child)
    def visit_PreviewModifier(self, n): return self.visit(n.child)
    def visit_ForceRender(self, n): return self.visit(n.child)

    # --- WithAnchor: recurse, then add the named anchor on top. ---

    def visit_WithAnchor(self, n):
        anchors = dict(self.visit(n.child))
        anchors[n.anchor_name] = n.anchor
        return anchors

    # --- WithBBox: anchor-transparent (bbox assertion doesn't affect anchors). ---

    def visit_WithBBox(self, n):
        return self.visit(n.child)

    # --- Difference: propagate first-child anchors, dropping any custom
    # anchor whose position falls inside a cutter's bbox.
    #
    # The first child's bbox is the difference's bbox (conservative);
    # its bbox-derived faces are also the difference's bbox-derived
    # faces, so they propagate as-is. Custom anchors on the first
    # child usually survive a difference — drilling a hole doesn't move
    # the bracket's mount face — but a cutter whose bbox covers an
    # anchor's position may have removed material at it. Drop those
    # defensively. The user gets a clear missing-anchor error at attach
    # time pointing at the lost anchor; if the cutter actually doesn't
    # affect the anchor's face, the user can re-declare a fresh anchor.
    #
    # Union and Intersection still drop all custom anchors (handled by
    # generic_visit) — the semantic ambiguity there is real and there's
    # no clear "first child's anchors carry through" rule.

    def visit_Difference(self, n):
        from scadwright.bbox import bbox as _bbox

        if not n.children:
            return self.generic_visit(n)

        first_anchors = dict(self.visit(n.children[0]))
        if len(n.children) == 1:
            return first_anchors

        first_bb = _bbox(n.children[0])
        bbox_defaults = anchors_from_bbox(first_bb)
        cutter_bboxes = [_bbox(c) for c in n.children[1:]]

        result: dict[str, Anchor] = {}
        for name, a in first_anchors.items():
            # Bbox-derived defaults of the first child = bbox-derived
            # defaults of the difference. Propagate without the cutter
            # check (they're at the bbox extreme and unaffected by the
            # boolean's conservative bbox).
            if bbox_defaults.get(name) == a:
                result[name] = a
                continue
            # Custom anchor: drop if any cutter's bbox covers it.
            if any(_point_in_bbox(a.position, cb) for cb in cutter_bboxes):
                continue
            result[name] = a
        return result

    def visit_Echo(self, n):
        if n.child is None:
            return self.generic_visit(n)
        return self.visit(n.child)

    # --- Custom: decoration transforms preserve host anchors. ---

    def visit_Custom(self, n):
        from scadwright._custom_transforms.base import get_transform

        t = get_transform(n.name)
        if t is not None and getattr(t, "decoration", False):
            return self.visit(n.child)
        return self.generic_visit(n)

    # --- Cylinder: bbox-derived faces plus rim/wall metadata. ---

    def visit_Cylinder(self, n):
        from scadwright.bbox import bbox as _bbox
        bb = _bbox(n)
        anchors = anchors_from_bbox(bb)
        rim_top, rim_bottom = _cylinder_rim_anchors(n)
        if rim_top is not None:
            anchors["top"] = rim_top
            anchors["+z"] = rim_top
        if rim_bottom is not None:
            anchors["bottom"] = rim_bottom
            anchors["-z"] = rim_bottom
        wall = _cylinder_outer_wall_anchor(n)
        if wall is not None:
            anchors["outer_wall"] = wall
        return anchors

    # --- Sphere: bbox-derived faces, but every face anchor is on the
    # spherical surface (a tangent point), not a planar face. Declare
    # kind="spherical" so curved-surface fuse dispatches via the bridge
    # mechanism instead of trying the planar cross-section path.
    # ``axis_origin`` (sphere center), ``axis`` (north-pole direction),
    # and ``meridian_zero`` (azimuth=0 reference) let attach() compute
    # arbitrary polar/azimuth points on the sphere.

    def visit_Sphere(self, n):
        from scadwright.bbox import bbox as _bbox
        bb = _bbox(n)
        radius = float(n.r)
        center = (bb.center[0], bb.center[1], bb.center[2])
        common = dict(
            kind="spherical",
            axis=(0.0, 0.0, 1.0),
            axis_origin=center,
            meridian_zero=(1.0, 0.0, 0.0),
            radius=radius,
        )
        anchors: dict[str, Anchor] = {}
        for name, (axis, sign) in FACE_NAMES.items():
            pos = [center[0], center[1], center[2]]
            pos[axis] = bb.max[axis] if sign > 0 else bb.min[axis]
            anchors[name] = Anchor(
                position=(pos[0], pos[1], pos[2]),
                normal=_NORMALS[(axis, sign)],
                **common,
            )
        # ``surface`` is the canonical entry-point anchor for polar /
        # angle placement on a sphere — defaults to the +Z tangent
        # point but the attach() helper recomputes position and normal
        # from polar/azimuth, so the actual default doesn't matter much.
        anchors["surface"] = Anchor(
            position=(center[0], center[1], center[2] + radius),
            normal=(0.0, 0.0, 1.0),
            **common,
        )
        return anchors

    # --- Default: bbox-derived only (other primitives, CSG, etc). ---

    def generic_visit(self, n):
        from scadwright.bbox import bbox as _bbox
        return anchors_from_bbox(_bbox(n))


def _cylinder_rim_anchors(cyl):
    """Return (top_rim, bottom_rim) Anchors for a Cylinder primitive.

    Rim anchors are planar (the disk face is flat) but carry ``rim_radius``
    in ``surface_params`` so disk-rim arc text knows the circumradius.
    ``axis`` is the cylinder's central axis direction — the same value for
    top and bottom rim, and identical to the wall anchor's ``axis``. This
    keeps the angular convention (``angle=`` CCW from +X around the
    cylinder's axis) consistent across both rims and the wall.

    ``meridian_zero`` is the +X-meridian direction in the local frame —
    the reference direction for ``angle=0``. It transforms with the host
    just like ``axis`` and the wall anchor's normal, so when the host is
    rotated around its own axis the meridian-zero direction follows. For
    an axis-aligned cylinder, this is just ``(1, 0, 0)``.
    """
    h = cyl.h
    if cyl.center:
        z_min = -h / 2.0
        z_max = h / 2.0
    else:
        z_min = 0.0
        z_max = h

    rim_top = None
    if cyl.r2 > 0:
        rim_top = Anchor(
            position=(0.0, 0.0, z_max),
            normal=(0.0, 0.0, 1.0),
            kind="planar",
            axis=(0.0, 0.0, 1.0),
            meridian_zero=(1.0, 0.0, 0.0),
            rim_radius=float(cyl.r2),
        )
    rim_bottom = None
    if cyl.r1 > 0:
        rim_bottom = Anchor(
            position=(0.0, 0.0, z_min),
            normal=(0.0, 0.0, -1.0),
            kind="planar",
            axis=(0.0, 0.0, 1.0),
            meridian_zero=(1.0, 0.0, 0.0),
            rim_radius=float(cyl.r1),
        )
    return rim_top, rim_bottom


def _cylinder_outer_wall_anchor(cyl) -> "Anchor | None":
    """Build the outer_wall anchor for a Cylinder primitive in its local frame.

    Cylinders (r1 == r2) get a ``"cylindrical"`` anchor; cones (r1 != r2)
    get a ``"conical"`` anchor with both radii. The reference position is
    the +X meridian at the wall's axial midpoint, with outward normal +X
    (radial — not the surface normal of a slanted cone, but the canonical
    reference direction add_text uses to compute glyph positions).
    """
    h = cyl.h
    if cyl.center:
        z_mid = 0.0
    else:
        z_mid = h / 2.0

    if cyl.r1 == cyl.r2:
        r = cyl.r1
        if r <= 0:
            return None
        return Anchor(
            position=(r, 0.0, z_mid),
            normal=(1.0, 0.0, 0.0),
            kind="cylindrical",
            axis=(0.0, 0.0, 1.0),
            length=float(h),
            radius=float(r),
        )

    # Conical: r1 at z_min, r2 at z_max. Mid-wall radius for the reference position.
    if cyl.r1 < 0 or cyl.r2 < 0:
        return None
    r_mid = (cyl.r1 + cyl.r2) / 2.0
    if r_mid <= 0:
        return None
    return Anchor(
        position=(r_mid, 0.0, z_mid),
        normal=(1.0, 0.0, 0.0),
        kind="conical",
        axis=(0.0, 0.0, 1.0),
        length=float(h),
        r1=float(cyl.r1),
        r2=float(cyl.r2),
    )


__all__ = [
    "ANCHOR_KINDS",
    "Anchor",
    "FACE_NAMES",
    "anchors_from_bbox",
    "get_node_anchors",
    "resolve_angle_to_radians",
    "resolve_face_name",
    "transform_anchors",
]
