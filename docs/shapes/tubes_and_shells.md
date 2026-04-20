# Tubes and shells

Parametric hollow shapes with equation-driven dimensions.

```python
from scadwright.shapes import Tube, Funnel, RoundedBox, UShapeChannel
```

## `Tube(h, id|od|thk)`

Hollow cylinder. Specify any two of inner diameter, outer diameter, and wall thickness; the framework solves the third.

```python
Tube(h=10, id=8, thk=1)      # od solved = 10
Tube(h=10, id=8, od=10)      # thk solved = 1
Tube(h=10, od=10, thk=1)     # id solved = 8
```

## `Funnel(h, thk, top_*, bot_*)`

Tapered tube. For each end, specify one of the inner or outer diameter.

```python
Funnel(h=20, thk=2, bot_id=10, top_id=14)
Funnel(h=20, thk=2, bot_od=14, top_od=18)
Funnel(h=20, thk=2, bot_id=10, top_od=18)    # mix and match
```

## `RoundedBox(size, r)`

Box with all edges rounded by a sphere of radius `r`. Centered on the origin. Each `size` axis must be larger than `2*r`.

```python
RoundedBox(size=(20, 10, 5), r=1)
```

## `UShapeChannel(channel_width, channel_height, outer_width, outer_height, wall_thk, channel_length)`

Three-sided rectangular channel with equation-driven dimensions. Specify `channel_length` plus any two cross-section params; the framework solves the rest. `n_shape=True` flips the opening downward.

```python
UShapeChannel(wall_thk=2, channel_length=20, channel_width=10)
UShapeChannel(wall_thk=2, channel_length=20, channel_width=10, n_shape=True)
```

Publishes `bottom_width`, `outer_width`, `outer_height`. Declares a `channel_opening` anchor at the center of the open face.
