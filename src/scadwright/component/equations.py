"""Equation-based Component parameter solving.

Components can declare a list of equations relating their Params:

    class Tube(Component):
        id  = Param(float, positive=True)
        od  = Param(float, positive=True)
        thk = Param(float, positive=True)
        equations = ["od == id + 2*thk"]

At instantiation, the framework solves for whichever Params the user didn't
supply. Under-, over-, and inconsistent-specification all raise clear
ValidationErrors. Params with defaults act as fallbacks when the solver needs
more input.

This module is the pure logic layer — no Component coupling. The wiring
lives in `scadwright.component.base`.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable, Sequence

from scadwright.errors import ValidationError


def _require_sympy():
    """Import sympy, or raise ImportError with extras-install hint."""
    try:
        import sympy  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "Components with `equations` require sympy. "
            "Install with: pip install 'scadwright[equations]'"
        ) from e


@dataclass(frozen=True)
class ParsedEquations:
    """Class-definition-time representation of an `equations` declaration."""

    equations: tuple  # tuple of sympy.Eq
    equation_vars: frozenset[str]
    symbol_cache: dict  # name -> sympy.Symbol


def parse_equations(
    eq_strs: Sequence[str], declared_params: Iterable[str]
) -> ParsedEquations:
    """Parse `equations = [...]` into sympy Eq objects.

    Validates that every free symbol (minus well-known math constants) names a
    declared Param. Raises ValidationError at class-definition time on typos
    or unparseable input.
    """
    _require_sympy()
    import sympy as sp

    declared = set(declared_params)
    # Known sympy constants we should not treat as equation variables.
    constants = {sp.pi, sp.E, sp.I, sp.oo, sp.zoo, sp.nan, sp.EulerGamma, sp.Catalan}

    equations = []
    symbol_cache: dict[str, Any] = {name: sp.Symbol(name) for name in declared}
    all_vars: set[str] = set()

    for i, raw in enumerate(eq_strs):
        if "==" in raw:
            lhs_s, rhs_s = raw.split("==", 1)
        elif "=" in raw:
            # Permissive: accept single `=` too; sympify can't parse it directly.
            lhs_s, rhs_s = raw.split("=", 1)
        else:
            raise ValidationError(
                f"equations[{i}]: missing '==' (or '='): {raw!r}"
            )
        try:
            # Pass declared params as locals so names like `id` (a Python
            # builtin) resolve to sympy Symbols, not the builtin.
            lhs = sp.sympify(lhs_s.strip(), locals=symbol_cache)
            rhs = sp.sympify(rhs_s.strip(), locals=symbol_cache)
        except (sp.SympifyError, SyntaxError, TypeError) as exc:
            raise ValidationError(
                f"equations[{i}]: cannot parse {raw!r}: {exc}"
            ) from exc
        eq = sp.Eq(lhs, rhs)
        equations.append(eq)

        for sym in eq.free_symbols:
            if sym in constants:
                continue
            all_vars.add(sym.name)

    # Every equation-variable must correspond to a declared Param.
    unknown = sorted(all_vars - declared)
    if unknown:
        hints = []
        for u in unknown:
            close = difflib.get_close_matches(u, declared, n=1, cutoff=0.6)
            if close:
                hints.append(f"{u!r} (did you mean {close[0]!r}?)")
            else:
                hints.append(repr(u))
        raise ValidationError(
            f"equations reference undeclared Param(s): {', '.join(hints)}. "
            f"Declared: {sorted(declared)}"
        )

    return ParsedEquations(
        equations=tuple(equations),
        equation_vars=frozenset(all_vars),
        symbol_cache=dict(symbol_cache),
    )


def _format_eq(eq) -> str:
    """User-readable form of a sympy Eq."""
    import sympy as sp

    return f"{sp.sstr(eq.lhs)} == {sp.sstr(eq.rhs)}"


def _tolerance(*values: float) -> float:
    """Scale-aware tolerance for equation residual checks."""
    return 1e-9 * max((abs(float(v)) for v in values), default=1.0)


def _check_consistency(parsed: ParsedEquations, values: dict[str, float]) -> None:
    """Verify every equation holds to tolerance given the fully-populated values dict."""
    import sympy as sp

    subs = {parsed.symbol_cache[k]: v for k, v in values.items() if k in parsed.symbol_cache}
    for eq in parsed.equations:
        lhs_v = float(eq.lhs.evalf(subs=subs))
        rhs_v = float(eq.rhs.evalf(subs=subs))
        if abs(lhs_v - rhs_v) > _tolerance(lhs_v, rhs_v):
            details = ", ".join(f"{k}={v}" for k, v in values.items() if k in parsed.equation_vars)
            raise ValidationError(
                f"equation violated: `{_format_eq(eq)}` "
                f"(given {details}: lhs={lhs_v}, rhs={rhs_v})"
            )


def _substitute_and_reduce(parsed: ParsedEquations, given: dict[str, float]) -> list:
    """Substitute known values into each equation and numerically reduce.

    Returns the equations that still contain unknowns. Drops equations
    that evaluated to ``True`` (auto-satisfied by the substitution) and
    raises ``ValidationError`` for any that evaluated to ``False`` (the
    user's inputs are mutually inconsistent).

    The ``.evalf()`` step forces numeric reduction of transcendental
    terms (cos, sin, etc.) before ``sp.solve`` sees them. Without it,
    sympy attempts symbolic simplification on ``cos(some_float * pi /
    180)`` for non-special angles, which can take tens of seconds
    (pressure_angle=14.5 vs. the trivial pressure_angle=20). Skip
    evalf on ``BooleanTrue``/``False`` since those are already fully
    reduced sentinels.
    """
    import sympy as sp

    subs = {parsed.symbol_cache[k]: sp.sympify(v) for k, v in given.items()}

    def _sub(eq):
        s = eq.subs(subs)
        return s if s is sp.true or s is sp.false else s.evalf()

    substituted = []
    for orig, eq in zip(parsed.equations, [_sub(eq) for eq in parsed.equations]):
        if eq is sp.true:
            continue  # auto-satisfied; drop from the system
        if eq is sp.false:
            details = ", ".join(f"{k}={v}" for k, v in given.items())
            raise ValidationError(
                f"equation violated: `{_format_eq(orig)}` (given {details})"
            )
        substituted.append(eq)
    return substituted


def _extract_numeric_solutions(solutions: list) -> list[dict[str, float]]:
    """Convert sympy's ``solve(..., dict=True)`` output to ``{name: float}``
    dicts. Drops solutions that don't reduce to concrete floats (treated
    as underdetermined by the caller).
    """
    numeric_solutions = []
    for sol in solutions:
        try:
            numeric = {sym.name: float(val.evalf()) for sym, val in sol.items()}
            numeric_solutions.append(numeric)
        except (TypeError, AttributeError):
            continue
    return numeric_solutions


def _try_solve(parsed: ParsedEquations, given: dict[str, float]) -> dict[str, float] | None:
    """Attempt to solve for the unknowns given the provided values.

    Returns dict of solved name->value on success. Returns None if
    underspecified (not enough to uniquely determine unknowns). Raises
    ValidationError on multiple non-eliminable solutions or on inconsistency.
    """
    import sympy as sp

    unknowns = [parsed.symbol_cache[n] for n in parsed.equation_vars if n not in given]
    if not unknowns:
        # All equation vars given — consistency-check and return.
        _check_consistency(parsed, dict(given))
        return {}

    substituted = _substitute_and_reduce(parsed, given)
    if not substituted:
        return None  # unknowns exist but every equation auto-satisfied

    try:
        solutions = sp.solve(substituted, unknowns, dict=True)
    except NotImplementedError:
        return None  # sympy can't solve; treat as underdetermined

    if not solutions:
        # Either inconsistent or underdetermined. If an equation became a
        # non-trivial constant (e.g. 10 == 12 still in symbolic form), it's
        # inconsistent; otherwise underdetermined.
        for eq in substituted:
            if not eq.free_symbols and sp.simplify(sp.sympify(eq.lhs) - sp.sympify(eq.rhs)) != 0:
                raise ValidationError(
                    f"equation violated after substitution: `{_format_eq(eq)}`"
                )
        return None

    numeric_solutions = _extract_numeric_solutions(solutions)
    if not numeric_solutions:
        return None
    if len(numeric_solutions) == 1:
        return numeric_solutions[0]
    # Multiple numeric solutions — caller filters by validators.
    return {"__multi__": numeric_solutions}  # type: ignore[dict-item]


def _filter_by_validators(
    candidates: list[dict[str, float]], param_descriptors: dict
) -> list[dict[str, float]]:
    """Drop candidates where any solved value fails its Param's validators."""
    surviving = []
    for cand in candidates:
        ok = True
        for name, value in cand.items():
            p = param_descriptors.get(name)
            if p is None:
                continue
            for v in p.validators:
                try:
                    v(value)
                except ValidationError:
                    # Only ValidationError signals "this candidate is invalid";
                    # other exceptions mean the validator itself is buggy and
                    # should surface, not silently drop the candidate.
                    ok = False
                    break
            if not ok:
                break
        if ok:
            surviving.append(cand)
    return surviving


