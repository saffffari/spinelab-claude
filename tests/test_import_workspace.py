import threading
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtGui import QImage, qRgb
from PySide6.QtWidgets import QFrame, QLabel, QMessageBox, QSizePolicy, QSlider, QToolButton

import spinelab.workspaces.import_workspace as import_workspace_module
from spinelab.io import CaseStore, SpinePackageService
from spinelab.models import CaseManifest, PipelineRun, SegmentationProfile, StudyAsset
from spinelab.pipeline import AnalysisProgressUpdate
from spinelab.pipeline.stage_registry import PipelineStageName
from spinelab.services import SettingsService
from spinelab.services.performance import PerformanceMode, reset_performance_coordinator
from spinelab.ui.theme import GEOMETRY, TYPOGRAPHY
from spinelab.workspaces.import_workspace import (
    AssetRowWidget,
    CaseExplorerTree,
    ImportWorkspace,
    RoundedImagePreview,
    analysis_required_comparison_slots,
    build_asset_thumbnail,
    canonical_analysis_pose_mode,
    canonical_comparison_modality,
    case_tree_patient_label,
    comparison_button_text,
    comparison_button_variant,
    ct_preview_slice_index,
    format_resolution,
    infer_xray_role_for_import,
    pose_engine_button_text,
    pose_engine_button_variant,
    resolved_analysis_pose_mode,
    suggested_import_role,
)


@pytest.fixture(autouse=True)
def _reset_performance_state() -> None:
    reset_performance_coordinator()
    yield
    reset_performance_coordinator()


def _settings_service(tmp_path: Path) -> SettingsService:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "import-workspace.ini"),
        QSettings.Format.IniFormat,
    )
    return service


def _create_saved_package(
    tmp_path: Path,
    *,
    patient_name: str,
    file_name: str = "current-ap.png",
) -> tuple[CaseStore, SettingsService, CaseManifest, Path]:
    settings = _settings_service(tmp_path)
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.patient_name = patient_name
    session = store.session_store.create_blank_session(manifest=manifest)
    store.activate_session(session)
    asset_path = session.workspace_root / "xray" / file_name
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(qRgb(255, 255, 255))
    image.save(str(asset_path))
    manifest.assets.append(
        StudyAsset(
            asset_id="asset-ap",
            kind="xray_2d",
            label="X-Ray",
            source_path=str(asset_path),
            managed_path=str(asset_path),
            processing_role="xray_ap",
        )
    )
    store.save_manifest(manifest)
    package_path = tmp_path / f"{manifest.case_id}.spine"
    SpinePackageService(store.session_store).save_package(session, manifest, package_path)
    settings.add_recent_case_path(package_path)
    return store, settings, manifest, package_path


def test_pose_engine_and_comparison_helpers_track_selection_state() -> None:
    manifest = CaseManifest.blank()
    assert canonical_analysis_pose_mode("Single Pose") == "single"
    assert canonical_analysis_pose_mode("dual_pose") == "dual"
    assert analysis_required_comparison_slots("single") == ("primary",)
    assert analysis_required_comparison_slots("dual") == ("primary", "secondary")
    assert pose_engine_button_text(None) == "Pose Engine"
    assert pose_engine_button_variant(None) == "danger"

    manifest.comparison_modalities = {"primary": "ct"}
    assert resolved_analysis_pose_mode(manifest) == "single"
    manifest.comparison_modalities["secondary"] = "xray"
    assert resolved_analysis_pose_mode(manifest) == "dual"
    manifest.analysis_pose_mode = "single"
    assert resolved_analysis_pose_mode(manifest) == "single"
    assert pose_engine_button_text("single") == "Pose Engine: Single Pose"
    assert pose_engine_button_variant("single") == "success"

    assert comparison_button_text("primary", None) == "Primary"
    assert comparison_button_variant(None) == "danger"

    assert canonical_comparison_modality("X-Ray") == "xray"
    assert comparison_button_text("secondary", "mri") == "Secondary"
    assert comparison_button_variant("mri") == "success"


def test_ct_preview_slice_index_uses_rounded_half_count() -> None:
    assert ct_preview_slice_index(1) == 0
    assert ct_preview_slice_index(2) == 0
    assert ct_preview_slice_index(3) == 1
    assert ct_preview_slice_index(4) == 1
    assert ct_preview_slice_index(5) == 2


