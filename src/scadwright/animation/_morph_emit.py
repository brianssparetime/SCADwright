"""Build the animated AST tree for a morph chain, given a ChainPlan and spec.

Consumes the walker's ChainPlan and produces a single Node — stage 0's
tree with each animated leaf's substitution root replaced by an animated
chain that composes one delta per leg in which the leaf moves. The
animated chain is a stack of Translate / Rotate / Scale nodes whose
numeric fields are SymbolicExprs over ``$t``, so the resulting SCAD
varies continuously with OpenSCAD's animation parameter.

The animation path follows Chasles' theorem: any rigid motion between
two poses is equivalent to a single rotation about a screw axis, plus
optional translation along that axis. For the box-and-lid case (a 180°
rotation combined with translation), this reads as a hinge swing rather
than a translate-while-rotating-in-midair tween.

Per leg, three branches:

- **Pure translation** (no rotation difference): straight-line translate
  lerp. Equivalent to the screw degenerating at θ ≈ 0.
- **Screw motion** (arc-dominated): single rotation about a computed
  hinge axis, with optional translation along the axis. Reads naturally
  for hinge-like motions.
- **Decomposed SRT** (corkscrew-dominated): translate lerp + slerp + scale
  lerp applied independently. Cleaner when the screw's translation along
  axis dominates the perpendicular arc.

For 180° rotations, the screw axis has a sign ambiguity (both ``+u`` and
``-u`` represent the same end pose but trace different arcs). The
heuristic: pick the sign whose mid-arc point has higher z (with y, x as
lexicographic tiebreakers), matching gravity-up physical intuition for
the typical "lid swings closed over the top" case.

**Chain composition.** For a leaf with N-1 legs, the final transform is

    Δ_{N-2}(α_{N-2}) @ … @ Δ_1(α_1) @ Δ_0(α_0) @ M_0_rigid @ scale @ leaf

where ``Δ_k(α)`` is the per-leg screw / SRT / translation chain that
interpolates from identity at α=0 to ``M_{k+1}_rigid @ M_k_rigid⁻¹`` at
α=1. At leg boundaries the telescoping cancels: ``Δ_{k-1}(1) @ M_{k-1} =
M_k``, so the chain produces ``M_k`` at the start of leg k regardless of
which legs the leaf animates in. Scale is combined into one piecewise
expression across all stages and wrapped innermost.

**Leg timing.** Each leg gets a share of the [0, 1] timeline proportional
to its motion magnitude (translation distance + a small rotation-arc
contribution). Legs with no motion still receive a minimum slice so a
deliberately-static intermediate stage reads as a pause.
"""

from __future__ import annotations

import math
from dataclasses import is_dataclass, replace as _dc_replace
from typing import TYPE_CHECKING

from scadwright.animation import (
    Const, FuncCall, SymbolicExpr, cond as _cond, t as _t_var,
)
from scadwright.animation._morph_walker import AnimatedLeaf, ChainPlan, LegPlan
from scadwright.api.morph import _MorphSpec
from scadwright.ast.transforms import Rotate, Scale, Translate
from scadwright.matrix import Matrix

if TYPE_CHECKING:
    from scadwright.ast.base import Node


_ROTATION_EPS_RAD = 1e-6
_CORKSCREW_RATIO_THRESHOLD = 1.0
_EPS = 1e-9

