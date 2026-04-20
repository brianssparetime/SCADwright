"""Class-scope anchor declarations for Components.

Usage at class scope::

    from scadwright import Component, Param, anchor

    class Bracket(Component):
        w = Param(float, default=20)
        thk = Param(float, default=3)

        mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

``at`` accepts a string (expression evaluated against instance attributes
after params are set) or a tuple/list (used as-is).
"""

from __future__ import annotations


class AnchorDef:
    """Descriptor-like placeholder for a class-scope anchor declaration.

    Collected by ``Component.__init_subclass__`` and resolved to real
    ``Anchor`` objects during instance construction.
    """

    def __init__(self, at, normal):
        self.at = at
        self.normal = (float(normal[0]), float(normal[1]), float(normal[2]))
        self._name: str = ""

    def __set_name__(self, owner, name: str) -> None:
        self._name = name

    def resolve(self, instance) -> tuple[float, float, float]:
        """Evaluate ``at`` against *instance* and return a position 3-tuple."""
        at = self.at
        if isinstance(at, str):
            parts = [s.strip() for s in at.split(",")]
            if len(parts) != 3:
                from scadwright.errors import ValidationError

                raise ValidationError(
                    f"anchor {self._name!r}: at= string must have 3 "
                    f"comma-separated expressions, got {len(parts)}: {at!r}"
                )
            namespace = instance.__dict__
            vals = []
            for expr in parts:
                try:
                    vals.append(float(eval(expr, {"__builtins__": {}}, namespace)))
                except Exception as exc:
                    from scadwright.errors import ValidationError

                    raise ValidationError(
                        f"anchor {self._name!r}: cannot evaluate {expr!r}: {exc}"
                    ) from exc
            return (vals[0], vals[1], vals[2])
        else:
            return (float(at[0]), float(at[1]), float(at[2]))


def anchor(at, normal):
    """Declare a named anchor at class scope.

    Returns an ``AnchorDef`` placeholder that the Component framework
    collects and resolves after construction.

    ``at`` is the anchor position — either a 3-tuple/list of floats, or a
    string of three comma-separated Python expressions evaluated against
    the instance's attributes (e.g. ``"w/2, w/2, thk"``).

    ``normal`` is the outward-facing direction as a 3-tuple of floats.
    """
    return AnchorDef(at=at, normal=normal)
