"""ASCII renderer: a scadwright project map.

Renders the :class:`scadwright.graph.view.ProjectView` as a grouped,
plain-text outline for terminal reading, grep, and AI consumers. The
output describes the project in the framework's own terms — Designs,
Components, Specs, Transforms — rather than as a node-and-edge graph.

Each entity lists its relationships in both directions, named with a
small fixed verb set plus the capitalized framework noun of the
target (``uses Spec``, ``built by Design``, ``read by Component``).
Locations are bracketed ``[path:line]``; parentheses carry qualifiers
(``(a BodyCap)``, ``(default)``). Lists of more than three values
break to one per line; a morph's stages always render as a numbered
list, since their order is the animation sequence.
"""

from __future__ import annotations

from scadwright.graph.model import Graph
from scadwright.graph.view import Entity, assemble


_INLINE_MAX = 3


def render_ascii(graph: Graph) -> str:
    """Return the project-map representation of ``graph``.

    Output is deterministic (the view sorts entities and their
    relationships) and ends with a trailing newline.
    """
    view = assemble(graph)
    lines: list[str] = [
        f"scadwright project: {view.project}",
        _counts(view),
    ]
    _section(lines, "Designs", view.designs, _design_lines)
    _section(lines, "Components", view.components, _component_lines)
    _section(lines, "Specs", view.specs, _spec_lines)
    _section(lines, "Transforms", view.transforms, _transform_lines)
    if view.warnings:
        lines.append("")
        lines.append("Warnings")
        for path, msg in view.warnings:
            lines.append(f"  {path}: {msg}")
    return "\n".join(lines) + "\n"


def _counts(view) -> str:
    parts: list[str] = []
    for n, word in (
        (len(view.designs), "design"),
        (len(view.components), "component"),
        (len(view.specs), "spec"),
        (len(view.transforms), "transform"),
    ):
        if n:
            parts.append(f"{n} {word}" + ("s" if n != 1 else ""))
    return ", ".join(parts) + "." if parts else "(empty project)"


def _section(lines, title, entities, render_entity) -> None:
    if not entities:
        return
    lines.append("")
    lines.append(title)
    for e in entities:
        lines.extend(render_entity(e))


def _header(e: Entity) -> str:
    quals = f" (a {', '.join(e.bases)})" if e.bases else ""
    loc = f" [{e.location}]" if e.location else ""
    return f"  {e.name}{quals}{loc}"


def _emit_rels(out, rels, indent) -> None:
    """Emit ``(phrase, targets)`` relationship lines, aligning the
    phrase column for inline ones and breaking >3-item lists vertical.
    """
    if not rels:
        return
    inline = [len(p) for p, t in rels if len(t) <= _INLINE_MAX]
    width = max(inline) if inline else 0
    for phrase, targets in rels:
        if len(targets) <= _INLINE_MAX:
            out.append(f"{indent}{phrase.ljust(width)}  {', '.join(targets)}")
        else:
            out.append(f"{indent}{phrase}")
            for t in targets:
                out.append(f"{indent}  {t}")


def _component_lines(e: Entity) -> list[str]:
    out = [_header(e)]
    rels = []
    if e.spec_uses:
        rels.append(("uses Spec", [s.spec for s in e.spec_uses]))
    if e.part_uses:
        rels.append(("uses Component", [p.part for p in e.part_uses]))
    if e.contains:
        rels.append(("contains Component", list(e.contains)))
    if e.uses_transform:
        rels.append(("uses Transform", list(e.uses_transform)))
    if e.specialized_by:
        rels.append(("specialized by Component", list(e.specialized_by)))
    if e.built_by:
        rels.append(("built by Design", list(e.built_by)))
    if e.used_in:
        rels.append(("used in Component", list(e.used_in)))
    _emit_rels(out, rels, "    ")
    return out


def _spec_lines(e: Entity) -> list[str]:
    out = [_header(e)]
    if e.read_by:
        out.append("    read by Component")
        fw = max(len(fld) for fld, _ in e.read_by)
        for fld, readers in e.read_by:
            readers = list(readers)
            if len(readers) <= _INLINE_MAX:
                out.append(f"      {fld.ljust(fw)}  {', '.join(readers)}")
            else:
                out.append(f"      {fld}")
                for r in readers:
                    out.append(f"        {r}")
    return out


def _design_lines(e: Entity) -> list[str]:
    out = [_header(e)]
    regular = [v for v in e.variants if not v.is_morph]
    morphs = [v for v in e.variants if v.is_morph]
    if regular:
        pw = max(len(_vlabel(v)) for v in regular)
        for v in regular:
            label = _vlabel(v).ljust(pw)
            if not v.builds:
                out.append(f"    {label}  no parts traced")
            elif len(v.builds) <= _INLINE_MAX:
                out.append(
                    f"    {label}  builds Component  {', '.join(v.builds)}"
                )
            else:
                out.append(f"    {label}  builds Component")
                for t in v.builds:
                    out.append(f"      {t}")
    for v in morphs:
        out.append(f"    Morph {v.name}")
        if v.builds:
            _emit_rels(out, [("builds Component", list(v.builds))], "      ")
        else:
            out.append("      no parts traced")
        if v.stages:
            out.append("      uses Variant as stage")
            for i, stage in enumerate(v.stages, 1):
                out.append(f"        {i}. {stage}")
    return out


def _vlabel(v) -> str:
    return f"Variant {v.name}" + (" (default)" if v.default else "")


def _transform_lines(e: Entity) -> list[str]:
    out = [_header(e)]
    rels = []
    if e.spec_uses:
        rels.append(("uses Spec", [s.spec for s in e.spec_uses]))
    if e.contains:
        rels.append(("contains Component", list(e.contains)))
    if e.uses_transform:
        rels.append(("uses Transform", list(e.uses_transform)))
    if e.used_by:
        rels.append(("used by", list(e.used_by)))
    _emit_rels(out, rels, "    ")
    return out