# Auto-weight tuning constants. Per-leg motion magnitude is
#   translation_distance_of_leaf_origin + |θ_deg| · _ROT_TO_TRANS_SCALE
# summed across animated leaves. The conversion factor is in
# (length-unit per degree). At 0.1 mm/deg, a 90° rotation contributes
# 9 units, comparable to a 9mm slide — calibrated against the
# box-and-lid hinge case where a 180° flip is the dominant motion
# and shouldn't be massively over- or under-weighted.
_ROT_TO_TRANS_SCALE = 0.1
# Smallest fraction of the timeline any leg can claim. Ensures a
# deliberately-static intermediate stage reads as a brief pause
# rather than a snap.
_MIN_LEG_FRACTION = 0.05


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_animated_tree(plan: ChainPlan, spec: _MorphSpec) -> "Node":
    """Return stage 0's tree with animated leaves replaced by their
    chained morph subtrees."""
    if all(not leg.leaves for leg in plan.legs):
        # Nothing animates anywhere in the chain. tree_a is the final
        # output. (Edge case: user declared a morph between variants
        # that turned out to be identical, or between identical poses
        # at every stage. Render stage 0 unchanged.)
        return plan.tree_a

    # Per-leg leaf grouping (display_name → slot index) and total slot
    # count per leg. Each leg has its own slot order so two parts that
    # share a leg compete for that leg's [t_k_start, t_k_end] slice,
    # not the whole timeline.
    slot_indices_per_leg: list[dict[int, int]] = []
    slot_counts_per_leg: list[int] = []
    for leg in plan.legs:
        slots, n_slots = _compute_slot_indices_for_leg(leg.leaves, spec)
        slot_indices_per_leg.append(slots)
        slot_counts_per_leg.append(n_slots)

    # Per-leg timeline fractions.
    weights = _compute_leg_weights(plan.legs)
    leg_starts: list[float] = []
    leg_ends: list[float] = []
    cum = 0.0
    for w in weights:
        leg_starts.append(cum)
        cum += w
        leg_ends.append(cum)
    # cum should be exactly 1.0 by construction; round to avoid drift.

    # Group animated entries by substitution root id so all legs that
    # share a leaf collect into one chain.
    groups: dict[int, list[tuple[int, AnimatedLeaf]]] = {}
    for k, leg in enumerate(plan.legs):
        for entry in leg.leaves:
            groups.setdefault(id(entry.leaf), []).append((k, entry))

    # When pingpong=True, the effective animation time runs from 0 to 1
    # and back: a triangle wave that maps $t∈[0, 0.5] forward to [0, 1]
    # and $t∈[0.5, 1] reverse to [1, 0]. Every alpha downstream consumes
    # this reshaped time, so the chain naturally plays forward then
    # reverse, ending exactly where it started — what users want for
    # looping APNGs (the next loop iteration starts on the start pose).
    t_expr = _pingpong_t_expr() if spec.pingpong else _t_var()

    substitutions: dict[int, "Node"] = {}
    for entries in groups.values():
        sub_root = entries[0][1].substitution_root
        substitutions[id(sub_root)] = _build_leaf_chain(
            entries=entries,
            leg_starts=leg_starts, leg_ends=leg_ends,
            slot_indices_per_leg=slot_indices_per_leg,
            slot_counts_per_leg=slot_counts_per_leg,
            simultaneous=spec.simultaneous,
            t_expr=t_expr,
        )

    return _substitute(plan.tree_a, substitutions)


