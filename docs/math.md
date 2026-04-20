# Math

`scadwright.math` provides the math functions OpenSCAD has built in, with the same names and the same behavior. The most important difference from Python's stdlib `math`: **trig functions use degrees**, not radians (matching SCAD).

Use this module when you're porting code from SCAD or want SCAD's exact semantics. For general-purpose math, Python's built-in `math` module is fine.

Examples below alias the module to `scmath` to avoid shadowing Python's `math`:

```python
from scadwright import math as scmath
```

## Numeric helpers

```python
scmath.sum([1, 2, 3])              # 6
scmath.min(3, 1, 2)                # 1
scmath.min([3, 1, 2])              # 1 (also accepts an iterable)
scmath.max(3, 1, 2)                # 3
scmath.abs(-5)                     # 5
scmath.sign(-3)                    # -1   (returns -1, 0, or 1)
```

## Rounding

```python
scmath.floor(2.7)                  # 2
scmath.ceil(2.1)                   # 3
scmath.round(2.5)                  # 3
scmath.round(-2.5)                 # -3
```

`scmath.round` rounds *half away from zero* (matching SCAD). Python's built-in `round()` rounds *half to even* (banker's rounding) — `round(2.5)` is `2` in Python but `3` in SCAD. The `scmath` version matches SCAD.

## Powers and logarithms

```python
scmath.pow(2, 10)                  # 1024
scmath.sqrt(16)                    # 4
scmath.exp(1)
scmath.ln(2.71828)                 # natural log (≈ 1)
scmath.log(100)                    # base 10 by default → 2
scmath.log(8, base=2)              # 3
```

## Trigonometry (degrees)

```python
scmath.sin(90)                     # 1.0
scmath.cos(0)                      # 1.0
scmath.tan(45)                     # 1.0
scmath.asin(1)                     # 90.0
scmath.acos(0)                     # 90.0
scmath.atan(1)                     # 45.0
scmath.atan2(1, 1)                 # 45.0
```

All angles in and out are in degrees.

## Vector helpers

```python
scmath.norm([3, 4])                # 5.0  — length of the vector
scmath.norm([1, 2, 2])             # 3.0
scmath.cross([1, 0, 0], [0, 1, 0]) # (0, 0, 1) — cross product
```

`cross` requires two 3-vectors. Anything else raises `ValueError`.

---

### Advanced notes

- `scmath.round` returns an `int`, not a `float`, mirroring SCAD's behavior.
- The trig functions internally call Python's `math.sin` etc. with `radians()` conversion, so precision matches stdlib.
- If you need radians directly, use `import math` (stdlib) instead of `scadwright.math`.
