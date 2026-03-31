from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QPushButton

from spinelab.models import CaseManifest
from spinelab.services import SettingsService
from spinelab.visualization.viewer_3d import MockVertebra
from spinelab.workspaces import report_workspace as report_module
from spinelab.workspaces.report_widgets import KpiCardWidget
from spinelab.workspaces.report_workspace import ReportWorkspace


def build_pose_scene() -> list[MockVertebra]:
    return [
        MockVertebra("L1", "L1", (0.0, 0.0, 10.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra("T1", "T1", (0.0, 0.0, 20.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra(
            "L1",
            "L1 Standing",
            (0.0, 0.0, 11.5),
            (1.0, 1.0, 1.0),
            render_id="L1_STANDING",
            selection_id="L1",
            pose_name="standing",
        ),
        MockVertebra(
            "T1",
            "T1 Standing",
            (0.0, 1.2, 20.0),
            (1.0, 1.0, 1.0),
            render_id="T1_STANDING",
            selection_id="T1",
            pose_name="standing",
        ),
    ]


def test_report_workspace_tracks_vertebra_selection(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(report_module, "models_for_manifest", lambda _manifest: build_pose_scene())

    workspace = ReportWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._handle_vertebra_requested("T1")

    assert workspace._view_state.selected_vertebra_id == "T1"
    assert workspace._view_state.selected_region_id == "thoracic"


def test_report_workspace_preserves_selection_on_activation(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(report_module, "models_for_manifest", lambda _manifest: build_pose_scene())

    workspace = ReportWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)
    workspace._handle_vertebra_requested("L1")

    workspace.on_workspace_activated()

    assert workspace._view_state.selected_vertebra_id == "L1"
    assert workspace._view_state.selected_region_id == "lumbar"


def test_report_workspace_region_selection_uses_region_anchor(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(report_module, "models_for_manifest", lambda _manifest: build_pose_scene())

    workspace = ReportWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._handle_region_requested("lumbar")

    assert workspace._view_state.selected_region_id == "lumbar"
    assert workspace._view_state.selected_vertebra_id is None


def test_report_workspace_applies_shared_point_size_to_hero_viewport(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(report_module, "models_for_manifest", lambda _manifest: build_pose_scene())

    workspace = ReportWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace.apply_shared_display_state(
        mode=workspace._shared_viewport_mode,
        detail_level=workspace._shared_detail_level,
        point_size=14,
        baseline_visible=True,
        standing_visible=True,
    )

    assert workspace._hero_viewport.current_point_size() == 14


def test_report_workspace_detail_panel_uses_compact_metric_rows(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(report_module, "models_for_manifest", lambda _manifest: build_pose_scene())

    workspace = ReportWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    workspace._handle_region_requested("lumbar")

    assert workspace._detail_scope_value.text() == "Lumbar region"
    assert workspace._detail_target_value.text() == "Lumbar Lordosis"
    assert workspace._detail_measurement_value.text() == "46.2 deg"
    assert "Total" in workspace._detail_summary_value.text()


def test_report_workspace_honors_shared_left_sidebar_width(
    qtbot,
    real_main_window,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(report_module, "models_for_manifest", lambda _manifest: build_pose_scene())

    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "report-workspace.ini"),
        QSettings.Format.IniFormat,
    )
    settings.save_shell_sidebar_visibility(True, True)
    settings.save_shell_sidebar_widths(360, 288)

    window = real_main_window(
        settings=settings,
        manifest=CaseManifest.demo(),
        analysis_ready=True,
    )
    window.set_workspace("report")
    qtbot.wait(50)
    workspace = window._workspace_pages["report"]
    workspace.sync_shell_layout()
    qtbot.wait(50)

    assert workspace.outer_splitter.sizes()[0] >= 340


def test_report_workspace_launch_width_fits_sidebar_content(
    qtbot,
    real_main_window,
    tmp_path: Path,
) -> None:
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "report-launch.ini"),
        QSettings.Format.IniFormat,
    )

    window = real_main_window(
        settings=settings,
        manifest=CaseManifest.demo(),
        analysis_ready=True,
    )
    window.set_workspace("report")
    qtbot.wait(50)
    workspace = window._workspace_pages["report"]

    assert workspace.outer_splitter.sizes()[0] >= workspace._left_panel.sizeHint().width()


def test_report_workspace_export_buttons_use_save_icon_on_right(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(report_module, "models_for_manifest", lambda _manifest: build_pose_scene())

    workspace = ReportWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    export_buttons = workspace.findChildren(QPushButton, "ReportExportButton")

    assert len(export_buttons) >= 4
    assert all(button.icon().isNull() is False for button in export_buttons)
    assert all(
        button.layoutDirection() == report_module.Qt.LayoutDirection.RightToLeft
        for button in export_buttons
    )


def test_report_panels_use_shared_text_inset(qtbot) -> None:
    workspace = ReportWorkspace(CaseManifest.demo(), SettingsService())
    qtbot.addWidget(workspace)

    for section_id in report_module.REPORT_SECTION_IDS:
        margins = workspace._section_anchors[section_id].layout().contentsMargins()
        assert margins.left() == report_module.GEOMETRY.panel_padding
        assert margins.right() == report_module.GEOMETRY.panel_padding

    kpi_cards = workspace.findChildren(KpiCardWidget)
    assert kpi_cards
    for card in kpi_cards:
        margins = card.layout().contentsMargins()
        assert margins.left() == report_module.GEOMETRY.panel_padding
        assert margins.right() == report_module.GEOMETRY.panel_padding
