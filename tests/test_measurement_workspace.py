from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

import spinelab.workspaces.measurement_workspace as measurement_workspace_module
from spinelab.exports.measurement_bundle import MeasurementBundleResult
from spinelab.io import CaseStore
from spinelab.models import CaseManifest, StudyAsset, VolumeMetadata
from spinelab.segmentation import SegmentationBackendSummary
from spinelab.services import SettingsService
from spinelab.ui.theme import GEOMETRY, THEME_COLORS
from spinelab.visualization import SpineViewport3D, ViewportMode
from spinelab.visualization.viewer_3d import MockVertebra
from spinelab.workspaces.measurement_workspace import (
    MeasurementSelectionButton,
    MeasurementSummaryCard,
    MeasurementTree,
    MeasurementWorkspace,
    advance_selection_state,
    build_initial_selection_state,
    clear_selection_state,
    collect_mesh_export_sources,
    compute_relative_motion_metrics,
    manifest_has_measurement_scene,
    measurement_values_for_manifest,
    model_ids_for_manifest,
    models_for_manifest,
    normalize_measurement_pose_models,
    set_isolate_selection,
    set_reference_state,
    write_mock_box_ply,
)


def test_measurement_values_prefer_structured_records_when_values_map_is_empty() -> None:
    manifest = CaseManifest.demo()
    manifest.measurements.values.clear()

    values = measurement_values_for_manifest(manifest)

    assert values["Cobb Angle"] == "42.0 deg"
    assert values["Thoracic Kyphosis"] == "34.6 deg"
    assert values["Lumbar Lordosis"] == "46.2 deg"
    assert values["Sagittal Vertical Axis"] == "23.0 mm"


def test_measurement_values_build_from_manifest_values_when_records_are_missing() -> None:
    manifest = CaseManifest.blank()
    manifest.measurements.values = {
        "Cobb Angle": "18.4 deg",
        "Pelvic Tilt": "12.1 deg",
    }

    values = measurement_values_for_manifest(manifest)

    assert values == {
        "Cobb Angle": "18.4 deg",
        "Pelvic Tilt": "12.1 deg",
    }


def test_measurement_values_stay_empty_for_blank_case() -> None:
    manifest = CaseManifest.blank()

    values = measurement_values_for_manifest(manifest)

    assert values == {}
    assert manifest_has_measurement_scene(manifest) is False
    assert model_ids_for_manifest(manifest) == []


def test_measurement_selection_button_uses_fill_indicator_without_checkmark(qtbot) -> None:
    button = MeasurementSelectionButton()
    qtbot.addWidget(button)

    assert button.text() == ""
    assert button.isChecked() is True

    button.setChecked(False)
    assert button.text() == ""

    button.setChecked(True)
    assert button.text() == ""


def test_measurement_tree_selection_fill_spans_full_sidebar_width(qtbot) -> None:
    tree = MeasurementTree()
    tree.resize(320, 240)
    qtbot.addWidget(tree)

    selection_rect = tree._selection_fill_rect(QRect(52, 12, 180, 32))  # pyright: ignore[reportPrivateUsage]

    assert selection_rect.x() == 0
    assert selection_rect.width() == tree.viewport().width()
    assert selection_rect.y() > 12


