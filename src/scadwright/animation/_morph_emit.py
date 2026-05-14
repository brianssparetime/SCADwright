"""Build the animated AST tree for a morph, given a MorphPlan and spec.

Consumes the walker's MorphPlan and produces a single Node — variant A's
tree with each animated leaf's substitution root replaced by an animated
chain. The animated chain is a stack of Translate / Rotate / Scale nodes
whose numeric fields are SymbolicExprs over ``$t``, so the resulting SCAD
varies continuously with OpenSCAD's animation parameter.

The animation path follows Chasles' theorem: any rigid motion between
two poses is equivalent to a single rotation about a screw axis, plus
optional translation along that axis. For the box-and-lid case (a 180°
rotation combined with translation), this reads as a hinge swing rather
than a translate-while-rotating-in-midair tween.

Three branches per leaf:

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
heuristic: pick the sign whose mid-arc point has higher z, matching
gravity-up physical intuition for the typical "lid swings closed over
the top" case.
"""

from __future__ import annotations

import math
from dataclasses import fields as _dc_fields, is_dataclass, replace as _dc_replace
from typing import TYPE_CHECKING

from scadwright.animation import Const, FuncCall, SymbolicExpr, t as _t_var
from scadwright.animation._morph_walker import AnimatedLeaf, MorphPlan
from scadwright.api.morph import _MorphSpec
from scadwright.ast.csg import Union
from scadwright.ast.transforms import Rotate, Scale, Translate
from scadwright.matrix import Matrix

if TYPE_CHECKING:
    from scadwright.ast.base import Node


_ROTATION_EPS_RAD = 1e-6
_CORKSCREW_RATIO_THRESHOLD = 1.0
_EPS = 1e-9


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_animated_tree(plan: MorphPlan, spec: _MorphSpec) -> "Node":
    """Return variant A's tree with animated leaves replaced by their
    morph chains."""
    if not plan.leaves:
        # Nothing animates; tree_a is the final output. (Edge case: user
        # declared a morph between two variants that turned out to be
        # identical. Render the start variant unchanged.)
        return plan.tree_a

    slot_index_for_leaf = _compute_slot_indices(plan.leaves, spec)
    n_slots = max(slot_index_for_leaf.values(), default=0) + 1

    substitutions: dict[int, "Node"] = {}
    for leaf in plan.leaves:
        slot = slot_index_for_leaf[id(leaf.leaf)]
        alpha = _alpha_for_slot(slot, n_slots, spec.simultaneous)
        substitutions[id(leaf.substitution_root)] = _build_chain(leaf, alpha)

    return _substitute(plan.tree_a, substitutions)


# ---------------------------------------------------------------------------
# Slot grouping and ordering
# ---------------------------------------------------------------------------


def _compute_slot_indices(
    leaves: tuple[AnimatedLeaf, ...], spec: _MorphSpec,
) -> dict[int, int]:
    """Map each leaf's id(leaf) to its slot index.

    Leaves are grouped by display_name (so multi-occurrence parts share
    one slot). Slot order is: names listed in ``spec.order`` first, then
    remaining names by ascending destination z (min over occurrences).
    """
    # Group by display_name; preserve first-occurrence order for stability.
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
    return out


# ---------------------------------------------------------------------------
# Alpha expression: per-slot eased local time
# ---------------------------------------------------------------------------


def _alpha_for_slot(slot_index: int, n_slots: int, simultaneous: bool) -> SymbolicExpr:
    """Return the eased local-time alpha for parts in this slot.

    Ease-in-out is applied as smoothstep: x²·(3 − 2x). Always applied
    (no linear option — see design doc rationale).
    """
    if simultaneous or n_slots <= 1:
        local = _t_var()
    else:
        slice_size = 1.0 / n_slots
        # local = clamp(($t - slot_index*slice_size) / slice_size, 0, 1)
        raw = (_t_var() - slot_index * slice_size) / slice_size
        local = FuncCall("max", (FuncCall("min", (raw, 1.0)), 0.0))
    return _smoothstep(local)


def _smoothstep(x: SymbolicExpr) -> SymbolicExpr:
    """3x² − 2x³, in factored form x·x·(3 − 2·x). Standard ease-in-out."""
    return x * x * (3.0 - 2.0 * x)


# ---------------------------------------------------------------------------
# Per-leaf animated chain
# ---------------------------------------------------------------------------


