from scadwright.primitives import cylinder
# Default text_curvature on a rim is "arc" (per-glyph wrap around the rim center).
MODEL = cylinder(h=10, r=15).add_text(
    label="MAX", relief=0.4, on="top", font_size=3,
)
