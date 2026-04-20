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

`attach()` defaults to `face="top"` (the anchor on the other shape) and `at="bottom"` (the anchor on self), so `peg.attach(plate)` means "put my bottom on your top."

## Choosing faces

Use `face` and `at` to pick which anchors to align:

```python
peg.attach(plate, face="bottom", at="top")       # peg underneath plate
peg.attach(plate, face="rside", at="lside")      # peg to the right of plate
peg.attach(plate, face="top", at="top")           # align top faces (peg hangs down)
```

Chain a translate for offset placement:

```python
peg.attach(plate).right(10)           # on top, shifted 10 in +X
```

## Orientation (`orient=True`)

By default, `attach()` only translates. Pass `orient=True` to also rotate self so the two anchors' normals oppose each other (faces touching):

```python
peg.attach(plate, face="rside", at="bottom", orient=True)
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
sensor = cube([8, 8, 4]).attach(Bracket(w=20, thk=3, depth=15), face="mount_face")
```

Custom anchors with the same name as a standard face (e.g. `"top"`) override the bbox-derived default. This lets a Component define a semantically meaningful "top" that differs from its bounding box top.

For anchors that need conditional logic (e.g. position depends on a boolean Param), use `self.anchor()` in `setup()` instead -- it still works and overrides class-scope declarations of the same name.

## Anchor propagation

Anchors (including custom ones) propagate through transforms:

```python
bracket = Bracket(w=20, thk=3, depth=15).right(20).up(10)
sensor = cube([8, 8, 4]).attach(bracket, face="mount_face")
# mount_face position is correctly shifted by both transforms
```

Boolean operations (union, difference, intersection) drop custom anchors. Only the standard bbox-derived faces survive, because a boolean combination creates new geometry whose custom attachment points are no longer meaningful.

Non-spatial wrappers (`.color()`, `.highlight()`, etc.) pass anchors through unchanged.

## Shape-library anchors

Shape-library Components ship with useful custom anchors:

| Component      | Anchor name       | Description                     |
|----------------|-------------------|---------------------------------|
| `UShapeChannel`| `channel_opening` | Center of the open face         |
| `Standoff`     | `mount_top`       | Top of the standoff column      |
| `Bolt`         | `tip`             | Bottom of the shaft             |
