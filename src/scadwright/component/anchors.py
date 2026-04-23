"""Class-scope anchor declarations for Components.

Usage at class scope::

    from scadwright import Component, anchor

    class Bracket(Component):
        equations = ["w, thk > 0"]

        mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

``at`` and ``normal`` each accept either a literal 3-tuple or a string of
three comma-separated Python expressions evaluated against the instance's
attributes after params are set. The string form covers conditional cases
the tuple form can't (e.g. a normal that flips on a boolean Param).
"""

from __future__ import annotations


def _eval_3tuple(spec, instance, anchor_name: str, role: str) -> tuple[float, float, float]:
    """Resolve ``spec`` (string of 3 comma-separated expressions or a literal
    3-tuple) into a concrete 3-tuple of floats against *instance*.

    Comma precedence note: in ``"0, 0, -1 if cond else 1"`` the conditional
    binds tighter than the comma, so this parses as
    ``(0, 0, (-1 if cond else 1))`` — exactly what's wanted for a single
    flippable component. Wrap any wider conditional in parentheses if the
    intent is to swap the whole tuple.
    """
    if isinstance(spec, str):
        parts = [s.strip() for s in spec.split(",")]
        if len(parts) != 3:
            from scadwright.errors import ValidationError

            raise ValidationError(
                f"anchor {anchor_name!r}: {role}= string must have 3 "
                f"comma-separated expressions, got {len(parts)}: {spec!r}"
            )
        namespace = instance.__dict__
        vals = []
        for expr in parts:
            try:
                vals.append(float(eval(expr, {"__builtins__": {}}, namespace)))
            except Exception as exc:
                from scadwright.errors import ValidationError

                raise ValidationError(
                    f"anchor {anchor_name!r}: cannot evaluate {role}= "
                    f"{expr!r}: {exc}"
                ) from exc
        return (vals[0], vals[1], vals[2])
    return (float(spec[0]), float(spec[1]), float(spec[2]))


class AnchorDef:
    """Descriptor-like placeholder for a class-scope anchor declaration.

    Collected by ``Component.__init_subclass__`` and resolved to real
    ``Anchor`` objects during instance construction.
    """

    def __init__(self, at, normal):
        self.at = at
        # Coerce literal tuple normals at class-def time so a malformed
        # constant tuple fails fast; defer string-expression normals to
        # instance-time resolution.
        self.normal = normal if isinstance(normal, str) else (
            float(normal[0]), float(normal[1]), float(normal[2])
        )
        self._name: str = ""

    def __set_name__(self, owner, name: str) -> None:
        self._name = name

    def resolve(self, instance) -> tuple[float, float, float]:
        """Evaluate ``at`` against *instance* and return a position 3-tuple."""
        return _eval_3tuple(self.at, instance, self._name, "at")

    def resolve_normal(self, instance) -> tuple[float, float, float]:
        """Resolve ``normal``; the literal-tuple case is the common path."""
        if isinstance(self.normal, str):
            return _eval_3tuple(self.normal, instance, self._name, "normal")
        return self.normal


def anchor(at, normal):
    """Declare a named anchor at class scope.

    Returns an ``AnchorDef`` placeholder that the Component framework
    collects and resolves after construction.

    ``at`` is the anchor position — either a 3-tuple/list of floats, or a
    string of three comma-separated Python expressions evaluated against
    the instance's attributes (e.g. ``"w/2, w/2, thk"``).

    ``normal`` is the outward-facing direction — same forms as ``at``.
    String normals are useful when the direction depends on a Param
    (e.g. ``"0, 0, -1 if n_shape else 1"`` for a flippable component).
    """
    return AnchorDef(at=at, normal=normal)
