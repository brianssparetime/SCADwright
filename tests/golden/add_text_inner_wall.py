from scadwright.shapes import Tube
MODEL = Tube(h=20, od=20, thk=2).add_text(
    label="IN", relief=0.4, on="inner_wall", font_size=4,
)
