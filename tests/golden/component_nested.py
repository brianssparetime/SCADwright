from scadwright import Component
from scadwright.boolops import union
from scadwright.primitives import cube, cylinder
class _Peg(Component):
    fn = 24

    def __init__(self, h):
        super().__init__()
        self.h = h

    def build(self):
        return cylinder(h=self.h, r=1)


class _Plate(Component):
    def __init__(self):
        super().__init__()

    def build(self):
        return union(
            cube([20, 20, 2]),
            _Peg(h=5).translate([5, 5, 2]),
            _Peg(h=5).translate([15, 15, 2]),
        )


MODEL = _Plate()
