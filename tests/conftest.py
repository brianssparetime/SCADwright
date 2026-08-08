"""pytest config — register markers, expose helpers."""

import os
import shutil
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
def bundled_fonts_dir() -> Path:
    """Directory holding the test-bundled Liberation Sans Regular TTF.

    The font ships in ``tests/fixtures/fonts/`` under the SIL OFL — see the
    sibling LICENSE.
    """
    d = Path(__file__).parent / "fixtures" / "fonts"
    if not (d / "LiberationSans-Regular.ttf").is_file():
        raise RuntimeError(
            f"bundled test font missing under {d}. "
            "Did you skip the test-fixtures setup?"
        )
    return d


@pytest.fixture(scope="session")
def fontconfig_conf(tmp_path_factory, bundled_fonts_dir) -> str:
    """Path to a minimal fontconfig config scanning only the bundled fonts.

    Pointing ``FONTCONFIG_FILE`` at this makes ``fc-match`` resolve names
    deterministically from ``tests/fixtures/fonts/`` alone — no system fonts —
    so the real fontconfig resolution path is exercised without depending on
    the host's installed fonts. Skips the test when ``fc-match`` is absent.
    """
    if shutil.which("fc-match") is None:
        pytest.skip("fontconfig `fc-match` not installed")
    d = tmp_path_factory.mktemp("fontconfig")
    cache = d / "cache"
    cache.mkdir()
    conf = d / "fonts.conf"
    conf.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        "<fontconfig>\n"
        f"  <dir>{bundled_fonts_dir}</dir>\n"
        f"  <cachedir>{cache}</cachedir>\n"
        "</fontconfig>\n"
    )
    return str(conf)


@pytest.fixture
def named_font(fontconfig_conf, monkeypatch) -> str:
    """Resolve font names from the bundled fixtures only, and return the
    family name to pass as ``font=``. With only Liberation Sans in scope,
    ``fc-match`` returns it for that name (and substitutes it for any other).
    """
    monkeypatch.setenv("FONTCONFIG_FILE", fontconfig_conf)
    return "Liberation Sans"


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
    try:
        from scadwright._custom_transforms import _textmetrics
    except ImportError:
        return  # module not yet added (commit 1 / pre-commit-2)

    # Clear the resolved-face cache either way. A marked test warms it,
    # and _resolve_face serves from it without re-probing freetype, so an
    # unmarked test that ran afterwards would silently get real metrics
    # and no longer be testing the path it claims to.
    _textmetrics._reset_state_for_tests()

    if request.node.get_closest_marker("freetype"):
        return  # opt-in: leave the real path active
    monkeypatch.setattr(_textmetrics, "_try_import_freetype", lambda: None)
    # Reset the import-probe cache so the patch takes effect on the next call.
    monkeypatch.setattr(_textmetrics, "_FREETYPE_AVAILABLE", None, raising=False)


@pytest.fixture(autouse=True)
def _reset_overflow_warn_state():
    """Clear the once-per-fact overflow warning caches between tests.

    ``add_text`` warns once per overflow and once per font when it can't
    measure, so a part with fifty labels doesn't emit fifty lines. Those
    caches are module-level, so without this a test that triggers a
    warning silences the next test that expects the same one.
    """
    try:
        from scadwright._custom_transforms.add_text import (
            _reset_overflow_state_for_tests,
        )
    except ImportError:
        yield
        return
    _reset_overflow_state_for_tests()
    yield
    _reset_overflow_state_for_tests()