def test_models_for_manifest_uses_real_mesh_scene_when_available(tmp_path: Path) -> None:
    mesh_root = tmp_path / "Mesh"
    mesh_root.mkdir()
    write_mock_box_ply(
        mesh_root / "L1.ply",
        MockVertebra("L1", "L1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
    )
    write_mock_box_ply(
        mesh_root / "PELVIS.ply",
        MockVertebra("PELVIS", "Pelvis", (0.0, 0.0, -2.0), (2.0, 2.0, 1.0)),
    )

    manifest = CaseManifest.demo()
    manifest.assets.append(
        StudyAsset(
            asset_id="mesh-root",
            kind="mesh_3d",
            label="Model",
            source_path=str(mesh_root),
            managed_path=str(mesh_root / "L1.ply"),
        )
    )

    scene_models = models_for_manifest(manifest)

    assert [model.vertebra_id for model in scene_models] == ["L1", "PELVIS"]
    assert model_ids_for_manifest(manifest) == ["L1", "PELVIS"]
    assert scene_models[0].selectable is True
    assert scene_models[1].selectable is True


def test_models_for_manifest_filters_non_spine_structures_from_demo_scene(
    tmp_path: Path,
) -> None:
    trimesh = pytest.importorskip("trimesh")

    mesh_root = tmp_path / "Mesh"
    mesh_root.mkdir()
    write_mock_box_ply(
        mesh_root / "L1.ply",
        MockVertebra("L1", "L1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
    )
    write_mock_box_ply(
        mesh_root / "LEFT_RIBS.ply",
        MockVertebra("LEFT_RIBS", "Left Ribs", (4.0, 0.0, 0.0), (3.0, 2.0, 4.0)),
    )
    write_mock_box_ply(
        mesh_root / "PELVIS.ply",
        MockVertebra("PELVIS", "Pelvis", (0.0, 0.0, -2.0), (2.0, 2.0, 1.0)),
    )

    scene = trimesh.Scene()
    for name, offset in (
        ("L1", (0.0, 0.0, 0.0)),
        ("LEFT_RIBS", (4.0, 0.0, 0.0)),
        ("PELVIS", (0.0, 0.0, -2.0)),
    ):
        mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
        mesh.apply_translation(offset)
        scene.add_geometry(mesh, geom_name=name, node_name=name)

    glb_path = tmp_path / "standing_demo_mesh.glb"
    glb_path.write_bytes(scene.export(file_type="glb"))

    manifest = CaseManifest.demo()
    manifest.assets.extend(
        [
            StudyAsset(
                asset_id="mesh-root",
                kind="mesh_3d",
                label="Model",
                source_path=str(mesh_root),
                managed_path=str(mesh_root),
            ),
            StudyAsset(
                asset_id="standing-scene",
                kind="mesh_3d",
                label="Standing",
                source_path=str(glb_path),
                managed_path=str(glb_path),
            ),
        ]
    )

    scene_models = models_for_manifest(manifest)

    assert {model.vertebra_id for model in scene_models} == {"L1", "PELVIS"}
    assert [model.pose_name for model in scene_models if model.vertebra_id == "L1"] == [
        "baseline",
        "standing",
    ]


def test_pose_normalization_reuses_baseline_pelvis_transform_for_standing_scene(
    monkeypatch,
) -> None:
    baseline_models = [
        MockVertebra("PELVIS", "Pelvis", (0.0, 0.0, 0.0), (2.0, 2.0, 1.0)),
        MockVertebra("L1", "L1", (0.0, 0.0, 2.0), (1.0, 1.0, 1.0)),
    ]
    standing_models = [
        MockVertebra(
            "PELVIS",
            "Pelvis Standing",
            (5.0, 0.0, 0.0),
            (2.0, 2.0, 1.0),
            pose_name="standing",
        ),
        MockVertebra(
            "L1",
            "L1 Standing",
            (7.0, 0.0, 2.0),
            (1.0, 1.0, 1.0),
            pose_name="standing",
        ),
    ]
    build_calls: list[str] = []

    def fake_build_pelvis_world_transform(models, *, anchor_id: str = "PELVIS"):
        del anchor_id
        pose_name = models[0].pose_name if models else "empty"
        build_calls.append(pose_name)
        if pose_name == "standing":
            return np.array(
                [
                    [-1.0, 0.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            )
        return np.eye(4)

    monkeypatch.setattr(
        measurement_workspace_module,
        "build_pelvis_world_transform",
        fake_build_pelvis_world_transform,
    )
    monkeypatch.setattr(
        measurement_workspace_module,
        "align_scene_models_to_reference",
        lambda scene_models, reference_models, *, anchor_id="PELVIS": scene_models,
    )

    normalized_baseline, normalized_standing = normalize_measurement_pose_models(
        baseline_models,
        standing_models,
    )

    assert build_calls == ["baseline"]
    assert normalized_baseline[0].center == (0.0, 0.0, 0.0)
    assert normalized_standing[0].center == (5.0, 0.0, 0.0)
    assert normalized_standing[1].center == (7.0, 0.0, 2.0)


def test_collect_mesh_export_sources_prefers_ply_files(tmp_path: Path) -> None:
    mesh_root = tmp_path / "Mesh"
    mesh_root.mkdir()
    (mesh_root / "L1.ply").write_text("ply", encoding="utf-8")
    (mesh_root / "L2.ply").write_text("ply", encoding="utf-8")
    (mesh_root / "notes.txt").write_text("ignore", encoding="utf-8")

    manifest = CaseManifest.demo()
    manifest.assets.append(
        StudyAsset(
            asset_id="mesh-root",
            kind="mesh_3d",
            label="Model",
            source_path=str(mesh_root),
            managed_path=str(mesh_root / "L1.ply"),
        )
    )

    mesh_files = collect_mesh_export_sources(manifest)

    assert [path.name for path in mesh_files] == ["L1.ply", "L2.ply"]


def test_selection_state_adds_items_without_auto_assigning_reference() -> None:
    state = build_initial_selection_state(["L1", "L2", "L3"], True)
    assert state.selected_ids == ()
    assert state.active_id is None
    assert state.reference_id is None

    state = advance_selection_state(state, "L2", remove_requested=False)
    assert state.selected_ids == ("L2",)
    assert state.active_id == "L2"
    assert state.reference_id is None

    state = advance_selection_state(state, "L3", remove_requested=False)
    assert state.selected_ids == ("L2", "L3")
    assert state.active_id == "L3"
    assert state.reference_id is None


def test_selection_state_does_not_auto_assign_pelvis_as_primary() -> None:
    state = build_initial_selection_state(
        ["L1", "L2"],
        True,
        reference_ids=("PELVIS", "L1", "L2"),
    )

    assert state.reference_id is None
    assert state.selected_ids == ()
    assert state.active_id is None


def test_set_reference_state_promotes_active_selection_to_reference() -> None:
    state = build_initial_selection_state(
        ["L1", "L2", "L3"],
        True,
        reference_ids=("PELVIS", "L1", "L2", "L3"),
    )
    state = advance_selection_state(
        state,
        "L2",
        remove_requested=False,
        default_reference_id="PELVIS",
    )

    promoted = set_reference_state(
        state,
        "L3",
        valid_reference_ids={"PELVIS", "L1", "L2", "L3"},
    )

    assert promoted.selected_ids == ("L2",)
    assert promoted.active_id == "L2"
    assert promoted.reference_id == "L3"


def test_selection_state_removal_does_not_change_explicit_reference() -> None:
    state = build_initial_selection_state(
        ["L1", "L2", "L3"],
        True,
        reference_ids=("PELVIS", "L1", "L2", "L3"),
    )
    state = advance_selection_state(state, "L2", remove_requested=False)
    state = advance_selection_state(state, "L1", remove_requested=False)
    state = advance_selection_state(state, "L3", remove_requested=False)
    state = set_reference_state(
        state,
        "L2",
        valid_reference_ids={"PELVIS", "L1", "L2", "L3"},
    )

    state = advance_selection_state(state, "L2", remove_requested=True)

    assert state.selected_ids == ("L1", "L3")
    assert state.reference_id == "L2"
    assert state.active_id == "L3"


def test_selection_state_can_remove_last_selected_vertebra() -> None:
    state = build_initial_selection_state(["L1"], True)

    state = advance_selection_state(state, "L1", remove_requested=True)

    assert state.selected_ids == ()
    assert state.reference_id is None
    assert state.active_id is None


def test_isolate_selection_requires_at_least_one_selected_vertebra() -> None:
    state = build_initial_selection_state(["L1", "L2", "L3"], True)
    state = advance_selection_state(state, "L2", remove_requested=False)

    isolated_state = set_isolate_selection(state, True)
    cleared_state = set_isolate_selection(
        build_initial_selection_state([], False),
        True,
    )

    assert isolated_state.isolate_selection is True
    assert cleared_state.isolate_selection is False


def test_clear_selection_state_resets_active_and_isolation_but_keeps_reference() -> None:
    state = build_initial_selection_state(
        ["L1", "L2", "L3"],
        True,
        reference_ids=("PELVIS", "L1", "L2", "L3"),
    )
    state = advance_selection_state(state, "L2", remove_requested=False)
    state = set_reference_state(
        state,
        "L2",
        valid_reference_ids={"PELVIS", "L1", "L2", "L3"},
    )
    state = set_isolate_selection(state, True)

    cleared_state = clear_selection_state(state)

    assert cleared_state.selected_ids == ()
    assert cleared_state.active_id is None
    assert cleared_state.reference_id == "L2"
    assert cleared_state.isolate_selection is False


def test_clear_selection_state_restores_default_primary_when_requested() -> None:
    state = build_initial_selection_state(
        ["L1", "L2", "L3"],
        True,
        reference_ids=("PELVIS", "L1", "L2", "L3"),
    )
    state = advance_selection_state(
        state,
        "L2",
        remove_requested=False,
        default_reference_id="PELVIS",
    )

    cleared_state = clear_selection_state(state, default_reference_id="PELVIS")

    assert cleared_state.selected_ids == ()
    assert cleared_state.active_id is None
    assert cleared_state.reference_id == "PELVIS"
    assert cleared_state.isolate_selection is False


def test_measurement_workspace_syncs_ortho_modes_with_main_viewport(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._viewport.set_mode(ViewportMode.TRANSPARENT)

    assert workspace._front_viewport.current_mode() == ViewportMode.TRANSPARENT
    assert workspace._side_viewport.current_mode() == ViewportMode.TRANSPARENT


def test_measurement_workspace_shows_pending_analysis_warning_on_each_viewport(qtbot) -> None:
    workspace = MeasurementWorkspace(
        CaseManifest.demo(),
        SettingsService(),
        analysis_ready=False,
    )
    qtbot.addWidget(workspace)

    warning_labels = workspace.findChildren(QLabel, "PendingAnalysisMessage")

    assert len(warning_labels) == 3
    assert {label.text() for label in warning_labels} == {"No Analysis Performed"}


def test_measurement_workspace_uses_ap_lat_and_3d_titles(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    front_labels = workspace._front_viewport.findChildren(QLabel, "ViewportOverlayChip")
    side_labels = workspace._side_viewport.findChildren(QLabel, "ViewportOverlayChip")
    view3d_labels = workspace._viewport.findChildren(QLabel, "ViewportOverlayChip")

    assert front_labels[0].text() == "AP"
    assert side_labels[0].text() == "Lat"
    assert view3d_labels[0].text() == "3D"


def test_measurement_workspace_launches_with_matched_sidebars_and_midpoint_viewports(
    qtbot,
    real_main_window,
    tmp_path: Path,
) -> None:
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "measurement-layout.ini"),
        QSettings.Format.IniFormat,
    )
    window = real_main_window(
        settings=settings,
        manifest=CaseManifest.demo(),
        analysis_ready=True,
    )
    window.set_workspace("measurement")
    qtbot.wait(50)
    workspace = window._workspace_pages["measurement"]

    sidebar_sizes = workspace.outer_splitter.sizes()
    center_sizes = workspace._center_splitter.sizes()  # pyright: ignore[reportPrivateUsage]
    ortho_sizes = workspace._orthographic_splitter.sizes()  # pyright: ignore[reportPrivateUsage]

    assert abs(sidebar_sizes[0] - sidebar_sizes[2]) <= 1
    assert abs(center_sizes[0] - center_sizes[1]) <= 1
    assert abs(ortho_sizes[0] - ortho_sizes[1]) <= 1


def test_measurement_export_button_uses_right_aligned_save_icon(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._export_model_button.objectName() == "ExportActionButton"
    assert workspace._export_model_button.icon().isNull() is False
    assert workspace._export_model_button.layoutDirection() == Qt.LayoutDirection.RightToLeft


def test_measurement_export_actions_are_anchored_in_left_sidebar(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._left_action_card is not None
    assert workspace._left_action_card.isAncestorOf(workspace._save_measurements_button)
    assert workspace._left_action_card.isAncestorOf(workspace._export_model_button)
    assert workspace._left_action_card.isAncestorOf(workspace._export_status_label)


def test_measurement_selection_actions_share_one_horizontal_row(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    left_actions = workspace._isolate_button.parentWidget()
    assert left_actions is workspace._clear_selection_button.parentWidget()
    layout = left_actions.layout()
    assert isinstance(layout, QHBoxLayout)


def test_measurement_tree_uses_custom_full_row_selection_widget(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._measurement_tree.objectName() == "MeasurementTree"


def test_measurement_selection_action_buttons_reflect_empty_and_ready_states(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._isolate_button.property("actionState") == "empty"
    assert workspace._clear_selection_button.property("actionState") == "empty"

    first_id = workspace._model_ids[0]
    workspace._handle_vertebra_button_interaction(first_id, False)

    assert workspace._isolate_button.property("actionState") == "ready"
    assert workspace._clear_selection_button.property("actionState") == "ready"

    workspace._clear_selection()

    assert workspace._isolate_button.property("actionState") == "empty"
    assert workspace._clear_selection_button.property("actionState") == "empty"


def test_measurement_workspace_has_horizontal_manual_tool_toolbar(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._manual_tool == "select"
    assert set(workspace._manual_tool_buttons) == {"select", "distance", "angle"}
    assert workspace._manual_tool_buttons["select"].isChecked() is True
    assert all(
        button.icon().isNull() is False
        for button in workspace._manual_tool_buttons.values()
    )
    toolbar = workspace.findChild(QFrame, "ManualMeasurementToolbar")
    assert toolbar is not None
    assert isinstance(toolbar.layout(), QHBoxLayout)

    workspace._set_manual_tool("angle")

    assert workspace._manual_tool == "angle"
    assert workspace._manual_tool_buttons["angle"].isChecked() is True
    assert workspace._manual_tool_buttons["select"].isChecked() is False


def test_measurement_workspace_manual_distance_tool_updates_overlay_session(
    qtbot,
    monkeypatch,
) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    overlays: list[tuple[str, object | None]] = []
    monkeypatch.setattr(
        workspace._viewport,
        "set_overlay_geometry",
        lambda overlay_id, overlay: overlays.append((overlay_id, overlay)),
    )
    monkeypatch.setattr(
        workspace._viewport,
        "clear_overlay_geometry",
        lambda overlay_id: overlays.append((overlay_id, None)),
    )
    monkeypatch.setattr(
        workspace._viewport,
        "set_surface_point_pick_callback",
        lambda callback: None,
    )
    monkeypatch.setattr(
        workspace._viewport,
        "set_surface_point_picking_enabled",
        lambda enabled: None,
    )

    workspace._set_manual_tool("distance")
    workspace._handle_manual_point_picked((0.0, 0.0, 0.0))
    workspace._handle_manual_point_picked((0.0, 0.0, 5.0))

    assert workspace._manual_measurement_points == [
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 5.0),
    ]
    assert overlays[-1][0] == "manual-measurement"
    assert workspace._overlay_status_label.text().startswith("Distance:")


def test_measurement_workspace_manual_angle_tool_updates_overlay_session(
    qtbot,
    monkeypatch,
) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    overlays: list[tuple[str, object | None]] = []
    monkeypatch.setattr(
        workspace._viewport,
        "set_overlay_geometry",
        lambda overlay_id, overlay: overlays.append((overlay_id, overlay)),
    )
    monkeypatch.setattr(
        workspace._viewport,
        "clear_overlay_geometry",
        lambda overlay_id: overlays.append((overlay_id, None)),
    )
    monkeypatch.setattr(
        workspace._viewport,
        "set_surface_point_pick_callback",
        lambda callback: None,
    )
    monkeypatch.setattr(
        workspace._viewport,
        "set_surface_point_picking_enabled",
        lambda enabled: None,
    )

    workspace._set_manual_tool("angle")
    workspace._handle_manual_point_picked((0.0, 0.0, 0.0))
    workspace._handle_manual_point_picked((1.0, 0.0, 0.0))
    workspace._handle_manual_point_picked((1.0, 1.0, 0.0))

    assert workspace._manual_measurement_points == [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
    ]
    assert overlays[-1][0] == "manual-measurement"
    assert workspace._overlay_status_label.text().startswith("Angle:")


def test_measurement_manual_tool_icons_match_inactive_render_control_tint(
    qtbot,
    monkeypatch,
    real_main_window,
) -> None:
    captured_manual_tints: dict[Path, str | None] = {}
    captured_display_tints: dict[Path, str | None] = {}
    original_build_svg_icon = measurement_workspace_module.build_svg_icon

    def capture_tinted_icon(path, size, *, device_pixel_ratio=1.0, tint=None):
        if path in measurement_workspace_module.MANUAL_TOOL_ICON_PATHS.values():
            captured_manual_tints[path] = tint
        if path in measurement_workspace_module.VIEWPORT_MODE_ICON_PATHS.values():
            captured_display_tints[path] = tint
        return original_build_svg_icon(
            path,
            size,
            device_pixel_ratio=device_pixel_ratio,
            tint=tint,
        )

    monkeypatch.setattr(measurement_workspace_module, "build_svg_icon", capture_tinted_icon)

    window = real_main_window(
        manifest=CaseManifest.demo(),
        analysis_ready=True,
    )
    window.set_workspace("measurement")
    qtbot.wait(50)
    workspace = window._workspace_pages["measurement"]

    captured_manual_tints.clear()
    captured_display_tints.clear()
    workspace._refresh_manual_tool_buttons()
    workspace._refresh_display_mode_buttons(workspace._viewport.current_mode())

    active_manual_icon = measurement_workspace_module.MANUAL_TOOL_ICON_PATHS[workspace._manual_tool]
    inactive_manual_tints = {
        tint
        for path, tint in captured_manual_tints.items()
        if path != active_manual_icon
    }
    active_display_icon = measurement_workspace_module.VIEWPORT_MODE_ICON_PATHS[
        workspace._viewport.current_mode()
    ]
    inactive_display_tints = {
        tint
        for path, tint in captured_display_tints.items()
        if path != active_display_icon
    }

    assert captured_manual_tints[active_manual_icon] == THEME_COLORS.focus
    assert inactive_manual_tints == {THEME_COLORS.text_primary}
    assert inactive_display_tints == {THEME_COLORS.text_primary}


def test_measurement_summary_cards_use_shared_text_inset(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    summary_cards = workspace.findChildren(MeasurementSummaryCard)
    assert summary_cards
    for card in summary_cards:
        margins = card.layout().contentsMargins()
        assert margins.left() == GEOMETRY.inspector_padding
        assert margins.right() == GEOMETRY.inspector_padding


def test_measurement_inspector_uses_compact_top_aligned_detail_layout(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert (
        workspace._motion_matrix_frame.sizePolicy().verticalPolicy()
        == QSizePolicy.Policy.Maximum
    )
    assert workspace._motion_matrix_layout.verticalSpacing() <= GEOMETRY.unit // 2


def test_measurement_workspace_syncs_ortho_detail_with_main_viewport(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._viewport.set_detail_level(1)

    assert workspace._front_viewport.current_detail_level() == 1
    assert workspace._side_viewport.current_detail_level() == 1


def test_measurement_workspace_syncs_ortho_point_size_with_main_viewport(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._viewport.set_point_size(14)

    assert workspace._front_viewport.current_point_size() == 14
    assert workspace._side_viewport.current_point_size() == 14


def test_measurement_workspace_keeps_render_controls_in_top_toolbar(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)
    toolbar = workspace.findChild(QFrame, "ManualMeasurementToolbar")
    assert toolbar is not None

    assert workspace._viewport.mode_buttons == {}
    assert workspace._viewport.detail_buttons == {}
    assert set(workspace._display_mode_buttons) == set(ViewportMode)
    assert set(workspace._display_detail_buttons) == {0, 2, 3}
    assert set(workspace._pose_visibility_buttons) == {"baseline", "standing"}
    assert all(button.text() == "" for button in workspace._display_mode_buttons.values())
    assert all(
        button.icon().isNull() is False
        for button in workspace._display_mode_buttons.values()
    )
    assert all(
        button.height() == GEOMETRY.toolbar_control_size
        for button in workspace._display_mode_buttons.values()
    )
    assert all(
        button.height() == GEOMETRY.toolbar_control_size
        for button in workspace._display_detail_buttons.values()
    )
    assert all(
        toolbar.isAncestorOf(button) for button in workspace._display_mode_buttons.values()
    )
    assert all(
        toolbar.isAncestorOf(button) for button in workspace._display_detail_buttons.values()
    )
    assert all(
        not toolbar.isAncestorOf(button)
        for button in workspace._pose_visibility_buttons.values()
    )
    assert workspace._left_action_card is not None
    assert all(
        workspace._left_action_card.isAncestorOf(button)
        for button in workspace._pose_visibility_buttons.values()
    )

    qtbot.mouseClick(
        workspace._display_mode_buttons[ViewportMode.WIRE],
        Qt.MouseButton.LeftButton,
    )
    qtbot.mouseClick(
        workspace._display_detail_buttons[3],
        Qt.MouseButton.LeftButton,
    )

    assert workspace._viewport.current_mode() == ViewportMode.WIRE
    assert workspace._front_viewport.current_mode() == ViewportMode.WIRE
    assert workspace._side_viewport.current_mode() == ViewportMode.WIRE
    assert workspace._viewport.current_detail_level() == 3
    assert workspace._front_viewport.current_detail_level() == 3
    assert workspace._side_viewport.current_detail_level() == 3


def test_measurement_workspace_syncs_pose_visibility_across_viewports(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._viewport.current_pose_visibility() == (True, False)
    assert workspace._front_viewport.current_pose_visibility() == (True, False)
    assert workspace._side_viewport.current_pose_visibility() == (True, False)
    assert workspace._pose_visibility_buttons["standing"].isEnabled() is False

    qtbot.mouseClick(
        workspace._pose_visibility_buttons["standing"],
        Qt.MouseButton.LeftButton,
    )

    assert workspace._viewport.current_pose_visibility() == (True, False)
    assert workspace._front_viewport.current_pose_visibility() == (True, False)
    assert workspace._side_viewport.current_pose_visibility() == (True, False)
    assert workspace._pose_visibility_buttons["standing"].isChecked() is False
    assert workspace._pose_visibility_buttons["standing"].property("visibilityState") == "hidden"


def test_measurement_workspace_builds_supine_and_standing_vertebra_columns(
    qtbot,
    monkeypatch,
) -> None:
    models = [
        MockVertebra("L1", "L1", (0.0, 0.0, 1.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra("L2", "L2", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra("L1", "L1", (0.1, 0.0, 1.1), (1.0, 1.0, 1.0), pose_name="standing"),
        MockVertebra("L2", "L2", (0.1, 0.0, 0.1), (1.0, 1.0, 1.0), pose_name="standing"),
    ]
    monkeypatch.setattr(
        measurement_workspace_module,
        "models_for_manifest",
        lambda _manifest: models,
    )

    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._has_comparison_scene is True
    assert workspace._standing_vertebra_header.isHidden() is False
    assert ("baseline", "L1") in workspace._vertebra_buttons
    assert ("standing", "L1") in workspace._vertebra_buttons
    assert workspace._vertebra_button_layout.itemAtPosition(0, 0) is not None
    assert workspace._vertebra_button_layout.itemAtPosition(0, 1) is not None


def test_measurement_workspace_builds_primary_relative_motion_columns(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._selection_state = advance_selection_state(
        workspace._selection_state,
        "L2",
        remove_requested=False,
        valid_ids=set(workspace._model_ids),
    )
    workspace._selection_state = advance_selection_state(
        workspace._selection_state,
        "L4",
        remove_requested=False,
        valid_ids=set(workspace._model_ids),
    )
    workspace._selection_state = advance_selection_state(
        workspace._selection_state,
        "L5",
        remove_requested=False,
        valid_ids=set(workspace._model_ids),
    )
    workspace._selection_state = set_reference_state(
        workspace._selection_state,
        "L2",
        valid_reference_ids=set(workspace._reference_ids),
    )

    workspace._apply_vertebra_selection()

    assert workspace._reference_vertebra_label.text() == "L2"
    assert workspace._global_axis_label.text() == "L2 local Z"
    assert workspace._selected_vertebrae_label.text() == "L4, L5"
    assert list(workspace._motion_matrix_headers) == ["L2", "L4", "L5"]

    l4_metrics = compute_relative_motion_metrics("L4", "L2")
    l5_metrics = compute_relative_motion_metrics("L5", "L2")

    assert l4_metrics is not None
    assert l5_metrics is not None
    assert workspace._motion_matrix_value_labels[("L2", "delta_x")].text() == "+0.00"
    assert workspace._motion_matrix_value_labels[("L2", "distance")].text() == "0.00"
    assert (
        workspace._motion_matrix_value_labels[("L4", "delta_z")].text()
        == f"{l4_metrics.delta_z:+.2f}"
    )
    assert (
        workspace._motion_matrix_value_labels[("L5", "distance")].text()
        == f"{l5_metrics.distance:.2f}"
    )


def test_measurement_workspace_shows_none_global_axis_without_primary(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert workspace._global_axis_label.text() == "None"


def test_measurement_workspace_clearing_selection_keeps_explicit_global_axis(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._selection_state = advance_selection_state(
        workspace._selection_state,
        "L3",
        remove_requested=False,
        valid_ids=set(workspace._model_ids),
    )
    workspace._selection_state = set_reference_state(
        workspace._selection_state,
        "L3",
        valid_reference_ids=set(workspace._reference_ids),
    )
    workspace._apply_vertebra_selection()

    assert workspace._global_axis_label.text() == "L3 local Z"

    workspace._clear_selection()

    assert workspace._global_axis_label.text() == "L3 local Z"


def test_measurement_workspace_allows_pelvis_selection_and_reference_button(
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        measurement_workspace_module,
        "models_for_manifest",
        lambda _manifest: [
            MockVertebra(
                "PELVIS",
                "Pelvis",
                (0.0, 0.0, -2.0),
                (2.0, 2.0, 1.0),
                pose_name="baseline",
            ),
            MockVertebra("L1", "L1", (0.0, 0.0, 1.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        ],
    )
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    assert "PELVIS" in workspace._model_ids
    assert workspace._selection_state.reference_id == "PELVIS"
    assert workspace._set_reference_frame_button.isEnabled() is False

    workspace._handle_vertebra_button_interaction("L1", False)

    assert workspace._selection_state.selected_ids == ("L1",)
    assert workspace._selection_state.reference_id == "PELVIS"
    assert workspace._set_reference_frame_button.isEnabled() is True

    qtbot.mouseClick(workspace._set_reference_frame_button, Qt.MouseButton.LeftButton)

    assert workspace._selection_state.reference_id == "L1"
    assert workspace._reference_vertebra_label.text() == "L1"


def test_motion_matrix_uses_vertebra_rows_and_metric_columns(qtbot) -> None:
    workspace = MeasurementWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace.apply_shared_selection_state(
        selected_ids=("L1", "L2"),
        active_id="L1",
        reference_id="L2",
        isolate_selection=False,
    )

    assert workspace._motion_matrix_layout.itemAtPosition(0, 0).widget().text() == "Vertebra"
    assert workspace._motion_matrix_layout.itemAtPosition(0, 1).widget().text() == "ΔX"
    assert workspace._motion_matrix_layout.itemAtPosition(0, 2).widget().text() == "ΔY"
    assert workspace._motion_matrix_layout.itemAtPosition(1, 0).widget().text() == "L2"
    assert workspace._motion_matrix_layout.itemAtPosition(2, 0).widget().text() == "L1"


def test_measurement_workspace_uses_mesh_viewport_for_processed_ct_only_case(
    qtbot,
    tmp_path: Path,
) -> None:
    volume_path = tmp_path / "volume.nii.gz"
    volume_data = np.arange(64, dtype=np.int16).reshape((4, 4, 4))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.0, 1.0, 2.0, 1.0])), str(volume_path))

    manifest = CaseManifest.blank()
    manifest.assets.append(
        StudyAsset(
            asset_id="ct-volume",
            kind="ct_zstack",
            label="CT",
            source_path=str(volume_path),
            managed_path=str(volume_path),
            processing_role="ct_stack",
        )
    )
    manifest.volumes.append(
        VolumeMetadata(
            volume_id="ct-volume",
            modality="ct",
            source_path=str(volume_path),
            canonical_path=str(volume_path),
            dimensions=(4, 4, 4),
            asset_id="ct-volume",
            voxel_spacing=(1.0, 1.0, 2.0),
            value_range=(0.0, 63.0),
        )
    )

    workspace = MeasurementWorkspace(manifest, SettingsService())
    qtbot.addWidget(workspace)

    assert isinstance(workspace._viewport, SpineViewport3D)


def test_relative_motion_metrics_are_calculated_from_reference() -> None:
    metrics = compute_relative_motion_metrics("L1", "L3")

    assert metrics is not None
    assert metrics.reference_id == "L3"
    assert metrics.active_id == "L1"
    assert metrics.delta_z == 2.5


def test_export_model_writes_to_user_selected_output_bundle(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path)
    workspace = MeasurementWorkspace(
        CaseManifest.demo(),
        SettingsService(),
        store=store,
    )
    qtbot.addWidget(workspace)

    called: dict[str, Path] = {}

    def fake_export_measurement_bundle(
        bundle_root,
        manifest,
        *,
        selected_measurements,
        baseline_mesh_files,
        standing_scene_files,
        standing_input_assets,
        scene_models,
        selected_ids=None,
        artifact_paths=None,
        backend_provenance=None,
    ):
        del manifest, selected_measurements, baseline_mesh_files, standing_scene_files
        del standing_input_assets, scene_models, selected_ids, artifact_paths, backend_provenance
        called["bundle_root"] = bundle_root
        return MeasurementBundleResult(
            root=bundle_root,
            measurements_pdf_path=bundle_root / "measurements" / "demo.pdf",
            measurements_json_path=bundle_root / "measurements" / "demo.json",
            baseline_mesh_count=1,
            standing_scene_count=0,
            standing_projection_paths={},
            warnings=("projection skipped",),
        )

    monkeypatch.setattr(
        measurement_workspace_module,
        "export_measurement_bundle",
        fake_export_measurement_bundle,
    )
    monkeypatch.setattr(
        measurement_workspace_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path / "exports"),
    )

    workspace._export_model()

    assert "measurement bundle" in workspace._export_status_label.text()
    assert "warning(s)" in workspace._export_status_label.text()
    assert called["bundle_root"].parent == (tmp_path / "exports")
    assert called["bundle_root"].name.startswith(
        f"{workspace._manifest.case_id}-measurement-export"
    )


def test_export_model_ignores_active_backend_slug_without_manifest_provenance(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path)
    workspace = MeasurementWorkspace(
        CaseManifest.demo(),
        SettingsService(),
        store=store,
    )
    qtbot.addWidget(workspace)

    called: dict[str, Path] = {}

    def fake_export_measurement_bundle(
        bundle_root,
        manifest,
        *,
        selected_measurements,
        baseline_mesh_files,
        standing_scene_files,
        standing_input_assets,
        scene_models,
        selected_ids=None,
        artifact_paths=None,
        backend_provenance=None,
    ):
        del manifest, selected_measurements, baseline_mesh_files, standing_scene_files
        del standing_input_assets, scene_models, selected_ids, artifact_paths, backend_provenance
        called["bundle_root"] = bundle_root
        return MeasurementBundleResult(
            root=bundle_root,
            measurements_pdf_path=bundle_root / "measurements" / "demo.pdf",
            measurements_json_path=bundle_root / "measurements" / "demo.json",
            baseline_mesh_count=1,
            standing_scene_count=0,
            standing_projection_paths={},
            warnings=(),
        )

    monkeypatch.setattr(
        measurement_workspace_module,
        "export_measurement_bundle",
        fake_export_measurement_bundle,
    )
    monkeypatch.setattr(
        measurement_workspace_module,
        "summary_for_manifest",
        lambda manifest: None,
    )
    monkeypatch.setattr(
        measurement_workspace_module,
        "summary_for_active_bundle",
        lambda store, settings=None: SegmentationBackendSummary(
            backend_id="verse20-resenc-fold1",
            display_name="VERSe20 ResEnc Fold 1",
            family="nnunet-verse20-resenc",
            driver_id="nnunetv2",
            runtime_environment_id="nnunet-verse20-win",
            checkpoint_id="fold-1:checkpoint_final",
            model_name="nnunet-verse20-resenc",
            model_version="verse20-resenc-fold1",
        ),
    )
    monkeypatch.setattr(
        measurement_workspace_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path / "exports"),
    )

    workspace._export_model()

    assert called["bundle_root"].name.startswith(
        f"{workspace._manifest.case_id}-measurement-export"
    )
