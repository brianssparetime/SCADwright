"""SCAD emitter visitors for CSG AST nodes (union, difference, etc.)."""

from __future__ import annotations

from scadwright.ast.base import Node
from scadwright.ast.csg import Difference, Hull, Intersection, Minkowski, Union


class _CSGVisitorMixin:
    """Visitors for Union, Difference, Intersection, Hull, Minkowski, plus
    the shared flattening/resolve helpers those visitors depend on.
    ``_resolve_inline_custom`` is also called from the core emitter's
    ``_dominant_value_for`` pre-pass; it lives here so CSG flattening has
    it locally, and MRO makes it visible to the core.
    """

    def _emit_csg(self, op: str, children: tuple[Node, ...]) -> None:
        self.out.write(self._prefix() + f"{op}()")
        def body():
            for c in children:
                self.visit(c)
        self._block(body)

    def _resolve_inline_custom(self, node: Node) -> Node:
        """If `node` is an inline Custom transform, return its expansion;
        otherwise return `node` unchanged. Flattening recurses through
        these so chained inline transforms that produce CSG (e.g. a
        `.finger_scoop()` that expands to a `difference()`) get pulled up
        into the enclosing op instead of stacking as nested one-argument
        ops."""
        from scadwright.ast.custom import Custom
        from scadwright._custom_transforms.base import get_transform

        if isinstance(node, Custom):
            t = get_transform(node.name)
            if t is not None and t.inline:
                return t.expand(node.child, **node.kwargs_dict())
        return node

    def _flatten_csg(self, op_type: type, children: tuple[Node, ...]) -> tuple[Node, ...]:
        """Pull children of same-type descendants into a flat list. Valid
        for commutative+associative operations (union, intersection, hull).
        Recurses through inline Custom transforms that resolve to op_type.
        """
        flat: list[Node] = []
        for c in children:
            resolved = self._resolve_inline_custom(c)
            if isinstance(resolved, op_type):
                flat.extend(self._flatten_csg(op_type, resolved.children))
            else:
                flat.append(c)
        return tuple(flat)

    def visit_Union(self, n: Union) -> None:
        self._maybe_source_comment(n)
        flat = self._flatten_csg(Union, n.children)
        if len(flat) == 1:
            self.visit(flat[0])
            return
        # At the top level, separate each child with a blank line so a
        # reader can see where one part ends and the next begins. Nested
        # unions emit tight (no extra blanks) to avoid whitespace bloat.
        if self.indent == 0 and self.pretty:
            self.out.write(self._prefix() + "union()")
            def body():
                first = True
                for c in flat:
                    if not first:
                        self.out.write("\n")
                    first = False
                    self.visit(c)
            self._block(body)
            return
        self._emit_csg("union", flat)

    def visit_Difference(self, n: Difference) -> None:
        self._maybe_source_comment(n)
        # Difference is associative in only one direction:
        # (A - B) - C == A - B - C, but A - (B - C) != A - B - C.
        # So we flatten only when the FIRST child resolves to a Difference
        # (possibly through an inline Custom wrapper).
        flat = list(n.children)
        while flat:
            resolved = self._resolve_inline_custom(flat[0])
            if not isinstance(resolved, Difference):
                break
            flat = list(resolved.children) + flat[1:]
        if len(flat) == 1:
            self.visit(flat[0])
            return
        self._emit_csg("difference", tuple(flat))

    def visit_Intersection(self, n: Intersection) -> None:
        self._maybe_source_comment(n)
        flat = self._flatten_csg(Intersection, n.children)
        if len(flat) == 1:
            self.visit(flat[0])
            return
        self._emit_csg("intersection", flat)

    def visit_Hull(self, n: Hull) -> None:
        self._maybe_source_comment(n)
        flat = self._flatten_csg(Hull, n.children)
        if len(flat) == 1:
            self.visit(flat[0])
            return
        self._emit_csg("hull", flat)

    def visit_Minkowski(self, n: Minkowski) -> None:
        self._maybe_source_comment(n)
        self._emit_csg("minkowski", n.children)
