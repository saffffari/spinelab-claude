import builtins

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel

from spinelab.visualization import SpineViewport3D, viewer_3d
from spinelab.visualization.viewer_3d import (
    DETAIL_PRESET_LEVELS,
    VIEWPORT_MODE_ICON_PATHS,
    MockVertebra,
    OrthographicMeshViewport,
    _import_optional_viewer_backends,
    apply_group_transform,
    apply_point_rendering,
    build_grid_line_positions,
    build_line_segment_mesh,
    build_pelvis_world_transform,
    coerce_detail_level,
    detail_preset_level,
    mesh_cache_key_for_spec,
    mesh_detail_reduction,
    nice_grid_step,
    orbit_camera_about_up_axis,
    orthographic_zoom_scale,
    pan_camera_from_screen_delta,
    prewarm_lod_mesh_cache,
)
from spinelab.visualization.viewport_gnomon import (
    GNOMON_VIEWPORT,
    ViewportGnomonOverlay,
    configure_plotter_gnomon,
)
from spinelab.visualization.viewport_theme import (
    MODEL_BASE_COLOR,
    MODEL_BASE_EDGE_COLOR,
    MODEL_REFERENCE_COLOR,
    MODEL_REFERENCE_EDGE_COLOR,
    MODEL_STANDING_COLOR,
    MODEL_STANDING_EDGE_COLOR,
    VIEWPORT_MODES,
    ViewportMode,
    resolve_mesh_visual_colors,
    resolve_mode_edge_color,
)


def test_nice_grid_step_scales_with_visible_span() -> None:
    assert nice_grid_step(1.2) == 0.2
    assert nice_grid_step(12.0) == 2.0
    assert nice_grid_step(120.0) == 20.0


def test_build_grid_line_positions_marks_major_lines() -> None:
    positions = build_grid_line_positions(-4.0, 4.0, 1.0)

    assert (0.0, True) in positions
    assert (-4.0, False) in positions
    assert (4.0, False) in positions


def test_build_line_segment_mesh_batches_segments_into_one_polydata() -> None:
    mesh = build_line_segment_mesh(
        [
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
            ((0.0, 1.0, 0.0), (1.0, 1.0, 0.0)),
        ]
    )

    assert mesh is not None
    assert mesh.n_points == 4
    assert mesh.n_lines == 2


def test_orthographic_zoom_scale_changes_with_wheel_direction() -> None:
    assert orthographic_zoom_scale(100.0, 120) < 100.0
    assert orthographic_zoom_scale(100.0, -120) > 100.0
    assert orthographic_zoom_scale(0.1, 120) == 0.25


def test_detail_level_helpers_clamp_and_reduce() -> None:
    assert coerce_detail_level(-5) == 0
    assert coerce_detail_level(99) == 3
    assert mesh_detail_reduction(0) > mesh_detail_reduction(2)
    assert mesh_detail_reduction(3) == 0.0
    assert detail_preset_level(1) == 0
    assert detail_preset_level(2) == 2
    assert detail_preset_level(3) == 3


def test_reference_visual_color_is_orange_for_all_poses() -> None:
    baseline_reference = resolve_mesh_visual_colors(
        "baseline",
        selected=False,
        reference=True,
    )
    standing_reference = resolve_mesh_visual_colors(
        "standing",
        selected=False,
        reference=True,
    )
    baseline_selected = resolve_mesh_visual_colors(
        "baseline",
        selected=True,
        reference=False,
    )

    assert baseline_reference.fill == MODEL_REFERENCE_COLOR
    assert baseline_reference.edge == MODEL_REFERENCE_EDGE_COLOR
    assert standing_reference.fill == MODEL_REFERENCE_COLOR
    assert standing_reference.edge == MODEL_REFERENCE_EDGE_COLOR
    assert baseline_selected.fill != MODEL_REFERENCE_COLOR


