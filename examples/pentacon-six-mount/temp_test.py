"""Throwaway fit tester for the Pentacon Six rear lens cap.

`rear_cap_tester` is the real `PentaconSixRearLensCap` with its closed
disc bored straight through, so the lens barrel passes clear out the
bottom. It prints faster (no solid disc) and lets you look down the bore
to watch the lugs and orientation post engage their channels.

Run:
    python examples/pentacon-six-mount/temp_test.py
"""

from scadwright.api.tolerances import default_eps
from scadwright.boolops import difference
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder

from rear_lens_cap import PentaconSixRearLensCap


class temp_test(Design):
    """The rear cap, opened at the bottom for a quick fit print."""

    # Keep the original short well (no aperture-pin room) so the tester stays
    # quick to print; the real cap adds that depth.
    part = PentaconSixRearLensCap(aperture_pin_clear=0)

    @variant(fn=96, default=True)
    def rear_cap_tester(self):                          # user-chosen variant name
        eps = default_eps()
        cap = self.part
        # Carry the bore down through the closed disc (and its raised mark),
        # so the bottom is open and the channels are visible.
        opener = (
            cylinder(h=cap.disc_thk + cap.label_relief + 2 * eps, r=cap.bore_cut_r)
            .down(cap.label_relief + eps)
        )
        return difference(cap, opener)


if __name__ == "__main__":
    run()
