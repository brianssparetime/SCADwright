"""Tests for the add_text decoration transform."""

import logging

import pytest

from scadwright import Component, anchor
from scadwright.anchor import Anchor, get_node_anchors
from scadwright.ast.csg import Difference, Union
from scadwright.ast.custom import Custom
from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# --- Smoke + structural ---


def test_smoke_emits():
    p = cube([20, 20, 5]).add_text(label="HI", relief=0.5, on="top", font_size=8)
    scad = emit_str(p)
    assert "text" in scad
    assert '"HI"' in scad


def test_raised_produces_union():
    """Raised text wraps the host in a union with the extruded prism."""
    from scadwright._custom_transforms.base import get_transform

    p = cube([20, 20, 5]).add_text(label="X", relief=0.5, on="top", font_size=4)
    # The transform produces a Custom; expand it to inspect the geometry.
    assert isinstance(p, Custom)
    expanded = get_transform("add_text").expand(p.child, **p.kwargs_dict())
    assert isinstance(expanded, Union)


def test_inset_produces_difference():
    """Inset text wraps the host in a difference with the cutter prism."""
    from scadwright._custom_transforms.base import get_transform

    p = cube([20, 20, 5]).add_text(label="X", relief=-0.5, on="top", font_size=4)
    assert isinstance(p, Custom)
    expanded = get_transform("add_text").expand(p.child, **p.kwargs_dict())
    assert isinstance(expanded, Difference)


# --- All six bbox faces ---


@pytest.mark.parametrize(
    "face",
    ["top", "bottom", "front", "back", "lside", "rside"],
)
def test_each_standard_face(face):
    """A label can be placed on any of the six bbox-derived faces."""
    p = cube([20, 20, 10]).add_text(
        label="F", relief=0.3, on=face, font_size=3,
    )
    scad = emit_str(p)
    assert '"F"' in scad


# --- Custom anchor on a Component ---


class WithAnchor(Component):
    equations = ["w > 0"]
    badge = anchor(at="0, 0, w", normal=(0, 0, 1))

    def build(self):
        return cube([self.w, self.w, self.w])


def test_custom_anchor_on_component():
    c = WithAnchor(w=10)
    p = c.add_text(label="A", relief=0.4, on="badge", font_size=4)
    scad = emit_str(p)
    assert '"A"' in scad


# --- Anchor object placement ---


def test_anchor_object_placement():
    a = Anchor(position=(5, 5, 5), normal=(0, 0, 1))
    p = cube([20, 20, 5]).add_text(label="O", relief=0.3, on=a, font_size=4)
    scad = emit_str(p)
    assert '"O"' in scad


# --- at + normal ad-hoc placement ---


def test_at_normal_placement():
    p = cube([20, 20, 5]).add_text(
        label="P", relief=0.3, font_size=4, at=(10, 10, 5), normal=(0, 0, 1),
    )
    scad = emit_str(p)
    assert '"P"' in scad


def test_at_normal_normalizes_normal():
    """A non-unit normal is accepted and normalized."""
    p = cube([20, 20, 5]).add_text(
        label="N", relief=0.3, font_size=4, at=(0, 0, 5), normal=(0, 0, 5),
    )
    scad = emit_str(p)
    assert '"N"' in scad


# --- Validation errors ---


# add_text validation runs at expand time (the Custom is built lazily at
# construction; the transform body only fires when the emitter or the bbox
# visitor expands it). Tests below trigger expansion via emit_str so the
# validation errors surface where pytest.raises can catch them.


def test_unknown_anchor_name():
    with pytest.raises(ValidationError, match="no anchor 'bogus'"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, on="bogus", font_size=4,
        ))


def test_relief_zero_rejected():
    with pytest.raises(ValidationError, match="relief=0"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0, on="top", font_size=4,
        ))


def test_label_must_be_string():
    with pytest.raises(ValidationError, match="must be a string"):
        emit_str(cube([10, 10, 10]).add_text(
            label=42, relief=0.5, on="top", font_size=4,
        ))


