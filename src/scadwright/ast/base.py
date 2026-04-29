"""Node base, SourceLocation, capture toggle.

The Node class aggregates four per-concern mixins from sibling modules —
``_DirectionalMixin`` (up/down/…/flip), ``_DisplayMixin`` (preview
modifiers + SVG color shorthands), ``_CompositionMixin``
(mirror_copy/halve/rotate_copy/linear_copy/array), and ``_ExtrudeMixin``
(linear_extrude/rotate_extrude). The core transforms, ``attach``,
``through``, ``center_bbox``, and the boolean operators stay here.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from scadwright.ast.node_compose import _CompositionMixin
from scadwright.ast.node_directional import _DirectionalMixin
from scadwright.ast.node_display import _DisplayMixin
from scadwright.ast.node_extrude import _ExtrudeMixin

if TYPE_CHECKING:
    pass


# Module-level toggle. Set to False to skip frame capture entirely.
capture_source_locations: bool = True


# Root of the scadwright package, used by from_caller to walk past internal
# frames to the user's call site. Computed once at import time.
_SCADWRIGHT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep


def _is_internal_frame(filename: str) -> bool:
    return filename.startswith(_SCADWRIGHT_ROOT)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    file: str
    line: int
    func: str | None = None

    def __str__(self) -> str:
        if self.func:
            return f"{self.file}:{self.line} ({self.func})"
        return f"{self.file}:{self.line}"

    @classmethod
    def from_caller(cls) -> "SourceLocation | None":
        """Capture the first frame outside the scadwright package.

        Walks up the stack past scadwright-internal frames to find the user's
        call site. Robust against wrappers that change call depth — no
        skip-counting required.

        Returns None if capture is disabled or no user frame is found.
        """
        if not capture_source_locations:
            return None
        try:
            frame = sys._getframe(1)
        except ValueError:
            return None
        while frame is not None:
            if not _is_internal_frame(frame.f_code.co_filename):
                return cls(
                    file=frame.f_code.co_filename,
                    line=frame.f_lineno,
                    func=frame.f_code.co_name or None,
                )
            frame = frame.f_back
        return None

    @classmethod
    def from_instantiation_site(cls) -> "SourceLocation | None":
        """Capture the user-code site that instantiated a Component.

        Differs from `from_caller` in that it walks past both scadwright frames
        AND any `__init__` frames in the call chain — the latter handles the
        `super().__init__()` pattern where the immediate user frame is the
        subclass's own `__init__` rather than the instantiation site.
        """
        if not capture_source_locations:
            return None
        try:
            frame = sys._getframe(1)
        except ValueError:
            return None
        while frame is not None:
            fname = frame.f_code.co_filename
            fn_name = frame.f_code.co_name
            if _is_internal_frame(fname) or fn_name == "__init__":
                frame = frame.f_back
                continue
            return cls(
                file=fname, line=frame.f_lineno, func=fn_name or None
            )
        return None


# --- through() helpers ---


_AXIS_MAP = {"x": 0, "y": 1, "z": 2}


def _detect_through_axis(self_bb, parent_bb, explicit_axis: str | None, loc) -> int:
    """Pick the cut axis for ``through()``.

    Returns the axis index (0/1/2). If ``explicit_axis`` is given, parses
    it. Otherwise auto-detects: prefers axes where the cutter has a
    face coincident with the parent (picking the most-spanning one if
    several match), and falls back to the axis where the cutter's size
    most closely matches the parent's.
    """
    from scadwright.errors import ValidationError

    if explicit_axis is not None:
        ax = _AXIS_MAP.get(explicit_axis.lower())
        if ax is None:
            raise ValidationError(
                f"through: axis must be 'x', 'y', or 'z', got {explicit_axis!r}",
                source_location=loc,
            )
        return ax

    tol_detect = 1e-4
    candidates = [
        i for i in range(3)
        if abs(self_bb.min[i] - parent_bb.min[i]) < tol_detect
        or abs(self_bb.max[i] - parent_bb.max[i]) < tol_detect
    ]
    parent_size = parent_bb.size
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Multiple coincident axes — pick the one where the cutter spans
        # the most of the parent.
        best = candidates[0]
        best_ratio = 0.0
        for i in candidates:
            if parent_size[i] > 1e-10:
                r = self_bb.size[i] / parent_size[i]
                if r > best_ratio:
                    best_ratio = r
                    best = i
        return best
    # No coincident faces — fall back to the closest size match.
    self_size = self_bb.size
    ratios = [
        float("inf") if parent_size[i] < 1e-10
        else abs(self_size[i] / parent_size[i] - 1.0)
        for i in range(3)
    ]
    return ratios.index(min(ratios))


def _extend_through_faces(self, self_bb, parent_bb, ax: int, eps: float, loc):
    """Wrap ``self`` in the Scale+Translate that extends it across whichever
    of its ``ax``-faces are coincident with ``parent``'s. Returns ``self``
    unchanged when no face matches (the call site's no-op contract).
    Raises ValidationError if the cutter doesn't overlap the parent on
    the cut axis at all.
    """
    from scadwright.ast.transforms import Scale, Translate
    from scadwright.errors import ValidationError

    tol = 1e-4
    if (self_bb.max[ax] < parent_bb.min[ax] - tol
            or self_bb.min[ax] > parent_bb.max[ax] + tol):
        raise ValidationError(
            f"through: cutter does not overlap parent on the "
            f"{'xyz'[ax]}-axis. Call through() after positioning the cutter.",
            source_location=loc,
        )

    min_coincident = abs(self_bb.min[ax] - parent_bb.min[ax]) < tol
    max_coincident = abs(self_bb.max[ax] - parent_bb.max[ax]) < tol
    if not min_coincident and not max_coincident:
        return self

    new_min = (parent_bb.min[ax] - eps) if min_coincident else self_bb.min[ax]
    new_max = (parent_bb.max[ax] + eps) if max_coincident else self_bb.max[ax]

    orig_size = self_bb.max[ax] - self_bb.min[ax]
    if orig_size < 1e-10:
        raise ValidationError(
            f"through: cutter has zero extent on the {'xyz'[ax]}-axis. "
            f"through() needs a 3D cutter with non-zero extent on the cut "
            f"axis; a 2D profile must be linear_extrude()'d or "
            f"rotate_extrude()'d before passing to through().",
            source_location=loc,
        )

    scale_factor = (new_max - new_min) / orig_size
    # Scale-from-origin + translate yields: new_pos = old_pos * s + delta
    # where delta shifts the scaled center onto the target center.
    old_center = (self_bb.min[ax] + self_bb.max[ax]) / 2.0
    new_center = (new_min + new_max) / 2.0
    delta = new_center - old_center * scale_factor

    factor = [1.0, 1.0, 1.0]
    factor[ax] = scale_factor
    offset = [0.0, 0.0, 0.0]
    offset[ax] = delta
    return Translate(
        v=tuple(offset),
        child=Scale(factor=tuple(factor), child=self, source_location=loc),
        source_location=loc,
    )


# --- attach() helpers ---


def _resolve_attach_anchor(node, name: str, role: str, loc):
    """Look up a named anchor on ``node``; raise ValidationError with a
    diagnostic message (custom-anchor vs. standard-face hint) on miss.
    """
    from scadwright.anchor import FACE_NAMES, get_node_anchors, resolve_face_name
    from scadwright.errors import ValidationError

    anchors = get_node_anchors(node)
    if name not in anchors:
        if name in FACE_NAMES:
            resolve_face_name(name)  # pragma: no cover — sanity path
        type_name = type(node).__name__
        available = sorted(anchors)
        # Components publish more than the 12 bbox defaults; use that as the
        # heuristic for whether a "custom anchor missing" message applies.
        if len(available) > 12:
            raise ValidationError(
                f"attach: no anchor {name!r} on {role} ({type_name}). "
                f"Available: {available}",
                source_location=loc,
            )
        raise ValidationError(
            f"attach: custom anchor {name!r} on {role} ({type_name}) — "
            f"custom anchors are only available on Components. Primitives "
            f"support the standard face names: top, bottom, front, back, "
            f"lside, rside (or +z, -z, -y, +y, -x, +x).",
            source_location=loc,
        )
    return anchors[name]


def _shift_for_anchors(self_anchor, other_anchor, fuse: bool, eps: float):
    """Translation vector that puts ``self_anchor`` on ``other_anchor``.

    When ``fuse`` is set, offset by ``eps`` along the other-anchor normal
    (into the contact face) to eliminate coincident-surface seams in
    unions.
    """
    shift = [
        other_anchor.position[i] - self_anchor.position[i] for i in range(3)
    ]
    if fuse:
        fn = other_anchor.normal
        for i in range(3):
            shift[i] -= fn[i] * eps
    return (shift[0], shift[1], shift[2])


def _orient_child_to_normal(child, self_normal, target_normal, loc):
    """Return ``child`` wrapped in the Rotate that takes ``self_normal`` to
    ``target_normal``. Picks the right branch (general, already-aligned,
    or 180° flip) based on the dot/cross of the two unit normals.
    """
    import math as _math

    from scadwright.ast.transforms import Rotate

    def _dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def _cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def _length(v):
        return _math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

    d = _dot(self_normal, target_normal)
    axis = _cross(self_normal, target_normal)
    if _length(axis) > 1e-10:
        # General case: rotate around the cross-product axis.
        angle_deg = _math.degrees(_math.acos(max(-1.0, min(1.0, d))))
        return Rotate(a=angle_deg, v=axis, child=child, source_location=loc)
    if d < -0.5:
        # Normals already opposite (touching-aligned) — no rotation.
        return child
    # Normals coincide (d ~ +1); 180° flip around any perpendicular axis.
    perp = _cross(self_normal, (1, 0, 0) if abs(self_normal[0]) < 0.9 else (0, 1, 0))
    return Rotate(a=180.0, v=perp, child=child, source_location=loc)


@dataclass(frozen=True)
class Node(
    _DirectionalMixin,
    _DisplayMixin,
    _CompositionMixin,
    _ExtrudeMixin,
):
    """Base for all AST nodes.

    source_location is kw_only so concrete subclasses can declare required positional
    fields without colliding with the default.

    Mixins add chained-method conveniences (directional helpers, color
    shorthands, composition/copy helpers, extrusions). See each mixin
    module for what they contribute.
    """

    source_location: SourceLocation | None = field(default=None, kw_only=True)

    # --- chained transforms (late imports to avoid circular deps) ---

    def translate(self, v=None, *, x: float = 0, y: float = 0, z: float = 0) -> "Node":
        from scadwright.ast.transforms import Translate
        from scadwright.api._vectors import _vec_from_args

        v_vec = _vec_from_args(v, x, y, z, default=(0.0, 0.0, 0.0), allow_symbolic=True)
        return Translate(
            v=v_vec, child=self, source_location=SourceLocation.from_caller()
        )

    def rotate(
        self,
        a=None,
        v=None,
        *,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        angle=None,
        axis=None,
    ) -> "Node":
        """Euler form: rotate([x, y, z]) or rotate(x=..., y=..., z=...).

        Axis-angle form: rotate(a=angle, v=[ax, ay, az]). The more readable
        aliases `angle=` and `axis=` are also accepted; pair them consistently
        (either short-name pair or long-name pair).
        """
        from scadwright.ast.transforms import Rotate
        from scadwright.api._vectors import _as_vec3
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        # Resolve angle/axis aliases. Collision = explicit error.
        if angle is not None:
            if a is not None:
                raise ValidationError(
                    "rotate: pass either `a=` or `angle=`, not both",
                    source_location=loc,
                )
            a = angle
        if axis is not None:
            if v is not None:
                raise ValidationError(
                    "rotate: pass either `v=` or `axis=`, not both",
                    source_location=loc,
                )
            v = axis

        from scadwright.animation import SymbolicExpr

        # Axis-angle: scalar `a` (or symbolic) + `v` axis vector.
        if v is not None and isinstance(a, (int, float, SymbolicExpr)) and not isinstance(a, bool):
            return Rotate(
                child=self,
                a=a if isinstance(a, SymbolicExpr) else float(a),
                v=_as_vec3(v, default_scalar_broadcast=False, allow_symbolic=True),
                source_location=loc,
            )
        # Euler via positional `a` (treated as angles vector) or kwargs x/y/z.
        if a is not None:
            angles = _as_vec3(a, default_scalar_broadcast=False, allow_symbolic=True)
        else:
            angles = tuple(
                v_ if isinstance(v_, SymbolicExpr) else float(v_)
                for v_ in (x, y, z)
            )
        return Rotate(child=self, angles=angles, source_location=loc)

    def scale(self, v=None, *, x: float = 1, y: float = 1, z: float = 1) -> "Node":
        from scadwright.ast.transforms import Scale
        from scadwright.api._vectors import _as_vec3
        from scadwright.animation import SymbolicExpr

        if v is not None:
            # Scalar scale broadcasts to all axes (SCAD accepts scale=2).
            factor = _as_vec3(v, default_scalar_broadcast=True, allow_symbolic=True)
        else:
            factor = tuple(
                v_ if isinstance(v_, SymbolicExpr) else float(v_)
                for v_ in (x, y, z)
            )
        return Scale(
            factor=factor, child=self, source_location=SourceLocation.from_caller()
        )

    def mirror(self, v=None, *, x: float = 0, y: float = 0, z: float = 0) -> "Node":
        from scadwright.ast.transforms import Mirror
        from scadwright.api._vectors import _vec_from_args

        normal = _vec_from_args(v, x, y, z, allow_symbolic=True)
        return Mirror(
            normal=normal, child=self, source_location=SourceLocation.from_caller()
        )

    def color(self, c, alpha: float = 1.0) -> "Node":
        from scadwright.ast.transforms import Color

        if isinstance(c, str):
            stored: str | tuple[float, ...] = c
        else:
            stored = tuple(float(x) for x in c)
        return Color(
            c=stored,
            child=self,
            alpha=float(alpha),
            source_location=SourceLocation.from_caller(),
        )

    def resize(self, v, *, auto=False) -> "Node":
        from scadwright.ast.transforms import Resize
        from scadwright.api._vectors import _as_vec3, _normalize_center

        new_size = _as_vec3(v, default_scalar_broadcast=False)
        # `auto` uses the same shape as center (bool, list, string).
        auto_tuple = _normalize_center(auto)
        return Resize(
            new_size=new_size,
            auto=auto_tuple,
            child=self,
            source_location=SourceLocation.from_caller(),
        )

    def offset(
        self,
        *,
        r: float | None = None,
        delta: float | None = None,
        chamfer: bool = False,
        fn: float | None = None,
        fa: float | None = None,
        fs: float | None = None,
    ) -> "Node":
        from scadwright.ast.transforms import Offset
        from scadwright.api._validate import _require_resolution
        from scadwright.api.resolution import resolve as _resolve_res
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if (r is None) == (delta is None):
            raise ValidationError(
                f"offset: pass exactly one of `r` or `delta`; got r={r!r}, delta={delta!r}",
                source_location=loc,
            )
        if r is not None and chamfer:
            raise ValidationError(
                "offset: chamfer only applies with delta, not r",
                source_location=loc,
            )
        fn, fa, fs = _resolve_res(fn, fa, fs)
        fn, fa, fs = _require_resolution(fn, fa, fs, context="offset")
        return Offset(
            child=self,
            r=float(r) if r is not None else None,
            delta=float(delta) if delta is not None else None,
            chamfer=bool(chamfer),
            fn=fn, fa=fa, fs=fs,
            source_location=loc,
        )

    def multmatrix(self, matrix) -> "Node":
        from scadwright.ast.transforms import MultMatrix
        from scadwright.matrix import Matrix
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if isinstance(matrix, Matrix):
            m = matrix
        else:
            try:
                rows = [list(row) for row in matrix]
            except TypeError:
                raise ValidationError(
                    f"multmatrix: expected a Matrix or 4x4 / 4x3 list, got {type(matrix).__name__}",
                    source_location=loc,
                ) from None
            if len(rows) == 3 and all(len(r) == 4 for r in rows):
                # 3x4: pad last row [0, 0, 0, 1]
                rows.append([0.0, 0.0, 0.0, 1.0])
            if len(rows) == 4 and all(len(r) == 3 for r in rows):
                # 4x3: pad last column with [0, 0, 0, 1]
                rows = [r + [0.0 if i < 3 else 1.0] for i, r in enumerate(rows)]
            if len(rows) != 4 or not all(len(r) == 4 for r in rows):
                got = f"{len(rows)}x{len(rows[0]) if rows else 0}"
                raise ValidationError(
                    f"multmatrix: matrix must be 4x4 (or 3x4 / 4x3, which "
                    f"scadwright pads to 4x4); got {got}. If you have a 3x3 "
                    f"rotation matrix, pad manually: append [0, 0, 0] to each "
                    f"row and add a [0, 0, 0, 1] row at the bottom.",
                    source_location=loc,
                )
            m = Matrix(tuple(tuple(float(x) for x in r) for r in rows))
        return MultMatrix(matrix=m, child=self, source_location=loc)

    def projection(self, *, cut: bool = False) -> "Node":
        from scadwright.ast.transforms import Projection

        return Projection(
            child=self,
            cut=bool(cut),
            source_location=SourceLocation.from_caller(),
        )

    # --- debug / diagnostic wrappers ---

    def force_render(self, *, convexity: int | None = None) -> "Node":
        """Wrap in SCAD's render(convexity=...) to force full CGAL rendering.

        Debug/performance aid — forces OpenSCAD to render this subtree fully
        even in preview (F5) mode. Doesn't change emitted geometry.
        """
        from scadwright.ast.transforms import ForceRender

        loc = SourceLocation.from_caller()
        if convexity is not None:
            convexity = int(convexity)
        return ForceRender(child=self, convexity=convexity, source_location=loc)

    def echo(self, *args, **kwargs) -> "Node":
        """Wrap this subtree in a SCAD echo(...) for diagnostics."""
        from scadwright.ast.transforms import Echo

        loc = SourceLocation.from_caller()
        values = tuple((None, v) for v in args) + tuple(sorted(kwargs.items()))
        return Echo(values=values, child=self, source_location=loc)

    # --- placement helpers ---

    def center_bbox(self, axes=None) -> "Node":
        """Translate so this shape's AABB is centered at the origin.

        ``axes`` controls which axes to center. Accepts the same forms
        as ``cube(center=...)``: ``True`` (all), ``"xy"`` (X and Y only),
        ``[True, False, True]`` (X and Z only), etc. Default (``None``)
        centers all axes.
        """
        from scadwright.bbox import bbox as _bbox
        from scadwright.ast.transforms import Translate

        bb = _bbox(self)
        cx, cy, cz = bb.center
        if axes is not None:
            from scadwright.api._vectors import _normalize_center
            ax = _normalize_center(axes)
            cx = cx if ax[0] else 0
            cy = cy if ax[1] else 0
            cz = cz if ax[2] else 0
        if cx == 0 and cy == 0 and cz == 0:
            return self
        return Translate(
            v=(-cx, -cy, -cz),
            child=self,
            source_location=SourceLocation.from_caller(),
        )

    def attach(
        self,
        other: "Node",
        on: str = "top",
        at: str = "bottom",
        *,
        orient: bool = False,
        fuse: bool = False,
        eps: float = 0.01,
    ) -> "Node":
        """Position self so its ``at`` anchor touches ``other``'s ``on`` anchor.

        Both ``on`` and ``at`` accept friendly names (``"top"``, ``"bottom"``,
        ``"front"``, ``"back"``, ``"lside"``, ``"rside"``) or axis-sign names
        (``"+z"``, ``"-z"``, ``"+y"``, ``"-y"``, ``"+x"``, ``"-x"``).

        By default, only translation is applied (self is moved so the anchor
        positions coincide). Pass ``orient=True`` to also rotate self so the
        two anchors' normals oppose each other (faces touching).

        Pass ``fuse=True`` to extend self by ``eps`` into the contact face,
        eliminating coincident-surface artifacts in unions::

            pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)

        Chain a directional helper for offset placement::

            peg.attach(plate).right(10)
        """
        from scadwright.anchor import anchors_from_bbox
        from scadwright.bbox import bbox as _bbox
        from scadwright.ast.transforms import Translate

        loc = SourceLocation.from_caller()
        other_anchor = _resolve_attach_anchor(other, on, "other", loc)
        self_anchor = _resolve_attach_anchor(self, at, "self", loc)

        if not orient:
            shift = _shift_for_anchors(self_anchor, other_anchor, fuse, eps)
            return Translate(v=shift, child=self, source_location=loc)

        # orient=True: rotate self so at-normal opposes face-normal, then translate.
        target_normal = tuple(-c for c in other_anchor.normal)
        child = _orient_child_to_normal(self, self_anchor.normal, target_normal, loc)

        # Recompute self's anchor position after rotation.
        rotated_anchors = anchors_from_bbox(_bbox(child))
        rotated_self_anchor = rotated_anchors.get(
            at, rotated_anchors.get("bottom", self_anchor)
        )
        shift = _shift_for_anchors(rotated_self_anchor, other_anchor, fuse, eps)
        return Translate(v=shift, child=child, source_location=loc)

    def through(
        self,
        parent: "Node",
        *,
        axis: str | None = None,
        eps: float = 0.01,
    ) -> "Node":
        """Extend self through coincident faces of ``parent`` by ``eps``.

        Use on cutters before passing them to ``difference()`` to eliminate
        manual epsilon overlap::

            part = difference(box, cylinder(h=20, r=3).through(box))

        The cutter is extended through any face of ``parent`` that it
        touches (within floating-point tolerance) on the cut axis. Faces
        that aren't coincident are left alone.

        ``axis`` is auto-detected (the axis where the cutter most closely
        spans the parent). Pass ``axis="x"``/``"y"``/``"z"`` to override.

        Call ``through()`` after positioning the cutter (after any
        ``.up()``, ``.translate()``, ``.attach()`` calls).
        """
        from scadwright.bbox import bbox as _bbox

        loc = SourceLocation.from_caller()
        self_bb = _bbox(self)
        parent_bb = _bbox(parent)
        ax = _detect_through_axis(self_bb, parent_bb, axis, loc)
        return _extend_through_faces(self, self_bb, parent_bb, ax, eps, loc)

    @property
    def bbox(self):
        """The world-space axis-aligned bounding box of this shape.

        Equivalent to ``scadwright.bbox(self)``. Use ``.bbox.size``,
        ``.bbox.center``, ``.bbox.min``, ``.bbox.max`` for derived
        quantities. For Components, the bbox is cached on the instance
        and invalidated when a Param is changed.
        """
        from scadwright.bbox import bbox as _bbox_fn
        return _bbox_fn(self)

    # --- boolean operators ---

    def __sub__(self, other):
        from scadwright.ast.csg import Difference
        if not isinstance(other, Node):
            return NotImplemented
        loc = SourceLocation.from_caller()
        if isinstance(self, Difference):
            return Difference(children=self.children + (other,), source_location=loc)
        return Difference(children=(self, other), source_location=loc)

    def __or__(self, other):
        from scadwright.ast.csg import Union
        if not isinstance(other, Node):
            return NotImplemented
        loc = SourceLocation.from_caller()
        if isinstance(self, Union):
            return Union(children=self.children + (other,), source_location=loc)
        return Union(children=(self, other), source_location=loc)

    def __and__(self, other):
        from scadwright.ast.csg import Intersection
        if not isinstance(other, Node):
            return NotImplemented
        loc = SourceLocation.from_caller()
        if isinstance(self, Intersection):
            return Intersection(children=self.children + (other,), source_location=loc)
        return Intersection(children=(self, other), source_location=loc)