def _sufficient_subsets_with_defaults(
    parsed: ParsedEquations,
    eq_vars_with_defaults: set[str],
) -> list[frozenset[str]]:
    """Enumerate minimal user-input subsets that, together with Param defaults,
    suffice to solve the system. Used only in error messages.
    """
    import sympy as sp

    eq_vars = list(parsed.equation_vars)
    n_eqs = len(parsed.equations)
    n_vars = len(eq_vars)
    min_given = n_vars - n_eqs  # free variables the user must pin

    # We enumerate by input-subset size. Smallest first, so the error lists
    # the easiest paths.
    sufficient: list[frozenset[str]] = []
    for size in range(max(0, min_given - len(eq_vars_with_defaults)), n_vars + 1):
        for combo in combinations(eq_vars, size):
            combo_set = frozenset(combo)
            # With defaults filling in absent eq_vars that have defaults:
            effective = combo_set | (eq_vars_with_defaults - combo_set)
            if len(effective) < min_given:
                continue
            # Try solving with dummy values.
            dummy_given = {v: 1.0 for v in effective}
            try:
                res = _try_solve(parsed, dummy_given)
            except ValidationError:
                # Consistency failure with dummy values is fine — it means
                # the combo *would* be solvable with real values.
                res = {}
            if res is not None:
                sufficient.append(combo_set)
    # Dedupe and return minimal subsets (drop any subset that's a strict superset
    # of another).
    sufficient.sort(key=len)
    minimal: list[frozenset[str]] = []
    for s in sufficient:
        if not any(m < s for m in minimal):
            minimal.append(s)
    return minimal


