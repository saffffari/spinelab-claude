from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QEventLoop, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QGuiApplication,
    QMouseEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedLayout,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from spinelab.exports import generate_testing_drrs
from spinelab.io import (
    DEFAULT_DATA_ROOT,
    PACKAGE_FILE_FILTER,
    CaseStore,
    LegacyCaseImporter,
    SessionHandle,
    SpinePackageError,
    SpinePackageService,
)
from spinelab.models import CaseManifest
from spinelab.pipeline import PipelineOrchestrator
from spinelab.segmentation import terminate_tracked_segmentation_processes
from spinelab.services import (
    RenderBackendProbe,
    SettingsService,
    configure_runtime_policy,
    probe_render_backend,
    should_enforce_hardware_rendering,
)
from spinelab.ui.theme import GEOMETRY
from spinelab.ui.widgets import CapsuleButton, HeaderStatusStrip, MenuButton, apply_text_role
from spinelab.visualization import ViewportMode
from spinelab.visualization.viewer_3d import DEFAULT_DETAIL_LEVEL

WORKSPACE_ORDER = ("import", "measurement", "report")



def clamp_rect_to_bounds(rect: QRect, bounds: QRect) -> QRect:
    width = min(rect.width(), bounds.width())
    height = min(rect.height(), bounds.height())
    x = max(bounds.x(), min(rect.x(), bounds.right() - width + 1))
    y = max(bounds.y(), min(rect.y(), bounds.bottom() - height + 1))
    return QRect(x, y, width, height)


def summarize_pipeline_status(manifest: CaseManifest) -> tuple[str, bool]:
    active_statuses = {"processing", "running", "queued"}
    active_runs = [
        run
        for run in manifest.pipeline_runs
        if run.status.strip().lower() in active_statuses
    ]
    if active_runs:
        if len(active_runs) == 1:
            stage_name = active_runs[0].stage.replace("_", " ").title()
            return f"Loading {stage_name}", True
        return f"Loading {len(active_runs)} processes", True
    if manifest.assets:
        return "Ready", False
    return "Idle", False


