"""JSON renderer: the scadwright project map as structured data.

Mirrors the ASCII renderer's vocabulary and grouping (Designs /
Components / Specs / Transforms) for machine consumers — doc
generators, dashboards, diff tooling, AI assistants. Two differences
from the ASCII output, both deliberate:

- **Full, not brief.** Every field a Component reads off a Spec is
  listed inline; nothing is moved or summarized for length.
- **Single-source forward.** Each relationship is stored once, on the
  entity that owns it (a Component's ``uses_spec``, a Design's
  ``builds``). The reverse views the ASCII shows (``read by``,
  ``built by``) are derivable by inversion and are not duplicated
  here, so the data has one source of truth and diffs cleanly.

Entities are keyed by display name. Relationship keys appear only when
non-empty; the four top-level group keys are always present.
"""

from __future__ import annotations

import json

from scadwright.graph.view import Entity, assemble


def render_json(graph) -> str:
    """Return the project map as a JSON string with a trailing newline."""
    view = assemble(graph)
    payload = {
        "project": view.project,
        "designs": {e.name: _design(e) for e in view.designs},
        "components": {e.name: _component(e) for e in view.components},
        "specs": {e.name: _spec(e) for e in view.specs},
        "transforms": {e.name: _transform(e) for e in view.transforms},
    }
    if view.warnings:
        payload["warnings"] = [list(w) for w in view.warnings]
    return json.dumps(payload, indent=2) + "\n"


def _loc(e: Entity) -> dict:
    return {"location": e.location} if e.location else {}


def _component(e: Entity) -> dict:
    out: dict[str, object] = _loc(e)
    if e.bases:
        out["based_on"] = list(e.bases)
    if e.spec_uses:
        out["uses_spec"] = [
            _drop_empty({
                "spec": s.spec, "via_param": s.via_param,
                "reads": list(s.fields),
            })
            for s in e.spec_uses
        ]
    if e.part_uses:
        out["uses_component"] = [
            _drop_empty({
                "component": p.part, "via_param": p.via_param,
                "reads": list(p.fields),
            })
            for p in e.part_uses
        ]
    if e.contains:
        out["contains"] = list(e.contains)
    if e.uses_transform:
        out["uses_transform"] = list(e.uses_transform)
    return out


def _spec(e: Entity) -> dict:
    return _loc(e)


def _design(e: Entity) -> dict:
    out: dict[str, object] = _loc(e)
    variants = {
        v.name: _drop_empty({"default": v.default, "builds": list(v.builds)})
        for v in e.variants if not v.is_morph
    }
    morphs = {
        v.name: {"builds": list(v.builds), "stages": list(v.stages)}
        for v in e.variants if v.is_morph
    }
    if variants:
        out["variants"] = variants
    if morphs:
        out["morphs"] = morphs
    return out


def _transform(e: Entity) -> dict:
    out: dict[str, object] = _loc(e)
    if e.spec_uses:
        out["uses_spec"] = [
            _drop_empty({"spec": s.spec, "reads": list(s.fields)})
            for s in e.spec_uses
        ]
    if e.contains:
        out["contains"] = list(e.contains)
    if e.uses_transform:
        out["uses_transform"] = list(e.uses_transform)
    return out


def _drop_empty(d: dict) -> dict:
    """Drop keys whose value is ``None``, an empty list, or ``False``
    for ``default`` — keeps per-entry records tight without losing
    meaningful zeros.
    """
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if v == [] :
            continue
        if k == "default" and v is False:
            continue
        out[k] = v
    return out
