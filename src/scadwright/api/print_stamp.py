"""Git-derived stamp text for embossing on printed parts.

``print_stamp()`` returns the short SHA of the current ``HEAD`` so a physical
artifact can be tied back to recoverable source. Recovery is then a matter of
``git show <sha>:path/to/source.py``. The default behavior refuses to produce
a stamp when the working tree has uncommitted changes — a dirty stamp would
record an identifier that cannot reproduce the geometry.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scadwright.errors import SCADwrightError


def print_stamp(
    *,
    allow_dirty: bool = False,
    length: int = 7,
    cwd: str | Path | None = None,
) -> str:
    """Return a short git-SHA stamp string for embedding on a printed part.

    Arguments:
        allow_dirty: When ``False`` (default), raise if tracked files differ
            from ``HEAD``. When ``True``, return the SHA with a ``-dirty``
            suffix so the stamp records that the exact source is not
            recoverable from the commit alone.
        length: Hex characters to keep from the SHA. Must be 4..40.
        cwd: Directory to run ``git`` in. Defaults to the process cwd.

    Returns the abbreviated SHA, e.g. ``"a1b2c3d"`` or ``"a1b2c3d-dirty"``.

    Raises ``SCADwrightError`` if ``git`` is missing, ``cwd`` is not a git
    working tree, ``HEAD`` has no commit, or the tree is dirty without
    ``allow_dirty=True``.
    """
    if not isinstance(length, int) or length < 4 or length > 40:
        raise SCADwrightError(
            f"print_stamp: length must be an int in 4..40 (got {length!r})"
        )
    if shutil.which("git") is None:
        raise SCADwrightError("print_stamp: 'git' executable not found on PATH")
    work = Path(cwd) if cwd is not None else Path.cwd()

    def _git(*args: str) -> tuple[int, str, str]:
        result = subprocess.run(
            ["git", *args],
            cwd=str(work),
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    code, out, err = _git("rev-parse", "--is-inside-work-tree")
    if code != 0 or out.strip() != "true":
        msg = err.strip() or "not a git working tree"
        raise SCADwrightError(f"print_stamp: {msg} (cwd={work})")

    code, out, err = _git("rev-parse", f"--short={length}", "HEAD")
    if code != 0:
        msg = err.strip() or "could not resolve HEAD"
        raise SCADwrightError(f"print_stamp: {msg}")
    sha = out.strip()

    # Tracked-files-only: untracked files don't change what
    # `git show <sha>:source.py` would produce, so they don't compromise
    # the stamp's recoverability claim.
    _, out, _ = _git("status", "--porcelain", "--untracked-files=no")
    dirty = bool(out.strip())
    if dirty and not allow_dirty:
        raise SCADwrightError(
            "print_stamp: working tree has uncommitted changes — "
            "commit them first, or pass allow_dirty=True to stamp with "
            "a '-dirty' suffix"
        )
    return f"{sha}-dirty" if dirty else sha
