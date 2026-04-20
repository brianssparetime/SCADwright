"""Text plate and embossed label Components."""

from __future__ import annotations

from scadwright.boolops import difference, union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.primitives import cube, text


class TextPlate(Component):
    """Rectangular plate with raised text.

    Text is centered on the plate surface and extruded upward by
    ``depth``. The plate dimensions are ``plate_w`` x ``plate_h`` x
    ``plate_thk``, centered in XY.
    """

    label = Param(str)
    equations = ["plate_w, plate_h, plate_thk, depth, font_size > 0"]
    font = Param(str, default="Liberation Sans")

    def build(self):
        plate = cube([self.plate_w, self.plate_h, self.plate_thk], center="xy")
        label_2d = text(
            self.label,
            size=self.font_size,
            font=self.font,
            halign="center",
            valign="center",
        )
        raised = linear_extrude(label_2d, height=self.depth).up(self.plate_thk)
        return union(plate, raised)


class EmbossedLabel(Component):
    """Rectangular plate with engraved (recessed) text.

    Text is centered on the plate surface and cut downward by ``depth``.
    """

    label = Param(str)
    equations = ["plate_w, plate_h, plate_thk, depth, font_size > 0"]
    font = Param(str, default="Liberation Sans")

    def build(self):
        plate = cube([self.plate_w, self.plate_h, self.plate_thk], center="xy")
        label_2d = text(
            self.label,
            size=self.font_size,
            font=self.font,
            halign="center",
            valign="center",
        )
        cutter = linear_extrude(label_2d, height=self.depth + 0.01).up(
            self.plate_thk - self.depth
        )
        return difference(plate, cutter)