def test_font_size_must_be_positive():
    with pytest.raises(ValidationError, match="positive number"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, on="top", font_size=0,
        ))
    with pytest.raises(ValidationError, match="positive number"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, on="top", font_size=-1,
        ))


def test_on_with_at_3tuple_rejected():
    """on= with at=(x, y, z) is the old conflict; now `at=` with `on=`
    must be a 2-tuple offset (mode 2). 3-tuple at= without on= is the
    ad-hoc path."""
    with pytest.raises(ValidationError, match="2-tuple"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, on="top", at=(1, 2, 3), font_size=4,
        ))


def test_at_without_normal_rejected():
    with pytest.raises(ValidationError, match="requires both"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, at=(1, 2, 3), font_size=4,
        ))


def test_normal_without_at_rejected():
    with pytest.raises(ValidationError, match="requires `at="):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, normal=(0, 0, 1), font_size=4,
        ))


def test_no_placement_rejected():
    with pytest.raises(ValidationError, match="must specify a placement"):
        emit_str(cube([10, 10, 10]).add_text(label="X", relief=0.5, font_size=4))


def test_zero_normal_rejected():
    with pytest.raises(ValidationError, match="non-zero"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, font_size=4, at=(0, 0, 5), normal=(0, 0, 0),
        ))


def test_unknown_surface_kind_raises():
    """A surface kind we don't know about falls through to a clear error."""
    weird_anchor = Anchor(
        position=(5, 0, 5),
        normal=(1, 0, 0),
        kind="spherical",
        surface_params=(),
    )
    with pytest.raises(ValidationError, match="not supported"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.5, font_size=4, on=weird_anchor,
        ))


# --- Pathway B: decoration preserves host anchors ---


def test_chain_two_labels():
    """Two add_text calls in a row: the second must see the host's anchors."""
    p = (
        cube([30, 30, 5])
        .add_text(label="A", relief=0.4, on="top", font_size=4)
        .add_text(label="B", relief=0.4, on="rside", font_size=4)
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


def test_attach_after_add_text_keeps_custom_anchor():
    """A Component's custom anchor must survive add_text so a later attach sees it."""
    host = WithAnchor(w=10)
    decorated = host.add_text(label="L", relief=0.3, on="top", font_size=4)
    anchors = get_node_anchors(decorated)
    assert "badge" in anchors, (
        "decoration transforms must preserve the host's custom anchors"
    )


def test_chain_uses_host_custom_anchor():
    """Chain: add_text on top, then add_text on the host's custom anchor."""
    host = WithAnchor(w=20)
    p = host.add_text(label="A", relief=0.3, on="top", font_size=4).add_text(
        label="B", relief=0.3, on="badge", font_size=4,
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


# --- Overflow warning ---


def test_overflow_warns(caplog):
    """A label too big for its face logs a warning."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        # 30-char label on a 10x10 face at size 8 → ~144 mm wide vs 10 mm face.
        emit_str(cube([10, 10, 5]).add_text(
            label="A" * 30, relief=0.5, on="top", font_size=8,
        ))
    assert any(
        "overflows face" in record.message for record in caplog.records
    ), "expected an overflow warning"


def test_no_overflow_warning_when_fits(caplog):
    """A label that fits doesn't log a warning."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cube([100, 100, 5]).add_text(
            label="OK", relief=0.5, on="top", font_size=4,
        ))
    assert not any(
        "overflows" in record.message for record in caplog.records
    )


