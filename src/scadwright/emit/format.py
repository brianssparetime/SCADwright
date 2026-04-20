"""Value formatters for SCAD output."""

from __future__ import annotations


def _fmt_num(n) -> str:
    """Render a number: integers without trailing .0, floats with minimal precision.

    `SymbolicExpr` values (animation expressions) emit as SCAD source via
    their `emit()` method instead of being coerced to a Python float."""
    # Late import: scadwright.animation depends on this module via Const.emit.
    from scadwright.animation import SymbolicExpr
    if isinstance(n, SymbolicExpr):
        return n.emit()
    if isinstance(n, bool):
        # bool is an int subclass; catch it before the int check.
        return "true" if n else "false"
    if isinstance(n, int):
        return str(n)
    f = float(n)
    if f.is_integer():
        return str(int(f))
    # Short precision; trim trailing zeros but keep at least one decimal.
    s = f"{f:.6g}"
    return s


def _fmt_bool(b: bool) -> str:
    return "true" if b else "false"


def _fmt_vec(v) -> str:
    return "[" + ", ".join(_fmt_num(x) for x in v) + "]"


def _fmt_matrix(m) -> str:
    """Render a scadwright.Matrix as a SCAD list-of-rows literal."""
    return "[" + ", ".join(_fmt_vec(row) for row in m.elements) + "]"


def _fmt_str(s: str) -> str:
    """Render a Python string as a SCAD-quoted, escaped string literal."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def _fmt_value(v) -> str:
    """Render an arbitrary parameter value (number, bool, str, sequence) as SCAD source."""
    if isinstance(v, bool):
        return _fmt_bool(v)
    if isinstance(v, (int, float)):
        return _fmt_num(v)
    if isinstance(v, str):
        return _fmt_str(v)
    if isinstance(v, (list, tuple)):
        return _fmt_vec(v)
    if v is None:
        return "undef"
    return str(v)


def _fmt_color(c, alpha: float = 1.0) -> str:
    """SCAD's color() accepts: color name string, hex string, or [r,g,b(,a)]."""
    if isinstance(c, str):
        return f'"{c}"'
    # Vector form: pass-through, optionally appending alpha.
    parts = list(c)
    if len(parts) == 3 and alpha != 1.0:
        parts = [*parts, alpha]
    return _fmt_vec(parts)
