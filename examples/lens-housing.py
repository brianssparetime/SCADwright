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
from math import inf, radians, tan

from scadwright import Component, Param
from scadwright.boolops import difference, union
from scadwright.composition_helpers import mirror_copy
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import FilletRing, Funnel, Tube


# =============================================================================
# GLOBALS
# =============================================================================

EPS = 0.1   # z-lap to avoid coincident-face artifacts in CSG


# =============================================================================
# REUSABLE: generic Components, helpers, value types
# =============================================================================


# spacing is from flange (z=0) to element center; +z = toward object.
Element = namedtuple("Element", "dia edge_thk spacing")


class ElementHolder(Component):
    """Two-sided clamp around one Element, symmetric about the element
    center. Pre-construction queries are classmethods so housing code can
    pick each holder's OD before constructing the holder."""

    GRIP_DEPTH = 1.5
    GRIP_WIDTH = 1.0
    Z_SLOP = 0.5
    DIA_CLEAR = 0.4

    element = Param(Element)
    equations = ["od > 0"]

    @classmethod
    def face_z_for(cls, element, side):
        """Z of the holder's top face (side=+1) or bottom face (side=-1)."""
        half = (element.edge_thk + 2 * cls.GRIP_WIDTH) / 2
        return element.spacing + side * half

    @classmethod
    def is_constricted_for(cls, element):
        """True iff any part of the holder dips below the flange."""
        return cls.face_z_for(element, -1) < 0

    def build(self):                                       # framework hook: required; returns the shape
        e = self.element
        surround_h = 0.5 * e.edge_thk + self.Z_SLOP
        surround = Tube(h=surround_h, od=self.od, id=e.dia + self.DIA_CLEAR)
        gripper = Tube(
            h=0.5 * self.GRIP_WIDTH,
            od=self.od,
            id=e.dia - self.GRIP_DEPTH,
        ).up(surround_h - EPS)
        half = union(surround, gripper).flip("z")
        return mirror_copy(half, normal=[0, 0, 1]).up(e.spacing)


def trunc_fillet_ring(*, id, od, base_angle, slant="outwards", rim_width):
    """A `FilletRing` with its sharp apex chopped to a flat rim of
    `rim_width` radial width."""
    if rim_width <= 0:
        raise ValueError("rim_width must be > 0")
    if rim_width >= (od - id) / 2:
        raise ValueError("rim_width must be less than the ring's radial extent")
    base = FilletRing(id=id, od=od, base_angle=base_angle, slant=slant)
    h_full = tan(radians(base_angle)) * (od - id) / 2
    z_t = tan(radians(base_angle)) * ((od - id) / 2 - rim_width)
    chopper = cylinder(h=h_full - z_t + 2 * EPS, d=od + 2 * EPS).up(z_t)
    return difference(base, chopper)


