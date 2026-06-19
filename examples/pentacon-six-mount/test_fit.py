"""Throwaway fit testers for the Pentacon Six rear lens cap.

`rear_cap_tester` is the real `PentaconSixRearLensCap` with its closed
disc bored straight through, so the lens barrel passes clear out the
bottom. It prints faster (no solid disc) and lets you look down the bore
to watch the lugs and orientation post engage their channels.

`mount_ring_slice` is a 30° wedge of that same capless ring, cut through
the rotation channels so a cross-section of the bayonet stack is exposed
for eyeballing how the axial features line up.

Run:
    python examples/pentacon-six-mount/test_fit.py
    python examples/pentacon-six-mount/test_fit.py --variant=mount_ring_slice
"""

from scadwright.api.tolerances import default_eps
from scadwright.boolops import difference, intersection
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import Sector

from rear_lens_cap import PentaconSixRearLensCap


class test_fit(Design):
    """The rear cap, opened at the bottom for a quick fit print."""

    # Keep the original short well (no aperture-pin room) so the testers stay
    # quick to print; the real cap adds that depth.
    part = PentaconSixRearLensCap(aperture_pin_clear=0)

    def _capless_ring(self):
        # The rear cap with its closed disc (and the raised mark on it) bored
        # straight through, leaving an open ring you can sight down to watch
        # the lugs and orientation post engage their channels.
        eps = default_eps()
        cap = self.part
        opener = (
            cylinder(h=cap.disc_thk + cap.label_relief + 2 * eps, r=cap.bore_cut_r)
            .down(cap.label_relief + eps)
        )
        return difference(cap, opener)

    @variant(fn=96, default=True)
    def rear_cap_tester(self):                          # user-chosen variant name
        return self._capless_ring()

    @variant(fn=96)
    def mount_ring_slice(self):
        """A 1/12 (30°) wedge of the capless test ring, cut where both
        the lug rotation channel and the post groove cross the wedge
        fully, so each cut face shows a clean channel section under its
        retaining roof rather than the open entry slot.
        """
        cap = self.part
        # Lug 0 sits at 0°; its channels sweep the lock twist toward +theta.
        # The cap publishes its channel angles, so the cut tracks the model:
        # from where the entry slot ends to where the shorter channel (the
        # post groove) ends, both channels are present. Cut at the middle of
        # that zone.
        zone_start = cap.entry_half_deg
        zone_end = cap.post_half_deg + cap.spec.lock_twist_deg
        slice_center = (zone_start + zone_end) / 2
        half_slice = 360 / 12 / 2                        # 15°, one twelfth of the ring
        wedge = (
            Sector(
                r=cap.cap_od / 2 + 1.0,
                angles=(slice_center - half_slice, slice_center + half_slice),
            )
            .linear_extrude(height=cap.cap_h + 2.0)
            .down(1.0)
        )
        return intersection(self._capless_ring(), wedge)


if __name__ == "__main__":
    run()