def classify_equation(eq_str: str) -> str:
    """Return ``"equality"``, ``"constraint"``, or ``"cross_constraint"``.

    - Equalities contain ``==`` (or a single ``=`` that is not ``>=``/``<=``).
    - Constraints have an inequality operator with a numeric RHS — they
      compile to a per-Param validator (``"x > 0"``, ``"x, y >= -5"``).
    - Cross-constraints have an inequality with a non-numeric RHS — they
      reference other Params or expressions (``"id < od"``,
      ``"cap_height < 2 * sphere_r"``) and are evaluated after all Params
      are set.
    """
    import re as _re

    s = eq_str.strip()
    if "==" in s:
        return "equality"
    m = _re.search(r'(>=|<=|>|<)', s)
    if m:
        rhs_part = s[m.end():].strip()
        try:
            float(rhs_part)
            return "constraint"
        except ValueError:
            return "cross_constraint"
    if "=" in s:
        return "equality"
    raise ValidationError(
        f"cannot classify equation (no operator found): {eq_str!r}"
    )


def extract_equality_symbols(eq_str: str, known_params: Iterable[str] = ()) -> set[str]:
    """Return the set of free-symbol names in an equality equation string.

    Uses sympy to parse the expression, then filters out known constants
    and function names. ``known_params`` are pre-declared names that should
    resolve as Symbols (not Python builtins like ``id``).
    """
    _require_sympy()
    import sympy as sp
    import re as _re
    import keyword as _kw

    if "==" in eq_str:
        lhs_s, rhs_s = eq_str.split("==", 1)
    else:
        lhs_s, rhs_s = eq_str.split("=", 1)

    # Pre-scan the expression text for identifiers and create Symbol locals
    # for all of them. This prevents names like `id` from resolving to
    # Python builtins during sympify.
    identifiers = set(_re.findall(r'\b([a-zA-Z_]\w*)\b', lhs_s + rhs_s))
    # Filter out Python keywords, sympy function names, and known constants.
    _sympy_funcs = {"sin", "cos", "tan", "sqrt", "log", "exp", "abs",
                    "asin", "acos", "atan", "atan2", "pi", "E", "I",
                    "ceiling", "floor", "Abs", "sign", "Max", "Min"}
    locals_dict = {}
    for ident in identifiers:
        if ident in _sympy_funcs or _kw.iskeyword(ident):
            continue
        locals_dict[ident] = sp.Symbol(ident)
    # Also include any known params.
    for name in known_params:
        locals_dict[name] = sp.Symbol(name)

    try:
        lhs = sp.sympify(lhs_s.strip(), locals=locals_dict)
        rhs = sp.sympify(rhs_s.strip(), locals=locals_dict)
    except (sp.SympifyError, SyntaxError, TypeError) as exc:
        raise ValidationError(
            f"cannot parse equation {eq_str!r}: {exc}"
        ) from exc

    constants = {sp.pi, sp.E, sp.I, sp.oo, sp.zoo, sp.nan, sp.EulerGamma, sp.Catalan}
    names = set()
    for sym in (lhs.free_symbols | rhs.free_symbols):
        if sym not in constants:
            names.add(sym.name)
    return names


