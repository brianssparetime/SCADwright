# Specs and Adjustments

A [Spec](#your-first-spec) is a group of related dimensions you collect in one place. You write them once, and you read them anywhere as plain attributes. Use one when you have a few values (a battery,  a panel stock, mesurements from something external you want to interface or connect with) that several parts share.

[Adjustments](#adjustments) lets you make small manufacturing-necessitated fudges, and keep them separate from the ideal, final geometry of your intended design; they are the lies you must tell in order to get the truth you need.  If, for example, on one printer, a particular dimension always comes out .5mm short, an adjustment addresses that, without muddying the generally correct design dimensions.

Adjustments are best used in the same `equations` block as the dimensions of a Spec, so this page covers both. You can use either independently: a Spec without adjustments is just shared dimensions; adjustments without a Spec are fine, just less reusable.

For when and why to introduce a Spec, see [Organizing a project](organizing_a_project.md).

----- TODO consider whether to keep line above

## Your first Spec

Suppose you're making a holder, a lid, and a charging cradle for AA batteries. The battery dimensions are the same across all three. Define them once:

```python
from scadwright import Spec

class AA(Spec):
    equations = """
        d = 14.5
        length = 50.5
        nominal_voltage = 1.5
    """
```

Read the values anywhere:

```python
print(AA.d)             # 14.5
print(AA.length)        # 50.5
```

Use them in another part's `build()`:

```python
from scadwright import Component
from scadwright.primitives import cylinder

class Cradle(Component):
    equations = """
        wall_thk, floor_thk > 0
    """

    def build(self):
        return cylinder(
            d=AA.d + 2 * self.wall_thk,
            h=AA.length + self.floor_thk,
        )
```

You don't have to pass `AA` anywhere. It's a class, importable, with class attributes you read directly.

This direct read works inside `build()` and at call sites. To use Spec values inside another Component's `equations` block, see [Letting the Spec flow through equations](#letting-the-spec-flow-through-equations) below.

## What goes in a Spec

A Spec uses the same `equations` block you already know from Components: equations on the left of `=`, rules on lines without `=`, type tags, optional inputs, comma broadcasts. See [Components](components.md) for the syntax of each.

A Spec collects parameters and runs the equations to compute derived values. That's the whole output. There's no `build()` to write because a Spec doesn't produce a shape.

```python
class M5Bolt(Spec):
    equations = """
        d = 5.0
        head_d = 8.5
        head_h = 3.0
        clearance_hole_d = d + 0.4
    """
```

Computed values are readable on the class:

```python
M5Bolt.clearance_hole_d                   # 5.4
```

`clearance_hole_d` was filled in from `d`, the same way a Component fills in derived values from the equations.

## Frozen after definition

Once a Spec is defined, the values are fixed. Try to change one and you get a clear error:

```python
M5Bolt.d = 6.0
# ValidationError: M5Bolt.d: Spec is frozen after resolution; cannot
# reassign. To change a value, edit the equations block in the M5Bolt
# definition.
```

That's the contract: code that reads `M5Bolt.d` knows the value won't shift under it. If you need different numbers, define a different Spec.

## Sharing a Spec across files

A Spec is a class, so importing it works the same way any Python import works. Put the Specs you reuse in a single module:

```python
# dimensions.py
from scadwright import Spec

class M5Bolt(Spec):
    equations = """
        d = 5.0
        head_d = 8.5
        head_h = 3.0
    """

class PanelStock(Spec):
    equations = """
        thk = 3.0
        corner_r = 5.0
    """
```

Import where you need them:

```python
# bracket.py
from scadwright import Component
from dimensions import M5Bolt, PanelStock

class Bracket(Component):
    equations = """
        wall_thk > 0
    """

    def build(self):
        # PanelStock.thk and M5Bolt.head_d are available throughout.
        ...
```

The Spec is the single source of truth across every file that imports it. Edit the value in `dimensions.py`, and every part that reads it rebuilds against the new value the next time you render.

## Where a value should live: Component or Spec?

A Component or Spec should hold the values that are most naturally its own. Not values it depends on, and not values that exist mainly for another part's benefit. If two parts share a value equally, they should share a Spec.

Some examples:

- **Measured dimensions vs design choices.** External measurements (a battery's diameter, a bolt's head height, a panel stock's thickness, anything else you want to interface or connect with) belong in a Spec; they're true regardless of which part reads them. Design choices about your own geometry (a wall thickness you settled on, a chamfer radius you preferred) belong on the Component.

- **An end-cap depends on a tube's OD.** The end-cap reads the OD but doesn't own it. The OD lives on the tube's Component (or in a shared Spec if multiple parts care). The end-cap holds the values specific to itself: lip height, attachment style.

- **Two mating connectors.** The interface they share (bolt circle, mounting depth, alignment-pin position) goes in a Spec that both connectors import. Each connector then holds whatever else is specific to it: length on one side, bracket geometry on the other.

- **Values only the Component cares about.** Wall thickness, alignment offset, a fillet radius you picked because it looked right. These belong on the Component.

- **Manufacturing fudges** (printer overshoot, material shrinkage, slop on a tight fit). These go best in a Spec, recorded as [Adjustments](#adjustments) so the design-intent dimensions stay clean and the fudge is visible on its own line.  Adjustments do, however, work in a Component as well.

## Letting the Spec flow through equations

The pattern above reads Spec values inside `build()`. If you want a derived value to be readable from outside the Component, the same way other equation-derived values are, declare the Spec as a parameter and use it in `equations`:

```python
from scadwright import Component, Param

class Bracket(Component):
    spec = Param()
    equations = """
        wall_thk > 0
        outer_d = spec.head_d + 2 * wall_thk
    """

b = Bracket(spec=M5Bolt, wall_thk=2)
b.outer_d                                  # 12.5 (readable from outside)
```

`Param()` accepts any value, including a Spec class. The equations read `spec.head_d` the same way they read a field off any other input.

This is heavier than direct access in `build()`. Reach for it when:

- You want the derived value (`outer_d`) readable from outside the Component.
- You want the option to swap the spec for a different Spec class with the same shape (M3 vs M5, AA vs AAA).

For a single-Spec, single-project setup, direct access in `build()` is plenty.

## Specs that need inputs

Sometimes a Spec is shaped by a choice you make at use site. A printer profile picks calibration values for that printer; a material profile picks the wall thicknesses for that material. For these, use the same `?` prefix you'd use for an optional input on a Component:

```python
class PrinterProfile(Spec):
    equations = """
        ?profile:str = ?profile or "BAMBU_X1"
        x_axis_overshoot = 0.3 if profile == "BAMBU_X1" else 0.1
        nozzle_d = 0.4 if profile == "BAMBU_X1" else 0.6
    """
```

The `:str` tag tells SCADwright that `profile` is a string, not the default float.

Once a Spec has `?` inputs, you make instances of it instead of reading the class:

```python
prof = PrinterProfile(profile="BAMBU_X1")
prof.x_axis_overshoot       # 0.3

prof = PrinterProfile(profile="VORON_24")
prof.x_axis_overshoot       # 0.1
```

The instance is fixed once constructed, the same way a Component is.

If you read a parameterized Spec at the class level by accident, you get a clear error pointing you to the instance form:

```python
PrinterProfile.x_axis_overshoot
# AttributeError: PrinterProfile.x_axis_overshoot: this Spec has
# parameters, so its values are only available on an instance.
# Use PrinterProfile(...).x_axis_overshoot instead.
```

## Adjustments

Sometimes the dimensions you derive aren't quite the dimensions that print well. The hole is 0.1 mm too tight, the rim sticks out 0.3 mm farther than your printer is calibrated for, the part shrinks 0.2% on cooling. The fix is to nudge specific values up or down with a small fudge factor that has nothing to do with the design intent and everything to do with the printer.

Adjustments are how you record those fudges in source. Inside an `equations` block, write `name += rhs`, `-=`, `*=`, or `/=` to layer a correction on top of the equation-resolved value:

```python
class CamMount(Spec):
    equations = """
        cam_barrel_od = 60.5
        cam_barrel_od += 0.3   # printer X-axis overshoot, ID side
        cam_barrel_od += 0.05  # extra slop for the o-ring
        max_lug_proj = 1.8
        mount_wall_thk = 2.0

        lens_mount_od = cam_barrel_od + 2*max_lug_proj + 2*mount_wall_thk
    """
```

The `+= 0.3` line layers on top of the `cam_barrel_od = 60.5` equation. The next line layers another 0.05. The final `CamMount.cam_barrel_od` is `60.85`. Each adjustment shows on its own line, with a comment naming the rationale, so a reader sees the design intent and the fudges side by side.

Use `+=` to add, `-=` to subtract, `*=` to multiply, `/=` to divide. Reach for `+=`/`-=` when the fudge is a number of mm (printer overshoot, hole tolerance). Reach for `*=`/`/=` when the fudge is a proportion (PLA shrinkage, gear backlash).

A few rules apply to every adjustment:

- **Comments are highly recommended.** Future-you (or your collaborator) needs to know why a `+= 0.3` was added when something doesn't fit a year later.
- **One family per name.** For a given name, every adjustment must be the same family: all additive (`+=` and `-=`) or all multiplicative (`*=` and `/=`). Mixing is rejected at class-define time.
- **The right side can read any name except another adjusted name.** `x += slop` is fine when `slop` isn't itself adjusted. `y += x` is rejected when `x` is adjusted, because that would let the order of the adjustment lines change the result.
- **An adjustment changes only the named value, not values derived from it.** In the example above, `lens_mount_od = cam_barrel_od + ...` sees the pre-adjust `cam_barrel_od` (60.5). Adjustments apply after the equations resolve, so other equations that reference `cam_barrel_od` keep using the design-intent number. To layer printer-error fudges into a derived value, adjust the derived value too.
- **Rules read pre-adjust values.** A rule like `bore_id > cam_barrel_od + 0.1` checks the design intent, not the post-fudge value. (`adjusted(name)` is available inside a rule for the rare case where you need the post-adjust value, but most rules don't.)
- **An adjustment runs only if the right side resolves to a non-None value.** If `x += slop` references an optional input that wasn't supplied, the adjustment skips silently and isn't recorded.

That last rule lets you write a Spec with optional fudges that turn off when not supplied:

```python
class CamMount(Spec):
    equations = """
        ?slop > 0
        cam_barrel_od = 60.5
        cam_barrel_od += slop   # only runs when caller passes slop=
    """

CamMount(slop=0.05).cam_barrel_od    # 60.55 (adjustment ran)
CamMount().cam_barrel_od             # 60.5 (slop is None, adjustment skipped)
```

## Reading the adjustment chain

Every adjustment that actually ran is recorded. Read the chain back with `adjustments_for(name)`:

```python
class CamMount(Spec):
    equations = """
        cam_barrel_od = 60.5
        cam_barrel_od += 0.3   # printer X-axis overshoot, ID side
        cam_barrel_od += 0.05  # extra slop for the o-ring
    """

for adj in CamMount.adjustments_for("cam_barrel_od"):
    print(adj.line, adj.delta, adj.comment)
# 2 0.3 printer X-axis overshoot, ID side
# 3 0.05 extra slop for the o-ring
```

Each entry is an `Adjustment` namedtuple with three fields:

- `line`: the source-line number inside the `equations` block (1-indexed; the first equation is line 1).
- `delta`: the resolved numeric value of the right side. For `+=` and `-=`, signed (a `-=` is stored as a negative number). For `*=` it's the factor as written; for `/=` it's stored as the reciprocal so the chain composes by multiplication.
- `comment`: the trailing or preceding comment text, with the leading `#` stripped.

Skipped adjustments (those whose right side resolved to None) don't appear in the chain.

`all_adjustments()` returns the whole map at once:

```python
CamMount.all_adjustments()
# {'cam_barrel_od': [
#     Adjustment(line=2, delta=0.3, comment='printer X-axis overshoot, ID side'),
#     Adjustment(line=3, delta=0.05, comment='extra slop for the o-ring'),
# ]}
```

For a parameterized Spec, call the same methods on the instance.