def _pingpong_t_expr() -> SymbolicExpr:
    """Return a SymbolicExpr that triangle-waves ``$t`` for pingpong
    playback: maps ``$t∈[0, 0.5]`` to ``[0, 1]`` and ``$t∈[0.5, 1]`` to
    ``[1, 0]`` so the morph plays forward then back over the full
    timeline."""
    t = _t_var()
    return _cond(t < 0.5, 2.0 * t, 2.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# Leg timing
# ---------------------------------------------------------------------------


def _compute_leg_weights(legs: tuple[LegPlan, ...]) -> list[float]:
    """Allocate timeline fractions to each leg by motion magnitude.

    Magnitude per leg = Σ over animated leaves of
        translation_distance_of_origin + |θ_deg| · _ROT_TO_TRANS_SCALE.

    Legs below _MIN_LEG_FRACTION of the timeline are bumped up so a
    deliberately-static intermediate stage still reads as a pause.
    """
    raw: list[float] = []
    for leg in legs:
        magnitude = 0.0
        for leaf in leg.leaves:
            origin_a = leaf.M_a.apply_point((0.0, 0.0, 0.0))
            origin_b = leaf.M_b.apply_point((0.0, 0.0, 0.0))
            dist = math.sqrt(
                sum((bi - ai) ** 2 for ai, bi in zip(origin_a, origin_b))
            )
            magnitude += dist
            try:
                M_diff = leaf.M_b @ leaf.M_a.invert()
                _, theta_deg = M_diff.decompose_rotation_axis_angle()
                magnitude += abs(theta_deg) * _ROT_TO_TRANS_SCALE
            except ValueError:
                # Singular M_a — _validate_pair already raised at walk
                # time, but the fallback here keeps weight computation
                # robust.
                pass
        raw.append(magnitude)

    total = sum(raw)
    if total < _EPS:
        # All legs static — divide the timeline equally.
        return [1.0 / len(legs)] * len(legs)
    fractions = [r / total for r in raw]
    floored = [max(f, _MIN_LEG_FRACTION) for f in fractions]
    norm = sum(floored)
    return [f / norm for f in floored]


# ---------------------------------------------------------------------------
# Slot grouping per leg
# ---------------------------------------------------------------------------


def _compute_slot_indices_for_leg(
    leaves: tuple[AnimatedLeaf, ...], spec: _MorphSpec,
) -> tuple[dict[int, int], int]:
    """For one leg, group leaves by display_name and assign slot indices.

    Slot order: names in ``spec.order`` first (in that order), then
    remaining names by ascending destination z (min over occurrences).
    Returns ``(id_to_slot, n_slots)`` where ``id_to_slot`` keys are
    ``id(leaf.leaf)`` for leaves in this leg.
    """
    groups: dict[str, list[AnimatedLeaf]] = {}
    for leaf in leaves:
        groups.setdefault(leaf.display_name, []).append(leaf)

    user_order = list(spec.order or [])
    listed = [n for n in user_order if n in groups]
    unlisted = [n for n in groups if n not in user_order]

    def _min_dest_z(name: str) -> float:
        return min(
            leaf.M_b.apply_point((0.0, 0.0, 0.0))[2]
            for leaf in groups[name]
        )

    unlisted.sort(key=_min_dest_z)
    ordered = listed + unlisted

    out: dict[int, int] = {}
    for slot_idx, name in enumerate(ordered):
        for leaf in groups[name]:
            out[id(leaf.leaf)] = slot_idx
    return out, len(ordered)


# ---------------------------------------------------------------------------
# Alpha expression: per-leg, per-slot eased local time
# ---------------------------------------------------------------------------


def _alpha_for_leg_and_slot(
    leg_index: int,
    leg_starts: list[float], leg_ends: list[float],
    slot_index: int, n_slots: int,
    simultaneous: bool,
    t_expr: SymbolicExpr,
) -> SymbolicExpr:
    """Build the eased local-time alpha for one leaf in one leg.

    Outside the leg's slice the alpha clamps to 0 (before) or 1 (after),
    so the chain reproduces the leg's start pose before the slice and
    its end pose after — which makes the composition telescope correctly
    when α flips between legs. ``t_expr`` is the effective animation
    time: ``$t`` for forward playback or a triangle-wave reshape of
    ``$t`` for pingpong mode.
    """
    leg_start = leg_starts[leg_index]
    leg_dur = leg_ends[leg_index] - leg_start

    leg_local_raw = (t_expr - leg_start) / leg_dur
    leg_local = FuncCall(
        "max", (FuncCall("min", (leg_local_raw, 1.0)), 0.0),
    )

    if simultaneous or n_slots <= 1:
        return _smoothstep(leg_local)

    slot_size = 1.0 / n_slots
    slot_raw = (leg_local - slot_index * slot_size) / slot_size
    slot_local = FuncCall(
        "max", (FuncCall("min", (slot_raw, 1.0)), 0.0),
    )
    return _smoothstep(slot_local)


def _smoothstep(x: SymbolicExpr) -> SymbolicExpr:
    """3x² − 2x³, in factored form x·x·(3 − 2·x). Standard ease-in-out."""
    return x * x * (3.0 - 2.0 * x)


# ---------------------------------------------------------------------------
# Per-leaf chain construction
# ---------------------------------------------------------------------------


def _build_leaf_chain(
    *, entries: list[tuple[int, AnimatedLeaf]],
    leg_starts: list[float], leg_ends: list[float],
    slot_indices_per_leg: list[dict[int, int]],
    slot_counts_per_leg: list[int],
    simultaneous: bool,
    t_expr: SymbolicExpr,
) -> "Node":
    """Build the full animated chain for one leaf across all legs it
    animates in.

    The composition is:

        Δ_{k_last}(α_{k_last}) @ … @ Δ_{k_first}(α_{k_first})
            @ M_0_rigid @ Scale(s_combined) @ leaf

    where the leaf is sitting at its stage-0 pose (``M_0 == entries[0].M_a``,
    valid because legs before the leaf's first animating leg are
    static), each per-leg Δ is built from the rigid difference
    ``M_{k+1}_rigid @ M_k_rigid⁻¹``, and Scale combines per-stage scale
    factors into one piecewise-linear-in-alphas expression.
    """
    leaf = entries[0][1].leaf

    # Per-leg alpha expressions, keyed by leg index.
    alphas: dict[int, SymbolicExpr] = {}
    for (k, entry) in entries:
        slot_idx = slot_indices_per_leg[k][id(entry.leaf)]
        n_slots = slot_counts_per_leg[k]
        alphas[k] = _alpha_for_leg_and_slot(
            leg_index=k,
            leg_starts=leg_starts, leg_ends=leg_ends,
            slot_index=slot_idx, n_slots=n_slots,
            simultaneous=simultaneous,
            t_expr=t_expr,
        )

    # Build the combined scale expression.
    # scale(t) = s_0 + Σ_k α_k · (s_{k+1} − s_k), with k indexing only
    # the legs this leaf animates in. For legs where the leaf is static
    # (no entry), s_{k+1} == s_k so the term is zero anyway.
    M_0 = entries[0][1].M_a   # leaf's stage-0 pose (see docstring)
    s_at_M_0 = M_0.decompose_scale()
    scale_factors: list = [float(s) for s in s_at_M_0]
    for (k, entry) in entries:
        s_a = entry.M_a.decompose_scale()
        s_b = entry.M_b.decompose_scale()
        for axis in range(3):
            delta = s_b[axis] - s_a[axis]
            if abs(delta) > _EPS:
                scale_factors[axis] = scale_factors[axis] + alphas[k] * delta

    # Wrap leaf inside out: leaf → Scale → M_0_rigid pose → per-leg deltas.
    chain: "Node" = leaf
    chain = Scale(factor=tuple(scale_factors), child=chain)

    M_0_rigid = _strip_scale(M_0, s_at_M_0)
    chain = _wrap_constant_pose(chain, M_0_rigid)

    # Per-leg delta chains, applied in order: leg 0 innermost, leg N-1
    # outermost. Each Δ_k uses world-space screw decomposition based on
    # M_{k+1}_rigid @ M_k_rigid⁻¹ and is wrapped around the cumulative
    # chain below it.
    M_pre = M_0_rigid  # leaf's pre-Δ_k pose (world space)
    for (k, entry) in entries:
        s_a = entry.M_a.decompose_scale()
        s_b = entry.M_b.decompose_scale()
        M_a_rigid = _strip_scale(entry.M_a, s_a)
        M_b_rigid = _strip_scale(entry.M_b, s_b)
        chain = _wrap_delta_chain(
            inner=chain,
            M_a_rigid=M_a_rigid, M_b_rigid=M_b_rigid,
            alpha=alphas[k],
        )
        M_pre = M_b_rigid  # for next leg's sign heuristic (unused now,
                            # but kept for future readers)

    return chain


def _wrap_constant_pose(inner: "Node", M_rigid: Matrix) -> "Node":
    """Wrap inner with Translate + Rotate representing M_rigid as a
    constant pose. Identity translation and identity rotation are
    omitted (no AST node added)."""
    chain = _emit_rotation_constant(M_rigid, inner)
    T = M_rigid.translation
    if not _vec_is_zero(T):
        chain = Translate(v=T, child=chain)
    return chain


def _wrap_delta_chain(
    *, inner: "Node",
    M_a_rigid: Matrix, M_b_rigid: Matrix,
    alpha: SymbolicExpr,
) -> "Node":
    """Wrap inner with one leg's animated transform stack.

    The stack interpolates from identity at α=0 to ``M_b @ M_a⁻¹`` at
    α=1 in world space, so when ``inner`` already produces the leaf at
    pose ``M_a`` (via the cumulative wrapping below), the full chain
    produces ``M_b`` at α=1.

    Three branches: pure translation, screw, SRT corkscrew fallback.
    """
    M_diff = M_b_rigid @ M_a_rigid.invert()
    u_dir, theta_deg = M_diff.decompose_rotation_axis_angle()
    T_diff = M_diff.translation
    theta_rad = math.radians(theta_deg)

    if abs(theta_rad) < _ROTATION_EPS_RAD:
        # Pure translation: lerp the world-space translation.
        lerp_t = tuple(alpha * float(T_diff[i]) for i in range(3))
        return Translate(v=lerp_t, child=inner)

    T_par_scalar = (
        T_diff[0] * u_dir[0] + T_diff[1] * u_dir[1] + T_diff[2] * u_dir[2]
    )
    T_par = (
        u_dir[0] * T_par_scalar,
        u_dir[1] * T_par_scalar,
        u_dir[2] * T_par_scalar,
    )
    T_perp = (
        T_diff[0] - T_par[0],
        T_diff[1] - T_par[1],
        T_diff[2] - T_par[2],
    )
    T_perp_mag = math.sqrt(sum(x * x for x in T_perp))
    T_par_mag = abs(T_par_scalar)

    sin_half = abs(math.sin(theta_rad / 2.0))
    arc_radius = T_perp_mag / (2.0 * sin_half) if sin_half > _EPS else 0.0

    corkscrew = (
        arc_radius < _EPS
        or T_par_mag / arc_radius > _CORKSCREW_RATIO_THRESHOLD
    )
    if corkscrew:
        # SRT fallback in world space:
        #   Translate(α·T_diff) @ Rotate(α·θ, u_diff) @ inner
        # At α=0: identity. At α=1: Translate(T_diff) @ Rotate(θ, u) = M_diff. ✓
        lerp_t = tuple(alpha * float(T_diff[i]) for i in range(3))
        chain = Rotate(a=alpha * float(theta_deg), v=u_dir, child=inner)
        chain = Translate(v=lerp_t, child=chain)
        return chain

    # Screw branch. For 180° rotations the axis is sign-ambiguous; pick
    # the sign whose mid-arc point has higher z (lex y, x as tiebreak),
    # evaluated in world coordinates by composing M_a's translation
    # into the mid-arc formula.
    u = u_dir
    if abs(theta_rad - math.pi) < _ROTATION_EPS_RAD:
        u = _pick_180_sign(u_dir, T_perp, M_a_rigid, T_diff)

    T_par_scalar = T_diff[0] * u[0] + T_diff[1] * u[1] + T_diff[2] * u[2]
    T_par = (
        u[0] * T_par_scalar, u[1] * T_par_scalar, u[2] * T_par_scalar,
    )
    T_perp = (
        T_diff[0] - T_par[0],
        T_diff[1] - T_par[1],
        T_diff[2] - T_par[2],
    )

    if abs(theta_rad - math.pi) < _ROTATION_EPS_RAD:
        P = (0.5 * T_perp[0], 0.5 * T_perp[1], 0.5 * T_perp[2])
    else:
        cot_half = 1.0 / math.tan(theta_rad / 2.0)
        cross = (
            u[1] * T_perp[2] - u[2] * T_perp[1],
            u[2] * T_perp[0] - u[0] * T_perp[2],
            u[0] * T_perp[1] - u[1] * T_perp[0],
        )
        P = (
            0.5 * (T_perp[0] + cot_half * cross[0]),
            0.5 * (T_perp[1] + cot_half * cross[1]),
            0.5 * (T_perp[2] + cot_half * cross[2]),
        )

    # Screw chain (world space):
    #   Translate(P + α·T_par) @ Rotate(α·θ, u) @ Translate(-P) @ inner
    # At α=0: Translate(P) @ Translate(-P) = identity. ✓
    # At α=1: Translate(P + T_par) @ Rotate(θ, u) @ Translate(-P) = M_diff. ✓
    outer_t = tuple(P[i] + alpha * float(T_par[i]) for i in range(3))
    neg_P = (-P[0], -P[1], -P[2])

    chain = inner
    if not _vec_is_zero(neg_P):
        chain = Translate(v=neg_P, child=chain)
    chain = Rotate(a=alpha * float(theta_deg), v=u, child=chain)
    chain = Translate(v=outer_t, child=chain)
    return chain


# ---------------------------------------------------------------------------
# Helpers shared with the original 2-stage implementation
# ---------------------------------------------------------------------------


def _strip_scale(M: Matrix, scale: tuple[float, float, float]) -> Matrix:
    """Return M with each of its first three columns divided by the
    corresponding scale factor. Yields the rigid (translation + rotation)
    portion of M."""
    sx, sy, sz = scale
    e = M.elements
    return Matrix((
        (e[0][0] / sx, e[0][1] / sy, e[0][2] / sz, e[0][3]),
        (e[1][0] / sx, e[1][1] / sy, e[1][2] / sz, e[1][3]),
        (e[2][0] / sx, e[2][1] / sy, e[2][2] / sz, e[2][3]),
        (e[3][0],      e[3][1],      e[3][2],      e[3][3]),
    ))


def _emit_rotation_constant(M_rigid: Matrix, child: "Node") -> "Node":
    """Wrap ``child`` in a Rotate node representing ``M_rigid``'s rotation
    component (the matrix with translation stripped). Identity rotation
    is a no-op."""
    e = M_rigid.elements
    R_only = Matrix((
        (e[0][0], e[0][1], e[0][2], 0.0),
        (e[1][0], e[1][1], e[1][2], 0.0),
        (e[2][0], e[2][1], e[2][2], 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    axis, angle_deg = R_only.decompose_rotation_axis_angle()
    if abs(angle_deg) < 1e-9:
        return child
    return Rotate(a=float(angle_deg), v=axis, child=child)


def _vec_is_zero(v, eps: float = _EPS) -> bool:
    return all(abs(x) <= eps for x in v)


def _pick_180_sign(u, T_perp, M_a_rigid, T_diff):
    """For a 180° rotation, pick the axis sign with the most physically
    natural arc.

    The 180° axis is sign-ambiguous: both ``+u`` and ``-u`` represent the
    same end pose but trace different arcs (symmetric about the line from
    start to end). The heuristic picks the sign whose mid-arc point has
    the lexicographically larger (z, y, x) coordinates in world space.
    This gives:

    - Higher-z when the geometry breaks z-symmetry — the "lifts up and
      over" choice, matching gravity-up intuition for box-and-lid cases.
    - Higher-y when z ties — an arbitrary but consistent default for the
      cases where the two arcs are z-symmetric.
    - +u as the final tiebreak. Always deterministic.
    """
    mid_pos = _mid_arc_point(u, T_perp, M_a_rigid, T_diff)
    mid_neg = _mid_arc_point(
        (-u[0], -u[1], -u[2]), T_perp, M_a_rigid, T_diff,
    )
    eps = 1e-9
    for axis_pos, axis_neg in (
        (mid_pos[2], mid_neg[2]),
        (mid_pos[1], mid_neg[1]),
        (mid_pos[0], mid_neg[0]),
    ):
        if axis_pos > axis_neg + eps:
            return u
        if axis_neg > axis_pos + eps:
            return (-u[0], -u[1], -u[2])
    return u


def _mid_arc_point(u, T_perp, M_a_rigid, T_diff) -> tuple[float, float, float]:
    """Compute world-space (x, y, z) of the leaf-origin's position at
    α=0.5 of the screw under axis u, given the leaf sits at M_a_rigid
    before the chain.

    For θ = 180°, P = 0.5·T_perp regardless of sign. T_par's sign flips
    with u, so the outer-translate's α·T_par term differs across signs.

    Computes ``Translate(P + 0.5·T_par) @ Rotate(90°, u) @ Translate(-P)
    @ M_a_rigid @ origin``, which is the world position the leaf origin
    arrives at when the chain runs from identity (at α=0) to M_diff (at
    α=1) wrapped around the leaf's pre-pose M_a_rigid.
    """
    P = (0.5 * T_perp[0], 0.5 * T_perp[1], 0.5 * T_perp[2])
    T_par_scalar = T_diff[0] * u[0] + T_diff[1] * u[1] + T_diff[2] * u[2]
    T_par = (u[0] * T_par_scalar, u[1] * T_par_scalar, u[2] * T_par_scalar)
    T_a = M_a_rigid.translation
    inner = (T_a[0] - P[0], T_a[1] - P[1], T_a[2] - P[2])
    R_half = Matrix.rotate_axis_angle(90.0, u)
    rotated = R_half.apply_point(inner)
    outer = (
        P[0] + 0.5 * T_par[0],
        P[1] + 0.5 * T_par[1],
        P[2] + 0.5 * T_par[2],
    )
    return (rotated[0] + outer[0], rotated[1] + outer[1], rotated[2] + outer[2])


# ---------------------------------------------------------------------------
# Tree substitution
# ---------------------------------------------------------------------------


def _substitute(node, substitutions: dict[int, "Node"]):
    """Walk tree_a; replace any node whose id is a substitution key with
    its precomputed animated chain. Reconstruct surrounding dataclass
    nodes with substituted children.
    """
    if id(node) in substitutions:
        return substitutions[id(node)]
    if not is_dataclass(node):
        return node
    children = getattr(node, "children", None)
    if children is not None and isinstance(children, tuple):
        new_children = tuple(_substitute(c, substitutions) for c in children)
        if new_children == children:
            return node
        return _dc_replace(node, children=new_children)
    child = getattr(node, "child", None)
    if child is not None:
        new_child = _substitute(child, substitutions)
        if new_child is child:
            return node
        return _dc_replace(node, child=new_child)
    return node
