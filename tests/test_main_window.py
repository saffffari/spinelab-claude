import json
import sys
from pathlib import Path

from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtWidgets import QLabel, QStackedLayout, QStyleOptionToolButton, QToolButton, QWidget

import spinelab.app.main_window as main_window_module
from spinelab.app.main_window import clamp_rect_to_bounds, summarize_pipeline_status
from spinelab.io import SpinePackageService
from spinelab.models import CaseManifest, PipelineRun, StudyAsset
from spinelab.services import SettingsService, classify_render_backend
from spinelab.ui.theme import THEME_COLORS
from spinelab.ui.widgets import TransparentSplitter
from spinelab.ui.widgets.chrome import HeaderStatusStrip, LoadingCapsule, MenuButton


def test_clamp_rect_to_bounds_limits_oversized_window_to_screen() -> None:
    screen = QRect(0, 0, 1920, 1080)
    oversized = QRect(200, 100, 24000, 1400)

    clamped = clamp_rect_to_bounds(oversized, screen)

    assert clamped.width() == screen.width()
    assert clamped.height() == screen.height()
    assert clamped.x() == screen.x()
    assert clamped.y() == screen.y()


def test_clamp_rect_to_bounds_repositions_offscreen_window_without_growing_it() -> None:
    screen = QRect(0, 0, 1920, 1080)
    shifted = QRect(1800, 900, 900, 600)

    clamped = clamp_rect_to_bounds(shifted, screen)

    assert clamped.width() == 900
    assert clamped.height() == 600
    assert clamped.right() <= screen.right()
    assert clamped.bottom() <= screen.bottom()


def test_summarize_pipeline_status_reports_idle_for_blank_case() -> None:
    status_text, active = summarize_pipeline_status(CaseManifest.blank())

    assert status_text == "Idle"
    assert active is False


def test_summarize_pipeline_status_reports_processing_stage() -> None:
    manifest = CaseManifest.blank()
    manifest.pipeline_runs = [PipelineRun(stage="registration", status="processing")]

    status_text, active = summarize_pipeline_status(manifest)

    assert status_text == "Loading Registration"
    assert active is True


