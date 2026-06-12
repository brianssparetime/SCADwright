"""Pentacon Six bayonet — the shared dimension contract.

This file describes the geometry of the Pentacon Six (P6) lens
mount. 

Both `body_cap.py` and `rear_lens_cap.py` import this one `Spec`
and read their dimensions from it, so the two parts can never drift out
of agreement: change a number here and both caps follow. That is the
whole point of splitting a project across files around a shared `Spec`.

The P6 bayonet is a three-lug medium-format mount. The three lugs are
identical and spaced 120 degrees apart, so a lens (or a cap) seats in
any of three orientations. A small post on the lens, just in front of
the top lug, picks the one orientation that comes out level on film. However, a
cap doesn't care which way round it sits, so the caps simply leave room
for that post rather than reproducing it.

The numbers come from measuring a real mount.   The lug width is the
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

        # The lug's face nearest the lens shoulder sits this far below that
        # shoulder, the flat ring a rear cap's rim seats against. It fixes how
        # far the cap's rim stands above the seated lug.
        axial_lug_face_to_lens_shoulder = 2.0

        # The lens barrel runs on past the lugs toward the camera; its back
        # face stands this far beyond the lug plane. A rear cap has to sink
        # the lens this much deeper so the barrel clears the closed disc.
        barrel_past_lugs = 6.0

        # Turn, in degrees, from dropping the lugs in to fully locked.
        lock_twist_deg = 60.0

        # The lens's orientation post, a stub at the bore edge centered in
        # the barrel's reach past the lugs. A rear cap that sinks the lens
        # cuts a groove for this post to turn in; pin_dia (its width) and
        # pin_height (how far it stands off the barrel) size that groove.
        pin_dia = 2.4
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