def parse_constraints(
    constraint_strs: Sequence[str],
) -> dict[str, list]:
    """Parse inequality constraint strings into per-param validator callables.

    Supports comma-expanded forms like ``"x, y, z > 0"`` which expand to
    three individual constraints. Returns a dict mapping param names to
    lists of validator callables.

    Supported operators: ``>``, ``>=``, ``<``, ``<=``.
    """
    from scadwright.component.params import (
        _positive_impl,
        _non_negative_impl,
        _minimum_impl,
        _maximum_impl,
    )
    import re

    result: dict[str, list] = {}

    for raw in constraint_strs:
        s = raw.strip()
        # Detect the operator: try longest first to avoid >= matching as >.
        m = re.search(r'(>=|<=|>|<)', s)
        if not m:
            raise ValidationError(
                f"constraint has no inequality operator: {raw!r}"
            )
        op = m.group(1)
        lhs_part = s[:m.start()].strip()
        rhs_part = s[m.end():].strip()

        # Parse the RHS as a number.
        try:
            bound = float(rhs_part)
        except ValueError:
            raise ValidationError(
                f"constraint RHS must be a number, got {rhs_part!r} in {raw!r}"
            )

        # Expand comma-separated LHS names.
        names = [n.strip() for n in lhs_part.replace(" ", ",").split(",") if n.strip()]
        if not names:
            raise ValidationError(
                f"constraint has no variable names: {raw!r}"
            )

        # Map to validator callables, using builtins for common patterns.
        for name in names:
            if op == ">" and bound == 0:
                validator = _positive_impl
            elif op == ">=" and bound == 0:
                validator = _non_negative_impl
            elif op == ">=":
                validator = _minimum_impl(bound)
            elif op == ">":
                validator = _minimum_impl(bound)  # strictly > N: use min(N) + check
                # For strict >, we need a custom validator.
                _bound = bound
                def _strict_gt(x, _b=_bound):
                    if not (x > _b):
                        raise ValidationError(f"must be > {_b}, got {x}")
                validator = _strict_gt
            elif op == "<=":
                validator = _maximum_impl(bound)
            elif op == "<":
                _bound = bound
                def _strict_lt(x, _b=_bound):
                    if not (x < _b):
                        raise ValidationError(f"must be < {_b}, got {x}")
                validator = _strict_lt
            else:
                raise ValidationError(f"unsupported constraint operator: {op!r}")

            result.setdefault(name, []).append(validator)

    return result


