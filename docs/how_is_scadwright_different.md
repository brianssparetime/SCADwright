# How is SCADwright different?

If you searched "Python OpenSCAD" or "Python parametric CAD," several other projects probably came up. Here's how SCADwright relates to each. The goal isn't to claim SCADwright is better at every axis — it's to help you pick the right tool for what you're building.

## SolidPython / SolidPython2

[SolidPython](https://github.com/SolidCode/SolidPython) and its actively-maintained successor [SolidPython2](https://github.com/jeff-dh/SolidPython) are the most common Python wrappers around OpenSCAD. Like SCADwright, they generate `.scad` source from a Python script.

**How SCADwright differs:**

- **Components let the caller read dimensions back.** A SolidPython part is a function that returns geometry; the caller can't ask "where are your mount holes?" without re-running the math themselves. SCADwright's `Component` classes use an `equations` list to relate their inputs; the caller can read every input and every value SCADwright filled in directly off the part (e.g. `tube.od`, `bracket.rise`).
- **Real validation with source locations.** `cube([-5, 10, 10])` in SCADwright raises `ValidationError: cube size[0] must be non-negative, got -5.0 (at widget.py:42)`. SolidPython hands the bad value to OpenSCAD and you debug from the rendered output.
- **Built-in shape library.** `Tube`, `Funnel`, `RoundedBox`, `FilletRing`, `Sector`, `RoundedSlot`, etc. ship with the package. SolidPython gives you the OpenSCAD primitives; reusable shapes you copy-paste between projects.
- **Equations and solving.** SCADwright Components can declare relationships like `od = id + 2*thk` and supply any two of the three; the framework solves for the third.
- **Test infrastructure.** `tree_hash` for regression-pinning a part's geometry, and `assert_fits_in` / `assert_contains` / `assert_no_collision` for geometry assertions.
- **Variants.** Named print/display variants are first-class instead of commented-out code blocks.

If you mostly want a thin Python layer over OpenSCAD's verbs and don't need the framework features above, SolidPython2 is lighter and well-established.

## OpenPySCAD

[OpenPySCAD](https://github.com/taxpon/openpyscad) is another wrapper that generates SCAD source. The original goals overlap with SolidPython — chained transforms on shape objects, then `.dumps()` to a string.

**How SCADwright differs:** essentially the same delta as SolidPython — Components, validation with source locations, shape library, equations, tests, variants, CLI. OpenPySCAD development has been quiet for several years; if you're starting fresh today, SCADwright or SolidPython2 are more current options.

## PythonSCAD (gsohler/openscad fork)

[PythonSCAD](https://pythonscad.org/) is Guillaume Sohler's fork that *replaces* OpenSCAD's interpreter with Python. Your script runs inside the OpenSCAD process and emits geometry directly to OpenSCAD's CSG engine — no `.scad` file in the middle.

**How SCADwright differs:**

- **Different objective.** PythonSCAD makes Python the primary language *inside* OpenSCAD. SCADwright stays outside: you author in Python, SCADwright emits a standard `.scad` file, and you can open it in stock OpenSCAD or any other tool that consumes SCAD. No fork required.
- **Distribution.** SCADwright is a `pip install` away and works with any OpenSCAD version. PythonSCAD requires installing a custom OpenSCAD build.
- **Interop.** SCADwright's output is plain SCAD that other people, scripts, and tools can read or modify. PythonSCAD scripts only run inside the forked interpreter.

If you're already committed to OpenSCAD as your end-to-end environment and want Python's expressiveness inside it, PythonSCAD is the more direct route. If you want a Python toolchain that produces standard SCAD output, SCADwright.

## OpenJSCAD / JSCAD

[JSCAD](https://openjscad.xyz/) is a JavaScript-based parametric modeling library with its own renderer. Same general idea as SolidPython — author in code, render to mesh — but the language is JS and the renderer is built in.

**How SCADwright differs:** language and runtime, mainly. SCADwright is Python-first and emits `.scad` for OpenSCAD to render. JSCAD is JS-first with its own web-based renderer. Pick whichever language you'd rather author in; both are mature.

## CadQuery

[CadQuery](https://github.com/CadQuery/cadquery) is a Python library on the OpenCASCADE B-Rep CAD kernel — the closest open-source analogue to commercial parametric CAD like SolidWorks or Onshape. B-Rep represents curved surfaces exactly and supports STEP/IGES export; SCADwright (via OpenSCAD) is CSG with curves tessellated to a mesh at render time.

**Pick CadQuery when** parts will be machined (CNC, lathe, mill), need surface continuity for mechanical mating (gear teeth, bearing races, machined fits), exchange with traditional CAD/CAM via STEP / IGES, or feed into FEA simulation. CadQuery's exact-surface representation is necessary for all of these.

**Pick SCADwright when** you're making 3D-printable parts where the STL mesh is the deliverable. SCADwright is simpler to install, faster to iterate against, and emits readable `.scad` you can diff and share. The Component model — parts that publish their dimensions back to callers — is the main edge over both CadQuery's parametric scripts and plain OpenSCAD.

## Build123d

[Build123d](https://github.com/gumyr/build123d) is a newer Python CAD library, also OpenCASCADE-based, sharing CadQuery's geometric capabilities with a different (often nicer) API.

**How SCADwright differs:** same axis as CadQuery — Build123d is B-Rep / OpenCASCADE / industrial CAD output, SCADwright is OpenSCAD / mesh CSG / `.scad` output. Pick SCADwright for OpenSCAD-style work; pick Build123d for the same niche CadQuery serves.

## Plain OpenSCAD

OpenSCAD itself, with no Python.

**How SCADwright differs:** SCADwright exists to give you Python's expressiveness — real classes that publish dimensions, real error messages with line numbers, real test infrastructure, real CLI argument parsing, a real module ecosystem — while emitting standard OpenSCAD as the output format. If your projects fit comfortably in OpenSCAD's `module` / `function` model and you don't miss the things above, plain OpenSCAD is one less moving part. The pain points SCADwright addresses (modules can't expose dimensions, errors don't tell you where, etc.) are the headers in this project's [README](../README.md).
