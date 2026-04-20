"""4x4 transform matrices.

Pure-Python (no numpy dep). Used by sc.bbox() and sc.resolved_transform() to
walk the AST and compute world-space geometry.

Matrices are immutable, hashable, and composable. Construct via class methods:

    Matrix.identity()
    Matrix.translate(x, y, z)
    Matrix.rotate_x(deg) / rotate_y(deg) / rotate_z(deg)
    Matrix.rotate_euler(x, y, z)        # SCAD ZYX order
    Matrix.rotate_axis_angle(deg, axis)
    Matrix.scale(x, y, z)
    Matrix.mirror(normal)               # reflection across plane through origin

Compose with `@` or `.compose(other)`. Apply to a point with `.apply_point((x, y, z))`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

Vec3 = tuple[float, float, float]
Row = tuple[float, float, float, float]
Elements = tuple[Row, Row, Row, Row]


def _vec3(v) -> Vec3:
    a, b, c = v
    return (float(a), float(b), float(c))


@dataclass(frozen=True, slots=True)
class Matrix:
    """Immutable 4x4 transform matrix in row-major form."""

    elements: Elements

    # --- constructors ---

    @classmethod
    def identity(cls) -> "Matrix":
        return cls((
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def translate(cls, x: float, y: float = 0.0, z: float = 0.0) -> "Matrix":
        return cls((
            (1.0, 0.0, 0.0, float(x)),
            (0.0, 1.0, 0.0, float(y)),
            (0.0, 0.0, 1.0, float(z)),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def scale(cls, x: float, y: float | None = None, z: float | None = None) -> "Matrix":
        if y is None:
            y = x
        if z is None:
            z = x
        return cls((
            (float(x), 0.0, 0.0, 0.0),
            (0.0, float(y), 0.0, 0.0),
            (0.0, 0.0, float(z), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def rotate_x(cls, deg: float) -> "Matrix":
        c = math.cos(math.radians(deg))
        s = math.sin(math.radians(deg))
        return cls((
            (1.0, 0.0, 0.0, 0.0),
            (0.0, c, -s, 0.0),
            (0.0, s, c, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def rotate_y(cls, deg: float) -> "Matrix":
        c = math.cos(math.radians(deg))
        s = math.sin(math.radians(deg))
        return cls((
            (c, 0.0, s, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (-s, 0.0, c, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def rotate_z(cls, deg: float) -> "Matrix":
        c = math.cos(math.radians(deg))
        s = math.sin(math.radians(deg))
        return cls((
            (c, -s, 0.0, 0.0),
            (s, c, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def rotate_euler(cls, x: float, y: float, z: float) -> "Matrix":
        """SCAD's rotate([x,y,z]) — applies Rx, then Ry, then Rz (so the matrix is Rz @ Ry @ Rx)."""
        return cls.rotate_z(z) @ cls.rotate_y(y) @ cls.rotate_x(x)

    @classmethod
    def rotate_axis_angle(cls, deg: float, axis) -> "Matrix":
        """Rotate by `deg` around `axis` (3-vector). Rodrigues' formula."""
        ax, ay, az = _vec3(axis)
        norm = math.sqrt(ax * ax + ay * ay + az * az)
        if norm == 0:
            return cls.identity()
        ax, ay, az = ax / norm, ay / norm, az / norm
        c = math.cos(math.radians(deg))
        s = math.sin(math.radians(deg))
        t = 1.0 - c
        return cls((
            (t * ax * ax + c, t * ax * ay - s * az, t * ax * az + s * ay, 0.0),
            (t * ax * ay + s * az, t * ay * ay + c, t * ay * az - s * ax, 0.0),
            (t * ax * az - s * ay, t * ay * az + s * ax, t * az * az + c, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def mirror(cls, normal) -> "Matrix":
        """Reflection across plane through origin with given normal."""
        nx, ny, nz = _vec3(normal)
        norm = math.sqrt(nx * nx + ny * ny + nz * nz)
        if norm == 0:
            return cls.identity()
        nx, ny, nz = nx / norm, ny / norm, nz / norm
        return cls((
            (1 - 2 * nx * nx, -2 * nx * ny, -2 * nx * nz, 0.0),
            (-2 * nx * ny, 1 - 2 * ny * ny, -2 * ny * nz, 0.0),
            (-2 * nx * nz, -2 * ny * nz, 1 - 2 * nz * nz, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    # --- properties ---

    @property
    def translation(self) -> Vec3:
        """Return the (x, y, z) translation component."""
        return (self.elements[0][3], self.elements[1][3], self.elements[2][3])

    @property
    def is_identity(self) -> bool:
        return self == Matrix.identity()

    # --- operations ---

    def compose(self, other: "Matrix") -> "Matrix":
        """Return self @ other (apply other first, then self when used on a point)."""
        a = self.elements
        b = other.elements
        out = tuple(
            tuple(
                sum(a[i][k] * b[k][j] for k in range(4))
                for j in range(4)
            )
            for i in range(4)
        )
        return Matrix(out)  # type: ignore[arg-type]

    def __matmul__(self, other: "Matrix") -> "Matrix":
        return self.compose(other)

    def apply_point(self, p) -> Vec3:
        """Apply the matrix to a 3D point (uses homogeneous coordinates with w=1)."""
        x, y, z = _vec3(p)
        e = self.elements
        nx = e[0][0] * x + e[0][1] * y + e[0][2] * z + e[0][3]
        ny = e[1][0] * x + e[1][1] * y + e[1][2] * z + e[1][3]
        nz = e[2][0] * x + e[2][1] * y + e[2][2] * z + e[2][3]
        nw = e[3][0] * x + e[3][1] * y + e[3][2] * z + e[3][3]
        if nw != 1.0 and nw != 0.0:
            nx, ny, nz = nx / nw, ny / nw, nz / nw
        return (nx, ny, nz)

    def apply_vector(self, v) -> Vec3:
        """Apply the rotation/scale component only (no translation).

        Directions don't have a position — when you rotate a ship by 45°, the
        "forward" direction rotates but doesn't translate. Use this for
        direction vectors, surface normals, and axes.
        """
        x, y, z = _vec3(v)
        e = self.elements
        return (
            e[0][0] * x + e[0][1] * y + e[0][2] * z,
            e[1][0] * x + e[1][1] * y + e[1][2] * z,
            e[2][0] * x + e[2][1] * y + e[2][2] * z,
        )

    def invert(self, tol: float = 1e-9) -> "Matrix":
        """Compute the matrix inverse via Gauss-Jordan.

        Raises ValueError if `|determinant| <= tol`. This makes `invert(tol=t)`
        and `is_invertible(tol=t)` coordinate: gating on one with a given
        tolerance means the other will agree with the same tolerance.
        """
        det = self.determinant()
        if abs(det) <= tol:
            raise ValueError(
                f"matrix is singular (|det|={abs(det):g}, tol={tol}); "
                f"cannot invert:\n{self!r}"
            )
        # Build augmented [M | I] and reduce.
        n = 4
        a = [list(row) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(self.elements)]
        for col in range(n):
            # Pivot: find max abs in this column at or below `col`.
            pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
            if abs(a[pivot][col]) <= tol:
                # Should not happen given the det check above, but defensive —
                # catches numerical pathologies where det > tol but elimination
                # still produces a near-zero pivot.
                raise ValueError(
                    f"matrix has near-zero pivot during inversion "
                    f"(col={col}, pivot={a[pivot][col]:g}, tol={tol}):\n{self!r}"
                )
            a[col], a[pivot] = a[pivot], a[col]
            piv_val = a[col][col]
            a[col] = [v / piv_val for v in a[col]]
            for r in range(n):
                if r == col:
                    continue
                factor = a[r][col]
                if factor == 0:
                    continue
                a[r] = [a[r][k] - factor * a[col][k] for k in range(2 * n)]
        inv_rows = tuple(tuple(row[n:]) for row in a)
        return Matrix(inv_rows)  # type: ignore[arg-type]

    def determinant(self) -> float:
        """Determinant of the 4x4 matrix (direct cofactor expansion along row 0)."""
        e = self.elements
        def det3(m):
            return (
                m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
            )

        total = 0.0
        for c in range(4):
            minor = [
                [e[r][k] for k in range(4) if k != c]
                for r in range(1, 4)
            ]
            sign = -1.0 if c % 2 else 1.0
            total += sign * e[0][c] * det3(minor)
        return total

    def is_invertible(self, tol: float = 1e-9) -> bool:
        """True if |det| > tol. Cheaper sanity check than catching invert()'s raise."""
        return abs(self.determinant()) > tol

    # --- representation ---

    def __repr__(self) -> str:
        rows = "\n  ".join(
            "[" + ", ".join(f"{v:7.3f}" for v in row) + "]"
            for row in self.elements
        )
        return f"Matrix(\n  {rows}\n)"


def to_matrix(node) -> Matrix:
    """Return the Matrix corresponding to a transform AST node.

    Color returns identity (no spatial effect). Resize raises — its scale is
    bbox-dependent and is computed in the bbox visitor instead.
    """
    # Late imports to avoid cycles.
    from scadwright.ast.transforms import (
        Color,
        Mirror,
        MultMatrix,
        Resize,
        Rotate,
        Scale,
        Translate,
    )

    if isinstance(node, Translate):
        return Matrix.translate(*node.v)
    if isinstance(node, Rotate):
        if node.angles is not None:
            return Matrix.rotate_euler(*node.angles)
        return Matrix.rotate_axis_angle(node.a, node.v)
    if isinstance(node, Scale):
        return Matrix.scale(*node.factor)
    if isinstance(node, Mirror):
        return Matrix.mirror(node.normal)
    if isinstance(node, MultMatrix):
        return node.matrix
    if isinstance(node, Color):
        return Matrix.identity()
    if isinstance(node, Resize):
        raise ValueError(
            "Resize has no free-standing matrix; its scale is computed from the child bbox"
        )
    raise TypeError(f"to_matrix: unsupported node type {type(node).__name__}")
