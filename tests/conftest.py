"""pytest config — register markers, expose helpers."""

import os


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: opt-in tests that shell out to external tools (OpenSCAD). "
        "Run with `pytest -m integration` or set SCADWRIGHT_TEST_OPENSCAD=1.",
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless explicitly enabled."""
    if config.getoption("-m") and "integration" in config.getoption("-m"):
        return
    if os.environ.get("SCADWRIGHT_TEST_OPENSCAD"):
        return
    import pytest

    skip_int = pytest.mark.skip(reason="set SCADWRIGHT_TEST_OPENSCAD=1 or `-m integration` to enable")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_int)
