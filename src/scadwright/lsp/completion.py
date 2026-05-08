"""Completion-item generators for cursor positions in equations text.

Maps a :class:`scadwright.lsp.context.ContextKind` to a list of
LSP-shaped completion items. The handler in ``server.py`` adapts
the internal :class:`CompletionItem` shape into
``lsprotocol.types.CompletionItem`` at the LSP boundary.

Coverage by context:

- ``EXPRESSION`` -> the curated namespace shared with the runtime
  (``_CURATED_BUILTINS``, ``_CURATED_MATH``) plus the cardinality
  helpers and ``isinstance``. Callables come with an auto-paren
  snippet (``name($0)``) so the caret lands inside the parens.
  When an :class:`EquationsBlock` and cursor position are provided,
  the surrounding class's Params and bare-Name targets declared on
  earlier lines join the list — Params take precedence on name
  collisions so a redeclared identifier surfaces with its Param
  signature rather than as ``auto-declared``.
- ``TYPE_TAG`` -> the six inline type names from
  ``_INLINE_TYPE_ALLOWLIST``.
- ``ATTRIBUTE`` -> when the cursor sits at ``b.|`` and ``b`` is a
  Param of the surrounding class whose ``type_text`` matches another
  Component class in the same source file, return that class's
  Param names. Cross-file resolution is out of scope here; bases
  whose type can't be resolved against the same-file blocks yield
  an empty list.
- ``STRING`` / ``COMMENT`` -> empty list.
"""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.component.equations import (
    _CURATED_BUILTINS,
    _CURATED_MATH,
    _INLINE_TYPE_ALLOWLIST,
)
from scadwright.lsp.analyze import (
    EquationsBlock,
    ParamInfo,
    auto_declared_origins_before,
)
from scadwright.lsp.context import ContextKind


# ``True``, ``False``, ``None`` live in ``_CURATED_BUILTINS`` as
# language values, not callables — surface them as constants.
_CONSTANT_LITERALS = frozenset({"True", "False", "None"})

# ``isinstance`` is a predicate-call name allowed inside equations
# but not present in ``_CURATED_BUILTINS``; add it explicitly so it
# completes alongside the curated callables.
_EXTRA_CALLABLES = ("isinstance",)


@dataclass(frozen=True)
class CompletionItem:
    """An LSP-shaped completion suggestion.

    ``kind`` is a lowercase string naming the LSP item kind
    (``function``, ``constant``, ``class``). The server adapter
    maps these to :class:`lsprotocol.types.CompletionItemKind` at
    the protocol boundary.

    ``insert_text`` overrides ``label`` as the inserted text.
    ``is_snippet`` marks ``insert_text`` as following LSP snippet
    syntax — ``$0`` for the final caret position, ``${1:foo}`` for
    placeholders. Snippet support depends on the client's
    capabilities; clients without it would see literal ``$0``
    characters, which is acceptable graceful degradation.
    """
    label: str
    kind: str
    insert_text: str | None = None
    is_snippet: bool = False
    detail: str | None = None
    documentation: str | None = None


def build_completion_items(
    context: ContextKind,
    *,
    block: EquationsBlock | None = None,
    host_index: int = 0,
    line_index: int = 0,
    attribute_base: str | None = None,
    sibling_blocks: tuple[EquationsBlock, ...] = (),
) -> list[CompletionItem]:
    """Return the completion items appropriate for ``context``.

    A fresh list is returned each call so callers may filter or
    extend without affecting the next call. ``STRING`` and
    ``COMMENT`` contexts return an empty list.

    For ``EXPRESSION`` context, passing a ``block`` enables
    Param-aware completion: items for the class's declared Params
    and for bare-Name targets declared on earlier equation lines
    are merged into the curated list and the whole result is
    re-sorted alphabetically. ``host_index`` and ``line_index``
    locate the cursor's logical line so auto-declared targets are
    only those that precede the cursor.

    For ``ATTRIBUTE`` context, ``attribute_base`` is the bare
    identifier appearing before the ``.`` (extracted by
    :func:`scadwright.lsp.context.extract_attribute_base`) and
    ``sibling_blocks`` is the list of every equations block in the
    current source file. The function looks up the base in
    ``block.params``, takes its ``type_text``, and offers the
    matching same-file class's Params as Variable items.
    """
    if context == ContextKind.EXPRESSION:
        items = list(_EXPRESSION_ITEMS)
        if block is not None:
            items.extend(_param_items(block.params))
            items.extend(
                _auto_declared_items(block, host_index, line_index),
            )
            items.sort(key=lambda it: it.label)
        return items
    if context == ContextKind.TYPE_TAG:
        return list(_TYPE_TAG_ITEMS)
    if context == ContextKind.ATTRIBUTE:
        if block is None or attribute_base is None:
            return []
        return _attribute_items(block, attribute_base, sibling_blocks)
    return []


