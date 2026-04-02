from spinelab.ui.theme import GEOMETRY, capsule_radius, concentric_radius


def test_concentric_radius_subtracts_with_floor() -> None:
    assert concentric_radius(20) == 12
    assert concentric_radius(12) == 10


def test_capsule_radius_is_half_height() -> None:
    assert capsule_radius(36) == 18
    assert capsule_radius(44) == 22


def test_geometry_nested_radius_steps_down_from_inner_radius() -> None:
    assert GEOMETRY.radius_panel == 12
    assert GEOMETRY.radius_inner == 8
    assert GEOMETRY.radius_nested == 10
