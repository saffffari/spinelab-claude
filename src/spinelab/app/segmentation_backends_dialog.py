from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spinelab.io import CaseStore
from spinelab.segmentation import (
    InstalledSegmentationBundle,
    SegmentationBundleRegistry,
)
from spinelab.services import SettingsService
from spinelab.ui.theme import GEOMETRY
from spinelab.ui.widgets.chrome import CapsuleButton, apply_text_role


class _BackendCard(QWidget):
    def __init__(
        self,
        bundle: InstalledSegmentationBundle,
        *,
        is_active: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.bundle = bundle
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        layout.setSpacing(GEOMETRY.unit)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_label = QLabel(bundle.display_name)
        apply_text_role(name_label, "body-emphasis")
        info.addWidget(name_label)

        checkpoint = bundle.active_checkpoint()
        detail = f"{bundle.driver_id}  ·  {checkpoint.checkpoint_id}"
        detail_label = QLabel(detail)
        apply_text_role(detail_label, "micro")
        detail_label.setStyleSheet("color: rgba(255,255,255,0.5);")
        info.addWidget(detail_label)
        layout.addLayout(info, stretch=1)

        self._active_badge = QLabel("Active")
        apply_text_role(self._active_badge, "micro")
        self._active_badge.setStyleSheet(
            "color: #22c55e; font-weight: 500; padding: 2px 8px;"
        )
        self._active_badge.setVisible(is_active)
        layout.addWidget(self._active_badge)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_active = is_active
        self._update_style()

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self._active_badge.setVisible(active)
        self._update_style()

    def _update_style(self) -> None:
        border = "1px solid #22c55e" if self._is_active else "1px solid rgba(255,255,255,0.1)"
        bg = "rgba(34,197,94,0.08)" if self._is_active else "transparent"
        self.setStyleSheet(
            f"_BackendCard {{ background: {bg}; border: {border}; border-radius: 8px; }}"
        )


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
        self._cards: list[_BackendCard] = []

        self.setWindowTitle("Segmentation Backends")
        self.resize(480, 0)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(GEOMETRY.unit)

        header = QLabel("Select the active segmentation backend:")
        apply_text_role(header, "body")
        layout.addWidget(header)

        bundles = self._registry.list_bundles()
        active_id = self._registry.resolved_active_bundle_id()

        if not bundles:
            empty = QLabel("No backends installed.")
            apply_text_role(empty, "body")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)
        else:
            for bundle in bundles:
                card = _BackendCard(bundle, is_active=bundle.bundle_id == active_id)
                card.mousePressEvent = lambda _event, b=bundle: self._activate(b.bundle_id)
                layout.addWidget(card)
                self._cards.append(card)

        layout.addSpacing(GEOMETRY.unit)
        close_btn = CapsuleButton("Close", variant="ghost")
        close_btn.clicked.connect(self.accept)
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

    def _activate(self, bundle_id: str) -> None:
        self._registry.set_active_bundle_id(bundle_id)
        for card in self._cards:
            card.set_active(card.bundle.bundle_id == bundle_id)
