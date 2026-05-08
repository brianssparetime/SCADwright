"""Node base, SourceLocation, capture toggle.

The Node class aggregates five per-concern mixins from sibling modules —
``_TransformMixin`` (translate/rotate/scale/mirror/color/resize/offset/
multmatrix/projection), ``_DirectionalMixin`` (up/down/…/flip),
``_DisplayMixin`` (preview modifiers + SVG color shorthands),
``_CompositionMixin`` (mirror_copy/halve/rotate_copy/linear_copy/array),
and ``_ExtrudeMixin`` (linear_extrude/rotate_extrude). The placement
helpers (``attach``, ``through``, ``center_bbox``) and the boolean
operators stay here. Helpers used by ``attach``/``through`` live in
``ast/placement.py``.
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
from scadwright.ast.node_transforms import _TransformMixin

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


# --- through() and attach() helpers live in ast/placement.py ---


from scadwright.ast.placement import (  # noqa: E402
    _detect_through_axis,
    _extend_through_faces,
    _orient_child_to_normal,
    _resolve_attach_anchor,
    _shift_for_anchors,
)


@dataclass(frozen=True)
class Node(
    _TransformMixin,
    _DirectionalMixin,
    _DisplayMixin,
    _CompositionMixin,
    _ExtrudeMixin,
):
    """Base for all AST nodes.

    source_location is kw_only so concrete subclasses can declare required positional
    fields without colliding with the default.

    Mixins add chained-method conveniences: ``_TransformMixin`` for the
    core transforms (translate/rotate/scale/mirror/color/resize/offset/
    multmatrix/projection); ``_DirectionalMixin`` for up/down/…/flip;
    ``_DisplayMixin`` for preview modifiers and SVG color shorthands;
    ``_CompositionMixin`` for mirror_copy/halve/rotate_copy/linear_copy/
    array; ``_ExtrudeMixin`` for linear_extrude/rotate_extrude. The
    placement methods (``attach``, ``through``, ``center_bbox``) and
    boolean operators stay on ``Node`` proper.
    """

    source_location: SourceLocation | None = field(default=None, kw_only=True)

    def __post_init__(self):
        """Recapture the resolution context onto direct-child Components.

        When a parent Node wraps a Component (the Component appears as a
        direct child via ``self.child`` or as an entry of ``self.children``),
        the wrap-time ambient ``(fn, fa, fs)`` context overwrites the
        Component's prior resolution snapshot. Wrap-time wins.

        Why this matters: a Component constructed at class-def time (no
        active context) and later wrapped inside a ``@variant(fn=...)``
        body or a user-managed ``with resolution(fn=...):`` block needs
        the wrap-time context to reach its ``build()`` — even if the
        build runs lazily, outside that block, during emit. The wrap's
        ``__post_init__`` is the moment that captures the user's intent.

        Concrete dataclass subclasses (Translate, Difference, etc.)
        inherit this hook automatically via the auto-generated
        ``__init__`` calling ``__post_init__`` after assigning fields.
        Components, which override ``__init__``, do their own initial
        capture in ``Component.__init__`` instead.
        """
        # Late import: ast.base is imported during component bootstrap.
        from scadwright.component.base import Component

        children = getattr(self, "children", None)
        if children:
            for c in children:
                if isinstance(c, Component):
                    c._capture_resolution_context()
        child = getattr(self, "child", None)
        if isinstance(child, Component):
            child._capture_resolution_context()

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

    # --- fuse extension ---

    def fuse_extend(self, anchor, eps: float):
        """Return self extended by ``eps`` along ``anchor``'s outward normal,
        or ``None`` if this shape doesn't support local extension.

        Used by ``attach(fuse=True)`` and the standalone ``fuse(...)`` to
        produce the small overlap that keeps a union manifold-clean
        without shifting the entire shape — the eps geometry is added
        locally at the interface, leaving the user-facing dimensions and
        anchors elsewhere on the shape unchanged.

        Default: ``None`` (this shape doesn't support local extension;
        the caller falls back to ``cross_section_extend`` for planar
        anchors, or the legacy shift for non-planar). Subclasses with a
        parametric extension lever (``Cube``, ``Cylinder`` planar caps,
        ``LinearExtrude`` end-faces) override.
        """
        return None

    def cross_section_extend(self, anchor, eps: float):
        """Generic local extension via projection + slab.

        Aligns ``anchor.position`` to the origin and ``anchor.normal``
        to +Z, takes ``projection(cut=True)`` to extract the 2D
        cross-section, ``linear_extrude``s by ``eps``, applies the
        inverse alignment, and unions the slab into self.

        The result has the contact face moved out by ``eps`` along the
        anchor normal while every other surface of the shape stays
        exactly where the user put it.

        Raises ``ValidationError`` if the anchor doesn't lie on the
        shape's outermost face along its normal (per the bbox-based
        check in ``_fuse_cross_section``). Returns ``None`` only if
        ``anchor.kind`` isn't ``"planar"`` — defensive; the cascade
        already gates on planarity.

        Subclasses can override to raise on shape-specific degenerate
        cases the bbox check misses (e.g., ``Cylinder`` with ``r=0``
        on the apex side).
        """
        if anchor.kind != "planar":
            return None
        from scadwright.ast._fuse_cross_section import (
            align_anchor_to_z_up,
            validate_planar_anchor_for_cross_section,
        )
        from scadwright.boolops import union as _union
        from scadwright.ast.transforms import MultMatrix

        validate_planar_anchor_for_cross_section(self, anchor)
        m = align_anchor_to_z_up(anchor)
        m_inv = m.invert()
        loc = self.source_location
        slab = (
            MultMatrix(matrix=m, child=self, source_location=loc)
            .projection(cut=True)
            .linear_extrude(height=eps)
        )
        slab = MultMatrix(matrix=m_inv, child=slab, source_location=loc)
        return _union(self, slab)

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
        angle: float | str | None = None,
        radius: float | None = None,
        at_z: float | None = None,
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

        Pass ``fuse=True`` to add a small overlap (``eps``, default
        0.01 mm) at the contact face, eliminating coincident-surface
        artifacts in unions::

            pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)

        For planar-to-planar fuses where ``self`` is a ``Cube``, a
        ``Cylinder`` planar cap, or a ``linear_extrude`` end-face
        (possibly wrapped in ``Translate`` / ``Rotate`` / ``Mirror``),
        the framework extends only the contact face by ``eps`` and
        leaves the opposite face at its declared position. Downstream
        operations that depend on exact coincidence (``through()``,
        further ``attach`` chains using the result's anchors) see
        the user-facing dimensions exactly. For other shapes — non-
        planar anchors, raw polyhedra, custom Components without
        intrinsic extension support — ``fuse=True`` falls back to
        translating ``self`` by ``eps`` along the contact normal,
        matching the legacy behavior.

        ``attach()`` only attempts local extension on ``self``;
        ``other`` isn't part of the returned value, so extending it
        wouldn't help. For the symmetric case (extend whichever side
        qualifies), use the ``fuse(a, b, on, at)`` free function in
        ``scadwright.boolops``.

        Chain a directional helper for offset placement::

            peg.attach(plate).right(10)

        For angular placement on a cylindrical or conical surface, or on
        a cylinder cap at a rim position, pass ``angle=`` (degrees CCW
        from +X, or one of the friendly aliases ``"rside"`` / ``"back"``
        / ``"lside"`` / ``"front"`` / ``"+x"`` / ``"+y"`` / ``"-x"`` /
        ``"-y"``)::

            peg.attach(hub, on="outer_wall", angle=30)        # 30° meridian on the wall
            peg.attach(hub, on="top", angle=30)               # 30° on the top rim
            peg.attach(hub, on="top", angle=30, radius=12)    # 30°, 12 mm from cap center

        On cylindrical/conical anchors, ``angle=`` rotates the anchor's
        position and surface normal around the surface axis; on cones
        the surface normal is the actual slanted-wall normal (not the
        radial reference that ``add_text`` consumes). On planar cap
        anchors that carry rim_radius (``top``/``bottom`` of a cylinder
        or cone), ``angle=`` places the attachment at angular position
        on the cap; ``radius=`` overrides the default rim radius for
        placements interior to the rim. Other anchor kinds reject
        ``angle=`` with a clear error.

        For axial placement along a cylindrical or conical wall, pass
        ``at_z=`` (mm offset from the anchor's reference axial position
        — mid-wall on ``outer_wall``)::

            peg.attach(hub, on="outer_wall", at_z=5)               # 5 mm above mid-wall, +X meridian
            peg.attach(hub, on="outer_wall", angle=30, at_z=5)     # 30° meridian, 5 mm above mid-wall

        ``at_z=`` works along the cylinder's actual axis line, so it's
        correct on translated and rotated hosts (``.up()`` after
        ``attach`` would only translate in world space). On a conical
        wall, the position is also adjusted radially so it stays on the
        slanted surface. ``at_z=`` is rejected on rim and other anchor
        kinds with a clear error.
        """
        from scadwright.anchor import anchors_from_bbox
        from scadwright.bbox import bbox as _bbox
        from scadwright.ast.transforms import Translate

        loc = SourceLocation.from_caller()

        if angle is None and radius is not None:
            from scadwright.errors import ValidationError
            raise ValidationError(
                "attach: radius= requires angle=. Pass both for angular "
                "placement on a cap anchor.",
                source_location=loc,
            )

        other_anchor = _resolve_attach_anchor(other, on, "other", loc)
        if at_z is not None:
            from scadwright.ast.placement import _apply_attach_at_z
            other_anchor = _apply_attach_at_z(other_anchor, at_z, loc)
        if angle is not None:
            from scadwright.ast.placement import _apply_attach_angle
            other_anchor = _apply_attach_angle(other_anchor, angle, radius, loc)
        self_anchor = _resolve_attach_anchor(self, at, "self", loc)

        # The scope-wide ``disable_eps_fuse()`` opt-out makes fuse=True
        # behave as fuse=False — no parametric extension, no shift. Read
        # the flag once here and use ``effective_fuse`` for the rest of
        # the dispatch.
        from scadwright.api.fuse_mode import fuse_enabled
        effective_fuse = fuse and fuse_enabled()

        if not orient:
            working_self = self
            working_self_anchor = self_anchor
            # bridge dispatch reads the at-anchor's actual normal (not a
            # bbox face) so curved-surface fuse can verify coaxial
            # alignment. With orient=False, that's just self_anchor.
            bridge_self_anchor = self_anchor
        else:
            # orient=True: rotate self so at-normal opposes face-normal.
            target_normal = tuple(-c for c in other_anchor.normal)
            working_self = _orient_child_to_normal(
                self, self_anchor.normal, target_normal, loc
            )
            rotated_anchors = anchors_from_bbox(_bbox(working_self))
            working_self_anchor = rotated_anchors.get(
                at, rotated_anchors.get("bottom", self_anchor)
            )
            if working_self is self:
                # No rotation needed (self_anchor.normal already pointed
                # at target_normal). At-anchor stays at its original
                # position and normal.
                bridge_self_anchor = self_anchor
            else:
                # bbox-derived anchors carry axis-aligned normals that
                # don't reflect the peg's orientation post-rotation. For
                # the bridge dispatch we need the at-anchor's actual
                # world-frame normal — apply the orient rotation matrix
                # to self_anchor explicitly.
                from scadwright.matrix import to_matrix
                from scadwright.anchor import Anchor as _Anchor
                import math as _math
                rot = to_matrix(working_self)
                new_pos = rot.apply_point(self_anchor.position)
                new_norm = rot.apply_vector(self_anchor.normal)
                nlen = _math.sqrt(sum(c * c for c in new_norm))
                if nlen > 0:
                    new_norm = tuple(c / nlen for c in new_norm)
                bridge_self_anchor = _Anchor(
                    position=new_pos,
                    normal=new_norm,
                    kind=self_anchor.kind,
                    surface_params=self_anchor.surface_params,
                )

        # Curved-host bridge dispatch. Convex-outer cylindrical / conical
        # / spherical surfaces fill the inscription gap with a bridge
        # piece (see ``_fuse_bridge``); concave-inner surfaces fall
        # through to legacy shift since the peg's corners naturally sit
        # inside host material.
        is_curved_host = other_anchor.kind in ("cylindrical", "conical", "spherical")
        is_inner = bool(other_anchor.surface_param("inner", default=False))
        if effective_fuse and is_curved_host and not is_inner:
            from scadwright.ast._fuse_bridge import (
                build_curved_bridge,
                coaxial_normals,
            )
            if not coaxial_normals(bridge_self_anchor.normal, other_anchor.normal):
                from scadwright.errors import ValidationError
                raise ValidationError(
                    f"attach(fuse=True) on a {other_anchor.kind} host "
                    f"requires coaxial normals (peg at-anchor "
                    f"anti-parallel to host on-anchor). Got peg normal "
                    f"{bridge_self_anchor.normal}, host normal "
                    f"{other_anchor.normal}. Pass orient=True, or align "
                    f"the peg manually so its at-anchor faces the host's "
                    f"on-anchor.",
                    source_location=loc,
                )
            unfused_shift = _shift_for_anchors(
                bridge_self_anchor, other_anchor, False, eps
            )
            bridge = build_curved_bridge(
                working_self,
                bridge_self_anchor,
                other,
                other_anchor,
                unfused_shift,
                eps,
            )
            if bridge is not None:
                from scadwright.boolops import union as _union
                placed_peg = Translate(
                    v=unfused_shift, child=working_self, source_location=loc
                )
                return _union(placed_peg, bridge)
            # No analytical depth available (host has no radius in
            # surface_params): fall through to legacy shift.

        # Planar-planar local extension. Curved hosts that bypassed the
        # bridge (concave inner, no analytical depth) fall through here,
        # but the planar gate excludes them.
        planar_fuse = (
            effective_fuse
            and working_self_anchor.kind == "planar"
            and other_anchor.kind == "planar"
        )
        if planar_fuse:
            extended = working_self.fuse_extend(working_self_anchor, eps)
            if extended is None:
                # Parametric path didn't apply; fall through to the
                # generic cross-section path. Raises on degenerate
                # contact (anchor not on the shape's outer face).
                extended = working_self.cross_section_extend(working_self_anchor, eps)
            if extended is not None:
                shift = _shift_for_anchors(working_self_anchor, other_anchor, False, eps)
                return Translate(v=shift, child=extended, source_location=loc)

        # Legacy shift fallback.
        shift = _shift_for_anchors(
            working_self_anchor, other_anchor, effective_fuse, eps
        )
        return Translate(v=shift, child=working_self, source_location=loc)

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
        spans the parent). Pass ``axis="x"``/``"y"``/``"z"`` to override
        with a world axis.

        For rotated cutters (angled drill holes, chamfered countersinks
        on non-vertical faces, draft-angled inserts), pass
        ``axis="local"`` (or ``"local_x"``/``"local_y"``/``"local_z"``)
        to interpret the cut axis in cutter-local space. ``through()``
        walks the cutter's outer rotations, projects the parent's bbox
        into cutter-local frame, and extends the leaf in local space —
        the rotates carry the extension correctly into world coordinates.
        ``axis="local"`` is a synonym for ``"local_z"`` (the cylinder
        convention).

        With ``axis=None`` and a rotated cutter, ``through()`` raises
        rather than guessing a local axis (cylinders use local_z, but
        cubes and Components don't have a canonical cut direction).

        Call ``through()`` after positioning the cutter (after any
        ``.up()``, ``.translate()``, ``.attach()`` calls).
        """
        from scadwright.ast._through_local import (
            extend_through_faces_local,
            has_rotation,
            is_local_axis,
        )
        from scadwright.bbox import bbox as _bbox

        loc = SourceLocation.from_caller()

        if is_local_axis(axis):
            return extend_through_faces_local(self, parent, axis, eps, loc)

        # World-axis path. Existing behavior preserved exactly for axis-aligned
        # cutters and for rotations that happen to preserve world-axis alignment
        # (90° permutations like FilletMask's `Rotate(0, 90, 0)`).
        self_bb = _bbox(self)
        parent_bb = _bbox(parent)
        ax = _detect_through_axis(self_bb, parent_bb, axis, loc)
        result = _extend_through_faces(self, self_bb, parent_bb, ax, eps, loc)

        # If the world-axis path found no coincident face AND the cutter has
        # a non-axis-permuting rotation in its transform stack, the user
        # almost certainly meant the local-axis path. Raise pointing them at
        # it. Cutters with axis-aligned bboxes (no rotation, or rotation that
        # permutes axes) preserve today's silent-no-op behavior.
        if axis is None and result is self and has_rotation(self):
            from scadwright.errors import ValidationError
            raise ValidationError(
                "through() found no coincident face on this cutter via the "
                "world-axis path, and the cutter has a non-axis-permuting "
                "rotation in its transform stack. Specify axis='local' (or "
                "'local_x' / 'local_y' / 'local_z') to indicate the cut "
                "direction in cutter-local space.",
                source_location=loc,
            )
        return result

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

