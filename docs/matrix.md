# Matrix

`Matrix` is scadwright's 4×4 transform type. It's what the bbox visitor uses internally to thread transforms through an AST, and it's exposed so you can use it directly when you need to compute placements, transform points, or compose transforms without building shapes.

You don't need Matrix for everyday modeling — `node.translate(...)`, `node.rotate(...)`, etc. handle the common cases. Reach for Matrix when:

- You need to know where a point on a shape ends up after a chain of transforms.
- You're computing an assembly placement (e.g., "put this flange where that bracket's mounting hole sits").
- You want to pre-compose several transforms and apply the result via [`multmatrix`](transformations.md#multmatrix).
- You're implementing a custom transform that needs to reason about its input geometry's frame.

Imports used on this page:

```python
from scadwright import Matrix
```

## Constructors

Every constructor returns a new `Matrix`; matrices are immutable.

```python
Matrix.identity()
Matrix.translate(x, y=0, z=0)
Matrix.scale(x, y=None, z=None)             # y/z default to x for uniform scale
Matrix.rotate_x(deg)                        # rotation around X (degrees)
Matrix.rotate_y(deg)
Matrix.rotate_z(deg)
Matrix.rotate_euler(x, y, z)                # SCAD's ZYX order: Rz @ Ry @ Rx
Matrix.rotate_axis_angle(deg, axis)         # rotate `deg` around a 3-vector axis
Matrix.mirror(normal)                       # reflection across plane through origin
```

Raw construction is also available if you need a specific matrix (shears, projective forms, etc.):

```python
shear = Matrix((
    (1, 0.5, 0, 0),
    (0, 1,   0, 0),
    (0, 0,   1, 0),
    (0, 0,   0, 1),
))
```

## Operations

### Composition

Compose two transforms with `@` (or the `compose` method). SCAD applies transforms right-to-left: `m = A @ B` means "apply B first, then A".

```python
m = Matrix.translate(10, 0, 0) @ Matrix.rotate_z(90)
# Applied to a point: rotate by 90° around Z, then translate by (10, 0, 0).
```

### Applying to points and vectors

```python
m.apply_point((1, 0, 0))    # transforms a position (translation included)
m.apply_vector((1, 0, 0))   # transforms a direction (translation ignored)
```

Use `apply_point` for positions (anchor points, feature centers). Use `apply_vector` for directions (axes, surface normals, "which way is +X pointing after this rotation?").

### Inversion

```python
m.invert(tol=1e-9)          # the inverse transform; raises ValueError if |det| <= tol
m.determinant()             # 4×4 determinant
m.is_invertible(tol=1e-9)   # True if |det| > tol
```

Inversion is useful for going from world-space back to a shape's local frame, or for undoing a placement.

If you gate inversion on `is_invertible`, pass the same `tol` to both so their decisions agree:

```python
if m.is_invertible(tol=1e-8):
    inv = m.invert(tol=1e-8)
```

With the default (`1e-9`) matched on both sides, `is_invertible()` and `invert()` always agree.

## Properties

```python
m.translation               # (x, y, z) translation component
m.is_identity               # True iff m == Matrix.identity()
m.elements                  # the raw row-major 4×4 tuple
```

## Practical examples

### Place a feature where another feature ended up

You have a plate with a mounting hole at local position `(5, 5, 0)`, and you've placed the plate with a translate+rotate. You want to put a peg exactly in the hole's world position, pointing outward along the plate's local +Z.

```python
placement = Matrix.translate(30, 10, 0) @ Matrix.rotate_z(45)

hole_local = (5, 5, 0)
hole_world = placement.apply_point(hole_local)
normal_world = placement.apply_vector((0, 0, 1))

peg = cylinder(h=10, r=2).translate(hole_world)
# …and if you wanted the peg to follow the plate's orientation, compose
# the same placement onto it instead of just translating.
```

### Rotate a direction without moving it

```python
rot = Matrix.rotate_z(30)
new_forward = rot.apply_vector((1, 0, 0))
# Rotated 30° around Z from +X.
```

### Invert a placement

```python
placement = Matrix.translate(5, 0, 0) @ Matrix.rotate_z(45)
world_point = (10, 10, 0)
local_point = placement.invert().apply_point(world_point)
# local_point is where (10, 10, 0) lives in the placed shape's own frame.
```

### Build a matrix from scratch and apply it to geometry

```python
from scadwright.primitives import cube

shear = Matrix((
    (1, 0.5, 0, 0),
    (0, 1,   0, 0),
    (0, 0,   1, 0),
    (0, 0,   0, 1),
))
sheared_cube = cube(10).multmatrix(shear)
```

See [`multmatrix`](transformations.md#multmatrix) for the AST-level form.

## Notes

- `Matrix` is a frozen dataclass: immutable, hashable, equatable.
- All operations return new matrices; none mutate.
- The `invert()` method uses Gauss-Jordan elimination and gates on `|determinant| > tol` upfront. Matrices with `|det| <= tol` raise `ValueError` with the determinant value, the tolerance used, and the matrix in the message.
