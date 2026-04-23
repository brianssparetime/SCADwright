"""Lens housing with stacked optical elements and a matching clip-on hood.

Demonstrates the recommended multi-part layout (see
docs/organizing_a_project.md): generic Components live in the REUSABLE
zone with flat Params (no project-specific defaults); the specific
design for an M57-throat camera lives in the CONCRETE zone as thin
subclasses that fill in measurements as class attributes.

Run:
    python examples/lens-housing.py                                  # print variant (default)
    scadwright build examples/lens-housing.py --variant=display        # assembled view
    scadwright build examples/lens-housing.py --variant=print          # split + spread for inspection
"""

from collections import namedtuple
from math import radians, tan

from scadwright import Component, Param, bbox
from scadwright.boolops import difference, union
from scadwright.composition_helpers import mirror_copy
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import FilletRing, Funnel, Tube


# =============================================================================
# REUSABLE: generic Components, helpers, value types
# =============================================================================


# spacing is from flange (z=0) to element center; +z = toward object.
# `face_z_top`, `face_z_bot`, `constricted`, `throat_dia_required` are
# precomputed by `element(...)` so the housing's equations-list can
# reference them without calling methods.
Element = namedtuple(
    "Element",
    "dia edge_thk spacing face_z_top face_z_bot constricted throat_dia_required",
)


class ElementHolder(Component):
    """Two-sided clamp around one Element, symmetric about the element center."""

    GRIP_DEPTH = 1.5
    GRIP_WIDTH = 1.0
    Z_SLOP = 0.5
    DIA_CLEAR = 0.4

    element = Param(Element)
    equations = ["od > 0"]

    def build(self):                                       # framework hook: required; returns the shape
        e = self.element
        surround_h = 0.5 * e.edge_thk + self.Z_SLOP
        surround = Tube(h=surround_h, od=self.od, id=e.dia + self.DIA_CLEAR)
        gripper = Tube(
            h=0.5 * self.GRIP_WIDTH,
            od=self.od,
            id=e.dia - self.GRIP_DEPTH,
        ).attach(surround, fuse=True)
        half = union(surround, gripper).flip("z")
        return mirror_copy(half, normal=[0, 0, 1]).up(e.spacing)


def element(*, dia, edge_thk, spacing):
    """Build an `Element` with geometric derived fields populated.

    Derived fields use `ElementHolder` grip geometry so the housing can reason
    about each element purely through attribute access (keeping the lens
    housing's equations list free of classmethod calls).
    """
    half = (edge_thk + 2 * ElementHolder.GRIP_WIDTH) / 2
    return Element(
        dia=dia, edge_thk=edge_thk, spacing=spacing,
        face_z_top=spacing + half,
        face_z_bot=spacing - half,
        constricted=(spacing - half) < 0,
        throat_dia_required=dia + ElementHolder.DIA_CLEAR,
    )


def trunc_fillet_ring(*, id, od, base_angle, slant="outwards", rim_width):
    """A `FilletRing` with its sharp apex chopped to a flat rim of
    `rim_width` radial width."""
    if rim_width <= 0:
        raise ValueError("rim_width must be > 0")
    if rim_width >= (od - id) / 2:
        raise ValueError("rim_width must be less than the ring's radial extent")
    # Radial eps: the chopper's outer cylindrical surface sits at d=od, same
    # as the FilletRing's outer wall. through() handles planar-bbox coplanar
    # faces but not cylinder-on-cylinder coincidence, so nudge the chopper
    # outward by a hair.
    eps = 0.01
    base = FilletRing(id=id, od=od, base_angle=base_angle, slant=slant)
    h_full = tan(radians(base_angle)) * (od - id) / 2
    z_t = tan(radians(base_angle)) * ((od - id) / 2 - rim_width)
    chopper = cylinder(h=h_full - z_t, d=od + 2 * eps).up(z_t).through(base, axis="z")
    return difference(base, chopper)


