"""Optional-default override-pattern recognition.

An equation whose bare-Name target is an optional name (``?n = ...``)
becomes the *override* pattern when its RHS evaluates to a definite
non-None value with the target bound to None. The dry-run discriminator
here decides three categories: ``"override"`` (pre-resolve fills the
target), ``"unsafe"`` (RHS raises on None — class-define-time error),
and ``"defer"`` (let the iterative loop fill it normally).
"""

from __future__ import annotations

import ast
from typing import Any

from scadwright.component.resolver.types import (
    ParsedEquation,
    equation_bare_targets,
)
from scadwright.component.resolver_ast import _free_names as _free_names_in


def _override_rhs_dry_run(
    target_name: str, rhs: ast.AST,
) -> str:
    """Dry-run an override RHS with ``target_name`` bound to None.

    Returns one of three strings:

    - ``"override"`` — the RHS evaluates to a definite non-None value
      when the target is None. The equation is the optional-default
      override pattern; the resolver should pre-resolve it.
    - ``"unsafe"`` — the RHS raises ``TypeError`` or ``ValueError``
      when the target is None (e.g., ``target + 1``, ``len(target)``,
      ``max(target, 1)``). The equation is malformed for an override
      and should be rejected at class-define time.
    - ``"defer"`` — the RHS depends on other names that aren't yet
      known (NameError), or its evaluation requires runtime info we
      can't simulate. Treat as not-an-override; the resolver's
      iterative loop will fill the target normally if possible.

    The other free names in the RHS are bound to a sentinel that
    behaves benignly under common operations so the discriminator
    isn't fooled by side-effect-free uses of those names.
    """
    if target_name not in _free_names_in(rhs):
        # No self-reference; not an override pattern. The iterative
        # loop will forward-eval the RHS normally.
        return "defer"

    from scadwright.component.equations import (
        _CURATED_BUILTINS, _CURATED_MATH,
    )

    ns: dict[str, Any] = {**_CURATED_BUILTINS, **_CURATED_MATH}
    ns[target_name] = None
    ns["__builtins__"] = {}

    try:
        expr_node = ast.Expression(body=rhs)
        ast.fix_missing_locations(expr_node)
        code = compile(expr_node, "<override-check>", "eval")
        result = eval(code, ns)
    except NameError:
        return "defer"
    except (TypeError, ValueError):
        return "unsafe"
    except Exception:
        return "defer"

    # The RHS evaluated. If it produced None, the override pattern
    # would default the target back to None — useless. Treat as
    # defer so the iterative loop has a chance.
    if result is None:
        return "defer"
    return "override"


def _classify_override_targets(
    equations: list[ParsedEquation],
    optional_names: frozenset[str],
) -> dict[int, tuple[str, str]]:
    """For each equation whose bare-Name target is an optional name,
    classify via :func:`_override_rhs_dry_run`.

    Returns a dict mapping equation index → (target_name, classification)
    where classification is ``"override"``, ``"unsafe"``, or ``"defer"``.
    Equations without an optional-name bare-Name target are absent.
    """
    out: dict[int, tuple[str, str]] = {}
    for i, eq in enumerate(equations):
        target_name = None
        rhs_node = None
        for name, other in equation_bare_targets(eq):
            if name in optional_names:
                target_name = name
                rhs_node = other
                break
        if target_name is None:
            continue
        out[i] = (target_name, _override_rhs_dry_run(target_name, rhs_node))
    return out
