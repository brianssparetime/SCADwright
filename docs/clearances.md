# Clearances

Project-wide fit tolerances for the [joint Components](shapes/joints.md).
You set them once for your printer and material; every
`AlignmentPin`, `PressFitPeg`, `SnapPin`, and `TabSlot` in your project
inherits automatically.

Joints opt out per-instance by passing `clearance=` explicitly.

## The vocabulary — four fit categories

```python
from scadwright import Clearances, DEFAULT_CLEARANCES

class Clearances(NamedTuple):
    sliding: float | None = None   # Location-only fits (AlignmentPin socket)
    press:   float | None = None   # Interference fits (PressFitPeg — socket < shaft)
    snap:    float | None = None   # Through-hole fits for compliant pins (SnapPin)
    finger:  float | None = None   # Finger-joint play (TabSlot slot vs. tab)

DEFAULT_CLEARANCES = Clearances(sliding=0.1, press=0.1, snap=0.2, finger=0.2)
```

Each category maps to exactly one fit family. Every field is `float | None`; `None` means "inherit from the enclosing scope."

`DEFAULT_CLEARANCES` are starter values — **tune for your printer on day one**. They're framework-level, importable, and meant to be overridden.

## Setting clearances

### Project-wide — on a `Design`

```python
from scadwright import Clearances
from scadwright.design import Design, variant

class MyProject(Design):
    clearances = Clearances(sliding=0.05, press=0.08, snap=0.2, finger=0.2)

    @variant(default=True)
    def print(self):
        return self.assembly()     # every joint built inside picks it up
```

### Scoped — `with clearances(...)`

```python
from scadwright import clearances, Clearances

with clearances(Clearances(sliding=0.05)):
    # Every joint built in this block sees sliding=0.05;
    # press/snap/finger inherit from any enclosing scope or
    # DEFAULT_CLEARANCES.
    peg = AlignmentPin(d=4, h=8, lead_in=1)
```

Partial specs compose per-field across nested scopes:

```python
with clearances(Clearances(sliding=0.2, press=0.1)):
    with clearances(Clearances(sliding=0.05)):
        # effective: sliding=0.05 (inner wins), press=0.1 (outer),
        # snap and finger from DEFAULT_CLEARANCES
        ...
```

### Per-Component — class attribute

A `Component` that has tight internal tolerances regardless of its caller's scope sets the class attr directly:

```python
class TightBracket(Component):
    clearances = Clearances(sliding=0.05)

    def build(self):
        return AlignmentPin(d=4, h=8, lead_in=1)   # always sliding=0.05
```

### Per-call — kwarg override

Highest priority — always wins for that one instance:

```python
AlignmentPin(d=4, h=8, lead_in=1, clearance=0.3)   # wins over everything
```

## Precedence

Per-field resolution, highest priority first:

1. **Per-call `clearance=` kwarg** — always wins for the one Component instance.
2. **Component class attribute** — pushed as an inner scope during the Component's `build()`. Inner scope wins over outer, mirroring how `fn` on a Component class beats an outer `with resolution(fn=...)`.
3. **`with clearances(...)` scope** — ContextVar; partial specs merge with enclosing scopes per-field.
4. **Design class attribute** — pushed as an outer scope around each variant's build.
5. **`DEFAULT_CLEARANCES`** — framework floor, all fields concrete.

Example of the chain in action:

```python
with clearances(Clearances(sliding=0.3)):          # outer scope
    class Tight(Component):
        clearances = Clearances(sliding=0.05)      # (2) inner scope during build
        def build(self):
            # Inside Tight.build():
            return AlignmentPin(
                d=4, h=8, lead_in=1,                # uses sliding=0.05 (class attr wins)
            )

    outside = AlignmentPin(d=4, h=8, lead_in=1)    # uses sliding=0.3 (with scope)
    inside = Tight()
```

## The press-fit sign convention

`PressFitPeg` uses `clearance` to mean *interference* — the shaft is oversized relative to its hole. Internally:

```
socket_d == shaft_d - 2 * clearance
```

The sign flips, but the name stays `clearance` so the resolution machinery works uniformly across all joints. See the `PressFitPeg` docstring for the geometric detail.

## When the resolver doesn't run

- **Non-joint Components** don't opt in — no `_clearance_category` means the resolver no-ops and nothing is injected into `kwargs`.
- **Passing `clearance=` explicitly** skips the resolver entirely; the per-call value wins.

## Seeing what's active

```python
from scadwright.api.clearances import current_clearances

with clearances(Clearances(sliding=0.05)):
    print(current_clearances())
    # → Clearances(sliding=0.05, press=None, snap=None, finger=None)
```

`None` fields in `current_clearances()` indicate fields that fall through to `DEFAULT_CLEARANCES`.
