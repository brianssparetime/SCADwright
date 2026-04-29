"""Parametric 3D-printable case for a single-board computer (Raspberry
Pi, Arduino, etc.). Base with standoffs at the PCB mount holes, port
cutouts matching the PCB's connectors, and a screw-on lid with vents.

A `PCBSpec` and `PortSpec` (plain namedtuples) carry all the board's
dimensions. Swapping one spec for another (an Arduino in place of the
Pi, for instance) produces a valid case with no Component changes.
Three custom transforms (`port_cutout`, `countersunk_hole`,
`vent_slot_array`) are applied once per hole, port, or vent. The lid
reads the base's dimensions off the base instance. `print_base` and
`print_lid` are bed-ready orientations; `display` shows the assembled
case with a stand-in PCB.

Run:
    python examples/electronics-case.py                          # default = display
    scadwright build examples/electronics-case.py --variant=print_base
    scadwright build examples/electronics-case.py --variant=print_lid
"""

from collections import namedtuple

from scadwright import Component, Param, bbox
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Tube, rounded_rect
from scadwright.transforms import transform


# =============================================================================
# REUSABLE: specs, custom transforms, generic Components
# =============================================================================


PortSpec = namedtuple("PortSpec", "face along z_above_pcb width height label", defaults=("",))

# `width`, `length`, `thk` are precomputed by `pcb_spec(...)` so the case's
# equations-list can reference them by name rather than indexing into `size`.
PCBSpec = namedtuple(
    "PCBSpec",
    "size width length thk mount_holes mount_hole_d ports component_clearance",
)


def pcb_spec(*, size, mount_holes, mount_hole_d, ports, component_clearance):
    """Build a PCBSpec with width/length/thk computed from `size`."""
    return PCBSpec(
        size=size, width=size[0], length=size[1], thk=size[2],
        mount_holes=mount_holes, mount_hole_d=mount_hole_d,
        ports=ports, component_clearance=component_clearance,
    )


PI4 = pcb_spec(
    size=(85.0, 56.0, 1.5),
    mount_holes=((3.5, 3.5), (61.0, 3.5), (3.5, 52.5), (61.0, 52.5)),
    mount_hole_d=2.7,
    ports=(
        PortSpec("-y", along=11.0, z_above_pcb=1.75, width=9.5,  height=4.0,  label="USB-C power"),
        PortSpec("-y", along=32.0, z_above_pcb=3.25, width=15.5, height=7.5,  label="HDMI0"),
        PortSpec("-y", along=45.5, z_above_pcb=3.25, width=15.5, height=7.5,  label="HDMI1"),
        PortSpec("-y", along=58.0, z_above_pcb=1.75, width=7.0,  height=4.0,  label="audio"),
        PortSpec("+x", along=9.0,  z_above_pcb=8.0,  width=13.5, height=17.0, label="USB 2.0 pair"),
        PortSpec("+x", along=27.0, z_above_pcb=8.0,  width=13.5, height=17.0, label="USB 3.0 pair"),
        PortSpec("+x", along=45.75, z_above_pcb=7.0, width=16.0, height=14.0, label="Ethernet"),
    ),
    component_clearance=20.0,
)


# --- custom transforms ---


@transform("port_cutout", inline=True)
def port_cutout(node, *, on, at_along, at_z, width, height, wall_thk):
    """Cut a rectangular port through one wall of a box-like node.

    The cutter is sized to `wall_thk` deep (matching the case wall) and
    positioned flush against the wall named by `on`. `through()` extends
    it outward so the boolean is clean without touching the opposite wall.
    """
    b = bbox(node)
    if on in ("+x", "-x"):
        cutter = cube([wall_thk, width, height])
        x = b.max[0] - wall_thk if on == "+x" else b.min[0]
        cutter = cutter.translate([x, at_along - width / 2, at_z - height / 2])
        cutter = cutter.through(node, axis="x")
    elif on in ("+y", "-y"):
        cutter = cube([width, wall_thk, height])
        y = b.max[1] - wall_thk if on == "+y" else b.min[1]
        cutter = cutter.translate([at_along - width / 2, y, at_z - height / 2])
        cutter = cutter.through(node, axis="y")
    else:
        raise ValueError(f"port_cutout: on must be +x/-x/+y/-y, got {on!r}")
    return difference(node, cutter)


@transform("countersunk_hole", inline=True)
def countersunk_hole(node, *, at, shaft_d, head_d, head_depth):
    """Drill a countersunk through-hole at `at=(x, y)` along the z-axis."""
    x, y = at
    b = bbox(node)
    shaft = (
        cylinder(h=b.size[2], d=shaft_d)
        .translate([x, y, b.min[2]])
        .through(node, axis="z")
    )
    head = (
        cylinder(h=head_depth, d=head_d)
        .translate([x, y, b.max[2] - head_depth])
        .through(node, axis="z")
    )
    return difference(node, shaft, head)


