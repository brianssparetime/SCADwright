"""SCADwright project dependency-graph analyzer.

A static analyzer that walks a scadwright project, identifies
``Component``, ``Spec``, and ``Design`` classes, extracts their
dependencies (Param-type relationships, equation references,
``self.x.y`` attribute reads in ``build()`` bodies, ``build()``
composition, ``@variant`` build targets), and emits a graph in
Mermaid, JSON, or Graphviz DOT format.

The ``scadwright graph PROJECT`` CLI subcommand is the user-facing
entry point. Each concern lives in its own submodule:

- :mod:`.walk` — file-system walking and per-file AST capture.
- :mod:`.registry` — base-class category resolution.
- :mod:`.extract` — Param / equations / build / variant extractors.
- :mod:`.model` — :class:`Node`, :class:`Edge`, :class:`Graph`.
- :mod:`.build` — top-level :func:`build_graph` orchestrator.
- :mod:`.filter` — focus-and-radius subgraph extraction.
- :mod:`.render_mermaid`, :mod:`.render_json`, :mod:`.render_dot` —
  per-format renderers.
"""

from scadwright.graph.build import build_graph
from scadwright.graph.filter import FocusNotFound, filter_graph
from scadwright.graph.model import Edge, Graph, Node
from scadwright.graph.render_dot import render_dot
from scadwright.graph.render_json import render_json
from scadwright.graph.render_mermaid import render_mermaid


__all__ = [
    "Edge",
    "FocusNotFound",
    "Graph",
    "Node",
    "build_graph",
    "filter_graph",
    "render_dot",
    "render_json",
    "render_mermaid",
]
