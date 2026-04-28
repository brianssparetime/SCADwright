from scadwright.primitives import cylinder
MODEL = cylinder(h=20, r=10).add_text(
    label="BR", relief=0.4, on="outer_wall", font_size=4, meridian="front",
)