class TitleBarFrame(QFrame):
    def __init__(self, owner: MainWindow) -> None:
        super().__init__()
        self._owner = owner

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._owner._start_system_move():
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner._toggle_maximize_restore()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._terminate_backend_processes)
        self._settings = SettingsService()
        configure_runtime_policy(settings=self._settings)
        left_visible, _right_visible = self._settings.load_shell_sidebar_visibility(True, True)
        self._settings.save_shell_sidebar_visibility(left_visible, True)
        self._store = CaseStore()
        self._store.session_store.purge_orphaned_sessions()
        self._package_service = SpinePackageService(self._store.session_store)
        self._legacy_importer = LegacyCaseImporter(self._store.session_store)
        self._pipeline = PipelineOrchestrator(self._store, settings=self._settings)
        self._active_session: SessionHandle | None = self._store.session_store.create_blank_session(
            manifest=self._store.create_blank_case()
        )
        self._store.activate_session(self._active_session)
        self._manifest = self._store.session_store.load_runtime_manifest(self._active_session)
        self._workspace_buttons: dict[str, CapsuleButton] = {}
        self._workspace_pages: dict[str, QWidget] = {}
        self._workspace_factories: dict[str, Callable[[], QWidget]] = {}
        self._case_label: QLabel | None = None
        self._header_status: HeaderStatusStrip | None = None
        self._render_mode_button: CapsuleButton | None = None
        self._minimize_button: QToolButton | None = None
        self._maximize_button: QToolButton | None = None
        self._close_button: QToolButton | None = None
        self._analysis_ready_for_tabs = False
        self._render_backend: RenderBackendProbe = probe_render_backend()
        self._enforce_hardware_rendering = should_enforce_hardware_rendering()
        self._prefer_gpu = self._settings.load_flag("window", "prefer_gpu", True)
        self._renderer_warning_shown = False
        self._shared_viewport_mode = ViewportMode.SOLID
        self._shared_detail_level = DEFAULT_DETAIL_LEVEL
        self._shared_point_size = 8
        self._shared_baseline_pose_visible = True
        self._shared_standing_pose_visible = False
        self._shared_selected_ids: tuple[str, ...] = ()
        self._shared_active_id: str | None = None
        self._shared_reference_id: str | None = None
        self._shared_isolate_selection = False
        self._transient_status_stack: list[str] = []
        self._analysis_status_override: tuple[str, bool] | None = None
        self._publish_render_backend_state()

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("SpineLab 0.2")
        self.resize(1680, 1080)

        from spinelab.ui.platform.win32_dwm import enable_mica

        enable_mica(int(self.winId()))

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._build_header())

        self._stack = QStackedWidget()
        stack_layout = self._stack.layout()
        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackingMode.StackOne)
        central_layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self._create_workspaces()
        geometry = self._settings.load_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
            self._clamp_restored_window_geometry()
        self.set_workspace("import")
        self._refresh_runtime_status()
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _build_header(self) -> QFrame:
        header = TitleBarFrame(self)
        header.setObjectName("HeaderBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(
            GEOMETRY.unit * 2,
            GEOMETRY.header_padding_y,
            GEOMETRY.unit * 2,
            GEOMETRY.header_padding_y,
        )
        layout.setSpacing(GEOMETRY.unit - 2)

        logo = QLabel("SpineLab")
        logo.setObjectName("HeaderBrandLabel")
        apply_text_role(logo, "header-brand")
        logo.setFixedHeight(GEOMETRY.header_control_height)
        logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        for menu_name in ["File", "Edit", "View", "Tools", "Window", "Help"]:
            menu_button = MenuButton(menu_name)
            menu_button.setFixedHeight(GEOMETRY.header_control_height)
            menu_button.setMenu(self._create_menu(menu_name))
            layout.addWidget(menu_button)

        layout.addSpacing(GEOMETRY.unit * 2)
        for workspace_id, label in [
            ("import", "Import"),
            ("measurement", "Measurement"),
            ("report", "Report"),
        ]:
            tab_button = CapsuleButton(label, checkable=True)
            tab_button.setObjectName("HeaderWorkspaceTabButton")
            tab_button.setFixedHeight(GEOMETRY.header_control_height)
            apply_text_role(tab_button, "header-text")
            tab_button.clicked.connect(
                lambda checked=False, key=workspace_id: self.set_workspace(key)
            )
            self._workspace_buttons[workspace_id] = tab_button
            layout.addWidget(tab_button)

        layout.addStretch(1)
        self._header_status = HeaderStatusStrip()
        self._header_status.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        layout.addWidget(self._header_status, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._render_mode_button = CapsuleButton("GPU")
        self._render_mode_button.setObjectName("HeaderRendererButton")
        self._render_mode_button.setFixedHeight(GEOMETRY.header_control_height)
        self._render_mode_button.clicked.connect(self._cycle_renderer_mode)
        layout.addWidget(self._render_mode_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._case_label = QLabel()
        self._case_label.setObjectName("HeaderCaseLabel")
        apply_text_role(self._case_label, "header-meta")
        self._case_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._case_label)
        layout.addSpacing(GEOMETRY.unit)
        self._minimize_button = self._build_window_control_button(
            "HeaderMinimizeButton",
            "–",
            "Minimize",
            self.showMinimized,
        )
        layout.addWidget(self._minimize_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._maximize_button = self._build_window_control_button(
            "HeaderMaximizeButton",
            "□",
            "Maximize",
            self._toggle_maximize_restore,
        )
        layout.addWidget(self._maximize_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._close_button = self._build_window_control_button(
            "HeaderCloseButton",
            "×",
            "Close",
            self.close,
        )
        layout.addWidget(self._close_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._refresh_case_label()
        self._refresh_renderer_button()
        self._refresh_window_control_buttons()
        return header

    def _build_window_control_button(
        self,
        object_name: str,
        text: str,
        tooltip: str,
        callback: Callable[[], object],
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName(object_name)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(True)
        button.setFixedSize(
            GEOMETRY.header_control_height + GEOMETRY.unit,
            GEOMETRY.header_control_height,
        )
        apply_text_role(button, "header-text")
        button.clicked.connect(callback)
        return button

    def _create_menu(self, name: str) -> QMenu:
        menu = QMenu(self)
        if name == "File":
            new_case = QAction("New Case", self)
            new_case.triggered.connect(self._new_blank_case)
            open_case = QAction("Open Case...", self)
            open_case.triggered.connect(self._open_case_dialog)
            open_legacy_case = QAction("Open Legacy Case Folder...", self)
            open_legacy_case.triggered.connect(self._open_legacy_case_dialog)
            save_case = QAction("Save Case", self)
            save_case.triggered.connect(self._save_case)
            save_case_as = QAction("Save Case As...", self)
            save_case_as.triggered.connect(self._save_case_as)
            export_package_folder = QAction("Export Package Folder...", self)
            export_package_folder.triggered.connect(self._export_package_folder)
            export_assets = QAction("Export Assets...", self)
            export_assets.triggered.connect(self._export_assets)
            ensure_demo = QAction("Load Demo Case", self)
            ensure_demo.triggered.connect(self._ensure_demo_case)
            clear_cases = QAction("Clear Cases", self)
            clear_cases.triggered.connect(self._clear_cases_from_explorer)
            make_testing_drrs = QAction("Make DRRs for Testing", self)
            make_testing_drrs.triggered.connect(self._make_testing_drrs_for_current_case)
            open_data_root = QAction("Open Data Root", self)
            open_data_root.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(DEFAULT_DATA_ROOT))))
            )
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self.close)
            menu.addAction(new_case)
            menu.addAction(open_case)
            menu.addAction(open_legacy_case)
            menu.addSeparator()
            menu.addAction(save_case)
            menu.addAction(save_case_as)
            menu.addSeparator()
            menu.addAction(export_package_folder)
            menu.addAction(export_assets)
            menu.addSeparator()
            menu.addAction(ensure_demo)
            menu.addAction(clear_cases)
            menu.addAction(make_testing_drrs)
            menu.addAction(open_data_root)
            menu.addSeparator()
            menu.addAction(quit_action)
        elif name == "View":
            for workspace_id, label in [
                ("import", "Import"),
                ("measurement", "Measurement"),
                ("report", "Report"),
            ]:
                action = QAction(label, self)
                action.triggered.connect(
                    lambda checked=False, key=workspace_id: self.set_workspace(key)
                )
                menu.addAction(action)
        elif name == "Tools":
            segmentation_backends = QAction("Segmentation Backends...", self)
            segmentation_backends.triggered.connect(
                self._open_segmentation_backends_dialog
            )
            menu.addAction(segmentation_backends)
        else:
            action = QAction(f"{name} unavailable", self)
            action.setEnabled(False)
            menu.addAction(action)
        return menu

    def _refresh_segmentation_backend_surfaces(self) -> None:
        import_page = self._workspace_pages.get("import")
        refresh_import = getattr(import_page, "_refresh_segmentation_backend_status", None)
        if callable(refresh_import):
            refresh_import()
        measurement_page = self._workspace_pages.get("measurement")
        refresh_measurement = getattr(
            measurement_page,
            "refresh_backend_provenance",
            None,
        )
        if callable(refresh_measurement):
            refresh_measurement()
        report_page = self._workspace_pages.get("report")
        refresh_report = getattr(report_page, "refresh_backend_provenance", None)
        if callable(refresh_report):
            refresh_report()

    def _open_segmentation_backends_dialog(self) -> None:
        from spinelab.app.segmentation_backends_dialog import SegmentationBackendsDialog

        dialog = SegmentationBackendsDialog(
            store=self._store,
            settings=self._settings,
            parent=self,
        )
        dialog.exec()
        self._refresh_segmentation_backend_surfaces()

    def _default_case_dialog_dir(self) -> Path:
        return (
            self._settings.load_last_case_directory()
            or (Path(DEFAULT_DATA_ROOT) / "cases")
        )

    def _set_active_session(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
        *,
        analysis_ready: bool = False,
        workspace_id: str = "import",
    ) -> None:
        self._active_session = session
        self._store.activate_session(session)
        self._manifest = manifest
        self._analysis_ready_for_tabs = analysis_ready
        self._reset_shared_selection_state()
        self._create_workspaces()
        self._refresh_case_label()
        self._refresh_runtime_status()
        self.set_workspace(workspace_id)

    def _maybe_discard_or_save_session(self) -> bool:
        if self._has_active_analysis():
            return self._confirm_cancel_processing_and_discard()
        if self._active_session is None or not self._active_session.dirty:
            return True
        response = QMessageBox.question(
            self,
            "Unsaved Case",
            "Save changes to the current case before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if response == QMessageBox.StandardButton.Cancel:
            return False
        if response == QMessageBox.StandardButton.Save:
            saved = self._save_case()
            return bool(saved)
        return True

    def _has_active_analysis(self) -> bool:
        import_page = self._workspace_pages.get("import")
        has_active_analysis = getattr(import_page, "has_active_analysis", None)
        if callable(has_active_analysis):
            return bool(has_active_analysis())
        return False

    def _confirm_cancel_processing_and_discard(self) -> bool:
        prompt = QMessageBox(self)
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setWindowTitle("Analyze Running")
        prompt.setText(
            "Analyze is still running. Cancel processing and discard the current unsaved "
            "case before continuing?"
        )
        discard_button = prompt.addButton(
            "Cancel Processing and Discard",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        prompt.addButton("Keep Working", QMessageBox.ButtonRole.RejectRole)
        prompt.setDefaultButton(discard_button)
        prompt.exec()
        return prompt.clickedButton() is discard_button

    def _destroy_active_session(self) -> None:
        if self._active_session is None:
            return
        self._store.session_store.destroy_session(self._active_session)
        self._store.clear_active_session()
        self._active_session = None

    def _open_case_dialog(self) -> None:
        if not self._maybe_discard_or_save_session():
            return
        default_dir = self._default_case_dialog_dir()
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open SpineLab Case",
            str(default_dir),
            PACKAGE_FILE_FILTER,
        )
        if not file_path:
            return
        self._open_package(Path(file_path))

    def _open_legacy_case_dialog(self) -> None:
        if not self._maybe_discard_or_save_session():
            return
        default_dir = self._default_case_dialog_dir()
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Open Legacy Case Folder",
            str(default_dir),
        )
        if not folder_path:
            return
        case_root = Path(folder_path)
        manifest_path = case_root / "analytics" / "manifest.json"
        if not manifest_path.exists():
            QMessageBox.critical(
                self,
                "Open Legacy Case Folder",
                "The selected folder does not contain analytics/manifest.json.",
            )
            return
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = CaseManifest.from_dict(payload)
            session, manifest = self._legacy_importer.import_case_folder(case_root, manifest)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Open Legacy Case Folder", str(exc))
            return
        old_session = self._active_session
        self._set_active_session(session, manifest)
        self._settings.save_last_case_directory(case_root.parent)
        if old_session is not None:
            self._store.session_store.destroy_session(old_session)

    def _open_package(self, package_path: Path) -> None:
        with self._transient_status(f"Opening {package_path.name}"):
            try:
                session, manifest = self._package_service.open_package(package_path)
            except SpinePackageError as exc:
                QMessageBox.critical(self, "Open Case", str(exc))
                return
            old_session = self._active_session
            self._set_active_session(session, manifest)
            self._settings.add_recent_case_path(package_path)
            self._settings.save_last_case_directory(package_path.parent)
            import_page = self._workspace_pages.get("import")
            refresh_tree = getattr(import_page, "_refresh_case_tree", None)
            if callable(refresh_tree):
                refresh_tree()
            if old_session is not None:
                self._store.session_store.destroy_session(old_session)

    def _save_case(self) -> Path | None:
        if self._active_session is None:
            return None
        if self._active_session.saved_package_path is None:
            return self._save_case_as()
        try:
            saved_path = self._package_service.save_package(
                self._active_session,
                self._manifest,
                self._active_session.saved_package_path,
            )
        except SpinePackageError as exc:
            QMessageBox.critical(self, "Save Case", str(exc))
            return None
        self._settings.add_recent_case_path(saved_path)
        self._settings.save_last_case_directory(saved_path.parent)
        self._refresh_case_label()
        import_page = self._workspace_pages.get("import")
        refresh_tree = getattr(import_page, "_refresh_case_tree", None)
        if callable(refresh_tree):
            refresh_tree()
        return saved_path

    def _save_case_as(self) -> Path | None:
        if self._active_session is None:
            return None
        default_dir = self._default_case_dialog_dir()
        suggested_name = f"{self._manifest.case_id}.spine"
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save SpineLab Case As",
            str(default_dir / suggested_name),
            PACKAGE_FILE_FILTER,
        )
        if not file_path:
            return None
        target_path = Path(file_path)
        if target_path.suffix.lower() != ".spine":
            target_path = target_path.with_suffix(".spine")
        current_case_id = self._manifest.case_id
        self._manifest.case_id = self._store.create_blank_case().case_id
        if self._active_session is not None:
            self._active_session.sync_case_id(self._manifest.case_id)
        try:
            saved_path = self._package_service.save_package(
                self._active_session,
                self._manifest,
                target_path,
            )
        except SpinePackageError as exc:
            self._manifest.case_id = current_case_id
            if self._active_session is not None:
                self._active_session.sync_case_id(current_case_id)
            QMessageBox.critical(self, "Save Case As", str(exc))
            return None
        self._settings.add_recent_case_path(saved_path)
        self._settings.save_last_case_directory(saved_path.parent)
        self._refresh_case_label()
        import_page = self._workspace_pages.get("import")
        refresh_tree = getattr(import_page, "_refresh_case_tree", None)
        if callable(refresh_tree):
            refresh_tree()
        return saved_path

    def _export_package_folder(self) -> None:
        if self._active_session is None:
            return
        default_dir = self._default_case_dialog_dir()
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Export Package Folder",
            str(default_dir),
        )
        if not output_dir:
            return
        try:
            export_root = self._package_service.export_package_folder(
                self._active_session,
                self._manifest,
                Path(output_dir),
            )
        except SpinePackageError as exc:
            QMessageBox.critical(self, "Export Package Folder", str(exc))
            return
        QMessageBox.information(
            self,
            "Export Package Folder",
            f"Exported case folder to:\n\n{export_root}",
        )

    def _export_assets(self) -> None:
        if self._active_session is None:
            return
        groups = self._package_service.asset_groups(self._active_session, self._manifest)
        button_map = {
            "Original DICOM": "dicom",
            "Standardized CT": "ct",
            "DRRs": "drr",
            "Meshes": "mesh",
            "Analytics": "analytics",
            "Reports": "reports",
            "All Assets": "all",
        }
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Export Assets")
        prompt.setText("Choose which asset group to export.")
        created_buttons = {
            label: prompt.addButton(label, QMessageBox.ButtonRole.ActionRole)
            for label in button_map
        }
        prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.exec()
        clicked = prompt.clickedButton()
        selected_group = next(
            (group for label, group in button_map.items() if created_buttons[label] is clicked),
            None,
        )
        if selected_group is None:
            return
        asset_ids = groups.get(selected_group, [])
        if not asset_ids:
            QMessageBox.information(
                self,
                "Export Assets",
                "The current case does not contain assets in that group.",
            )
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose asset export folder",
            str(self._default_case_dialog_dir()),
        )
        if not output_dir:
            return
        exported = self._package_service.export_assets(
            self._active_session,
            self._manifest,
            asset_ids,
            Path(output_dir),
        )
        QMessageBox.information(
            self,
            "Export Assets",
            f"Exported {len(exported)} file(s) to:\n\n{output_dir}",
        )

    def _ensure_demo_case(self) -> None:
        if not self._maybe_discard_or_save_session():
            return
        with self._transient_status("Loading demo case"):
            demo_manifest = self._store.ensure_demo_case()
            demo_root = self._store.case_dir(demo_manifest.case_id)
            session, manifest = self._legacy_importer.import_case_folder(demo_root, demo_manifest)
            old_session = self._active_session
            self._set_active_session(session, manifest)
            if old_session is not None:
                self._store.session_store.destroy_session(old_session)

    def _new_blank_case(self) -> None:
        if not self._maybe_discard_or_save_session():
            return
        with self._transient_status("Creating blank case"):
            session = self._store.session_store.create_blank_session(
                manifest=self._store.create_blank_case()
            )
            manifest = self._store.session_store.load_runtime_manifest(session)
            old_session = self._active_session
            self._set_active_session(session, manifest)
            if old_session is not None:
                self._store.session_store.destroy_session(old_session)

    def _clear_cases_from_explorer(self) -> None:
        response = QMessageBox.question(
            self,
            "Clear Cases from Explorer",
            (
                "This removes saved case packages from Patient Explorer without deleting "
                "anything from disk.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        with self._transient_status("Clearing cases from explorer"):
            self._settings.save_recent_case_paths([])
            self._create_workspaces()
            self._refresh_runtime_status()
            self.set_workspace("import")

    def _make_testing_drrs_for_current_case(self) -> None:
        response = QMessageBox.question(
            self,
            "Make DRRs for Testing",
            (
                "This generates temporary bilateral AP/LAT testing projections from the current "
                "case CT and assigns them as the current standing inputs.\n\n"
                "These are not calibrated NanoDRR outputs.\n\nContinue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        with self._transient_status("Generating testing DRRs"):
            try:
                generate_testing_drrs(self._store, self._manifest)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Make DRRs for Testing",
                    f"Unable to generate testing DRRs.\n\n{exc}",
                )
                return
            current_workspace = self._current_workspace_id() or "import"
            self._create_workspaces()
            self._refresh_case_label()
            self._refresh_runtime_status()
            self.set_workspace(current_workspace)

    def _current_workspace_id(self) -> str | None:
        current_page = self._stack.currentWidget()
        for workspace_id, page in self._workspace_pages.items():
            if page is current_page:
                return workspace_id
        return None

    def _create_workspaces(self) -> None:
        if (
            self._active_session is not None
            and self._active_session.case_id != self._manifest.case_id
        ):
            self._active_session.sync_case_id(self._manifest.case_id)
            self._store.activate_session(self._active_session)
            self._store.session_store.write_runtime_manifest(self._active_session, self._manifest)
            self._active_session.mark_clean()
        self._dispose_workspaces()
        self._workspace_pages.clear()
        self._workspace_factories = {
            "import": self._create_import_workspace,
            "measurement": self._create_measurement_workspace,
            "report": self._create_report_workspace,
        }
        self._ensure_workspace("import")
        if self._analysis_ready_for_tabs:
            self._ensure_workspace("measurement")
            self._ensure_workspace("report")
        self._prime_workspace_shell_sidebar_widths()

    def _create_import_workspace(self) -> QWidget:
        from spinelab.workspaces.import_workspace import ImportWorkspace

        return ImportWorkspace(
            self._manifest,
            self._settings,
            self._store,
            self._load_case,
            pipeline=self._pipeline,
            on_manifest_updated=self._handle_manifest_updated,
            on_analysis_status_changed=self._handle_analysis_status_changed,
        )

    def _create_measurement_workspace(self) -> QWidget:
        from spinelab.workspaces.measurement_workspace import MeasurementWorkspace

        return MeasurementWorkspace(
            self._manifest,
            self._settings,
            store=self._store,
            render_backend=self._render_backend,
            interactive_3d_enabled=self._interactive_3d_enabled(),
            analysis_ready=self._analysis_ready_for_tabs,
            initial_viewport_mode=self._shared_viewport_mode,
            initial_detail_level=self._shared_detail_level,
            initial_point_size=self._shared_point_size,
            initial_baseline_pose_visible=self._shared_baseline_pose_visible,
            initial_standing_pose_visible=self._shared_standing_pose_visible,
            initial_selected_ids=self._shared_selected_ids,
            initial_active_id=self._shared_active_id,
            initial_reference_id=self._shared_reference_id,
            initial_isolate_selection=self._shared_isolate_selection,
            on_display_state_changed=lambda mode,
            detail_level,
            point_size,
            baseline_visible,
            standing_visible: (
                self._handle_shared_display_state_changed(
                    "measurement",
                    mode,
                    detail_level,
                    point_size,
                    baseline_visible,
                    standing_visible,
                )
            ),
            on_selection_state_changed=lambda selected_ids,
            active_id,
            reference_id,
            isolate_selection: (
                self._handle_shared_selection_state_changed(
                    "measurement",
                    selected_ids,
                    active_id,
                    reference_id,
                    isolate_selection,
                )
            ),
        )

    def _create_report_workspace(self) -> QWidget:
        from spinelab.workspaces.report_workspace import ReportWorkspace

        return ReportWorkspace(
            self._manifest,
            self._settings,
            store=self._store,
            render_backend=self._render_backend,
            interactive_3d_enabled=self._interactive_3d_enabled(),
            analysis_ready=self._analysis_ready_for_tabs,
            initial_viewport_mode=self._shared_viewport_mode,
            initial_detail_level=self._shared_detail_level,
            initial_point_size=self._shared_point_size,
            initial_baseline_pose_visible=self._shared_baseline_pose_visible,
            initial_standing_pose_visible=self._shared_standing_pose_visible,
            initial_selected_ids=self._shared_selected_ids,
            initial_active_id=self._shared_active_id,
            initial_reference_id=self._shared_reference_id,
            on_selection_state_changed=lambda selected_ids,
            active_id,
            reference_id,
            isolate_selection: (
                self._handle_shared_selection_state_changed(
                    "report",
                    selected_ids,
                    active_id,
                    reference_id,
                    isolate_selection,
                )
            ),
        )

    def _ensure_workspace(self, workspace_id: str) -> QWidget:
        page = self._workspace_pages.get(workspace_id)
        if page is not None:
            return page

        with self._transient_status(f"Loading {workspace_id.title()} workspace"):
            page = self._workspace_factories[workspace_id]()
        self._workspace_pages[workspace_id] = page

        insert_index = self._stack.count()
        workspace_position = WORKSPACE_ORDER.index(workspace_id)
        for candidate_id in WORKSPACE_ORDER[workspace_position + 1 :]:
            candidate_page = self._workspace_pages.get(candidate_id)
            if candidate_page is None:
                continue
            insert_index = self._stack.indexOf(candidate_page)
            break
        self._stack.insertWidget(insert_index, page)
        page.setVisible(False)
        page.setUpdatesEnabled(False)
        sidebar_widths_changed = getattr(page, "sidebar_widths_changed", None)
        if sidebar_widths_changed is not None and hasattr(sidebar_widths_changed, "connect"):
            sidebar_widths_changed.connect(
                lambda left_width, right_width, key=workspace_id: (
                    self._handle_workspace_sidebar_widths_changed(
                        key,
                        left_width,
                        right_width,
                    )
                )
            )
        self._prime_workspace_shell_sidebar_widths()
        return page

    def _load_case(self, case_ref: str) -> None:
        if not self._maybe_discard_or_save_session():
            return
        with self._transient_status(f"Loading case {case_ref}"):
            package_path = Path(case_ref)
            if package_path.exists() and package_path.suffix.lower() == ".spine":
                self._open_package(package_path)
                return

    def _handle_manifest_updated(self, manifest: CaseManifest) -> None:
        with self._transient_status("Refreshing workspaces"):
            self._manifest = manifest
            if self._active_session is not None:
                self._active_session.sync_case_id(manifest.case_id)
            self._analysis_ready_for_tabs = True
            self._reset_shared_selection_state()
            self._create_workspaces()
            self._refresh_case_label()
            self._refresh_runtime_status()
            self.set_workspace("measurement")

    def _refresh_case_label(self) -> None:
        if self._case_label is not None:
            case_name = self._manifest.patient_name or "Untitled Case"
            dirty_suffix = (
                " *"
                if self._active_session is not None and self._active_session.dirty
                else ""
            )
            self._case_label.setText(f"{case_name} · {self._manifest.case_id}{dirty_suffix}")

    def _refresh_runtime_status(self) -> None:
        if self._header_status is None:
            return
        if self._analysis_status_override is not None:
            text, active = self._analysis_status_override
            self._header_status.set_status(text, active=active)
            self._sync_header_progress_width()
            self._refresh_renderer_button()
            return
        status_text, active = summarize_pipeline_status(self._manifest)
        self._header_status.set_status(status_text, active=active)
        self._sync_header_progress_width()
        self._refresh_renderer_button()

    def _handle_analysis_status_changed(
        self, text: str, active: bool, percent: float = 0.0,
    ) -> None:
        del percent
        if text:
            self._analysis_status_override = (text, active)
            if self._header_status is not None:
                self._header_status.set_status(text, active=active)
                self._refresh_renderer_button()
            return
        self._analysis_status_override = None
        if self._header_status is not None:
            self._header_status.set_progress(0.0, active=False)
            self._header_status.set_eta("")
        self._refresh_runtime_status()

    def _prime_workspace_shell_sidebar_widths(self) -> None:
        saved_left_width, saved_right_width = self._settings.load_shell_sidebar_widths()
        sidebar_targets = [
            max(saved_left_width or 0, saved_right_width or 0),
            GEOMETRY.sidebar_min,
            GEOMETRY.inspector_min,
        ]
        for page in self._workspace_pages.values():
            targets = getattr(page, "shell_sidebar_width_targets", None)
            if not callable(targets):
                continue
            left_target, right_target = targets()
            if left_target is not None:
                sidebar_targets.append(left_target)
            if right_target is not None:
                sidebar_targets.append(right_target)
        shared_width = max(sidebar_targets)
        self._settings.save_shell_sidebar_widths(shared_width, shared_width)

    def set_workspace(self, workspace_id: str) -> None:
        with self._transient_status(f"Opening {workspace_id.title()} workspace"):
            page = self._ensure_workspace(workspace_id)
            current_page = self._stack.currentWidget()
            if current_page is not None and current_page is not page:
                deactivate_workspace = getattr(current_page, "on_workspace_deactivated", None)
                if callable(deactivate_workspace):
                    deactivate_workspace()
            self._stack.setCurrentWidget(page)
            self._update_workspace_visibility(workspace_id)
            sync_layout = getattr(page, "sync_shell_layout", None)
            if callable(sync_layout):
                sync_layout()
            activate_workspace = getattr(page, "on_workspace_activated", None)
            if callable(activate_workspace):
                activate_workspace()
            self._sync_header_progress_width(page)
            for key, button in self._workspace_buttons.items():
                button.setChecked(key == workspace_id)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
            self._settings.save_current_workspace(workspace_id)

    def _update_workspace_visibility(self, active_workspace_id: str) -> None:
        active_page = self._workspace_pages.get(active_workspace_id)
        for workspace_id, page in self._workspace_pages.items():
            visible = workspace_id == active_workspace_id
            page.setVisible(visible)
            page.setUpdatesEnabled(visible)
            if not visible:
                continue
            try:
                page.raise_()
            except Exception:
                pass
        if active_page is not None:
            self._stack.setCurrentWidget(active_page)

    def _handle_workspace_sidebar_widths_changed(
        self,
        workspace_id: str,
        left_width: int,
        right_width: int,
    ) -> None:
        del right_width
        if self._header_status is None:
            return
        active_page = self._stack.currentWidget()
        if active_page is not self._workspace_pages.get(workspace_id):
            return
        self._header_status.set_progress_target_width(left_width)

    def _sync_header_progress_width(self, page: QWidget | None = None) -> None:
        if self._header_status is None:
            return
        active_page = page if page is not None else self._stack.currentWidget()
        if active_page is None:
            return
        outer_splitter = getattr(active_page, "outer_splitter", None)
        if outer_splitter is None or not hasattr(outer_splitter, "sizes"):
            return
        sizes = outer_splitter.sizes()
        left_width = sizes[0] if len(sizes) >= 1 else 0
        self._header_status.set_progress_target_width(left_width)

    def _reset_shared_selection_state(self) -> None:
        self._shared_selected_ids = ()
        self._shared_active_id = None
        self._shared_reference_id = None
        self._shared_isolate_selection = False

    def _handle_shared_display_state_changed(
        self,
        source_workspace_id: str,
        mode: ViewportMode,
        detail_level: int,
        point_size: int,
        baseline_visible: bool,
        standing_visible: bool,
    ) -> None:
        self._shared_viewport_mode = mode
        self._shared_detail_level = detail_level
        self._shared_point_size = point_size
        self._shared_baseline_pose_visible = bool(baseline_visible)
        self._shared_standing_pose_visible = bool(standing_visible)
        for workspace_id in ("measurement", "report"):
            if workspace_id == source_workspace_id:
                continue
            page = self._workspace_pages.get(workspace_id)
            apply_state = getattr(page, "apply_shared_display_state", None)
            if callable(apply_state):
                apply_state(
                    mode=self._shared_viewport_mode,
                    detail_level=self._shared_detail_level,
                    point_size=self._shared_point_size,
                    baseline_visible=self._shared_baseline_pose_visible,
                    standing_visible=self._shared_standing_pose_visible,
                )

    def _handle_shared_selection_state_changed(
        self,
        source_workspace_id: str,
        selected_ids: tuple[str, ...],
        active_id: str | None,
        reference_id: str | None,
        isolate_selection: bool,
    ) -> None:
        self._shared_selected_ids = selected_ids
        self._shared_active_id = active_id
        self._shared_reference_id = reference_id
        self._shared_isolate_selection = isolate_selection
        for workspace_id in ("measurement", "report"):
            if workspace_id == source_workspace_id:
                continue
            page = self._workspace_pages.get(workspace_id)
            apply_state = getattr(page, "apply_shared_selection_state", None)
            if callable(apply_state):
                apply_state(
                    selected_ids=self._shared_selected_ids,
                    active_id=self._shared_active_id,
                    reference_id=self._shared_reference_id,
                    isolate_selection=self._shared_isolate_selection,
                )

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._maybe_discard_or_save_session():
            event.ignore()
            return
        self._dispose_workspaces()
        self._terminate_backend_processes()
        self._settings.save_window_geometry(self.saveGeometry())
        self._destroy_active_session()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._renderer_warning_shown:
            return
        if not self._enforce_hardware_rendering or self._render_backend.hardware_ok:
            return
        QTimer.singleShot(0, self._show_render_backend_warning)

    def _dispose_workspaces(self) -> None:
        while self._stack.count():
            widget = self._stack.widget(0)
            if widget is None:
                continue
            dispose_workspace = getattr(widget, "dispose", None)
            if callable(dispose_workspace):
                dispose_workspace()
            self._stack.removeWidget(widget)
            widget.close()
            widget.deleteLater()

    def _terminate_backend_processes(self) -> None:
        terminate_tracked_segmentation_processes(timeout_seconds=5.0)

    def _clamp_restored_window_geometry(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        clamped = clamp_rect_to_bounds(self.geometry(), screen.availableGeometry())
        if clamped != self.geometry():
            self.setGeometry(clamped)
        self._settings.save_window_geometry(self.saveGeometry())

    def _interactive_3d_enabled(self) -> bool:
        return not self._enforce_hardware_rendering or self._render_backend.hardware_ok

    def _show_render_backend_warning(self) -> None:
        if self._renderer_warning_shown:
            return
        self._renderer_warning_shown = True
        QMessageBox.warning(
            self,
            "Interactive 3D Disabled",
            self._render_backend.warning_text(),
        )

    def _publish_render_backend_state(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setProperty("renderBackendClassification", self._render_backend.classification)
        app.setProperty("renderBackendHardwareOk", self._render_backend.hardware_ok)
        app.setProperty("renderBackendRenderer", self._render_backend.opengl_renderer)
        app.setProperty("renderTargetPreference", "gpu" if self._prefer_gpu else "cpu")

    def _cycle_renderer_mode(self) -> None:
        if self._render_backend.hardware_ok:
            self._prefer_gpu = not self._prefer_gpu
        else:
            self._prefer_gpu = False
        self._settings.save_flag("window", "prefer_gpu", self._prefer_gpu)
        self._publish_render_backend_state()
        self._refresh_renderer_button()

    def _refresh_renderer_button(self) -> None:
        if self._render_mode_button is None:
            return
        if self._render_backend.hardware_ok and self._prefer_gpu:
            text = "GPU"
            variant = "success"
            detected_renderer = (
                self._render_backend.opengl_renderer
                or self._render_backend.opengl_vendor
                or "Hardware OpenGL"
            )
            tooltip = (
                "Hardware renderer detected and GPU mode is preferred.\n"
                f"Detected renderer: {detected_renderer}"
            )
        elif self._render_backend.hardware_ok:
            text = "CPU"
            variant = "danger"
            tooltip = (
                "CPU mode selected manually.\n"
                "The detected hardware renderer remains available in this session."
            )
        else:
            text = "CPU"
            variant = "danger"
            tooltip = (
                self._render_backend.failure_reason
                or "Hardware GPU rendering is unavailable."
            )
        self._render_mode_button.setText(text)
        self._render_mode_button.setToolTip(tooltip)
        self._render_mode_button.setProperty("variant", variant)
        self._render_mode_button.style().unpolish(self._render_mode_button)
        self._render_mode_button.style().polish(self._render_mode_button)
        self._render_mode_button.update()

    def _start_system_move(self) -> bool:
        window_handle = self.windowHandle()
        if window_handle is None or not hasattr(window_handle, "startSystemMove"):
            return False
        try:
            return bool(window_handle.startSystemMove())
        except Exception:
            return False

    def _toggle_maximize_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._refresh_window_control_buttons()

    def _refresh_window_control_buttons(self) -> None:
        if self._maximize_button is None:
            return
        if self.isMaximized():
            self._maximize_button.setText("❐")
            self._maximize_button.setToolTip("Restore")
        else:
            self._maximize_button.setText("□")
            self._maximize_button.setToolTip("Maximize")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._refresh_window_control_buttons()

    def _push_transient_status(self, text: str) -> None:
        self._transient_status_stack.append(text)
        if self._header_status is not None:
            self._header_status.set_status(text, active=True)
        self._flush_ui_updates()

    def _pop_transient_status(self) -> None:
        if self._transient_status_stack:
            self._transient_status_stack.pop()
        if self._transient_status_stack and self._header_status is not None:
            self._header_status.set_status(self._transient_status_stack[-1], active=True)
        else:
            self._refresh_runtime_status()
        self._flush_ui_updates()

    @contextmanager
    def _transient_status(self, text: str):
        self._push_transient_status(text)
        try:
            yield
        finally:
            self._pop_transient_status()

    def _flush_ui_updates(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
