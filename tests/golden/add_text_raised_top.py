from scadwright.primitives import cube
MODEL = cube([20, 20, 5]).add_text(
    label="HELLO", relief=0.5, on="top", font_size=8,
)
