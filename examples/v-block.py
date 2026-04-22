"""Parametric V-block: a machinist cradle for round stock.

A rectangular block with a V-shaped groove cut along its length. Specify
any two of (angle, max_d, groove_depth) and the third solves. The groove
is sized so a rod of diameter max_d sits tangent to both V faces with
its center at the block's top surface.

Demonstrates (intermediate scope):
- Equations doing the heavy lifting: trig (sin, tan) relates groove
  angle, rod diameter, groove depth, and opening width -- specify any
  two primary vars, the rest are solved.
- Three concrete subclasses, each pinned by a different pair.
- No `setup()`, no `params=`, no explicit `Param` -- every dimension
  flows through `equations`.
- Print and display `@variant`s.

Run:
    python examples/v-block.py
    scadwright build examples/v-block.py --variant=display
"""

from scadwright import Component
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cube, cylinder, polygon


# =============================================================================
# REUSABLE: generic V-block
# =============================================================================


class VBlock(Component):
    """Rectangular block with a V-shaped groove along its length, sized to
    cradle cylindrical stock tangent to both groove faces.

    Specify any two of (angle, max_d, groove_depth); the third is solved
    by the trig relationship. `contact_width` (the opening width at the
    top of the groove) is always derived.
    """

    equations = [
        # V-groove trig -- any two of (angle, max_d, groove_depth) solve the third:
        "half_angle == angle / 2",
        "max_d == 2 * groove_depth * sin(half_angle * pi / 180)",
        "contact_width == 2 * groove_depth * tan(half_angle * pi / 180)",
        # positivity:
        "angle, max_d, groove_depth, contact_width, block_w, block_l, block_h > 0",
        # physical bounds:
        "angle < 180",
        "groove_depth < block_h",
        "contact_width < block_w",
    ]

    def build(self):                                       # framework hook: required; returns the shape
        body = cube([self.block_l, self.block_w, self.block_h], center="xy")
        cutter = (
            polygon([
                (self.groove_depth, 0),
                (0, self.contact_width / 2),
                (0, -self.contact_width / 2),
            ])
            .linear_extrude(height=self.block_l)
            .rotate([0, 90, 0])
            .translate([-self.block_l / 2, 0, self.block_h])
            .through(body, axis="x")                           # the cutter runs end-to-end along X
            .through(body, axis="z")                           # and opens flush with the top face
        )
        return difference(body, cutter)


# =============================================================================
# CONCRETE: three V-blocks, each specified via a different pair
# =============================================================================


class PipeVBlock90(VBlock):
    """90° V-block for pipe up to 1\" nominal OD.
    Pinned by (angle, max_d); groove_depth solves."""
    angle = 90
    max_d = 28
    block_l = 60
    block_w = 50
    block_h = 30


class ShaftVBlock60(VBlock):
    """Shallow 60° cradle for small shafts.
    Pinned by (angle, groove_depth); max_d solves."""
    angle = 60
    groove_depth = 10
    block_l = 70
    block_w = 40
    block_h = 22


class DeepCradleVBlock(VBlock):
    """Deep cradle for 35 mm rod held at a fixed depth.
    Pinned by (max_d, groove_depth); angle solves."""
    max_d = 35
    groove_depth = 22
    block_l = 80
    block_w = 60
    block_h = 35


# =============================================================================
# DESIGN
# =============================================================================


def _cradled_rod(block: VBlock, overhang: float = 30.0):
    """A darkgreen cylinder sized to `block.max_d` and laid in its V-groove,
    running along the block's length with its center at the top surface."""
    return (
        cylinder(h=block.block_l + overhang, d=block.max_d, center=True)
        .rotate([0, 90, 0])
        .up(block.block_h)
        .color("darkgreen")
    )


class VBlockSet(Design):
    pipe_block = PipeVBlock90()
    shaft_block = ShaftVBlock60()
    deep_block = DeepCradleVBlock()

    @variant(fn=64, default=True)
    def print(self):
        # Canonical print: one block per print bed. Switch to .shaft_block
        # or .deep_block to print the others.
        return self.pipe_block

    @variant(fn=64)
    def display(self):
        # Three blocks laid out along Y, each cradling a rod sized to its
        # own max_d. Showcases that three different (primary-var,
        # primary-var) pairs all yield a valid V-block via the same equations.
        blocks = (self.pipe_block, self.shaft_block, self.deep_block)
        pitch = max(b.block_w for b in blocks) + 25
        return union(*[
            union(b, _cradled_rod(b)).forward((i - 1) * pitch)
            for i, b in enumerate(blocks)
        ])


if __name__ == "__main__":
    run()
