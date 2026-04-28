from scadwright.primitives import cube
MODEL = cube([50, 30, 3]).add_text(
    label="LINE 1\nLINE 2", relief=0.5, on="top", font_size=5,
)
