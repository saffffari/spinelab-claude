from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pydicom
from pydicom.errors import InvalidDicomError
from PySide6.QtCore import (
    QEasingCurve,
    QMimeData,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QImageReader, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spinelab.io import CaseStore, SpinePackageError, SpinePackageService
from spinelab.models import CaseManifest, StudyAsset
from spinelab.pipeline import (
    AnalysisProgressUpdate,
    PipelineOrchestrator,
    import_review_summary,
    latest_completed_run,
)
from spinelab.segmentation import (
    SegmentationBundleRegistry,
    terminate_tracked_segmentation_processes,
)
from spinelab.segmentation.precision import (
    DEFAULT_PRECISION_TIER,
    PRECISION_TIER_PARAMS,
    InferencePrecisionTier,
)
from spinelab.segmentation_profiles import DEFAULT_SEGMENTATION_PROFILE
from spinelab.services import (
    SettingsService,
    current_qt_platform_name,
    performance_coordinator,
)
from spinelab.ui.svg_icons import build_svg_icon, build_svg_pixmap
from spinelab.ui.theme import (
    GEOMETRY,
    THEME_COLORS,
    concentric_radius,
    qcolor_from_css,
)
from spinelab.ui.widgets import (
    AnalyzeProgressButton,
    CapsuleButton,
    CollapsiblePanelSection,
    NestedBubbleFrame,
    PanelFrame,
    TransparentSplitter,
    TurboModeButton,
    apply_text_role,
    major_button_icon_size,
    schedule_splitter_midpoint,
)
from spinelab.visualization import ImageViewport2D, XrayProjection, ZStackViewport2D
from spinelab.visualization.viewer_2d import (
    SPINELAB_ASSET_MIME,
    describe_display_stack,
    render_empty_placeholder,
    render_loaded_ct_slice,
    render_loaded_xray,
    resolve_slice_sources,
    stack_preview_slice_index,
)
from spinelab.visualization.viewer_3d import DETAIL_PRESET_LEVELS, prewarm_lod_mesh_cache
from spinelab.workspaces.base import WorkspacePage
from spinelab.workspaces.measurement_workspace import models_for_manifest

ROLE_LABELS = {
    "xray_ap": "X-Ray AP",
    "xray_lat": "X-Ray LAT",
    "ct_stack": "CT Stack",
}
COMPARISON_SLOT_LABELS = {
    "primary": "Primary",
    "secondary": "Secondary",
}
ANALYSIS_POSE_MODE_LABELS = {
    "single": "Single Pose",
    "dual": "Dual Pose",
}
COMPARISON_MODALITY_LABELS = {
    "ct": "CT",
    "mri": "MRI",
    "xray": "X-Ray",
}

FILE_DIALOG_FILTER = (
    "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.dcm *.nii "
    "*.nii.gz *.nrrd *.mhd *.mha);;All Files (*.*)"
)
DELETE_ICON_PATH = Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-delete-16.svg"
EMPTY_BUBBLE_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-document-add-danger-16.svg"
)
REPORT_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-textbox-filled-48.svg"
)
IMPORT_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-document-add-48.svg"
)
PATIENT_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-person-circle-16.svg"
)
CASE_IMAGE_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-rectangle-16.svg"
)
COMPARISON_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-table-simple-regular-48.svg"
)
CASE_TREE_REF_ROLE = Qt.ItemDataRole.UserRole
CASE_TREE_HIDDEN_ROLE = Qt.ItemDataRole.UserRole + 1
_PROJECTION_LAT_TOKENS = {"lat", "lateral", "llat", "rlat", "sag", "sagittal"}
_PROJECTION_AP_TOKENS = {"ap", "pa", "frontal", "front", "coronal"}
_DICOM_PROJECTION_FIELDS = (
    "ViewPosition",
    "SeriesDescription",
    "ProtocolName",
    "StudyDescription",
    "PerformedProcedureStepDescription",
    "RequestedProcedureDescription",
    "ImageComments",
)


def format_analysis_progress_status(update: AnalysisProgressUpdate) -> str:
    stage_label = update.stage.value.replace("_", " ").title()
    normalized_status = update.status.strip().lower()
    if normalized_status == "failed":
        return f"Analyze failed: {stage_label}"
    if normalized_status == "running":
        return stage_label
    return stage_label


class AnalyzeCaseThread(QThread):
    progress_changed = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        pipeline: PipelineOrchestrator,
        manifest: CaseManifest,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
    ) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._manifest = manifest
        self._disable_tta = disable_tta
        self._tile_step_size = tile_step_size

    def run(self) -> None:
        try:
            updated_manifest = self._pipeline.submit_case_analysis(
                self._manifest,
                progress_callback=self._handle_progress,
                disable_tta=self._disable_tta,
                tile_step_size=self._tile_step_size,
            )
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            self.failed.emit(str(exc))
            return
        if self.isInterruptionRequested():
            return
        self.completed.emit(updated_manifest)

    def _handle_progress(self, update: AnalysisProgressUpdate) -> None:
        if self.isInterruptionRequested():
            return
        self.progress_changed.emit(update)


