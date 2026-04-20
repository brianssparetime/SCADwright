from scadwright import Component
from scadwright.boolops import difference, union
from scadwright.primitives import cube, cylinder
class Widget(Component):
    fn = 48

    def __init__(self, width, height, hole_radius):
        super().__init__()
        self.width = width
        self.height = height
        self.hole_radius = hole_radius
        self.mount_points = [
            (width / 2 - 5, 0, 0),
            (-width / 2 + 5, 0, 0),
        ]

    def build(self):
        body = cube([self.width, self.width, self.height], center="xy")
        hole = cylinder(h=self.height + 2, r=self.hole_radius, center=True)
        return difference(
            body,
            *[hole.translate(list(p)) for p in self.mount_points],
        )


w = Widget(width=40, height=20, hole_radius=3)

MODEL = union(
    w,
    w.translate([50, 0, 0]).red(),
)