# =============================================================================
# Static item lists, computed once at module import
# =============================================================================


def _callable_item(name: str) -> CompletionItem:
    return CompletionItem(
        label=name,
        kind="function",
        insert_text=f"{name}($0)",
        is_snippet=True,
    )


def _constant_item(name: str) -> CompletionItem:
    return CompletionItem(label=name, kind="constant")


def _class_item(name: str) -> CompletionItem:
    return CompletionItem(label=name, kind="class")


def _build_expression_items() -> list[CompletionItem]:
    items: list[CompletionItem] = []
    seen: set[str] = set()
    for namespace in (_CURATED_BUILTINS, _CURATED_MATH):
        for name, value in namespace.items():
            if name in seen:
                continue
            seen.add(name)
            if name in _CONSTANT_LITERALS or not callable(value):
                items.append(_constant_item(name))
            else:
                items.append(_callable_item(name))
    for name in _EXTRA_CALLABLES:
        if name not in seen:
            seen.add(name)
            items.append(_callable_item(name))
    items.sort(key=lambda it: it.label)
    return items


def _build_type_tag_items() -> list[CompletionItem]:
    return [_class_item(name) for name in sorted(_INLINE_TYPE_ALLOWLIST)]


_EXPRESSION_ITEMS: list[CompletionItem] = _build_expression_items()
_TYPE_TAG_ITEMS: list[CompletionItem] = _build_type_tag_items()


# =============================================================================
# Param-aware completion helpers
# =============================================================================


def _param_items(params: tuple[ParamInfo, ...]) -> list[CompletionItem]:
    """Build a completion item per Param. Item kind is ``variable``;
    ``detail`` is the compact ``Param(...)`` signature; ``documentation``
    carries the literal ``doc=`` string when present.
    """
    return [
        CompletionItem(
            label=p.name,
            kind="variable",
            detail=p.signature(),
            documentation=p.doc_text,
        )
        for p in params
    ]


def _auto_declared_items(
    block: EquationsBlock, host_index: int, line_index: int,
) -> list[CompletionItem]:
    """Build completion items for bare-Name targets declared on lines
    strictly before the cursor's line. Names that are already
    declared as Params are skipped so the Param item wins on
    collisions.
    """
    origins = auto_declared_origins_before(block, host_index, line_index)
    declared = block.param_names
    return [
        CompletionItem(
            label=name,
            kind="variable",
            detail="auto-declared",
        )
        for name in origins
        if name not in declared
    ]


def _attribute_items(
    block: EquationsBlock,
    base_name: str,
    sibling_blocks: tuple[EquationsBlock, ...],
) -> list[CompletionItem]:
    """Build completion items for the attributes of ``base_name``.

    Looks up ``base_name`` in the surrounding block's Params; if its
    ``type_text`` matches the class name of another equations block
    in the same file, returns that block's Params as Variable items.
    Same-file only — cross-file resolution would need import-graph
    walking that's out of scope here.
    """
    target_param: ParamInfo | None = None
    for p in block.params:
        if p.name == base_name:
            target_param = p
            break
    if target_param is None or target_param.type_text is None:
        return []
    type_name = target_param.type_text
    for other in sibling_blocks:
        if other.class_name == type_name:
            return [
                CompletionItem(
                    label=p.name,
                    kind="variable",
                    detail=p.signature(),
                    documentation=p.doc_text,
                )
                for p in other.params
            ]
    return []
