from scadwright import Component
from scadwright.primitives import cube
class _Plate(Component):
    def __init__(self):
        super().__init__()

    def build(self):
        return cube([20, 20, 2])


MODEL = _Plate().translate([0, 0, 5]).red()
