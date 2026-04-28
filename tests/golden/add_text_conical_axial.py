from scadwright.shapes import Funnel
MODEL = Funnel(h=20, bot_od=20, top_od=10, thk=2).add_text(
    label="LO", relief=0.4, on="outer_wall", font_size=4,
)
