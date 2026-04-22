"""Animation and viewpoint support.

Two pieces:

- `t()` — returns a SymbolicExpr standing for OpenSCAD's `$t` animation
  variable. Arithmetic with `t()` (and Python floats) builds an expression
  tree that emits as SCAD source instead of a resolved Python number, so
  primitives and transforms can take values that vary with `$t` at render
  time.

- `viewpoint(...)` — context manager that records the default OpenSCAD
  camera (`$vpr`/`$vpt`/`$vpd`/`$vpf`). The renderer emits matching
  top-level assignments at the start of the output `.scad` file.

SymbolicExprs are accepted in transform operands (`translate`, `rotate`,
`scale`, `mirror`) and in primitive sizes (`cube`, `sphere`, `cylinder`).
For conditional branching on `$t`, see `cond()`.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Sequence


# ---------------------------------------------------------------------------
# Symbolic expressions
# ---------------------------------------------------------------------------

class SymbolicExpr:
    """A deferred numeric expression that emits as SCAD source.

    Built by arithmetic operations on `t()`, `preview()`, etc. Everywhere
    scadwright accepts a number in a transform operand, it also accepts a
    SymbolicExpr — and emits the underlying SCAD expression instead of a
    resolved Python float.

    Subclasses define `emit()` returning SCAD source. Arithmetic dunders
    here build BinOp / UnaryOp wrappers automatically.
    """

    # Operator precedence for parenthesization. SCAD follows C-like rules.
    _PREC = 100  # default for atoms; subclasses override.

    def emit(self) -> str:  # pragma: no cover - subclass responsibility
        raise NotImplementedError(
            f"{type(self).__name__} must implement emit()"
        )

    def _emit_with_prec(self, parent_prec: int) -> str:
        """Emit this expression, parenthesized if its precedence is lower
        than the parent context's."""
        s = self.emit()
        if self._PREC < parent_prec:
            return f"({s})"
        return s

    # --- arithmetic dunders ---

    def __add__(self, other): return _binop("+", self, other, 4)
    def __radd__(self, other): return _binop("+", other, self, 4)
    def __sub__(self, other): return _binop("-", self, other, 4)
    def __rsub__(self, other): return _binop("-", other, self, 4)
    def __mul__(self, other): return _binop("*", self, other, 5)
    def __rmul__(self, other): return _binop("*", other, self, 5)
    def __truediv__(self, other): return _binop("/", self, other, 5)
    def __rtruediv__(self, other): return _binop("/", other, self, 5)
    def __mod__(self, other): return _binop("%", self, other, 5)
    def __rmod__(self, other): return _binop("%", other, self, 5)
    def __neg__(self): return UnaryOp("-", self)
    def __pos__(self): return self

    def __pow__(self, other):
        # OpenSCAD has no `**` operator; emit pow(a, b).
        return FuncCall("pow", [self, _to_expr(other)])

    # --- comparison dunders for use with cond() ---
    # NOTE: These return SymbolicExpr (a "comparison expression"), not Python
    # bools. Don't use them in `if`/`while`/`assert`; they raise TypeError on
    # bool() to make accidental misuse loud.

    def __lt__(self, other): return _binop("<", self, other, 3)
    def __le__(self, other): return _binop("<=", self, other, 3)
    def __gt__(self, other): return _binop(">", self, other, 3)
    def __ge__(self, other): return _binop(">=", self, other, 3)
    def __eq__(self, other): return _binop("==", self, other, 2)
    def __ne__(self, other): return _binop("!=", self, other, 2)
    def __hash__(self): return id(self)
    def __bool__(self):
        raise TypeError(
            "SymbolicExpr is not a Python bool — comparisons return a deferred "
            "expression. Use cond(test, a, b) instead of `a if test else b`, "
            "and don't put a SymbolicExpr inside `if`/`while`/`assert`."
        )

    def __repr__(self):
        return f"SymbolicExpr({self.emit()!r})"


@dataclass(frozen=True)
class Identifier(SymbolicExpr):
    """A bare SCAD identifier: `$t`, `$preview`, `$vpr`, etc."""

    name: str
    _PREC = 100

    def emit(self) -> str:
        return self.name


@dataclass(frozen=True)
class Const(SymbolicExpr):
    """A numeric constant lifted into a SymbolicExpr (rare; usually plain
    numbers stay as Python floats and only get lifted when combined with a
    real SymbolicExpr)."""

    value: float
    _PREC = 100

    def emit(self) -> str:
        from scadwright.emit.format import _fmt_num
        return _fmt_num(self.value)


@dataclass(frozen=True)
class BinOp(SymbolicExpr):
    op: str
    left: SymbolicExpr
    right: SymbolicExpr
    prec: int

    @property
    def _PREC(self) -> int:  # type: ignore[override]
        return self.prec

    def emit(self) -> str:
        # Right operand of a left-associative op needs > our prec, not >=,
        # to preserve grouping. Keep the conservative approach: parenthesize
        # at equal prec on the right side.
        return f"{self.left._emit_with_prec(self.prec)} {self.op} {self.right._emit_with_prec(self.prec + 1)}"


