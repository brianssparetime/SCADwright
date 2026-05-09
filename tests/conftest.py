"""pytest config — register markers, expose helpers."""

import os
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: opt-in tests that shell out to external tools (OpenSCAD). "
        "Run with `pytest -m integration` or set SCADWRIGHT_TEST_OPENSCAD=1.",
    )
    config.addinivalue_line(
        "markers",
        "freetype: tests that exercise the real freetype-py path in "
        "scadwright._custom_transforms._textmetrics. By default the autouse "
        "_disable_freetype fixture forces the heuristic fallback; this marker "
        "opts out of that, so the test runs against real font metrics. "
        "Skipped if freetype-py isn't installed.",
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless explicitly enabled."""
    if config.getoption("-m") and "integration" in config.getoption("-m"):
        return
    if os.environ.get("SCADWRIGHT_TEST_OPENSCAD"):
        return

    skip_int = pytest.mark.skip(reason="set SCADWRIGHT_TEST_OPENSCAD=1 or `-m integration` to enable")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_int)


# --- Font / textmetrics fixtures ---


@pytest.fixture(scope="session")
def bundled_font_path() -> str:
    """Absolute path to the test-bundled Liberation Sans Regular TTF.

    Tests pass this as ``font=<path>`` to bypass system font resolution and
    get deterministic metrics across machines. The font ships in
    ``tests/fixtures/fonts/`` under the SIL OFL — see the sibling LICENSE.
    """
    p = Path(__file__).parent / "fixtures" / "fonts" / "LiberationSans-Regular.ttf"
    if not p.is_file():
        raise RuntimeError(
            f"bundled test font missing: {p}. "
            "Did you skip the test-fixtures setup?"
        )
    return str(p)


@pytest.fixture(autouse=True)
def _disable_freetype(request, monkeypatch):
    """Force the heuristic fallback path in ``get_advances`` for every test
    that doesn't carry the ``@pytest.mark.freetype`` marker.

    Why: golden ``.scad`` files encode the heuristic-mode emission so they
    stay deterministic without freetype-py installed. Any test that wants
    real metrics must opt in by adding the ``freetype`` marker; that test
    is also responsible for passing an explicit font path so it doesn't
    depend on the host's system font search path.
    """
    if request.node.get_closest_marker("freetype"):
        return  # opt-in: leave the real path active
    try:
        from scadwright._custom_transforms import _textmetrics
    except ImportError:
        return  # module not yet added (commit 1 / pre-commit-2)
    monkeypatch.setattr(_textmetrics, "_try_import_freetype", lambda: None)
    # Reset the import-probe cache so the patch takes effect on the next call.
    monkeypatch.setattr(_textmetrics, "_FREETYPE_AVAILABLE", None, raising=False)