def _build_chain(leaf: AnimatedLeaf, alpha: SymbolicExpr) -> "Node":
    """Build the animated AST for one leaf."""
    M_a = leaf.M_a
    M_b = leaf.M_b

    s_a = M_a.decompose_scale()
    s_b = M_b.decompose_scale()
    M_a_rigid = _strip_scale(M_a, s_a)
    M_b_rigid = _strip_scale(M_b, s_b)

    # M_diff captures the rigid motion from M_a to M_b.
    M_diff = M_b_rigid @ M_a_rigid.invert()
    u_dir, theta_deg = M_diff.decompose_rotation_axis_angle()
    T_diff = M_diff.translation
    theta_rad = math.radians(theta_deg)

    if abs(theta_rad) < _ROTATION_EPS_RAD:
        return _build_pure_translation(leaf.leaf, M_a_rigid, M_b_rigid, s_a, s_b, alpha)

    # Split the rigid translation into components parallel and perpendicular
    # to the rotation axis.
    T_par_scalar = T_diff[0] * u_dir[0] + T_diff[1] * u_dir[1] + T_diff[2] * u_dir[2]
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

    # Arc radius: for a 180° rotation, half-angle sin is 1, so r = |T_perp|/2.
    # For other angles, r = |T_perp| / (2·sin(θ/2)).
    sin_half = abs(math.sin(theta_rad / 2.0))
    arc_radius = T_perp_mag / (2.0 * sin_half) if sin_half > _EPS else 0.0

    # Corkscrew check: if translation along the axis dominates the arc
    # radius, the screw degenerates into a helix that reads as a corkscrew.
    # Fall back to decomposed SRT.
    corkscrew = (
        arc_radius < _EPS
        or T_par_mag / arc_radius > _CORKSCREW_RATIO_THRESHOLD
    )
    if corkscrew:
        return _build_srt(
            leaf.leaf, M_a_rigid, T_diff, u_dir, theta_deg, s_a, s_b, alpha,
        )

    # Screw motion. For 180° rotations, the axis is sign-ambiguous; the
    # heuristic picks lexicographically-higher (z, y, x) for the mid-arc.
    u = u_dir
    if abs(theta_rad - math.pi) < _ROTATION_EPS_RAD:
        u = _pick_180_sign(u_dir, T_perp, M_a_rigid, T_diff)

    # Recompute T_par and T_perp under the possibly-flipped u (for 180°
    # the dot product gives the same T_par regardless of sign; for safety
    # we redo the math).
    T_par_scalar = T_diff[0] * u[0] + T_diff[1] * u[1] + T_diff[2] * u[2]
    T_par = (u[0] * T_par_scalar, u[1] * T_par_scalar, u[2] * T_par_scalar)
    T_perp = (
        T_diff[0] - T_par[0],
        T_diff[1] - T_par[1],
        T_diff[2] - T_par[2],
    )

    # P = closest point of screw axis to origin.
    # For θ ≈ π, cot(θ/2) ≈ 0 and the cross term vanishes; P = 0.5·T_perp.
    # For other θ, P = 0.5·(T_perp + cot(θ/2)·(u × T_perp)).
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

    return _build_screw(
        leaf.leaf, M_a_rigid, s_a, s_b, P, T_par, u, theta_deg, alpha,
    )


def _build_pure_translation(
    leaf, M_a_rigid: Matrix, M_b_rigid: Matrix,
    s_a, s_b, alpha: SymbolicExpr,
) -> "Node":
    """Animated chain for the no-rotation case.

    T(α) = translate(lerp(T_a, T_b, α)) @ R_a @ scale(lerp(s_a, s_b, α)) @ leaf

    Note R_a == R_b at θ ≈ 0, so the rotation is constant.
    """
    T_a = M_a_rigid.translation
    T_b = M_b_rigid.translation
    lerp_t = tuple(_lerp(a, b, alpha) for a, b in zip(T_a, T_b))
    lerp_s = tuple(_lerp(a, b, alpha) for a, b in zip(s_a, s_b))

    chain = leaf
    chain = _maybe_scale(chain, lerp_s)
    chain = _emit_rotation_constant(M_a_rigid, chain)
    chain = Translate(v=lerp_t, child=chain)
    return chain


def _build_screw(
    leaf, M_a_rigid: Matrix, s_a, s_b,
    P, T_par, u, theta_deg: float, alpha: SymbolicExpr,
) -> "Node":
    """Screw-motion animated chain.

    T(α) = translate(P + α·T_par) @ rotate(α·θ, u)
         @ translate(-P) @ M_a_rigid @ scale(lerp(s_a, s_b, α)) @ leaf

    The translate(-P) folds into M_a_rigid's translation column at emit
    time: translate(-P) @ translate(T_a) = translate(T_a - P).
    """
    lerp_s = tuple(_lerp(a, b, alpha) for a, b in zip(s_a, s_b))

    # Outer translate: P + α·T_par.
    outer_t = tuple(
        P[i] + alpha * float(T_par[i]) for i in range(3)
    )

    # Inner translate (-P combined with M_a_rigid's translation column):
    # M_a_rigid = translate(T_a) @ R_a. The chain inside the screw rotate
    # is translate(-P) @ translate(T_a) @ R_a = translate(T_a - P) @ R_a.
    T_a = M_a_rigid.translation
    inner_t = (T_a[0] - P[0], T_a[1] - P[1], T_a[2] - P[2])

    chain = leaf
    chain = _maybe_scale(chain, lerp_s)
    chain = _emit_rotation_constant(M_a_rigid, chain)
    if not _vec_is_zero(inner_t):
        chain = Translate(v=inner_t, child=chain)
    chain = Rotate(a=alpha * float(theta_deg), v=u, child=chain)
    chain = Translate(v=outer_t, child=chain)
    return chain


