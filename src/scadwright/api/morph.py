"""`morph(...)` factory for variant-to-variant animation.

Writes a class-attribute declaration inside a Design subclass:

    class BoxAndLid(Design):
        box = MyBox()
        lid = MyLid(box=box)

        @variant
        def print(self):
            return union(self.box, self.lid.up(self.lid.thk).right(80))

        @variant(default=True)
        def display(self):
            return union(self.box, self.lid.up(self.box.height))

        assemble = morph(start="print", end="display")

The attribute name (``assemble``) becomes the morph's variant name. The
``Design.__init_subclass__`` scan picks up ``_MorphSpec`` instances from
``vars(cls)`` and registers them under ``cls.__morphs__``; it also
synthesizes a ``_VariantMeta`` entry in ``cls.__variants__`` so the
existing variant resolution machinery (``resolve_variants``, CLI
``--variant=``) finds the morph without a special case.

The morph render path itself lives in ``design.py:_render_one``: when the
selected variant name appears in ``__morphs__``, ``_render_one`` invokes
the start/end variants under their own contexts, walks the trees, and
emits the animated tree. See `design_docs/variants-animate.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.errors import ValidationError


@dataclass(frozen=True)
class _MorphSpec:
    """Class-attribute declaration of a morph between two variants.

    Carries the start/end variant names and the small set of optional
    knobs. ``Design.__init_subclass__`` recognizes ``_MorphSpec`` instances
    by the ``_scadwright_morph`` sentinel attribute (set in ``__init__``).

    Not intended for direct construction — use the ``morph()`` factory.
    """

    start: str
    end: str
    order: tuple[str, ...] | None = None
    simultaneous: bool = False

    @property
    def _scadwright_morph(self) -> bool:
        # Sentinel for Design.__init_subclass__'s scan. Mirrors the
        # ``_scadwright_variant`` attribute that @variant-decorated methods
        # carry, so the same scan pattern works for both.
        return True


def morph(
    start: str,
    end: str,
    *,
    order: list[str] | None = None,
    simultaneous: bool = False,
) -> _MorphSpec:
    """Declare a morph between two variants of the enclosing Design.

    Use as a class-attribute assignment inside a Design subclass:

        assemble = morph(start="print", end="display")

    The attribute name becomes the morph's variant name; both
    ``scadwright morph script.py assemble out.apng`` and
    ``scadwright build script.py --variant=assemble`` find it under that
    name.

    Arguments:
        start: name of the start-pose variant (a method on the Design
            class decorated with ``@variant``).
        end: name of the end-pose variant.
        order: optional list of class-attribute names specifying the
            order in which parts animate when ``simultaneous=False``.
            Names not listed inherit the default (destination-z
            ascending). Listing a subset is fine — listed names go in
            the listed order at the front, the rest fall in by default
            order behind them.
        simultaneous: if False (default), animate one part at a time
            across the ``$t ∈ [0, 1]`` timeline. If True, all parts
            animate over the full timeline simultaneously.

    Validation happens eagerly: ``start == end`` raises at class-
    definition time, and ``start``/``end`` are checked against the
    Design's registered variants in ``Design.__init_subclass__``.
    """
    if not isinstance(start, str) or not start:
        raise ValidationError(f"morph: start must be a non-empty string, got {start!r}")
    if not isinstance(end, str) or not end:
        raise ValidationError(f"morph: end must be a non-empty string, got {end!r}")
    if start == end:
        raise ValidationError(
            f"morph: start and end must be different variants (both are {start!r})"
        )
    if order is not None:
        if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
            raise ValidationError(
                f"morph: order must be a list of variant-part names, got {order!r}"
            )
    return _MorphSpec(
        start=start,
        end=end,
        order=tuple(order) if order is not None else None,
        simultaneous=bool(simultaneous),
    )


__all__ = ["morph"]
