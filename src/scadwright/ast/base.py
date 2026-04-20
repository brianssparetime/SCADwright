"""Node base, SourceLocation, capture toggle."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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


@dataclass(frozen=True)
class Node:
    """Base for all AST nodes.

    source_location is kw_only so concrete subclasses can declare required positional
    fields without colliding with the default.
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
        face: str = "top",
        at: str = "bottom",
        *,
        orient: bool = False,
        fuse: bool = False,
        eps: float = 0.01,
    ) -> "Node":
        """Position self so its ``at`` anchor touches ``other``'s ``face`` anchor.

        Both ``face`` and ``at`` accept friendly names (``"top"``, ``"bottom"``,
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
        import math as _math

        from scadwright.anchor import (
            FACE_NAMES,
            anchors_from_bbox,
            get_node_anchors,
            resolve_face_name,
        )
        from scadwright.bbox import bbox as _bbox
        from scadwright.ast.transforms import Rotate, Translate
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()

        def _get_anchor(node, name, role):
            """Return the Anchor for *name* on *node*, validating."""
            anchors = get_node_anchors(node)
            if name not in anchors:
                if name in FACE_NAMES:
                    resolve_face_name(name)  # pragma: no cover
                else:
                    available = sorted(anchors)
                    # Check if the node has any custom anchors (Component or
                    # transform-wrapped Component).
                    has_custom = len(available) > 12
                    if has_custom:
                        raise ValidationError(
                            f"attach: no anchor {name!r} on {role}. "
                            f"Available: {available}",
                            source_location=loc,
                        )
                    else:
                        raise ValidationError(
                            f"attach: custom anchor {name!r} is only available "
                            f"on Components. Primitives support the standard "
                            f"face names: top, bottom, front, back, lside, rside "
                            f"(or +z, -z, -y, +y, -x, +x).",
                            source_location=loc,
                        )
            return anchors[name]

        other_anchor = _get_anchor(other, face, "other")
        self_anchor = _get_anchor(self, at, "self")

        def _apply_fuse(shift_list):
            """Push self EPS into other along the face normal."""
            if not fuse:
                return
            # Face normal points outward from other. To push self INTO
            # other, move in the opposite direction of the face normal.
            fn = other_anchor.normal
            shift_list[0] -= fn[0] * eps
            shift_list[1] -= fn[1] * eps
            shift_list[2] -= fn[2] * eps

        if not orient:
            shift = [
                other_anchor.position[0] - self_anchor.position[0],
                other_anchor.position[1] - self_anchor.position[1],
                other_anchor.position[2] - self_anchor.position[2],
            ]
            _apply_fuse(shift)
            return Translate(v=(shift[0], shift[1], shift[2]), child=self, source_location=loc)

        # orient=True: rotate self so at-normal opposes face-normal, then translate.
        an = self_anchor.normal
        # Target: at-normal should point opposite to face-normal (faces touching).
        tn = (
            -other_anchor.normal[0],
            -other_anchor.normal[1],
            -other_anchor.normal[2],
        )

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

        d = _dot(an, tn)
        axis = _cross(an, tn)
        axis_len = _length(axis)

        child = self
        if axis_len > 1e-10:
            # General case: rotate around the cross-product axis.
            angle_deg = _math.degrees(_math.acos(max(-1.0, min(1.0, d))))
            child = Rotate(
                a=angle_deg,
                v=axis,
                child=child,
                source_location=loc,
            )
        elif d < -0.5:
            # Normals are opposite (already aligned for touching) -- no rotation.
            pass
        else:
            # Normals are the same direction (d ~ +1) -- need 180-degree flip.
            # Pick a perpendicular axis.
            if abs(an[0]) < 0.9:
                perp = _cross(an, (1, 0, 0))
            else:
                perp = _cross(an, (0, 1, 0))
            child = Rotate(a=180.0, v=perp, child=child, source_location=loc)

        # Recompute self's anchor position after rotation.
        rotated_bb = _bbox(child)
        rotated_anchors = anchors_from_bbox(rotated_bb)
        if at in rotated_anchors:
            rotated_self_anchor = rotated_anchors[at]
        else:
            rotated_self_anchor = rotated_anchors.get("bottom", self_anchor)

        shift = [
            other_anchor.position[0] - rotated_self_anchor.position[0],
            other_anchor.position[1] - rotated_self_anchor.position[1],
            other_anchor.position[2] - rotated_self_anchor.position[2],
        ]
        _apply_fuse(shift)
        return Translate(v=(shift[0], shift[1], shift[2]), child=child, source_location=loc)

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
        from scadwright.ast.transforms import Scale, Translate
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        self_bb = _bbox(self)
        parent_bb = _bbox(parent)

        # Determine cut axis.
        axis_map = {"x": 0, "y": 1, "z": 2}
        if axis is not None:
            ax = axis_map.get(axis.lower())
            if ax is None:
                raise ValidationError(
                    f"through: axis must be 'x', 'y', or 'z', got {axis!r}",
                    source_location=loc,
                )
        else:
            # Auto-detect: prefer an axis where the cutter has at least
            # one face coincident with the parent. Among those, pick the
            # axis where the cutter spans the most of the parent.
            tol_detect = 1e-4
            candidates = []
            for i in range(3):
                lo_match = abs(self_bb.min[i] - parent_bb.min[i]) < tol_detect
                hi_match = abs(self_bb.max[i] - parent_bb.max[i]) < tol_detect
                if lo_match or hi_match:
                    candidates.append(i)
            if len(candidates) == 1:
                ax = candidates[0]
            elif len(candidates) > 1:
                # Multiple axes have coincident faces; pick the one where
                # the cutter spans the most of the parent.
                parent_size = parent_bb.size
                best = candidates[0]
                best_ratio = 0.0
                for i in candidates:
                    if parent_size[i] > 1e-10:
                        r = self_bb.size[i] / parent_size[i]
                        if r > best_ratio:
                            best_ratio = r
                            best = i
                ax = best
            else:
                # No coincident faces on any axis — fall back to the axis
                # where the cutter most closely spans the parent.
                parent_size = parent_bb.size
                self_size = self_bb.size
                ratios = []
                for i in range(3):
                    if parent_size[i] < 1e-10:
                        ratios.append(float("inf"))
                    else:
                        ratios.append(abs(self_size[i] / parent_size[i] - 1.0))
                ax = ratios.index(min(ratios))

        tol = 1e-4

        # Check the cutter overlaps the parent on the cut axis at all.
        if (self_bb.max[ax] < parent_bb.min[ax] - tol or
                self_bb.min[ax] > parent_bb.max[ax] + tol):
            raise ValidationError(
                f"through: cutter does not overlap parent on the "
                f"{'xyz'[ax]}-axis. Call through() after positioning "
                f"the cutter.",
                source_location=loc,
            )

        # Detect coincident faces.
        min_coincident = abs(self_bb.min[ax] - parent_bb.min[ax]) < tol
        max_coincident = abs(self_bb.max[ax] - parent_bb.max[ax]) < tol

        if not min_coincident and not max_coincident:
            return self  # No coincident faces; no-op.

        # Compute extended bounds on the cut axis.
        new_min = (parent_bb.min[ax] - eps) if min_coincident else self_bb.min[ax]
        new_max = (parent_bb.max[ax] + eps) if max_coincident else self_bb.max[ax]

        orig_size = self_bb.max[ax] - self_bb.min[ax]
        if orig_size < 1e-10:
            return self  # Zero-thickness shape; can't scale.

        new_size = new_max - new_min
        scale_factor = new_size / orig_size

        # Scale along the cut axis from the cutter's center, then
        # translate to the new center.
        old_center = (self_bb.min[ax] + self_bb.max[ax]) / 2.0
        new_center = (new_min + new_max) / 2.0

        # To scale from center: translate to origin, scale, translate back.
        # Combined: new_pos = (old_pos - old_center) * scale + new_center
        # As a single translate after scale:
        #   delta = new_center - old_center * scale_factor
        delta = new_center - old_center * scale_factor

        factor = [1.0, 1.0, 1.0]
        factor[ax] = scale_factor
        offset = [0.0, 0.0, 0.0]
        offset[ax] = delta

        return Translate(
            v=(offset[0], offset[1], offset[2]),
            child=Scale(
                factor=(factor[0], factor[1], factor[2]),
                child=self,
                source_location=loc,
            ),
            source_location=loc,
        )

    def array(self, count: int, spacing: float, axis="x") -> "Node":
        """Evenly-spaced copies along an axis. Alias over `linear_copy`.

        `axis` accepts `"x"`, `"y"`, `"z"` (case-insensitive) or a 3-vector
        to array along an arbitrary direction. `spacing` may be negative.
        """
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValidationError(
                f"array: count must be a positive integer, got {count!r}",
                source_location=loc,
            )
        if isinstance(axis, str):
            axis_map = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
            key = axis.lower()
            if key not in axis_map:
                raise ValidationError(
                    f"array: axis must be 'x', 'y', 'z', or a 3-vector, got {axis!r}",
                    source_location=loc,
                )
            axis_vec = axis_map[key]
        else:
            from scadwright.api._vectors import _as_vec3
            axis_vec = _as_vec3(axis, name="array axis", default_scalar_broadcast=False)
        offset = (spacing * axis_vec[0], spacing * axis_vec[1], spacing * axis_vec[2])
        return self.linear_copy(offset=offset, n=count)

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

    # --- preview modifiers ---

    def _preview(self, mode: str, loc) -> "Node":
        from scadwright.ast.transforms import PreviewModifier
        return PreviewModifier(mode=mode, child=self, source_location=loc)

    def highlight(self) -> "Node":
        return self._preview("highlight", SourceLocation.from_caller())

    def background(self) -> "Node":
        return self._preview("background", SourceLocation.from_caller())

    def disable(self) -> "Node":
        return self._preview("disable", SourceLocation.from_caller())

    def only(self) -> "Node":
        return self._preview("only", SourceLocation.from_caller())

    # --- shorthand ---
    # Shorthand methods build wrappers directly rather than calling the chained
    # methods, so the captured source_location points at the user's call site
    # (e.g. `cube(10).up(5)` -> location is the `.up(5)` line), not the body of
    # the shorthand helper.

    def _translate_with_loc(self, v: tuple[float, float, float], loc) -> "Node":
        from scadwright.ast.transforms import Translate

        return Translate(v=v, child=self, source_location=loc)

    def up(self, d: float) -> "Node":
        return self._translate_with_loc((0.0, 0.0, float(d)), SourceLocation.from_caller())

    def down(self, d: float) -> "Node":
        return self._translate_with_loc((0.0, 0.0, -float(d)), SourceLocation.from_caller())

    def left(self, d: float) -> "Node":
        return self._translate_with_loc((-float(d), 0.0, 0.0), SourceLocation.from_caller())

    def right(self, d: float) -> "Node":
        return self._translate_with_loc((float(d), 0.0, 0.0), SourceLocation.from_caller())

    def forward(self, d: float) -> "Node":
        return self._translate_with_loc((0.0, float(d), 0.0), SourceLocation.from_caller())

    def back(self, d: float) -> "Node":
        return self._translate_with_loc((0.0, -float(d), 0.0), SourceLocation.from_caller())

    def flip(self, axis: str = "z") -> "Node":
        """Mirror across the given axis plane ("x", "y", or "z")."""
        from scadwright.ast.transforms import Mirror

        a = axis.lower()
        normal = (1.0 if a == "x" else 0.0, 1.0 if a == "y" else 0.0, 1.0 if a == "z" else 0.0)
        return Mirror(
            normal=normal, child=self, source_location=SourceLocation.from_caller()
        )

    def _color_with_loc(self, name: str, alpha: float, loc) -> "Node":
        from scadwright.ast.transforms import Color

        return Color(c=name, child=self, alpha=alpha, source_location=loc)

    # --- composition helpers ---

    def mirror_copy(
        self,
        v=None,
        *,
        normal=None,
        x: float = 0,
        y: float = 0,
        z: float = 0,
    ) -> "Node":
        """Keep the original AND add a mirrored copy. Returns union(self, self.mirror(v)).

        Accepts the mirror-plane normal as `v` (positional or first arg),
        `normal=` (readable alias — matches the standalone `mirror_copy`
        helper), or as component kwargs `x=, y=, z=`.
        """
        from scadwright.ast.csg import Union
        from scadwright.ast.transforms import Mirror
        from scadwright.api._vectors import _vec_from_args
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if normal is not None:
            if v is not None:
                raise ValidationError(
                    "mirror_copy: pass either positional `v` or `normal=`, not both",
                    source_location=loc,
                )
            v = normal
        mirror_normal = _vec_from_args(v, x, y, z, name="mirror_copy normal")
        mirrored = Mirror(normal=mirror_normal, child=self, source_location=loc)
        return Union(children=(self, mirrored), source_location=loc)

    def halve(
        self,
        v=None,
        *,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        size: float = 1e4,
    ) -> "Node":
        """Cut the shape down to one half (or quadrant/octant) along signed axes.

        Each nonzero component of `v` picks an axis and the side to keep:

            part.halve([0, 1, 0])        # keep +y, cut away -y
            part.halve([0, -1, 0])       # keep -y
            part.halve([1, 1, 0])        # keep the +x,+y quadrant
            part.halve(y=1)              # kwarg form

        Cut planes pass through the world origin on their axes; translate the
        part first to cut at a different plane. `size` is the edge length of
        each cutter cube; the default (1e4) is far larger than any practical
        part. Set `size` smaller only if the huge literal in the SCAD output
        bothers you.
        """
        from scadwright.ast.csg import Difference
        from scadwright.api._vectors import _vec_from_args
        from scadwright.api.factories import cube as _cube
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        v_vec = _vec_from_args(v, x, y, z, name="halve axis vector")
        if all(c == 0 for c in v_vec):
            raise ValidationError(
                "halve: at least one axis component must be nonzero",
                source_location=loc,
            )
        if size <= 0:
            raise ValidationError(
                f"halve size must be positive, got {size}",
                source_location=loc,
            )

        cutters = []
        for i, comp in enumerate(v_vec):
            if comp == 0:
                continue
            sign = 1.0 if comp > 0 else -1.0
            shift = [0.0, 0.0, 0.0]
            shift[i] = -sign * size / 2.0
            cutters.append(_cube([size, size, size], center=True).translate(shift))
        return Difference(children=(self, *cutters), source_location=loc)

    def rotate_copy(self, angle: float, n: int = 4, *, axis=(0.0, 0.0, 1.0)) -> "Node":
        """Rotate by `angle` degrees, n total copies (including original). Returns a union."""
        from scadwright.ast.csg import Union
        from scadwright.ast.transforms import Rotate
        from scadwright.api._vectors import _as_vec3

        loc = SourceLocation.from_caller()
        axis_vec = _as_vec3(axis, name="rotate_copy axis", default_scalar_broadcast=False)
        copies = [self]
        for i in range(1, int(n)):
            copies.append(
                Rotate(
                    child=self,
                    a=float(angle) * i,
                    v=axis_vec,
                    source_location=loc,
                )
            )
        return Union(children=tuple(copies), source_location=loc)

    def linear_copy(self, offset, n: int) -> "Node":
        """Translate by `offset` repeatedly; `n` total copies (including original)."""
        from scadwright.ast.csg import Union
        from scadwright.ast.transforms import Translate
        from scadwright.api._vectors import _as_vec3

        loc = SourceLocation.from_caller()
        off = _as_vec3(offset, name="linear_copy offset", default_scalar_broadcast=False)
        copies = [self]
        for i in range(1, int(n)):
            copies.append(
                Translate(
                    v=(off[0] * i, off[1] * i, off[2] * i),
                    child=self,
                    source_location=loc,
                )
            )
        return Union(children=tuple(copies), source_location=loc)

    def linear_extrude(
        self,
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
    ) -> "Node":
        from scadwright.ast.extrude import LinearExtrude
        from scadwright.api._validate import _require_resolution
        from scadwright.api._vectors import _as_vec2
        from scadwright.api.resolution import resolve as _resolve_res

        scale_val = float(scale) if isinstance(scale, (int, float)) else _as_vec2(scale)
        rfn, rfa, rfs = _resolve_res(fn, fa, fs)
        rfn, rfa, rfs = _require_resolution(rfn, rfa, rfs, context="linear_extrude")
        return LinearExtrude(
            child=self,
            height=float(height),
            center=bool(center),
            twist=float(twist),
            slices=slices,
            scale=scale_val,
            convexity=convexity,
            fn=rfn,
            fa=rfa,
            fs=rfs,
            source_location=SourceLocation.from_caller(),
        )

    def rotate_extrude(
        self,
        *,
        angle: float = 360.0,
        convexity: int | None = None,
        fn: float | None = None,
        fa: float | None = None,
        fs: float | None = None,
    ) -> "Node":
        from scadwright.ast.extrude import RotateExtrude
        from scadwright.api._validate import _require_resolution
        from scadwright.api.resolution import resolve as _resolve_res

        rfn, rfa, rfs = _resolve_res(fn, fa, fs)
        rfn, rfa, rfs = _require_resolution(rfn, rfa, rfs, context="rotate_extrude")
        return RotateExtrude(
            child=self,
            angle=float(angle),
            convexity=convexity,
            fn=rfn,
            fa=rfa,
            fs=rfs,
            source_location=SourceLocation.from_caller(),
        )


def _make_color_shorthand(color_name: str):
    def _color_method(self, alpha: float = 1.0) -> "Node":
        return self._color_with_loc(
            color_name, float(alpha), SourceLocation.from_caller()
        )

    _color_method.__name__ = color_name
    _color_method.__qualname__ = f"Node.{color_name}"
    _color_method.__doc__ = f"Apply the SVG/X11 color '{color_name}'."
    return _color_method


def _attach_svg_color_methods() -> None:
    from scadwright.colors import SVG_COLORS

    for _name in SVG_COLORS:
        setattr(Node, _name, _make_color_shorthand(_name))


_attach_svg_color_methods()