def _build_srt(
    leaf, M_a_rigid: Matrix, T_diff,
    u_diff, theta_deg: float,
    s_a, s_b, alpha: SymbolicExpr,
) -> "Node":
    """Decomposed translate-lerp + slerp + scale-lerp (the corkscrew fallback).

    T(α) = translate(lerp(T_a, T_b, α)) @ R_a @ rotate(α·θ_diff, u_diff)
         @ scale(lerp(s_a, s_b, α)) @ leaf

    Here R_a is M_a_rigid's pure rotation; the slerp's axis-angle
    parameterization gives the geodesic in rotation space from R_a to R_b.
    """
    T_a = M_a_rigid.translation
    T_b = (T_a[0] + T_diff[0], T_a[1] + T_diff[1], T_a[2] + T_diff[2])
    lerp_t = tuple(_lerp(a, b, alpha) for a, b in zip(T_a, T_b))
    lerp_s = tuple(_lerp(a, b, alpha) for a, b in zip(s_a, s_b))

    chain = leaf
    chain = _maybe_scale(chain, lerp_s)
    # Slerp rotation in axis-angle form: R(α) = rotate(α·θ_diff, u_diff)
    # composes outside R_a, so the full chain becomes
    #   rotate(α·θ_diff, u_diff) @ R_a, which at α=1 equals R_diff @ R_a
    #   = (R_b @ R_a^-1) @ R_a = R_b. ✓
    chain = Rotate(a=alpha * float(theta_deg), v=u_diff, child=chain)
    chain = _emit_rotation_constant(M_a_rigid, chain)
    chain = Translate(v=lerp_t, child=chain)
    return chain


# ---------------------------------------------------------------------------
# Helpers
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
    # Strip translation by zeroing the last column rows 0..2 — but actually
    # we need the rotation alone, not the rotation+translation. Construct
    # a rotation-only Matrix and decompose its axis-angle.
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


def _maybe_scale(child: "Node", lerp_s) -> "Node":
    """Wrap in Scale only if at least one factor isn't statically 1."""
    # If all three factors are Const(1.0), the wrapper is redundant. But
    # SymbolicExpr identity comparison is complex; skip the optimization
    # and always emit. Static (Const(1) on both sides) Scale is harmless.
    return Scale(factor=lerp_s, child=child)


def _lerp(a: float, b: float, alpha: SymbolicExpr) -> SymbolicExpr:
    """lerp(a, b, α) = a + α·(b − a) as a SymbolicExpr.

    If a == b, returns a Const (no animation on this axis)."""
    a, b = float(a), float(b)
    if a == b:
        return Const(a)
    return a + alpha * (b - a)


def _vec_is_zero(v: tuple[float, float, float], eps: float = _EPS) -> bool:
    return all(abs(x) <= eps for x in v)


def _pick_180_sign(u, T_perp, M_a_rigid, T_diff):
    """For a 180° rotation, pick the axis sign with the most physically
    natural arc.

    The 180° axis is sign-ambiguous: both ``+u`` and ``-u`` represent the
    same end pose but trace different arcs (symmetric about the line from
    start to end). For most cases the arcs differ only in their direction
    perpendicular to the rotation axis (the "y direction" of the arc
    plane), with no z preference.

    Heuristic: pick the sign whose mid-arc point has the lexicographically
    larger (z, y, x) coordinates. This gives:

    - Higher-z when the geometry breaks z-symmetry (e.g. translation has a
      component perpendicular to the rotation axis in a direction with
      a z component) — the "lifts up and over" choice.
    - Higher-y when z ties — a "forward swing" default. Arbitrary but
      consistent for box-and-lid style cases where the arcs are
      symmetric in z.
    - +u as the final tiebreak. Always deterministic.
    """
    mid_pos = _mid_arc_point(u, T_perp, M_a_rigid, T_diff)
    mid_neg = _mid_arc_point(
        (-u[0], -u[1], -u[2]), T_perp, M_a_rigid, T_diff,
    )
    # Compare (z, y, x). Use a small tolerance per-axis: lexicographic
    # with ties broken at the next axis.
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
    return u  # exact tie — pick +u


def _mid_arc_point(u, T_perp, M_a_rigid, T_diff) -> tuple[float, float, float]:
    """Compute the (x, y, z) of the leaf-origin's position at α = 0.5 of
    the screw, under axis u.

    For θ = 180°, P = 0.5·T_perp regardless of sign. T_par's sign flips
    with u, so the outer-translate's α·T_par term differs across signs.
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
    # Look for children to substitute.
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
