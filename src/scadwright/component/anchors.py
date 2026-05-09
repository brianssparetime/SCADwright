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

    def __init__(self, at, normal, *, kind: str = "planar", surface_params=None):
        self.at = at
        # Coerce literal tuple normals at class-def time so a malformed
        # constant tuple fails fast; defer string-expression normals to
        # instance-time resolution.
        self.normal = normal if isinstance(normal, str) else (
            float(normal[0]), float(normal[1]), float(normal[2])
        )
        self.kind = kind
        # Store surface_params as supplied (dict or tuple-of-pairs); string
        # values are evaluated at instance-construction time alongside `at=`
        # so curved-surface params can reference Param attributes.
        self._surface_params_spec = surface_params
        self._name: str = ""

    def __set_name__(self, owner, name: str) -> None:
        self._name = name

    @property
    def surface_params(self) -> dict:
        """Inspection-only view of the raw spec (strings unresolved)."""
        spec = self._surface_params_spec
        if not spec:
            return {}
        return dict(spec) if isinstance(spec, dict) else dict(spec)

    def resolve(self, instance) -> tuple[float, float, float]:
        """Evaluate ``at`` against *instance* and return a position 3-tuple."""
        return _eval_3tuple(self.at, instance, self._name, "at")

    def resolve_normal(self, instance) -> tuple[float, float, float]:
        """Resolve ``normal``; the literal-tuple case is the common path."""
        if isinstance(self.normal, str):
            return _eval_3tuple(self.normal, instance, self._name, "normal")
        return self.normal

    def resolve_surface_params(self, instance) -> dict:
        """Evaluate any string values in ``surface_params`` against *instance*
        and return them as a kwargs dict suitable for ``Anchor(**kwargs)``.

        String values are Python expressions evaluated against the instance's
        attributes (the same namespace used by ``at=`` strings). Non-string
        values pass through unchanged.
        """
        from scadwright.errors import ValidationError

        spec = self._surface_params_spec
        if not spec:
            return {}
        items = spec.items() if isinstance(spec, dict) else spec
        namespace = instance.__dict__
        resolved: dict = {}
        for key, val in items:
            if isinstance(val, str):
                try:
                    resolved[key] = eval(val, {"__builtins__": {}}, namespace)
                except Exception as exc:
                    raise ValidationError(
                        f"anchor {self._name!r}: cannot evaluate surface_params"
                        f"[{key!r}] = {val!r}: {exc}"
                    ) from exc
            else:
                resolved[key] = val
        return resolved

    def _validate_expressions(self, valid_names) -> None:
        """Parse every string-expression field (``at``, ``normal``,
        ``surface_params`` values) and verify that every Load-context
        ``Name`` resolves to a declared Param or an equation-derived
        symbol from ``valid_names``.

        Catches typos in anchor expressions at class-definition time
        instead of at instance construction. Doesn't remove the
        runtime ``eval`` (values still resolve dynamically against the
        instance's attribute namespace), but moves typo-detection
        forward so an author error fires when the module imports
        rather than when a downstream user instantiates the Component.

        ``valid_names`` is the set of names the runtime eval namespace
        will contain (the Component's ``_spec_value_names`` —
        equivalent to ``set(params) | equation-derived | adjustment-LHS``).
        """
        if isinstance(self.at, str):
            _validate_str_expr(self.at, valid_names, self._name, "at")
        if isinstance(self.normal, str):
            _validate_str_expr(self.normal, valid_names, self._name, "normal")
        spec = self._surface_params_spec
        if spec:
            items = spec.items() if isinstance(spec, dict) else spec
            for key, val in items:
                if isinstance(val, str):
                    _validate_str_expr(
                        val, valid_names, self._name,
                        f"surface_params[{key!r}]",
                    )


def _validate_str_expr(
    expr: str, valid_names, anchor_name: str, role: str,
) -> None:
    """Parse ``expr`` as a Python expression and verify every Load-context
    ``Name`` resolves against ``valid_names``.

    Constants, operators, conditionals (``a if c else b``), and tuple
    displays (``"x, y, z"``) are all fine — only unresolved Names raise.
    Comprehensions are not parsed for scope (the comprehension-bound
    target name would false-positive); anchor expressions don't
    typically use them. Function calls (``abs(x)``, ``min(...)``) require
    the function name to be in ``valid_names``; since the runtime eval
    runs with ``__builtins__: {}``, builtin calls would fail at runtime
    anyway, so the class-load check is consistent.

    Raises ``ValidationError`` on syntax errors or unresolved names.
    """
    import ast

    from scadwright.errors import ValidationError

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValidationError(
            f"anchor {anchor_name!r}: {role}= has a syntax error in "
            f"{expr!r}: {exc.msg}"
        ) from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in valid_names:
                names_list = sorted(valid_names)
                names_preview = (
                    str(names_list) if len(names_list) <= 12
                    else f"{names_list[:12]} ... ({len(names_list)} total)"
                )
                raise ValidationError(
                    f"anchor {anchor_name!r}: {role}= references unknown "
                    f"name {node.id!r} in expression {expr!r}. The "
                    f"runtime eval namespace contains only declared "
                    f"Params and equation-derived names. Available: "
                    f"{names_preview}."
                )


def anchor(at, normal, *, kind: str = "planar", surface_params=None):
    """Declare a named anchor at class scope.

    Returns an ``AnchorDef`` placeholder that the Component framework
    collects and resolves after construction.

    ``at`` is the anchor position — either a 3-tuple/list of floats, or a
    string of three comma-separated Python expressions evaluated against
    the instance's attributes (e.g. ``"w/2, w/2, thk"``).

    ``normal`` is the outward-facing direction — same forms as ``at``.
    String normals are useful when the direction depends on a Param
    (e.g. ``"0, 0, -1 if n_shape else 1"`` for a flippable component).

    ``kind`` describes the surface the anchor lies on. Defaults to
    ``"planar"``. ``"cylindrical"`` and ``"conical"`` are reserved for
    decoration transforms (see ``docs/add_text.md``) and require
    ``surface_params``.

    ``surface_params`` carries the surface's geometric parameters
    (radius, axis, etc.) for curved kinds. Pass a dict for ergonomics
    (``{"radius": 5, "axis": (0, 0, 1)}``); it's normalized to a sorted
    tuple of pairs internally so the resulting Anchor stays hashable.
    """
    return AnchorDef(at=at, normal=normal, kind=kind, surface_params=surface_params)
