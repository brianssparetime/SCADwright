"""Face winding for ``polyhedron``.

OpenSCAD orders a face's vertices clockwise seen from outside, which
puts the right-hand normal on the inside and makes a correct mesh's
signed volume negative. That is a detail of OpenSCAD's file format
rather than a decision the author of a part is making, so
:func:`orient_for_openscad` fixes it wherever fixing it is unambiguous.

Getting it wrong is expensive to notice. CGAL builds its Nef from the
polygon soup and ignores winding entirely, so an exact render, an STL
export, and every geometric assertion all pass. OpenCSG resolves
booleans from front and back facing, so a backwards mesh is culled: it
renders as nothing inside a ``difference()`` or ``intersection()`` and
as a normal solid on its own.
"""

from __future__ import annotations

from typing import NamedTuple

Point = tuple[float, float, float]
Face = tuple[int, ...]

# A closed mesh whose volume is this small relative to its own size has
# no reliable sense to read. Scale-relative so it holds for a part
# measured in metres or in microns.
_DEGENERATE_FRACTION = 1e-9


class Problem(NamedTuple):
    """Why the winding could not be settled. ``kind`` is one of
    ``"inconsistent"``, ``"open"``, or ``"degenerate"``."""

    kind: str
    message: str


def orient_for_openscad(
    points: list[Point] | tuple[Point, ...],
    faces: list[Face] | tuple[Face, ...],
) -> tuple[tuple[Face, ...], Problem | None]:
    """Return ``(faces, problem)`` with faces in OpenSCAD's winding.

    A mesh that is closed and consistently wound has a determinable
    sense, and comes back oriented correctly whichever way it went in.
    Anything else comes back untouched, with a :class:`Problem` saying
    what stopped us. The caller decides whether that is worth raising
    over: an inconsistent mesh cannot be repaired by flipping, while an
    open one is usually a mistake but still renders.
    """
    faces = tuple(tuple(f) for f in faces)
    canon, first_original = _canonical_indices(points)

    dup = _first_repeated_directed_edge(faces, canon)
    if dup is not None:
        (a, b), fi, fj = dup
        return faces, Problem("inconsistent", _inconsistent_message(
            first_original[a], first_original[b], fi, fj,
        ))

    boundary = _boundary_edges(faces, canon)
    if boundary:
        a, b = boundary[0]
        return faces, Problem("open", _open_message(
            len(boundary), first_original[a], first_original[b],
        ))

    volume = signed_volume(points, faces)
    if abs(volume) <= _DEGENERATE_FRACTION * _scale_cubed(points):
        return faces, Problem("degenerate", _degenerate_message(volume))

    if volume > 0:
        return tuple(tuple(reversed(f)) for f in faces), None
    return faces, None


def signed_volume(points, faces) -> float:
    """Volume enclosed by ``faces``, signed by their winding.

    Negative under OpenSCAD's convention. Each face is fanned from its
    first vertex, which is exact for planar faces and good enough for
    the sign on anything a renderer would accept.
    """
    total = 0.0
    for face in faces:
        for k in range(1, len(face) - 1):
            ax, ay, az = points[face[0]]
            bx, by, bz = points[face[k]]
            cx, cy, cz = points[face[k + 1]]
            total += (
                ax * (by * cz - bz * cy)
                - ay * (bx * cz - bz * cx)
                + az * (bx * cy - by * cx)
            )
    return total / 6.0


# --- Internals ---


def _canonical_indices(points) -> tuple[list[int], list[int]]:
    """Collapse points that share coordinates exactly.

    A generator that emits a seam vertex twice produces a mesh that is
    closed geometrically and open by index. Matching on exact equality
    settles that without a tolerance: identical coordinates are one
    point, and coordinates a micron apart are two, which is the truth
    the renderer will act on either way.

    Returns ``canonical[i]`` for each input index, and for each
    canonical index the first input index that reached it, so messages
    can name a point the caller actually wrote.
    """
    seen: dict[Point, int] = {}
    canonical: list[int] = []
    first_original: list[int] = []
    for i, p in enumerate(points):
        key = tuple(p)
        if key not in seen:
            seen[key] = len(seen)
            first_original.append(i)
        canonical.append(seen[key])
    return canonical, first_original


def _first_repeated_directed_edge(faces, canon):
    """Find an edge two faces both traverse the same way, or None.

    In a consistently wound closed mesh each edge is walked once in
    each direction. A repeat means two neighbouring faces disagree
    about which side is out.
    """
    owner: dict[tuple[int, int], int] = {}
    for fi, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            edge = (canon[face[i]], canon[face[(i + 1) % n]])
            if edge in owner:
                return edge, owner[edge], fi
            owner[edge] = fi
    return None


def _boundary_edges(faces, canon) -> list[tuple[int, int]]:
    """Edges not shared by exactly two faces. Empty for a closed mesh."""
    counts: dict[tuple[int, int], int] = {}
    for face in faces:
        n = len(face)
        for i in range(n):
            a, b = canon[face[i]], canon[face[(i + 1) % n]]
            key = (a, b) if a < b else (b, a)
            counts[key] = counts.get(key, 0) + 1
    return [e for e, n in counts.items() if n != 2]


def _scale_cubed(points) -> float:
    """Cube of the bounding box diagonal, as a volume to compare against."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    diag = (
        (max(xs) - min(xs)) ** 2
        + (max(ys) - min(ys)) ** 2
        + (max(zs) - min(zs)) ** 2
    ) ** 0.5
    return diag ** 3


def _inconsistent_message(pa: int, pb: int, fi: int, fj: int) -> str:
    return (
        f"faces[{fi}] and faces[{fj}] both run along the edge from "
        f"points[{pa}] to points[{pb}] in the same direction, so the mesh "
        f"is not wound consistently. Two faces sharing an edge have to "
        f"walk it in opposite directions. Reverse one of the two, then "
        f"work outwards from it until every face agrees with its "
        f"neighbours; the generator that built them usually has one "
        f"loop running the wrong way. SCADwright turns a mesh that is "
        f"wound consistently the wrong way round, but it cannot decide "
        f"which of two conflicting faces is the right one."
    )


def _open_message(count: int, pa: int, pb: int) -> str:
    return (
        f"the mesh is not closed: {count} "
        f"{'edge belongs' if count == 1 else 'edges belong'} to one face "
        f"instead of two, starting with the edge from points[{pa}] to "
        f"points[{pb}]. This is almost always a mistake. OpenSCAD will "
        f"render it, but a boolean against an open mesh produces "
        f"nonsense and an exact render can fail outright. The usual "
        f"causes are a missing cap face and a seam whose two sides use "
        f"different point indices for the same corner. Emitting it as "
        f"given; SCADwright cannot tell which way round an open mesh "
        f"faces, so its winding is left alone too."
    )


def _degenerate_message(volume: float) -> str:
    return (
        f"the mesh is closed but encloses no volume ({volume:g} against "
        f"its own size), so there is no outside for its faces to face "
        f"and SCADwright cannot tell whether they are wound correctly. "
        f"A shell with coincident front and back surfaces does this. "
        f"Emitting it as given, though OpenSCAD is unlikely to make "
        f"anything of it."
    )
