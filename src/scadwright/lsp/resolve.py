"""Dotted-chain type resolution for equations attribute access.

Given a chain of identifiers like ``["spec", "clearances"]``,
resolves each step by looking up the name as a Param in the
current block, reading its ``type_text``, and finding the matching
sibling block. Used by completion, hover, and definition.
"""

from __future__ import annotations

from scadwright.lsp.analyze import EquationsBlock


def resolve_chain_to_block(
    chain: list[str],
    block: EquationsBlock,
    sibling_blocks: tuple[EquationsBlock, ...],
) -> EquationsBlock | None:
    """Walk a dotted attribute chain through Param type_text lookups.

    Returns the :class:`EquationsBlock` at the end of the chain, or
    ``None`` if any step fails (name not a Param, no ``type_text``,
    ``type_text`` doesn't match any sibling class).
    """
    current_block = block
    for name in chain:
        target_param: ParamInfo | None = None
        for p in current_block.params:
            if p.name == name:
                target_param = p
                break
        if target_param is None or target_param.type_text is None:
            return None
        type_name = target_param.type_text
        next_block: EquationsBlock | None = None
        for other in sibling_blocks:
            if other.class_name == type_name:
                next_block = other
                break
        if next_block is None:
            return None
        current_block = next_block
    return current_block