def parse_cross_constraints(
    cross_strs: Sequence[str], declared_params: Iterable[str]
) -> tuple[list[tuple], set[str]]:
    """Parse var-vs-var inequality constraints into evaluable sympy form.

    Returns (compiled, referenced_symbols) where ``compiled`` is a list of
    ``(lhs_expr, op, rhs_expr, raw_str)`` tuples ready for runtime
    evaluation, and ``referenced_symbols`` is the set of identifier names
    appearing on either side (caller uses this to auto-declare any
    undeclared Params).
    """
    _require_sympy()
    import re as _re
    import sympy as sp

    declared = set(declared_params)
    compiled: list[tuple] = []
    referenced: set[str] = set()
    constants = {sp.pi, sp.E, sp.I, sp.oo, sp.zoo, sp.nan, sp.EulerGamma, sp.Catalan}
    _sympy_funcs = {"sin", "cos", "tan", "sqrt", "log", "exp", "abs",
                    "asin", "acos", "atan", "atan2", "pi", "E", "I",
                    "ceiling", "floor", "Abs", "sign", "Max", "Min"}

    for raw in cross_strs:
        s = raw.strip()
        m = _re.search(r'(>=|<=|>|<)', s)
        if not m:
            raise ValidationError(
                f"cross-constraint missing inequality operator: {raw!r}"
            )
        op = m.group(1)
        lhs_part = s[:m.start()].strip()
        rhs_part = s[m.end():].strip()

        # Build a symbol-locals dict covering every identifier in the
        # expression, so e.g. `id` resolves to a Symbol rather than the
        # Python builtin.
        idents = set(_re.findall(r'\b([a-zA-Z_]\w*)\b', lhs_part + " " + rhs_part))
        symbol_cache = {n: sp.Symbol(n) for n in idents if n not in _sympy_funcs}
        for name in declared:
            symbol_cache.setdefault(name, sp.Symbol(name))

        try:
            rhs = sp.sympify(rhs_part, locals=symbol_cache)
        except (sp.SympifyError, SyntaxError, TypeError) as exc:
            raise ValidationError(
                f"cross-constraint cannot parse RHS {rhs_part!r} in {raw!r}: {exc}"
            ) from exc

        # LHS may be comma-expanded: `"a, b < c"` → two constraints.
        lhs_chunks = [
            n.strip()
            for n in lhs_part.replace(" ", ",").split(",")
            if n.strip()
        ]
        if not lhs_chunks:
            raise ValidationError(
                f"cross-constraint has no LHS in {raw!r}"
            )

        for chunk in lhs_chunks:
            try:
                lhs = sp.sympify(chunk, locals=symbol_cache)
            except (sp.SympifyError, SyntaxError, TypeError) as exc:
                raise ValidationError(
                    f"cross-constraint cannot parse LHS {chunk!r} in {raw!r}: {exc}"
                ) from exc
            compiled.append((lhs, op, rhs, raw))
            for sym in lhs.free_symbols | rhs.free_symbols:
                if sym not in constants:
                    referenced.add(sym.name)

    return compiled, referenced


