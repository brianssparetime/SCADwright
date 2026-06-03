"""Pentacon Six print plate — both caps laid out for one print job.

`arrange_on_bed` drops the body cap and the rear lens cap flat onto the
print bed, side by side, so a single build covers the whole set. Each cap
already builds in its support-free orientation (flat face down), so the
layout just spaces them out, and it raises if they wouldn't fit the bed.

This is the file that pulls the other two together: it imports both caps,
which in turn read the shared `spec.py`.

Run:
    python examples/pentacon-six-mount/print_plate.py
"""

from scadwright.composition_helpers import arrange_on_bed
from scadwright.design import Design, run, variant

from body_cap import PentaconSixBodyCap
from rear_lens_cap import PentaconSixRearLensCap


class print_plate(Design):
    """Both caps arranged on the print bed as one build."""

    body = PentaconSixBodyCap()
    rear = PentaconSixRearLensCap()

    @variant(fn=96, default=True)
    def bed(self):
        return arrange_on_bed(self.body, self.rear)


if __name__ == "__main__":
    run()
