from scadwright.primitives import cube
def test_cube_scalar_broadcasts():
    c = cube(10)
    assert c.size == (10.0, 10.0, 10.0)


def test_cube_vector():
    c = cube([1, 2, 3])
    assert c.size == (1.0, 2.0, 3.0)


def test_cube_center_default_false():
    c = cube([1, 2, 3])
    assert c.center == (False, False, False)


def test_cube_center_true_broadcasts():
    c = cube([1, 2, 3], center=True)
    assert c.center == (True, True, True)


def test_cube_center_string():
    c = cube([1, 2, 3], center="xy")
    assert c.center == (True, True, False)


def test_cube_center_string_full():
    c = cube([1, 2, 3], center="xyz")
    assert c.center == (True, True, True)


def test_cube_center_list():
    c = cube([1, 2, 3], center=[True, False, True])
    assert c.center == (True, False, True)


def test_cube_is_frozen():
    import dataclasses

    c = cube(10)
    try:
        c.size = (1, 2, 3)  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    except AttributeError:
        return
    raise AssertionError("Cube should be frozen")
