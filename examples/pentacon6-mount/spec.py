"""Pentacon Six bayonet — the shared dimension contract.

This file is the single source of truth for the Pentacon Six (P6) lens
mount. Both `body_cap.py` and `rear_lens_cap.py` import this one `Spec`
and read their dimensions from it, so the two parts can never drift out
of agreement: change a number here and both caps follow. That is the
whole point of splitting a project across files around a shared `Spec`.

The P6 bayonet is a three-lug medium-format mount. The three lugs are
identical and spaced 120 degrees apart, so a lens (or a cap) seats in
any of three orientations. A small post on the lens, just in front of
the top lug, picks the one orientation that comes out level on film; a
cap doesn't care which way round it sits, so the caps simply leave room
for that post rather than reproducing it.

The numbers come from measuring a real mount and cross-checking against
published references and community 3D models. The lug width is the
softest of them (derived from a chord measurement); `fit_clearance` is
the knob to turn if a printed cap comes out tight or loose.
"""

from scadwright import Spec


class PentaconSixMount(Spec):
    equations = """
        # --- The bayonet itself (measured) ---
        # Bore the lens barrel passes through, i.e. the camera throat.
        bore_dia = 60.0

        # Three identical lugs, 120 degrees apart.
        lug_count = 3
        # Angular width of one lug (from a 19.5 mm chord at the lug tip).
        lug_span_deg = 35.0
        # How far each lug projects past the bore wall, and how thick it
        # is along the axis. Root sits at the bore (~60), tip 2.6 further
        # out (~65).
        lug_radial = 2.6
        lug_axial = 1.8

        # Turn, in degrees, from dropping the lugs in to fully locked.
        lock_twist_deg = 60.0

        # The lens's orientation post, just in front of the top lug.
        # The caps don't build a post; the bore simply clears it.
        pin_dia = 2.3
        pin_height = 2.0

        # --- Printed fit ---
        # Gap left between mating faces. PLA versus PETG and your
        # printer's calibration both shift the real fit; raise this if a
        # test cap binds, lower it if it rattles.
        fit_clearance = 0.20
        fit_clearance += 0.05      # adjustments idiom: a fit tweak you'd dial on a test print

        # --- Derived (read by both caps) ---
        bore_r = bore_dia / 2
        lug_tip_r = bore_r + lug_radial
        lug_step_deg = 360 / lug_count
    """