def test_prewarm_lod_mesh_cache_populates_all_requested_levels(monkeypatch) -> None:
    spec = MockVertebra(
        "L3",
        "L3",
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0),
        mesh_data=object(),
    )
    build_calls: list[int] = []

    def fake_build_mock_mesh(candidate: MockVertebra):
        assert candidate is spec
        return "base-mesh"

    def fake_load_lod_mesh(candidate: MockVertebra, base_mesh, detail_level: int):
        assert candidate is spec
        assert base_mesh == "base-mesh"
        build_calls.append(detail_level)
        return object()

    monkeypatch.setattr(viewer_3d, "build_mock_mesh", fake_build_mock_mesh)
    monkeypatch.setattr(viewer_3d, "load_lod_mesh", fake_load_lod_mesh)

    prewarm_lod_mesh_cache((spec,), detail_levels=(0, 2, 3))

    assert build_calls == [0, 2, 3]


def test_mesh_cache_key_distinguishes_pose_and_actor() -> None:
    baseline = MockVertebra("L1", "L1", (0, 0, 0), (1, 1, 1), mesh_path="C:/tmp/demo.glb")
    standing = MockVertebra(
        "L1",
        "L1 Standing",
        (0, 0, 0),
        (1, 1, 1),
        mesh_path="C:/tmp/demo.glb",
        render_id="L1_STANDING",
        pose_name="standing",
    )

    assert mesh_cache_key_for_spec(baseline) != mesh_cache_key_for_spec(standing)


