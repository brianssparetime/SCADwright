"""Tests for the Emitter ABC contract (MajorReview Group 6b)."""

import pytest

from scadwright.emit.visitor import Emitter, Visitor


def test_emitter_is_abstract():
    with pytest.raises(TypeError, match="abstract"):
        Emitter()


def test_visitor_is_not_abstract():
    # Visitor is an ordinary base; direct instantiation is allowed.
    Visitor()


def test_scademitter_is_emitter_subclass():
    from scadwright.emit.scad import SCADEmitter

    assert issubclass(SCADEmitter, Emitter)


def test_custom_emitter_without_emit_root_is_abstract():
    class Incomplete(Emitter):
        pass

    with pytest.raises(TypeError, match="abstract"):
        Incomplete()


def test_custom_emitter_with_emit_root_instantiates():
    class Minimal(Emitter):
        def emit_root(self, node):
            return None

    Minimal()  # no raise