def test_no_overflow_warning_for_adhoc(caplog):
    """Ad-hoc placement skips overflow check (no face dimensions known)."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cube([10, 10, 10]).add_text(
            label="A" * 50, relief=0.3, font_size=8,
            at=(0, 0, 5), normal=(0, 0, 1),
        ))
    assert not any(
        "overflows" in record.message for record in caplog.records
    )


# --- Patch B: warn on ad-hoc placement on a curved host ---


def test_adhoc_on_cube_no_curved_warning(caplog):
    """Ad-hoc placement on a cube doesn't warn — there's nothing to wrap around."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cube([20, 20, 20]).add_text(
            label="X", relief=0.3, font_size=4,
            at=(10, 10, 20), normal=(0, 0, 1),
        ))
    assert not any(
        "ad-hoc planar placement on a host with curved anchors" in r.message
        for r in caplog.records
    )


def test_adhoc_on_cylinder_warns(caplog):
    """Ad-hoc placement on a cylinder warns about the curved-anchor option."""
    from scadwright.primitives import cylinder

    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cylinder(h=20, r=10).add_text(
            label="X", relief=0.3, font_size=4,
            at=(10, 0, 10), normal=(1, 0, 0),
        ))
    assert any(
        "outer_wall" in r.message and "curved anchors" in r.message
        for r in caplog.records
    )


def test_adhoc_on_funnel_warns(caplog):
    """Same warning fires on conical hosts."""
    from scadwright.shapes import Funnel

    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(Funnel(h=20, bot_od=20, top_od=10, thk=2).add_text(
            label="X", relief=0.3, font_size=4,
            at=(7.5, 0, 10), normal=(1, 0, 0),
        ))
    assert any(
        "outer_wall" in r.message for r in caplog.records
    )


def test_adhoc_on_rotated_cylinder_still_warns(caplog):
    """Curved anchors propagate through transforms — the warning must too."""
    from scadwright.primitives import cylinder

    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cylinder(h=20, r=10).rotate([90, 0, 0]).add_text(
            label="X", relief=0.3, font_size=4,
            at=(10, 0, 0), normal=(1, 0, 0),
        ))
    assert any(
        "curved anchors" in r.message for r in caplog.records
    )


# --- Patch A: at=(u, v) offset on a named face ---


def _translate_in_scad(scad: str, count: int = 1) -> list[str]:
    """Return the first `count` translate-vector strings from a SCAD blob."""
    out = []
    for line in scad.split("\n"):
        if line.lstrip().startswith("translate("):
            out.append(line.strip())
            if len(out) >= count:
                return out
    return out


def test_at_offset_on_top_shifts_xy():
    """at=(u, v) on top face translates by +u in world X, +v in world Y."""
    no_offset = emit_str(cube([20, 20, 5]).add_text(
        label="X", relief=0.4, on="top", font_size=4,
    ))
    with_offset = emit_str(cube([20, 20, 5]).add_text(
        label="X", relief=0.4, on="top", font_size=4, at=(5, 3),
    ))
    # Default position (10, 10, ~5); offset (15, 13, ~5).
    assert "[10, 10," in no_offset
    assert "[15, 13," in with_offset


def test_at_offset_on_rside_shifts_yz():
    """at=(u, v) on rside: u=-Y axis, v=+Z axis."""
    scad = emit_str(cube([20, 20, 10]).add_text(
        label="X", relief=0.4, on="rside", font_size=4, at=(2, 1),
    ))
    # rside face center: (20, 10, 5). After at=(2,1) with (u=-Y, v=+Z) frame:
    # translate = (20 - eps, 10 + 2*-1, 5 + 1*1) = (19.99, 8, 6).
    assert "19.99, 8, 6" in scad


def test_at_offset_on_front_shifts_xz():
    """at=(u, v) on front: u=+X, v=+Z."""
    scad = emit_str(cube([20, 20, 10]).add_text(
        label="X", relief=0.4, on="front", font_size=4, at=(2, 1),
    ))
    # front face center: (10, 0, 5) with normal (0, -1, 0).
    # at=(2, 1) → (+2 X, +1 Z). Position: (10 + 2, 0 + eps, 5 + 1) = (12, 0.01, 6).
    assert "12, 0.01, 6" in scad


