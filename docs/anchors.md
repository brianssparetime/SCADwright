# Anchors and attachment

Anchors are named attachment points on shapes. Each anchor has a position (where it is in space) and a normal (which direction it faces). The `attach()` method uses anchors to position one shape relative to another without manual coordinate math.

Imports used on this page:

```python
from scadwright import Component, anchor
from scadwright.primitives import cube, cylinder
```

## Basic usage

Every shape gets six standard anchors derived from its bounding box:

| Name     | Axis-sign | Normal    | Position                  |
|----------|-----------|-----------|---------------------------|
| `top`    | `+z`      | (0,0,1)   | center of top face        |
| `bottom` | `-z`      | (0,0,-1)  | center of bottom face     |
| `front`  | `-y`      | (0,-1,0)  | center of front face      |
| `back`   | `+y`      | (0,1,0)   | center of back face       |
| `lside`  | `-x`      | (-1,0,0)  | center of left face       |
| `rside`  | `+x`      | (1,0,0)   | center of right face      |

The friendly names (`top`, `bottom`, etc.) and axis-sign names (`+z`, `-z`, etc.) both work everywhere. Friendly names are preferred in code.

Stack a peg on top of a plate:

```python
plate = cube([40, 40, 2])
peg   = cube([10, 10, 5]).attach(plate)    # bottom of peg on top of plate
```

`attach()` defaults to `on="top"` (the anchor on the other shape) and `at="bottom"` (the anchor on self), so `peg.attach(plate)` means "put my bottom on your top."

## Choosing faces

Use `on` and `at` to pick which anchors to align:

```python
peg.attach(plate, on="bottom", at="top")       # peg underneath plate
peg.attach(plate, on="rside", at="lside")      # peg to the right of plate
peg.attach(plate, on="top", at="top")           # align top faces (peg hangs down)
```

`on` names the anchor on the parent (the thing being attached to); `at` names the anchor on self (the thing being moved). The same `on` convention is used by other surface-aware verbs like `add_text()`. `at` is context-sensitive — see [`at=` across the API](#at-across-the-api) below.

Chain a translate for offset placement:

```python
peg.attach(plate).right(10)           # on top, shifted 10 in +X
```

## Orientation (`orient=True`)

By default, `attach()` only translates. Pass `orient=True` to also rotate self so the two anchors' normals oppose each other (faces touching):

```python
peg.attach(plate, on="rside", at="bottom", orient=True)
```

This rotates the peg so its bottom normal faces in the -X direction (opposing the plate's rside +X normal), then translates it into position.

When the normals already oppose (e.g. attaching bottom-to-top), `orient=True` produces the same result as `orient=False`.

## Custom anchors on Components

Declare anchors at class scope with the `anchor()` descriptor, alongside equations:

```python
from scadwright import Component, anchor

class Bracket(Component):
    equations = ["w, thk, depth > 0"]

    mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

    def build(self):
        return cube([self.w, self.w, self.depth])
```

The `at=` argument accepts either a string of three comma-separated Python expressions (evaluated against the instance's attributes after params are set) or a literal tuple:

```python
fixed_point = anchor(at=(0, 0, 10), normal=(0, 0, 1))       # literal position
mount_face  = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))  # expression
```

The attribute name (`mount_face`) becomes the anchor's name. Callers attach to it by that name:

```python
sensor = cube([8, 8, 4]).attach(Bracket(w=20, thk=3, depth=15), on="mount_face")
```

Custom anchors with the same name as a standard face (e.g. `"top"`) override the bbox-derived default. This lets a Component define a semantically meaningful "top" that differs from its bounding box top.

The `at=` string supports ternary expressions evaluated against instance attributes, so conditional positions don't need any special machinery: `anchor(at="0 if n_shape else h", normal=(0, 0, 1))`. Conditional **normals** are the narrow remaining case — `normal=` is a fixed tuple at class definition time, so a runtime-chosen normal is a framework-internal escape hatch (library Components only; not a user-facing pattern).

## Anchor propagation

Anchors (including custom ones) propagate through transforms:

```python
bracket = Bracket(w=20, thk=3, depth=15).right(20).up(10)
sensor = cube([8, 8, 4]).attach(bracket, on="mount_face")
# mount_face position is correctly shifted by both transforms
```

Boolean operations (union, difference, intersection) drop custom anchors. Only the standard bbox-derived faces survive, because a boolean combination creates new geometry whose custom attachment points are no longer meaningful.

Non-spatial wrappers (`.color()`, `.highlight()`, etc.) pass anchors through unchanged.

## Surface metadata: `kind` and `surface_params`

Every `Anchor` carries a `kind` field describing the surface it lies on. The default is `"planar"`. Curved-surface kinds — `"cylindrical"` and `"conical"` — also carry the geometric parameters of the surface (`radius` or `r1`/`r2`, `axis`, `length`) so [`add_text()`](add_text.md) can wrap text around them.

`cylinder()` carries an `outer_wall` anchor (cylindrical when `r1 == r2`, conical when tapered). `Tube` and `Funnel` carry `outer_wall` and `inner_wall` anchors.

```python
from scadwright.primitives import cylinder
from scadwright.anchor import get_node_anchors

a = get_node_anchors(cylinder(h=20, r=5))["outer_wall"]
a.kind                     # "cylindrical"
a.surface_param("radius")  # 5.0
a.surface_param("axis")    # (0.0, 0.0, 1.0)
a.surface_param("length")  # 20.0
```

Surface params transform alongside `position` and `normal`: rotating the host rotates the axis, scaling scales the radius and length. `cylinder(h=20, r=5).rotate([90, 0, 0])` reports `axis=(0, -1, 0)` for its outer wall, and `add_text(on="outer_wall", ...)` wraps correctly around the rotated cylinder.

```python
from scadwright import anchor

# Planar (the default — surface_params is omitted).
mount = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

# Cylindrical anchor on a Component. surface_params values can be
# Python expressions (strings) evaluated against instance attributes —
# same as `at=` strings.
outer_wall = anchor(
    at="od/2, 0, h/2",
    normal=(1, 0, 0),
    kind="cylindrical",
    surface_params={"axis": (0, 0, 1), "radius": "od/2", "length": "h"},
)
```

Use `Anchor.surface_param(name, default)` to read back a value.

## Shape-library anchors

Shape-library Components ship with useful custom anchors:

| Component      | Anchor name       | Description                     |
|----------------|-------------------|---------------------------------|
| `UShapeChannel`| `channel_opening` | Center of the open face         |
| `Standoff`     | `mount_top`       | Top of the standoff column      |
| `Bolt`         | `tip`             | Bottom of the shaft             |
| `Counterbore`  | `tip`             | Bottom of the shaft, points -z (mates to `Bolt.tip`) |

## `at=` across the API

`at=` answers "where on the placed/moved thing?" Its form varies with the call:

| Call | `at=` form | Meaning |
|---|---|---|
| `attach(other, on=..., at=...)` | string | anchor name on self (the thing being moved) |
| `add_text(on=..., at=(u, v))` | 2-tuple in mm | offset in the chosen face's tangent plane |
| `add_text(at=(x, y, z), normal=...)` | 3-tuple in mm | ad-hoc 3D position (no `on=`) |
| `anchor(at=..., normal=...)` (declaration) | 3-tuple or string-expr | the anchor's position |

The asymmetry is deliberate: `attach` moves an existing shape (which has its own anchors), so `at=` selects one. `add_text` stamps a generated 2D feature onto a host (no self-anchors), so `at=` is the placement offset within the chosen face. Anchor *declarations* use `at=` for the anchor's position itself.
