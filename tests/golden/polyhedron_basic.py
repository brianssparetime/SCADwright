from scadwright.primitives import polyhedron
MODEL = polyhedron(
    points=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
    faces=[[0, 1, 2], [0, 2, 3], [0, 3, 1], [1, 3, 2]],
    convexity=2,
)
