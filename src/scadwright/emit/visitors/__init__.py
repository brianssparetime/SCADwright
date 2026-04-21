"""SCADEmitter visitor mixins, grouped by AST node category.

Each mixin defines ``visit_<NodeType>`` methods for one conceptual family
(primitives, transforms, CSG, extrusions, special forms). ``SCADEmitter``
inherits from all of them so Python's MRO wires the dispatch table
together — the base Visitor's ``visit(node)`` still dispatches via
``visit_<ClassName>`` lookup on the fully-assembled class.
"""

from scadwright.emit.visitors.csg import _CSGVisitorMixin
from scadwright.emit.visitors.extrude import _ExtrudeVisitorMixin
from scadwright.emit.visitors.primitives import _PrimitiveVisitorMixin
from scadwright.emit.visitors.special import _SpecialVisitorMixin
from scadwright.emit.visitors.transforms import _TransformVisitorMixin

__all__ = [
    "_CSGVisitorMixin",
    "_ExtrudeVisitorMixin",
    "_PrimitiveVisitorMixin",
    "_SpecialVisitorMixin",
    "_TransformVisitorMixin",
]
