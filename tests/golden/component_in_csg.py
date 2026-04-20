from scadwright import Component
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder
class _Block(Component):
    def __init__(self):
        super().__init__()

    def build(self):
        return cube([10, 10, 10], center=True)


MODEL = difference(
    _Block(),
    cylinder(h=12, r=2, center=True, fn=32),
)