def test_blank_import_inspector_shows_no_images_bubble(qtbot, tmp_path: Path) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    assert workspace._empty_state_bubble.isHidden() is False
    assert workspace._empty_state_bubble.text() == ""
    assert workspace._empty_state_bubble.toolTip() == "No images"
    assert workspace._empty_state_bubble.pixmap() is not None
    assert workspace._import_drop_zone.text() == "Import or Drag and Drop Images"
    assert workspace._import_drop_zone.icon().isNull() is False
    assert workspace._import_drop_zone.property("variant") == "info"
    assert workspace._import_drop_zone.font().weight() == TYPOGRAPHY.weight_semibold
    assert (
        workspace._import_drop_zone.sizePolicy().horizontalPolicy()
        == QSizePolicy.Policy.Expanding
    )
    assert workspace._analyze_button.icon().isNull() is False
    assert workspace._analyze_button.layoutDirection() == Qt.LayoutDirection.LeftToRight
    assert workspace._analyze_button.font().weight() == TYPOGRAPHY.weight_semibold
    assert workspace._metadata_rows["filename"].isHidden() is True
    assert workspace._metadata_rows["modality"].isHidden() is True
    assert workspace._metadata_rows["filename"].title_label.text() == "Properties"
    assert workspace._metadata_rows["filename"].layout().spacing() == 0
    assert workspace._modality_tag.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
    assert isinstance(workspace._preview_label, RoundedImagePreview)
    assert workspace._preview_label.pixmap() is not None


def test_import_workspace_uses_short_viewport_titles(qtbot, tmp_path: Path) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    assert workspace._xray_ap_viewport.title_label.text() == "AP"
    assert workspace._xray_lat_viewport.title_label.text() == "Lat"
    assert workspace._ct_viewport.title_label.text() == "CT"


def test_import_workspace_hosts_ct_slider_in_top_toolbar(qtbot, tmp_path: Path) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    toolbar = workspace.findChild(QFrame, "ImportViewportToolbar")
    assert toolbar is not None

    slider_group = workspace._ct_viewport.slice_toolbar_group()  # pyright: ignore[reportPrivateUsage]
    slider = slider_group.findChild(QSlider, "ViewportSliceSlider")

    assert toolbar.isAncestorOf(slider_group)
    assert slider is not None
    assert toolbar.isAncestorOf(slider)


def test_import_images_section_is_last_left_sidebar_section(qtbot, tmp_path: Path) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    left_sections = workspace._left_panel.section_splitter  # pyright: ignore[reportPrivateUsage]
    assert left_sections.count() == 4
    assert left_sections.widget(3).content_widget() is workspace._images_section  # pyright: ignore[reportPrivateUsage]


def test_import_actions_are_anchored_in_left_sidebar(qtbot, tmp_path: Path) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    assert workspace._left_action_card is not None  # pyright: ignore[reportPrivateUsage]
    assert workspace._left_action_card.isAncestorOf(
        workspace._pose_engine_button  # pyright: ignore[reportPrivateUsage]
    )
    assert workspace._left_action_card.isAncestorOf(workspace._analyze_button)  # pyright: ignore[reportPrivateUsage]
    assert all(
        workspace._left_action_card.isAncestorOf(button)  # pyright: ignore[reportPrivateUsage]
        for button in workspace._comparison_buttons.values()  # pyright: ignore[reportPrivateUsage]
    )
    assert workspace._left_action_card.isAncestorOf(
        workspace._comparison_selector_strip  # pyright: ignore[reportPrivateUsage]
    )
    assert workspace._left_action_card.isAncestorOf(
        workspace._turbo_mode_button  # pyright: ignore[reportPrivateUsage]
    )
    assert workspace._left_action_card.isAncestorOf(
        workspace._precision_strip  # pyright: ignore[reportPrivateUsage]
    )
    assert workspace._left_action_card.isAncestorOf(workspace._import_drop_zone) is False  # pyright: ignore[reportPrivateUsage]
    assert workspace._import_drop_zone.height() == GEOMETRY.major_button_height
    assert workspace._images_section.isAncestorOf(workspace._import_drop_zone) is True  # pyright: ignore[reportPrivateUsage]
    assert (
        workspace._images_section.content_layout.itemAt(0).widget()
        is workspace._import_drop_zone  # pyright: ignore[reportPrivateUsage]
    )
    assert (
        workspace._images_section.content_layout.itemAt(1).widget()
        is workspace._asset_list  # pyright: ignore[reportPrivateUsage]
    )


def test_import_workspace_defaults_segmentation_profile_to_production(
    qtbot,
    tmp_path: Path,
) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        _settings_service(tmp_path),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    assert workspace._manifest.segmentation_profile == SegmentationProfile.PRODUCTION.value
    assert len(workspace._precision_buttons) == 3  # pyright: ignore[reportPrivateUsage]
    assert hasattr(workspace, "_segmentation_profile_button") is False


