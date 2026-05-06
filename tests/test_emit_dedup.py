"""Emit-time Component subtree deduplication.

The emitter's pre-pass identifies Component instances referenced more
than once in the AST and renders each one as a top-level SCAD module.
This shrinks SCAD files where the same Component appears in many places
(lap-split halves, gridded copies of an assembly, etc.) and lets
OpenSCAD's preview reuse a single module evaluation per Boolean instead
of re-walking the duplicated subtree per frame.
"""
from __future__ import annotations

import re

from scadwright import Component, emit_str
from scadwright.boolops import difference, union
from scadwright.primitives import cube, cylinder, sphere


class _BigBox(Component):
    """A Component with enough primitives to clear the default threshold."""

    def __init__(self, size=10):
        super().__init__()
        self.size = size

    def build(self):
        s = self.size
        return difference(
            cube([s, s, s]),
            cylinder(h=s + 2, r=s / 4).down(1),
            cylinder(h=s + 2, r=s / 4).down(1).translate([s / 4, 0, 0]),
            cylinder(h=s + 2, r=s / 4).down(1).translate([-s / 4, 0, 0]),
            cylinder(h=s + 2, r=s / 4).down(1).translate([0, s / 4, 0]),
            cylinder(h=s + 2, r=s / 4).down(1).translate([0, -s / 4, 0]),
        )


class _SmallBox(Component):
    """Below the threshold (1 primitive)."""

    def __init__(self, size=2):
        super().__init__()
        self.size = size

    def build(self):
        return cube([self.size, self.size, self.size])


def _module_blocks(out: str) -> list[str]:
    return re.findall(r"^module \w+\(\) \{$", out, flags=re.MULTILINE)


def _module_def_count(out: str, module_name: str) -> int:
    return len(re.findall(rf"^module {re.escape(module_name)}\(\) \{{$",
                          out, flags=re.MULTILINE))


def _call_count(out: str, module_name: str) -> int:
    """Count call sites: matches `Foo_xx();` even if preceded by indent or transforms."""
    return len(re.findall(rf"\b{re.escape(module_name)}\(\);",
                          out))


def test_repeated_component_hoists_to_module():
    b = _BigBox(size=10)
    out = emit_str(union(b, b.translate([20, 0, 0])))
    assert "module _BigBox_" in out
    # exactly one module def
    matches = re.findall(r"^module (_BigBox_\w+)\(\) \{$", out, flags=re.MULTILINE)
    assert len(matches) == 1, f"expected one module def, got {matches}"
    name = matches[0]
    # call sites: two
    assert _call_count(out, name) == 2


def test_single_reference_does_not_hoist():
    b = _BigBox(size=10)
    out = emit_str(b)
    assert "module _BigBox_" not in out
    # inline content present
    assert "difference()" in out


def test_below_threshold_does_not_hoist():
    s = _SmallBox(size=2)
    out = emit_str(union(s, s, s.translate([5, 0, 0])))
    # _SmallBox has 1 primitive; threshold prevents hoisting trivially-small
    # subtrees where module-call indirection would cost more than it saves.
    assert "module _SmallBox_" not in out


def test_chained_transforms_compose_at_call_site():
    b = _BigBox(size=10)
    out = emit_str(union(
        b.translate([1, 2, 3]),
        b.rotate([0, 0, 45]),
    ))
    matches = re.findall(r"^module (_BigBox_\w+)\(\) \{$", out, flags=re.MULTILINE)
    assert len(matches) == 1
    name = matches[0]
    # Each call site should be wrapped by its outer transform.
    assert "translate([1, 2, 3])" in out
    assert "rotate([0, 0, 45])" in out
    assert _call_count(out, name) == 2


def test_color_modifier_at_call_site_not_inside_module():
    b = _BigBox(size=10)
    out = emit_str(union(b, b.color("red")))
    matches = re.findall(r"^module (_BigBox_\w+)\(\) \{([\s\S]*?)^\}$",
                         out, flags=re.MULTILINE)
    assert len(matches) == 1
    name, body = matches[0]
    # color() must wrap the call site, not appear inside the module body.
    assert 'color("red")' in out
    assert 'color("red")' not in body
    assert _call_count(out, name) == 2


def test_glossary_renders_inside_hoisted_module_once():
    class _Gloss(Component):
        equations = """
            od = id + 2*thk
            h, id, od, thk > 0
        """

        def build(self):
            return difference(
                cylinder(h=self.h, r=self.od / 2),
                cylinder(h=self.h + 2, r=self.id / 2).down(1),
                cylinder(h=self.h + 2, r=self.id / 4).down(1).translate([self.od / 4, 0, 0]),
                cylinder(h=self.h + 2, r=self.id / 4).down(1).translate([-self.od / 4, 0, 0]),
                cylinder(h=self.h + 2, r=self.id / 4).down(1).translate([0, self.od / 4, 0]),
            )

    t = _Gloss(h=10, id=8, thk=1)
    out = emit_str(union(t, t.translate([15, 0, 0])))
    # Class header appears exactly once, inside the module body.
    assert out.count("// _Gloss") == 1
    # The header sits above the module body, not at a call site.
    header_pos = out.find("// _Gloss")
    module_open = out.find("module _Gloss_")
    module_close_after_header = out.find("}", header_pos)
    assert module_open < header_pos < module_close_after_header


def test_module_name_is_deterministic_across_runs():
    b1 = _BigBox(size=10)
    out1 = emit_str(union(b1, b1.translate([5, 0, 0])))
    b2 = _BigBox(size=10)
    out2 = emit_str(union(b2, b2.translate([5, 0, 0])))
    name1 = re.findall(r"module (_BigBox_\w+)\(\)", out1)[0]
    name2 = re.findall(r"module (_BigBox_\w+)\(\)", out2)[0]
    assert name1 == name2
    # Full output is bit-identical too.
    assert out1 == out2


