import logging

import pytest

from scadwright import Component, emit_str, materialize, resolution, set_verbose
from scadwright.primitives import cube
@pytest.fixture(autouse=True)
def reset_scadwright_logger():
    """Ensure clean state for each test."""
    logger = logging.getLogger("scadwright")
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    saved_propagate = logger.propagate
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    yield
    for h in list(logger.handlers):
        logger.removeHandler(h)
    for h in saved_handlers:
        logger.addHandler(h)
    logger.setLevel(saved_level)
    logger.propagate = saved_propagate


def test_component_build_logs_at_info(caplog):
    class _W(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            return cube(1)

    with caplog.at_level(logging.INFO, logger="scadwright.component"):
        materialize(_W())

    assert any("built _W" in r.message for r in caplog.records)


def test_emit_logs_at_info(caplog):
    with caplog.at_level(logging.INFO, logger="scadwright.emit"):
        emit_str(cube(1))

    assert any("emitted" in r.message for r in caplog.records)


def test_resolution_logs_at_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger="scadwright.resolution"):
        with resolution(fn=32):
            pass

    msgs = [r.message for r in caplog.records]
    assert any("enter resolution" in m for m in msgs)
    assert any("exit resolution" in m for m in msgs)


def test_set_verbose_idempotent():
    set_verbose(logging.INFO)
    set_verbose(logging.INFO)
    set_verbose(logging.DEBUG)
    logger = logging.getLogger("scadwright")
    managed = [h for h in logger.handlers if getattr(h, "_scadwright_managed", False)]
    assert len(managed) == 1


def test_set_verbose_false_quiets():
    set_verbose(False)
    logger = logging.getLogger("scadwright")
    assert logger.level == logging.WARNING


def test_library_silent_by_default(caplog):
    """Library must not emit anything at import time or at INFO without set_verbose."""
    # We're inside caplog which configures propagation — this still tests that
    # we don't spam WARNING-level things unprompted.
    with caplog.at_level(logging.WARNING, logger="scadwright"):
        materialize(_FreshComponent())
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 0


class _FreshComponent(Component):
    def __init__(self):
        super().__init__()

    def build(self):
        return cube(1)
