"""Tests for SCAD echo() — diagnostic statement, with or without subject."""

from scadwright import bbox, emit_str
from scadwright.debug import echo
from scadwright.primitives import cube


def test_echo_bare_statement():
    out = emit_str(echo("hello"), banner=False).strip()
    assert out == 'echo("hello");'


def test_echo_chained_wraps_subtree():
    out = emit_str(cube(10).echo("size"))
    assert 'echo("size")' in out
    assert "cube" in out
    assert "{" in out  # braces around the wrapped child


def test_echo_standalone_with_node_wraps():
    out = emit_str(echo("label", _node=cube(5)))
    assert 'echo("label")' in out
    assert "cube" in out


def test_echo_positional_args_preserved_in_order():
    out = emit_str(echo(1, 2, 3))
    assert 'echo(1, 2, 3)' in out


def test_echo_keyword_args_emit_as_named():
    out = emit_str(echo(name="widget", count=3))
    assert "name=" in out
    assert '"widget"' in out
    assert "count=3" in out


def test_echo_mixed_positional_and_keyword():
    out = emit_str(echo("label:", value=42))
    assert '"label:"' in out
    assert "value=42" in out


def test_echo_string_escaping():
    out = emit_str(echo('it\'s "quoted"'))
    assert r'\"quoted\"' in out


def test_echo_bare_has_zero_bbox():
    bb = bbox(echo("hi"))
    assert bb.min == (0, 0, 0) and bb.max == (0, 0, 0)


def test_echo_wrapping_passes_bbox_through():
    bb = bbox(cube(10).echo("label"))
    assert bb.max == (10.0, 10.0, 10.0)


def test_echo_vector_arg():
    out = emit_str(echo([1, 2, 3]))
    assert "[1, 2, 3]" in out
