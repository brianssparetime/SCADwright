from scadwright.primitives import cube
MODEL = cube([30, 20, 10]).add_text(
    label="v1.0", relief=-0.3, on="rside", font_size=4,
)
