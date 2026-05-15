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

    def with_bbox_from(self, source) -> "Node":
        """Override bbox and tight_bbox queries on this node to report
        ``source``'s extents instead of computing from the AST.

        This is a user assertion: the framework does NOT verify that
        ``source`` matches actual geometry. Reach for it when AST
        analysis can't tighten a Difference (the canonical case is a
        small cutter against a much larger host where you know the
        cutter doesn't move the bbox), and downstream consumers like
        ``pack_on_bed`` need the host's extents.

        ``source`` is a :class:`Node` (its bbox / tight_bbox is queried
        lazily, so spatial transforms applied after this call propagate
        to source's bbox just like they do to the child's) or a
        :class:`BBox` literal.
        """
        from scadwright.ast.transforms import WithBBox

        loc = SourceLocation.from_caller()
        return WithBBox(child=self, source=source, source_location=loc)

    def with_anchor(
        self,
        name: str,
        *,
        at: tuple[float, float, float],
        normal: tuple[float, float, float],
        kind: str = "planar",
        **surface_kwargs,
    ) -> "Node":
        """Attach a named anchor to this node without wrapping in a Component.

        ``at`` and ``normal`` are in this node's local frame. Spatial
        transforms applied after this call propagate to the anchor's
        position and normal, the same way custom Component anchors do.

        Curved-surface kwargs (``axis``, ``radius``, ``r1``/``r2``,
        ``length``, ``rim_radius``, ``axis_origin``, ``meridian_zero``,
        ``inner``, etc.) carry the geometry that ``add_text`` and the
        fuse bridge dispatch need on curved kinds.

        Custom anchors added this way override bbox-derived defaults of
        the same name. They are dropped by boolean operations (``union``,
        ``intersection``); ``difference`` propagates first-child anchors
        through with a cutter-bbox check.
        """
        from scadwright.anchor import Anchor
        from scadwright.ast.transforms import WithAnchor

        loc = SourceLocation.from_caller()
        a = Anchor(
            position=(float(at[0]), float(at[1]), float(at[2])),
            normal=(float(normal[0]), float(normal[1]), float(normal[2])),
            kind=kind,
            **surface_kwargs,
        )
        a._validate_geometry()
        return WithAnchor(
            child=self,
            anchor_name=str(name),
            anchor=a,
            source_location=loc,
        )

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

    def prefers_shift_at_anchor(self, anchor) -> bool:
        """Declare that ``attach(fuse=True)`` should pick ``bond='shift'``
        instead of ``bond='overlap'`` at this anchor.

        Returning ``True`` tells the smart cascade in ``attach(fuse=True)``
        to skip local extension (Tier 1 ``fuse_extend`` and Tier 2
        ``cross_section_extend``) and use the bilateral shift directly.
        The use case is Components whose cross-section at this anchor IS
        the entire outermost cross-section of the shape — annular caps
        (fillet rings, lids, washers) sized to match a host's outer
        diameter — where ``cross_section_extend`` produces a slab
        coplanar with the host's outer surface and the union has the
        same coplanarity it was supposed to fix.

        The shift mode accepts a bilateral ``eps`` drift on the opposite
        face. Override only when that drift is acceptable for this
        Component's design (typically yes for decorative caps; check
        before overriding if the opposite face is dimensionally
        critical).

        Default ``False`` (use the local-extension cascade as usual).
        Consulted only when the user passes ``fuse=True`` without an
        explicit ``bond=`` — explicit ``bond='overlap'`` or
        ``bond='shift'`` bypasses the hook.
        """
        return False

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

        **Cap-like Components.** When the cross-section at the anchor
        IS the entire outermost cross-section of the shape (annular
        caps on fillet rings, lids, washers sized to match a host's
        outer dimension), the resulting slab is coplanar with whatever
        the shape is attached to. The union has the same coplanarity
        ``attach(fuse=True)`` was meant to fix, just rotated 90° — no
        error, but no improvement over ``fuse=False`` either. For
        Components in that pattern, override
        :meth:`Node.prefers_shift_at_anchor` to return ``True`` at the
        affected anchor; the smart cascade will skip this method and
        use bilateral shift instead.
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
        *,
        using_anchor: str = "bottom",
        angle: float | str | None = None,
        at_radial: float | None = None,
        at_z: float | None = None,
        polar: float | None = None,
        orient: bool = False,
        fuse=None,        # sentinel-default; see _validate_attach_eps_bridge_kwargs
        bond: str | None = None,
        bridge: bool = False,
        eps: float | None = None,    # default from scadwright.tolerances.default_eps()
    ) -> "Node":
        """Position self so its ``using_anchor`` anchor touches ``other``'s
        ``on`` anchor.

        Both ``on`` and ``using_anchor`` accept friendly names
        (``"top"``, ``"bottom"``, ``"front"``, ``"back"``, ``"lside"``,
        ``"rside"``) or axis-sign names (``"+z"``, ``"-z"``, ``"+y"``,
        ``"-y"``, ``"+x"``, ``"-x"``). ``on`` selects the anchor on
        ``other``; ``using_anchor`` selects the anchor on self.

        By default, only translation is applied (self is moved so the anchor
        positions coincide). Pass ``orient=True`` to also rotate self so the
        two anchors' normals oppose each other (faces touching).

        Pass ``fuse=True`` to add a small overlap (``eps``, default
        0.01 mm) at a planar contact face, eliminating coincident-surface
        artifacts in unions::

            pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)

        For planar-to-planar attachments where ``self`` is a ``Cube``, a
        ``Cylinder`` planar cap, or a ``linear_extrude`` end-face
        (possibly wrapped in ``Translate`` / ``Rotate`` / ``Mirror``),
        the framework extends only the contact face by ``eps`` and
        leaves the opposite face at its declared position. Downstream
        operations that depend on exact coincidence (``through()``,
        further ``attach`` chains using the result's anchors) see
        the user-facing dimensions exactly. ``fuse=True`` on a
        convex-outer curved host raises — curved hosts use ``bridge=True``
        instead.

        Pass ``bridge=True`` to attach to a convex-outer curved surface
        (cylinder, cone, sphere) with a designed-in fill that merges the
        peg into the surface::

            peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True)

        The bridge is the peg's cross-section extruded by the analytical
        inscription depth, differenced with the host — a structural piece
        of material that fills the air gap between the peg's flat near-face
        and the curved surface. ``bridge=True`` alone produces a bridge
        flush with the peg's near-face; ``bridge=True, fuse=True`` adds an
        ``eps`` overlap on the peg side for a manifold-clean union with
        the peg. ``bridge=True`` on a planar host or concave-inner wall
        raises.

        ``attach()`` only attempts local extension on ``self``;
        ``other`` isn't part of the returned value, so extending it
        wouldn't help. For the symmetric case (extend whichever side
        qualifies), use the ``fuse(a, b, on=, using_anchor=)`` free
        function in ``scadwright.boolops``.

        Chain a directional helper for offset placement::

            peg.attach(plate).right(10)

        For angular placement on a cylindrical or conical surface, or on
        a cylinder cap at a rim position, pass ``angle=`` (degrees CCW
        from +X, or one of the friendly aliases ``"rside"`` / ``"back"``
        / ``"lside"`` / ``"front"`` / ``"+x"`` / ``"+y"`` / ``"-x"`` /
        ``"-y"``)::

            peg.attach(hub, on="outer_wall", angle=30)         # 30° meridian on the wall
            peg.attach(hub, on="top", angle=30)                # 30° on the top rim
            peg.attach(hub, on="top", angle=30, at_radial=12)  # 30°, 12 mm from cap center

        On cylindrical/conical anchors, ``angle=`` rotates the anchor's
        position and surface normal around the surface axis; on cones
        the surface normal is the actual slanted-wall normal (not the
        radial reference that ``add_text`` consumes). On planar cap
        anchors that carry rim_radius (``top``/``bottom`` of a cylinder
        or cone), ``angle=`` places the attachment at angular position
        on the cap; ``at_radial=`` overrides the default (the rim radius)
        for placements interior to the rim. Other anchor kinds reject
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

        For placement on a spherical surface, pass ``polar=`` (degrees
        from the north-pole / ``axis`` direction, range [0, 180]) and
        optionally ``angle=`` (azimuth, degrees CCW from the
        ``meridian_zero`` reference direction)::

            peg.attach(ball, on="surface", polar=30, angle=45)
            peg.attach(ball, on="surface", angle=90)        # polar defaults to 90 (equator)
            peg.attach(ball, on="surface", polar=0)         # north pole

        ``polar=`` is only valid on spherical anchors. ``at_z=`` and
        ``at_radial=`` raise on spherical anchors — sphere placement uses
        the polar/angle pair.

        For explicit control over the planar eps mechanism, pass ``bond=``
        instead of (or alongside) ``fuse=True``:

        - ``bond="overlap"`` — local face extension at a planar contact.
          Raises on curved hosts or non-planar contact.
        - ``bond="shift"`` — bilateral shift by ``eps`` along the contact
          normal. Always succeeds; the entire shape moves by eps.

        ``bond="..."`` implies ``fuse=True``; passing ``fuse=False`` with
        a bond raises. ``bond=`` and ``bridge=True`` don't combine — bond
        is for planar contacts; bridge is for curved hosts. ``fuse=True``
        without a bond tries ``overlap``; on a curved host it raises and
        points at ``bridge=True``.
        """
        from scadwright.anchor import anchors_from_bbox
        from scadwright.bbox import bbox as _bbox
        from scadwright.ast.transforms import Translate

        loc = SourceLocation.from_caller()

        if eps is None:
            from scadwright.api.tolerances import default_eps
            eps = default_eps()

        if angle is None and at_radial is not None:
            from scadwright.errors import ValidationError
            raise ValidationError(
                "attach: at_radial= requires angle=. Pass both for angular "
                "placement on a cap anchor.",
                source_location=loc,
            )

        other_anchor = _resolve_attach_anchor(other, on, "other", loc)

        # Spherical hosts: polar / angle (= azimuth) select a point on
        # the sphere's surface. polar=0 is the +axis pole; angle=0 is
        # the meridian_zero meridian. If only angle is supplied,
        # polar defaults to 90 (equator wrap).
        if polar is not None or (
            angle is not None and other_anchor.kind == "spherical"
        ):
            if at_z is not None:
                from scadwright.errors import ValidationError
                raise ValidationError(
                    "attach: at_z= is not valid on spherical anchors; use "
                    "polar= and angle= to select a point on the sphere.",
                    source_location=loc,
                )
            if at_radial is not None:
                from scadwright.errors import ValidationError
                raise ValidationError(
                    "attach: at_radial= is not valid on spherical anchors; use "
                    "polar= and angle= to select a point on the sphere.",
                    source_location=loc,
                )
            from scadwright.ast.placement import _apply_attach_polar
            polar_eff = polar if polar is not None else 90.0
            azimuth_eff = angle if angle is not None else 0.0
            other_anchor = _apply_attach_polar(
                other_anchor, polar_eff, azimuth_eff, loc
            )
            angle = None  # handled by polar dispatch; suppress angle path below

        if at_z is not None:
            from scadwright.ast.placement import _apply_attach_at_z
            other_anchor = _apply_attach_at_z(other_anchor, at_z, loc)
        if angle is not None:
            from scadwright.ast.placement import _apply_attach_angle
            other_anchor = _apply_attach_angle(other_anchor, angle, at_radial, loc)
        self_anchor = _resolve_attach_anchor(self, using_anchor, "self", loc)

        # Validate bond / fuse / bridge combination. bond='bridge' is
        # removed (use bridge=True); bond+bridge is a contradiction;
        # fuse=False+bond is a contradiction.
        from scadwright.ast.placement import (
            _dispatch_bridge,
            _dispatch_overlap,
            _dispatch_smart_cascade_attach,
            _shift_translate,
            _validate_attach_eps_bridge_kwargs,
        )
        bond, fuse, bridge = _validate_attach_eps_bridge_kwargs(
            bond, fuse, bridge, loc,
        )

        # Build working_self / working_self_anchor / bridge_self_anchor.
        # working_self_anchor is what bond='overlap' and bond='shift' use
        # (axis-aligned bbox face after orient rotation). bridge_self_anchor
        # is what bridge=True uses (the actual rotated anchor — needed
        # for the coaxial check).
        if not orient:
            working_self = self
            working_self_anchor = self_anchor
            bridge_self_anchor = self_anchor
        else:
            target_normal = tuple(-c for c in other_anchor.normal)
            working_self = _orient_child_to_normal(
                self, self_anchor.normal, target_normal, loc
            )
            rotated_anchors = anchors_from_bbox(_bbox(working_self))
            working_self_anchor = rotated_anchors.get(
                using_anchor, rotated_anchors.get("bottom", self_anchor)
            )
            if working_self is self:
                # No rotation needed; self_anchor stays as-is.
                bridge_self_anchor = self_anchor
            else:
                # bbox-derived anchors carry axis-aligned normals that
                # don't reflect the peg's post-rotation orientation. For
                # the bridge dispatch we need the at-anchor's actual
                # world-frame normal — apply the orient rotation
                # explicitly.
                from dataclasses import replace
                from scadwright.matrix import to_matrix
                import math as _math
                rot = to_matrix(working_self)
                new_pos = rot.apply_point(self_anchor.position)
                new_norm = rot.apply_vector(self_anchor.normal)
                nlen = _math.sqrt(sum(c * c for c in new_norm))
                if nlen > 0:
                    new_norm = tuple(c / nlen for c in new_norm)
                bridge_self_anchor = replace(
                    self_anchor, position=new_pos, normal=new_norm,
                )

        # disable_eps_fuse() collapses any requested eps to zero: fuse
        # becomes False (so bond= no longer offsets), and bridge's
        # peg-side -eps slice drops. Bridge geometry itself persists —
        # it's structural, not eps.
        from scadwright.api.fuse_mode import fuse_enabled
        eps_enabled = fuse_enabled()
        if not eps_enabled:
            fuse = False
            bond = None

        # Bridge wins when requested; the eps overlap on the peg side is
        # gated on fuse= (and disable_eps_fuse() above).
        if bridge:
            return _dispatch_bridge(
                working_self, bridge_self_anchor, other, other_anchor,
                eps, loc, eps_overlap=fuse,
            )

        # fuse=False, bond=None: exact contact, no eps geometry.
        if not fuse:
            return _shift_translate(
                working_self, working_self_anchor, other_anchor,
                with_eps=False, eps=eps, loc=loc,
            )

        # Explicit bond dispatch (planar paths only).
        if bond == "overlap":
            return _dispatch_overlap(
                working_self, working_self_anchor, other_anchor, eps, loc,
            )
        if bond == "shift":
            return _shift_translate(
                working_self, working_self_anchor, other_anchor,
                with_eps=True, eps=eps, loc=loc,
            )

        # bond=None and fuse=True: smart cascade (overlap or raise).
        return _dispatch_smart_cascade_attach(
            working_self, working_self_anchor,
            other, other_anchor, eps, loc,
        )

    def through(
        self,
        parent: "Node",
        *,
        axis: str | None = None,
        eps: float | None = None,
    ) -> "Node":
        """Extend the cutter through coincident faces of ``parent`` by ``eps``.

        Use on cutters before passing them to ``difference()`` to eliminate
        manual epsilon overlap::

            part = difference(box, cylinder(h=20, r=3).through(box))

        Extends the cutter through any face of ``parent`` that it touches
        (within floating-point tolerance) on the cut axis. Faces that
        aren't coincident are left alone.

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

        if eps is None:
            from scadwright.api.tolerances import default_eps
            eps = default_eps()

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

