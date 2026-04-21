"""Composition/copy mixin for Node: mirror_copy, rotate_copy, linear_copy, halve, array."""

from __future__ import annotations


class _CompositionMixin:
    """Copy-and-combine helpers that wrap the receiver in a Union (or
    Difference for ``halve``) alongside derived copies of itself.
    """

    def mirror_copy(
        self,
        v=None,
        *,
        normal=None,
        x: float = 0,
        y: float = 0,
        z: float = 0,
    ) -> "Node":
        """Keep the original AND add a mirrored copy. Returns union(self, self.mirror(v)).

        Accepts the mirror-plane normal as `v` (positional or first arg),
        `normal=` (readable alias — matches the standalone `mirror_copy`
        helper), or as component kwargs `x=, y=, z=`.
        """
        from scadwright.api._vectors import _vec_from_args
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.csg import Union
        from scadwright.ast.transforms import Mirror
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if normal is not None:
            if v is not None:
                raise ValidationError(
                    "mirror_copy: pass either positional `v` or `normal=`, not both",
                    source_location=loc,
                )
            v = normal
        mirror_normal = _vec_from_args(v, x, y, z, name="mirror_copy normal")
        mirrored = Mirror(normal=mirror_normal, child=self, source_location=loc)
        return Union(children=(self, mirrored), source_location=loc)

    def halve(
        self,
        v=None,
        *,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        size: float = 1e4,
    ) -> "Node":
        """Cut the shape down to one half (or quadrant/octant) along signed axes.

        Each nonzero component of `v` picks an axis and the side to keep:

            part.halve([0, 1, 0])        # keep +y, cut away -y
            part.halve([0, -1, 0])       # keep -y
            part.halve([1, 1, 0])        # keep the +x,+y quadrant
            part.halve(y=1)              # kwarg form

        Cut planes pass through the world origin on their axes; translate the
        part first to cut at a different plane. `size` is the edge length of
        each cutter cube; the default (1e4) is far larger than any practical
        part. Set `size` smaller only if the huge literal in the SCAD output
        bothers you.
        """
        from scadwright.api._vectors import _vec_from_args
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.csg import Difference
        from scadwright.errors import ValidationError
        from scadwright.primitives import cube as _cube

        loc = SourceLocation.from_caller()
        v_vec = _vec_from_args(v, x, y, z, name="halve axis vector")
        if all(c == 0 for c in v_vec):
            raise ValidationError(
                "halve: at least one axis component must be nonzero",
                source_location=loc,
            )
        if size <= 0:
            raise ValidationError(
                f"halve size must be positive, got {size}",
                source_location=loc,
            )

        cutters = []
        for i, comp in enumerate(v_vec):
            if comp == 0:
                continue
            sign = 1.0 if comp > 0 else -1.0
            shift = [0.0, 0.0, 0.0]
            shift[i] = -sign * size / 2.0
            cutters.append(_cube([size, size, size], center=True).translate(shift))
        return Difference(children=(self, *cutters), source_location=loc)

    def rotate_copy(self, angle: float, n: int = 4, *, axis=(0.0, 0.0, 1.0)) -> "Node":
        """Rotate by `angle` degrees, n total copies (including original). Returns a union."""
        from scadwright.api._vectors import _as_vec3
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.csg import Union
        from scadwright.ast.transforms import Rotate

        loc = SourceLocation.from_caller()
        axis_vec = _as_vec3(axis, name="rotate_copy axis", default_scalar_broadcast=False)
        copies = [self]
        for i in range(1, int(n)):
            copies.append(
                Rotate(
                    child=self,
                    a=float(angle) * i,
                    v=axis_vec,
                    source_location=loc,
                )
            )
        return Union(children=tuple(copies), source_location=loc)

    def linear_copy(self, offset, n: int) -> "Node":
        """Translate by `offset` repeatedly; `n` total copies (including original)."""
        from scadwright.api._vectors import _as_vec3
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.csg import Union
        from scadwright.ast.transforms import Translate

        loc = SourceLocation.from_caller()
        off = _as_vec3(offset, name="linear_copy offset", default_scalar_broadcast=False)
        copies = [self]
        for i in range(1, int(n)):
            copies.append(
                Translate(
                    v=(off[0] * i, off[1] * i, off[2] * i),
                    child=self,
                    source_location=loc,
                )
            )
        return Union(children=tuple(copies), source_location=loc)

    def array(self, count: int, spacing: float, axis="x") -> "Node":
        """Evenly-spaced copies along an axis. Alias over `linear_copy`.

        `axis` accepts `"x"`, `"y"`, `"z"` (case-insensitive) or a 3-vector
        to array along an arbitrary direction. `spacing` may be negative.
        """
        from scadwright.ast.base import SourceLocation
        from scadwright.errors import ValidationError

        loc = SourceLocation.from_caller()
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValidationError(
                f"array: count must be a positive integer, got {count!r}",
                source_location=loc,
            )
        if isinstance(axis, str):
            axis_map = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
            key = axis.lower()
            if key not in axis_map:
                raise ValidationError(
                    f"array: axis must be 'x', 'y', 'z', or a 3-vector, got {axis!r}",
                    source_location=loc,
                )
            axis_vec = axis_map[key]
        else:
            from scadwright.api._vectors import _as_vec3
            axis_vec = _as_vec3(axis, name="array axis", default_scalar_broadcast=False)
        offset = (spacing * axis_vec[0], spacing * axis_vec[1], spacing * axis_vec[2])
        return self.linear_copy(offset=offset, n=count)
