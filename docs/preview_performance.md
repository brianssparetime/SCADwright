# Preview performance

When a heavy model makes OpenSCAD's preview (F5) sluggish to orbit, or makes surfaces shimmer where parts overlap, `force_render` caches the expensive geometry so the preview stays responsive and clean.

You pay a slow first compile and get fast redraws afterward, so it pays back only where redraws happen: sitting in OpenSCAD's window turning the model around. A headless preview image (`openscad -o out.png`) compiles once and never redraws, so it pays the cost and collects nothing. On a model carrying 116 engraved glyph solids, that image took 0.5 seconds without the wrap and 64 seconds with it.

```python
from scadwright.debug import force_render
```

## `force_render`

Wraps a subtree in SCAD's `render(convexity=...)`, forcing OpenSCAD to do a full CGAL render of that subtree in preview (F5) mode rather than its cheaper OpenCSG approximation.

```python
# Chained (preferred when you're in a shape expression):
complex_part.force_render(convexity=5)

# Standalone:
force_render(complex_part, convexity=5)
```

**Parameters:**

- `convexity` — optional render-complexity hint. Higher values allow OpenSCAD to correctly render more deeply-nested concavities; default is OpenSCAD's.

This doesn't change the emitted geometry — only OpenSCAD's rendering strategy. The bounding box passes straight through the child.

### What goes inside the wrap

`force_render` caches everything inside it, and editing anything inside re-runs the full render. Wrap only the stable, expensive geometry. Keep whatever you tweak often — engravings, version stamps, a hole array you're still placing — outside the wrap, and apply it afterward as a difference against the cached body:

```python
# Cutter inside the cache, dragged into every rebuild:
result = body.add_text(label="...", relief=-0.3, ...).force_render()

# Cutter outside, body cached on its own:
cutter = body.text_geometry(label="...", relief=-0.3, ...)
result = difference(body.force_render(), cutter)
```

[`text_geometry`](add_text.md#returning-glyph-geometry-without-combining-text_geometry) is the text-specific tool; for hole cutouts and similar, plain `difference()` with the cutter as its own expression does the same job. When a downstream consumer (`arrange_on_bed`, anything that calls `tight_bbox`) needs to see the cached body's extents, wrap with [`with_bbox_from(body)`](introspection.md#overriding-bbox-with_bbox_from) so the difference doesn't trip the "can't tighten" raise.

## It won't rescue a slow exact render

`force_render` is not the fix for an F6 or an STL export that crawls or never finishes. On that same 116-glyph model an export took 70.4 seconds either way, and the wrap raised OpenSCAD's CGAL cache from 48.8 MB to 73.7 MB for the extra meshes it had to keep. A subtree containing a hand-built `polyhedron` can also make an export abort inside CGAL rather than finish. Reach for `force_render` when the preview is the problem, not otherwise.

An exact render that won't finish usually means the model hands CGAL more separate solids than it can work through. Engraved text on a curved wall is the usual route there, because [every glyph is its own solid](add_text.md#per-glyph-spacing-internals). Treat that as a ceiling rather than something to tune around: the preview renderer copes with counts the exact one will not.
