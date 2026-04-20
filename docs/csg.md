# Boolean operations

Boolean operations combine shapes. The three classics — union, difference, intersection — let you build complex parts from simple ones. Two more — hull and minkowski — produce shapes that "fill in" between operands.

Imports used on this page:

```python
from scadwright.boolops import union, difference, intersection, hull, minkowski
```

Each operation takes any number of shapes. You can pass them as separate arguments, as a list, or mix the two:

```python
union(a, b, c)                 # variadic
union([a, b, c])               # one list
union(*parts)                  # unpacking a list
union(a, [b, c], d)            # mix is fine — the inner list is flattened
```

**Flattening is one level only.** `union([[a, b], [c]])` is an error — the outer list contains lists, not shapes. This is deliberate: deeper flattening hides bugs where a user accidentally nests their shape collections. If you need to flatten deeper, do it explicitly with `itertools.chain.from_iterable(...)` before passing.

## `union`

Combines shapes into one. The result is everywhere any operand is.

```python
union(
    cube([10, 10, 10]),
    sphere(r=7).translate([5, 5, 5]),
)
```

## `difference`

Subtracts later shapes from the first. Use this for holes, slots, cutouts.

```python
difference(
    cube([20, 20, 10], center=True),    # the body
    cylinder(h=12, r=3, center=True),   # the hole through it
)
```

The order matters: `difference(a, b)` is "a minus b," not "b minus a."

## `intersection`

Keeps only the volume that's in *every* operand.

```python
intersection(
    cube([10, 10, 10], center=True),
    sphere(r=6),
)
```

The result is what fits inside both shapes — useful for clipping or for shapes defined as the overlap of simpler ones.

## `hull`

The smallest convex shape that contains all the operands. Think of stretching plastic wrap around the shapes.

```python
hull(
    cube([1, 1, 1]),                     # one corner
    cube([1, 1, 1]).translate([10, 0, 0]),  # another corner
)
```

The result above is a slanted prism connecting the two cubes — a swept rectangle.

## `minkowski`

The Minkowski sum: the result of "sliding" one shape over the other and unioning every position. Common pattern: pass a `sphere` to round all edges, or a `cube` to chamfer them.

```python
# A box with all edges rounded by 1mm:
minkowski(
    cube([20, 20, 5], center=True),
    sphere(r=1, fn=8),
)
```

Minkowski grows the shape by the second operand's size, so the result is bigger than the first operand.

## Operator shorthand

For simple expressions, scadwright supports Python's set-operator syntax on shapes:

```python
a | b          # union          (matches Python set: |)
a & b          # intersection   (matches Python set: &)
a - b          # difference     (first minus the rest)
```

Chains left-fold and flatten to the variadic forms:

```python
a | b | c      # same AST as union(a, b, c)     — one union, three children
a & b & c      # same AST as intersection(a, b, c)
a - b - c      # same AST as difference(a, b, c)
```

Mixing types doesn't flatten: `(a | b) & c` produces `intersection(union(a, b), c)`, preserving the parenthesization.

The named functions (`union`, `difference`, etc.) remain the right choice when:
- you're collecting shapes from a list or generator,
- the call is far from the operands and needs an explicit verb,
- you want the source-location pointing at the CSG call rather than an operator.

---

### Epsilon clearances

When a cutter shares a face with the shape it's cutting (e.g. a hole through a wall), coincident surfaces produce rendering artifacts in OpenSCAD. scadwright handles this automatically with `through()`:

```python
body = cube([40, 40, 5])
hole = cylinder(h=5, d=6).translate([20, 20, 0])
part = difference(body, hole.through(body))
```

`through()` detects which faces of the cutter are flush with the parent and extends them by a small epsilon. For unions where parts sit flush, use `attach(fuse=True)` to overlap the contact face. See [Eliminating epsilon overlap](auto-eps_fuse_and_through.md) for the full reference.

### Advanced notes

- Empty operations (`union()`, `difference()`) raise `ValidationError`.
- `union`, `intersection`, and `hull` don't care about argument order; `difference` does.
- Minkowski is expensive at render time -- OpenSCAD slows down significantly with complex operands. Use sparingly.

### See also

- [Composition helpers](composition_helpers.md) -- `mirror_copy`, `rotate_copy`, `linear_copy`, `multi_hull`, `sequential_hull` for common patterns built on these operations
- [Eliminating epsilon overlap](auto-eps_fuse_and_through.md) -- `through()` and `attach(fuse=True)` for clean CSG without manual epsilon
