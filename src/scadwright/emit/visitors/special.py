"""SCAD emitter visitors for special AST nodes (Component, Custom, etc.)."""

from __future__ import annotations

import hashlib
import io

from scadwright.ast.custom import CHILDREN, ChildrenMarker, Custom
from scadwright.ast.transforms import Echo, ForceRender
from scadwright.emit.format import _fmt_value


class _SpecialVisitorMixin:
    """Visitors for non-geometry nodes: Component (dispatched by Visitor
    base as ``visit_component``), Custom transforms, ChildrenMarker,
    ForceRender, Echo.
    """

    def visit_component(self, n) -> None:
        # Emit a leading comment naming the Component class so a reader can
        # find where each part starts in the generated file. When the
        # `glossary` flag is set, also emit one comment line per resolved
        # equation name so the reader can map inlined literals in the
        # geometry below back to their named, derived form. The
        # construction-site source location stays under the `debug` flag
        # (via `_maybe_source_comment`) — it varies by call site, which
        # would make otherwise-identical emits compare unequal.
        if self.pretty and self.section_labels:
            self._line(f"// {type(n).__name__}")
            if getattr(self, "glossary", False):
                from scadwright.component.glossary import format_glossary
                for line in format_glossary(n):
                    self._line(f"//{line}")
        self._maybe_source_comment(n)
        self.visit(n._get_built_tree())

    def visit_Custom(self, n: Custom) -> None:
        from scadwright.errors import EmitError
        from scadwright._custom_transforms.base import get_transform

        t = get_transform(n.name)
        if t is None:
            raise EmitError(
                f"unregistered transform: {n.name!r}",
                source_location=n.source_location,
            )
        kwargs = n.kwargs_dict()
        self._maybe_source_comment(n)

        if t.inline:
            # Inline expansion: call expand with the actual child, recurse.
            expanded = t.expand(n.child, **kwargs)
            self.visit(expanded)
            return

        # Hoisted form: render the module body once with the CHILDREN placeholder,
        # then emit a module call at the use site.
        h = self._hash_custom(n.name, n.kwargs)
        if h not in self._module_defs:
            module_name = f"{n.name}_{h}"
            body_tree = t.expand(CHILDREN, **kwargs)

            # Render the body into its own buffer with indent reset for the module body.
            module_buf = io.StringIO()
            saved_out = self.out
            saved_indent = self.indent
            self.out = module_buf
            self.indent = 1
            try:
                self.visit(body_tree)
            finally:
                self.out = saved_out
                self.indent = saved_indent

            # Module signature uses parameter names.
            sig_params = ", ".join(name for name, _ in n.kwargs)
            nl = "\n" if self.pretty else " "
            self._module_defs[h] = (
                f"module {module_name}({sig_params}) {{{nl}"
                f"{module_buf.getvalue()}"
                f"}}{nl}"
            )
            self._module_call_names[h] = module_name

        module_name = self._module_call_names[h]
        call_args = ", ".join(f"{name}={_fmt_value(val)}" for name, val in n.kwargs)
        # The source comment was already written at the top of visit_Custom;
        # use a raw wrap here to avoid duplicating it.
        self.out.write(self._prefix() + f"{module_name}({call_args})")
        self._block(lambda: self.visit(n.child))

    def visit_ChildrenMarker(self, n: ChildrenMarker) -> None:
        self._line("children();")

    @staticmethod
    def _hash_custom(name: str, kwargs: tuple) -> str:
        """Stable 8-char hex hash of (name, sorted kwargs)."""
        key = repr((name, kwargs)).encode("utf-8")
        return hashlib.sha1(key).hexdigest()[:8]

    def visit_ForceRender(self, n: ForceRender) -> None:
        args = f"convexity={int(n.convexity)}" if n.convexity is not None else ""
        self._emit_wrap(n, "render", args, n.child)

    def visit_Echo(self, n: Echo) -> None:
        parts = []
        for name, value in n.values:
            if name is None:
                parts.append(_fmt_value(value))
            else:
                parts.append(f"{name}={_fmt_value(value)}")
        args = ", ".join(parts)
        if n.child is None:
            self._maybe_source_comment(n)
            self._line(f"echo({args});")
        else:
            self._emit_wrap(n, "echo", args, n.child)
