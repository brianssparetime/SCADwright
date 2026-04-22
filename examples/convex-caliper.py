"""Convex caliper: slips over a measuring caliper's jaws so the caliper
can span a part whose outer faces are both concave -- the central
thickness of a biconcave lens, or the web of material left between two
opposing countersunk holes drilled from each side of a plate. A plain
jaw tip can't seat on either surface; the spherical-cap feeler nests
into the concavity so the caliper ends up reading the distance between
the feelers' outer domes.

One primitive (`cylinder`) and two shape-library Components
(`UShapeChannel` as the jaw clip, `SphericalCap` as the feeler tip)
stacked with `attach()`. The print variant lays a matching pair out
side-by-side for a single print job.

Run:
    python examples/convex-caliper.py
"""

from scadwright.boolops import union
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import SphericalCap, UShapeChannel


class ConvexCaliper(Design):
    @variant(fn=48, default=True)
    def print(self):                                    # user-chosen variant name
        # One head: U-channel clip + cylindrical neck + spherical-cap feeler.
        # Channel sized for a caliper jaw ~2.5 mm thick.
        clip = UShapeChannel(
            wall_thk=3,
            channel_length=30, channel_width=2.6, channel_height=10,
            n_shape=True, center="xy",
        )
        neck = cylinder(r=clip.bottom_width / 2, h=15).attach(clip)
        cap = SphericalCap(cap_dia=clip.bottom_width, cap_height=5).attach(neck)
        head = union(clip, neck, cap)
        # Two mirrored heads on the bed -- one slides onto each caliper jaw.
        spread = clip.outer_width / 2 + 10
        return union(head.right(spread), head.left(spread))


if __name__ == "__main__":
    run()