def test_optional_viewer_backends_do_not_require_trimesh(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "trimesh":
            raise ImportError("trimesh intentionally unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    pv_module, trimesh_module, qt_interactor = _import_optional_viewer_backends()

    assert viewer_3d.pv is not None
    assert pv_module is not None
    assert trimesh_module is None
    assert qt_interactor is not None


def test_configure_plotter_gnomon_uses_shared_bottom_left_viewport() -> None:
    class MockPlotter:
        def __init__(self) -> None:
            self.kwargs = None

        def add_axes(self, **kwargs):
            self.kwargs = kwargs
            return object()

    plotter = MockPlotter()

    configure_plotter_gnomon(plotter)

    assert plotter.kwargs is not None
    assert plotter.kwargs["viewport"] == GNOMON_VIEWPORT
    assert plotter.kwargs["labels_off"] is True


def test_apply_point_rendering_enables_round_point_sprites() -> None:
    class MockProp:
        def __init__(self) -> None:
            self.render_points_as_spheres = False

    class MockActor:
        def __init__(self) -> None:
            self.prop = MockProp()

    actor = MockActor()
    apply_point_rendering(actor, True)
    assert actor.prop.render_points_as_spheres is True

    apply_point_rendering(actor, False)
    assert actor.prop.render_points_as_spheres is False


def test_pan_camera_from_screen_delta_moves_camera_and_focal_together() -> None:
    class MockCamera:
        def __init__(self) -> None:
            self.position = (10.0, 0.0, 0.0)
            self.focal_point = (0.0, 0.0, 0.0)
            self.up = (0.0, 0.0, 1.0)
            self.parallel_projection = True
            self.parallel_scale = 20.0
            self.view_angle = 30.0

    class MockPlotter:
        def __init__(self) -> None:
            self.camera = MockCamera()

        def width(self) -> int:
            return 800

        def height(self) -> int:
            return 600

    plotter = MockPlotter()
    original_position = np.asarray(plotter.camera.position, dtype=float)
    original_focal = np.asarray(plotter.camera.focal_point, dtype=float)

    pan_camera_from_screen_delta(plotter, 40.0, -20.0)

    next_position = np.asarray(plotter.camera.position, dtype=float)
    next_focal = np.asarray(plotter.camera.focal_point, dtype=float)
    translation = next_position - original_position

    assert np.allclose(next_focal - original_focal, translation)
    assert np.linalg.norm(translation) > 0.0


def test_orbit_camera_about_up_axis_preserves_radius_and_up_vector() -> None:
    class MockCamera:
        def __init__(self) -> None:
            self.position = (10.0, 0.0, 0.0)
            self.focal_point = (0.0, 0.0, 0.0)
            self.up = (0.0, 0.0, 1.0)

    class MockPlotter:
        def __init__(self) -> None:
            self.camera = MockCamera()

    plotter = MockPlotter()
    initial_offset = np.asarray(plotter.camera.position) - np.asarray(plotter.camera.focal_point)

    orbit_camera_about_up_axis(plotter, 32.0)

    next_offset = np.asarray(plotter.camera.position) - np.asarray(plotter.camera.focal_point)
    assert np.isclose(np.linalg.norm(next_offset), np.linalg.norm(initial_offset))
    assert np.allclose(np.asarray(plotter.camera.up, dtype=float), np.array((0.0, 0.0, 1.0)))
    assert not np.allclose(next_offset, initial_offset)


def test_viewport_mode_buttons_use_icons(qtbot) -> None:
    viewport = SpineViewport3D("3D Review", show_demo_scene=False)
    qtbot.addWidget(viewport)

    assert all(path.exists() for path in VIEWPORT_MODE_ICON_PATHS.values())
    assert len(viewport._mode_buttons) == 4
    for button in viewport._mode_buttons.values():
        assert button.text() == ""
        assert button.icon().isNull() is False


def test_viewport_detail_buttons_use_discrete_presets(qtbot) -> None:
    viewport = SpineViewport3D("3D Review", show_demo_scene=False)
    qtbot.addWidget(viewport)

    assert list(viewport.detail_buttons) == [level for _, level in DETAIL_PRESET_LEVELS]
    assert [button.text() for button in viewport.detail_buttons.values()] == [
        label for label, _level in DETAIL_PRESET_LEVELS
    ]
    assert viewport.detail_buttons[2].isChecked() is True

    qtbot.mouseClick(viewport.detail_buttons[3], Qt.MouseButton.LeftButton)

    assert viewport.current_detail_level() == 3
    assert viewport.detail_buttons[3].isChecked() is True

    qtbot.mouseClick(viewport.detail_buttons[3], Qt.MouseButton.LeftButton)

    assert viewport.current_detail_level() == 3
    assert viewport.detail_buttons[3].isChecked() is True


def test_viewport_can_hide_display_controls_and_keep_title_chip(qtbot) -> None:
    viewport = SpineViewport3D(
        "3D Review",
        show_demo_scene=False,
        show_display_controls=False,
    )
    qtbot.addWidget(viewport)

    assert viewport.mode_buttons == {}
    assert viewport.detail_buttons == {}
    chips = viewport.findChildren(QLabel, "ViewportOverlayChip")
    assert chips
    assert chips[0].parentWidget() is viewport


def test_viewport_freezes_to_snapshot_during_layout_transition(qtbot) -> None:
    viewport = SpineViewport3D("3D Review", show_demo_scene=False)
    qtbot.addWidget(viewport)
    viewport.resize(320, 240)

    viewport.set_layout_transition_active(True)

    assert viewport._transition_overlay is not None
    assert viewport._surface is not None
    assert viewport._transition_overlay.parentWidget() is viewport._surface
    assert viewport._surface.isHidden() is False
    assert viewport._toolbar_overlay is None or viewport._toolbar_overlay.isHidden() is False
    if viewport._toolbar_overlay is not None:
        expected_parent = (
            viewport
            if viewport._toolbar_overlay.objectName() == "ViewportOverlayChip"
            else viewport
        )
        assert viewport._toolbar_overlay.parentWidget() is expected_parent
    assert viewport._plotter is None or viewport._plotter.isHidden() is True

    viewport.set_layout_transition_active(False)

    assert viewport._transition_overlay is None
    assert viewport._surface.isHidden() is False
    assert viewport._toolbar_overlay is None or viewport._toolbar_overlay.isHidden() is False
    assert viewport._plotter is None or viewport._plotter.isHidden() is False


def test_orthographic_viewport_freezes_only_render_surface_during_layout_transition(qtbot) -> None:
    viewport = OrthographicMeshViewport("AP", "front", show_demo_scene=False)
    qtbot.addWidget(viewport)
    viewport.resize(320, 240)

    viewport.set_layout_transition_active(True)

    assert viewport._transition_overlay is not None
    assert viewport._surface is not None
    assert viewport._transition_overlay.parentWidget() is viewport._surface
    assert viewport._surface.isHidden() is False
    assert viewport._toolbar_overlay is None or viewport._toolbar_overlay.isHidden() is False
    assert viewport._toolbar_overlay is None or (
        viewport._toolbar_overlay.parentWidget() is viewport
    )
    assert viewport._plotter is None or viewport._plotter.isHidden() is True

    viewport.set_layout_transition_active(False)

    assert viewport._transition_overlay is None
    assert viewport._surface.isHidden() is False
    assert viewport._toolbar_overlay is None or viewport._toolbar_overlay.isHidden() is False
    assert viewport._plotter is None or viewport._plotter.isHidden() is False


def test_viewport_render_widgets_are_opaque_and_parented_to_surface(qtbot) -> None:
    viewports = (
        SpineViewport3D("3D Review", show_demo_scene=False),
        OrthographicMeshViewport("AP", "front", show_demo_scene=False),
    )

    for viewport in viewports:
        qtbot.addWidget(viewport)
        if viewport._plotter is None:
            continue
        surface = viewport.findChild(QFrame, "ViewportCardFrame")
        assert surface is not None
        assert viewport._plotter.parentWidget() is surface
        if viewport._toolbar_overlay is not None:
            expected_parent = (
                viewport
                if viewport._toolbar_overlay.objectName() == "ViewportOverlayChip"
                else viewport
            )
            assert viewport._toolbar_overlay.parentWidget() is expected_parent
        assert viewport._plotter.autoFillBackground() is True
        assert viewport._plotter.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)


def test_orthographic_grid_reuses_stable_actor_set(qtbot) -> None:
    viewport = OrthographicMeshViewport("AP", "front", show_demo_scene=True)
    qtbot.addWidget(viewport)
    if viewport._plotter is None:
        return

    viewport._refresh_grid()
    initial_actor_ids = {key: id(actor) for key, actor in viewport._grid_actors.items()}

    assert set(initial_actor_ids) == {"minor", "major"}

    viewport._plotter.camera.parallel_scale *= 1.1
    viewport._refresh_grid()

    assert set(viewport._grid_actors) == {"minor", "major"}
    assert {key: id(actor) for key, actor in viewport._grid_actors.items()} == initial_actor_ids


def test_orthographic_viewport_uses_shared_bottom_left_gnomon_overlay(qtbot) -> None:
    viewport = OrthographicMeshViewport("AP", "front", show_demo_scene=False)
    side_viewport = OrthographicMeshViewport("Lat", "side", show_demo_scene=False)
    qtbot.addWidget(viewport)
    qtbot.addWidget(side_viewport)

    gnomons = viewport.findChildren(ViewportGnomonOverlay)
    side_gnomons = side_viewport.findChildren(ViewportGnomonOverlay)

    assert len(gnomons) == 1
    assert len(side_gnomons) == 1
    assert gnomons[0].parentWidget() is viewport
    assert side_gnomons[0].parentWidget() is side_viewport
    assert gnomons[0].spec.horizontal_negative == "R"
    assert gnomons[0].spec.horizontal_positive == "L"
    assert gnomons[0].spec.vertical_negative == "I"
    assert gnomons[0].spec.vertical_positive == "S"
    assert gnomons[0].spec.horizontal_color == viewer_3d.THEME_COLORS.axis_y
    assert gnomons[0].spec.vertical_color == viewer_3d.THEME_COLORS.axis_z
    assert side_gnomons[0].spec.horizontal_negative == "P"
    assert side_gnomons[0].spec.horizontal_positive == "A"
    assert side_gnomons[0].spec.vertical_negative == "I"
    assert side_gnomons[0].spec.vertical_positive == "S"
    assert side_gnomons[0].spec.horizontal_color == viewer_3d.THEME_COLORS.axis_x
    assert side_gnomons[0].spec.vertical_color == viewer_3d.THEME_COLORS.axis_z


def test_3d_viewport_uses_shared_overlay_gnomon_instead_of_native_widget(qtbot) -> None:
    viewport = SpineViewport3D("3D Review", show_demo_scene=False)
    qtbot.addWidget(viewport)

    gnomons = viewport.findChildren(ViewportGnomonOverlay)

    assert len(gnomons) == 1
    assert gnomons[0].parentWidget() is viewport


def test_3d_viewport_reuses_stable_actor_set_for_horizontal_floor_grid(qtbot) -> None:
    viewport = SpineViewport3D("3D Review", show_demo_scene=True)
    qtbot.addWidget(viewport)
    if viewport._plotter is None:
        return

    viewport._refresh_grid()
    initial_actor_ids = {key: id(actor) for key, actor in viewport._grid_actors.items()}

    assert set(initial_actor_ids) == {"floor-minor", "floor-major"}

    position = np.asarray(viewport._plotter.camera.position, dtype=float)
    viewport._plotter.camera.position = tuple(float(value) for value in position * 1.08)
    viewport._refresh_grid()

    assert set(viewport._grid_actors) == {"floor-minor", "floor-major"}
    assert {key: id(actor) for key, actor in viewport._grid_actors.items()} == initial_actor_ids


def test_3d_grid_does_not_rebuild_for_constant_radius_orbit(qtbot) -> None:
    viewport = SpineViewport3D("3D Review", show_demo_scene=True)
    qtbot.addWidget(viewport)
    if viewport._plotter is None:
        return

    viewport._refresh_grid()
    initial_signature = viewport._last_grid_signature

    update_calls: list[str] = []
    original_update_grid_actor = viewport._update_grid_actor

    def tracking_update_grid_actor(*args, **kwargs):
        grid_key = args[0] if args else kwargs.get("grid_key", "")
        update_calls.append(str(grid_key))
        return original_update_grid_actor(*args, **kwargs)

    viewport._update_grid_actor = tracking_update_grid_actor  # type: ignore[method-assign]

    camera = viewport._plotter.camera
    focus = np.asarray(camera.focal_point, dtype=float)
    position = np.asarray(camera.position, dtype=float)
    up = np.asarray(camera.up, dtype=float)
    up = up / np.linalg.norm(up)
    offset = position - focus
    angle = np.deg2rad(18.0)
    rotated_offset = (
        offset * np.cos(angle)
        + np.cross(up, offset) * np.sin(angle)
        + up * np.dot(up, offset) * (1.0 - np.cos(angle))
    )
    camera.position = tuple(float(value) for value in (focus + rotated_offset))
    viewport._refresh_grid()

    assert viewport._last_grid_signature == initial_signature
    assert update_calls == []


def test_pose_visibility_can_hide_baseline_or_standing_scene_members(qtbot) -> None:
    viewport = SpineViewport3D(
        "3D Review",
        models=[
            MockVertebra("L1", "L1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), pose_name="baseline"),
            MockVertebra(
                "L1",
                "L1 Standing",
                (0.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
                render_id="L1_STANDING",
                selection_id="L1",
                pose_name="standing",
            ),
        ],
        show_display_controls=False,
    )
    qtbot.addWidget(viewport)
    if viewport._plotter is None:
        return

    viewport.set_pose_visibility(baseline_visible=False, standing_visible=True)

    assert viewport.current_pose_visibility() == (False, True)
    assert viewport._actor_map["L1"].visibility is False
    assert viewport._actor_map["L1_STANDING"].visibility is True


def test_selected_render_mode_applies_to_baseline_and_standing_pose_members(qtbot) -> None:
    models = [
        MockVertebra("L1", "L1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra(
            "L1",
            "L1 Standing",
            (0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0),
            render_id="L1_STANDING",
            selection_id="L1",
            pose_name="standing",
        ),
    ]
    viewport = SpineViewport3D("3D Review", show_demo_scene=False, models=models)
    qtbot.addWidget(viewport)
    if viewport._plotter is None:
        return

    viewport.set_selection(
        ("L1",),
        active_id="L1",
        reference_id="L1",
        isolate_selection=False,
    )
    viewport.set_mode(ViewportMode.POINTS)

    baseline_actor = viewport._actor_map["L1"]
    standing_actor = viewport._actor_map["L1_STANDING"]

    assert str(baseline_actor.prop.style).lower() == "points"
    assert str(standing_actor.prop.style).lower() == "points"
    assert baseline_actor.prop.point_size == VIEWPORT_MODES[ViewportMode.POINTS].point_size
    assert standing_actor.prop.point_size == VIEWPORT_MODES[ViewportMode.POINTS].point_size
    assert baseline_actor.prop.color.hex_rgb.lower() == resolve_mesh_visual_colors(
        "baseline",
        selected=True,
        reference=True,
    ).fill.lower()
    assert standing_actor.prop.color.hex_rgb.lower() == resolve_mesh_visual_colors(
        "standing",
        selected=True,
        reference=True,
    ).fill.lower()


def test_solid_mode_does_not_force_edges_for_active_reference_meshes(qtbot) -> None:
    viewport = SpineViewport3D(
        "3D Review",
        show_demo_scene=False,
        models=[MockVertebra("L1", "L1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))],
    )
    qtbot.addWidget(viewport)
    if viewport._plotter is None:
        return

    viewport.set_selection(
        ("L1",),
        active_id="L1",
        reference_id="L1",
        isolate_selection=False,
    )
    viewport.set_mode(ViewportMode.SOLID)

    actor = viewport._actor_map["L1"]
    assert actor.prop.show_edges is False

    viewport.set_mode(ViewportMode.WIRE)
    assert actor.prop.show_edges is True


def test_spine_viewport_leaves_reference_unset_when_none_is_requested(qtbot) -> None:
    models = [
        MockVertebra("PELVIS", "Pelvis", (0.0, 0.0, 0.0), (2.0, 2.0, 1.0), pose_name="baseline"),
        MockVertebra("L1", "L1", (0.0, 0.0, 5.0), (1.0, 1.0, 1.0), pose_name="baseline"),
    ]
    viewport = SpineViewport3D("3D Review", show_demo_scene=False, models=models)
    qtbot.addWidget(viewport)

    viewport.set_selection(
        ("PELVIS",),
        active_id="PELVIS",
        reference_id=None,
        isolate_selection=False,
    )

    assert viewport._reference_id is None


def test_orthographic_viewport_leaves_reference_unset_when_none_is_requested(qtbot) -> None:
    models = [
        MockVertebra("PELVIS", "Pelvis", (0.0, 0.0, 0.0), (2.0, 2.0, 1.0), pose_name="baseline"),
        MockVertebra("L1", "L1", (0.0, 0.0, 5.0), (1.0, 1.0, 1.0), pose_name="baseline"),
    ]
    viewport = OrthographicMeshViewport("AP", "front", show_demo_scene=False, models=models)
    qtbot.addWidget(viewport)

    viewport.set_selection(
        ("PELVIS",),
        active_id="PELVIS",
        reference_id=None,
        isolate_selection=False,
    )

    assert viewport._reference_id is None


def test_orthographic_selected_render_mode_applies_to_baseline_and_standing_pose_members(
    qtbot,
) -> None:
    models = [
        MockVertebra("L1", "L1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra(
            "L1",
            "L1 Standing",
            (0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0),
            render_id="L1_STANDING",
            selection_id="L1",
            pose_name="standing",
        ),
    ]
    viewport = OrthographicMeshViewport("AP", "front", show_demo_scene=False, models=models)
    qtbot.addWidget(viewport)
    if viewport._plotter is None:
        return

    viewport.set_selection(
        ("L1",),
        active_id="L1",
        reference_id="L1",
        isolate_selection=False,
    )
    viewport.set_mode(ViewportMode.POINTS)

    baseline_actor = viewport._actor_map["L1"]
    standing_actor = viewport._actor_map["L1_STANDING"]

    assert str(baseline_actor.prop.style).lower() == "points"
    assert str(standing_actor.prop.style).lower() == "points"
    assert baseline_actor.prop.point_size == VIEWPORT_MODES[ViewportMode.POINTS].point_size
    assert standing_actor.prop.point_size == VIEWPORT_MODES[ViewportMode.POINTS].point_size
    assert baseline_actor.prop.color.hex_rgb.lower() == resolve_mesh_visual_colors(
        "baseline",
        selected=True,
        reference=True,
    ).fill.lower()
    assert standing_actor.prop.color.hex_rgb.lower() == resolve_mesh_visual_colors(
        "standing",
        selected=True,
        reference=True,
    ).fill.lower()


def test_default_mesh_visual_colors_match_reference_palette() -> None:
    baseline = resolve_mesh_visual_colors(None, selected=False, reference=False)
    standing = resolve_mesh_visual_colors("standing", selected=False, reference=False)

    assert baseline.fill == MODEL_BASE_COLOR
    assert baseline.edge == MODEL_BASE_EDGE_COLOR
    assert standing.fill == MODEL_STANDING_COLOR
    assert standing.edge == MODEL_STANDING_EDGE_COLOR


def test_solid_mode_uses_thin_black_edges_until_active_or_reference() -> None:
    solid_mode = VIEWPORT_MODES[ViewportMode.SOLID]

    assert solid_mode.show_edges is False
    assert solid_mode.edge_width == 1
    assert (
        resolve_mode_edge_color(
            ViewportMode.SOLID,
            MODEL_STANDING_EDGE_COLOR,
            active=False,
            reference=False,
        )
        == MODEL_BASE_EDGE_COLOR
    )
    assert (
        resolve_mode_edge_color(
            ViewportMode.SOLID,
            MODEL_STANDING_EDGE_COLOR,
            active=True,
            reference=False,
        )
        == MODEL_STANDING_EDGE_COLOR
    )


def test_pelvis_world_transform_centers_group_on_origin() -> None:
    models = [
        MockVertebra("PELVIS", "Pelvis", (10.0, 20.0, 30.0), (4.0, 3.0, 2.0), selectable=False),
        MockVertebra("L5", "L5", (10.0, 20.0, 40.0), (1.0, 1.0, 1.0)),
        MockVertebra(
            "LEFT_FEMUR",
            "Left Femur",
            (15.0, 20.0, 20.0),
            (1.0, 1.0, 1.0),
            selectable=False,
        ),
        MockVertebra(
            "RIGHT_FEMUR",
            "Right Femur",
            (5.0, 20.0, 20.0),
            (1.0, 1.0, 1.0),
            selectable=False,
        ),
        MockVertebra("STERNUM", "Sternum", (10.0, 15.0, 60.0), (1.0, 1.0, 1.0), selectable=False),
    ]

    transform = build_pelvis_world_transform(models)
    transformed = apply_group_transform(models, transform)
    lookup = {model.vertebra_id: model for model in transformed}

    assert transform is not None
    assert np.allclose(lookup["PELVIS"].center, (0.0, 0.0, 0.0), atol=1e-6)
    assert lookup["L5"].center[2] > 0.0
    assert lookup["RIGHT_FEMUR"].center[0] > lookup["LEFT_FEMUR"].center[0]