def test_import_workspace_canonicalizes_unknown_segmentation_profile_to_production(
    qtbot, tmp_path: Path
) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.segmentation_profile = "legacy-bootstrap"
    store.save_manifest(manifest)

    workspace = ImportWorkspace(
        manifest,
        _settings_service(tmp_path),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    reloaded = store.load_manifest(manifest.case_id)
    assert reloaded.segmentation_profile == SegmentationProfile.PRODUCTION.value


def test_import_workspace_promotes_debug_scaffold_profile_to_production(
    qtbot, tmp_path: Path
) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value
    store.save_manifest(manifest)

    workspace = ImportWorkspace(
        manifest,
        _settings_service(tmp_path),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    reloaded = store.load_manifest(manifest.case_id)
    assert workspace._manifest.segmentation_profile == SegmentationProfile.PRODUCTION.value
    assert reloaded.segmentation_profile == SegmentationProfile.PRODUCTION.value


def test_case_explorer_selection_fill_spans_full_sidebar_width(qtbot) -> None:
    tree = CaseExplorerTree()
    tree.resize(320, 240)
    qtbot.addWidget(tree)

    selection_rect = tree._selection_fill_rect(QRect(52, 12, 180, 32))  # pyright: ignore[reportPrivateUsage]

    assert selection_rect.x() == GEOMETRY.unit
    assert selection_rect.width() == tree.viewport().width() - (GEOMETRY.unit * 2)
    assert selection_rect.y() > 12


def test_case_explorer_uses_patient_and_image_icons(qtbot, tmp_path: Path) -> None:
    store, settings, manifest, _package_path = _create_saved_package(
        tmp_path,
        patient_name="Alex Doe",
    )

    workspace = ImportWorkspace(
        manifest,
        settings,
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    imported_root = workspace._cases_tree.topLevelItem(0)
    case_item = imported_root.child(0)
    image_item = case_item.child(0)

    assert case_item.text(0) == case_tree_patient_label(manifest)
    assert case_item.icon(0).isNull() is False
    assert image_item.text(0) == "AP · current-ap.png"
    assert image_item.icon(0).isNull() is False
    assert not bool(image_item.flags() & Qt.ItemFlag.ItemIsSelectable)


def test_import_workspace_can_remove_case_from_explorer_without_deleting_disk(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, settings, current_manifest, current_path = _create_saved_package(
        tmp_path / "current",
        patient_name="Current Case",
    )
    _unused_store, _unused_settings, hidden_manifest, hidden_path = _create_saved_package(
        tmp_path / "hidden",
        patient_name="Archived Case",
    )
    settings.add_recent_case_path(hidden_path)
    settings.add_recent_case_path(current_path)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    workspace = ImportWorkspace(
        current_manifest,
        settings,
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    workspace._remove_case_from_explorer(str(hidden_path))  # pyright: ignore[reportPrivateUsage]

    imported_root = workspace._cases_tree.topLevelItem(0)  # pyright: ignore[reportPrivateUsage]

    assert imported_root.childCount() == 1
    assert hidden_path not in settings.load_recent_case_paths()
    assert current_path in settings.load_recent_case_paths()
    assert hidden_path.exists() is True


def test_import_workspace_case_tree_shows_saved_packages_only(
    qtbot,
    tmp_path: Path,
) -> None:
    store, settings, current_manifest, package_path = _create_saved_package(
        tmp_path,
        patient_name="Current Case",
    )

    workspace = ImportWorkspace(
        current_manifest,
        settings,
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    imported_root = workspace._cases_tree.topLevelItem(0)  # pyright: ignore[reportPrivateUsage]

    assert imported_root.text(0) == "Saved Cases"
    assert imported_root.childCount() == 1
    assert imported_root.child(0).data(0, import_workspace_module.CASE_TREE_REF_ROLE) == str(
        package_path
    )


def test_import_workspace_launches_with_matched_sidebars_and_midpoint_viewports(
    real_main_window,
    tmp_path: Path,
) -> None:
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "import-layout.ini"),
        QSettings.Format.IniFormat,
    )
    window = real_main_window(settings=settings)
    workspace = window._workspace_pages["import"]

    sidebar_sizes = workspace.outer_splitter.sizes()
    center_sizes = workspace._center_splitter.sizes()  # pyright: ignore[reportPrivateUsage]
    stack_sizes = workspace._xray_stack_splitter.sizes()  # pyright: ignore[reportPrivateUsage]

    assert abs(sidebar_sizes[0] - sidebar_sizes[2]) <= 1
    assert abs(center_sizes[0] - center_sizes[1]) <= 1
    assert abs(stack_sizes[0] - stack_sizes[1]) <= 1


def test_import_workspace_uses_one_flush_center_canvas_block(
    real_main_window,
) -> None:
    window = real_main_window()
    workspace = window._workspace_pages["import"]
    center_surface = workspace.outer_splitter.widget(1)

    assert isinstance(center_surface, QFrame)

    center_layout = center_surface.layout()
    assert center_layout is not None
    margins = center_layout.contentsMargins()

    assert margins.left() == 0
    assert margins.top() == 0
    assert margins.right() == 0
    assert margins.bottom() == 0

    center_canvas = center_layout.itemAt(0).widget()

    assert isinstance(center_canvas, QFrame)
    assert center_canvas.objectName() == "PanelInner"


def test_asset_rows_render_preview_thumbnail(qtbot, tmp_path: Path) -> None:
    image = QImage(24, 24, QImage.Format.Format_ARGB32)
    image.fill(qRgb(120, 120, 120))
    image_path = tmp_path / "preview.png"
    image.save(str(image_path))

    asset = StudyAsset(
        asset_id="preview-asset",
        kind="xray_2d",
        label="X-Ray",
        source_path=str(image_path),
        managed_path=str(image_path),
    )

    pixmap = build_asset_thumbnail(asset)
    row = AssetRowWidget(asset, delete_enabled=False, on_delete=lambda: None)
    qtbot.addWidget(row)
    preview_label = row.findChild(RoundedImagePreview, "AssetPreview")
    kind_badge = row.findChild(QLabel, "AssetTag")
    delete_button = row.findChild(QToolButton, "AssetDeleteButton")

    assert pixmap.isNull() is False
    assert preview_label is not None
    assert preview_label.pixmap() is not None
    assert preview_label.width() == GEOMETRY.asset_thumbnail_size
    assert preview_label.height() == GEOMETRY.asset_thumbnail_size
    assert kind_badge is not None
    assert kind_badge.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
    assert kind_badge.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
    assert delete_button is not None
    assert delete_button.text() == ""
    assert delete_button.icon().isNull() is False


def test_build_asset_thumbnail_uses_mid_nifti_slice_for_ct(tmp_path: Path) -> None:
    volume = np.zeros((8, 8, 5), dtype=np.float32)
    volume[2:6, 2:6, 2] = 255.0
    source_path = tmp_path / "preview-volume.nii.gz"
    nib.save(nib.Nifti1Image(volume, np.eye(4)), str(source_path))

    asset = StudyAsset(
        asset_id="ct-preview",
        kind="ct_zstack",
        label="CT",
        source_path=str(source_path),
        managed_path=str(source_path),
    )

    pixmap = build_asset_thumbnail(asset)
    image = pixmap.toImage()
    center = image.pixelColor(image.width() // 2, image.height() // 2)

    assert pixmap.isNull() is False
    assert center.red() > 200
    assert center.green() > 200
    assert center.blue() > 200


def test_asset_row_keeps_delete_button_visible_when_narrow(qtbot, tmp_path: Path) -> None:
    image = QImage(24, 24, QImage.Format.Format_ARGB32)
    image.fill(qRgb(120, 120, 120))
    image_path = tmp_path / ("very-long-preview-name-" * 4 + ".png")
    image.save(str(image_path))

    asset = StudyAsset(
        asset_id="narrow-asset",
        kind="xray_2d",
        label="X-Ray",
        source_path=str(image_path),
        managed_path=str(image_path),
    )

    row = AssetRowWidget(asset, delete_enabled=True, on_delete=lambda: None)
    row.resize(232, row.sizeHint().height())
    row.show()
    qtbot.addWidget(row)
    qtbot.wait(10)

    delete_button = row.findChild(QToolButton, "AssetDeleteButton")

    assert delete_button is not None
    assert delete_button.isVisible() is True

    top_left = delete_button.mapTo(row, delete_button.rect().topLeft())
    right_edge = top_left.x() + delete_button.width()
    expected_right = row.width() - GEOMETRY.panel_padding

    assert right_edge <= expected_right
    assert right_edge >= expected_right - GEOMETRY.control_height_md


def test_inspector_preview_surface_is_centered_in_preview_block(qtbot, tmp_path: Path) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    workspace.resize(1600, 900)
    workspace.show()
    qtbot.addWidget(workspace)
    qtbot.wait(50)

    preview_frame = workspace.findChild(QFrame, "InspectorPreviewFrame")
    assert preview_frame is not None
    assert isinstance(workspace._preview_label, RoundedImagePreview)
    assert (
        workspace._preview_label.sizePolicy().horizontalPolicy()
        == QSizePolicy.Policy.Expanding
    )
    assert (
        workspace._preview_label.sizePolicy().verticalPolicy()
        == QSizePolicy.Policy.Expanding
    )
    assert workspace._preview_label.geometry().size() == preview_frame.contentsRect().size()

    preview_item = preview_frame.layout().itemAt(0)
    assert preview_item.widget() is workspace._preview_label
    assert preview_item.alignment() == Qt.AlignmentFlag(0)


def test_import_inspector_summary_cards_use_shared_text_inset(qtbot, tmp_path: Path) -> None:
    workspace = ImportWorkspace(
        CaseManifest.blank(),
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    live_cards = [
        workspace._viewport_value_label.parentWidget(),
        workspace._metadata_rows["filename"].parentWidget(),
    ]
    for card in live_cards:
        assert card is not None
        margins = card.layout().contentsMargins()
        assert margins.left() == GEOMETRY.inspector_padding
        assert margins.right() == GEOMETRY.inspector_padding


def test_import_inspector_preview_uses_mid_nifti_slice_for_ct_stack(
    qtbot,
    tmp_path: Path,
) -> None:
    volume = np.zeros((8, 8, 5), dtype=np.float32)
    volume[2:6, 2:6, 2] = 255.0
    source_path = tmp_path / "preview-volume.nii.gz"
    nib.save(nib.Nifti1Image(volume, np.eye(4)), str(source_path))

    manifest = CaseManifest.blank()
    asset = StudyAsset(
        asset_id="ct-preview",
        kind="ct_zstack",
        label="CT",
        source_path=str(source_path),
        managed_path=str(source_path),
        processing_role="ct_stack",
    )
    manifest.assets.append(asset)
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        CaseStore(tmp_path),
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    image = workspace._build_inspector_preview(asset)  # pyright: ignore[reportPrivateUsage]
    center = image.pixelColor(image.width() // 2, image.height() // 2)

    assert center.red() > 200
    assert center.green() > 200
    assert center.blue() > 200


def test_stack_resolution_reports_slice_size_and_count(tmp_path: Path) -> None:
    for index in range(3):
        image = QImage(32, 24, QImage.Format.Format_ARGB32)
        image.fill(qRgb(80 + index, 80 + index, 80 + index))
        image.save(str(tmp_path / f"slice-{index}.png"))

    asset = StudyAsset(
        asset_id="ct-stack",
        kind="ct_zstack",
        label="CT",
        source_path=str(tmp_path),
        managed_path=str(tmp_path),
    )

    assert format_resolution(asset) == "32 × 24 · 3 slices"


def test_import_workspace_analyze_runs_pipeline_and_notifies(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    class StubPipeline:
        def __init__(self) -> None:
            self.called = False

        def submit_case_analysis(
            self,
            manifest: CaseManifest,
            progress_callback=None,
            **_kwargs,
        ) -> CaseManifest:
            self.called = True
            if progress_callback is not None:
                progress_callback(
                    AnalysisProgressUpdate(
                        stage=PipelineStageName.INGEST,
                        stage_index=1,
                        total_stages=8,
                        status="running",
                        detail="Preparing inputs",
                        percent=0,
                        stage_fraction=0.0,
                    )
                )
                progress_callback(
                    AnalysisProgressUpdate(
                        stage=PipelineStageName.INGEST,
                        stage_index=1,
                        total_stages=8,
                        status="complete",
                        detail="Ingest complete.",
                        percent=2,
                        stage_fraction=1.0,
                    )
                )
            manifest.pipeline_runs.append(PipelineRun(stage="ingest", status="complete"))
            return manifest

    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "dual"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    store.save_manifest(manifest)
    callback_payload: list[str] = []
    status_payload: list[tuple[str, bool]] = []
    prewarmed_model_counts: list[int] = []
    pipeline = StubPipeline()

    monkeypatch.setattr(
        import_workspace_module,
        "prewarm_lod_mesh_cache",
        lambda models, *, detail_levels, max_workers=None: prewarmed_model_counts.append(
            len(list(models))
        ),
    )

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
        pipeline=pipeline,
        on_manifest_updated=lambda updated_manifest: callback_payload.append(
            updated_manifest.case_id
        ),
        on_analysis_status_changed=lambda text, active, percent=0.0: status_payload.append((text, active)),
    )
    qtbot.addWidget(workspace)
    workspace._refresh_comparison_buttons()  # pyright: ignore[reportPrivateUsage]

    workspace._handle_analyze_requested()  # pyright: ignore[reportPrivateUsage]
    qtbot.waitUntil(lambda: callback_payload == [manifest.case_id], timeout=1000)
    qtbot.waitUntil(lambda: workspace._analysis_thread is None, timeout=1000)  # pyright: ignore[reportPrivateUsage]
    qtbot.waitUntil(lambda: prewarmed_model_counts == [5], timeout=1000)

    assert pipeline.called is True
    assert workspace._analyze_button.is_busy() is False
    assert callback_payload == [manifest.case_id]
    assert manifest.pipeline_runs[-1].stage == "ingest"
    assert prewarmed_model_counts == [5]
    assert status_payload[0] == ("Preparing analysis", True)
    assert ("Processing 1/8: Ingest", True) in status_payload
    assert ("Completed 1/8: Ingest", True) in status_payload
    assert ("Preparing review scene", True) in status_payload
    assert status_payload[-1] == ("", False)
    assert "Ingest" in workspace._analysis_status_card.value_label.text()  # pyright: ignore[reportPrivateUsage]
    assert "Awaiting Import review output" in workspace._analysis_review_card.value_label.text()  # pyright: ignore[reportPrivateUsage]


def test_import_workspace_keeps_failed_progress_visible_until_next_run(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    class StubPipeline:
        def __init__(self) -> None:
            self.calls = 0

        def submit_case_analysis(
            self,
            manifest: CaseManifest,
            progress_callback=None,
            **_kwargs,
        ) -> CaseManifest:
            self.calls += 1
            if self.calls == 1:
                if progress_callback is not None:
                    progress_callback(
                        AnalysisProgressUpdate(
                            stage=PipelineStageName.INGEST,
                            stage_index=1,
                            total_stages=8,
                            status="running",
                            detail="Preparing inputs",
                            percent=12,
                            stage_fraction=0.5,
                        )
                    )
                    progress_callback(
                        AnalysisProgressUpdate(
                            stage=PipelineStageName.INGEST,
                            stage_index=1,
                            total_stages=8,
                            status="failed",
                            detail="Input staging failed",
                            percent=12,
                            stage_fraction=0.5,
                        )
                    )
                raise RuntimeError("input staging failed")

            if progress_callback is not None:
                progress_callback(
                    AnalysisProgressUpdate(
                        stage=PipelineStageName.INGEST,
                        stage_index=1,
                        total_stages=8,
                        status="running",
                        detail="Preparing inputs",
                        percent=0,
                        stage_fraction=0.0,
                    )
                )
                progress_callback(
                    AnalysisProgressUpdate(
                        stage=PipelineStageName.INGEST,
                        stage_index=1,
                        total_stages=8,
                        status="complete",
                        detail="Ingest complete.",
                        percent=2,
                        stage_fraction=1.0,
                    )
                )
            manifest.pipeline_runs.append(PipelineRun(stage="ingest", status="complete"))
            return manifest

    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "dual"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    store.save_manifest(manifest)
    callback_payload: list[str] = []
    status_payload: list[tuple[str, bool]] = []
    critical_messages: list[str] = []
    pipeline = StubPipeline()

    monkeypatch.setattr(
        import_workspace_module.QMessageBox,
        "critical",
        lambda *args: critical_messages.append(str(args[-1])),
    )
    monkeypatch.setattr(
        import_workspace_module,
        "prewarm_lod_mesh_cache",
        lambda models, *, detail_levels, max_workers=None: None,
    )

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
        pipeline=pipeline,
        on_manifest_updated=lambda updated_manifest: callback_payload.append(
            updated_manifest.case_id
        ),
        on_analysis_status_changed=lambda text, active, percent=0.0: status_payload.append((text, active)),
    )
    qtbot.addWidget(workspace)
    workspace._refresh_comparison_buttons()  # pyright: ignore[reportPrivateUsage]

    workspace._handle_analyze_requested()  # pyright: ignore[reportPrivateUsage]
    qtbot.waitUntil(lambda: workspace._analysis_thread is None, timeout=1000)  # pyright: ignore[reportPrivateUsage]

    assert critical_messages == ["Unable to complete analysis.\n\ninput staging failed"]
    assert status_payload[-1] == ("Analyze failed at 1/8: Ingest", True)
    assert workspace._analysis_progress_percent == 12  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.is_busy() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.shows_spinner() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.is_spinner_active() is False  # pyright: ignore[reportPrivateUsage]
    assert workspace._turbo_mode_button.isEnabled() is True  # pyright: ignore[reportPrivateUsage]

    workspace._handle_analyze_requested()  # pyright: ignore[reportPrivateUsage]
    qtbot.waitUntil(lambda: callback_payload == [manifest.case_id], timeout=1000)
    qtbot.waitUntil(lambda: workspace._analysis_thread is None, timeout=1000)  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.is_busy() is False  # pyright: ignore[reportPrivateUsage]


def test_import_workspace_turbo_button_requires_two_clicks(
    qtbot,
    tmp_path: Path,
) -> None:
    settings = _settings_service(tmp_path)
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "dual"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    store.save_manifest(manifest)

    workspace = ImportWorkspace(
        manifest,
        settings,
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)
    button = workspace._turbo_mode_button  # pyright: ignore[reportPrivateUsage]

    assert workspace._performance_coordinator.active_mode == PerformanceMode.ADAPTIVE  # pyright: ignore[reportPrivateUsage]
    assert button.state() == "idle"

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert button.state() == "armed"
    assert workspace._performance_coordinator.active_mode == PerformanceMode.ADAPTIVE  # pyright: ignore[reportPrivateUsage]

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert button.state() == "active"
    assert workspace._performance_coordinator.active_mode == PerformanceMode.TURBO  # pyright: ignore[reportPrivateUsage]

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert button.state() == "idle"
    assert workspace._performance_coordinator.active_mode == PerformanceMode.ADAPTIVE  # pyright: ignore[reportPrivateUsage]


def test_import_workspace_analysis_start_clears_armed_turbo_button(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    class BlockingPipeline:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()

        def submit_case_analysis(
            self,
            manifest: CaseManifest,
            progress_callback=None,
            **_kwargs,
        ) -> CaseManifest:
            self.started.set()
            self.release.wait(timeout=1.0)
            return manifest

    settings = _settings_service(tmp_path)
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "dual"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    store.save_manifest(manifest)
    pipeline = BlockingPipeline()
    monkeypatch.setattr(
        import_workspace_module,
        "prewarm_lod_mesh_cache",
        lambda models, *, detail_levels, max_workers=None: None,
    )

    workspace = ImportWorkspace(
        manifest,
        settings,
        store,
        lambda case_id: None,
        pipeline=pipeline,
    )
    qtbot.addWidget(workspace)
    button = workspace._turbo_mode_button  # pyright: ignore[reportPrivateUsage]

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert button.is_armed() is True

    workspace._handle_analyze_requested()  # pyright: ignore[reportPrivateUsage]
    qtbot.waitUntil(lambda: pipeline.started.is_set(), timeout=1000)

    assert button.is_armed() is False
    assert button.isEnabled() is False

    pipeline.release.set()
    qtbot.waitUntil(lambda: workspace._analysis_thread is None, timeout=1000)  # pyright: ignore[reportPrivateUsage]

    assert button.isEnabled() is True
    assert button.state() == "idle"


def test_import_workspace_single_pose_arms_analyze_with_primary_only(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "single"
    manifest.comparison_modalities = {"primary": "ct"}
    store.save_manifest(manifest)

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)
    qtbot.waitUntil(
        lambda: workspace._comparison_selector_strip.maximumHeight()  # pyright: ignore[reportPrivateUsage]
        == GEOMETRY.major_button_height,
        timeout=1000,
    )

    assert workspace._comparison_selector_strip.mode() == "single"  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_selector_strip.maximumHeight() == GEOMETRY.major_button_height  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_buttons["primary"].isEnabled() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_buttons["secondary"].isEnabled() is False  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_selector_strip._secondary_host.isHidden() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.isEnabled() is True  # pyright: ignore[reportPrivateUsage]


def test_import_workspace_dual_pose_requires_both_modalities(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "dual"
    manifest.comparison_modalities = {"primary": "ct"}
    store.save_manifest(manifest)

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)
    qtbot.waitUntil(
        lambda: workspace._comparison_selector_strip._secondary_host.isHidden() is False,  # pyright: ignore[reportPrivateUsage]
        timeout=1000,
    )

    assert workspace._comparison_selector_strip.mode() == "dual"  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_selector_strip._secondary_host.isHidden() is False  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.isEnabled() is False  # pyright: ignore[reportPrivateUsage]

    workspace._set_comparison_modality("secondary", "xray")  # pyright: ignore[reportPrivateUsage]

    assert workspace._comparison_buttons["secondary"].isEnabled() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.isEnabled() is True  # pyright: ignore[reportPrivateUsage]


def test_import_workspace_pose_engine_switch_preserves_secondary_selection(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "dual"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    store.save_manifest(manifest)

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    workspace._set_analysis_pose_mode("single")  # pyright: ignore[reportPrivateUsage]
    qtbot.waitUntil(
        lambda: workspace._comparison_selector_strip._secondary_host.isHidden() is True,  # pyright: ignore[reportPrivateUsage]
        timeout=1000,
    )

    assert workspace._manifest.comparison_modalities["secondary"] == "xray"  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_selector_strip.mode() == "single"  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_selector_strip._secondary_host.isHidden() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.isEnabled() is True  # pyright: ignore[reportPrivateUsage]

    workspace._set_analysis_pose_mode("dual")  # pyright: ignore[reportPrivateUsage]
    qtbot.waitUntil(
        lambda: workspace._comparison_selector_strip._secondary_host.isHidden() is False,  # pyright: ignore[reportPrivateUsage]
        timeout=1000,
    )

    assert workspace._comparison_selector_strip.mode() == "dual"  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_buttons["secondary"].isEnabled() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.isEnabled() is True  # pyright: ignore[reportPrivateUsage]


def test_import_workspace_infers_single_pose_for_legacy_primary_only_manifest(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.comparison_modalities = {"primary": "ct"}
    store.save_manifest(manifest)

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)
    qtbot.waitUntil(
        lambda: workspace._comparison_selector_strip.maximumHeight()  # pyright: ignore[reportPrivateUsage]
        == GEOMETRY.major_button_height,
        timeout=1000,
    )

    assert workspace._pose_engine_button.text() == "Pose Engine: Single Pose"  # pyright: ignore[reportPrivateUsage]
    assert workspace._comparison_selector_strip.mode() == "single"  # pyright: ignore[reportPrivateUsage]
    assert workspace._analyze_button.isEnabled() is True  # pyright: ignore[reportPrivateUsage]


def test_import_workspace_auto_assigns_first_ct_and_xray_slots(qtbot, tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    store.save_manifest(manifest)

    ct_path = tmp_path / "case_ct.nii.gz"
    _write_test_nifti(ct_path)
    ap_path = tmp_path / "standing_ap.png"
    _write_test_png(ap_path)
    lat_path = tmp_path / "standing_lat.png"
    _write_test_png(lat_path)

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    workspace._import_into_library([ct_path, ap_path, lat_path])  # pyright: ignore[reportPrivateUsage]

    assert workspace._manifest.get_asset_for_role("ct_stack") is not None
    assert workspace._manifest.get_asset_for_role("xray_ap") is not None
    assert workspace._manifest.get_asset_for_role("xray_lat") is not None


def test_import_workspace_leaves_unrecognized_xray_unassigned(qtbot, tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    store.save_manifest(manifest)

    xray_path = tmp_path / "standing_view.png"
    _write_test_png(xray_path)

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    workspace._import_into_library([xray_path])  # pyright: ignore[reportPrivateUsage]

    assert workspace._manifest.get_asset_for_role("xray_ap") is None
    assert workspace._manifest.get_asset_for_role("xray_lat") is None


def test_import_workspace_can_guess_xray_role_from_dicom_metadata(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    store.save_manifest(manifest)

    dicom_path = tmp_path / "projection.dcm"
    _write_test_dicom(dicom_path, view_position="LAT")

    workspace = ImportWorkspace(
        manifest,
        SettingsService(),
        store,
        lambda case_id: None,
    )
    qtbot.addWidget(workspace)

    workspace._import_into_library([dicom_path])  # pyright: ignore[reportPrivateUsage]

    lat_asset = workspace._manifest.get_asset_for_role("xray_lat")
    assert lat_asset is not None
    assert Path(lat_asset.managed_path).suffix.lower() == ".dcm"


def test_suggested_import_role_uses_first_empty_slots(tmp_path: Path) -> None:
    manifest = CaseManifest.blank()
    ct_asset = StudyAsset(
        asset_id="ct-1",
        kind="ct_zstack",
        label="CT",
        source_path=str(tmp_path / "scan.nii.gz"),
        managed_path=str(tmp_path / "scan.nii.gz"),
    )
    xray_asset = StudyAsset(
        asset_id="xr-1",
        kind="xray_2d",
        label="X-Ray",
        source_path=str(tmp_path / "standing_ap.png"),
        managed_path=str(tmp_path / "standing_ap.png"),
    )

    assert suggested_import_role(manifest, ct_asset) == "ct_stack"
    manifest.assets.append(ct_asset)
    manifest.assign_asset_to_role(ct_asset.asset_id, "ct_stack")
    assert suggested_import_role(manifest, ct_asset) is None
    assert suggested_import_role(manifest, xray_asset) == "xray_ap"


def test_infer_xray_role_for_import_prefers_filename_then_metadata(tmp_path: Path) -> None:
    from_metadata = tmp_path / "projection.dcm"
    _write_test_dicom(from_metadata, view_position="PA")
    metadata_asset = StudyAsset(
        asset_id="xr-meta",
        kind="xray_2d",
        label="X-Ray",
        source_path=str(from_metadata),
        managed_path=str(from_metadata),
    )
    from_name = StudyAsset(
        asset_id="xr-name",
        kind="xray_2d",
        label="X-Ray",
        source_path=str(tmp_path / "standing_lateral.png"),
        managed_path=str(tmp_path / "standing_lateral.png"),
    )

    assert infer_xray_role_for_import(metadata_asset) == "xray_ap"
    assert infer_xray_role_for_import(from_name) == "xray_lat"


def _write_test_dicom(path: Path, *, view_position: str) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = generate_uid()
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    dataset = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = file_meta.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.Modality = "DX"
    dataset.PatientName = "Test^Projection"
    dataset.PatientID = "TEST-001"
    dataset.ViewPosition = view_position
    dataset.SeriesDescription = f"{view_position} spine"
    pydicom.dcmwrite(
        str(path),
        dataset,
        little_endian=True,
        implicit_vr=False,
        enforce_file_format=True,
    )


def _write_test_png(path: Path) -> None:
    image = QImage(12, 12, QImage.Format.Format_Grayscale8)
    image.fill(180)
    image.save(str(path))


def _write_test_nifti(path: Path) -> None:
    volume = np.zeros((8, 8, 8), dtype=np.int16)
    nib.save(nib.Nifti1Image(volume, np.eye(4)), str(path))
