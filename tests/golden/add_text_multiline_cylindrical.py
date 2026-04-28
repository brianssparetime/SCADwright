from scadwright.primitives import cylinder
MODEL = cylinder(h=30, r=12).add_text(
    label="AB\nCD", relief=0.4, on="outer_wall", font_size=4,
)
