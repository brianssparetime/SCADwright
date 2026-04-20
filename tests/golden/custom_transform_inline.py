"""Golden: an inline custom transform (no SCAD module hoisting)."""

from scadwright.primitives import circle
from scadwright.transforms import transform
@transform("flat_inline", inline=True)
def _flat(node, *, height):
    return node.linear_extrude(height=height)


MODEL = circle(r=5, fn=12).flat_inline(height=3)
