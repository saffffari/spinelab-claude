from __future__ import annotations

import subprocess
from dataclasses import dataclass

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spinelab.io import CaseStore
from spinelab.pipeline.backends import BACKEND_ADAPTERS
from spinelab.pipeline.device import choose_runtime_device
from spinelab.segmentation import (
    DEBUG_SEGMENTATION_BUNDLES_ENV_VAR,
    KNOWN_SEGMENTATION_BACKENDS,
    InstalledSegmentationBundle,
    KnownSegmentationBackend,
    SegmentationBundleRegistry,
    debug_segmentation_bundles_enabled,
    identify_known_backend_id,
    install_known_segmentation_backend,
    is_debug_only_bundle_id,
    map_installed_bundles_to_known_backends,
)
from spinelab.services import SettingsService

_ADAPTERS_BY_TOOL = {adapter.spec.tool_name: adapter for adapter in BACKEND_ADAPTERS}


@dataclass(frozen=True, slots=True)
class _BackendRow:
    backend: KnownSegmentationBackend
    bundle: InstalledSegmentationBundle | None
    environment_health: str
    status: str


class SegmentationBackendsDialog(QDialog):
    def __init__(
        self,
        *,
        store: CaseStore,
        settings: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._settings = settings
        self._registry = SegmentationBundleRegistry(store, settings=settings)
        self._rows: list[_BackendRow] = []
        self._table = QTableWidget(0, 7, self)
        self._table.setHorizontalHeaderLabels(
            (
                "Name",
                "Family",
                "Driver",
                "Modality",
                "Checkpoint",
                "Environment",
                "Status",
            )
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._active_label = QLabel("")
        self._status_label = QLabel("")
        self._activate_button = QPushButton("Activate")
        self._install_button = QPushButton("Install / Register")
        self._open_bundle_button = QPushButton("Open Bundle Folder")
        self._refresh_button = QPushButton("Refresh")
        self._close_button = QPushButton("Close")

        self.setWindowTitle("Segmentation Backends")
        self.resize(980, 420)
        self._build_ui()
        self._connect_signals()
        self._reload_rows()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        summary_layout = QGridLayout()
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setHorizontalSpacing(12)
        summary_layout.setVerticalSpacing(6)
        summary_layout.addWidget(QLabel("Active backend"), 0, 0)
        summary_layout.addWidget(self._active_label, 0, 1)
        summary_layout.addWidget(QLabel("Status"), 1, 0)
        self._status_label.setWordWrap(True)
        summary_layout.addWidget(self._status_label, 1, 1)
        layout.addLayout(summary_layout)
        layout.addWidget(self._table, stretch=1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self._activate_button)
        actions.addWidget(self._install_button)
        actions.addWidget(self._open_bundle_button)
        actions.addWidget(self._refresh_button)
        actions.addStretch(1)
        actions.addWidget(self._close_button)
        layout.addLayout(actions)

    def _connect_signals(self) -> None:
        self._activate_button.clicked.connect(self._activate_selected_bundle)
        self._install_button.clicked.connect(self._install_selected_backend)
        self._open_bundle_button.clicked.connect(self._open_selected_bundle_folder)
        self._refresh_button.clicked.connect(self._reload_rows)
        self._close_button.clicked.connect(self.accept)
        self._table.itemSelectionChanged.connect(self._refresh_action_state)

    def _reload_rows(self) -> None:
        installed_bundles = self._registry.list_bundles()
        installed_by_id = map_installed_bundles_to_known_backends(installed_bundles)
        active_bundle_id = self._registry.resolved_active_bundle_id()
        configured_bundle_id = self._registry.active_bundle_id()
        debug_enabled = debug_segmentation_bundles_enabled()
        active_bundle = (
            self._registry.load_bundle(active_bundle_id)
            if active_bundle_id is not None
            else None
        )
        self._rows = []
        for backend in KNOWN_SEGMENTATION_BACKENDS:
            bundle = installed_by_id.get(backend.backend_id)
            self._rows.append(
                _BackendRow(
                    backend=backend,
                    bundle=bundle,
                    environment_health=self._environment_health(backend),
                    status=self._bundle_status(
                        bundle,
                        active_bundle_id=active_bundle_id,
                        configured_bundle_id=configured_bundle_id,
                        debug_enabled=debug_enabled,
                    ),
                )
            )

        self._table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            checkpoint = row.bundle.active_checkpoint().checkpoint_id if row.bundle else "—"
            family = row.bundle.family if row.bundle is not None else row.backend.family
            driver_id = row.bundle.driver_id if row.bundle is not None else row.backend.driver_id
            modality = row.bundle.modality if row.bundle is not None else row.backend.modality
            values = (
                row.bundle.display_name if row.bundle is not None else row.backend.display_name,
                family,
                driver_id,
                modality.upper(),
                checkpoint,
                row.environment_health,
                row.status,
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.backend.backend_id)
                if column_index in {0, 4, 6}:
                    item.setToolTip(value)
                self._table.setItem(row_index, column_index, item)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)
        self._active_label.setText(
            active_bundle.display_name if active_bundle is not None else "None"
        )
        summary = (
            "Install, health-check, and activate the workstation-level segmentation backend "
            "used by Analyze. This remains a dev and evaluation setting, not a case setting."
        )
        if not debug_enabled:
            summary += (
                f" nnU-Net comparison bundles are quarantined unless "
                f"{DEBUG_SEGMENTATION_BUNDLES_ENV_VAR}=1 is set before launch."
            )
        self._status_label.setText(summary)
        active_backend_id = (
            identify_known_backend_id(active_bundle) if active_bundle is not None else None
        )
        if active_backend_id is not None:
            self._select_backend_row(active_backend_id)
        self._refresh_action_state()

    def _selected_row(self) -> _BackendRow | None:
        items = self._table.selectedItems()
        if not items:
            return None
        backend_id = items[0].data(Qt.ItemDataRole.UserRole)
        if not isinstance(backend_id, str):
            return None
        for row in self._rows:
            if row.backend.backend_id == backend_id:
                return row
        return None

    def _select_backend_row(self, backend_id: str) -> None:
        for row_index, row in enumerate(self._rows):
            if row.backend.backend_id == backend_id:
                self._table.selectRow(row_index)
                return

    def _refresh_action_state(self) -> None:
        selected_row = self._selected_row()
        can_open = selected_row is not None and selected_row.bundle is not None
        can_activate = (
            selected_row is not None
            and selected_row.bundle is not None
            and selected_row.bundle.bundle_id != self._registry.resolved_active_bundle_id()
            and (
                debug_segmentation_bundles_enabled()
                or not is_debug_only_bundle_id(selected_row.bundle.bundle_id)
            )
        )
        can_install = selected_row is not None and selected_row.bundle is None
        self._activate_button.setEnabled(can_activate)
        self._install_button.setEnabled(can_install)
        self._open_bundle_button.setEnabled(can_open)

    def _bundle_status(
        self,
        bundle: InstalledSegmentationBundle | None,
        *,
        active_bundle_id: str | None,
        configured_bundle_id: str | None,
        debug_enabled: bool,
    ) -> str:
        if bundle is None:
            return "Not Installed"
        if active_bundle_id is not None and bundle.bundle_id == active_bundle_id:
            if is_debug_only_bundle_id(bundle.bundle_id) and debug_enabled:
                return "Active (Debug)"
            return "Active"
        if is_debug_only_bundle_id(bundle.bundle_id) and not debug_enabled:
            if configured_bundle_id == bundle.bundle_id:
                return "Selected (Debug Only)"
            return "Installed (Debug Only)"
        return "Installed"

    def _environment_health(self, backend: KnownSegmentationBackend) -> str:
        adapter = _ADAPTERS_BY_TOOL.get(backend.driver_id)
        if adapter is None:
            return "Unknown"
        if adapter.spec.required_device.value == "cuda":
            runtime = choose_runtime_device("cuda")
            if runtime.effective_device != "cuda":
                return "CUDA unavailable"
        try:
            completed = subprocess.run(
                adapter.healthcheck_command(),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except OSError as exc:
            return f"Unavailable ({exc})"
        except subprocess.TimeoutExpired:
            return "Healthcheck timed out"
        if completed.returncode == 0:
            return "Ready"
        stderr = (completed.stderr or completed.stdout or "").strip().splitlines()
        if stderr:
            return f"Unavailable ({stderr[-1][:60]})"
        return f"Unavailable (exit {completed.returncode})"

    def _activate_selected_bundle(self) -> None:
        selected_row = self._selected_row()
        if selected_row is None or selected_row.bundle is None:
            return
        self._registry.set_active_bundle_id(selected_row.bundle.bundle_id)
        self._reload_rows()

    def _install_selected_backend(self) -> None:
        selected_row = self._selected_row()
        if selected_row is None or selected_row.bundle is not None:
            return
        try:
            install_known_segmentation_backend(
                store=self._store,
                backend_id=selected_row.backend.backend_id,
                settings=self._settings,
                activate=False,
            )
        except FileExistsError:
            QMessageBox.information(
                self,
                "Install Backend",
                f"{selected_row.backend.display_name} is already installed.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Install Backend", str(exc))
            return
        self._reload_rows()
        self._select_backend_row(selected_row.backend.backend_id)

    def _open_selected_bundle_folder(self) -> None:
        selected_row = self._selected_row()
        if selected_row is None or selected_row.bundle is None:
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(selected_row.bundle.bundle_dir.resolve()))
        )
