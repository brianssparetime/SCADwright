"""The iterative resolver itself.

Construct an :class:`IterativeResolver` with the parsed equations and
constraints plus the user's supplied values, then call ``resolve()``.
The resolver fills in unknowns by alternating single-equation passes
with a system-solve fallback, and surfaces explanatory errors when the
inputs are insufficient, inconsistent, or ambiguous.
"""

from __future__ import annotations

import ast
from typing import Any

from scadwright.component.params import Param
from scadwright.component.resolver.coercion import _coerce_for_param
from scadwright.component.resolver.enrichment import _enrich_constraint_failure
from scadwright.component.resolver.per_param import extract_per_param_validator
from scadwright.component.resolver.sympy_bridge import (
    _sufficient_subsets,
    ast_to_sympy,
)
from scadwright.component.resolver.types import (
    ParsedConstraint,
    ParsedEquation,
)
from scadwright.component.resolver_ast import (
    find_unknowns,
    is_fully_algebraic,
    substitute_knowns,
)
from scadwright.errors import ValidationError


# =============================================================================
# Iterative resolver
# =============================================================================


_AMBIGUOUS_LIST_LIMIT = 10


class IterativeResolver:
    """Resolve a system of equations and constraints to a complete knowns dict.

    The resolver runs an iterative single-equation pass until no progress
    is made, then attempts a system-solve fallback for any remaining
    algebraic equations. Constraints are evaluated as soon as their
    referenced names are all known.
    """

    def __init__(
        self,
        equations: list[ParsedEquation],
        constraints: list[ParsedConstraint],
        params: dict[str, Param],
        supplied: dict[str, Any],
        component_name: str,
        override_names: frozenset[str] = frozenset(),
    ):
        from scadwright.component.equations import (
            _CURATED_BUILTINS, _CURATED_MATH,
        )

        self.equations = equations
        self.constraints = constraints
        self.params = params
        self.component_name = component_name
        self._override_names = override_names

        # knowns: name → value, coerced via each Param's type so the
        # resolver sees the same form Param.__set__ would produce.
        #
        # `None` defaults (the `?` sigil) are added immediately so the
        # optional-handling path can detect the unset state.
        #
        # Non-None defaults are deferred: only applied if the iterative
        # loop stalls. This matches legacy behavior — a default value
        # yields to a solver-found value when the equations + user
        # inputs are sufficient on their own.
        self.knowns: dict[str, Any] = {
            name: _coerce_for_param(
                value, params.get(name),
                name=name, component_name=component_name,
            )
            for name, value in supplied.items()
        }
        self._pending_defaults: dict[str, Any] = {}
        for name, param in params.items():
            if name in self.knowns:
                continue
            if not param.has_default():
                continue
            if param.default is None:
                # Override names are equation-filled, not None-defaulted.
                # The optional sigil declares the parameter optional from
                # the caller's view; the equation provides the value when
                # the caller doesn't.
                if name in override_names:
                    continue
                self.knowns[name] = None
            else:
                self._pending_defaults[name] = _coerce_for_param(
                    param.default, param,
                    name=name, component_name=component_name,
                )
        self._supplied_names = set(supplied.keys())
        # Tracks which `_pending_defaults` entries actually fire (i.e., the
        # iterative loop stalled on the name and the default was applied).
        # Read after `resolve()` to classify a name as caller-input vs
        # Param-default vs equation-derived in downstream consumers
        # (e.g. the emit-time glossary).
        self._applied_defaults: set[str] = set()

        # Curated namespace for evaluation (does not include knowns).
        self._curated_ns = {**_CURATED_BUILTINS, **_CURATED_MATH}

        # Pending indices into self.equations / self.constraints. Lists
        # preserve declaration order so error messages report the first
        # failing equation/constraint, matching how the legacy pipeline
        # surfaced errors.
        self._pending_eqs: list[int] = list(range(len(equations)))
        self._pending_constraints: list[int] = list(range(len(constraints)))

        # Pre-resolve optional-name overrides before the iterative loop
        # runs. For each equation whose bare-Name target is an override
        # name and was NOT user-supplied, evaluate the RHS with the
        # target bound to None and assign the result. The user-supplied
        # case falls through to the normal consistency-check path.
        self._preresolve_overrides()

    # --- error-location helpers ---

    def _loc(self, eq_or_constraint) -> str:
        """Prefix string pointing at the source line in the user's
        ``equations`` list. Used by every per-equation/per-constraint
        error message."""
        return (
            f"{self.component_name}.equations"
            f"[{eq_or_constraint.source_line_index}]"
        )

    def _loc_multi(self, items) -> str:
        """Prefix for errors that span multiple equations (system-solve
        aggregates). Lists each unique source-line index."""
        unique = sorted({i.source_line_index for i in items})
        return f"{self.component_name}.equations[{', '.join(str(i) for i in unique)}]"

    # --- override pre-resolution ---

    def _preresolve_overrides(self) -> None:
        """Resolve optional-name overrides before the iterative loop.

        For each equation whose bare-Name target is an override name
        (optional + equation LHS target) AND the user did NOT supply
        a value, evaluate the RHS with the target temporarily bound
        to None and assign the result. The equation is then removed
        from the pending list — already resolved.

        If the user DID supply a value, leave the equation pending so
        the iterative loop's normal consistency-check path runs.
        """
        if not self._override_names:
            return

        for i in list(self._pending_eqs):
            eq = self.equations[i]
            # Identify the bare-Name override target on either side.
            target_name = None
            rhs_node = None
            if (
                isinstance(eq.lhs, ast.Name)
                and eq.lhs.id in self._override_names
            ):
                target_name = eq.lhs.id
                rhs_node = eq.rhs
            elif (
                isinstance(eq.rhs, ast.Name)
                and eq.rhs.id in self._override_names
            ):
                target_name = eq.rhs.id
                rhs_node = eq.lhs
            if target_name is None:
                continue
            # User-supplied non-None values fall through to the
            # consistency-check path. An explicit ``name=None`` from
            # the caller is treated the same as "not supplied" — it
            # selects the default branch of the override pattern.
            if (
                target_name in self._supplied_names
                and self.knowns.get(target_name) is not None
            ):
                continue
            # Drop the explicit-None binding so the override evaluates
            # cleanly. The pre-resolve overwrites it with the RHS.
            if target_name in self.knowns and self.knowns[target_name] is None:
                del self.knowns[target_name]

            # Evaluate the RHS with the target bound to None. The pre-
            # resolution check (_check_non_float_solver_target for
            # non-float types; the override-RHS evaluability check for
            # all types) ensures the RHS is well-defined when the
            # target is None.
            tentative = dict(self.knowns)
            tentative[target_name] = None
            sub = substitute_knowns(rhs_node, tentative, self._curated_ns)
            full_known = set(tentative) | set(self._curated_ns)
            if find_unknowns(sub, full_known):
                # Other names unknown; leave pending — the iterative
                # loop will pick this up once those resolve.
                continue
            try:
                expr_node = ast.Expression(body=sub)
                ast.fix_missing_locations(expr_node)
                code = compile(expr_node, "<override>", "eval")
                ns = {**self._curated_ns, **tentative, "__builtins__": {}}
                value = eval(code, ns)
            except (TypeError, ValueError) as exc:
                # The RHS evaluated as far as it could and threw on
                # the None binding. The class-define-time
                # _check_override_rhs_evaluable should have caught
                # this; if we got here, it's a shape that slipped
                # through. Surface a clear error rather than letting
                # the iterative loop misreport as "cannot solve."
                raise ValidationError(
                    f"{self._loc(eq)}: override pattern `{eq.raw}` "
                    f"failed to evaluate with `{target_name}` "
                    f"defaulted to None: {type(exc).__name__}: {exc}"
                ) from exc
            except Exception:
                # NameError or another exception means the RHS
                # depends on a name that isn't known yet; let the
                # iterative loop handle it.
                continue

            # Coerce per the Param's type and assign.
            param = self.params.get(target_name)
            value = _coerce_for_param(
                value, param,
                name=target_name, component_name=self.component_name,
            )
            self.knowns[target_name] = value
            self._pending_eqs.remove(i)

    # --- public ---

    def resolve(self) -> dict[str, Any]:
        """Run the iterative loop. Returns the final knowns dict.

        Raises ValidationError on insufficient/inconsistent/ambiguous.
        """
        # Initial constraint check on anything fully evaluable.
        self._check_pending_constraints()

        while self._pending_eqs:
            progress = False
            for i in list(self._pending_eqs):
                outcome = self._try_resolve_equation(self.equations[i])
                if outcome in ("resolved", "skipped", "consistent"):
                    self._pending_eqs.remove(i)
                if outcome == "resolved":
                    progress = True
            # New knowns may unlock constraints.
            self._check_pending_constraints()
            if progress:
                continue
            # No progress this pass — apply deferred Param defaults if
            # any, and re-iterate. Defaults yield to solver-found values
            # because they're only added when the loop is stuck.
            if self._pending_defaults:
                for name, value in self._pending_defaults.items():
                    if name not in self.knowns:
                        self.knowns[name] = value
                        self._applied_defaults.add(name)
                self._pending_defaults = {}
                continue
            # System-solve fallback for coupled equations.
            if not self._pending_eqs:
                break
            sys_progress = self._system_solve()
            if not sys_progress:
                self._raise_insufficient()

        # Final check on anything that's still pending (None-skipped or otherwise).
        self._check_pending_constraints()
        return self.knowns

    # --- per-equation resolve ---

    def _try_resolve_equation(self, eq: ParsedEquation) -> str:
        """Returns ``'resolved'``, ``'skipped'``, ``'consistent'``, or
        ``'postponed'``."""
        # OQ 6: explicit-None-supplied vs equation-pinning detection.
        # If one side is a bare Name that the user explicitly supplied as
        # None, and the other side evaluates (with all other knowns) to a
        # concrete non-None value, the equation contradicts the user's
        # explicit None. Surface that as a specific error.
        self._check_supplied_none_conflict(eq)

        # Try to substitute knowns into both sides.
        sub_lhs = substitute_knowns(eq.lhs, self.knowns, self._curated_ns)
        sub_rhs = substitute_knowns(eq.rhs, self.knowns, self._curated_ns)

        full_known_names = set(self.knowns) | set(self._curated_ns)
        lhs_unknowns = find_unknowns(sub_lhs, full_known_names)
        rhs_unknowns = find_unknowns(sub_rhs, full_known_names)
        all_unknowns = lhs_unknowns | rhs_unknowns

        # Optional handling: if any referenced name has value None and the
        # equation didn't manage to evaluate cleanly, decide skip vs.
        # inconsistent.
        none_refs = {
            n for n in eq.referenced_names
            if n in self.knowns and self.knowns[n] is None
        }
        if none_refs:
            return self._handle_none_referenced(
                eq, sub_lhs, sub_rhs, all_unknowns, none_refs
            )

        if not all_unknowns:
            return self._consistency_check(eq, sub_lhs, sub_rhs)

        # Forward-eval first: when one side is a bare unknown Name and
        # the other has no remaining unknowns, evaluate the other side
        # in Python and assign. Runtime errors (ZeroDivisionError,
        # TypeError, etc.) surface as derivation failures rather than
        # being swallowed.
        if (
            isinstance(sub_lhs, ast.Name)
            and sub_lhs.id in all_unknowns
            and not rhs_unknowns
        ):
            return self._forward_assign(eq, sub_lhs.id, sub_rhs)
        if (
            isinstance(sub_rhs, ast.Name)
            and sub_rhs.id in all_unknowns
            and not lhs_unknowns
        ):
            return self._forward_assign(eq, sub_rhs.id, sub_lhs)

        if is_fully_algebraic(sub_lhs) and is_fully_algebraic(sub_rhs):
            return self._sympy_solve_one(eq, sub_lhs, sub_rhs, all_unknowns)

        return "postponed"

    def _check_supplied_none_conflict(self, eq: ParsedEquation) -> None:
        """Raise if the equation pins a bare-Name target to a non-None
        value but the user explicitly supplied that name as None.
        """
        for side, other in ((eq.lhs, eq.rhs), (eq.rhs, eq.lhs)):
            if not isinstance(side, ast.Name):
                continue
            name = side.id
            if name not in self._supplied_names:
                continue
            if self.knowns.get(name) is not None:
                continue
            knowns_minus = {
                k: v for k, v in self.knowns.items() if k != name
            }
            sub_other = substitute_knowns(other, knowns_minus, self._curated_ns)
            full_names = set(knowns_minus) | set(self._curated_ns)
            if find_unknowns(sub_other, full_names):
                continue
            try:
                expr_node = ast.Expression(body=sub_other)
                ast.fix_missing_locations(expr_node)
                code = compile(expr_node, "<resolver>", "eval")
                full_ns = {
                    **self._curated_ns, **knowns_minus, "__builtins__": {},
                }
                val = eval(code, full_ns)
            except Exception:
                continue
            if val is not None:
                raise ValidationError(
                    f"{self._loc(eq)}: equation `{eq.raw}` would "
                    f"assign {name}={val!r} but {name} was explicitly "
                    f"supplied as None"
                )

    def _handle_none_referenced(
        self, eq, sub_lhs, sub_rhs, all_unknowns, none_refs,
    ) -> str:
        """An equation references one or more None-valued names. Try to
        evaluate; if it errors on None, skip; if it pins a None-supplied
        name to a value, raise inconsistent (per OQ 6).
        """
        if not all_unknowns:
            # Both sides reduced to constants — consistency-check.
            return self._consistency_check(eq, sub_lhs, sub_rhs)

        # Try a forward-eval if exactly one side is a bare-name unknown.
        # If the equation pins a None-supplied name, that's inconsistent.
        target_node = None
        value_node = None
        if (
            isinstance(sub_lhs, ast.Name) and sub_lhs.id in all_unknowns
        ):
            target_node, value_node = sub_lhs, sub_rhs
        elif (
            isinstance(sub_rhs, ast.Name) and sub_rhs.id in all_unknowns
        ):
            target_node, value_node = sub_rhs, sub_lhs

        if target_node is not None:
            target_name = target_node.id
            if target_name in none_refs and target_name in self._supplied_names:
                # User explicitly supplied None; equation tries to assign
                # a different value → inconsistent.
                try:
                    val = self._eval_node(value_node)
                except Exception:
                    return "skipped"
                raise ValidationError(
                    f"{self._loc(eq)}: equation `{eq.raw}` would "
                    f"assign {target_name}={val!r} but {target_name} was "
                    f"explicitly supplied as None"
                )
            # Otherwise: treat as a regular forward-eval.
            try:
                val = self._eval_node(value_node)
            except (TypeError, ValueError):
                return "skipped"
            self._assign_new(target_name, val, eq)
            return "resolved"

        # Couldn't pin a target. Try evaluating a constraint-style check.
        try:
            self._eval_node(sub_lhs)
            self._eval_node(sub_rhs)
        except (TypeError, ValueError):
            return "skipped"
        return "postponed"

    def _consistency_check(self, eq, sub_lhs, sub_rhs) -> str:
        try:
            lv = self._eval_node(sub_lhs)
            rv = self._eval_node(sub_rhs)
        except Exception:
            return "postponed"
        if self._values_equal(lv, rv):
            return "consistent"
        raise ValidationError(
            f"{self._loc(eq)}: equation violated: `{eq.raw}` "
            f"(lhs={lv!r}, rhs={rv!r})"
        )

    def _sympy_solve_one(self, eq, sub_lhs, sub_rhs, unknowns) -> str:
        if len(unknowns) > 1:
            return "postponed"

        import sympy as sp

        target = next(iter(unknowns))
        symbols = {n: sp.Symbol(n) for n in unknowns}
        try:
            lhs_expr = self._ast_to_sympy(sub_lhs, symbols)
            rhs_expr = self._ast_to_sympy(sub_rhs, symbols)
        except Exception:
            return "postponed"

        try:
            solutions = sp.solve(sp.Eq(lhs_expr, rhs_expr), symbols[target])
        except (NotImplementedError, Exception):
            return "postponed"
        if not solutions:
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}` has no solution"
            )

        numeric = self._extract_numeric(solutions)
        if not numeric:
            return "postponed"

        if len(numeric) == 1:
            # Single solution: assign directly. Per-Param validator
            # failures bubble up with their original message (e.g.,
            # "must be positive, got -5").
            self._assign_new(target, numeric[0], eq)
            return "resolved"

        # Multiple solutions: filter by per-Param validators first
        # (cheap), then by feasibility against the full constraint set
        # (expensive but necessary when the disambiguating bound lives
        # in a cross-equation constraint, e.g. ``angle < 180`` ruling
        # out the second branch of an asin solve).
        valid = self._filter_by_validators(target, numeric)
        if len(valid) > 1:
            valid = self._filter_by_feasibility(target, valid)
        if not valid:
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}`: no candidate "
                f"for {target} satisfies validators or constraints "
                f"(candidates: {numeric!r})"
            )
        if len(valid) > 1:
            shown = valid[:_AMBIGUOUS_LIST_LIMIT]
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}` has multiple "
                f"solutions for {target}: {shown!r}"
                + (" (truncated)" if len(valid) > _AMBIGUOUS_LIST_LIMIT else "")
            )

        self._assign_new(target, valid[0], eq)
        return "resolved"

    def _forward_assign(self, eq, target_name, value_node) -> str:
        try:
            value = self._eval_node(value_node)
        except Exception as exc:
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}` failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        self._assign_new(target_name, value, eq)
        return "resolved"

    # --- system solve ---

    def _system_solve(self) -> bool:
        """Hand all pending algebraic equations to sympy.solve as a
        system. Returns True if at least one new value was resolved.
        """
        import sympy as sp

        algebraic: list[tuple[int, ast.AST, ast.AST]] = []
        for i in self._pending_eqs:
            eq = self.equations[i]
            sub_lhs = substitute_knowns(eq.lhs, self.knowns, self._curated_ns)
            sub_rhs = substitute_knowns(eq.rhs, self.knowns, self._curated_ns)
            if is_fully_algebraic(sub_lhs) and is_fully_algebraic(sub_rhs):
                algebraic.append((i, sub_lhs, sub_rhs))

        if not algebraic:
            return False

        full_known_names = set(self.knowns) | set(self._curated_ns)
        unknowns: set[str] = set()
        for _, l, r in algebraic:
            unknowns |= find_unknowns(l, full_known_names)
            unknowns |= find_unknowns(r, full_known_names)
        if not unknowns:
            return False

        symbols = {n: sp.Symbol(n) for n in unknowns}
        sympy_eqs = []
        for _, l, r in algebraic:
            try:
                le = self._ast_to_sympy(l, symbols)
                re = self._ast_to_sympy(r, symbols)
                sympy_eqs.append(sp.Eq(le, re))
            except Exception:
                continue
        if not sympy_eqs:
            return False

        try:
            solutions = sp.solve(
                sympy_eqs, list(symbols.values()), dict=True,
            )
        except (NotImplementedError, Exception):
            return False

        algebraic_eqs = [self.equations[i] for i, _, _ in algebraic]

        if not solutions:
            raise ValidationError(
                f"{self._loc_multi(algebraic_eqs)}: equations are inconsistent "
                f"(no solution to the system)"
            )

        numeric_solutions = []
        for sol in solutions:
            try:
                cand = {sym.name: float(val.evalf()) for sym, val in sol.items()}
                numeric_solutions.append(cand)
            except (TypeError, ValueError, AttributeError):
                continue
        if not numeric_solutions:
            return False

        valid = []
        for cand in numeric_solutions:
            if self._candidate_passes_validators(cand):
                valid.append(cand)
        # When several candidates pass per-Param validators, narrow by
        # full-system feasibility — propagate each candidate forward
        # through the equation system and reject any that violate a
        # cross-equation constraint.
        if len(valid) > 1:
            valid = self._filter_systems_by_feasibility(valid)
        if not valid:
            raise ValidationError(
                f"{self._loc_multi(algebraic_eqs)}: equations have no "
                f"solution satisfying validators or constraints "
                f"(candidates: {numeric_solutions[:_AMBIGUOUS_LIST_LIMIT]!r})"
            )
        if len(valid) > 1:
            shown = valid[:_AMBIGUOUS_LIST_LIMIT]
            raise ValidationError(
                f"{self._loc_multi(algebraic_eqs)}: equations have multiple "
                f"solutions: {shown!r}"
                + (" (truncated)" if len(valid) > _AMBIGUOUS_LIST_LIMIT else "")
            )

        for name, value in valid[0].items():
            self._assign_new(name, value, raw_for_msg="system-solve")
        return True

    # --- assignment & validator helpers ---

    def _assign_new(self, name: str, value: Any, eq=None, raw_for_msg=None):
        # Consistency check if name was already known with a different value.
        if name in self.knowns and self.knowns[name] is not None:
            if not self._values_equal(self.knowns[name], value):
                raw = (
                    eq.raw if eq is not None
                    else (raw_for_msg or "system-solve")
                )
                prefix = (
                    self._loc(eq) if eq is not None else self.component_name
                )
                raise ValidationError(
                    f"{prefix}: equation `{raw}` would "
                    f"assign {name}={value!r} but {name} is already "
                    f"{self.knowns[name]!r}"
                )
            return  # no change

        # OQ 6: explicit None supplied + equation pinning value → inconsistent.
        if (
            name in self._supplied_names
            and self.knowns.get(name) is None
            and value is not None
        ):
            raw = (
                eq.raw if eq is not None
                else (raw_for_msg or "system-solve")
            )
            prefix = (
                self._loc(eq) if eq is not None else self.component_name
            )
            raise ValidationError(
                f"{prefix}: equation `{raw}` would assign "
                f"{name}={value!r} but {name} was explicitly supplied as None"
            )

        self.knowns[name] = value
        # Run validators on newly assigned value.
        param = self.params.get(name)
        if param is not None and value is not None:
            for validator in param.validators:
                try:
                    validator(value)
                except ValidationError as exc:
                    raise ValidationError(
                        f"{self.component_name}.{name}: {exc}"
                    ) from exc

    def _filter_by_validators(self, name: str, candidates: list[float]) -> list[float]:
        param = self.params.get(name)
        if param is None or not param.validators:
            return list(candidates)
        out = []
        for v in candidates:
            ok = True
            for validator in param.validators:
                try:
                    validator(v)
                except ValidationError:
                    ok = False
                    break
            if ok:
                out.append(v)
        return out

    def _candidate_passes_validators(self, cand: dict[str, float]) -> bool:
        for name, value in cand.items():
            param = self.params.get(name)
            if param is None:
                continue
            for validator in param.validators:
                try:
                    validator(value)
                except ValidationError:
                    return False
        return True

    def _filter_by_feasibility(
        self, target: str, candidates: list[float],
    ) -> list[float]:
        """Drop candidates whose tentative assignment violates a constraint.

        For each candidate value of ``target``, simulate forward through
        the equation system using forward-evaluation only (no sympy) and
        check every constraint whose names become known. A candidate
        whose downstream values would violate any constraint is dropped.

        Used to disambiguate sympy multi-solution returns when the
        deciding bound lives in a cross-equation constraint
        (e.g. ``angle < 180`` ruling out one branch of an asin).
        """
        survivors: list[float] = []
        for cand in candidates:
            tentative = dict(self.knowns)
            tentative[target] = cand

            # Forward-eval pass: keep substituting+evaluating until no
            # new values resolve. Bounded by the number of unresolved
            # equations.
            progress = True
            while progress:
                progress = False
                for eq in self.equations:
                    bare = None
                    if (
                        isinstance(eq.lhs, ast.Name)
                        and eq.lhs.id not in tentative
                    ):
                        bare = (eq.lhs.id, eq.rhs)
                    elif (
                        isinstance(eq.rhs, ast.Name)
                        and eq.rhs.id not in tentative
                    ):
                        bare = (eq.rhs.id, eq.lhs)
                    if bare is None:
                        continue
                    name, expr = bare
                    sub = substitute_knowns(expr, tentative, self._curated_ns)
                    full_known = set(tentative) | set(self._curated_ns)
                    if find_unknowns(sub, full_known):
                        continue
                    try:
                        val = self._eval_substituted(sub, tentative)
                    except Exception:
                        continue
                    tentative[name] = val
                    progress = True

            # Check every constraint whose names are known in the
            # tentative world. Any failure rules out this candidate.
            full_known = set(tentative) | set(self._curated_ns)
            feasible = True
            for c in self.constraints:
                if find_unknowns(c.expr, full_known):
                    continue
                try:
                    sub = substitute_knowns(c.expr, tentative, self._curated_ns)
                    val = self._eval_substituted(sub, tentative)
                except Exception:
                    continue
                if not val:
                    feasible = False
                    break
            if feasible:
                survivors.append(cand)
        return survivors

    def _filter_systems_by_feasibility(
        self, candidates: list[dict[str, float]],
    ) -> list[dict[str, float]]:
        """Drop system-solve candidate dicts whose values violate any
        cross-equation constraint.

        Each candidate is a ``{name: value}`` dict that satisfies the
        algebraic system. Apply the candidate to a tentative knowns
        copy, propagate forward through any equations that resolve, and
        reject the candidate if any constraint fails.
        """
        survivors: list[dict[str, float]] = []
        for cand in candidates:
            tentative = dict(self.knowns)
            tentative.update(cand)
            progress = True
            while progress:
                progress = False
                for eq in self.equations:
                    bare = None
                    if (
                        isinstance(eq.lhs, ast.Name)
                        and eq.lhs.id not in tentative
                    ):
                        bare = (eq.lhs.id, eq.rhs)
                    elif (
                        isinstance(eq.rhs, ast.Name)
                        and eq.rhs.id not in tentative
                    ):
                        bare = (eq.rhs.id, eq.lhs)
                    if bare is None:
                        continue
                    name, expr = bare
                    sub = substitute_knowns(expr, tentative, self._curated_ns)
                    full_known = set(tentative) | set(self._curated_ns)
                    if find_unknowns(sub, full_known):
                        continue
                    try:
                        val = self._eval_substituted(sub, tentative)
                    except Exception:
                        continue
                    tentative[name] = val
                    progress = True

            full_known = set(tentative) | set(self._curated_ns)
            feasible = True
            for c in self.constraints:
                if find_unknowns(c.expr, full_known):
                    continue
                try:
                    sub = substitute_knowns(c.expr, tentative, self._curated_ns)
                    val = self._eval_substituted(sub, tentative)
                except Exception:
                    continue
                if not val:
                    feasible = False
                    break
            if feasible:
                survivors.append(cand)
        return survivors

    def _eval_substituted(self, sub_node: ast.AST, tentative: dict) -> Any:
        """Compile and eval an AST node in a curated+tentative namespace."""
        expr_node = ast.Expression(body=sub_node)
        ast.fix_missing_locations(expr_node)
        code = compile(expr_node, "<feasibility>", "eval")
        ns = {**self._curated_ns, **tentative, "__builtins__": {}}
        return eval(code, ns)

    # --- constraint evaluation ---

    def _check_pending_constraints(self) -> bool:
        progress = False
        full_ns = {**self._curated_ns, **self.knowns, "__builtins__": {}}
        full_known_names = set(self.knowns) | set(self._curated_ns)
        for i in list(self._pending_constraints):
            c = self.constraints[i]
            unknowns = find_unknowns(c.expr, full_known_names)
            if unknowns:
                continue  # not yet evaluable
            try:
                expr_node = ast.Expression(body=c.expr)
                ast.fix_missing_locations(expr_node)
                code = compile(expr_node, "<constraint>", "eval")
                result = eval(code, full_ns)
            except (TypeError, ValueError):
                # None propagation → skip silently.
                self._pending_constraints.remove(i)
                progress = True
                continue
            except Exception as exc:
                raise ValidationError(
                    f"{self._loc(c)}: constraint `{c.raw}` "
                    f"failed to evaluate: {exc}"
                ) from exc
            self._pending_constraints.remove(i)
            progress = True
            if not result:
                # If the constraint is a name-vs-numeric form, the same
                # check is attached as a per-Param validator. Run it and
                # let its specific error message bubble up
                # ("must be positive, got -1") instead of the generic
                # constraint-violated message.
                pp_result = extract_per_param_validator(c)
                if pp_result is not None:
                    name, validator = pp_result
                    value = self.knowns.get(name)
                    if value is not None:
                        try:
                            validator(value)
                        except ValidationError as exc:
                            raise ValidationError(
                                f"{self.component_name}.{name}: {exc}"
                            ) from exc
                detail = _enrich_constraint_failure(c.expr, full_ns)
                msg = f"{self._loc(c)}: constraint violated: `{c.raw}`"
                if detail:
                    msg += f": {detail}"
                raise ValidationError(msg)
        return progress

    # --- error messages ---

    def _raise_insufficient(self):
        full_known_names = set(self.knowns) | set(self._curated_ns)
        unresolved: set[str] = set()
        pending_eqs = []
        for i in self._pending_eqs:
            eq = self.equations[i]
            pending_eqs.append(eq)
            sub_lhs = substitute_knowns(eq.lhs, self.knowns, self._curated_ns)
            sub_rhs = substitute_knowns(eq.rhs, self.knowns, self._curated_ns)
            unresolved |= find_unknowns(sub_lhs, full_known_names)
            unresolved |= find_unknowns(sub_rhs, full_known_names)
        given = sorted(
            n for n in self._supplied_names if self.knowns.get(n) is not None
        )
        # Enumerate sufficient input combinations to help the caller.
        subsets = _sufficient_subsets(pending_eqs, set(self.knowns))
        if subsets:
            combos = ", ".join(
                "{" + ", ".join(sorted(s)) + "}" for s in subsets[:8]
            )
        else:
            combos = "{" + ", ".join(sorted(unresolved)) + "}"
        raise ValidationError(
            f"{self.component_name}: cannot solve for equation variables: "
            f"given {{{', '.join(given) or 'none'}}}, "
            f"need one of: {combos}"
        )

    # --- AST → sympy ---

    def _ast_to_sympy(self, node: ast.AST, symbols: dict[str, Any]):
        """Convert a fully-algebraic AST to a sympy expression, sympifying
        any Names that resolve to concrete values in ``self.knowns``.
        """
        return ast_to_sympy(node, symbols, knowns=self.knowns)

    # --- helpers ---

    def _eval_node(self, node: ast.AST) -> Any:
        full_ns = {**self._curated_ns, **self.knowns, "__builtins__": {}}
        expr = ast.Expression(body=node)
        ast.fix_missing_locations(expr)
        code = compile(expr, "<resolver>", "eval")
        return eval(code, full_ns)

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Tolerance-aware equality for consistency checks.

        Relative tolerance of 1e-6 (sub-micron in mm-scale CAD) with an
        absolute floor of 1e-9 for near-zero values. Loose enough to
        accept hand-typed values against full-precision sympy results
        (`1.41421356` vs sympy's `1.4142135623730951` for sqrt(2)),
        tight enough to reject any genuinely different values.
        """
        if a is None or b is None:
            return a is b
        try:
            af = float(a)
            bf = float(b)
        except (TypeError, ValueError):
            return a == b
        magnitude = max(abs(af), abs(bf))
        tolerance = max(1e-6 * magnitude, 1e-9)
        return abs(af - bf) <= tolerance

    def _extract_numeric(self, solutions) -> list[float]:
        out: list[float] = []
        for sol in solutions:
            try:
                out.append(float(sol.evalf()))
            except (TypeError, ValueError, AttributeError):
                # Symbolic / interval / conditional → not numeric.
                continue
        return out
