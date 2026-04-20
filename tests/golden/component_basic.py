from scadwright import Component
from scadwright.primitives import cube
class _Box(Component):
    def __init__(self, size):
        super().__init__()
        self.size = size

    def build(self):
        return cube([self.size, self.size, self.size])


MODEL = _Box(size=10)