def test_at_offset_zero_is_noop():
    """at=(0, 0) produces the same emit as no `at`."""
    a = emit_str(cube([20, 20, 5]).add_text(
        label="X", relief=0.4, on="top", font_size=4,
    ))
    b = emit_str(cube([20, 20, 5]).add_text(
        label="X", relief=0.4, on="top", font_size=4, at=(0, 0),
    ))
    assert a == b


def test_at_offset_on_custom_anchor_uses_algorithmic_frame():
    """A Component custom anchor (not in the hardcoded face table) uses the
    deterministic fallback frame. The exact direction depends on the
    anchor's normal, but the offset must be perpendicular to it.
    """
    from scadwright import Component, anchor as anchor_def

    class WithCustom(Component):
        equations = ["w > 0"]
        # Tilted normal — not aligned to any cardinal axis.
        spot = anchor_def(
            at="w/2, w/2, w",
            normal=(0.0, 1.0, 1.0),  # equal Y/Z
        )
        def build(self):
            return cube([self.w, self.w, self.w])

    p = WithCustom(w=10).add_text(
        label="X", relief=0.4, on="spot", font_size=2, at=(3, 0),
    )
    # The placement should succeed without error; the exact offset depends
    # on the algorithmic frame, but emitted SCAD must contain the label.
    scad = emit_str(p)
    assert '"X"' in scad


def test_at_3tuple_with_on_string_rejected():
    """at=(x, y, z) only valid for ad-hoc; with on= it must be 2-tuple."""
    with pytest.raises(ValidationError, match="2-tuple"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.4, on="top", font_size=4, at=(1, 2, 3),
        ))


def test_at_2tuple_without_on_rejected():
    """at=(u, v) needs `on=` to define which face's plane."""
    with pytest.raises(ValidationError, match="ad-hoc placement requires"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.4, font_size=4, at=(1, 2),
        ))


def test_at_offset_on_cylindrical_anchor_rejected():
    """Curved walls use meridian/at_z, not at=(u, v)."""
    from scadwright.primitives import cylinder

    with pytest.raises(ValidationError, match="meridian"):
        emit_str(cylinder(h=20, r=10).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=4, at=(2, 1),
        ))


def test_at_offset_with_anchor_object():
    """on=Anchor + at=(u, v): uses the algorithmic tangent frame."""
    from scadwright.anchor import Anchor as _Anchor

    a = _Anchor(position=(0, 0, 5), normal=(0, 0, 1))
    p = cube([20, 20, 5]).add_text(
        label="X", relief=0.4, on=a, font_size=4, at=(3, 2),
    )
    scad = emit_str(p)
    assert '"X"' in scad


def test_at_offset_chains_through_decoration():
    """Offset placement preserves host anchors via the decoration framework."""
    p = (
        cube([20, 20, 5])
        .add_text(label="A", relief=0.4, on="top", font_size=4, at=(5, 0))
        .add_text(label="B", relief=0.4, on="rside", font_size=4)
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


# --- SCAD output sanity ---


def test_emitted_scad_contains_label_and_size():
    p = cube([40, 15, 2]).add_text(
        label="SCADwright", relief=0.5, on="top", font_size=8,
    )
    scad = emit_str(p)
    assert '"SCADwright"' in scad
    assert "size=8" in scad


def test_emitted_scad_passes_through_font():
    p = cube([40, 15, 2]).add_text(
        label="X", relief=0.3, on="top", font_size=5, font="DejaVu Sans",
    )
    scad = emit_str(p)
    assert "DejaVu Sans" in scad


def test_emitted_scad_uses_union_for_raised():
    p = cube([20, 20, 5]).add_text(
        label="R", relief=0.5, on="top", font_size=4,
    )
    scad = emit_str(p)
    assert "union" in scad


def test_emitted_scad_uses_difference_for_inset():
    p = cube([20, 20, 5]).add_text(
        label="I", relief=-0.5, on="top", font_size=4,
    )
    scad = emit_str(p)
    assert "difference" in scad
