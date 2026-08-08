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

        assemble = morph(stages=["print", "display"])

The attribute name (``assemble``) becomes the morph's variant name. The
``Design.__init_subclass__`` scan picks up ``_MorphSpec`` instances from
``vars(cls)`` and registers them under ``cls.__morphs__``; it also
synthesizes a ``_VariantMeta`` entry in ``cls.__variants__`` so the
existing variant resolution machinery (``resolve_variants``, CLI
``--variant=``) finds the morph without a special case.

The morph render path itself lives in ``design.py:_render_one``: when the
selected variant name appears in ``__morphs__``, ``_render_one`` invokes
each stage variant under its own context, walks the trees, and emits the
chained animated tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.errors import ValidationError


@dataclass(frozen=True)
class _MorphSpec:
    """Class-attribute declaration of a morph across a sequence of variants.

    Carries the stage names (two or more) and the small set of optional
    knobs. ``Design.__init_subclass__`` recognizes ``_MorphSpec`` instances
    by the ``_scadwright_morph`` sentinel attribute, mirroring the
    ``_scadwright_variant`` marker on @variant-decorated methods so a
    single class-body scan can pick up both kinds.

    Not intended for direct construction — use the ``morph()`` factory.
    """

    stages: tuple[str, ...]
    order: tuple[str, ...] | None = None
    simultaneous: bool = False
    pingpong: bool = False
    michael_bay: bool = False
    # (stage_name, timeline_fraction) pairs, in the order the user wrote
    # them. A tuple rather than a dict so the spec stays hashable.
    hold: tuple[tuple[str, float], ...] = ()

    @property
    def _scadwright_morph(self) -> bool:
        return True


def morph(
    stages: list[str],
    *,
    order: list[str] | None = None,
    simultaneous: bool = False,
    pingpong: bool = False,
    michael_bay: bool = False,
    hold: dict[str, float] | None = None,
) -> _MorphSpec:
    """Declare a morph across a sequence of two or more variants.

    Use as a class-attribute assignment inside a Design subclass:

        assemble = morph(stages=["print", "display"])
        settle = morph(stages=["exploded", "loose", "seated"])

    The attribute name becomes the morph's variant name; both
    ``scadwright morph script.py assemble out.apng`` and
    ``scadwright build script.py --variant=assemble`` find it under that
    name.

    Arguments:
        stages: list of two or more variant names (methods decorated with
            ``@variant`` on the same Design). The animation runs across
            consecutive pairs ``(stages[0], stages[1])``,
            ``(stages[1], stages[2])``, ..., each pair forming one "leg"
            of the chain. Two-variant morphs are ``stages=["a", "b"]``;
            three or more stages make a chain.
        order: optional list of class-attribute names specifying the
            order in which parts animate within each leg when
            ``simultaneous=False``. Names not listed inherit the default
            (destination-z ascending). Listing a subset is fine — listed
            names go in the listed order at the front, the rest fall in
            by default order behind them.
        simultaneous: if False (default), animate one part at a time
            inside each leg's slice. If True, all parts in a leg animate
            over that leg's full slice simultaneously.
        pingpong: if True, the animation plays forward over the first
            half of the timeline and reverses back over the second
            half. The chain visits stages[0] → stages[1] → … →
            stages[-1] → … → stages[1] → stages[0] as ``$t`` runs from
            0 to 1, ending exactly where it started — natural for
            looping APNGs.
        michael_bay: if True, the camera orbits 360° around world z
            over the animation, overriding the final stage's
            ``rotation`` viewpoint field. Pairs naturally with
            ``pingpong=True``: the model plays forward then back
            while the camera completes one full revolution.
        hold: ``{stage_name: fraction}`` — how long the animation rests
            on a stage when it arrives there, as a fraction of the
            whole timeline. ``hold={"seated": 0.3}`` spends 30% of the
            loop sitting on the seated pose, which is what lets the eye
            land on the finished object before the loop restarts.
            Arrival at ``stages[0]`` is the start of the timeline, so
            holding it rests before anything moves. Hold as many stages
            as you like; the fractions must leave room for the motion.
            The rest is time the parts aren't moving, so raise
            ``--frames`` if the motion starts to look coarse.

    Validation happens eagerly: ``stages`` must be a list of non-empty
    strings of length >= 2, with no consecutive duplicates. Each stage
    name is checked against the Design's registered variants in
    ``Design.__init_subclass__``.
    """
    if not isinstance(stages, list):
        raise ValidationError(
            f"morph: stages must be a list of variant names, got {stages!r}"
        )
    if len(stages) < 2:
        raise ValidationError(
            f"morph: stages must have at least 2 entries, got {len(stages)}"
        )
    for i, name in enumerate(stages):
        if not isinstance(name, str) or not name:
            raise ValidationError(
                f"morph: stages[{i}] must be a non-empty string, got {name!r}"
            )
    for i in range(len(stages) - 1):
        if stages[i] == stages[i + 1]:
            raise ValidationError(
                f"morph: stages[{i}] and stages[{i + 1}] are both "
                f"{stages[i]!r}; a stage listed twice in a row has no "
                f"motion between the two. To rest on a stage, name it in "
                f"`hold=` instead, e.g. "
                f"`morph(stages={stages!r}, hold={{{stages[i]!r}: 0.3}})`."
            )
    if order is not None:
        if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
            raise ValidationError(
                f"morph: order must be a list of variant-part names, got {order!r}"
            )
    return _MorphSpec(
        stages=tuple(stages),
        order=tuple(order) if order is not None else None,
        simultaneous=bool(simultaneous),
        pingpong=bool(pingpong),
        michael_bay=bool(michael_bay),
        hold=_validate_hold(hold, stages),
    )


def _validate_hold(
    hold: "dict[str, float] | None", stages: list[str],
) -> tuple[tuple[str, float], ...]:
    """Check ``hold`` against the chain and return it as ordered pairs.

    Every key has to name a stage in this chain, every fraction has to
    be positive, and the fractions together have to leave time for the
    parts to move.
    """
    if hold is None:
        return ()
    if not isinstance(hold, dict):
        raise ValidationError(
            f"morph: hold must be a dict of {{stage_name: fraction}}, "
            f"got {hold!r}"
        )
    for name, fraction in hold.items():
        if name not in stages:
            raise ValidationError(
                f"morph: hold names {name!r}, which is not a stage of "
                f"this morph. Stages are {list(stages)!r}."
            )
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
            raise ValidationError(
                f"morph: hold[{name!r}] must be a number, got {fraction!r}"
            )
        if fraction <= 0:
            raise ValidationError(
                f"morph: hold[{name!r}] is {fraction}; a hold is a "
                f"fraction of the timeline and has to be greater than 0."
            )
    total = sum(hold.values())
    if total >= 1.0:
        raise ValidationError(
            f"morph: the holds add up to {total:g} of the timeline, "
            f"leaving nothing for the parts to move in. Holds are "
            f"fractions of the whole animation and must total less "
            f"than 1."
        )
    return tuple((name, float(f)) for name, f in hold.items())


__all__ = ["morph"]
