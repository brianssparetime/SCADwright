"""The `mate` morph proves the two bayonet halves fit by mating them on screen.

Both caps read `spec.py`, so the body cap's lugs and the rear cap's channels
are cut to one pattern and must fit. Change a lug count in the spec and they
still mate.

The caps rise off the print bed, turn to face each other, slide together, and
the body cap twists into the lock.

The rear cap renders as a ghost, so the lugs show as they ride into its
channels; the body cap stays gold, so the lock reads as its `Pentacon Six`
mark turning.

The body cap's cover face stays a little proud of the rear cap's rim. That
gap is right: the halves fit through the bayonet but cap different things, so
their faces were never meant to meet. Don't close it.

Run:
    python examples/pentacon-six-mount/validation_morph.py        # static, locked
    scadwright morph examples/pentacon-six-mount/validation_morph.py mate out.apng
"""

from scadwright import morph
from scadwright.boolops import union
from scadwright.design import Design, run, variant

from spec import PentaconSixMount
from body_cap import PentaconSixBodyCap
from rear_lens_cap import PentaconSixRearLensCap

# --- pose constants ---
BED_SEP   = 44.0    # half-distance between the caps lying flat on the bed
STAND_Z   = 36.0    # height the parts rise to when stood up to face each other
FACE_GAP  = 28.0    # half-distance between them once faced off, before sliding in
SEAT_GAP  = 5.0     # half-distance once the lugs bottom on the channel floor
ALIGN     = 60.0    # extra body turn to line lugs up with the slots after the flip
TWIST     = PentaconSixMount.lock_twist_deg   # turn from lugs-in to locked


class validation_morph(Design):
    """The two bayonet halves, posed for a face-to-face mating animation."""

    body = PentaconSixBodyCap()
    rear = PentaconSixRearLensCap()

    @variant(fn=96)
    def spread(self):
        # Both caps flat on the bed, side by side, as they would print.
        return union(
            self.rear.left(BED_SEP).background(),
            self.body.right(BED_SEP).gold(),
        )

    @variant(fn=96)
    def faced(self):
        # Both stand up and turn to face each other across a gap: the rear
        # cap's opening points one way, the body cap's lugs point back at it.
        return union(
            self.rear.rotate([0, 90, 0]).up(STAND_Z).left(FACE_GAP).background(),
            self.body.rotate([0, 0, ALIGN]).rotate([0, -90, 0]).up(STAND_Z).right(FACE_GAP).gold(),
        )

    @variant(fn=96)
    def mated(self):
        # Slide together so the lugs run straight down the entry slots to
        # the channel floor, still lined up with the slots (no turn yet).
        return union(
            self.rear.rotate([0, 90, 0]).up(STAND_Z).left(SEAT_GAP).background(),
            self.body.rotate([0, 0, ALIGN]).rotate([0, -90, 0]).up(STAND_Z).right(SEAT_GAP).gold(),
        )

    def _locked(self):
        # Body cap turned `TWIST` degrees about the bayonet axis (no axial
        # move), so the lugs sweep from the entry slots under the roof into
        # the rotation channels.
        return union(
            self.rear.rotate([0, 90, 0]).up(STAND_Z).left(SEAT_GAP).background(),
            self.body.rotate([0, 0, ALIGN + TWIST]).rotate([0, -90, 0]).up(STAND_Z).right(SEAT_GAP).gold(),
        )

    @variant(fn=96, default=True, rotation=[62, 0, 28], target=[0, 0, 24], distance=340)
    def locked(self):
        return self._locked()

    @variant(fn=96, rotation=[62, 0, 28], target=[0, 0, 24], distance=340)
    def held(self):
        # Same pose as `locked`. A zero-motion leg gets the minimum
        # timeline slice, so the lock holds for a moment before the loop
        # reverses.
        # The morph reads its fixed camera from this final stage's
        # viewpoint, so it must carry one or OpenSCAD auto-frames every
        # frame and the camera appears to pump in and out.
        return self._locked()

    mate = morph(
        stages=["spread", "faced", "mated", "locked", "held"],
        simultaneous=True,
        pingpong=True,
    )


if __name__ == "__main__":
    run()