def evaluate_cross_constraints(
    compiled: list[tuple],
    values: dict[str, Any],
    component_name: str,
) -> None:
    """Evaluate compiled cross-constraints with the populated Param values.

    Raises ``ValidationError`` on the first violated constraint, with a
    message naming the constraint and the offending values.
    """
    if not compiled:
        return
    import sympy as sp

    # Only numeric Params can be substituted into a sympy expression.
    # String/bool/object Params (like a `slant="outwards"`) are skipped.
    subs = {
        sp.Symbol(k): float(v)
        for k, v in values.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }

    for lhs, op, rhs, raw in compiled:
        # Skip constraints whose referenced Params are opt-out (None) —
        # mirrors the behavior of per-Param validators on optional Params.
        refs = {s.name for s in (lhs.free_symbols | rhs.free_symbols)}
        if any(values.get(name) is None for name in refs):
            continue
        try:
            lhs_v = float(lhs.evalf(subs=subs))
            rhs_v = float(rhs.evalf(subs=subs))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"{component_name}: cross-constraint {raw!r} cannot be "
                f"evaluated (missing values?): {exc}"
            ) from exc

        ok = {
            ">":  lhs_v >  rhs_v,
            ">=": lhs_v >= rhs_v,
            "<":  lhs_v <  rhs_v,
            "<=": lhs_v <= rhs_v,
        }[op]
        if not ok:
            ref_names = sorted({s.name for s in (lhs.free_symbols | rhs.free_symbols)})
            details = ", ".join(
                f"{n}={values[n]}" for n in ref_names if n in values
            )
            # Show the expanded form (e.g. `a < c` from raw `a, b < c`).
            expanded = f"{sp.sstr(lhs)} {op} {sp.sstr(rhs)}"
            raise ValidationError(
                f"{component_name}: constraint violated: {expanded} (with {details})"
            )


def solve_instance(
    parsed: ParsedEquations,
    given: dict[str, float],
    defaults: dict[str, float],
    param_descriptors: dict,
) -> dict[str, float]:
    """Resolve missing equation-variables from given + defaults.

    Returns a dict mapping newly-resolved Param names to values. Does NOT
    include values already in `given`.
    """
    import sympy as sp

    # Step 1: try solving with just the user-given values.
    result = _try_solve(parsed, given)

    # Step 2: if underspecified, apply defaults and retry.
    applied_defaults: dict[str, float] = {}
    if result is None and defaults:
        combined = {**given, **defaults}
        result = _try_solve(parsed, combined)
        if result is not None:
            applied_defaults = {k: v for k, v in defaults.items() if k not in given}

    if result is None:
        # Still underspecified — enumerate sufficient subsets for the error.
        eq_vars_with_defaults = set(defaults.keys())
        subsets = _sufficient_subsets_with_defaults(parsed, eq_vars_with_defaults)
        combos = ", ".join(
            "{" + ", ".join(sorted(s)) + "}" for s in subsets[:8]
        ) or "(no sufficient combination found)"
        given_str = ", ".join(sorted(given.keys())) or "(none)"
        raise ValidationError(
            f"cannot solve for equation variables: given {{{given_str}}}, "
            f"need one of: {combos}"
        )

    # Handle multi-solution case: filter by validators.
    if "__multi__" in result:
        candidates = result["__multi__"]  # type: ignore[assignment]
        surviving = _filter_by_validators(candidates, param_descriptors)
        if len(surviving) == 0:
            raise ValidationError(
                f"no solution satisfies all Param validators; candidates were: "
                f"{candidates}"
            )
        if len(surviving) > 1:
            raise ValidationError(
                f"multiple valid solutions: {surviving} — add a validator "
                f"(e.g. positive=True) to disambiguate"
            )
        result = surviving[0]

    # Merge any defaults we used into the returned set so callers assign them too.
    merged = {**applied_defaults, **result}
    return merged
