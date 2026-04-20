# Testing SCADwright projects

SCADwright provides a few tools for writing automated tests against your designs.

## Geometry pinning with `tree_hash`

`tree_hash` computes a short hex hash of a shape's AST (ignoring source locations). If any dimension, transform, or boolean op changes, the hash changes. Use it to pin a part's geometry in a unit test:

```python
from scadwright import tree_hash

def test_widget_geometry_pinned():
    w = MyWidget(width=40, height=20)
    assert tree_hash(w) == "a1b2c3d4e5f6..."
```

When you intentionally change the geometry, run the test, copy the new hash from the failure message, and update the assertion.

## Geometry assertions

```python
from scadwright.asserts import assert_fits_in, assert_contains, assert_no_collision, assert_bbox_equal
```

- `assert_fits_in(part, [200, 200, 50])` -- part's bounding box fits within the given volume.
- `assert_contains(outer, inner)` -- outer's bbox fully contains inner's bbox.
- `assert_no_collision(a, b)` -- bounding boxes don't overlap.
- `assert_bbox_equal(part, ((0, 0, 0), (10, 10, 10)))` -- bbox matches exactly (within tolerance).

These check bounding boxes, not mesh geometry. They're fast (no rendering required) and catch the most common errors: a part that grew too large, parts that overlap, or a part that shifted unexpectedly.

## Testing variants

To test that each variant builds without errors:

```python
from scadwright import emit_str

def test_print_variant_builds():
    design = MyDesign()
    node = design.print()
    scad = emit_str(node)
    assert "difference" in scad    # or whatever you expect

def test_display_variant_builds():
    design = MyDesign()
    node = design.display()
    assert tree_hash(node) == "..."
```

## Golden-file testing

For regression testing the generated SCAD output, compare against a saved "golden" file:

```python
from pathlib import Path
from scadwright import emit_str

def test_widget_scad_output(tmp_path):
    golden = Path("tests/golden/widget.scad")
    actual = emit_str(MyWidget(width=40))
    if golden.exists():
        assert actual == golden.read_text()
    else:
        golden.write_text(actual)    # first run: create the golden file
```

SCADwright's own test suite uses this pattern extensively. When you make an intentional change, regenerate the golden files and review the diff.
