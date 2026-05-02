"""Core-transform mixin for Node: translate, rotate, scale, mirror, color, resize, offset, multmatrix, projection.

These are the chained-method conveniences that wrap the receiver in a
single transform AST node. Pure functional construction — no shared
state, late imports for the AST dataclasses to keep
``ast/base.py``-side imports light. Each method captures the user's
call site via ``SourceLocation.from_caller`` so error messages from
downstream validators point at the chained call rather than this
mixin's body.
"""

from __future__ import annotations


class _TransformMixin:
    """Chained core transforms: translate, rotate, scale, mirror,
    color, resize, offset, multmatrix, projection.
    """

    def translate(self, v=None, *, x: float = 0, y: float = 0, z: float = 0) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Translate
        from scadwright.api._vectors import _vec_from_args

        v_vec = _vec_from_args(v, x, y, z, default=(0.0, 0.0, 0.0), allow_symbolic=True)
        return Translate(
            v=v_vec, child=self, source_location=SourceLocation.from_caller()
        )

    def rotate(
        self,
        a=None,
        v=None,
        *,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        angle=None,
        axis=None,
    ) -> "Node":
        """Euler form: rotate([x, y, z]) or rotate(x=..., y=..., z=...).

        Axis-angle form: rotate(a=angle, v=[ax, ay, az]). The more readable
        aliases `angle=` and `axis=` are also accepted; pair them consistently
        (either short-name pair or long-name pair).
        """
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Rotate
        from scadwright.api._vectors import _as_vec3
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        # Resolve angle/axis aliases. Collision = explicit error.
        if angle is not None:
            if a is not None:
                raise ValidationError(
                    "rotate: pass either `a=` or `angle=`, not both",
                    source_location=loc,
                )
            a = angle
        if axis is not None:
            if v is not None:
                raise ValidationError(
                    "rotate: pass either `v=` or `axis=`, not both",
                    source_location=loc,
                )
            v = axis

        from scadwright.animation import SymbolicExpr

        # Axis-angle: scalar `a` (or symbolic) + `v` axis vector.
        if v is not None and isinstance(a, (int, float, SymbolicExpr)) and not isinstance(a, bool):
            return Rotate(
                child=self,
                a=a if isinstance(a, SymbolicExpr) else float(a),
                v=_as_vec3(v, default_scalar_broadcast=False, allow_symbolic=True),
                source_location=loc,
            )
        # Euler via positional `a` (treated as angles vector) or kwargs x/y/z.
        if a is not None:
            angles = _as_vec3(a, default_scalar_broadcast=False, allow_symbolic=True)
        else:
            angles = tuple(
                v_ if isinstance(v_, SymbolicExpr) else float(v_)
                for v_ in (x, y, z)
            )
        return Rotate(child=self, angles=angles, source_location=loc)

    def scale(self, v=None, *, x: float = 1, y: float = 1, z: float = 1) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Scale
        from scadwright.api._vectors import _as_vec3
        from scadwright.animation import SymbolicExpr

        if v is not None:
            # Scalar scale broadcasts to all axes (SCAD accepts scale=2).
            factor = _as_vec3(v, default_scalar_broadcast=True, allow_symbolic=True)
        else:
            factor = tuple(
                v_ if isinstance(v_, SymbolicExpr) else float(v_)
                for v_ in (x, y, z)
            )
        return Scale(
            factor=factor, child=self, source_location=SourceLocation.from_caller()
        )

    def mirror(self, v=None, *, x: float = 0, y: float = 0, z: float = 0) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Mirror
        from scadwright.api._vectors import _vec_from_args

        normal = _vec_from_args(v, x, y, z, allow_symbolic=True)
        return Mirror(
            normal=normal, child=self, source_location=SourceLocation.from_caller()
        )

    def color(self, c, alpha: float = 1.0) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Color

        if isinstance(c, str):
            stored: str | tuple[float, ...] = c
        else:
            stored = tuple(float(x) for x in c)
        return Color(
            c=stored,
            child=self,
            alpha=float(alpha),
            source_location=SourceLocation.from_caller(),
        )

    def resize(self, v, *, auto=False) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Resize
        from scadwright.api._vectors import _as_vec3, _normalize_center

        new_size = _as_vec3(v, default_scalar_broadcast=False)
        # `auto` uses the same shape as center (bool, list, string).
        auto_tuple = _normalize_center(auto)
        return Resize(
            new_size=new_size,
            auto=auto_tuple,
            child=self,
            source_location=SourceLocation.from_caller(),
        )

    def offset(
        self,
        *,
        r: float | None = None,
        delta: float | None = None,
        chamfer: bool = False,
        fn: float | None = None,
        fa: float | None = None,
        fs: float | None = None,
    ) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Offset
        from scadwright.api._validate import _require_resolution
        from scadwright.api.resolution import resolve as _resolve_res
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if (r is None) == (delta is None):
            raise ValidationError(
                f"offset: pass exactly one of `r` or `delta`; got r={r!r}, delta={delta!r}",
                source_location=loc,
            )
        if r is not None and chamfer:
            raise ValidationError(
                "offset: chamfer only applies with delta, not r",
                source_location=loc,
            )
        fn, fa, fs = _resolve_res(fn, fa, fs)
        fn, fa, fs = _require_resolution(fn, fa, fs, context="offset")
        return Offset(
            child=self,
            r=float(r) if r is not None else None,
            delta=float(delta) if delta is not None else None,
            chamfer=bool(chamfer),
            fn=fn, fa=fa, fs=fs,
            source_location=loc,
        )

    def multmatrix(self, matrix) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import MultMatrix
        from scadwright.matrix import Matrix
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if isinstance(matrix, Matrix):
            m = matrix
        else:
            try:
                rows = [list(row) for row in matrix]
            except TypeError:
                raise ValidationError(
                    f"multmatrix: expected a Matrix or 4x4 / 4x3 list, got {type(matrix).__name__}",
                    source_location=loc,
                ) from None
            if len(rows) == 3 and all(len(r) == 4 for r in rows):
                # 3x4: pad last row [0, 0, 0, 1]
                rows.append([0.0, 0.0, 0.0, 1.0])
            if len(rows) == 4 and all(len(r) == 3 for r in rows):
                # 4x3: pad last column with [0, 0, 0, 1]
                rows = [r + [0.0 if i < 3 else 1.0] for i, r in enumerate(rows)]
            if len(rows) != 4 or not all(len(r) == 4 for r in rows):
                got = f"{len(rows)}x{len(rows[0]) if rows else 0}"
                raise ValidationError(
                    f"multmatrix: matrix must be 4x4 (or 3x4 / 4x3, which "
                    f"scadwright pads to 4x4); got {got}. If you have a 3x3 "
                    f"rotation matrix, pad manually: append [0, 0, 0] to each "
                    f"row and add a [0, 0, 0, 1] row at the bottom.",
                    source_location=loc,
                )
            m = Matrix(tuple(tuple(float(x) for x in r) for r in rows))
        return MultMatrix(matrix=m, child=self, source_location=loc)

    def projection(self, *, cut: bool = False) -> "Node":
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Projection

        return Projection(
            child=self,
            cut=bool(cut),
            source_location=SourceLocation.from_caller(),
        )