@dataclass(frozen=True)
class UnaryOp(SymbolicExpr):
    op: str
    operand: SymbolicExpr
    _PREC = 8

    def emit(self) -> str:
        return f"{self.op}{self.operand._emit_with_prec(self._PREC)}"


@dataclass(frozen=True)
class FuncCall(SymbolicExpr):
    name: str
    args: tuple
    _PREC = 100

    def __init__(self, name: str, args: Sequence):
        # frozen dataclass: use object.__setattr__
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "args", tuple(args))

    def emit(self) -> str:
        from scadwright.emit.format import _fmt_num
        parts = []
        for a in self.args:
            if isinstance(a, SymbolicExpr):
                parts.append(a.emit())
            else:
                parts.append(_fmt_num(a))
        return f"{self.name}({', '.join(parts)})"


def _to_expr(x) -> SymbolicExpr:
    """Coerce a Python number to a Const, or pass through a SymbolicExpr."""
    if isinstance(x, SymbolicExpr):
        return x
    return Const(float(x))


def _binop(op: str, left, right, prec: int) -> SymbolicExpr:
    return BinOp(op=op, left=_to_expr(left), right=_to_expr(right), prec=prec)


# ---------------------------------------------------------------------------
# Public symbol factories
# ---------------------------------------------------------------------------

def cond(test, true_val, false_val) -> SymbolicExpr:
    """Build a SCAD ternary expression: `test ? true_val : false_val`.

    Use this when a value branches on `$t` (or any SymbolicExpr predicate),
    since Python's `a if test else b` requires a real bool and won't work
    with deferred expressions:

        # Forward then back: 0..0.5 goes 0->1, 0.5..1 goes 1->0.
        ping_pong = cond(t() < 0.5, 2 * t(), 2 - 2 * t())

    All three arguments may be plain numbers or SymbolicExprs."""
    return Ternary(_to_expr(test), _to_expr(true_val), _to_expr(false_val))


@dataclass(frozen=True)
class Ternary(SymbolicExpr):
    test: SymbolicExpr
    a: SymbolicExpr
    b: SymbolicExpr
    _PREC = 1

    def emit(self) -> str:
        return f"{self.test._emit_with_prec(2)} ? {self.a._emit_with_prec(2)} : {self.b._emit_with_prec(2)}"


def t() -> SymbolicExpr:
    """The OpenSCAD `$t` animation variable, as a SymbolicExpr.

    Use in transform operands to build animations:

        cube(10).rotate([0, 0, t() * 360])

    OpenSCAD drives `$t` from 0 to 1 over the animation timeline (set
    Steps/FPS in View → Animate)."""
    return Identifier("$t")


# ---------------------------------------------------------------------------
# Viewpoint
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Viewpoint:
    """Default OpenSCAD camera. Any field left as None is omitted from the
    emitted output (OpenSCAD uses its own default for omitted values).

    Fields:
        rotation: `$vpr` — Euler degrees [x, y, z].
        target:   `$vpt` — point the camera looks at, [x, y, z].
        distance: `$vpd` — camera distance from target.
        fov:      `$vpf` — vertical field-of-view in degrees.

    All fields accept SymbolicExpr (e.g. `t() * 360` for a turntable)."""

    rotation: tuple | None = None
    target: tuple | None = None
    distance: object | None = None
    fov: object | None = None


# ContextVar is per-thread / per-async-task, so nested `viewpoint(...)`
# blocks in concurrent renders don't interfere. Users who render in
# multiple threads each get their own effective viewpoint.
_current_viewpoint: ContextVar[Viewpoint | None] = ContextVar(
    "scadwright_viewpoint", default=None
)


def current_viewpoint() -> Viewpoint | None:
    """Return the active Viewpoint (or None if none is set). Used by the
    emitter to write top-level `$vpr=…` assignments."""
    return _current_viewpoint.get()


@contextmanager
def viewpoint(*, rotation=None, target=None, distance=None, fov=None):
    """Set the OpenSCAD default camera for renders inside this block.

        with viewpoint(rotation=[60, 0, 30], distance=200):
            render(MODEL, "out.scad")

    Any field left as None is omitted (OpenSCAD picks its default).
    Nested `viewpoint(...)` blocks merge: inner None fields fall back to
    the outer block's value rather than to OpenSCAD's default."""
    outer = _current_viewpoint.get()
    merged = Viewpoint(
        rotation=rotation if rotation is not None else (outer.rotation if outer else None),
        target=target if target is not None else (outer.target if outer else None),
        distance=distance if distance is not None else (outer.distance if outer else None),
        fov=fov if fov is not None else (outer.fov if outer else None),
    )
    token = _current_viewpoint.set(merged)
    try:
        yield merged
    finally:
        _current_viewpoint.reset(token)


__all__ = [
    "SymbolicExpr",
    "Identifier",
    "Const",
    "BinOp",
    "UnaryOp",
    "FuncCall",
    "Ternary",
    "t",
    "cond",
    "Viewpoint",
    "viewpoint",
    "current_viewpoint",
]
