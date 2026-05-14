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

    def decompose_scale(self) -> Vec3:
        """Return (sx, sy, sz) — the column norms of the upper-left 3×3.

        For a matrix composed as translate ∘ rotate ∘ scale (uniform or
        non-uniform), this returns the scale factors. For a pure rotation
        or pure translation, returns (1, 1, 1). For a matrix containing a
        mirror, at least one scale will compose with the reflection in a
        way the column-norm formula can't see: callers needing to reject
        mirrors should check `determinant() > 0` separately.
        """
        e = self.elements
        sx = math.sqrt(e[0][0] * e[0][0] + e[1][0] * e[1][0] + e[2][0] * e[2][0])
        sy = math.sqrt(e[0][1] * e[0][1] + e[1][1] * e[1][1] + e[2][1] * e[2][1])
        sz = math.sqrt(e[0][2] * e[0][2] + e[1][2] * e[1][2] + e[2][2] * e[2][2])
        return (sx, sy, sz)

    def decompose_rotation_axis_angle(self) -> tuple[Vec3, float]:
        """Return (axis_unit, angle_degrees) after stripping per-axis scale.

        Builds a rotation matrix from the column-normalized upper-left 3×3,
        then converts to axis-angle. Assumes the matrix represents a proper
        rotation (possibly composed with scale) — callers should check
        `determinant() > 0` to reject mirrors before calling.

        - Identity rotation returns ((1, 0, 0), 0.0).
        - 180° rotation has a sign-ambiguous axis; this routine returns one
          of the two valid axes (the one whose largest component is
          non-negative). Callers needing a particular sign (e.g. the morph
          z-bias heuristic) must select after the fact.
        """
        sx, sy, sz = self.decompose_scale()
        if sx == 0 or sy == 0 or sz == 0:
            raise ValueError(
                f"matrix has a zero-length column; rotation is undefined.\n{self!r}"
            )
        e = self.elements
        r00, r01, r02 = e[0][0] / sx, e[0][1] / sy, e[0][2] / sz
        r10, r11, r12 = e[1][0] / sx, e[1][1] / sy, e[1][2] / sz
        r20, r21, r22 = e[2][0] / sx, e[2][1] / sy, e[2][2] / sz
        trace = r00 + r11 + r22
        cos_theta = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
        theta = math.acos(cos_theta)
        if theta < 1e-9:
            return ((1.0, 0.0, 0.0), 0.0)
        if theta > math.pi - 1e-6:
            # 180° rotation: sin(theta) ≈ 0, the standard formula divides by
            # zero. Use the diagonal: R = 2·axis⊗axis − I, so
            # axis[i]² = (R[i][i] + 1) / 2  and  axis[i]·axis[j] = R[i][j] / 2.
            # Pick the i with the largest diagonal to maximize precision in
            # the sqrt — the smallest-magnitude axis components fall out as
            # ratios of larger numbers.
            diags = (r00, r11, r22)
            i = max(range(3), key=lambda k: diags[k])
            sq = max(0.0, (diags[i] + 1.0) / 2.0)
            ax_i = math.sqrt(sq)
            row_i = (
                (r00, r01, r02),
                (r10, r11, r12),
                (r20, r21, r22),
            )[i]
            axis = [0.0, 0.0, 0.0]
            axis[i] = ax_i
            denom = 2.0 * ax_i if ax_i > 0 else 1.0
            for j in range(3):
                if j != i:
                    axis[j] = row_i[j] / denom
            norm = math.sqrt(sum(a * a for a in axis))
            if norm > 0:
                axis = [a / norm for a in axis]
            return ((axis[0], axis[1], axis[2]), 180.0)
        # General case.
        sin_theta = math.sin(theta)
        ax = (r21 - r12) / (2.0 * sin_theta)
        ay = (r02 - r20) / (2.0 * sin_theta)
        az = (r10 - r01) / (2.0 * sin_theta)
        return ((ax, ay, az), math.degrees(theta))

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