class LensHousing(Component):
    """Generic lens barrel: lower recess + flange + upper housing (narrow
    or funnel-widened) + element holders + front fillet. Publishes outer
    dimensions and hood cone angle so a hood Component can mate without
    shared scope."""

    equations = [
        "lower_housing_od == lower_housing_id + barrel_thk",
        "hood_base_angle == 90 - fov_angle / 2",
        "lower_housing_od, lower_housing_id, lower_housing_len, barrel_thk > 0",
        "flange_flange_od, flange_flange_len, fov_angle, hood_base_angle > 0",
    ]
    elements = Param(tuple)

    def setup(self):                                       # framework hook: element iteration needs loops + conditionals
        unconstricted = [e for e in self.elements if not ElementHolder.is_constricted_for(e)]
        self.max_upper_ele_dia = max((e.dia for e in unconstricted), default=0.0)
        self.is_wide = self.max_upper_ele_dia > self.lower_housing_id
        self.expansion_funnel_len = (
            min(ElementHolder.face_z_for(e, -1) for e in unconstricted)
            if unconstricted else inf
        )
        self.upper_housing_len = max(ElementHolder.face_z_for(e, +1) for e in self.elements)
        self.upper_housing_od = (
            self.max_upper_ele_dia + self.barrel_thk
            if self.is_wide
            else self.flange_flange_od
        )

        self._validate_elements()

    def _validate_elements(self):
        clr = ElementHolder.DIA_CLEAR
        for i, e in enumerate(self.elements, start=1):
            if ElementHolder.is_constricted_for(e) and e.dia + clr > self.lower_housing_id:
                raise ValueError(
                    f"Element #{i} is constricted (spacing {e.spacing}mm dips into "
                    f"the throat) but its diameter {e.dia}mm + clearance "
                    f"{clr}mm exceeds the throat ID {self.lower_housing_id}mm."
                )

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
            yield Tube(
                h=self.upper_housing_len - funnel_len,
                od=self.max_upper_ele_dia + self.barrel_thk,
                id=self.max_upper_ele_dia,
            ).up(funnel_len)
        else:
            yield Tube(
                h=self.upper_housing_len, od=self.upper_housing_od, id=lower_id,
            )

        for e in self.elements:
            holder_od = lower_id if ElementHolder.is_constricted_for(e) else upper_id
            yield ElementHolder(element=e, od=holder_od)

        front_ele_dia = max(self.elements, key=lambda e: e.spacing).dia
        FRONT_FILLET_OFFSET = 5.0
        yield trunc_fillet_ring(
            id=front_ele_dia - ElementHolder.GRIP_DEPTH + FRONT_FILLET_OFFSET,
            od=self.upper_housing_od,
            base_angle=self.hood_base_angle,
            slant="inwards",
            rim_width=2,
        ).up(self.upper_housing_len - EPS)


class LensHood(Component):
    """Generic clip-on hood sized by a paired housing. `housing_upper_od`
    and `hood_base_angle` come from the housing instance at construction
    time; the rest are hood-specific."""

    equations = [
        "housing_upper_od, hood_base_angle, wall_thk, hood_length, coupler_overlap > 0",
        "hood_clr >= 0",
    ]

    def build(self):
        od_bot = self.housing_upper_od
        od_top = od_bot + 2 * self.hood_length * tan(radians(90 - self.hood_base_angle))
        hood = Funnel(
            h=self.hood_length, thk=self.wall_thk,
            bot_od=od_bot, top_od=od_top,
        ).up(self.coupler_overlap - EPS)

        coupler = Tube(
            h=self.coupler_overlap,
            id=self.housing_upper_od + self.hood_clr,
            thk=self.wall_thk,
        )

        top = union(hood, coupler).flip("z").up(self.hood_length + self.coupler_overlap)

        fillet = FilletRing(
            id=self.housing_upper_od + self.hood_clr,
            od=self.housing_upper_od + self.hood_clr + 2 * self.wall_thk,
            base_angle=63,
        ).flip("z").up(self.hood_length)

        return union(top, fillet)


def half_housing_splay(housing):
    """Cut in half and lay on its side for a section view."""
    return housing.halve([0, -1, 0]).rotate([270, 0, 0])


# =============================================================================
# CONCRETE: the specific M57 design
# =============================================================================


ELEMENTS = (
    Element(dia=40.0, edge_thk=5, spacing=18),
    Element(dia=50.0, edge_thk=2, spacing=-2),
    Element(dia=38.5, edge_thk=2, spacing=-12),
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
        spread = self.housing.upper_housing_od * 1.5
        return union(
            half_housing_splay(self.housing),
            half_housing_splay(self.housing).right(spread),
            self.hood.left(spread),
        )

    @variant(fn=48)
    def display(self):
        return union(
            self.housing,
            self.hood.flip("z").up(
                self.housing.upper_housing_len + self.hood.hood_length
            ),
        )


if __name__ == "__main__":
    run()
