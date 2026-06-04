"""Graph edges for an inherited Param bound to a project Spec / Component
via a plain class attribute.

A reusable base declares ``spec = Param()`` untyped and reads ``spec.x``
in its equations; a concrete subclass binds ``spec = ConcreteSpec``. The
binding lives on the subclass, the reads on the base, so the edge has to
be resolved across that boundary and attributed to the subclass. These
tests pin that, the attribution rule that keeps the edge from multiplying
down a typed inheritance chain, and the warnings for bindings the runtime
rejects.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.build import build_graph
from scadwright.graph.model import Edge, Graph


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _edges(graph: Graph, source: str, kind: str) -> list[Edge]:
    return [
        e for e in graph.edges if e.source == source and e.kind == kind
    ]


# A reusable base reading an untyped Param, plus a concrete subclass that
# binds the shared fixed Spec — the pentacon shape, reduced.
_UNTYPED_BASE = (
    "from scadwright import Component, Param, Spec\n"
    "from scadwright.primitives import cube\n"
    "\n"
    "class Bayonet(Spec):\n"
    "    equations = '''\n"
    "        bore = 60.0\n"
    "        bore_r = bore / 2\n"
    "    '''\n"
    "\n"
    "class Cap(Component):\n"
    "    spec = Param()\n"
    "    equations = '''\n"
    "        wall = spec.bore_r + 1\n"
    "    '''\n"
    "    def build(self):\n"
    "        return cube([self.wall, self.spec.bore, 1])\n"
    "\n"
    "class P6Cap(Cap):\n"
    "    spec = Bayonet\n"
)


def test_bare_fixed_spec_binding_emits_edges_from_subclass(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "main.py", _UNTYPED_BASE)
    graph = build_graph(tmp_path)

    uses = _edges(graph, "main.P6Cap", "uses_param")
    assert [(e.target, e.via_param) for e in uses] == [
        ("main.Bayonet", "spec"),
    ]

    reads = _edges(graph, "main.P6Cap", "reads_attr")
    assert len(reads) == 1
    assert reads[0].target == "main.Bayonet"
    # Union of the reads off `spec` across the inherited equations
    # (bore_r) and the inherited build body (bore_r, bore).
    assert reads[0].attrs_read == ("bore", "bore_r")


def test_untyped_base_emits_no_spec_edge(tmp_path: Path) -> None:
    """The reusable base's `spec` is genuinely unknown, so it points at
    nothing — that independence is the pattern, not a defect."""
    _write(tmp_path, "main.py", _UNTYPED_BASE)
    graph = build_graph(tmp_path)

    assert _edges(graph, "main.Cap", "uses_param") == []
    assert _edges(graph, "main.Cap", "reads_attr") == []


def test_spec_instance_binding_emits_edges_from_subclass(
    tmp_path: Path,
) -> None:
    """A constructor-call binding on an untyped base resolves the same way
    a bare fixed-Spec class does."""
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Param, Spec\n"
        "from scadwright.primitives import cube\n"
        "\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        ?bore > 0\n"
        "        bore_r = bore / 2\n"
        "    '''\n"
        "\n"
        "class Cap(Component):\n"
        "    spec = Param()\n"
        "    equations = '''\n"
        "        wall = spec.bore_r + 1\n"
        "    '''\n"
        "    def build(self):\n"
        "        return cube([self.wall, 1, 1])\n"
        "\n"
        "class P6Cap(Cap):\n"
        "    spec = Bayonet(bore=40.0)\n"
    ))
    graph = build_graph(tmp_path)

    uses = _edges(graph, "main.P6Cap", "uses_param")
    assert [e.target for e in uses] == ["main.Bayonet"]
    reads = _edges(graph, "main.P6Cap", "reads_attr")
    assert reads and reads[0].target == "main.Bayonet"
    assert reads[0].attrs_read == ("bore_r",)


def test_typed_base_does_not_duplicate_on_instance_override(
    tmp_path: Path,
) -> None:
    """When the base types the Param, the edge belongs to the base. A
    subclass that overrides with an instance of the same type must not
    re-emit it (the inherits edge already connects them)."""
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Param, Spec\n"
        "from scadwright.primitives import cube\n"
        "\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        ?bore > 0\n"
        "        bore_r = bore / 2\n"
        "    '''\n"
        "\n"
        "STD = Bayonet(bore=60.0)\n"
        "\n"
        "class Cap(Component):\n"
        "    spec = Param(Bayonet)\n"
        "    equations = '''\n"
        "        wall = spec.bore_r + 1\n"
        "    '''\n"
        "    def build(self):\n"
        "        return cube([self.wall, 1, 1])\n"
        "\n"
        "class P6Cap(Cap):\n"
        "    spec = STD\n"
    ))
    graph = build_graph(tmp_path)

    # Base draws the edge from its typed Param.
    assert [e.target for e in _edges(graph, "main.Cap", "uses_param")] == [
        "main.Bayonet",
    ]
    # Subclass re-emits nothing: `spec = STD` is an instance of the same
    # type, so it neither establishes nor changes the resolved type.
    assert _edges(graph, "main.P6Cap", "uses_param") == []
    assert _edges(graph, "main.P6Cap", "reads_attr") == []


def test_component_class_binding_warns_and_draws_no_edge(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Param\n"
        "from scadwright.primitives import cube\n"
        "\n"
        "class Part(Component):\n"
        "    equations = '''\n"
        "        w > 0\n"
        "    '''\n"
        "    def build(self):\n"
        "        return cube([self.w, 1, 1])\n"
        "\n"
        "class Base(Component):\n"
        "    part = Param()\n"
        "    equations = '''\n"
        "        x = part.w + 1\n"
        "    '''\n"
        "    def build(self):\n"
        "        return cube([self.x, 1, 1])\n"
        "\n"
        "class Bad(Base):\n"
        "    part = Part\n"
    ))
    graph = build_graph(tmp_path)

    assert _edges(graph, "main.Bad", "uses_param") == []
    assert _edges(graph, "main.Bad", "reads_attr") == []
    msgs = [m for _, m in graph.warnings]
    assert any(
        "Bad.part" in m and "Component class `Part`" in m for m in msgs
    )


def test_parameterized_spec_class_binding_warns_and_draws_no_edge(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Param, Spec\n"
        "from scadwright.primitives import cube\n"
        "\n"
        "class Sized(Spec):\n"
        "    equations = '''\n"
        "        ?bore > 0\n"
        "        bore_r = bore / 2\n"
        "    '''\n"
        "\n"
        "class Base(Component):\n"
        "    spec = Param()\n"
        "    equations = '''\n"
        "        x = spec.bore_r + 1\n"
        "    '''\n"
        "    def build(self):\n"
        "        return cube([self.x, 1, 1])\n"
        "\n"
        "class Bad(Base):\n"
        "    spec = Sized\n"
    ))
    graph = build_graph(tmp_path)

    assert _edges(graph, "main.Bad", "uses_param") == []
    msgs = [m for _, m in graph.warnings]
    assert any(
        "Bad.spec" in m and "parameterized Spec class `Sized`" in m
        for m in msgs
    )


# =============================================================================
# Regression fixture: the pentacon-six-mount example
# =============================================================================


def _pentacon_root() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "examples" / "pentacon-six-mount"
    )


def test_pentacon_caps_point_at_the_shared_spec() -> None:
    """Both concrete caps read and use the one shared spec; the reusable
    bases, being spec-agnostic, point at neither. This is the relationship
    the example exists to teach."""
    root = _pentacon_root()
    graph = build_graph(root)

    spec = "spec.PentaconSixMount"
    for cap in ("body_cap.PentaconSixBodyCap", "rear_lens_cap.PentaconSixRearLensCap"):
        uses = _edges(graph, cap, "uses_param")
        assert [(e.target, e.via_param) for e in uses] == [(spec, "spec")], cap
        reads = _edges(graph, cap, "reads_attr")
        assert len(reads) == 1 and reads[0].target == spec, cap
        # Every cap reads the lug pattern off the shared spec.
        assert "lug_count" in reads[0].attrs_read, cap

    # The reusable bases stay independent of any concrete mount.
    for base in ("body_cap.BodyCap", "rear_lens_cap.RearLensCap"):
        assert _edges(graph, base, "uses_param") == [], base
        assert _edges(graph, base, "reads_attr") == [], base


def test_pentacon_has_no_binding_warnings() -> None:
    """The example uses only the valid fixed-Spec-class binding, so it
    produces no would-raise warnings."""
    graph = build_graph(_pentacon_root())
    assert graph.warnings == ()