@transform("vent_slot_array", inline=True)
def vent_slot_array(node, *, count, slot_w, slot_l, spacing):
    """Cut an array of long thin ventilation slots through the +z face.

    Each slot is sized to the node's z-extent and extended via `through()`
    so the boolean is clean on both top and bottom faces.
    """
    b = bbox(node)
    half = (count - 1) * spacing / 2
    slots = union(*[
        cube([slot_w, slot_l, b.size[2]], center="xy")
            .translate([-half + i * spacing, 0, b.min[2]])
        for i in range(count)
    ]).through(node, axis="z")
    return difference(node, slots)


# --- generic Components ---


class CaseBase(Component):
    """Generic PCB case base: walled tray with standoffs at the PCB mount
    holes and port cutouts for each `PortSpec`. A lid can read the outer
    size, standoff positions, and `pcb_top_z` off this base to mate
    against.
    """

    pcb = Param(PCBSpec)
    equations = [
        "wall_thk, floor_thk, standoff_h, wall_h, corner_r, clearance, standoff_outer_d > 0",
        "inner_size = (pcb.width + 2 * clearance, pcb.length + 2 * clearance, standoff_h + pcb.component_clearance)",
        "outer_size = (inner_size[0] + 2 * wall_thk, inner_size[1] + 2 * wall_thk, floor_thk + wall_h)",
        "pcb_top_z = floor_thk + standoff_h + pcb.thk",
        "mount_positions = tuple((x - pcb.width / 2, y - pcb.length / 2) for (x, y) in pcb.mount_holes)",
    ]

    def build(self):                                       # framework hook: required; returns the shape
        w, l, h = self.outer_size
        iw, il, _ = self.inner_size

        outer = rounded_rect(w, l, r=self.corner_r).linear_extrude(height=h)
        inner_r = max(self.corner_r - self.wall_thk, 0.5)
        inner = (
            rounded_rect(iw, il, r=inner_r)
            .linear_extrude(height=h)
            .up(self.floor_thk)
        )
        shell = difference(outer, inner)

        standoffs = union(*[
            Tube(
                h=self.standoff_h,
                od=self.standoff_outer_d,
                id=self.pcb.mount_hole_d,
            ).translate([x, y, self.floor_thk])
            for (x, y) in self.mount_positions
        ])

        body = union(shell, standoffs)

        pcb = self.pcb
        for port in pcb.ports:
            if port.face in ("+y", "-y"):
                at_along = port.along - pcb.width / 2
            else:
                at_along = port.along - pcb.length / 2
            body = body.port_cutout(
                on=port.face,
                at_along=at_along,
                at_z=self.pcb_top_z + port.z_above_pcb,
                width=port.width,
                height=port.height,
                wall_thk=self.wall_thk,
            )

        return body


class CaseLid(Component):
    """Generic lid for a `CaseBase`. Reads the base's outer size, mount
    positions, and corner radius off the base instance; adds countersunk
    screw holes and a vent-slot array.
    """

    base = Param(CaseBase)
    equations = ["thk, vent_slot_w, vent_slot_l, vent_spacing, screw_d, screw_head_d, screw_head_depth > 0"]
    vent_count = Param(int, positive=True)

    def build(self):
        b = self.base
        bw, bl, _ = b.outer_size
        w, l, h = bw, bl, self.thk
        slab = rounded_rect(w, l, r=b.corner_r).linear_extrude(height=h)
        body = slab
        for at in b.mount_positions:
            body = body.countersunk_hole(
                at=at,
                shaft_d=self.screw_d,
                head_d=self.screw_head_d,
                head_depth=self.screw_head_depth,
            )
        body = body.vent_slot_array(
            count=self.vent_count,
            slot_w=self.vent_slot_w,
            slot_l=self.vent_slot_l,
            spacing=self.vent_spacing,
        )
        return body


# =============================================================================
# CONCRETE: the Pi 4 design
# =============================================================================


class Pi4Case(CaseBase):
    pcb = PI4
    wall_thk = 2.0
    floor_thk = 2.5
    standoff_h = 4.0
    wall_h = 25.0
    corner_r = 3.0
    clearance = 0.5
    standoff_outer_d = 6.0


class Pi4Lid(CaseLid):
    thk = 2.5
    vent_slot_w = 2.5
    vent_slot_l = 30.0
    vent_spacing = 5.0
    vent_count = 9
    screw_d = 2.7
    screw_head_d = 5.0
    screw_head_depth = 1.5


# =============================================================================
# DESIGN: assembly + variants
# =============================================================================


class ProjectBox(Design):
    base = Pi4Case()
    lid = Pi4Lid(base=base)

    @variant(fn=48)
    def print_base(self):
        return self.base

    @variant(fn=48)
    def print_lid(self):
        return self.lid.flip("z").up(self.lid.thk)

    @variant(fn=48, default=True)
    def display(self):
        spec = self.base.pcb
        pcb = (
            cube([spec.width, spec.length, spec.thk], center="xy")
            .up(self.base.floor_thk + self.base.standoff_h)
            .color("darkgreen")
        )
        return union(self.base, pcb, self.lid.attach(self.base, fuse=True))


if __name__ == "__main__":
    run()