def test_two_distinct_param_values_get_distinct_modules():
    a = _BigBox(size=10)
    b = _BigBox(size=20)
    out = emit_str(union(
        a, a.translate([5, 0, 0]),
        b, b.translate([5, 0, 0]),
    ))
    names = sorted(set(re.findall(r"module (_BigBox_\w+)\(\)", out)))
    assert len(names) == 2, f"expected two modules, got {names}"


def test_two_instances_with_same_canonical_form_share_module():
    """Identity-keyed counting + content-addressed naming: two distinct
    instances that canonicalize identically share one module def."""
    a = _BigBox(size=10)
    b = _BigBox(size=10)  # separate instance, same params/build
    out = emit_str(union(a, a.translate([5, 0, 0]), b, b.translate([10, 0, 0])))
    # One module def; four call sites total.
    names = re.findall(r"module (_BigBox_\w+)\(\) \{", out)
    assert len(names) == 1
    assert _call_count(out, names[0]) == 4


def test_nested_components_each_dedup_independently():
    class _Outer(Component):
        def __init__(self):
            super().__init__()
            self.inner = _BigBox(size=8)

        def build(self):
            # Wrap inner uses with a flange of additional primitives so
            # _Outer clears the prim threshold on its own. Without these,
            # _Outer's cached subtree has only two ops (the two inner refs),
            # which is below the default threshold and would skip hoist.
            return union(
                self.inner,
                self.inner.translate([10, 0, 0]),
                cylinder(h=1, r=15).down(2),
                cylinder(h=1, r=15).up(10),
                cube([30, 30, 0.5]).down(3),
                sphere(r=2).up(20),
            )

    o = _Outer()
    out = emit_str(union(o, o.translate([30, 0, 0])))
    # Both _Outer and _BigBox should hoist (each referenced 2× via the
    # surrounding/inner unions respectively).
    outer_names = re.findall(r"module (_Outer_\w+)\(\)", out)
    bigbox_names = re.findall(r"module (_BigBox_\w+)\(\)", out)
    assert len(outer_names) == 1, outer_names
    assert len(bigbox_names) == 1, bigbox_names
    # _Outer's module body should contain calls to _BigBox, not inlined geometry.
    outer_body = re.search(rf"module {outer_names[0]}\(\) \{{([\s\S]*?)^\}}",
                           out, flags=re.MULTILINE).group(1)
    assert bigbox_names[0] in outer_body
    assert "difference()" not in outer_body


def test_nested_dedup_works_when_parent_class_sorts_before_inner():
    """Module-emission order is alphabetical by class name. If the parent
    Component's class name sorts before the inner's, naive per-iteration
    registration would render the parent's body before the inner is
    registered, leaving the inner inlined twice inside the parent module
    body — defeating dedup. Two passes (register all, then render bodies)
    keep the dedup correct regardless of class-name ordering."""

    class _AOuter(Component):
        def __init__(self):
            super().__init__()
            self.inner = _BigBox(size=8)

        def build(self):
            return union(
                self.inner,
                self.inner.translate([10, 0, 0]),
                cylinder(h=1, r=15).down(2),
                cylinder(h=1, r=15).up(10),
                cube([30, 30, 0.5]).down(3),
                sphere(r=2).up(20),
            )

    o = _AOuter()
    out = emit_str(union(o, o.translate([30, 0, 0])))
    outer_names = re.findall(r"module (_AOuter_\w+)\(\)", out)
    bigbox_names = re.findall(r"module (_BigBox_\w+)\(\)", out)
    assert len(outer_names) == 1
    assert len(bigbox_names) == 1
    outer_body = re.search(rf"module {outer_names[0]}\(\) \{{([\s\S]*?)^\}}",
                           out, flags=re.MULTILINE).group(1)
    # Parent body must contain calls to the inner module, NOT the inlined
    # difference() geometry.
    assert bigbox_names[0] in outer_body
    assert "difference()" not in outer_body
    # Inner module is actually called from outer's body, so the call count
    # is non-zero (otherwise we'd have a module def that nothing uses).
    assert _call_count(out, bigbox_names[0]) >= 2


def test_lap_split_pattern_emits_one_module_six_calls():
    """Regression model for the s2-evolving v12c.py print-variant case:
    one Component referenced six times collapses to one module + six calls."""
    b = _BigBox(size=10)
    out = emit_str(union(
        b,
        b.translate([20, 0, 0]),
        b.translate([40, 0, 0]),
        b.translate([0, 20, 0]),
        b.translate([20, 20, 0]),
        b.translate([40, 20, 0]),
    ))
    names = re.findall(r"module (_BigBox_\w+)\(\) \{", out)
    assert len(names) == 1
    assert _call_count(out, names[0]) == 6
    # Inflation gone: difference() body appears once (inside module), not six times.
    assert out.count("difference()") == 1


def test_debug_source_comments_compose_with_dedup():
    b = _BigBox(size=10)
    out = emit_str(union(b, b.translate([20, 0, 0])), debug=True)
    matches = re.findall(r"module (_BigBox_\w+)\(\)", out)
    assert len(matches) == 1
    # Debug comments still emitted at the call sites.
    assert "// " in out


def test_dedup_with_section_labels_off_omits_header_inside_module():
    b = _BigBox(size=10)
    out = emit_str(union(b, b.translate([20, 0, 0])), section_labels=False)
    assert "// _BigBox" not in out
    matches = re.findall(r"module (_BigBox_\w+)\(\) \{", out)
    assert len(matches) == 1