class LensHousing(Component):
    """Generic lens barrel: lower recess + flange + upper housing (narrow
    or funnel-widened) + element holders + front fillet. Publishes outer
    dimensions and hood cone angle so a hood Component can mate without
    shared scope."""

    FRONT_FILLET_OFFSET = 5.0   # aperture rim inset from the front element's grip ID

    equations = [
        "lower_housing_od == lower_housing_id + barrel_thk",
        "hood_base_angle == 90 - fov_angle / 2",
        "lower_housing_od, lower_housing_id, lower_housing_len, barrel_thk > 0",
        "flange_flange_od, flange_flange_len, fov_angle, hood_base_angle > 0",
        "unconstricted = tuple(e for e in elements if not e.constricted)",
        "max_upper_ele_dia = max((e.dia for e in unconstricted), default=0.0)",
        "is_wide = max_upper_ele_dia > lower_housing_id",
        "expansion_funnel_len = min((e.face_z_bot for e in unconstricted), default=inf)",
        "upper_housing_len = max(e.face_z_top for e in elements)",
        "upper_housing_od = (max_upper_ele_dia + barrel_thk) if is_wide else flange_flange_od",
        "all(not e.constricted or e.throat_dia_required <= lower_housing_id for e in elements)",
    ]
    elements = Param(tuple)

    def build(self):
        lower_id = self.lower_housing_id
        upper_id = self.max_upper_ele_dia if self.is_wide else lower_id

        yield Tube(
            h=self.lower_housing_len, od=self.lower_housing_od, id=lower_id,
        ).down(self.lower_housing_len)

        yield Tube(
            h=self.flange_flange_len, od=self.flange_flange_od, id=lower_id,
        )

        if self.is_wide:
            funnel_len = self.expansion_funnel_len
            yield Funnel(
                h=funnel_len, thk=self.barrel_thk / 2,
                bot_id=lower_id, top_id=self.max_upper_ele_dia,
            )
            upper = Tube(
                h=self.upper_housing_len - funnel_len,
                od=self.max_upper_ele_dia + self.barrel_thk,
                id=self.max_upper_ele_dia,
            ).up(funnel_len)
        else:
            upper = Tube(
                h=self.upper_housing_len, od=self.upper_housing_od, id=lower_id,
            )
        yield upper

        for e in self.elements:
            holder_od = lower_id if e.constricted else upper_id
            yield ElementHolder(element=e, od=holder_od)

        front_ele_dia = max(self.elements, key=lambda e: e.spacing).dia
        yield trunc_fillet_ring(
            id=front_ele_dia - ElementHolder.GRIP_DEPTH + self.FRONT_FILLET_OFFSET,
            od=self.upper_housing_od,
            base_angle=self.hood_base_angle,
            slant="inwards",
            rim_width=2,
        ).attach(upper, fuse=True)


class LensHood(Component):
    """Generic clip-on hood sized by a paired housing. `housing_upper_od`
    and `hood_base_angle` come from the housing instance at construction
    time; the rest are hood-specific. Built in its mounted orientation --
    coupler at z=0, funnel flaring upward; the print variant flips it."""

    equations = [
        "housing_upper_od, hood_base_angle, wall_thk, hood_length, coupler_overlap > 0",
        "hood_clr >= 0",
        "id_coupler == housing_upper_od + hood_clr",
        "od_coupler == id_coupler + 2 * wall_thk",
        "flare_od == housing_upper_od + 2 * hood_length * tan((90 - hood_base_angle) * pi / 180)",
    ]

    def build(self):                                       # framework hook: required; returns the shape
        coupler = Tube(
            h=self.coupler_overlap, id=self.id_coupler, thk=self.wall_thk,
        )
        yield coupler
        yield Funnel(
            h=self.hood_length, thk=self.wall_thk,
            bot_od=self.housing_upper_od, top_od=self.flare_od,
        ).attach(coupler, fuse=True)
        yield FilletRing(
            id=self.id_coupler, od=self.od_coupler,
            base_angle=63, slant="inwards",
        ).attach(coupler, fuse=True)


def half_housing_splay(housing):
    """Cut in half and lay on its side for a section view."""
    return housing.halve([0, -1, 0]).rotate([270, 0, 0])


# =============================================================================
# CONCRETE: the specific M57 design
# =============================================================================


ELEMENTS = (
    element(dia=40.0, edge_thk=5, spacing=18),
    element(dia=50.0, edge_thk=2, spacing=-2),
    element(dia=38.5, edge_thk=2, spacing=-12),
)


class M57LensHousing(LensHousing):
    lower_housing_od = 56.0
    lower_housing_len = 14.5
    barrel_thk = 2.0
    flange_flange_od = 59.0
    flange_flange_len = 5.0
    fov_angle = 57.0
    elements = ELEMENTS


class M57LensHood(LensHood):
    wall_thk = 2.0
    hood_clr = 0.4
    hood_length = 20.0
    coupler_overlap = 6.0


# =============================================================================
# DESIGN: shared parts + variant methods
# =============================================================================


class M57Lens(Design):
    housing = M57LensHousing()
    hood = M57LensHood(
        housing_upper_od=housing.upper_housing_od,
        hood_base_angle=housing.hood_base_angle,
    )

    @variant(fn=48, default=True)
    def print(self):
        # Bed-ready layout: two splayed housing halves + the inverted hood,
        # spaced with a uniform gap between adjacent parts and Y-aligned on
        # a shared baseline.
        half = half_housing_splay(self.housing)
        flipped_hood = self.hood.flip("z")   # wide flare on the print bed
        half_bb = bbox(half)
        hood_bb = bbox(flipped_hood)
        gap = self.housing.upper_housing_od   # ~one barrel-diameter of breathing room
        half_w = half_bb.size[0]
        hood_w = hood_bb.size[0]
        y_align = half_bb.center[1] - hood_bb.center[1]
        return union(
            half,
            half.right(half_w + gap),
            flipped_hood.translate(
                [-(hood_w + half_w) / 2 - gap, y_align, 0]
            ),
        )

    @variant(fn=48)
    def display(self):
        # Lift the hood one coupler_overlap above the true housing top (which
        # sits above upper_housing_len because of the front fillet ring) so
        # the housing's upper rim is visible between the two parts.
        housing_top_z = bbox(self.housing).max[2]
        gap = self.hood.coupler_overlap
        return union(
            self.housing,
            self.hood.up(housing_top_z + gap),
        )


if __name__ == "__main__":
    run()
