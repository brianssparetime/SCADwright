from scadwright.primitives import cube
# Mode 2: in-face offset on a named face.
MODEL = cube([40, 30, 5]).add_text(
    label="LO", relief=0.4, on="top", font_size=4, at=(8, -5),
)
