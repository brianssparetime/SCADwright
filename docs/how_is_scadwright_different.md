# How is SCADwright different?

If you searched "Python OpenSCAD" or "Python parametric CAD," several other projects probably came up. Here is how SCADwright relates to each. The goal isn't to argue SCADwright wins on every axis. It's to help you pick the right tool for what you're building.

## SolidPython / SolidPython2

[SolidPython](https://github.com/SolidCode/SolidPython) and its actively-maintained successor [SolidPython2](https://github.com/jeff-dh/SolidPython) are the most common Python wrappers around OpenSCAD. Like SCADwright, they turn a Python script into `.scad` source.

Components carry their own dimensions. A SolidPython part is a function that returns geometry, so the caller can't ask where its mount holes are without redoing the math. A SCADwright `Component` relates its inputs through an `equations` list: declare `od = id + 2*thk`, supply any two, and SCADwright solves for the third. The caller then reads every input and every solved value straight off the part, like `tube.od` or `bracket.rise`.

Errors point at the line that caused them. `cube([-5, 10, 10])` raises `ValidationError: cube size[0] must be non-negative, got -5.0 (at widget.py:42)`. SolidPython hands the bad value to OpenSCAD, and you work backward from the rendered output.

A shape library comes with the package. `Tube`, `Funnel`, `RoundedBox`, `FilletRing`, `Sector`, `RoundedSlot`, and others are ready to use. SolidPython gives you the OpenSCAD primitives and leaves the reusable shapes for you to copy between projects.

Tests pin geometry. `tree_hash` fails a test when a part's output changes, and `assert_fits_in`, `assert_contains`, and `assert_no_collision` check geometry directly.

Variants are named and selectable. Print and display versions of a part are real objects you choose between, not code blocks you comment in and out.

If you mostly want a thin Python layer over OpenSCAD's verbs and none of the above, SolidPython2 is lighter and well-established.

## OpenPySCAD

[OpenPySCAD](https://github.com/taxpon/openpyscad) is another wrapper that generates SCAD source, with goals much like SolidPython's: chained transforms on shape objects, then `.dumps()` to a string. The difference from SCADwright is the same one SolidPython has, namely Components, errors with source locations, a shape library, equations, tests, variants, and a command-line tool. Development has been quiet for several years, so for a fresh start today SCADwright or SolidPython2 are more current.

## PythonSCAD (gsohler/openscad fork)

[PythonSCAD](https://pythonscad.org/) is Guillaume Sohler's fork that *replaces* OpenSCAD's interpreter with Python. Your script runs inside the OpenSCAD process and emits geometry straight to its CSG engine, with no `.scad` file in between.

The objective is different. PythonSCAD makes Python the language inside OpenSCAD. SCADwright stays outside it: you author in Python, SCADwright writes a standard `.scad` file, and you open that file in stock OpenSCAD or any other tool that reads SCAD. No fork required.

That objective drives the rest. SCADwright installs with `pip` and works with any OpenSCAD version, while PythonSCAD needs its own custom OpenSCAD build. SCADwright's output is plain SCAD that other people, scripts, and tools can read or change; a PythonSCAD script only runs inside the forked interpreter.

If you've committed to OpenSCAD as your whole environment and want Python's expressiveness inside it, PythonSCAD is the more direct route. If you want a Python toolchain that produces standard SCAD, use SCADwright.

## OpenJSCAD / JSCAD

[JSCAD](https://openjscad.xyz/) is a JavaScript parametric modeling library with its own renderer. The general idea matches SolidPython's, author in code and render to a mesh, but the language is JavaScript and the renderer is built in. The choice is mostly language and runtime: SCADwright is Python and emits `.scad` for OpenSCAD to render, JSCAD is JavaScript with its own web-based renderer. Both are mature, so pick the language you'd rather write.

## CadQuery

[CadQuery](https://github.com/CadQuery/cadquery) is a Python library built on the OpenCASCADE B-Rep CAD kernel, the closest open-source analogue to commercial parametric CAD like SolidWorks or Onshape. B-Rep represents curved surfaces exactly and exports STEP and IGES. SCADwright, through OpenSCAD, is CSG, and its curves become a mesh at render time.

Reach for CadQuery when the part leaves the 3D printer. Machined parts (CNC, lathe, mill), mechanical fits that need surface continuity (gear teeth, bearing races), exchange with traditional CAD and CAM through STEP and IGES, and FEA simulation all depend on that exact-surface representation.

Reach for SCADwright when the STL mesh is the deliverable, as it is for most 3D printing. SCADwright is simpler to install and faster to change and re-render, and it emits readable `.scad` you can diff and share. Its Component model, where a part reports its own dimensions to the caller, is the main thing it adds over both CadQuery's scripts and plain OpenSCAD.

## Build123d

[Build123d](https://github.com/gumyr/build123d) is a newer Python CAD library, also OpenCASCADE-based. It shares CadQuery's geometric capabilities behind a different and often nicer API. It sits on the same axis as CadQuery does against SCADwright: B-Rep and industrial CAD output on one side, OpenSCAD and mesh CSG with `.scad` output on the other. Choose SCADwright for OpenSCAD-style work and Build123d for the niche CadQuery serves.

## Plain OpenSCAD

OpenSCAD itself, with no Python.

SCADwright exists to bring Python's expressiveness to OpenSCAD work while keeping standard `.scad` as the output format. That means real classes whose parts report their dimensions, error messages with line numbers, test infrastructure, command-line argument parsing, and a module ecosystem. If your projects fit comfortably in OpenSCAD's `module` and `function` model and you don't miss those, plain OpenSCAD is one less moving part. The pain points SCADwright addresses, like modules that can't report their dimensions and errors that don't tell you where, are the section headers in this project's [README](../README.md).