class PoseEngineSelectorStrip(QWidget):
    def __init__(
        self,
        primary_button: CapsuleButton,
        secondary_button: CapsuleButton,
    ) -> None:
        super().__init__()
        self.setObjectName("PoseEngineSelectorStrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._mode: str | None = None
        self._split_progress = 0.0
        self._animations_enabled = current_qt_platform_name() not in {"minimal", "offscreen"}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        self._primary_host = QWidget()
        self._primary_host.setObjectName("ComparisonSelectorHost")
        self._primary_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._primary_host.setMinimumWidth(0)
        self._primary_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        primary_layout = QVBoxLayout(self._primary_host)
        primary_layout.setContentsMargins(0, 0, 0, 0)
        primary_layout.setSpacing(0)
        primary_layout.addWidget(primary_button)

        self._secondary_host = QWidget()
        self._secondary_host.setObjectName("ComparisonSelectorHost")
        self._secondary_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._secondary_host.setMinimumWidth(0)
        self._secondary_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        secondary_layout = QVBoxLayout(self._secondary_host)
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        secondary_layout.setSpacing(0)
        secondary_layout.addWidget(secondary_button)

        self._secondary_opacity = QGraphicsOpacityEffect(self._secondary_host)
        self._secondary_host.setGraphicsEffect(self._secondary_opacity)

        layout.addWidget(self._primary_host, stretch=1)
        layout.addWidget(self._secondary_host, stretch=1)

        self._height_animation = QVariantAnimation(self)
        self._height_animation.setDuration(220)
        self._height_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._height_animation.valueChanged.connect(self._handle_height_value_changed)

        self._split_animation = QVariantAnimation(self)
        self._split_animation.setDuration(220)
        self._split_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._split_animation.valueChanged.connect(self._handle_split_value_changed)
        self._split_animation.finished.connect(self._handle_split_animation_finished)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_height(0)
        self._apply_split_progress(0.0)
        self._secondary_host.hide()

    def mode(self) -> str | None:
        return self._mode

    def set_mode(self, mode: str | None, *, animated: bool = True) -> None:
        normalized_mode = canonical_analysis_pose_mode(mode)
        target_height = GEOMETRY.major_button_height if normalized_mode is not None else 0
        target_split = 1.0 if normalized_mode == "dual" else 0.0
        should_animate = animated and self._animations_enabled
        self._mode = normalized_mode
        if target_split > 0.0:
            self._secondary_host.show()
        if should_animate:
            self._animate_height(target_height)
            self._animate_split(target_split)
            return
        self._height_animation.stop()
        self._split_animation.stop()
        self._apply_height(target_height)
        self._apply_split_progress(target_split)
        self._handle_split_animation_finished()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_split_progress(self._split_progress)

    def _animate_height(self, target_height: int) -> None:
        start_value = int(self.maximumHeight())
        if start_value == target_height:
            self._apply_height(target_height)
            return
        self._height_animation.stop()
        self._height_animation.setStartValue(start_value)
        self._height_animation.setEndValue(target_height)
        self._height_animation.start()

    def _animate_split(self, target_progress: float) -> None:
        start_value = float(self._split_progress)
        if abs(start_value - target_progress) <= 1e-3:
            self._apply_split_progress(target_progress)
            self._handle_split_animation_finished()
            return
        self._split_animation.stop()
        self._split_animation.setStartValue(start_value)
        self._split_animation.setEndValue(target_progress)
        self._split_animation.start()

    def _handle_height_value_changed(self, value) -> None:
        self._apply_height(int(round(float(value))))

    def _handle_split_value_changed(self, value) -> None:
        self._apply_split_progress(float(value))

    def _handle_split_animation_finished(self) -> None:
        if self._split_progress <= 1e-3:
            self._secondary_host.hide()

    def _apply_height(self, height: int) -> None:
        resolved_height = max(0, int(height))
        self.setMinimumHeight(resolved_height)
        self.setMaximumHeight(resolved_height)
        self.updateGeometry()

    def _apply_split_progress(self, progress: float) -> None:
        self._split_progress = max(0.0, min(1.0, float(progress)))
        available_width = max(0, self.contentsRect().width())
        layout = self.layout()
        gap = layout.spacing() if layout is not None else 0
        split_width = max(0, int(round(max(0, available_width - gap) / 2.0)))
        current_secondary_width = int(round(split_width * self._split_progress))
        self._secondary_host.setMaximumWidth(current_secondary_width)
        self._secondary_opacity.setOpacity(self._split_progress)
        if current_secondary_width > 0:
            self._secondary_host.show()
        self.updateGeometry()


class LODPrewarmThread(QThread):
    def __init__(
        self,
        *,
        models,
        detail_levels: tuple[int, ...],
        max_workers: int,
    ) -> None:
        super().__init__()
        self._models = list(models)
        self._detail_levels = detail_levels
        self._max_workers = max_workers

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        prewarm_lod_mesh_cache(
            self._models,
            detail_levels=self._detail_levels,
            max_workers=self._max_workers,
        )


class SidebarSection(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("PanelInner")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        self._layout.setSpacing(GEOMETRY.inspector_row_gap)

        self.title_label = QLabel(title.upper())
        apply_text_role(self.title_label, "section-label")
        self._layout.addWidget(self.title_label)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(GEOMETRY.inspector_row_gap)
        self._layout.addLayout(self.content_layout)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title.upper())

    def set_title_visible(self, visible: bool) -> None:
        self.title_label.setVisible(visible)
        self._layout.setSpacing(GEOMETRY.unit if visible else 0)


class CaseExplorerTree(QTreeWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CaseExplorerTree")
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setIndentation(GEOMETRY.unit * 2)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)

    def _selection_fill_rect(self, row_rect: QRectF) -> QRectF:
        horizontal_inset = float(GEOMETRY.unit)
        vertical_inset = float(max(1, GEOMETRY.unit // 2))
        return QRectF(
            horizontal_inset,
            row_rect.top() + vertical_inset,
            max(0.0, float(self.viewport().width()) - (horizontal_inset * 2.0)),
            max(0.0, row_rect.height() - (vertical_inset * 2.0)),
        )

    def drawRow(self, painter: QPainter, options: QStyleOptionViewItem, index) -> None:
        option = QStyleOptionViewItem(options)
        selection_model = self.selectionModel()
        is_selected = selection_model.isSelected(index) if selection_model is not None else False
        if is_selected:
            selection_rect = self._selection_fill_rect(QRectF(option.rect))
            if not selection_rect.isEmpty():
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor_from_css(THEME_COLORS.focus_soft))
                radius = selection_rect.height() / 2.0
                painter.drawRoundedRect(selection_rect, radius, radius)
                painter.restore()
            option.state &= ~QStyle.StateFlag.State_Selected
            option.state &= ~QStyle.StateFlag.State_HasFocus
        super().drawRow(painter, option, index)


class ImportDropZone(CapsuleButton):
    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Import or Drag and Drop Images", variant="info", major=True)
        self.setObjectName("ImportDropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(GEOMETRY.major_button_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setIcon(
            build_svg_icon(
                IMPORT_ICON_PATH,
                major_button_icon_size(),
                device_pixel_ratio=self.devicePixelRatioF(),
                tint=THEME_COLORS.info,
            )
        )
        self.setIconSize(major_button_icon_size())
        self.clicked.connect(self.browse_requested.emit)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            local_paths = [
                Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()
            ]
            if local_paths:
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        local_paths = [
            Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()
        ]
        if local_paths:
            self.files_dropped.emit(local_paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class AssetLibraryList(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

    def mimeData(self, items):
        mime_data = super().mimeData(items)
        if mime_data is None:
            mime_data = QMimeData()
        if items:
            asset_id = items[0].data(Qt.ItemDataRole.UserRole)
            if isinstance(asset_id, str):
                mime_data.setData(SPINELAB_ASSET_MIME, asset_id.encode("utf-8"))
        return mime_data


class RoundedImagePreview(QFrame):
    resized = Signal()

    def __init__(self, object_name: str, *, fixed_size: QSize | None = None) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self._pixmap = QPixmap()
        self._fixed_size = QSize(fixed_size) if fixed_size is not None else None
        if fixed_size is None:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.setFixedSize(fixed_size)

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = QPixmap(pixmap)
        self.update()

    def pixmap(self) -> QPixmap | None:
        if self._pixmap.isNull():
            return None
        return QPixmap(self._pixmap)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fixed_size is None and event.size() != event.oldSize():
            self.resized.emit()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        rect = QRectF(self.rect())
        if rect.isEmpty():
            painter.end()
            return

        corner_radius = float(
            concentric_radius(
                GEOMETRY.radius_inner,
                inset=GEOMETRY.inspector_row_gap,
                minimum=GEOMETRY.unit,
            )
        )
        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, corner_radius, corner_radius)
        painter.fillPath(clip_path, qcolor_from_css(THEME_COLORS.viewport_bg))

        if self._pixmap.isNull():
            painter.end()
            return

        if self._fixed_size is None:
            display_size = self._pixmap.deviceIndependentSize()
            fitted_size = display_size.scaled(
                rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        else:
            fitted_size = self._pixmap.deviceIndependentSize()
        target_rect = QRectF(
            rect.center().x() - (fitted_size.width() / 2.0),
            rect.center().y() - (fitted_size.height() / 2.0),
            fitted_size.width(),
            fitted_size.height(),
        )
        source_rect = QRectF(
            0.0,
            0.0,
            float(self._pixmap.width()),
            float(self._pixmap.height()),
        )
        painter.save()
        painter.setClipPath(clip_path)
        painter.drawPixmap(target_rect, self._pixmap, source_rect)
        painter.restore()
        painter.end()


class AssetRowWidget(QFrame):
    def __init__(
        self,
        asset: StudyAsset,
        *,
        delete_enabled: bool,
        on_delete: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setObjectName("AssetRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        layout.setSpacing(GEOMETRY.unit)

        preview_label = RoundedImagePreview(
            "AssetPreview",
            fixed_size=QSize(
                GEOMETRY.asset_thumbnail_size,
                GEOMETRY.asset_thumbnail_size,
            ),
        )
        preview_label.setPixmap(build_asset_thumbnail(asset))
        layout.addWidget(preview_label)
        layout.setAlignment(preview_label, Qt.AlignmentFlag.AlignVCenter)

        meta_panel = QWidget()
        meta_panel.setObjectName("AssetMetaPanel")
        meta_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        meta_panel.setMinimumWidth(0)
        meta_column = QVBoxLayout()
        meta_panel.setLayout(meta_column)
        meta_column.setContentsMargins(0, 0, 0, 0)
        meta_column.setSpacing(GEOMETRY.unit // 2)

        name_label = QLabel(Path(asset.managed_path).name)
        name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name_label.setMinimumWidth(0)
        apply_text_role(name_label, "body-emphasis")
        meta_column.addWidget(name_label)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(GEOMETRY.unit)

        kind_badge = QLabel(asset.label)
        kind_badge.setObjectName("AssetTag")
        kind_badge.setProperty("variant", asset_tag_variant(asset))
        kind_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        kind_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(kind_badge, "micro")
        badge_row.addWidget(kind_badge)

        date_label = QLabel(asset.created_at[:10])
        apply_text_role(date_label, "meta")
        badge_row.addWidget(date_label)
        badge_row.addStretch(1)
        meta_column.addLayout(badge_row)

        if asset.processing_role:
            role_name = ROLE_LABELS.get(asset.processing_role, asset.processing_role)
            assigned = QLabel(f"Assigned to {role_name}")
            assigned.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            assigned.setMinimumWidth(0)
            apply_text_role(assigned, "meta")
            meta_column.addWidget(assigned)

        layout.addWidget(meta_panel, stretch=1)
        layout.setAlignment(meta_panel, Qt.AlignmentFlag.AlignVCenter)

        delete_button = QToolButton()
        delete_button.setObjectName("AssetDeleteButton")
        delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_button.setAutoRaise(True)
        delete_button.setToolTip("Delete image")
        delete_button.setAccessibleName("Delete image")
        delete_button.setFixedSize(GEOMETRY.control_height_md, GEOMETRY.control_height_md)
        delete_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        delete_button.setIcon(
            build_svg_icon(
                DELETE_ICON_PATH,
                QSize(16, 16),
                device_pixel_ratio=self.devicePixelRatioF(),
                tint=THEME_COLORS.danger,
            )
        )
        delete_button.setIconSize(QSize(16, 16))
        delete_button.setEnabled(delete_enabled)
        delete_button.clicked.connect(on_delete)

        action_slot = QWidget()
        action_slot.setObjectName("AssetActionSlot")
        action_slot.setFixedWidth(GEOMETRY.control_height_md)
        action_slot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        action_layout = QVBoxLayout(action_slot)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(0)
        action_layout.addStretch(1)
        action_layout.addWidget(
            delete_button,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        action_layout.addStretch(1)

        layout.addWidget(action_slot)
        layout.setAlignment(
            action_slot,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )


class InspectorInfoRow(QFrame):
    def __init__(
        self,
        icon: QStyle.StandardPixmap,
        title: str,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__()
        del icon
        self.setObjectName("InspectorInfoRow")
        row_spacing = 0 if compact else GEOMETRY.inspector_row_gap
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(row_spacing)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(row_spacing)

        self.title_label = QLabel(title)
        apply_text_role(self.title_label, "meta")
        text_column.addWidget(self.title_label)

        self.value_label = QLabel("Unassigned")
        self.value_label.setWordWrap(True)
        apply_text_role(self.value_label, "body-emphasis")
        text_column.addWidget(self.value_label)

        layout.addLayout(text_column, stretch=1)


class InspectorSummaryCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("InspectorSummaryCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        layout.setSpacing(GEOMETRY.inspector_gap)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(GEOMETRY.inspector_row_gap)

        kicker = QLabel(title.upper())
        kicker.setObjectName("InspectorSummaryKicker")
        apply_text_role(kicker, "micro")
        text_column.addWidget(kicker)

        self.value_label = QLabel("")
        self.value_label.setWordWrap(True)
        apply_text_role(self.value_label, "body")
        text_column.addWidget(self.value_label)

        layout.addLayout(text_column, stretch=1)

        chevron = QLabel("⌄")
        chevron.setObjectName("InspectorSummaryChevron")
        apply_text_role(chevron, "meta")
        layout.addWidget(chevron)
        layout.setAlignment(
            chevron,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )


class ImportWorkspace(WorkspacePage):
    def __init__(
        self,
        manifest: CaseManifest,
        settings: SettingsService,
        store: CaseStore,
        on_case_selected: Callable[[str], None],
        *,
        pipeline: PipelineOrchestrator | None = None,
        on_manifest_updated: Callable[[CaseManifest], None] | None = None,
        on_analysis_status_changed: Callable[[str, bool, float], None] | None = None,
    ) -> None:
        self._manifest = manifest
        self._workspace_settings = settings
        self._store = store
        self._package_service = SpinePackageService(self._store.session_store)
        self._performance_coordinator = performance_coordinator(self._workspace_settings)
        self._on_case_selected = on_case_selected
        self._pipeline = pipeline or PipelineOrchestrator(store, settings=self._workspace_settings)
        self._on_manifest_updated = on_manifest_updated
        self._on_analysis_status_changed = on_analysis_status_changed
        self._inspected_role = "xray_ap"
        self._analysis_thread: AnalyzeCaseThread | None = None
        self._analysis_failed = False
        self._lod_prewarm_thread: LODPrewarmThread | None = None
        self._analysis_progress_percent = 0.0

        self._cases_tree = CaseExplorerTree()
        self._import_drop_zone = ImportDropZone()
        self._asset_list = AssetLibraryList()
        self._patient_value_labels: dict[str, QLabel] = {}
        self._history_section = SidebarSection("Procedure History")
        self._images_section = SidebarSection("Images (0)")
        self._images_section_container: CollapsiblePanelSection | None = None
        self._left_action_card: QFrame | None = None

        self._xray_ap_viewport = ImageViewport2D("AP", XrayProjection.AP)
        self._xray_lat_viewport = ImageViewport2D("Lat", XrayProjection.LAT)
        self._ct_viewport = ZStackViewport2D("CT", use_external_slice_toolbar=True)

        self._preview_label = RoundedImagePreview("InspectorPreviewImage")
        self._viewport_value_label = QLabel("AP")
        self._empty_state_bubble = QLabel()
        self._analysis_status_card = InspectorSummaryCard("Analysis Status")
        self._analysis_review_card = InspectorSummaryCard("Review Focus")
        self._metadata_rows: dict[str, InspectorInfoRow] = {}
        self._modality_tag = QLabel("")
        self._pose_engine_button = CapsuleButton("Pose Engine", variant="danger", major=True)
        self._comparison_buttons: dict[str, CapsuleButton] = {
            slot: CapsuleButton("", variant="danger", major=True)
            for slot in COMPARISON_SLOT_LABELS
        }
        self._comparison_selector_strip = PoseEngineSelectorStrip(
            self._comparison_buttons["primary"],
            self._comparison_buttons["secondary"],
        )
        self._precision_kicker = QLabel("INFERENCE PRECISION")
        self._precision_strip = QWidget()
        self._precision_buttons: dict[InferencePrecisionTier, CapsuleButton] = {}
        self._active_precision_tier = DEFAULT_PRECISION_TIER
        self._turbo_mode_button = TurboModeButton(self._performance_coordinator.active_mode)
        self._analyze_button = AnalyzeProgressButton("Analyze")
        self._enforce_operator_segmentation_profile()

        super().__init__(
            "import",
            "Import",
            f"Case {manifest.case_id} · {manifest.patient_name}",
            settings,
            self._build_left_panel(),
            self._build_center_panel(),
            self._build_right_panel(),
            center_surface_padding=0,
        )

        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.timeout.connect(self._refresh_inspector_preview)

        self._connect_signals()
        self._refresh_all()

    def _build_left_panel(self) -> PanelFrame:
        panel = PanelFrame(
            "Cases",
            "Select a case, import images, then assign AP, LAT, and CT inputs.",
            settings=self._workspace_settings,
            workspace_id="import",
            panel_id="left",
        )
        panel.add_widget(self._cases_tree, stretch=2, title="Patient Explorer")

        patient_info = SidebarSection("Patient Info")
        patient_info.set_title_visible(False)
        for label_text, field_name in [
            ("Name", "patient_name"),
            ("Age / Sex", "age_and_sex"),
            ("Patient ID", "patient_id"),
            ("Diagnosis", "diagnosis"),
            ("Cobb Angle", "cobb_angle"),
        ]:
            row = QVBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            label = QLabel(label_text)
            apply_text_role(label, "meta")
            value = QLabel("")
            value.setWordWrap(True)
            apply_text_role(value, "body-emphasis")
            row.addWidget(label)
            row.addWidget(value)
            patient_info.content_layout.addLayout(row)
            self._patient_value_labels[field_name] = value
        panel.add_widget(patient_info, title="Patient Info")

        self._history_section.set_title_visible(False)
        panel.add_widget(self._history_section, title="Procedure History")

        self._import_drop_zone.setFixedHeight(GEOMETRY.major_button_height)
        self._import_drop_zone.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._images_section.content_layout.addWidget(self._import_drop_zone)
        self._images_section.content_layout.addWidget(self._asset_list)
        self._images_section.set_title_visible(False)
        self._images_section_container = panel.add_widget(
            self._images_section,
            stretch=3,
            title="Images (0)",
        )

        action_card = QFrame()
        action_card.setObjectName("InspectorActionCard")
        action_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._left_action_card = action_card
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        action_layout.setSpacing(GEOMETRY.inspector_row_gap)

        self._pose_engine_button.setObjectName("PoseEngineSelectorButton")
        self._pose_engine_button.setFixedHeight(GEOMETRY.major_button_height)
        self._pose_engine_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        action_layout.addWidget(self._pose_engine_button)

        for button in self._comparison_buttons.values():
            button.setObjectName("ComparisonSelectorButton")
            button.setFixedHeight(GEOMETRY.major_button_height)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._comparison_selector_strip.setObjectName("ComparisonSelectorStrip")
        action_layout.addWidget(self._comparison_selector_strip)

        self._precision_kicker.setObjectName("InferencePrecisionKicker")
        apply_text_role(self._precision_kicker, "micro")
        action_layout.addWidget(self._precision_kicker)

        _tier_variants = {
            InferencePrecisionTier.DRAFT: "warning",
            InferencePrecisionTier.STANDARD: "info",
            InferencePrecisionTier.QUALITY: "success",
        }
        precision_layout = QHBoxLayout(self._precision_strip)
        precision_layout.setContentsMargins(0, 0, 0, 0)
        precision_layout.setSpacing(GEOMETRY.unit // 2)
        for tier in InferencePrecisionTier:
            btn = CapsuleButton(
                tier.value.title(),
                variant=_tier_variants.get(tier, "ghost"),
                checkable=True,
                major=True,
            )
            btn.setChecked(tier == self._active_precision_tier)
            btn.clicked.connect(lambda _checked, t=tier: self._handle_precision_tier_clicked(t))
            precision_layout.addWidget(btn)
            self._precision_buttons[tier] = btn
        action_layout.addWidget(self._precision_strip)

        self._analyze_button.setObjectName("InspectorAnalyzeButton")
        self._analyze_button.setFixedHeight(GEOMETRY.analyze_button_height)
        self._analyze_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._analyze_button.setIcon(
            build_svg_icon(
                REPORT_ICON_PATH,
                major_button_icon_size(),
                device_pixel_ratio=self._analyze_button.devicePixelRatioF(),
                tint=THEME_COLORS.info,
            )
        )
        self._analyze_button.setIconSize(major_button_icon_size())

        analyze_row = QHBoxLayout()
        analyze_row.setContentsMargins(0, 0, 0, 0)
        analyze_row.setSpacing(GEOMETRY.inspector_row_gap)
        analyze_row.addWidget(self._turbo_mode_button)
        analyze_row.addWidget(self._analyze_button, 1)
        action_layout.addLayout(analyze_row)

        panel.outer_layout.addWidget(action_card)
        return panel

    def _build_center_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("PanelInner")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
        )
        frame_layout.setSpacing(GEOMETRY.viewport_gap)

        frame_layout.addWidget(self._build_center_toolbar())

        layout = TransparentSplitter(Qt.Orientation.Horizontal)
        xray_stack = TransparentSplitter(Qt.Orientation.Vertical)
        self._center_splitter = layout
        self._xray_stack_splitter = xray_stack
        layout.setHandleWidth(GEOMETRY.viewport_gap)
        xray_stack.setHandleWidth(GEOMETRY.viewport_gap)

        xray_stack.addWidget(NestedBubbleFrame(self._xray_ap_viewport))
        xray_stack.addWidget(NestedBubbleFrame(self._xray_lat_viewport))
        xray_stack.setStretchFactor(0, 1)
        xray_stack.setStretchFactor(1, 1)
        xray_stack.setSizes([1, 1])

        layout.addWidget(xray_stack)
        layout.addWidget(NestedBubbleFrame(self._ct_viewport))
        layout.setStretchFactor(0, 1)
        layout.setStretchFactor(1, 1)
        layout.setSizes([1, 1])
        schedule_splitter_midpoint(xray_stack)
        schedule_splitter_midpoint(layout)
        frame_layout.addWidget(layout, stretch=1)
        return frame

    def _build_center_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ImportViewportToolbar")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        title_label = QLabel("Z Stack")
        apply_text_role(title_label, "meta")
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(
            self._ct_viewport.slice_toolbar_group(),
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        return frame

    def _build_right_panel(self) -> PanelFrame:
        panel = PanelFrame(
            "Image Inspector",
            settings=self._workspace_settings,
            workspace_id="import",
            panel_id="right",
        )

        preview_frame = QFrame()
        preview_frame.setObjectName("InspectorPreviewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        preview_layout.addWidget(self._preview_label, stretch=1)
        preview_frame.setMinimumHeight(GEOMETRY.inspector_preview_height)
        panel.add_widget(preview_frame, stretch=2, title="Preview")

        viewport_frame = QFrame()
        viewport_frame.setObjectName("PanelInner")
        viewport_section = QVBoxLayout(viewport_frame)
        viewport_section.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        viewport_section.setSpacing(GEOMETRY.inspector_row_gap)

        apply_text_role(self._viewport_value_label, "panel-title")
        viewport_section.addWidget(self._viewport_value_label)
        self._empty_state_bubble.setObjectName("InspectorEmptyBubble")
        self._empty_state_bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state_bubble.setFixedSize(
            GEOMETRY.control_height_sm,
            GEOMETRY.control_height_sm,
        )
        self._empty_state_bubble.setToolTip("No images")
        self._empty_state_bubble.setPixmap(
            build_svg_pixmap(
                EMPTY_BUBBLE_ICON_PATH,
                QSize(12, 12),
                device_pixel_ratio=self._empty_state_bubble.devicePixelRatioF(),
            )
        )
        viewport_section.addWidget(self._empty_state_bubble)
        viewport_section.setAlignment(
            self._empty_state_bubble,
            Qt.AlignmentFlag.AlignLeft,
        )
        panel.add_widget(viewport_frame, title="Viewport")

        self._metadata_rows["filename"] = InspectorInfoRow(
            QStyle.StandardPixmap.SP_FileIcon,
            "Properties",
            compact=True,
        )
        self._metadata_rows["modality"] = InspectorInfoRow(
            QStyle.StandardPixmap.SP_DriveHDIcon,
            "Modality",
        )
        self._metadata_rows["acquisition_date"] = InspectorInfoRow(
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "Acquisition Date",
        )
        self._metadata_rows["file_size"] = InspectorInfoRow(
            QStyle.StandardPixmap.SP_MessageBoxInformation,
            "File Size",
        )
        self._metadata_rows["format"] = InspectorInfoRow(
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            "Format",
        )
        self._metadata_rows["resolution"] = InspectorInfoRow(
            QStyle.StandardPixmap.SP_ArrowRight,
            "Resolution",
        )
        self._metadata_rows["scale"] = InspectorInfoRow(
            QStyle.StandardPixmap.SP_BrowserReload,
            "Scale",
        )

        self._modality_tag.setObjectName("AssetTag")
        self._modality_tag.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._modality_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(self._modality_tag, "micro")
        modality_row = self._metadata_rows["modality"]
        modality_row.value_label.hide()
        modality_layout = modality_row.layout()
        if modality_layout is not None:
            modality_layout.addWidget(self._modality_tag)
            modality_layout.setAlignment(
                self._modality_tag,
                Qt.AlignmentFlag.AlignLeft,
            )

        metadata_card = QFrame()
        metadata_card.setObjectName("PanelInner")
        metadata_layout = QVBoxLayout(metadata_card)
        metadata_layout.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        metadata_layout.setSpacing(GEOMETRY.inspector_gap)
        for key in [
            "filename",
            "modality",
            "acquisition_date",
            "file_size",
            "format",
            "resolution",
            "scale",
        ]:
            metadata_layout.addWidget(self._metadata_rows[key])
        panel.add_widget(metadata_card, stretch=2, title="Metadata")

        analysis_card = QFrame()
        analysis_card.setObjectName("PanelInner")
        analysis_layout = QVBoxLayout(analysis_card)
        analysis_layout.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        analysis_layout.setSpacing(GEOMETRY.inspector_row_gap)
        analysis_layout.addWidget(self._analysis_status_card)
        analysis_layout.addWidget(self._analysis_review_card)
        panel.add_widget(analysis_card, title="Analysis")

        return panel

    def _connect_signals(self) -> None:
        self._cases_tree.itemSelectionChanged.connect(self._handle_case_tree_selection)
        self._cases_tree.customContextMenuRequested.connect(self._open_case_tree_context_menu)
        self._import_drop_zone.files_dropped.connect(self._import_into_library)
        self._import_drop_zone.browse_requested.connect(self._browse_library_files)

        self._xray_ap_viewport.files_dropped.connect(
            lambda paths: self._handle_viewport_files("xray_ap", paths)
        )
        self._xray_lat_viewport.files_dropped.connect(
            lambda paths: self._handle_viewport_files("xray_lat", paths)
        )
        self._ct_viewport.files_dropped.connect(
            lambda paths: self._handle_viewport_files("ct_stack", paths)
        )

        self._xray_ap_viewport.asset_dropped.connect(
            lambda asset_id: self._assign_existing_asset("xray_ap", asset_id)
        )
        self._xray_lat_viewport.asset_dropped.connect(
            lambda asset_id: self._assign_existing_asset("xray_lat", asset_id)
        )
        self._ct_viewport.asset_dropped.connect(
            lambda asset_id: self._assign_existing_asset("ct_stack", asset_id)
        )

        self._xray_ap_viewport.activated.connect(lambda: self._set_inspected_role("xray_ap"))
        self._xray_lat_viewport.activated.connect(lambda: self._set_inspected_role("xray_lat"))
        self._ct_viewport.activated.connect(lambda: self._set_inspected_role("ct_stack"))
        self._preview_label.resized.connect(self._schedule_inspector_preview_refresh)
        self._pose_engine_button.clicked.connect(self._open_analysis_pose_selector)
        for slot, button in self._comparison_buttons.items():
            button.clicked.connect(
                lambda checked=False, selected_slot=slot: self._open_comparison_selector(
                    selected_slot
                )
            )
        self._turbo_mode_button.mode_changed.connect(self._handle_turbo_mode_changed)
        self._analyze_button.clicked.connect(self._handle_analyze_requested)

    def _refresh_all(self) -> None:
        self._refresh_case_tree()
        self._refresh_patient_info()
        self._refresh_procedure_history()
        self._refresh_asset_list()
        self._refresh_viewports()
        self._refresh_inspector()
        self._refresh_analysis_cards()
        self._refresh_comparison_buttons()
        self._refresh_performance_mode_widget()

    def dispose(self) -> None:
        self._notify_analysis_status("", False)
        thread = self._analysis_thread
        if thread is not None:
            thread.blockSignals(True)
            thread.requestInterruption()
            if thread.isRunning():
                terminate_tracked_segmentation_processes(timeout_seconds=5.0)
                thread.wait(5000)
            if thread.isRunning():
                thread.terminate()
                thread.wait(2000)
            thread.deleteLater()
            self._analysis_thread = None
            self._analyze_button.reset_progress()
        self._cancel_lod_prewarm()
        super().dispose()

    def has_active_analysis(self) -> bool:
        return self._analysis_thread is not None

    def _refresh_case_tree(self) -> None:
        self._cases_tree.blockSignals(True)
        self._cases_tree.clear()
        tree_icon_size = QSize(14, 14)
        patient_icon = build_svg_icon(
            PATIENT_ICON_PATH,
            tree_icon_size,
            device_pixel_ratio=self._cases_tree.devicePixelRatioF(),
            tint=THEME_COLORS.text_secondary,
        )
        image_icon = build_svg_icon(
            CASE_IMAGE_ICON_PATH,
            tree_icon_size,
            device_pixel_ratio=self._cases_tree.devicePixelRatioF(),
            tint=THEME_COLORS.text_secondary,
        )
        current_case_ref = self._current_case_ref()
        current_item_to_select: QTreeWidgetItem | None = None
        saved_root = QTreeWidgetItem(["Saved Cases"])
        saved_root.setFlags(saved_root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self._cases_tree.addTopLevelItem(saved_root)

        retained_paths: list[Path] = []
        for package_path in self._workspace_settings.load_recent_case_paths():
            if not package_path.exists() or package_path.suffix.lower() != ".spine":
                continue
            try:
                package_summary = self._package_service.load_summary(package_path)
            except SpinePackageError:
                continue
            retained_paths.append(package_path)
            case_manifest = package_summary.to_case_manifest_stub()
            case_ref = str(package_path)
            item = build_case_tree_item(
                case_manifest,
                case_ref=case_ref,
                patient_icon=patient_icon,
                image_icon=image_icon,
                hidden=False,
            )
            saved_root.addChild(item)
            item.setExpanded(case_ref == current_case_ref and item.childCount() > 0)
            if case_ref == current_case_ref:
                current_item_to_select = item
        self._workspace_settings.save_recent_case_paths(retained_paths)
        saved_root.setExpanded(True)
        if current_item_to_select is not None:
            self._cases_tree.setCurrentItem(current_item_to_select)
        self._cases_tree.blockSignals(False)

    def _refresh_patient_info(self) -> None:
        age_and_sex = self._manifest.age_text
        if self._manifest.sex:
            age_and_sex = (
                f"{age_and_sex} / {self._manifest.sex}"
                if age_and_sex
                else self._manifest.sex
            )

        values = {
            "patient_name": self._manifest.patient_name or "Unassigned",
            "age_and_sex": age_and_sex or "Unassigned",
            "patient_id": self._manifest.patient_id or "Unassigned",
            "diagnosis": self._manifest.diagnosis or "Unassigned",
            "cobb_angle": self._manifest.cobb_angle or "Unassigned",
        }
        for field_name, value in values.items():
            self._patient_value_labels[field_name].setText(value)

    def _refresh_procedure_history(self) -> None:
        while self._history_section.content_layout.count():
            item = self._history_section.content_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        entries = self._manifest.procedure_history or ["No history"]
        for entry in entries:
            chip = QFrame()
            chip.setObjectName("PanelInner")
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(
                GEOMETRY.panel_padding,
                GEOMETRY.panel_padding,
                GEOMETRY.panel_padding,
                GEOMETRY.panel_padding,
            )
            chip_layout.setSpacing(GEOMETRY.unit)
            label = QLabel(entry)
            apply_text_role(label, "body")
            chip_layout.addWidget(label)
            self._history_section.content_layout.addWidget(chip)

    def _refresh_asset_list(self) -> None:
        image_assets = [asset for asset in self._manifest.assets if asset.kind != "mesh_3d"]
        self._images_section.set_title(f"Images ({len(image_assets)})")
        if self._images_section_container is not None:
            self._images_section_container.set_title(f"Images ({len(image_assets)})")
        self._asset_list.clear()
        allow_delete = self._store.case_is_editable(self._manifest.case_id)
        for asset in image_assets:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, asset.asset_id)
            row = AssetRowWidget(
                asset,
                delete_enabled=allow_delete,
                on_delete=self._build_delete_handler(asset.asset_id),
            )
            item.setSizeHint(row.sizeHint())
            self._asset_list.addItem(item)
            self._asset_list.setItemWidget(item, row)

    def _refresh_viewports(self) -> None:
        self._xray_ap_viewport.set_asset(self._manifest.get_asset_for_role("xray_ap"))
        self._xray_lat_viewport.set_asset(self._manifest.get_asset_for_role("xray_lat"))
        self._ct_viewport.set_asset(self._manifest.get_asset_for_role("ct_stack"))

    def _refresh_inspector(self) -> None:
        asset = self._manifest.get_asset_for_role(self._inspected_role)
        has_active_image = asset is not None
        self._viewport_value_label.setText(inspector_viewport_value(self._inspected_role))
        self._modality_tag.setText("")
        self._empty_state_bubble.setVisible(not has_active_image)

        self._refresh_inspector_preview()

        for row in self._metadata_rows.values():
            row.setVisible(has_active_image)

        if has_active_image:
            assert asset is not None
            filename = Path(asset.managed_path).name
            self._metadata_rows["filename"].value_label.setText(filename)
            self._modality_tag.setText(asset_badge_text(asset))
            self._modality_tag.setProperty("variant", asset_tag_variant(asset))
            refresh_widget_style(self._modality_tag)
            self._metadata_rows["acquisition_date"].value_label.setText(asset.created_at[:10])
            self._metadata_rows["file_size"].value_label.setText(format_file_size(asset))
            self._metadata_rows["format"].value_label.setText(format_asset_format(asset))
            self._metadata_rows["resolution"].value_label.setText(format_resolution(asset))
            self._metadata_rows["scale"].value_label.setText("1:1")

    def _refresh_comparison_buttons(self) -> None:
        pose_mode = resolved_analysis_pose_mode(self._manifest)
        required_slots = analysis_required_comparison_slots(pose_mode)
        can_edit_controls = self._analysis_thread is None
        selected_required_modalities: list[str] = []

        self._pose_engine_button.setText(pose_engine_button_text(pose_mode))
        self._pose_engine_button.setProperty("variant", pose_engine_button_variant(pose_mode))
        self._pose_engine_button.setEnabled(can_edit_controls)
        self._pose_engine_button.setIcon(
            build_svg_icon(
                COMPARISON_ICON_PATH,
                major_button_icon_size(),
                device_pixel_ratio=self._pose_engine_button.devicePixelRatioF(),
                tint=pose_engine_button_tint(pose_mode),
            )
        )
        self._pose_engine_button.setIconSize(major_button_icon_size())
        refresh_widget_style(self._pose_engine_button)

        for slot, button in self._comparison_buttons.items():
            modality = canonical_comparison_modality(
                self._manifest.comparison_modalities.get(slot)
            )
            if slot in required_slots and modality is not None:
                selected_required_modalities.append(modality)
            button.setText(comparison_button_text(slot, modality))
            button.setProperty("variant", comparison_button_variant(modality))
            button.setEnabled(can_edit_controls and slot in required_slots)
            button.setIcon(
                build_svg_icon(
                    COMPARISON_ICON_PATH,
                    major_button_icon_size(),
                    device_pixel_ratio=button.devicePixelRatioF(),
                    tint=comparison_button_tint(modality),
                )
            )
            button.setIconSize(major_button_icon_size())
            refresh_widget_style(button)
        self._comparison_selector_strip.set_mode(pose_mode)
        self._analyze_button.setEnabled(
            pose_mode is not None
            and len(selected_required_modalities) == len(required_slots)
            and can_edit_controls
        )
        self._analyze_button.setIcon(
            build_svg_icon(
                REPORT_ICON_PATH,
                major_button_icon_size(),
                device_pixel_ratio=self._analyze_button.devicePixelRatioF(),
                tint=(
                    THEME_COLORS.info
                    if self._analyze_button.isEnabled()
                    else THEME_COLORS.text_muted
                ),
            )
        )
        self._analyze_button.setIconSize(major_button_icon_size())

    def _enforce_operator_segmentation_profile(self) -> None:
        if self._manifest.segmentation_profile == DEFAULT_SEGMENTATION_PROFILE:
            return
        self._manifest.segmentation_profile = DEFAULT_SEGMENTATION_PROFILE
        if self._store.case_is_editable(self._manifest.case_id):
            self._store.save_manifest(self._manifest)

    def _handle_precision_tier_clicked(self, tier: InferencePrecisionTier) -> None:
        self._active_precision_tier = tier
        for t, btn in self._precision_buttons.items():
            btn.setChecked(t == tier)

    def _refresh_performance_mode_widget(self) -> None:
        self._turbo_mode_button.set_mode(self._performance_coordinator.active_mode)
        self._turbo_mode_button.setEnabled(self._analysis_thread is None)

    def _handle_turbo_mode_changed(self, mode_value: str) -> None:
        if self._analysis_thread is not None:
            self._refresh_performance_mode_widget()
            return
        self._performance_coordinator.set_mode(mode_value)
        self._refresh_performance_mode_widget()

    def _refresh_analysis_cards(self) -> None:
        status_title, status_detail = latest_completed_run(self._manifest)
        review_title, review_detail = import_review_summary(self._manifest)
        self._analysis_status_card.value_label.setText(f"{status_title}\n{status_detail}")
        self._analysis_review_card.value_label.setText(f"{review_title}\n{review_detail}")

    def _schedule_inspector_preview_refresh(self) -> None:
        self._preview_refresh_timer.start(0)

    def _refresh_inspector_preview(self) -> None:
        asset = self._manifest.get_asset_for_role(self._inspected_role)
        preview_image = self._build_inspector_preview(asset)
        self._preview_label.setPixmap(QPixmap.fromImage(preview_image))

    def _build_inspector_preview(self, asset: StudyAsset | None):
        preview_width = max(self._preview_label.width(), GEOMETRY.inspector_preview_width)
        preview_height = max(self._preview_label.height(), GEOMETRY.inspector_preview_height)
        if asset is None:
            title = inspector_viewport_label(self._inspected_role)
            return render_empty_placeholder(
                preview_width,
                preview_height,
                title,
                "Unassigned",
            )

        source_path = Path(asset.managed_path)
        if asset.kind == "ct_zstack":
            descriptor = describe_display_stack(source_path, render_mode="ct")
            slice_count = max(1, descriptor.slice_count) if descriptor is not None else 1
            slice_index = stack_preview_slice_index(slice_count)
            return render_loaded_ct_slice(
                preview_width,
                preview_height,
                source_path,
                slice_index,
                slice_count,
            )

        projection = (
            XrayProjection.AP if self._inspected_role == "xray_ap" else XrayProjection.LAT
        )
        return render_loaded_xray(preview_width, preview_height, source_path, projection)

    def _set_inspected_role(self, role: str) -> None:
        if self._inspected_role == role:
            return
        self._inspected_role = role
        self._refresh_inspector()

    def _open_comparison_selector(self, slot: str) -> None:
        button = self._comparison_buttons[slot]
        current_modality = canonical_comparison_modality(
            self._manifest.comparison_modalities.get(slot)
        )

        menu = QMenu(button)
        for modality_key, modality_label in COMPARISON_MODALITY_LABELS.items():
            action = menu.addAction(modality_label)
            action.setCheckable(True)
            action.setChecked(current_modality == modality_key)
            action.triggered.connect(
                lambda checked=False, selected_slot=slot, selected_modality=modality_key: (
                    self._set_comparison_modality(selected_slot, selected_modality)
                )
            )

        if current_modality is not None:
            menu.addSeparator()
            clear_action = menu.addAction("Clear selection")
            clear_action.triggered.connect(
                lambda checked=False, selected_slot=slot: self._set_comparison_modality(
                    selected_slot,
                    None,
                )
            )

        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _open_analysis_pose_selector(self) -> None:
        button = self._pose_engine_button
        current_mode = resolved_analysis_pose_mode(self._manifest)

        menu = QMenu(button)
        for mode_key, mode_label in ANALYSIS_POSE_MODE_LABELS.items():
            action = menu.addAction(f"{mode_label} Analysis")
            action.setCheckable(True)
            action.setChecked(current_mode == mode_key)
            action.triggered.connect(
                lambda checked=False, selected_mode=mode_key: self._set_analysis_pose_mode(
                    selected_mode
                )
            )

        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _set_analysis_pose_mode(self, mode: str | None) -> None:
        normalized_mode = canonical_analysis_pose_mode(mode) or ""
        if self._manifest.analysis_pose_mode == normalized_mode:
            return
        self._manifest.analysis_pose_mode = normalized_mode
        if self._store.case_is_editable(self._manifest.case_id):
            self._store.save_manifest(self._manifest)
        self._refresh_comparison_buttons()

    def _set_comparison_modality(self, slot: str, modality: str | None) -> None:
        normalized_modality = canonical_comparison_modality(modality)
        if normalized_modality is None:
            self._manifest.comparison_modalities.pop(slot, None)
        else:
            self._manifest.comparison_modalities[slot] = normalized_modality

        if self._store.case_is_editable(self._manifest.case_id):
            self._store.save_manifest(self._manifest)
        self._refresh_comparison_buttons()

    def _handle_case_tree_selection(self) -> None:
        item = self._cases_tree.currentItem()
        if item is None:
            return
        case_id = item.data(0, CASE_TREE_REF_ROLE)
        current_case_ref = self._current_case_ref()
        if isinstance(case_id, str) and case_id != current_case_ref:
            self._on_case_selected(case_id)

    def _open_case_tree_context_menu(self, position) -> None:
        item = self._cases_tree.itemAt(position)
        if item is None:
            return
        case_ref = item.data(0, CASE_TREE_REF_ROLE)
        if not isinstance(case_ref, str):
            return

        menu = QMenu(self._cases_tree)
        remove_action = menu.addAction("Remove from Explorer")
        remove_action.triggered.connect(
            lambda checked=False, selected_case_ref=case_ref: (
                self._remove_case_from_explorer(selected_case_ref)
            )
        )
        menu.exec(self._cases_tree.viewport().mapToGlobal(position))

    def _current_case_ref(self) -> str | None:
        active_session = self._store.active_session
        if active_session is None or active_session.saved_package_path is None:
            return None
        return str(active_session.saved_package_path)

    def _remove_case_from_explorer(self, case_ref: str) -> None:
        response = QMessageBox.question(
            self,
            "Remove Case from Explorer",
            (
                "This removes the saved case package from Patient Explorer only. "
                "The `.spine` file stays on disk.\n\nContinue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        self._workspace_settings.remove_recent_case_path(Path(case_ref))
        self._refresh_case_tree()

    def _browse_library_files(self) -> None:
        self._import_drop_zone.set_busy(True, tint=THEME_COLORS.info)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import medical images",
            str(Path.home()),
            FILE_DIALOG_FILTER,
        )
        try:
            if file_paths:
                self._import_into_library([Path(path) for path in file_paths])
        finally:
            self._import_drop_zone.set_busy(False)

    def _import_into_library(self, paths: list[Path]) -> None:
        auto_assigned_roles: list[str] = []
        for path in normalize_import_paths(paths):
            asset = self._store.import_asset(self._manifest, path)
            role = self._auto_assign_imported_asset(asset)
            if role is not None:
                auto_assigned_roles.append(role)
        if (
            auto_assigned_roles
            and self._manifest.get_asset_for_role(self._inspected_role) is None
        ):
            self._inspected_role = auto_assigned_roles[0]
        self._refresh_case_tree()
        self._refresh_asset_list()
        self._refresh_viewports()
        self._refresh_inspector()
        self._refresh_comparison_buttons()

    def _handle_viewport_files(self, role: str, paths: list[Path]) -> None:
        imported_asset = self._import_for_role(role, normalize_import_paths(paths))
        if imported_asset is None:
            return
        self._manifest.assign_asset_to_role(imported_asset.asset_id, role)
        self._store.save_manifest(self._manifest)
        self._inspected_role = role
        self._refresh_case_tree()
        self._refresh_asset_list()
        self._refresh_viewports()
        self._refresh_inspector()
        self._refresh_comparison_buttons()

    def _assign_existing_asset(self, role: str, asset_id: str) -> None:
        asset = self._manifest.assign_asset_to_role(asset_id, role)
        if asset is None:
            return
        self._store.save_manifest(self._manifest)
        self._inspected_role = role
        self._refresh_asset_list()
        self._refresh_viewports()
        self._refresh_inspector()
        self._refresh_comparison_buttons()

    def _delete_asset(self, asset_id: str) -> None:
        asset = self._manifest.get_asset(asset_id)
        if asset is None:
            return
        if not self._store.case_is_editable(self._manifest.case_id):
            QMessageBox.information(
                self,
                "Delete Image",
                "This Case is read-only, so its source images cannot be deleted.",
            )
            return
        self._store.delete_asset(self._manifest, asset_id)
        if self._inspected_role == asset.processing_role:
            self._inspected_role = "xray_ap"
        self._refresh_case_tree()
        self._refresh_asset_list()
        self._refresh_viewports()
        self._refresh_inspector()
        self._refresh_comparison_buttons()

    def _handle_analyze_requested(self) -> None:
        if (
            not self._analyze_button.isEnabled()
            or self._analysis_thread is not None
        ):
            return
        self._enforce_operator_segmentation_profile()
        params = PRECISION_TIER_PARAMS[self._active_precision_tier]
        self._analysis_failed = False
        self._analysis_progress_percent = 0.0
        self._analyze_button.set_progress_percent(0, active=True, spinner_active=True)
        self._notify_analysis_status("Preparing analysis", True)
        self._precision_strip.setEnabled(False)
        thread = AnalyzeCaseThread(
            pipeline=self._pipeline,
            manifest=self._manifest,
            disable_tta=params.disable_tta,
            tile_step_size=params.tile_step_size,
        )
        self._analysis_thread = thread
        self._refresh_performance_mode_widget()
        self._refresh_comparison_buttons()
        thread.progress_changed.connect(self._handle_analysis_progress_changed)
        thread.completed.connect(self._handle_analysis_completed)
        thread.failed.connect(self._handle_analysis_failed)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._handle_analysis_thread_finished)
        thread.start()

    def _handle_analysis_progress_changed(self, update: AnalysisProgressUpdate) -> None:
        self._analysis_progress_percent = update.percent
        self._analyze_button.set_progress_percent(
            update.percent,
            active=True,
            spinner_active=True,
        )
        self._analyze_button.update_progress_eta(update.percent)
        self._notify_analysis_status(
            format_analysis_progress_status(update), True, update.percent,
        )

    def _handle_analysis_completed(self, manifest: CaseManifest) -> None:
        self._notify_analysis_status("Preparing review scene", True)
        self._cancel_lod_prewarm()
        self._manifest = manifest
        self._enforce_operator_segmentation_profile()
        self._refresh_all()
        self._start_lod_prewarm(models_for_manifest(self._manifest))
        self._notify_analysis_status("", False)
        callback = self._on_manifest_updated
        if callback is not None:
            QTimer.singleShot(0, lambda: callback(self._manifest))

    def _handle_analysis_failed(self, message: str) -> None:
        self._analysis_failed = True
        self._analyze_button.set_spinner_active(False)
        QMessageBox.critical(
            self,
            "Analyze Case",
            f"Unable to complete analysis.\n\n{message}",
        )

    def _handle_analysis_thread_finished(self) -> None:
        self._analysis_thread = None
        self._precision_strip.setEnabled(True)
        self._refresh_performance_mode_widget()
        self._refresh_comparison_buttons()
        if not self._analysis_failed:
            self._analyze_button.reset_progress()
            self._analysis_progress_percent = 0.0

    def _start_lod_prewarm(self, models) -> None:
        if not models:
            return
        max_workers = self._performance_coordinator.active_policy.lod_prewarm_workers
        if current_qt_platform_name() in {"offscreen", "minimal"}:
            prewarm_lod_mesh_cache(
                models,
                detail_levels=tuple(level for _label, level in DETAIL_PRESET_LEVELS),
                max_workers=max_workers,
            )
            return
        thread = LODPrewarmThread(
            models=models,
            detail_levels=tuple(level for _label, level in DETAIL_PRESET_LEVELS),
            max_workers=max_workers,
        )
        self._lod_prewarm_thread = thread
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._handle_lod_prewarm_finished)
        thread.start()

    def _cancel_lod_prewarm(self) -> None:
        thread = self._lod_prewarm_thread
        if thread is None:
            return
        thread.blockSignals(True)
        thread.requestInterruption()
        thread.quit()
        thread.wait(50)
        thread.deleteLater()
        self._lod_prewarm_thread = None

    def _handle_lod_prewarm_finished(self) -> None:
        self._lod_prewarm_thread = None

    def _notify_analysis_status(
        self, text: str, active: bool, percent: float = 0.0,
    ) -> None:
        callback = self._on_analysis_status_changed
        if callback is not None:
            callback(text, active, percent)

    def _auto_assign_imported_asset(self, asset: StudyAsset) -> str | None:
        role = suggested_import_role(self._manifest, asset)
        if role is None:
            return None
        assigned = self._manifest.assign_asset_to_role(asset.asset_id, role)
        if assigned is None:
            return None
        self._store.save_manifest(self._manifest)
        return role

    def _build_delete_handler(self, asset_id: str) -> Callable[[], None]:
        def handle_delete() -> None:
            self._delete_asset(asset_id)

        return handle_delete

    def _import_for_role(self, role: str, paths: list[Path]) -> StudyAsset | None:
        if not paths:
            return None
        if role == "ct_stack":
            if len(paths) > 1 and all(path.is_file() for path in paths):
                return self._store.import_stack(self._manifest, paths, label="CT")
            if paths[0].is_dir():
                return self._store.import_asset(
                    self._manifest,
                    paths[0],
                    kind="ct_zstack",
                    label="CT",
                )
            return self._store.import_asset(
                self._manifest,
                paths[0],
                kind="ct_zstack",
                label="CT",
            )

        source_path = coerce_single_image_path(paths[0])
        if source_path is None:
            return None
        return self._store.import_asset(
            self._manifest,
            source_path,
            kind="xray_2d",
            label="X-Ray",
        )


def build_case_tree_item(
    manifest: CaseManifest,
    *,
    case_ref: str,
    patient_icon,
    image_icon,
    hidden: bool,
) -> QTreeWidgetItem:
    item = QTreeWidgetItem([case_tree_patient_label(manifest)])
    item.setIcon(0, patient_icon)
    item.setData(0, CASE_TREE_REF_ROLE, case_ref)
    item.setData(0, CASE_TREE_HIDDEN_ROLE, hidden)
    append_case_tree_assets(item, manifest, image_icon)
    return item


def normalize_import_paths(paths: list[Path]) -> list[Path]:
    unique_paths: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    return unique_paths


def coerce_single_image_path(source_path: Path) -> Path | None:
    if source_path.is_file():
        return source_path
    if not source_path.is_dir():
        return None
    files = sorted(
        [path for path in source_path.iterdir() if path.is_file()],
        key=lambda path: path.name.lower(),
    )
    return files[0] if files else None


def suggested_import_role(manifest: CaseManifest, asset: StudyAsset) -> str | None:
    if asset.kind == "ct_zstack":
        if manifest.get_asset_for_role("ct_stack") is None:
            return "ct_stack"
        return None
    if asset.kind != "xray_2d":
        return None
    projection_role = infer_xray_role_for_import(asset)
    if projection_role is None:
        return None
    if manifest.get_asset_for_role(projection_role) is not None:
        return None
    return projection_role


def infer_xray_role_for_import(asset: StudyAsset) -> str | None:
    for candidate in (
        Path(asset.source_path),
        Path(asset.managed_path),
    ):
        projection_role = _infer_projection_role_from_name(candidate.name)
        if projection_role is not None:
            return projection_role
    for candidate in (
        Path(asset.source_path),
        Path(asset.managed_path),
    ):
        projection_role = _infer_projection_role_from_metadata(candidate)
        if projection_role is not None:
            return projection_role
    return None


def _infer_projection_role_from_name(name: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower())
    tokens = set(normalized.split())
    if tokens & _PROJECTION_LAT_TOKENS:
        return "xray_lat"
    if tokens & _PROJECTION_AP_TOKENS:
        return "xray_ap"
    return None


def _infer_projection_role_from_metadata(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        dataset = pydicom.dcmread(
            str(path),
            stop_before_pixels=True,
            force=True,
            specific_tags=list(_DICOM_PROJECTION_FIELDS),
        )
    except (InvalidDicomError, OSError):
        return None
    for field_name in _DICOM_PROJECTION_FIELDS:
        value = getattr(dataset, field_name, None)
        if value is None:
            continue
        projection_role = _infer_projection_role_from_name(str(value))
        if projection_role is not None:
            return projection_role
    return None


def canonical_comparison_modality(modality: str | None) -> str | None:
    if modality is None:
        return None
    normalized = modality.strip().lower().replace("-", "")
    if normalized in COMPARISON_MODALITY_LABELS:
        return normalized
    return None


def canonical_analysis_pose_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    normalized = mode.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if normalized in {"single", "singlepose"}:
        return "single"
    if normalized in {"dual", "dualpose"}:
        return "dual"
    return None


def resolved_analysis_pose_mode(manifest: CaseManifest) -> str | None:
    explicit_mode = canonical_analysis_pose_mode(manifest.analysis_pose_mode)
    if explicit_mode is not None:
        return explicit_mode
    if canonical_comparison_modality(manifest.comparison_modalities.get("secondary")) is not None:
        return "dual"
    if canonical_comparison_modality(manifest.comparison_modalities.get("primary")) is not None:
        return "single"
    return None


def analysis_required_comparison_slots(mode: str | None) -> tuple[str, ...]:
    normalized_mode = canonical_analysis_pose_mode(mode)
    if normalized_mode == "single":
        return ("primary",)
    if normalized_mode == "dual":
        return ("primary", "secondary")
    return ()


def pose_engine_button_text(mode: str | None) -> str:
    normalized_mode = canonical_analysis_pose_mode(mode)
    if normalized_mode is None:
        return "Pose Engine"
    return f"Pose Engine: {ANALYSIS_POSE_MODE_LABELS[normalized_mode]}"


def pose_engine_button_variant(mode: str | None) -> str:
    return "success" if canonical_analysis_pose_mode(mode) is not None else "danger"


def pose_engine_button_tint(mode: str | None) -> str:
    return (
        THEME_COLORS.success
        if canonical_analysis_pose_mode(mode) is not None
        else THEME_COLORS.danger
    )


def comparison_button_text(slot: str, modality: str | None) -> str:
    del modality
    slot_label = COMPARISON_SLOT_LABELS.get(slot, slot.title())
    return slot_label


def comparison_button_variant(modality: str | None) -> str:
    return "success" if canonical_comparison_modality(modality) is not None else "danger"


def asset_tag_variant(asset: StudyAsset) -> str:
    if asset.kind == "ct_zstack":
        return "ct"
    if asset.kind == "mri_2d" or asset.label.upper() == "MRI":
        return "mri"
    if asset.kind == "mesh_3d":
        return "model"
    return "xray"


def asset_badge_text(asset: StudyAsset) -> str:
    if asset.kind == "ct_zstack":
        return "CT"
    if asset.kind == "mri_2d" or asset.label.upper() == "MRI":
        return "MRI"
    if asset.kind == "mesh_3d":
        return "Model"
    return "X-Ray"


def inspector_viewport_label(role: str) -> str:
    return ROLE_LABELS[role]


def inspector_viewport_value(role: str) -> str:
    if role == "xray_ap":
        return "AP"
    if role == "xray_lat":
        return "LAT"
    return "CT"


def format_file_size(asset: StudyAsset) -> str:
    path = Path(asset.managed_path)
    total_bytes = 0
    if path.is_dir():
        for file_path in path.rglob("*"):
            if file_path.is_file():
                total_bytes += file_path.stat().st_size
    elif path.exists():
        total_bytes = path.stat().st_size
    if total_bytes <= 0:
        return "N/A"
    if total_bytes < 1024 * 1024:
        return f"{total_bytes / 1024:.1f} KB"
    return f"{total_bytes / (1024 * 1024):.1f} MB"


def format_asset_format(asset: StudyAsset) -> str:
    path = Path(asset.managed_path)
    if path.is_dir():
        slice_paths = resolve_slice_sources(path)
        if slice_paths:
            first_suffix = "".join(slice_paths[0].suffixes).lower()
            if first_suffix == ".dcm":
                return "DICOM"
            return first_suffix.lstrip(".").upper() or "STACK"
        return "STACK"
    suffix = "".join(path.suffixes).lower()
    if suffix == ".dcm":
        return "DICOM"
    return suffix.lstrip(".").upper() or "UNKNOWN"


def format_resolution(asset: StudyAsset) -> str:
    path = Path(asset.managed_path)
    if path.is_dir():
        slice_paths = resolve_slice_sources(path)
        if not slice_paths:
            return "N/A"
        image_reader = QImageReader(str(slice_paths[0]))
        size = image_reader.size()
        if not size.isValid():
            return "N/A"
        slice_count = len(slice_paths)
        slice_label = "slice" if slice_count == 1 else "slices"
        return f"{size.width()} × {size.height()} · {slice_count} {slice_label}"
    image_reader = QImageReader(str(path))
    size = image_reader.size()
    if size.isValid():
        return f"{size.width()} × {size.height()}"
    return "N/A"


def refresh_widget_style(widget: QFrame | QLabel | CapsuleButton) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def case_tree_patient_label(manifest: CaseManifest) -> str:
    patient_name = manifest.patient_name.strip() or "Untitled Case"
    return f"{patient_name} ({manifest.case_id})"


def append_case_tree_assets(
    parent_item: QTreeWidgetItem,
    manifest: CaseManifest,
    image_icon,
) -> None:
    for asset in manifest.assets:
        asset_item = QTreeWidgetItem([case_tree_asset_label(asset)])
        asset_item.setIcon(0, image_icon)
        asset_item.setFlags(asset_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        parent_item.addChild(asset_item)


def case_tree_asset_label(asset: StudyAsset) -> str:
    role_label = case_tree_asset_role(asset.processing_role)
    file_name = Path(asset.managed_path).name
    if role_label is not None:
        return f"{role_label} · {file_name}"
    return file_name


def case_tree_asset_role(role: str | None) -> str | None:
    if role == "xray_ap":
        return "AP"
    if role == "xray_lat":
        return "Lat"
    if role == "ct_stack":
        return "CT"
    return None


def comparison_button_tint(modality: str | None) -> str:
    return (
        THEME_COLORS.success
        if canonical_comparison_modality(modality) is not None
        else THEME_COLORS.danger
    )


def build_asset_thumbnail(asset: StudyAsset) -> QPixmap:
    preview_width = 56
    preview_height = 56
    source_path = Path(asset.managed_path)

    if asset.kind == "ct_zstack":
        descriptor = describe_display_stack(source_path, render_mode="ct")
        slice_count = max(1, descriptor.slice_count) if descriptor is not None else 1
        slice_index = stack_preview_slice_index(slice_count)
        image = render_loaded_ct_slice(
            preview_width,
            preview_height,
            source_path,
            slice_index,
            slice_count,
        )
        return QPixmap.fromImage(image)

    image = render_loaded_xray(
        preview_width,
        preview_height,
        source_path,
        infer_asset_projection(asset),
    )
    return QPixmap.fromImage(image)


def infer_asset_projection(asset: StudyAsset) -> XrayProjection:
    role = (asset.processing_role or "").lower()
    file_name = Path(asset.managed_path).name.lower()
    if role == "xray_lat" or "lat" in file_name or "lateral" in file_name:
        return XrayProjection.LAT
    return XrayProjection.AP


def ct_preview_slice_index(slice_count: int) -> int:
    return stack_preview_slice_index(slice_count)
