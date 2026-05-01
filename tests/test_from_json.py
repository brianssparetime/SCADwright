"""`from_json()` — pass complex/nested data into a script via `--from-json`."""

from __future__ import annotations

import json

import pytest

from scadwright import from_json
from scadwright.api import args as _args
from scadwright.errors import SCADwrightError


@pytest.fixture(autouse=True)
def reset_args():
    _args._reset_for_testing()
    yield
    _args._reset_for_testing()


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return str(p)


# =============================================================================
# Single-payload mode: from_json() with no name.
# =============================================================================


def test_single_payload_returns_content(tmp_path):
    path = _write(tmp_path, "design.json", {"elements": [1, 2, 3]})
    _args.set_argv(["--from-json", path])
    assert from_json() == {"elements": [1, 2, 3]}


def test_single_payload_named_match_by_basename(tmp_path):
    path = _write(tmp_path, "design.json", {"k": "v"})
    _args.set_argv(["--from-json", path])
    # Same single payload — named call matches by basename regardless
    # of the absolute path the runner passed.
    assert from_json("design.json") == {"k": "v"}


def test_no_payload_returns_none():
    _args.set_argv([])
    assert from_json() is None


def test_no_payload_named_returns_none():
    _args.set_argv([])
    assert from_json("anything.json") is None


def test_no_payload_required_errors():
    _args.set_argv([])
    with pytest.raises(SCADwrightError, match="--from-json is required"):
        from_json(required=True)


def test_named_missing_required_errors(tmp_path):
    path = _write(tmp_path, "design.json", {"k": "v"})
    _args.set_argv(["--from-json", path])
    with pytest.raises(SCADwrightError, match="other.json"):
        from_json("other.json", required=True)


# =============================================================================
# Named mode: multiple --from-json payloads disambiguated by basename.
# =============================================================================


def test_two_payloads_named_each(tmp_path):
    a = _write(tmp_path, "design.json", {"a": 1})
    b = _write(tmp_path, "clearances.json", {"b": 2})
    _args.set_argv(["--from-json", a, "--from-json", b])
    assert from_json("design.json") == {"a": 1}
    assert from_json("clearances.json") == {"b": 2}


def test_two_payloads_unnamed_call_errors(tmp_path):
    a = _write(tmp_path, "design.json", {"a": 1})
    b = _write(tmp_path, "clearances.json", {"b": 2})
    _args.set_argv(["--from-json", a, "--from-json", b])
    with pytest.raises(SCADwrightError, match="Disambiguate"):
        from_json()


def test_basename_collision_errors(tmp_path):
    a = _write(tmp_path / "a", "design.json", {"a": 1}) if False else None
    # Two files with the same basename in different dirs.
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    p1 = _write(tmp_path / "a", "design.json", {"src": "a"})
    p2 = _write(tmp_path / "b", "design.json", {"src": "b"})
    _args.set_argv(["--from-json", p1, "--from-json", p2])
    with pytest.raises(SCADwrightError, match="basename collision"):
        from_json()


# =============================================================================
# Error surfaces: malformed file, bad JSON.
# =============================================================================


def test_missing_file_errors(tmp_path):
    _args.set_argv(["--from-json", str(tmp_path / "does-not-exist.json")])
    with pytest.raises(SCADwrightError, match="file not found"):
        from_json()


def test_invalid_json_errors(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json")
    _args.set_argv(["--from-json", str(p)])
    with pytest.raises(SCADwrightError, match="invalid JSON"):
        from_json()


# =============================================================================
# Content shapes: dict, list, scalar — all valid JSON top-levels.
# =============================================================================


def test_list_payload(tmp_path):
    p = _write(tmp_path, "items.json", [1, 2, 3])
    _args.set_argv(["--from-json", p])
    assert from_json() == [1, 2, 3]


def test_scalar_payload(tmp_path):
    p = _write(tmp_path, "n.json", 42)
    _args.set_argv(["--from-json", p])
    assert from_json() == 42


def test_nested_payload_shape_preserved(tmp_path):
    nested = {
        "elements": [
            {"code": "A", "diameter": 10.0},
            {"code": "B", "diameter": 12.5, "mounted_od": 14.0},
        ],
        "stop": {"depth": 5, "hole_diameters": [20.0, 14.3]},
    }
    p = _write(tmp_path, "design.json", nested)
    _args.set_argv(["--from-json", p])
    assert from_json() == nested


# =============================================================================
# Caching: from_json() doesn't re-read the file on subsequent calls.
# =============================================================================


def test_repeated_call_caches(tmp_path):
    p = _write(tmp_path, "design.json", {"v": 1})
    _args.set_argv(["--from-json", p])
    first = from_json()
    # Mutate the file on disk; the next call should still return the cached
    # parse, since payloads are loaded once per --from-json set.
    (tmp_path / "design.json").write_text(json.dumps({"v": 2}))
    second = from_json()
    assert first == second == {"v": 1}


# =============================================================================
# Lazy registration: --help only shows --from-json after a from_json() call.
# =============================================================================


def test_lazy_registration():
    """--from-json registers on first call, not on import."""
    _args.set_argv([])
    parser = _args._get_parser()
    # Before any from_json() call, the flag isn't on the parser.
    actions = {a.dest for a in parser._actions}
    assert "from_json" not in actions
    # After the call, it is.
    from_json()
    actions = {a.dest for a in parser._actions}
    assert "from_json" in actions


# =============================================================================
# Coexists with arg().
# =============================================================================


def test_coexists_with_arg(tmp_path):
    from scadwright import arg
    p = _write(tmp_path, "design.json", {"k": "v"})
    _args.set_argv(["--width=80", "--from-json", p])
    assert arg("width", default=40, type=float) == 80.0
    assert from_json() == {"k": "v"}