def test_workspace_selection_and_display_state_carry_across_measurement_and_report(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window._manifest = CaseManifest.demo()
    window._analysis_ready_for_tabs = True  # pyright: ignore[reportPrivateUsage]
    window._create_workspaces()
    window.set_workspace("measurement")

    measurement_page = window._workspace_pages["measurement"]
    first_id = measurement_page._model_ids[0]
    second_id = measurement_page._model_ids[1]
    measurement_page._handle_vertebra_button_interaction(first_id, False)
    measurement_page._viewport.set_mode(main_window_module.ViewportMode.WIRE)
    measurement_page._viewport.set_detail_level(3)
    measurement_page._set_pose_visible("standing", False)  # pyright: ignore[reportPrivateUsage]

    assert measurement_page._selection_state.selected_ids == (first_id,)

    window.set_workspace("report")
    report_page = window._workspace_pages["report"]

    assert (
        report_page._hero_viewport.current_viewport_mode()
        == main_window_module.ViewportMode.WIRE
    )
    assert report_page._hero_viewport.current_detail_level() == 3
    assert report_page._hero_viewport.current_pose_visibility() == (True, False)
    assert report_page._hero_viewport._viewport._selected_ids == (first_id,)
    assert report_page._hero_viewport._viewport._active_id == first_id
    assert (
        report_page._hero_viewport._viewport._reference_id
        == measurement_page._default_reference_id
    )

    report_page._handle_vertebra_requested(second_id)  # pyright: ignore[reportPrivateUsage]
    window.set_workspace("measurement")

    assert measurement_page._selection_state.selected_ids == (second_id,)
    assert measurement_page._selection_state.active_id == second_id
    assert measurement_page._selection_state.reference_id == measurement_page._default_reference_id
    assert measurement_page._viewport.current_mode() == main_window_module.ViewportMode.WIRE
    assert measurement_page._viewport.current_detail_level() == 3
    assert measurement_page._viewport.current_pose_visibility() == (True, False)


def test_transparent_splitter_keeps_live_resize_enabled() -> None:
    splitter = TransparentSplitter(Qt.Orientation.Horizontal)

    assert splitter.opaqueResize() is True


def test_main_window_defers_heavy_workspaces_until_requested(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert set(window._workspace_pages) == {"import"}
    assert window._stack.count() == 1

    window.set_workspace("report")

    assert set(window._workspace_pages) == {"import", "report"}
    assert window._stack.count() == 2


def test_main_window_sets_loading_status_before_workspace_factory_runs(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    status_snapshot: dict[str, object] = {}

    def measurement_factory() -> QWidget:
        assert window._header_status is not None
        status_snapshot["text"] = window._header_status._status_label.text()
        status_snapshot["active"] = window._header_status._progress_capsule._active
        return QWidget()

    window._workspace_factories["measurement"] = measurement_factory
    window.set_workspace("measurement")

    assert status_snapshot == {
        "text": "Loading Measurement workspace",
        "active": True,
    }
    assert window._header_status is not None
    assert window._header_status._status_label.text() == "Idle"


def test_main_window_sets_loading_status_when_switching_existing_workspace(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.set_workspace("measurement")
    window.set_workspace("import")

    measurement_page = window._workspace_pages["measurement"]
    status_snapshot: dict[str, object] = {}
    original_activate = measurement_page.on_workspace_activated

    def wrapped_activate() -> None:
        assert window._header_status is not None
        status_snapshot["text"] = window._header_status._status_label.text()
        status_snapshot["active"] = window._header_status._progress_capsule._active
        original_activate()

    measurement_page.on_workspace_activated = wrapped_activate
    window.set_workspace("measurement")

    assert status_snapshot == {
        "text": "Opening Measurement workspace",
        "active": True,
    }


def test_main_window_close_prompt_uses_cancel_processing_path_during_active_analysis(
    qtbot,
    monkeypatch,
) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window._active_session.dirty = True  # pyright: ignore[reportPrivateUsage]
    prompt_calls: list[str] = []
    save_calls: list[str] = []

    monkeypatch.setattr(
        window._workspace_pages["import"],
        "has_active_analysis",
        lambda: True,
    )
    monkeypatch.setattr(
        window,
        "_confirm_cancel_processing_and_discard",
        lambda: prompt_calls.append("prompt") or True,
    )
    monkeypatch.setattr(
        window,
        "_save_case",
        lambda: save_calls.append("save") or None,
    )

    assert window._maybe_discard_or_save_session() is True  # pyright: ignore[reportPrivateUsage]
    assert prompt_calls == ["prompt"]
    assert save_calls == []


def test_main_window_close_prompt_can_keep_running_during_active_analysis(
    qtbot,
    monkeypatch,
) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    monkeypatch.setattr(
        window._workspace_pages["import"],
        "has_active_analysis",
        lambda: True,
    )
    monkeypatch.setattr(
        window,
        "_confirm_cancel_processing_and_discard",
        lambda: False,
    )

    assert window._maybe_discard_or_save_session() is False  # pyright: ignore[reportPrivateUsage]


def test_main_window_uses_stack_one_and_hides_inactive_workspaces(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(50)

    stack_layout = window._stack.layout()
    assert isinstance(stack_layout, QStackedLayout)
    assert stack_layout.stackingMode() == QStackedLayout.StackingMode.StackOne

    import_page = window._workspace_pages["import"]
    assert import_page.isVisible() is True

    window.set_workspace("measurement")
    qtbot.wait(50)

    measurement_page = window._workspace_pages["measurement"]
    assert measurement_page.isVisible() is True
    assert import_page.isVisible() is False


def test_main_window_hides_native_measurement_plotters_when_switching_tabs(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window._manifest = CaseManifest.demo()
    window._analysis_ready_for_tabs = True  # pyright: ignore[reportPrivateUsage]
    window._create_workspaces()
    window.set_workspace("import")
    window.resize(1600, 900)
    window.show()
    qtbot.wait(50)
    window.set_workspace("measurement")
    qtbot.wait(50)

    measurement_page = window._workspace_pages["measurement"]
    plotters = [
        measurement_page._viewport._plotter,
        measurement_page._front_viewport._plotter,
        measurement_page._side_viewport._plotter,
    ]
    if any(plotter is None for plotter in plotters):
        return

    assert all(plotter.isVisible() for plotter in plotters)

    window.set_workspace("import")
    qtbot.wait(50)

    assert all(not plotter.isVisible() for plotter in plotters)


def test_main_window_disposes_existing_workspace_widgets_before_rebuild(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    class DisposableWidget(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.dispose_called = False
            self.close_called = False

        def dispose(self) -> None:
            self.dispose_called = True

        def close(self) -> bool:
            self.close_called = True
            return super().close()

    window = MainWindow()
    qtbot.addWidget(window)
    disposable = DisposableWidget()
    window._stack.addWidget(disposable)
    window._workspace_pages["disposable"] = disposable

    window._create_workspaces()

    assert disposable.dispose_called is True
    assert disposable.close_called is True


def test_main_window_starts_maximized(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert bool(window.windowState() & Qt.WindowState.WindowMaximized)


def test_main_window_uses_frameless_single_title_bar(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert window.findChild(QWidget, "HeaderBar") is not None


def test_main_window_header_exposes_window_control_buttons(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    minimize_button = window.findChild(QWidget, "HeaderMinimizeButton")
    maximize_button = window.findChild(QWidget, "HeaderMaximizeButton")
    close_button = window.findChild(QWidget, "HeaderCloseButton")

    assert minimize_button is not None
    assert maximize_button is not None
    assert close_button is not None


def test_main_window_tools_menu_exposes_segmentation_backends_action(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    tools_menu = window._create_menu("Tools")  # pyright: ignore[reportPrivateUsage]
    action_texts = [action.text() for action in tools_menu.actions()]

    assert "Segmentation Backends..." in action_texts


def test_main_window_maximize_button_toggles_restore_state(qtbot, monkeypatch) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    maximize_button = window.findChild(QToolButton, "HeaderMaximizeButton")
    state = {"maximized": True}

    monkeypatch.setattr(window, "isMaximized", lambda: state["maximized"])
    monkeypatch.setattr(window, "showNormal", lambda: state.__setitem__("maximized", False))
    monkeypatch.setattr(window, "showMaximized", lambda: state.__setitem__("maximized", True))
    window._refresh_window_control_buttons()  # pyright: ignore[reportPrivateUsage]

    assert maximize_button is not None
    assert maximize_button.text() == "❐"
    assert maximize_button.toolTip() == "Restore"

    maximize_button.click()

    assert state["maximized"] is False
    assert maximize_button.text() == "□"
    assert maximize_button.toolTip() == "Maximize"

    maximize_button.click()

    assert state["maximized"] is True
    assert maximize_button.text() == "❐"
    assert maximize_button.toolTip() == "Restore"


class _StubMouseEvent:
    def __init__(self, button: Qt.MouseButton) -> None:
        self._button = button
        self.accepted = False

    def button(self) -> Qt.MouseButton:
        return self._button

    def accept(self) -> None:
        self.accepted = True


def test_title_bar_left_press_starts_system_move(qtbot, monkeypatch) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    header = window.findChild(QWidget, "HeaderBar")
    move_calls: list[bool] = []

    monkeypatch.setattr(window, "_start_system_move", lambda: move_calls.append(True) or True)
    event = _StubMouseEvent(Qt.MouseButton.LeftButton)

    assert header is not None

    header.mousePressEvent(event)

    assert move_calls == [True]
    assert event.accepted is True


def test_title_bar_double_click_toggles_maximize_restore(qtbot, monkeypatch) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    header = window.findChild(QWidget, "HeaderBar")
    toggle_calls: list[bool] = []

    monkeypatch.setattr(
        window,
        "_toggle_maximize_restore",
        lambda: toggle_calls.append(True),
    )
    event = _StubMouseEvent(Qt.MouseButton.LeftButton)

    assert header is not None

    header.mouseDoubleClickEvent(event)

    assert toggle_calls == [True]
    assert event.accepted is True


def test_header_status_strip_keeps_loading_capsule_left_and_blue(qtbot) -> None:
    header_status = HeaderStatusStrip()
    qtbot.addWidget(header_status)

    layout = header_status.layout()
    first_item = layout.itemAt(0)
    second_item = layout.itemAt(1)

    assert isinstance(first_item.widget(), LoadingCapsule)
    assert first_item.widget().track_color_css() == THEME_COLORS.info_soft
    assert first_item.widget().fill_color_css() == THEME_COLORS.info
    assert first_item.widget().isHidden() is True
    assert second_item.widget() is header_status._status_label


def test_header_status_strip_loading_capsule_tracks_target_width_within_header(qtbot) -> None:
    header_status = HeaderStatusStrip()
    header_status.resize(1200, 48)
    header_status.show()
    qtbot.addWidget(header_status)
    qtbot.wait(20)

    header_status.set_progress_target_width(320)
    qtbot.wait(20)
    wide_width = header_status._progress_capsule.width()

    header_status.resize(360, 48)
    qtbot.wait(20)
    narrow_width = header_status._progress_capsule.width()

    assert wide_width == 0
    assert narrow_width == 0


def test_main_window_header_loading_capsule_tracks_active_sidebar_width(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    window.resize(1600, 900)
    window.show()
    qtbot.addWidget(window)
    qtbot.wait(50)

    import_page = window._workspace_pages["import"]
    sizes = import_page.outer_splitter.sizes()  # pyright: ignore[reportPrivateUsage]
    left_width = 336
    center_width = max(1, sum(sizes) - left_width - sizes[2])
    import_page.outer_splitter.setSizes([left_width, center_width, sizes[2]])  # pyright: ignore[reportPrivateUsage]
    import_page._persist_splitter()  # pyright: ignore[reportPrivateUsage]
    qtbot.wait(20)

    assert window._header_status is not None
    assert window._header_status.progress_target_width() == left_width
    assert window._header_status._progress_capsule.isHidden() is True


def test_main_window_warns_once_and_blocks_interactive_3d_on_software_renderer(
    qtbot,
    monkeypatch,
) -> None:
    env_bin = Path(sys.prefix) / "Library" / "bin"
    software_probe = classify_render_backend(
        backend_class="OpenGL2",
        opengl_vendor="Mesa/X.org",
        opengl_renderer="llvmpipe",
        opengl_version="4.5",
        render_window_class="vtkWin32OpenGLRenderWindow",
        loaded_module_paths=(
            str(env_bin / "OPENGL32.dll"),
            str(env_bin / "libgallium_wgl.dll"),
        ),
    )
    warning_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(main_window_module, "probe_render_backend", lambda: software_probe)
    monkeypatch.setattr(main_window_module, "should_enforce_hardware_rendering", lambda: True)
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        lambda _parent, title, text: warning_calls.append((title, text)),
    )

    window = main_window_module.MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(50)

    assert len(warning_calls) == 1
    assert "non-hardware OpenGL backend" in warning_calls[0][1]
    assert window._render_mode_button is not None
    assert window._render_mode_button.text() == "CPU"
    assert window._render_mode_button.property("variant") == "danger"

    window.set_workspace("measurement")
    qtbot.wait(50)
    measurement_page = window._workspace_pages["measurement"]

    assert measurement_page._viewport._plotter is None
    assert measurement_page._front_viewport._plotter is None
    assert measurement_page._side_viewport._plotter is None

    window.set_workspace("report")
    qtbot.wait(50)
    report_page = window._workspace_pages["report"]

    assert report_page._hero_viewport._viewport._plotter is None


def test_main_window_keeps_measurement_and_report_pending_until_analyze(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window._manifest = CaseManifest.demo()
    window._analysis_ready_for_tabs = False  # pyright: ignore[reportPrivateUsage]
    window._create_workspaces()

    window.set_workspace("measurement")
    measurement_page = window._workspace_pages["measurement"]
    assert measurement_page._analysis_ready is False
    assert measurement_page._has_model_scene is False
    assert measurement_page._measurement_records == ()
    warning_labels = measurement_page.findChildren(QLabel, "PendingAnalysisMessage")
    assert len(warning_labels) == 3
    assert {label.text() for label in warning_labels} == {"No Analysis Performed"}

    window.set_workspace("report")
    report_page = window._workspace_pages["report"]
    assert report_page._analysis_ready is False
    assert report_page._dataset.has_measurements is False
    assert report_page._section_list.isEnabled() is False


def test_main_window_unlocks_measurement_and_report_after_manifest_update(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window._manifest = CaseManifest.demo()
    window._analysis_ready_for_tabs = False  # pyright: ignore[reportPrivateUsage]
    window._create_workspaces()

    window._handle_manifest_updated(CaseManifest.demo())  # pyright: ignore[reportPrivateUsage]

    assert window._analysis_ready_for_tabs is True  # pyright: ignore[reportPrivateUsage]
    assert set(window._workspace_pages) == {"import", "measurement", "report"}
    measurement_page = window._workspace_pages["measurement"]
    assert window._stack.currentWidget() is measurement_page

    assert measurement_page._analysis_ready is True
    assert measurement_page._has_model_scene is True

    window.set_workspace("report")
    report_page = window._workspace_pages["report"]
    assert report_page._analysis_ready is True
    assert report_page._section_list.isEnabled() is True


def test_main_window_clear_cases_resets_recent_package_catalog_and_blank_case(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    store = main_window_module.CaseStore(tmp_path)
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "main-window-settings.ini"),
        QSettings.Format.IniFormat,
    )
    manifest = CaseManifest.demo()
    session = store.session_store.create_blank_session(manifest=manifest)
    store.activate_session(session)
    package_service = SpinePackageService(store.session_store)
    package_path = tmp_path / f"{manifest.case_id}.spine"
    package_service.save_package(session, manifest, package_path)
    settings.add_recent_case_path(package_path)
    monkeypatch.setattr(main_window_module, "CaseStore", lambda: store)
    monkeypatch.setattr(main_window_module, "SettingsService", lambda: settings)
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: main_window_module.QMessageBox.StandardButton.Yes,
    )

    window = main_window_module.MainWindow()
    qtbot.addWidget(window)
    window._load_case(str(package_path))

    window._clear_cases_from_explorer()

    assert settings.load_recent_case_paths() == []
    assert window._manifest.patient_name == manifest.patient_name
    assert window._stack.currentWidget() is window._workspace_pages["import"]


def test_main_window_opens_legacy_case_folder_into_transient_session(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("SPINELAB_SESSION_ROOT", str(tmp_path / "sessions"))
    legacy_root = tmp_path / "legacy-case"
    manifest = CaseManifest.demo()
    ct_path = legacy_root / "ct" / "volume.nii.gz"
    manifest_path = legacy_root / "analytics" / "manifest.json"
    ct_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    ct_path.write_bytes(b"legacy-ct")
    manifest.assets.append(
        StudyAsset(
            asset_id="asset-ct",
            kind="ct_zstack",
            label="CT",
            source_path=str(ct_path),
            managed_path=str(ct_path),
            processing_role="ct_stack",
        )
    )
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    window = main_window_module.MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(legacy_root),
    )

    window._open_legacy_case_dialog()

    assert window._active_session is not None
    assert window._active_session.source_kind == "legacy"
    assert window._manifest.patient_name == manifest.patient_name
    assert (window._active_session.workspace_root / "ct" / "volume.nii.gz").exists() is True


def test_header_menu_button_style_option_hides_disclosure_arrow() -> None:
    button = MenuButton("File")
    option = QStyleOptionToolButton()

    button.initStyleOption(option)

    assert not bool(option.features & QStyleOptionToolButton.ToolButtonFeature.HasMenu)
    assert not bool(
        option.features & QStyleOptionToolButton.ToolButtonFeature.MenuButtonPopup
    )
    assert option.arrowType == Qt.ArrowType.NoArrow


def test_header_text_elements_share_one_size_and_brand_uses_heaviest_weight(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    brand_label = window.findChild(QLabel, "HeaderBrandLabel")
    case_label = window.findChild(QLabel, "HeaderCaseLabel")
    menu_buttons = window.findChildren(MenuButton, "HeaderMenuButton")

    assert brand_label is not None
    assert case_label is not None
    assert menu_buttons

    shared_point_size = menu_buttons[0].font().pointSize()
    assert brand_label.font().pointSize() == shared_point_size
    assert case_label.font().pointSize() == shared_point_size
    assert all(button.font().pointSize() == shared_point_size for button in menu_buttons)
    assert brand_label.font().family() == menu_buttons[0].font().family()
    assert all(
        button.font().pointSize() == shared_point_size
        for button in window._workspace_buttons.values()
    )
    assert brand_label.font().weight() == 600


def test_workspace_tabs_use_dedicated_header_tab_buttons(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert set(window._workspace_buttons) == {"import", "measurement", "report"}
    assert all(
        button.objectName() == "HeaderWorkspaceTabButton"
        for button in window._workspace_buttons.values()
    )
    assert window._workspace_buttons["import"].isChecked() is True
    assert window._workspace_buttons["measurement"].isChecked() is False
    assert window._workspace_buttons["report"].isChecked() is False


def test_main_window_places_runtime_status_controls_before_case_label(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window._header_status is not None
    assert window._render_mode_button is not None
    assert window._case_label is not None
    header_layout = window.findChild(QWidget, "HeaderBar").layout()
    runtime_index = header_layout.indexOf(window._header_status)
    render_index = header_layout.indexOf(window._render_mode_button)
    case_index = header_layout.indexOf(window._case_label)

    assert runtime_index >= 0
    assert render_index == runtime_index + 1
    assert case_index == render_index + 1


def test_main_window_renderer_button_cycles_gpu_and_cpu_when_hardware_is_available(qtbot) -> None:
    from spinelab.app.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window._render_mode_button is not None
    assert window._render_mode_button.text() == "GPU"
    assert window._render_mode_button.property("variant") == "success"

    qtbot.mouseClick(window._render_mode_button, Qt.MouseButton.LeftButton)

    assert window._render_mode_button.text() == "CPU"
    assert window._render_mode_button.property("variant") == "danger"

    qtbot.mouseClick(window._render_mode_button, Qt.MouseButton.LeftButton)

    assert window._render_mode_button.text() == "GPU"
    assert window._render_mode_button.property("variant") == "success"


def test_main_window_launches_with_shared_sidebar_width_across_tabs(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "main-window-layout.ini"),
        QSettings.Format.IniFormat,
    )
    settings.save_shell_sidebar_visibility(True, True)
    settings.save_shell_sidebar_widths(248, 312)
    monkeypatch.setattr(main_window_module, "SettingsService", lambda: settings)

    window = main_window_module.MainWindow()
    qtbot.addWidget(window)
    window._manifest = CaseManifest.demo()
    window._analysis_ready_for_tabs = True  # pyright: ignore[reportPrivateUsage]
    window._create_workspaces()
    window.set_workspace("import")
    window.resize(1600, 900)
    window.show()
    qtbot.wait(50)

    import_page = window._workspace_pages["import"]
    import_sizes = import_page.outer_splitter.sizes()

    window.set_workspace("measurement")
    qtbot.wait(50)
    measurement_page = window._workspace_pages["measurement"]
    measurement_sizes = measurement_page.outer_splitter.sizes()

    window.set_workspace("report")
    qtbot.wait(50)
    report_page = window._workspace_pages["report"]
    report_sizes = report_page.outer_splitter.sizes()

    assert abs(import_sizes[0] - import_sizes[2]) <= 1
    assert abs(measurement_sizes[0] - measurement_sizes[2]) <= 1
    assert import_sizes[0] >= 312
    assert measurement_sizes[0] >= import_sizes[0]
    assert report_sizes[0] >= import_sizes[0]
